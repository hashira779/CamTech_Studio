using Microsoft.Graphics.Canvas;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using System.Numerics;
using Windows.UI;

namespace VidaStudio.Styles.Visualizers;

public class VisualizerPreviewContext
{
    public double WavePhase { get; set; }
    public double AmplitudeScale { get; set; }
    public Color PrimaryColor { get; set; }
    public Color SecondaryColor { get; set; }
    public float Bass { get; set; }
    public double[] Spectrum { get; set; } = new double[0];
}

public class Win2DVisualizerContext
{
    public float Width { get; set; }
    public float Height { get; set; }
    public float Bass { get; set; }
    public float[] Spectrum { get; set; } = new float[0];
    public Color PrimaryColor { get; set; }
    public Color SecondaryColor { get; set; }
    public CanvasBitmap? LogoBitmap { get; set; }
}

public interface IVisualizerStyle
{
    string Id { get; }
    string DisplayName { get; }
    
    // --- XAML Preview ---
    UIElement CreatePreviewElement();
    void UpdatePreview(UIElement element, VisualizerPreviewContext context);

    // --- DirectX Export ---
    void RenderExport(CanvasDrawingSession ds, Win2DVisualizerContext context);

    /// <summary>
    /// Returns true if this visualizer uses a CanvasAnimatedControl for real-time GPU preview.
    /// If true, CreatePreviewElement returns a CanvasAnimatedControl and UpdatePreview feeds data to it.
    /// </summary>
    bool UsesGpuPreview => false;
}
