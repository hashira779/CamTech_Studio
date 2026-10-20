/**
 * Low-resolution glow layer.
 *
 * Canvas `shadowBlur` costs a full-resolution GPU blur per draw call. On the
 * studio's iGPU a theme that gives every bar its own shadow spent most of its
 * frame there (~130 blur passes, preview stuck at ~33 fps), and the cost grows
 * with the blurred area.
 *
 * A glow is low-frequency by nature, so it does not need full resolution:
 * shapes are drawn once into a down-scaled buffer in their shadow colour, the
 * buffer is blurred with a single filter pass, and the result is upscaled onto
 * the main canvas. Callers then draw the crisp shapes with shadowBlur = 0.
 *
 * Equivalence with `shadowBlur = B, shadowColor = C`: the shadow is the
 * shape's alpha mask tinted with C, blurred with sigma = B / 2. Drawing the
 * shape filled/stroked with C and blurring with sigma B / 2 is the same
 * image, minus the stacking of overlapping shadows (measured per theme).
 *
 * Works for preview and export alike: buffers are sized from ctx.canvas.
 */

const layers = new WeakMap();

function getLayer(canvas, scale) {
  let byScale = layers.get(canvas);
  if (!byScale) { byScale = new Map(); layers.set(canvas, byScale); }
  const w = Math.max(1, Math.ceil(canvas.width / scale));
  const h = Math.max(1, Math.ceil(canvas.height / scale));
  let L = byScale.get(scale);
  if (!L || L.w !== w || L.h !== h) {
    const mk = () => {
      const c = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(w, h) : Object.assign(document.createElement('canvas'), { width: w, height: h });
      return c;
    };
    const a = mk(), b = mk();
    L = { w, h, a, b, ga: a.getContext('2d'), gb: b.getContext('2d') };
    byScale.set(scale, L);
  }
  return L;
}

/**
 * @param {CanvasRenderingContext2D} ctx  target context (current transform is honoured)
 * @param {number} blur                   the shadowBlur value this glow replaces
 * @param {(g:CanvasRenderingContext2D)=>void} draw
 *        draws the glow shapes into `g` in the SAME user coordinates as ctx,
 *        using the old shadowColor as fill/stroke style. lineWidth / lineCap /
 *        lineJoin are copied from ctx before `draw` runs.
 */
export function glowLayer(ctx, blur, draw) {
  if (!(blur > 0)) return;
  // like shadowBlur, `blur` is in output pixels; the adaptive preview renders
  // below project resolution and sets __shadowScale (see visualizer.js)
  const sigma = (blur / 2) * (ctx.__shadowScale || 1);
  // keep >= ~1.5px of blur at low resolution so the upscale stays smooth
  const scale = sigma >= 6 ? 4 : sigma >= 3 ? 2 : 1;
  const L = getLayer(ctx.canvas, scale);
  const { ga, gb, w, h } = L;

  ga.setTransform(1, 0, 0, 1, 0, 0);
  ga.globalAlpha = 1;
  ga.globalCompositeOperation = 'source-over';
  ga.clearRect(0, 0, w, h);
  const m = ctx.getTransform();
  ga.setTransform(m.a / scale, m.b / scale, m.c / scale, m.d / scale, m.e / scale, m.f / scale);
  ga.lineWidth = ctx.lineWidth;
  ga.lineCap = ctx.lineCap;
  ga.lineJoin = ctx.lineJoin;
  draw(ga);

  gb.setTransform(1, 0, 0, 1, 0, 0);
  gb.clearRect(0, 0, w, h);
  gb.filter = `blur(${(sigma / scale).toFixed(2)}px)`;
  gb.drawImage(L.a, 0, 0);
  gb.filter = 'none';

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.shadowBlur = 0;
  ctx.shadowColor = 'transparent';
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(L.b, 0, 0, w, h, 0, 0, w * scale, h * scale);
  ctx.restore();
}
