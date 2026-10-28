/**
 * Setting a line's start by hand (frontend/js/features/line_timing.js):
 *   - the line moves and its words move with it
 *   - the line before ends where this one now starts
 *   - lines keep their order: a time past a neighbour is pulled back inside
 *   - a line timed by hand counts as confirmed (no longer "unsure")
 *   - the unsure lines right after it move by the same amount; confident and hand-set lines stay
 * Usage: node tests/test_line_timing.mjs
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
const { setLineStart, parseClock, formatClock } = await import('../frontend/js/features/line_timing.js');

const W = (word, start, end) => ({ word, start, end });
function song() {
  state.lyrics = [
    { text: 'one', start: 50.2, end: 55.5, confidence: 0.6, words: [W('o', 50.2, 52), W('ne', 52, 55.5)] },
    { text: 'two', start: 55.6, end: 59.1, confidence: 0.1, words: [W('t', 55.6, 57), W('wo', 57, 59.1)] },
    { text: 'three', start: 59.1, end: 65.2, confidence: 0.1, words: [W('th', 59.1, 62), W('ree', 62, 65.2)] },
  ];
}

console.log('=== moving a line ===');
song();
let got = setLineStart(1, 54.0);
const [one, two, three] = state.lyrics;
assert(got.start === 54.0 && two.start === 54.0, 'the line starts at the typed time');
assert(two.words[0].start === 54.0 && two.words[1].start > 54.0 && two.words[1].end <= two.end, 'its words move with it and stay inside it');
assert(one.end === 53.95 && one.words[1].end <= 53.95, 'the line before ends where it now starts');
assert(two.confidence === 1 && two.timing_source === 'manual', 'it counts as confirmed, no longer unsure');

console.log('\n=== the unsure lines after it follow ===');
assert(got.moved === 1 && three.start === 57.5 && three.end === 63.6 && three.words[1].start === 60.4, 'the unsure line after it moved by the same 1.6 s, words too');
assert(three.confidence === 0.1 && !three.timing_source, 'it stays marked unsure, since nobody checked it yet');
song();
state.lyrics.push({ text: 'four', start: 66, end: 70, confidence: 0.7, words: [W('four', 66, 70)] });
got = setLineStart(1, 57.6);
assert(got.moved === 1 && state.lyrics[2].start === 61.1, 'moving later pushes the unsure line after it later too');
assert(state.lyrics[3].start === 66 && state.lyrics[2].end === 65.95, 'a confident line stays where it is, and the moved line ends before it');
song();
state.lyrics[2].timing_source = 'tapped';
got = setLineStart(1, 54.0);
assert(got.moved === 0 && state.lyrics[2].start === 59.1, 'a line timed by hand never moves');
song();
state.lyrics[1].confidence = 0.9; state.lyrics[2].confidence = 0.9;
got = setLineStart(0, 49.0);
assert(got.moved === 0 && state.lyrics[1].start === 55.6, 'when the lines after are confident, only this line moves');

console.log('\n=== keeping the order ===');
song();
state.lyrics[2].confidence = 0.9;
got = setLineStart(1, 70.0);
assert(got.start === 58.8 && state.lyrics[1].start === 58.8, 'a time past the next line that stays is pulled back before it');
song();
state.lyrics.push({ text: 'four', start: 66, end: 70, confidence: 0.7, words: [W('four', 66, 70)] });
got = setLineStart(1, 70.0);
assert(got.start === 62.2 && state.lyrics[2].start === 65.7 && state.lyrics[2].end === 65.95, 'lines that move together still stop before the line that stays');
song();
got = setLineStart(1, 10.0);
assert(got.start === 50.5, 'a time before the previous line is pulled after it');

console.log('\n=== reading times ===');
assert(parseClock('1:05.4') === 65.4 && parseClock('65.4') === 65.4 && parseClock(' 0:55 ') === 55, 'm:ss.s and plain seconds are read');
assert(parseClock('abc') === null && parseClock('1:') === null, 'anything else is rejected');
assert(formatClock(65.4) === '1:05.40', 'times are shown as m:ss.cc');

console.log(`\n${failures ? '❌' : '✅'} ${failures ? `${failures} FAILED` : 'ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
