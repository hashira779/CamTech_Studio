using VidaStudio.Models;
using VidaStudio.Services.Rendering;

namespace VidaStudio.Services;

/// <summary>
/// Wraps the new C# NativeVideoRenderer to be easily called from ViewModels (ExportPage, StudioPage).
/// Bypasses the slow Python backend HTTP API for rendering.
/// </summary>
public class RenderService
{
    private static RenderService? _instance;
    public static RenderService Instance => _instance ??= new RenderService();

    public bool IsRendering { get; private set; }
    public double ProgressPercent { get; private set; }
    public string StatusMessage { get; private set; } = string.Empty;

    public event Action<double, string>? ProgressChanged;

    /// <summary>
    /// Starts a native C# render job.
    /// </summary>
    public async Task<string> StartNativeRenderAsync(
        string audioPath, string outputPath, int width = 1920, int height = 1080, int fps = 60,
        string theme = "ocean_wave", string palette = "cyberpunk", string? bgImagePath = null,
        string? logoPath = null, string songTitle = "", string artistName = "",
        List<LyricLine>? lyrics = null, string fontName = "Leelawadee UI")
    {
        if (IsRendering)
            throw new InvalidOperationException("A render job is already in progress.");

        IsRendering = true;
        ProgressPercent = 0;
        StatusMessage = "Starting native render engine...";
        ReportProgress(0, StatusMessage);

        try
        {
            using var cts = new CancellationTokenSource();
            
            // The NativeVideoRenderer is pure C# and uses SkiaSharp + FFmpeg pipe
            using var renderer = new NativeVideoRenderer(
                audioPath, outputPath, width, height, fps, theme, palette,
                bgImagePath, logoPath, songTitle, artistName, lyrics, fontName
            );

            await Task.Run(async () =>
            {
                await renderer.RenderAsync(
                    progress => 
                    {
                        ProgressPercent = progress.Percent;
                        StatusMessage = progress.Status;
                        ReportProgress(progress.Percent, progress.Status);
                    }, 
                    cts.Token
                );
            });

            StatusMessage = "Render completed successfully!";
            ReportProgress(100, StatusMessage);
            return outputPath;
        }
        catch (Exception ex)
        {
            StatusMessage = $"Render failed: {ex.Message}";
            ReportProgress(0, StatusMessage);
            throw;
        }
        finally
        {
            IsRendering = false;
        }
    }

    private void ReportProgress(double percent, string status)
    {
        // Fire event on UI thread using the main window's dispatcher queue
        var dq = App.CurrentWindow?.DispatcherQueue;
        if (dq != null)
        {
            dq.TryEnqueue(() => ProgressChanged?.Invoke(percent, status));
        }
        else
        {
            ProgressChanged?.Invoke(percent, status);
        }
    }
}
