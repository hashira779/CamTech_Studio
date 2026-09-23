import { state, PALETTES } from './state.js';
import { getAudioData, getAnalyser } from './audio.js';
import { renderActiveTheme } from '../themes/index.js';
import { updateLyricState, drawLyrics } from './lyrics.js';
import { getCameraShakeOffset, renderPostVFX } from '../plugins/vfx_engine.js';
import { evaluateDirectorRules } from '../plugins/director_rules.js';

let canvas = null;
let ctx = null;
let isRendering = false;
let animationFrameId = null;

// Ballistics state
let prevSpectrum = new Float32Array(256);
let tempSpectrum = new Float32Array(256);
let smoothedBass = 0.2;

// Ambient Particles
const particles = [];
for (let i = 0; i < 80; i++) {
  particles.push({
    x: Math.random() * 1920,
    y: Math.random() * 1080,
    vx: (Math.random() - 0.5) * 0.9,
    vy: -Math.random() * 1.3 - 0.3,
    r: Math.random() * 2.8 + 1.2,
    alpha: Math.random() * 0.5 + 0.3
  });
}

export function initVisualizer(canvasElement) {
  canvas = canvasElement;
  ctx = canvas.getContext('2d');
}

export function startVisualizer() {
  if (isRendering) return;
  isRendering = true;
  renderFrame();
}

export function stopVisualizer() {
  isRendering = false;
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
  }
}

function renderFrame() {
  if (!isRendering) return;
  
  const width = canvas.width;
  const height = canvas.height;
  
  // Clear canvas
  ctx.clearRect(0, 0, width, height);

  // Apply Camera Shake Transform if active
  const shake = getCameraShakeOffset();
  ctx.save();
  if (shake.x !== 0 || shake.y !== 0 || shake.angle !== 0) {
    ctx.translate(width / 2 + shake.x, height / 2 + shake.y);
    ctx.rotate(shake.angle);
    ctx.translate(-width / 2, -height / 2);
  }
  
  // Draw Background
  if (state.bgImageObj && state.bgImageObj.complete) {
    ctx.drawImage(state.bgImageObj, 0, 0, width, height);
  } else {
    const curPal = PALETTES[state.palette] || PALETTES.cyberpunk;
    const bgGrad = ctx.createRadialGradient(width / 2, height * 0.45, width * 0.05, width / 2, height / 2, width * 0.75);
    bgGrad.addColorStop(0, `rgba(${curPal.secondary.join(',')}, 0.08)`);
    bgGrad.addColorStop(0.55, "#0b0e17");
    bgGrad.addColorStop(1, "#040508");
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);
  }

  const rawData = getAudioData();
  const analyser = getAnalyser();
  
  let bass = 0;
  const barCount = state.barCount;
  const displayBars = [];
  
  if (rawData && analyser) {
    const binCount = analyser.frequencyBinCount; // Usually 1024
    
    // Low pass filter for bass (approx 0-250Hz)
    let bassSum = 0;
    const bassBins = Math.floor(binCount * (250 / 22050));
    for(let i=0; i<bassBins; i++) {
      bassSum += rawData[i];
    }
    const instBass = (bassSum / (bassBins || 1)) / 255.0;
    // Fast attack, slow decay for bass
    smoothedBass = smoothedBass * 0.8 + instBass * 0.2;
    bass = smoothedBass * state.bassBoost;

    // Resample frequency bins into exactly 'barCount' buckets with logarithmic scaling
    const activeBins = Math.floor(binCount * 0.7); // Discard top 30% (mostly noise)
    
    for (let i = 0; i < barCount; i++) {
      const minLog = Math.log(1);
      const maxLog = Math.log(activeBins);
      const scale = (maxLog - minLog) / barCount;
      
      const startBin = Math.floor(Math.exp(minLog + i * scale));
      const endBin = Math.floor(Math.exp(minLog + (i + 1) * scale));
      
      let sum = 0;
      let count = 0;
      for (let j = startBin; j <= endBin && j < activeBins; j++) {
        sum += rawData[j];
        count++;
      }
      
      const instVal = count > 0 ? (sum / count) / 255.0 : 0;
      
      // Asymmetric Ballistics: Responsive Attack, Smooth Decay
      let attack = 0.6;
      let decay = state.smoothing;
      
      if (instVal > prevSpectrum[i]) {
        tempSpectrum[i] = prevSpectrum[i] * (1 - attack) + instVal * attack;
      } else {
        tempSpectrum[i] = prevSpectrum[i] * decay + instVal * (1 - decay);
      }
    }
    
    // Spatial Gaussian Convolution (Neighborhood smoothing)
    for (let i = 0; i < barCount; i++) {
      let p2 = i > 1 ? tempSpectrum[i-2] : tempSpectrum[0];
      let p1 = i > 0 ? tempSpectrum[i-1] : tempSpectrum[0];
      let c0 = tempSpectrum[i];
      let n1 = i < barCount - 1 ? tempSpectrum[i+1] : tempSpectrum[barCount-1];
      let n2 = i < barCount - 2 ? tempSpectrum[i+2] : tempSpectrum[barCount-1];
      
      let smoothedVal = p2*0.07 + p1*0.23 + c0*0.40 + n1*0.23 + n2*0.07;
      prevSpectrum[i] = smoothedVal;
      displayBars.push(smoothedVal);
    }
  } else {
    for (let i = 0; i < barCount; i++) {
       displayBars.push(0);
       prevSpectrum[i] = 0;
    }
    bass = 0;
  }

  // 🧠 Evaluate Smart Video Director & Rule Flow System
  evaluateDirectorRules(bass, displayBars, width, height);
  
  // Update particles
  if (state.particlesLevel > 0) {
    ctx.save();
    const activePalette = PALETTES[state.palette] || PALETTES.cyberpunk;
    for (let p of particles) {
      if (Math.random() > 0.98 - (bass * 0.1)) p.alpha = Math.min(1, p.alpha + 0.1);
      
      p.x += p.vx;
      p.y += p.vy - (bass * 3);
      
      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;
      
      if (p.alpha > 0.05) {
        ctx.fillStyle = `rgba(${activePalette.primary.join(',')}, ${p.alpha * (state.particlesLevel/3)})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r + (bass * 1.5), 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  // Draw selected theme
  renderActiveTheme(ctx, width, height, bass, displayBars);

  // Update and draw kinetic lyrics overlay
  const audioPlayer = document.getElementById("audio-player");
  if (audioPlayer) {
    updateLyricState(audioPlayer.currentTime);
  }
  drawLyrics(ctx, width, height);

  ctx.restore(); // Restore Camera Shake Transform

  // ✨ Apply Real-Time Post-Processing VFX (Shockwaves, Bloom Flash, Scanlines)
  renderPostVFX(ctx, width, height, bass);

  // Loop
  animationFrameId = requestAnimationFrame(renderFrame);
}
