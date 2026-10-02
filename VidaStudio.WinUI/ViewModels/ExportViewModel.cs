using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VidaStudio.Models;
using VidaStudio.Services;
using VidaStudio.Services.Rendering;

namespace VidaStudio.ViewModels;

public partial class ExportViewModel : ObservableObject
{
    public ObservableCollection<ExportPreset> Presets { get; } = new();

    [ObservableProperty]
    public partial ExportPreset? SelectedPreset { get; set; }

    [ObservableProperty]
    public partial bool Enable60Fps { get; set; } = true;

    [ObservableProperty]
    public partial bool EnableGpuAcceleration { get; set; } = true;

    [ObservableProperty]
    public partial bool IncludeOpeningTitleCard { get; set; } = true;

    [ObservableProperty]
    public partial bool IncludeSafeAreas { get; set; } = true;

    [ObservableProperty]
    public partial string ExportResolution { get; set; } = "1080p (Full HD)";

    [ObservableProperty]
    public partial bool IsExporting { get; set; }

    [ObservableProperty]
    public partial double ExportProgress { get; set; }

    [ObservableProperty]
    public partial string StatusMessage { get; set; } = "Ready for render & multi-format delivery";

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
        };
    }

    [RelayCommand]
    public async Task StartExportAsync()
    {
        if (IsExporting) return;

        IsExporting = true;
        ExportProgress = 0;
        StatusMessage = $"Starting render engine: {SelectedPreset?.Title} at {ExportResolution}...";

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
                StatusMessage = "Export Error: No audio track is currently loaded in the Studio.";
                return;
            }

            string inputAudio = studio.CurrentAudioPath;
            string outPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos), $"VIDA_Export_{DateTime.Now:yyyyMMdd_HHmmss}.mp4");

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
                lyrics: studio.CurrentLyrics
            );

            StatusMessage = $"✨ Video exported successfully to {outPath}!";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Export Error: {ex.Message}";
        }
        finally
        {
            IsExporting = false;
        }
    }
}
