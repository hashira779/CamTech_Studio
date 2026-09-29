using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.UI.Dispatching;
using VidaStudio.Services;

namespace VidaStudio.ViewModels;

public partial class SettingsViewModel : ObservableObject
{
    private readonly DispatcherQueue _dispatcherQueue;

    [ObservableProperty]
    public partial string BackendUrl { get; set; } = string.Empty;

    [ObservableProperty]
    public partial bool IsBackendRunning { get; set; }

    [ObservableProperty]
    public partial bool IsBackendReady { get; set; }

    [ObservableProperty]
    public partial string PythonPath { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string GeminiApiKey { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SelectedDemucsDevice { get; set; } = "CUDA GPU (Auto-Detect)";

    [ObservableProperty]
    public partial string SelectedKhmerModel { get; set; } = "Gemini Cloud AI Fast-Path (Recommended)";

    public ObservableCollection<string> DemucsDevices { get; } = new()
    {
        "CUDA GPU (Auto-Detect)",
        "CPU (Multi-threaded)",
        "DirectML (Windows Hardware)"
    };

    public ObservableCollection<string> KhmerModels { get; } = new()
    {
        "Gemini Cloud AI Fast-Path (Recommended)",
        "Qwen3-Khmer-ASR (Local)",
        "OpenAI Whisper Large-v3"
    };

    public ObservableCollection<string> BackendLogs { get; } = new();

    public SettingsViewModel()
    {
        _dispatcherQueue = DispatcherQueue.GetForCurrentThread();

        var bs = BackendService.Instance;
        BackendUrl = bs.BaseUrl;
        IsBackendRunning = bs.IsRunning;
        IsBackendReady = bs.IsReady;
        PythonPath = bs.PythonPath;

        foreach (var log in bs.GetLogs())
        {
            BackendLogs.Add(log);
        }

        bs.LogReceived += OnLogReceived;
        bs.StatusChanged += OnStatusChanged;
    }

    private void OnStatusChanged()
    {
        _dispatcherQueue.TryEnqueue(() =>
        {
            var bs = BackendService.Instance;
            IsBackendRunning = bs.IsRunning;
            IsBackendReady = bs.IsReady;
            BackendUrl = bs.BaseUrl;
        });
    }

    private void OnLogReceived(string log)
    {
        _dispatcherQueue.TryEnqueue(() =>
        {
            BackendLogs.Add(log);
            if (BackendLogs.Count > 500)
            {
                BackendLogs.RemoveAt(0);
            }
        });
    }

    [RelayCommand]
    public async Task RestartBackendAsync()
    {
        BackendService.Instance.Stop();
        await BackendService.Instance.StartAsync();
    }

    [RelayCommand]
    public void ClearLogs()
    {
        BackendLogs.Clear();
    }
}
