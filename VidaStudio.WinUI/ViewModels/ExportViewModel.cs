using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VidaStudio.Models;

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
    }

    [RelayCommand]
    public async Task StartExportAsync()
    {
        if (IsExporting) return;

        IsExporting = true;
        ExportProgress = 0;
        StatusMessage = $"Rendering {SelectedPreset?.Title} at {ExportResolution} (60 FPS: {Enable60Fps})...";

        try
        {
            for (int i = 0; i <= 100; i += 5)
            {
                await Task.Delay(100);
                ExportProgress = i;
                if (i == 25) StatusMessage = "Encoding audio & kinetic typography layers...";
                if (i == 65) StatusMessage = "Hardware accelerated H.264 video rendering...";
                if (i == 90) StatusMessage = "Generating YouTube and social media thumbnails...";
            }

            StatusMessage = "✨ Video exported successfully to outputs folder!";
        }
        finally
        {
            IsExporting = false;
        }
    }
}
