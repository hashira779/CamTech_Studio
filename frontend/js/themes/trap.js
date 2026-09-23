import { state, PALETTES } from '../core/state.js';

export function drawTrapCircle(ctx, w, h, bars, bass) {
  const pal = PALETTES[state.palette];
  let cx = w / 2;
  let cy = h / 2;

  // Bass camera shake
  if (bass > 0.65) {
    cx += (Math.random() - 0.5) * 8 * bass;
    cy += (Math.random() - 0.5) * 8 * bass;
  }

  const baseRadius = Math.min(w, h) * 0.17;
  const dynamicRadius = baseRadius + bass * (baseRadius * 0.32);
  const maxBarLength = Math.min(w, h) * 0.24;

  const mirrored = [];
  for (let i = 0; i < bars.length; i++) mirrored.push(bars[i]);
  for (let i = bars.length - 1; i >= 0; i--) mirrored.push(bars[i]);

  const total = mirrored.length;
  ctx.lineWidth = 3.5;
  ctx.lineCap = "round";

  const outerTips = [];
  // Outer radial bars
  for (let i = 0; i < total; i++) {
    const angle = (i / total) * Math.PI * 2 - Math.PI / 2;
    const len = Math.max(4, mirrored[i] * maxBarLength);

    const x1 = cx + Math.cos(angle) * dynamicRadius;
    const y1 = cy + Math.sin(angle) * dynamicRadius;
    const x2 = cx + Math.cos(angle) * (dynamicRadius + len);
    const y2 = cy + Math.sin(angle) * (dynamicRadius + len);
    outerTips.push({ x: x2, y: y2 });

    const t = i / total;
    const r = Math.floor(pal.primary[0] * (1 - t) + pal.secondary[0] * t);
    const g = Math.floor(pal.primary[1] * (1 - t) + pal.secondary[1] * t);
    const b = Math.floor(pal.primary[2] * (1 - t) + pal.secondary[2] * t);

    ctx.strokeStyle = `rgb(${r}, ${g}, ${b})`;
    ctx.shadowColor = `rgba(${r}, ${g}, ${b}, 0.65)`;
    ctx.shadowBlur = 12;

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  // Smooth Outer Aura Spline linking bar tips
  if (outerTips.length > 4) {
    ctx.strokeStyle = `rgba(${pal.primary[0]}, ${pal.primary[1]}, ${pal.primary[2]}, 0.55)`;
    ctx.lineWidth = 2.0;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 16;
    ctx.beginPath();
    ctx.moveTo((outerTips[0].x + outerTips[total - 1].x) / 2, (outerTips[0].y + outerTips[total - 1].y) / 2);
    for (let i = 0; i < total; i++) {
      const next = (i + 1) % total;
      const xc = (outerTips[i].x + outerTips[next].x) / 2;
      const yc = (outerTips[i].y + outerTips[next].y) / 2;
      ctx.quadraticCurveTo(outerTips[i].x, outerTips[i].y, xc, yc);
    }
    ctx.stroke();
  }
  ctx.shadowBlur = 0;

  // Center Album Disc
  drawCenterDisc(ctx, cx, cy, dynamicRadius, bass, pal);
}

// Authentic 33 RPM Rotating Vinyl Record Disc Helper
let vinylRotation = 0;

function drawCenterDisc(ctx, cx, cy, radius, bass, pal) {
  if (state.isPlaying) {
    vinylRotation += 0.006 + bass * 0.008;
  }

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(vinylRotation);

  // 1. Black Vinyl Disc Base with realistic texture gradient
  const vGrad = ctx.createRadialGradient(0, 0, radius * 0.35, 0, 0, radius);
  vGrad.addColorStop(0, "#161616");
  vGrad.addColorStop(0.6, "#0a0a0a");
  vGrad.addColorStop(1, "#030303");
  ctx.fillStyle = vGrad;
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.fill();

  // 2. Realistic concentric audio grooves (etched record tracks)
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
  ctx.lineWidth = 1;
  const numGrooves = 8;
  for (let g = 1; g <= numGrooves; g++) {
    const rG = radius * (0.52 + (g / (numGrooves + 1)) * 0.44);
    ctx.beginPath();
    ctx.arc(0, 0, rG, 0, Math.PI * 2);
    ctx.stroke();
  }

  // 3. Specular reflection highlight sheen (dual reflective light cone)
  const sheenGrad = ctx.createRadialGradient(0, 0, radius * 0.2, 0, 0, radius);
  sheenGrad.addColorStop(0, "rgba(255, 255, 255, 0.09)");
  sheenGrad.addColorStop(0.8, "rgba(255, 255, 255, 0.03)");
  sheenGrad.addColorStop(1, "transparent");
  ctx.fillStyle = sheenGrad;

  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, radius, -Math.PI / 5, Math.PI / 5);
  ctx.closePath();
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, radius, Math.PI * 4 / 5, Math.PI * 6 / 5);
  ctx.closePath();
  ctx.fill();

  // 4. Center Record Label (52% radius)
  const labelRadius = radius * 0.52;
  ctx.save();
  ctx.beginPath();
  ctx.arc(0, 0, labelRadius, 0, Math.PI * 2);
  ctx.clip();

  if (state.logoImageObj && state.logoImageObj.complete) {
    ctx.drawImage(state.logoImageObj, -labelRadius, -labelRadius, labelRadius * 2, labelRadius * 2);
  } else {
    // Authentic Cambodian Record Label
    const isVintage = state.palette === "vintage_vinyl" || state.palette === "candlelight" || state.palette === "angkor" || state.palette === "chapei_wood";
    const labelGrad = ctx.createRadialGradient(0, 0, labelRadius * 0.15, 0, 0, labelRadius);
    if (isVintage) {
      labelGrad.addColorStop(0, "#d97706");
      labelGrad.addColorStop(0.65, "#78350f");
      labelGrad.addColorStop(1, "#451a03");
    } else {
      labelGrad.addColorStop(0, "#1e293b");
      labelGrad.addColorStop(0.65, "#0f172a");
      labelGrad.addColorStop(1, "#020617");
    }
    ctx.fillStyle = labelGrad;
    ctx.fill();

    // Vintage Decorative Concentric Ring
    ctx.strokeStyle = isVintage ? "rgba(251, 191, 36, 0.65)" : `rgba(${pal.primary.join(",")}, 0.5)`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(0, 0, labelRadius * 0.86, 0, Math.PI * 2);
    ctx.stroke();

    // Vintage inner ring
    if (isVintage) {
      ctx.strokeStyle = "rgba(253, 230, 138, 0.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(0, 0, labelRadius * 0.70, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (state.showCenterText !== false) {
      // Artist Name (top text)
      let displayArtist = state.artistName !== undefined ? state.artistName : (isVintage ? "ស៊ីន ស៊ីសាមុត" : "VIDA AUDIO");
      if (displayArtist && displayArtist.trim()) {
        if (displayArtist.length > 20) {
          displayArtist = displayArtist.split("(")[0].trim();
        }
        ctx.fillStyle = isVintage ? "#fef3c7" : `rgb(${pal.primary.join(",")})`;
        const artistFontSize = Math.max(10, Math.min(Math.floor(labelRadius * 0.20), Math.floor((labelRadius * 1.5) / Math.max(displayArtist.length, 6))));
        ctx.font = `700 ${artistFontSize}px 'Kantumruy Pro', 'Outfit', sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(displayArtist, 0, -labelRadius * 0.35);
      }

      // Vintage Stereo Sub-badge (center text secondary)
      const subBadge = state.centerTextSecondary !== undefined ? state.centerTextSecondary : "33⅓ RPM STEREO";
      if (subBadge && subBadge.trim()) {
        ctx.font = `600 ${Math.max(9, Math.floor(labelRadius * 0.12))}px 'Outfit', sans-serif`;
        ctx.fillStyle = isVintage ? "#fde68a" : "#94a3b8";
        ctx.textAlign = "center";
        ctx.fillText(subBadge, 0, -labelRadius * 0.12);
      }

      // Song Title (bottom text)
      let displayTitle = state.songTitle !== undefined ? state.songTitle : (isVintage ? "ចំប៉ាបាត់ដំបង" : "SYNTH ENGINE");
      if (displayTitle && displayTitle.trim()) {
        if (displayTitle.length > 22) {
          displayTitle = displayTitle.split("(")[0].trim();
        }
        ctx.fillStyle = isVintage ? "#fef08a" : "#cbd5e1";
        const titleFontSize = Math.max(9, Math.min(Math.floor(labelRadius * 0.17), Math.floor((labelRadius * 1.5) / Math.max(displayTitle.length, 6))));
        ctx.font = `600 ${titleFontSize}px 'Kantumruy Pro', 'Outfit', sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(displayTitle, 0, labelRadius * 0.32);
      }
    }
  }

  // 5. Center Spindle Hole (metallic brass ring)
  ctx.restore();
  ctx.beginPath();
  ctx.arc(0, 0, labelRadius * 0.13, 0, Math.PI * 2);
  ctx.fillStyle = "#050505";
  ctx.fill();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.restore();

  // 6. Audio-Reactive Glowing Outer Rim
  ctx.strokeStyle = `rgb(${pal.primary.join(",")})`;
  ctx.lineWidth = 3.5 + bass * 2.5;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 18;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;
}
