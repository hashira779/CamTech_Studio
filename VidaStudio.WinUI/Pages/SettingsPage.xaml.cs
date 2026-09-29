using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using VidaStudio.ViewModels;

namespace VidaStudio.Pages;

public sealed partial class SettingsPage : Page
{
    public SettingsViewModel ViewModel { get; } = new();

    public SettingsPage()
    {
        InitializeComponent();
    }

    private async void RestartBackend_Click(object sender, RoutedEventArgs e)
    {
        await ViewModel.RestartBackendCommand.ExecuteAsync(null);
    }

    private void ClearLogs_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ClearLogsCommand.Execute(null);
    }
}
