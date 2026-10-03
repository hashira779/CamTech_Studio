using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.IO;
using VidaStudio.Models;
using VidaStudio.Services;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace VidaStudio.Pages;

/// <summary>
/// Library: Drag & Drop, Media picker, track loading.
/// </summary>
public sealed partial class StudioPage
{
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
}
