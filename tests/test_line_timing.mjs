/**
 * Setting a line's start by hand (frontend/js/features/line_timing.js):
 *   - the line moves and its words move with it
 *   - the line before ends where this one now starts
 *   - lines keep their order: a time past a neighbour is pulled back inside
 *   - a line timed by hand counts as confirmed (no longer "unsure")
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
const [one, two] = state.lyrics;
assert(got === 54.0 && two.start === 54.0, 'the line starts at the typed time');
assert(two.words[0].start === 54.0 && two.words[1].start > 54.0 && two.words[1].end <= two.end, 'its words move with it and stay inside it');
assert(one.end === 53.95 && one.words[1].end <= 53.95, 'the line before ends where it now starts');
assert(two.confidence === 1 && two.timing_source === 'manual', 'it counts as confirmed, no longer unsure');

console.log('\n=== keeping the order ===');
song();
got = setLineStart(1, 70.0);
assert(got === 58.8 && state.lyrics[1].start === 58.8, 'a time past the next line is pulled back before it');
song();
got = setLineStart(1, 10.0);
assert(got === 50.5, 'a time before the previous line is pulled after it');

console.log('\n=== reading times ===');
assert(parseClock('1:05.4') === 65.4 && parseClock('65.4') === 65.4 && parseClock(' 0:55 ') === 55, 'm:ss.s and plain seconds are read');
assert(parseClock('abc') === null && parseClock('1:') === null, 'anything else is rejected');
assert(formatClock(65.4) === '1:05.40', 'times are shown as m:ss.cc');

console.log(`\n${failures ? '❌' : '✅'} ${failures ? `${failures} FAILED` : 'ALL PASS'} — ${checks - failures}/${checks} checks passed`);
process.exit(failures ? 1 : 0);
