import { state, PALETTES } from '../core/state.js';
import { glowLayer } from './glow.js';

let peakCaps = new Float32Array(256);
let peakCapDecay = new Float32Array(256);
let neonAnim = 0;

export function drawNeonBars(ctx, w, h, bars, bass) {
  neonAnim += 0.025;
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const count = bars.length;
  const isVintage = state.palette === "vintage_vinyl" || state.palette === "candlelight" || state.palette === "angkor" || state.palette === "chapei_wood";

  const marginX = Math.max(30, w * 0.06);
  const availableW = w - marginX * 2;
  const barW = Math.max(3, (availableW / count) * 0.72);
  const gap = (availableW - barW * count) / Math.max(1, count - 1);
  const baseY = h * 0.72;
  const maxH = h * 0.44;

  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');

  ctx.save();

  // 1. Ambient Background Glow
  const glowGrad = ctx.createRadialGradient(w / 2, baseY - maxH * 0.4, w * 0.05, w / 2, baseY - maxH * 0.4, w * 0.6);
  glowGrad.addColorStop(0, `rgba(${priRgb}, ${0.12 + bass * 0.15})`);
  glowGrad.addColorStop(0.6, `rgba(${secRgb}, ${0.04 + bass * 0.06})`);
  glowGrad.addColorStop(1, "transparent");
  ctx.fillStyle = glowGrad;
  ctx.fillRect(0, 0, w, h);


  // 3. Grid Lines
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
  for (let g = 1; g <= 4; g++) {
    const gy = baseY - (g / 4) * maxH;
    ctx.beginPath();
    ctx.moveTo(marginX, gy);
    ctx.lineTo(w - marginX, gy);
    ctx.stroke();
  }

  // 4. Render Neon Bars with Glow & Segmented Glass
  const items = new Array(count);
  for (let i = 0; i < count; i++) {
    const x = marginX + i * (barW + gap);
    const rawVal = bars[i] || 0;
    const idleVal = Math.sin(neonAnim * 2.0 + i * 0.16) * 0.02 + 0.01;
    const effectiveVal = Math.max(idleVal, rawVal);
    const barHeight = Math.max(4, effectiveVal * maxH);

    // Gravity Peak Drop with lingering trail
    if (barHeight > (peakCaps[i] || 0)) {
      peakCaps[i] = barHeight;
      peakCapDecay[i] = 0;
    } else {
      peakCapDecay[i] = (peakCapDecay[i] || 0) + 0.2;
      peakCaps[i] = Math.max(barHeight, peakCaps[i] - peakCapDecay[i]);
    }

    const t = i / count;
    const r = Math.floor(pal.primary[0] * (1 - t) + pal.secondary[0] * t);
    const g = Math.floor(pal.primary[1] * (1 - t) + pal.secondary[1] * t);
    const b = Math.floor(pal.primary[2] * (1 - t) + pal.secondary[2] * t);
    const capY = baseY - (peakCaps[i] || barHeight) - 4;
    items[i] = { x, barHeight, capY, r, g, b };
  }

  // Bar glow (shadow = the bar's gradient alpha tinted with its colour),
  // all bars in one low-res blur instead of one full-res blur per bar.
  const sa = 0.5 + bass * 0.4;
  glowLayer(ctx, 10 + bass * 6, (gl) => {
    for (const it of items) {
      const gg = gl.createLinearGradient(0, baseY, 0, baseY - it.barHeight);
      gg.addColorStop(0, `rgba(${it.r}, ${it.g}, ${it.b}, ${0.2 * sa})`);
      gg.addColorStop(0.65, `rgba(${it.r}, ${it.g}, ${it.b}, ${0.8 * sa})`);
      gg.addColorStop(0.95, `rgba(${it.r}, ${it.g}, ${it.b}, ${sa})`);
      gl.fillStyle = gg;
      gl.beginPath();
      gl.roundRect(it.x, baseY - it.barHeight, barW, it.barHeight, [3, 3, 0, 0]);
      gl.fill();
    }
  });
  // Peak cap glow
  glowLayer(ctx, 8, (gl) => {
    for (const it of items) {
      gl.fillStyle = `rgb(${it.r}, ${it.g}, ${it.b})`;
      gl.fillRect(it.x, it.capY, barW, 2.5);
    }
  });

  ctx.shadowBlur = 0;
  for (const it of items) {
    const { x, barHeight, capY, r, g, b } = it;
    // Dynamic Upward Neon Bar with Multi-stop Gradient
    const grad = ctx.createLinearGradient(0, baseY, 0, baseY - barHeight);
    grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.2)`);
    grad.addColorStop(0.65, `rgba(${r}, ${g}, ${b}, 0.8)`);
    grad.addColorStop(0.95, `rgb(${r}, ${g}, ${b})`);
    grad.addColorStop(1, "#ffffff");

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x, baseY - barHeight, barW, barHeight, [3, 3, 0, 0]);
    ctx.fill();

    // Peak Cap
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x, capY, barW, 2.5);

    // Floor Glass Reflection
    const reflectGrad = ctx.createLinearGradient(0, baseY, 0, baseY + barHeight * 0.35);
    reflectGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.28)`);
    reflectGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = reflectGrad;
    ctx.fillRect(x, baseY + 3, barW, barHeight * 0.35);
  }

  // 5. Glowing Horizon Baseline
  ctx.lineWidth = 2 + bass * 2;
  const base = (p) => { p.beginPath(); p.moveTo(marginX, baseY); p.lineTo(w - marginX, baseY); };
  glowLayer(ctx, 12 + bass * 8, (gl) => { gl.globalAlpha = 0.85; gl.strokeStyle = pal.glow; base(gl); gl.stroke(); });
  ctx.strokeStyle = `rgba(${priRgb}, 0.85)`;
  base(ctx);
  ctx.stroke();

  ctx.restore();
}
