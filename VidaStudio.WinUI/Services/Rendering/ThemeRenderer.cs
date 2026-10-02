using SkiaSharp;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// All 11 visualizer themes rendered via SkiaSharp GPU canvas.
/// Port of Python renderer.py + theme_renderers.py.
/// Each theme method takes the canvas, spectrum data, and palette and draws the visualizer.
/// </summary>
public sealed class ThemeRenderer
{
    private readonly int _width, _height;
    private readonly int _cx, _cy;
    private readonly float[] _peakCaps;
    private readonly Random _rng = new(42);

    // Quantum vortex state
    private float _vortexAngle;
    private readonly (float radius, float angle, float speed, float size)[] _vortexParticles;

    // Neural synapse state
    private readonly (float x, float y, float vx, float vy, float baseR, int bin)[] _neuralNodes;

    // Mandala state
    private float _mandalaRotation;

    // Helix state
    private float _helixTime;

    // Radar angle for hologram
    private float _radarAngle;

    // Aurora ribbons
    private readonly (float phase, float speed, float amplitude, float yOffset)[] _auroraRibbons;

    // Nebula state
    private float _nebulaTime;
    private float _nebulaPrevBass;

    // Liquid state
    private float _liquidPhase;

    public ThemeRenderer(int width, int height, int numBars = 64)
    {
        _width = width;
        _height = height;
        _cx = width / 2;
        _cy = height / 2;
        _peakCaps = new float[numBars * 2]; // mirrored

        // Initialize vortex particles
        _vortexParticles = new (float, float, float, float)[140];
        for (int i = 0; i < 140; i++)
            _vortexParticles[i] = (
                (float)(_rng.NextDouble() * 650 + 60),
                (float)(_rng.NextDouble() * Math.PI * 2),
                (float)(_rng.NextDouble() * 0.02 + 0.008),
                (float)(_rng.NextDouble() * 3.5 + 1.2)
            );

        // Initialize neural nodes
        _neuralNodes = new (float, float, float, float, float, int)[48];
        for (int i = 0; i < 48; i++)
            _neuralNodes[i] = (
                (float)(_rng.NextDouble() * width),
                (float)(_rng.NextDouble() * height),
                (float)((_rng.NextDouble() - 0.5) * 1.2),
                (float)((_rng.NextDouble() - 0.5) * 1.2),
                (float)(_rng.NextDouble() * 4 + 2),
                _rng.Next(0, 64)
            );

        // Initialize aurora ribbons
        _auroraRibbons = new (float, float, float, float)[7];
        for (int i = 0; i < 7; i++)
            _auroraRibbons[i] = (
                (float)(_rng.NextDouble() * Math.PI * 2),
                (float)(0.003 + _rng.NextDouble() * 0.005),
                (float)(0.15 + _rng.NextDouble() * 0.25),
                0.2f + (float)i / 7f * 0.55f
            );
    }

    /// <summary>Dispatches to the appropriate theme renderer.</summary>
    public void Render(SKCanvas canvas, string theme, float[] spectrum, float bass, float onset,
                       float animTime, ColorPalettes.Palette palette)
    {
        switch (theme)
        {
            case "trap_circle":
                RenderTrapCircle(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "neon_bars":
            case "spectrum":
                RenderNeonBars(canvas, spectrum, bass, onset, palette);
                break;
            case "ocean_wave":
            case "horizon_wave":
                RenderOceanWave(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "quantum_vortex":
                RenderQuantumVortex(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "neural_synapse":
                RenderNeuralSynapse(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "hyper_liquid":
                RenderHyperLiquid(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "angkor_mandala":
                RenderAngkorMandala(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "hologram_hud":
                RenderHologramHud(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "aurora_borealis":
                RenderAuroraBorealis(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "dna_helix":
                RenderDnaHelix(canvas, spectrum, bass, onset, animTime, palette);
                break;
            case "sonic_nebula":
                RenderSonicNebula(canvas, spectrum, bass, onset, animTime, palette);
                break;
            default:
                RenderTrapCircle(canvas, spectrum, bass, onset, animTime, palette);
                break;
        }
    }

    #region Trap Circle

    private void RenderTrapCircle(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                   float animTime, ColorPalettes.Palette palette)
    {
        float baseR = Math.Min(_width, _height) * 0.18f;
        float maxBar = Math.Min(_width, _height) * 0.28f;

        // Mirror spectrum: first half + reversed second half
        int halfLen = spectrum.Length;
        float[] mirrored = new float[halfLen * 2];
        for (int i = 0; i < halfLen; i++)
        {
            mirrored[i] = spectrum[i];
            mirrored[halfLen * 2 - 1 - i] = spectrum[i];
        }

        int numBars = mirrored.Length;
        float angleStep = 2f * MathF.PI / numBars;

        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        using var barPaint = new SKPaint { IsAntialias = true, StrokeWidth = 3, Style = SKPaintStyle.Stroke };

        // Collect outer tips for spline
        SKPoint[] outerTips = new SKPoint[numBars];

        for (int i = 0; i < numBars; i++)
        {
            float angle = angleStep * i - MathF.PI / 2;
            float val = mirrored[i];
            float rInner = baseR + 5;
            float rOuter = baseR + 5 + val * maxBar;

            float cos = MathF.Cos(angle);
            float sin = MathF.Sin(angle);

            float x1 = _cx + rInner * cos;
            float y1 = _cy + rInner * sin;
            float x2 = _cx + rOuter * cos;
            float y2 = _cy + rOuter * sin;

            // Gradient color per bar
            float t = (float)i / numBars;
            barPaint.Color = LerpColor(priColor, secColor, t);

            canvas.DrawLine(x1, y1, x2, y2, barPaint);
            outerTips[i] = new SKPoint(x2, y2);

            // Peak caps
            if (rOuter > _peakCaps[i])
                _peakCaps[i] = rOuter;
            else
                _peakCaps[i] = Math.Max(baseR + 5, _peakCaps[i] - 0.015f * maxBar);

            float peakR = _peakCaps[i];
            float px = _cx + peakR * cos;
            float py = _cy + peakR * sin;
            barPaint.StrokeWidth = 2;
            barPaint.Color = priColor.WithAlpha(180);
            canvas.DrawPoint(px, py, barPaint);
            barPaint.StrokeWidth = 3;
        }

        // Outer aura spline
        if (outerTips.Length > 4)
        {
            using var path = new SKPath();
            path.MoveTo(outerTips[0]);
            for (int i = 1; i < outerTips.Length; i++)
                path.LineTo(outerTips[i]);
            path.Close();

            using var auraPaint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Stroke,
                StrokeWidth = 2,
                Color = priColor.WithAlpha(60)
            };
            canvas.DrawPath(path, auraPaint);
        }

        // Center disc (dark circle + glow ring)
        DrawCenterDisc(canvas, baseR, bass, animTime, palette);
    }

    #endregion

    #region Neon Bars

    private void RenderNeonBars(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                 ColorPalettes.Palette palette)
    {
        int numBars = spectrum.Length;
        float barWidth = (float)_width / numBars * 0.7f;
        float gap = (float)_width / numBars * 0.3f;
        float maxH = _height * 0.7f;

        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);
        var glowColor = ToSKColor(palette.Glow);

        using var barPaint = new SKPaint { IsAntialias = true, Style = SKPaintStyle.Fill };
        using var glowPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill,
            MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, 8)
        };

        for (int i = 0; i < numBars; i++)
        {
            float h = spectrum[i] * maxH;
            float x = i * (barWidth + gap) + gap / 2;
            float y = _height - h;

            float t = (float)i / numBars;
            barPaint.Color = LerpColor(priColor, secColor, t);

            // Glow under bar
            glowPaint.Color = glowColor.WithAlpha((byte)(spectrum[i] * 80));
            canvas.DrawRect(x - 2, y - 4, barWidth + 4, h + 8, glowPaint);

            // Bar body with rounded top
            using var barRect = new SKRoundRect(new SKRect(x, y, x + barWidth, _height), 3, 3);
            canvas.DrawRoundRect(barRect, barPaint);

            // Peak cap line
            if (h > _peakCaps[i])
                _peakCaps[i] = h;
            else
                _peakCaps[i] = Math.Max(0, _peakCaps[i] - 0.8f);

            float peakY = _height - _peakCaps[i];
            using var peakPaint = new SKPaint
            {
                IsAntialias = true,
                Color = priColor.WithAlpha(200),
                StrokeWidth = 2,
                Style = SKPaintStyle.Stroke
            };
            canvas.DrawLine(x, peakY, x + barWidth, peakY, peakPaint);
        }
    }

    #endregion

    #region Ocean Wave

    private void RenderOceanWave(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                  float animTime, ColorPalettes.Palette palette)
    {
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        int layers = 3;
        float[] alphas = [0.25f, 0.18f, 0.12f];
        float[] freqs = [0.008f, 0.012f, 0.006f];
        float[] speeds = [1.0f, 1.4f, 0.7f];
        float[] baseYFactors = [0.6f, 0.55f, 0.65f];

        for (int layer = 0; layer < layers; layer++)
        {
            using var path = new SKPath();
            float baseY = _height * baseYFactors[layer];
            float freq = freqs[layer];
            float spd = speeds[layer];
            float alpha = alphas[layer] + bass * 0.15f;

            path.MoveTo(0, _height);
            for (int x = 0; x <= _width; x += 4)
            {
                int specIdx = Math.Clamp(x * spectrum.Length / _width, 0, spectrum.Length - 1);
                float amp = spectrum[specIdx] * _height * 0.25f * (1f + bass * 0.5f);
                float y = baseY - amp * MathF.Sin(x * freq + animTime * spd * 2f + layer * 1.2f);
                path.LineTo(x, y);
            }
            path.LineTo(_width, _height);
            path.Close();

            var layerColor = LerpColor(priColor, secColor, (float)layer / layers);
            using var wavePaint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Fill,
                Color = layerColor.WithAlpha((byte)(alpha * 255))
            };
            canvas.DrawPath(path, wavePaint);
        }
    }

    #endregion

    #region Quantum Vortex

    private void RenderQuantumVortex(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                      float animTime, ColorPalettes.Palette palette)
    {
        _vortexAngle += 0.02f + bass * 0.05f;
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        using var paint = new SKPaint { IsAntialias = true, Style = SKPaintStyle.Fill };

        // Orbital rings
        for (int ring = 0; ring < 5; ring++)
        {
            float r = 100 + ring * 80 + bass * 30;
            using var ringPaint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Stroke,
                StrokeWidth = 1.5f,
                Color = priColor.WithAlpha((byte)(40 + ring * 15))
            };
            canvas.DrawCircle(_cx, _cy, r, ringPaint);
        }

        // Vortex particles
        for (int i = 0; i < _vortexParticles.Length; i++)
        {
            ref var p = ref _vortexParticles[i];
            p.angle += p.speed * (1 + bass * 3);
            float r = p.radius + bass * 40;
            float px = _cx + r * MathF.Cos(p.angle + _vortexAngle);
            float py = _cy + r * MathF.Sin(p.angle + _vortexAngle);

            if (px < 0 || px > _width || py < 0 || py > _height) continue;

            float t = (float)i / _vortexParticles.Length;
            paint.Color = LerpColor(priColor, secColor, t).WithAlpha((byte)(150 + bass * 100));
            canvas.DrawCircle(px, py, p.size * (1 + bass * 0.5f), paint);
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.12f, bass, animTime, palette);
    }

    #endregion

    #region Neural Synapse

    private void RenderNeuralSynapse(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                      float animTime, ColorPalettes.Palette palette)
    {
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        using var nodePaint = new SKPaint { IsAntialias = true, Style = SKPaintStyle.Fill };
        using var linePaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 1
        };

        // Update and draw nodes
        for (int i = 0; i < _neuralNodes.Length; i++)
        {
            ref var n = ref _neuralNodes[i];
            n.x += n.vx * (1 + bass);
            n.y += n.vy * (1 + bass);

            // Bounce off walls
            if (n.x < 0 || n.x > _width) n.vx = -n.vx;
            if (n.y < 0 || n.y > _height) n.vy = -n.vy;
            n.x = Math.Clamp(n.x, 0, _width);
            n.y = Math.Clamp(n.y, 0, _height);

            int specIdx = Math.Clamp(n.bin, 0, spectrum.Length - 1);
            float energy = spectrum[specIdx];
            float r = n.baseR * (1 + energy * 3);

            nodePaint.Color = LerpColor(priColor, secColor, energy);
            canvas.DrawCircle(n.x, n.y, r, nodePaint);

            // Draw connections to nearby nodes
            for (int j = i + 1; j < _neuralNodes.Length; j++)
            {
                float dx = _neuralNodes[j].x - n.x;
                float dy = _neuralNodes[j].y - n.y;
                float dist = MathF.Sqrt(dx * dx + dy * dy);
                if (dist < 200)
                {
                    float alpha = (1f - dist / 200f) * (0.3f + energy * 0.5f);
                    linePaint.Color = priColor.WithAlpha((byte)(alpha * 255));
                    canvas.DrawLine(n.x, n.y, _neuralNodes[j].x, _neuralNodes[j].y, linePaint);
                }
            }
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.1f, bass, animTime, palette);
    }

    #endregion

    #region Hyper Liquid

    private void RenderHyperLiquid(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                    float animTime, ColorPalettes.Palette palette)
    {
        _liquidPhase += 0.03f + bass * 0.06f;
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        // Metaball-style blobs
        using var blobPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill,
            MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, 20)
        };

        int numBlobs = Math.Min(16, spectrum.Length);
        for (int i = 0; i < numBlobs; i++)
        {
            float angle = i * MathF.PI * 2 / numBlobs + _liquidPhase;
            float dist = 120 + spectrum[i % spectrum.Length] * 250 + bass * 80;
            float x = _cx + dist * MathF.Cos(angle);
            float y = _cy + dist * MathF.Sin(angle);
            float r = 30 + spectrum[i % spectrum.Length] * 60;

            float t = (float)i / numBlobs;
            blobPaint.Color = LerpColor(priColor, secColor, t).WithAlpha((byte)(60 + spectrum[i % spectrum.Length] * 120));
            canvas.DrawCircle(x, y, r, blobPaint);
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.12f, bass, animTime, palette);
    }

    #endregion

    #region Angkor Mandala

    private void RenderAngkorMandala(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                      float animTime, ColorPalettes.Palette palette)
    {
        _mandalaRotation += 0.005f + bass * 0.02f;
        var priColor = ToSKColor(palette.Primary);
        var accentColor = ToSKColor(palette.Accent);

        using var paint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 2
        };

        // Concentric mandala rings with spectrum-modulated vertices
        int symmetry = 12;
        for (int ring = 0; ring < 6; ring++)
        {
            float baseR = 60 + ring * 55 + bass * 20;
            int specBand = Math.Clamp(ring * 10, 0, spectrum.Length - 1);
            float energy = spectrum[specBand];

            using var path = new SKPath();
            bool first = true;
            for (int s = 0; s <= symmetry; s++)
            {
                float angle = s * MathF.PI * 2 / symmetry + _mandalaRotation;
                float r = baseR + energy * 60 * MathF.Sin(angle * 3 + animTime);
                float px = _cx + r * MathF.Cos(angle);
                float py = _cy + r * MathF.Sin(angle);
                if (first) { path.MoveTo(px, py); first = false; }
                else path.LineTo(px, py);
            }
            path.Close();

            float t = (float)ring / 6;
            paint.Color = LerpColor(priColor, accentColor, t).WithAlpha((byte)(120 + energy * 120));
            canvas.DrawPath(path, paint);
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.1f, bass, animTime, palette);
    }

    #endregion

    #region Hologram HUD

    private void RenderHologramHud(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                    float animTime, ColorPalettes.Palette palette)
    {
        _radarAngle += 0.03f + bass * 0.04f;
        var priColor = ToSKColor(palette.Primary);
        var glowColor = ToSKColor(palette.Glow);

        using var paint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 1
        };

        // Concentric rings
        for (int r = 1; r <= 5; r++)
        {
            float radius = r * 70 + bass * 15;
            paint.Color = priColor.WithAlpha((byte)(30 + r * 12));
            canvas.DrawCircle(_cx, _cy, radius, paint);
        }

        // Radar sweep line
        float sweepX = _cx + 350 * MathF.Cos(_radarAngle);
        float sweepY = _cy + 350 * MathF.Sin(_radarAngle);
        paint.Color = glowColor.WithAlpha(120);
        paint.StrokeWidth = 2;
        canvas.DrawLine(_cx, _cy, sweepX, sweepY, paint);

        // Spectrum data points on radar
        for (int i = 0; i < spectrum.Length; i++)
        {
            float angle = i * MathF.PI * 2 / spectrum.Length;
            float dist = 50 + spectrum[i] * 280;
            float px = _cx + dist * MathF.Cos(angle);
            float py = _cy + dist * MathF.Sin(angle);

            using var dotPaint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Fill,
                Color = priColor.WithAlpha((byte)(100 + spectrum[i] * 155))
            };
            canvas.DrawCircle(px, py, 2 + spectrum[i] * 3, dotPaint);
        }

        // HUD text elements
        using var font = new SKFont(SKTypeface.Default, 11);
        using var textPaint = new SKPaint
        {
            IsAntialias = true,
            Color = priColor.WithAlpha(160)
        };
        canvas.DrawText($"BASS: {bass:F2}", 20, 30, SKTextAlign.Left, font, textPaint);
        canvas.DrawText($"ONSET: {onset:F2}", 20, 46, SKTextAlign.Left, font, textPaint);

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.08f, bass, animTime, palette);
    }

    #endregion

    #region Aurora Borealis

    private void RenderAuroraBorealis(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                       float animTime, ColorPalettes.Palette palette)
    {
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        for (int r = 0; r < _auroraRibbons.Length; r++)
        {
            ref var ribbon = ref _auroraRibbons[r];
            ribbon.phase += ribbon.speed * (1 + bass * 2);

            using var path = new SKPath();
            float baseY = _height * ribbon.yOffset;
            path.MoveTo(0, baseY);

            for (int x = 0; x <= _width; x += 6)
            {
                int specIdx = Math.Clamp(x * spectrum.Length / _width, 0, spectrum.Length - 1);
                float amp = ribbon.amplitude * _height * (0.08f + spectrum[specIdx] * 0.15f);
                float y = baseY + amp * MathF.Sin(x * 0.005f + ribbon.phase);
                path.LineTo(x, y);
            }
            path.LineTo(_width, _height);
            path.LineTo(0, _height);
            path.Close();

            float t = (float)r / _auroraRibbons.Length;
            using var paint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Fill,
                Color = LerpColor(priColor, secColor, t).WithAlpha((byte)(35 + bass * 40))
            };
            canvas.DrawPath(path, paint);
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.1f, bass, animTime, palette);
    }

    #endregion

    #region DNA Helix

    private void RenderDnaHelix(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                 float animTime, ColorPalettes.Palette palette)
    {
        _helixTime += 0.04f + bass * 0.06f;
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        int numRungs = 30;
        float helixW = _width * 0.35f;
        float stepY = (float)_height / numRungs;

        using var strandPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill
        };
        using var rungPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 2
        };

        for (int i = 0; i < numRungs; i++)
        {
            float y = i * stepY;
            float phase = _helixTime + i * 0.3f;
            int specIdx = Math.Clamp(i * spectrum.Length / numRungs, 0, spectrum.Length - 1);
            float energy = spectrum[specIdx];

            float x1 = _cx + helixW * MathF.Sin(phase) * (0.5f + energy * 0.5f);
            float x2 = _cx - helixW * MathF.Sin(phase) * (0.5f + energy * 0.5f);

            float r = 4 + energy * 6;

            // Strand 1
            strandPaint.Color = priColor.WithAlpha((byte)(160 + energy * 95));
            canvas.DrawCircle(x1, y, r, strandPaint);

            // Strand 2
            strandPaint.Color = secColor.WithAlpha((byte)(160 + energy * 95));
            canvas.DrawCircle(x2, y, r, strandPaint);

            // Connecting rung
            rungPaint.Color = priColor.WithAlpha((byte)(40 + energy * 80));
            canvas.DrawLine(x1, y, x2, y, rungPaint);
        }

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.1f, bass, animTime, palette);
    }

    #endregion

    #region Sonic Nebula

    private void RenderSonicNebula(SKCanvas canvas, float[] spectrum, float bass, float onset,
                                    float animTime, ColorPalettes.Palette palette)
    {
        _nebulaTime += 0.01f;
        var priColor = ToSKColor(palette.Primary);
        var secColor = ToSKColor(palette.Secondary);

        using var nebPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill,
            MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, 30)
        };

        // Large nebula clouds
        int numClouds = 12;
        for (int i = 0; i < numClouds; i++)
        {
            float angle = i * MathF.PI * 2 / numClouds + _nebulaTime * 0.5f;
            int specIdx = Math.Clamp(i * spectrum.Length / numClouds, 0, spectrum.Length - 1);
            float dist = 80 + spectrum[specIdx] * 250 + bass * 60;
            float x = _cx + dist * MathF.Cos(angle);
            float y = _cy + dist * MathF.Sin(angle);
            float r = 40 + spectrum[specIdx] * 80;

            float t = (float)i / numClouds;
            nebPaint.Color = LerpColor(priColor, secColor, t).WithAlpha((byte)(30 + spectrum[specIdx] * 80));
            canvas.DrawCircle(x, y, r, nebPaint);
        }

        // Bass shockwave
        if (bass > _nebulaPrevBass + 0.15f)
        {
            float shockR = 50 + bass * 200;
            using var shockPaint = new SKPaint
            {
                IsAntialias = true,
                Style = SKPaintStyle.Stroke,
                StrokeWidth = 3,
                Color = priColor.WithAlpha((byte)(bass * 180))
            };
            canvas.DrawCircle(_cx, _cy, shockR, shockPaint);
        }
        _nebulaPrevBass = bass;

        DrawCenterDisc(canvas, Math.Min(_width, _height) * 0.1f, bass, animTime, palette);
    }

    #endregion

    #region Shared Helpers

    private void DrawCenterDisc(SKCanvas canvas, float baseRadius, float bass, float animTime,
                                 ColorPalettes.Palette palette)
    {
        float dynamicR = baseRadius * (1f + bass * 0.15f);
        var priColor = ToSKColor(palette.Primary);
        var glowColor = ToSKColor(palette.Glow);

        // Dark center fill
        using var discPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill,
            Color = new SKColor(10, 14, 24)
        };
        canvas.DrawCircle(_cx, _cy, dynamicR, discPaint);

        // Glow ring
        using var ringPaint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Stroke,
            StrokeWidth = 3,
            Color = priColor
        };
        canvas.DrawCircle(_cx, _cy, dynamicR, ringPaint);

        // Outer glow
        ringPaint.StrokeWidth = 1;
        ringPaint.Color = glowColor.WithAlpha(120);
        canvas.DrawCircle(_cx, _cy, dynamicR + 2, ringPaint);
    }

    private static SKColor ToSKColor((byte R, byte G, byte B) c)
        => new(c.R, c.G, c.B);

    private static SKColor LerpColor(SKColor a, SKColor b, float t)
    {
        t = Math.Clamp(t, 0f, 1f);
        return new SKColor(
            (byte)(a.Red + (b.Red - a.Red) * t),
            (byte)(a.Green + (b.Green - a.Green) * t),
            (byte)(a.Blue + (b.Blue - a.Blue) * t),
            (byte)(a.Alpha + (b.Alpha - a.Alpha) * t)
        );
    }

    #endregion
}
