using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace VidaStudio;

/// <summary>
/// Provides application-specific behavior to supplement the default Application class.
/// </summary>
public partial class App : Application
{
    private Window? _window;
    public static Window CurrentWindow { get; private set; } = null!;

    public App()
    {
        InitializeComponent();
        UnhandledException += (sender, e) =>
        {
            e.Handled = true;
            string msg = e.Exception?.ToString() ?? "Unknown error";
            try { System.IO.File.WriteAllText(@"d:\Project\VIDA\crash.txt", msg); } catch { }
            try
            {
                if (CurrentWindow?.Content is FrameworkElement fe && fe.XamlRoot != null)
                {
                    fe.DispatcherQueue.TryEnqueue(async () =>
                    {
                        var dlg = new ContentDialog
                        {
                            Title = "⚠️ Unexpected Error",
                            Content = new ScrollViewer
                            {
                                Content = new TextBlock { Text = msg, TextWrapping = Microsoft.UI.Xaml.TextWrapping.Wrap, IsTextSelectionEnabled = true },
                                MaxHeight = 400
                            },
                            CloseButtonText = "OK",
                            XamlRoot = fe.XamlRoot
                        };
                        await dlg.ShowAsync();
                    });
                }
            }
            catch { }
        };
        AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
        {
            string msg = e.ExceptionObject?.ToString() ?? "Unknown fatal error";
            try { System.IO.File.WriteAllText(@"d:\Project\VIDA\crash.txt", msg); } catch { }
        };
        AppDomain.CurrentDomain.ProcessExit += (_, _) =>
        {
            Services.BackendService.Instance.Stop();
        };
    }

    protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
    {
        _window = new MainWindow();
        CurrentWindow = _window;
        _window.Closed += (_, _) =>
        {
            Services.BackendService.Instance.Stop();
        };
        _window.Activate();
    }
}
