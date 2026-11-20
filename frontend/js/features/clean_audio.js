// "Clean old recording" in the Audio tab: makes a cleaned copy of the song (backend/audio_restore.py)
// and lets the user play and export either the original or the clean one. The original file is
// never changed, and the lyrics stay tied to it: only the player's source and the exported audio
// switch. The choice is remembered per song.

import { state } from '../core/state.js';
import { showToast } from '../ui/feedback.js';

const CHOICE_KEY = 'vida_clean_choice';
const byId = (id) => document.getElementById(id);
const song = () => state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';

let versions = [];
let strength = 'medium';
let animTimer = null;

function startProcessingAnimation(voiceForward) {
  const card = byId('clean-processing-card');
  const bar = byId('clean-progress-bar');
  const stepEl = byId('clean-current-step');
  const pctEl = byId('clean-percent-text');
  const timerBadge = byId('clean-timer-badge');
  const btn = byId('btn-clean-audio');
  const spinner = byId('clean-btn-spinner');
  const label = byId('clean-btn-label');

  if (card) card.hidden = false;
  if (spinner) spinner.hidden = false;
  if (label) label.textContent = 'Restoring audio…';
  if (btn) btn.classList.add('is-processing');

  const startMs = Date.now();
  if (animTimer) clearInterval(animTimer);

  const steps = voiceForward ? [
    { at: 0, pct: 10, text: 'Stage 1: Measuring loudness & DC offset…' },
    { at: 3, pct: 25, text: 'Stage 2: Filtering 50/60 Hz hum & subsonic rumble…' },
    { at: 8, pct: 45, text: 'Stage 3: Demucs AI stem separation (Vocals + Band)…' },
    { at: 22, pct: 70, text: 'Stage 4: Widening stereo backing band & vocal pocket…' },
    { at: 38, pct: 90, text: 'Stage 5: Analog tape warmth & broadcast limiter…' },
  ] : [
    { at: 0, pct: 12, text: 'Stage 1: Measuring loudness & DC offset…' },
    { at: 3, pct: 32, text: 'Stage 2: Filtering 50/60 Hz hum & subsonic rumble…' },
    { at: 8, pct: 58, text: 'Stage 3: Adaptive spectral de-hiss & de-crackle…' },
    { at: 16, pct: 82, text: 'Stage 4: Golden Era tape warmth & vocal presence…' },
    { at: 24, pct: 92, text: 'Stage 5: True-peak limiting & audio remaster…' },
  ];

  animTimer = setInterval(() => {
    const elapsedSec = (Date.now() - startMs) / 1000;
    const m = Math.floor(elapsedSec / 60);
    const s = Math.floor(elapsedSec % 60);
    if (timerBadge) {
      timerBadge.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    let cur = steps[0];
    for (let i = steps.length - 1; i >= 0; i--) {
      if (elapsedSec >= steps[i].at) {
        cur = steps[i];
        break;
      }
    }

    const targetPct = Math.min(95, cur.pct + (elapsedSec - cur.at) * 0.7);
    if (bar) bar.style.width = `${targetPct.toFixed(1)}%`;
    if (pctEl) pctEl.textContent = `${Math.round(targetPct)}%`;
    if (stepEl) stepEl.textContent = cur.text;
  }, 200);
}

function stopProcessingAnimation(success = true) {
  if (animTimer) {
    clearInterval(animTimer);
    animTimer = null;
  }
  const card = byId('clean-processing-card');
  const bar = byId('clean-progress-bar');
  const stepEl = byId('clean-current-step');
  const pctEl = byId('clean-percent-text');
  const btn = byId('btn-clean-audio');
  const spinner = byId('clean-btn-spinner');
  const label = byId('clean-btn-label');

  if (bar) bar.style.width = success ? '100%' : '0%';
  if (pctEl) pctEl.textContent = success ? '100%' : '0%';
  if (stepEl) stepEl.textContent = success ? '✨ Audio restored successfully!' : 'Restoration stopped';

  setTimeout(() => {
    if (card) card.hidden = true;
    if (spinner) spinner.hidden = true;
    if (label) label.textContent = 'Clean this song';
    if (btn) btn.classList.remove('is-processing');
  }, 2200);
}

/** The audio file to export / send: the clean copy when chosen, else the song itself. */
export function activeAudioPath() {
  return (state.cleanAudio && state.cleanAudio.song === song() && state.cleanAudio.path) || song();
}

export function isCleanAudioActive() {
  return Boolean(state.cleanAudio && state.cleanAudio.song === song() && state.cleanAudio.path);
}

export function getCleanAudioInfo() {
  if (isCleanAudioActive()) {
    return {
      isClean: true,
      path: state.cleanAudio.path,
      strength: state.cleanAudio.strength,
      voice_forward: state.cleanAudio.voice_forward,
      label: `Clean (${state.cleanAudio.strength || 'Restored'}${state.cleanAudio.voice_forward ? ' + Stems' : ''})`,
    };
  }
  return {
    isClean: false,
    path: song(),
    label: 'Original Audio',
  };
}

const normPath = (p) => String(p || '').replace(/\\/g, '/').trim().toLowerCase();

function choices() {
  try { return JSON.parse(localStorage.getItem(CHOICE_KEY) || '{}'); } catch (_) { return {}; }
}

function remember(path, isCleanChosen = true) {
  const all = choices();
  const key = normPath(song());
  if (key) {
    if (path && isCleanChosen) {
      all[key] = { path, chosen: 'clean', time: Date.now() };
    } else {
      all[key] = { path: null, chosen: 'original', time: Date.now() };
    }
  }
  try { localStorage.setItem(CHOICE_KEY, JSON.stringify(all)); } catch (_) {}
}

function wanted() {
  const voice = byId('clean-voice')?.checked;
  return versions.find((v) => v.strength === strength && v.voice_forward === Boolean(voice));
}

function setSeg(groupId, attr, value) {
  byId(groupId)?.querySelectorAll('.ui-seg-btn').forEach((b) => {
    const on = b.dataset[attr] === value;
    b.classList.toggle('is-active', on);
    b.setAttribute('aria-pressed', String(on));
  });
}

function status(text) {
  const el = byId('clean-status');
  if (el) el.textContent = text;
}

/** Plays `url` from the same moment, keeping play / pause. */
function swapSource(url, force = false) {
  const p = byId('audio-player');
  if (!p || !url) return;
  const t = p.currentTime;
  const playing = !p.paused;
  const cleanUrl = url.split('?')[0];
  if (!force && p.src.split('?')[0].endsWith(cleanUrl)) return;
  p.src = force ? `${cleanUrl}?v=${Date.now()}` : url;
  p.addEventListener('loadedmetadata', () => {
    p.currentTime = Math.min(t, p.duration || t);
    if (playing) p.play().catch(() => {});
  }, { once: true });
}

function use(which, force = false) {
  const version = which === 'clean'
    ? (wanted() || (state.cleanAudio && versions.find((v) => normPath(v.path) === normPath(state.cleanAudio.path))) || versions[versions.length - 1] || null)
    : null;
  if (which === 'clean' && !version) return;
  state.cleanAudio = version ? { ...version, song: song() } : null;
  swapSource(version ? version.url : state.audioUrl, force);
  setSeg('clean-use', 'use', version ? 'clean' : 'original');
  remember(version ? version.path : null, Boolean(version));
  const dlRow = byId('clean-download-row');
  const dlBtn = byId('btn-download-clean');
  if (dlRow && dlBtn) {
    if (version && version.url) {
      dlBtn.href = version.url;
      dlRow.hidden = false;
    } else {
      dlRow.hidden = true;
    }
  }
  if (version) status(`Playing and exporting the clean copy (${version.strength}${version.voice_forward ? ', voice forward' : ''}).`);
}

function updateCleanButton() {
  const btn = byId('clean-use')?.querySelector('[data-use="clean"]');
  if (btn) {
    const ok = Boolean(wanted() || state.cleanAudio);
    btn.disabled = !ok;
    btn.classList.toggle('is-disabled', !ok);
  }
  const voice = byId('clean-voice');
  const engineSelect = byId('clean-stem-engine');
  if (engineSelect && voice) {
    engineSelect.disabled = !voice.checked;
    engineSelect.style.opacity = voice.checked ? '1' : '0.55';
  }
}

async function refresh() {
  const current = song();
  state.cleanAudio = null;
  versions = [];
  setSeg('clean-use', 'use', 'original');
  status('');
  const voice = byId('clean-voice');
  const note = byId('clean-voice-note');
  if (voice) voice.disabled = false;
  if (note) note.hidden = true;
  updateCleanButton();
  if (!current) return;
  try {
    const data = await (await fetch(`/api/audio/clean?audio_path=${encodeURIComponent(current)}`)).json();
    if (song() !== current) return;
    versions = data.versions || [];
    const entry = choices()[normPath(current)] || choices()[current];
    const savedPath = (typeof entry === 'object' && entry !== null) ? entry.path : entry;
    const userWantsClean = (typeof entry === 'object' && entry !== null) ? (entry.chosen === 'clean') : Boolean(savedPath);

    let matched = null;
    if (savedPath) {
      matched = versions.find((v) => normPath(v.path) === normPath(savedPath));
    }
    if (!matched && userWantsClean && versions.length > 0) {
      matched = versions[versions.length - 1];
    }

    if (matched && userWantsClean) {
      strength = matched.strength;
      setSeg('clean-strength', 'strength', strength);
      if (voice) voice.checked = matched.voice_forward;
      use('clean');
    }
  } catch (_) { /* the panel stays on Original */ }
  updateCleanButton();
}

async function clean() {
  const btn = byId('btn-clean-audio');
  const current = song();
  if (!current) {
    showToast('No Song', 'Load a song first.', 'info', 2500);
    return;
  }

  // Release active file locks on Windows if the player is currently playing a clean audio file
  const player = byId('audio-player');
  const wasPlaying = player && !player.paused;
  const curSrc = player?.src || '';
  if (player && curSrc.includes('/uploads/clean/')) {
    const curTime = player.currentTime;
    player.src = state.audioUrl || '';
    player.currentTime = curTime;
    if (wasPlaying) player.play().catch(() => {});
  }

  btn.disabled = true;
  const isVoiceForward = Boolean(byId('clean-voice')?.checked);
  startProcessingAnimation(isVoiceForward);
  status('');
  let success = false;
  try {
    const stemEngine = byId('clean-stem-engine')?.value || 'uvr_kim_vocal_2';
    const eqSub = parseFloat(byId('eq-sub')?.value || 0);
    const eqMid = parseFloat(byId('eq-mid')?.value || 0);
    const eqHigh = parseFloat(byId('eq-high')?.value || 0);
    const res = await fetch('/api/audio/clean', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_path: current,
        strength,
        voice_forward: isVoiceForward,
        stem_engine: stemEngine,
        eq_sub: eqSub,
        eq_mid: eqMid,
        eq_high: eqHigh,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not clean this song');
    if (song() !== current) return;
    versions = versions.filter((v) => normPath(v.path) !== normPath(data.path)).concat([data]);
    remember(data.path, true);
    use('clean', true);
    success = true;
    const drop = (data.before && data.after) ? ` (Noise: ${data.before.noise_floor_db} dB ➔ ${data.after.noise_floor_db} dB)` : '';
    status(`Done in ${data.seconds}s${drop}. Switch Original / Clean while it plays to compare by ear.`);
  } catch (err) {
    status(err.message);
    showToast('Clean old recording', err.message, 'warning', 6000);
  } finally {
    stopProcessingAnimation(success);
    btn.disabled = false;
    updateCleanButton();
  }
}

export function initCleanAudio() {
  byId('clean-strength')?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-strength]');
    if (!b) return;
    strength = b.dataset.strength;
    setSeg('clean-strength', 'strength', strength);
    if (strength === 'uvr_stems') {
      const v = byId('clean-voice');
      if (v) v.checked = true;
    }
    updateCleanButton();
  });
  byId('clean-voice')?.addEventListener('change', updateCleanButton);
  byId('btn-clean-audio')?.addEventListener('click', clean);
  byId('clean-use')?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-use]');
    if (b && !b.disabled) use(b.dataset.use);
  });
  // A different song was loaded: start from its own saved choice.
  let last = null;
  byId('audio-player')?.addEventListener('loadedmetadata', () => {
    if (song() !== last) { last = song(); refresh(); }
  });
  last = song();
  refresh();
}
