using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using VidaStudio.Models;
using VidaStudio.ViewModels;

namespace VidaStudio.Pages;

public sealed partial class StylesPage : Page
{
    public StylesViewModel ViewModel { get; } = new();

    public StylesPage()
    {
        InitializeComponent();
    }

    private void StyleGridView_ItemClick(object sender, ItemClickEventArgs e)
    {
        if (e.ClickedItem is VisualStyle style)
        {
            ViewModel.SelectStyleCommand.Execute(style);
        }
    }

    private void PromptChip_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string prompt)
        {
            ViewModel.DirectorPrompt = prompt;
        }
    }
}
