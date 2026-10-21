/**
 * Cached fill bitmaps.
 *
 * A full-screen soft fill — the background wash, the cinematic vignette, the
 * strobe bloom, the CRT scanlines — is the same pixels every single frame; only
 * the canvas size, the palette and (for the bloom) an overall alpha change.
 * Shading it per frame costs a full-resolution pass: at 1920x1080 that is ~2M
 * pixels of gradient maths 30-60 times a second, twice over, and at export it
 * is a large part of why 1080p crawls.
 *
 * Painting it once into an offscreen bitmap and blitting gives the same image
 * through a memory copy instead of a shader. `scale` drops the bitmap
 * resolution further: valid only for low-frequency fills (a two-stop gradient
 * loses nothing at half size; a 1.5px stripe must stay at 1).
 *
 * The blit always covers the whole backing store, so it ignores the current
 * transform — that is what a full-screen overlay under an identity transform
 * did, and it also means the preview's scaled backing store is filled exactly.
 */

const cache = new Map();

function makeCanvas(w, h) {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(w, h);
  return Object.assign(document.createElement('canvas'), { width: w, height: h });
}

/**
 * @param {CanvasRenderingContext2D} ctx   target; its canvas size defines the blit
 * @param {string} key                     identity of what `paint` draws (palette, effect…)
 * @param {(g:CanvasRenderingContext2D, bw:number, bh:number)=>void} paint
 *         fills the bitmap; receives buffer size so it can map its own units
 * @param {number} [scale=1]               buffer is 1/scale of the canvas
 * @param {number} [alpha=1]               overall alpha of the blit
 */
export function cachedFill(ctx, key, paint, scale = 1, alpha = 1) {
  const canvas = ctx.canvas;
  const w = canvas.width, h = canvas.height;
  const bw = Math.max(1, Math.ceil(w / scale));
  const bh = Math.max(1, Math.ceil(h / scale));
  const ck = `${key}|${w}x${h}|${scale}`;
  let bmp = cache.get(ck);
  if (!bmp) {
    bmp = makeCanvas(bw, bh);
    const g = bmp.getContext('2d');
    g.setTransform(1, 0, 0, 1, 0, 0);
    paint(g, bw, bh);
    cache.set(ck, bmp);
    if (cache.size > 20) {                 // a stale project must not leak
      const oldest = cache.keys().next().value;
      if (oldest !== ck) cache.delete(oldest);
    }
  }
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = alpha;
  ctx.imageSmoothingEnabled = scale > 1;
  ctx.drawImage(bmp, 0, 0, bw, bh, 0, 0, w, h);
  ctx.restore();
  return bmp;
}

/** Called by anything that changes what the cached fills look like. */
export function invalidateFills() {
  cache.clear();
}
