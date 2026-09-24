/**
 * VIDA 2029 Cyber-Angkor Sacred Geometric Mandala Theme
 * 3D Concentric Lotus Gears • Ancient Khmer Laser Filigree • Sacred Harmonic Rays
 */
import { state, PALETTES } from '../core/state.js';

let mandalaRotation = 0;
const KHMER_RUNES = ["ក", "ខ", "គ", "ឃ", "ង", "ច", "ឆ", "ជ", "ឈ", "ញ", "ដ", "ឋ", "ឌ", "ឍ", "ណ", "ត", "ថ", "ទ", "ធ", "ន", "ប", "ផ", "ព", "ភ", "ម", "យ", "រ", "ល", "វ", "ស", "ហ", "ឡ", "អ"];

export function drawAngkorMandala(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette] || PALETTES.angkor;
  const priRgb = pal.primary.join(',');
  const secRgb = pal.secondary.join(',');
  const accRgb = (pal.accent || [217, 119, 6]).join(',');

  const cx = w / 2;
  const cy = h / 2;
  const baseRadius = Math.min(w, h) * 0.12;

  ctx.save();
  mandalaRotation += 0.008 + bass * 0.02;

  // 1. Outer Sacred Laser Radiance Rays (Harmonic Frequencies)
  const numRays = 48;
  for (let i = 0; i < numRays; i++) {
    const angle = (i * (Math.PI * 2 / numRays)) + mandalaRotation * 0.5;
    const barIdx = Math.floor((i / numRays) * bars.length);
    const barAmp = bars[barIdx] || 0;

    const innerR = baseRadius * 1.8 + bass * 20;
    const outerR = innerR + 60 + barAmp * 240;

    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
    ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
    
    ctx.strokeStyle = i % 2 === 0 ? `rgba(${priRgb}, ${0.5 + barAmp * 0.5})` : `rgba(${secRgb}, ${0.4 + barAmp * 0.4})`;
    ctx.lineWidth = 1.8 + barAmp * 3;
    ctx.stroke();

    // Floating Khmer Sacred Rune on Outer Tip
    if (i % 3 === 0 && barAmp > 0.25) {
      const runeX = cx + Math.cos(angle) * (outerR + 24);
      const runeY = cy + Math.sin(angle) * (outerR + 24);
      ctx.fillStyle = `rgba(${secRgb}, ${Math.min(1, barAmp * 1.5)})`;
      ctx.font = `600 13px 'Kantumruy Pro', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(KHMER_RUNES[i % KHMER_RUNES.length], runeX, runeY);
    }
  }

  // 2. Interlocking Angkor Lotus Petal Gears (Opposing Rotations)
  const gearTiers = [
    { petals: 12, radius: baseRadius * 1.6, speed: -1, width: 2 },
    { petals: 16, radius: baseRadius * 1.3, speed: 1.4, width: 2.5 },
    { petals: 8,  radius: baseRadius * 1.05, speed: -1.8, width: 3 }
  ];

  for (let g of gearTiers) {
    const gearAngle = mandalaRotation * g.speed;
    ctx.beginPath();

    for (let p = 0; p < g.petals; p++) {
      const petalAngle = (p * (Math.PI * 2 / g.petals)) + gearAngle;
      const petalAmp = (bars[p % bars.length] || 0) * 35;
      const rOuter = g.radius + 18 + petalAmp + (bass * 15);
      const rInner = g.radius - 8;

      const px1 = cx + Math.cos(petalAngle - 0.15) * rInner;
      const py1 = cy + Math.sin(petalAngle - 0.15) * rInner;
      const pxTip = cx + Math.cos(petalAngle) * rOuter;
      const pyTip = cy + Math.sin(petalAngle) * rOuter;
      const px2 = cx + Math.cos(petalAngle + 0.15) * rInner;
      const py2 = cy + Math.sin(petalAngle + 0.15) * rInner;

      if (p === 0) ctx.moveTo(px1, py1);
      else ctx.lineTo(px1, py1);
      ctx.quadraticCurveTo(pxTip, pyTip, px2, py2);
    }

    ctx.closePath();
    ctx.strokeStyle = `rgba(${priRgb}, ${0.75 + bass * 0.25})`;
    ctx.lineWidth = g.width + bass * 1.5;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 14;
    ctx.stroke();
  }
  ctx.shadowBlur = 0;

  // 3. Sacred Center Emblem & Royal Halo
  const emblemRadius = baseRadius * (1 + bass * 0.25);
  ctx.beginPath();
  ctx.arc(cx, cy, emblemRadius, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(18, 14, 8, 0.9)";
  ctx.fill();

  ctx.strokeStyle = `rgb(${priRgb})`;
  ctx.lineWidth = 3 + bass * 3;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 24;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Center Logo or Royal Angkorian Typography
  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, emblemRadius * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(state.logoImageObj, cx - emblemRadius, cy - emblemRadius, emblemRadius * 2, emblemRadius * 2);
    ctx.restore();
  } else if (state.showCenterText !== false) {
    const center1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : "អង្គរ";
    const center2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "SACRED MANDALA";

    if (center1 && center1.trim()) {
      const len1 = Math.max(center1.length, 4);
      const baseFs1 = Math.floor(emblemRadius * 0.42);
      const fs1 = len1 > 6 ? Math.max(11, Math.floor(baseFs1 * (6 / len1))) : baseFs1;
      ctx.fillStyle = "#fef08a";
      ctx.font = `700 ${fs1}px 'Kantumruy Pro', 'Noto Sans SC', 'Noto Sans JP', 'Noto Sans KR', 'Noto Sans Thai', 'Outfit', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center1, cx, center2 && center2.trim() ? cy - emblemRadius * 0.15 : cy);
    }

    if (center2 && center2.trim()) {
      const len2 = Math.max(center2.length, 6);
      const baseFs2 = Math.floor(emblemRadius * 0.2);
      const fs2 = len2 > 10 ? Math.max(9, Math.floor(baseFs2 * (10 / len2))) : baseFs2;
      ctx.font = `600 ${fs2}px 'Kantumruy Pro', 'Noto Sans SC', 'Noto Sans JP', 'Noto Sans KR', 'Noto Sans Thai', 'Outfit', sans-serif`;
      ctx.fillStyle = `rgb(${secRgb})`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(center2, cx, center1 && center1.trim() ? cy + emblemRadius * 0.24 : cy);
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
      ctx.fillStyle = "#fef3c7";
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 10 + bass * 8;
      ctx.fillText(displayTitle, cx, h * 0.10);
      ctx.shadowBlur = 0;
    }

    if (displayArtist && displayArtist.trim()) {
      ctx.font = `600 ${Math.max(10, Math.min(13, Math.floor(w * 0.010)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = "#fde68a";
      ctx.fillText(displayArtist, cx, h * 0.10 + 20);
    }
  }

  ctx.restore();
}
