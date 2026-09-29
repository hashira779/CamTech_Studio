using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VidaStudio.Models;

namespace VidaStudio.ViewModels;

public partial class StylesViewModel : ObservableObject
{
    public ObservableCollection<VisualStyle> Styles { get; } = new();

    [ObservableProperty]
    public partial VisualStyle? SelectedStyle { get; set; }

    [ObservableProperty]
    public partial string DirectorPrompt { get; set; } = "Romantic Khmer song about missing someone at night in Phnom Penh riverside, cinematic golden hour lighting, gentle rain reflections.";

    [ObservableProperty]
    public partial string SelectedKaraokeStyle { get; set; } = "Modern Khmer Pop";

    public ObservableCollection<string> KaraokeStyles { get; } = new()
    {
        "Classic Karaoke (Fill Sweep)",
        "Word Highlight (Smooth Ramp)",
        "Neon Glow (Active Syllable)",
        "Kinetic Syllable Bounce",
        "Typewriter Reveal",
        "Subtle Cross-Fade",
        "Modern Khmer Pop",
        "Cinematic Golden Gradient",
        "Emotional Ballad Trailing Glow"
    };

    public StylesViewModel()
    {
        foreach (var style in VisualStyle.GetCuratedStyles())
        {
            Styles.Add(style);
        }
        SelectedStyle = Styles.FirstOrDefault();
    }

    [RelayCommand]
    public void SelectStyle(VisualStyle style)
    {
        SelectedStyle = style;
        if (!string.IsNullOrEmpty(style.DefaultPrompt))
        {
            DirectorPrompt = style.DefaultPrompt;
        }
    }
}
