/**
 * VIDA Studio Pro — Real-Time VFX Post-Processing Plugin Engine
 * Camera Shake • Bass Shockwaves • Optical Bloom Flash • RGB Split • CRT Scanlines
 */
import { state, PALETTES } from '../core/state.js';

let shakePower = 0;
let flashAlpha = 0;
const shockwaves = [];

/**
 * Trigger Camera Shake (called by bass drop or rule engine)
 */
export function triggerCameraShake(intensity = 15) {
  if (!state.vfxShake) return;
  shakePower = Math.max(shakePower, intensity * (state.vfxIntensity || 1));
}

/**
 * Trigger Center Shockwave Ring
 */
export function triggerShockwave(cx, cy, power = 1.0) {
  if (!state.vfxShockwave) return;
  shockwaves.push({
    x: cx,
    y: cy,
    radius: 40,
    maxRadius: 550 * power * (state.vfxIntensity || 1),
    speed: 14 + power * 10,
    alpha: 0.9,
    width: 4 + power * 6
  });
}

/**
 * Trigger Optical Strobe Bloom Flash
 */
export function triggerBloomFlash(intensity = 0.6) {
  if (!state.vfxBloom) return;
  flashAlpha = Math.max(flashAlpha, Math.min(1.0, intensity * (state.vfxIntensity || 1)));
}

/**
 * Get current frame camera transform for pre-render shake
 */
export function getCameraShakeOffset() {
  if (shakePower <= 0.1 || !state.vfxShake) {
    shakePower = 0;
    return { x: 0, y: 0, angle: 0 };
  }

  const offset = {
    x: (Math.random() - 0.5) * shakePower,
    y: (Math.random() - 0.5) * shakePower,
    angle: (Math.random() - 0.5) * shakePower * 0.0008
  };

  // Natural physics decay
  shakePower *= 0.88;
  return offset;
}

/**
 * Render Post-Processing VFX Layer (called after themes and lyrics)
 */
export function renderPostVFX(ctx, w, h, bass) {
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');

  // 1. Render Expanding Audio Shockwaves
  if (shockwaves.length > 0 && state.vfxShockwave) {
    ctx.save();
    for (let i = shockwaves.length - 1; i >= 0; i--) {
      const sw = shockwaves[i];
      sw.radius += sw.speed;
      sw.alpha *= 0.93;

      if (sw.alpha < 0.02 || sw.radius >= sw.maxRadius) {
        shockwaves.splice(i, 1);
        continue;
      }

      ctx.beginPath();
      ctx.arc(sw.x, sw.y, sw.radius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(${secRgb}, ${sw.alpha})`;
      ctx.lineWidth = sw.width * (sw.alpha);
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 18;
      ctx.stroke();

      // Outer refraction ring
      ctx.beginPath();
      ctx.arc(sw.x, sw.y, sw.radius * 0.96, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(${priRgb}, ${sw.alpha * 0.6})`;
      ctx.lineWidth = sw.width * 0.5;
      ctx.stroke();
    }
    ctx.restore();
  }

  // 2. Optical Strobe Bloom Flash Overlay
  if (flashAlpha > 0.01 && state.vfxBloom) {
    ctx.save();
    const flashGrad = ctx.createRadialGradient(w / 2, h / 2, 40, w / 2, h / 2, Math.min(w, h) * 0.7);
    flashGrad.addColorStop(0, `rgba(255, 255, 255, ${flashAlpha * 0.85})`);
    flashGrad.addColorStop(0.4, `rgba(${priRgb}, ${flashAlpha * 0.4})`);
    flashGrad.addColorStop(1, 'transparent');

    ctx.fillStyle = flashGrad;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();

    flashAlpha *= 0.84; // Fast bloom decay
  }

  // 3. Cyberpunk CRT Scanlines
  if (state.vfxScanlines) {
    ctx.save();
    ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
    for (let y = 0; y < h; y += 4) {
      ctx.fillRect(0, y, w, 1.5);
    }
    ctx.restore();
  }

  // 4. Subtle Cinematic Vignette
  ctx.save();
  const vigGrad = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.min(w, h) * 0.75);
  vigGrad.addColorStop(0, 'transparent');
  vigGrad.addColorStop(1, 'rgba(0, 0, 0, 0.45)');
  ctx.fillStyle = vigGrad;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();
}
