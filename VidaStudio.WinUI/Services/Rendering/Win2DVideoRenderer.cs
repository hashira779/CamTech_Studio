using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Text;
using Windows.UI;
using Microsoft.UI;
using VidaStudio.Models;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// Ultra-fast DirectX/Win2D Video Renderer.
/// Replaces CPU SkiaSharp with hardware GPU rendering.
/// </summary>
public sealed class Win2DVideoRenderer : IDisposable
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
    private readonly List<LyricLine> _lyrics;
    private readonly string? _bgImagePath;
    private readonly string? _logoPath;
    
    private Process? _ffmpegProcess;

    public Win2DVideoRenderer(
        string audioPath, string outputPath, int width, int height, int fps,
        string theme, string paletteName, string? bgImagePath, string? logoPath,
        string songTitle, string artistName, List<LyricLine>? lyrics, string fontName)
    {
        _audioPath = audioPath;
        _outputPath = outputPath;
        _width = width;
        _height = height;
        _fps = fps;
        _theme = theme;
        _paletteName = paletteName;
        _bgImagePath = bgImagePath;
        _logoPath = logoPath;
        _songTitle = songTitle;
        _artistName = artistName;
        _lyrics = lyrics ?? new List<LyricLine>();
        _fontName = fontName;
    }

    public async Task RenderAsync(Action<RenderProgress> progressCallback, CancellationToken cancellationToken)
    {
        progressCallback(new RenderProgress(0, 0, "Initializing DirectX GPU Engine...", 0));

        // 1. Audio Analysis
        var (data, sr, duration) = await Task.Run(() => AudioAnalyzer.DecodeAudio(_audioPath));
        var analyzer = new AudioAnalyzer(data, sr, _fps);
        var analysis = await Task.Run(() => analyzer.Analyze());
        int totalFrames = analysis.Spectrum.GetLength(0);

        // 2. Setup DirectX Win2D Surface
        var device = CanvasDevice.GetSharedDevice();
        using var renderTarget = new CanvasRenderTarget(device, _width, _height, 96);

        CanvasBitmap? bgBitmap = null;
        if (!string.IsNullOrEmpty(_bgImagePath) && File.Exists(_bgImagePath))
        {
            try { bgBitmap = await CanvasBitmap.LoadAsync(device, _bgImagePath); } catch { }
        }

        CanvasBitmap? logoBitmap = null;
        if (!string.IsNullOrEmpty(_logoPath) && File.Exists(_logoPath))
        {
            try { logoBitmap = await CanvasBitmap.LoadAsync(device, _logoPath); } catch { }
        }

        // 3. Start FFmpeg pipe
        StartFfmpegPipe();
        using var pipeStream = _ffmpegProcess!.StandardInput.BaseStream;
        int frameByteCount = _width * _height * 4;

        var frameChannel = Channel.CreateBounded<byte[]>(new BoundedChannelOptions(15) { FullMode = BoundedChannelFullMode.Wait });

        var writerTask = Task.Run(async () =>
        {
            await foreach (var frame in frameChannel.Reader.ReadAllAsync(cancellationToken))
            {
                await pipeStream.WriteAsync(frame.AsMemory(0, frameByteCount), cancellationToken);
                System.Buffers.ArrayPool<byte>.Shared.Return(frame);
            }
        });

        // 4. Colors
        var p = ColorPalettes.Get(_paletteName);
        var primaryColor = Color.FromArgb(255, p.Primary.R, p.Primary.G, p.Primary.B);
        var secondaryColor = Color.FromArgb(255, p.Secondary.R, p.Secondary.G, p.Secondary.B);

        // 5. Render Loop
        var sw = Stopwatch.StartNew();
        for (int fIdx = 0; fIdx < totalFrames; fIdx++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            
            float bass = analysis.Bass[fIdx];
            float onset = analysis.Onsets[fIdx];
            float tCurrent = (float)fIdx / _fps;

            using (var ds = renderTarget.CreateDrawingSession())
            {
                ds.Clear(Color.FromArgb(255, 10, 10, 15));

                if (bgBitmap != null)
                {
                    ds.DrawImage(bgBitmap, new Windows.Foundation.Rect(0, 0, _width, _height), bgBitmap.Bounds, 0.4f);
                }

                // Dynamic Pluggable Visualizer Engine
                // Default to pro_spectrum (GPU ring + bloom + particles) for all themes
                string vizId = _theme switch
                {
                    "spectrum" => "spectrum_bars",
                    "modern_orb" => "modern_orb",
                    _ => "pro_spectrum"  // Everything else uses the premium GPU visualizer
                };
                
                var visualizer = VidaStudio.Styles.Visualizers.VisualizerFactory.GetVisualizer(vizId);
                
                // Construct the export context
                float[] specArray = new float[analysis.Spectrum.GetLength(1)];
                for(int s = 0; s < specArray.Length; s++) {
                    specArray[s] = analysis.Spectrum[fIdx, s];
                }

                var vizContext = new VidaStudio.Styles.Visualizers.Win2DVisualizerContext
                {
                    Width = _width,
                    Height = _height,
                    Bass = bass,
                    Spectrum = specArray,
                    PrimaryColor = primaryColor,
                    SecondaryColor = secondaryColor,
                    LogoBitmap = logoBitmap
                };

                visualizer.RenderExport(ds, vizContext);

                // Draw Lyrics
                var tSpan = TimeSpan.FromSeconds(tCurrent);
                LyricLine? currentLine = _lyrics.Find(l => tSpan >= l.StartTime && tSpan <= l.EndTime);
                if (currentLine != null)
                {
                    var textFormat = new CanvasTextFormat
                    {
                        FontFamily = _fontName,
                        FontSize = 48,
                        HorizontalAlignment = CanvasHorizontalAlignment.Center,
                        VerticalAlignment = CanvasVerticalAlignment.Center,
                        Options = CanvasDrawTextOptions.EnableColorFont
                    };
                    var textRect = new Windows.Foundation.Rect(50, _height - 300, _width - 100, 200);
                    ds.DrawText(currentLine.Text, textRect, Colors.White, textFormat);
                }
            }

            // Extract RGBA bytes
            byte[] bgraFrame = System.Buffers.ArrayPool<byte>.Shared.Rent(frameByteCount);
            var pixelBytes = renderTarget.GetPixelBytes();
            Buffer.BlockCopy(pixelBytes, 0, bgraFrame, 0, frameByteCount);

            await frameChannel.Writer.WriteAsync(bgraFrame, cancellationToken);

            if (fIdx % 15 == 0 || fIdx == totalFrames - 1)
            {
                double pct = (double)(fIdx + 1) / totalFrames * 100.0;
                double elapsed = sw.Elapsed.TotalSeconds;
                double currentFps = (fIdx + 1) / Math.Max(0.1, elapsed);
                double eta = (totalFrames - (fIdx + 1)) / Math.Max(0.1, currentFps);
                progressCallback(new RenderProgress(pct, fIdx + 1, $"DirectX Engine... ({currentFps:F1} fps)", (int)eta));
            }
        }

        frameChannel.Writer.Complete();
        await writerTask;
        pipeStream.Close();
        await _ffmpegProcess.WaitForExitAsync(cancellationToken);
        if (_ffmpegProcess.ExitCode != 0) throw new Exception($"FFmpeg failed: {_ffmpegProcess.ExitCode}");
    }

    private void StartFfmpegPipe()
    {
        string ffmpegExe = "ffmpeg";
        string venvFfmpeg = System.IO.Path.Combine(BackendService.Instance.GetProjectRoot(), "venv", "Scripts", "ffmpeg.exe");
        if (File.Exists(venvFfmpeg)) ffmpegExe = venvFfmpeg;
        else if (File.Exists(@"C:\ffmpeg\bin\ffmpeg.exe")) ffmpegExe = @"C:\ffmpeg\bin\ffmpeg.exe";

        string videoCodec = "-c:v libx264 -preset fast -crf 18";
        try 
        {
            var searcher = new System.Management.ManagementObjectSearcher("SELECT Name FROM Win32_VideoController");
            foreach (System.Management.ManagementBaseObject obj in searcher.Get())
            {
                string gpuName = obj["Name"]?.ToString()?.ToLowerInvariant() ?? "";
                if (gpuName.Contains("nvidia")) { videoCodec = "-c:v h264_nvenc -preset p6 -rc vbr -cq 19 -b:v 15M -maxrate 24M"; break; }
                if (gpuName.Contains("amd") || gpuName.Contains("radeon")) { videoCodec = "-c:v h264_amf -quality quality -b:v 15M"; break; }
                if (gpuName.Contains("intel")) { videoCodec = "-c:v h264_qsv -preset slow -b:v 15M"; break; }
            }
        }
        catch { }

        string args = $"-y -f rawvideo -vcodec rawvideo -s {_width}x{_height} -pix_fmt bgra -r {_fps} " +
                      $"-i - -i \"{_audioPath}\" " +
                      $"{videoCodec} -pix_fmt yuv420p " +
                      $"-c:a aac -b:a 192k -shortest " +
                      $"\"{_outputPath}\"";

        var psi = new ProcessStartInfo
        {
            FileName = ffmpegExe,
            Arguments = args,
            RedirectStandardInput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        _ffmpegProcess = Process.Start(psi) ?? throw new Exception("Failed to start FFmpeg");
        _ffmpegProcess.ErrorDataReceived += (s, e) => { };
        _ffmpegProcess.BeginErrorReadLine();
    }

    public void Dispose()
    {
        if (_ffmpegProcess != null && !_ffmpegProcess.HasExited)
        {
            try { _ffmpegProcess.Kill(); } catch { }
            _ffmpegProcess.Dispose();
        }
    }
}
