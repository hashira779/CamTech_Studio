// Every re-sync (Paste & Align, Re-Sync to Music, Double-Check, Auto-Sync) goes through
// applySyncResult, so:
//   - lines the user timed by hand (Tap sync, or a typed time) keep that timing: an aligner
//     result never overwrites them. Lines are matched by their text, so this holds even when
//     lines were added or split between syncs.
//   - the lyrics as they were before the sync are kept, and "↶ Undo last sync" brings them back.

import { state } from '../core/state.js';
import { showToast } from '../ui/feedback.js';
import { refit } from './tap_sync.js';

const HAND_TIMED = new Set(['manual', 'tapped']);
const PREV_KEY = 'vida_lyrics_before_sync';
const byId = (id) => document.getElementById(id);
const lineKey = (t) => String(t || '').replace(/[\s\p{P}\p{S}]+/gu, '').toLowerCase();
const songKey = () => state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
const copy = (x) => JSON.parse(JSON.stringify(x));

/** Pairs of (old index, new index) for lines with the same text, in order (longest common run). */
function matchLines(oldLines, newLines) {
  const a = oldLines.map((l) => lineKey(l.text));
  const b = newLines.map((l) => lineKey(l.text));
  const n = a.length, m = b.length;
  const L = Array.from({ length: n + 1 }, () => new Int16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
    L[i][j] = a[i] && a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  }
  const pairs = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] && a[i] === b[j]) { pairs.push([i, j]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) i++;
    else j++;
  }
  return pairs;
}

/** Copies hand-set timings from the old lines onto the new ones and makes their neighbours fit. */
export function keepHandTimings(oldLines, newLines) {
  const kept = new Set();
  for (const [i, j] of matchLines(oldLines, newLines)) {
    const o = oldLines[i];
    if (!HAND_TIMED.has(o.timing_source)) continue;
    const words = copy(o.words || []);
    Object.assign(newLines[j], { start: o.start, end: o.end, words, confidence: o.confidence ?? 1, timing_source: o.timing_source });
    kept.add(j);
  }
  // Aligned neighbours give way to the hand-set lines, never the other way round.
  for (const j of kept) {
    const line = newLines[j];
    const prev = newLines[j - 1];
    const next = newLines[j + 1];
    if (prev && !kept.has(j - 1) && Number(prev.end) > Number(line.start) - 0.05) {
      refit(prev, Math.min(Number(prev.start), Number(line.start) - 0.35), Number(line.start) - 0.05);
    }
    if (next && !kept.has(j + 1) && Number(next.start) < Number(line.end) + 0.05) {
      const s = Number(line.end) + 0.05;
      refit(next, s, Math.max(Number(next.end), s + 0.6));
    }
  }
  return kept.size;
}

function updateUndoButton() {
  const btn = byId('btn-undo-sync');
  if (!btn) return;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(PREV_KEY) || 'null'); } catch (_) {}
  btn.hidden = !(saved && saved.song === songKey() && Array.isArray(saved.lyrics) && saved.lyrics.length);
}

/**
 * Use this instead of `state.lyrics = data.lyrics` after any sync. Remembers the lyrics as they
 * were, keeps hand-set timings, and returns how many lines kept them.
 */
export function applySyncResult(newLyrics) {
  const old = state.lyrics || [];
  if (old.length) {
    try { localStorage.setItem(PREV_KEY, JSON.stringify({ song: songKey(), lyrics: old })); } catch (_) {}
  }
  const lines = copy(newLyrics || []);
  const kept = old.length ? keepHandTimings(old, lines) : 0;
  state.lyrics = lines;
  updateUndoButton();
  return kept;
}

/** Wires "↶ Undo last sync". renderLyrics(lines) redraws; save() persists; onRestore(old) e.g. remaps translations. */
export function initSyncKeep({ renderLyrics, save, onRestore = async () => {} }) {
  updateUndoButton();
  byId('btn-undo-sync')?.addEventListener('click', async () => {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(PREV_KEY) || 'null'); } catch (_) {}
    if (!saved || saved.song !== songKey() || !Array.isArray(saved.lyrics)) { updateUndoButton(); return; }
    const current = state.lyrics || [];
    // Swap, so pressing it again redoes the sync.
    try { localStorage.setItem(PREV_KEY, JSON.stringify({ song: songKey(), lyrics: current })); } catch (_) {}
    state.lyrics = saved.lyrics;
    try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch (_) {}
    await onRestore(current);
    renderLyrics(state.lyrics);
    await save();
    updateUndoButton();
    showToast('Previous Sync Restored', 'The lyrics are back as they were before the last sync. Press it again to redo.', 'info', 4000);
  });
}

export { updateUndoButton };
