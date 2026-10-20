/**
 * VIDA 2027 Neural AI Synapse Matrix Theme
 * 3D Neural Constellation • Electrical Lightning Synapses • Tensor Harmonic Graph
 */
import { state, PALETTES } from '../core/state.js';
import { glowLayer } from './glow.js';

const NUM_NODES = 48;
const nodes = [];

for (let i = 0; i < NUM_NODES; i++) {
  nodes.push({
    x: Math.random() * 1920,
    y: Math.random() * 1080,
    vx: (Math.random() - 0.5) * 1.2,
    vy: (Math.random() - 0.5) * 1.2,
    baseR: Math.random() * 4 + 2,
    harmonicBin: Math.floor(Math.random() * 64),
    energy: 0,
    connections: []
  });
}

export function drawNeuralSynapse(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette] || PALETTES.cyberpunk;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');
  const accRgb = (pal.accent || [130, 80, 255]).join(',');

  const cx = w / 2;
  const cy = h / 2;
  const coreRadius = Math.min(w, h) * 0.1;

  ctx.save();

  // 1. Update nodes and build a display list. Every draw in this loop used to
  // run with the node's shadow active (one full-res blur per node AND per
  // synapse line); the glow is now rendered once per blur size in glow.js.
  const ops = [];
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    const barVal = bars[node.harmonicBin % bars.length] || 0;
    
    // Physics update with acoustic excitation
    node.x += node.vx * (1 + bass * 2);
    node.y += node.vy * (1 + bass * 2);

    // Bounce off edges with soft margins
    if (node.x < 50 || node.x > w - 50) node.vx *= -1;
    if (node.y < 50 || node.y > h - 50) node.vy *= -1;

    // Decay or boost excitation
    node.energy = node.energy * 0.85 + barVal * 0.45;
    const blur = node.energy > 0.4 ? 18 : 6;

    // Node Body
    const currentR = node.baseR * (1 + node.energy * 3 + bass * 1.5);
    const hot = node.energy > 0.4;
    ops.push({ blur, fill: true, style: hot ? `rgb(${secRgb})` : `rgba(${priRgb}, 0.8)`, alpha: hot ? 1 : 0.8,
      x: node.x, y: node.y, r: currentR });

    // 2. Connect nearby nodes with Electrical Synapse Arcs
    for (let j = i + 1; j < nodes.length; j++) {
      const target = nodes[j];
      const dx = target.x - node.x;
      const dy = target.y - node.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      const maxConnectDist = 180 + bass * 80;
      if (dist < maxConnectDist) {
        const proximity = 1 - (dist / maxConnectDist);
        const synapsePower = (node.energy + target.energy) * 0.5;

        if (synapsePower > 0.35) {
          // Electric Lightning Jitter Arc
          const midX = (node.x + target.x) / 2 + (Math.random() - 0.5) * 16 * synapsePower;
          const midY = (node.y + target.y) / 2 + (Math.random() - 0.5) * 16 * synapsePower;
          const a = proximity * (0.6 + synapsePower * 0.4);
          ops.push({ blur, pts: [node.x, node.y, midX, midY, target.x, target.y],
            style: `rgba(${secRgb}, ${a})`, alpha: a, lw: 1.8 + synapsePower * 2 });
        } else {
          // Smooth Synaptic Filament
          const a = proximity * 0.35;
          ops.push({ blur, pts: [node.x, node.y, target.x, target.y],
            style: `rgba(${priRgb}, ${a})`, alpha: a, lw: 1.2 });
        }
      }
    }

    // Connect node to center Neural Core if close enough
    const distToCenter = Math.sqrt((cx - node.x) ** 2 + (cy - node.y) ** 2);
    if (distToCenter < 350 + bass * 100) {
      const a = (1 - distToCenter / 450) * 0.25;
      ops.push({ blur, pts: [node.x, node.y, cx, cy], style: `rgba(${accRgb}, ${a})`, alpha: a, lw: 0.8 });
    }
  }

  const trace = (p, op) => {
    p.beginPath();
    if (op.fill) { p.arc(op.x, op.y, op.r, 0, Math.PI * 2); return; }
    const q = op.pts;
    p.moveTo(q[0], q[1]);
    for (let k = 2; k < q.length; k += 2) p.lineTo(q[k], q[k + 1]);
  };
  for (const blur of [6, 18]) {
    glowLayer(ctx, blur, (g) => {
      g.fillStyle = g.strokeStyle = pal.glow;
      for (const op of ops) {
        if (op.blur !== blur || op.alpha <= 0) continue;
        g.globalAlpha = Math.min(1, op.alpha);
        trace(g, op);
        if (op.fill) g.fill(); else { g.lineWidth = op.lw; g.stroke(); }
      }
    });
  }
  ctx.shadowBlur = 0;
  for (const op of ops) {
    trace(ctx, op);
    if (op.fill) { ctx.fillStyle = op.style; ctx.fill(); }
    else { ctx.strokeStyle = op.style; ctx.lineWidth = op.lw; ctx.stroke(); }
  }
  ctx.shadowBlur = 0;

  // 3. Center Neural Processing Core
  const pulseRadius = coreRadius * (1 + bass * 0.35);
  ctx.beginPath();
  ctx.arc(cx, cy, pulseRadius, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(10, 15, 28, 0.85)";
  ctx.fill();

  // Multi-tier digital hexagon / ring border
  ctx.lineWidth = 2.5 + bass * 2;
  glowLayer(ctx, 20, (g) => {
    g.strokeStyle = pal.glow;
    g.beginPath(); g.arc(cx, cy, pulseRadius, 0, Math.PI * 2); g.stroke();
  });
  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.beginPath();
  ctx.arc(cx, cy, pulseRadius, 0, Math.PI * 2);
  ctx.stroke();

  // Center Logo or Neural Typography
  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, pulseRadius * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - pulseRadius, cy - pulseRadius, pulseRadius * 2, pulseRadius * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : "SYNAPSE";
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "NEURAL MATRIX";

    if (center1 && center1.trim()) {
      const len1 = Math.max(center1.length, 4);
      const baseFs1 = Math.floor(pulseRadius * 0.36);
      const fs1 = len1 > 7 ? Math.max(11, Math.floor(baseFs1 * (7 / len1))) : baseFs1;
      ctx.fillStyle = `rgb(${priRgb})`;
      ctx.font = `800 ${Math.floor((Math.floor((Math.floor((fs1) * (state.titleScale || 1.5))) * (state.titleScale || 1.5))) * (state.titleScale || 1.5))}px 'Kantumruy Pro', 'Noto Sans SC', 'Noto Sans JP', 'Noto Sans KR', 'Noto Sans Thai', 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - pulseRadius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      const len2 = Math.max(center2.length, 6);
      const baseFs2 = Math.floor(pulseRadius * 0.2);
      const fs2 = len2 > 10 ? Math.max(9, Math.floor(baseFs2 * (10 / len2))) : baseFs2;
      ctx.font = `600 ${Math.floor((Math.floor((Math.floor((fs2) * (state.titleScale || 1.5))) * (state.titleScale || 1.5))) * (state.titleScale || 1.5))}px 'Kantumruy Pro', 'Noto Sans SC', 'Noto Sans JP', 'Noto Sans KR', 'Noto Sans Thai', 'Outfit', sans-serif`;
      ctx.fillStyle = `rgba(${secRgb}, 0.9)`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center2, cx, center1 && center1.trim() ? cy + pulseRadius * 0.24 : cy);
    }
  }


  ctx.restore();
}
