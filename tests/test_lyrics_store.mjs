/**
 * The lyric lines kept in this browser and in the song's file never disagree for long
 * (frontend/js/core/lyrics_store.js):
 *   - saving writes the browser copy with the song and the time it changed
 *   - on start the newer copy wins, never the longer one, so a deleted line stays deleted
 *   - a browser copy of another song, or from before this rule (no date), loses to the file
 * Usage: node tests/test_lyrics_store.mjs
 */

let failures = 0;
let checks = 0;
function assert(cond, msg) {
  checks++;
  if (!cond) { failures++; console.error(`  ❌ ${msg}`); }
  else console.log(`  ✅ ${msg}`);
}

const store = new Map();
globalThis.localStorage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) };
globalThis.window = {};
const posted = [];
globalThis.fetch = async (url, opts) => { posted.push({ url, body: JSON.parse(opts.body) }); return { ok: true, json: async () => ({}) }; };

const { state } = await import('../frontend/js/core/state.js');
const { saveLyrics, pickNewer } = await import('../frontend/js/core/lyrics_store.js');

const SONG = 'uploads/audio/song.mp3';
state.audioServerPath = SONG;
const nowS = () => Date.now() / 1000;

console.log('=== saving ===');
state.lyrics = [{ text: 'one', start: 1, end: 2 }, { text: 'three', start: 5, end: 6 }]; // "two" was deleted
await saveLyrics();
assert(posted.length === 1 && posted[0].url === '/api/subtitles/save' && posted[0].body.lyrics_data.length === 2 && posted[0].body.audio_path === SONG,
  'the lines go to the song\'s subtitle files');
assert(JSON.parse(store.get('vida_lyrics')).length === 2, 'and to this browser\'s copy, without the deleted line');

console.log('\n=== on start ===');
assert(pickNewer(SONG, nowS() - 60) === 'local', 'the browser copy wins when it changed after the file (the save did not reach it)');
assert(pickNewer(SONG, nowS() + 60) === 'file', 'the file wins when it was saved later');
assert(pickNewer('uploads/audio/other.mp3', nowS() - 60) === 'file', 'a browser copy of another song never wins');
store.delete('vida_lyrics_meta');
assert(pickNewer(SONG, nowS() - 60) === 'file', 'a browser copy from before this rule (no date) loses to the file');

console.log(`\n${failures ? '❌' : '✅'} ${failures ? `${failures} FAILED` : 'ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
