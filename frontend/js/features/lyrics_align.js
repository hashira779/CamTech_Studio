// Paste original lyrics -> align every word to the singer -> review the lines marked "Check".
// Both entry points (the AI prompt's "Align lyrics" and the lyrics panel's "Paste & Align")
// open the same dialog, so there is one flow to learn and one code path to keep working.

import { state } from '../core/state.js';
import { showToast } from '../ui/feedback.js';

const ALIGN_TIMEOUT_MS = 5 * 60 * 1000;
const PROGRESS_POLL_MS = 2000;

const byId = (id) => document.getElementById(id);

function countLines(text) {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).length;
}

function currentAudioPath() {
  return state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
}

/**
 * Sends the pasted lyrics to the backend and resolves with its answer. While it runs,
 * onStage(stage, percent) receives the backend's real step (vocal isolation, word matching...).
 */
async function alignToSinger(referenceText, onStage) {
  const controller = new AbortController();
  const abortTimer = setTimeout(() => controller.abort(), ALIGN_TIMEOUT_MS);
  const poller = setInterval(async () => {
    try {
      const p = await (await fetch('/api/transcribe/progress')).json();
      if (p && p.status === 'in_progress' && p.stage) onStage(p.stage.replace(/\.+$/, ''), p.percent || 0);
    } catch (_) { /* the next poll will try again */ }
  }, PROGRESS_POLL_MS);

  try {
    const res = await fetch('/api/lyrics/correct-with-reference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        lyrics_data: state.lyrics || [],
        reference_text: referenceText,
        audio_path: currentAudioPath(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Lyrics alignment failed');
    return data;
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('No answer after 5 minutes. Another AI job (transcribe / vocal isolation) may be running; check the backend console and try again.');
    }
    throw err;
  } finally {
    clearInterval(poller);
    clearTimeout(abortTimer);
  }
}

/** The toast that tells the user what happened and which lines to check. */
function summarize(data, secs) {
  const wordAligned = data.source === 'ctc_word_alignment';
  const unsure = Array.isArray(data.unsure_lines) ? data.unsure_lines : [];
  if (!wordAligned) {
    return {
      title: 'Estimated Vocal Timing',
      detail: 'Timing estimated from when the voice starts and stops. Play it back to check.',
      type: 'warning',
    };
  }
  const title = `${data.lines_count} Lines Aligned in ${secs}s`;
  if (!unsure.length) {
    return { title, detail: 'Every word matched to the singer with good confidence.', type: 'success' };
  }
  const plural = unsure.length > 1;
  return {
    title,
    detail: `Every word matched to the singer. ${unsure.length} line${plural ? 's are' : ' is'} marked "Check" (line${plural ? 's' : ''} ${unsure.map((i) => i + 1).join(', ')}).`,
    type: 'warning',
  };
}

/**
 * Wires the align dialog. `setGlobalProgress(percent, visible, label)` drives the header bar and
 * `renderLyrics(lines)` redraws the teleprompter; both live in the studio shell.
 */
export function initLyricsAlign({ setGlobalProgress, renderLyrics }) {
  const modal = byId('align-lyrics-modal');
  const input = byId('input-align-reference');
  const lineCount = byId('align-modal-line-count');
  const submitBtn = byId('btn-submit-align-lyrics');
  const promptInput = byId('input-ai-prompt');
  if (!modal || !input || !submitBtn) return;

  const updateLineCount = () => {
    if (lineCount) lineCount.textContent = `${countLines(input.value)} Lines`;
  };

  const open = () => {
    if (!state.audioPath && !state.audioUrl && !(state.lyrics && state.lyrics.length)) {
      showToast('No Audio Loaded', 'Load the song first, then paste its lyrics to align them.', 'info', 3500);
      return;
    }
    // Lyrics typed into the AI prompt carry over, so either entry point starts from the same text.
    const fromPrompt = promptInput?.value?.trim();
    if (fromPrompt && !input.value.trim()) input.value = fromPrompt;
    modal.style.display = 'flex';
    updateLineCount();
    setTimeout(() => input.focus(), 100);
  };

  const close = () => { modal.style.display = 'none'; };

  const submit = async () => {
    if (submitBtn.disabled) return; // a second request would only queue behind the first
    const text = input.value.trim();
    if (!text) {
      showToast('Empty Lyrics', 'Paste the original lyrics into the box first.', 'warning', 3000);
      return;
    }

    const idleLabel = submitBtn.innerHTML;
    const started = Date.now();
    const elapsed = () => Math.round((Date.now() - started) / 1000);
    let stage = `Aligning ${countLines(text)} lyrics to the singer`;
    let percent = 10;
    const showProgress = () => {
      submitBtn.textContent = `Aligning... ${elapsed()}s`;
      setGlobalProgress(Math.min(95, percent), true, `${stage}... ${elapsed()}s`);
    };
    const ticker = setInterval(showProgress, 1000);
    submitBtn.disabled = true;
    submitBtn.classList.add('btn-loading');
    showProgress();

    try {
      const data = await alignToSinger(text, (s, p) => { stage = s; percent = Math.max(percent, p); });
      if (data.status !== 'success' || !data.lyrics?.length) {
        showToast('Alignment Notice', data.detail || 'Could not complete lyrics alignment', 'info', 3500);
        return;
      }
      state.lyrics = data.lyrics;
      try { localStorage.setItem('vida_lyrics', JSON.stringify(state.lyrics)); } catch (_) {}
      renderLyrics(state.lyrics);
      const { title, detail, type } = summarize(data, elapsed());
      showToast(title, detail, type, 6000);
      setGlobalProgress(100, true, 'Lyrics alignment complete');
      close();
    } catch (err) {
      console.error('Lyrics alignment error:', err);
      showToast('Alignment Error', err.message, 'error', 6000);
    } finally {
      clearInterval(ticker);
      submitBtn.disabled = false;
      submitBtn.classList.remove('btn-loading');
      submitBtn.innerHTML = idleLabel;
      setTimeout(() => setGlobalProgress(100, false, ''), 1000);
    }
  };

  input.addEventListener('input', updateLineCount);
  byId('btn-paste-align-lyrics')?.addEventListener('click', open);
  byId('btn-ai-align-lyrics')?.addEventListener('click', open);
  byId('btn-close-align-modal')?.addEventListener('click', close);
  byId('btn-cancel-align-modal')?.addEventListener('click', close);
  submitBtn.addEventListener('click', submit);
}
