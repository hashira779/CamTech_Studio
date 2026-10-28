// Set a line's time by hand. Click the time of any line in the lyric list to edit it:
// type a time ("0:55.6" or "55.6"), nudge it by a tenth of a second, or take the playback
// position ("⏱ Now"), then Enter / ✓. The line before ends where this one now starts and the
// words move with the line. A line timed by hand counts as confirmed, so it is no longer "unsure".

import { state } from '../core/state.js';
import { showToast } from '../ui/feedback.js';
import { refit } from './tap_sync.js';

const MIN_LINE_S = 0.3;
const byId = (id) => document.getElementById(id);

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

/**
 * Moves line `index` to start at `t`. It must stay after the previous line's start and before
 * the next line's start, so the lines keep their order; a time outside that is pulled inside.
 * Returns the start that was applied, or null when there is no room at all.
 */
export function setLineStart(index, t) {
  const all = state.lyrics || [];
  const line = all[index];
  if (!line) return null;
  const prev = all[index - 1];
  const next = all[index + 1];
  const lo = prev ? Number(prev.start) + MIN_LINE_S : 0;
  const hi = next ? Number(next.start) - MIN_LINE_S : Number.POSITIVE_INFINITY;
  if (hi < lo) return null;
  const start = Math.round(Math.min(hi, Math.max(lo, t)) * 100) / 100;

  if (prev && Number(prev.end) > start - 0.05) refit(prev, Number(prev.start), start - 0.05);
  const oldLen = Math.max(0.6, Number(line.end) - Number(line.start));
  let end = Number(line.end);
  if (end < start + MIN_LINE_S) end = start + oldLen;
  if (next && end > Number(next.start) - 0.05) end = Number(next.start) - 0.05;
  refit(line, start, end);
  line.confidence = 1;
  line.timing_source = 'manual';
  return start;
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
    const applied = setLineStart(index, t);
    open = null;
    renderLyrics(state.lyrics || []);
    if (applied === null) {
      showToast('No Room', 'This line has no room between its neighbours.', 'warning', 3000);
      return;
    }
    if (Math.abs(applied - t) > 0.005) {
      showToast('Time Adjusted', `Kept the lines in order: set to ${formatClock(applied)} instead.`, 'info', 3500);
    }
    try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch (_) {}
    await save();
    // Let the user hear the result right away.
    const p = player();
    if (p && p.src) {
      p.currentTime = Math.max(0, applied - 1);
      p.play().catch(() => {});
    }
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
