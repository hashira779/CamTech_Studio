using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Brushes;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System;
using System.Numerics;
using Windows.UI;

namespace VidaStudio.Styles.Visualizers;

public class ModernOrbVisualizer : IVisualizerStyle
{
    public string Id => "modern_orb";
    public string DisplayName => "2026 Glassmorphic Orb";

    public UIElement CreatePreviewElement()
    {
        var grid = new Grid
        {
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, -60, 0, 0)
        };

        var auraGlow = new Ellipse
        {
            Name = "AuraGlow",
            Width = 240,
            Height = 240,
            Opacity = 0.4
        };
        var radialBrush = new RadialGradientBrush
        {
            GradientOrigin = new Windows.Foundation.Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5
        };
        radialBrush.GradientStops.Add(new GradientStop { Color = ColorHelper.FromArgb(255, 236, 72, 153), Offset = 0.0 });
        radialBrush.GradientStops.Add(new GradientStop { Color = ColorHelper.FromArgb(0, 236, 72, 153), Offset = 1.0 });
        auraGlow.Fill = radialBrush;
        grid.Children.Add(auraGlow);

        var corePulse = new Ellipse
        {
            Name = "CorePulseOrb",
            Width = 140,
            Height = 140
        };
        var linearBrush = new LinearGradientBrush
        {
            StartPoint = new Windows.Foundation.Point(0, 0),
            EndPoint = new Windows.Foundation.Point(1, 1)
        };
        linearBrush.GradientStops.Add(new GradientStop { Color = ColorHelper.FromArgb(255, 139, 92, 246), Offset = 0.0 });
        linearBrush.GradientStops.Add(new GradientStop { Color = ColorHelper.FromArgb(255, 236, 72, 153), Offset = 1.0 });
        corePulse.Fill = linearBrush;
        grid.Children.Add(corePulse);

        var glassRing = new Ellipse
        {
            Width = 160,
            Height = 160,
            StrokeThickness = 2,
            Stroke = new SolidColorBrush(ColorHelper.FromArgb(40, 255, 255, 255)),
            Opacity = 0.6
        };
        grid.Children.Add(glassRing);

        return grid;
    }

    public void UpdatePreview(UIElement element, VisualizerPreviewContext context)
    {
        if (element is not Grid grid) return;
        if (grid.Children.Count < 2) return;
        
        var auraGlow = grid.Children[0] as Ellipse;
        var corePulse = grid.Children[1] as Ellipse;
        
        if (auraGlow == null || corePulse == null) return;

        double scale = 1.0 + (Math.Sin(context.WavePhase) * 0.15 * context.AmplitudeScale);
        if (corePulse.RenderTransform is not ScaleTransform st)
        {
            st = new ScaleTransform { CenterX = 70, CenterY = 70 };
            corePulse.RenderTransform = st;
        }
        st.ScaleX = scale;
        st.ScaleY = scale;

        double auraScale = 1.0 + (Math.Sin(context.WavePhase * 0.8) * 0.2 * context.AmplitudeScale);
        if (auraGlow.RenderTransform is not ScaleTransform stAura)
        {
            stAura = new ScaleTransform { CenterX = 120, CenterY = 120 };
            auraGlow.RenderTransform = stAura;
        }
        stAura.ScaleX = auraScale;
        stAura.ScaleY = auraScale;
        auraGlow.Opacity = 0.3 + (Math.Sin(context.WavePhase * 1.5) * 0.2 * context.AmplitudeScale);
    }

    public void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context)
    {
        float centerX = context.Width / 2f;
        float centerY = context.Height / 2f - 100f; // Shifted up slightly
                
        // Bass pulse
        float pulse = 1.0f + (context.Bass * 0.4f);
        float radius = 250f * pulse;

        // Draw Aura Glow
        using (var auraGradient = new CanvasRadialGradientBrush(ds.Device, context.SecondaryColor, Colors.Transparent))
        {
            auraGradient.Center = new Vector2(centerX, centerY);
            auraGradient.RadiusX = radius * 1.5f;
            auraGradient.RadiusY = radius * 1.5f;
            ds.FillEllipse(centerX, centerY, radius * 1.5f, radius * 1.5f, auraGradient);
        }

        // Draw Core Pulse Orb
        using (var coreGradient = new CanvasLinearGradientBrush(ds.Device, context.PrimaryColor, context.SecondaryColor))
        {
            coreGradient.StartPoint = new Vector2(centerX - radius, centerY - radius);
            coreGradient.EndPoint = new Vector2(centerX + radius, centerY + radius);
            ds.FillEllipse(centerX, centerY, radius, radius, coreGradient);
        }

        // Draw Logo inside Orb
        if (context.LogoBitmap != null)
        {
            float logoSize = radius * 1.2f;
            var destRect = new Windows.Foundation.Rect(centerX - (logoSize / 2), centerY - (logoSize / 2), logoSize, logoSize);
            ds.DrawImage(context.LogoBitmap, destRect, context.LogoBitmap.Bounds, 1.0f);
        }
    }
}
