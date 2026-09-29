using Microsoft.UI.Xaml.Controls;

namespace VidaStudio.Dialogs;

public sealed partial class YouTubeDetailsDialog : ContentDialog
{
    public string VideoTitle
    {
        get => YtTitleBox.Text;
        set => YtTitleBox.Text = value;
    }

    public string VideoDescription
    {
        get => YtDescBox.Text;
        set => YtDescBox.Text = value;
    }

    public string VideoTags
    {
        get => YtTagsBox.Text;
        set => YtTagsBox.Text = value;
    }

    public string PrivacyStatus
    {
        get => (YtPrivacyCombo.SelectedItem as ComboBoxItem)?.Content?.ToString()?.Contains("Private") == true ? "private" :
               (YtPrivacyCombo.SelectedItem as ComboBoxItem)?.Content?.ToString()?.Contains("Unlisted") == true ? "unlisted" : "public";
    }

    public YouTubeDetailsDialog()
    {
        InitializeComponent();
    }
}
