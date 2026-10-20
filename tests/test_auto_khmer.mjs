/**
 * Auto-Khmer second track — headless test.
 *
 * Proves the behaviour the studio asked for: when the loaded song's lyrics are a foreign
 * language, Khmer becomes the default target and the translated track is built once,
 * automatically, as the SECOND line — without ever re-billing the translation API on
 * reload and without touching the original lyrics or the original SRT.
 *
 * Usage: node tests/test_auto_khmer.mjs
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

function makeSelect() {
  return {
    value: 'en', disabled: false, title: '', handlers: {},
    options: {},
    querySelector(sel) {
      this.options.km = this.options.km || { value: 'km', disabled: false, title: '' };
      return this.options.km;
    },
    addEventListener(type, fn) { this.handlers[type] = fn; },
    click(type = 'change') { return this.handlers[type] && this.handlers[type]({ target: this }); }
  };
}
function makeButton(text) {
  return { textContent: text, disabled: false, checked: false, value: '', handlers: {},
    addEventListener(type, fn) { this.handlers[type] = fn; },
    click(type = 'click') { return this.handlers[type] && this.handlers[type]({ target: this }); } };
}
const elements = {
  'select-translation-lang': makeSelect(),
  'chk-auto-khmer': makeButton('auto'),
  'btn-translate-all': makeButton('🌐 Translate')
};
elements['chk-auto-khmer'].checked = true;
globalThis.document = {
  getElementById: id => (elements[id] || null),
  createElement: () => ({ style: {}, classList: { add() {}, remove() {}, toggle() {} }, appendChild() {} }),
  body: { appendChild() {}, removeChild() {} },
  querySelector: () => null
};

let calls = [];
let handler = () => ({ langs: [] });
globalThis.fetch = async (url, opts) => {
  const body = opts && opts.body ? JSON.parse(opts.body) : null;
  calls.push({ url: String(url), method: (opts && opts.method) || 'GET', body });
  const out = handler(String(url), body) || {};
  if (out.__throw) throw new Error(out.__throw);
  return { ok: !out.__status || out.__status === 200, status: out.__status || 200, json: async () => out };
};
const translatePosts = () => calls.filter(c => c.url.includes('/translate-lines')).length;
const savePosts = () => calls.filter(c => c.url.includes('/translation/save'));

const { state } = await import('../frontend/js/core/state.js');
const T = await import('../frontend/js/core/translation.js');

const VI = [
  { text: 'Thiên đường với người thương', start: 1.0, end: 4.0 },
  { text: 'Câu yêu thương xin gửi về', start: 4.2, end: 7.0 },
  { text: 'Dù xa cách nhưng lòng vẫn nhớ', start: 7.2, end: 10.5 }
];
const KH = [
  { text: 'បេះដូងខ្ញុំបែកបាក់', start: 1.0, end: 4.0 },
  { text: 'ខ្ញុំស្រលាញ់អ្នកណាស់', start: 4.2, end: 7.0 },
  { text: 'សង្ឃឹមថានឹងបានជួបគ្នា', start: 7.2, end: 10.5 }
];

function loadSong(lines, key) {
  state.lyrics = lines.map((l, i) => ({ index: i, ...l, words: [] }));
  state.audioServerPath = key;
  state.audioPath = ''; state.audioUrl = '';
  state.translation.lines = [];
  state.translation.loaded = false;
  state.translation.lang = 'en';
  state.translation.displayMode = 'original_only';
  state.translation.autoTranslate = true;
  calls = [];
}

/** Same as loadSong, but puts lines back — a real song switch with a track still in memory. */
function switchSong(lines, key, keepLines) {
  loadSong(lines, key);
  if (keepLines) {
    state.translation.lines = keepLines;
    state.translation.loaded = true;
  }
  calls = [];
}
const snapshot = () => JSON.stringify(state.lyrics);

console.log('=== VIDA auto-Khmer second track ===\n');

// ---------- 1. language detection ----------
loadSong(VI, 'uploads/audio/vi_song.mp3');
assert(T.sourceIsForeign() === true, 'Vietnamese lyrics are detected as a foreign song');
assert(T.sourceIsKhmer() === false, 'Vietnamese lyrics are not treated as Khmer');
assert(T.wantsAutoKhmer() === true, 'Foreign song + auto on ⇒ Khmer is the wanted target');

loadSong(KH, 'uploads/audio/km_song.mp3');
assert(T.sourceIsKhmer() === true, 'Khmer lyrics are detected as Khmer');
assert(T.wantsAutoKhmer() === false, 'Khmer song never auto-targets Khmer at itself');

// ---------- 2. auto build on load (foreign song, no track on disk) ----------
loadSong(VI, 'uploads/audio/vi_song.mp3');
store.clear();
const origSnap = snapshot();
handler = (url, body) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) {
    return { status: 'success', lines: ['ទំនាញចិត្តសម្រាល', 'សំនួរស្រលាញ់ផ្ញើទៅ', 'ទោះឆ្ងាយក៏នៅរំលឹក'] };
  }
  if (url.includes('/translation/save')) return { status: 'success', saved: 3 };
  return {};
};
const built = await T.loadTranslationForSong();
assert(built === true, 'Loading a foreign song builds the Khmer track automatically');
assert(translatePosts() === 1, `exactly one translate-lines call on the first load (got ${translatePosts()})`);
const firstPost = calls.find(c => c.url.includes('/translate-lines'));
assert(firstPost && firstPost.body.target_lang === 'Khmer', 'the automatic target language is Khmer');
assert(state.translation.lang === 'km', `target language switched to km (${state.translation.lang})`);
const sv = savePosts();
assert(sv.length === 1 && sv[0].body.lang === 'km', 'the built track is persisted as the km track');
assert(sv.length === 1 && sv[0].body.lines.length === 3, 'all 3 lines are saved 1:1 with the original cues');
assert(/[\u1780-\u17FF]/.test((state.translation.lines || []).map(l => l.text).join('')), 'translated lines contain Khmer codepoints (U+1780–U+17FF)');
assert(T.getDisplayMode() === 'bilingual', `mode lands on bilingual so Khmer shows as the second line (${T.getDisplayMode()})`);
assert(state.lyrics.every(l => !/[ក-៿]/.test(l.text)), 'original lyric lines stay in the original language');
assert(snapshot() === origSnap, 'state.lyrics is byte-identical after the auto build');
assert(T.getTranslationCues().every(c => c.start > 0 && c.end > c.start), 'translated cues reuse the original timing windows');

// ---------- 3. reload must not re-bill ----------
const madeMarks = JSON.parse(store.get('vida_auto_khmer_built') || '{}');
assert(Object.keys(madeMarks).includes('uploads/audio/vi_song.mp3'), 'the song is marked as already auto-built');
loadSong(VI, 'uploads/audio/vi_song.mp3');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: ['km'] };
  if (url.includes('/api/lyrics/translation?')) return { cues: [
    { start: 1.0, end: 4.0, text: 'ទំនាញចិត្តសម្រាល' },
    { start: 4.2, end: 7.0, text: 'សំនួរស្រលាញ់ផ្ញើទៅ' },
    { start: 7.2, end: 10.5, text: 'ទោះឆ្ងាយក៏នៅរំលឹក' }
  ] };
  return {};
};
const rebuilt = await T.loadTranslationForSong();
assert(rebuilt === true, 'the stored Khmer track loads on reopen');
assert(translatePosts() === 0, 'reopening the song does NOT call the translation API again');
assert(state.translation.lang === 'km', 'the restored track keeps Khmer as the target language');

// ---------- 4. auto switch off ⇒ no build ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
state.translation.autoTranslate = false;
assert(T.wantsAutoKhmer() === false, 'Auto Khmer off ⇒ foreign songs are not auto-translated');
handler = (url) => (url.includes('/translation/list') ? { langs: [] } : {});
const skipped = await T.loadTranslationForSong();
assert(skipped === false, 'nothing is built while Auto Khmer is off');
assert(translatePosts() === 0, 'no translation API call while Auto Khmer is off');
state.translation.autoTranslate = true;

// ---------- 5. explicit saved language still wins ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
localStorage.setItem('vida_project_session', JSON.stringify({
  audioKey: 'uploads/audio/vi_song.mp3', lang: 'en', displayMode: 'translation_only'
}));
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: ['en'] };
  if (url.includes('/api/lyrics/translation?')) return { lines: ['Sky with my love', 'Words of love sent on', 'Still remembering you'] };
  return {};
};
const kept = await T.loadTranslationForSong();
assert(kept === true && state.translation.lang === 'en', 'a language the user saved for this song beats the auto default');
assert(translatePosts() === 0, 'the saved English track is reused, not re-translated');

// ---------- 6. failed build releases its marker so it can retry ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { __status: 503, detail: 'translation provider down' };
  return {};
};
const failed = await T.loadTranslationForSong();
assert(failed === false, 'a failed auto build is reported as no track');
assert(JSON.parse(localStorage.getItem('vida_auto_khmer_built') || '{}')['uploads/audio/vi_song.mp3'] === undefined,
  'a failed build releases the marker so a later load can retry');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['ទំនាញចិត្តសម្រាល', 'សំនួរស្រលាញ់ផ្ញើទៅ', 'ទោះឆ្ងាយក៏នៅរំលឹក'] };
  return {};
};
const retried = await T.loadTranslationForSong();
assert(retried === true && translatePosts() === 2, `retry after a failure rebuilds the track (calls: ${translatePosts()})`);

// ---------- 8. switching songs must never carry the previous song's translation on screen ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['ទំនាញចិត្តសម្រាល', 'សំនួរស្រលាញ់ផ្ញើទៅ', 'ទោះឆ្ងាយក៏នៅរំលឹក'] };
  return {};
};
await T.loadTranslationForSong();
const songALines = (state.translation.lines || []).map(l => l.text).join('|');
assert(songALines.length > 0, 'song A got its own Khmer track');

// Switch to a different foreign song whose Khmer track does not exist yet
const VI2 = VI.map(l => ({ ...l, text: l.text + '!' }));
const keepA = (state.translation.lines || []).slice();
switchSong(VI2, 'uploads/audio/vi_song_two.mp3', keepA);
assert((state.translation.lines || []).filter(l => l.text).length === 3,
  'the previous song\'s lines are still in state right before reconciliation');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['សម្លេងបទចម្រៀងពីរ', 'វាមិនមែនជាបទចាស់ទេ', 'តែជាការបកប្រែថ្មី'] };
  return {};
};
await T.loadTranslationForSong();
assert((state.translation.lines || []).map(l => l.text).join('|') !== songALines,
  'the new song does not keep song A\'s Khmer lines');
assert(translatePosts() === 1, `the new song builds its own track (calls: ${translatePosts()})`);
assert(state.translation.lines.every((l, i) => l.start === state.lyrics[i].start && l.end === state.lyrics[i].end),
  'the rebuilt track is anchored to the new song\'s own cue timings');

// Stale lines are dropped immediately, even when the new song has NO translation at all
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['ទំនាញចិត្តសម្រាល', 'សំនួរស្រលាញ់ផ្ញើទៅ', 'ទោះឆ្ងាយក៏នៅរំលឹក'] };
  return {};
};
await T.loadTranslationForSong();
const builtOwner = String(state.translation.ownerKey || '');
const builtLines = (state.translation.lines || []).slice();
switchSong(KH, 'uploads/audio/km_song.mp3', builtLines);   // Khmer song: auto-build must NOT run
handler = (url) => (url.includes('/translation/list') ? { langs: [] } : {});
calls = [];
const kmRes = await T.loadTranslationForSong();
assert(kmRes === false, 'a Khmer song does not trigger the auto Khmer build');
assert(translatePosts() === 0, 'no translation API call for a Khmer song');
assert((state.translation.lines || []).every(l => !l.text),
  'loading another song drops the previous track instead of showing it as the second line');
assert(state.translation.ownerKey === builtOwner, 'ownership of the dropped track is remembered for the song that owns it');

// ---------- 9. a language switch never leaves another language's lines on screen ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_song.mp3');
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: ['km'] };
  if (url.includes('/api/lyrics/translation?')) return { cues: [
    { start: 1.0, end: 4.0, text: 'ទំនាញចិត្តសម្រាល' },
    { start: 4.2, end: 7.0, text: 'សំនួរស្រលាញ់ផ្ញើទៅ' },
    { start: 7.2, end: 10.5, text: 'ទោះឆ្ងាយក៏នៅរំលឹក' }
  ] };
  return {};
};
await T.loadTranslationForSong();
assert(String(state.translation.ownerKey || '') === 'uploads/audio/vi_song.mp3::km',
  `track ownership recorded (${state.translation.ownerKey})`);
assert((state.translation.lines || []).filter(l => l.text).length === 3, 'the Khmer track is in memory');

// Pick a language that has no saved track at all, with auto-Khmer off so nothing re-targets
state.translation.autoTranslate = false;
state.translation.lang = 'th';
handler = (url) => (url.includes('/translation/list') ? { langs: [] } : {});
const thRes = await T.loadTranslationForSong();
assert(thRes === false, 'a language with no saved track reports no track');
assert((state.translation.lines || []).every(l => !l.text),
  'the Khmer lines are dropped instead of being shown as the Thai track');
state.translation.autoTranslate = true;

// ---------- 10. the saved mode returns even when the song key arrives after boot ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_restore.mp3');
localStorage.setItem('vida_project_session', JSON.stringify({
  audioKey: 'uploads/audio/vi_restore.mp3', displayMode: 'translation_only', lang: 'km', visible: true, autoTranslate: true
}));
state.translation.displayMode = 'original_only';   // what a boot with no audio key falls back to
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: ['km'] };
  if (url.includes('/api/lyrics/translation?')) return { cues: [
    { start: 1.0, end: 4.0, text: 'ទំនាញចិត្តសម្រាល' },
    { start: 4.2, end: 7.0, text: 'សំនួរស្រលាញ់ផ្ញើទៅ' },
    { start: 7.2, end: 10.5, text: 'ទោះឆ្ងាយក៏នៅរំលឹក' }
  ] };
  return {};
};
await T.loadTranslationForSong();
assert(T.getDisplayMode() === 'translation_only', 'the display mode saved with the project is restored when the song is reconciled');
assert(state.translation.visible === true, 'second-line visibility is restored with it');
assert(translatePosts() === 0, 'restoring the mode costs no translation API call');

// ---------- 11. UI wiring: manual translate keeps the mode you were in ----------
T.initTranslationTrack(() => {});
store.clear();
loadSong(VI, 'uploads/audio/vi_manual.mp3');
state.translation.autoTranslate = false;
state.translation.displayMode = 'translation_only';
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['បន្ទាត់ខ្មែរមួយ', 'បន្ទាត់ខ្មែរពីរ', 'បន្ទាត់ខ្មែរបី'] };
  return {};
};
await elements['btn-translate-all'].click();
assert(translatePosts() === 1, 'the 🌐 Translate button runs one translation');
assert(T.getDisplayMode() === 'translation_only', 'a manual translate keeps the display mode you had chosen');
assert((state.translation.lines || []).filter(l => l.text).length === 3, 'the manual track is filled');
assert(elements['btn-translate-all'].disabled === false && elements['btn-translate-all'].textContent === '🌐 Translate',
  'the button is re-enabled with its original label afterwards');

// ---------- 12. ticking the auto box on builds the Khmer track right away ----------
store.clear();
loadSong(VI, 'uploads/audio/vi_chk.mp3');
state.translation.autoTranslate = false;
elements['chk-auto-khmer'].checked = true;
handler = (url) => {
  if (url.includes('/translation/list')) return { langs: [] };
  if (url.includes('/translate-lines')) return { status: 'success', lines: ['បន្ទាត់ខ្មែរមួយ', 'បន្ទាត់ខ្មែរពីរ', 'បន្ទាត់ខ្មែរបី'] };
  return {};
};
await elements['chk-auto-khmer'].click('change');
assert(state.translation.autoTranslate === true, 'the checkbox writes the preference');
assert(translatePosts() === 1, 'turning Auto Khmer on builds the track for the foreign song immediately');
assert(state.translation.lang === 'km' && T.getDisplayMode() === 'bilingual',
  `auto build from the checkbox targets km + bilingual (${state.translation.lang} / ${T.getDisplayMode()})`);
elements['chk-auto-khmer'].checked = false;
await elements['chk-auto-khmer'].click('change');
assert(state.translation.autoTranslate === false, 'turning it off is persisted too');

console.log(`\n${failures ? '❌ ' + failures + ' FAILED' : '✅ ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
