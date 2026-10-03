using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using VidaStudio.Models;
using VidaStudio.Services;
using VidaStudio.Dialogs;

namespace VidaStudio.Pages;

public sealed partial class StudioPage : Page
{
    private async void LoadDemoSynth_Click(object sender, RoutedEventArgs e)
    {
        ShowActivity("Loading Synthwave Demo...");
        var demo = await VidaApiClient.Instance.LoadSynthDemoAsync();
        HideActivity();

        string path = "";
        string title = "Cyber Horizon";
        string artist = "VIDA Synth Engine";

        if (demo.HasValue && demo.Value.TryGetProperty("audio_path", out var p))
        {
            path = p.GetString() ?? "";
            title = demo.Value.TryGetProperty("title", out var t) ? t.GetString() ?? title : title;
            artist = demo.Value.TryGetProperty("artist", out var a) ? a.GetString() ?? artist : artist;
        }

        if (string.IsNullOrEmpty(path) || !File.Exists(path))
        {
            string uploads = Path.Combine(BackendService.Instance.GetProjectRoot(), "uploads", "audio");
            if (Directory.Exists(uploads))
            {
                var files = Directory.GetFiles(uploads, "*.mp3");
                if (files.Length > 1) path = files[1];
                else if (files.Length > 0) path = files[0];
            }
        }

        TitleInputBox.Text = title;
        ArtistInputBox.Text = artist;
        StageSongTitleText.Text = title;
        StageArtistText.Text = artist;

        // Apply Cyberpunk Neon style
        ApplyThemeVisualizer("neon_bars");
        ApplyColorPalette("cyberpunk");

        if (!string.IsNullOrEmpty(path) && File.Exists(path))
        {
            var item = new MediaItem { Name = Path.GetFileName(path), Path = path, Type = "audio" };
            _libraryItems.Insert(0, item);
            LoadAudioTrack(item);
            _player.Play();
        }
    }

    private async void LoadDemoSinisamut_Click(object sender, RoutedEventArgs e)
    {
        ShowActivity("Loading Sinn Sisamouth 60s Vinyl Demo...");
        var demo = await VidaApiClient.Instance.LoadSinisamutDemoAsync();
        HideActivity();

        string path = "";
        string title = "ចំប៉ាបាត់ដំបង";
        string artist = "ស៊ីន ស៊ីសាមុត";

        if (demo.HasValue && demo.Value.TryGetProperty("audio_path", out var p))
        {
            path = p.GetString() ?? "";
        }

        if (string.IsNullOrEmpty(path) || !File.Exists(path))
        {
            string uploads = Path.Combine(BackendService.Instance.GetProjectRoot(), "uploads", "audio");
            if (Directory.Exists(uploads))
            {
                var files = Directory.GetFiles(uploads, "*.mp3");
                if (files.Length > 0)
                {
                    path = files[0];
                    title = Path.GetFileNameWithoutExtension(files[0]);
                }
            }
        }

        TitleInputBox.Text = title;
        ArtistInputBox.Text = artist;
        StageSongTitleText.Text = title;
        StageArtistText.Text = artist;

        // Apply 60s Vinyl style
        ApplyKhmerTemplateById("vinyl_60s");

        if (!string.IsNullOrEmpty(path) && File.Exists(path))
        {
            var item = new MediaItem { Name = Path.GetFileName(path), Path = path, Type = "audio" };
            _libraryItems.Insert(0, item);
            LoadAudioTrack(item);
            _player.Play();
        }
    }

    // ================= KHMER TEMPLATES =================
    private async void OpenKhmerTemplates_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new KhmerTemplatesDialog
        {
            XamlRoot = this.XamlRoot
        };
        await dlg.ShowAsync();

        if (dlg.SelectedTemplate != null)
        {
            ApplyKhmerTemplate(dlg.SelectedTemplate);
        }
    }

    private void Browse20KhmerTemplates_Click(object sender, RoutedEventArgs e)
    {
        OpenKhmerTemplates_Click(sender, e);
    }

    private void KhmerTemplateCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (KhmerTemplateCombo.SelectedItem is ComboBoxItem item && item.Tag is string templateId && !string.IsNullOrEmpty(templateId))
        {
            ApplyKhmerTemplateById(templateId);
        }
    }

    private void ApplyKhmerTemplateById(string templateId)
    {
        var template = KhmerTemplate.AllTemplates.FirstOrDefault(t => t.Id == templateId);
        if (template != null)
        {
            ApplyKhmerTemplate(template);
        }
    }

    private void ApplyKhmerTemplate(KhmerTemplate template)
    {
        if (VisualizerThemeCombo == null || ColorPaletteCombo == null || LyricStyleCombo == null) return;

        try
        {
            _isApplyingTemplate = true;

            // Select theme in combo
            for (int i = 0; i < VisualizerThemeCombo.Items.Count; i++)
            {
                if (VisualizerThemeCombo.Items[i] is ComboBoxItem cbi && (cbi.Tag as string) == template.Theme)
                {
                    VisualizerThemeCombo.SelectedIndex = i;
                    break;
                }
            }

            // Select palette in combo
            for (int i = 0; i < ColorPaletteCombo.Items.Count; i++)
            {
                if (ColorPaletteCombo.Items[i] is ComboBoxItem cbi && (cbi.Tag as string) == template.Palette)
                {
                    ColorPaletteCombo.SelectedIndex = i;
                    break;
                }
            }

            // Select lyric animation
            for (int i = 0; i < LyricStyleCombo.Items.Count; i++)
            {
                if (LyricStyleCombo.Items[i] is ComboBoxItem cbi && (cbi.Tag as string) == template.LyricStyle)
                {
                    LyricStyleCombo.SelectedIndex = i;
                    break;
                }
            }

            if (BassBoostSlider != null)
            {
                BassBoostSlider.Value = (int)(template.BassBoost * 10);
            }
        }
        finally
        {
            _isApplyingTemplate = false;
        }

        // Apply immediately to stage canvas
        ApplyThemeVisualizer(template.Theme);
        ApplyColorPalette(template.Palette);
        ApplyLyricStyle(template.LyricStyle);
    }
}
