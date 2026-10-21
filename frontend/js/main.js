import { state, PALETTES } from './core/state.js';
import { initAudioContext, updateVolume, updateEq } from './core/audio.js';
import { initVisualizer, startVisualizer, setPreviewSize, getPreviewSize } from './core/visualizer.js';
import { ensureAudioFeatures } from './core/audio_features.js';
import { KHMER_TEMPLATES, KHMER_SINGERS_60S_70S } from './core/khmer_templates.js';
import { DIRECTOR_PRESETS } from './plugins/director_rules.js';
import { triggerCameraShake, triggerShockwave, triggerBloomFlash } from './plugins/vfx_engine.js';
import { initSRTEditor } from './core/srt_editor.js';
import { initTranslationTrack, loadTranslationForSong, getTranslationRenderOptions } from './core/translation.js';
import { 
  initResizableLayout, 
  toggleLeftPanel, 
  toggleRightPanel, 
  toggleTheaterMode, 
  onLayoutResize 
} from './ui/resizable_layout.js';

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
  const vizCanvas = canvas;
  const audioPlayer = document.getElementById("audio-player");
  const btnPlayPause = document.getElementById("btn-play-pause");
  const volumeSlider = document.getElementById("volume-slider");
  
  // Initialize Visualizer Context
  if (canvas) {
    initVisualizer(canvas);
    startVisualizer();
  }

  // Initialize Studio Resizable Layout System
  initResizableLayout();

  // A backend started on the wrong interpreter silently loses the word aligner and Demucs, which
  // makes sync look broken. Say which engine is missing instead of letting the timings drift quietly.
  (async () => {
    const chip = document.getElementById('studio-engine-chip');
    if (!chip) return;
    try {
      const info = await (await fetch('/api/health')).json();
      if (info.sync_grade === 'word') return;
      const missing = (info.word_aligner && info.word_aligner.missing) ||
                      (info.vocal_separator && info.vocal_separator.missing);
      chip.style.display = 'inline-block';
      chip.textContent = info.sync_grade === 'phrase' ? 'Phrase sync only' : 'Energy sync only';
      chip.title = missing
        ? `"${missing}" is missing from ${info.python}. Start VIDA with run_vida_desktop.bat so it runs ${info.venv_python || 'the project venv'}.`
        : `Sync is running with reduced engines on ${info.python}.`;
    } catch (e) { /* backend unreachable; every other call already reports that */ }
  })();

  // ============ Restore Session & Lyrics Persistence ============
  const cachedLyricsStr = localStorage.getItem('vida_lyrics');
  const cachedTitle = localStorage.getItem('vida_song_title');
  const cachedArtist = localStorage.getItem('vida_artist_name');
  const cachedServerPath = localStorage.getItem('vida_audio_server_path');
  const cachedMetaAudio = localStorage.getItem('vida_meta_audio');

  // Metadata is only trustworthy for the audio it was cached with. A title left behind by a
  // different song (e.g. after a hard refresh) must never label the audio now on screen.
  const metaBelongsToAudio = !cachedServerPath || cachedMetaAudio === cachedServerPath;
  let restoreTitle = metaBelongsToAudio ? (cachedTitle || '') : '';
  let restoreArtist = metaBelongsToAudio ? (cachedArtist || '') : '';
  if (cachedServerPath && !restoreTitle) {
    const fname = decodeURIComponent((cachedServerPath.split(/[\\/]/).pop() || ''));
    restoreTitle = fname.replace(/\.[^.]+$/, '');
    restoreArtist = restoreArtist || 'Unknown';
  }

  if (restoreTitle) {
    state.songTitle = restoreTitle;
    const titleInput = document.getElementById('input-song-title');
    if (titleInput) titleInput.value = restoreTitle;
    try { localStorage.setItem('vida_song_title', restoreTitle); } catch (_) {}
  }
  if (restoreArtist) {
    state.artistName = restoreArtist;
    const artistInput = document.getElementById('input-artist-name');
    if (artistInput) artistInput.value = restoreArtist;
    try { localStorage.setItem('vida_artist_name', restoreArtist); } catch (_) {}
  }
  if (cachedServerPath) {
    state.audioServerPath = cachedServerPath;
    window.__VIDA_SERVER_PATH = cachedServerPath;
    if (restoreTitle) {
      const titleEl = document.querySelector('.project-title');
      if (titleEl) titleEl.textContent = `Project: ${restoreTitle}${restoreArtist ? ' — ' + restoreArtist : ''}`;
    }
  }

  if (cachedLyricsStr) {
    try {
      const parsedLyrics = JSON.parse(cachedLyricsStr);
      const isSpam = Array.isArray(parsedLyrics) && parsedLyrics.some(l => /subscribe|kênh|ghiền mì gõ|la la school|đăng ký/i.test(l.text || ''));
      if (isSpam) {
        localStorage.removeItem('vida_lyrics');
        state.lyrics = [];
      } else if (Array.isArray(parsedLyrics) && parsedLyrics.length > 0) {
        state.lyrics = parsedLyrics;
        renderLyricsTeleprompter(state.lyrics);
        setStudioPipelineProgress(3, 100, `${state.lyrics.length} lines restored (100%)`, 'Lyrics Synced');
      }
    } catch(e) {
      state.lyrics = [];
    }
  } else {
    state.lyrics = [];
  }

  // Auto-refresh authentic synced lyrics from server companion .lrc if available
  if (cachedServerPath) {
    fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio_path: cachedServerPath, force_ai: false })
    }).then(r => r.json()).then(data => {
      if (data && data.status === 'success' && data.lyrics && data.lyrics.length > 0 && data.source === 'subtitle') {
        state.lyrics = data.lyrics;
        try { localStorage.setItem('vida_lyrics', JSON.stringify(data.lyrics)); } catch(_) {}
        renderLyricsTeleprompter(state.lyrics, true);
        setStudioPipelineProgress(3, 100, `${state.lyrics.length} authentic lines loaded (100%)`, 'Lyrics Synced');
      }
    }).catch(() => {});
  }

  // ============ Default VibeTunes Logo Initialization ============
  const defaultLogoUrl = '/uploads/images/vibetunes_logo.png';
  const defaultLogoPath = 'd:\\Project\\VIDA\\uploads\\images\\vibetunes_logo.png';

  const defaultLogoImg = new Image();
  defaultLogoImg.onload = () => {
    state.logoImageObj = defaultLogoImg;
    state.logoImageUrl = defaultLogoUrl;
    state.logoImagePath = defaultLogoPath;
    
    // Update Media Item & Center Badge UI
    const btnLogoEl = document.getElementById('btn-upload-logo');
    if (btnLogoEl) {
      btnLogoEl.classList.add('active');
      btnLogoEl.innerHTML = `<div class="media-item-left"><span class="icon">🎨</span><span class="media-item-title">Logo: VibeTunes</span></div><span class="media-item-badge media-item-badge--ok">Default ✓</span>`;
    }
    const badgeStatusText = document.getElementById('badge-status-text');
    if (badgeStatusText) {
      badgeStatusText.className = 'ui-t ui-t--ok';
      badgeStatusText.textContent = 'VibeTunes Logo Active';
    }
    const btnRemoveLogo = document.getElementById('btn-remove-logo');
    if (btnRemoveLogo) btnRemoveLogo.classList.remove('hidden');
  };
  defaultLogoImg.src = defaultLogoUrl;

  function hasValidAudioSource(player) {
    if (!player || !player.src) return false;
    const s = (player.src || '').trim();
    return s !== '' && s !== window.location.href && s !== 'about:blank' && !s.endsWith('/');
  }

  const savedSrc = sessionStorage.getItem('vida_audio_src') || localStorage.getItem('vida_audio_src');
  const savedTime = parseFloat(sessionStorage.getItem('vida_audio_time') || '0');

  if (savedSrc && savedSrc !== window.location.href && savedSrc !== 'about:blank' && audioPlayer) {
    audioPlayer.src = savedSrc;
    state.audioUrl = savedSrc;
    ensureAudioFeatures(savedSrc).catch(() => {});
    audioPlayer.currentTime = savedTime;
    showToast('Session Restored', 'Audio & lyrics resumed from where you left off', 'info', 2500);
    
    // Auto-play and init visualizer safely
    audioPlayer.play().then(() => {
      state.isPlaying = true;
      if (btnPlayPause) btnPlayPause.textContent = "⏸";
      initAudioContext(audioPlayer, () => startVisualizer());
    }).catch((err) => {
      state.isPlaying = false;
      if (btnPlayPause) btnPlayPause.textContent = "▶";
    });
  }

  // ============ Audio Play/Pause ============
  if (btnPlayPause && audioPlayer) {
    btnPlayPause.addEventListener('click', async () => {
      if (!hasValidAudioSource(audioPlayer)) {
        showToast('No Audio Loaded', 'Please upload or select an audio track first to play', 'info', 3000);
        return;
      }

      initAudioContext(audioPlayer, () => startVisualizer());
      startVisualizer();
      
      if (audioPlayer.paused) {
        try {
          await audioPlayer.play();
          state.isPlaying = true;
          btnPlayPause.textContent = "⏸";
        } catch (err) {
          console.warn('Playback prevented or source unavailable:', err);
          state.isPlaying = false;
          btnPlayPause.textContent = "▶";
        }
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


  // ============ Universal Studio Activity & Progress Bar Helper ============
  function setGlobalProgress(percent, isVisible = true, label = 'Processing') {
    const line = document.getElementById('global-progress-line');
    const fill = document.getElementById('global-progress-fill');
    const headerCapsule = document.getElementById('header-progress-capsule');
    const headerTask = document.getElementById('header-progress-task');
    const headerPct = document.getElementById('header-progress-pct');

    if (!line || !fill) return;
    if (!isVisible) {
      line.style.display = 'none';
      fill.style.width = '0%';
      if (headerCapsule) headerCapsule.style.display = 'none';
      return;
    }
    line.style.display = 'block';
    const clamped = Math.min(100, Math.max(0, Math.round(percent)));
    fill.style.width = `${clamped}%`;

    if (headerCapsule && headerPct) {
      headerCapsule.style.display = 'inline-flex';
      if (headerTask && label) headerTask.textContent = label;
      headerPct.textContent = `${clamped}%`;
    }

    if (clamped >= 100) {
      if (headerCapsule && headerPct) {
        headerPct.textContent = '100% ✓';
      }
      setTimeout(() => {
        line.style.display = 'none';
        fill.style.width = '0%';
        if (headerCapsule) headerCapsule.style.display = 'none';
      }, 1600);
    }
  }

  // ============ Studio Unified Pipeline Progress Card Helper ============
  function setStudioPipelineProgress(stepIndex, percent, stageText, title = 'Smart Studio Pipeline', isVisible = true) {
    const card = document.getElementById('studio-pipeline-card');
    if (!card) return;
    if (!isVisible) {
      card.style.display = 'none';
      return;
    }
    card.style.display = 'block';
    const pctEl = document.getElementById('pipeline-card-pct');
    const fillEl = document.getElementById('pipeline-card-fill');
    const stageEl = document.getElementById('pipeline-card-stage');
    const titleEl = document.getElementById('pipeline-card-title');

    const clamped = Math.min(100, Math.max(0, Math.round(percent)));
    if (pctEl) pctEl.textContent = `${clamped}%`;
    if (fillEl) fillEl.style.width = `${clamped}%`;
    if (stageEl && stageText) stageEl.textContent = stageText;
    if (titleEl && title) titleEl.textContent = title;

    // Highlight active step
    const step1 = document.getElementById('pstep-1');
    const step2 = document.getElementById('pstep-2');
    const step3 = document.getElementById('pstep-3');
    if (step1 && step2 && step3) {
      step1.className = 'pstep' + (stepIndex === 1 ? ' active' : (stepIndex > 1 ? ' done' : ''));
      step2.className = 'pstep' + (stepIndex === 2 ? ' active' : (stepIndex > 2 ? ' done' : ''));
      step3.className = 'pstep' + (stepIndex === 3 ? ' active' : (stepIndex >= 3 && clamped === 100 ? ' done' : ''));
    }

    setGlobalProgress(clamped, true, title);

    if (clamped >= 100 && stepIndex >= 3) {
      setTimeout(() => {
        card.style.display = 'none';
      }, 3000);
    }
  }

  // ============ Panel Toggles & Theater Mode ============
  const btnToggleLeft = document.getElementById('btn-toggle-left-panel');
  const btnToggleRight = document.getElementById('btn-toggle-right-panel');
  const btnFullscreen = document.getElementById('btn-fullscreen-stage');

  if (btnToggleLeft) {
    btnToggleLeft.addEventListener('click', () => {
      toggleLeftPanel();
    });
  }

  if (btnToggleRight) {
    btnToggleRight.addEventListener('click', () => {
      toggleRightPanel();
    });
  }

  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      toggleTheaterMode();
    });
  }

  // ============ Stage Aspect Ratio Tabs (16:9, 9:16, 1:1) ============
  const aspectTabs = document.querySelectorAll('#stage-aspect-tabs button, #btn-aspect-16-9, #btn-aspect-9-16, #btn-aspect-1-1, .aspect-tabs button');
  const canvasWrapper = document.querySelector('.canvas-wrapper');
  const formatBadge = document.querySelector('.project-format-badge');

  function setStageAspectRatio(ratio) {
    state.aspectRatio = ratio;
    
    // 1. Update button active states
    aspectTabs.forEach(b => {
      if (b.dataset.ratio === ratio) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    // 2. Update Canvas Wrapper CSS class
    if (canvasWrapper) {
      canvasWrapper.classList.remove('aspect-16-9', 'aspect-9-16', 'aspect-1-1');
      const classSuffix = ratio.replace(':', '-');
      canvasWrapper.classList.add(`aspect-${classSuffix}`);
    }

    // 3. Update the project (logical) resolution; the preview's backing store
    //    follows the on-screen size (see visualizer.js setPreviewSize)
    if (canvas) {
      if (ratio === '9:16') {
        setPreviewSize(1080, 1920);
      } else if (ratio === '1:1') {
        setPreviewSize(1080, 1080);
      } else {
        setPreviewSize(1920, 1080);
      }
    }

    // 4. Update Project Header Format Badge
    if (formatBadge) {
      const label = ratio === '9:16' ? '1080x1920 (9:16 TikTok/CapCut)' : (ratio === '1:1' ? '1080x1080 (1:1 Square)' : '1080p • 60 FPS (16:9)');
      formatBadge.textContent = label;
    }

    // 5. Notify user
    const friendlyName = ratio === '9:16' ? '9:16 Vertical (CapCut/TikTok/Shorts)' : (ratio === '1:1' ? '1:1 Square (Instagram/Cover)' : '16:9 Landscape (YouTube/Desktop)');
    showToast('Aspect Ratio Changed', friendlyName, 'info', 2000);
  }

  aspectTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const ratio = btn.dataset.ratio || '16:9';
      setStageAspectRatio(ratio);
    });
  });

  // ============ YouTube Auto-Post Details Modal ============
  const btnOpenYtModal = document.getElementById('btn-open-yt-modal');
  const ytDetailsModal = document.getElementById('youtube-details-modal');
  const btnCloseYtDetailsModal = document.getElementById('btn-close-yt-details-modal');
  const btnYtModalCancel = document.getElementById('btn-yt-modal-cancel');
  const btnYtModalSave = document.getElementById('btn-yt-modal-save');
  const btnYtInsertLyrics = document.getElementById('btn-yt-insert-lyrics');
  const inputYtTitle = document.getElementById('yt-modal-title');
  const inputYtDesc = document.getElementById('yt-modal-description');
  const inputYtTags = document.getElementById('yt-modal-tags');
  const selectYtPrivacy = document.getElementById('yt-modal-privacy');
  const topSelectYtPrivacy = document.getElementById('select-youtube-privacy');

  function openYouTubeDetailsModal() {
    if (!ytDetailsModal) return;
    
    if (inputYtTitle) {
      inputYtTitle.value = state.youtubeTitle || `${state.songTitle || 'VIDA Soundscape'}${state.artistName ? ' - ' + state.artistName : ''} (Official Lyric Video)`;
    }
    
    if (inputYtDesc) {
      if (!inputYtDesc.value) {
        inputYtDesc.value = state.youtubeDescription || `🎵 "${state.songTitle || 'Track'}" by ${state.artistName || 'Artist'}\nCreated with VIDA Studio Pro.\n\n#music #lyrics #vibes`;
      }
    }

    if (inputYtTags) {
      inputYtTags.value = state.youtubeTags || `${state.songTitle || 'music'}, ${state.artistName || 'artist'}, khmer music, lyrics, official audio, capcut`;
    }

    if (selectYtPrivacy && topSelectYtPrivacy) {
      selectYtPrivacy.value = topSelectYtPrivacy.value || 'public';
    }

    ytDetailsModal.style.display = 'flex';
  }

  function closeYouTubeDetailsModal() {
    if (ytDetailsModal) ytDetailsModal.style.display = 'none';
  }

  if (btnOpenYtModal) {
    btnOpenYtModal.addEventListener('click', openYouTubeDetailsModal);
  }
  if (btnCloseYtDetailsModal) {
    btnCloseYtDetailsModal.addEventListener('click', closeYouTubeDetailsModal);
  }
  if (btnYtModalCancel) {
    btnYtModalCancel.addEventListener('click', closeYouTubeDetailsModal);
  }

  if (btnYtInsertLyrics) {
    btnYtInsertLyrics.addEventListener('click', () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('No Lyrics Loaded', 'Transcribe or load lyrics first before inserting.', 'warning', 2500);
        return;
      }
      const lyricsBlock = "\n\n--- LYRICS ---\n" + state.lyrics.map(l => l.text).join('\n');
      if (inputYtDesc) {
        inputYtDesc.value = (inputYtDesc.value || '').trim() + lyricsBlock;
        showToast('Lyrics Inserted', `Added ${state.lyrics.length} lines of lyrics into description.`, 'success', 2500);
      }
    });
  }

  if (btnYtModalSave) {
    btnYtModalSave.addEventListener('click', () => {
      state.youtubeTitle = inputYtTitle ? inputYtTitle.value.trim() : '';
      state.youtubeDescription = inputYtDesc ? inputYtDesc.value.trim() : '';
      state.youtubeTags = inputYtTags ? inputYtTags.value.trim() : '';
      if (selectYtPrivacy && topSelectYtPrivacy) {
        topSelectYtPrivacy.value = selectYtPrivacy.value;
      }
      closeYouTubeDetailsModal();
      showToast('YouTube Details Saved', 'Auto-post metadata updated successfully.', 'success', 3000);
    });
  }

  // ============ Top DAW Header Menu Items Wiring ============
  const menuBindings = [
    { id: 'menu-act-open-media', action: () => { const f = document.getElementById('audio-file-input'); if (f) f.click(); } },
    { id: 'menu-act-import-sub', action: () => { const b = document.getElementById('btn-upload-lrc'); if (b) b.click(); } },
    { id: 'menu-act-open-library', action: () => { const b = document.getElementById('btn-open-library'); if (b) b.click(); } },
    { id: 'menu-act-export-capcut', action: () => { const b = document.getElementById('btn-quick-export-capcut'); if (b) b.click(); } },
    { id: 'menu-act-load-demo', action: () => { const b = document.getElementById('btn-load-demo'); if (b) b.click(); } },
    { id: 'menu-act-open-srt', action: () => { const b = document.getElementById('btn-open-srt-editor'); if (b) b.click(); } },
    { id: 'menu-act-ai-spelling', action: () => { const b = document.getElementById('btn-ai-auto-fix'); if (b) b.click(); } },
    { id: 'menu-act-fix-words', action: () => { const b = document.getElementById('btn-autofix-lyrics'); if (b) b.click(); } },
    { id: 'menu-act-verify', action: () => { const b = document.getElementById('btn-verify-lyrics'); if (b) b.click(); } },
    { id: 'menu-act-clear-lyrics', action: () => { const b = document.getElementById('btn-clear-lyrics'); if (b) b.click(); } },
    { id: 'menu-act-ai-gemini', action: () => {
        const m = document.getElementById('select-whisper-model');
        if (m) m.value = 'gemini-fast';
        showToast('AI Model Selected', 'Gemini Cloud AI (Fast & Accurate)', 'info', 2500);
      }
    },
    { id: 'menu-act-ai-whisper', action: () => {
        const m = document.getElementById('select-whisper-model');
        if (m) m.value = 'large-v3-turbo';
        showToast('AI Model Selected', 'Whisper Large-v3 Turbo', 'info', 2500);
      }
    },
    { id: 'menu-act-ai-qwen', action: () => {
        const m = document.getElementById('select-whisper-model');
        if (m) m.value = 'qwen3-khmer';
        showToast('AI Model Selected', '🇰🇭 Qwen3-ASR Khmer Singing', 'info', 2500);
      }
    },
    { id: 'menu-act-toggle-demucs', action: () => {
        const chk = document.getElementById('check-use-demucs');
        if (chk) {
          chk.checked = !chk.checked;
          showToast('Demucs Stem Isolation', chk.checked ? 'Enabled (Isolates singing voice)' : 'Disabled', 'info', 2500);
        }
      }
    },
    { id: 'menu-act-render-video', action: () => { const b = document.getElementById('btn-export'); if (b) b.click(); } },
    { id: 'menu-act-yt-details', action: () => openYouTubeDetailsModal() },
    { id: 'menu-act-khmer-templates', action: () => { const b = document.getElementById('btn-open-khmer-templates'); if (b) b.click(); } },
    { id: 'menu-act-shortcuts', action: () => {
        showToast('⌨Keyboard Shortcuts', 'Space: Play/Pause | Scrubber: Jump | Click Lyric: Seek to Line', 'info', 5000);
      }
    },
    { id: 'menu-act-about', action: () => {
        showToast('VIDA Studio Pro', 'Next-Gen 60 FPS Visualizer & AI Subtitle Studio with CapCut Export.', 'info', 4000);
      }
    }
  ];

  menuBindings.forEach(({ id, action }) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.nav-menu-item').forEach(m => m.classList.remove('active'));
        action();
      });
    }
  });

  document.querySelectorAll('.menu-trigger-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const parent = btn.closest('.nav-menu-item');
      const wasActive = parent && parent.classList.contains('active');
      document.querySelectorAll('.nav-menu-item').forEach(m => m.classList.remove('active'));
      if (!wasActive && parent) parent.classList.add('active');
    });
  });

  document.addEventListener('click', () => {
    document.querySelectorAll('.nav-menu-item').forEach(m => m.classList.remove('active'));
  });

  // Redraw waveform when layout dimensions resize
  onLayoutResize(() => {
    if (window.__VIDA_AUDIO_PEAKS) {
      drawWaveform(window.__VIDA_AUDIO_PEAKS);
    }
  });

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

  // ============ LLM Chat Box & Lyrics Aligner ============
  const llmInput = document.getElementById('input-ai-prompt') || document.querySelector('.llm-input');
  const llmBtn = document.getElementById('btn-ask-gemini') || document.querySelector('.btn-ai-small');
  const btnAiAlignLyrics = document.getElementById('btn-ai-align-lyrics');

  async function runLyricsAlignmentWithReference(referenceText, triggerBtn = null) {
    const cleanRef = (referenceText || '').trim();
    if (!cleanRef) {
      showToast('Empty Lyrics', 'Please paste your 100% correct lyrics text first', 'warning', 3000);
      return false;
    }

    const prevBtnText = triggerBtn ? triggerBtn.textContent : '';
    if (triggerBtn) setButtonLoading(triggerBtn, 'Aligning...');
    setGlobalProgress(25, true, 'Aligning with Original Lyrics & Audio...');

    const audioFilePath = state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';

    try {
      const res = await fetch('/api/lyrics/correct-with-reference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lyrics_data: state.lyrics || [],
          reference_text: cleanRef,
          audio_path: audioFilePath
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lyrics alignment failed');
      setGlobalProgress(100, true, 'Lyrics Alignment Complete');

      if (data.status === 'success' && data.lyrics && data.lyrics.length > 0) {
        state.lyrics = data.lyrics;
        try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
        renderLyricsTeleprompter(state.lyrics, true);
        const wordAligned = data.source === 'ctc_word_alignment';
        showToast(
          wordAligned ? 'Original Lyrics Aligned' : 'Estimated Vocal Timing',
          `Preserved ${data.lines_count} original lines. ${wordAligned ? 'Word timings aligned to singer audio.' : 'Acoustic estimates need playback review.'}`,
          wordAligned ? 'success' : 'warning',
          4500
        );
        return true;
      } else {
        showToast('Alignment Notice', data.detail || 'Could not complete lyrics alignment', 'info', 3000);
        return false;
      }
    } catch (err) {
      console.error('Lyrics alignment error:', err);
      showToast('Alignment Error', err.message, 'error', 3500);
      return false;
    } finally {
      if (triggerBtn) clearButtonLoading(triggerBtn, prevBtnText || 'Align & Fix Teleprompter');
      setTimeout(() => setGlobalProgress(100, false, ''), 1000);
    }
  }

  if (llmBtn && llmInput) {
    llmBtn.addEventListener('click', async () => {
      const text = llmInput.value.trim();
      if (!text) {
        showToast('Empty Prompt', 'Type a question or message to ask Gemini AI', 'info', 2500);
        return;
      }
      
      try {
        setButtonLoading(llmBtn, 'Asking Gemini...');
        const res = await fetch('/api/ai/llm/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await res.json();
        
        if (data.analysis) {
          showToast('Gemini AI Response', data.analysis.substring(0, 100) + '...', 'success', 5000);
        } else if (data.status === 'error') {
          showToast('AI Error', 'Could not get response from Gemini', 'error');
        }
      } catch (err) {
        showToast('AI Error', err.message, 'error');
      } finally {
        clearButtonLoading(llmBtn, 'Ask Gemini AI (Khmer Focus)');
      }
    });
  }

  if (btnAiAlignLyrics && llmInput) {
    btnAiAlignLyrics.addEventListener('click', async () => {
      const text = llmInput.value.trim();
      if (!text) {
        showToast('Empty Lyrics', 'Please paste original lyrics into the box first to align', 'warning', 3000);
        return;
      }
      await runLyricsAlignmentWithReference(text, btnAiAlignLyrics);
    });
  }

  // ============ AI Khmer Lyric Composer Controls ============
  const btnGenKhmerLyrics = document.getElementById('btn-generate-khmer-lyrics');
  const btnPolishLyrics = document.getElementById('btn-polish-khmer-lyrics');
  const btnLoadGenLyrics = document.getElementById('btn-load-generated-lyrics');
  const selectLyricGenre = document.getElementById('select-ai-lyric-genre');

  if (btnGenKhmerLyrics) {
    btnGenKhmerLyrics.addEventListener('click', async () => {
      const genre = selectLyricGenre ? selectLyricGenre.value : 'romantic';
      const prompt = llmInput ? llmInput.value.trim() : '';

      try {
        setButtonLoading(btnGenKhmerLyrics, 'Composing...');
        const res = await fetch('/api/lyrics/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, genre })
        });
        const data = await res.json();

        if (data.status === 'success' && data.lyrics_text) {
          window.__last_generated_lyrics = data;
          if (llmInput) llmInput.value = data.lyrics_text;
          if (btnLoadGenLyrics) btnLoadGenLyrics.style.display = 'inline-block';
          showToast('Song Composed', `${data.title} (${data.count} lines generated)`, 'success', 4000);
        } else {
          showToast('Generation Notice', data.detail || 'Could not compose lyrics', 'info');
        }
      } catch (err) {
        showToast('Error', err.message, 'error');
      } finally {
        clearButtonLoading(btnGenKhmerLyrics, 'Compose');
      }
    });
  }

  if (btnPolishLyrics) {
    btnPolishLyrics.addEventListener('click', async () => {
      const textToPolish = (llmInput && llmInput.value.trim()) ||
        (state.lyrics && state.lyrics.length > 0 ? state.lyrics.map(l => l.text).join('\n') : '');

      if (!textToPolish) {
        showToast('Info', 'Enter Khmer lyrics in the prompt box or load lyrics to polish!', 'info');
        return;
      }

      try {
        setButtonLoading(btnPolishLyrics, 'Fixing...');
        const res = await fetch('/api/lyrics/polish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lyrics_text: textToPolish })
        });
        const data = await res.json();

        if (data.status === 'success') {
          if (llmInput) llmInput.value = data.polished_text;
          showToast('Khmer Spelling Polished', `Fixed ${data.corrections_made} spelling & subscript issues!`, 'success', 4000);
        } else {
          showToast('Notice', data.detail || 'Could not polish lyrics', 'info');
        }
      } catch (err) {
        showToast('Error', err.message, 'error');
      } finally {
        clearButtonLoading(btnPolishLyrics, 'Fix Spelling');
      }
    });
  }

  if (btnLoadGenLyrics) {
    btnLoadGenLyrics.addEventListener('click', () => {
      const gen = window.__last_generated_lyrics;
      if (!gen || !gen.lyrics_data || gen.lyrics_data.length === 0) {
        showToast('No Lyrics', 'Please compose a song first!', 'info');
        return;
      }
      state.lyrics = gen.lyrics_data;
      if (gen.title) {
        state.songTitle = gen.title;
        const inputTitle = document.getElementById('input-song-title');
        if (inputTitle) inputTitle.value = gen.title;
      }
      renderLyricsTeleprompter(state.lyrics);
      setLyricsVisibility(true, false);
      showToast('Loaded into Studio', `${gen.title} ready for video sync & visualizer!`, 'success', 3500);
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

  // ============ On-Screen Typography & Titles (Add, Update, Delete) ============
  const checkShowTitles = document.getElementById('check-show-titles');
  const inputSongTitle = document.getElementById('input-song-title');
  const btnClearTitle = document.getElementById('btn-clear-title');
  const inputArtistName = document.getElementById('input-artist-name');
  const btnClearArtist = document.getElementById('btn-clear-artist');
  const checkShowCenterText = document.getElementById('check-show-center-text');
  const inputCenterPrimary = document.getElementById('input-center-primary');
  const inputCenterSecondary = document.getElementById('input-center-secondary');
  const btnClearCenterText = document.getElementById('btn-clear-center-text');
  const badgeStatusText = document.getElementById('badge-status-text');
  const btnRemoveLogo = document.getElementById('btn-remove-logo');
  const btnUploadLogoInline = document.getElementById('btn-upload-logo-inline');
  const btnSyncTitlesToBadge = document.getElementById('btn-sync-titles-to-badge');
  const btnStageCenterBadge = document.getElementById('btn-stage-center-badge');

  // The badge status line is painted by ui.css (.ui-t--*) and written with
  // textContent, so centre-text typed by the user can never inject markup.
  function setBadgeStatus(tone, text) {
    if (!badgeStatusText) return;
    badgeStatusText.className = `ui-t ${tone}`;
    badgeStatusText.textContent = text;
  }

  function updateBadgeStatusUI() {
    if (state.logoImageObj && state.logoImageObj.complete) {
      setBadgeStatus('ui-t--ok', 'VibeTunes Logo Active');
      if (btnRemoveLogo) {
        btnRemoveLogo.classList.remove('hidden');
        btnRemoveLogo.textContent = 'Switch to Text';
      }
    } else if (state.showCenterText === false) {
      setBadgeStatus('ui-t--dim', 'Badge Hidden (Off)');
      if (btnRemoveLogo) btnRemoveLogo.classList.add('hidden');
    } else {
      const c1 = state.centerTextPrimary !== undefined ? state.centerTextPrimary : 'VibeTunes';
      const c2 = state.centerTextSecondary !== undefined ? state.centerTextSecondary : 'OFFICIAL';
      if (!c1.trim() && !c2.trim()) {
        setBadgeStatus('ui-t--warn', 'Clean Ring (No Text)');
      } else {
        setBadgeStatus('ui-t--pink', `Badge: "${c1}" / "${c2}"`);
      }
      if (btnRemoveLogo) {
        btnRemoveLogo.classList.remove('hidden');
        btnRemoveLogo.textContent = 'Restore VibeTunes';
      }
    }
  }

  function focusCenterBadgeEditor(showToastMsg = true) {
    // 1. Ensure Right Panel is on Visualizer tab
    const styleTab = document.querySelector('#nav-right-panel .segmented-tab[data-target="tab-right-visualizer"]');
    if (styleTab && !styleTab.classList.contains('active')) {
      styleTab.click();
    }

    // 2. Scroll into view and flash highlight ring
    const section = document.getElementById('section-center-badge');
    if (section) {
      // The badge lives inside collapsible sections — open them so the focus below works
      if ('open' in section) section.open = true;
      const parent = section.closest('.ui-sec');
      if (parent && 'open' in parent) parent.open = true;
      section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      section.classList.remove('badge-highlight-active');
      void section.offsetWidth; // Trigger reflow for animation restart
      section.classList.add('badge-highlight-active');
      setTimeout(() => {
        section.classList.remove('badge-highlight-active');
      }, 2000);
    }

    // 3. Focus Line 1 input and select text for effortless typing
    if (inputCenterPrimary) {
      setTimeout(() => {
        inputCenterPrimary.focus();
        inputCenterPrimary.select();
      }, 150);
    }

    // 4. Helpful toast notification
    if (showToastMsg) {
      showToast('Center Badge', 'Edit Line 1 & Line 2, clear text, or upload custom logo artwork!', 'info', 3000);
    }
  }

  // Quick Center Badge button on stage header
  if (btnStageCenterBadge) {
    btnStageCenterBadge.addEventListener('click', () => {
      focusCenterBadgeEditor();
    });
  }

  // Interactive Click & Hover on Visualizer Canvas Center Circle
  function isMouseInCenterBadge(e) {
    if (!vizCanvas) return false;
    const rect = vizCanvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    const scaleX = vizCanvas.width / rect.width;
    const scaleY = vizCanvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    const cx = vizCanvas.width / 2;
    const cy = vizCanvas.height / 2;
    const dist = Math.hypot(x - cx, y - cy);
    const radius = Math.min(vizCanvas.width, vizCanvas.height) * 0.18;
    return dist <= radius;
  }

  if (vizCanvas) {
    vizCanvas.addEventListener('mousemove', (e) => {
      if (isMouseInCenterBadge(e)) {
        vizCanvas.style.cursor = 'pointer';
        vizCanvas.title = 'Click to customize Center Badge (Text & Logo)';
      } else {
        vizCanvas.style.cursor = 'default';
        vizCanvas.title = '';
      }
    });

    vizCanvas.addEventListener('click', (e) => {
      if (isMouseInCenterBadge(e)) {
        focusCenterBadgeEditor();
      }
    });
  }

  function syncTitleInputs() {
    if (inputSongTitle) inputSongTitle.value = state.songTitle || '';
    if (inputArtistName) inputArtistName.value = state.artistName || '';
    if (inputCenterPrimary && state.centerTextPrimary !== undefined) inputCenterPrimary.value = state.centerTextPrimary;
    if (inputCenterSecondary && state.centerTextSecondary !== undefined) inputCenterSecondary.value = state.centerTextSecondary;
    if (checkShowTitles) checkShowTitles.checked = state.showTitles !== false;
    if (checkShowCenterText) checkShowCenterText.checked = state.showCenterText !== false;
    const sliderScale = document.getElementById('slider-title-scale');
    const labelScale = document.getElementById('label-title-scale');
    if (sliderScale) sliderScale.value = state.titleScale || 1.5;
    if (labelScale) labelScale.textContent = `${Math.round((state.titleScale || 1.5) * 100)}%`;
    updateBadgeStatusUI();
  }
  syncTitleInputs();

  const sliderTitleScale = document.getElementById('slider-title-scale');
  const labelTitleScale = document.getElementById('label-title-scale');
  if (sliderTitleScale && labelTitleScale) {
    sliderTitleScale.addEventListener('input', (e) => {
      state.titleScale = parseFloat(e.target.value);
      labelTitleScale.textContent = `${Math.round(state.titleScale * 100)}%`;
    });
  }

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
      updateBadgeStatusUI();
      showToast('Center Badge', state.showCenterText ? 'Badge Text Visible' : 'Badge Text Hidden', 'info', 1500);
    });
  }

  if (inputCenterPrimary) {
    inputCenterPrimary.value = state.centerTextPrimary !== undefined ? state.centerTextPrimary : 'VIDA';
    inputCenterPrimary.addEventListener('input', (e) => {
      state.centerTextPrimary = e.target.value;
      updateBadgeStatusUI();
    });
  }

  if (inputCenterSecondary) {
    inputCenterSecondary.value = state.centerTextSecondary !== undefined ? state.centerTextSecondary : 'FLUID WAVE';
    inputCenterSecondary.addEventListener('input', (e) => {
      state.centerTextSecondary = e.target.value;
      updateBadgeStatusUI();
    });
  }

  if (btnClearCenterText) {
    btnClearCenterText.addEventListener('click', () => {
      state.centerTextPrimary = '';
      state.centerTextSecondary = '';
      if (inputCenterPrimary) inputCenterPrimary.value = '';
      if (inputCenterSecondary) inputCenterSecondary.value = '';
      updateBadgeStatusUI();
      showToast('Center Badge', 'Center emblem text deleted/cleared', 'info', 1500);
    });
  }

  if (btnRemoveLogo) {
    btnRemoveLogo.addEventListener('click', () => {
      if (state.logoImageObj) {
        state.logoImageObj = null;
        state.logoImagePath = null;
        state.logoImageUrl = null;
        const btnLogoEl = document.getElementById('btn-upload-logo');
        if (btnLogoEl) {
          btnLogoEl.classList.remove('active');
          btnLogoEl.innerHTML = `<div class="media-item-left"><span class="icon">🎨</span><span class="media-item-title">Center Logo</span></div><span class="media-item-badge">None</span>`;
        }
        updateBadgeStatusUI();
        showToast('Center Badge', 'Switched to text badge (Click "Restore VibeTunes" anytime)', 'info', 2500);
      } else {
        const defaultLogoUrl = '/uploads/images/vibetunes_logo.png';
        const defaultLogoPath = 'd:\\Project\\VIDA\\uploads\\images\\vibetunes_logo.png';
        const img = new Image();
        img.onload = () => {
          state.logoImageObj = img;
          state.logoImageUrl = defaultLogoUrl;
          state.logoImagePath = defaultLogoPath;
          const btnLogoEl = document.getElementById('btn-upload-logo');
          if (btnLogoEl) {
            btnLogoEl.classList.add('active');
            btnLogoEl.innerHTML = `<div class="media-item-left"><span class="icon">🎨</span><span class="media-item-title">Logo: VibeTunes</span></div><span class="media-item-badge media-item-badge--ok">Default ✓</span>`;
          }
          updateBadgeStatusUI();
          showToast('Center Badge', 'Restored default VibeTunes logo!', 'success', 2500);
        };
        img.src = defaultLogoUrl;
      }
    });
  }

  if (btnUploadLogoInline) {
    btnUploadLogoInline.addEventListener('click', () => {
      const inputLogoEl = document.getElementById('logo-file-input');
      if (inputLogoEl) inputLogoEl.click();
    });
  }

  if (btnSyncTitlesToBadge) {
    btnSyncTitlesToBadge.addEventListener('click', () => {
      const title = (state.songTitle || 'VIDA').split('(')[0].trim();
      const artist = (state.artistName || 'AUDIO').split('(')[0].trim();
      state.centerTextPrimary = title;
      state.centerTextSecondary = artist;
      if (inputCenterPrimary) inputCenterPrimary.value = title;
      if (inputCenterSecondary) inputCenterSecondary.value = artist;
      state.showCenterText = true;
      if (checkShowCenterText) checkShowCenterText.checked = true;
      updateBadgeStatusUI();
      showToast('Badge Synced', `Set to "${title}" / "${artist}"`, 'success', 2000);
    });
  }

  // ============ Smart Video Director & Rule Flow ============
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
      if (p) showToast('Director Rule Flow', p.name, 'success', 2500);
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

  // ============ Real-Time VFX Rack ============
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
      const { width: w, height: h } = getPreviewSize();
      triggerCameraShake(24);
      triggerShockwave(w / 2, h / 2, 1.4);
      triggerBloomFlash(0.85);
      showToast('Drop Impact Tested', 'Triggered Shake + Shockwave + Optical Bloom', 'info', 2000);
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
        card.className = 'khmer-card khmer-card--singer';
        card.dataset.id = s.id;
        card.style.setProperty('--kc-accent', s.accent);

        const famousTags = s.famousSongs.map(f => `<span class="khmer-pill">${f}</span>`).join('');

        card.innerHTML = `
          <div class="kc-swatch" style="background: ${s.bgAccent}">
            <span class="kc-badge">${s.badge}</span>
            <span class="kc-years">${s.years}</span>
          </div>
          <div>
            <h4 class="kc-title">${s.name_km} (${s.name_en})</h4>
            <div class="kc-role">${s.title}</div>
          </div>
          <p class="kc-desc">${s.desc}</p>
          <div>
            <div class="kc-sec">Classic Songs</div>
            <div class="kc-tags">${famousTags}</div>
          </div>
          <div class="kc-foot">
            <button class="btn-apply-singer ui-btn ui-btn--warn ui-btn--sm">Apply Singer Vinyl</button>
            ${s.id === 'sinn_sisamouth' ? `
            <button class="btn-play-singer-demo ui-btn ui-btn--sm">▶Play Demo</button>` : ''}
          </div>
        `;

        const applyBtn = card.querySelector('.btn-apply-singer');
        if (applyBtn) {
          applyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            state.artistName = `${s.name_km} (${s.name_en})`;
            state.songTitle = s.defaultSong;
            applyKhmerTemplate(s.templateId);
            showToast('Singer Preset Applied', `${s.name_km} — 33⅓ RPM Vinyl Ready!`, 'success', 4000);
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
      banner.className = 'ui-banner ui-banner--gold';
      banner.innerHTML = `
        <div class="ui-row">
          <span class="ui-banner-ico">🎙️</span>
          <div>
            <div class="kc-legend">តារាចម្រៀងខ្មែរ យុគមាស ឆ្នាំ៦០-៧០ <span class="kc-legend-en">(11 Cambodian Golden Era Legends)</span></div>
            <div class="ui-hint">Sinn Sisamouth, Ros Sereysothea, Pen Ran, Mao Sareth, Meas Samon, Drakkar &amp; more</div>
          </div>
        </div>
        <button id="btn-banner-view-singers" class="ui-btn ui-btn--warn ui-btn--sm">View 11 Legends →</button>
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
        <div class="kc-swatch" style="background: ${t.gradient}">
          <span class="kc-badge">${t.badge}</span>
          <span class="kc-cat">${t.category}</span>
        </div>
        <div>
          <h4 class="kc-title">${t.title_km}</h4>
          <div class="kc-en">${t.title_en}</div>
        </div>
        <p class="kc-desc">${t.desc}</p>
        <div class="kc-tags">
          <span class="khmer-pill">${t.palette.replace('_', ' ')}</span>
          <span class="khmer-pill">${t.theme.replace('_', ' ')}</span>
          <span class="khmer-pill">${t.lyricStyle}</span>
        </div>
        <div class="kc-best"><strong>Best for</strong> ${t.bestFor}</div>
        <button class="ui-btn ui-btn--warn ui-btn--sm ui-btn--block">Apply Template</button>
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
      if (overlayBtn) overlayBtn.classList.add('is-on');
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
      if (overlayBtn) overlayBtn.classList.remove('is-on');
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
        btnToggleTeleprompter.textContent = 'Hide';
        btnToggleTeleprompter.style.color = 'var(--text-muted)';
      } else {
        teleprompterEl.style.display = 'none';
        btnToggleTeleprompter.textContent = 'Show';
        btnToggleTeleprompter.style.color = 'var(--accent)';
      }
    });
  }

  // Double-Check Lyrics (re-measure timing against the selected singer audio)
  const btnVerifyLyrics = document.getElementById('btn-verify-lyrics');
  if (btnVerifyLyrics) {
    btnVerifyLyrics.addEventListener('click', async () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('No Lyrics', 'Please load audio, demo, or import lyrics first to verify', 'info', 2500);
        return;
      }
      const audioFilePath = state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
      setButtonLoading(btnVerifyLyrics, 'Checking...');
      setGlobalProgress(20, true, 'Checking lyric timing against selected singer audio...');
      try {
        const res = await fetch('/api/lyrics/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lyrics_data: state.lyrics,
            audio_path: audioFilePath
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Lyric timing check failed');
        setGlobalProgress(100, true, 'Lyric timing checked');
        if (data.status === 'success' && data.lyrics) {
          state.lyrics = data.lyrics;
          try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
          renderLyricsTeleprompter(state.lyrics, true);
          showToast(
            'Lyric Timing Checked',
            data.source === 'ctc_word_alignment'
              ? `Aligned ${data.lines_count} lines (${data.words_count || 0} words) to singer audio. Review playback.`
              : 'Timing structure checked; estimated singing timing still needs playback review.',
            data.source === 'ctc_word_alignment' ? 'success' : 'warning',
            3500
          );
        } else {
          showToast('Verification Notice', data.message || 'Lyrics processed successfully', 'info', 3000);
        }
      } catch (err) {
        console.error('Lyrics verification error:', err);
        showToast('Verification Error', err.message, 'error', 3000);
      } finally {
        clearButtonLoading(btnVerifyLyrics, 'Double-Check');
        setTimeout(() => setGlobalProgress(100, false, ''), 1000);
      }
    });
  }

  // Re-Sync Lyrics to Music & Singing Tempo (Fast & Slow vocal tracking)
  const btnSyncVocalTiming = document.getElementById('btn-sync-vocal-timing');
  if (btnSyncVocalTiming) {
    btnSyncVocalTiming.addEventListener('click', async () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('No Lyrics', 'Please load, transcribe, or import lyrics first to sync timing', 'info', 2500);
        return;
      }
      const audioFilePath = state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
      if (!audioFilePath) {
        showToast('No Audio Track', 'Please load an audio file first to align with real singing', 'warning', 3000);
        return;
      }

      setButtonLoading(btnSyncVocalTiming, 'Syncing...');
      setGlobalProgress(25, true, 'Aligning Lyric Pacing to Vocal Waveform...');
      try {
        const res = await fetch('/api/subtitles/align-audio', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lyrics_data: state.lyrics,
            audio_path: audioFilePath
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Lyric synchronization failed');
        setGlobalProgress(100, true, 'Timing Re-Sync Complete');
        if (data.status === 'success' && data.lyrics && data.lyrics.length > 0) {
          state.lyrics = data.lyrics;
          try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
          renderLyricsTeleprompter(state.lyrics, true);
          const wordAligned = data.source === 'ctc_word_alignment';
          showToast(
            wordAligned ? 'Singer Timing Aligned' : 'Estimated Vocal Timing',
            wordAligned
              ? `Aligned ${data.count || state.lyrics.length} original lines and word timings. Review playback.`
              : 'Acoustic estimates applied; the word aligner could not confidently match this song. Review playback.',
            wordAligned ? 'success' : 'warning',
            4000
          );
        } else {
          showToast('Sync Notice', data.detail || 'Could not align timestamps to vocal waveform', 'info', 3000);
        }
      } catch (err) {
        console.error('Lyric timing sync error:', err);
        showToast('Sync Error', err.message, 'error', 3000);
      } finally {
        clearButtonLoading(btnSyncVocalTiming, 'Re-Sync to Music');
        setTimeout(() => setGlobalProgress(100, false, ''), 1000);
      }
    });
  }

  async function persistSubtitleChanges() {
    const audioFilePath = state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
    if (audioFilePath && state.lyrics && state.lyrics.length > 0) {
      try {
        await fetch('/api/subtitles/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lyrics_data: state.lyrics, audio_path: audioFilePath })
        });
      } catch(_) {}
    }
  }

  function shiftLyricsEarlier(amount = 0.5) {
    if (!state.lyrics || state.lyrics.length === 0) {
      showToast('No Lyrics', 'Please load lyrics first to shift timing', 'info', 2000);
      return;
    }
    let prevEnd = 0.0;
    state.lyrics.forEach((l, idx) => {
      let curStart = parseFloat(l.start != null ? l.start : l.time || 0);
      let curEnd = parseFloat(l.end != null ? l.end : l.endTime || (curStart + 2.5));
      
      let newStart = Math.max(0.0, Math.round((curStart - amount) * 100) / 100);
      if (idx > 0 && newStart < prevEnd) {
        newStart = Math.max(0.0, Math.round((prevEnd + 0.02) * 100) / 100);
      }
      let newEnd = Math.max(newStart + 0.35, Math.round((curEnd - amount) * 100) / 100);
      
      l.start = newStart;
      l.end = newEnd;
      if (l.time !== undefined) l.time = newStart;
      if (l.endTime !== undefined) l.endTime = newEnd;
      
      if (Array.isArray(l.words)) {
        l.words.forEach((w) => {
          w.start = Math.max(0.0, Math.round((parseFloat(w.start) - amount) * 100) / 100);
          w.end = Math.max(w.start + 0.04, Math.round((parseFloat(w.end) - amount) * 100) / 100);
        });
      }
      prevEnd = newEnd;
    });
    try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
    renderLyricsTeleprompter(state.lyrics, true);
    persistSubtitleChanges();
    showToast('Show Earlier', `Lyric timing increased by +${amount}s earlier (now showing earlier before vocals).`, 'success', 2500);
  }

  function shiftLyricsLater(amount = 0.5) {
    if (!state.lyrics || state.lyrics.length === 0) {
      showToast('No Lyrics', 'Please load lyrics first to shift timing', 'info', 2000);
      return;
    }
    state.lyrics.forEach((l) => {
      let curStart = parseFloat(l.start != null ? l.start : l.time || 0);
      let curEnd = parseFloat(l.end != null ? l.end : l.endTime || (curStart + 2.5));
      l.start = Math.round((curStart + amount) * 100) / 100;
      l.end = Math.round((curEnd + amount) * 100) / 100;
      if (l.time !== undefined) l.time = l.start;
      if (l.endTime !== undefined) l.endTime = l.end;
      if (Array.isArray(l.words)) {
        l.words.forEach((w) => {
          w.start = Math.round((parseFloat(w.start) + amount) * 100) / 100;
          w.end = Math.round((parseFloat(w.end) + amount) * 100) / 100;
        });
      }
    });
    try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
    renderLyricsTeleprompter(state.lyrics, true);
    persistSubtitleChanges();
    showToast('⏪ Show Later', `All lyrics delayed by ${amount}s later.`, 'success', 2000);
  }

  const btnShowEarlier500 = document.getElementById('btn-show-earlier-500') || document.getElementById('btn-shift-lyrics-prev');
  if (btnShowEarlier500) {
    btnShowEarlier500.addEventListener('click', () => shiftLyricsEarlier(0.5));
  }

  const btnShowEarlier100 = document.getElementById('btn-show-earlier-100');
  if (btnShowEarlier100) {
    btnShowEarlier100.addEventListener('click', () => shiftLyricsEarlier(0.1));
  }

  const btnShowLater500 = document.getElementById('btn-show-later-500') || document.getElementById('btn-shift-lyrics-next');
  if (btnShowLater500) {
    btnShowLater500.addEventListener('click', () => shiftLyricsLater(0.5));
  }

  // Auto-Fix Words (In-Place, Zero Structure/Timestamp Change)
  const btnAutofixLyrics = document.getElementById('btn-autofix-lyrics');
  if (btnAutofixLyrics) {
    btnAutofixLyrics.addEventListener('click', async () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('No Lyrics', 'Please load audio or lyrics first to fix words', 'info', 2500);
        return;
      }
      setButtonLoading(btnAutofixLyrics, 'Fixing...');
      setGlobalProgress(25, true, 'Fixing Words in Place...');
      try {
        const res = await fetch('/api/lyrics/auto_fix', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lyrics_data: state.lyrics })
        });
        const data = await res.json();
        setGlobalProgress(100, true, 'Words Fixed');
        if (data.status === 'success' && data.lyrics) {
          state.lyrics = data.lyrics;
          try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(e) {}
          renderLyricsTeleprompter(state.lyrics, true);
          showToast(
            'Words Fixed (Structure Preserved)',
            `Fixed spelling & phonetic errors across ${data.lyrics.length} lines in place. Line timings preserved; word highlights were regenerated.`,
            'success',
            4000
          );
        } else {
          showToast('Notice', data.detail || 'Could not auto-fix words', 'info', 3000);
        }
      } catch (err) {
        console.error('Auto-fix words error:', err);
        showToast('Fix Error', err.message, 'error', 3000);
      } finally {
        clearButtonLoading(btnAutofixLyrics, 'Fix Words');
        setTimeout(() => setGlobalProgress(100, false, ''), 1000);
      }
    });
  }

  // Paste & Align Original Lyrics Modal
  const btnPasteAlignLyrics = document.getElementById('btn-paste-align-lyrics');
  const alignLyricsModal = document.getElementById('align-lyrics-modal');
  const btnCloseAlignModal = document.getElementById('btn-close-align-modal');
  const btnCancelAlignModal = document.getElementById('btn-cancel-align-modal');
  const btnSubmitAlignLyrics = document.getElementById('btn-submit-align-lyrics');
  const inputAlignReference = document.getElementById('input-align-reference');
  const alignModalLineCount = document.getElementById('align-modal-line-count');

  function openAlignModal() {
    if (!alignLyricsModal) return;
    alignLyricsModal.style.display = 'flex';
    const aiInputVal = (document.getElementById('input-ai-prompt') || document.querySelector('.llm-input'))?.value?.trim();
    if (aiInputVal && inputAlignReference && (!inputAlignReference.value || !inputAlignReference.value.trim())) {
      inputAlignReference.value = aiInputVal;
    }
    updateAlignLineCount();
    setTimeout(() => inputAlignReference?.focus(), 100);
  }

  function closeAlignModal() {
    if (alignLyricsModal) alignLyricsModal.style.display = 'none';
  }

  function updateAlignLineCount() {
    if (!inputAlignReference || !alignModalLineCount) return;
    const lines = inputAlignReference.value.split('\n').map(l => l.trim()).filter(Boolean);
    alignModalLineCount.textContent = `${lines.length} Lines`;
  }

  if (inputAlignReference) {
    inputAlignReference.addEventListener('input', updateAlignLineCount);
  }

  if (btnPasteAlignLyrics) {
    btnPasteAlignLyrics.addEventListener('click', () => {
      if ((!state.lyrics || state.lyrics.length === 0) && !state.audioPath && !state.audioUrl) {
        showToast('No Audio or Lyrics', 'Please load an audio file first to align lyrics', 'info', 3500);
        return;
      }
      openAlignModal();
    });
  }

  if (btnCloseAlignModal) btnCloseAlignModal.addEventListener('click', closeAlignModal);
  if (btnCancelAlignModal) btnCancelAlignModal.addEventListener('click', closeAlignModal);

  if (btnSubmitAlignLyrics) {
    btnSubmitAlignLyrics.addEventListener('click', async () => {
      const text = inputAlignReference ? inputAlignReference.value.trim() : '';
      if (!text) {
        showToast('Empty Lyrics', 'Please paste your original lyrics text into the box', 'warning', 3000);
        return;
      }
      const success = await runLyricsAlignmentWithReference(text, btnSubmitAlignLyrics);
      if (success) {
        closeAlignModal();
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
      try { localStorage.removeItem('vida_lyrics'); } catch(e) {}
      const btnTranscribe = document.getElementById('btn-transcribe-ai');
      if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Auto-Sync Lyrics');
      showToast('Lyrics Cleared', 'Loaded lyrics have been removed from studio', 'info', 3000);
    });
  }

  // Fullscreen Lyrics Toggle
  const btnFullscreenTeleprompter = document.getElementById('btn-fullscreen-teleprompter');
  if (btnFullscreenTeleprompter) {
    btnFullscreenTeleprompter.addEventListener('click', () => {
      const el = document.getElementById('lyrics-teleprompter');
      if (el.style.position === 'fixed') {
        el.style.position = '';
        el.style.top = '';
        el.style.left = '';
        el.style.width = '';
        el.style.height = '';
        el.style.zIndex = '';
        el.style.maxWidth = '';
        btnFullscreenTeleprompter.innerHTML = 'Full';
        document.body.style.overflow = '';
      } else {
        el.style.position = 'fixed';
        el.style.top = '20px';
        el.style.left = '20px';
        el.style.width = 'calc(100% - 40px)';
        el.style.height = 'calc(100% - 40px)';
        el.style.zIndex = '9999';
        el.style.maxWidth = '100%';
        btnFullscreenTeleprompter.innerHTML = 'Exit Full';
        document.body.style.overflow = 'hidden';
      }
    });
  }

  // ============ Synced Lyrics Teleprompter ============
  function renderLyricsTeleprompter(lyrics, isVerified = true) {
    const el = document.getElementById('lyrics-teleprompter');
    const badge = document.getElementById('lyrics-count-badge');
    const verifiedBadge = document.getElementById('lyrics-verified-badge');
    if (!el) return;

    // Auto-restore the saved translated track for this song (guarded against re-entrancy)
    if (lyrics && lyrics.length > 0 && !window.__VIDA_TR_LOADING && !(state.translation && state.translation.loaded)) {
      window.__VIDA_TR_LOADING = true;
      Promise.resolve(loadTranslationForSong())
        .catch(() => {})
        .finally(() => { window.__VIDA_TR_LOADING = false; });
    }
    if (!lyrics || lyrics.length === 0) {
      el.innerHTML = '<div class="ui-empty">No lyrics loaded yet</div>';
      if (badge) badge.textContent = '0 Lines';
      if (verifiedBadge) verifiedBadge.style.display = 'none';
      return;
    }

    if (badge) badge.textContent = `${lyrics.length} Lines`;
    if (verifiedBadge) {
      const wordTimed = lyrics.every((l) => Number.isFinite(l.confidence));
      verifiedBadge.style.display = 'inline-block';
      verifiedBadge.classList.toggle('ui-chip--ok', wordTimed);
      verifiedBadge.classList.toggle('ui-chip--warn', !wordTimed);
      verifiedBadge.textContent = wordTimed ? 'Word-Timed' : 'Timing Checked';
      verifiedBadge.title = wordTimed
        ? 'Line and word timings measured from the selected singer audio. Still review playback.'
        : 'Timestamps are ordered and inside the track, but were not measured word-by-word from the singing. Review playback.';
    }
    el.innerHTML = '';

    lyrics.forEach((line, index) => {
      const item = document.createElement('div');
      item.className = 'teleprompter-line';
      item.dataset.index = index;
      item.dataset.start = line.start;
      item.dataset.end = line.end;

      const isKhmer = /[\u1780-\u17FF]/.test(line.text);
      const font = isKhmer ? "'Kantumruy Pro', 'Battambang', 'Siemreap', sans-serif" : "'Outfit', 'Inter', sans-serif";

      // Optional translated line shown right under the original in the teleprompter list
      const trCfg = state.translation || {};
      const trEntry = Array.isArray(trCfg.lines) ? trCfg.lines[index] : null;
      const trText = ((trEntry && (typeof trEntry === 'string' ? trEntry : trEntry.text)) || '').trim();
      const showTr = !!trText && trCfg.displayMode !== 'original_only';
      const trIsKhmer = /[\u1780-\u17FF]/.test(trText);
      const trFont = trIsKhmer ? "'Kantumruy Pro', 'Battambang', 'Siemreap', sans-serif" : "'Outfit', 'Inter', sans-serif";

      item.innerHTML = `<div class="tp-main"><span class="tp-time">[${formatTime(line.start)}]</span><span class="editable-lyric tp-text" contenteditable="true" spellcheck="false" style="font-family: ${font}">${line.text}</span></div>${showTr ? `<div class="tp-tr" style="font-family: ${trFont}">${trText}</div>` : ''}`;
      
      const textSpan = item.querySelector('.editable-lyric');
      textSpan.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent audio jump when clicking to edit text
      });
      textSpan.addEventListener('blur', (e) => {
        const newText = e.target.textContent.trim();
        if (newText !== line.text) {
          state.lyrics[index].text = newText;
          showToast('Lyric Updated', 'Correction saved to memory.', 'success', 2000);
        }
      });

      item.addEventListener('click', () => {
        if (audioPlayer && hasValidAudioSource(audioPlayer)) {
          try {
            audioPlayer.currentTime = line.start;
            if (audioPlayer.paused) {
              initAudioContext(audioPlayer, () => startVisualizer());
              audioPlayer.play().then(() => {
                state.isPlaying = true;
                if (btnPlayPause) btnPlayPause.textContent = "⏸";
              }).catch(() => {});
            }
          } catch(e) {}
          showToast('Jump to Lyric', `[${formatTime(line.start)}] "${line.text.substring(0, 30)}..."`, 'info', 1500);
        } else {
          showToast('Audio Track Not Loaded', 'Upload or select an audio file to listen to this section', 'info', 2000);
        }
      });

      el.appendChild(item);
    });
  }

  // Initialize empty teleprompter state safely
  renderLyricsTeleprompter(state.lyrics);

  // Initialize SRT Subtitle Editor & Multi-Format Exporter
  initSRTEditor(showToast, renderLyricsTeleprompter);

  // Initialize Translated Lyric Track (3 display modes, AI translate, editor, separate SRT)
  initTranslationTrack(showToast);
  window.addEventListener('vida:translation-changed', () => {
    try { renderLyricsTeleprompter(state.lyrics); } catch (_) {}
  });
  if (state.lyrics && state.lyrics.length > 0) loadTranslationForSong();

  function updateTeleprompterHighlight(currentTime) {
    const el = document.getElementById('lyrics-teleprompter');
    if (!el || !state.lyrics || state.lyrics.length === 0) return;
    const lines = el.querySelectorAll('.teleprompter-line');

    let activeItem = null;

    // Frame-perfect 100% vocal tracking: active strictly when singer begins phrase
    for (let i = 0; i < lines.length; i++) {
      const item = lines[i];
      const start = parseFloat(item.dataset.start);
      const end = parseFloat(item.dataset.end);
      const nextItem = i + 1 < lines.length ? lines[i + 1] : null;
      const nextStart = nextItem ? parseFloat(nextItem.dataset.start) : Infinity;

      const effectiveEnd = (nextStart - end < 0.45) ? nextStart : end;
      if (currentTime >= start && currentTime < effectiveEnd) {
        activeItem = item;
        break;
      }
    }

    lines.forEach((item) => {
      const shouldActivate = item === activeItem;
      if (shouldActivate && !item.classList.contains('active')) {
        item.classList.add('active');
        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else if (!shouldActivate && item.classList.contains('active')) {
        item.classList.remove('active');
      }
    });
  }
  window.__updateTeleprompterHighlight = updateTeleprompterHighlight;

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
      initAudioContext(audioPlayer, () => startVisualizer());
      startVisualizer();
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

    // 2. Set source and force load with full URI encoding protection
    let finalSrc = src;
    if (src && !src.startsWith('blob:') && !src.startsWith('data:')) {
      try {
        if (src.startsWith('http://') || src.startsWith('https://')) {
          const u = new URL(src);
          const parts = u.pathname.split('/');
          u.pathname = parts.map((p, idx) => (idx === 0 && !p) ? '' : encodeURIComponent(decodeURIComponent(p))).join('/');
          finalSrc = u.toString();
        } else {
          const parts = src.split('/');
          finalSrc = parts.map((p, idx) => (idx === 0 && !p) ? '' : encodeURIComponent(decodeURIComponent(p))).join('/');
        }
      } catch (e) {
        finalSrc = encodeURI(src);
      }
    }
    audioPlayer.src = finalSrc;
    try {
      audioPlayer.load();
    } catch(e) {}

    // 3. Update application state
    state.audioUrl = finalSrc;
    ensureAudioFeatures(finalSrc).catch(() => {});
    state.audioPath = filename || 'audio.mp3';
    state.audioServerPath = serverPath || '';
    state.songTitle = title || filename || 'VIDA Project';
    state.artistName = artist || 'Official Audio';
    state.lyrics = lyrics || [];
    // A new master track must never inherit the previous song's translated lines or mode.
    state.translation.lines = [];
    state.translation.loaded = false;
    state.translation.ownerKey = null;
    state.translation.displayMode = 'original_only';
    state.translation.visible = false;
    renderLyricsTeleprompter(state.lyrics); // also starts the translation-track load
    window.__VIDA_SERVER_PATH = serverPath || '';

    // Cache in sessionStorage for hot-reload persistence
    try {
      sessionStorage.setItem('vida_audio_src', finalSrc);
      sessionStorage.setItem('vida_audio_time', '0');
      sessionStorage.setItem('vida_audio_server_path', serverPath || '');
      localStorage.setItem('vida_audio_server_path', serverPath || '');
      // Keep every cached field in sync with the song actually loaded on screen.
      localStorage.setItem('vida_meta_audio', serverPath || finalSrc);
      localStorage.setItem('vida_audio_src', finalSrc);
      localStorage.setItem('vida_song_title', state.songTitle);
      localStorage.setItem('vida_artist_name', state.artistName);
      if (lyrics && lyrics.length > 0) {
        localStorage.setItem('vida_lyrics', JSON.stringify(lyrics));
      } else {
        localStorage.removeItem('vida_lyrics');
      }
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

  const btnUploadAudio = document.getElementById('btn-upload-audio');
  if (btnUploadAudio && audioFileInput) {
    btnUploadAudio.addEventListener('click', () => audioFileInput.click());
  }

  // Shared audio loading function with live upload percentage
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

    const uploadBox = document.getElementById('upload-progress-box');
    const uploadStatus = document.getElementById('upload-progress-status');
    const uploadPct = document.getElementById('upload-progress-pct');
    const uploadFill = document.getElementById('upload-progress-fill');

    if (uploadBox) {
      uploadBox.style.display = 'block';
      if (uploadPct) uploadPct.textContent = '5%';
      if (uploadFill) uploadFill.style.width = '5%';
      if (uploadStatus) uploadStatus.textContent = `Uploading ${file.name.substring(0, 22)}...`;
    }
    setStudioPipelineProgress(1, 5, `Uploading ${file.name.substring(0, 20)} (5%)...`, 'Audio Upload');
    setGlobalProgress(5, true, 'Audio Upload');

    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 95);
        if (uploadPct) uploadPct.textContent = `${pct}%`;
        if (uploadFill) uploadFill.style.width = `${pct}%`;
        if (uploadStatus) uploadStatus.textContent = `Uploading audio (${pct}%)...`;
        setStudioPipelineProgress(1, pct, `Uploading ${file.name.substring(0, 20)} (${pct}%)...`, 'Audio Upload');
      }
    };

    xhr.onload = async () => {
      if (xhr.status === 200) {
        try {
          const data = JSON.parse(xhr.responseText);
          if (uploadPct) uploadPct.textContent = '100%';
          if (uploadFill) uploadFill.style.width = '100%';
          if (uploadStatus) uploadStatus.textContent = 'Upload Complete (100%)';
          setStudioPipelineProgress(1, 100, `✅ "${file.name.substring(0, 20)}" Uploaded (100%)`, 'Audio Upload');

          state.audioServerPath = data.audio_path || data.saved_path;
          window.__VIDA_SERVER_PATH = state.audioServerPath;
          if (data.video_path) {
            state.videoServerPath = data.video_path;
          }
          if (data.url && audioPlayer) {
            audioPlayer.src = data.url;
            try { audioPlayer.load(); } catch(_) {}
          }
          try {
            sessionStorage.setItem('vida_audio_server_path', state.audioServerPath);
          } catch(e) {}

          setTimeout(() => {
            if (uploadBox) uploadBox.style.display = 'none';
          }, 1600);

          // Smart Pipeline: auto-analyze + auto-lyrics
          await runSmartPipeline();
        } catch (err) {
          console.error("Upload parse error:", err);
          if (uploadBox) uploadBox.style.display = 'none';
          setStudioPipelineProgress(1, 0, 'Upload parse error', 'Audio Upload', false);
        }
      } else {
        if (uploadStatus) uploadStatus.textContent = 'Upload failed';
        if (uploadBox) setTimeout(() => uploadBox.style.display = 'none', 3000);
        setStudioPipelineProgress(1, 0, 'Upload failed', 'Audio Upload', false);
      }
    };

    xhr.onerror = () => {
      if (uploadStatus) uploadStatus.textContent = 'Upload network error';
      if (uploadBox) setTimeout(() => uploadBox.style.display = 'none', 3000);
      setStudioPipelineProgress(1, 0, 'Network error', 'Audio Upload', false);
    };

    xhr.send(formData);
  }

  // ============ SMART STUDIO AI PIPELINE ============
  async function runSmartPipeline() {
    if (!state.audioServerPath) return;
    
    // Lock pipeline — prevents hot-reloader from refreshing mid-pipeline
    window.__VIDA_PIPELINE_RUNNING = true;
    window.__VIDA_SERVER_PATH = state.audioServerPath;
    
    const btnAnalyze = document.getElementById('btn-run-deep-audit');
    const btnTranscribe = document.getElementById('btn-transcribe-ai');
    const selectTheme = document.getElementById('select-theme');
    const selectPalette = document.getElementById('select-palette');

    // ── Check if lyrics already loaded or available from server captions/LRC ──
    try {
      const subCheckRes = await fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_path: state.audioServerPath, force_ai: false })
      });
      const subCheckData = await subCheckRes.json();
      if (subCheckData && subCheckData.status === 'success' && subCheckData.lyrics && subCheckData.source === 'subtitle') {
        state.lyrics = subCheckData.lyrics;
        try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch(_) {}
        renderLyricsTeleprompter(state.lyrics, true);
        if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Lyrics Synced (100%)');
        setStudioPipelineProgress(3, 100, `${state.lyrics.length} authentic lines synced from verified captions (100%)`, 'Lyrics Synced');
        showToast('Lyrics Ready', `${state.lyrics.length} authentic lines loaded! ⚡`, 'success', 4000);
      } else if (state.lyrics && state.lyrics.length > 0) {
        renderLyricsTeleprompter(state.lyrics);
        if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Lyrics Synced (100%)');
        setStudioPipelineProgress(3, 100, `${state.lyrics.length} lines restored (100%)`, 'Lyrics Synced');
      }
    } catch(_) {
      if (state.lyrics && state.lyrics.length > 0) {
        renderLyricsTeleprompter(state.lyrics);
      }
    }

    // ── Prepare Audio DNA Analysis (Step 1+2) ──
    const analyzePromise = (async () => {
      const auditBox = document.getElementById('audit-progress-box');
      const auditStatus = document.getElementById('audit-progress-status');
      const auditPct = document.getElementById('audit-progress-pct');
      const auditFill = document.getElementById('audit-progress-fill');

      if (auditBox) {
        auditBox.style.display = 'block';
        if (auditPct) auditPct.textContent = '15%';
        if (auditFill) auditFill.style.width = '15%';
        if (auditStatus) auditStatus.textContent = 'FFT Spectrogram & Frequency Spectrum (15%)...';
      }
      setStudioPipelineProgress(2, 15, 'FFT Spectrogram & Frequency Spectrum (15%)...', 'Audio DNA Analysis');

      showToast('Smart Studio', 'Analyzing audio DNA (BPM, Key & Sections)...', 'info', 6000);
      if (btnAnalyze) setButtonLoading(btnAnalyze, 'AI Scanning (20%)...');

      let curAuditPct = 20;
      const auditSimInterval = setInterval(() => {
        if (curAuditPct < 85) {
          curAuditPct += 15;
          if (auditPct) auditPct.textContent = `${curAuditPct}%`;
          if (auditFill) auditFill.style.width = `${curAuditPct}%`;
          if (btnAnalyze) btnAnalyze.textContent = `AI Scanning (${curAuditPct}%)...`;

          let stageDesc = `BPM & Harmonic Key Detection (${curAuditPct}%)...`;
          if (curAuditPct >= 70) {
            stageDesc = `Song Sections & Viral Hook Detection (${curAuditPct}%)...`;
          }
          if (auditStatus) auditStatus.textContent = stageDesc;
          setStudioPipelineProgress(2, curAuditPct, stageDesc, 'Audio DNA Analysis');
        }
      }, 380);
      
      try {
        const analyzeRes = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audio_path: state.audioServerPath })
        });
        const analyzeData = await analyzeRes.json();
        clearInterval(auditSimInterval);

        if (auditPct) auditPct.textContent = '100%';
        if (auditFill) auditFill.style.width = '100%';
        if (auditStatus) auditStatus.textContent = `Audio DNA Complete: BPM ${analyzeData.bpm} (100%)`;
        setStudioPipelineProgress(2, 100, `Audio DNA Complete: BPM ${analyzeData.bpm} (100%)`, 'Audio DNA Analysis');
        setTimeout(() => {
          if (auditBox) auditBox.style.display = 'none';
        }, 2000);
        
        if (analyzeData.status === 'success' || analyzeData.status === 'fallback') {
          // Update stats
          const bpmEl = document.getElementById('stat-bpm');
          const energyEl = document.getElementById('stat-energy');
          const keyEl = document.getElementById('stat-key');
          if (bpmEl) bpmEl.textContent = analyzeData.bpm;
          if (keyEl && analyzeData.key) keyEl.textContent = analyzeData.key;
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
          
          if (btnAnalyze) clearButtonLoading(btnAnalyze, 'Analysis Complete (100%)');
          showToast('Audio DNA', `BPM: ${analyzeData.bpm} | Energy: ${Math.round(analyzeData.energy * 100)}% | Mood: ${analyzeData.mood}`, 'success', 4000);

          // ── Step 2: Smart Theme & Palette ──
          const rec = getSmartRecommendation(analyzeData.mood, analyzeData.genre, analyzeData.energy);
          state.theme = rec.theme;
          state.palette = rec.palette;
          if (selectTheme) selectTheme.value = rec.theme;
          if (selectPalette) selectPalette.value = rec.palette;
          
          const themeName = selectTheme ? selectTheme.options[selectTheme.selectedIndex]?.text : rec.theme;
          const paletteName = selectPalette ? selectPalette.options[selectPalette.selectedIndex]?.text : rec.palette;
          setStudioPipelineProgress(2, 100, `Style Selected: ${themeName} (${paletteName})`, 'Style Auto-Matching');
          showToast('Auto-Style', `Theme: ${themeName} | Palette: ${paletteName}`, 'success', 3000);
        }
      } catch (err) {
        clearInterval(auditSimInterval);
        console.error('Smart Pipeline - Analysis failed:', err);
        if (btnAnalyze) clearButtonLoading(btnAnalyze, 'SuperSmart Scan');
        if (auditBox) auditBox.style.display = 'none';
        setStudioPipelineProgress(2, 0, 'Analysis failed', 'Audio DNA Analysis', false);
      }
    })();

    // ── Prepare Lyrics Transcription (Step 3) — runs in PARALLEL with analysis ──
    const lyricsPromise = (async () => {
      if (state.lyrics && state.lyrics.length > 0) return; // Already loaded authentic lyrics — skip Whisper!

      showToast('Smart Studio', 'Transcribing vocals with Whisper AI...', 'info', 8000);
      const langSelect = document.getElementById('select-vocal-lang');
      const modelSelect = document.getElementById('select-whisper-model');
      let targetLang = langSelect ? langSelect.value : 'auto';
      if (!targetLang) targetLang = 'auto';

      // ── SMART LANGUAGE DETECTION ──
      // Only force Khmer if user explicitly chose it in the dropdown.
      // For "auto", let Whisper detect the actual language from the audio.
      // This prevents English songs being transcribed as Khmer gibberish.
      if (targetLang === 'auto') {
        // Check song title/filename for Khmer script as a hint
        const titleText = (state.songTitle || '') + (state.audioPath || '') + (state.audioServerPath || '');
        if (/[\u1780-\u17FF]/.test(titleText)) {
          targetLang = 'km'; // Khmer title → force Khmer for accuracy
        } else {
          targetLang = null; // Let Whisper auto-detect from actual audio content
        }
      }
      
      const useDemucsCheck = document.getElementById('check-use-demucs');
      const useDemucs = useDemucsCheck ? useDemucsCheck.checked : true;
      const targetModel = modelSelect ? modelSelect.value : (targetLang === 'km' ? 'gemini-fast' : 'small');
      try {
        await runAITranscription({ targetLang, targetModel, useDemucs });
      } catch (err) {
        console.error('Smart Pipeline - Lyrics failed:', err);
      }
    })();

    // ── Run BOTH in parallel — saves 3-5 seconds! ──
    await Promise.allSettled([analyzePromise, lyricsPromise]);

    // ── Pipeline Complete ──
    window.__VIDA_PIPELINE_RUNNING = false;
    setStudioPipelineProgress(3, 100, 'Studio Ready: Audio analyzed, styled & synced (100%)', 'Studio Complete');
    showToast('Studio Ready', 'Audio analyzed, styled, and synced — ready to create!', 'success', 5000);
  }

  // ============ Image Upload Handling (Background & Logo) ============
  const btnBg = document.getElementById('btn-upload-bg');
  const inputBg = document.getElementById('bg-file-input');
  if (btnBg && inputBg) {
    btnBg.addEventListener('click', () => inputBg.click());
    inputBg.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (file) {
        const url = URL.createObjectURL(file);
        state.backgroundImageUrl = url;
        
        if (file.type.startsWith('video/')) {
          const vid = document.createElement('video');
          vid.src = url;
          vid.loop = true;
          vid.muted = true;
          vid.play();
          state.bgVideoObj = vid;
          state.bgImageObj = null;
        } else {
          const img = new Image();
          img.src = url;
          state.bgImageObj = img;
          state.bgVideoObj = null;
        }
        
        btnBg.classList.add('active');
        btnBg.innerHTML = `<span class="icon">🖼️</span> ${file.name.substring(0, 20)}`;
        showToast('Background Set', `Using "${file.name}"`, 'success', 2000);

        const badgeBg = document.getElementById('badge-upload-bg');
        if (badgeBg) badgeBg.textContent = '5%';
        setGlobalProgress(5, true, 'Uploading BG');

        try {
          const formData = new FormData();
          formData.append('file', file);
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/api/upload');
          xhr.upload.onprogress = (evt) => {
            if (evt.lengthComputable) {
              const pct = Math.round((evt.loaded / evt.total) * 100);
              if (badgeBg) badgeBg.textContent = `${pct}%`;
              setGlobalProgress(pct, true, 'Uploading BG');
            }
          };
          xhr.onload = () => {
            if (xhr.status === 200) {
              try {
                const data = JSON.parse(xhr.responseText);
                if (data.saved_path) state.bgImagePath = data.saved_path;
                if (badgeBg) badgeBg.textContent = 'Active ✓';
                setGlobalProgress(100, true, 'Uploading BG');
              } catch(e) {}
            } else {
              if (badgeBg) badgeBg.textContent = 'Error';
            }
          };
          xhr.send(formData);
        } catch (err) {
          console.warn('Background server upload error:', err);
        }
      }
    });
  }

  const btnLogo = document.getElementById('btn-upload-logo');
  const inputLogo = document.getElementById('logo-file-input');
  if (btnLogo && inputLogo) {
    btnLogo.addEventListener('click', () => inputLogo.click());
    inputLogo.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (file) {
        const url = URL.createObjectURL(file);
        state.logoImageUrl = url;
        const img = new Image();
        img.src = url;
        state.logoImageObj = img;
        btnLogo.classList.add('active');
        btnLogo.innerHTML = `<span class="icon">🎨</span> ${file.name.substring(0, 20)}`;
        updateBadgeStatusUI();
        showToast('Center Artwork Set', `Using "${file.name}"`, 'success', 2500);

        const badgeLogo = document.getElementById('badge-upload-logo');
        if (badgeLogo) badgeLogo.textContent = '5%';
        setGlobalProgress(5, true, 'Uploading Logo');

        try {
          const formData = new FormData();
          formData.append('file', file);
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/api/upload');
          xhr.upload.onprogress = (evt) => {
            if (evt.lengthComputable) {
              const pct = Math.round((evt.loaded / evt.total) * 100);
              if (badgeLogo) badgeLogo.textContent = `${pct}%`;
              setGlobalProgress(pct, true, 'Uploading Logo');
            }
          };
          xhr.onload = () => {
            if (xhr.status === 200) {
              try {
                const data = JSON.parse(xhr.responseText);
                if (data.saved_path) state.logoImagePath = data.saved_path;
                if (badgeLogo) badgeLogo.textContent = 'Active ✓';
                setGlobalProgress(100, true, 'Uploading Logo');
              } catch(e) {}
            } else {
              if (badgeLogo) badgeLogo.textContent = 'Error';
            }
          };
          xhr.send(formData);
        } catch (err) {
          console.warn('Logo server upload error:', err);
        }
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
          // Auto-trigger download if it's a valid YouTube URL
          if (/youtu\.?be/.test(text.trim()) && btnDownloadYt) {
            btnDownloadYt.click();
          }
        }
      } catch (err) {
        showToast('Paste Failed', 'Clipboard access denied or empty.', 'error');
      }
    });
  }

  // ── Magic Auto-Paste: paste a YouTube URL → auto-starts downloading ──
  if (inputYt && btnDownloadYt) {
    inputYt.addEventListener('paste', (e) => {
      setTimeout(() => {
        const url = inputYt.value.trim();
        if (/youtu\.?be/.test(url) || /youtube\.com/.test(url)) {
          btnDownloadYt.click();
        }
      }, 100); // Small delay to let paste value propagate
    });
  }

  if (inputYt && btnDownloadYt) {
    inputYt.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        btnDownloadYt.click();
      }
    });
  }

  if (btnDownloadYt && inputYt) {
    btnDownloadYt.addEventListener('click', async () => {
      const url = inputYt.value.trim();
      if (!url) {
        showToast('YouTube URL Required', 'Please paste a valid YouTube video link first.', 'warning', 3500);
        inputYt.focus();
        return;
      }
      
      const ytProgressBox = document.getElementById('youtube-progress-box');
      const ytProgressStatus = document.getElementById('youtube-progress-status');
      const ytProgressPct = document.getElementById('youtube-progress-pct');
      const ytProgressFill = document.getElementById('youtube-progress-fill');

      if (ytProgressBox) {
        ytProgressBox.style.display = 'block';
        if (ytProgressPct) ytProgressPct.textContent = '5%';
        if (ytProgressFill) ytProgressFill.style.width = '5%';
        if (ytProgressStatus) ytProgressStatus.textContent = 'Connecting to YouTube stream...';
      }
      setStudioPipelineProgress(1, 5, 'Connecting to YouTube stream (5%)...', 'YouTube Stream');
      setGlobalProgress(5, true, 'YouTube Stream');

      let ytPollInterval = setInterval(async () => {
        try {
          const res = await fetch('/api/youtube/progress');
          if (res.ok) {
            const data = await res.json();
            if (data && typeof data.percent === 'number') {
              const pct = data.percent;
              const stage = data.stage || 'Downloading audio...';
              if (ytProgressPct) ytProgressPct.textContent = `${pct}%`;
              if (ytProgressFill) ytProgressFill.style.width = `${pct}%`;
              if (ytProgressStatus) ytProgressStatus.textContent = stage;
              if (btnDownloadYt) btnDownloadYt.textContent = `⏳ ${pct}%`;
              setStudioPipelineProgress(1, pct, `${stage} (${pct}%)`, 'YouTube Stream');
              setGlobalProgress(pct, true, 'YouTube Stream');
              if (pct >= 100) {
                clearInterval(ytPollInterval);
              }
            }
          }
        } catch (_) {}
      }, 250);

      try {
        window.__VIDA_PIPELINE_RUNNING = true;
        setButtonLoading(btnDownloadYt, '⏳ 5%');
        showToast('Downloading', 'Extracting audio from YouTube...', 'info', 10000);

        const res = await fetch('/api/youtube', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url })
        });
        
        const data = await res.json();
        clearInterval(ytPollInterval);

        if (data.status === 'success') {
          if (ytProgressPct) ytProgressPct.textContent = '100%';
          if (ytProgressFill) ytProgressFill.style.width = '100%';
          if (ytProgressStatus) ytProgressStatus.textContent = `Ready: "${data.title}" (100%)`;
          setStudioPipelineProgress(1, 100, `Ready: "${data.title}" (100%)`, 'YouTube Stream');
          setGlobalProgress(100, true, 'YouTube Stream');
          showToast('Download Complete', `"${data.title}" loaded successfully (100%)`, 'success');
          if (data.lyrics && data.lyrics.length > 0) {
            showToast('Gemini AI Synced', `${data.lyrics.length} authentic lyric lines loaded automatically!`, 'success', 5000);
          }

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

          setTimeout(() => {
            if (ytProgressBox) ytProgressBox.style.display = 'none';
          }, 2000);

          // Smart Pipeline: auto-analyze + auto-lyrics
          await runSmartPipeline();
          
        } else {
          showToast('Download Failed', data.detail || 'Could not extract audio', 'error');
          if (ytProgressStatus) ytProgressStatus.textContent = 'Download failed';
          setStudioPipelineProgress(1, 0, 'Download failed', 'YouTube Stream', false);
          window.__VIDA_PIPELINE_RUNNING = false;
        }
      } catch (err) {
        clearInterval(ytPollInterval);
        console.error("YouTube download failed:", err);
        showToast('Network Error', 'Failed to reach backend', 'error');
        if (ytProgressStatus) ytProgressStatus.textContent = 'Network error';
        window.__VIDA_PIPELINE_RUNNING = false;
      } finally {
        clearInterval(ytPollInterval);
        clearButtonLoading(btnDownloadYt, 'DL');
        if (!state.audioServerPath) {
          window.__VIDA_PIPELINE_RUNNING = false;
        }
      }
    });
  }

  // ============ Load Synth Demo ============
  const btnLoadDemo = document.getElementById('btn-load-demo');
  if (btnLoadDemo && audioPlayer) {
    btnLoadDemo.addEventListener('click', async () => {
      try {
        setButtonLoading(btnLoadDemo, 'Ingesting 25%...');
        setGlobalProgress(25, true, 'Synth Demo');
        setStudioPipelineProgress(1, 25, 'Loading Synthwave Master Track (25%)...', 'Synth Demo');

        const res = await fetch('/api/demo');
        setButtonLoading(btnLoadDemo, 'Synthesizing 75%...');
        setGlobalProgress(75, true, 'Synth Demo');
        setStudioPipelineProgress(1, 75, 'Decoding waveform audio buffer (75%)...', 'Synth Demo');

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

        setStudioPipelineProgress(1, 100, `"${data.title}" Ready (100%)`, 'Synth Demo');
        setGlobalProgress(100, true, 'Synth Demo');
        showToast('Demo Loaded', `"${data.title}" — Ready to play! (100%)`, 'success');
        
      } catch (err) {
        console.error(err);
        showToast('Demo Error', 'Failed to load demo track', 'error');
      } finally {
        clearButtonLoading(btnLoadDemo, 'Load Synth Demo');
      }
    });
  }

  // ============ Load Sinn Sisamouth 60s Golden Era Demo ============
  const btnLoadSinisamut = document.getElementById('btn-load-sinisamut');
  if (btnLoadSinisamut && audioPlayer) {
    btnLoadSinisamut.addEventListener('click', async () => {
      try {
        setButtonLoading(btnLoadSinisamut, 'Restoring Vinyl 30%...');
        setGlobalProgress(30, true, '60s Vinyl Demo');
        setStudioPipelineProgress(1, 30, 'Simulating 33⅓ RPM vinyl groove & tube warmth (30%)...', 'Sinn Sisamouth Demo');

        const res = await fetch('/api/demo/sinisamut');
        setButtonLoading(btnLoadSinisamut, 'Tube Saturation 80%...');
        setGlobalProgress(80, true, '60s Vinyl Demo');
        setStudioPipelineProgress(1, 80, 'Applying warm vintage analog acoustic model (80%)...', 'Sinn Sisamouth Demo');

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

        setStudioPipelineProgress(1, 100, `📻 "${data.title}" Ready (100%)`, 'Sinn Sisamouth Demo');
        setGlobalProgress(100, true, '60s Vinyl Demo');
        showToast('ស៊ីន ស៊ីសាមុត Loaded!', `"${data.title}" — 33⅓ RPM Vinyl Playing (100%)`, 'success', 5000);
        
      } catch (err) {
        console.error(err);
        showToast('Demo Error', 'Failed to load Sinn Sisamouth track', 'error');
      } finally {
        clearButtonLoading(btnLoadSinisamut, 'ស៊ីន ស៊ីសាមុត Demo (60s Vinyl)');
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
      const auditBox = document.getElementById('audit-progress-box');
      const auditStatus = document.getElementById('audit-progress-status');
      const auditPct = document.getElementById('audit-progress-pct');
      const auditFill = document.getElementById('audit-progress-fill');

      if (auditBox) {
        auditBox.style.display = 'block';
        if (auditPct) auditPct.textContent = '15%';
        if (auditFill) auditFill.style.width = '15%';
        if (auditStatus) auditStatus.textContent = 'FFT Spectrogram & Frequency Spectrum (15%)...';
      }
      setButtonLoading(btnAnalyze, 'Scanning DNA (20%)...');
      setStudioPipelineProgress(2, 20, 'Scanning audio DNA (20%)...', 'Audio DNA Scan');

      let curAuditPct = 20;
      const auditSimInterval = setInterval(() => {
        if (curAuditPct < 85) {
          curAuditPct += 15;
          if (auditPct) auditPct.textContent = `${curAuditPct}%`;
          if (auditFill) auditFill.style.width = `${curAuditPct}%`;
          if (btnAnalyze) btnAnalyze.textContent = `AI Scanning (${curAuditPct}%)...`;
          let stageDesc = `BPM & Harmonic Key Detection (${curAuditPct}%)...`;
          if (curAuditPct >= 70) {
            stageDesc = `Song Sections & Viral Hook Detection (${curAuditPct}%)...`;
          }
          if (auditStatus) auditStatus.textContent = stageDesc;
          setStudioPipelineProgress(2, curAuditPct, stageDesc, 'Audio DNA Scan');
        }
      }, 380);

      try {
        const res = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audio_path: state.audioServerPath })
        });
        const data = await res.json();
        clearInterval(auditSimInterval);

        if (auditPct) auditPct.textContent = '100%';
        if (auditFill) auditFill.style.width = '100%';
        if (auditStatus) auditStatus.textContent = `Audio DNA Complete: BPM ${data.bpm} (100%)`;
        setStudioPipelineProgress(2, 100, `Audio DNA Complete: BPM ${data.bpm} (100%)`, 'Audio DNA Scan');
        setTimeout(() => {
          if (auditBox) auditBox.style.display = 'none';
        }, 2200);

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
          
          showToast('Analysis Complete', `BPM: ${data.bpm} | Energy: ${Math.round(data.energy * 100)}% (100%)`, 'success');
          clearButtonLoading(btnAnalyze, 'Analysis Complete (100%)');
        } else {
          clearButtonLoading(btnAnalyze, 'Analysis Failed');
        }
      } catch (err) {
        clearInterval(auditSimInterval);
        console.error(err);
        clearButtonLoading(btnAnalyze, 'Analysis Failed');
        if (auditBox) auditBox.style.display = 'none';
        showToast('Analysis Error', err.message, 'error');
      }
    });
  }

  // ============ AI Transcription Engine with Real-Time Percentage ============
  async function runAITranscription({ targetLang, targetModel, useDemucs = true, forceAI = false }) {
    const btnTranscribe = document.getElementById('btn-transcribe-ai');
    const progressBox = document.getElementById('transcribe-progress-box');
    const progressStatus = document.getElementById('transcribe-progress-status');
    const progressPct = document.getElementById('transcribe-progress-pct');
    const progressFill = document.getElementById('transcribe-progress-fill');

    if (progressBox) progressBox.style.display = 'block';
    if (progressFill) progressFill.style.width = '0%';
    if (progressPct) progressPct.textContent = '0%';
    if (progressStatus) progressStatus.textContent = targetModel === 'qwen3-khmer' ? 'Initializing Qwen3-ASR & Demucs...' : 'Initializing Whisper AI...';
    if (btnTranscribe) setButtonLoading(btnTranscribe, '⏳ AI 0%');

    let currentPercent = 0;
    let isFinished = false;
    let elapsed = 0;

    // Active polling for real-time progress & synchronization
    const pollInterval = setInterval(async () => {
      if (isFinished) return;
      elapsed += 0.8;

      try {
        const res = await fetch('/api/transcribe/progress');
        if (res.ok) {
          const data = await res.json();
          if (data && typeof data.percent === 'number') {
            if (data.percent > 0) {
              currentPercent = Math.max(currentPercent, data.percent);
            }
            if (data.stage && progressStatus) {
              progressStatus.textContent = data.stage;
            }
          }
        }
      } catch (_) {}

      // If we are stuck waiting for something, slowly crawl forward up to a cap
      if (currentPercent < 15) {
        currentPercent = Math.max(currentPercent, Math.min(15, Math.floor(elapsed * 1.5)));
      } else if (currentPercent >= 20 && currentPercent < 42 && progressStatus && progressStatus.textContent.includes('Demucs')) {
        // Demucs vocal isolation running on CPU
        const demucsTicks = Math.min(21, Math.floor((elapsed - 10) * 0.18));
        currentPercent = Math.max(currentPercent, Math.min(41, 20 + demucsTicks));
      }

      const displayPct = Math.min(100, Math.floor(currentPercent));
      if (progressPct) progressPct.textContent = `${displayPct}%`;
      if (progressFill) progressFill.style.width = `${displayPct}%`;
      if (btnTranscribe) btnTranscribe.textContent = `⏳ AI ${displayPct}%`;
      setStudioPipelineProgress(3, displayPct, progressStatus ? progressStatus.textContent : `AI Lyrics (${displayPct}%)...`, 'AI Lyrics Engine');
    }, 800);

    try {
      const hasExistingLyrics = state.lyrics && Array.isArray(state.lyrics) && state.lyrics.length >= 2;
      const res = await fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_path: state.audioServerPath,
          model_size: targetModel,
          language: targetLang,
          use_demucs: !!useDemucs,
          force_ai: !!forceAI,
          song_title: state.songTitle || '',
          artist_name: state.artistName || '',
          lyrics_data: hasExistingLyrics ? state.lyrics : null
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lyric synchronization failed');
      isFinished = true;
      clearInterval(pollInterval);

      if (data.status === 'success' && data.lyrics && data.lyrics.length > 0) {
        currentPercent = 100;
        if (progressPct) progressPct.textContent = '100%';
        if (progressFill) progressFill.style.width = '100%';
        if (progressStatus) progressStatus.textContent = 'Sync Complete (100%)';
        if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Synced 100%');
        setStudioPipelineProgress(3, 100, `Synced ${data.count} lines (100%)`, 'AI Whisper Lyrics');

        state.lyrics = data.lyrics;
        renderLyricsTeleprompter(state.lyrics);
        try {
          localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics));
          if (state.audioServerPath) localStorage.setItem('vida_audio_server_path', state.audioServerPath);
          if (state.songTitle) localStorage.setItem('vida_song_title', state.songTitle);
          if (state.artistName) localStorage.setItem('vida_artist_name', state.artistName);
          if (state.audioUrl) localStorage.setItem('vida_audio_src', state.audioUrl);
        } catch(e) {}
        const sources = { subtitle: 'Captions', 'retrieved-timing': 'Retrieved Captions', ctc_word_alignment: 'Singer Word Alignment', acoustic_estimate: 'Acoustic Estimates' };
        const src = sources[data.source] || 'Whisper AI';
        const langTag = data.detected_language ? ` [${data.detected_language.toUpperCase()}]` : '';
        showToast('Lyrics Ready', `${data.count} lines from ${src}${langTag}. Review singing timing in playback.`, data.source === 'acoustic_estimate' ? 'warning' : 'success', 6000);

        setTimeout(() => {
          if (progressBox) progressBox.style.display = 'none';
        }, 4000);
        return data;
      } else {
        if (progressStatus) progressStatus.textContent = 'No Lyrics Detected';
        if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Auto-Sync Lyrics');
        setStudioPipelineProgress(3, 0, 'No vocal segments detected', 'AI Whisper Lyrics', false);
        showToast('No Lyrics', 'No vocal segments detected in audio', 'info');
        setTimeout(() => {
          if (progressBox) progressBox.style.display = 'none';
        }, 4000);
        return null;
      }
    } catch (err) {
      isFinished = true;
      clearInterval(pollInterval);
      if (progressStatus) progressStatus.textContent = 'Failed';
      if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Auto-Sync Lyrics');
      setStudioPipelineProgress(3, 0, 'Transcription failed', 'AI Whisper Lyrics', false);
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
      let targetLang = langSelect ? langSelect.value : 'km';
      if (!targetLang) targetLang = 'km';
      if (targetLang === 'auto') {
        const isKhmer = /[\u1780-\u17FF]/.test(state.songTitle || '') ||
                        /[\u1780-\u17FF]/.test(state.artistName || '') ||
                        /[\u1780-\u17FF]/.test(state.audioPath || '') ||
                        /[\u1780-\u17FF]/.test(state.audioServerPath || '');
        targetLang = isKhmer ? 'km' : null;
      }
      const useDemucsCheck = document.getElementById('check-use-demucs');
      let useDemucs = useDemucsCheck ? useDemucsCheck.checked : false;
      const targetModel = modelSelect ? modelSelect.value : 'gemini-fast';
      // Auto-skip Demucs if Gemini Cloud AI is chosen to prevent 3-minute CPU freeze!
      if (targetModel === 'gemini-fast') {
        useDemucs = false;
      }
      try {
        await runAITranscription({ targetLang, targetModel, useDemucs, forceAI: true });
      } catch (err) {
        console.error('Manual transcription failed:', err);
      }
    });
  }

  // ============ AI Auto-Fix Spelling Click ============
  const btnAiAutoFix = document.getElementById('btn-ai-auto-fix');
  if (btnAiAutoFix) {
    btnAiAutoFix.addEventListener('click', async () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        showToast('No Lyrics', 'Please transcribe lyrics first before fixing!', 'error');
        return;
      }
      try {
        setButtonLoading(btnAiAutoFix, 'Auto-Fixing...');
        setGlobalProgress(50, true, 'Running LLM Auto-Correction...');
        
        const res = await fetch('/api/lyrics/auto_fix', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lyrics_data: state.lyrics })
        });
        
        const data = await res.json();
        if (data.status === 'success') {
          state.lyrics = data.lyrics;
          renderLyricsTeleprompter(state.lyrics);
          showToast('LLM Fix Complete', 'Phonetic errors successfully auto-corrected!', 'success');
        } else {
          showToast('Auto-Fix Error', 'LLM failed to correct lyrics.', 'error');
        }
      } catch (err) {
        console.error('LLM Auto-Fix failed:', err);
        showToast('Error', 'API error during auto-fix', 'error');
      } finally {
        clearButtonLoading(btnAiAutoFix, 'AI Auto-Fix Spelling');
        setGlobalProgress(100, true, 'Done');
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
      setButtonLoading(btnUploadLrc, '⏳ 15%');
      setGlobalProgress(15, true, 'Parsing Subtitles');

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/lyrics/upload');
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable) {
          const pct = Math.round((evt.loaded / evt.total) * 90);
          btnUploadLrc.textContent = `⏳ ${pct}%`;
          setGlobalProgress(pct, true, 'Parsing Subtitles');
        }
      };
      xhr.onload = () => {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.status === 'success' && data.lyrics && data.count > 0) {
              state.lyrics = data.lyrics;
              renderLyricsTeleprompter(state.lyrics);
              btnUploadLrc.textContent = '100%';
              setGlobalProgress(100, true, 'Subtitles Ready');
              showToast('Lyrics Loaded', `Imported ${data.count} lines with word timing (100%)`, 'success');
              if (btnTranscribe) clearButtonLoading(btnTranscribe, 'Lyrics Synced!');
              setTimeout(() => { btnUploadLrc.textContent = 'Import Sub'; }, 3000);
            } else {
              btnUploadLrc.textContent = 'Import Sub';
              showToast('Import Error', 'Could not parse lyrics from file', 'error');
            }
          } catch(err) {
            btnUploadLrc.textContent = 'Import Sub';
          }
        } else {
          btnUploadLrc.textContent = 'Import Sub';
        }
      };
      xhr.onerror = () => {
        btnUploadLrc.textContent = 'Import Sub';
      };
      xhr.send(formData);
    });
  }

  // ============ Export Video ============
  const selectExportPreset = document.getElementById('select-export-preset');
  if (selectExportPreset) {
    const applyPreset = (val) => {
      if (val === '720p@30') {
        state.renderResolution = '720p';
        state.renderFps = 30;
      } else if (val === '1080p@30') {
        state.renderResolution = '1080p';
        state.renderFps = 30;
      } else if (val === '1080p@60') {
        state.renderResolution = '1080p';
        state.renderFps = 60;
      } else if (val === '480p@30') {
        state.renderResolution = '480p';
        state.renderFps = 30;
      }
    };
    applyPreset(selectExportPreset.value);
    selectExportPreset.addEventListener('change', (e) => applyPreset(e.target.value));
  }

  const btnExport = document.getElementById('btn-export');
  if (btnExport) {
    btnExport.addEventListener('click', async () => {
      if (!state.audioServerPath && !state.audioUrl) {
        showToast('No Audio', 'Please load an audio file before exporting', 'error');
        return;
      }

      const currentFps = state.renderFps || 60;
      const currentRes = state.renderResolution || '1080p';

      // ===== WYSIWYG path: encode the exact preview frames in-browser =====
      try {
        setButtonLoading(btnExport, 'Rendering...');
        const onProgress = (p, label) => {
          const pct = Math.round(Math.min(1, Math.max(0, p)) * 100);
          if (miniFill) miniFill.style.width = `${pct}%`;
          const ms = document.getElementById('export-modal-status');
          if (ms) ms.textContent = `${label || 'Rendering preview frames'} (${pct}%)`;
          setGlobalProgress(pct, pct >= 100, label || 'Exporting');
        };
        showToast('Export Started', `What-you-see-what-you-get ${currentRes} @ ${currentFps} FPS`, 'info', 8000);
        const { supportsFastExport, exportVideoWYSIWYG, exportVideoRealtime } = await import('./core/exporter.js');
        const data = supportsFastExport()
          ? await exportVideoWYSIWYG({ onProgress })
          : await exportVideoRealtime({ onProgress });

        clearButtonLoading(btnExport, 'Export Video');
        if (miniFill) miniFill.style.width = '100%';
        const ms2 = document.getElementById('export-modal-status');
        if (ms2) ms2.textContent = 'Export Complete — identical to preview (100%)!';
        showToast('Export Complete (WYSIWYG)', 'Video matches the preview exactly. Download started.', 'success', 10000);
        if (data.url) {
          const a = document.createElement('a');
          a.href = data.url;
          a.download = '';
          document.body.appendChild(a);
          a.click();
          setTimeout(() => a.remove(), 1000);
        }

        const autopost = document.getElementById('check-youtube-autopost');
        if (autopost && autopost.checked && data.path) {
          try {
            const ytRes = await fetch('/api/export/post-youtube', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                video_path: data.path,
                song_title: state.songTitle,
                artist_name: state.artistName,
                theme: state.theme,
                aspect_ratio: state.aspectRatio,
                privacy: (document.getElementById('select-youtube-privacy') || {}).value || 'public'
              })
            });
            const yt = await ytRes.json();
            if (yt.youtube_url) {
              showToast('YouTube Upload Complete', yt.youtube_url, 'success', 12000);
              window.open(yt.youtube_url, '_blank');
            } else {
              showToast('YouTube Upload Notice', yt.detail || 'Upload failed', 'warning', 8000);
            }
          } catch (ytErr) {
            showToast('YouTube Upload Notice', ytErr.message, 'warning', 8000);
          }
        }
        return;
      } catch (clientErr) {
        console.warn('[VIDA Export] In-browser export unavailable, using server renderer:', clientErr);
        showToast('Using Server Renderer', `In-browser export unavailable (${clientErr.message})`, 'warning', 6000);
      }

      // ===== Legacy path: server-side re-render (approximate look) =====
      try {
        setButtonLoading(btnExport, 'Rendering...');
        showToast('Export Started', `Server rendering ${currentRes} @ ${currentFps} FPS (approximate look)`, 'info', 15000);

        const res = await fetch('/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            audio_path: state.audioServerPath,
            theme: state.theme,
            palette: state.palette,
            aspect_ratio: state.aspectRatio,
            fps: currentFps,
            resolution: currentRes,
            song_title: state.songTitle,
            artist_name: state.artistName,
            title_scale: state.titleScale || 1.5,
            background_image: state.bgImagePath,
            logo_image: state.logoImagePath,
            center_text_primary: state.centerTextPrimary !== undefined ? state.centerTextPrimary : "VIDA",
            center_text_secondary: state.centerTextSecondary !== undefined ? state.centerTextSecondary : "FLUID WAVE",
            show_center_text: state.showCenterText !== false,
            lyrics_data: state.showLyrics === false ? [] : state.lyrics,
            lyric_style: state.showLyrics === false ? "none" : state.lyricStyle,
            bar_count: state.barCount,
            bass_boost: state.bassBoost,
            ...getTranslationRenderOptions(),
            auto_post_youtube: document.getElementById('check-youtube-autopost') ? document.getElementById('check-youtube-autopost').checked : false,
            youtube_privacy: document.getElementById('select-youtube-privacy') ? document.getElementById('select-youtube-privacy').value : 'public'
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

  // ============ YouTube Channel Auth Manager ============
  const btnYtConnect = document.getElementById('btn-youtube-connect');
  const ytConnectIcon = document.getElementById('yt-connect-icon');
  const ytConnectText = document.getElementById('yt-connect-text');

  async function checkYouTubeAuthStatus() {
    try {
      const res = await fetch('/api/youtube/auth/status');
      const data = await res.json();
      if (data.connected && btnYtConnect) {
        btnYtConnect.style.background = 'rgba(16, 185, 129, 0.15)';
        btnYtConnect.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        btnYtConnect.style.color = '#34d399';
        if (ytConnectIcon) ytConnectIcon.textContent = '🟢';
        if (ytConnectText) ytConnectText.textContent = data.channel_title ? data.channel_title.substring(0, 14) : 'Connected';
        btnYtConnect.title = `Connected Channel: ${data.channel_title || 'Authorized'}`;
        delete btnYtConnect.dataset.enableUrl;
      } else if (data.needs_api_enable && btnYtConnect) {
        btnYtConnect.style.background = 'rgba(245, 158, 11, 0.2)';
        btnYtConnect.style.borderColor = 'rgba(245, 158, 11, 0.5)';
        btnYtConnect.style.color = '#fbbf24';
        if (ytConnectIcon) ytConnectIcon.textContent = '⚠️';
        if (ytConnectText) ytConnectText.textContent = 'Enable API';
        btnYtConnect.title = 'YouTube API is disabled in Google Cloud. Click to open and click ENABLE!';
        btnYtConnect.dataset.enableUrl = data.enable_url;
      } else if (btnYtConnect) {
        btnYtConnect.style.background = 'rgba(239, 68, 68, 0.15)';
        btnYtConnect.style.borderColor = 'rgba(239, 68, 68, 0.4)';
        btnYtConnect.style.color = '#f87171';
        if (ytConnectIcon) ytConnectIcon.textContent = '🔴';
        if (ytConnectText) ytConnectText.textContent = 'Connect YT';
        btnYtConnect.title = 'Click to authorize your YouTube channel for auto-posting';
        delete btnYtConnect.dataset.enableUrl;
      }
      return data;
    } catch (_) {
      return { connected: false };
    }
  }

  if (btnYtConnect) {
    btnYtConnect.addEventListener('click', async () => {
      // If needs API enable, open the direct link directly!
      if (btnYtConnect.dataset.enableUrl) {
        window.open(btnYtConnect.dataset.enableUrl, '_blank');
        showToast('Enable YouTube API', 'Opening Google Cloud Console — click the blue ENABLE button!', 'warning', 8000);
        return;
      }
      setButtonLoading(btnYtConnect, 'Connecting...');
      showToast('YouTube Sign-In', 'Opening browser to authorize your YouTube channel...', 'info', 6000);
      try {
        await fetch('/api/youtube/auth/connect', { method: 'POST' });
        // Poll status every 2 seconds for up to 60 seconds
        let attempts = 0;
        const authPoll = setInterval(async () => {
          attempts++;
          const authData = await checkYouTubeAuthStatus();
          if (authData.connected || authData.needs_api_enable || attempts > 30) {
            clearInterval(authPoll);
            if (authData.connected) {
              clearButtonLoading(btnYtConnect, 'Connected');
              showToast('YouTube Connected!', 'Your channel is now authorized for auto-posting!', 'success', 5000);
            } else if (authData.needs_api_enable) {
              clearButtonLoading(btnYtConnect, 'Enable API');
              showToast('Enable YouTube API', 'Login authorized! Click "Enable API" to enable YouTube API on Google Cloud', 'warning', 10000);
            } else {
              clearButtonLoading(btnYtConnect, 'Connect YT');
            }
          }
        }, 2000);
      } catch (err) {
        clearButtonLoading(btnYtConnect, 'Connect YT');
        showToast('Auth Error', err.message, 'error');
      }
    });
  }

  // Check auth status on startup
  checkYouTubeAuthStatus();

  // ============ Background Render & Mini PIP Widget Controls ============
  const miniWidget = document.getElementById('export-mini-widget');
  const miniPct = document.getElementById('mini-render-pct');
  const miniFill = document.getElementById('mini-render-fill');
  const miniFrames = document.getElementById('mini-render-frames');
  const miniFps = document.getElementById('mini-render-fps');

  let isRenderMinimized = false;

  const btnMinimizeRender = document.getElementById('btn-minimize-render');
  const btnRunInBgAction = document.getElementById('btn-run-in-bg-action');
  const btnExpandRender = document.getElementById('btn-expand-render');

  function minimizeRenderProgress() {
    isRenderMinimized = true;
    const modal = document.getElementById('export-progress-modal');
    if (modal) modal.style.display = 'none';
    if (miniWidget) miniWidget.style.display = 'block';
    showToast('Background Render Active', 'Rendering in background — you can freely work in the studio!', 'info', 4000);
  }

  function expandRenderProgress() {
    isRenderMinimized = false;
    if (miniWidget) miniWidget.style.display = 'none';
    const modal = document.getElementById('export-progress-modal');
    if (modal) modal.style.display = 'flex';
  }

  if (btnMinimizeRender) btnMinimizeRender.addEventListener('click', minimizeRenderProgress);
  if (btnRunInBgAction) btnRunInBgAction.addEventListener('click', minimizeRenderProgress);
  if (btnExpandRender) btnExpandRender.addEventListener('click', (e) => { e.stopPropagation(); expandRenderProgress(); });
  if (miniWidget) miniWidget.addEventListener('click', expandRenderProgress);

  function pollRenderProgress(jobId) {
    const modal = document.getElementById('export-progress-modal');
    const modalTitle = document.getElementById('export-modal-title');
    const modalPct = document.getElementById('export-modal-pct');
    const modalFill = document.getElementById('export-modal-fill');
    const modalStatus = document.getElementById('export-modal-status');
    const modalFrames = document.getElementById('export-modal-frames');
    const modalFps = document.getElementById('export-modal-fps');
    const modalEta = document.getElementById('export-modal-eta');

    if (modalTitle) modalTitle.textContent = `Rendering ${state.renderResolution || '720p'} @ ${state.renderFps || 30} FPS Video`;

    if (!isRenderMinimized && modal) {
      modal.style.display = 'flex';
    } else if (miniWidget) {
      miniWidget.style.display = 'block';
    }
    setGlobalProgress(5, true);

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/progress/${jobId}`);
        const data = await res.json();
        
        const btnExport = document.getElementById('btn-export');
        const pct = Math.round(data.percent || 0);

        if (modalPct) modalPct.textContent = `${pct}%`;
        if (modalFill) modalFill.style.width = `${pct}%`;
        if (miniPct) miniPct.textContent = `${pct}%`;
        if (miniFill) miniFill.style.width = `${pct}%`;
        if (btnExport) btnExport.textContent = `Rendering ${pct}%`;
        setGlobalProgress(pct, true);

        if (data.frame && data.total_frames) {
          if (modalFrames) modalFrames.textContent = `Frame: ${data.frame} / ${data.total_frames}`;
          if (miniFrames) miniFrames.textContent = `${data.frame}/${data.total_frames}`;
        }
        if (data.fps) {
          if (modalFps) modalFps.textContent = `Speed: ${Math.round(data.fps)} FPS`;
          if (miniFps) miniFps.textContent = `${Math.round(data.fps)} FPS`;
        }
        if (modalEta) {
          if (data.eta_seconds && data.eta_seconds > 0 && pct < 100) {
            const m = Math.floor(data.eta_seconds / 60);
            const s = Math.floor(data.eta_seconds % 60);
            modalEta.textContent = `ETA: ${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
          } else {
            modalEta.textContent = `ETA: --:--`;
          }
        }

        if (data.status === 'uploading') {
          const uploadPct = Math.round(data.upload_percent || 0);
          if (modalStatus) modalStatus.textContent = data.message || `Uploading to YouTube (${uploadPct}%)...`;
          if (modalPct) modalPct.textContent = `${uploadPct}%`;
          if (modalFill) modalFill.style.width = `${uploadPct}%`;
          if (miniPct) miniPct.textContent = `${uploadPct}%`;
          if (miniFill) miniFill.style.width = `${uploadPct}%`;
          if (btnExport) btnExport.textContent = `Uploading ${uploadPct}%`;
          if (modalFrames) modalFrames.textContent = `Auto-Posting: ${uploadPct}% sent to YouTube`;
          if (modalFps) modalFps.textContent = `Cloud Upload`;
          setGlobalProgress(uploadPct, true);
        }

        if (data.status === 'completed') {
          clearInterval(interval);
          if (modalPct) modalPct.textContent = '100%';
          if (modalFill) modalFill.style.width = '100%';
          if (miniPct) miniPct.textContent = '100%';
          if (miniFill) miniFill.style.width = '100%';
          if (modalStatus) modalStatus.textContent = 'Video Rendered Successfully (100%)!';
          setGlobalProgress(100, true);

          clearButtonLoading(btnExport, 'Export Video');
          
          if (data.youtube_url) {
            showToast('Export & YouTube Upload Complete!', `Video rendered and auto-posted to YouTube:\n${data.youtube_url}`, 'success', 15000);
            console.log("YouTube URL:", data.youtube_url);
            window.open(data.youtube_url, '_blank');
          } else if (data.youtube_error) {
            showToast('YouTube Upload Notice', `Video rendered, but YouTube upload failed:\n${data.youtube_error}`, 'warning', 10000);
          } else {
            showToast('Export Complete!', 'Your 60 FPS video is ready for download (100%)', 'success', 8000);
          }
          
          setTimeout(() => {
            if (modal) modal.style.display = 'none';
            if (miniWidget) miniWidget.style.display = 'none';
            isRenderMinimized = false;
          }, 3000);

          if (data.output_url) {
            const a = document.createElement('a');
            a.href = data.output_url;
            a.download = data.output_filename || '';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => a.remove(), 1000);
          }
        } else if (data.status === 'failed') {
          clearInterval(interval);
          if (modalStatus) modalStatus.textContent = `Render Failed: ${data.error || 'Unknown error'}`;
          clearButtonLoading(btnExport, 'Export Video');
          showToast('Render Failed', data.error || 'Unknown error', 'error');
          setTimeout(() => {
            if (modal) modal.style.display = 'none';
          }, 3500);
        } else {
          if (modalStatus) modalStatus.textContent = `Compositing visualizer & audio at 60 FPS (${pct}%)...`;
        }
      } catch (e) {
        clearInterval(interval);
      }
    }, 1000);
  }

  // ============ Draw Waveform to Canvas ============
  function drawWaveform(peaks) {
    if (peaks && peaks.length > 0) {
      window.__VIDA_AUDIO_PEAKS = peaks;
    }
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
  
  window.loadAudioTrack = loadAudioTrack;
  window.runSmartPipeline = runSmartPipeline;
});

// ============ Local Library / Media Pool ============
document.addEventListener('DOMContentLoaded', () => {
  const btnOpenLibrary = document.getElementById('btn-open-library');
  const btnCloseLibrary = document.getElementById('btn-close-library-modal');
  const libraryModal = document.getElementById('local-library-modal');
  const fileList = document.getElementById('library-file-list');

  if (btnOpenLibrary && libraryModal) {
    btnOpenLibrary.addEventListener('click', async () => {
      libraryModal.style.display = 'flex';
      if (fileList) fileList.innerHTML = '<div class="ui-empty">Loading media…</div>';
      
      try {
        const res = await fetch('/api/library');
        const data = await res.json();
        
        if (data.status === 'success' && data.files) {
          fileList.innerHTML = '';
          if (data.files.length === 0) {
             fileList.innerHTML = '<div class="ui-empty">No files found. Upload a track or download a YouTube video first.</div>';
             return;
          }
          
          data.files.forEach(f => {
            const el = document.createElement('div');
            el.className = 'lib-row';
            
            const icon = f.type === 'video' ? '🎬' : '🎵';
            
            el.innerHTML = `
              <span class="lib-row-ico">${icon}</span>
              <div class="lib-row-main">
                <div class="lib-row-name">${f.name}</div>
                <div class="lib-row-type">${f.type.toUpperCase()}</div>
              </div>
            `;
            
            el.addEventListener('click', () => {
              libraryModal.style.display = 'none';
              
              const nameNoExt = f.name.replace(/\.[^/.]+$/, "");
              
              // Load the file as if it was uploaded using the robust loadAudioTrack method
              if (window.loadAudioTrack) {
                window.loadAudioTrack({
                  src: f.url,
                  serverPath: f.path,
                  filename: f.name,
                  title: nameNoExt,
                  artist: "Unknown",
                  autoPlay: true
                });
              } else {
                console.error("loadAudioTrack not found!");
              }
              
              // Auto-fill title
              const inputTitle = document.getElementById('input-song-title');
              if (inputTitle) inputTitle.value = nameNoExt;
              
              showToast('Media Loaded', `Loaded ${f.name} from Library`, 'success');
              
              // Smart Pipeline: auto-analyze + auto-lyrics
              if (window.runSmartPipeline) {
                setTimeout(() => window.runSmartPipeline(), 500);
              }
            });
            
            fileList.appendChild(el);
          });
        }
      } catch (err) {
        if (fileList) fileList.innerHTML = `<div class="ui-empty ui-empty--bad">Error loading library: ${err.message}</div>`;
      }
    });
  }

  if (btnCloseLibrary && libraryModal) {
    btnCloseLibrary.addEventListener('click', () => {
      libraryModal.style.display = 'none';
    });
  }

  // ============ Desktop UI Lifecycle & Heartbeat ============
  function sendDesktopHeartbeat() {
    fetch('/api/system/heartbeat', { method: 'POST' }).catch(() => {});
  }
  // Heartbeat every 2.5 seconds
  setInterval(sendDesktopHeartbeat, 2500);
  sendDesktopHeartbeat();

  // Multi-terminal support: Keep session alive without shutting down server or closing window
});
