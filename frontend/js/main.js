import { state, PALETTES } from './core/state.js';
import { initAudioContext, updateVolume, updateEq } from './core/audio.js';
import { initVisualizer, startVisualizer } from './core/visualizer.js';
import { KHMER_TEMPLATES, KHMER_SINGERS_60S_70S } from './core/khmer_templates.js';
import { DIRECTOR_PRESETS } from './plugins/director_rules.js';
import { triggerCameraShake, triggerShockwave, triggerBloomFlash } from './plugins/vfx_engine.js';

// ============ Toast Notification System ============
function showToast(title, body, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-body">${body}</div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ============ Button Loading Helpers ============
function setButtonLoading(btn, text) {
  btn._originalText = btn._originalText || btn.textContent;
  btn.textContent = text;
  btn.classList.add('btn-loading');
}
function clearButtonLoading(btn, text) {
  btn.textContent = text || btn._originalText || 'Done';
  btn.classList.remove('btn-loading');
}

// ============ Duration Formatter ============
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// ============ Smart AI Theme Recommendation ============
const MOOD_TO_THEME = {
  'energetic':    { theme: 'trap_circle',  palette: 'cyberpunk' },
  'aggressive':   { theme: 'trap_circle',  palette: 'bloodmoon' },
  'dark':         { theme: 'neon_bars',    palette: 'bloodmoon' },
  'chill':        { theme: 'ocean_wave',   palette: 'sunset' },
  'romantic':     { theme: 'ocean_wave',   palette: 'pastel' },
  'sad':          { theme: 'ocean_wave',   palette: 'monochrome' },
  'happy':        { theme: 'trap_circle',  palette: 'sunset' },
  'epic':         { theme: 'spectrum',     palette: 'electric' },
  'traditional':  { theme: 'neon_bars',    palette: 'angkor' },
  'electronic':   { theme: 'spectrum',     palette: 'cyberpunk' },
  'pop':          { theme: 'trap_circle',  palette: 'pastel' },
  'hiphop':       { theme: 'trap_circle',  palette: 'matrix' },
  'classical':    { theme: 'ocean_wave',   palette: 'monochrome' },
  'default':      { theme: 'trap_circle',  palette: 'cyberpunk' }
};

function getSmartRecommendation(mood, genre, energy) {
  const key = (mood || '').toLowerCase();
  const genreKey = (genre || '').toLowerCase();
  
  // Try mood match first
  for (const [k, v] of Object.entries(MOOD_TO_THEME)) {
    if (key.includes(k)) return v;
  }
  // Try genre match
  for (const [k, v] of Object.entries(MOOD_TO_THEME)) {
    if (genreKey.includes(k)) return v;
  }
  // Energy-based fallback
  if (energy >= 0.8) return { theme: 'trap_circle', palette: 'cyberpunk' };
  if (energy <= 0.4) return { theme: 'ocean_wave', palette: 'monochrome' };
  return MOOD_TO_THEME['default'];
}

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById("visualizer-canvas");
  const audioPlayer = document.getElementById("audio-player");
  const btnPlayPause = document.getElementById("btn-play-pause");
  const volumeSlider = document.getElementById("volume-slider");
  
  // Initialize Visualizer Context
  if (canvas) {
    initVisualizer(canvas);
    startVisualizer();
  }

  // Clear lyrics on startup
  state.lyrics = [];

  // ============ Restore Session After Hot-Reload ============
  const savedSrc = sessionStorage.getItem('vida_audio_src');
  const savedTime = parseFloat(sessionStorage.getItem('vida_audio_time') || '0');
  const savedServerPath = sessionStorage.getItem('vida_audio_server_path');

  if (savedSrc && audioPlayer) {
    audioPlayer.src = savedSrc;
    state.audioUrl = savedSrc;
    if (savedServerPath) {
      state.audioServerPath = savedServerPath;
      window.__VIDA_SERVER_PATH = savedServerPath;
    }
    audioPlayer.currentTime = savedTime;
    showToast('🔄 Session Restored', 'Audio resumed from where you left off', 'info', 2500);
    
    // Auto-play and init visualizer
    audioPlayer.play().then(() => {
      state.isPlaying = true;
      if (btnPlayPause) btnPlayPause.textContent = "⏸";
      initAudioContext(audioPlayer, () => startVisualizer());
    }).catch(() => {});
    
    // Clear storage after restore
    sessionStorage.removeItem('vida_audio_src');
    sessionStorage.removeItem('vida_audio_time');
    sessionStorage.removeItem('vida_audio_server_path');
    
    // Re-run smart pipeline if we have a server path
    if (savedServerPath) {
      setTimeout(() => runSmartPipeline(), 1500);
    }
  }

  // ============ Audio Play/Pause ============
  if (btnPlayPause && audioPlayer) {
    btnPlayPause.addEventListener('click', () => {
      initAudioContext(audioPlayer, (isNew, status) => {
         if (isNew || status === "resumed") {
           startVisualizer();
         }
      });
      
      if (audioPlayer.paused) {
        audioPlayer.play();
        state.isPlaying = true;
        btnPlayPause.textContent = "⏸";
      } else {
        audioPlayer.pause();
        state.isPlaying = false;
        btnPlayPause.textContent = "▶";
      }
    });
  }

  // ============ Volume ============
  if (volumeSlider) {
    volumeSlider.addEventListener('input', (e) => {
      state.lastVolume = parseFloat(e.target.value);
      updateVolume(state.lastVolume, state.isMuted);
    });
  }

  // ============ EQ Sliders ============
  const eqSub = document.getElementById('eq-sub');
  const eqMid = document.getElementById('eq-mid');
  const eqHigh = document.getElementById('eq-high');
  
  if (eqSub) {
    eqSub.addEventListener('input', (e) => updateEq('sub', parseFloat(e.target.value)));
  }
  if (eqMid) {
    eqMid.addEventListener('input', (e) => updateEq('mid', parseFloat(e.target.value)));
  }
  if (eqHigh) {
    eqHigh.addEventListener('input', (e) => updateEq('high', parseFloat(e.target.value)));
  }

  // ============ Aspect Ratio Tabs ============
  const aspectTabs = document.querySelectorAll('.aspect-tabs button');
  const canvasWrapper = document.querySelector('.canvas-wrapper');
  const vizCanvas = document.getElementById('visualizer-canvas');

  aspectTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      aspectTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const label = tab.textContent.trim();
      if (canvasWrapper && vizCanvas) {
        // Clear any inline styles so responsive CSS classes take effect
        canvasWrapper.style.maxWidth = '';
        canvasWrapper.style.aspectRatio = '';

        if (label.includes('9:16')) {
          state.aspectRatio = '9:16';
          canvasWrapper.className = 'canvas-wrapper aspect-9-16';
          vizCanvas.width = 1080;
          vizCanvas.height = 1920;
        } else if (label.includes('1:1')) {
          state.aspectRatio = '1:1';
          canvasWrapper.className = 'canvas-wrapper aspect-1-1';
          vizCanvas.width = 1080;
          vizCanvas.height = 1080;
        } else {
          state.aspectRatio = '16:9';
          canvasWrapper.className = 'canvas-wrapper aspect-16-9';
          vizCanvas.width = 1920;
          vizCanvas.height = 1080;
        }
      }
      showToast('Aspect Ratio', `Switched to ${state.aspectRatio}`, 'info', 1500);
    });
  });

  // ============ Panel Toggles & Theater Mode ============
  const btnToggleLeft = document.getElementById('btn-toggle-left-panel');
  const btnToggleRight = document.getElementById('btn-toggle-right-panel');
  const dawWorkspace = document.getElementById('daw-workspace');
  const btnFullscreen = document.getElementById('btn-fullscreen-stage');

  if (btnToggleLeft && dawWorkspace) {
    btnToggleLeft.addEventListener('click', () => {
      dawWorkspace.classList.toggle('left-collapsed');
      btnToggleLeft.classList.toggle('active', !dawWorkspace.classList.contains('left-collapsed'));
    });
  }

  if (btnToggleRight && dawWorkspace) {
    btnToggleRight.addEventListener('click', () => {
      dawWorkspace.classList.toggle('right-collapsed');
      btnToggleRight.classList.toggle('active', !dawWorkspace.classList.contains('right-collapsed'));
    });
  }

  if (btnFullscreen && dawWorkspace) {
    btnFullscreen.addEventListener('click', () => {
      const isTheater = dawWorkspace.classList.contains('left-collapsed') && dawWorkspace.classList.contains('right-collapsed');
      if (isTheater) {
        dawWorkspace.classList.remove('left-collapsed', 'right-collapsed');
        if (btnToggleLeft) btnToggleLeft.classList.add('active');
        if (btnToggleRight) btnToggleRight.classList.add('active');
      } else {
        dawWorkspace.classList.add('left-collapsed', 'right-collapsed');
        if (btnToggleLeft) btnToggleLeft.classList.remove('active');
        if (btnToggleRight) btnToggleRight.classList.remove('active');
      }
    });
  }

  // ============ Segmented Tab Switcher (Left & Right Panels) ============
  function setupSegmentedNav(navId, panelId) {
    const nav = document.getElementById(navId);
    const panel = document.getElementById(panelId);
    if (!nav || !panel) return;

    const tabs = nav.querySelectorAll('.segmented-tab');
    const panes = panel.querySelectorAll('.tab-pane');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const targetId = tab.dataset.target;
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        panes.forEach(pane => {
          if (pane.id === targetId) {
            pane.classList.remove('hidden');
          } else {
            pane.classList.add('hidden');
          }
        });
      });
    });
  }

  setupSegmentedNav('nav-left-panel', 'left-panel');
  setupSegmentedNav('nav-right-panel', 'right-panel');

  // ============ Additional Transport Buttons ============
  const btnPrev = document.getElementById('btn-transport-prev');
  const btnStop = document.getElementById('btn-transport-stop');
  const btnVolumeIcon = document.getElementById('btn-volume-icon');

  if (btnPrev && audioPlayer) {
    btnPrev.addEventListener('click', () => {
      audioPlayer.currentTime = 0;
      const tc = document.querySelector('.timecode');
      if (tc) tc.textContent = '00:00:00:00';
    });
  }

  if (btnStop && audioPlayer) {
    btnStop.addEventListener('click', () => {
      audioPlayer.pause();
      audioPlayer.currentTime = 0;
      state.isPlaying = false;
      if (btnPlayPause) btnPlayPause.textContent = "▶";
      const tc = document.querySelector('.timecode');
      if (tc) tc.textContent = '00:00:00:00';
    });
  }

  if (btnVolumeIcon && audioPlayer) {
    btnVolumeIcon.addEventListener('click', () => {
      state.isMuted = !state.isMuted;
      btnVolumeIcon.textContent = state.isMuted ? '🔇' : '🔊';
      updateVolume(state.lastVolume, state.isMuted);
    });
  }

  // ============ Keyboard Spacebar Play/Pause ============
  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault();
      if (btnPlayPause) btnPlayPause.click();
    }
  });

  // ============ LLM Chat Box ============
  const llmInput = document.querySelector('.llm-input');
  const llmBtn = document.querySelector('.btn-ai-small');
  if (llmBtn && llmInput) {
    llmBtn.addEventListener('click', async () => {
      const text = llmInput.value.trim();
      if (!text) return;
      
      try {
        setButtonLoading(llmBtn, 'Thinking...');
        const res = await fetch('/api/ai/llm/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await res.json();
        
        if (data.analysis) {
          llmInput.value = data.analysis;
          showToast('🤖 AI Response', data.analysis.substring(0, 80) + '...', 'success');
        } else if (data.status === 'error') {
          llmInput.value = data.analysis || 'Model not loaded. Run: pip install llama-cpp-python';
          showToast('LLM Error', 'Model not installed or loaded', 'error');
        }
      } catch (err) {
        showToast('LLM Error', err.message, 'error');
      } finally {
        clearButtonLoading(llmBtn, 'Ask Qwen 2.5');
      }
    });
  }

  // ============ Theme, Palette & Lyric Style Selectors ============
  const selectTheme = document.getElementById('select-theme');
  const selectPalette = document.getElementById('select-palette');
  const selectLyricStyle = document.getElementById('select-lyric-style');

  if (selectTheme) {
    selectTheme.value = state.theme;
    selectTheme.addEventListener('change', (e) => {
      state.theme = e.target.value;
      showToast('Theme Changed', `Switched to ${selectTheme.options[selectTheme.selectedIndex].text}`, 'info', 2000);
    });
  }

  if (selectPalette) {
    selectPalette.value = state.palette;
    selectPalette.addEventListener('change', (e) => {
      state.palette = e.target.value;
      showToast('Palette Changed', `Now using ${selectPalette.options[selectPalette.selectedIndex].text}`, 'info', 2000);
    });
  }

  // ============ 📝 On-Screen Typography & Titles (Add, Update, Delete) ============
  const checkShowTitles = document.getElementById('check-show-titles');
  const inputSongTitle = document.getElementById('input-song-title');
  const btnClearTitle = document.getElementById('btn-clear-title');
  const inputArtistName = document.getElementById('input-artist-name');
  const btnClearArtist = document.getElementById('btn-clear-artist');
  const checkShowCenterText = document.getElementById('check-show-center-text');
  const inputCenterPrimary = document.getElementById('input-center-primary');
  const inputCenterSecondary = document.getElementById('input-center-secondary');
  const btnClearCenterText = document.getElementById('btn-clear-center-text');

  function syncTitleInputs() {
    if (inputSongTitle) inputSongTitle.value = state.songTitle || '';
    if (inputArtistName) inputArtistName.value = state.artistName || '';
    if (inputCenterPrimary && state.centerTextPrimary !== undefined) inputCenterPrimary.value = state.centerTextPrimary;
    if (inputCenterSecondary && state.centerTextSecondary !== undefined) inputCenterSecondary.value = state.centerTextSecondary;
    if (checkShowTitles) checkShowTitles.checked = state.showTitles !== false;
    if (checkShowCenterText) checkShowCenterText.checked = state.showCenterText !== false;
  }
  syncTitleInputs();

  if (checkShowTitles) {
    checkShowTitles.checked = state.showTitles !== false;
    checkShowTitles.addEventListener('change', (e) => {
      state.showTitles = e.target.checked;
      showToast('Header Titles', state.showTitles ? 'Titles Visible' : 'Titles Hidden', 'info', 1500);
    });
  }

  if (inputSongTitle) {
    inputSongTitle.value = state.songTitle || '';
    inputSongTitle.addEventListener('input', (e) => {
      state.songTitle = e.target.value;
      const titleEl = document.querySelector('.project-title');
      if (titleEl) titleEl.textContent = `Project: ${state.songTitle}${state.artistName ? ' — ' + state.artistName : ''}`;
    });
  }

  if (btnClearTitle && inputSongTitle) {
    btnClearTitle.addEventListener('click', () => {
      state.songTitle = '';
      inputSongTitle.value = '';
      const titleEl = document.querySelector('.project-title');
      if (titleEl) titleEl.textContent = `Project: ${state.artistName || 'VIDA'}`;
      showToast('Song Title', 'Title deleted/cleared', 'info', 1500);
    });
  }

  if (inputArtistName) {
    inputArtistName.value = state.artistName || '';
    inputArtistName.addEventListener('input', (e) => {
      state.artistName = e.target.value;
      const titleEl = document.querySelector('.project-title');
      if (titleEl) titleEl.textContent = `Project: ${state.songTitle || 'VIDA'}${state.artistName ? ' — ' + state.artistName : ''}`;
    });
  }

  if (btnClearArtist && inputArtistName) {
    btnClearArtist.addEventListener('click', () => {
      state.artistName = '';
      inputArtistName.value = '';
      const titleEl = document.querySelector('.project-title');
      if (titleEl) titleEl.textContent = `Project: ${state.songTitle || 'VIDA'}`;
      showToast('Singer / Artist', 'Singer deleted/cleared', 'info', 1500);
    });
  }

  if (checkShowCenterText) {
    checkShowCenterText.checked = state.showCenterText !== false;
    checkShowCenterText.addEventListener('change', (e) => {
      state.showCenterText = e.target.checked;
      showToast('Center Badge', state.showCenterText ? 'Badge Text Visible' : 'Badge Text Hidden', 'info', 1500);
    });
  }

  if (inputCenterPrimary) {
    inputCenterPrimary.value = state.centerTextPrimary !== undefined ? state.centerTextPrimary : 'VIDA';
    inputCenterPrimary.addEventListener('input', (e) => {
      state.centerTextPrimary = e.target.value;
    });
  }

  if (inputCenterSecondary) {
    inputCenterSecondary.value = state.centerTextSecondary !== undefined ? state.centerTextSecondary : 'FLUID WAVE';
    inputCenterSecondary.addEventListener('input', (e) => {
      state.centerTextSecondary = e.target.value;
    });
  }

  if (btnClearCenterText) {
    btnClearCenterText.addEventListener('click', () => {
      state.centerTextPrimary = '';
      state.centerTextSecondary = '';
      if (inputCenterPrimary) inputCenterPrimary.value = '';
      if (inputCenterSecondary) inputCenterSecondary.value = '';
      showToast('Center Badge', 'Center emblem text deleted/cleared', 'info', 1500);
    });
  }

  // ============ 🎬 Smart Video Director & Rule Flow ============
  const selectDirector = document.getElementById('select-director-preset');
  const checkDirectorActive = document.getElementById('check-director-active');
  const checkRuleShake = document.getElementById('check-rule-shake');
  const checkRuleShockwave = document.getElementById('check-rule-shockwave');
  const checkRuleBloom = document.getElementById('check-rule-bloom');
  const checkRuleSwitch = document.getElementById('check-rule-switch');

  function syncDirectorUI(presetId) {
    const p = DIRECTOR_PRESETS[presetId] || DIRECTOR_PRESETS.festival_drop;
    if (checkRuleShake) checkRuleShake.checked = p.dropShake;
    if (checkRuleShockwave) checkRuleShockwave.checked = p.dropShockwave;
    if (checkRuleBloom) checkRuleBloom.checked = p.dropBloom;
    if (checkRuleSwitch) checkRuleSwitch.checked = p.autoSwitchThemes;
    if (p.themeSequence && p.themeSequence.length > 0 && !p.autoSwitchThemes) {
      state.theme = p.themeSequence[0];
      if (selectTheme) selectTheme.value = p.themeSequence[0];
    }
  }

  if (selectDirector) {
    selectDirector.value = state.activeDirectorPreset;
    selectDirector.addEventListener('change', (e) => {
      state.activeDirectorPreset = e.target.value;
      syncDirectorUI(e.target.value);
      const p = DIRECTOR_PRESETS[e.target.value];
      if (p) showToast('🎬 Director Rule Flow', p.name, 'success', 2500);
    });
  }

  if (checkDirectorActive) {
    checkDirectorActive.checked = state.directorActive;
    checkDirectorActive.addEventListener('change', (e) => {
      state.directorActive = e.target.checked;
      showToast('Director Flow', state.directorActive ? 'Auto Director Active' : 'Director Disabled', 'info', 1500);
    });
  }

  [checkRuleShake, checkRuleShockwave, checkRuleBloom, checkRuleSwitch].forEach(cb => {
    if (cb) {
      cb.addEventListener('change', () => {
        const cur = DIRECTOR_PRESETS[state.activeDirectorPreset];
        if (cur) {
          if (cb === checkRuleShake) cur.dropShake = cb.checked;
          if (cb === checkRuleShockwave) cur.dropShockwave = cb.checked;
          if (cb === checkRuleBloom) cur.dropBloom = cb.checked;
          if (cb === checkRuleSwitch) cur.autoSwitchThemes = cb.checked;
        }
      });
    }
  });

  // ============ ✨ Real-Time VFX Rack ============
  const sliderVfxPower = document.getElementById('slider-vfx-power');
  const labelVfxPower = document.getElementById('label-vfx-power');
  const checkVfxScanlines = document.getElementById('check-vfx-scanlines');
  const btnTriggerVfxTest = document.getElementById('btn-trigger-vfx-test');

  if (sliderVfxPower) {
    sliderVfxPower.value = state.vfxIntensity;
    sliderVfxPower.addEventListener('input', (e) => {
      state.vfxIntensity = parseFloat(e.target.value);
      if (labelVfxPower) labelVfxPower.textContent = `${Math.round(state.vfxIntensity * 100)}%`;
    });
  }

  if (checkVfxScanlines) {
    checkVfxScanlines.checked = state.vfxScanlines;
    checkVfxScanlines.addEventListener('change', (e) => {
      state.vfxScanlines = e.target.checked;
    });
  }

  if (btnTriggerVfxTest) {
    btnTriggerVfxTest.addEventListener('click', () => {
      const viz = document.getElementById('visualizer-canvas');
      const w = viz ? viz.width : 1920;
      const h = viz ? viz.height : 1080;
      triggerCameraShake(24);
      triggerShockwave(w / 2, h / 2, 1.4);
      triggerBloomFlash(0.85);
      showToast('⚡ Drop Impact Tested', 'Triggered Shake + Shockwave + Optical Bloom', 'info', 2000);
    });
  }



  // ============ 🇰🇭 20 Authentic Khmer Templates Controller ============
  function applyKhmerTemplate(templateId, showToastAlert = true) {
    const t = KHMER_TEMPLATES.find(x => x.id === templateId);
    if (!t) return;

    state.theme = t.theme;
    state.palette = t.palette;
    state.lyricStyle = t.lyricStyle;
    state.barCount = t.barCount;
    state.bassBoost = t.bassBoost;
    state.particlesLevel = t.particlesLevel;
    state.showLyrics = true;

    // Synchronize UI dropdowns
    if (selectTheme) selectTheme.value = t.theme;
    if (selectPalette) selectPalette.value = t.palette;
    if (selectLyricStyle) selectLyricStyle.value = t.lyricStyle;
    const selectKhmer = document.getElementById('select-khmer-template');
    if (selectKhmer) selectKhmer.value = t.id;

    // Update active highlight on modal cards
    document.querySelectorAll('.khmer-card').forEach(card => {
      card.classList.toggle('active-template', card.dataset.id === t.id);
    });

    // Update lyrics visibility UI
    setLyricsVisibility(true, false);

    // Close modal if open
    const modal = document.getElementById('khmer-templates-modal');
    if (modal) modal.style.display = 'none';

    if (showToastAlert) {
      showToast('🇰🇭 Template Applied!', `${t.title_km} (${t.title_en})`, 'success', 4500);
    }
  }

  // Dropdown handler
  const selectKhmerTemplate = document.getElementById('select-khmer-template');
  if (selectKhmerTemplate) {
    selectKhmerTemplate.addEventListener('change', (e) => {
      applyKhmerTemplate(e.target.value);
    });
  }

  // Modal open/close & rendering
  const modalKhmer = document.getElementById('khmer-templates-modal');
  const btnOpenKhmer = document.getElementById('btn-open-khmer-templates');
  const btnBrowseGrid = document.getElementById('btn-browse-khmer-grid');
  const btnCloseKhmer = document.getElementById('btn-close-khmer-modal');
  const gridKhmer = document.getElementById('khmer-templates-grid');
  const tabsKhmer = document.getElementById('khmer-category-tabs');

  function openKhmerModal() {
    if (!modalKhmer) return;
    renderKhmerGrid('all');
    modalKhmer.style.display = 'flex';
  }

  if (btnOpenKhmer) btnOpenKhmer.addEventListener('click', openKhmerModal);
  if (btnBrowseGrid) btnBrowseGrid.addEventListener('click', openKhmerModal);
  if (btnCloseKhmer) btnCloseKhmer.addEventListener('click', () => modalKhmer.style.display = 'none');
  if (modalKhmer) {
    modalKhmer.addEventListener('click', (e) => {
      if (e.target === modalKhmer) modalKhmer.style.display = 'none';
    });
  }

  function renderKhmerGrid(categoryFilter = 'all') {
    if (!gridKhmer) return;
    gridKhmer.innerHTML = '';

    // Special view for 11 Golden Era Cambodian Legends
    if (categoryFilter === 'singers') {
      KHMER_SINGERS_60S_70S.forEach(s => {
        const card = document.createElement('div');
        card.className = 'khmer-card';
        card.dataset.id = s.id;
        card.style.border = `1px solid ${s.accent}55`;
        card.style.background = 'rgba(255, 255, 255, 0.025)';

        const famousTags = s.famousSongs.map(f => `<span class="khmer-pill" style="border-color:${s.accent}88; color:#fef3c7; font-size: 10px;">🎵 ${f}</span>`).join(' ');

        card.innerHTML = `
          <div style="height: 64px; border-radius: 6px; background: ${s.bgAccent}; display: flex; align-items: flex-end; padding: 8px 10px; position: relative; overflow: hidden; box-shadow: inset 0 -15px 25px rgba(0,0,0,0.5);">
            <span style="position: absolute; top: 6px; right: 8px; font-size: 9px; font-weight: 700; color: #fbbf24; background: rgba(0,0,0,0.75); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(251,191,36,0.4);">${s.badge}</span>
            <span style="font-size: 11px; color: #fde68a; font-weight: 700; text-shadow: 0 1px 3px rgba(0,0,0,0.8);">${s.years}</span>
          </div>
          <div style="margin-top: 4px;">
            <h4 style="font-size: 14px; font-weight: 700; color: #fff; margin: 0; font-family: 'Kantumruy Pro', sans-serif;">${s.name_km} (${s.name_en})</h4>
            <div style="font-size: 11px; color: #fbbf24; margin-top: 1px; font-weight: 600;">${s.title}</div>
          </div>
          <p style="font-size: 11px; color: rgba(255,255,255,0.75); margin: 0; line-height: 1.4; flex: 1;">${s.desc}</p>
          <div style="margin-top: 4px;">
            <div style="font-size: 10px; color: #94a3b8; font-weight: 600; margin-bottom: 3px;">Classic Songs:</div>
            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
              ${famousTags}
            </div>
          </div>
          <div style="display: flex; gap: 6px; margin-top: 8px;">
            <button class="btn-apply-singer btn-primary" style="flex: 1; padding: 7px 8px; font-size: 11px; background: linear-gradient(135deg, #d97706, #b45309); border: 1px solid #f59e0b;">
              ⚡ Apply Singer Vinyl
            </button>
            ${s.id === 'sinn_sisamouth' ? `
            <button class="btn-play-singer-demo btn-secondary" style="padding: 7px 10px; font-size: 11px; background: #451a03; border: 1px solid #d97706; color: #fbbf24; font-weight: 600; white-space: nowrap;">
              ▶️ Play Demo
            </button>` : ''}
          </div>
        `;

        const applyBtn = card.querySelector('.btn-apply-singer');
        if (applyBtn) {
          applyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            state.artistName = `${s.name_km} (${s.name_en})`;
            state.songTitle = s.defaultSong;
            applyKhmerTemplate(s.templateId);
            showToast('🎙️ Singer Preset Applied', `${s.name_km} — 33⅓ RPM Vinyl Ready!`, 'success', 4000);
          });
        }

        const demoBtn = card.querySelector('.btn-play-singer-demo');
        if (demoBtn) {
          demoBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const btnSini = document.getElementById('btn-load-sinisamut');
            if (btnSini) btnSini.click();
            if (modalKhmer) modalKhmer.style.display = 'none';
          });
        }

        card.addEventListener('click', () => {
          state.artistName = `${s.name_km} (${s.name_en})`;
          state.songTitle = s.defaultSong;
          applyKhmerTemplate(s.templateId);
        });

        gridKhmer.appendChild(card);
      });
      return;
    }

    // Default template rendering
    const list = categoryFilter === 'all' 
      ? KHMER_TEMPLATES 
      : KHMER_TEMPLATES.filter(x => x.category === categoryFilter);

    // If 'all' is selected, prepend a golden recommendation banner for the 11 Golden Era singers
    if (categoryFilter === 'all') {
      const banner = document.createElement('div');
      banner.style.cssText = 'grid-column: 1 / -1; background: linear-gradient(90deg, rgba(217, 119, 6, 0.25), rgba(120, 53, 15, 0.15)); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px;';
      banner.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
          <span style="font-size: 24px;">🎙️</span>
          <div>
            <div style="font-size: 13px; font-weight: 700; color: #fbbf24; font-family: 'Kantumruy Pro', sans-serif;">តារាចម្រៀងខ្មែរ យុគមាស ឆ្នាំ៦០-៧០ (11 Cambodian Golden Era Legends)</div>
            <div style="font-size: 11px; color: rgba(255,255,255,0.7);">Sinn Sisamouth, Ros Sereysothea, Pen Ran, Mao Sareth, Meas Samon, Drakkar & more</div>
          </div>
        </div>
        <button id="btn-banner-view-singers" class="btn-primary" style="padding: 6px 12px; font-size: 11px; background: #d97706; border-color: #f59e0b; white-space: nowrap; font-weight: 600;">
          View 11 Legends →
        </button>
      `;
      gridKhmer.appendChild(banner);

      const btnViewSingers = banner.querySelector('#btn-banner-view-singers');
      if (btnViewSingers && tabsKhmer) {
        btnViewSingers.addEventListener('click', () => {
          const singerTab = tabsKhmer.querySelector('[data-cat="singers"]');
          if (singerTab) singerTab.click();
        });
      }
    }

    list.forEach(t => {
      const card = document.createElement('div');
      card.className = 'khmer-card';
      card.dataset.id = t.id;
      if (state.palette === t.palette && state.theme === t.theme) {
        card.classList.add('active-template');
      }

      card.innerHTML = `
        <div style="height: 60px; border-radius: 6px; background: ${t.gradient}; display: flex; align-items: flex-end; padding: 8px 10px; position: relative; overflow: hidden; box-shadow: inset 0 -15px 25px rgba(0,0,0,0.5);">
          <span style="position: absolute; top: 6px; right: 8px; font-size: 9px; font-weight: 700; color: #fbbf24; background: rgba(0,0,0,0.65); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(251,191,36,0.3);">${t.badge}</span>
          <span style="font-size: 10px; color: rgba(255,255,255,0.9); font-weight: 600; text-shadow: 0 1px 3px rgba(0,0,0,0.8);">${t.category}</span>
        </div>
        <div style="margin-top: 2px;">
          <h4 style="font-size: 13px; font-weight: 700; color: #fff; margin: 0; font-family: 'Kantumruy Pro', sans-serif;">${t.title_km}</h4>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 1px;">${t.title_en}</div>
        </div>
        <p style="font-size: 11px; color: rgba(255,255,255,0.7); margin: 0; line-height: 1.4; flex: 1;">${t.desc}</p>
        <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px;">
          <span class="khmer-pill">🎨 ${t.palette.replace('_', ' ')}</span>
          <span class="khmer-pill">📐 ${t.theme.replace('_', ' ')}</span>
          <span class="khmer-pill">🎤 ${t.lyricStyle}</span>
        </div>
        <div style="font-size: 10px; color: #fbbf24; opacity: 0.9; margin-top: 2px;">
          <strong>Best For:</strong> ${t.bestFor}
        </div>
        <button class="btn-primary" style="margin-top: 6px; padding: 6px; font-size: 11px; background: linear-gradient(135deg, #d97706, #b45309); border: 1px solid #f59e0b; width: 100%;">
          ⚡ Apply Template
        </button>
      `;

      card.addEventListener('click', () => {
        applyKhmerTemplate(t.id);
      });

      gridKhmer.appendChild(card);
    });
  }

  // Category filter tabs
  if (tabsKhmer) {
    tabsKhmer.querySelectorAll('.khmer-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        tabsKhmer.querySelectorAll('.khmer-tab').forEach(x => x.classList.remove('active'));
        tab.classList.add('active');
        renderKhmerGrid(tab.dataset.cat);
      });
    });
  }

  // ============ Lyrics Visibility & Overlay Controls ============
  function setLyricsVisibility(show, notify = true) {
    state.showLyrics = show;
    const overlayBtn = document.getElementById('btn-toggle-lyrics-overlay');
    const overlayIcon = document.getElementById('toggle-lyrics-icon');
    const overlayText = document.getElementById('toggle-lyrics-text');
    const propIcon = document.getElementById('prop-toggle-lyrics-icon');
    const propText = document.getElementById('prop-toggle-lyrics-text');
    const styleSelect = document.getElementById('select-lyric-style');

    if (show) {
      if (overlayBtn) {
        overlayBtn.style.background = 'rgba(16, 185, 129, 0.15)';
        overlayBtn.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        overlayBtn.style.color = '#10b981';
      }
      if (overlayIcon) overlayIcon.textContent = '👁️';
      if (overlayText) overlayText.textContent = 'Lyrics: ON';
      if (propIcon) propIcon.textContent = '👁️';
      if (propText) { propText.textContent = 'Visible'; propText.style.color = '#10b981'; }
      if (styleSelect && styleSelect.value === 'none') {
        styleSelect.value = state.lastLyricStyle || 'karaoke';
        state.lyricStyle = styleSelect.value;
      }
      if (notify) showToast('Lyrics Overlay', 'Lyrics visible on stage video', 'success', 2500);
    } else {
      if (overlayBtn) {
        overlayBtn.style.background = 'rgba(255, 255, 255, 0.05)';
        overlayBtn.style.borderColor = 'var(--border-color)';
        overlayBtn.style.color = 'var(--text-muted)';
      }
      if (overlayIcon) overlayIcon.textContent = '👁️‍🗨️';
      if (overlayText) overlayText.textContent = 'Lyrics: OFF';
      if (propIcon) propIcon.textContent = '👁️‍🗨️';
      if (propText) { propText.textContent = 'Hidden'; propText.style.color = 'var(--text-muted)'; }
      if (notify) showToast('Lyrics Overlay', 'Lyrics hidden from stage video', 'info', 2500);
    }
  }

  const btnToggleLyricsOverlay = document.getElementById('btn-toggle-lyrics-overlay');
  if (btnToggleLyricsOverlay) {
    btnToggleLyricsOverlay.addEventListener('click', () => {
      setLyricsVisibility(!state.showLyrics);
    });
  }

  const btnToggleLyricsProp = document.getElementById('btn-toggle-lyrics-prop');
  if (btnToggleLyricsProp) {
    btnToggleLyricsProp.addEventListener('click', () => {
      setLyricsVisibility(!state.showLyrics);
    });
  }

  if (selectLyricStyle) {
    selectLyricStyle.value = state.lyricStyle || 'karaoke';
    selectLyricStyle.addEventListener('change', (e) => {
      state.lyricStyle = e.target.value;
      if (e.target.value === 'none') {
        setLyricsVisibility(false, false);
      } else {
        state.lastLyricStyle = e.target.value;
        setLyricsVisibility(true, false);
      }
      const label = selectLyricStyle.options[selectLyricStyle.selectedIndex]?.text || e.target.value;
      showToast('Lyric Style', `Active: ${label}`, 'info', 2000);
    });
  }

  // Teleprompter Collapse / Expand Toggle
  const btnToggleTeleprompter = document.getElementById('btn-toggle-teleprompter');
  const teleprompterEl = document.getElementById('lyrics-teleprompter');
  let teleprompterVisible = true;
  if (btnToggleTeleprompter && teleprompterEl) {
    btnToggleTeleprompter.addEventListener('click', () => {
      teleprompterVisible = !teleprompterVisible;
      if (teleprompterVisible) {
        teleprompterEl.style.display = 'flex';
        btnToggleTeleprompter.textContent = '👁️ Hide';
        btnToggleTeleprompter.style.color = 'var(--text-muted)';
      } else {
        teleprompterEl.style.display = 'none';
        btnToggleTeleprompter.textContent = '👁️ Show';
        btnToggleTeleprompter.style.color = 'var(--accent)';
      }
    });
  }

  // Clear Lyrics Button
  const btnClearLyrics = document.getElementById('btn-clear-lyrics');
  if (btnClearLyrics) {
    btnClearLyrics.addEventListener('click', () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('Lyrics Empty', 'No lyrics are currently loaded', 'info', 2500);
        return;
      }
      state.lyrics = [];
      renderLyricsTeleprompter([]);
      const btnTranscribe = document.getElementById('btn-transcribe-ai');
      if (btnTranscribe) clearButtonLoading(btnTranscribe, '🎤 Auto-Sync Lyrics (AI)');
      showToast('Lyrics Cleared', 'Loaded lyrics have been removed from studio', 'info', 3000);
    });
  }

  // ============ Synced Lyrics Teleprompter ============
  function renderLyricsTeleprompter(lyrics) {
    const el = document.getElementById('lyrics-teleprompter');
    const badge = document.getElementById('lyrics-count-badge');
    if (!el) return;
    if (!lyrics || lyrics.length === 0) {
      el.innerHTML = '<div class="teleprompter-empty" style="color: var(--text-muted); text-align: center; padding: 12px 0;">No lyrics loaded yet</div>';
      if (badge) badge.textContent = '0 Lines';
      return;
    }

    if (badge) badge.textContent = `${lyrics.length} Lines`;
    el.innerHTML = '';

    lyrics.forEach((line, index) => {
      const item = document.createElement('div');
      item.className = 'teleprompter-line';
      item.dataset.index = index;
      item.dataset.start = line.start;
      item.dataset.end = line.end;
      item.style.cssText = 'display: flex; align-items: baseline; gap: 8px; padding: 5px 8px; border-radius: 4px; cursor: pointer; transition: all 0.15s ease; border-left: 2px solid transparent; user-select: none;';
      item.innerHTML = `<span style="font-family: monospace; font-size: 10px; color: var(--accent); opacity: 0.85; white-space: nowrap;">[${formatTime(line.start)}]</span> <span style="flex: 1; line-height: 1.4; font-family: 'Kantumruy Pro', 'Khmer OS Battambang', 'Leelawadee UI', 'Khmer UI', sans-serif;">${line.text}</span>`;
      
      item.addEventListener('mouseenter', () => {
        if (!item.classList.contains('active')) {
          item.style.background = 'rgba(255, 255, 255, 0.06)';
        }
      });
      item.addEventListener('mouseleave', () => {
        if (!item.classList.contains('active')) {
          item.style.background = 'transparent';
        }
      });

      item.addEventListener('click', () => {
        if (audioPlayer) {
          audioPlayer.currentTime = line.start;
          if (audioPlayer.paused) {
            initAudioContext(audioPlayer, () => startVisualizer());
            audioPlayer.play().then(() => {
              state.isPlaying = true;
              if (btnPlayPause) btnPlayPause.textContent = "⏸";
            }).catch(() => {});
          }
          showToast('Jump to Lyric', `[${formatTime(line.start)}] "${line.text.substring(0, 30)}..."`, 'info', 1500);
        }
      });

      el.appendChild(item);
    });
  }

  // Initialize empty teleprompter state safely
  renderLyricsTeleprompter(state.lyrics);

  function updateTeleprompterHighlight(currentTime) {
    const el = document.getElementById('lyrics-teleprompter');
    if (!el || !state.lyrics || state.lyrics.length === 0) return;
    const lines = el.querySelectorAll('.teleprompter-line');
    lines.forEach((item) => {
      const start = parseFloat(item.dataset.start);
      const end = parseFloat(item.dataset.end);
      if (currentTime >= start - 0.25 && currentTime <= end + 0.35) {
        if (!item.classList.contains('active')) {
          item.classList.add('active');
          item.style.background = 'rgba(14, 165, 233, 0.2)';
          item.style.borderLeft = '3px solid var(--accent)';
          item.style.color = '#ffffff';
          item.style.fontWeight = '600';
          item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        if (item.classList.contains('active')) {
          item.classList.remove('active');
          item.style.background = 'transparent';
          item.style.borderLeft = '2px solid transparent';
          item.style.color = '';
          item.style.fontWeight = 'normal';
        }
      }
    });
  }

  // ============ Timeline Scrubber & Timecode ============
  const timecodeEl = document.querySelector('.timecode');
  const durationEl = document.getElementById('duration-display');
  const scrubber = document.getElementById('timeline-scrubber');
  const progressFill = document.getElementById('timeline-progress');

  if (audioPlayer) {
    const syncDuration = () => {
      if (durationEl && audioPlayer.duration && !isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
        durationEl.textContent = `/ ${formatTime(audioPlayer.duration)}`;
      }
    };
    audioPlayer.addEventListener('loadedmetadata', syncDuration);
    audioPlayer.addEventListener('durationchange', syncDuration);
    audioPlayer.addEventListener('canplay', syncDuration);

    audioPlayer.addEventListener('play', () => {
      state.isPlaying = true;
      if (btnPlayPause) btnPlayPause.textContent = "⏸";
    });
    audioPlayer.addEventListener('pause', () => {
      state.isPlaying = false;
      if (btnPlayPause) btnPlayPause.textContent = "▶";
    });
    audioPlayer.addEventListener('ended', () => {
      state.isPlaying = false;
      if (btnPlayPause) btnPlayPause.textContent = "▶";
      if (scrubber) scrubber.value = 0;
      if (progressFill) progressFill.style.width = '0%';
      if (timecodeEl) timecodeEl.textContent = '00:00:00:00';
    });

    audioPlayer.addEventListener('timeupdate', () => {
      if (!audioPlayer.duration) return;
      
      const percent = (audioPlayer.currentTime / audioPlayer.duration) * 100;
      if (scrubber && progressFill) {
        scrubber.value = percent;
        progressFill.style.width = `${percent}%`;
      }

      const t = audioPlayer.currentTime;
      const h = Math.floor(t / 3600);
      const m = Math.floor((t % 3600) / 60);
      const s = Math.floor(t % 60);
      const f = Math.floor((t % 1) * 60);
      
      if (timecodeEl) {
        timecodeEl.textContent = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}:${f.toString().padStart(2, '0')}`;
      }

      updateTeleprompterHighlight(t);
    });
  }

  if (scrubber && audioPlayer) {
    scrubber.addEventListener('input', (e) => {
       if (audioPlayer.duration) {
         const seekTime = (parseFloat(e.target.value) / 100) * audioPlayer.duration;
         audioPlayer.currentTime = seekTime;
         updateTeleprompterHighlight(seekTime);
       }
    });
  }

  // ============ Centralized Audio Track Loader ============
  function loadAudioTrack({ src, serverPath, filename, title, artist, duration = null, lyrics = [], autoPlay = true }) {
    if (!audioPlayer) return;

    // 1. Reset current player state
    try {
      audioPlayer.pause();
    } catch(e) {}
    audioPlayer.currentTime = 0;

    // 2. Set source and force load
    const finalSrc = src.startsWith('blob:') ? src : encodeURI(src);
    audioPlayer.src = finalSrc;
    try {
      audioPlayer.load();
    } catch(e) {}

    // 3. Update application state
    state.audioUrl = finalSrc;
    state.audioPath = filename || 'audio.mp3';
    state.audioServerPath = serverPath || '';
    state.songTitle = title || filename || 'VIDA Project';
    state.artistName = artist || 'Official Audio';
    state.lyrics = lyrics || [];
    renderLyricsTeleprompter(state.lyrics);
    window.__VIDA_SERVER_PATH = serverPath || '';

    // Cache in sessionStorage for hot-reload persistence
    try {
      sessionStorage.setItem('vida_audio_src', finalSrc);
      sessionStorage.setItem('vida_audio_time', '0');
      sessionStorage.setItem('vida_audio_server_path', serverPath || '');
    } catch(e) {}

    // 4. Update UI displays immediately
    if (timecodeEl) timecodeEl.textContent = '00:00:00:00';
    if (scrubber) scrubber.value = 0;
    if (progressFill) progressFill.style.width = '0%';
    
    const titleEl = document.querySelector('.project-title');
    if (titleEl) {
      titleEl.textContent = `Project: ${state.songTitle}${artist ? ' — ' + artist : ''}`;
    }
    syncTitleInputs();

    if (duration && durationEl) {
      durationEl.textContent = `/ ${formatTime(duration)}`;
    }

    // 5. Autoplay if requested
    if (autoPlay) {
      initAudioContext(audioPlayer, () => startVisualizer());
      audioPlayer.play().then(() => {
        state.isPlaying = true;
        if (btnPlayPause) btnPlayPause.textContent = "⏸";
      }).catch(() => {
        state.isPlaying = false;
        if (btnPlayPause) btnPlayPause.textContent = "▶";
        showToast('Playback Ready', 'Click ▶ or spacebar to start audio', 'info', 2500);
      });
    } else {
      state.isPlaying = false;
      if (btnPlayPause) btnPlayPause.textContent = "▶";
    }
  }

  // ============ Audio Dropzone (Click + Drag-and-Drop) ============
  const dropzone = document.getElementById('audio-dropzone');
  const audioFileInput = document.getElementById('audio-file-input');

  if (dropzone && audioFileInput) {
    dropzone.addEventListener('click', () => audioFileInput.click());

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('drag-over');
    });
    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('drag-over');
    });
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) {
        loadAudioFile(file);
      }
    });
  }

  if (audioFileInput && audioPlayer) {
    audioFileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) loadAudioFile(file);
    });
  }

  // Shared audio loading function
  async function loadAudioFile(file) {
    const url = URL.createObjectURL(file);
    const baseName = file.name.replace(/\.[^/.]+$/, '');
    showToast('Audio Loaded', `"${file.name}" ready to play`, 'success');

    loadAudioTrack({
      src: url,
      serverPath: null,
      filename: file.name,
      title: baseName,
      artist: 'Local Track',
      autoPlay: true
    });

    // Upload to server then auto-run Smart Pipeline
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await res.json();
      state.audioServerPath = data.saved_path;
      window.__VIDA_SERVER_PATH = data.saved_path;
      try {
        sessionStorage.setItem('vida_audio_server_path', data.saved_path);
      } catch(e) {}
      
      // 🧠 Smart Pipeline: auto-analyze + auto-lyrics
      runSmartPipeline();
    } catch (err) {
      console.error("Upload failed:", err);
    }
  }

  // ============ 🧠 SMART STUDIO AI PIPELINE ============
  async function runSmartPipeline() {
    if (!state.audioServerPath) return;
    
    // Lock pipeline — prevents hot-reloader from refreshing mid-pipeline
    window.__VIDA_PIPELINE_RUNNING = true;
    window.__VIDA_SERVER_PATH = state.audioServerPath;
    
    const btnAnalyze = document.getElementById('btn-run-deep-audit');
    const btnTranscribe = document.getElementById('btn-transcribe-ai');
    const selectTheme = document.getElementById('select-theme');
    const selectPalette = document.getElementById('select-palette');

    // ── Step 1: Audio DNA Analysis ──
    showToast('🧠 Smart Studio', 'Step 1/3: Analyzing audio DNA...', 'info', 6000);
    if (btnAnalyze) setButtonLoading(btnAnalyze, 'AI Scanning...');
    
    try {
      const analyzeRes = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_path: state.audioServerPath })
      });
      const analyzeData = await analyzeRes.json();
      
      if (analyzeData.status === 'success' || analyzeData.status === 'fallback') {
        // Update stats
        const bpmEl = document.getElementById('stat-bpm');
        const energyEl = document.getElementById('stat-energy');
        if (bpmEl) bpmEl.textContent = analyzeData.bpm;
        if (energyEl) {
          let label = 'Medium';
          if (analyzeData.energy >= 0.75) label = 'High';
          if (analyzeData.energy <= 0.4) label = 'Low';
          energyEl.textContent = label;
        }
        
        // Update duration display from audio analysis if audioPlayer duration is not yet available
        if (analyzeData.duration) {
          state.audioDuration = analyzeData.duration;
          if (durationEl) {
            durationEl.textContent = `/ ${formatTime(analyzeData.duration)}`;
          }
        }

        // Draw waveform
        if (analyzeData.waveform_peaks && analyzeData.waveform_peaks.length > 0) {
          drawWaveform(analyzeData.waveform_peaks);
        }

        // Save to state
        state.bpm = analyzeData.bpm;
        state.energy = analyzeData.energy;
        state.mood = analyzeData.mood;
        state.genre = analyzeData.genre;
        state.sections = analyzeData.sections || [];
        if (analyzeData.hook) {
          state.hookStart = analyzeData.hook.start;
          state.hookEnd = analyzeData.hook.end;
          state.hookName = analyzeData.hook.name;
        }
        
        if (btnAnalyze) clearButtonLoading(btnAnalyze, '✅ Analysis Complete');
        showToast('✅ Audio DNA', `BPM: ${analyzeData.bpm} | Energy: ${Math.round(analyzeData.energy * 100)}% | Mood: ${analyzeData.mood}`, 'success', 4000);

        // ── Step 2: Smart Theme & Palette ──
        showToast('🧠 Smart Studio', 'Step 2/3: Selecting best visual style...', 'info', 3000);
        const rec = getSmartRecommendation(analyzeData.mood, analyzeData.genre, analyzeData.energy);
        state.theme = rec.theme;
        state.palette = rec.palette;
        if (selectTheme) selectTheme.value = rec.theme;
        if (selectPalette) selectPalette.value = rec.palette;
        
        const themeName = selectTheme ? selectTheme.options[selectTheme.selectedIndex]?.text : rec.theme;
        const paletteName = selectPalette ? selectPalette.options[selectPalette.selectedIndex]?.text : rec.palette;
        showToast('🎨 Auto-Style', `Theme: ${themeName} | Palette: ${paletteName}`, 'success', 3000);
      }
    } catch (err) {
      console.error('Smart Pipeline - Analysis failed:', err);
      if (btnAnalyze) clearButtonLoading(btnAnalyze, '🧠 SuperSmart Scan');
    }

    // ── Step 3: Auto Lyrics with Live Percentage ──
    if (state.lyrics && state.lyrics.length > 0) {
      if (btnTranscribe) clearButtonLoading(btnTranscribe, '✅ Lyrics Synced!');
      showToast('🎤 Lyrics Ready', `${state.lyrics.length} lines synced from captions`, 'success', 4000);
      renderLyricsTeleprompter(state.lyrics);
    } else {
      showToast('🧠 Smart Studio', 'Step 3/3: Transcribing vocals with Whisper AI...', 'info', 8000);
      const langSelect = document.getElementById('select-vocal-lang');
      const modelSelect = document.getElementById('select-whisper-model');
      let targetLang = langSelect ? langSelect.value : 'auto';
      if (targetLang === 'auto') {
        targetLang = (/[\u1780-\u17FF]/.test(state.audioPath || '') || /[\u1780-\u17FF]/.test(state.audioServerPath || '')) ? 'km' : null;
      }
      const targetModel = modelSelect ? modelSelect.value : 'base';
      try {
        await runAITranscription({ targetLang, targetModel });
      } catch (err) {
        console.error('Smart Pipeline - Lyrics failed:', err);
      }
    }

    // ── Pipeline Complete ──
    window.__VIDA_PIPELINE_RUNNING = false;
    showToast('🚀 Studio Ready', 'Audio analyzed, styled, and synced — ready to create!', 'success', 5000);
  }

  // ============ Image Upload Handling (Background & Logo) ============
  const btnBg = document.getElementById('btn-upload-bg');
  const inputBg = document.getElementById('bg-file-input');
  if (btnBg && inputBg) {
    btnBg.addEventListener('click', () => inputBg.click());
    inputBg.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const url = URL.createObjectURL(file);
        state.backgroundImageUrl = url;
        const img = new Image();
        img.src = url;
        state.bgImageObj = img;
        btnBg.classList.add('active');
        btnBg.innerHTML = `<span class="icon">🖼️</span> ${file.name.substring(0, 20)}`;
        showToast('Background Set', `Using "${file.name}"`, 'success', 2000);
      }
    });
  }

  const btnLogo = document.getElementById('btn-upload-logo');
  const inputLogo = document.getElementById('logo-file-input');
  if (btnLogo && inputLogo) {
    btnLogo.addEventListener('click', () => inputLogo.click());
    inputLogo.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const url = URL.createObjectURL(file);
        state.logoImageUrl = url;
        const img = new Image();
        img.src = url;
        state.logoImageObj = img;
        btnLogo.classList.add('active');
        btnLogo.innerHTML = `<span class="icon">🎨</span> ${file.name.substring(0, 20)}`;
        showToast('Logo Set', `Using "${file.name}"`, 'success', 2000);
      }
    });
  }

  // ============ YouTube Downloader ============
  const btnDownloadYt = document.getElementById('btn-download-yt');
  const inputYt = document.getElementById('youtube-url-input');
  const btnPasteYt = document.getElementById('btn-paste-yt');
  
  if (btnPasteYt && inputYt) {
    btnPasteYt.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          inputYt.value = text.trim();
        }
      } catch (err) {
        showToast('Paste Failed', 'Clipboard access denied or empty.', 'error');
      }
    });
  }

  if (btnDownloadYt && inputYt && audioPlayer) {
    btnDownloadYt.addEventListener('click', async () => {
      const url = inputYt.value.trim();
      if (!url) return;
      
      try {
        setButtonLoading(btnDownloadYt, '⏳');
        showToast('Downloading', 'Extracting audio from YouTube...', 'info', 8000);

        const res = await fetch('/api/youtube', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url })
        });
        
        const data = await res.json();
        if (data.status === 'success') {
          showToast('Download Complete', `"${data.title}" loaded successfully`, 'success');

          loadAudioTrack({
            src: data.audio_url,
            serverPath: data.audio_path,
            filename: data.filename,
            title: data.title,
            artist: data.artist,
            duration: data.duration,
            lyrics: data.lyrics || [],
            autoPlay: true
          });

          // 🧠 Smart Pipeline: auto-analyze + auto-lyrics
          runSmartPipeline();
          
        } else {
          showToast('Download Failed', data.detail || 'Could not extract audio', 'error');
        }
      } catch (err) {
        console.error("YouTube download failed:", err);
        showToast('Network Error', 'Failed to reach backend', 'error');
      } finally {
        clearButtonLoading(btnDownloadYt, '⬇️ DL');
      }
    });
  }

  // ============ Load Synth Demo ============
  const btnLoadDemo = document.getElementById('btn-load-demo');
  if (btnLoadDemo && audioPlayer) {
    btnLoadDemo.addEventListener('click', async () => {
      try {
        setButtonLoading(btnLoadDemo, 'Loading...');
        const res = await fetch('/api/demo');
        const data = await res.json();
        
        loadAudioTrack({
          src: data.audio_url,
          serverPath: data.audio_path,
          filename: 'demo_synthwave.wav',
          title: data.title,
          artist: data.artist,
          duration: data.duration,
          lyrics: data.lyrics || [],
          autoPlay: true
        });
        
        // Update stats
        const bpmEl = document.getElementById('stat-bpm');
        const energyEl = document.getElementById('stat-energy');
        if (bpmEl) bpmEl.textContent = data.bpm;
        if (energyEl) energyEl.textContent = data.energy >= 0.75 ? 'High' : 'Medium';

        showToast('Demo Loaded', `"${data.title}" — Ready to play!`, 'success');
        
      } catch (err) {
        console.error(err);
        showToast('Demo Error', 'Failed to load demo track', 'error');
      } finally {
        clearButtonLoading(btnLoadDemo, '⚡ Load Synth Demo');
      }
    });
  }

  // ============ Load Sinn Sisamouth 60s Golden Era Demo ============
  const btnLoadSinisamut = document.getElementById('btn-load-sinisamut');
  if (btnLoadSinisamut && audioPlayer) {
    btnLoadSinisamut.addEventListener('click', async () => {
      try {
        setButtonLoading(btnLoadSinisamut, 'Loading 60s Vinyl...');
        const res = await fetch('/api/demo/sinisamut');
        const data = await res.json();
        
        loadAudioTrack({
          src: data.audio_url,
          serverPath: data.audio_path,
          filename: 'demo_sinisamut.wav',
          title: data.title,
          artist: data.artist,
          duration: data.duration,
          lyrics: data.lyrics || [],
          autoPlay: true
        });

        // Apply 60s Vinyl Template
        applyKhmerTemplate('vinyl_60s', false);

        // Update stats
        const bpmEl = document.getElementById('stat-bpm');
        const energyEl = document.getElementById('stat-energy');
        if (bpmEl) bpmEl.textContent = data.bpm;
        if (energyEl) energyEl.textContent = 'Golden 60s';

        showToast('📻 ស៊ីន ស៊ីសាមុត Loaded!', `"${data.title}" — 33⅓ RPM Vinyl Playing`, 'success', 5000);
        
      } catch (err) {
        console.error(err);
        showToast('Demo Error', 'Failed to load Sinn Sisamouth track', 'error');
      } finally {
        clearButtonLoading(btnLoadSinisamut, '📻 ស៊ីន ស៊ីសាមុត Demo (60s Vinyl)');
      }
    });
  }

  // ============ SuperSmart AI Analyze ============
  const btnAnalyze = document.getElementById('btn-run-deep-audit');
  if (btnAnalyze) {
    btnAnalyze.addEventListener('click', async () => {
      if (!state.audioServerPath) {
        showToast('No Audio', 'Please load an audio file first!', 'error');
        return;
      }
      try {
        setButtonLoading(btnAnalyze, 'Scanning DNA...');
        const res = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audio_path: state.audioServerPath })
        });
        const data = await res.json();
        
        if (data.status === 'success' || data.status === 'fallback') {
          const bpmEl = document.getElementById('stat-bpm');
          const energyEl = document.getElementById('stat-energy');
          
          if (bpmEl) bpmEl.textContent = data.bpm;
          if (energyEl) {
            let energyLabel = "Medium";
            if (data.energy >= 0.75) energyLabel = "High";
            if (data.energy <= 0.4) energyLabel = "Low";
            energyEl.textContent = energyLabel;
          }
          
          if (data.waveform_peaks && data.waveform_peaks.length > 0) {
             drawWaveform(data.waveform_peaks);
          }
          
          showToast('Analysis Complete', `BPM: ${data.bpm} | Energy: ${Math.round(data.energy * 100)}%`, 'success');
          clearButtonLoading(btnAnalyze, '✅ Analysis Complete');
        } else {
          clearButtonLoading(btnAnalyze, '❌ Analysis Failed');
        }
      } catch (err) {
        console.error(err);
        clearButtonLoading(btnAnalyze, '❌ Analysis Failed');
        showToast('Analysis Error', err.message, 'error');
      }
    });
  }

  // ============ 🎤 AI Transcription Engine with Real-Time Percentage ============
  async function runAITranscription({ targetLang, targetModel }) {
    const btnTranscribe = document.getElementById('btn-transcribe-ai');
    const progressBox = document.getElementById('transcribe-progress-box');
    const progressStatus = document.getElementById('transcribe-progress-status');
    const progressPct = document.getElementById('transcribe-progress-pct');
    const progressFill = document.getElementById('transcribe-progress-fill');

    if (progressBox) progressBox.style.display = 'block';
    if (progressFill) progressFill.style.width = '0%';
    if (progressPct) progressPct.textContent = '0%';
    if (progressStatus) progressStatus.textContent = 'Initializing Whisper AI...';
    if (btnTranscribe) setButtonLoading(btnTranscribe, '⏳ AI 0%');

    let currentPercent = 0;
    let isFinished = false;
    let elapsed = 0;

    // Active polling for real-time Whisper progress & smooth interpolation
    const pollInterval = setInterval(async () => {
      if (isFinished) return;
      elapsed += 0.4;

      try {
        const res = await fetch('/api/transcribe/progress');
        if (res.ok) {
          const data = await res.json();
          if (data && typeof data.percent === 'number' && data.percent > 0) {
            if (data.percent > currentPercent) {
              currentPercent = data.percent;
            }
            if (data.stage && progressStatus) {
              progressStatus.textContent = data.stage;
            }
          }
        }
      } catch (_) {}

      // Smooth percentage crawl so the UI continuously moves and never appears frozen
      if (currentPercent < 22) {
        currentPercent = Math.min(22, Math.floor(elapsed * 1.5));
        if (progressStatus && elapsed > 3 && currentPercent < 20) {
          progressStatus.textContent = `Analyzing audio with AI (${Math.round(elapsed)}s)...`;
        }
      } else if (currentPercent < 94) {
        currentPercent = Math.min(94, +(currentPercent + 0.25).toFixed(1));
      }

      const displayPct = Math.floor(currentPercent);
      if (progressPct) progressPct.textContent = `${displayPct}%`;
      if (progressFill) progressFill.style.width = `${displayPct}%`;
      if (btnTranscribe) btnTranscribe.textContent = `⏳ AI ${displayPct}%`;
    }, 400);

    try {
      const res = await fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_path: state.audioServerPath,
          model_size: targetModel,
          language: targetLang
        })
      });
      const data = await res.json();
      isFinished = true;
      clearInterval(pollInterval);

      if (data.status === 'success' && data.lyrics && data.lyrics.length > 0) {
        currentPercent = 100;
        if (progressPct) progressPct.textContent = '100%';
        if (progressFill) progressFill.style.width = '100%';
        if (progressStatus) progressStatus.textContent = '✅ Sync Complete (100%)';
        if (btnTranscribe) clearButtonLoading(btnTranscribe, '✅ Synced 100%');

        state.lyrics = data.lyrics;
        renderLyricsTeleprompter(state.lyrics);
        const src = data.source === 'subtitle' ? 'Captions' : 'Whisper AI';
        showToast('🎤 Lyrics Ready', `${data.count} lines synced from ${src} (100%)`, 'success', 4000);

        setTimeout(() => {
          if (progressBox) progressBox.style.display = 'none';
        }, 4000);
        return data;
      } else {
        if (progressStatus) progressStatus.textContent = '❌ No Lyrics Detected';
        if (btnTranscribe) clearButtonLoading(btnTranscribe, '🎤 Auto-Sync Lyrics (AI)');
        showToast('No Lyrics', 'No vocal segments detected in audio', 'info');
        setTimeout(() => {
          if (progressBox) progressBox.style.display = 'none';
        }, 4000);
        return null;
      }
    } catch (err) {
      isFinished = true;
      clearInterval(pollInterval);
      if (progressStatus) progressStatus.textContent = '❌ Failed';
      if (btnTranscribe) clearButtonLoading(btnTranscribe, '🎤 Auto-Sync Lyrics (AI)');
      showToast('Transcription Error', err.message, 'error');
      setTimeout(() => {
        if (progressBox) progressBox.style.display = 'none';
      }, 4000);
      throw err;
    }
  }

  // ============ AI Whisper Auto-Transcription Click ============
  const btnTranscribe = document.getElementById('btn-transcribe-ai');
  if (btnTranscribe) {
    btnTranscribe.addEventListener('click', async () => {
      if (!state.audioServerPath) {
        showToast('No Audio', 'Please load an audio file first!', 'error');
        return;
      }
      const langSelect = document.getElementById('select-vocal-lang');
      const modelSelect = document.getElementById('select-whisper-model');
      let targetLang = langSelect ? langSelect.value : 'auto';
      if (targetLang === 'auto') {
        targetLang = (/[\u1780-\u17FF]/.test(state.audioPath || '') || /[\u1780-\u17FF]/.test(state.audioServerPath || '')) ? 'km' : null;
      }
      const targetModel = modelSelect ? modelSelect.value : 'base';
      try {
        await runAITranscription({ targetLang, targetModel });
      } catch (err) {
        console.error('Manual transcription failed:', err);
      }
    });
  }

  // ============ Import Subtitles / LRC ============
  const btnUploadLrc = document.getElementById('btn-upload-lrc');
  const inputLrc = document.getElementById('lrc-file-input');
  if (btnUploadLrc && inputLrc) {
    btnUploadLrc.addEventListener('click', () => inputLrc.click());
    inputLrc.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('file', file);

      try {
        showToast('Importing Subtitles', `Parsing ${file.name}...`, 'info', 3000);
        const res = await fetch('/api/lyrics/upload', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.status === 'success' && data.lyrics && data.count > 0) {
          state.lyrics = data.lyrics;
          renderLyricsTeleprompter(state.lyrics);
          showToast('Lyrics Loaded', `Imported ${data.count} lines with word timing`, 'success');
          if (btnTranscribe) clearButtonLoading(btnTranscribe, '✅ Lyrics Synced!');
        } else {
          showToast('Import Error', 'Could not parse lyrics from file', 'error');
        }
      } catch (err) {
        console.error('LRC import failed:', err);
        showToast('Import Failed', err.message, 'error');
      }
    });
  }

  // ============ Export Video ============
  const btnExport = document.getElementById('btn-export');
  if (btnExport) {
    btnExport.addEventListener('click', async () => {
      if (!state.audioServerPath) {
        showToast('No Audio', 'Please load an audio file before exporting', 'error');
        return;
      }

      try {
        setButtonLoading(btnExport, 'Rendering...');
        showToast('Export Started', 'Rendering 60 FPS video — this may take a few minutes', 'info', 15000);

        const res = await fetch('/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            audio_path: state.audioServerPath,
            theme: state.theme,
            palette: state.palette,
            aspect_ratio: state.aspectRatio,
            fps: state.renderFps,
            song_title: state.songTitle,
            artist_name: state.artistName,
            lyrics_data: state.showLyrics === false ? [] : state.lyrics,
            lyric_style: state.showLyrics === false ? "none" : state.lyricStyle,
            bar_count: state.barCount,
            bass_boost: state.bassBoost
          })
        });
        const data = await res.json();
        
        if (data.job_id) {
          state.renderJobId = data.job_id;
          pollRenderProgress(data.job_id);
        }
      } catch (err) {
        clearButtonLoading(btnExport, 'Export Video');
        showToast('Export Error', err.message, 'error');
      }
    });
  }

  function pollRenderProgress(jobId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/progress/${jobId}`);
        const data = await res.json();
        
        const btnExport = document.getElementById('btn-export');
        
        if (data.status === 'completed') {
          clearInterval(interval);
          clearButtonLoading(btnExport, 'Export Video');
          showToast('Export Complete!', 'Your video is ready for download', 'success', 8000);
          
          if (data.output_url) {
            const a = document.createElement('a');
            a.href = data.output_url;
            a.download = '';
            a.click();
          }
        } else if (data.status === 'failed') {
          clearInterval(interval);
          clearButtonLoading(btnExport, 'Export Video');
          showToast('Render Failed', data.error || 'Unknown error', 'error');
        } else {
          const pct = Math.round(data.percent || 0);
          if (btnExport) btnExport.textContent = `Rendering ${pct}%`;
        }
      } catch (e) {
        clearInterval(interval);
      }
    }, 1500);
  }

  // ============ Draw Waveform to Canvas ============
  function drawWaveform(peaks) {
    const canvas = document.getElementById('waveform-canvas');
    if (!canvas || !peaks || peaks.length === 0) return;
    const parent = canvas.parentElement;
    const targetWidth = (parent && parent.clientWidth) ? parent.clientWidth : 800;
    const targetHeight = (parent && parent.clientHeight) ? parent.clientHeight : 48;
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext('2d');
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
    grad.addColorStop(0, "rgba(14, 165, 233, 0.95)");
    grad.addColorStop(1, "rgba(14, 165, 233, 0.2)");
    ctx.fillStyle = grad;
    
    const step = canvas.width / peaks.length;
    
    for (let i = 0; i < peaks.length; i++) {
      const p = peaks[i];
      const h = Math.max(2, p * (canvas.height * 0.9)); 
      const x = i * step;
      ctx.fillRect(x, canvas.height - h, Math.max(1, step - 0.5), h);
    }
  }

});
