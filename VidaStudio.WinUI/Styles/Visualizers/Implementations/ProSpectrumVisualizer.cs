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
using Windows.UI;

namespace VidaStudio.Styles.Visualizers;

/// <summary>
/// Ultra-modern GPU-accelerated spectrum visualizer with:
/// - Glowing circular ring (bass-reactive pulsing)
/// - 128-band neon spectrum bars with gradient
/// - Floating particles that scatter on beats
/// - Multi-pass bloom/glow (outer + inner)
/// - Mirror reflection floor
/// - Peak indicators
/// - Horizontal scan lines for depth
/// Renders at 60fps via CanvasAnimatedControl using Win2D/DirectX.
/// </summary>
public class ProSpectrumVisualizer : IVisualizerStyle
{
    public string Id => "pro_spectrum";
    public string DisplayName => "Pro Audio Spectrum (GPU Accelerated)";
    public bool UsesGpuPreview => true;

    private const int BANDS = 128;
    private const int PARTICLE_COUNT = 60;

    private float[] _smoothedSpectrum = new float[BANDS];
    private float[] _peaks = new float[BANDS];

    // Animation state
    private float _bassBump = 0f;
    private float _phase = 0f;
    private float _ringPulse = 0f;
    private Color _primaryColor = Color.FromArgb(255, 0, 200, 255);    // Cyan
    private Color _secondaryColor = Color.FromArgb(255, 200, 0, 255);  // Magenta
    private double _wavePhase = 0;
    private double _amplitudeScale = 0.4;

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
            IsFixedTimeStep = true,
            TargetElapsedTime = TimeSpan.FromMilliseconds(16), // 60 FPS
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
    }

    private void Canvas_Draw(ICanvasAnimatedControl sender, CanvasAnimatedDrawEventArgs args)
    {
        var ds = args.DrawingSession;
        float w = (float)sender.Size.Width;
        float h = (float)sender.Size.Height;
        if (w < 10 || h < 10) return;

        _phase += 0.025f;

        // Simulate spectrum
        for (int i = 0; i < BANDS; i++)
        {
            float f1 = (float)Math.Sin(_phase * 1.3 + i * 0.09) * 0.5f + 0.5f;
            float f2 = (float)Math.Sin(_phase * 0.6 + i * 0.17 + 1.8) * 0.35f + 0.35f;
            float f3 = (float)Math.Sin(_phase * 2.5 + i * 0.04 + 3.2) * 0.2f + 0.2f;
            float bassW = Math.Max(0, 1.0f - i / (float)BANDS * 1.6f);
            float val = (f1 * bassW + f2 * 0.7f + f3 * 0.4f) * (float)_amplitudeScale;
            val = Math.Clamp(val, 0f, 1f);

            if (val > _smoothedSpectrum[i])
                _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.25f + val * 0.75f;
            else
                _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.93f + val * 0.07f;

            if (_smoothedSpectrum[i] > _peaks[i]) _peaks[i] = _smoothedSpectrum[i];
            else _peaks[i] = Math.Max(0, _peaks[i] - 0.005f);
        }

        float currentBass = 0;
        for (int i = 0; i < 12; i++) currentBass = Math.Max(currentBass, _smoothedSpectrum[i]);
        _bassBump = _bassBump * 0.82f + currentBass * 0.18f;

        RenderScene(ds, w, h, _primaryColor, _secondaryColor);
    }

    /// <summary>
    /// Full scene renderer — shared between live preview and video export.
    /// </summary>
    private void RenderScene(CanvasDrawingSession ds, float w, float h, Color c1, Color c2)
    {
        float cx = w / 2f;
        float baseY = h * 0.72f;

        // ===== 1. GLOWING RING =====
        DrawGlowingRing(ds, w, h, cx, baseY, c1, c2);

        // ===== 2. SPECTRUM BARS =====
        DrawSpectrumBars(ds, w, h, cx, baseY, c1, c2);

        // ===== 3. PARTICLES =====
        UpdateAndDrawParticles(ds, w, h, cx, baseY, c1, c2);

        // ===== 4. HORIZONTAL SCAN LINES (depth effect) =====
        DrawScanLines(ds, w, h, baseY, c1);
    }

    private void DrawGlowingRing(CanvasDrawingSession ds, float w, float h, float cx, float baseY, Color c1, Color c2)
    {
        float ringCenterY = baseY - h * 0.32f;
        float baseRadius = Math.Min(w, h) * 0.18f;
        float pulse = 1.0f + _bassBump * 0.15f; // bass makes ring pulse
        float radius = baseRadius * pulse;
        _ringPulse = _bassBump;

        // Draw the ring into a command list so we can blur it for glow
        using var ringCL = new CanvasCommandList(ds.Device);
        using (var rds = ringCL.CreateDrawingSession())
        {
            // Outer ring arc (partial, rotating)
            float arcStart = _phase * 40f;
            float arcSweep = 300f + _bassBump * 60f;

            // Ring stroke with gradient
            using var ringBrush = new CanvasLinearGradientBrush(ds.Device, c1, c2)
            {
                StartPoint = new Vector2(cx - radius, ringCenterY),
                EndPoint = new Vector2(cx + radius, ringCenterY)
            };

            // Main ring
            using var ringGeo = CreateArcGeometry(rds.Device, cx, ringCenterY, radius, arcStart, arcSweep);
            rds.DrawGeometry(ringGeo, ringBrush, 3.0f + _bassBump * 2f);

            // Inner ring (smaller, opposite rotation)
            float innerRadius = radius * 0.75f;
            using var innerGeo = CreateArcGeometry(rds.Device, cx, ringCenterY, innerRadius, -arcStart * 0.7f, arcSweep * 0.8f);
            rds.DrawGeometry(innerGeo, Color.FromArgb((byte)(140 + (int)(_bassBump * 80)), c2.R, c2.G, c2.B), 1.5f);

            // Tick marks around ring (like a gauge)
            int tickCount = 48;
            for (int t = 0; t < tickCount; t++)
            {
                float tickAngle = (float)(t * 360.0 / tickCount + _phase * 20);
                float rad = tickAngle * MathF.PI / 180f;
                float tickLen = 4f + (_smoothedSpectrum[t % BANDS] * 18f);
                float x1 = cx + MathF.Cos(rad) * (radius + 4);
                float y1 = ringCenterY + MathF.Sin(rad) * (radius + 4);
                float x2 = cx + MathF.Cos(rad) * (radius + 4 + tickLen);
                float y2 = ringCenterY + MathF.Sin(rad) * (radius + 4 + tickLen);

                byte alpha = (byte)(80 + (int)(_smoothedSpectrum[t % BANDS] * 175));
                rds.DrawLine(x1, y1, x2, y2, Color.FromArgb(alpha, c1.R, c1.G, c1.B), 1.5f);
            }
        }

        // Draw solid ring
        ds.DrawImage(ringCL);

        // Glow pass — heavy bloom on the ring
        using var ringGlow = new GaussianBlurEffect { BlurAmount = 12f + _bassBump * 10f, Source = ringCL };
        ds.Blend = CanvasBlend.Add;
        ds.DrawImage(ringGlow, 0, 0, new Windows.Foundation.Rect(0, 0, w, h), 0.6f + _bassBump * 0.3f);

        // Tight inner glow
        using var ringGlow2 = new GaussianBlurEffect { BlurAmount = 3f, Source = ringCL };
        ds.DrawImage(ringGlow2, 0, 0, new Windows.Foundation.Rect(0, 0, w, h), 0.4f);
        ds.Blend = CanvasBlend.SourceOver;
    }

    private void DrawSpectrumBars(CanvasDrawingSession ds, float w, float h, float cx, float baseY, Color c1, Color c2)
    {
        using var barBuilder = new CanvasPathBuilder(ds.Device);
        using var mirrorBuilder = new CanvasPathBuilder(ds.Device);

        float spacing = Math.Max(2f, w / (BANDS + 16));
        float barW = Math.Max(1.5f, spacing * 0.55f);
        float totalW = BANDS * spacing;
        float startX = (w - totalW) / 2f;
        float maxH = h * 0.35f + _bassBump * h * 0.08f;

        for (int i = 0; i < BANDS; i++)
        {
            float barH = Math.Max(1.5f, _smoothedSpectrum[i] * maxH);
            float x = startX + i * spacing;
            float r = barW / 2f;

            barBuilder.AddGeometry(CanvasGeometry.CreateRoundedRectangle(ds.Device, x, baseY - barH, barW, barH, r, r));

            // Mirror
            float mH = barH * 0.2f;
            mirrorBuilder.AddGeometry(CanvasGeometry.CreateRoundedRectangle(ds.Device, x, baseY + 2, barW, mH, r, r));

            // Peak dot
            if (_peaks[i] > 0.04f)
            {
                float py = baseY - Math.Max(1.5f, _peaks[i] * maxH) - barW * 2.5f;
                ds.FillEllipse(x + barW / 2, py, barW * 0.8f, barW * 0.8f, c2);
            }
        }

        using var barGeo = CanvasGeometry.CreatePath(barBuilder);
        using var mirrorGeo = CanvasGeometry.CreatePath(mirrorBuilder);

        // Bar gradient
        using var barGrad = new CanvasLinearGradientBrush(ds.Device, c1, c2)
        {
            StartPoint = new Vector2(0, baseY - maxH),
            EndPoint = new Vector2(0, baseY)
        };

        // Mirror gradient (fade out)
        using var mirGrad = new CanvasLinearGradientBrush(ds.Device,
            Color.FromArgb(60, c1.R, c1.G, c1.B),
            Color.FromArgb(0, c1.R, c1.G, c1.B))
        {
            StartPoint = new Vector2(0, baseY),
            EndPoint = new Vector2(0, baseY + maxH * 0.2f)
        };

        ds.FillGeometry(mirrorGeo, mirGrad);
        ds.FillGeometry(barGeo, barGrad);

        // Bar bloom
        using var barCL = new CanvasCommandList(ds.Device);
        using (var bds = barCL.CreateDrawingSession())
        {
            bds.FillGeometry(barGeo, barGrad);
        }

        ds.Blend = CanvasBlend.Add;
        using var barBloom = new GaussianBlurEffect { BlurAmount = 10f + _bassBump * 6f, Source = barCL };
        ds.DrawImage(barBloom, 0, 0, new Windows.Foundation.Rect(0, 0, w, h), 0.55f);
        using var barBloom2 = new GaussianBlurEffect { BlurAmount = 2.5f, Source = barCL };
        ds.DrawImage(barBloom2, 0, 0, new Windows.Foundation.Rect(0, 0, w, h), 0.4f);
        ds.Blend = CanvasBlend.SourceOver;

        // Baseline glow line
        ds.Blend = CanvasBlend.Add;
        byte lineAlpha = (byte)Math.Clamp(40 + (int)(_bassBump * 100), 0, 200);
        ds.DrawLine(startX, baseY, startX + totalW, baseY, Color.FromArgb(lineAlpha, c1.R, c1.G, c1.B), 1.2f);
        ds.Blend = CanvasBlend.SourceOver;
    }

    private void UpdateAndDrawParticles(CanvasDrawingSession ds, float w, float h, float cx, float baseY, Color c1, Color c2)
    {
        if (!_particlesInitialized)
        {
            for (int i = 0; i < PARTICLE_COUNT; i++)
                RespawnParticle(ref _particles[i], cx, baseY, w, h);
            _particlesInitialized = true;
        }

        // Spawn new particles on bass hits
        float spawnChance = _bassBump * 0.6f;

        ds.Blend = CanvasBlend.Add;
        for (int i = 0; i < PARTICLE_COUNT; i++)
        {
            ref var p = ref _particles[i];
            p.Life -= 0.012f;

            if (p.Life <= 0)
            {
                if (_rng.NextSingle() < spawnChance)
                    RespawnParticle(ref p, cx, baseY, w, h);
                else
                    continue;
            }

            // Physics
            p.X += p.VX;
            p.Y += p.VY;
            p.VY -= 0.03f; // slight upward drift
            p.VX *= 0.995f;
            p.VY *= 0.995f;

            float lifeRatio = p.Life / p.MaxLife;
            byte alpha = (byte)(lifeRatio * 200);
            float size = p.Size * (0.5f + lifeRatio * 0.5f);

            ds.FillEllipse(p.X, p.Y, size, size, Color.FromArgb(alpha, p.R, p.G, p.B));
        }
        ds.Blend = CanvasBlend.SourceOver;
    }

    private void RespawnParticle(ref Particle p, float cx, float baseY, float w, float h)
    {
        float ringCenterY = baseY - h * 0.32f;
        float radius = Math.Min(w, h) * 0.18f;

        // Spawn around the ring or from the bar tips
        float angle = (float)(_rng.NextDouble() * Math.PI * 2);
        bool fromRing = _rng.NextSingle() > 0.4f;

        if (fromRing)
        {
            p.X = cx + MathF.Cos(angle) * (radius + _rng.NextSingle() * 20);
            p.Y = ringCenterY + MathF.Sin(angle) * (radius + _rng.NextSingle() * 20);
        }
        else
        {
            int band = _rng.Next(BANDS);
            float spacing = Math.Max(2f, w / (BANDS + 16));
            float totalW = BANDS * spacing;
            float startX = (w - totalW) / 2f;
            p.X = startX + band * spacing;
            p.Y = baseY - _smoothedSpectrum[band] * h * 0.35f;
        }

        float speed = 0.5f + _bassBump * 2.5f;
        p.VX = (float)(_rng.NextDouble() - 0.5) * speed * 2;
        p.VY = (float)(_rng.NextDouble() - 0.8) * speed * 1.5f;
        p.Life = 0.5f + (float)_rng.NextDouble() * 0.5f;
        p.MaxLife = p.Life;
        p.Size = 1.0f + (float)_rng.NextDouble() * 2.5f;

        // Color variety — mix between primary and secondary
        float mix = (float)_rng.NextDouble();
        p.R = (byte)(_primaryColor.R * (1 - mix) + _secondaryColor.R * mix);
        p.G = (byte)(_primaryColor.G * (1 - mix) + _secondaryColor.G * mix);
        p.B = (byte)(_primaryColor.B * (1 - mix) + _secondaryColor.B * mix);
    }

    private void DrawScanLines(CanvasDrawingSession ds, float w, float h, float baseY, Color c1)
    {
        // Subtle horizontal scan lines for a futuristic feel
        ds.Blend = CanvasBlend.Add;
        for (float y = 0; y < h; y += 4f)
        {
            byte a = (byte)(6 + (int)(Math.Sin(y * 0.1 + _phase * 2) * 3));
            ds.DrawLine(0, y, w, y, Color.FromArgb(a, c1.R, c1.G, c1.B), 0.5f);
        }
        ds.Blend = CanvasBlend.SourceOver;
    }

    private static CanvasGeometry CreateArcGeometry(ICanvasResourceCreator device, float cx, float cy, float radius, float startDeg, float sweepDeg)
    {
        var builder = new CanvasPathBuilder(device);
        float startRad = startDeg * MathF.PI / 180f;
        float sweepRad = sweepDeg * MathF.PI / 180f;
        int segments = Math.Max(16, (int)(Math.Abs(sweepDeg) / 3));
        float step = sweepRad / segments;

        float x0 = cx + MathF.Cos(startRad) * radius;
        float y0 = cy + MathF.Sin(startRad) * radius;
        builder.BeginFigure(x0, y0);

        for (int i = 1; i <= segments; i++)
        {
            float a = startRad + step * i;
            builder.AddLine(cx + MathF.Cos(a) * radius, cy + MathF.Sin(a) * radius);
        }

        builder.EndFigure(CanvasFigureLoop.Open);
        return CanvasGeometry.CreatePath(builder);
    }

    // ===== VIDEO EXPORT PATH =====
    public void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context)
    {
        float w = context.Width;
        float h = context.Height;
        _phase += 0.02f;

        int inputBands = context.Spectrum.Length;
        for (int i = 0; i < BANDS; i++)
        {
            float val = 0;
            if (inputBands > 0)
            {
                double minLog = Math.Log10(1);
                double maxLog = Math.Log10(inputBands * 0.8);
                double ratio = (double)i / BANDS;
                int binIndex = (int)Math.Pow(10, minLog + ratio * (maxLog - minLog));
                if (binIndex >= 0 && binIndex < inputBands)
                    val = context.Spectrum[binIndex] * 2.0f;
            }
            else
            {
                val = context.Bass * (1.0f - i / (float)BANDS);
            }
            val = Math.Min(1.0f, val);

            if (val > _smoothedSpectrum[i])
                _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.2f + val * 0.8f;
            else
                _smoothedSpectrum[i] = _smoothedSpectrum[i] * 0.90f + val * 0.10f;

            if (_smoothedSpectrum[i] > _peaks[i]) _peaks[i] = _smoothedSpectrum[i];
            else _peaks[i] = Math.Max(0, _peaks[i] - 0.008f);
        }

        float currentBass = 0;
        for (int i = 0; i < 12; i++) currentBass = Math.Max(currentBass, _smoothedSpectrum[i]);
        _bassBump = _bassBump * 0.8f + currentBass * 0.2f;

        RenderScene(ds, w, h, context.PrimaryColor, context.SecondaryColor);
    }
}
