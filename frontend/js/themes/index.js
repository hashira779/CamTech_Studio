import { state } from '../core/state.js';
import { drawTrapCircle } from './trap.js';
import { drawNeonBars } from './neon.js';
import { drawWaveTheme } from './wave.js';
import { drawSpectrumAnalyzer } from './spectrum.js';
import { drawQuantumVortex } from './quantum_vortex.js';
import { drawNeuralSynapse } from './neural_synapse.js';
import { drawHyperLiquid } from './hyper_liquid.js';
import { drawAngkorMandala } from './angkor_mandala.js';
import { drawHologramHUD } from './hologram_hud.js';

const THEME_RENDERERS = {
  trap_circle: drawTrapCircle,
  neon_bars: drawNeonBars,
  ocean_wave: drawWaveTheme,
  spectrum: drawSpectrumAnalyzer,
  // 🚀 2026–2029 Next-Gen Futuristic Themes
  quantum_vortex: drawQuantumVortex,
  neural_synapse: drawNeuralSynapse,
  hyper_liquid: drawHyperLiquid,
  angkor_mandala: drawAngkorMandala,
  hologram_hud: drawHologramHUD
};

export function renderActiveTheme(ctx, width, height, bass, bars) {
  const renderer = THEME_RENDERERS[state.theme] || drawTrapCircle;
  renderer(ctx, width, height, bars, bass);
}
