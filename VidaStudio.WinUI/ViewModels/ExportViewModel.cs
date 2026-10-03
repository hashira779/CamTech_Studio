using System.Collections.ObjectModel;
using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VidaStudio.Models;
using VidaStudio.Services;
using VidaStudio.Services.Rendering;

namespace VidaStudio.ViewModels;

public partial class ExportViewModel : ObservableObject
{
    private CancellationTokenSource? _exportCts;
    private string _lastExportPath = string.Empty;
    private readonly Stopwatch _exportStopwatch = new();

    public ObservableCollection<ExportPreset> Presets { get; } = new();

    [ObservableProperty]
    public partial ExportPreset? SelectedPreset { get; set; }

    [ObservableProperty]
    public partial bool Enable60Fps { get; set; } = true;

    [ObservableProperty]
    public partial bool EnableGpuAcceleration { get; set; } = false;

    [ObservableProperty]
    public partial bool IncludeOpeningTitleCard { get; set; } = true;

    [ObservableProperty]
    public partial bool IncludeSafeAreas { get; set; } = true;

    [ObservableProperty]
    public partial string ExportResolution { get; set; } = "1080p (Full HD)";

    [ObservableProperty]
    public partial bool IsExporting { get; set; }

    [ObservableProperty]
    public partial bool IsExportComplete { get; set; }

    [ObservableProperty]
    public partial double ExportProgress { get; set; }

    [ObservableProperty]
    public partial string StatusMessage { get; set; } = "Ready to render";

    [ObservableProperty]
    public partial string OutputPathDisplay { get; set; } = "Exports will be saved to your Videos folder";

    [ObservableProperty]
    public partial string ProgressText { get; set; } = "0%";

    [ObservableProperty]
    public partial string RenderFpsText { get; set; } = "--";

    [ObservableProperty]
    public partial string ElapsedText { get; set; } = "00:00";

    [ObservableProperty]
    public partial string EtaText { get; set; } = "--";

    public ObservableCollection<string> Resolutions { get; } = new()
    {
        "1080p (Full HD - Recommended)",
        "4K UHD (2160p - Ultra Crisp)",
        "720p (HD - Fast Draft)"
    };

    public ExportViewModel()
    {
        foreach (var p in ExportPreset.GetPresets())
        {
            Presets.Add(p);
        }
        SelectedPreset = Presets.FirstOrDefault();

        RenderService.Instance.ProgressChanged += (pct, msg) =>
        {
            ExportProgress = pct;
            StatusMessage = msg;
            ProgressText = $"{pct:F1}%";

            // Parse FPS from status message like "Rendering... (45.2 fps)"
            if (msg.Contains("fps"))
            {
                var match = System.Text.RegularExpressions.Regex.Match(msg, @"\((\d+\.?\d*) fps\)");
                if (match.Success)
                {
                    RenderFpsText = $"{match.Groups[1].Value} fps";
                }
            }

            // Update elapsed time
            if (_exportStopwatch.IsRunning)
            {
                var elapsed = _exportStopwatch.Elapsed;
                ElapsedText = elapsed.TotalHours >= 1
                    ? elapsed.ToString(@"hh\:mm\:ss")
                    : elapsed.ToString(@"mm\:ss");

                // Calculate ETA
                if (pct > 0.5)
                {
                    double remaining = elapsed.TotalSeconds * (100.0 - pct) / pct;
                    var eta = TimeSpan.FromSeconds(remaining);
                    EtaText = eta.TotalHours >= 1
                        ? eta.ToString(@"hh\:mm\:ss")
                        : eta.ToString(@"mm\:ss");
                }
            }
        };
    }

    [RelayCommand]
    public async Task StartExportAsync()
    {
        if (IsExporting) return;

        IsExporting = true;
        IsExportComplete = false;
        ExportProgress = 0;
        ProgressText = "0%";
        RenderFpsText = "--";
        ElapsedText = "00:00";
        EtaText = "Calculating...";
        StatusMessage = $"Initializing render engine...";

        _exportCts = new CancellationTokenSource();
        _exportStopwatch.Restart();

        try
        {
            // Determine dimensions from selected preset
            int width = 1920, height = 1080;
            if (SelectedPreset?.AspectRatio == "9:16")
            {
                width = 1080; height = 1920;
            }
            else if (SelectedPreset?.AspectRatio == "1:1")
            {
                width = 1080; height = 1080;
            }

            int fps = Enable60Fps ? 60 : 30;

            // Get actual path and state from UI state (StudioHub)
            var studio = VidaStudio.Pages.StudioPage.Current;
            if (studio == null || string.IsNullOrEmpty(studio.CurrentAudioPath))
            {
                StatusMessage = "⚠️ No audio track loaded. Go to Studio and load a song first.";
                return;
            }

            string inputAudio = studio.CurrentAudioPath;
            string outDir = Environment.GetFolderPath(Environment.SpecialFolder.MyVideos);
            string outPath = Path.Combine(outDir, $"VIDA_Export_{DateTime.Now:yyyyMMdd_HHmmss}.mp4");

            _lastExportPath = outPath;
            OutputPathDisplay = $"Saving to: {outPath}";

            await RenderService.Instance.StartNativeRenderAsync(
                audioPath: inputAudio,
                outputPath: outPath,
                width: width,
                height: height,
                fps: fps,
                theme: studio.CurrentTheme,
                palette: studio.CurrentPalette,
                songTitle: studio.CurrentSongTitle,
                artistName: studio.CurrentArtistName,
                lyrics: studio.CurrentLyrics,
                useGpu: EnableGpuAcceleration
            );

            _exportStopwatch.Stop();
            var totalTime = _exportStopwatch.Elapsed;
            string timeStr = totalTime.TotalMinutes >= 1
                ? $"{totalTime.Minutes}m {totalTime.Seconds}s"
                : $"{totalTime.Seconds}s";

            StatusMessage = $"✅ Export complete in {timeStr}!";
            ExportProgress = 100;
            ProgressText = "100%";
            EtaText = "Done!";
            IsExportComplete = true;
        }
        catch (OperationCanceledException)
        {
            _exportStopwatch.Stop();
            StatusMessage = "⛔ Export cancelled.";
            ExportProgress = 0;
            OutputPathDisplay = "Export was cancelled by user.";
        }
        catch (Exception ex)
        {
            _exportStopwatch.Stop();
            StatusMessage = $"❌ Render failed: {ex.Message}";
            OutputPathDisplay = "Check the error above and try again.";
        }
        finally
        {
            IsExporting = false;
            _exportCts?.Dispose();
            _exportCts = null;
        }
    }

    public void CancelExport()
    {
        _exportCts?.Cancel();
    }

    public void OpenExportedFile()
    {
        if (!string.IsNullOrEmpty(_lastExportPath) && File.Exists(_lastExportPath))
        {
            Process.Start(new ProcessStartInfo(_lastExportPath) { UseShellExecute = true });
        }
    }

    public void OpenExportFolder()
    {
        if (!string.IsNullOrEmpty(_lastExportPath))
        {
            string? dir = Path.GetDirectoryName(_lastExportPath);
            if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir))
            {
                // Open explorer and select the file
                Process.Start("explorer.exe", $"/select,\"{_lastExportPath}\"");
            }
        }
    }
}
