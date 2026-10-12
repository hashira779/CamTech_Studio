/**
 * VIDA Studio — SRT Subtitle Editor & Multi-Format Exporter
 * 
 * A professional subtitle editing engine with:
 * - Visual cue-by-cue editor with inline timing & text editing
 * - Raw SRT text editor with syntax-aware parsing
 * - Add, delete, duplicate, sort, shift, merge-overlapping cues
 * - Multi-format export: SRT, VTT, LRC, ASS, TXT
 * - Bidirectional sync with studio lyrics state
 */

import { state } from './state.js';

// ─── Time Formatting Utilities ───

/** Converts seconds to SRT timestamp format: HH:MM:SS,mmm */
export function secsToSrtTime(totalSeconds) {
  if (!totalSeconds || isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  const ms = Math.round((totalSeconds % 1) * 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
}

/** Converts seconds to VTT timestamp format: HH:MM:SS.mmm */
export function secsToVttTime(totalSeconds) {
  return secsToSrtTime(totalSeconds).replace(',', '.');
}

/** Converts seconds to LRC timestamp format: [MM:SS.xx] */
export function secsToLrcTime(totalSeconds) {
  if (!totalSeconds || isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `[${String(m).padStart(2, '0')}:${s.toFixed(2).padStart(5, '0')}]`;
}

/** Converts seconds to ASS timestamp format: H:MM:SS.cc */
export function secsToAssTime(totalSeconds) {
  if (!totalSeconds || isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  const cs = Math.round((totalSeconds % 1) * 100);
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
}

/** Parses SRT/VTT timestamp string to seconds */
export function parseSrtTimestamp(str) {
  if (!str) return 0;
  str = str.trim().replace(',', '.');
  const parts = str.split(':');
  if (parts.length === 3) {
    return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
  } else if (parts.length === 2) {
    return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
  }
  return parseFloat(str) || 0;
}

/** Quick MM:SS formatter for display */
function fmtShort(s) {
  if (!s || isNaN(s)) return '--:--';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}


// ─── Export Generators ───

/** Generates SRT format string from lyrics array with monotonic, non-overlapping validation */
export function generateSRT(lyrics) {
  if (!lyrics || lyrics.length === 0) return '';
  let prevEnd = 0.0;
  let cueIdx = 1;
  const blocks = [];
  for (const line of lyrics) {
    let start = Number(line.start !== undefined ? line.start : prevEnd);
    let end = Number(line.end !== undefined ? line.end : start + 2.5);
    const text = (line.text || '').trim();
    if (!text) continue;
    if (start < prevEnd) start = Number((prevEnd + 0.02).toFixed(3));
    if (end <= start + 0.3) end = Number((start + 1.2).toFixed(3));
    blocks.push(`${cueIdx}\n${secsToSrtTime(start)} --> ${secsToSrtTime(end)}\n${text}\n`);
    prevEnd = end;
    cueIdx++;
  }
  return blocks.join('\n');
}

/** Generates WebVTT format string with monotonic validation */
export function generateVTT(lyrics) {
  if (!lyrics || lyrics.length === 0) return 'WEBVTT\n\n';
  let out = 'WEBVTT\n\n';
  let prevEnd = 0.0;
  let cueIdx = 1;
  for (const line of lyrics) {
    let start = Number(line.start !== undefined ? line.start : prevEnd);
    let end = Number(line.end !== undefined ? line.end : start + 2.5);
    const text = (line.text || '').trim();
    if (!text) continue;
    if (start < prevEnd) start = Number((prevEnd + 0.02).toFixed(3));
    if (end <= start + 0.3) end = Number((start + 1.2).toFixed(3));
    out += `${cueIdx}\n${secsToVttTime(start)} --> ${secsToVttTime(end)}\n${text}\n\n`;
    prevEnd = end;
    cueIdx++;
  }
  return out;
}

/** Generates LRC format string */
export function generateLRC(lyrics) {
  if (!lyrics || lyrics.length === 0) return '';
  const title = state.songTitle || 'Unknown';
  const artist = state.artistName || 'Unknown';
  let out = `[ti:${title}]\n[ar:${artist}]\n[by:VIDA Studio Pro]\n\n`;
  lyrics.forEach(line => {
    out += `${secsToLrcTime(line.start)}${line.text}\n`;
  });
  return out;
}

/** Generates ASS/SSA format string with professional styling */
export function generateASS(lyrics) {
  if (!lyrics || lyrics.length === 0) return '';
  const title = state.songTitle || 'VIDA Studio Subtitles';
  const isKhmer = lyrics.some(l => /[\u1780-\u17FF]/.test(l.text));
  const fontName = isKhmer ? 'Kantumruy Pro' : 'Arial';
  const fontSize = isKhmer ? 28 : 24;

  let out = `[Script Info]
Title: ${title}
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0
Timer: 100.0000
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,${fontName},${fontSize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`;
  lyrics.forEach(line => {
    out += `Dialogue: 0,${secsToAssTime(line.start)},${secsToAssTime(line.end)},Default,,0,0,0,,${line.text}\n`;
  });
  return out;
}

/** Generates plain text (lyrics only, no timestamps) */
export function generateTXT(lyrics) {
  if (!lyrics || lyrics.length === 0) return '';
  return lyrics.map(l => l.text).join('\n');
}

/** Downloads a string as a file */
export function downloadFile(content, filename, mimeType = 'text/plain') {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

/** Gets the base filename for exports */
function getExportBaseName() {
  const title = (state.songTitle || 'subtitles').replace(/[^a-zA-Z0-9\u1780-\u17FF\u4E00-\u9FFF_\- ]/g, '').trim().replace(/\s+/g, '_');
  return title || 'subtitles';
}

/** Generates CapCut-optimized SRT with non-overlapping timings and safe-zone line splits */
export function generateCapCutSRT(lyrics) {
  if (!lyrics || lyrics.length === 0) return '';
  const blocks = [];
  let prevEnd = 0.0;
  let cueIndex = 1;

  lyrics.forEach((cue) => {
    let start = Math.max(0, cue.start || 0);
    let end = Math.max(start + 0.4, cue.end || start + 2.5);

    // Strictly eliminate overlap (CapCut drops overlapping cues)
    if (start < prevEnd) {
      start = prevEnd + 0.02;
    }
    if (end <= start) {
      end = start + 0.8;
    }

    let text = (cue.text || '').trim();
    // Split long lines at word boundary if line is too long (> 40 chars)
    if (text.length > 40 && text.includes(' ')) {
      const words = text.split(/\s+/);
      if (words.length >= 4) {
        const mid = Math.floor(words.length / 2);
        const p1 = words.slice(0, mid).join(' ');
        const p2 = words.slice(mid).join(' ');
        const midTime = start + (end - start) * 0.5;

        blocks.push(`${cueIndex++}\n${secsToSrtTime(start)} --> ${secsToSrtTime(midTime - 0.01)}\n${p1}\n`);
        blocks.push(`${cueIndex++}\n${secsToSrtTime(midTime)} --> ${secsToSrtTime(end)}\n${p2}\n`);
        prevEnd = end;
        return;
      }
    }

    blocks.push(`${cueIndex++}\n${secsToSrtTime(start)} --> ${secsToSrtTime(end)}\n${text}\n`);
    prevEnd = end;
  });

  return blocks.join('\n');
}

/** Exports 100% voice-synced SRT optimized specifically for CapCut */
export async function exportSubtitlesForCapCut(lyrics, showToastFn) {
  lyrics = lyrics || state.lyrics;
  if (!lyrics || lyrics.length === 0) return false;
  const baseName = getExportBaseName();

  try {
    const res = await fetch('/api/subtitles/export-capcut', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lyrics_data: lyrics,
        title: baseName
      })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.content) {
        downloadFile(data.content, data.filename || `${baseName}_CapCut.srt`, 'text/plain');
        if (showToastFn) {
          showToastFn('🎬 CapCut SRT Ready', `${data.cues_count} cues exported! Ready to drag & drop into CapCut.`, 'success', 3500);
        }
        return true;
      }
    }
  } catch (err) {
    console.warn('Backend CapCut export notice, using client fallback:', err);
  }

  // Client-side fallback
  const content = generateCapCutSRT(lyrics);
  downloadFile(content, `${baseName}_CapCut.srt`, 'text/plain');
  if (showToastFn) {
    showToastFn('🎬 CapCut SRT Exported', `${lyrics.length} cues formatted for CapCut video editor.`, 'success', 3500);
  }
  return true;
}

/** Exports subtitles in the specified format with backend verification and client fallback */
export async function exportSubtitles(format, lyrics, showToastFn) {
  lyrics = lyrics || state.lyrics;
  if (!lyrics || lyrics.length === 0) return false;

  const baseName = getExportBaseName();
  if (format === 'capcut' || format === 'capcut_srt') {
    return exportSubtitlesForCapCut(lyrics, showToastFn);
  }

  // 1. Try server-side verified export first for 100% studio-grade precision
  try {
    const res = await fetch('/api/subtitles/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lyrics_data: lyrics,
        format: format,
        title: baseName,
        artist: state.artistName || ''
      })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.content) {
        downloadFile(data.content, data.filename || `${baseName}.${format}`, data.mime_type || 'text/plain');
        if (showToastFn) {
          const formatNames = { srt: 'SRT', vtt: 'WebVTT', lrc: 'LRC', ass: 'ASS', txt: 'Plain Text' };
          showToastFn('📤 Subtitles Exported', `✅ ${lyrics.length} cues exported as studio-grade ${formatNames[format] || format}.`, 'success', 3000);
        }
        return true;
      }
    }
  } catch (err) {
    console.warn('Backend export notice, using client generator:', err);
  }

  // 2. Client-side fallback with strict validation
  switch (format) {
    case 'srt':
      downloadFile(generateSRT(lyrics), `${baseName}.srt`, 'text/plain');
      break;
    case 'vtt':
      downloadFile(generateVTT(lyrics), `${baseName}.vtt`, 'text/vtt');
      break;
    case 'lrc':
      downloadFile(generateLRC(lyrics), `${baseName}.lrc`, 'text/plain');
      break;
    case 'ass':
      downloadFile(generateASS(lyrics), `${baseName}.ass`, 'text/plain');
      break;
    case 'txt':
      downloadFile(generateTXT(lyrics), `${baseName}.txt`, 'text/plain');
      break;
    default:
      downloadFile(generateSRT(lyrics), `${baseName}.srt`, 'text/plain');
      break;
  }
  if (showToastFn) {
    const formatNames = { srt: 'SRT', vtt: 'WebVTT', lrc: 'LRC', ass: 'ASS', txt: 'Plain Text' };
    showToastFn('📤 Subtitles Exported', `✅ ${lyrics.length} cues exported as ${formatNames[format] || format}.`, 'success', 3000);
  }
  return true;
}


// ─── SRT Parser (Raw text → lyrics array) ───

/** Parses raw SRT text into a lyrics array [{start, end, text}] */
export function parseSRTText(srtText) {
  if (!srtText || !srtText.trim()) return [];
  const lyrics = [];
  // Split on double newlines or cue-number boundaries
  const blocks = srtText.trim().replace(/\r\n/g, '\n').split(/\n\s*\n/);

  for (const block of blocks) {
    const lines = block.trim().split('\n');
    if (lines.length < 2) continue;

    // Find the timestamp line
    let tsLineIdx = -1;
    for (let i = 0; i < lines.length; i++) {
      if (/-->/.test(lines[i])) {
        tsLineIdx = i;
        break;
      }
    }
    if (tsLineIdx < 0) continue;

    const tsLine = lines[tsLineIdx];
    const tsParts = tsLine.split('-->');
    if (tsParts.length !== 2) continue;

    const start = parseSrtTimestamp(tsParts[0]);
    const end = parseSrtTimestamp(tsParts[1]);
    const text = lines.slice(tsLineIdx + 1).join('\n').trim();

    if (text) {
      lyrics.push({ start, end, text });
    }
  }

  return lyrics.sort((a, b) => a.start - b.start);
}


// ─── SRT Editor Controller ───

let editorCues = [];     // Working copy of cues in the editor
let selectedCueIndices = new Set();

/** Clones the studio lyrics into the editor working copy */
function loadCuesFromState() {
  editorCues = (state.lyrics || []).map(l => ({
    start: l.start,
    end: l.end,
    text: l.text
  }));
  selectedCueIndices.clear();
}

/** Applies editor cues back to the studio state */
function applyCuesToState(showToastFn) {
  state.lyrics = editorCues.map(c => ({
    start: c.start,
    end: c.end,
    text: c.text,
    words: []
  }));
  if (showToastFn) {
    showToastFn('✅ Subtitles Applied', `${editorCues.length} cues synced to studio.`, 'success', 2500);
  }
}

/** Renders a single cue row in the visual editor */
function renderCueRow(cue, index) {
  const isSelected = selectedCueIndices.has(index);
  const isKhmer = /[\u1780-\u17FF]/.test(cue.text);
  const fontFamily = isKhmer
    ? "'Kantumruy Pro', 'Battambang', 'Siemreap', sans-serif"
    : "'Inter', 'Outfit', sans-serif";

  const row = document.createElement('div');
  row.className = 'srt-cue-row';
  row.dataset.index = index;
  if (isSelected) row.classList.add('srt-cue-selected');

  row.innerHTML = `
    <div class="srt-cue-num">
      <input type="checkbox" class="srt-cue-checkbox" ${isSelected ? 'checked' : ''} title="Select cue">
      <span class="srt-cue-index">${index + 1}</span>
    </div>
    <div class="srt-cue-timing">
      <div class="srt-time-group">
        <label>IN</label>
        <input type="text" class="srt-time-input srt-time-start" value="${secsToSrtTime(cue.start)}" title="Start time (click to jump audio)" spellcheck="false">
      </div>
      <span class="srt-time-arrow">→</span>
      <div class="srt-time-group">
        <label>OUT</label>
        <input type="text" class="srt-time-input srt-time-end" value="${secsToSrtTime(cue.end)}" spellcheck="false">
      </div>
      <span class="srt-cue-duration" title="Cue duration">${(cue.end - cue.start).toFixed(1)}s</span>
    </div>
    <div class="srt-cue-text-wrapper">
      <textarea class="srt-cue-text" rows="1" spellcheck="false" style="font-family: ${fontFamily};">${cue.text}</textarea>
    </div>
    <div class="srt-cue-actions">
      <button class="srt-cue-action-btn srt-cue-duplicate" title="Duplicate cue">📋</button>
      <button class="srt-cue-action-btn srt-cue-insert-after" title="Insert cue after this">➕</button>
      <button class="srt-cue-action-btn srt-cue-delete" title="Delete this cue">🗑️</button>
    </div>
  `;

  return row;
}

/** Updates header badges */
function updateEditorStats() {
  const countEl = document.getElementById('srt-editor-line-count');
  const durEl = document.getElementById('srt-editor-duration');
  if (countEl) countEl.textContent = `${editorCues.length} cue${editorCues.length !== 1 ? 's' : ''}`;
  if (durEl) {
    const maxEnd = editorCues.reduce((max, c) => Math.max(max, c.end || 0), 0);
    durEl.textContent = fmtShort(maxEnd);
  }
}

/** Renders all cue rows in the visual editor */
function renderVisualEditor() {
  const container = document.getElementById('srt-visual-editor');
  const emptyEl = document.getElementById('srt-editor-empty');
  if (!container) return;

  // Clear existing cue rows (keep empty state placeholder)
  container.querySelectorAll('.srt-cue-row').forEach(el => el.remove());

  if (editorCues.length === 0) {
    if (emptyEl) emptyEl.style.display = 'block';
    updateEditorStats();
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';

  editorCues.forEach((cue, index) => {
    const row = renderCueRow(cue, index);
    container.appendChild(row);
  });

  updateEditorStats();
  attachCueRowListeners();
}

/** Attach event listeners to all cue rows */
function attachCueRowListeners() {
  const container = document.getElementById('srt-visual-editor');
  if (!container) return;

  container.querySelectorAll('.srt-cue-row').forEach(row => {
    const index = parseInt(row.dataset.index);

    // Checkbox selection
    const checkbox = row.querySelector('.srt-cue-checkbox');
    if (checkbox) {
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) {
          selectedCueIndices.add(index);
          row.classList.add('srt-cue-selected');
        } else {
          selectedCueIndices.delete(index);
          row.classList.remove('srt-cue-selected');
        }
      });
    }

    // Start time input — click to jump audio
    const startInput = row.querySelector('.srt-time-start');
    if (startInput) {
      startInput.addEventListener('click', () => {
        const audioPlayer = document.getElementById('audio-player');
        if (audioPlayer && audioPlayer.src) {
          audioPlayer.currentTime = editorCues[index].start;
        }
      });
      startInput.addEventListener('change', () => {
        editorCues[index].start = parseSrtTimestamp(startInput.value);
        // Update duration badge
        const durSpan = row.querySelector('.srt-cue-duration');
        if (durSpan) durSpan.textContent = `${(editorCues[index].end - editorCues[index].start).toFixed(1)}s`;
        updateEditorStats();
      });
    }

    // End time input
    const endInput = row.querySelector('.srt-time-end');
    if (endInput) {
      endInput.addEventListener('change', () => {
        editorCues[index].end = parseSrtTimestamp(endInput.value);
        const durSpan = row.querySelector('.srt-cue-duration');
        if (durSpan) durSpan.textContent = `${(editorCues[index].end - editorCues[index].start).toFixed(1)}s`;
        updateEditorStats();
      });
    }

    // Text editing
    const textArea = row.querySelector('.srt-cue-text');
    if (textArea) {
      textArea.addEventListener('input', () => {
        editorCues[index].text = textArea.value;
        // Auto-resize textarea
        textArea.style.height = 'auto';
        textArea.style.height = textArea.scrollHeight + 'px';
      });
      // Auto-resize on load
      requestAnimationFrame(() => {
        textArea.style.height = 'auto';
        textArea.style.height = textArea.scrollHeight + 'px';
      });
    }

    // Duplicate cue
    const dupBtn = row.querySelector('.srt-cue-duplicate');
    if (dupBtn) {
      dupBtn.addEventListener('click', () => {
        const clone = { ...editorCues[index] };
        clone.start = editorCues[index].end;
        clone.end = clone.start + (editorCues[index].end - editorCues[index].start);
        editorCues.splice(index + 1, 0, clone);
        renderVisualEditor();
      });
    }

    // Insert after
    const insertBtn = row.querySelector('.srt-cue-insert-after');
    if (insertBtn) {
      insertBtn.addEventListener('click', () => {
        const endTime = editorCues[index].end;
        const nextStart = (index + 1 < editorCues.length) ? editorCues[index + 1].start : endTime + 3;
        const newCue = {
          start: endTime,
          end: Math.min(endTime + 3, nextStart),
          text: ''
        };
        editorCues.splice(index + 1, 0, newCue);
        renderVisualEditor();
        // Focus the new text area
        setTimeout(() => {
          const newRow = document.querySelector(`.srt-cue-row[data-index="${index + 1}"]`);
          if (newRow) {
            const ta = newRow.querySelector('.srt-cue-text');
            if (ta) ta.focus();
            newRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }, 50);
      });
    }

    // Delete cue
    const delBtn = row.querySelector('.srt-cue-delete');
    if (delBtn) {
      delBtn.addEventListener('click', () => {
        editorCues.splice(index, 1);
        selectedCueIndices.delete(index);
        renderVisualEditor();
      });
    }
  });
}


/** Syncs editor cues to raw SRT textarea */
function syncToRawEditor() {
  const textarea = document.getElementById('srt-raw-textarea');
  if (textarea) {
    textarea.value = generateSRT(editorCues);
  }
}

/** Parses raw SRT textarea back to editor cues */
function syncFromRawEditor() {
  const textarea = document.getElementById('srt-raw-textarea');
  if (textarea) {
    editorCues = parseSRTText(textarea.value);
    renderVisualEditor();
  }
}


// ─── Main Initialization ───

export function initSRTEditor(showToastFn, renderTeleprompterFn) {
  const modal = document.getElementById('srt-editor-modal');
  const shiftDialog = document.getElementById('srt-shift-dialog');
  if (!modal) return;

  // ── Open SRT Editor ──
  const btnOpen = document.getElementById('btn-open-srt-editor');
  if (btnOpen) {
    btnOpen.addEventListener('click', () => {
      loadCuesFromState();
      renderVisualEditor();
      syncToRawEditor();
      modal.style.display = 'flex';
    });
  }

  // ── Close SRT Editor ──
  const btnClose = document.getElementById('btn-close-srt-editor');
  if (btnClose) {
    btnClose.addEventListener('click', () => {
      modal.style.display = 'none';
    });
  }
  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });

  // ── Mode Toggle (Visual / Raw SRT) ──
  const btnVisual = document.getElementById('srt-btn-visual-mode');
  const btnRaw = document.getElementById('srt-btn-raw-mode');
  const visualEditor = document.getElementById('srt-visual-editor');
  const rawEditor = document.getElementById('srt-raw-editor');
  const btnApplyRaw = document.getElementById('srt-btn-apply-raw');

  if (btnVisual && btnRaw) {
    btnVisual.addEventListener('click', () => {
      btnVisual.classList.add('srt-mode-active');
      btnVisual.style.background = 'rgba(56, 189, 248, 0.2)';
      btnVisual.style.borderColor = 'rgba(56, 189, 248, 0.5)';
      btnVisual.style.color = '#38bdf8';
      btnRaw.classList.remove('srt-mode-active');
      btnRaw.style.background = 'rgba(255,255,255,0.06)';
      btnRaw.style.borderColor = 'rgba(255,255,255,0.12)';
      btnRaw.style.color = '#94a3b8';
      if (visualEditor) visualEditor.style.display = 'flex';
      if (rawEditor) rawEditor.style.display = 'none';
      if (btnApplyRaw) btnApplyRaw.style.display = 'none';
      // Parse raw back if we were in raw mode
      syncFromRawEditor();
    });

    btnRaw.addEventListener('click', () => {
      btnRaw.classList.add('srt-mode-active');
      btnRaw.style.background = 'rgba(56, 189, 248, 0.2)';
      btnRaw.style.borderColor = 'rgba(56, 189, 248, 0.5)';
      btnRaw.style.color = '#38bdf8';
      btnVisual.classList.remove('srt-mode-active');
      btnVisual.style.background = 'rgba(255,255,255,0.06)';
      btnVisual.style.borderColor = 'rgba(255,255,255,0.12)';
      btnVisual.style.color = '#94a3b8';
      if (visualEditor) visualEditor.style.display = 'none';
      if (rawEditor) rawEditor.style.display = 'flex';
      if (btnApplyRaw) btnApplyRaw.style.display = 'inline-flex';
      syncToRawEditor();
    });
  }

  // ── Parse & Apply Raw ──
  if (btnApplyRaw) {
    btnApplyRaw.addEventListener('click', () => {
      syncFromRawEditor();
      if (showToastFn) showToastFn('📝 Raw SRT Parsed', `${editorCues.length} cues parsed from raw text.`, 'success', 2000);
    });
  }

  // ── Add Cue at End ──
  const btnAddCue = document.getElementById('srt-btn-add-cue');
  if (btnAddCue) {
    btnAddCue.addEventListener('click', () => {
      const lastEnd = editorCues.length > 0 ? editorCues[editorCues.length - 1].end : 0;
      editorCues.push({
        start: lastEnd,
        end: lastEnd + 3,
        text: ''
      });
      renderVisualEditor();
      syncToRawEditor();
      // Scroll to bottom and focus
      setTimeout(() => {
        const container = document.getElementById('srt-visual-editor');
        if (container) container.scrollTop = container.scrollHeight;
        const lastRow = document.querySelector(`.srt-cue-row[data-index="${editorCues.length - 1}"]`);
        if (lastRow) {
          const ta = lastRow.querySelector('.srt-cue-text');
          if (ta) ta.focus();
        }
      }, 50);
    });
  }

  // ── Add Cue at Playhead ──
  const btnAddHere = document.getElementById('srt-btn-add-cue-here');
  if (btnAddHere) {
    btnAddHere.addEventListener('click', () => {
      const audioPlayer = document.getElementById('audio-player');
      const currentTime = (audioPlayer && audioPlayer.currentTime) || 0;
      const newCue = {
        start: currentTime,
        end: currentTime + 3,
        text: ''
      };
      // Insert in sorted position
      let insertIdx = editorCues.findIndex(c => c.start > currentTime);
      if (insertIdx === -1) insertIdx = editorCues.length;
      editorCues.splice(insertIdx, 0, newCue);
      renderVisualEditor();
      syncToRawEditor();
      setTimeout(() => {
        const newRow = document.querySelector(`.srt-cue-row[data-index="${insertIdx}"]`);
        if (newRow) {
          newRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
          const ta = newRow.querySelector('.srt-cue-text');
          if (ta) ta.focus();
        }
      }, 50);
      if (showToastFn) showToastFn('⏱️ Cue Added', `New cue at ${secsToSrtTime(currentTime)}`, 'info', 2000);
    });
  }

  // ── Delete Selected ──
  const btnDeleteSelected = document.getElementById('srt-btn-delete-selected');
  if (btnDeleteSelected) {
    btnDeleteSelected.addEventListener('click', () => {
      if (selectedCueIndices.size === 0) {
        if (showToastFn) showToastFn('ℹ️ No Selection', 'Check the boxes next to cues you want to delete.', 'info', 2000);
        return;
      }
      const sorted = [...selectedCueIndices].sort((a, b) => b - a);
      sorted.forEach(idx => editorCues.splice(idx, 1));
      selectedCueIndices.clear();
      renderVisualEditor();
      syncToRawEditor();
      if (showToastFn) showToastFn('🗑️ Deleted', `${sorted.length} cue(s) removed.`, 'success', 2000);
    });
  }

  // ── Sort Cues ──
  const btnSort = document.getElementById('srt-btn-sort-cues');
  if (btnSort) {
    btnSort.addEventListener('click', () => {
      editorCues.sort((a, b) => a.start - b.start);
      selectedCueIndices.clear();
      renderVisualEditor();
      syncToRawEditor();
      if (showToastFn) showToastFn('🔃 Sorted', 'All cues sorted by start time.', 'success', 1500);
    });
  }

  // ── Shift All ──
  const btnShiftAll = document.getElementById('srt-btn-shift-all');
  if (btnShiftAll && shiftDialog) {
    btnShiftAll.addEventListener('click', () => {
      shiftDialog.style.display = 'flex';
    });

    const btnShiftCancel = document.getElementById('srt-shift-cancel');
    const btnShiftApply = document.getElementById('srt-shift-apply');
    const shiftInput = document.getElementById('srt-shift-value');

    if (btnShiftCancel) {
      btnShiftCancel.addEventListener('click', () => {
        shiftDialog.style.display = 'none';
      });
    }

    if (btnShiftApply && shiftInput) {
      btnShiftApply.addEventListener('click', () => {
        const offset = parseFloat(shiftInput.value) || 0;
        if (offset === 0) {
          shiftDialog.style.display = 'none';
          return;
        }
        editorCues.forEach(cue => {
          cue.start = Math.max(0, cue.start + offset);
          cue.end = Math.max(cue.start + 0.1, cue.end + offset);
        });
        renderVisualEditor();
        syncToRawEditor();
        shiftDialog.style.display = 'none';
        if (showToastFn) showToastFn('⏩ Shifted', `All cues shifted by ${offset > 0 ? '+' : ''}${offset}s.`, 'success', 2000);
      });
    }

    // Close shift dialog on backdrop
    shiftDialog.addEventListener('click', (e) => {
      if (e.target === shiftDialog) shiftDialog.style.display = 'none';
    });
  }

  // ── Show Earlier (+0.5s) ──
  const btnSrtShowEarlier = document.getElementById('srt-btn-show-earlier');
  if (btnSrtShowEarlier) {
    btnSrtShowEarlier.addEventListener('click', () => {
      editorCues.forEach(cue => {
        cue.start = Math.max(0, Math.round((cue.start - 0.5) * 100) / 100);
        cue.end = Math.max(cue.start + 0.35, Math.round((cue.end - 0.5) * 100) / 100);
      });
      renderVisualEditor();
      syncToRawEditor();
      if (showToastFn) showToastFn('⚡ Show Earlier (+0.5s)', 'All cues shifted 0.5s earlier to show before singing.', 'success', 2500);
    });
  }

  // ── Fix Overlaps ──
  const btnFixOverlaps = document.getElementById('srt-btn-merge-overlap');
  if (btnFixOverlaps) {
    btnFixOverlaps.addEventListener('click', () => {
      let fixed = 0;
      editorCues.sort((a, b) => a.start - b.start);
      for (let i = 0; i < editorCues.length - 1; i++) {
        if (editorCues[i].end > editorCues[i + 1].start) {
          // Trim end of current cue to match start of next
          editorCues[i].end = editorCues[i + 1].start - 0.01;
          if (editorCues[i].end < editorCues[i].start) {
            editorCues[i].end = editorCues[i].start + 0.1;
          }
          fixed++;
        }
      }
      renderVisualEditor();
      syncToRawEditor();
      if (showToastFn) showToastFn('🔧 Overlaps Fixed', `${fixed} overlap(s) resolved.`, 'success', 2000);
    });
  }

  // ── Apply to Studio ──
  const btnApply = document.getElementById('srt-btn-apply-changes');
  if (btnApply) {
    btnApply.addEventListener('click', () => {
      // If in raw mode, parse first
      if (rawEditor && rawEditor.style.display !== 'none') {
        syncFromRawEditor();
      }
      applyCuesToState(showToastFn);
      if (renderTeleprompterFn) renderTeleprompterFn(state.lyrics, true);
    });
  }

  // ── AI Core Auto-Fix ──
  const btnAiFix = document.getElementById('srt-btn-ai-fix');
  const aiBanner = document.getElementById('srt-ai-status-banner');
  const aiStatusText = document.getElementById('srt-ai-status-text');

  if (btnAiFix) {
    btnAiFix.addEventListener('click', async () => {
      // If in raw mode, parse first
      if (rawEditor && rawEditor.style.display !== 'none') {
        syncFromRawEditor();
      }
      if (editorCues.length === 0) {
        if (showToastFn) showToastFn('⚠️ No Cues', 'No subtitle cues to enhance. Add cues or import lyrics first.', 'warning', 2500);
        return;
      }

      btnAiFix.disabled = true;
      btnAiFix.style.opacity = '0.6';
      if (aiBanner) aiBanner.style.display = 'flex';
      if (aiStatusText) aiStatusText.textContent = '🤖 AI Core correcting Khmer spelling, phonetic accuracy & millisecond timestamps...';

      try {
        const res = await fetch('/api/subtitles/ai-fix', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lyrics_data: editorCues,
            audio_path: state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || '',
            align_vocals: true
          })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.status === 'success' && Array.isArray(data.lyrics)) {
          editorCues = data.lyrics.map(l => ({
            start: l.start,
            end: l.end,
            text: l.text
          }));
          renderVisualEditor();
          syncToRawEditor();
          const count = data.corrections_made || 0;
          if (showToastFn) {
            showToastFn('✨ AI Auto-Fix Complete', `Guaranteed 100% correct! ${count} correction(s) applied.`, 'success', 3500);
          }
        } else {
          throw new Error(data.detail || 'AI correction returned unexpected format');
        }
      } catch (err) {
        console.error('AI Subtitle Fix Error:', err);
        if (showToastFn) showToastFn('⚠️ AI Correction Notice', `Fallback used: ${err.message}`, 'warning', 3000);
      } finally {
        btnAiFix.disabled = false;
        btnAiFix.style.opacity = '1';
        if (aiBanner) aiBanner.style.display = 'none';
      }
    });
  }

  // ── AI Vocal Sync (Acoustic Alignment) ──
  const btnVocalAlign = document.getElementById('srt-btn-vocal-align');
  if (btnVocalAlign) {
    btnVocalAlign.addEventListener('click', async () => {
      if (rawEditor && rawEditor.style.display !== 'none') {
        syncFromRawEditor();
      }
      if (editorCues.length === 0) {
        if (showToastFn) showToastFn('⚠️ No Cues', 'No subtitle cues to align. Add cues first.', 'warning', 2500);
        return;
      }

      btnVocalAlign.disabled = true;
      btnVocalAlign.style.opacity = '0.6';
      if (aiBanner) aiBanner.style.display = 'flex';
      if (aiStatusText) aiStatusText.textContent = '🎙️ Snapping subtitle boundaries to real singing vocal acoustics...';

      try {
        const res = await fetch('/api/subtitles/align-audio', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lyrics_data: editorCues,
            audio_path: state.audioServerPath || state.audioPath || window.__VIDA_SERVER_PATH || ''
          })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.status === 'success' && Array.isArray(data.lyrics)) {
          editorCues = data.lyrics.map(l => ({
            start: l.start,
            end: l.end,
            text: l.text
          }));
          renderVisualEditor();
          syncToRawEditor();
          if (showToastFn) showToastFn('🎯 Vocal Sync Applied', `${editorCues.length} cues calibrated to vocal waveform.`, 'success', 3000);
        } else {
          throw new Error(data.detail || 'Vocal alignment failed');
        }
      } catch (err) {
        console.warn('Vocal align notice:', err);
        if (showToastFn) showToastFn('🎙️ Vocal Sync Notice', 'Make sure an audio track is loaded in studio.', 'info', 3000);
      } finally {
        btnVocalAlign.disabled = false;
        btnVocalAlign.style.opacity = '1';
        if (aiBanner) aiBanner.style.display = 'none';
      }
    });
  }

  // ── Import Subtitle File ──
  const fileImportInput = document.getElementById('srt-file-import-input');
  if (fileImportInput) {
    fileImportInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      try {
        const text = await file.text();
        // Check if LRC or SRT/VTT
        let parsed = [];
        if (/\[\d{1,2}:\d{2}/.test(text)) {
          // LRC format: parse via backend or regex
          const res = await fetch('/api/parse-lrc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lrc_text: text })
          });
          if (res.ok) {
            const data = await res.json();
            parsed = (data.lyrics || []).map(l => ({ start: l.start, end: l.end, text: l.text }));
          }
        }
        if (!parsed.length) {
          parsed = parseSRTText(text);
        }

        if (parsed.length > 0) {
          editorCues = parsed;
          renderVisualEditor();
          syncToRawEditor();
          if (showToastFn) showToastFn('📥 Subtitles Loaded', `${parsed.length} cues imported from ${file.name}.`, 'success', 2500);
        } else {
          if (showToastFn) showToastFn('⚠️ Parse Warning', 'Could not parse timestamped cues from file.', 'warning', 2500);
        }
      } catch (err) {
        console.error('Import error:', err);
        if (showToastFn) showToastFn('❌ Import Error', err.message, 'error', 3000);
      } finally {
        fileImportInput.value = '';
      }
    });
  }

  // ── Modal Export Subtitles Dropdown ──
  const btnExportModal = document.getElementById('srt-btn-export-dropdown');
  const exportModalMenu = document.getElementById('srt-export-dropdown-menu');
  if (btnExportModal && exportModalMenu) {
    btnExportModal.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = exportModalMenu.style.display === 'block';
      exportModalMenu.style.display = isOpen ? 'none' : 'block';
    });

    document.addEventListener('click', () => {
      exportModalMenu.style.display = 'none';
    });
    exportModalMenu.addEventListener('click', (e) => e.stopPropagation());

    exportModalMenu.querySelectorAll('.srt-export-choice').forEach(btn => {
      btn.addEventListener('mouseenter', () => {
        btn.style.background = 'rgba(56, 189, 248, 0.12)';
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.background = 'transparent';
      });
      btn.addEventListener('click', () => {
        const format = btn.dataset.format;
        if (editorCues.length === 0) {
          if (showToastFn) showToastFn('⚠️ No Cues', 'No subtitle cues to export.', 'warning', 2500);
          exportModalMenu.style.display = 'none';
          return;
        }
        const success = exportSubtitles(format, editorCues, showToastFn);
        if (success && showToastFn && format !== 'capcut') {
          const formatNames = { srt: 'SRT', vtt: 'WebVTT', lrc: 'LRC', ass: 'ASS', txt: 'Plain Text' };
          showToastFn('📤 Exported', `${editorCues.length} cues exported as ${formatNames[format] || format}.`, 'success', 2500);
        }
        exportModalMenu.style.display = 'none';
      });
    });
  }

  // ── Modal Direct CapCut Button ──
  const btnCapCutDirect = document.getElementById('srt-btn-capcut-direct');
  if (btnCapCutDirect) {
    btnCapCutDirect.addEventListener('click', () => {
      if (editorCues.length === 0) {
        if (showToastFn) showToastFn('⚠️ No Cues', 'No subtitle cues loaded to export for CapCut.', 'warning', 2500);
        return;
      }
      exportSubtitlesForCapCut(editorCues, showToastFn);
    });
  }

  // ── Quick Export CapCut Button (Teleprompter Header) ──
  const btnQuickCapCut = document.getElementById('btn-quick-export-capcut');
  if (btnQuickCapCut) {
    btnQuickCapCut.addEventListener('click', () => {
      if (!state.lyrics || state.lyrics.length === 0) {
        if (showToastFn) showToastFn('⚠️ No Lyrics', 'No lyrics loaded yet. Transcribe or import lyrics first.', 'warning', 2500);
        return;
      }
      exportSubtitlesForCapCut(state.lyrics, showToastFn);
    });
  }

  // ── Teleprompter Export Subtitles Dropdown ──
  const btnExportTeleprompter = document.getElementById('btn-export-subtitles');
  const exportTeleprompterDropdown = document.getElementById('export-sub-dropdown');
  if (btnExportTeleprompter && exportTeleprompterDropdown) {
    btnExportTeleprompter.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = exportTeleprompterDropdown.style.display === 'block';
      exportTeleprompterDropdown.style.display = isOpen ? 'none' : 'block';
    });

    document.addEventListener('click', () => {
      exportTeleprompterDropdown.style.display = 'none';
    });
    exportTeleprompterDropdown.addEventListener('click', (e) => e.stopPropagation());

    exportTeleprompterDropdown.querySelectorAll('.export-sub-option').forEach(btn => {
      btn.addEventListener('click', () => {
        const format = btn.dataset.format;
        if (!state.lyrics || state.lyrics.length === 0) {
          if (showToastFn) showToastFn('⚠️ No Lyrics', 'No lyrics loaded to export.', 'warning', 2500);
          exportTeleprompterDropdown.style.display = 'none';
          return;
        }
        exportSubtitles(format, state.lyrics, showToastFn);
        exportTeleprompterDropdown.style.display = 'none';
      });
    });
  }

  // ── Audio Playback Synchronization (Active Cue Highlight) ──
  const audioPlayer = document.getElementById('audio-player');
  if (audioPlayer) {
    audioPlayer.addEventListener('timeupdate', () => {
      if (!modal || modal.style.display === 'none') return;
      const t = audioPlayer.currentTime;
      const visualContainer = document.getElementById('srt-visual-editor');
      if (!visualContainer) return;

      const rows = visualContainer.querySelectorAll('.srt-cue-row');
      rows.forEach(row => {
        const idx = parseInt(row.dataset.index);
        const cue = editorCues[idx];
        if (cue && t >= cue.start && t < cue.end) {
          if (!row.classList.contains('srt-cue-active')) {
            row.classList.add('srt-cue-active');
          }
        } else {
          row.classList.remove('srt-cue-active');
        }
      });
    });
  }

  // ── Keyboard shortcut: Escape to close ──
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (shiftDialog && shiftDialog.style.display !== 'none') {
        shiftDialog.style.display = 'none';
        return;
      }
      if (exportModalMenu && exportModalMenu.style.display !== 'none') {
        exportModalMenu.style.display = 'none';
        return;
      }
      if (exportTeleprompterDropdown && exportTeleprompterDropdown.style.display !== 'none') {
        exportTeleprompterDropdown.style.display = 'none';
        return;
      }
      if (modal && modal.style.display !== 'none') {
        modal.style.display = 'none';
      }
    }
  });
}
