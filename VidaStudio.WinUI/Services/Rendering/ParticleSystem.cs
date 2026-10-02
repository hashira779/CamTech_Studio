using SkiaSharp;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// Audio-reactive floating particle system rendered via SkiaSharp.
/// Port of Python ParticleSystem — manages 80 dust motes with bass-reactive velocity.
/// </summary>
public sealed class ParticleSystem
{
    private readonly int _count;
    private readonly int _width, _height;
    private readonly float[] _x, _y, _vx, _vy, _radius, _baseAlpha;
    private readonly Random _rng = new(42);

    public ParticleSystem(int count, int width, int height)
    {
        _count = count;
        _width = width;
        _height = height;

        _x = new float[count];
        _y = new float[count];
        _vx = new float[count];
        _vy = new float[count];
        _radius = new float[count];
        _baseAlpha = new float[count];

        for (int i = 0; i < count; i++)
        {
            _x[i] = (float)(_rng.NextDouble() * width);
            _y[i] = (float)(_rng.NextDouble() * height);
            _vx[i] = (float)(_rng.NextDouble() * 1.0 - 0.5);
            _vy[i] = (float)(-_rng.NextDouble() * 1.0 - 0.2);
            _radius[i] = (float)(_rng.NextDouble() * 2.5 + 1.5);
            _baseAlpha[i] = (float)(_rng.NextDouble() * 0.5 + 0.3);
        }
    }

    public void UpdateAndDraw(SKCanvas canvas, float bass, float onset, SKColor color)
    {
        float boost = 1.0f + bass * 2.5f + onset * 1.5f;

        using var paint = new SKPaint
        {
            IsAntialias = true,
            Style = SKPaintStyle.Fill
        };

        for (int i = 0; i < _count; i++)
        {
            _x[i] += _vx[i] * boost;
            _y[i] += _vy[i] * boost;

            // Wrap around
            if (_x[i] < 0) _x[i] = _width;
            if (_x[i] > _width) _x[i] = 0;
            if (_y[i] < 0) _y[i] = _height;
            if (_y[i] > _height) _y[i] = 0;

            float r = _radius[i] * (1.0f + bass * 0.8f);
            float alpha = Math.Clamp(_baseAlpha[i] + bass * 0.4f, 0f, 1f);

            paint.Color = color.WithAlpha((byte)(alpha * 255));
            canvas.DrawCircle(_x[i], _y[i], r, paint);
        }
    }
}
