/**
 * VIDA 2026 — DNA Helix Waveform Theme
 * Double-helix DNA strands that twist and pulse with audio frequency data.
 * Bio-luminescent molecular visualization with phosphor glow trails.
 */
import { state, PALETTES } from '../core/state.js';

let helixTime = 0;

export function drawDNAHelix(ctx, w, h, bars, bass) {
  helixTime += 0.022 + bass * 0.015;
  const pal = PALETTES[state.palette] || PALETTES.electric;
  const pri = pal.primary;
  const sec = pal.secondary;
  const acc = pal.accent || [130, 80, 255];
  const count = bars.length;

  const cx = w / 2;
  const cy = h / 2;

  ctx.save();

  // ── 1. Bio-luminescent Background Pulse ──
  const bgGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.6);
  bgGrad.addColorStop(0, `rgba(${pri.join(',')}, ${0.04 + bass * 0.06})`);
  bgGrad.addColorStop(0.5, `rgba(${sec.join(',')}, ${0.02 + bass * 0.03})`);
  bgGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, w, h);

  // ── 2. Double Helix DNA Strands ──
  const helixRadius = Math.min(w, h) * 0.12;
  const helixLength = h * 0.8;
  const startY = (h - helixLength) / 2;
  const segments = 120;
  const twistSpeed = 3.5;

  // Draw connecting rungs first (behind strands)
  const rungInterval = 4;
  for (let i = 0; i < segments; i += rungInterval) {
    const t = i / segments;
    const y = startY + t * helixLength;
    const barIdx = Math.floor(t * count);
    const val = bars[barIdx] || 0;

    const angle = t * Math.PI * twistSpeed + helixTime;
    const x1 = cx + Math.sin(angle) * (helixRadius + val * helixRadius * 1.5);
    const x2 = cx + Math.sin(angle + Math.PI) * (helixRadius + val * helixRadius * 1.5);

    // DNA base pair rungs
    const depth = (Math.cos(angle) + 1) / 2; // 0-1 depth factor
    const rungAlpha = 0.15 + val * 0.4 + bass * 0.1;

    ctx.beginPath();
    ctx.moveTo(x1, y);
    ctx.lineTo(x2, y);

    const rungGrad = ctx.createLinearGradient(x1, y, x2, y);
    rungGrad.addColorStop(0, `rgba(${pri.join(',')}, ${rungAlpha})`);
    rungGrad.addColorStop(0.3, `rgba(${acc.join(',')}, ${rungAlpha * 0.7})`);
    rungGrad.addColorStop(0.7, `rgba(${acc.join(',')}, ${rungAlpha * 0.7})`);
    rungGrad.addColorStop(1, `rgba(${sec.join(',')}, ${rungAlpha})`);
    ctx.strokeStyle = rungGrad;
    ctx.lineWidth = 2 + val * 3 + bass * 2;
    ctx.globalAlpha = 0.4 + depth * 0.6;
    ctx.stroke();

    // Nucleotide node circles at rung endpoints
    const nodeR = 2.5 + val * 4;
    ctx.fillStyle = `rgba(${pri.join(',')}, ${0.5 + val * 0.5})`;
    ctx.beginPath();
    ctx.arc(x1, y, nodeR, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = `rgba(${sec.join(',')}, ${0.5 + val * 0.5})`;
    ctx.beginPath();
    ctx.arc(x2, y, nodeR, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1.0;

  // Draw Strand A (primary helix)
  drawHelixStrand(ctx, cx, startY, helixLength, segments, helixRadius, helixTime, 0, bars, count, bass, pri, pal);
  // Draw Strand B (secondary helix — 180° offset)
  drawHelixStrand(ctx, cx, startY, helixLength, segments, helixRadius, helixTime, Math.PI, bars, count, bass, sec, pal);

  // ── 3. Floating Phosphor Particles ──
  for (let i = 0; i < 40; i++) {
    const pt = (i / 40 + helixTime * 0.05) % 1;
    const py = startY + pt * helixLength;
    const barIdx = Math.floor(pt * count);
    const val = bars[barIdx] || 0;
    const angle = pt * Math.PI * twistSpeed + helixTime;
    const spread = helixRadius * 2.5 + val * helixRadius;
    const px = cx + Math.sin(angle + i * 0.5) * spread * (0.3 + Math.random() * 0.7);

    const pAlpha = 0.1 + val * 0.5 + bass * 0.2;
    const pSize = 1 + val * 3;
    const colorT = i / 40;
    const pr = Math.floor(pri[0] * (1 - colorT) + acc[0] * colorT);
    const pg = Math.floor(pri[1] * (1 - colorT) + acc[1] * colorT);
    const pb = Math.floor(pri[2] * (1 - colorT) + acc[2] * colorT);

    ctx.beginPath();
    ctx.arc(px, py, pSize, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${pr}, ${pg}, ${pb}, ${pAlpha})`;
    ctx.shadowColor = `rgba(${pr}, ${pg}, ${pb}, 0.7)`;
    ctx.shadowBlur = 8 + val * 10;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ── 4. Center Energy Core ──
  const coreR = 15 + bass * 25;
  const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
  coreGrad.addColorStop(0, `rgba(255, 255, 255, ${0.6 + bass * 0.4})`);
  coreGrad.addColorStop(0.3, `rgba(${pri.join(',')}, ${0.4 + bass * 0.3})`);
  coreGrad.addColorStop(0.7, `rgba(${sec.join(',')}, 0.15)`);
  coreGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = coreGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
  ctx.fill();

  // ── 5. Title ──
  if (state.showTitles !== false) {
    ctx.textAlign = 'center';
    ctx.font = `700 ${Math.max(14, Math.floor(w * 0.016))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 10 + bass * 8;
    ctx.fillText(state.songTitle || 'DNA HELIX', cx, h * 0.93);
    ctx.shadowBlur = 0;
    ctx.font = `600 ${Math.max(10, Math.floor(w * 0.010))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
    ctx.fillStyle = `rgba(${pri.join(',')}, 0.85)`;
    ctx.fillText(state.artistName || 'VIDA Studio', cx, h * 0.96);
  }

  ctx.restore();
}

function drawHelixStrand(ctx, cx, startY, length, segments, radius, time, phaseOffset, bars, barCount, bass, color, pal) {
  const twistSpeed = 3.5;

  ctx.beginPath();
  let firstPoint = true;

  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const y = startY + t * length;
    const barIdx = Math.floor(t * barCount);
    const val = bars[barIdx] || 0;

    const angle = t * Math.PI * twistSpeed + time + phaseOffset;
    const dynamicR = radius + val * radius * 1.5 + bass * radius * 0.3;
    const x = cx + Math.sin(angle) * dynamicR;

    // Depth-based line width variation
    const depth = (Math.cos(angle) + 1) / 2;

    if (firstPoint) {
      ctx.moveTo(x, y);
      firstPoint = false;
    } else {
      ctx.lineTo(x, y);
    }
  }

  ctx.strokeStyle = `rgb(${color.join(',')})`;
  ctx.lineWidth = 3 + bass * 2;
  ctx.shadowColor = `rgba(${color.join(',')}, 0.7)`;
  ctx.shadowBlur = 15 + bass * 15;
  ctx.stroke();
  ctx.shadowBlur = 0;
}
