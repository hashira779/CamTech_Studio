import { state, PALETTES } from '../core/state.js';

let peakHold = new Float32Array(256);
let peakHoldDecay = new Float32Array(256);
let animTime = 0;

export function drawSpectrumAnalyzer(ctx, w, h, bars, bass) {
  animTime += 0.025;
  const pal = PALETTES[state.palette] || PALETTES.vintage_vinyl;
  const count = bars.length;
  const isVintage = state.palette === "vintage_vinyl" || state.palette === "candlelight" || state.palette === "angkor" || state.palette === "chapei_wood" || state.palette === "romduol";

  // Calculate dynamic responsive frame layout
  const marginX = Math.max(28, w * 0.05);
  const marginTop = Math.max(50, h * 0.12);
  const marginBottom = Math.max(60, h * 0.16);
  const availableW = w - marginX * 2;
  const availableH = h - marginTop - marginBottom;
  const baseY = h - marginBottom;

  ctx.save();

  // ── 1. Studio Ambient Radial Aura & Acoustic Vignette ──
  const bgGrad = ctx.createRadialGradient(w / 2, baseY - availableH * 0.45, availableW * 0.05, w / 2, baseY - availableH * 0.4, availableW * 0.75);
  const primaryRgb = pal.primary.join(",");
  const secondaryRgb = pal.secondary.join(",");
  bgGrad.addColorStop(0, `rgba(${primaryRgb}, ${0.12 + bass * 0.15})`);
  bgGrad.addColorStop(0.5, `rgba(${secondaryRgb}, ${0.05 + bass * 0.08})`);
  bgGrad.addColorStop(1, "rgba(5, 7, 12, 0)");
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, w, h);

  // ── 2. Top Mastering Studio HUD & Metadata Header ──
  // Top Left: Analyzer Engine Telemetry
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.font = "700 10px 'Outfit', sans-serif";
  ctx.fillStyle = `rgba(${primaryRgb}, 0.85)`;
  ctx.fillText("ANALOG RTA MASTERING ANALYZER", marginX, 28);

  ctx.font = "500 9px monospace";
  ctx.fillStyle = "rgba(255, 255, 255, 0.45)";
  const fftSpec = `${count}-BAND FFT • 48kHz 24-BIT • SMOOTH ${(state.smoothing || 0.88).toFixed(2)}`;
  ctx.fillText(fftSpec, marginX, 42);

  // Top Center: Artist & Song Title Display
  if (state.showTitles !== false) {
    const centerTitle = state.songTitle !== undefined ? state.songTitle : (isVintage ? "ចំប៉ាបាត់ដំបង" : "AUDIO VISUALIZER");
    let centerArtist = state.artistName !== undefined ? state.artistName : (isVintage ? "ស៊ីន ស៊ីសាមុត (Sinn Sisamouth)" : "MASTER AUDIO");

    ctx.textAlign = "center";

    if (centerTitle && centerTitle.trim()) {
      ctx.font = `700 ${Math.max(14, Math.min(22, Math.floor(w * 0.016)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fef3c7" : "#ffffff";
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 10 + bass * 8;
      ctx.fillText(centerTitle, w / 2, 28);
      ctx.shadowBlur = 0;
    }

    if (centerArtist && centerArtist.trim()) {
      ctx.font = `600 ${Math.max(10, Math.min(13, Math.floor(w * 0.010)))}px 'Kantumruy Pro', 'Outfit', sans-serif`;
      ctx.fillStyle = isVintage ? "#fde68a" : `rgba(${primaryRgb}, 0.9)`;
      ctx.fillText(centerArtist, w / 2, 46);
    }
  }

  // Top Right: Live Stereo VU Peak Meters
  const vuW = 100;
  const vuH = 7;
  const vuX = w - marginX - vuW;
  const vuY = 24;

  // L Channel
  const lLevel = Math.min(1.0, (bars[Math.floor(count * 0.2)] || 0) * 1.35 + bass * 0.35);
  ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
  ctx.fillRect(vuX, vuY, vuW, vuH);
  const vuGradL = ctx.createLinearGradient(vuX, 0, vuX + vuW, 0);
  vuGradL.addColorStop(0, "#10b981");
  vuGradL.addColorStop(0.7, "#fbbf24");
  vuGradL.addColorStop(1, "#ef4444");
  ctx.fillStyle = vuGradL;
  ctx.fillRect(vuX, vuY, vuW * Math.max(0.04, lLevel), vuH);

  ctx.font = "600 8px monospace";
  ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
  ctx.textAlign = "right";
  ctx.fillText(`L ${( -36 + lLevel * 36 ).toFixed(1)} dB`, vuX - 8, vuY + 4);

  // R Channel
  const rLevel = Math.min(1.0, (bars[Math.floor(count * 0.45)] || 0) * 1.35 + bass * 0.3);
  ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
  ctx.fillRect(vuX, vuY + 12, vuW, vuH);
  ctx.fillStyle = vuGradL;
  ctx.fillRect(vuX, vuY + 12, vuW * Math.max(0.04, rLevel), vuH);
  ctx.fillText(`R ${( -36 + rLevel * 36 ).toFixed(1)} dB`, vuX - 8, vuY + 16);

  // ── 3. High-Precision Logarithmic Grid & dB Reference Lines ──
  const dbSteps = [
    { label: "+6 dB", val: 1.0 },
    { label: "0 dB", val: 0.85 },
    { label: "-6 dB", val: 0.70 },
    { label: "-12 dB", val: 0.55 },
    { label: "-24 dB", val: 0.38 },
    { label: "-36 dB", val: 0.22 },
    { label: "-48 dB", val: 0.08 }
  ];

  ctx.lineWidth = 1;
  for (let s of dbSteps) {
    const y = baseY - s.val * availableH;
    ctx.strokeStyle = s.label === "0 dB" ? `rgba(${primaryRgb}, 0.25)` : "rgba(255, 255, 255, 0.045)";
    ctx.setLineDash(s.label === "0 dB" ? [] : [4, 4]);
    ctx.beginPath();
    ctx.moveTo(marginX, y);
    ctx.lineTo(w - marginX, y);
    ctx.stroke();

    ctx.setLineDash([]);
    ctx.fillStyle = s.label === "0 dB" ? `rgba(${primaryRgb}, 0.85)` : "rgba(255, 255, 255, 0.28)";
    ctx.font = "500 9px monospace";
    ctx.textAlign = "right";
    ctx.fillText(s.label, marginX - 6, y);
  }

  // ── 4. Acoustic Octave Bands Background Highlights ──
  const bands = [
    { name: "SUB BASS", start: 0.0, end: 0.12, col: "rgba(239, 68, 68, 0.03)" },
    { name: "BASS", start: 0.12, end: 0.28, col: "rgba(245, 158, 11, 0.025)" },
    { name: "LOW MID", start: 0.28, end: 0.46, col: "rgba(16, 185, 129, 0.02)" },
    { name: "HIGH MID", start: 0.46, end: 0.68, col: "rgba(6, 182, 212, 0.02)" },
    { name: "PRESENCE", start: 0.68, end: 0.86, col: "rgba(59, 130, 246, 0.02)" },
    { name: "BRILLIANCE", start: 0.86, end: 1.0, col: "rgba(168, 85, 247, 0.025)" }
  ];

  for (let b of bands) {
    const bx = marginX + b.start * availableW;
    const bw = (b.end - b.start) * availableW;
    ctx.fillStyle = b.col;
    ctx.fillRect(bx, marginTop, bw, availableH);

    ctx.fillStyle = "rgba(255, 255, 255, 0.22)";
    ctx.font = "600 8px 'Outfit', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(b.name, bx + bw / 2, marginTop + 14);

    // Subtle vertical octave separators
    ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
    ctx.beginPath();
    ctx.moveTo(bx + bw, marginTop);
    ctx.lineTo(bx + bw, baseY);
    ctx.stroke();
  }

  // ── 5. Frequency Labels along Baseline ──
  ctx.textAlign = "center";
  ctx.font = "500 9px monospace";
  ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
  const freqTags = [
    { text: "20Hz", pos: 0.0 },
    { text: "60Hz", pos: 0.10 },
    { text: "150Hz", pos: 0.22 },
    { text: "400Hz", pos: 0.36 },
    { text: "1kHz", pos: 0.50 },
    { text: "2.5kHz", pos: 0.64 },
    { text: "6kHz", pos: 0.78 },
    { text: "12kHz", pos: 0.90 },
    { text: "20kHz", pos: 1.0 }
  ];

  for (let f of freqTags) {
    const fx = marginX + f.pos * availableW;
    ctx.fillText(f.text, fx, baseY + 18);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
    ctx.beginPath();
    ctx.moveTo(fx, baseY);
    ctx.lineTo(fx, baseY + 4);
    ctx.stroke();
  }

  // ── 6. Calculate Bar Coordinates & Living Idle Motion ──
  const barW = Math.max(3, (availableW / count) * 0.72);
  const gap = (availableW - barW * count) / Math.max(1, count - 1);
  const barPoints = [];

  for (let i = 0; i < count; i++) {
    const rawVal = bars[i] || 0;
    // Organic living baseline breathing wave when paused or quiet
    const idleWave = Math.sin(animTime * 2.2 + i * 0.18) * 0.025 + Math.cos(animTime * 1.5 - i * 0.12) * 0.015;
    const effectiveVal = Math.max(0.015 + Math.abs(idleWave), rawVal * 1.25);
    const barH = Math.min(availableH * 0.98, effectiveVal * availableH);

    const x = marginX + i * (barW + gap);
    const y = baseY - barH;
    barPoints.push({ x: x + barW / 2, y, h: barH, barX: x });

    // Peak Hold tracking with natural gravity physics
    if (barH > (peakHold[i] || 0)) {
      peakHold[i] = barH;
      peakHoldDecay[i] = 0;
    } else {
      peakHoldDecay[i] = (peakHoldDecay[i] || 0) + 0.15;
      peakHold[i] = Math.max(0, peakHold[i] - peakHoldDecay[i]);
    }
  }

  // ── 7. Spline Ribbon Curve Overlay (FabFilter / Ozone Mastering Look) ──
  if (barPoints.length > 2) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(barPoints[0].x, baseY);
    ctx.lineTo(barPoints[0].x, barPoints[0].y);

    for (let i = 0; i < barPoints.length - 1; i++) {
      const pCurrent = barPoints[i];
      const pNext = barPoints[i + 1];
      const cx = (pCurrent.x + pNext.x) / 2;
      const cy = (pCurrent.y + pNext.y) / 2;
      ctx.quadraticCurveTo(pCurrent.x, pCurrent.y, cx, cy);
    }
    const lastP = barPoints[barPoints.length - 1];
    ctx.lineTo(lastP.x, lastP.y);
    ctx.lineTo(lastP.x, baseY);
    ctx.closePath();

    // Spline translucent radiant fill
    const splineGrad = ctx.createLinearGradient(0, marginTop, 0, baseY);
    splineGrad.addColorStop(0, `rgba(${primaryRgb}, 0.22)`);
    splineGrad.addColorStop(0.5, `rgba(${secondaryRgb}, 0.10)`);
    splineGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = splineGrad;
    ctx.fill();

    // Spline Neon Stroke
    ctx.beginPath();
    ctx.moveTo(barPoints[0].x, barPoints[0].y);
    for (let i = 0; i < barPoints.length - 1; i++) {
      const pCurrent = barPoints[i];
      const pNext = barPoints[i + 1];
      const cx = (pCurrent.x + pNext.x) / 2;
      const cy = (pCurrent.y + pNext.y) / 2;
      ctx.quadraticCurveTo(pCurrent.x, pCurrent.y, cx, cy);
    }
    ctx.strokeStyle = `rgb(${primaryRgb})`;
    ctx.lineWidth = 2.5;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 12 + bass * 10;
    ctx.stroke();
    ctx.restore();
  }

  // ── 8. Render Segmented Glowing Spectrum Bars ──
  for (let i = 0; i < count; i++) {
    const p = barPoints[i];
    const x = p.barX;
    const barHeight = p.h;

    const t = i / count;
    const r = Math.floor(pal.primary[0] * (1 - t) + pal.secondary[0] * t);
    const g = Math.floor(pal.primary[1] * (1 - t) + pal.secondary[1] * t);
    const b = Math.floor(pal.primary[2] * (1 - t) + pal.secondary[2] * t);

    // Multi-stop high-tech bar gradient
    const barGrad = ctx.createLinearGradient(0, baseY, 0, baseY - barHeight);
    barGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.2)`);
    barGrad.addColorStop(0.6, `rgba(${r}, ${g}, ${b}, 0.75)`);
    barGrad.addColorStop(0.92, `rgb(${r}, ${g}, ${b})`);
    barGrad.addColorStop(1, "#ffffff");

    ctx.fillStyle = barGrad;
    // Rounded top bar
    const radius = Math.min(barW / 2, 4);
    ctx.beginPath();
    ctx.roundRect(x, baseY - barHeight, barW, barHeight, [radius, radius, 0, 0]);
    ctx.fill();

    // LED segmentation stripes
    if (barHeight > 20) {
      ctx.fillStyle = "rgba(0, 0, 0, 0.28)";
      const segStep = 6;
      for (let sy = baseY - barHeight + 4; sy < baseY - 4; sy += segStep) {
        ctx.fillRect(x, sy, barW, 1.5);
      }
    }

    // Top Peak Glow Cap
    ctx.fillStyle = isVintage ? "#fef3c7" : "#ffffff";
    ctx.shadowColor = `rgb(${r}, ${g}, ${b})`;
    ctx.shadowBlur = 6;
    ctx.fillRect(x, baseY - barHeight - 1, barW, 2.5);
    ctx.shadowBlur = 0;

    // Peak Hold floating horizontal marker
    const pHold = peakHold[i] || 0;
    if (pHold > 6) {
      const peakY = baseY - pHold - 4;
      ctx.fillStyle = isVintage ? "#fde68a" : "#ffffff";
      ctx.shadowColor = "#ffffff";
      ctx.shadowBlur = 8;
      ctx.fillRect(x, peakY, barW, 2);
      ctx.shadowBlur = 0;
    }

    // Floor Mirror Reflection
    const reflectGrad = ctx.createLinearGradient(0, baseY, 0, baseY + barHeight * 0.25);
    reflectGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.22)`);
    reflectGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = reflectGrad;
    ctx.fillRect(x, baseY + 2, barW, barHeight * 0.22);
  }

  // ── 9. Baseline Horizon Glow Line ──
  ctx.strokeStyle = isVintage ? "rgba(251, 191, 36, 0.75)" : `rgba(${primaryRgb}, 0.8)`;
  ctx.lineWidth = 2 + bass * 1.5;
  ctx.shadowColor = pal.glow;
  ctx.shadowBlur = 10 + bass * 8;
  ctx.beginPath();
  ctx.moveTo(marginX, baseY);
  ctx.lineTo(w - marginX, baseY);
  ctx.stroke();
  ctx.shadowBlur = 0;

  // ── 10. Vintage Cambodian / Modern Watermark Stamp ──
  if (state.logoImageObj && state.logoImageObj.complete) {
    const logoSize = 64;
    ctx.save();
    ctx.globalAlpha = 0.8;
    ctx.drawImage(state.logoImageObj, w - marginX - logoSize, marginTop + 10, logoSize, logoSize);
    ctx.restore();
  } else if (isVintage) {
    // Elegant Golden Era Emblem Stamp
    ctx.fillStyle = "rgba(251, 191, 36, 0.4)";
    ctx.font = "700 13px 'Kantumruy Pro', sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("វិភាគសំនៀងតន្ត្រី • យុគមាស 60s", w - marginX, marginTop + 20);
    ctx.font = "600 10px 'Outfit', sans-serif";
    ctx.fillStyle = "rgba(253, 230, 138, 0.3)";
    ctx.fillText("DISQUES VINTAGE STEREO", w - marginX, marginTop + 34);
  } else {
    ctx.fillStyle = `rgba(${primaryRgb}, 0.35)`;
    ctx.font = "800 16px 'Outfit', sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("VIDA RTA PRO", w - marginX, marginTop + 22);
  }

  ctx.restore();
}
