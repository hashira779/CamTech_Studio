/**
 * VIDA 2028 Hyper-Liquid Chromatic Wave Theme
 * Multi-Layer Ferrofluid Dynamic Ribbons • Subsurface Sheen • Organic Droplets
 */
import { state, PALETTES } from '../core/state.js';

let liquidPhase = 0;
const liquidDroplets = [];

// Floating reactive droplets
for (let i = 0; i < 40; i++) {
  liquidDroplets.push({
    x: Math.random() * 1920,
    y: Math.random() * 1080,
    vy: -(Math.random() * 1.5 + 0.5),
    r: Math.random() * 8 + 3,
    phase: Math.random() * Math.PI * 2,
    harmonicBin: Math.floor(Math.random() * 64)
  });
}

export function drawHyperLiquid(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');
  const accRgb = (pal.accent || [130, 80, 255]).join(',');

  const cx = w / 2;
  const cy = h / 2;
  const coreRadius = Math.min(w, h) * 0.11;

  ctx.save();
  liquidPhase += 0.02 + bass * 0.05;

  // 1. Multi-Layer Visceral Liquid Ribbons (Chromatically displaced)
  const ribbonLayers = 5;
  const points = 60;
  const step = w / (points - 1);

  for (let l = 0; l < ribbonLayers; l++) {
    const layerProg = l / ribbonLayers;
    const baseHeight = cy + (l - 2) * 55;
    const layerAmp = (60 + l * 25) * (1 + bass * 1.6);

    ctx.beginPath();
    ctx.moveTo(0, h);
    ctx.lineTo(0, baseHeight);

    for (let i = 0; i < points; i++) {
      const x = i * step;
      const barIdx = Math.floor((i / points) * bars.length);
      const barVal = bars[barIdx] || 0;

      // Harmonic wave synthesis
      const wave1 = Math.sin(liquidPhase * 1.5 + i * 0.15 + l) * layerAmp * 0.4;
      const wave2 = Math.cos(liquidPhase * 0.8 + i * 0.3 - l) * layerAmp * 0.25;
      const soundWave = barVal * layerAmp * 1.2;

      const y = baseHeight + wave1 + wave2 - soundWave;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        const prevX = (i - 1) * step;
        const cpx = (prevX + x) / 2;
        ctx.quadraticCurveTo(prevX, y, cpx, y);
      }
    }

    ctx.lineTo(w, h);
    ctx.closePath();

    // Liquid Gradient with Subsurface Sheen
    const liquidGrad = ctx.createLinearGradient(0, baseHeight - layerAmp, 0, h);
    liquidGrad.addColorStop(0, l % 2 === 0 ? `rgba(${priRgb}, 0.75)` : `rgba(${secRgb}, 0.65)`);
    liquidGrad.addColorStop(0.4, `rgba(${accRgb}, 0.45)`);
    liquidGrad.addColorStop(1, 'rgba(6, 8, 16, 0.95)');

    ctx.fillStyle = liquidGrad;
    ctx.fill();

    // Crest Highlights
    ctx.strokeStyle = `rgba(255, 255, 255, ${0.4 + bass * 0.4})`;
    ctx.lineWidth = 1.5 + (l === 0 ? 1.5 : 0);
    ctx.stroke();
  }

  // 2. Audio-Reactive Floating Liquid Droplets
  for (let d of liquidDroplets) {
    const barAmp = bars[d.harmonicBin % bars.length] || 0;
    d.y += d.vy * (1 + bass * 3);
    d.x += Math.sin(liquidPhase + d.phase) * 1.2;

    if (d.y < -30) {
      d.y = h + 20;
      d.x = Math.random() * w;
    }

    const dropRadius = d.r * (1 + barAmp * 2.5 + bass);
    ctx.beginPath();
    ctx.arc(d.x, d.y, dropRadius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${priRgb}, 0.85)`;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 12;
    ctx.fill();

    // Specular highlight on droplet
    ctx.beginPath();
    ctx.arc(d.x - dropRadius * 0.3, d.y - dropRadius * 0.3, dropRadius * 0.3, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.7)";
    ctx.fill();
  }
  ctx.shadowBlur = 0;

  // 3. Center Morphing Fluid Core Emblem
  const pulseRadius = coreRadius * (1 + bass * 0.3);
  ctx.beginPath();
  
  // Wobbly liquid perimeter
  const numPetals = 16;
  for (let a = 0; a < Math.PI * 2; a += 0.05) {
    const wobble = Math.sin(a * 4 + liquidPhase * 2) * (6 + bass * 14);
    const r = pulseRadius + wobble;
    const px = cx + Math.cos(a) * r;
    const py = cy + Math.sin(a) * r;
    if (a === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();

  ctx.fillStyle = "rgba(9, 12, 22, 0.88)";
  ctx.fill();

  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 3 + bass * 3;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 22;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Center Logo or Liquid Typography
  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, pulseRadius * 0.9, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - pulseRadius, cy - pulseRadius, pulseRadius * 2, pulseRadius * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : "HYPER";
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "LIQUID WAVE";

    if (center1 && center1.trim()) {
      ctx.fillStyle = `rgb(${priRgb})`;
      ctx.font = `800 ${Math.floor(pulseRadius * 0.38)}px 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - pulseRadius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      ctx.font = `600 ${Math.floor(pulseRadius * 0.22)}px 'Outfit', sans-serif`;
      ctx.fillStyle = `rgba(${secRgb}, 0.95)`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center2, cx, center1 && center1.trim() ? cy + pulseRadius * 0.24 : cy);
    }
  }

  // Top Header HUD (Song & Artist)
  if (state.showTitles !== false) {
    const displayTitle = state.songTitle;
    const displayArtist = state.artistName;

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    if (displayTitle && displayTitle.trim()) {
      ctx.font = `700 ${Math.max(14, Math.min(22, Math.floor(w * 0.016)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = "#ffffff";
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 10 + bass * 8;
      ctx.fillText(displayTitle, cx, h * 0.10);
      ctx.shadowBlur = 0;
    }

    if (displayArtist && displayArtist.trim()) {
      ctx.font = `600 ${Math.max(10, Math.min(13, Math.floor(w * 0.010)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = `rgba(${priRgb}, 0.9)`;
      ctx.fillText(displayArtist, cx, h * 0.10 + 20);
    }
  }

  ctx.restore();
}
