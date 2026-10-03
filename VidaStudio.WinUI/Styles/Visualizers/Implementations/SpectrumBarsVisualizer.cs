using Microsoft.Graphics.Canvas;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System;

namespace VidaStudio.Styles.Visualizers;

public class SpectrumBarsVisualizer : IVisualizerStyle
{
    public string Id => "spectrum_bars";
    public string DisplayName => "Classic Spectrum Bars";

    private const int BARS_COUNT = 32;

    public UIElement CreatePreviewElement()
    {
        var panel = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Bottom,
            Height = 200,
            Spacing = 4
        };

        for (int i = 0; i < BARS_COUNT; i++)
        {
            var rect = new Rectangle
            {
                Width = 14,
                Height = 10,
                RadiusX = 7,
                RadiusY = 7,
                VerticalAlignment = VerticalAlignment.Bottom
            };
            panel.Children.Add(rect);
        }

        return panel;
    }

    public void UpdatePreview(UIElement element, VisualizerPreviewContext context)
    {
        if (element is not StackPanel panel) return;

        for (int i = 0; i < BARS_COUNT; i++)
        {
            if (i < panel.Children.Count && panel.Children[i] is Rectangle rect)
            {
                rect.Fill = new SolidColorBrush(context.PrimaryColor);

                // Add some chaotic harmonic waves to simulate music spectrum if we don't have real data
                double harmonic1 = Math.Sin(context.WavePhase + (i * 0.5));
                double harmonic2 = Math.Sin((context.WavePhase * 1.3) - (i * 0.8));
                double combined = (harmonic1 * 0.5) + (harmonic2 * 0.5);
                double mapped = (combined + 1.0) / 2.0;

                double centerDistNorm = Math.Abs(i - BARS_COUNT / 2.0) / (BARS_COUNT / 2.0);
                double eqBias = 1.0 - (centerDistNorm * 0.5); 
                
                double targetH = 10 + (mapped * 140 * context.AmplitudeScale * eqBias);

                double currentHeight = rect.Height;
                if (double.IsNaN(currentHeight)) currentHeight = 10;
                
                rect.Height = currentHeight + (targetH - currentHeight) * 0.45;
                rect.Opacity = Math.Max(0.15, 1.0 - (centerDistNorm * 0.85));
            }
        }
    }

    public void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context)
    {
        float barWidth = (context.Width - 100) / (float)BARS_COUNT;
        
        for (int i = 0; i < BARS_COUNT; i++)
        {
            float val = 0;
            if (context.Spectrum.Length > 0)
            {
                int index = i * (context.Spectrum.Length / BARS_COUNT);
                if (index < context.Spectrum.Length) val = context.Spectrum[index];
            }
            else
            {
                // Fallback pulse
                val = (float)(0.2 + context.Bass * 0.8); 
            }
            
            float h = 20 + (val * 400f);
            var rect = new Windows.Foundation.Rect(50 + (i * barWidth), context.Height / 2 - h / 2, barWidth - 4, h);
            ds.FillRoundedRectangle(rect, 10, 10, context.PrimaryColor);
        }
    }
}
