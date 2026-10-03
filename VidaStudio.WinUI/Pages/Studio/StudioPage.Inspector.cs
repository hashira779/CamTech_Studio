using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace VidaStudio.Pages;

public sealed partial class StudioPage : Page
{
    private async void BrowseLogo_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(App.CurrentWindow));
        picker.ViewMode = Windows.Storage.Pickers.PickerViewMode.Thumbnail;
        picker.SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.PicturesLibrary;
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");

        var file = await picker.PickSingleFileAsync();
        if (file != null)
        {
            LogoPathBox.Text = file.Path;
            
            // Update UI preview
            // var bmp = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri(file.Path));
            // BadgeLogoBrush.ImageSource = bmp;
            // BadgeLogoEllipse.Visibility = Visibility.Visible;
            // BadgeTextStack.Visibility = Visibility.Collapsed;
        }
    }

    private void FontSelector_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (FontSelector.SelectedItem is string fontName)
        {
            var fontFamily = new Microsoft.UI.Xaml.Media.FontFamily(fontName);
            if (StageLyricsText != null) StageLyricsText.FontFamily = fontFamily;
            if (StageSongTitleText != null) StageSongTitleText.FontFamily = fontFamily;
            if (StageArtistText != null) StageArtistText.FontFamily = fontFamily;
        }
    }

    // ================= INSPECTOR & TITLE CONTROLS =================
    private void TitlesVisibleToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (OnScreenTitlesPanel != null && TitlesVisibleToggle != null)
            OnScreenTitlesPanel.Visibility = TitlesVisibleToggle.IsOn ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ClearTitle_Click(object sender, RoutedEventArgs e)
    {
        if (TitleInputBox != null) TitleInputBox.Text = string.Empty;
        if (StageSongTitleText != null) StageSongTitleText.Text = string.Empty;
    }

    private void ClearArtist_Click(object sender, RoutedEventArgs e)
    {
        if (ArtistInputBox != null) ArtistInputBox.Text = string.Empty;
        if (StageArtistText != null) StageArtistText.Text = string.Empty;
    }

    private void TitleInputBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (StageSongTitleText != null && TitleInputBox != null)
            StageSongTitleText.Text = TitleInputBox.Text;
    }

    private void ArtistInputBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (StageArtistText != null && ArtistInputBox != null)
            StageArtistText.Text = ArtistInputBox.Text;
    }

    private void TitleScaleSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (StageSongTitleText != null)
        {
            StageSongTitleText.FontSize = 24 * (e.NewValue / 100.0);
            if (TitleScaleValueText != null)
            {
                TitleScaleValueText.Text = $"{(int)e.NewValue}%";
            }
        }
    }

    private void CenterBadgeToggle_Toggled(object sender, RoutedEventArgs e)
    {
        // if (CenterBadgeGrid != null && CenterBadgeToggle != null)
        //     CenterBadgeGrid.Visibility = CenterBadgeToggle.IsOn ? Visibility.Visible : Visibility.Collapsed;
    }

    private void BadgeLine1_TextChanged(object sender, TextChangedEventArgs e)
    {
        // if (BadgePrimaryText != null && BadgeLine1Box != null)
        //     BadgePrimaryText.Text = BadgeLine1Box.Text;
    }

    private void BadgeLine2_TextChanged(object sender, TextChangedEventArgs e)
    {
        // if (BadgeSecondaryText != null && BadgeLine2Box != null)
        //     BadgeSecondaryText.Text = BadgeLine2Box.Text;
    }

    private void SyncSongInfoToBadge_Click(object sender, RoutedEventArgs e)
    {
        BadgeLine1Box.Text = TitleInputBox.Text.Length > 12 ? TitleInputBox.Text[..12] : TitleInputBox.Text;
        BadgeLine2Box.Text = ArtistInputBox.Text.Length > 12 ? ArtistInputBox.Text[..12] : ArtistInputBox.Text;
    }

    // ================= ASPECT RATIO SWITCHER =================
    private void Aspect_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string aspect)
        {
            Aspect169Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            Aspect916Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            Aspect11Btn.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];

            btn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];

            switch (aspect)
            {
                case "16:9":
                    StageContainer.Width = 720;
                    StageContainer.Height = 405;
                    break;
                case "9:16":
                    StageContainer.Width = 360;
                    StageContainer.Height = 640;
                    break;
                case "1:1":
                    StageContainer.Width = 460;
                    StageContainer.Height = 460;
                    break;
            }
        }
    }
}
