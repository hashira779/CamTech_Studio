/**
 * VIDA Studio Pro — Smart Video Director & Rule Flow Engine
 * Dynamic Song Section Analysis • Automatic Drop Triggers • Customizable Rule Flows
 */
import { state } from '../core/state.js';
import { triggerCameraShake, triggerShockwave, triggerBloomFlash } from './vfx_engine.js';

let prevBass = 0;
let lastDropTime = 0;
let lastThemeSwitchTime = 0;

export const DIRECTOR_PRESETS = {
  festival_drop: {
    id: "festival_drop",
    name: "🔥 2026 Ultra Festival Drop",
    desc: "Heavy bass drops trigger maximum camera shake, expanding shockwaves, and strobe bloom.",
    dropShake: true,
    dropShockwave: true,
    dropBloom: true,
    transientPulse: true,
    autoSwitchThemes: false,
    themeSequence: ["quantum_vortex", "trap_circle"]
  },
  neural_glitch: {
    id: "neural_glitch",
    name: "🧠 2027 Neural Glitch Flow",
    desc: "Cybernetic AI flow with electric synapses, scanline flicker, and transient shockwaves.",
    dropShake: true,
    dropShockwave: true,
    dropBloom: false,
    transientPulse: true,
    autoSwitchThemes: false,
    themeSequence: ["neural_synapse", "hologram_hud"]
  },
  ambient_liquid: {
    id: "ambient_liquid",
    name: "🌊 2028 Ambient Liquid Float",
    desc: "Silky organic waves and floating droplets with gentle harmonic bloom without harsh shaking.",
    dropShake: false,
    dropShockwave: true,
    dropBloom: true,
    transientPulse: false,
    autoSwitchThemes: false,
    themeSequence: ["hyper_liquid", "ocean_wave"]
  },
  cyber_angkor: {
    id: "cyber_angkor",
    name: "🇰🇭 2029 Cyber-Angkor Sacred Flow",
    desc: "Majestic Khmer lotus mandalas and golden laser halos that ignite on musical drops.",
    dropShake: true,
    dropShockwave: true,
    dropBloom: true,
    transientPulse: true,
    autoSwitchThemes: false,
    themeSequence: ["angkor_mandala", "vinyl_60s"]
  },
  auto_ai_director: {
    id: "auto_ai_director",
    name: "🤖 Full Autonomous AI Director",
    desc: "AI intelligently switches visualizer themes, camera dynamics, and VFX according to song sections.",
    dropShake: true,
    dropShockwave: true,
    dropBloom: true,
    transientPulse: true,
    autoSwitchThemes: true,
    themeSequence: ["quantum_vortex", "neural_synapse", "hyper_liquid", "angkor_mandala", "hologram_hud"]
  },
  custom: {
    id: "custom",
    name: "🛠️ Custom User Rule Flow",
    desc: "User defined trigger rules and effect intensities.",
    dropShake: true,
    dropShockwave: true,
    dropBloom: true,
    transientPulse: true,
    autoSwitchThemes: false,
    themeSequence: []
  }
};

/**
 * Evaluates active rule flow every frame
 */
export function evaluateDirectorRules(bass, bars, width, height) {
  if (!state.directorActive) return;

  const now = performance.now();
  const preset = DIRECTOR_PRESETS[state.activeDirectorPreset] || DIRECTOR_PRESETS.festival_drop;

  // 1. Drop & Transient Detection
  const bassDelta = bass - prevBass;
  const isBassDrop = bass > 0.72 && bassDelta > 0.14 && (now - lastDropTime > 400);

  if (isBassDrop) {
    lastDropTime = now;

    // Trigger Camera Shake
    if (preset.dropShake && state.vfxShake) {
      triggerCameraShake(18 * (state.vfxIntensity || 1));
    }

    // Trigger Expanding Shockwave
    if (preset.dropShockwave && state.vfxShockwave) {
      triggerShockwave(width / 2, height / 2, 1.2 * (state.vfxIntensity || 1));
    }

    // Trigger Optical Strobe Bloom
    if (preset.dropBloom && state.vfxBloom) {
      triggerBloomFlash(0.75 * (state.vfxIntensity || 1));
    }
  }

  // 2. Autonomous AI Theme Switching across song sections (every 16-24 bars or on major transitions)
  if (preset.autoSwitchThemes && (now - lastThemeSwitchTime > 14000)) {
    if (isBassDrop || (bass > 0.6 && Math.random() > 0.95)) {
      lastThemeSwitchTime = now;
      const themes = preset.themeSequence;
      const currentIdx = themes.indexOf(state.theme);
      const nextTheme = themes[(currentIdx + 1) % themes.length];
      state.theme = nextTheme;

      const themeSelect = document.getElementById('select-theme');
      if (themeSelect) themeSelect.value = nextTheme;

      // Trigger transition flare
      triggerBloomFlash(0.6);
      triggerShockwave(width / 2, height / 2, 1.0);
    }
  }

  prevBass = bass;
}
