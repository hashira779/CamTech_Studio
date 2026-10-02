using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using VidaStudio.Dialogs;
using VidaStudio.Models;
using VidaStudio.Services;
using Windows.ApplicationModel.DataTransfer;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;
using Rectangle = Microsoft.UI.Xaml.Shapes.Rectangle;

namespace VidaStudio.Pages;

public sealed partial class StudioPage : Page
{
    private readonly MediaPlayer _player = new();
    private readonly DispatcherTimer _playbackTimer;
    private readonly ObservableCollection<MediaItem> _libraryItems = new();
    private readonly ObservableCollection<LyricLine> _teleprompterItems = new();
    private readonly List<LyricLine> _lyricLines = new();
    private readonly Random _random = new();

    private string _currentAudioPath = string.Empty;
    private string _customYtTitle = string.Empty;
    private string _customYtDesc = string.Empty;
    private string _customYtTags = string.Empty;

    private string _currentColorPalette = "angkor";
    private string _currentTheme = "ocean_wave";
    private readonly List<Windows.UI.Color> _currentBarColors = new();
    private double _wavePhase = 0;
    private bool _isApplyingTemplate = false;

    public StudioPage()
    {
        InitializeComponent();

        LibrarySelector.ItemsSource = _libraryItems;

        _player.PlaybackSession.PlaybackStateChanged += PlaybackSession_PlaybackStateChanged;

        // Try to load default logo into UI preview
        try
        {
            var defaultLogoUri = new Uri("ms-appx:///Assets/VibeTunesLogo.png");
            BadgeLogoBrush.ImageSource = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(defaultLogoUri);
            BadgeLogoEllipse.Visibility = Visibility.Visible;
            BadgeTextStack.Visibility = Visibility.Collapsed;
        }
        catch { }

        _playbackTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(33) }; // ~30-60 FPS
        _playbackTimer.Tick += PlaybackTimer_Tick;

        Loaded += StudioPage_Loaded;
        Unloaded += StudioPage_Unloaded;
    }

    private async void StudioPage_Loaded(object sender, RoutedEventArgs e)
    {
        TeleprompterListView.ItemsSource = _teleprompterItems;

        // Apply initial visualizer & palette
        ApplyColorPalette(_currentColorPalette);
        ApplyThemeVisualizer(_currentTheme);

        // Populate System Fonts for Magic Text
        var fontFamilies = SkiaSharp.SKFontManager.Default.FontFamilies.OrderBy(f => f).ToList();
        FontSelector.ItemsSource = fontFamilies;
        int defaultFontIdx = fontFamilies.IndexOf("Leelawadee UI");
        if (defaultFontIdx < 0) defaultFontIdx = fontFamilies.IndexOf("Segoe UI");
        FontSelector.SelectedIndex = defaultFontIdx >= 0 ? defaultFontIdx : 0;

        // Start continuous visualizer & animation loop (ambient motion when paused, reactive when playing)
        _playbackTimer.Start();

        await LoadLibraryAsync();

        // If library has tracks, load the first one by default
        if (_libraryItems.Count > 0)
        {
            LoadAudioTrack(_libraryItems[0]);
        }
    }

    private void StudioPage_Unloaded(object sender, RoutedEventArgs e)
    {
        _playbackTimer.Stop();
        _player.Pause();
    }

    private async Task LoadLibraryAsync()
    {
        _libraryItems.Clear();
        var items = await VidaApiClient.Instance.GetLibraryAsync();
        foreach (var item in items)
        {
            _libraryItems.Add(item);
        }
    }

    private void PlaybackSession_PlaybackStateChanged(MediaPlaybackSession sender, object args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (sender.PlaybackState == MediaPlaybackState.Playing)
            {
                PlayPauseGlyph.Glyph = "\uE769"; // Pause
            }
            else
            {
                PlayPauseGlyph.Glyph = "\uE768"; // Play
            }
        });
    }

    private void PlaybackTimer_Tick(object? sender, object e)
    {
        bool isPlaying = _player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing;

        if (isPlaying)
        {
            var session = _player.PlaybackSession;
            var pos = session.Position;
            var dur = session.NaturalDuration;

            if (dur > TimeSpan.Zero)
            {
                TotalTimeText.Text = dur.ToString(@"mm\:ss\.ff");
                WaveformSlider.Maximum = dur.TotalSeconds;
            }

            CurrentTimeText.Text = pos.ToString(@"mm\:ss\.ff");
            WaveformSlider.Value = pos.TotalSeconds;

            // Rotate center vinyl disc in DirectX (playing speed)
            VinylRotateTransform.Angle = (VinylRotateTransform.Angle + 2.0) % 360;

            // Synchronize Khmer Lyrics
            var activeLine = _lyricLines.FirstOrDefault(l => l.IsActive(pos));
            if (activeLine != null && !string.IsNullOrEmpty(activeLine.Text))
            {
                StageLyricsText.Text = activeLine.Text;
                LyricTimecodeText.Text = $"{activeLine.StartTime:mm\\:ss} → {activeLine.EndTime:mm\\:ss} ({(int)(activeLine.Confidence * 100)}% Confidence)";
            }
        }
        else
        {
            // Ambient subtle vinyl rotation when paused/idle
            VinylRotateTransform.Angle = (VinylRotateTransform.Angle + 0.4) % 360;
        }

        // Animate spectrum bars dynamically matching active theme and palette on EVERY frame
        UpdateVisualizerFrame();
    }

    private async void LoadAudioTrack(MediaItem item)
    {
        if (string.IsNullOrEmpty(item.Path)) return;

        string resolvedPath = item.Path;
        if (!File.Exists(resolvedPath))
        {
            string projectRoot = BackendService.Instance.GetProjectRoot();
            string candidate = Path.Combine(projectRoot, resolvedPath.TrimStart('\\', '/'));
            if (File.Exists(candidate))
            {
                resolvedPath = candidate;
            }
            else
            {
                string inUploads = Path.Combine(projectRoot, "uploads", "audio", item.Name);
                if (File.Exists(inUploads))
                {
                    resolvedPath = inUploads;
                }
            }
        }

        if (!File.Exists(resolvedPath)) return;

        item.Path = resolvedPath;
        _currentAudioPath = resolvedPath;
        MasterTrackNameText.Text = item.Name;
        string cleanTitle = Path.GetFileNameWithoutExtension(item.Name);
        StageSongTitleText.Text = cleanTitle;
        TitleInputBox.Text = cleanTitle;
        
        // Reset artist and lyrics to avoid stale data from previous tracks
        StageArtistText.Text = "Unknown Artist";
        ArtistInputBox.Text = "";
        StageLyricsText.Text = "No lyrics loaded... 🧠 Scan ready.";
        UpdateLoadedLyrics(new List<LyricLine>());
        
        BadgeLine1Box.Text = cleanTitle.Length > 12 ? cleanTitle[..12] : cleanTitle;
        ProjectTitleText.Text = $"Project: {cleanTitle} - 60 FPS";

        // Auto-load cached .lrc lyrics if they exist from a previous process
        string lrcPath = Path.ChangeExtension(resolvedPath, ".lrc");
        if (File.Exists(lrcPath))
        {
            var lyrics = await VidaApiClient.Instance.ImportSubtitleFileAsync(lrcPath);
            if (lyrics != null && lyrics.Count > 0)
            {
                UpdateLoadedLyrics(lyrics);
                StageLyricsText.Text = lyrics[0].Text;
                
                // Show right panel
                TabRightTeleprompterBtn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
                TabRightStyleBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
                RightTeleprompterPanel.Visibility = Visibility.Visible;
                RightStylePanel.Visibility = Visibility.Collapsed;
            }
        }

        // Native Windows MediaPlayer loading with HTTP streaming fallback
        try
        {
            Uri mediaUri;
            if (!string.IsNullOrEmpty(item.Url))
            {
                mediaUri = new Uri($"{VidaApiClient.Instance.BaseUrl}{item.Url}");
            }
            else
            {
                mediaUri = new Uri(Path.GetFullPath(resolvedPath));
            }
            _player.Source = MediaSource.CreateFromUri(mediaUri);
            _player.Volume = VolumeSlider.Value / 100.0;
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[Studio Audio Player] Error loading {resolvedPath}: {ex.Message}");
        }

        // Fast Audio DNA Analysis in background (BPM, Mood, Energy - 1-2s)
        ShowActivity("Analyzing audio DNA & BPM...");
        _ = Task.Run(async () =>
        {
            var analysis = await VidaApiClient.Instance.AnalyzeAudioAsync(resolvedPath);

            DispatcherQueue.TryEnqueue(() =>
            {
                HideActivity();

                if (analysis.HasValue && analysis.Value.TryGetProperty("bpm", out var bpmProp))
                {
                    int bpm = bpmProp.GetInt32();
                    string mood = analysis.Value.TryGetProperty("mood", out var m) ? m.GetString() ?? "Dynamic" : "Dynamic";
                    AudioStatsBadge.Text = $"{bpm} BPM · {mood} · 60 FPS";
                    StatBpmText.Text = bpm.ToString();
                    StatEnergyText.Text = analysis.Value.TryGetProperty("energy", out var en) ? $"{(int)(en.GetDouble() * 100)}%" : "88%";
                }
            });
        });
    }

    private void UpdateLoadedLyrics(List<LyricLine> lyrics)
    {
        _lyricLines.Clear();
        _teleprompterItems.Clear();

        if (lyrics.Count > 0)
        {
            _lyricLines.AddRange(lyrics);
            foreach (var l in lyrics)
            {
                _teleprompterItems.Add(l);
            }
            StageLyricsText.Text = lyrics[0].Text;
            LyricTimecodeText.Text = $"Loaded {lyrics.Count} Synced Khmer Lines";
            TeleprompterLinesBadge.Text = $"{lyrics.Count} Lines";
        }
        else
        {
            StageLyricsText.Text = "ស្រឡាញ់អូនរហូតដល់ថ្ងៃសូន្យ 🌙✨";
            LyricTimecodeText.Text = "Standard Khmer Lyric Alignment";
            TeleprompterLinesBadge.Text = "0 Lines";
        }
    }

    private void ShowActivity(string message)
    {
        ActivityStatusText.Text = message;
        ActivityCapsule.Visibility = Visibility.Visible;
    }

    private void HideActivity()
    {
        ActivityCapsule.Visibility = Visibility.Collapsed;
    }

    // ================= SEGMENTED TAB SWITCHING =================
    private void TabLeft_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string tag)
        {
            TabLeftMediaBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabLeftAiBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            btn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];

            LeftMediaPanel.Visibility = tag == "media" ? Visibility.Visible : Visibility.Collapsed;
            LeftAiPanel.Visibility = tag == "ai" ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    private void TabRight_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string tag)
        {
            TabRightStyleBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabRightDirectorBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabRightDspBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabRightTeleprompterBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            btn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];

            RightStylePanel.Visibility = tag == "style" ? Visibility.Visible : Visibility.Collapsed;
            RightDirectorPanel.Visibility = tag == "director" ? Visibility.Visible : Visibility.Collapsed;
            RightDspPanel.Visibility = tag == "dsp" ? Visibility.Visible : Visibility.Collapsed;
            RightTeleprompterPanel.Visibility = tag == "lyrics" ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    // ================= YOUTUBE DOWNLOAD & PRESETS =================
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
            ShowActivity($"⚠️ {err}");
            await Task.Delay(3500);
            HideActivity();
        }
    }

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

    private async void BrowseLogo_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(App.CurrentWindow));
        picker.ViewMode = Windows.Storage.Pickers.PickerViewMode.Thumbnail;
        picker.SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.PicturesLibrary;
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");

        var file = await picker.PickSingleFileAsync();
        if (file != null)
        {
            LogoPathBox.Text = file.Path;
            
            // Update UI preview
            var bmp = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri(file.Path));
            BadgeLogoBrush.ImageSource = bmp;
            BadgeLogoEllipse.Visibility = Visibility.Visible;
            BadgeTextStack.Visibility = Visibility.Collapsed;
        }
    }

    private void FontSelector_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (FontSelector.SelectedItem is string fontName)
        {
            var fontFamily = new Microsoft.UI.Xaml.Media.FontFamily(fontName);
            if (StageLyricsText != null) StageLyricsText.FontFamily = fontFamily;
            if (StageSongTitleText != null) StageSongTitleText.FontFamily = fontFamily;
            if (StageArtistText != null) StageArtistText.FontFamily = fontFamily;
        }
    }

    // ================= DYNAMIC REACTIVE THEME & COLOR PALETTE =================
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

    private void ApplyThemeVisualizer(string theme)
    {
        _currentTheme = theme;
        UpdateVisualizerFrame();
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

        if (VinylOuterBorder != null) VinylOuterBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(accent));
        if (VinylCenterLabel != null) VinylCenterLabel.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(label));

        if (StageArtistText != null) StageArtistText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(artist));
        if (StageLyricsText != null) StageLyricsText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(ParseHexColor(lyric));

        _currentBarColors.Clear();
        foreach (var b in bars)
        {
            _currentBarColors.Add(ParseHexColor(b));
        }

        UpdateVisualizerFrame();
    }

    private void UpdateVisualizerFrame()
    {
        if (SpectrumPanel == null || SpectrumPanel.Children.Count == 0) return;

        bool isPlaying = _player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing;
        double ampScale = isPlaying ? 1.0 : 0.65;

        _wavePhase += isPlaying ? 0.20 : 0.08;
        int count = SpectrumPanel.Children.Count; // 24 bars

        for (int i = 0; i < count; i++)
        {
            if (SpectrumPanel.Children[i] is Rectangle rect)
            {
                // Ensure fill dynamically matches active palette colors
                if (_currentBarColors.Count > 0)
                {
                    var col = _currentBarColors[i % _currentBarColors.Count];
                    rect.Fill = new Microsoft.UI.Xaml.Media.SolidColorBrush(col);
                }

                double targetHeight = 35;
                switch (_currentTheme)
                {
                    case "ocean_wave":
                    case "hyper_liquid":
                        // Smooth flowing oceanic sine wave
                        targetHeight = 22 + (38 + Math.Sin(i * 0.40 + _wavePhase) * 35) * ampScale;
                        break;

                    case "trap_circle":
                        // Heavy bass pump, center and side pulsing
                        double centerDist = Math.Abs(i - count / 2.0) / (count / 2.0);
                        targetHeight = 20 + ((1.0 - centerDist) * 70 + (isPlaying ? _random.Next(-8, 9) : 0)) * ampScale;
                        break;

                    case "neon_bars":
                    case "hologram_hud":
                        // Punchy electronic stepped equalizer
                        double freq = (double)i / count;
                        targetHeight = 18 + ((1.0 - freq * 0.7) * 75 + (isPlaying ? _random.Next(-12, 13) : Math.Sin(_wavePhase + i) * 10)) * ampScale;
                        break;

                    case "dna_helix":
                    case "quantum_vortex":
                    case "neural_synapse":
                        // Double interleaved harmonic waves
                        double phase = (i % 2 == 0) ? _wavePhase : _wavePhase + Math.PI;
                        targetHeight = 22 + (32 + Math.Sin(i * 0.45 + phase) * 36) * ampScale;
                        break;

                    case "angkor_mandala":
                    case "aurora_borealis":
                    case "sonic_nebula":
                        // Majestic cathedral spire symmetry
                        double norm = 1.0 - Math.Pow((i - count / 2.0) / (count / 2.0), 2);
                        targetHeight = 20 + (norm * 70 + Math.Sin(_wavePhase + i * 0.25) * 14) * ampScale;
                        break;

                    case "spectrum":
                    default:
                        // Standard audio frequency curve with live jitter
                        double normPos = (double)i / count;
                        double decay = Math.Exp(-normPos * 1.5);
                        targetHeight = 16 + (decay * 74 + (isPlaying ? _random.Next(-10, 11) : Math.Sin(_wavePhase + i * 0.3) * 8)) * ampScale;
                        break;
                }

                rect.Height = Math.Max(10, Math.Min(98, targetHeight));
            }
        }
    }

    private void LyricStyleCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_isApplyingTemplate) return;
        string? tag = (LyricStyleCombo?.SelectedItem as ComboBoxItem)?.Tag?.ToString()
                      ?? (e.AddedItems.Count > 0 ? (e.AddedItems[0] as ComboBoxItem)?.Tag?.ToString() : null);
        if (!string.IsNullOrEmpty(tag))
        {
            ApplyLyricStyle(tag);
        }
    }

    private void ApplyLyricStyle(string style)
    {
        if (StageLyricsText == null || LyricPillBorder == null) return;

        LyricPillBorder.Visibility = Visibility.Visible;

        switch (style)
        {
            case "karaoke":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
                StageLyricsText.FontSize = 19;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(220, 15, 23, 42));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 245, 158, 11));
                LyricPillBorder.BorderThickness = new Thickness(1.5);
                LyricPillBorder.CornerRadius = new CornerRadius(8);
                break;
            case "glow":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.ExtraBold;
                StageLyricsText.FontSize = 21;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(200, 30, 27, 75));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 168, 85, 247));
                LyricPillBorder.BorderThickness = new Thickness(2);
                LyricPillBorder.CornerRadius = new CornerRadius(12);
                break;
            case "bounce":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
                StageLyricsText.FontSize = 22;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(190, 88, 28, 135));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 236, 72, 153));
                LyricPillBorder.BorderThickness = new Thickness(1.5);
                LyricPillBorder.CornerRadius = new CornerRadius(14);
                break;
            case "cinematic":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Normal;
                StageLyricsText.FontSize = 16;
                StageLyricsText.FontStyle = Windows.UI.Text.FontStyle.Italic;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(160, 0, 0, 0));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(180, 217, 119, 6));
                LyricPillBorder.BorderThickness = new Thickness(1);
                LyricPillBorder.CornerRadius = new CornerRadius(4);
                break;
            case "pop":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
                StageLyricsText.FontSize = 18;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(240, 30, 27, 75));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 99, 102, 241));
                LyricPillBorder.BorderThickness = new Thickness(2);
                LyricPillBorder.CornerRadius = new CornerRadius(20);
                break;
            case "typewriter":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
                StageLyricsText.FontSize = 17;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(230, 24, 18, 12));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 217, 119, 6));
                LyricPillBorder.BorderThickness = new Thickness(1);
                LyricPillBorder.CornerRadius = new CornerRadius(4);
                break;
            case "highlight":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
                StageLyricsText.FontSize = 19;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(220, 40, 20, 10));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 251, 191, 36));
                LyricPillBorder.BorderThickness = new Thickness(2);
                LyricPillBorder.CornerRadius = new CornerRadius(16);
                break;
            case "fade":
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.Medium;
                StageLyricsText.FontSize = 18;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(170, 9, 13, 22));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(100, 100, 116, 139));
                LyricPillBorder.BorderThickness = new Thickness(1);
                LyricPillBorder.CornerRadius = new CornerRadius(6);
                break;
            case "none":
                LyricPillBorder.Visibility = Visibility.Collapsed;
                break;
            default:
                StageLyricsText.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
                StageLyricsText.FontSize = 18;
                LyricPillBorder.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(170, 9, 13, 22));
                LyricPillBorder.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(100, 100, 116, 139));
                LyricPillBorder.BorderThickness = new Thickness(1);
                LyricPillBorder.CornerRadius = new CornerRadius(6);
                break;
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

    // ================= AI TOOLS & TELEPROMPTER =================
    private async Task EnsureAudioLoadedAsync()
    {
        if (!string.IsNullOrEmpty(_currentAudioPath) && File.Exists(_currentAudioPath)) return;

        if (_libraryItems.Count > 0)
        {
            LoadAudioTrack(_libraryItems[0]);
            return;
        }

        var demo = await VidaApiClient.Instance.LoadSinisamutDemoAsync();
        if (demo.HasValue && demo.Value.TryGetProperty("audio_path", out var p))
        {
            string path = p.GetString() ?? "";
            var item = new MediaItem { Name = Path.GetFileName(path), Path = path, Type = "audio" };
            _libraryItems.Insert(0, item);
            LoadAudioTrack(item);
        }
    }

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

    private async void AutoSyncLyrics_Click(object sender, RoutedEventArgs e)
    {
        await EnsureAudioLoadedAsync();
        if (string.IsNullOrEmpty(_currentAudioPath))
        {
            ShowActivity("Please select or drop an audio track first.");
            await Task.Delay(1500);
            HideActivity();
            return;
        }

        string lang = (VocalLanguageCombo.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "km";
        string model = (AiModelCombo.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "gemini-fast";
        bool demucs = DemucsToggle.IsOn;

        ShowActivity("Auto-syncing lyrics with AI...");
        var lyrics = await VidaApiClient.Instance.TranscribeAudioAsync(_currentAudioPath, lang, model, demucs);
        HideActivity();

        if (lyrics == null || lyrics.Count == 0)
        {
            string trackName = string.IsNullOrEmpty(TitleInputBox.Text) ? Path.GetFileNameWithoutExtension(_currentAudioPath) : TitleInputBox.Text;
            lyrics = GetFallbackPoeticLyrics("romantic", trackName);
        }

        UpdateLoadedLyrics(lyrics);
    }

    private async void AiFixSpelling_Click(object sender, RoutedEventArgs e)
    {
        if (_lyricLines.Count == 0)
        {
            GenerateKhmerLyrics_Click(sender, e);
            return;
        }

        ShowActivity("Fixing phonetic spelling across song...");
        var fixedLyrics = await VidaApiClient.Instance.AutoFixLyricsAsync(_lyricLines);
        HideActivity();

        UpdateLoadedLyrics(fixedLyrics);
    }

    private async void ImportSubtitle_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        var hwnd = WindowNative.GetWindowHandle(App.CurrentWindow);
        InitializeWithWindow.Initialize(picker, hwnd);

        picker.FileTypeFilter.Add(".lrc");
        picker.FileTypeFilter.Add(".srt");
        picker.FileTypeFilter.Add(".vtt");
        picker.FileTypeFilter.Add(".txt");

        var file = await picker.PickSingleFileAsync();
        if (file != null)
        {
            ShowActivity("Parsing subtitle file...");
            var lyrics = await VidaApiClient.Instance.ImportSubtitleFileAsync(file.Path);
            HideActivity();
            UpdateLoadedLyrics(lyrics);
        }
    }

    private async void GenerateKhmerLyrics_Click(object sender, RoutedEventArgs e)
    {
        string genre = (LyricGenreCombo.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "romantic";
        string prompt = TitleInputBox.Text.Trim();
        if (string.IsNullOrEmpty(prompt)) prompt = "រាត្រីស្រមៃស្នេហ៍";

        ShowActivity("Composing poetic Khmer lyrics...");
        var result = await VidaApiClient.Instance.GenerateKhmerLyricsAsync(prompt, genre, 85);
        HideActivity();

        var parsed = new List<LyricLine>();

        if (result.HasValue)
        {
            var root = result.Value;
            if (root.TryGetProperty("title", out var titleProp) && !string.IsNullOrEmpty(titleProp.GetString()))
            {
                string newTitle = titleProp.GetString()!;
                TitleInputBox.Text = newTitle;
                StageSongTitleText.Text = newTitle;
                ProjectTitleText.Text = $"Project: {newTitle} - 60 FPS";
            }

            JsonElement lyrArray = default;
            bool found = false;
            if (root.TryGetProperty("lyrics_data", out var ld) && ld.ValueKind == JsonValueKind.Array)
            {
                lyrArray = ld;
                found = true;
            }
            else if (root.TryGetProperty("lyrics", out var l) && l.ValueKind == JsonValueKind.Array)
            {
                lyrArray = l;
                found = true;
            }

            if (found)
            {
                int idx = 0;
                foreach (var item in lyrArray.EnumerateArray())
                {
                    double s = item.TryGetProperty("start", out var sp) ? sp.GetDouble() : idx * 3.5;
                    double end = item.TryGetProperty("end", out var ep) ? ep.GetDouble() : s + 3.2;
                    string t = item.TryGetProperty("text", out var tp) ? tp.GetString() ?? "" : "";
                    if (!string.IsNullOrWhiteSpace(t))
                    {
                        parsed.Add(new LyricLine { LineId = idx++, StartTime = TimeSpan.FromSeconds(s), EndTime = TimeSpan.FromSeconds(end), Text = t });
                    }
                }
            }
        }

        // Resilient poetic fallback if backend is offline or warming up
        if (parsed.Count == 0)
        {
            parsed = GetFallbackPoeticLyrics(genre, prompt);
        }

        UpdateLoadedLyrics(parsed);

        // Switch right tab to teleprompter so user sees the lyrics immediately!
        TabRightTeleprompterBtn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        TabRightStyleBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
        TabRightDirectorBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
        TabRightDspBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];

        RightStylePanel.Visibility = Visibility.Collapsed;
        RightDirectorPanel.Visibility = Visibility.Collapsed;
        RightDspPanel.Visibility = Visibility.Collapsed;
        RightTeleprompterPanel.Visibility = Visibility.Visible;
    }

    private List<LyricLine> GetFallbackPoeticLyrics(string genre, string title)
    {
        var lyrics = new List<LyricLine>();
        string[] lines;

        switch (genre.ToLowerInvariant())
        {
            case "golden_era":
                lines = new[]
                {
                    $"ឱ! {title} ស្រស់ត្រកាលកាលជំនាន់មុន",
                    "សំនៀងរៃយំរណ្តំក្នុងរាត្រីរងារ",
                    "ចំប៉ាបាត់ដំបងស្រស់ល្អឆើតឆាយ",
                    "ផ្កាយព្រះចន្ទរះកណ្តាលវេហារំលឹកស្នេហ៍",
                    "ស្នេហាគ្រាដើមមិនដែលរសាយពីដួងចិត្ត"
                };
                break;
            case "melancholy":
                lines = new[]
                {
                    "ដំណក់ទឹកភ្លៀងធ្លាក់ស្រក់លើដំបូលផ្ទះ",
                    "ចិត្តរៀមស្ទើរបែកព្រោះបែកថ្លៃស្នេហា",
                    "រាត្រីរងារគ្មានស្រីក្បែរប្រាណដូចគ្រាមុន",
                    "ចាំអូនវិលវិញទោះបីខែឆ្នាំកន្លងផុតទៅ",
                    "ទឹកភ្នែកហូរស្រក់លាយឡំដំណក់ទឹកភ្លៀងរាត្រី"
                };
                break;
            case "romvong":
                lines = new[]
                {
                    "មកចុះស្រីស្រស់ឡើងរាំវង់ជាមួយបង",
                    "ចង្វាក់រាំក្បាច់សប្បាយរីករាយពេញភូមិស្ថាន",
                    "កន្ទ្រាក់អារម្មណ៍រាំលេងកម្សាន្តចូលឆ្នាំខ្មែរ",
                    "ស្គរដៃបន្លឺរណ្តំក្នុងចិត្តស្រស់ស្រាយ",
                    "រាំលេងសប្បាយក្នុងពិធីបុណ្យប្រពៃណីជាតិ"
                };
                break;
            case "modern_pop":
                lines = new[]
                {
                    $"Vibe ក្នុងរាត្រី {title} ភ្លើងពណ៌ស្រស់បំព្រង",
                    "Bass drop រណ្តំជំរុញឱ្យបេះដូងលោតញាប់",
                    "Flow ទៅតាមចង្វាក់ភ្លេងកន្ត្រាក់អារម្មណ៍យុវវ័យ",
                    "យើងរាំជាមួយគ្នាពេញមួយរាត្រីកុំខ្វល់រឿងអ្វី",
                    "Drop the beat, let the visualizer ignite the night!"
                };
                break;
            case "heritage":
                lines = new[]
                {
                    "មហានគរថ្មរុងរឿងលើដីសុវណ្ណភូមិខ្មែរ",
                    "ប្រាសាទអង្គរវត្តសក្ការៈនៃបុព្វបុរស",
                    "ក្បូរក្បាច់រចនាប្រណីតគ្មានពីរលើលោកា",
                    "ដួងព្រលឹងជាតិខ្មែររស់នៅជារៀងរហូតតទៅ",
                    "មោទនភាពជាតិខ្មែរលើទឹកដីអច្ឆរិយៈអស្ចារ្យ"
                };
                break;
            case "romantic":
            default:
                lines = new[]
                {
                    "រាត្រីស្ងប់ស្ងាត់ចិត្តនៅនឹកដល់រូបស្រី",
                    "ពន្លឺដួងចន្ទបំភ្លឺស្នេហ៍ក្នុងហឫទ័យស្មោះ",
                    "ទោះបីឃ្លាតឆ្ងាយចិត្តនៅក្បែរថ្លៃជានិច្ច",
                    "ស្រឡាញ់អូនរហូតដល់ថ្ងៃសូន្យ 🌙✨",
                    "ពាក្យសច្ចាស្នេហ៍មិនប្រែជាថ្មីឡើយណាពៅ"
                };
                break;
        }

        double start = 2.0;
        for (int i = 0; i < lines.Length; i++)
        {
            lyrics.Add(new LyricLine
            {
                LineId = i + 1,
                StartTime = TimeSpan.FromSeconds(start),
                EndTime = TimeSpan.FromSeconds(start + 4.5),
                Text = lines[i],
                Confidence = 0.98
            });
            start += 5.0;
        }

        return lyrics;
    }

    private async void PolishKhmerLyrics_Click(object sender, RoutedEventArgs e)
    {
        if (_lyricLines.Count == 0)
        {
            GenerateKhmerLyrics_Click(sender, e);
            return;
        }

        string allText = string.Join("\n", _lyricLines.Select(l => l.Text));

        ShowActivity("Polishing Khmer diacritics & subscripts...");
        string? polished = await VidaApiClient.Instance.PolishKhmerLyricsAsync(allText);
        HideActivity();

        if (!string.IsNullOrEmpty(polished))
        {
            string[] lines = polished.Split('\n', StringSplitOptions.RemoveEmptyEntries);
            for (int i = 0; i < Math.Min(lines.Length, _lyricLines.Count); i++)
            {
                _lyricLines[i].Text = lines[i].Trim();
            }
            UpdateLoadedLyrics(_lyricLines);
        }
    }

    private async void AskGemini_Click(object sender, RoutedEventArgs e)
    {
        string prompt = AiAssistantPromptBox.Text.Trim();
        if (string.IsNullOrEmpty(prompt))
        {
            prompt = "Suggest poetic Khmer rhymes and song ideas for: " + (string.IsNullOrEmpty(TitleInputBox.Text) ? "ស្នេហា" : TitleInputBox.Text);
            AiAssistantPromptBox.Text = prompt;
        }

        ShowActivity("Querying Gemini AI Assistant...");
        string? reply = await VidaApiClient.Instance.AskGeminiAssistantAsync(prompt, _lyricLines);
        HideActivity();

        if (!string.IsNullOrEmpty(reply))
        {
            var cd = new ContentDialog
            {
                Title = "🤖 Gemini AI Response",
                Content = new ScrollViewer
                {
                    MaxHeight = 400,
                    Content = new TextBlock { Text = reply, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 0), FontSize = 13 }
                },
                CloseButtonText = "Close",
                XamlRoot = this.XamlRoot
            };
            await cd.ShowAsync();
        }
    }

    private async void PasteAiPrompt_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var dataPackageView = Clipboard.GetContent();
            if (dataPackageView.Contains(StandardDataFormats.Text))
            {
                string text = await dataPackageView.GetTextAsync();
                AiAssistantPromptBox.Text = text.Trim();
                ShowActivity("Pasted lyrics into AI Assistant");
                await Task.Delay(1000);
                HideActivity();
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[Paste AI Prompt] Error: {ex.Message}");
        }
    }

    private async void AlignPromptLyrics_Click(object sender, RoutedEventArgs e)
    {
        string refText = AiAssistantPromptBox.Text.Trim();
        if (string.IsNullOrEmpty(refText))
        {
            ShowActivity("Please enter or paste reference lyrics first.");
            await Task.Delay(1500);
            HideActivity();
            return;
        }

        string[] rawLines = refText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                                   .Select(l => l.Trim())
                                   .Where(l => !string.IsNullOrEmpty(l))
                                   .ToArray();

        ShowActivity("Aligning teleprompter with reference lyrics...");
        var aligned = await VidaApiClient.Instance.AlignLyricsWithReferenceAsync(_lyricLines, refText, _currentAudioPath);
        HideActivity();

        if (aligned != null && aligned.Count > 0 && aligned != _lyricLines)
        {
            UpdateLoadedLyrics(aligned);
        }
        else if (rawLines.Length > 0)
        {
            // Robust local timecode distribution across audio duration
            var localAligned = new List<LyricLine>();
            double totalDur = _player.PlaybackSession.NaturalDuration.TotalSeconds;
            if (totalDur <= 5) totalDur = 180;
            double step = Math.Max(3.0, (totalDur - 4) / Math.Max(1, rawLines.Length));

            for (int i = 0; i < rawLines.Length; i++)
            {
                double start = 2.0 + i * step;
                double end = Math.Min(totalDur, start + step * 0.9);
                localAligned.Add(new LyricLine
                {
                    LineId = i + 1,
                    StartTime = TimeSpan.FromSeconds(start),
                    EndTime = TimeSpan.FromSeconds(end),
                    Text = rawLines[i],
                    Confidence = 1.0
                });
            }
            UpdateLoadedLyrics(localAligned);
        }

        // Switch right tab to teleprompter so user immediately sees their lyrics!
        TabRightTeleprompterBtn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        TabRightStyleBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
        TabRightDirectorBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
        TabRightDspBtn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];

        RightStylePanel.Visibility = Visibility.Collapsed;
        RightDirectorPanel.Visibility = Visibility.Collapsed;
        RightDspPanel.Visibility = Visibility.Collapsed;
        RightTeleprompterPanel.Visibility = Visibility.Visible;
    }

    private async void OpenPasteAlignModal_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new PasteAlignLyricsDialog
        {
            XamlRoot = this.XamlRoot
        };
        var result = await dlg.ShowAsync();
        if (result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(dlg.ReferenceLyricsText))
        {
            ShowActivity("Aligning teleprompter with original lyrics...");
            var aligned = await VidaApiClient.Instance.AlignLyricsWithReferenceAsync(_lyricLines, dlg.ReferenceLyricsText, _currentAudioPath);
            HideActivity();
            UpdateLoadedLyrics(aligned);
        }
    }

    private async void DoubleCheckLyrics_Click(object sender, RoutedEventArgs e)
    {
        if (_lyricLines.Count == 0)
        {
            GenerateKhmerLyrics_Click(sender, e);
            return;
        }

        ShowActivity("Validating 100% millisecond synchronization...");
        var verified = await VidaApiClient.Instance.AutoFixLyricsAsync(_lyricLines);
        HideActivity();
        UpdateLoadedLyrics(verified);
    }

    private void TeleprompterListView_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (TeleprompterListView.SelectedItem is LyricLine line)
        {
            _player.Position = line.StartTime;
            StageLyricsText.Text = line.Text;
        }
    }

    // ================= INSPECTOR & TITLE CONTROLS =================
    private void TitlesVisibleToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (OnScreenTitlesPanel != null && TitlesVisibleToggle != null)
            OnScreenTitlesPanel.Visibility = TitlesVisibleToggle.IsOn ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ClearTitle_Click(object sender, RoutedEventArgs e)
    {
        if (TitleInputBox != null) TitleInputBox.Text = string.Empty;
        if (StageSongTitleText != null) StageSongTitleText.Text = string.Empty;
    }

    private void ClearArtist_Click(object sender, RoutedEventArgs e)
    {
        if (ArtistInputBox != null) ArtistInputBox.Text = string.Empty;
        if (StageArtistText != null) StageArtistText.Text = string.Empty;
    }

    private void TitleInputBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (StageSongTitleText != null && TitleInputBox != null)
            StageSongTitleText.Text = TitleInputBox.Text;
    }

    private void ArtistInputBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (StageArtistText != null && ArtistInputBox != null)
            StageArtistText.Text = ArtistInputBox.Text;
    }

    private void TitleScaleSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (StageSongTitleText != null)
        {
            StageSongTitleText.FontSize = 24 * (e.NewValue / 100.0);
            if (TitleScaleValueText != null)
            {
                TitleScaleValueText.Text = $"{(int)e.NewValue}%";
            }
        }
    }

    private void CenterBadgeToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (CenterBadgeGrid != null && CenterBadgeToggle != null)
            CenterBadgeGrid.Visibility = CenterBadgeToggle.IsOn ? Visibility.Visible : Visibility.Collapsed;
    }

    private void BadgeLine1_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (BadgePrimaryText != null && BadgeLine1Box != null)
            BadgePrimaryText.Text = BadgeLine1Box.Text;
    }

    private void BadgeLine2_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (BadgeSecondaryText != null && BadgeLine2Box != null)
            BadgeSecondaryText.Text = BadgeLine2Box.Text;
    }

    private void SyncSongInfoToBadge_Click(object sender, RoutedEventArgs e)
    {
        BadgeLine1Box.Text = TitleInputBox.Text.Length > 12 ? TitleInputBox.Text[..12] : TitleInputBox.Text;
        BadgeLine2Box.Text = ArtistInputBox.Text.Length > 12 ? ArtistInputBox.Text[..12] : ArtistInputBox.Text;
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
        foreach (var child in SpectrumPanel.Children)
        {
            if (child is Rectangle rect)
            {
                rect.Height = 98;
            }
        }
    }

    // ================= YOUTUBE DETAILS DIALOG =================
    private async void YoutubeDetails_Click(object sender, RoutedEventArgs e)
    {
        string fullLyrics = string.Join("\n", _lyricLines.Select(l => $"{l.DisplayTime} {l.Text}"));
        var dlg = new YouTubeDetailsDialog
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

    // ================= ASPECT RATIO SWITCHER =================
    private void Aspect_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string aspect)
        {
            Aspect169Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            Aspect916Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            Aspect11Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];

            btn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];

            switch (aspect)
            {
                case "16:9":
                    StageContainer.Width = 720;
                    StageContainer.Height = 405;
                    break;
                case "9:16":
                    StageContainer.Width = 360;
                    StageContainer.Height = 640;
                    break;
                case "1:1":
                    StageContainer.Width = 460;
                    StageContainer.Height = 460;
                    break;
            }
        }
    }

    // ================= FILE INGESTION & DRAG DROP =================
    private async void DropZone_Tapped(object sender, Microsoft.UI.Xaml.Input.TappedRoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        var hwnd = WindowNative.GetWindowHandle(App.CurrentWindow);
        InitializeWithWindow.Initialize(picker, hwnd);

        picker.ViewMode = PickerViewMode.Thumbnail;
        picker.SuggestedStartLocation = PickerLocationId.MusicLibrary;
        picker.FileTypeFilter.Add(".mp3");
        picker.FileTypeFilter.Add(".wav");
        picker.FileTypeFilter.Add(".m4a");
        picker.FileTypeFilter.Add(".flac");
        picker.FileTypeFilter.Add(".mp4");

        var file = await picker.PickSingleFileAsync();
        if (file != null)
        {
            string? saved = await VidaApiClient.Instance.UploadAudioFileAsync(file.Path);
            var item = new MediaItem { Name = file.Name, Path = saved ?? file.Path, Type = "audio" };
            _libraryItems.Insert(0, item);
            LibrarySelector.SelectedItem = item; // Auto-select newly dropped item
            LoadAudioTrack(item);
            _player.Play();
        }
    }

    private void DropZone_DragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            e.AcceptedOperation = DataPackageOperation.Copy;
        }
    }

    private async void DropZone_Drop(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            var items = await e.DataView.GetStorageItemsAsync();
            if (items.Count > 0 && items[0] is StorageFile file)
            {
                string? saved = await VidaApiClient.Instance.UploadAudioFileAsync(file.Path);
                var item = new MediaItem { Name = file.Name, Path = saved ?? file.Path, Type = "audio" };
                _libraryItems.Insert(0, item);
                LibrarySelector.SelectedItem = item; // Auto-select newly dropped item
                LoadAudioTrack(item);
                _player.Play();
            }
        }
    }

    private void LibrarySelector_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (LibrarySelector.SelectedItem is MediaItem item)
        {
            LoadAudioTrack(item);
            _player.Play();
        }
    }

    private void LibraryListView_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        // Stubbed since LibraryListView is removed in the magic UI
        /*
        if (LibraryListView.SelectedItem is MediaItem item)
        {
            LoadAudioTrack(item);
            _player.Play();
        }
        */
    }

    // ================= TRANSPORT CONTROLS =================
    private void PlayPause_Click(object sender, RoutedEventArgs e)
    {
        if (_player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing)
        {
            _player.Pause();
        }
        else
        {
            _player.Play();
        }
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _player.Pause();
        _player.Position = TimeSpan.Zero;
        WaveformSlider.Value = 0;
        CurrentTimeText.Text = "00:00:00";
    }

    private void Prev_Click(object sender, RoutedEventArgs e)
    {
        var pos = _player.PlaybackSession.Position;
        _player.Position = pos > TimeSpan.FromSeconds(5) ? pos - TimeSpan.FromSeconds(5) : TimeSpan.Zero;
    }

    private void Next_Click(object sender, RoutedEventArgs e)
    {
        _player.Position = _player.PlaybackSession.Position + TimeSpan.FromSeconds(5);
    }

    private void WaveformSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (Math.Abs(_player.PlaybackSession.Position.TotalSeconds - e.NewValue) > 1.5)
        {
            _player.Position = TimeSpan.FromSeconds(e.NewValue);
        }
    }

    private void VolumeSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        _player.Volume = e.NewValue / 100.0;
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
            // 3. Transcription (AI)
            var lyrics = await VidaApiClient.Instance.TranscribeAudioAsync(_currentAudioPath, "km", "gemini-fast");
            DispatcherQueue.TryEnqueue(() =>
            {
                UpdateLoadedLyrics(lyrics);
                MagicLoadingSubtext.Text = "Auto-styling and preparing Render Engine...";
            });

            // 4. Auto-Select Theme & Palette randomly from top-tier ones
            string[] topThemes = { "ocean_wave", "quantum_vortex", "hyper_liquid", "aurora_borealis", "sonic_nebula", "dna_helix" };
            string[] topPalettes = { "cyberpunk", "angkor", "neon_synth", "royal_palace", "sunset" };
            
            string autoTheme = topThemes[_random.Next(topThemes.Length)];
            string autoPalette = topPalettes[_random.Next(topPalettes.Length)];
            string selectedFont = FontSelector.SelectedItem as string ?? "Leelawadee UI";

            DispatcherQueue.TryEnqueue(() =>
            {
                ApplyThemeVisualizer(autoTheme);
                ApplyColorPalette(autoPalette);
            });

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
                songTitle: StageSongTitleText.Text,
                artistName: TitleInputBox.Text,
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
        // Find the button and disable it during work
        // The sender isn't passed here, so we just toggle the UI generically
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
