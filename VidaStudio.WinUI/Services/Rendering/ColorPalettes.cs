namespace VidaStudio.Services.Rendering;

/// <summary>
/// All 20+ color palettes matching the Python backend exactly.
/// Each palette is RGB tuples (R, G, B) in 0-255 range.
/// </summary>
public static class ColorPalettes
{
    public record Palette(
        (byte R, byte G, byte B) Primary,
        (byte R, byte G, byte B) Secondary,
        (byte R, byte G, byte B) Accent,
        (byte R, byte G, byte B) Glow,
        (byte R, byte G, byte B) TextHighlight
    );

    public static readonly Dictionary<string, Palette> All = new()
    {
        ["cyberpunk"] = new((0, 240, 255), (255, 0, 128), (120, 0, 255), (0, 255, 200), (0, 240, 255)),
        ["sunset"] = new((255, 170, 0), (255, 45, 85), (160, 20, 100), (255, 200, 50), (255, 215, 0)),
        ["matrix"] = new((0, 255, 128), (0, 180, 255), (10, 60, 30), (50, 255, 150), (0, 255, 160)),
        ["electric"] = new((130, 80, 255), (0, 210, 255), (50, 20, 120), (180, 120, 255), (220, 180, 255)),
        ["angkor"] = new((255, 183, 3), (251, 133, 0), (142, 71, 0), (255, 200, 50), (255, 215, 0)),
        ["bloodmoon"] = new((230, 57, 70), (114, 9, 183), (43, 45, 66), (230, 80, 90), (255, 100, 100)),
        ["pastel"] = new((247, 37, 133), (114, 9, 183), (76, 201, 240), (247, 100, 180), (255, 150, 200)),
        ["monochrome"] = new((248, 249, 250), (108, 117, 125), (33, 37, 41), (200, 200, 200), (255, 255, 255)),
        ["vintage_vinyl"] = new((217, 163, 98), (140, 80, 30), (245, 215, 160), (217, 163, 98), (245, 215, 160)),
        ["candlelight"] = new((251, 146, 60), (194, 65, 12), (254, 215, 170), (251, 146, 60), (254, 215, 170)),
        ["rainy_night"] = new((56, 189, 248), (14, 116, 144), (186, 230, 253), (56, 189, 248), (125, 211, 252)),
        ["tonle_sap"] = new((14, 165, 233), (3, 105, 161), (125, 211, 252), (14, 165, 233), (56, 189, 248)),
        ["royal_palace"] = new((234, 179, 8), (161, 98, 7), (254, 240, 138), (234, 179, 8), (250, 204, 21)),
        ["romduol"] = new((253, 224, 71), (161, 98, 7), (254, 249, 195), (253, 224, 71), (254, 240, 138)),
        ["pleng_kar"] = new((244, 63, 94), (190, 18, 60), (254, 205, 211), (244, 63, 94), (251, 113, 133)),
        ["romvong_festive"] = new((236, 72, 153), (219, 39, 119), (251, 207, 232), (236, 72, 153), (244, 114, 182)),
        ["kirirom_pine"] = new((16, 185, 129), (5, 150, 105), (167, 243, 208), (16, 185, 129), (52, 211, 153)),
        ["lotus_pond"] = new((244, 114, 182), (219, 39, 119), (252, 231, 243), (244, 114, 182), (244, 114, 182)),
        ["chapei_wood"] = new((217, 119, 6), (146, 64, 14), (253, 230, 138), (217, 119, 6), (251, 191, 36)),
    };

    public static Palette Get(string name)
        => All.TryGetValue(name, out var p) ? p : All["cyberpunk"];
}
