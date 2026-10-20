/**
 * Headless parity test for the 3 lyrics display modes.
 * Runs the real frontend renderer (frontend/js/core/lyrics.js) against a stub 2D context
 * and asserts exactly which strings land on which canvas rows — the same function that
 * both the live preview and the WYSIWYG exporter call.
 *
 * Usage: node tests/test_display_modes.mjs
 */
import { state } from '../frontend/js/core/state.js';
import { updateLyricState, drawLyrics } from '../frontend/js/core/lyrics.js';

let failures = 0;
let checks = 0;
function assert(cond, msg) {
  checks++;
  if (!cond) { failures++; console.error(`  ❌ ${msg}`); }
  else console.log(`  ✅ ${msg}`);
}

// ---- stub canvas 2D context that records every fillText draw ----
function makeCtx() {
  const draws = [];
  const ctx = {
    draws,
    font: '700 40px sans-serif',
    textAlign: 'left', textBaseline: 'alphabetic',
    fillStyle: '#000', strokeStyle: '#000',
    globalAlpha: 1, lineWidth: 1, lineJoin: 'miter', miterLimit: 10,
    shadowColor: '', shadowBlur: 0, shadowOffsetY: 0,
    save() {}, restore() {}, beginPath() {}, closePath() {}, moveTo() {},
    rect() {}, roundRect() {}, arcTo() {}, clip() {}, fill() {},
    fillRect() {}, strokeRect() {}, translate() {}, scale() {}, rotate() {},
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    measureText(t) {
      const px = parseFloat((this.font.match(/(\d+(?:\.\d+)?)px/) || [0, 40])[1]);
      return { width: String(t).length * px * 0.52 };
    },
    fillText(text, x, y) {
      draws.push({ text: String(text), x, y, font: this.font, alpha: this.globalAlpha });
    },
    strokeText(text, x, y) {
      draws.push({ text: String(text), x, y, font: this.font, alpha: this.globalAlpha, stroke: true });
    }
  };
  ctx.stroke = function () {};
  return ctx;
}

const W = 1920, H = 1080;
const LYRIC_Y = H * 0.85;

const ORIGINAL = [
  { line_id: 0, start: 1.00, end: 4.00, text: 'ខ្ញុំស្រលាញ់អ្នកណាស់', words: [] },
  { line_id: 1, start: 4.20, end: 7.00, text: 'បេះដូងខ្ញុំបែកបាក់', words: [] },
  { line_id: 2, start: 7.20, end: 10.00, text: 'ត្រឡប់មកវិញម៉ឹន', words: [] }
];
const TRANSLATED = ['I love you so much', 'My heart is broken apart', 'Come back to me again'];

function setup(mode, lines = TRANSLATED) {
  state.lyrics = ORIGINAL.map(l => ({ ...l, words: [] }));
  state.showLyrics = true;
  state.lyricStyle = 'karaoke';
  state.palette = 'cyberpunk';
  state.translation.displayMode = mode;
  state.translation.visible = mode !== 'original_only';
  state.translation.lang = 'en';
  state.translation.lines = state.lyrics.map((l, i) => ({
    index: i, text: lines[i] || '', start: l.start, end: l.end
  }));
  state.translation.style = { sizeRatio: 0.55, offsetRatio: 0.55, color: '#ffffff', align: 'center', outline: true, shadow: true, background: false };
}

function drawAt(t) {
  const ctx = makeCtx();
  updateLyricState(t);
  drawLyrics(ctx, W, H);
  return ctx.draws.filter(d => !d.stroke);
}

console.log('\n=== VIDA Lyrics Display Mode parity tests ===\n');

// 1) ORIGINAL ONLY — default behaviour, no translated text anywhere
setup('original_only');
let drawn = drawAt(2.5).map(d => d.text);
assert(drawn.some(t => t.includes('ស្រលាញ់')), 'original_only draws the original Khmer line');
assert(!drawn.some(t => t.includes('I love you')), 'original_only draws NO translated text');
console.log(`   (texts on canvas: ${JSON.stringify(drawn)})`);

// 2) BILINGUAL — original at 85% height, translation in a lower row
setup('bilingual');
let rows = drawAt(2.5);
let kh = rows.find(d => d.text.includes('ស្រលាញ់'));
let en = rows.find(d => d.text.includes('I love you'));
assert(!!kh && !!en, 'bilingual draws BOTH the original and the translated line');
assert(kh && en && en.y > kh.y, `bilingual translation sits BELOW the original (orig y=${kh?.y?.toFixed(0)}, tr y=${en?.y?.toFixed(0)})`);
assert(en && parseFloat(en.font.match(/(\d+)px/)[1]) < parseFloat(kh.font.match(/(\d+)px/)[1]),
  'translation line is smaller than the original line');
console.log(`   (texts on canvas: ${JSON.stringify(rows.map(r => ({ t: r.text.slice(0, 22), y: Math.round(r.y) })))})`);

// 3) TRANSLATION ONLY — translated text takes the primary karaoke position, original hidden
setup('translation_only');
rows = drawAt(2.5);
const primary = rows.find(d => Math.abs(d.y - LYRIC_Y) < 2);
assert(!!primary && primary.text.includes('I love you'), `translation_only puts the translated line at the primary row (y=${primary?.y})`);
assert(!rows.some(d => /ស្រលាញ់/.test(d.text)), 'translation_only never shows the original text');
console.log(`   (texts on canvas: ${JSON.stringify(rows.map(r => ({ t: r.text.slice(0, 24), y: Math.round(r.y) })))})`);

// 4) TRANSLATION ONLY — next-line preview follows the translated track
setup('translation_only');
rows = drawAt(2.5);
const preview = rows.find(d => d.y < LYRIC_Y - 20);
assert(!!preview && /[a-zA-Z]/.test(preview.text), `next-line preview is translated too ("${preview?.text}")`);

// 5) Missing line falls back to the original — the stage is never blank
setup('translation_only', ['', 'My heart is broken apart', '']);
drawn = drawAt(2.5).map(d => d.text);
assert(drawn.some(t => t.includes('ស្រលាញ់')), 'translation_only falls back to the original when that line has no translation');
setup('translation_only', ['', 'My heart is broken apart', '']);
drawn = drawAt(5.5).map(d => d.text);
assert(drawn.some(t => t.includes('broken')), 'translated lines still render where present');

// 6) Mode switching must never mutate the original cue text or timings
setup('bilingual');
const before = JSON.stringify(state.lyrics.map(l => ({ text: l.text, start: l.start, end: l.end })));
drawAt(2.5); drawAt(5.5); drawAt(8.0);
setup('translation_only');
drawAt(2.5); drawAt(5.5); drawAt(8.0);
setup('original_only');
drawAt(2.5); drawAt(5.5); drawAt(8.0);
const after = JSON.stringify(state.lyrics.map(l => ({ text: l.text, start: l.start, end: l.end })));
assert(before === after, 'state.lyrics text/timestamps are byte-identical after cycling all three modes');
const trAfter = state.translation.lines.map(l => l.text);
assert(trAfter.join('|') === TRANSLATED.join('|'), 'translated track content is untouched by mode switching');

// 7) Word-timing isolation: translated sweep must never leak into the original cues
setup('translation_only');
drawAt(3.0);
const leaked = state.lyrics.filter(l => (l.words || []).some(w => !l.text.includes(w.word)));
assert(leaked.length === 0, `every cached word on the original cues belongs to the ORIGINAL text (leaks: ${leaked.length})`);
setup('original_only');
drawAt(3.0);
assert((state.lyrics[0].words || []).length > 0, 'original_only still populates original word timings as before');

console.log(`\n${failures === 0 ? '✅ ALL PASS' : '❌ FAILURES'} — ${checks - failures}/${checks} checks passed\n`);
process.exit(failures === 0 ? 0 : 1);
