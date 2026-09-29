using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using VidaStudio.ViewModels;

namespace VidaStudio.Pages;

public sealed partial class AutoPipelinePage : Page
{
    public AutoPipelineViewModel ViewModel { get; } = new();

    public AutoPipelinePage()
    {
        InitializeComponent();
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        await ViewModel.StartPipelineCommand.ExecuteAsync(null);
    }

    private void Reset_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ResetPipelineCommand.Execute(null);
    }
}
