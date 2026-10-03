using System.Collections.Generic;
using System.Linq;

namespace VidaStudio.Styles.Visualizers;

public static class VisualizerFactory
{
    private static readonly Dictionary<string, IVisualizerStyle> _visualizers = new();

    static VisualizerFactory()
    {
        Register(new ModernOrbVisualizer());
        Register(new SpectrumBarsVisualizer());
        Register(new ProSpectrumVisualizer());
    }

    public static void Register(IVisualizerStyle style)
    {
        _visualizers[style.Id] = style;
    }

    public static IVisualizerStyle GetVisualizer(string id)
    {
        if (_visualizers.TryGetValue(id, out var visualizer))
        {
            return visualizer;
        }
        return _visualizers.Values.First(); // Fallback
    }

    public static IEnumerable<IVisualizerStyle> GetAllVisualizers()
    {
        return _visualizers.Values;
    }
}
