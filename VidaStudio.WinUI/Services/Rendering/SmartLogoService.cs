using Microsoft.Graphics.Canvas;
using System;
using System.IO;
using System.Threading.Tasks;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// Smart Logo & Center Badge Service.
/// Automatically detects solid backgrounds (white/black box) and provides
/// smart AI-style auto-segmentation so user logos never render as ugly square lumps.
/// </summary>
public static class SmartLogoService
{
    public static async Task<CanvasBitmap?> LoadAndProcessLogoAsync(
        ICanvasResourceCreator device, 
        string path, 
        string removalMode)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            return null;

        try
        {
            using var rawBmp = await CanvasBitmap.LoadAsync(device, path);
            int w = (int)rawBmp.SizeInPixels.Width;
            int h = (int)rawBmp.SizeInPixels.Height;

            if (removalMode == "original" || w <= 0 || h <= 0)
            {
                // Return fresh copy
                return await CanvasBitmap.LoadAsync(device, path);
            }

            byte[] pixels = rawBmp.GetPixelBytes();

            // Detect corners in BGRA format
            bool isWhiteBg = false;
            bool isBlackBg = false;

            if (removalMode == "key_white") isWhiteBg = true;
            else if (removalMode == "key_black") isBlackBg = true;
            else if (removalMode == "auto")
            {
                // Inspect corners to decide
                int[] cornerIndices = new int[]
                {
                    0,
                    Math.Max(0, (w - 1) * 4),
                    Math.Max(0, (h - 1) * w * 4),
                    Math.Max(0, ((h - 1) * w + (w - 1)) * 4)
                };

                float avgCornerLum = 0;
                int validCorners = 0;
                for (int i = 0; i < cornerIndices.Length; i++)
                {
                    int idx = cornerIndices[i];
                    if (idx + 3 < pixels.Length)
                    {
                        byte b = pixels[idx];
                        byte g = pixels[idx + 1];
                        byte r = pixels[idx + 2];
                        byte a = pixels[idx + 3];
                        if (a > 128) // solid corner
                        {
                            avgCornerLum += 0.299f * r + 0.587f * g + 0.114f * b;
                            validCorners++;
                        }
                    }
                }

                if (validCorners >= 3)
                {
                    avgCornerLum /= validCorners;
                    if (avgCornerLum > 220) isWhiteBg = true;
                    else if (avgCornerLum < 35) isBlackBg = true;
                }
            }

            if (!isWhiteBg && !isBlackBg)
            {
                // Likely a full album cover photo or transparent PNG, keep as is
                return await CanvasBitmap.LoadAsync(device, path);
            }

            // Apply Smart Chroma Cleaning in memory
            for (int i = 0; i < pixels.Length; i += 4)
            {
                byte b = pixels[i];
                byte g = pixels[i + 1];
                byte r = pixels[i + 2];
                byte a = pixels[i + 3];

                if (a == 0) continue;

                if (isWhiteBg)
                {
                    float dist = MathF.Sqrt((255 - r) * (255 - r) + (255 - g) * (255 - g) + (255 - b) * (255 - b));
                    if (dist < 30f)
                    {
                        pixels[i + 3] = 0; // Pure transparent
                    }
                    else if (dist < 60f)
                    {
                        pixels[i + 3] = (byte)((dist - 30f) / 30f * a);
                    }
                    else
                    {
                        // Invert dark text/lines (< 70 lum) to bright silver-white so it stands out on dark visualizers
                        float lum = 0.299f * r + 0.587f * g + 0.114f * b;
                        float sat = MathF.Max(r, MathF.Max(g, b)) - MathF.Min(r, MathF.Min(g, b));
                        if (lum < 75f && sat < 45f)
                        {
                            pixels[i] = 252;     // B
                            pixels[i + 1] = 248; // G
                            pixels[i + 2] = 245; // R
                        }
                    }
                }
                else if (isBlackBg)
                {
                    float lum = 0.299f * r + 0.587f * g + 0.114f * b;
                    if (lum < 25f)
                    {
                        pixels[i + 3] = 0;
                    }
                    else if (lum < 55f)
                    {
                        pixels[i + 3] = (byte)((lum - 25f) / 30f * a);
                    }
                }
            }

            // Create processed render target with the cleaned pixels
            var processedBmp = new CanvasRenderTarget(device, w, h, rawBmp.Dpi);
            processedBmp.SetPixelBytes(pixels);
            return processedBmp;
        }
        catch
        {
            return null;
        }
    }
}
