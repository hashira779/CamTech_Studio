import { state, PALETTES } from '../core/state.js';

let waveAnim = 0;

export function drawWaveTheme(ctx, w, h, bars, bass) {
  waveAnim += 0.02;
  const pal = PALETTES[state.palette] || PALETTES.candlelight;
  const cx = w / 2;
  const cy = h / 2;
  const count = bars.length;
  const isVintage = state.palette === "vintage_vinyl" || state.palette === "candlelight" || state.palette === "angkor" || state.palette === "chapei_wood" || state.palette === "romduol";

  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');

  ctx.save();

  // 1. Ambient Background Vignette & Aura
  const auraGrad = ctx.createRadialGradient(cx, cy, Math.min(w, h) * 0.1, cx, cy, Math.min(w, h) * 0.7);
  auraGrad.addColorStop(0, `rgba(${priRgb}, ${0.15 + bass * 0.15})`);
  auraGrad.addColorStop(0.6, `rgba(${secRgb}, ${0.05 + bass * 0.08})`);
  auraGrad.addColorStop(1, "transparent");
  ctx.fillStyle = auraGrad;
  ctx.fillRect(0, 0, w, h);

  // 2. Top Header HUD (Song & Artist)
  if (state.showTitles !== false) {
    const displayTitle = state.songTitle !== undefined ? state.songTitle : (isVintage ? "ចំប៉ាបាត់ដំបង" : "OCEAN WAVES");
    const displayArtist = state.artistName !== undefined ? state.artistName : (isVintage ? "ស៊ីន ស៊ីសាមុត" : "VIDA WAVE STUDIO");

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    if (displayTitle && displayTitle.trim()) {
      ctx.font = `700 ${Math.max(14, Math.min(22, Math.floor(w * 0.016)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fef3c7" : "#ffffff";
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 10 + bass * 8;
      ctx.fillText(displayTitle, cx, h * 0.10);
      ctx.shadowBlur = 0;
    }

    if (displayArtist && displayArtist.trim()) {
      ctx.font = `600 ${Math.max(10, Math.min(13, Math.floor(w * 0.010)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fde68a" : `rgba(${priRgb}, 0.9)`;
      ctx.fillText(displayArtist, cx, h * 0.10 + 20);
    }
  }

  // 3. Multi-Layer Fluid Wave Harmonic Layers
  for (let layer = 2; layer >= 0; layer--) {
    const opacity = 0.25 + layer * 0.25;
    const amplitude = (h * 0.14) * (1 + layer * 0.45) * (0.8 + bass * 0.8);
    const yOffset = cy + (layer - 1) * 36;

    const t = layer / 3;
    const r = Math.floor(pal.primary[0] * (1 - t) + pal.secondary[0] * t);
    const g = Math.floor(pal.primary[1] * (1 - t) + pal.secondary[1] * t);
    const b = Math.floor(pal.primary[2] * (1 - t) + pal.secondary[2] * t);

    ctx.beginPath();
    ctx.moveTo(0, yOffset);

    for (let i = 0; i <= count; i++) {
      const x = (i / count) * w;
      const barVal = Math.max(0.04, bars[Math.min(i, count - 1)] || 0);
      const wave = Math.sin((i / count) * Math.PI * 4 + waveAnim * (layer + 1.2)) * amplitude * barVal;
      ctx.lineTo(x, yOffset + wave);
    }

    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();

    const grad = ctx.createLinearGradient(0, yOffset - amplitude, 0, h);
    grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${opacity * 0.85})`);
    grad.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, ${opacity * 0.25})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.fill();

    // Wave glowing crest stroke
    ctx.beginPath();
    ctx.moveTo(0, yOffset);
    for (let i = 0; i <= count; i++) {
      const x = (i / count) * w;
      const barVal = Math.max(0.04, bars[Math.min(i, count - 1)] || 0);
      const wave = Math.sin((i / count) * Math.PI * 4 + waveAnim * (layer + 1.2)) * amplitude * barVal;
      ctx.lineTo(x, yOffset + wave);
    }
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${opacity + 0.35})`;
    ctx.lineWidth = 2.5 - layer * 0.4;
    ctx.shadowColor = `rgba(${r}, ${g}, ${b}, 0.7)`;
    ctx.shadowBlur = 10 + bass * 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // 4. Center Glowing Audio-Pulse Core Emblem
  const radius = Math.min(w, h) * 0.085 + bass * 20;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(10, 14, 24, 0.75)";
  ctx.fill();

  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 2.5 + bass * 2;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 15;
  ctx.stroke();
  ctx.shadowBlur = 0;

  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - radius, cy - radius, radius * 2, radius * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : (isVintage ? "យុគមាស" : "VIDA");
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "FLUID WAVE";

    if (center1 && center1.trim()) {
      ctx.fillStyle = isVintage ? "#fef3c7" : `rgb(${priRgb})`;
      ctx.font = `700 ${Math.floor(radius * 0.42)}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - radius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      ctx.font = `600 ${Math.floor(radius * 0.22)}px 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fde68a" : "#94a3b8";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center2, cx, center1 && center1.trim() ? cy + radius * 0.25 : cy);
    }
  }

  ctx.restore();
}
