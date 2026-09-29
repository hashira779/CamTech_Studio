using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Collections.ObjectModel;
using VidaStudio.Models;

namespace VidaStudio.Dialogs;

public sealed partial class KhmerTemplatesDialog : ContentDialog
{
    private readonly ObservableCollection<KhmerTemplate> _displayedTemplates = new();
    public KhmerTemplate? SelectedTemplate { get; private set; }

    public KhmerTemplatesDialog()
    {
        InitializeComponent();
        TemplatesGridView.ItemsSource = _displayedTemplates;
        LoadCategory("all");
    }

    private void CategoryTab_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string cat)
        {
            // Reset styles
            TabAll.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabLegends.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabGolden.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabAngkor.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabRomantic.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabNature.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];
            TabFestive.Style = (Style)Application.Current.Resources["DefaultButtonStyle"];

            btn.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
            LoadCategory(cat);
        }
    }

    private void LoadCategory(string cat)
    {
        _displayedTemplates.Clear();

        if (cat == "all")
        {
            foreach (var t in KhmerTemplate.AllTemplates)
            {
                _displayedTemplates.Add(t);
            }
        }
        else if (cat == "singers")
        {
            // Convert singers into template cards
            foreach (var singer in KhmerSinger.AllSingers)
            {
                _displayedTemplates.Add(new KhmerTemplate
                {
                    Id = singer.Id,
                    Category = "🎙️ Legends",
                    TitleKm = singer.NameKm,
                    TitleEn = $"{singer.NameEn} ({singer.Years})",
                    Badge = singer.Badge,
                    Theme = singer.TemplateId == "candlelight" ? "ocean_wave" : "trap_circle",
                    Palette = singer.TemplateId == "candlelight" ? "candlelight" : "vintage_vinyl",
                    LyricStyle = "typewriter",
                    Desc = $"{singer.Title}. {singer.Desc}",
                    BestFor = string.Join(", ", singer.FamousSongs)
                });
            }
        }
        else
        {
            foreach (var t in KhmerTemplate.AllTemplates.Where(x => x.Category.Contains(cat) || cat.Contains(x.Category)))
            {
                _displayedTemplates.Add(t);
            }
        }
    }

    private void ApplyTemplate_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.DataContext is KhmerTemplate template)
        {
            SelectedTemplate = template;
            Hide();
        }
    }
}
