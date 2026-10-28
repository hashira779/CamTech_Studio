// The lyric lines live in two places: the song's .srt/.lrc beside the audio (what export and the
// backend read) and a copy in this browser for a fast start. Every edit goes through saveLyrics,
// so the two never disagree, and on start the newer copy wins (pickNewer), never the longer one:
// counting lines brought deleted lines back.

import { state } from './state.js';

const KEY = 'vida_lyrics';
const META = 'vida_lyrics_meta';

export const songKey = () => state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '';

/** Keeps this browser's copy of `lines`, with the song it belongs to and when it changed. */
export function cacheLyrics(lines = state.lyrics) {
  try {
    localStorage.setItem(KEY, JSON.stringify(lines || []));
    localStorage.setItem(META, JSON.stringify({ song: songKey(), at: Date.now() }));
  } catch (_) { /* private window or full storage: the file beside the audio still has them */ }
}

/** Saves the current lines to this browser and to the song's subtitle files. */
export async function saveLyrics() {
  cacheLyrics(state.lyrics);
  const song = songKey();
  if (!song || !state.lyrics?.length) return;
  try {
    await fetch('/api/subtitles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lyrics_data: state.lyrics, audio_path: song }),
    });
  } catch (_) { /* backend unreachable: the browser copy is newer and is saved on the next start */ }
}

/**
 * On start: 'local' when this browser's copy is of `song` and was changed after the saved file
 * (modified, seconds since 1970), otherwise 'file'. A copy from before this rule has no date,
 * so the file wins.
 */
export function pickNewer(song, fileModified) {
  let meta = null;
  try { meta = JSON.parse(localStorage.getItem(META) || 'null'); } catch (_) {}
  if (!meta || meta.song !== song || !Number.isFinite(fileModified)) return 'file';
  return meta.at > fileModified * 1000 ? 'local' : 'file';
}
