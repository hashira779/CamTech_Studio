using Microsoft.UI.Xaml.Controls;

namespace VidaStudio.Dialogs;

public sealed partial class PasteAlignLyricsDialog : ContentDialog
{
    public string ReferenceLyricsText => LyricsInputBox.Text;

    public PasteAlignLyricsDialog()
    {
        InitializeComponent();
    }

    private void LyricsInputBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        string[] lines = LyricsInputBox.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        LineCountBadge.Text = $"{lines.Length} Lines";
    }
}
