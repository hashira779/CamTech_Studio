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

/** The audio file to export / send: the clean copy when chosen, else the song itself. */
export function activeAudioPath() {
  return (state.cleanAudio && state.cleanAudio.song === song() && state.cleanAudio.path) || song();
}

function choices() {
  try { return JSON.parse(localStorage.getItem(CHOICE_KEY) || '{}'); } catch (_) { return {}; }
}

function remember(path) {
  const all = choices();
  if (path) all[song()] = path; else delete all[song()];
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
function swapSource(url) {
  const p = byId('audio-player');
  if (!p || !url) return;
  const t = p.currentTime;
  const playing = !p.paused;
  if (p.src.endsWith(url)) return;
  p.src = url;
  p.addEventListener('loadedmetadata', () => {
    p.currentTime = Math.min(t, p.duration || t);
    if (playing) p.play().catch(() => {});
  }, { once: true });
}

function use(which) {
  const version = which === 'clean' ? wanted() || versions.find((v) => v.path === state.cleanAudio?.path) : null;
  if (which === 'clean' && !version) return;
  state.cleanAudio = version ? { ...version, song: song() } : null;
  swapSource(version ? version.url : state.audioUrl);
  setSeg('clean-use', 'use', version ? 'clean' : 'original');
  remember(version ? version.path : null);
  if (version) status(`Playing and exporting the clean copy (${version.strength}${version.voice_forward ? ', voice forward' : ''}).`);
}

function updateCleanButton() {
  const btn = byId('clean-use')?.querySelector('[data-use="clean"]');
  if (!btn) return;
  const ok = Boolean(wanted() || state.cleanAudio);
  btn.disabled = !ok;
  btn.classList.toggle('is-disabled', !ok);
}

async function refresh() {
  const current = song();
  state.cleanAudio = null;
  versions = [];
  setSeg('clean-use', 'use', 'original');
  status('');
  if (!current) return;
  try {
    const data = await (await fetch(`/api/audio/clean?audio_path=${encodeURIComponent(current)}`)).json();
    if (song() !== current) return;
    versions = data.versions || [];
    const voice = byId('clean-voice');
    const note = byId('clean-voice-note');
    if (voice) voice.disabled = !data.voice_forward_available;
    if (note) note.hidden = Boolean(data.voice_forward_available);
    const saved = versions.find((v) => v.path === choices()[current]);
    if (saved) {
      strength = saved.strength;
      setSeg('clean-strength', 'strength', strength);
      if (voice) voice.checked = saved.voice_forward;
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
  btn.disabled = true;
  status('Cleaning… about 20–30 seconds.');
  try {
    const res = await fetch('/api/audio/clean', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio_path: current, strength, voice_forward: Boolean(byId('clean-voice')?.checked) }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not clean this song');
    if (song() !== current) return;
    versions = versions.filter((v) => v.path !== data.path).concat([data]);
    use('clean');
    const drop = (data.before && data.after) ? ` (Noise: ${data.before.noise_floor_db} dB ➔ ${data.after.noise_floor_db} dB)` : '';
    status(`Done in ${data.seconds}s${drop}. Switch Original / Clean while it plays to compare by ear.`);
  } catch (err) {
    status(err.message);
    showToast('Clean old recording', err.message, 'warning', 6000);
  } finally {
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
