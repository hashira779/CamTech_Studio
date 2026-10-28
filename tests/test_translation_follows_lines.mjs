/**
 * The translated track must follow each lyric line, never its position in the list.
 *
 * Reproduces the studio bug: after re-aligning សុភាពបុរសចេះដាល់ with "ទៅណាមកណា ទៅណាមកណា" split into
 * two lines, every later translation slid one line down ("No one would ever dare mess with me"
 * showed under ទៅណាមកណា instead of under អ្នកណាក៏មិនហ៊ាននឹងបងដែរ).
 *
 * Usage: node tests/test_translation_follows_lines.mjs
 */

let failures = 0;
let checks = 0;
function assert(cond, msg) {
  checks++;
  if (!cond) { failures++; console.error(`  ❌ ${msg}`); }
  else console.log(`  ✅ ${msg}`);
}

// ---------- environment stubs (installed BEFORE the module is imported) ----------
const store = new Map();
globalThis.localStorage = {
  getItem: k => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: k => store.delete(k)
};
globalThis.document = {
  getElementById: () => null,
  createElement: () => ({ style: {}, classList: { add() {}, remove() {}, toggle() {} }, appendChild() {} }),
  body: { appendChild() {}, removeChild() {} },
  querySelector: () => null
};
let saved = null;
let savedCues = [];
globalThis.fetch = async (url, opts) => {
  const body = opts && opts.body ? JSON.parse(opts.body) : null;
  if (String(url).includes('/translation/save')) saved = body;
  let out = {};
  if (String(url).includes('/translation/list')) out = { langs: ['en'] };
  else if (String(url).includes('/api/lyrics/translation?')) out = { cues: savedCues };
  return { ok: true, status: 200, json: async () => out };
};

const { state } = await import('../frontend/js/core/state.js');
const T = await import('../frontend/js/core/translation.js');

const L = (text, start) => ({ text, start, end: start + 1.5, words: [] });
const OLD = [
  L('ព្រមទៅ យកបងធ្វើប្ដី', 24.62),
  L('អូនអើយកុំភ័យបងការពារ', 26.78),
  L('ទៅណាមកណា ទៅណាមកណា', 32.38),
  L('អ្នកណាក៏មិនហ៊ាននឹងបងដែរ', 35.14),
  L('អ្នកប្រដាល់ស្រុកខ្មែរគេខ្លាចតែបងទេ', 36.92),
];
const EN = [
  'Say yes and take me as your man,',
  "Oh my darling, fear not, I'll protect you.",
  'Wherever we go, wherever we roam,',
  'No one would ever dare mess with me,',
  'Fighters across Cambodia only fear me.',
];
const NEW = [OLD[0], OLD[1], L('ទៅណាមកណា', 32.38), L('ទៅណាមកណា', 33.8), OLD[3], OLD[4]];

function songWithTrack(lyrics, translations) {
  state.lyrics = lyrics.map((l, i) => ({ index: i, ...l }));
  state.audioServerPath = 'uploads/audio/sopheap.mp3';
  state.translation.lang = 'en';
  state.translation.lines = translations.map((text, i) => ({ index: i, text, source: lyrics[i].text,
    start: lyrics[i].start, end: lyrics[i].end }));
  state.translation.loaded = true;
}
const shown = () => state.translation.lines.map(l => l.text);

console.log('=== a line split in two ===');
songWithTrack(OLD, EN);
state.lyrics = NEW.map((l, i) => ({ index: i, ...l }));
let missing = await T.remapTranslationToLyrics(OLD);
assert(shown()[4] === EN[3], 'អ្នកណាក៏មិនហ៊ាននឹងបងដែរ keeps "No one would ever dare mess with me"');
assert(shown()[5] === EN[4], 'the line after it keeps its own translation too');
assert(shown()[2] === EN[2] && shown()[3] === '', 'the first half of the split line keeps the translation, the second is left empty');
assert(missing === 1, 'one new line is reported as untranslated');
assert(saved && saved.lines.length === NEW.length && saved.lines[4] === EN[3], 'the remapped track is saved in the new line order');

console.log('\n=== the in-memory order was already off (built before this fix) ===');
songWithTrack(OLD, EN);
// what the studio had: 5 translations index-matched to 5 old lines, now displayed against 6 lines
state.lyrics = NEW.map((l, i) => ({ index: i, ...l }));
missing = await T.remapTranslationToLyrics(NEW);  // the caller only knows the lines on screen
assert(shown()[4] === EN[3], 'each translation still finds its line by the source it remembers');

console.log('\n=== a line removed and lines merged ===');
songWithTrack(OLD, EN);
state.lyrics = [OLD[0], OLD[1], OLD[3], OLD[4]].map((l, i) => ({ index: i, ...l }));
await T.remapTranslationToLyrics(OLD);
assert(JSON.stringify(shown()) === JSON.stringify([EN[0], EN[1], EN[3], EN[4]]), 'removing a line shifts nothing');
songWithTrack(OLD, EN);
state.lyrics = [OLD[0], OLD[1], L('ទៅណាមកណា ទៅណាមកណា អ្នកណាក៏មិនហ៊ាននឹងបងដែរ', 32.38), OLD[4]].map((l, i) => ({ index: i, ...l }));
await T.remapTranslationToLyrics(OLD);
assert(shown()[2] === `${EN[2]} ${EN[3]}`, 'two lines merged into one get both translations');

console.log('\n=== loading a saved track after the lines were re-timed ===');
state.lyrics = NEW.map((l, i) => ({ index: i, ...l }));
state.translation.lines = []; state.translation.loaded = false;
savedCues = OLD.map((l, i) => ({ start: l.start + 0.01, end: l.end, text: EN[i] }));  // saved for the old lines
await T.loadTranslationForSong();
assert(shown()[4] === EN[3] && shown()[5] === EN[4], 'saved cues land on the lines starting nearest them');
assert(shown()[3] === '', 'the new line gets nothing rather than its neighbour\'s translation');

console.log(`\n${failures ? '❌' : '✅'} ${failures ? `${failures} FAILED` : 'ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
