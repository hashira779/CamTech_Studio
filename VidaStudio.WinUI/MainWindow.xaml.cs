using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.IO;
using VidaStudio.Pages;
using VidaStudio.Services;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace VidaStudio;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;
        AppWindow.SetIcon("Assets/AppIcon.ico");

        // Set default initial window size (1480 x 940)
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1480, 940));

        // Start backend service in background
        _ = BackendService.Instance.StartAsync();

        // Navigate to default studio page
        NavFrame.Navigate(typeof(StudioPage));
    }

    private void TitleBar_PaneToggleRequested(TitleBar sender, object args)
    {
        NavView.IsPaneOpen = !NavView.IsPaneOpen;
    }

    private void TitleBar_BackRequested(TitleBar sender, object args)
    {
        if (NavFrame.CanGoBack)
        {
            NavFrame.GoBack();
        }
    }

    private void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.IsSettingsSelected)
        {
            NavFrame.Navigate(typeof(SettingsPage));
        }
        else if (args.SelectedItem is NavigationViewItem item)
        {
            switch (item.Tag?.ToString())
            {
                case "studio":
                    NavFrame.Navigate(typeof(StudioPage));
                    break;
                case "auto":
                    NavFrame.Navigate(typeof(AutoPipelinePage));
                    break;
                case "styles":
                    NavFrame.Navigate(typeof(StylesPage));
                    break;
                case "export":
                    NavFrame.Navigate(typeof(ExportPage));
                    break;
                case "about":
                    NavFrame.Navigate(typeof(AboutPage));
                    break;
                default:
                    NavFrame.Navigate(typeof(StudioPage));
                    break;
            }
        }
    }

    private void Grid_DragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            e.AcceptedOperation = DataPackageOperation.Copy;
            DropOverlay.Visibility = Visibility.Visible;
        }
    }

    private void Grid_DragLeave(object sender, DragEventArgs e)
    {
        DropOverlay.Visibility = Visibility.Collapsed;
    }

    private async void Grid_Drop(object sender, DragEventArgs e)
    {
        DropOverlay.Visibility = Visibility.Collapsed;

        if (e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            var items = await e.DataView.GetStorageItemsAsync();
            if (items.Count > 0 && items[0] is StorageFile file)
            {
                string ext = Path.GetExtension(file.Path).ToLowerInvariant();
                if (ext is ".mp3" or ".wav" or ".m4a" or ".flac" or ".aac" or ".mp4")
                {
                    BackendService.Instance.AppendLog($"[VIDA Drag-and-Drop] Ingesting dropped media: {file.Path}");
                    string? uploadedPath = await VidaApiClient.Instance.UploadAudioFileAsync(file.Path);
                    if (!string.IsNullOrEmpty(uploadedPath))
                    {
                        // Navigate to studio and load
                        NavFrame.Navigate(typeof(StudioPage));
                    }
                }
            }
        }
    }
}
