// Tap to sync: for songs the word aligner cannot hear (a duet, an old recording), the user plays
// the song and presses Enter the moment each line starts. Exact, and works for any song.
//
// Enter (or the Tap button) sets the current line's start and ends the line before it there.
// Backspace undoes the last tap, Esc finishes. Only tapped lines change; their words keep their
// relative places inside the line. A tapped line counts as confirmed, so it is no longer "unsure".

import { state } from '../core/state.js';
import { cacheLyrics } from '../core/lyrics_store.js';
import { showToast } from '../ui/feedback.js';
import { escapeHtml } from '../core/translation.js';

// People press a key a little after they hear the line start.
const REACTION_S = 0.15;
const LEAD_IN_S = 3;
const MIN_LINE_S = 0.3;

const byId = (id) => document.getElementById(id);
const player = () => byId('audio-player');
const round = (t) => Math.round(t * 100) / 100;

/** Moves a line to [start, end], keeping each word's relative place inside it. */
export function refit(line, start, end) {
  const s0 = Number(line.start) || 0;
  const e0 = Number(line.end) || s0 + 1;
  const scale = (end - start) / Math.max(0.01, e0 - s0);
  (line.words || []).forEach((w) => {
    w.start = round(start + (Number(w.start) - s0) * scale);
    w.end = round(start + (Number(w.end) - s0) * scale);
  });
  line.start = round(start);
  line.end = round(end);
}

/**
 * Wires tap-to-sync. renderLyrics(lines) redraws the lyric list; save() persists the timings.
 */
export function initTapSync({ renderLyrics, save }) {
  const bar = byId('tap-sync-bar');
  if (!bar) return;
  let target = -1;   // index of the line the next tap times
  let tapped = 0;
  let undo = [];     // snapshots: { target, lines: [[index, copy], ...] }

  const lines = () => state.lyrics || [];

  const firstTarget = () => {
    const unsure = lines().findIndex((l) => Number.isFinite(l.confidence) && l.confidence < 0.2);
    if (unsure >= 0) return unsure;
    const now = player()?.currentTime || 0;
    const at = lines().findIndex((l) => Number(l.end) > now);
    return at >= 0 ? at : 0;
  };

  const markTarget = () => {
    document.querySelectorAll('#lyrics-teleprompter .tp-tap-target').forEach((el) => el.classList.remove('tp-tap-target'));
    const row = document.querySelector(`#lyrics-teleprompter .teleprompter-line[data-index="${target}"]`);
    if (row) {
      row.classList.add('tp-tap-target');
      row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  };

  const show = () => {
    const line = lines()[target];
    bar.hidden = false;
    byId('tap-sync-line').innerHTML = line
      ? `<span class="tap-num">Line ${target + 1} of ${lines().length}</span> <span class="tap-text">${escapeHtml(line.text)}</span>`
      : '<span class="tap-text">All lines tapped</span>';
    byId('tap-sync-count').textContent = tapped ? `${tapped} tapped` : '';
    byId('btn-tap-undo').disabled = undo.length === 0;
    markTarget();
  };

  const redraw = () => { renderLyrics(lines()); markTarget(); };

  const start = () => {
    if (!lines().length) { showToast('No Lyrics', 'Load or align the lyrics first.', 'info', 3000); return; }
    const p = player();
    if (!p || !p.src) { showToast('No Audio', 'Load the song first.', 'info', 3000); return; }
    target = firstTarget();
    tapped = 0;
    undo = [];
    const from = Math.max(0, (Number(lines()[target].start) || 0) - LEAD_IN_S);
    p.currentTime = from;
    p.play().catch(() => {});
    show();
  };

  const tap = () => {
    const all = lines();
    const line = all[target];
    const p = player();
    if (!line || !p) return;
    const t = Math.max(0, p.currentTime - REACTION_S);
    const prev = all[target - 1];
    if (prev && t < Number(prev.start) + MIN_LINE_S) return; // a tap before the previous line could even start
    undo.push({ target, lines: [target - 1, target].filter((i) => i >= 0).map((i) => [i, JSON.parse(JSON.stringify(all[i]))]) });

    if (prev && Number(prev.end) > t - 0.05) refit(prev, Number(prev.start), t - 0.05);
    const next = all[target + 1];
    const oldLen = Math.max(0.6, Number(line.end) - Number(line.start));
    let end = Number(line.end);
    if (end < t + MIN_LINE_S) end = t + oldLen;
    if (next && end > Number(next.start) - 0.05 && Number(next.start) > t + MIN_LINE_S) end = Number(next.start) - 0.05;
    refit(line, t, end);
    line.confidence = 1;
    line.timing_source = 'tapped';
    tapped += 1;
    target += 1;
    redraw();
    show();
  };

  const undoTap = () => {
    const last = undo.pop();
    if (!last) return;
    last.lines.forEach(([i, copy]) => { lines()[i] = copy; });
    target = last.target;
    tapped = Math.max(0, tapped - 1);
    const p = player();
    if (p) p.currentTime = Math.max(0, (Number(lines()[target].start) || 0) - LEAD_IN_S);
    redraw();
    show();
  };

  const finish = async () => {
    bar.hidden = true;
    document.querySelectorAll('#lyrics-teleprompter .tp-tap-target').forEach((el) => el.classList.remove('tp-tap-target'));
    const count = tapped;
    target = -1;
    undo = [];
    if (!count) return;
    cacheLyrics(lines());
    await save();
    showToast('Tap Sync Saved', `${count} line${count > 1 ? 's' : ''} timed by your taps.`, 'success', 4000);
  };

  // While tapping, Enter / Backspace / Esc belong to tap sync (not to lyric editing).
  window.addEventListener('keydown', (e) => {
    if (target < 0) return;
    const handlers = { Enter: tap, Backspace: undoTap, Escape: finish };
    const fn = handlers[e.key];
    if (!fn) return;
    e.preventDefault();
    e.stopPropagation();
    fn();
  }, true);

  byId('btn-tap-sync')?.addEventListener('click', start);
  byId('btn-tap-tap')?.addEventListener('click', tap);
  byId('btn-tap-undo')?.addEventListener('click', undoTap);
  byId('btn-tap-done')?.addEventListener('click', finish);
}
