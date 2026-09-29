using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using VidaStudio.ViewModels;

namespace VidaStudio.Pages;

public sealed partial class ExportPage : Page
{
    public ExportViewModel ViewModel { get; } = new();

    public ExportPage()
    {
        InitializeComponent();
    }

    private async void StartExport_Click(object sender, RoutedEventArgs e)
    {
        await ViewModel.StartExportCommand.ExecuteAsync(null);
    }
}
