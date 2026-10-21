import { state, PALETTES } from './state.js';
import { getFrameSpectrum, hasFeatures } from './audio_features.js';
import { renderRand, resetRenderSeed } from './rng.js';
import { renderActiveTheme } from '../themes/index.js?v=20261012-v1';
import { cachedFill } from '../themes/fill_cache.js';
import { updateLyricState, drawLyrics } from './lyrics.js?v=20261012-v2';
import { getCameraShakeOffset, renderPostVFX, resetVFX } from '../plugins/vfx_engine.js';
import { evaluateDirectorRules, resetDirector } from '../plugins/director_rules.js';

let canvas = null;
let ctx = null;
let isRendering = false;
let animationFrameId = null;
let lastFrameTs = 0;

// Ballistics state (frame-rate independent, shared by preview & export)
let prevSpectrum = new Float32Array(256);
let tempSpectrum = new Float32Array(256);
let smoothedBass = 0.2;

// Time constants derived from the original 60fps coefficients
const TAU_ATTACK = -1 / (60 * Math.log(1 - 0.6));
const TAU_BASS = -1 / (60 * Math.log(0.8));

// Ambient particle fill styles: one `rgba()` per (palette, alpha) instead of one
// per particle per frame (80 string allocations -> a couple of lookups).
const dotStyles = new Map();
function dotFill(rgb, a) {
  const q = Math.min(255, Math.max(0, Math.round(a * 255)));
  const ck = rgb + '|' + q;
  let s = dotStyles.get(ck);
  if (!s) {
    s = `rgba(${rgb}, ${(q / 255).toFixed(3)})`;
    dotStyles.set(ck, s);
    if (dotStyles.size > 900) dotStyles.clear();
  }
  return s;
}

// Ambient Particles (seeded so preview & export reproduce the same field)
const particles = [];
function initParticles() {
  particles.length = 0;
  for (let i = 0; i < 80; i++) {
    particles.push({
      x: renderRand() * 1920,
      y: renderRand() * 1080,
      vx: (renderRand() - 0.5) * 0.9,
      vy: -renderRand() * 1.3 - 0.3,
      r: renderRand() * 2.8 + 1.2,
      alpha: renderRand() * 0.5 + 0.3
    });
  }
}
initParticles();

export function initVisualizer(canvasElement) {
  canvas = canvasElement;
  ctx = canvas.getContext('2d');
  logicalW = canvas.width;
  logicalH = canvas.height;
  installShadowScale(ctx);
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver((entries) => {
      for (const e of entries) {
        cssWidth = e.contentRect.width;
        cssHeight = e.contentRect.height;
      }
      applyPreviewBacking();
    }).observe(canvas);
  }
  applyPreviewBacking();
}

/*
 * Adaptive preview resolution.
 *
 * The scene is always laid out in the logical project size (1920x1080 etc.) —
 * that is what the exporter renders — but the preview canvas is shown at a
 * few hundred CSS px. Rasterising all 2M pixels for a 439px box made the
 * preview GPU-bound (~25-50 fps). The backing store now follows the displayed
 * size (steps of 0.5 / 0.75 / 1 of the logical size, never below 2x the
 * on-screen pixels at the minimum step), with a scale transform so every
 * theme draws exactly the same layout. Canvas shadows are specified in device
 * pixels, so they are scaled with it to keep the glow proportions unchanged.
 */
let logicalW = 1920;
let logicalH = 1080;
let cssWidth = 0;
let cssHeight = 0;
let previewScale = 1;

function pickPreviewScale() {
  const dpr = window.devicePixelRatio || 1;
  const need = Math.max(cssWidth / logicalW, cssHeight / logicalH) * dpr;
  if (need <= 0.5) return 0.5;
  if (need <= 0.75) return 0.75;
  return 1;
}

function applyPreviewBacking() {
  if (!canvas) return;
  const s = pickPreviewScale();
  const bw = Math.round(logicalW * s);
  const bh = Math.round(logicalH * s);
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  previewScale = s;
  ctx.__shadowScale = s;
}

/** Project (logical) size of the preview — use instead of canvas.width/height. */
export function getPreviewSize() {
  return { width: logicalW, height: logicalH };
}

export function setPreviewSize(w, h) {
  logicalW = w;
  logicalH = h;
  applyPreviewBacking();
}

// Per-instance accessors: only the preview context scales its shadows; the
// exporter's own canvas is untouched.
function installShadowScale(c) {
  const P = CanvasRenderingContext2D.prototype;
  for (const key of ['shadowBlur', 'shadowOffsetX', 'shadowOffsetY']) {
    const d = Object.getOwnPropertyDescriptor(P, key);
    if (!d || !d.set) continue;
    let v = d.get.call(c);
    Object.defineProperty(c, key, {
      configurable: true,
      get() { return v; },
      set(x) { v = x; d.set.call(this, x * (this.__shadowScale || 1)); },
    });
  }
}

export function startVisualizer() {
  if (isRendering && animationFrameId) return;
  isRendering = true;
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
  lastFrameTs = 0;
  animationFrameId = requestAnimationFrame(renderFrame);
}

export function stopVisualizer() {
  isRendering = false;
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
}

/** Restarts every stateful part of the scene so a session replays identically from t = 0. */
export function resetSceneState() {
  resetRenderSeed();
  initParticles();
  prevSpectrum.fill(0);
  tempSpectrum.fill(0);
  smoothedBass = 0.2;
  resetVFX();
  resetDirector();
}

/**
 * The single source of truth for one video frame. The live preview and the
 * offline exporter both call this, so what you see is exactly what you get.
 * t = song time (s), dt = step size (s).
 */
export function renderScene(context, surface, t, dt) {
  const width = surface.width;
  const height = surface.height;

  context.clearRect(0, 0, width, height);

  // Apply Camera Shake Transform if active
  const shake = getCameraShakeOffset(renderRand, dt);
  context.save();
  if (shake.x !== 0 || shake.y !== 0 || shake.angle !== 0) {
    context.translate(width / 2 + shake.x, height / 2 + shake.y);
    context.rotate(shake.angle);
    context.translate(-width / 2, -height / 2);
  }

  // Draw Background
  if (state.bgVideoObj) {
    context.drawImage(state.bgVideoObj, 0, 0, width, height);
  } else if (state.bgImageObj && state.bgImageObj.complete) {
    context.drawImage(state.bgImageObj, 0, 0, width, height);
  } else {
    // The default wash is a fixed image for a given size + palette: shade it
    // once, blit it every frame. It is opaque once composited, so it is cached
    // on black and drawn at half resolution (two-stop radial = pure gradient).
    const curPal = PALETTES[state.palette] || PALETTES.cyberpunk;
    cachedFill(context, `bg.wash|${state.palette}|${curPal.secondary.join(',')}`, (g, bw, bh) => {
      g.fillStyle = '#000000';
      g.fillRect(0, 0, bw, bh);
      const s = bw / width;
      g.setTransform(s, 0, 0, s, 0, 0);
      const bgGrad = g.createRadialGradient(width / 2, height * 0.45, width * 0.05, width / 2, height / 2, width * 0.75);
      bgGrad.addColorStop(0, `rgba(${curPal.secondary.join(',')}, 0.08)`);
      bgGrad.addColorStop(0.55, "#0b0e17");
      bgGrad.addColorStop(1, "#040508");
      g.fillStyle = bgGrad;
      g.fillRect(0, 0, width, height);
    }, 2);
  }

  const rawData = getFrameSpectrum(t);

  let bass = 0;
  const barCount = state.barCount;
  const displayBars = [];

  if (rawData) {
    const binCount = rawData.length; // 1024

    // Low pass filter for bass (approx 0-250Hz)
    let bassSum = 0;
    const bassBins = Math.max(1, Math.floor(binCount * (250 / 22050)));
    for (let i = 0; i < bassBins; i++) bassSum += rawData[i];
    const instBass = (bassSum / bassBins) / 255.0;
    // Fast attack, slow decay for bass (frame-rate independent)
    const aBass = 1 - Math.exp(-dt / TAU_BASS);
    smoothedBass = smoothedBass * (1 - aBass) + instBass * aBass;
    bass = smoothedBass * state.bassBoost;

    // Resample frequency bins into exactly 'barCount' buckets with logarithmic scaling
    const activeBins = Math.floor(binCount * 0.7); // Discard top 30% (mostly noise)
    const minLog = Math.log(1);
    const maxLog = Math.log(activeBins);
    const scale = (maxLog - minLog) / barCount;

    const decay = Math.max(0.01, Math.min(0.995, state.smoothing));
    const aAttack = 1 - Math.exp(-dt / TAU_ATTACK);
    const aDecay = 1 - Math.exp(-dt / (-1 / (60 * Math.log(decay))));

    for (let i = 0; i < barCount; i++) {
      const startBin = Math.floor(Math.exp(minLog + i * scale));
      const endBin = Math.floor(Math.exp(minLog + (i + 1) * scale));

      let sum = 0;
      let count = 0;
      for (let j = startBin; j <= endBin && j < activeBins; j++) {
        sum += rawData[j];
        count++;
      }
      const instVal = count > 0 ? (sum / count) / 255.0 : 0;

      // Asymmetric Ballistics: Responsive Attack, Smooth Decay
      if (instVal > prevSpectrum[i]) {
        tempSpectrum[i] = prevSpectrum[i] * (1 - aAttack) + instVal * aAttack;
      } else {
        tempSpectrum[i] = prevSpectrum[i] * (1 - aDecay) + instVal * aDecay;
      }
    }

    // Spatial Gaussian Convolution (Neighborhood smoothing)
    for (let i = 0; i < barCount; i++) {
      const p2 = i > 1 ? tempSpectrum[i - 2] : tempSpectrum[0];
      const p1 = i > 0 ? tempSpectrum[i - 1] : tempSpectrum[0];
      const c0 = tempSpectrum[i];
      const n1 = i < barCount - 1 ? tempSpectrum[i + 1] : tempSpectrum[barCount - 1];
      const n2 = i < barCount - 2 ? tempSpectrum[i + 2] : tempSpectrum[barCount - 1];

      const smoothedVal = p2 * 0.07 + p1 * 0.23 + c0 * 0.40 + n1 * 0.23 + n2 * 0.07;
      prevSpectrum[i] = smoothedVal;
      displayBars.push(smoothedVal);
    }
  } else {
    for (let i = 0; i < barCount; i++) {
      displayBars.push(0);
      prevSpectrum[i] = 0;
    }
    bass = 0;
  }

  // 🧠 Evaluate Smart Video Director & Rule Flow System
  evaluateDirectorRules(bass, displayBars, width, height, t * 1000, renderRand);

  // Update particles (seeded, dt-scaled so any fps traces the same path)
  if (state.particlesLevel > 0) {
    context.save();
    const activePalette = PALETTES[state.palette] || PALETTES.cyberpunk;
    const rgb = activePalette.primary.join(',');
    const k = dt * 60;
    const flickerP = Math.min(1, (0.02 + bass * 0.1) * k);
    const aScale = state.particlesLevel / 3;
    let lastFill = '';
    for (const p of particles) {
      if (renderRand() < flickerP) p.alpha = Math.min(1, p.alpha + 0.1);

      p.x += p.vx * k;
      p.y += p.vy * k - (bass * 3 * k);

      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;

      if (p.alpha > 0.05) {
        // 80 dots share one colour and differ only by alpha, and alpha is only
        // ever 0.05..1 in ~0.05 steps after the flicker quantising — so reuse
        // the style string instead of building 80 of them per frame.
        const fill = dotFill(rgb, p.alpha * aScale);
        if (fill !== lastFill) { context.fillStyle = fill; lastFill = fill; }
        context.beginPath();
        context.arc(p.x, p.y, p.r + (bass * 1.5), 0, Math.PI * 2);
        context.fill();
      }
    }
    context.restore();
  }

  // Draw selected theme
  renderActiveTheme(context, width, height, bass, displayBars);

  // Update and draw kinetic lyrics overlay
  updateLyricState(t);
  drawLyrics(context, width, height);

  // Draw Header Metadata (Top-Left)
  if (state.showTitles !== false && state.songTitle) {
    context.save();
    const marginX = width * 0.05;
    const marginY = height * 0.06;
    const titleScale = state.titleScale || 1.5;

    // Song Title
    const titleSize = Math.max(12, Math.floor(height * 0.035 * titleScale));
    context.font = `700 ${titleSize}px 'Kantumruy Pro', 'Outfit', sans-serif`;
    context.textAlign = 'left';
    context.textBaseline = 'top';

    // Shadow
    context.fillStyle = 'rgba(0, 0, 0, 0.7)';
    context.fillText(state.songTitle, marginX + 2, marginY + 2);
    // Text
    context.fillStyle = '#ffffff';
    context.fillText(state.songTitle, marginX, marginY);

    // Artist Name
    if (state.artistName) {
      const artistY = marginY + height * 0.045 * titleScale;
      const artistSize = Math.max(10, Math.floor(height * 0.022 * titleScale));
      const activePalette = PALETTES[state.palette] || PALETTES.cyberpunk;
      context.font = `600 ${artistSize}px 'Kantumruy Pro', 'Outfit', sans-serif`;

      // Shadow
      context.fillStyle = 'rgba(0, 0, 0, 0.5)';
      context.fillText(state.artistName, marginX + 1, artistY + 1);
      // Text
      context.fillStyle = `rgb(${activePalette.primary.join(',')})`;
      context.fillText(state.artistName, marginX, artistY);
    }
    context.restore();
  }

  context.restore(); // Restore Camera Shake Transform

  // ✨ Apply Real-Time Post-Processing VFX (Shockwaves, Bloom Flash, Scanlines)
  renderPostVFX(context, width, height, bass, dt);
}

function renderFrame(ts) {
  if (!isRendering) return;

  try {
    if (!lastFrameTs) lastFrameTs = ts;
    const dt = Math.min(0.05, Math.max(0.001, (ts - lastFrameTs) / 1000));
    lastFrameTs = ts;

    const audioPlayer = document.getElementById("audio-player");
    const t = audioPlayer ? audioPlayer.currentTime : 0;
    if (!hasFeatures() && ctx) {
      // Features not decoded yet (first load): draw a silent frame rather than stale spectrum
    }
    ctx.setTransform(previewScale, 0, 0, previewScale, 0, 0);
    renderScene(ctx, { width: logicalW, height: logicalH }, t, dt);
  } catch (frameErr) {
    console.error('[VIDA Visualizer] Frame render error:', frameErr);
  } finally {
    // Keep 60fps loop alive forever even if individual frame throws
    if (isRendering) {
      animationFrameId = requestAnimationFrame(renderFrame);
    }
  }
}
