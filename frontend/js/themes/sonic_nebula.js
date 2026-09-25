/**
 * VIDA 2026 — Sonic Nebula Galaxy Theme
 * Galactic nebula clouds with spiral arms that react to audio.
 * Stellar explosions on bass hits, cosmic dust particles, and gravitational audio field.
 */
import { state, PALETTES } from '../core/state.js';

let nebulaTime = 0;
let prevBass = 0;

// Nebula cloud points
const nebulaPoints = [];
for (let i = 0; i < 200; i++) {
  const angle = Math.random() * Math.PI * 2;
  const dist = Math.random() * 0.4 + 0.05;
  nebulaPoints.push({
    angle,
    dist,
    baseSize: Math.random() * 40 + 10,
    speed: (Math.random() - 0.5) * 0.003,
    colorMix: Math.random(),
    opacity: Math.random() * 0.3 + 0.05,
    layer: Math.floor(Math.random() * 3)
  });
}

// Stellar explosion particles
const explosions = [];

export function drawSonicNebula(ctx, w, h, bars, bass) {
  nebulaTime += 0.012;
  const pal = PALETTES[state.palette] || PALETTES.bloodmoon;
  const pri = pal.primary;
  const sec = pal.secondary;
  const acc = pal.accent || [130, 80, 255];
  const count = bars.length;
  const cx = w / 2;
  const cy = h / 2;
  const maxR = Math.min(w, h) * 0.45;

  ctx.save();

  // ── 1. Bass-triggered stellar explosions ──
  if (bass > 0.6 && bass > prevBass + 0.1) {
    for (let i = 0; i < 12; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 6;
      explosions.push({
        x: cx + (Math.random() - 0.5) * maxR * 0.3,
        y: cy + (Math.random() - 0.5) * maxR * 0.3,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 1.0,
        size: 2 + Math.random() * 4,
        color: Math.random() > 0.5 ? pri : sec
      });
    }
  }
  prevBass = bass;

  // Update & render explosions
  for (let i = explosions.length - 1; i >= 0; i--) {
    const e = explosions[i];
    e.x += e.vx;
    e.y += e.vy;
    e.vx *= 0.97;
    e.vy *= 0.97;
    e.life -= 0.02;

    if (e.life <= 0) {
      explosions.splice(i, 1);
      continue;
    }

    ctx.beginPath();
    ctx.arc(e.x, e.y, e.size * e.life, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${e.color.join(',')}, ${e.life * 0.8})`;
    ctx.shadowColor = `rgba(${e.color.join(',')}, ${e.life})`;
    ctx.shadowBlur = 10 + e.life * 15;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ── 2. Nebula Cloud Layers ──
  for (let layer = 0; layer < 3; layer++) {
    for (const p of nebulaPoints) {
      if (p.layer !== layer) continue;

      p.angle += p.speed + bass * 0.005;
      const barIdx = Math.floor(((p.angle / (Math.PI * 2)) % 1) * count);
      const val = bars[Math.abs(barIdx) % count] || 0;

      const dynamicDist = p.dist + val * 0.15 + bass * 0.05;
      const x = cx + Math.cos(p.angle + nebulaTime * (0.3 + layer * 0.1)) * dynamicDist * maxR;
      const y = cy + Math.sin(p.angle + nebulaTime * (0.3 + layer * 0.1)) * dynamicDist * maxR * 0.7;
      const size = p.baseSize + val * 30 + bass * 15;

      // Mix colors based on position
      const cr = Math.floor(pri[0] * (1 - p.colorMix) + sec[0] * p.colorMix);
      const cg = Math.floor(pri[1] * (1 - p.colorMix) + sec[1] * p.colorMix);
      const cb = Math.floor(pri[2] * (1 - p.colorMix) + sec[2] * p.colorMix);

      const grad = ctx.createRadialGradient(x, y, 0, x, y, size);
      const alpha = p.opacity + val * 0.15 + bass * 0.08;
      grad.addColorStop(0, `rgba(${cr}, ${cg}, ${cb}, ${Math.min(0.5, alpha * 1.5)})`);
      grad.addColorStop(0.5, `rgba(${cr}, ${cg}, ${cb}, ${alpha * 0.5})`);
      grad.addColorStop(1, 'rgba(0, 0, 0, 0)');

      ctx.fillStyle = grad;
      ctx.fillRect(x - size, y - size, size * 2, size * 2);
    }
  }

  // ── 3. Spiral Arm Frequency Lines ──
  const armCount = 3;
  for (let arm = 0; arm < armCount; arm++) {
    ctx.beginPath();
    const armOffset = (arm / armCount) * Math.PI * 2;

    for (let i = 0; i < 80; i++) {
      const t = i / 80;
      const spiralAngle = armOffset + t * Math.PI * 2.5 + nebulaTime * 0.5;
      const barIdx = Math.floor(t * count);
      const val = bars[barIdx] || 0;
      const spiralR = t * maxR * 0.85 + val * maxR * 0.2;

      const x = cx + Math.cos(spiralAngle) * spiralR;
      const y = cy + Math.sin(spiralAngle) * spiralR * 0.65;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    const armColor = arm === 0 ? pri : arm === 1 ? sec : acc;
    ctx.strokeStyle = `rgba(${armColor.join(',')}, ${0.2 + bass * 0.3})`;
    ctx.lineWidth = 1.5 + bass * 2;
    ctx.shadowColor = `rgba(${armColor.join(',')}, 0.5)`;
    ctx.shadowBlur = 8 + bass * 12;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // ── 4. Central Black Hole / Core ──
  const coreR = 20 + bass * 35;
  // Dark core
  const darkGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
  darkGrad.addColorStop(0, 'rgba(0, 0, 0, 0.9)');
  darkGrad.addColorStop(0.6, 'rgba(0, 0, 0, 0.4)');
  darkGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = darkGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
  ctx.fill();

  // Accretion disk glow ring
  ctx.beginPath();
  ctx.arc(cx, cy, coreR + 3, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(${pri.join(',')}, ${0.5 + bass * 0.5})`;
  ctx.lineWidth = 2 + bass * 3;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 20 + bass * 25;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Inner white-hot ring
  ctx.beginPath();
  ctx.arc(cx, cy, coreR * 0.7, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(255, 255, 255, ${0.3 + bass * 0.5})`;
  ctx.lineWidth = 1;
  ctx.shadowColor = '#ffffff';
  ctx.shadowBlur = 10;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // ── 5. Cosmic Dust Stars ──
  for (let i = 0; i < 50; i++) {
    const sx = (Math.sin(i * 173.1 + nebulaTime * 0.15) * 0.5 + 0.5) * w;
    const sy = (Math.cos(i * 257.7 + nebulaTime * 0.08) * 0.5 + 0.5) * h;
    const twinkle = Math.sin(nebulaTime * 3 + i * 2.1) * 0.5 + 0.5;
    ctx.fillStyle = `rgba(255, 255, 255, ${0.1 + twinkle * 0.4})`;
    ctx.beginPath();
    ctx.arc(sx, sy, 0.5 + twinkle * 1.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // ── 6. Title ──
  if (state.showTitles !== false) {
    ctx.textAlign = 'center';
    ctx.font = `700 ${Math.max(14, Math.floor(w * 0.018))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 12 + bass * 10;
    ctx.fillText(state.songTitle || 'NEBULA', cx, h * 0.92);
    ctx.shadowBlur = 0;
    ctx.font = `600 ${Math.max(10, Math.floor(w * 0.011))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
    ctx.fillStyle = `rgba(${pri.join(',')}, 0.85)`;
    ctx.fillText(state.artistName || 'VIDA Studio', cx, h * 0.955);
  }

  ctx.restore();
}
