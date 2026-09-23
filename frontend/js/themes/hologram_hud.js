/**
 * VIDA 2029 Cyberpunk Holographic Spatial HUD Theme
 * Multi-Tier Telemetry Rings • Audio Radar Sweep • Segmented Decibel Gauges
 */
import { state, PALETTES } from '../core/state.js';

let radarAngle = 0;
let hudFlicker = 1;

export function drawHologramHUD(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');
  const accRgb = (pal.accent || [0, 240, 255]).join(',');

  const cx = w / 2;
  const cy = h / 2;
  const baseRadius = Math.min(w, h) * 0.12;

  ctx.save();
  radarAngle += 0.025 + bass * 0.05;
  hudFlicker = Math.random() > 0.96 ? 0.8 : 1.0;

  // 1. Outer Concentric Telemetry Calibration Rings & Compass Ticks
  const outerRadius = Math.min(w, h) * 0.42;
  ctx.beginPath();
  ctx.arc(cx, cy, outerRadius, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(${priRgb}, ${0.2 * hudFlicker})`;
  ctx.lineWidth = 1;
  ctx.stroke();

  // Compass Decibel Degree Ticks
  const totalTicks = 72;
  for (let t = 0; t < totalTicks; t++) {
    const angle = t * (Math.PI * 2 / totalTicks);
    const isMajor = t % 6 === 0;
    const tickLen = isMajor ? 14 : 6;
    const r1 = outerRadius - tickLen;
    const r2 = outerRadius;

    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * r1, cy + Math.sin(angle) * r1);
    ctx.lineTo(cx + Math.cos(angle) * r2, cy + Math.sin(angle) * r2);
    ctx.strokeStyle = isMajor ? `rgba(${secRgb}, ${0.7 * hudFlicker})` : `rgba(${priRgb}, ${0.3 * hudFlicker})`;
    ctx.lineWidth = isMajor ? 2 : 1;
    ctx.stroke();
  }

  // 2. Segmented Circular Audio Decibel Meter Arc (Dual Hemispheres)
  const meterRadius = outerRadius - 35;
  const numSegments = 36;
  for (let s = 0; s < numSegments; s++) {
    const barIdx = Math.floor((s / numSegments) * bars.length);
    const barVal = bars[barIdx] || 0;
    
    // Left & Right Hemisphere mirror
    for (let side of [-1, 1]) {
      const angle = (Math.PI / 2) + side * (s * 0.075 + 0.1);
      const segLen = 6 + barVal * 45;
      
      const p1x = cx + Math.cos(angle) * meterRadius;
      const p1y = cy + Math.sin(angle) * meterRadius;
      const p2x = cx + Math.cos(angle) * (meterRadius + segLen);
      const p2y = cy + Math.sin(angle) * (meterRadius + segLen);

      ctx.beginPath();
      ctx.moveTo(p1x, p1y);
      ctx.lineTo(p2x, p2y);
      ctx.strokeStyle = barVal > 0.6 ? `rgb(${secRgb})` : `rgba(${priRgb}, ${0.6 + barVal * 0.4})`;
      ctx.lineWidth = 3.5;
      ctx.stroke();
    }
  }

  // 3. Sweeping Radar Line & Phosphor Glow
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(radarAngle) * (outerRadius * 0.95), cy + Math.sin(radarAngle) * (outerRadius * 0.95));
  ctx.strokeStyle = `rgba(${secRgb}, ${0.85 * hudFlicker})`;
  ctx.lineWidth = 2 + bass * 2;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // 4. Sci-Fi HUD Reticle Brackets (Top, Bottom, Left, Right)
  const bracketDist = baseRadius * 1.5 + bass * 15;
  const bracketLen = 22;
  const directions = [
    { x: 0, y: -bracketDist, dx: bracketLen, dy: 0 },
    { x: 0, y: bracketDist, dx: bracketLen, dy: 0 },
    { x: -bracketDist, y: 0, dx: 0, dy: bracketLen },
    { x: bracketDist, y: 0, dx: 0, dy: bracketLen }
  ];

  for (let b of directions) {
    ctx.beginPath();
    ctx.moveTo(cx + b.x - b.dx, cy + b.y - b.dy);
    ctx.lineTo(cx + b.x + b.dx, cy + b.y + b.dy);
    ctx.strokeStyle = `rgb(${secRgb})`;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }

  // Live Decibel Readout Text
  ctx.fillStyle = `rgba(${priRgb}, 0.8)`;
  ctx.font = `600 11px 'JetBrains Mono', monospace`;
  ctx.textAlign = 'left';
  ctx.fillText(`SYS: OPTICAL HUD 2029`, cx + outerRadius * 0.45, cy - outerRadius * 0.45);
  ctx.fillText(`BASS PEAK: ${(bass * 100).toFixed(1)}%`, cx + outerRadius * 0.45, cy - outerRadius * 0.45 + 16);
  ctx.fillText(`AUDIO LOCK: TRACKING`, cx + outerRadius * 0.45, cy - outerRadius * 0.45 + 32);

  // 5. Center Core Emblem
  const pulseRadius = baseRadius * (1 + bass * 0.25);
  ctx.beginPath();
  ctx.arc(cx, cy, pulseRadius, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(4, 9, 18, 0.92)";
  ctx.fill();

  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 2.5 + bass * 2;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 20;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Center Logo or HUD Typography
  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, pulseRadius * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - pulseRadius, cy - pulseRadius, pulseRadius * 2, pulseRadius * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : "HUD // 29";
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "CYBER SPATIAL";

    if (center1 && center1.trim()) {
      ctx.fillStyle = `rgb(${priRgb})`;
      ctx.font = `800 ${Math.floor(pulseRadius * 0.36)}px 'JetBrains Mono', monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - pulseRadius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      ctx.font = `600 ${Math.floor(pulseRadius * 0.18)}px 'JetBrains Mono', monospace`;
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
