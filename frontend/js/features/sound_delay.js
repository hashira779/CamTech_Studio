// "Sound delay" in the Lyrics ⋯ menu: the preview already allows for the delay the browser
// reports between the player's clock and your speakers; + and − add the user's own correction
// (25 ms a press) for devices that report less than they add, such as Bluetooth headphones.

import { reportedSoundDelay, getExtraSoundDelayMs, setExtraSoundDelayMs } from '../core/audio.js';

const STEP_MS = 25;
const byId = (id) => document.getElementById(id);

function show() {
  const el = byId('sound-delay-value');
  if (!el) return;
  const auto = Math.round(reportedSoundDelay() * 1000);
  const extra = getExtraSoundDelayMs();
  const total = Math.max(0, auto + extra);
  el.textContent = `${total} ms`;
  el.title = `Measured by the browser: ${auto} ms. Your correction: ${extra > 0 ? '+' : ''}${extra} ms.`;
}

export function initSoundDelay() {
  byId('btn-sound-delay-less')?.addEventListener('click', () => { setExtraSoundDelayMs(getExtraSoundDelayMs() - STEP_MS); show(); });
  byId('btn-sound-delay-more')?.addEventListener('click', () => { setExtraSoundDelayMs(getExtraSoundDelayMs() + STEP_MS); show(); });
  // The measured part is only known once sound has started; refresh whenever the menu opens.
  byId('lyrics-more')?.addEventListener('toggle', show);
  document.getElementById('audio-player')?.addEventListener('play', () => setTimeout(show, 500));
  show();
}
