using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Shapes;
using System.Text.Json;
using VidaStudio.Dialogs;
using VidaStudio.Models;

namespace VidaStudio.Pages;

/// <summary>
/// Themes: Visualizer theme, color palettes, visualizer math, presets.
/// </summary>
public sealed partial class StudioPage
{
    private void VisualizerThemeCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_isApplyingTemplate) return;
        string? tag = (VisualizerThemeCombo?.SelectedItem as ComboBoxItem)?.Tag?.ToString()
                      ?? (e.AddedItems.Count > 0 ? (e.AddedItems[0] as ComboBoxItem)?.Tag?.ToString() : null);
        if (!string.IsNullOrEmpty(tag))
        {
            ApplyThemeVisualizer(tag);
        }
    }

    private VidaStudio.Styles.Visualizers.IVisualizerStyle? _currentVisualizer;
    private UIElement? _visualizerElement;

    private void ApplyThemeVisualizer(string theme)
    {
        _currentTheme = theme;
        
        string vizId = "modern_orb";
        if (theme == "spectrum") vizId = "spectrum_bars";
        if (theme == "pro_spectrum") vizId = "pro_spectrum";
        if (theme == "modern_orb") vizId = "modern_orb";
        
        _currentVisualizer = VidaStudio.Styles.Visualizers.VisualizerFactory.GetVisualizer(vizId);
        
        if (VisualizerHostGrid != null && _currentVisualizer != null)
        {
            VisualizerHostGrid.Children.Clear();
            _visualizerElement = _currentVisualizer.CreatePreviewElement();
            VisualizerHostGrid.Children.Add(_visualizerElement);
        }
    }

    private void ColorPaletteCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_isApplyingTemplate) return;
        string? tag = (ColorPaletteCombo?.SelectedItem as ComboBoxItem)?.Tag?.ToString()
                      ?? (e.AddedItems.Count > 0 ? (e.AddedItems[0] as ComboBoxItem)?.Tag?.ToString() : null);
        if (!string.IsNullOrEmpty(tag))
        {
            ApplyColorPalette(tag);
        }
    }

    private static Windows.UI.Color ParseHexColor(string hex)
    {
        hex = hex.TrimStart('#');
        if (hex.Length == 6)
        {
            byte r = Convert.ToByte(hex.Substring(0, 2), 16);
            byte g = Convert.ToByte(hex.Substring(2, 2), 16);
            byte b = Convert.ToByte(hex.Substring(4, 2), 16);
            return Windows.UI.Color.FromArgb(255, r, g, b);
        }
        if (hex.Length == 8)
        {
            byte a = Convert.ToByte(hex.Substring(0, 2), 16);
            byte r = Convert.ToByte(hex.Substring(2, 2), 16);
            byte g = Convert.ToByte(hex.Substring(4, 2), 16);
            byte b = Convert.ToByte(hex.Substring(6, 2), 16);
            return Windows.UI.Color.FromArgb(a, r, g, b);
        }
        return Windows.UI.Color.FromArgb(255, 129, 140, 248);
    }

    private void ApplyColorPalette(string palette)
    {
        _currentColorPalette = palette;

        (string bg0, string bg1, string bg2, string accent, string label, string artist, string lyric, string[] bars) = palette switch
        {
            "vintage_vinyl" => ("#2A1810", "#140A06", "#050201", "#D97706", "#451A03", "#D97706", "#FEF3C7", new[] { "#D97706", "#A16207", "#78350F", "#CA8A04", "#F59E0B" }),
            "candlelight" => ("#3F1905", "#1D0B02", "#090300", "#F97316", "#7C2D12", "#FB923C", "#FFEDD5", new[] { "#EA580C", "#F97316", "#FBBF24", "#F59E0B", "#FB923C" }),
            "rainy_night" => ("#0F172A", "#020617", "#000208", "#38BDF8", "#1E3A8A", "#38BDF8", "#BAE6FD", new[] { "#38BDF8", "#0284C7", "#2563EB", "#60A5FA", "#93C5FD" }),
            "tonle_sap" => ("#042F2E", "#021C1B", "#010C0B", "#2DD4BF", "#134E4A", "#2DD4BF", "#CCFBF1", new[] { "#2DD4BF", "#0D9488", "#06B6D4", "#14B8A6", "#5EEAD4" }),
            "royal_palace" => ("#261C02", "#120E01", "#060400", "#EAB308", "#713F12", "#FACC15", "#FEF08A", new[] { "#EAB308", "#CA8A04", "#10B981", "#059669", "#FDE047" }),
            "romduol" => ("#272015", "#14100A", "#070503", "#FDE68A", "#854D0E", "#FDE68A", "#FFFBEB", new[] { "#FDE68A", "#F59E0B", "#D97706", "#FBBF24", "#FEF3C7" }),
            "pleng_kar" => ("#3B0712", "#1C0308", "#080103", "#F43F5E", "#881337", "#F43F5E", "#FFE4E6", new[] { "#E11D48", "#BE123C", "#F59E0B", "#F43F5E", "#FB7185" }),
            "romvong_festive" => ("#2E1065", "#140530", "#060110", "#EC4899", "#831843", "#F472B6", "#FCE7F3", new[] { "#EC4899", "#F59E0B", "#10B981", "#3B82F6", "#8B5CF6" }),
            "kirirom_pine" => ("#052E16", "#02170B", "#010A04", "#22C55E", "#14532D", "#4ADE80", "#DCFCE7", new[] { "#22C55E", "#16A34A", "#15803D", "#4ADE80", "#86EFAC" }),
            "lotus_pond" => ("#3B0D2E", "#1C0616", "#08010A", "#D946EF", "#701A75", "#E879F9", "#FAE8FF", new[] { "#D946EF", "#C026D3", "#10B981", "#E879F9", "#F0ABFC" }),
            "chapei_wood" => ("#2E180A", "#160B04", "#070301", "#B45309", "#451A03", "#D97706", "#FEF3C7", new[] { "#B45309", "#92400E", "#78350F", "#D97706", "#F59E0B" }),
            "cyberpunk" => ("#2A0845", "#110220", "#05000A", "#00F0FF", "#FF007F", "#FF007F", "#00F0FF", new[] { "#00F0FF", "#FF007F", "#7928CA", "#00E5FF", "#FF0080" }),
            "sunset" => ("#3A0824", "#1A0310", "#080005", "#F97316", "#BE185D", "#F97316", "#FFEDD5", new[] { "#F97316", "#EF4444", "#EC4899", "#F59E0B", "#FB7185" }),
            "matrix" => ("#022409", "#011204", "#000602", "#22C55E", "#064E3B", "#22C55E", "#86EFAC", new[] { "#22C55E", "#10B981", "#15803D", "#4ADE80", "#16A34A" }),
            "electric" => ("#2E1065", "#0F0525", "#04010D", "#A855F7", "#581C87", "#C084FC", "#F3E8FF", new[] { "#A855F7", "#8B5CF6", "#6366F1", "#C084FC", "#818CF8" }),
            "bloodmoon" => ("#3F0708", "#1F0203", "#0A0001", "#EF4444", "#7F1D1D", "#EF4444", "#FEE2E2", new[] { "#EF4444", "#DC2626", "#B91C1C", "#F87171", "#991B1B" }),
            "pastel" => ("#241835", "#120B1C", "#06030A", "#F472B6", "#6366F1", "#818CF8", "#FDF2F8", new[] { "#F472B6", "#818CF8", "#38BDF8", "#FCD34D", "#A7F3D0" }),
            "monochrome" => ("#1E293B", "#0F172A", "#020617", "#E2E8F0", "#334155", "#94A3B8", "#FFFFFF", new[] { "#F8FAFC", "#E2E8F0", "#94A3B8", "#64748B", "#CBD5E1" }),
            _ => ("#3B1A04", "#180B02", "#0A0401", "#F59E0B", "#78350F", "#F59E0B", "#FDE68A", new[] { "#F59E0B", "#D97706", "#B45309", "#FBBF24", "#FCD34D" }) // angkor default
        };

        // Fully redraw StageContainer background with a fresh RadialGradientBrush to force compositor update
        if (StageContainer != null)
        {
            var radialBrush = new Microsoft.UI.Xaml.Media.RadialGradientBrush
            {
                Center = new Windows.Foundation.Point(0.5, 0.5),
                GradientOrigin = new Windows.Foundation.Point(0.5, 0.5),
                RadiusX = 0.7,
                RadiusY = 0.7
            };
            radialBrush.GradientStops.Add(new Microsoft.UI.Xaml.Media.GradientStop { Color = ParseHexColor(bg0), Offset = 0.0 });
            radialBrush.GradientStops.Add(new Microsoft.UI.Xaml.Media.GradientStop { Color = ParseHexColor(bg1), Offset = 0.7 });
            radialBrush.GradientStops.Add(new Microsoft.UI.Xaml.Media.GradientStop { Color = ParseHexColor(bg2), Offset = 1.0 });
            StageContainer.Background = radialBrush;
        }

        // if (VinylOuterBorder != null) VinylOuterBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(accent));
        // if (VinylCenterLabel != null) VinylCenterLabel.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(label));

        if (StageArtistText != null) StageArtistText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(artist));
        
        // Clean modern lyrical look
        if (LyricPillBorder != null) LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor("#AA090D16"));
        if (StageLyricsText != null) StageLyricsText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor("#FFFFFF"));

        _currentBarColors.Clear();
        foreach (var b in bars)
        {
            _currentBarColors.Add(ParseHexColor(b));
        }

        UpdateVisualizerFrame();
    }

    private void UpdateVisualizerFrame()
    {
        if (_currentVisualizer == null || _visualizerElement == null) return;

        bool isPlaying = _player.PlaybackSession.PlaybackState == Windows.Media.Playback.MediaPlaybackState.Playing;
        double ampScale = isPlaying ? 1.0 : 0.4;
        _wavePhase += isPlaying ? 0.25 : 0.05;

        Windows.UI.Color primary = _currentBarColors.Count > 0 ? _currentBarColors[0] : Microsoft.UI.Colors.DeepPink;
        Windows.UI.Color secondary = _currentBarColors.Count > 1 ? _currentBarColors[1] : Microsoft.UI.Colors.DeepSkyBlue;

        var context = new VidaStudio.Styles.Visualizers.VisualizerPreviewContext
        {
            WavePhase = _wavePhase,
            AmplitudeScale = ampScale,
            PrimaryColor = primary,
            SecondaryColor = secondary,
            Bass = 1.0f 
        };

        if (_visualizerElement != null)
        {
            _currentVisualizer?.UpdatePreview(_visualizerElement, context);
        }
    }

    private void DirectorPresetCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (RuleShakeToggle == null || RuleShockwaveToggle == null || RuleBloomToggle == null || RuleAutoSwitchToggle == null)
            return;

        if (DirectorPresetCombo.SelectedItem is ComboBoxItem item && item.Tag is string tag)
        {
            switch (tag)
            {
                case "festival_drop":
                    RuleShakeToggle.IsOn = true;
                    RuleShockwaveToggle.IsOn = true;
                    RuleBloomToggle.IsOn = true;
                    RuleAutoSwitchToggle.IsOn = true;
                    break;
                case "neural_glitch":
                    RuleShakeToggle.IsOn = true;
                    RuleShockwaveToggle.IsOn = false;
                    RuleBloomToggle.IsOn = true;
                    RuleAutoSwitchToggle.IsOn = true;
                    break;
                case "ambient_liquid":
                    RuleShakeToggle.IsOn = false;
                    RuleShockwaveToggle.IsOn = true;
                    RuleBloomToggle.IsOn = false;
                    RuleAutoSwitchToggle.IsOn = false;
                    break;
                case "cyber_angkor":
                    RuleShakeToggle.IsOn = true;
                    RuleShockwaveToggle.IsOn = true;
                    RuleBloomToggle.IsOn = true;
                    RuleAutoSwitchToggle.IsOn = false;
                    break;
                case "auto_ai_director":
                    RuleShakeToggle.IsOn = true;
                    RuleShockwaveToggle.IsOn = true;
                    RuleBloomToggle.IsOn = true;
                    RuleAutoSwitchToggle.IsOn = true;
                    break;
            }
        }
    }

    private void EqSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (EqSubLabel != null && EqSubSlider != null)
        {
            EqSubLabel.Text = $"Sub ({(EqSubSlider.Value >= 0 ? "+" : "")}{(int)EqSubSlider.Value} dB)";
        }
        if (EqMidLabel != null && EqMidSlider != null)
        {
            EqMidLabel.Text = $"Mid ({(EqMidSlider.Value >= 0 ? "+" : "")}{(int)EqMidSlider.Value} dB)";
        }
        if (EqHighLabel != null && EqHighSlider != null)
        {
            EqHighLabel.Text = $"High ({(EqHighSlider.Value >= 0 ? "+" : "")}{(int)EqHighSlider.Value} dB)";
        }
    }
}
