// Checks pasted lyrics before aligning: rows left out, and rows that write one phrase twice.
// Catches rows left out of pasted lyrics before aligning. A missing row pushes every later
// line off the singer, so the align dialog checks the paste as it changes and offers to add
// the row back. The check uses the song's own repeats (backend: /api/lyrics/check-paste).
// When the text cannot tell which of two verses lost the row, both options are offered.

import { escapeHtml } from '../core/translation.js';

const CHECK_DELAY_MS = 400;

function insertRow(text, afterRow, row) {
  const rows = text.split('\n');
  rows.splice(afterRow + 1, 0, row);
  return rows.join('\n');
}

function renderGroup(group, gi) {
  const quote = (t) => `<span class="am-quote">${escapeHtml(t)}</span>`;
  if (group.length === 1) {
    const o = group[0];
    return `<div class="am-item">
      <div class="am-text">A row seems missing after line ${o.after_line} ${o.before ? quote(o.before) : ''}.
        The same passage elsewhere has ${quote(o.text)} here (line ${o.copied_from_line}).</div>
      <div class="am-acts">
        <button class="ui-btn ui-btn--sm ui-btn--go" data-g="${gi}" data-o="0">Add this row</button>
        <button class="ui-btn ui-btn--sm ui-btn--ghost" data-ignore="${gi}">Ignore</button>
      </div></div>`;
  }
  const opts = group.map((o, oi) => `<button class="ui-btn ui-btn--sm" data-g="${gi}" data-o="${oi}"
      title="Insert after line ${o.after_line}">Add ${quote(o.text)} after line ${o.after_line}</button>`).join('');
  return `<div class="am-item">
    <div class="am-text">Two copies of a repeated passage differ here, so one of them is missing a row.
      The words alone can't tell which; you know the song, so pick the one that is sung:</div>
    <div class="am-acts am-acts--stack">${opts}
      <button class="ui-btn ui-btn--sm ui-btn--ghost" data-ignore="${gi}">Neither, ignore</button>
    </div></div>`;
}

function renderDoubled(d, di) {
  const where = d.lines.length === 1 ? `Row ${d.lines[0]}` : `Rows ${d.lines.join(', ')}`;
  return `<div class="am-item">
    <div class="am-text">${where} sing <span class="am-quote">${escapeHtml(d.phrase)}</span> twice.
      Show each time on its own line, so it appears when it is sung?</div>
    <div class="am-acts">
      <button class="ui-btn ui-btn--sm ui-btn--go" data-split="${di}">Show as ${d.lines.length * 2} lines</button>
      <button class="ui-btn ui-btn--sm ui-btn--ghost" data-ignore-doubled="${di}">Keep as one line</button>
    </div></div>`;
}

/** Splits the given pasted rows into their two halves, each on its own row. */
function splitRows(text, rowIndexes) {
  const rows = text.split('\n');
  [...rowIndexes].sort((a, b) => b - a).forEach((r) => {
    const parts = (rows[r] || '').trim().split(/\s+/);
    const half = parts.length / 2;
    if (!Number.isInteger(half) || half < 1) return;
    rows.splice(r, 1, parts.slice(0, half).join(' '), parts.slice(half).join(' '));
  });
  return rows.join('\n');
}

/**
 * Wires the check to the align dialog's textarea. Returns check() to run it immediately.
 * onCount(n) receives the number of sung lines the backend will align (instrumental markers excluded).
 */
export function initPasteCheck(input, onCount = () => {}) {
  const box = document.getElementById('align-missing');
  if (!input || !box) return { check: () => {} };
  let timer = 0;
  let seq = 0;
  let groups = [];
  let doubled = [];
  const ignored = new Set();

  const render = () => {
    const shown = [
      ...groups.map((g, gi) => (ignored.has(JSON.stringify(g)) ? '' : renderGroup(g, gi))),
      ...doubled.map((d, di) => (ignored.has('doubled:' + d.phrase) ? '' : renderDoubled(d, di))),
    ].filter(Boolean);
    box.hidden = shown.length === 0;
    box.innerHTML = shown.length
      ? `<div class="am-head">${shown.length === 1 ? 'One thing to check before aligning' : `${shown.length} things to check before aligning`}</div>${shown.join('')}`
      : '';
  };

  const check = async () => {
    const mine = ++seq;
    const text = input.value;
    if (!text.trim()) { groups = []; doubled = []; render(); return; }
    try {
      const res = await fetch('/api/lyrics/check-paste', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reference_text: text }),
      });
      const data = await res.json();
      if (mine !== seq) return; // a newer edit is already being checked
      groups = res.ok && Array.isArray(data.missing) ? data.missing : [];
      doubled = res.ok && Array.isArray(data.doubled) ? data.doubled : [];
      if (res.ok && Number.isFinite(data.lines_count)) onCount(data.lines_count);
    } catch (_) {
      groups = []; // the check is a helper; aligning still works without it
      doubled = [];
    }
    render();
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(check, CHECK_DELAY_MS);
  });

  box.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    if (btn.dataset.ignoreDoubled !== undefined) {
      ignored.add('doubled:' + doubled[+btn.dataset.ignoreDoubled].phrase);
      render();
      return;
    }
    if (btn.dataset.split !== undefined) {
      const d = doubled[+btn.dataset.split];
      if (!d) return;
      input.value = splitRows(input.value, d.rows);
      input.dispatchEvent(new Event('input'));
      return;
    }
    if (btn.dataset.ignore !== undefined) {
      ignored.add(JSON.stringify(groups[+btn.dataset.ignore]));
      render();
      return;
    }
    const o = groups[+btn.dataset.g]?.[+btn.dataset.o];
    if (!o) return;
    input.value = insertRow(input.value, o.insert_after_row, o.text);
    input.dispatchEvent(new Event('input')); // updates the line count and re-checks
  });

  return { check };
}
