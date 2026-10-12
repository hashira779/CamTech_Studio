using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Brushes;
using Microsoft.Graphics.Canvas.Effects;
using Microsoft.Graphics.Canvas.Geometry;
using Microsoft.Graphics.Canvas.UI.Xaml;
using Microsoft.UI.Xaml;
using System;
using System.Numerics;
using Windows.UI;

namespace VidaStudio.Styles.Visualizers;

public class Synthwave3DVisualizer : IVisualizerStyle
{
    public string Id => "synthwave_3d";
    public string DisplayName => "Synthwave 3D Landscape (Modern)";
    public bool UsesGpuPreview => true;

    private const int BANDS = 64;
    private float[] _smoothedSpectrum = new float[BANDS];
    private float _bassBump = 0f;
    private float _phase = 0f;
    
    private string _loadedLogoPath = "";
    private CanvasBitmap? _previewLogo = null;

    public UIElement CreatePreviewElement()
    {
        var canvas = new CanvasAnimatedControl
        {
            ClearColor = Color.FromArgb(0, 0, 0, 0),
            IsFixedTimeStep = true,
            TargetElapsedTime = TimeSpan.FromMilliseconds(16),
            HorizontalAlignment = HorizontalAlignment.Stretch,
            VerticalAlignment = VerticalAlignment.Stretch,
        };
        canvas.Draw += Canvas_Draw;
        return canvas;
    }

    public void UpdatePreview(UIElement element, VisualizerPreviewContext context) 
    {
        if (context.LogoPath != _loadedLogoPath && element is CanvasAnimatedControl canvas && !string.IsNullOrWhiteSpace(context.LogoPath))
        {
            _ = LoadPreviewLogoAsync(canvas, context.LogoPath);
        }
    }

    private async System.Threading.Tasks.Task LoadPreviewLogoAsync(CanvasAnimatedControl canvas, string path)
    {
        try
        {
            if (!canvas.ReadyToDraw) return;
            _previewLogo = await CanvasBitmap.LoadAsync(canvas, path);
            _loadedLogoPath = path;
        }
        catch
        {
            _previewLogo = null;
        }
    }

    private void Canvas_Draw(ICanvasAnimatedControl sender, CanvasAnimatedDrawEventArgs args)
    {
        var ds = args.DrawingSession;
        float w = (float)sender.Size.Width;
        float h = (float)sender.Size.Height;
        if (w < 10 || h < 10) return;

        _phase += 0.05f;

        // Simulate spectrum for preview
        for (int i = 0; i < BANDS; i++)
        {
            float val = (float)(Math.Sin(_phase * 0.5 + i * 0.2) * 0.5 + 0.5);
            _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.8f + val * 0.2f;
        }
        _bassBump = _smoothedSpectrum[0];

        RenderScene(ds, w, h, Microsoft.UI.Colors.DeepSkyBlue, Microsoft.UI.Colors.DeepPink, _previewLogo);
    }

    private void RenderScene(CanvasDrawingSession ds, float w, float h, Color c1, Color c2, CanvasBitmap? logo)
    {
        float cx = w / 2f;
        float cy = h * 0.5f;

        using var cl = new CanvasCommandList(ds.Device);
        using (var bds = cl.CreateDrawingSession())
        {
            // 1. Draw Sun
            float sunRadius = Math.Min(w, h) * 0.2f + _bassBump * 20f;
            bds.FillEllipse(cx, cy - 100, sunRadius, sunRadius, Color.FromArgb(255, 255, 100, 0));
            // Add stripes to sun
            bds.Blend = CanvasBlend.Copy;
            for (int i = 0; i < 10; i++)
            {
                float y = cy - 100 + sunRadius - i * 15;
                bds.FillRectangle(cx - sunRadius, y, sunRadius * 2, 4 + i, Microsoft.UI.Colors.Transparent);
            }
            bds.Blend = CanvasBlend.SourceOver;

            // Draw logo inside the sun
            if (logo != null)
            {
                float badgeRadius = sunRadius * 0.85f;
                using (var clipGeo = CanvasGeometry.CreateCircle(bds.Device, cx, cy - 100, badgeRadius))
                using (bds.CreateLayer(1.0f, clipGeo))
                {
                    float imgW = (float)logo.Size.Width;
                    float imgH = (float)logo.Size.Height;
                    float scale = (badgeRadius * 1.8f) / Math.Max(imgW, imgH);
                    
                    float targetW = imgW * scale;
                    float targetH = imgH * scale;

                    var destRect = new Windows.Foundation.Rect(cx - targetW / 2, cy - 100 - targetH / 2, targetW, targetH);
                    bds.DrawImage(logo, destRect);
                }
            }

            // 2. Draw 3D Grid Landscape
            float fov = 300f;
            float cameraY = 100f;
            
            bds.Blend = CanvasBlend.Add;
            
            int rows = 20;
            int cols = 40;
            float spacing = 50f;
            
            float zOffset = (_phase * 20f) % spacing;

            for (int r = 1; r < rows; r++)
            {
                float z = r * spacing - zOffset;
                float projY = cy + (cameraY * fov) / z;
                
                // Opacity fades in distance
                byte alpha = (byte)Math.Clamp(255 - (z / (rows * spacing)) * 255, 0, 255);
                Color gridColor = Color.FromArgb(alpha, c2.R, c2.G, c2.B);

                bds.DrawLine(0, projY, w, projY, gridColor, 1.5f);
            }

            for (int c = -cols/2; c < cols/2; c++)
            {
                float x = c * spacing;
                
                float zNear = spacing;
                float zFar = rows * spacing;

                float startProjX = cx + (x * fov) / zNear;
                float startProjY = cy + (cameraY * fov) / zNear;
                
                float endProjX = cx + (x * fov) / zFar;
                float endProjY = cy + (cameraY * fov) / zFar;

                bds.DrawLine(startProjX, startProjY, endProjX, endProjY, Color.FromArgb(100, c1.R, c1.G, c1.B), 1.5f);
            }

            // 3. Draw 3D Spectrum Mountains on the sides
            for (int i = 0; i < BANDS/2; i++)
            {
                float z = (i + 1) * spacing * 1.5f - zOffset;
                if (z < 10) continue;

                float hVal = _smoothedSpectrum[i] * 300f;
                
                // Left mountain
                float xL = -500f;
                float projXL = cx + (xL * fov) / z;
                float projYL_base = cy + (cameraY * fov) / z;
                float projYL_peak = cy + ((cameraY - hVal) * fov) / z;

                bds.DrawLine(projXL, projYL_base, projXL, projYL_peak, c1, 4f);

                // Right mountain
                float xR = 500f;
                float projXR = cx + (xR * fov) / z;
                float projYR_base = cy + (cameraY * fov) / z;
                float projYR_peak = cy + ((cameraY - hVal) * fov) / z;

                bds.DrawLine(projXR, projYR_base, projXR, projYR_peak, c2, 4f);
            }
            bds.Blend = CanvasBlend.SourceOver;
        }

        ds.DrawImage(cl);
        
        ds.Blend = CanvasBlend.Add;
        using var blur = new GaussianBlurEffect { BlurAmount = 8f, Source = cl };
        ds.DrawImage(blur, 0, 0, new Windows.Foundation.Rect(0, 0, w, h), 0.6f);
        ds.Blend = CanvasBlend.SourceOver;
    }

    public void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context)
    {
        _phase += 0.02f;
        
        int inputBands = context.Spectrum.Length;
        for (int i = 0; i < BANDS; i++)
        {
            float val = 0;
            if (inputBands > 0)
            {
                int binIndex = (int)((float)i / BANDS * inputBands * 0.5f);
                if (binIndex < inputBands) val = context.Spectrum[binIndex];
            }
            else
            {
                val = context.Bass * (1.0f - i / (float)BANDS);
            }
            _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.5f + val * 0.5f;
        }
        _bassBump = context.Bass;

        RenderScene(ds, context.Width, context.Height, context.PrimaryColor, context.SecondaryColor, context.LogoBitmap);
    }
}
