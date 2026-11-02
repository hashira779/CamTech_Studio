// One place to review what the aligner was unsure about, instead of a loud tag on each line.
// The bar above the lyric list
//   - counts the lines it barely heard and steps through them ("Play next"), and
//   - points at stretches where someone sings words the lyrics do not contain (a duet partner's
//     answer, an echo), which make the aligner stretch a line over them.

import { escapeHtml } from '../core/translation.js';

const byId = (id) => document.getElementById(id);

// Set when the last alignment could not use the word aligner and fell back to a rough estimate.
let roughTiming = { on: false, lineCount: -1, note: '' };

/** Remembers how the last alignment was timed; a rough estimate is announced in the bar, with why. */
export function setTimingSource(source, lineCount, note = '') {
  roughTiming = { on: Boolean(source) && source !== 'ctc_word_alignment' && source !== 'gemini_multimodal_alignment', lineCount, note: note || '' };
  updateLyricsReview();
}

// Spots reported by the last alignment, valid while the lyrics keep the same number of lines.
let unlisted = { spots: [], lineCount: -1 };

function unsureRows() {
  return [...document.querySelectorAll('#lyrics-teleprompter .teleprompter-line.tp-unsure')];
}

const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

function seek(t) {
  const player = byId('audio-player');
  if (!player) return;
  player.currentTime = Math.max(0, t - 1);
  player.play().catch(() => {});
}

/** Remembers where the last alignment heard singing that is not in the lyrics. */
export function setUnlistedSinging(spots, lineCount) {
  unlisted = { spots: Array.isArray(spots) ? spots : [], lineCount };
  updateLyricsReview();
}

/** Refreshes the bar after the lyric list is redrawn. */
export function updateLyricsReview() {
  const bar = byId('lyrics-review-bar');
  const text = byId('lyrics-review-text');
  if (!bar || !text) return;
  const rows = unsureRows();
  const total = document.querySelectorAll('#lyrics-teleprompter .teleprompter-line').length;
  const spots = unlisted.lineCount === total ? unlisted.spots : [];
  const nextBtn = byId('btn-review-next');
  const rough = roughTiming.on && roughTiming.lineCount === total;
  bar.hidden = rows.length === 0 && spots.length === 0 && !rough;
  if (bar.hidden) return;

  const parts = [];
  if (rough) {
    const why = roughTiming.note ? ` <b>Why:</b> ${escapeHtml(roughTiming.note)}` : ' Align again.';
    parts.push(`<b>Rough timing only.</b> The word aligner could not run this time, so lines were spread over the singing without hearing the words.${why}`);
  }
  if (rows.length) {
    parts.push(`<b>${rows.length} of ${total} lines unsure</b>. The singer was hard to hear there, so their timing is a best guess. Check them with ▶ Play next, or time them yourself with ✋ Tap sync.`);
  }
  spots.forEach((s, k) => {
    parts.push(`<span class="tp-review-spot"><b>Singing not in your lyrics at ${clock(s.start)}–${clock(s.end)}</b>,
      inside line ${s.line + 1} (after <span class="am-quote">${escapeHtml(s.after_word)}</span>). Another singer's part or an echo?
      Add those words to the lyrics and align again.
      <button class="ui-btn ui-btn--sm" data-listen="${k}">▶ Listen</button></span>`);
  });
  text.innerHTML = parts.join('<br>');
  if (nextBtn) nextBtn.hidden = rows.length === 0;
}

export function initLyricsReview() {
  byId('btn-review-next')?.addEventListener('click', () => {
    const rows = unsureRows();
    if (!rows.length) return;
    const now = byId('audio-player')?.currentTime || 0;
    const next = rows.find((r) => parseFloat(r.dataset.start) > now + 0.25) || rows[0];
    next.scrollIntoView({ block: 'center', behavior: 'smooth' });
    next.click();
  });
  byId('lyrics-review-text')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-listen]');
    const spot = btn && unlisted.spots[+btn.dataset.listen];
    if (spot) seek(spot.start);
  });
}
