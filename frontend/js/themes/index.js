import { state } from '../core/state.js';
import { drawTrapCircle } from './trap.js?v=20260927-v7';
import { drawNeonBars } from './neon.js?v=20260927-v7';
import { drawWaveTheme } from './wave.js?v=20260927-v7';
import { drawSpectrumAnalyzer } from './spectrum.js?v=20260927-v7';
import { drawQuantumVortex } from './quantum_vortex.js?v=20260927-v7';
import { drawNeuralSynapse } from './neural_synapse.js?v=20260927-v7';
import { drawHyperLiquid } from './hyper_liquid.js?v=20260927-v7';
import { drawAngkorMandala } from './angkor_mandala.js?v=20260927-v7';
import { drawHologramHUD } from './hologram_hud.js?v=20260927-v7';
import { drawAuroraBorealis } from './aurora_borealis.js?v=20260927-v7';
import { drawDNAHelix } from './dna_helix.js?v=20260927-v7';
import { drawSonicNebula } from './sonic_nebula.js?v=20260927-v7';

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
  hologram_hud: drawHologramHUD,
  // 🌌 2026 Ultra-Premium Themes
  aurora_borealis: drawAuroraBorealis,
  dna_helix: drawDNAHelix,
  sonic_nebula: drawSonicNebula
};

export function renderActiveTheme(ctx, width, height, bass, bars) {
  const renderer = THEME_RENDERERS[state.theme] || drawTrapCircle;
  renderer(ctx, width, height, bars, bass);
}
