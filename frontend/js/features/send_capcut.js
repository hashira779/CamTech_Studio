// "Send to CapCut" in the Export dialog: a new CapCut project made from one of the user's own CapCut
// projects (their design), with this song's audio, title, singer and lyric lines as captions.
// The backend (backend/capcut_export.py) copies the design and never changes existing projects.

import { state } from '../core/state.js';
import { showToast } from '../ui/feedback.js';
import { getOriginalCues, getSecondTrackCues } from '../core/srt_editor.js';
import { ensureTranslation, hasValidTranslation, sourceIsKhmer } from '../core/translation.js';

const byId = (id) => document.getElementById(id);
const song = () => state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';
const asLines = (cues) => cues.map((c) => ({ start: Number(c.start), end: Number(c.end), text: String(c.text || '') }))
  .filter((l) => l.text.trim() && l.end > l.start);

function setStatus(text, bad = false) {
  const el = byId('capcut-status');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('ui-hint--bad', bad);
}

/**
 * Title and singer of the song now loaded. With no artist known, a name like "Title - Singer"
 * (how most songs are saved) is split, so neither the singer nor a dash ends up in the title.
 */
export function titleAndSinger(songTitle, artistName) {
  let title = String(songTitle || '').trim();
  let singer = String(artistName || '').trim();
  if (!singer || /^unknown$/i.test(singer)) {
    singer = '';
    const cut = title.indexOf(' - ');
    if (cut > 0) {
      singer = title.slice(cut + 3).trim();
      title = title.slice(0, cut).trim();
    }
  }
  return { title, singer };
}

function fillFields() {
  const title = byId('capcut-title');
  const singer = byId('capcut-singer');
  if (!title || !singer) return;
  // Refill for each song; keep what the user typed while the same song is loaded.
  if (title.dataset.song === song()) return;
  const guess = titleAndSinger(state.songTitle, state.artistName);
  title.value = guess.title;
  singer.value = guess.singer;
  title.dataset.song = song();
}

function singerNote() {
  return byId('capcut-singer')?.value.trim() ? '' : "Singer is empty: the design's singer line will be removed.";
}

async function refresh() {
  fillFields();
  const select = byId('capcut-template');
  const btn = byId('btn-send-capcut');
  try {
    const data = await (await fetch('/api/capcut/templates')).json();
    if (!data.found) {
      setStatus('CapCut for Windows was not found on this computer.', true);
      if (btn) btn.disabled = true;
      return;
    }
    const keep = select.value;
    select.innerHTML = '';
    for (const t of data.templates) select.add(new Option(t.name, t.name));
    if (keep && data.templates.some((t) => t.name === keep)) select.value = keep;
    if (!data.templates.length) {
      setStatus('Make one CapCut project with your design, a song and its captions first; VIDA copies it for every song.', true);
      if (btn) btn.disabled = true;
      return;
    }
    if (btn) btn.disabled = false;
    setStatus(data.running
      ? 'CapCut is open: you can still send. The project appears in CapCut after you close it and open it again.'
      : singerNote());
  } catch (_) {
    setStatus('Could not reach VIDA to list your CapCut projects.', true);
  }
}

async function send() {
  const btn = byId('btn-send-capcut');
  const lines = asLines(getOriginalCues(state.lyrics || []));
  if (!lines.length) {
    showToast('No Lyrics', 'Load or align the lyrics first.', 'warning', 3000);
    return;
  }
  btn.disabled = true;
  try {
    // Khmer lyrics get their English line automatically: the saved English track, or a new
    // translation (Gemini, checked for meaning) when the song has none yet.
    if (sourceIsKhmer() && !(state.translation.lang === 'en' && hasValidTranslation())) {
      setStatus('Translating the lyrics to English…');
      if (!(await ensureTranslation('en'))) {
        setStatus('English translation failed, so it was not sent. Try again, or send without it from the Lyrics tab.', true);
        return;
      }
    }
    const second = asLines(getSecondTrackCues(state.lyrics || []));
    setStatus('Making the CapCut project…');
    const res = await fetch('/api/capcut/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_path: song(),
        title: byId('capcut-title')?.value || '',
        singer: byId('capcut-singer')?.value || '',
        template: byId('capcut-template')?.value || null,
        lines,
        second_lines: second,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'CapCut project could not be made');
    const missed = [!data.title_found && 'title', !data.singer_found && 'singer'].filter(Boolean);
    let note = missed.length ? ` The design's ${missed.join(' and ')} text was not found, so it is unchanged.` : '';
    if ((data.removed || []).includes('singer')) note += ' The singer line was removed (no singer given).';
    const where = data.listed === false
      ? 'Close CapCut and open it again: it will be first in your projects (keep VIDA running until you close CapCut).'
      : 'Open CapCut: it is first in your projects.';
    setStatus(`Made "${data.name}". ${where}${note}`);
    showToast('Sent to CapCut', `"${data.name}" — ${lines.length} lines${second.length ? ' + translation' : ''}, ${data.length_s}s. ${where}${note}`, 'success', 8000);
  } catch (err) {
    setStatus(err.message, true);
    showToast('CapCut', err.message, 'warning', 6000);
  } finally {
    btn.disabled = false;
  }
}

export function initSendCapCut() {
  byId('btn-send-capcut')?.addEventListener('click', send);
  byId('capcut-singer')?.addEventListener('input', () => setStatus(singerNote()));
  // Fresh list and CapCut state each time the Export dialog opens.
  byId('btn-open-export')?.addEventListener('click', refresh);
  byId('menu-act-render-video')?.addEventListener('click', refresh);
}
