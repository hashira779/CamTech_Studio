/**
 * VIDA 2026 — Aurora Borealis Silk Theme
 * Fluid northern-lights ribbons that breathe with the music.
 * Multi-layered translucent silk curtains with iridescent color blending.
 */
import { state, PALETTES } from '../core/state.js';
import { glowLayer } from './glow.js';

let auroraTime = 0;
const ribbonCount = 7;

// Persistent ribbon state for smooth animation
const ribbons = [];
for (let i = 0; i < ribbonCount; i++) {
  ribbons.push({
    phase: Math.random() * Math.PI * 2,
    speed: 0.003 + Math.random() * 0.005,
    amplitude: 0.15 + Math.random() * 0.25,
    yOffset: 0.2 + (i / ribbonCount) * 0.55,
    thickness: 0.06 + Math.random() * 0.08,
    hueShift: i * 35
  });
}

export function drawAuroraBorealis(ctx, w, h, bars, bass) {
  auroraTime += 0.018;
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const pri = pal.primary;
  const sec = pal.secondary;
  const acc = pal.accent || [130, 80, 255];
  const count = bars.length;

  ctx.save();

  // ── 1. Deep Space Star Field ──
  ctx.globalAlpha = 0.4;
  for (let i = 0; i < 60; i++) {
    const sx = (Math.sin(i * 127.1 + auroraTime * 0.1) * 0.5 + 0.5) * w;
    const sy = (Math.cos(i * 311.7 + auroraTime * 0.05) * 0.5 + 0.5) * h * 0.6;
    const twinkle = Math.sin(auroraTime * 2 + i) * 0.5 + 0.5;
    ctx.fillStyle = `rgba(255, 255, 255, ${0.15 + twinkle * 0.5})`;
    ctx.beginPath();
    ctx.arc(sx, sy, 0.5 + twinkle * 1.2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1.0;

  // ── 2. Aurora Silk Ribbons ──
  for (let r = 0; r < ribbonCount; r++) {
    const ribbon = ribbons[r];
    ribbon.phase += ribbon.speed + bass * 0.02;

    // Sample frequency bands for this ribbon
    const bandStart = Math.floor((r / ribbonCount) * count);
    const bandEnd = Math.floor(((r + 1) / ribbonCount) * count);
    let bandEnergy = 0;
    for (let b = bandStart; b < bandEnd && b < count; b++) {
      bandEnergy += bars[b] || 0;
    }
    bandEnergy /= Math.max(1, bandEnd - bandStart);

    const points = 80;
    const baseY = ribbon.yOffset * h;

    // Build ribbon path
    ctx.beginPath();
    for (let p = 0; p <= points; p++) {
      const t = p / points;
      const x = t * w;

      // Multi-frequency wave composition for organic flow
      const wave1 = Math.sin(t * Math.PI * 3 + ribbon.phase) * ribbon.amplitude * h;
      const wave2 = Math.sin(t * Math.PI * 5 - ribbon.phase * 1.3) * ribbon.amplitude * h * 0.4;
      const wave3 = Math.cos(t * Math.PI * 2 + ribbon.phase * 0.7) * ribbon.amplitude * h * 0.2;
      const bassWave = Math.sin(t * Math.PI * 1.5 + auroraTime) * bass * h * 0.12;
      const freqReact = bandEnergy * Math.sin(t * Math.PI * 4 + ribbon.phase * 2) * h * 0.15;

      const y = baseY + wave1 + wave2 + wave3 + bassWave + freqReact;

      if (p === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    // Close to bottom for fill
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();

    // Iridescent gradient fill
    const grad = ctx.createLinearGradient(0, baseY - h * 0.2, 0, h);
    const hueShift = ribbon.hueShift + auroraTime * 10;
    const colorT = (r / ribbonCount);
    const cr = Math.floor(pri[0] * (1 - colorT) + sec[0] * colorT);
    const cg = Math.floor(pri[1] * (1 - colorT) + sec[1] * colorT);
    const cb = Math.floor(pri[2] * (1 - colorT) + sec[2] * colorT);
    const intensity = 0.08 + bandEnergy * 0.15 + bass * 0.08;

    grad.addColorStop(0, `rgba(${cr}, ${cg}, ${cb}, ${Math.min(0.5, intensity * 1.8)})`);
    grad.addColorStop(0.3, `rgba(${cr}, ${cg}, ${cb}, ${Math.min(0.35, intensity)})`);
    grad.addColorStop(0.7, `rgba(${acc[0]}, ${acc[1]}, ${acc[2]}, ${intensity * 0.3})`);
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');

    ctx.fillStyle = grad;
    ctx.fill();

    // Bright edge stroke
    const edge = new Path2D();
    for (let p = 0; p <= points; p++) {
      const t = p / points;
      const x = t * w;
      const wave1 = Math.sin(t * Math.PI * 3 + ribbon.phase) * ribbon.amplitude * h;
      const wave2 = Math.sin(t * Math.PI * 5 - ribbon.phase * 1.3) * ribbon.amplitude * h * 0.4;
      const wave3 = Math.cos(t * Math.PI * 2 + ribbon.phase * 0.7) * ribbon.amplitude * h * 0.2;
      const bassWave = Math.sin(t * Math.PI * 1.5 + auroraTime) * bass * h * 0.12;
      const freqReact = bandEnergy * Math.sin(t * Math.PI * 4 + ribbon.phase * 2) * h * 0.15;
      const y = baseY + wave1 + wave2 + wave3 + bassWave + freqReact;
      if (p === 0) edge.moveTo(x, y);
      else edge.lineTo(x, y);
    }
    const edgeAlpha = Math.min(1, 0.4 + bandEnergy * 0.5);
    ctx.lineWidth = 1.5 + bass * 2;
    // full-width glow: low-res blur instead of a full-res one (see glow.js)
    glowLayer(ctx, 15 + bass * 20, (g) => {
      g.strokeStyle = `rgba(${cr}, ${cg}, ${cb}, ${0.6 * edgeAlpha})`;
      g.stroke(edge);
    });
    ctx.strokeStyle = `rgba(${cr}, ${cg}, ${cb}, ${0.4 + bandEnergy * 0.5})`;
    ctx.stroke(edge);
  }

  // ── 3. Horizon Reflection Line ──
  const horizonY = h * 0.82;
  const horizGrad = ctx.createLinearGradient(0, horizonY - 2, 0, horizonY + 2);
  horizGrad.addColorStop(0, 'rgba(255, 255, 255, 0)');
  horizGrad.addColorStop(0.5, `rgba(${pri.join(',')}, ${0.2 + bass * 0.4})`);
  horizGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = horizGrad;
  ctx.fillRect(0, horizonY - 2, w, 4);

  // ── 4. Floating frequency orbs along the bottom ──
  const orbCount = Math.min(count, 32);
  const orbs = [];
  for (let i = 0; i < orbCount; i++) {
    const val = bars[i * Math.floor(count / orbCount)] || 0;
    if (val < 0.05) continue;
    const t = i / orbCount;
    orbs.push({
      val,
      x: (i / orbCount) * w + w / orbCount / 2,
      y: horizonY - val * h * 0.15 - 10,
      r: 2 + val * 8 + bass * 3,
      a: Math.min(1, 0.3 + val * 0.5),
      c: `${Math.floor(pri[0] * (1 - t) + sec[0] * t)}, ${Math.floor(pri[1] * (1 - t) + sec[1] * t)}, ${Math.floor(pri[2] * (1 - t) + sec[2] * t)}`,
    });
  }
  // Glow (blur 12 + val*15 per orb): two low-res buckets instead of 32 full-res blurs
  for (const [lo, hi] of [[0, 0.5], [0.5, Infinity]]) {
    const group = orbs.filter((o) => o.val >= lo && o.val < hi);
    if (!group.length) continue;
    const meanVal = group.reduce((s, o) => s + o.val, 0) / group.length;
    glowLayer(ctx, 12 + meanVal * 15, (g) => {
      for (const o of group) {
        g.fillStyle = `rgba(${o.c}, ${0.8 * o.a})`;
        g.beginPath(); g.arc(o.x, o.y, o.r, 0, Math.PI * 2); g.fill();
      }
    });
  }
  ctx.shadowBlur = 0;
  for (const o of orbs) {
    ctx.beginPath();
    ctx.arc(o.x, o.y, o.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${o.c}, ${o.a})`;
    ctx.fill();
  }


  ctx.restore();
}
