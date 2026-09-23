/**
 * VIDA 2027 Neural AI Synapse Matrix Theme
 * 3D Neural Constellation • Electrical Lightning Synapses • Tensor Harmonic Graph
 */
import { state, PALETTES } from '../core/state.js';

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

  // 1. Update and Draw Interconnected Neural Nodes
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

    // Draw Node Body
    const currentR = node.baseR * (1 + node.energy * 3 + bass * 1.5);
    ctx.beginPath();
    ctx.arc(node.x, node.y, currentR, 0, Math.PI * 2);
    ctx.fillStyle = node.energy > 0.4 ? `rgb(${secRgb})` : `rgba(${priRgb}, 0.8)`;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = node.energy > 0.4 ? 18 : 6;
    ctx.fill();

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

        ctx.beginPath();
        if (synapsePower > 0.35) {
          // Electric Lightning Jitter Arc
          ctx.moveTo(node.x, node.y);
          const midX = (node.x + target.x) / 2 + (Math.random() - 0.5) * 16 * synapsePower;
          const midY = (node.y + target.y) / 2 + (Math.random() - 0.5) * 16 * synapsePower;
          ctx.lineTo(midX, midY);
          ctx.lineTo(target.x, target.y);
          ctx.strokeStyle = `rgba(${secRgb}, ${proximity * (0.6 + synapsePower * 0.4)})`;
          ctx.lineWidth = 1.8 + synapsePower * 2;
        } else {
          // Smooth Synaptic Filament
          ctx.moveTo(node.x, node.y);
          ctx.lineTo(target.x, target.y);
          ctx.strokeStyle = `rgba(${priRgb}, ${proximity * 0.35})`;
          ctx.lineWidth = 1.2;
        }
        ctx.stroke();
      }
    }

    // Connect node to center Neural Core if close enough
    const distToCenter = Math.sqrt((cx - node.x) ** 2 + (cy - node.y) ** 2);
    if (distToCenter < 350 + bass * 100) {
      ctx.beginPath();
      ctx.moveTo(node.x, node.y);
      ctx.lineTo(cx, cy);
      ctx.strokeStyle = `rgba(${accRgb}, ${(1 - distToCenter / 450) * 0.25})`;
      ctx.lineWidth = 0.8;
      ctx.stroke();
    }
  }
  ctx.shadowBlur = 0;

  // 3. Center Neural Processing Core
  const pulseRadius = coreRadius * (1 + bass * 0.35);
  ctx.beginPath();
  ctx.arc(cx, cy, pulseRadius, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(10, 15, 28, 0.85)";
  ctx.fill();

  // Multi-tier digital hexagon / ring border
  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 2.5 + bass * 2;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 20;
  ctx.stroke();
  ctx.shadowBlur = 0;

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
      ctx.fillStyle = `rgb(${priRgb})`;
      ctx.font = `800 ${Math.floor(pulseRadius * 0.36)}px 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - pulseRadius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      ctx.font = `600 ${Math.floor(pulseRadius * 0.2)}px 'JetBrains Mono', sans-serif`;
      ctx.fillStyle = `rgba(${secRgb}, 0.9)`;
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
