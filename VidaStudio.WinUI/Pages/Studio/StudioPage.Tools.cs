using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Shapes;
using VidaStudio.Models;
using VidaStudio.Services;
using VidaStudio.Dialogs;

namespace VidaStudio.Pages;

public sealed partial class StudioPage : Page
{
    private async void RunSuperSmartScan_Click(object sender, RoutedEventArgs e)
    {
        await EnsureAudioLoadedAsync();
        if (string.IsNullOrEmpty(_currentAudioPath))
        {
            ShowActivity("Please select or drop an audio track first.");
            await Task.Delay(1500);
            HideActivity();
            return;
        }

        ShowActivity("Deep scanning audio DNA, BPM & key...");
        var analysis = await VidaApiClient.Instance.AnalyzeAudioAsync(_currentAudioPath);
        HideActivity();

        if (analysis.HasValue && analysis.Value.TryGetProperty("bpm", out var bpmProp))
        {
            int bpm = bpmProp.GetInt32();
            string mood = analysis.Value.TryGetProperty("mood", out var m) ? m.GetString() ?? "Dynamic" : "Dynamic";
            AudioStatsBadge.Text = $"{bpm} BPM · {mood} · 60 FPS";
            StatBpmText.Text = bpm.ToString();
            StatEnergyText.Text = analysis.Value.TryGetProperty("energy", out var en) ? $"{(int)(en.GetDouble() * 100)}%" : "88%";
        }
    }

    private void VfxPowerSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (VfxPowerLabel != null)
        {
            VfxPowerLabel.Text = $"{(int)e.NewValue}%";
        }
    }

    private void BassBoostSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (BassBoostValueText != null)
        {
            BassBoostValueText.Text = $"{(e.NewValue / 10.0):0.0}x";
        }
    }

    private void TriggerVfxTest_Click(object sender, RoutedEventArgs e)
    {
        // Flash test
        // foreach (var child in SpectrumPanel.Children)
        // {
        //     if (child is Rectangle rect)
        //     {
        //         rect.Height = 98;
        //     }
        // }
    }

    private async void QuickAutoPerfect_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrEmpty(_currentAudioPath) || !File.Exists(_currentAudioPath))
        {
            var noAudioDialog = new ContentDialog
            {
                Title = "No Audio Loaded",
                Content = "Please drop a song file into the media pool first to use the Auto Perfect magic.",
                CloseButtonText = "OK",
                XamlRoot = this.XamlRoot
            };
            await noAudioDialog.ShowAsync();
            return;
        }

        // 1. File Picker for Save Location
        var savePicker = new Windows.Storage.Pickers.FileSavePicker();
        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.CurrentWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(savePicker, hwnd);
        savePicker.SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.VideosLibrary;
        savePicker.FileTypeChoices.Add("MP4 Video", new List<string>() { ".mp4" });
        savePicker.SuggestedFileName = $"VIDA_Magic_{DateTime.Now:yyyyMMdd_HHmmss}";

        var file = await savePicker.PickSaveFileAsync();
        if (file == null) return; // User cancelled
        string outPath = file.Path;

        // 2. Show 2027 Magic UI State
        ShowActivity("✨ AI Auto Perfect: Extracting Lyrics & Stems...");
        MagicLoadingOverlay.Visibility = Visibility.Visible;
        MagicLoadingBar.IsIndeterminate = true;
        MagicLoadingSubtext.Text = "Transcribing audio via Gemini AI...";
        QuickAutoPerfect_Click_Visuals(true);

        try
        {
            // 3. Transcription (AI) with Progress Polling
            MagicLoadingBar.IsIndeterminate = false;
            MagicLoadingBar.Value = 0;

            using var cts = new CancellationTokenSource();
            var progressTask = Task.Run(async () =>
            {
                while (!cts.Token.IsCancellationRequested)
                {
                    await Task.Delay(500, cts.Token).ConfigureAwait(false);
                    if (cts.Token.IsCancellationRequested) break;

                    var (pct, stage) = await VidaApiClient.Instance.GetTranscribeProgressAsync();
                    if (!string.IsNullOrEmpty(stage))
                    {
                        DispatcherQueue.TryEnqueue(() =>
                        {
                            MagicLoadingBar.Value = pct;
                            MagicLoadingSubtext.Text = $"{stage} ({pct}%)";
                        });
                    }
                }
            }, cts.Token);

            List<LyricLine> lyrics = new List<LyricLine>();
            try
            {
                lyrics = await VidaApiClient.Instance.TranscribeAudioAsync(_currentAudioPath, "km", "gemini-fast");
            }
            finally
            {
                cts.Cancel();
                try { await progressTask; } catch { }
            }

            DispatcherQueue.TryEnqueue(() =>
            {
                UpdateLoadedLyrics(lyrics);
                MagicLoadingSubtext.Text = "Auto-styling and preparing Render Engine...";
                MagicLoadingBar.IsIndeterminate = true;
            });

            // 4. Auto-Select Theme & Palette randomly from top-tier ones
            string[] topPalettes = { "cyberpunk", "angkor", "neon_synth", "royal_palace", "sunset", "electric", "bloodmoon", "matrix" };
            
            // Always use pro_spectrum — the GPU-accelerated visualizer with ring, bloom, particles
            string autoTheme = "pro_spectrum";
            string autoPalette = topPalettes[_random.Next(topPalettes.Length)];
            string selectedFont = FontSelector.SelectedItem as string ?? "Leelawadee UI";

            DispatcherQueue.TryEnqueue(() =>
            {
                ApplyThemeVisualizer(autoTheme);
                ApplyColorPalette(autoPalette);
            });

            // 4.5 Generate Smart AI Background based on Song and Palette
            DispatcherQueue.TryEnqueue(() => { MagicLoadingSubtext.Text = "Painting AI background masterpiece..."; });
            
            string songTitle = string.IsNullOrWhiteSpace(StageSongTitleText.Text) ? "Music" : StageSongTitleText.Text;
            string artistName = string.IsNullOrWhiteSpace(ArtistInputBox.Text) ? "Unknown Artist" : ArtistInputBox.Text;
            string prompt = $"A cinematic masterpiece background wallpaper for a music video. The song is '{songTitle}' by '{artistName}'. Highly detailed, 8k resolution, trending on artstation, {autoPalette} colors, aesthetic mood, no text, clean.";
            string encodedPrompt = Uri.EscapeDataString(prompt);
            string bgUrl = $"https://image.pollinations.ai/prompt/{encodedPrompt}?width=1080&height=1920&nologo=true";
            
            string? aiBgPath = System.IO.Path.Combine(Windows.Storage.ApplicationData.Current.TemporaryFolder.Path, $"auto_bg_{Guid.NewGuid()}.jpg");
            
            try
            {
                using var http = new System.Net.Http.HttpClient();
                var bgBytes = await http.GetByteArrayAsync(bgUrl);
                await File.WriteAllBytesAsync(aiBgPath, bgBytes);
                
                // Update UI Stage with the new AI background
                DispatcherQueue.TryEnqueue(() =>
                {
                    StageContainer.Background = new Microsoft.UI.Xaml.Media.ImageBrush
                    {
                        ImageSource = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri(aiBgPath)),
                        Stretch = Microsoft.UI.Xaml.Media.Stretch.UniformToFill,
                        Opacity = 0.3
                    };
                });
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"AI Background generation failed: {ex.Message}");
                aiBgPath = null;
            }

            // 5. Start Native Render (Superfast C# Pipeline)
            RenderService.Instance.ProgressChanged += (pct, msg) =>
            {
                DispatcherQueue.TryEnqueue(() =>
                {
                    MagicLoadingBar.IsIndeterminate = false;
                    MagicLoadingBar.Value = pct;
                    MagicLoadingSubtext.Text = $"Rendering: {pct:F0}% - {msg}";
                });
            };

            await RenderService.Instance.StartNativeRenderAsync(
                audioPath: _currentAudioPath,
                outputPath: outPath,
                width: 1080, height: 1920, fps: 60, // Auto-pick 9:16 Shorts format by default for "magic" modern feel
                theme: autoTheme,
                palette: autoPalette,
                bgImagePath: aiBgPath, // Pass the AI generated background!
                songTitle: songTitle,
                artistName: artistName,
                lyrics: lyrics,
                fontName: selectedFont,
                logoPath: string.IsNullOrWhiteSpace(LogoPathBox.Text) ? @"Assets\VibeTunesLogo.png" : LogoPathBox.Text
            );

            // 5. Done!
            var successDialog = new ContentDialog
            {
                Title = "✨ Magic Video Created!",
                Content = $"Your video is ready and rendered at 60FPS in record time.\n\nSaved to: {outPath}",
                PrimaryButtonText = "Open Folder",
                CloseButtonText = "Awesome",
                XamlRoot = this.XamlRoot
            };
            
            var result = await successDialog.ShowAsync();
            if (result == ContentDialogResult.Primary)
            {
                System.Diagnostics.Process.Start("explorer.exe", $"/select,\"{outPath}\"");
            }
        }
        catch (Exception ex)
        {
            var errDialog = new ContentDialog
            {
                Title = "Magic Failed",
                Content = $"An error occurred during Auto Perfect: {ex.Message}",
                CloseButtonText = "OK",
                XamlRoot = this.XamlRoot
            };
            await errDialog.ShowAsync();
        }
        finally
        {
            HideActivity();
            MagicLoadingOverlay.Visibility = Visibility.Collapsed;
            QuickAutoPerfect_Click_Visuals(false);
        }
    }

    private void QuickAutoPerfect_Click_Visuals(bool isWorking)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (isWorking)
            {
                ActivityCapsule.Visibility = Visibility.Visible;
                ActivityCapsule.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 139, 92, 246)); // Purple glow
            }
            else
            {
                ActivityCapsule.Visibility = Visibility.Collapsed;
                ActivityCapsule.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 49, 46, 129));
            }
        });
    }

    private void NavigateExport_Click(object sender, RoutedEventArgs e)
    {
        Frame.Navigate(typeof(ExportPage));
    }
}
