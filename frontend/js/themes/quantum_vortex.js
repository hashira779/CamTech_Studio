/**
 * VIDA 2026 Quantum Warp Vortex Theme
 * Relativistic Event Horizon • Gravitational Lensing • Inward Particle Spiral
 */
import { state, PALETTES } from '../core/state.js';

let vortexAngle = 0;
const vortexParticles = [];

// Initialize 120 orbiting relativistic quantum particles
for (let i = 0; i < 140; i++) {
  vortexParticles.push({
    radius: Math.random() * 650 + 60,
    angle: Math.random() * Math.PI * 2,
    speed: (Math.random() * 0.02 + 0.008) * (Math.random() > 0.5 ? 1 : 1),
    size: Math.random() * 3.5 + 1.2,
    hueOffset: Math.random() * 40 - 20,
    depth: Math.random()
  });
}

export function drawQuantumVortex(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');
  const accRgb = (pal.accent || [130, 80, 255]).join(',');

  const cx = w / 2;
  const cy = h / 2;
  const baseRadius = Math.min(w, h) * 0.11;
  const eventHorizon = baseRadius * (1 + bass * 0.45);

  ctx.save();
  vortexAngle += 0.012 + bass * 0.04;

  // 1. Gravitational Lensing Distortion Rings (Audio-Reactive Space Warping)
  const ringCount = 14;
  for (let r = 0; r < ringCount; r++) {
    const ringRadius = eventHorizon + (r + 1) * 32 + (bars[r % bars.length] || 0) * 85;
    const alpha = Math.max(0, 0.4 - (r * 0.028) + bass * 0.2);

    ctx.beginPath();
    ctx.arc(cx, cy, ringRadius, 0, Math.PI * 2);
    ctx.strokeStyle = r % 2 === 0 ? `rgba(${priRgb}, ${alpha})` : `rgba(${secRgb}, ${alpha * 0.8})`;
    ctx.lineWidth = 1.5 + (r === 0 ? bass * 3 : 0);
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = r === 0 ? 25 : 8;
    ctx.stroke();
  }
  ctx.shadowBlur = 0;

  // 2. Multi-Strand Quantum Accretion Spiral Arms
  const arms = 6;
  const pointsPerArm = 48;
  for (let a = 0; a < arms; a++) {
    const armAngleOffset = (a * (Math.PI * 2 / arms)) + vortexAngle;
    ctx.beginPath();

    for (let p = 0; p < pointsPerArm; p++) {
      const prog = p / pointsPerArm;
      const barIdx = Math.floor(prog * (bars.length - 1));
      const barVal = bars[barIdx] || 0;
      
      const spiralDist = eventHorizon * 0.9 + prog * (Math.min(w, h) * 0.65) + (barVal * 40);
      const theta = armAngleOffset + prog * 4.2 + (bass * 0.3 * Math.sin(prog * 10));

      const px = cx + Math.cos(theta) * spiralDist;
      const py = cy + Math.sin(theta) * spiralDist;

      if (p === 0) {
        ctx.moveTo(px, py);
      } else {
        ctx.lineTo(px, py);
      }
    }

    const armGrad = ctx.createLinearGradient(cx, cy, cx + Math.cos(armAngleOffset) * 400, cy + Math.sin(armAngleOffset) * 400);
    armGrad.addColorStop(0, `rgba(${priRgb}, ${0.8 + bass * 0.2})`);
    armGrad.addColorStop(0.5, `rgba(${secRgb}, 0.5)`);
    armGrad.addColorStop(1, 'transparent');

    ctx.strokeStyle = armGrad;
    ctx.lineWidth = 2.2 + bass * 2;
    ctx.stroke();
  }

  // 3. Inward Relativistic Particle Stream
  for (let i = 0; i < vortexParticles.length; i++) {
    const pt = vortexParticles[i];
    
    // Orbit and slowly spiral inward
    pt.angle += pt.speed * (1 + bass * 2.5);
    pt.radius -= (0.4 + bass * 1.8);
    if (pt.radius < eventHorizon * 0.8) {
      pt.radius = Math.min(w, h) * 0.55 + Math.random() * 200;
      pt.angle = Math.random() * Math.PI * 2;
    }

    const px = cx + Math.cos(pt.angle) * pt.radius;
    const py = cy + Math.sin(pt.angle) * pt.radius;

    const barIdx = Math.floor((pt.radius / 600) * bars.length) % bars.length;
    const barAmp = bars[barIdx] || 0;
    const pSize = pt.size * (1 + barAmp * 2.2);

    ctx.beginPath();
    ctx.arc(px, py, pSize, 0, Math.PI * 2);
    ctx.fillStyle = i % 2 === 0 ? `rgba(${priRgb}, 0.85)` : `rgba(${secRgb}, 0.85)`;
    ctx.fill();

    // Particle motion blur trail towards center
    ctx.beginPath();
    ctx.moveTo(px, py);
    const trailLen = 8 + bass * 16;
    ctx.lineTo(px - Math.cos(pt.angle) * trailLen, py - Math.sin(pt.angle) * trailLen);
    ctx.strokeStyle = `rgba(${accRgb}, 0.4)`;
    ctx.lineWidth = pSize * 0.6;
    ctx.stroke();
  }

  // 4. Center Black Hole Singularity & Core Emblem
  ctx.beginPath();
  ctx.arc(cx, cy, eventHorizon, 0, Math.PI * 2);
  ctx.fillStyle = '#020308';
  ctx.fill();

  // Glowing photon ring border
  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 3 + bass * 4;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 24 + bass * 20;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Center Logo or Quantum Typography
  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, eventHorizon * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - eventHorizon, cy - eventHorizon, eventHorizon * 2, eventHorizon * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : "QUANTUM";
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "WARP VORTEX";

    if (center1 && center1.trim()) {
      ctx.fillStyle = `rgb(${priRgb})`;
      ctx.font = `800 ${Math.floor(eventHorizon * 0.38)}px 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - eventHorizon * 0.14 : cy);
    }

    if (center2 && center2.trim()) {
      ctx.font = `600 ${Math.floor(eventHorizon * 0.2)}px 'JetBrains Mono', sans-serif`;
      ctx.fillStyle = `rgba(${secRgb}, 0.9)`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center2, cx, center1 && center1.trim() ? cy + eventHorizon * 0.22 : cy);
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
