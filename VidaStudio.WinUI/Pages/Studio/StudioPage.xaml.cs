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

    public static StudioPage? Current { get; private set; }

    public string CurrentAudioPath => _currentAudioPath;
    public string CurrentTheme => _currentTheme;
    public string CurrentPalette => _currentColorPalette;
    public string CurrentSongTitle => StageSongTitleText?.Text ?? "My Song";
    public string CurrentArtistName => StageArtistText?.Text ?? "My Artist";
    public List<LyricLine> CurrentLyrics => _lyricLines;

    public StudioPage()
    {
        Current = this;
        InitializeComponent();

        LibrarySelector.ItemsSource = _libraryItems;

        _player.PlaybackSession.PlaybackStateChanged += PlaybackSession_PlaybackStateChanged;

        // Try to load default logo into UI preview
        // try
        // {
        //     var defaultLogoUri = new Uri("ms-appx:///Assets/VibeTunesLogo.png");
        //     BadgeLogoBrush.ImageSource = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(defaultLogoUri);
        //     BadgeLogoEllipse.Visibility = Visibility.Visible;
        //     BadgeTextStack.Visibility = Visibility.Collapsed;
        // }
        // catch { }

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

        // If library has tracks and we don't have one loaded yet, load the first one by default
        if (string.IsNullOrEmpty(_currentAudioPath) && _libraryItems.Count > 0)
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

        // Native Windows MediaPlayer loading via StorageFile (fixes silent playback)
        try
        {
            var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(resolvedPath));
            _player.Source = MediaSource.CreateFromStorageFile(file);
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
        
        // Auto-process if no lyrics exist (parity with Web app)
        AutoTriggerPipelineIfNoLyrics();
    }
    
    private async void AutoTriggerPipelineIfNoLyrics()
    {
        // Wait briefly to allow any synchronized loading (e.g., YouTube subtitles) to finish
        await Task.Delay(1000);
        if (_lyricLines == null || _lyricLines.Count == 0)
        {
            try
            {
                // Only auto-sync lyrics, don't trigger a full render
                AutoSyncLyrics_Click(this, new RoutedEventArgs());
            }
            catch (Exception ex)
            {
                BackendService.Instance.AppendLog($"[AutoTrigger] Error: {ex.Message}");
                HideActivity();
            }
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




}
