using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading.Channels;
using SkiaSharp;
using VidaStudio.Models;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// Orchestrates the entire native C# rendering pipeline.
/// Uses SkiaSharp for GPU-accelerated drawing and pipes raw YUV frames to FFmpeg.
/// Replaces the Python renderer.py backend.
/// </summary>
public sealed class NativeVideoRenderer : IDisposable
{
    private readonly int _width;
    private readonly int _height;
    private readonly int _fps;
    private readonly string _audioPath;
    private readonly string _outputPath;
    private readonly string _theme;
    private readonly string _paletteName;
    private readonly string _songTitle;
    private readonly string _artistName;
    private readonly string _fontName;
    private readonly string? _logoPath;
    private readonly List<LyricLine> _lyrics;
    
    private SKBitmap? _bgBitmap;
    private Process? _ffmpegProcess;
    
    // Components
    private AudioAnalyzer? _analyzer;
    private ThemeRenderer? _themeRenderer;
    private LyricRenderer? _lyricRenderer;
    private ParticleSystem? _particles;

    public NativeVideoRenderer(
        string audioPath, string outputPath, int width = 1920, int height = 1080, int fps = 60,
        string theme = "ocean_wave", string palette = "cyberpunk", string? bgImagePath = null,
        string? logoPath = null, string songTitle = "", string artistName = "",
        List<LyricLine>? lyrics = null, string fontName = "Leelawadee UI")
    {
        _audioPath = audioPath;
        _outputPath = outputPath;
        _width = width;
        _height = height;
        _fps = fps;
        _theme = theme;
        _paletteName = palette;
        _songTitle = songTitle;
        _artistName = artistName;
        _fontName = fontName;
        _logoPath = logoPath;
        _lyrics = lyrics ?? new List<LyricLine>();

        if (!string.IsNullOrEmpty(bgImagePath) && File.Exists(bgImagePath))
        {
            try { _bgBitmap = SKBitmap.Decode(bgImagePath); }
            catch { /* Ignore */ }
        }
    }

    public async Task RenderAsync(Action<RenderProgress> progressCallback, CancellationToken cancellationToken)
    {
        // 1. Analyze Audio
        progressCallback(new RenderProgress(0, 0, "Analyzing audio...", 0));
        var (audioData, sr, duration) = AudioAnalyzer.DecodeAudio(_audioPath);
        _analyzer = new AudioAnalyzer(audioData, sr, _fps);
        var analysis = _analyzer.Analyze();

        int totalFrames = analysis.TotalFrames;
        
        // 2. Initialize Renderers
        _themeRenderer = new ThemeRenderer(_width, _height);
        _lyricRenderer = new LyricRenderer(_width, _height, _fontName);
        if (!string.IsNullOrEmpty(_logoPath))
        {
            _lyricRenderer.LoadLogo(_logoPath);
        }
        
        _particles = new ParticleSystem(80, _width, _height);
        var palette = ColorPalettes.Get(_paletteName);
        var priColor = new SKColor(palette.Primary.R, palette.Primary.G, palette.Primary.B);

        // 3. Setup SkiaSharp Surface
        var info = new SKImageInfo(_width, _height, SKColorType.Rgba8888, SKAlphaType.Premul);
        using var surface = SKSurface.Create(info);
        var canvas = surface.Canvas;

        // 4. Start FFmpeg Pipe
        StartFfmpegPipe();
        using var pipeStream = _ffmpegProcess!.StandardInput.BaseStream;

        int ySize = _width * _height;
        int uvSize = ySize / 4;
        
        // Use an unbounded channel (producer/consumer queue) for writing frames to FFmpeg in the background
        // This prevents the render thread from waiting for FFmpeg.
        var frameChannel = Channel.CreateUnbounded<byte[]>();

        var sw = Stopwatch.StartNew();

        // Start background writer task
        var writerTask = Task.Run(async () =>
        {
            await foreach (var frame in frameChannel.Reader.ReadAllAsync(cancellationToken))
            {
                await pipeStream.WriteAsync(frame.AsMemory(), cancellationToken);
            }
        });

        // Audio data for current frame buffer
        float[] spec = new float[analysis.Spectrum.GetLength(1)];

        // 5. Render Loop
        for (int fIdx = 0; fIdx < totalFrames; fIdx++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            float tCurrent = (float)fIdx / _fps;
            
            for(int i=0; i<spec.Length; i++) spec[i] = analysis.Spectrum[fIdx, i];
            float bass = analysis.Bass[fIdx];
            float onset = analysis.Onsets[fIdx];

            canvas.Clear(SKColors.Black);

            // Draw Background (Static or solid color)
            if (_bgBitmap != null)
            {
                var dest = new SKRect(0, 0, _width, _height);
                using var bgPaint = new SKPaint();
                using var cf = SKColorFilter.CreateBlendMode(SKColors.Black.WithAlpha(150), SKBlendMode.Darken);
                bgPaint.ColorFilter = cf;
                canvas.DrawBitmap(_bgBitmap, dest, bgPaint);
            }
            else
            {
                canvas.Clear(new SKColor(5, 8, 15)); // Deep dark blue base
            }

            // Draw Particles
            _particles.UpdateAndDraw(canvas, bass, onset, priColor);

            // Draw Theme Visualizer
            _themeRenderer.Render(canvas, _theme, spec, bass, onset, tCurrent, palette);

            // Draw Lyrics and UI
            _lyricRenderer.Render(canvas, tCurrent, _songTitle, _artistName, _lyrics, palette);

            // 6. Read Pixels and Convert to YUV420p
            canvas.Flush();
            using var pixmap = surface.PeekPixels();
            
            // Allocate a new frame buffer for the queue
            byte[] yuvFrame = new byte[ySize + uvSize * 2];
            ConvertToYuv420p(pixmap, yuvFrame);

            // 7. Write to Queue (Instant return)
            frameChannel.Writer.TryWrite(yuvFrame);

            // 8. Progress Reporting
            if (fIdx % 15 == 0 || fIdx == totalFrames - 1)
            {
                double pct = (double)(fIdx + 1) / totalFrames * 100.0;
                double elapsed = sw.Elapsed.TotalSeconds;
                double currentFps = (fIdx + 1) / Math.Max(0.1, elapsed);
                double eta = (totalFrames - (fIdx + 1)) / Math.Max(0.1, currentFps);

                progressCallback(new RenderProgress(
                    pct, 
                    fIdx + 1, 
                    $"Rendering... ({currentFps:F1} fps)", 
                    (int)eta
                ));
            }
        }

        // Close channel and wait for the writer to flush everything to FFmpeg
        frameChannel.Writer.Complete();
        await writerTask;

        // Close pipe to finish encoding
        pipeStream.Close();
        await _ffmpegProcess.WaitForExitAsync(cancellationToken);
        
        if (_ffmpegProcess.ExitCode != 0)
        {
            throw new Exception($"FFmpeg failed with exit code {_ffmpegProcess.ExitCode}");
        }
    }

    private void StartFfmpegPipe()
    {
        string ffmpegExe = "ffmpeg";
        string venvFfmpeg = System.IO.Path.Combine(BackendService.Instance.GetProjectRoot(), "venv", "Scripts", "ffmpeg.exe");
        if (System.IO.File.Exists(venvFfmpeg)) ffmpegExe = venvFfmpeg;
        else if (System.IO.File.Exists(@"C:\ffmpeg\bin\ffmpeg.exe")) ffmpegExe = @"C:\ffmpeg\bin\ffmpeg.exe";
        string args = $"-y -f rawvideo -vcodec rawvideo -s {_width}x{_height} -pix_fmt yuv420p -r {_fps} " +
                      $"-i - -i \"{_audioPath}\" " +
                      $"-c:v libx264 -preset ultrafast -crf 20 " +
                      $"-c:a aac -b:a 192k -shortest " +
                      $"\"{_outputPath}\"";

        var psi = new ProcessStartInfo
        {
            FileName = ffmpegExe,
            Arguments = args,
            RedirectStandardInput = true,
            RedirectStandardError = true, // FFmpeg writes logs to stderr
            UseShellExecute = false,
            CreateNoWindow = true
        };

        _ffmpegProcess = Process.Start(psi) ?? throw new Exception("Failed to start FFmpeg");
        
        // Discard stderr to prevent blocking
        _ffmpegProcess.ErrorDataReceived += (s, e) => { /* Optionally log e.Data */ };
        _ffmpegProcess.BeginErrorReadLine();
    }

    /// <summary>
    /// Fast unsafe RGB to YUV420p conversion. 
    /// Skia returns RGBA, FFmpeg expects YUV420p planes.
    /// </summary>
    private unsafe void ConvertToYuv420p(SKPixmap pixmap, byte[] yuvOutput)
    {
        int width = pixmap.Width;
        int height = pixmap.Height;
        int ySize = width * height;
        
        byte* srcPtr = (byte*)pixmap.GetPixels().ToPointer();
        
        fixed (byte* dstPtr = yuvOutput)
        {
            byte* yPlane = dstPtr;
            byte* uPlane = dstPtr + ySize;
            byte* vPlane = dstPtr + ySize + (ySize / 4);

            // Parallel processing for YUV conversion (massive speedup on large frames)
            Parallel.For(0, height, y =>
            {
                byte* rowSrc = srcPtr + y * pixmap.RowBytes;
                int yDstOffset = y * width;
                int uvDstOffset = (y / 2) * (width / 2);

                for (int x = 0; x < width; x++)
                {
                    byte r = rowSrc[x * 4 + 0];
                    byte g = rowSrc[x * 4 + 1];
                    byte b = rowSrc[x * 4 + 2];

                    int yVal = ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16;
                    yPlane[yDstOffset + x] = yVal < 0 ? (byte)0 : (yVal > 255 ? (byte)255 : (byte)yVal);

                    if (y % 2 == 0 && x % 2 == 0)
                    {
                        int uVal = ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128;
                        int vVal = ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128;
                        
                        uPlane[uvDstOffset + (x / 2)] = uVal < 0 ? (byte)0 : (uVal > 255 ? (byte)255 : (byte)uVal);
                        vPlane[uvDstOffset + (x / 2)] = vVal < 0 ? (byte)0 : (vVal > 255 ? (byte)255 : (byte)vVal);
                    }
                }
            });
        }
    }

    public void Dispose()
    {
        _bgBitmap?.Dispose();
        
        if (_ffmpegProcess != null && !_ffmpegProcess.HasExited)
        {
            try { _ffmpegProcess.Kill(); } catch { }
            _ffmpegProcess.Dispose();
        }
    }
}

public record RenderProgress(double Percent, int CurrentFrame, string Status, int EtaSeconds);
