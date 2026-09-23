import { state, PALETTES } from '../core/state.js';

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

  // 2. Neon Header HUD (Artist & Title)
  if (state.showTitles !== false) {
    const displayTitle = state.songTitle !== undefined ? state.songTitle : (isVintage ? "ចំប៉ាបាត់ដំបង" : "CYBER HORIZON");
    const displayArtist = state.artistName !== undefined ? state.artistName : (isVintage ? "ស៊ីន ស៊ីសាមុត" : "VIDA NEON CORE");

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    if (displayTitle && displayTitle.trim()) {
      ctx.font = `700 ${Math.max(14, Math.min(22, Math.floor(w * 0.016)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fef3c7" : "#ffffff";
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 12 + bass * 10;
      ctx.fillText(displayTitle, w / 2, h * 0.12);
      ctx.shadowBlur = 0;
    }

    if (displayArtist && displayArtist.trim()) {
      ctx.font = `600 ${Math.max(10, Math.min(13, Math.floor(w * 0.010)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fde68a" : `rgba(${priRgb}, 0.9)`;
      ctx.fillText(displayArtist, w / 2, h * 0.12 + 22);
    }
  }

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

    // Dynamic Upward Neon Bar with Multi-stop Gradient
    const grad = ctx.createLinearGradient(0, baseY, 0, baseY - barHeight);
    grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.2)`);
    grad.addColorStop(0.65, `rgba(${r}, ${g}, ${b}, 0.8)`);
    grad.addColorStop(0.95, `rgb(${r}, ${g}, ${b})`);
    grad.addColorStop(1, "#ffffff");

    ctx.fillStyle = grad;
    ctx.shadowColor = `rgba(${r}, ${g}, ${b}, ${0.5 + bass * 0.4})`;
    ctx.shadowBlur = 10 + bass * 6;
    ctx.beginPath();
    ctx.roundRect(x, baseY - barHeight, barW, barHeight, [3, 3, 0, 0]);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Glowing Peak Cap
    const capY = baseY - (peakCaps[i] || barHeight) - 4;
    ctx.fillStyle = "#ffffff";
    ctx.shadowColor = `rgb(${r}, ${g}, ${b})`;
    ctx.shadowBlur = 8;
    ctx.fillRect(x, capY, barW, 2.5);
    ctx.shadowBlur = 0;

    // Floor Glass Reflection
    const reflectGrad = ctx.createLinearGradient(0, baseY, 0, baseY + barHeight * 0.35);
    reflectGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.28)`);
    reflectGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = reflectGrad;
    ctx.fillRect(x, baseY + 3, barW, barHeight * 0.35);
  }

  // 5. Glowing Horizon Baseline
  ctx.strokeStyle = `rgba(${priRgb}, 0.85)`;
  ctx.lineWidth = 2 + bass * 2;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 12 + bass * 8;
  ctx.beginPath();
  ctx.moveTo(marginX, baseY);
  ctx.lineTo(w - marginX, baseY);
  ctx.stroke();
  ctx.shadowBlur = 0;

  ctx.restore();
}
