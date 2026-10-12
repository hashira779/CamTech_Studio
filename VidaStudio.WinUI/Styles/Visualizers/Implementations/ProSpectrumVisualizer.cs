using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Brushes;
using Microsoft.Graphics.Canvas.Effects;
using Microsoft.Graphics.Canvas.Geometry;
using Microsoft.Graphics.Canvas.UI.Xaml;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System;
using System.Collections.Generic;
using System.Numerics;
using VidaStudio.Services.Rendering;
using Windows.UI;

namespace VidaStudio.Styles.Visualizers;

/// <summary>
/// Epic YouTube-style Circular Visualizer with:
/// - Smart Logo System (Trap Nation badge, Spinning Vinyl, Floating Hologram, Cyber HUD)
/// - Auto-Chroma Background Cleaning (No ugly square boxes)
/// - 128-band circular neon spectrum bars
/// - Outward shooting bass-reactive particles
/// - Heavy bloom and cinematic vignette
/// Renders at 60fps via CanvasAnimatedControl using Win2D/DirectX.
/// </summary>
public class ProSpectrumVisualizer : IVisualizerStyle
{
    public string Id => "pro_spectrum";
    public string DisplayName => "Pro Audio Spectrum (GPU Accelerated)";
    public bool UsesGpuPreview => true;

    private const int BANDS = 128;
    private const int PARTICLE_COUNT = 150;

    private float[] _smoothedSpectrum = new float[BANDS];
    private float[] _peaks = new float[BANDS];

    // Animation state
    private float _bassBump = 0f;
    private float _phase = 0f;
    private Color _primaryColor = Color.FromArgb(255, 0, 200, 255);    // Cyan
    private Color _secondaryColor = Color.FromArgb(255, 200, 0, 255);  // Magenta
    private double _wavePhase = 0;
    private double _amplitudeScale = 0.4;
    private string _loadedLogoPath = "";
    private string _loadedBgRemoval = "";
    private CanvasBitmap? _previewLogo = null;

    // Smart Logo System Parameters
    private string _badgeMode = "trap_nation";
    private string _bgRemoval = "auto";
    private bool _logoSpin = true;
    private bool _logoBassPulse = true;
    private float _logoRotation = 0f;
    private float _scanlineY = 0f;
    private double[]? _liveSpectrum = null;
    private float _liveBass = 0f;

    // Particle system
    private struct Particle
    {
        public float X, Y, VX, VY, Life, MaxLife, Size;
        public byte R, G, B;
    }
    private Particle[] _particles = new Particle[PARTICLE_COUNT];
    private Random _rng = new Random();
    private bool _particlesInitialized = false;

    public UIElement CreatePreviewElement()
    {
        var canvas = new CanvasAnimatedControl
        {
            ClearColor = Color.FromArgb(0, 0, 0, 0),
            IsFixedTimeStep = false, // Liquid smooth VSync framerate without frame dropping
            Paused = false,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            VerticalAlignment = VerticalAlignment.Stretch,
        };
        canvas.Draw += Canvas_Draw;
        return canvas;
    }

    public void UpdatePreview(UIElement element, VisualizerPreviewContext context)
    {
        _primaryColor = context.PrimaryColor;
        _secondaryColor = context.SecondaryColor;
        _wavePhase = context.WavePhase;
        _amplitudeScale = context.AmplitudeScale;
        _badgeMode = context.LogoBadgeMode;
        _bgRemoval = context.LogoBgRemoval;
        _logoSpin = context.LogoSpin;
        _logoBassPulse = context.LogoBassPulse;
        _liveSpectrum = context.Spectrum;
        _liveBass = context.Bass;

        if ((context.LogoPath != _loadedLogoPath || context.LogoBgRemoval != _loadedBgRemoval) 
            && element is CanvasAnimatedControl canvas 
            && !string.IsNullOrWhiteSpace(context.LogoPath))
        {
            _ = LoadPreviewLogoAsync(canvas, context.LogoPath, context.LogoBgRemoval);
        }
    }

    private async System.Threading.Tasks.Task LoadPreviewLogoAsync(CanvasAnimatedControl canvas, string path, string removalMode)
    {
        try
        {
            if (!canvas.ReadyToDraw) return; // Wait until device is ready
            _previewLogo = await SmartLogoService.LoadAndProcessLogoAsync(canvas, path, removalMode);
            _loadedLogoPath = path;
            _loadedBgRemoval = removalMode;
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

        _phase += 0.025f;

        float[] rawBars = new float[BANDS];
        bool hasRealAudio = _liveSpectrum != null && _liveSpectrum.Length > 0;

        if (hasRealAudio)
        {
            int inputBands = _liveSpectrum!.Length;
            double minLog = Math.Log10(1);
            double maxLog = Math.Log10(inputBands * 0.85);

            for (int i = 0; i < BANDS / 2; i++)
            {
                double ratio = (double)i / (BANDS / 2);
                int binIndex = (int)Math.Pow(10, minLog + ratio * (maxLog - minLog));
                binIndex = Math.Clamp(binIndex, 0, inputBands - 1);
                float val = (float)_liveSpectrum[binIndex];
                
                // Aesthetic frequency balancing (subtle high-end lift)
                float eqBoost = 1.0f + (float)ratio * 0.6f;
                float barVal = Math.Clamp(val * eqBoost * (float)_amplitudeScale, 0f, 1f);

                rawBars[i] = barVal;
                rawBars[BANDS - 1 - i] = barVal; // Symmetrical mirror
            }
        }
        else
        {
            // Organic, liquid breathing harmonic wave (buttery smooth, zero twitching)
            for (int i = 0; i < BANDS / 2; i++)
            {
                float norm = (float)i / (BANDS / 2);
                float wave1 = MathF.Sin(_phase * 1.4f + norm * 3.5f) * 0.35f + 0.35f;
                float wave2 = MathF.Sin(_phase * 0.8f + norm * 2.0f + 1.5f) * 0.25f + 0.25f;
                float bassWeight = MathF.Max(0.15f, 1.0f - norm * 0.75f);
                float val = (wave1 * bassWeight + wave2) * 0.45f * (float)_amplitudeScale;
                val = Math.Clamp(val, 0f, 1f);

                rawBars[i] = val;
                rawBars[BANDS - 1 - i] = val;
            }
        }

        // 1. Spatial 3-Tap Gaussian Blur across adjacent bars (eliminates jagged comb-tooth steps)
        float[] targetBars = new float[BANDS];
        for (int i = 0; i < BANDS; i++)
        {
            int prev = (i - 1 + BANDS) % BANDS;
            int next = (i + 1) % BANDS;
            targetBars[i] = 0.22f * rawBars[prev] + 0.56f * rawBars[i] + 0.22f * rawBars[next];
        }

        // 2. Organic Ballistics (Snappy responsive attack + silky exponential gravity release)
        for (int i = 0; i < BANDS; i++)
        {
            float target = targetBars[i];
            if (target > _smoothedSpectrum[i])
            {
                _smoothedSpectrum[i] += (target - _smoothedSpectrum[i]) * 0.45f;
            }
            else
            {
                _smoothedSpectrum[i] = MathF.Max(target, _smoothedSpectrum[i] * 0.88f - 0.002f);
            }

            // Peak Hold with smooth gravity
            if (_smoothedSpectrum[i] > _peaks[i])
            {
                _peaks[i] = _smoothedSpectrum[i];
            }
            else
            {
                _peaks[i] = MathF.Max(_smoothedSpectrum[i], _peaks[i] - 0.007f);
            }
        }

        float currentBass = hasRealAudio ? _liveBass : 0f;
        if (!hasRealAudio)
        {
            for (int i = 0; i < 12; i++) currentBass = Math.Max(currentBass, _smoothedSpectrum[i]);
        }
        _bassBump = _bassBump * 0.82f + currentBass * 0.18f;

        if (_logoSpin)
        {
            _logoRotation += 0.015f * (1.0f + _bassBump * 0.8f);
        }

        RenderScene(ds, w, h, _primaryColor, _secondaryColor, _previewLogo, _badgeMode, _logoSpin, _logoBassPulse);
    }

    /// <summary>
    /// Full scene renderer — shared between live preview and video export.
    /// </summary>
    private void RenderScene(
        CanvasDrawingSession ds, 
        float w, 
        float h, 
        Color c1, 
        Color c2, 
        CanvasBitmap? logo,
        string badgeMode,
        bool logoSpin,
        bool logoBassPulse)
    {
        float cx = w / 2f;
        float cy = h * 0.45f; // Center slightly above middle to leave room for lyrics

        // ===== 1. TRAP NATION CIRCULAR BARS =====
        DrawCircularBars(ds, w, h, cx, cy, c1, c2);

        // ===== 2. PARTICLES =====
        UpdateAndDrawParticles(ds, w, h, cx, cy, c1, c2);

        // ===== 3. SMART CENTER LOGO & BADGE SYSTEM =====
        DrawCenterLogo(ds, w, h, cx, cy, c1, c2, logo, badgeMode, logoSpin, logoBassPulse);

        // ===== 4. VIGNETTE & SCAN LINES =====
        DrawScanLines(ds, w, h, cy, c1);
    }

    private void DrawCircularBars(CanvasDrawingSession ds, float w, float h, float cx, float cy, Color c1, Color c2)
    {
        float baseRadius = Math.Min(w, h) * 0.22f;
        float pulse = 1.0f + _bassBump * 0.15f;
        float radius = baseRadius * pulse;
        float maxBarH = h * 0.35f;

        using var roundCapStyle = new CanvasStrokeStyle
        {
            StartCap = CanvasCapStyle.Round,
            EndCap = CanvasCapStyle.Round
        };

        // Cache geometry coordinates and colors for ultra-fast multi-pass drawing
        var startPts = new Vector2[BANDS];
        var endPts = new Vector2[BANDS];
        var peakPts = new Vector2[BANDS];
        var barColors = new Color[BANDS];

        for (int i = 0; i < BANDS; i++)
        {
            float barH = Math.Max(3f, _smoothedSpectrum[i] * maxBarH);
            barH += _bassBump * maxBarH * 0.10f;

            float peakH = Math.Max(barH + 4f, _peaks[i] * maxBarH + 4f);

            float angle = (float)(i * Math.PI * 2 / BANDS - Math.PI / 2);
            float cosA = MathF.Cos(angle);
            float sinA = MathF.Sin(angle);

            startPts[i] = new Vector2(cx + cosA * radius, cy + sinA * radius);
            endPts[i] = new Vector2(cx + cosA * (radius + barH), cy + sinA * (radius + barH));
            peakPts[i] = new Vector2(cx + cosA * (radius + peakH), cy + sinA * (radius + peakH));

            float mix = (i < BANDS / 2 ? i : BANDS - 1 - i) / (float)(BANDS / 2);
            barColors[i] = Color.FromArgb(255,
                (byte)(c1.R * (1 - mix) + c2.R * mix),
                (byte)(c1.G * (1 - mix) + c2.G * mix),
                (byte)(c1.B * (1 - mix) + c2.B * mix));
        }

        // PASS 1: Wide Bloom Aura (Direct GPU Additive Raster, ultra-fast 60FPS)
        ds.Blend = CanvasBlend.Add;
        for (int i = 0; i < BANDS; i++)
        {
            var col = barColors[i];
            var auraCol = Color.FromArgb((byte)(45 + _bassBump * 40), col.R, col.G, col.B);
            ds.DrawLine(startPts[i], endPts[i], auraCol, 10.0f, roundCapStyle);
        }

        // PASS 2: Vivid Mid Glow
        for (int i = 0; i < BANDS; i++)
        {
            var col = barColors[i];
            var midCol = Color.FromArgb(120, col.R, col.G, col.B);
            ds.DrawLine(startPts[i], endPts[i], midCol, 5.5f, roundCapStyle);
        }
        ds.Blend = CanvasBlend.SourceOver;

        // PASS 3: Razor Sharp Core Line with Rounded Endcaps
        for (int i = 0; i < BANDS; i++)
        {
            ds.DrawLine(startPts[i], endPts[i], barColors[i], 3.0f, roundCapStyle);
        }

        // PASS 4: Floating Peak Pearl Caps (Signature Trap Nation floating drops)
        ds.Blend = CanvasBlend.Add;
        for (int i = 0; i < BANDS; i++)
        {
            var col = barColors[i];
            var peakCol = Color.FromArgb((byte)(160 + _bassBump * 80), col.R, col.G, col.B);
            ds.FillCircle(peakPts[i].X, peakPts[i].Y, 2.2f, peakCol);
        }
        ds.Blend = CanvasBlend.SourceOver;
    }

    private void DrawCenterLogo(
        CanvasDrawingSession ds, 
        float w, 
        float h, 
        float cx, 
        float cy, 
        Color c1, 
        Color c2, 
        CanvasBitmap? logo,
        string badgeMode,
        bool logoSpin,
        bool logoBassPulse)
    {
        float baseRadius = Math.Min(w, h) * 0.22f;
        float pulse = 1.0f + (logoBassPulse ? _bassBump * 0.16f : 0f);
        float radius = baseRadius * pulse;

        switch (badgeMode?.ToLowerInvariant())
        {
            case "vinyl":
                DrawVinylDisc(ds, cx, cy, radius, c1, c2, logo, logoSpin, logoBassPulse);
                break;

            case "hologram":
                DrawFloatingHologram(ds, cx, cy, radius, c1, c2, logo, logoSpin, logoBassPulse);
                break;

            case "cyber_hud":
                DrawCyberHudPod(ds, cx, cy, radius, c1, c2, logo, logoSpin, logoBassPulse);
                break;

            case "trap_nation":
            default:
                DrawTrapNationBadge(ds, cx, cy, radius, c1, c2, logo, logoSpin, logoBassPulse);
                break;
        }
    }

    private void DrawTrapNationBadge(CanvasDrawingSession ds, float cx, float cy, float radius, Color c1, Color c2, CanvasBitmap? logo, bool logoSpin, bool logoBassPulse)
    {
        float badgeRadius = radius * 0.94f;

        // 1. Audio-reactive expanding shockwave ring
        if (logoBassPulse && _bassBump > 0.35f)
        {
            float shockRadius = badgeRadius * (1.1f + (_bassBump - 0.35f) * 0.5f);
            byte shockAlpha = (byte)Math.Clamp((int)(140 * (1.0f - (_bassBump - 0.35f) * 1.5f)), 0, 180);
            ds.Blend = CanvasBlend.Add;
            ds.DrawEllipse(cx, cy, shockRadius, shockRadius, Color.FromArgb(shockAlpha, c1.R, c1.G, c1.B), 2.5f);
            ds.Blend = CanvasBlend.SourceOver;
        }

        // 2. Bass-reactive outer glow behind badge
        ds.Blend = CanvasBlend.Add;
        ds.FillEllipse(cx, cy, badgeRadius * 1.08f, badgeRadius * 1.08f, 
            Color.FromArgb((byte)(30 + _bassBump * 80), c1.R, c1.G, c1.B));
        ds.Blend = CanvasBlend.SourceOver;

        // 3. Circular Badge with Layer Clipping
        using (var clipGeo = CanvasGeometry.CreateCircle(ds.Device, cx, cy, badgeRadius))
        using (ds.CreateLayer(1.0f, clipGeo))
        {
            // Deep obsidian / midnight backing disc
            ds.FillEllipse(cx, cy, badgeRadius, badgeRadius, Color.FromArgb(245, 12, 14, 20));

            // Center radial glow
            ds.Blend = CanvasBlend.Add;
            ds.FillEllipse(cx, cy, badgeRadius * 0.7f, badgeRadius * 0.7f, 
                Color.FromArgb((byte)(25 + _bassBump * 50), c2.R, c2.G, c2.B));
            ds.Blend = CanvasBlend.SourceOver;

            if (logo != null)
            {
                float imgW = (float)logo.Size.Width;
                float imgH = (float)logo.Size.Height;
                float targetDiameter = badgeRadius * 1.75f;
                float scale = targetDiameter / Math.Max(imgW, imgH);
                float targetW = imgW * scale;
                float targetH = imgH * scale;

                var prevTransform = ds.Transform;
                if (logoSpin)
                {
                    ds.Transform = Matrix3x2.CreateRotation(_logoRotation * 0.35f, new Vector2(cx, cy)) * prevTransform;
                }

                var destRect = new Windows.Foundation.Rect(cx - targetW / 2, cy - targetH / 2, targetW, targetH);
                ds.DrawImage(logo, destRect);

                if (logoSpin)
                {
                    ds.Transform = prevTransform;
                }
            }
            else
            {
                ds.DrawEllipse(cx, cy, badgeRadius * 0.5f, badgeRadius * 0.5f, c1, 3f);
            }
        }

        // 4. Glowing Neon / Metallic Ring Bezel (Trap Nation style)
        ds.Blend = CanvasBlend.Add;
        ds.DrawEllipse(cx, cy, badgeRadius, badgeRadius, 
            Color.FromArgb((byte)(120 + _bassBump * 100), c1.R, c1.G, c1.B), 5f + _bassBump * 4f);
        ds.Blend = CanvasBlend.SourceOver;

        // Sharp inner metallic rim
        ds.DrawEllipse(cx, cy, badgeRadius, badgeRadius, c1, 3f);
        ds.DrawEllipse(cx, cy, badgeRadius - 3f, badgeRadius - 3f, 
            Color.FromArgb(100, 255, 255, 255), 1.5f);

        // Subtle outer border ring at spectrum base
        ds.DrawEllipse(cx, cy, radius, radius, 
            Color.FromArgb(50, c2.R, c2.G, c2.B), 1.5f);

        // Tech ticks around perimeter
        int tickCount = 24;
        for (int t = 0; t < tickCount; t++)
        {
            float a = (float)(t * Math.PI * 2 / tickCount + (logoSpin ? _logoRotation * 0.25f : 0));
            float rIn = badgeRadius + 2f;
            float rOut = badgeRadius + (t % 6 == 0 ? 8f : 5f);
            ds.DrawLine(
                cx + MathF.Cos(a) * rIn, cy + MathF.Sin(a) * rIn,
                cx + MathF.Cos(a) * rOut, cy + MathF.Sin(a) * rOut,
                Color.FromArgb(140, c1.R, c1.G, c1.B), 1.5f);
        }
    }

    private void DrawVinylDisc(CanvasDrawingSession ds, float cx, float cy, float radius, Color c1, Color c2, CanvasBitmap? logo, bool logoSpin, bool logoBassPulse)
    {
        float vinylRadius = radius * 0.96f;
        float labelRadius = vinylRadius * 0.45f;

        // 1. Black Vinyl Record body
        ds.FillEllipse(cx, cy, vinylRadius, vinylRadius, Color.FromArgb(255, 14, 14, 18));

        // 2. Micro grooves (fine concentric rings)
        for (float gr = labelRadius + 8f; gr < vinylRadius - 4f; gr += 5f)
        {
            byte a = (byte)(15 + (int)(Math.Sin(gr * 0.7f) * 10));
            ds.DrawEllipse(cx, cy, gr, gr, Color.FromArgb(a, 200, 220, 255), 1.0f);
        }

        // 3. Specular vinyl reflection sheen (opposing light fan beams)
        ds.Blend = CanvasBlend.Add;
        for (int s = 0; s < 2; s++)
        {
            float sheenAngle = (float)(_logoRotation + s * Math.PI + Math.PI / 4);
            float xTip = cx + MathF.Cos(sheenAngle) * vinylRadius;
            float yTip = cy + MathF.Sin(sheenAngle) * vinylRadius;
            ds.DrawLine(cx, cy, xTip, yTip, Color.FromArgb((byte)(40 + _bassBump * 40), 255, 255, 255), 8f);
        }
        ds.Blend = CanvasBlend.SourceOver;

        // 4. Center Label with Logo (Rotates continuously like a real vinyl LP)
        using (var clipGeo = CanvasGeometry.CreateCircle(ds.Device, cx, cy, labelRadius))
        using (ds.CreateLayer(1.0f, clipGeo))
        {
            ds.FillEllipse(cx, cy, labelRadius, labelRadius, Color.FromArgb(255, 22, 22, 30));

            if (logo != null)
            {
                float imgW = (float)logo.Size.Width;
                float imgH = (float)logo.Size.Height;
                float targetDiameter = labelRadius * 2.0f;
                float scale = targetDiameter / Math.Min(imgW, imgH);
                float targetW = imgW * scale;
                float targetH = imgH * scale;

                var prevTransform = ds.Transform;
                if (logoSpin)
                {
                    ds.Transform = Matrix3x2.CreateRotation(_logoRotation, new Vector2(cx, cy)) * prevTransform;
                }

                var destRect = new Windows.Foundation.Rect(cx - targetW / 2, cy - targetH / 2, targetW, targetH);
                ds.DrawImage(logo, destRect);

                if (logoSpin)
                {
                    ds.Transform = prevTransform;
                }
            }
        }

        // 5. Center spindle hole & metallic grommet ring
        ds.DrawEllipse(cx, cy, labelRadius, labelRadius, c1, 2.5f);
        float spindleR = 12f;
        ds.FillEllipse(cx, cy, spindleR, spindleR, Color.FromArgb(255, 8, 8, 12));
        ds.DrawEllipse(cx, cy, spindleR, spindleR, Color.FromArgb(220, 210, 215, 225), 2.0f);
    }

    private void DrawFloatingHologram(CanvasDrawingSession ds, float cx, float cy, float radius, Color c1, Color c2, CanvasBitmap? logo, bool logoSpin, bool logoBassPulse)
    {
        float logoDiameter = radius * 1.55f;

        // 1. Intense bass-reactive back-bloom
        ds.Blend = CanvasBlend.Add;
        ds.FillEllipse(cx, cy, radius * 0.9f, radius * 0.9f, 
            Color.FromArgb((byte)(40 + _bassBump * 110), c1.R, c1.G, c1.B));
        ds.FillEllipse(cx, cy, radius * 0.5f, radius * 0.5f, 
            Color.FromArgb((byte)(60 + _bassBump * 120), c2.R, c2.G, c2.B));
        ds.Blend = CanvasBlend.SourceOver;

        if (logo != null)
        {
            float imgW = (float)logo.Size.Width;
            float imgH = (float)logo.Size.Height;
            float scale = logoDiameter / Math.Max(imgW, imgH);
            float targetW = imgW * scale;
            float targetH = imgH * scale;

            var prevTransform = ds.Transform;
            if (logoSpin)
            {
                ds.Transform = Matrix3x2.CreateRotation(_logoRotation * 0.35f, new Vector2(cx, cy)) * prevTransform;
            }

            var destRect = new Windows.Foundation.Rect(cx - targetW / 2, cy - targetH / 2, targetW, targetH);
            
            // Glowing drop-shadow / hologram aura
            ds.Blend = CanvasBlend.Add;
            var glowRect = new Windows.Foundation.Rect(destRect.X - 4, destRect.Y - 4, destRect.Width + 8, destRect.Height + 8);
            ds.DrawImage(logo, glowRect, logo.Bounds, 0.45f);
            ds.Blend = CanvasBlend.SourceOver;

            ds.DrawImage(logo, destRect);

            // 2. Futuristic vertical hologram laser scanline
            _scanlineY = (_scanlineY + 3.5f) % (targetH + 40f);
            float scanCurrentY = (float)destRect.Y - 20f + _scanlineY;
            if (scanCurrentY >= destRect.Y && scanCurrentY <= destRect.Bottom)
            {
                ds.Blend = CanvasBlend.Add;
                ds.DrawLine((float)destRect.X, scanCurrentY, (float)destRect.Right, scanCurrentY, 
                    Color.FromArgb(180, c2.R, c2.G, c2.B), 2.5f);
                ds.Blend = CanvasBlend.SourceOver;
            }

            if (logoSpin)
            {
                ds.Transform = prevTransform;
            }
        }
        else
        {
            ds.DrawEllipse(cx, cy, radius * 0.5f, radius * 0.5f, c1, 2.5f);
        }
    }

    private void DrawCyberHudPod(CanvasDrawingSession ds, float cx, float cy, float radius, Color c1, Color c2, CanvasBitmap? logo, bool logoSpin, bool logoBassPulse)
    {
        float hudRadius = radius * 0.92f;

        // 1. High-Tech Concentric Orbiting Arc Rings
        ds.Blend = CanvasBlend.Add;
        ds.DrawEllipse(cx, cy, hudRadius, hudRadius, Color.FromArgb(60, c1.R, c1.G, c1.B), 1.5f);

        // Segmented arcs clockwise
        for (int a = 0; a < 3; a++)
        {
            float arcStart = _logoRotation * 1.5f + (float)(a * Math.PI * 2 / 3);
            int arcSteps = 16;
            for (int step = 0; step < arcSteps; step++)
            {
                float a1 = arcStart + step * 0.05f;
                float a2 = a1 + 0.05f;
                ds.DrawLine(
                    cx + MathF.Cos(a1) * hudRadius, cy + MathF.Sin(a1) * hudRadius,
                    cx + MathF.Cos(a2) * hudRadius, cy + MathF.Sin(a2) * hudRadius,
                    c1, 3.5f + _bassBump * 2f);
            }
        }

        // Ring 2 counter-clockwise
        float r2 = hudRadius * 0.85f;
        for (int a = 0; a < 4; a++)
        {
            float arcStart = -_logoRotation * 1.2f + (float)(a * Math.PI * 2 / 4);
            int arcSteps = 12;
            for (int step = 0; step < arcSteps; step++)
            {
                float a1 = arcStart + step * 0.04f;
                float a2 = a1 + 0.04f;
                ds.DrawLine(
                    cx + MathF.Cos(a1) * r2, cy + MathF.Sin(a1) * r2,
                    cx + MathF.Cos(a2) * r2, cy + MathF.Sin(a2) * r2,
                    Color.FromArgb(160, c2.R, c2.G, c2.B), 2.0f);
            }
        }
        ds.Blend = CanvasBlend.SourceOver;

        // 2. Cardinal Crosshairs
        for (int i = 0; i < 4; i++)
        {
            float angle = (float)(i * Math.PI / 2);
            float rx1 = cx + MathF.Cos(angle) * (hudRadius - 8f);
            float ry1 = cy + MathF.Sin(angle) * (hudRadius - 8f);
            float rx2 = cx + MathF.Cos(angle) * (hudRadius + 8f);
            float ry2 = cy + MathF.Sin(angle) * (hudRadius + 8f);
            ds.DrawLine(rx1, ry1, rx2, ry2, Color.FromArgb(200, 255, 255, 255), 1.5f);
        }

        // 3. Center Clipped Core with Logo
        float coreRadius = hudRadius * 0.72f;
        using (var clipGeo = CanvasGeometry.CreateCircle(ds.Device, cx, cy, coreRadius))
        using (ds.CreateLayer(1.0f, clipGeo))
        {
            ds.FillEllipse(cx, cy, coreRadius, coreRadius, Color.FromArgb(240, 10, 12, 18));
            
            ds.Blend = CanvasBlend.Add;
            ds.FillEllipse(cx, cy, coreRadius * 0.8f, coreRadius * 0.8f, 
                Color.FromArgb((byte)(40 + _bassBump * 70), c1.R, c1.G, c1.B));
            ds.Blend = CanvasBlend.SourceOver;

            if (logo != null)
            {
                float imgW = (float)logo.Size.Width;
                float imgH = (float)logo.Size.Height;
                float targetDiameter = coreRadius * 1.75f;
                float scale = targetDiameter / Math.Max(imgW, imgH);
                float targetW = imgW * scale;
                float targetH = imgH * scale;

                var prevTransform = ds.Transform;
                if (logoSpin)
                {
                    ds.Transform = Matrix3x2.CreateRotation(_logoRotation * 0.5f, new Vector2(cx, cy)) * prevTransform;
                }

                var destRect = new Windows.Foundation.Rect(cx - targetW / 2, cy - targetH / 2, targetW, targetH);
                ds.DrawImage(logo, destRect);

                if (logoSpin)
                {
                    ds.Transform = prevTransform;
                }
            }
        }
        ds.DrawEllipse(cx, cy, coreRadius, coreRadius, c2, 2.5f);
    }

    private void UpdateAndDrawParticles(CanvasDrawingSession ds, float w, float h, float cx, float cy, Color c1, Color c2)
    {
        if (!_particlesInitialized)
        {
            for (int i = 0; i < PARTICLE_COUNT; i++)
                RespawnParticle(ref _particles[i], cx, cy, w, h, true);
            _particlesInitialized = true;
        }

        float spawnChance = _bassBump * 0.9f;
        float baseRadius = Math.Min(w, h) * 0.22f;

        ds.Blend = CanvasBlend.Add;
        for (int i = 0; i < PARTICLE_COUNT; i++)
        {
            ref var p = ref _particles[i];
            p.Life -= 0.012f;

            if (p.Life <= 0)
            {
                if (_rng.NextSingle() < spawnChance)
                    RespawnParticle(ref p, cx, cy, w, h, false);
                else
                    continue;
            }

            // Move outwards from center radially
            p.X += p.VX * (1.0f + _bassBump * 4.0f);
            p.Y += p.VY * (1.0f + _bassBump * 4.0f);

            float lifeRatio = p.Life / p.MaxLife;
            byte alpha = (byte)(lifeRatio * 255);
            float size = p.Size * (0.5f + lifeRatio * 0.5f);

            ds.FillEllipse(p.X, p.Y, size, size, Color.FromArgb(alpha, p.R, p.G, p.B));
        }
        ds.Blend = CanvasBlend.SourceOver;
    }

    private void RespawnParticle(ref Particle p, float cx, float cy, float w, float h, bool randomPos)
    {
        float baseRadius = Math.Min(w, h) * 0.22f;
        float angle = (float)(_rng.NextDouble() * Math.PI * 2);
        
        float startRadius = baseRadius * (1.0f + _bassBump * 0.15f);
        
        if (randomPos)
        {
            startRadius += (float)_rng.NextDouble() * 300f; // Initial scatter
        }

        p.X = cx + MathF.Cos(angle) * startRadius;
        p.Y = cy + MathF.Sin(angle) * startRadius;

        float speed = 1.5f + (float)_rng.NextDouble() * 4.0f;
        p.VX = MathF.Cos(angle) * speed;
        p.VY = MathF.Sin(angle) * speed;
        
        p.Life = 0.5f + (float)_rng.NextDouble() * 1.5f;
        p.MaxLife = p.Life;
        p.Size = 2.0f + (float)_rng.NextDouble() * 4.0f;

        float mix = (float)_rng.NextDouble();
        p.R = (byte)(_primaryColor.R * (1 - mix) + _secondaryColor.R * mix);
        p.G = (byte)(_primaryColor.G * (1 - mix) + _secondaryColor.G * mix);
        p.B = (byte)(_primaryColor.B * (1 - mix) + _secondaryColor.B * mix);
    }

    private void DrawScanLines(CanvasDrawingSession ds, float w, float h, float cy, Color c1)
    {
        // Draw heavy vignette (dark edges) for cinematic depth
        using var vignette = new CanvasRadialGradientBrush(ds.Device, Color.FromArgb(0,0,0,0), Color.FromArgb(200,0,0,0))
        {
            Center = new Vector2(w/2, h/2),
            RadiusX = w * 0.7f,
            RadiusY = h * 0.7f
        };
        ds.FillRectangle(0, 0, w, h, vignette);

        // Scan lines
        ds.Blend = CanvasBlend.Add;
        for (float y = 0; y < h; y += 4f)
        {
            byte a = (byte)(6 + (int)(Math.Sin(y * 0.1 + _phase * 2) * 3));
            ds.DrawLine(0, y, w, y, Color.FromArgb(a, c1.R, c1.G, c1.B), 0.5f);
        }
        ds.Blend = CanvasBlend.SourceOver;
    }

    // ===== VIDEO EXPORT PATH =====
    public void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context)
    {
        float w = context.Width;
        float h = context.Height;
        _phase += 0.02f;

        float[] rawBars = new float[BANDS];
        int inputBands = context.Spectrum.Length;

        if (inputBands > 0)
        {
            double minLog = Math.Log10(1);
            double maxLog = Math.Log10(inputBands * 0.85);

            for (int i = 0; i < BANDS / 2; i++)
            {
                double ratio = (double)i / (BANDS / 2);
                int binIndex = (int)Math.Pow(10, minLog + ratio * (maxLog - minLog));
                binIndex = Math.Clamp(binIndex, 0, inputBands - 1);
                float val = context.Spectrum[binIndex];
                
                float eqBoost = 1.0f + (float)ratio * 0.6f;
                float barVal = Math.Clamp(val * eqBoost * (float)context.AmplitudeScale, 0f, 1f);

                rawBars[i] = barVal;
                rawBars[BANDS - 1 - i] = barVal;
            }
        }
        else
        {
            for (int i = 0; i < BANDS; i++)
            {
                rawBars[i] = context.Bass * (1.0f - MathF.Abs(i - BANDS / 2f) / (BANDS / 2f));
            }
        }

        // 1. Spatial 3-Tap Gaussian Blur across adjacent bars
        float[] targetBars = new float[BANDS];
        for (int i = 0; i < BANDS; i++)
        {
            int prev = (i - 1 + BANDS) % BANDS;
            int next = (i + 1) % BANDS;
            targetBars[i] = 0.22f * rawBars[prev] + 0.56f * rawBars[i] + 0.22f * rawBars[next];
        }

        // 2. Organic Ballistics (Snappy responsive attack + silky exponential gravity release)
        for (int i = 0; i < BANDS; i++)
        {
            float target = targetBars[i];
            if (target > _smoothedSpectrum[i])
            {
                _smoothedSpectrum[i] += (target - _smoothedSpectrum[i]) * 0.45f;
            }
            else
            {
                _smoothedSpectrum[i] = MathF.Max(target, _smoothedSpectrum[i] * 0.88f - 0.002f);
            }

            if (_smoothedSpectrum[i] > _peaks[i])
            {
                _peaks[i] = _smoothedSpectrum[i];
            }
            else
            {
                _peaks[i] = MathF.Max(_smoothedSpectrum[i], _peaks[i] - 0.007f);
            }
        }

        float currentBass = context.Bass;
        _bassBump = _bassBump * 0.80f + currentBass * 0.20f;

        if (context.LogoSpin)
        {
            _logoRotation += 0.015f * (1.0f + _bassBump * 0.8f);
        }

        RenderScene(ds, w, h, context.PrimaryColor, context.SecondaryColor, context.LogoBitmap,
            context.LogoBadgeMode, context.LogoSpin, context.LogoBassPulse);
    }
}

