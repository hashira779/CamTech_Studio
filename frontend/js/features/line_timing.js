// Set a line's time by hand. Click the time of any line in the lyric list to edit it:
// type a time ("0:55.6" or "55.6"), nudge it by a tenth of a second, or take the playback
// position ("⏱ Now"), then Enter / ✓. The line before ends where this one now starts and the
// words move with the line. A line timed by hand counts as confirmed, so it is no longer "unsure".
// The unsure lines right after it move by the same amount at once: when the aligner lost the
// singer, it is usually off by the same time for the whole stretch. Confident and hand-set lines
// stay. Then the aligner listens again to just that stretch, from the user's time to the next
// line it was sure of, and re-times those lines word by word.

import { state } from '../core/state.js';
import { cacheLyrics } from '../core/lyrics_store.js';
import { showToast } from '../ui/feedback.js';
import { refit } from './tap_sync.js';

const MIN_LINE_S = 0.3;
const RELISTEN_TIMEOUT_MS = 5 * 60 * 1000;
// Off until measured against shifting (scratchpad eval_realign.py): only turn on if it is closer.
const RELISTEN = false;
const byId = (id) => document.getElementById(id);
const songKey = () => state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
const copy = (x) => JSON.parse(JSON.stringify(x));

export const formatClock = (t) => {
  const s = Math.max(0, Number(t) || 0);
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, '0')}`;
};

/** "1:05.4", "65.4" or "65" -> seconds; null when it is not a time. */
export function parseClock(text) {
  const m = String(text || '').trim().match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
  if (!m) return null;
  return (m[1] ? Number(m[1]) * 60 : 0) + Number(m[2]);
}

const UNSURE = 0.2;
const HAND_TIMED = new Set(['manual', 'tapped']);
const followsAlong = (l) => !HAND_TIMED.has(l.timing_source) && Number.isFinite(l.confidence) && l.confidence < UNSURE;

/**
 * Moves line `index` to start at `t`, and the unsure lines right after it by the same amount.
 * Everything that moves must stay between the previous line and the first line that stays, so
 * the lines keep their order; a time outside that is pulled inside.
 * Returns { start, moved } (the start applied, how many lines after it moved too), or null
 * when there is no room at all.
 */
export function setLineStart(index, t) {
  const all = state.lyrics || [];
  const line = all[index];
  if (!line) return null;
  const prev = all[index - 1];
  let stop = index + 1;
  while (stop < all.length && followsAlong(all[stop])) stop++;
  const run = all.slice(index + 1, stop);
  const next = all[stop]; // the first line that stays where it is
  const lastStart = Number((run.length ? run[run.length - 1] : line).start);
  const lo = prev ? Number(prev.start) + MIN_LINE_S : 0;
  const hi = next ? Number(line.start) + (Number(next.start) - MIN_LINE_S - lastStart) : Number.POSITIVE_INFINITY;
  if (hi < lo) return null;
  const start = Math.round(Math.min(hi, Math.max(lo, t)) * 100) / 100;
  const delta = start - Number(line.start);

  if (prev && Number(prev.end) > start - 0.05) refit(prev, Number(prev.start), start - 0.05);
  if (run.length) {
    refit(line, start, Number(line.end) + delta);
    if (delta) run.forEach((l) => refit(l, Number(l.start) + delta, Number(l.end) + delta));
    const last = run[run.length - 1];
    if (next && Number(last.end) > Number(next.start) - 0.05) refit(last, Number(last.start), Number(next.start) - 0.05);
  } else {
    const oldLen = Math.max(0.6, Number(line.end) - Number(line.start));
    let end = Number(line.end);
    if (end < start + MIN_LINE_S) end = start + oldLen;
    if (next && end > Number(next.start) - 0.05) end = Number(next.start) - 0.05;
    refit(line, start, end);
  }
  line.confidence = 1;
  line.timing_source = 'manual';
  return { start, moved: delta ? run.length : 0 };
}

/** The stretch as it is now, to tell whether it changed while the aligner was listening. */
const stretchKey = (index, count) => JSON.stringify((state.lyrics || []).slice(index, index + count)
  .map((l) => [l.text, l.start, l.end]));

/**
 * Has the aligner hear lines index..index+moved again, only between the user's time for line
 * `index` and the next line that stayed, and puts its timings on them. Line `index` keeps the
 * user's start. Returns how many of the re-timed lines are now sure, or null when nothing was
 * applied (aligner unavailable, or the lines were changed meanwhile).
 */
export async function relistenStretch(index, moved) {
  const all = state.lyrics || [];
  const count = moved + 1;
  const stretch = all.slice(index, index + count);
  if (stretch.length !== count) return null;
  const stop = all[index + count];
  const userStart = Number(stretch[0].start);
  const end = stop ? Number(stop.start) : Number(stretch[count - 1].end) + 3;
  const song = songKey();
  const before = stretchKey(index, count);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), RELISTEN_TIMEOUT_MS);
  let data;
  try {
    const res = await fetch('/api/subtitles/relisten', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ lines: stretch.map((l) => l.text), start: userStart - 0.3, end, audio_path: song }),
    });
    data = await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
  if (data?.status !== 'success' || data.lines?.length !== count) return null;
  if (songKey() !== song || stretchKey(index, count) !== before) return null;

  const lines = state.lyrics;
  data.lines.forEach((got, k) => {
    const line = lines[index + k];
    if (k === 0) {
      // The user's start stands; the aligner gives the end and where the words fall.
      const nextStart = data.lines[1] ? Number(data.lines[1].start) : end;
      const lineEnd = Math.max(userStart + MIN_LINE_S, Math.min(Number(got.end), nextStart - 0.05));
      Object.assign(line, { start: got.start, end: got.end, words: copy(got.words || []) });
      refit(line, userStart, lineEnd);
      return;
    }
    Object.assign(line, { start: got.start, end: got.end, words: copy(got.words || []), confidence: got.confidence });
  });
  return data.lines.slice(1).filter((l) => Number(l.confidence) >= UNSURE).length;
}

/** Wires the editor. renderLyrics(lines) redraws the list; save() persists the timings. */
export function initLineTiming({ renderLyrics, save }) {
  const list = byId('lyrics-teleprompter');
  if (!list) return;
  const player = () => byId('audio-player');
  let open = null; // { index, chip }

  const close = () => {
    if (!open) return;
    renderLyrics(state.lyrics || []);
    open = null;
  };

  const apply = async (index, value) => {
    const t = parseClock(value);
    if (t === null) {
      showToast('Not a Time', 'Type a time like 1:05.4 or 65.4', 'warning', 3000);
      return;
    }
    const result = setLineStart(index, t);
    open = null;
    renderLyrics(state.lyrics || []);
    if (result === null) {
      showToast('No Room', 'This line has no room between its neighbours.', 'warning', 3000);
      return;
    }
    const applied = result.start;
    if (Math.abs(applied - t) > 0.005) {
      showToast('Time Adjusted', `Kept the lines in order: set to ${formatClock(applied)} instead.`, 'info', 3500);
    }
    cacheLyrics(state.lyrics);
    await save();
    if (result.moved && RELISTEN) relistenAfter(index, result.moved);
    else if (result.moved) showToast('Lines After Moved Too', `The ${result.moved} unsure line${result.moved > 1 ? 's' : ''} after it moved by the same amount. Play them to check.`, 'info', 4000);
    // Let the user hear the result right away.
    const p = player();
    if (p && p.src) {
      p.currentTime = Math.max(0, applied - 1);
      p.play().catch(() => {});
    }
  };

  // The lines after moved with it already; now the aligner listens to that stretch again.
  const relistenAfter = async (index, moved) => {
    const plural = moved > 1;
    showToast('Listening Again', `The ${moved} unsure line${plural ? 's' : ''} after it moved with it. Now listening to ${plural ? 'them' : 'it'} again from your time...`, 'info', 4000);
    const sure = await relistenStretch(index, moved);
    if (sure === null) return; // the shifted timing stays
    renderLyrics(state.lyrics || []);
    cacheLyrics(state.lyrics);
    await save();
    showToast('Lines After Re-timed', sure
      ? `Listened again: ${sure} of ${moved} line${plural ? 's are' : ' is'} now heard clearly. Play the rest to check.`
      : `Listened again and re-timed ${moved} line${plural ? 's' : ''}; still hard to hear, so play ${plural ? 'them' : 'it'} to check.`, sure === moved ? 'success' : 'info', 5000);
  };

  const openEditor = (chip, index) => {
    if (open) close();
    const line = (state.lyrics || [])[index];
    if (!line) return;
    const row = list.querySelector(`.teleprompter-line[data-index="${index}"]`);
    const target = row ? row.querySelector('.tp-time') : chip;
    if (!target) return;
    open = { index };
    target.classList.add('tp-time--editing');
    target.innerHTML = `<input class="tp-time-input" value="${formatClock(line.start)}" aria-label="Line start time" spellcheck="false">
      <button class="tp-time-btn" data-act="minus" title="0.1 s earlier">−0.1</button>
      <button class="tp-time-btn" data-act="plus" title="0.1 s later">+0.1</button>
      <button class="tp-time-btn" data-act="now" title="Use the current playback position">⏱ Now</button>
      <button class="tp-time-btn tp-time-btn--ok" data-act="ok" title="Apply (Enter)">✓</button>`;
    const input = target.querySelector('input');
    input.focus();
    input.select();
    input.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') { e.preventDefault(); apply(index, input.value); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
  };

  // Capture phase: runs before the row's own click (which seeks and plays the line).
  list.addEventListener('click', (e) => {
    const editing = e.target.closest('.tp-time--editing');
    if (editing) {
      e.stopPropagation();
      const btn = e.target.closest('button[data-act]');
      if (!btn || !open) return;
      const input = editing.querySelector('input');
      const cur = parseClock(input.value);
      const act = btn.dataset.act;
      if (act === 'ok') { apply(open.index, input.value); return; }
      if (act === 'now') input.value = formatClock(player()?.currentTime || 0);
      if ((act === 'minus' || act === 'plus') && cur !== null) input.value = formatClock(cur + (act === 'plus' ? 0.1 : -0.1));
      input.focus();
      return;
    }
    const chip = e.target.closest('.tp-time');
    if (!chip) return;
    e.stopPropagation();
    const row = chip.closest('.teleprompter-line');
    openEditor(chip, Number(row?.dataset.index));
  }, true);
}
