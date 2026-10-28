/**
 * Re-syncing keeps what the user timed by hand, and can be undone
 * (frontend/js/features/sync_keep.js):
 *   - a line timed by hand (Tap sync / typed time) keeps its timing after a re-sync
 *   - its aligned neighbours give way to it, so nothing overlaps
 *   - this holds when lines were split between syncs (matched by text, not position)
 *   - the lyrics from before the sync are kept for "Undo last sync"
 * Usage: node tests/test_sync_keep.mjs
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
globalThis.document = {
  getElementById: () => null,
  createElement: () => ({ style: {}, classList: { add() {}, remove() {}, toggle() {} }, appendChild() {} }),
  body: { appendChild() {}, removeChild() {} },
  querySelector: () => null, querySelectorAll: () => [],
};
globalThis.window = { addEventListener() {} };

const { state } = await import('../frontend/js/core/state.js');
const { applySyncResult } = await import('../frontend/js/features/sync_keep.js');

const W = (word, start, end) => ({ word, start, end });
const L = (text, start, end, extra = {}) => ({ text, start, end, words: [W(text, start, end)], ...extra });
state.audioServerPath = 'uploads/audio/song.mp3';

console.log('=== a hand-timed line survives a re-sync ===');
state.lyrics = [L('one', 50, 55), L('two', 60.5, 63, { timing_source: 'manual', confidence: 1 }), L('three', 63.2, 66)];
const aligner = [L('one', 50.2, 59.5), L('two', 59.6, 62.1, { confidence: 0.1 }), L('three', 62.2, 66)];
let kept = applySyncResult(aligner);
const [one, two, three] = state.lyrics;
assert(kept === 1, 'one line kept its own timing');
assert(two.start === 60.5 && two.end === 63 && two.timing_source === 'manual' && two.confidence === 1, 'the hand-set time and confirmed status are kept');
assert(one.end <= 60.45, 'the aligned line before ends before it');
assert(three.start >= 63.05, 'the aligned line after starts after it');
assert(aligner[1].start === 59.6, 'the aligner result passed in is not modified');

console.log('\n=== lines split between syncs ===');
state.lyrics = [L('intro', 10, 14), L('ទៅណាមកណា ទៅណាមកណា', 30.2, 33.9, { timing_source: 'tapped', confidence: 1 }), L('outro', 35, 38)];
kept = applySyncResult([L('intro', 10, 14), L('extra line', 20, 25), L('ទៅណាមកណា ទៅណាមកណា', 32.4, 35.1, { confidence: 0.45 }), L('outro', 35.2, 38)]);
assert(kept === 1 && state.lyrics[2].start === 30.2, 'the tapped line is found by its text after a line was added before it');
assert(state.lyrics[3].start >= 33.95, 'the line after it moves out of its way');

console.log('\n=== aligner-timed lines are replaced as usual ===');
state.lyrics = [L('one', 50, 55, { confidence: 0.3 }), L('two', 56, 60, { confidence: 0.1 })];
kept = applySyncResult([L('one', 51, 55), L('two', 57, 60)]);
assert(kept === 0 && state.lyrics[0].start === 51 && state.lyrics[1].start === 57, 'only hand-set timings are protected');

console.log('\n=== undo keeps the lyrics from before the sync ===');
const saved = JSON.parse(store.get('vida_lyrics_before_sync'));
assert(saved.song === 'uploads/audio/song.mp3' && saved.lyrics[0].start === 50 && saved.lyrics[1].start === 56,
  'the lyrics as they were before the last sync are kept for this song');

console.log(`\n${failures ? '❌' : '✅'} ${failures ? `${failures} FAILED` : 'ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
