#pragma warning disable CS0618
using SkiaSharp;
using SkiaSharp.HarfBuzz;
using VidaStudio.Models;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// Renders kinetic karaoke typography and UI overlays (title, artist, logo).
/// Uses SkiaSharp for high-quality text rendering, anti-aliasing, and glassmorphism.
/// </summary>
public sealed class LyricRenderer
{
    private readonly int _width, _height;
    private readonly SKTypeface _boldFont;
    private readonly SKTypeface _regularFont;
    private SKBitmap? _logoBitmap;

    public LyricRenderer(int width, int height, string fontName = "Leelawadee UI")
    {
        _width = width;
        _height = height;

        // Load fonts with user selected font first, then fallback to Leelawadee UI (Khmer) and Segoe UI
        _boldFont = SKTypeface.FromFamilyName(fontName, SKFontStyleWeight.Bold, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ??
                    SKTypeface.FromFamilyName("Leelawadee UI", SKFontStyleWeight.Bold, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ?? 
                    SKTypeface.FromFamilyName("Segoe UI", SKFontStyleWeight.Bold, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ?? SKTypeface.Default;
        _regularFont = SKTypeface.FromFamilyName(fontName, SKFontStyleWeight.Normal, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ??
                       SKTypeface.FromFamilyName("Leelawadee UI", SKFontStyleWeight.Normal, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ?? 
                       SKTypeface.FromFamilyName("Segoe UI", SKFontStyleWeight.Normal, SKFontStyleWidth.Normal, SKFontStyleSlant.Upright) ?? SKTypeface.Default;
    }

    public void LoadLogo(string logoPath)
    {
        if (File.Exists(logoPath))
        {
            try
            {
                _logoBitmap = SKBitmap.Decode(logoPath);
            }
            catch { /* Ignore decoding errors */ }
        }
    }

    public void Render(SKCanvas canvas, float animTime, string title, string artist,
                       List<LyricLine> lyrics, ColorPalettes.Palette palette)
    {
        var priColor = new SKColor(palette.Primary.R, palette.Primary.G, palette.Primary.B);
        var secColor = new SKColor(palette.Secondary.R, palette.Secondary.G, palette.Secondary.B);

        // Draw header (Song Title & Artist)
        if (!string.IsNullOrEmpty(title) || !string.IsNullOrEmpty(artist))
        {
            DrawHeader(canvas, title, artist, priColor);
        }

        // Draw Watermark Logo if present
        if (_logoBitmap != null)
        {
            DrawLogo(canvas, animTime);
        }

        // Draw Karaoke Lyrics
        if (lyrics != null && lyrics.Count > 0)
        {
            DrawLyrics(canvas, animTime, lyrics, priColor, secColor);
        }
    }

    private void DrawHeader(SKCanvas canvas, string title, string artist, SKColor priColor)
    {
        float x = 50;
        float y = 70;

        using var titlePaint = new SKPaint
        {
            IsAntialias = true,
            Color = SKColors.White,
            Typeface = _boldFont,
            TextSize = 48
        };

        // Title drop shadow
        using var shadowPaint = titlePaint.Clone();
        shadowPaint.Color = SKColors.Black.WithAlpha(150);
        shadowPaint.MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, 4);

        if (!string.IsNullOrEmpty(title))
        {
            canvas.DrawShapedText(title, x + 2, y + 2, shadowPaint);
            canvas.DrawShapedText(title, x, y, titlePaint);
            y += 50;
        }

        if (!string.IsNullOrEmpty(artist))
        {
            using var artistPaint = new SKPaint
            {
                IsAntialias = true,
                Color = priColor,
                Typeface = _regularFont,
                TextSize = 32
            };

            canvas.DrawShapedText(artist, x + 2, y + 2, shadowPaint);
            canvas.DrawShapedText(artist, x, y, artistPaint);
        }
    }

    private void DrawLogo(SKCanvas canvas, float animTime)
    {
        if (_logoBitmap == null) return;

        float targetWidth = 140f;
        float scale = targetWidth / _logoBitmap.Width;
        float targetHeight = _logoBitmap.Height * scale;

        float cx = _width / 2;
        float cy = _height / 2;

        float rotationDegrees = (animTime * 30f) % 360f;

        canvas.Save();
        canvas.Translate(cx, cy);
        canvas.RotateDegrees(rotationDegrees);

        var destRect = new SKRect(-targetWidth / 2, -targetHeight / 2, targetWidth / 2, targetHeight / 2);
        
        // Clip to a perfect circle to hide ugly square white backgrounds
        using var clipPath = new SKPath();
        clipPath.AddCircle(0, 0, targetWidth / 2.05f); // Slightly smaller to fit inside the vinyl grooves
        canvas.ClipPath(clipPath, SKClipOperation.Intersect, antialias: true);

        using var paint = new SKPaint { IsAntialias = true };
        canvas.DrawBitmap(_logoBitmap, destRect, paint);
        
        canvas.Restore();
    }

    private void DrawLyrics(SKCanvas canvas, float currentTimeSec, List<LyricLine> lyrics, SKColor priColor, SKColor secColor)
    {
        var currentTime = TimeSpan.FromSeconds(currentTimeSec);

        // Find active and next lines
        LyricLine? activeLine = null;
        LyricLine? nextLine = null;
        float progress = 0f;

        for (int i = 0; i < lyrics.Count; i++)
        {
            var line = lyrics[i];
            
            // Check if current time is within this line's duration
            if (currentTime >= line.StartTime && currentTime <= line.EndTime)
            {
                activeLine = line;
                progress = (float)((currentTime - line.StartTime).TotalSeconds / (line.EndTime - line.StartTime).TotalSeconds);
                if (i + 1 < lyrics.Count) nextLine = lyrics[i + 1];
                break;
            }
            
            // Or if we're in the gap before this line (lead-in)
            if (currentTime < line.StartTime)
            {
                if (i == 0 || currentTime > lyrics[i-1].EndTime)
                {
                    nextLine = line;
                    
                    // If we're close (within 2 seconds), show it as active but with 0 progress
                    if ((line.StartTime - currentTime).TotalSeconds < 2.0)
                    {
                        activeLine = line;
                        progress = 0f;
                    }
                    break;
                }
            }
        }

        if (activeLine == null) return;

        float yPos = _height - 180;
        float centerYPos = yPos; // Adjust based on animation

        // Glassmorphism pill background
        DrawGlassPill(canvas, _width / 2, centerYPos - 15, _width * 0.8f, 100);

        // Draw active line text
        if (activeLine != null)
        {
            using var textPaint = new SKPaint
            {
                IsAntialias = true,
                Typeface = _boldFont,
                TextSize = 56,
                TextAlign = SKTextAlign.Center
            };

            // Base text (unfilled)
            textPaint.Color = SKColors.White.WithAlpha(200);
            canvas.DrawShapedText(activeLine.Text, _width / 2, centerYPos + 10, textPaint);

            // Karaoke filled text (clip to progress)
            if (progress > 0)
            {
                // Measure text width to calculate clip region
                float textWidth = textPaint.MeasureText(activeLine.Text);
                float textLeft = _width / 2 - textWidth / 2;
                float clipRight = textLeft + (textWidth * progress);

                // Create linear gradient for filled text
                using var shader = SKShader.CreateLinearGradient(
                    new SKPoint(textLeft, centerYPos - 40),
                    new SKPoint(textLeft + textWidth, centerYPos + 20),
                    new[] { priColor, secColor },
                    null,
                    SKShaderTileMode.Clamp
                );

                using var fillPaint = textPaint.Clone();
                fillPaint.Shader = shader;
                fillPaint.Color = SKColors.White; // Required when using shader

                // Draw filled text clipped by progress
                canvas.Save();
                canvas.ClipRect(new SKRect(0, 0, clipRight, _height));
                canvas.DrawShapedText(activeLine.Text, _width / 2, centerYPos + 10, fillPaint);
                
                // Add glowing leading edge
                using var edgeGlow = new SKPaint
                {
                    IsAntialias = true,
                    Color = SKColors.White,
                    MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, 8)
                };
                canvas.DrawCircle(clipRight, centerYPos - 10, 15, edgeGlow);
                
                canvas.Restore();
            }
        }

        // Draw next line preview (small, faded)
        if (nextLine != null && activeLine != nextLine)
        {
            using var previewPaint = new SKPaint
            {
                IsAntialias = true,
                Typeface = _regularFont,
                TextSize = 32,
                TextAlign = SKTextAlign.Center,
                Color = SKColors.White.WithAlpha(120)
            };
            canvas.DrawShapedText(nextLine.Text, _width / 2, centerYPos + 60, previewPaint);
        }
    }

    private void DrawGlassPill(SKCanvas canvas, float cx, float cy, float width, float height)
    {
        float x = cx - width / 2;
        float y = cy - height / 2;
        var rect = new SKRect(x, y, x + width, y + height);
        var rrect = new SKRoundRect(rect, height / 2, height / 2);

        // Dark translucent base
        using var basePaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill,
            Color = new SKColor(10, 15, 25, 160)
        };
        canvas.DrawRoundRect(rrect, basePaint);

        // Soft inner border
        using var borderPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 1.5f,
            Color = SKColors.White.WithAlpha(40)
        };
        canvas.DrawRoundRect(rrect, borderPaint);
    }
}
