using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using VidaStudio.Models;
using VidaStudio.Services;
using Windows.ApplicationModel.DataTransfer;

namespace VidaStudio.Pages;

/// <summary>
/// YouTube: Download, URL normalization, progress polling.
/// </summary>
public sealed partial class StudioPage
{
    private async void PasteYouTube_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var dataPackageView = Clipboard.GetContent();
            if (dataPackageView.Contains(StandardDataFormats.Text))
            {
                string text = await dataPackageView.GetTextAsync();
                YouTubeUrlBox.Text = text;
                
                // If it looks like a URL, auto-download it immediately
                if (text.Contains("http://") || text.Contains("https://"))
                {
                    DownloadYouTube_Click(sender, e);
                }
                else
                {
                    ShowActivity("Pasted text from clipboard");
                    await Task.Delay(1000);
                    HideActivity();
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[Paste YouTube] Error: {ex.Message}");
            var errDialog = new ContentDialog
            {
                Title = "Paste Error",
                Content = $"Could not paste from clipboard:\n{ex.Message}",
                CloseButtonText = "OK",
                XamlRoot = this.XamlRoot
            };
            await errDialog.ShowAsync();
        }
    }

    private static string NormalizeYouTubeUrl(string input)
    {
        if (string.IsNullOrWhiteSpace(input)) return "";
        string url = input.Trim();

        // 1. Direct 11-char ID
        if (Regex.IsMatch(url, @"^[a-zA-Z0-9_-]{11}$"))
        {
            return $"https://www.youtube.com/watch?v={url}";
        }

        // 2. youtu.be/<id>
        var mShort = Regex.Match(url, @"youtu\.be/([a-zA-Z0-9_-]{11})", RegexOptions.IgnoreCase);
        if (mShort.Success)
        {
            return $"https://www.youtube.com/watch?v={mShort.Groups[1].Value}";
        }

        // 3. (www|m|music).youtube.com/(watch?v=|shorts/|live/|embed/|v/)([id])
        var mFull = Regex.Match(url, @"(?:youtube\.com|youtube-nocookie\.com)/(?:watch\?[^ \t\r\n]*?v=|shorts/|live/|embed/|v/)([a-zA-Z0-9_-]{11})", RegexOptions.IgnoreCase);
        if (mFull.Success)
        {
            return $"https://www.youtube.com/watch?v={mFull.Groups[1].Value}";
        }

        // 4. Query param ?v= or &v=
        var mV = Regex.Match(url, @"[?&]v=([a-zA-Z0-9_-]{11})", RegexOptions.IgnoreCase);
        if (mV.Success)
        {
            return $"https://www.youtube.com/watch?v={mV.Groups[1].Value}";
        }

        if (!url.StartsWith("http://", StringComparison.OrdinalIgnoreCase) && !url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            return "https://" + url;
        }

        return url;
    }

    private async void DownloadYouTube_Click(object sender, RoutedEventArgs e)
    {
        string rawInput = YouTubeUrlBox.Text;
        if (string.IsNullOrEmpty(rawInput))
        {
            ShowActivity("Please paste a valid YouTube URL first.");
            await Task.Delay(1500);
            HideActivity();
            return;
        }

        string url = NormalizeYouTubeUrl(rawInput);

        ShowActivity("Connecting to YouTube stream...");
        YouTubeProgressBar.Visibility = Visibility.Visible;

        using var cts = new CancellationTokenSource();
        var progressTask = Task.Run(async () =>
        {
            while (!cts.Token.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(600, cts.Token).ConfigureAwait(false);
                    if (cts.Token.IsCancellationRequested) break;
                    var (pct, stage) = await VidaApiClient.Instance.GetYouTubeProgressAsync();
                    if (!string.IsNullOrEmpty(stage))
                    {
                        DispatcherQueue.TryEnqueue(() =>
                        {
                            ShowActivity($"{stage} ({pct}%)");
                        });
                    }
                }
                catch { }
            }
        }, cts.Token);

        JsonElement? result = null;
        try
        {
            result = await VidaApiClient.Instance.DownloadYouTubeAsync(url);
        }
        finally
        {
            cts.Cancel();
            try { await progressTask; } catch { }
            YouTubeProgressBar.Visibility = Visibility.Collapsed;
        }

        if (result.HasValue && result.Value.TryGetProperty("audio_path", out var pProp))
        {
            string audioPath = pProp.GetString() ?? "";
            string title = result.Value.TryGetProperty("title", out var tProp) ? tProp.GetString() ?? "" : "";
            string artist = result.Value.TryGetProperty("artist", out var aProp) ? aProp.GetString() ?? "" : "";

            var item = new MediaItem { Name = Path.GetFileName(audioPath), Path = audioPath, Type = "audio" };
            _libraryItems.Insert(0, item);
            LibrarySelector.SelectedItem = item;
            LoadAudioTrack(item);
            
            // Apply metadata AFTER LoadAudioTrack clears it
            if (!string.IsNullOrEmpty(title))
            {
                TitleInputBox.Text = title;
                StageSongTitleText.Text = title;
                ProjectTitleText.Text = $"Project: {title} - 60 FPS";
            }
            if (!string.IsNullOrEmpty(artist))
            {
                ArtistInputBox.Text = artist;
                StageArtistText.Text = artist;
            }
            
            _player.Play();

            // Auto-load any synchronized subtitles or lyrics extracted with the track
            if (result.Value.TryGetProperty("lyrics", out var lyrProp) && lyrProp.ValueKind == JsonValueKind.Array)
            {
                var extractedLyrics = new List<LyricLine>();
                int idx = 0;
                foreach (var lineEl in lyrProp.EnumerateArray())
                {
                    double st = lineEl.TryGetProperty("start", out var s) ? s.GetDouble() : 0;
                    double et = lineEl.TryGetProperty("end", out var endVal) ? endVal.GetDouble() : st + 3;
                    string tx = lineEl.TryGetProperty("text", out var t) ? t.GetString() ?? "" : "";
                    if (!string.IsNullOrWhiteSpace(tx))
                    {
                        extractedLyrics.Add(new LyricLine { LineId = idx++, StartTime = TimeSpan.FromSeconds(st), EndTime = TimeSpan.FromSeconds(et), Text = tx });
                    }
                }
                if (extractedLyrics.Count > 0)
                {
                    UpdateLoadedLyrics(extractedLyrics);
                    TabRightTeleprompterBtn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
                    TabRightStyleBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
                    RightTeleprompterPanel.Visibility = Visibility.Visible;
                    RightStylePanel.Visibility = Visibility.Collapsed;
                    RightDirectorPanel.Visibility = Visibility.Collapsed;
                    RightDspPanel.Visibility = Visibility.Collapsed;
                }
            }

            ShowActivity($"✓ Downloaded: {title}");
            await Task.Delay(2000);
            HideActivity();
        }
        else
        {
            string err = VidaApiClient.Instance.LastYouTubeError ?? "Could not download. Please check the URL.";
            HideActivity();
            var errDialog = new ContentDialog
            {
                Title = "⚠️ YouTube Download Failed",
                Content = err,
                CloseButtonText = "OK",
                XamlRoot = this.XamlRoot
            };
            await errDialog.ShowAsync();
        }
    }

    // ================= YOUTUBE DETAILS DIALOG =================
    private async void YoutubeDetails_Click(object sender, RoutedEventArgs e)
    {
        string fullLyrics = string.Join("\n", _lyricLines.Select(l => $"{l.DisplayTime} {l.Text}"));
        var dlg = new Dialogs.YouTubeDetailsDialog
        {
            XamlRoot = this.XamlRoot,
            VideoTitle = string.IsNullOrEmpty(_customYtTitle) ? $"[Official Visualizer] {TitleInputBox.Text} - {ArtistInputBox.Text} (60 FPS 4K)" : _customYtTitle,
            VideoDescription = string.IsNullOrEmpty(_customYtDesc) ? $"🎵 Title: {TitleInputBox.Text}\n🎙️ Artist: {ArtistInputBox.Text}\n⚡ Rendered with VIDA Studio 60 FPS\n\n📝 Synchronized Lyrics:\n{fullLyrics}" : _customYtDesc,
            VideoTags = string.IsNullOrEmpty(_customYtTags) ? $"{TitleInputBox.Text}, {ArtistInputBox.Text}, Khmer song, 60fps, 4K visualizer" : _customYtTags
        };

        var result = await dlg.ShowAsync();
        if (result == ContentDialogResult.Primary)
        {
            _customYtTitle = dlg.VideoTitle;
            _customYtDesc = dlg.VideoDescription;
            _customYtTags = dlg.VideoTags;
        }
    }
}
