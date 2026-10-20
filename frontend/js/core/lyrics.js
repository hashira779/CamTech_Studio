import { state, PALETTES } from './state.js';

let activeLyricState = null;

export function getActiveLyricState() {
  return activeLyricState;
}

/**
 * Detects the dominant linguistic script for locale-aware segmentation and typography.
 */
export function detectLanguageLocale(text) {
  if (!text) return 'en';
  if (/[\u1780-\u17FF]/.test(text)) return 'km'; // Khmer
  if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return 'ja'; // Japanese (Hiragana/Katakana)
  if (/[\u4E00-\u9FFF]/.test(text)) return 'zh'; // Chinese
  if (/[\uAC00-\uD7AF\u1100-\u11FF]/.test(text)) return 'ko'; // Korean
  if (/[\u0E00-\u0E7F]/.test(text)) return 'th'; // Thai
  if (/[\u0E80-\u0EFF]/.test(text)) return 'lo'; // Lao
  if (/[\u1000-\u109F]/.test(text)) return 'my'; // Burmese
  if (/[\u0900-\u097F]/.test(text)) return 'hi'; // Hindi
  if (/[\u0600-\u06FF]/.test(text)) return 'ar'; // Arabic
  if (/[\u0400-\u04FF]/.test(text)) return 'ru'; // Russian / Cyrillic
  if (/[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i.test(text)) return 'vi'; // Vietnamese
  return 'en';
}

/**
 * Splits text into words or singing units with universal multi-language support.
 * Modern browsers support Intl.Segmenter which handles unspaced scripts (Khmer, Chinese,
 * Japanese, Thai, Lao, Burmese) and spaced scripts seamlessly according to Unicode Annex #29.
 * Preserves exact character indices in the original text for pixel-perfect unified text rendering.
 */
export function splitLineIntoWords(text, lineStart, lineEnd) {
  if (!text) return [];
  const clean = text.trim();
  if (!clean) return [];

  const locale = detectLanguageLocale(clean);
  let words = [];

  // Use native browser Intl.Segmenter for 100% Unicode standard segmentation
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      const segmenter = new Intl.Segmenter(locale, { granularity: 'word' });
      const segments = Array.from(segmenter.segment(clean));
      for (const item of segments) {
        // If punctuation follows a word, attach it cleanly to the preceding word
        if (!item.isWordLike && /^[\s\p{P}]+$/u.test(item.segment)) {
          if (words.length > 0 && !/^\s+$/.test(item.segment)) {
            words[words.length - 1].word += item.segment;
            words[words.length - 1].endIndex = item.index + item.segment.length;
          }
          continue;
        }
        words.push({
          word: item.segment,
          startIndex: item.index,
          endIndex: item.index + item.segment.length
        });
      }
    } catch(e) {
      console.warn("Intl.Segmenter fallback:", e);
    }
  }

  // Fallback for environments where Intl.Segmenter wasn't available
  if (!words || words.length === 0) {
    const rawTokens = clean.split(/\s+/).filter(Boolean);
    let curIdx = 0;
    for (const t of rawTokens) {
      const startIdx = clean.indexOf(t, curIdx);
      const endIdx = (startIdx !== -1 ? startIdx : curIdx) + t.length;
      curIdx = endIdx;
      words.push({
        word: t,
        startIndex: Math.max(0, startIdx !== -1 ? startIdx : 0),
        endIndex: endIdx
      });
    }
  }

  if (!words || words.length === 0) {
    words = [{ word: clean, startIndex: 0, endIndex: clean.length }];
  }

  // Calculate singing weights for natural musical phrasing & breath pacing
  const weights = words.map((w, idx) => {
    let syl = 1;
    if (locale === 'km') {
      const consonants = w.word.match(/(?<!\u17D2)[\u1780-\u17A2\u17A3-\u17B3]/g);
      syl = Math.max(1, consonants ? consonants.length : 1);
    } else if (locale === 'ja' || locale === 'zh') {
      syl = Math.max(1, w.word.replace(/\s+/g, '').length);
    } else {
      const vowels = w.word.match(/[aeiouyàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]+/gi);
      syl = Math.max(1, vowels ? vowels.length : 1);
    }
    // Initial melodic call / vocalization or final cadence extension
    let mult = 1.0;
    if (idx === 0 && /(?:អឺង|អឺយ|Oh|Ah|Woah|Hey)/i.test(w.word)) mult = 1.25;
    else if (idx === words.length - 1) mult = 1.30;
    return Math.max(0.5, syl * mult);
  });

  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1.0;
  const dur = Math.max(0.4, lineEnd - lineStart);
  let curT = lineStart;

  return words.map((w, i) => {
    const wDur = dur * (weights[i] / totalWeight);
    const start = Number(curT.toFixed(2));
    const end = Number((curT + wDur).toFixed(2));
    curT += wDur;
    return {
      word: w.word,
      start: start,
      end: i === words.length - 1 ? Number(lineEnd.toFixed(2)) : end,
      startIndex: w.startIndex,
      endIndex: w.endIndex
    };
  });
}

export function updateLyricState(currentTime) {
  const lyrics = state.lyrics;
  if (!lyrics || lyrics.length === 0) {
    activeLyricState = null;
    return;
  }

  const leadTime = 0.50; // At least 500ms visual lead-in for human reading preview & sing-along preparation
  const fadeDuration = 0.35;

  let activeLine = null;
  let activeLineIndex = -1;
  let nextLine = null;

  // Frame-perfect 100% vocal tracking with visual reading lead-in:
  // Visual line appears smoothly at least 0.5s before vocal onset so audience can read ahead.
  // Real-time karaoke highlight begins strictly when currentTime reaches the line's vocal start.
  for (let i = 0; i < lyrics.length; i++) {
    const cur = lyrics[i];
    const nxt = i + 1 < lyrics.length ? lyrics[i + 1] : null;
    const effectiveEnd = nxt && (nxt.start - cur.end < 0.12) ? nxt.start : cur.end;

    if (currentTime >= cur.start - leadTime && currentTime < effectiveEnd) {
      activeLine = cur;
      activeLineIndex = i;
      nextLine = nxt;
      break;
    } else if (currentTime < cur.start - leadTime) {
      nextLine = cur;
      break;
    }
  }

  if (!activeLine) {
    activeLyricState = {
      line: null,
      lineIndex: -1,
      currentTime: currentTime,
      nextLine: nextLine,
      isInstrumental: true,
      diffToNext: nextLine ? Math.max(0, nextLine.start - currentTime) : 0
    };
    return;
  }

  const cleanText = (activeLine.text || '').trim();

  // Ensure words are populated and have character index mappings to cleanText
  if (!activeLine.words || activeLine.words.length === 0) {
    activeLine.words = splitLineIntoWords(cleanText, activeLine.start, activeLine.end);
  } else if (activeLine.words.length > 0 && activeLine.words[0].startIndex === undefined) {
    let searchPos = 0;
    for (let i = 0; i < activeLine.words.length; i++) {
      const w = activeLine.words[i];
      const foundIdx = cleanText.indexOf(w.word, searchPos);
      if (foundIdx !== -1) {
        w.startIndex = foundIdx;
        w.endIndex = foundIdx + w.word.length;
        searchPos = w.endIndex;
      } else {
        w.startIndex = searchPos;
        w.endIndex = Math.min(cleanText.length, searchPos + w.word.length);
        searchPos = w.endIndex;
      }
    }
  }

  const words = activeLine.words || [];
  let activeWordIndex = -1;
  let wordProgress = 0.0;

  // Only highlight words once the vocalist actually begins singing
  if (currentTime >= activeLine.start) {
    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      if (currentTime >= w.start && currentTime <= w.end) {
        activeWordIndex = i;
        const dur = Math.max(0.04, w.end - w.start);
        wordProgress = (currentTime - w.start) / dur;
        break;
      } else if (currentTime > w.end) {
        activeWordIndex = i;
        wordProgress = 1.0;
      }
    }
  } else {
    // In pre-vocal lead-in window: text is displayed for reading, zero words highlighted yet
    activeWordIndex = -1;
    wordProgress = 0.0;
  }

  let alpha = 1.0;
  if (currentTime < activeLine.start) {
    alpha = Math.max(0.15, Math.min(1.0, (currentTime - (activeLine.start - leadTime)) / leadTime));
  } else if (currentTime > activeLine.end) {
    alpha = Math.max(0, 1.0 - (currentTime - activeLine.end) / fadeDuration);
  }

  activeLyricState = {
    line: activeLine,
    lineIndex: activeLineIndex,
    currentTime: currentTime,
    nextLine: nextLine,
    activeWordIndex: activeWordIndex,
    wordProgress: wordProgress,
    alpha: alpha,
    isInstrumental: false
  };
}

function safeRoundRect(ctx, x, y, w, h, r) {
  if (w <= 0 || h <= 0 || isNaN(x) || isNaN(y) || isNaN(w) || isNaN(h)) return;
  const radius = Math.max(0, Math.min(Math.min(w, h) / 2, r || 0));
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') {
    try {
      ctx.roundRect(x, y, w, h, radius);
      return;
    } catch (_) {}
  }
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

/**
 * Resolves the translated text for the currently active original line.
 * Mapping is strictly index-based (1:1 with state.lyrics) so the original
 * cues and their timestamps are never mutated by the translation track.
 */
export function getActiveTranslationText() {
  const tr = state.translation;
  if (!tr || tr.displayMode === 'original_only') return '';
  if (!Array.isArray(tr.lines) || tr.lines.length === 0) return '';
  if (!activeLyricState || activeLyricState.isInstrumental) return '';
  const idx = activeLyricState.lineIndex;
  if (typeof idx !== 'number' || idx < 0) return '';
  const entry = tr.lines[idx];
  if (!entry) return '';
  return (typeof entry === 'string' ? entry : (entry.text || '')).trim();
}

function translationFontStack(locale) {
  switch (locale) {
    case 'km': return "'Kantumruy Pro', 'Battambang', 'Siemreap', 'Noto Sans Khmer', 'Outfit', sans-serif";
    case 'th': return "'Noto Sans Thai', 'Sarabun', 'Outfit', sans-serif";
    case 'zh': return "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";
    case 'ja': return "'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', sans-serif";
    case 'ko': return "'Noto Sans KR', 'Malgun Gothic', sans-serif";
    case 'ar': return "'Noto Sans Arabic', 'Segoe UI', sans-serif";
    case 'hi': return "'Noto Sans Devanagari', 'Nirmala UI', sans-serif";
    case 'ru': return "'Noto Sans', 'Segoe UI', sans-serif";
    default:   return "'Outfit', 'Inter', 'Segoe UI', sans-serif";
  }
}

function wrapTranslationLines(ctx, text, maxWidth, maxLines) {
  const single = ctx.measureText(text).width;
  if (single <= maxWidth || maxLines <= 1) return [text];

  const locale = detectLanguageLocale(text);
  // Unspaced scripts (Khmer/Thai/CJK) have no reliable whitespace tokens: use Intl.Segmenter words when present.
  let tokens;
  if (locale === 'km' || locale === 'th' || locale === 'zh' || locale === 'ja') {
    if (typeof Intl !== 'undefined' && Intl.Segmenter) {
      try {
        tokens = Array.from(new Intl.Segmenter(locale, { granularity: 'word' }).segment(text)).map(s => s.segment);
      } catch (_) { tokens = null; }
    }
    if (!tokens) tokens = Array.from(text);
  } else {
    tokens = text.split(/(\s+)/).filter(t => t.length > 0);
  }

  const lines = [];
  let cur = '';
  for (const tok of tokens) {
    const candidate = cur + tok;
    if (ctx.measureText(candidate).width > maxWidth && cur.trim().length > 0) {
      lines.push(cur.trim());
      cur = tok.replace(/^\s+/, '');
      if (lines.length === maxLines - 1) {
        // Last line absorbs everything remaining so no text is ever dropped
        const restIdx = tokens.indexOf(tok);
        cur = cur + tokens.slice(restIdx + 1).join('');
        break;
      }
    } else {
      cur = candidate;
    }
  }
  if (cur.trim().length > 0) lines.push(cur.trim());
  return lines.length > 0 ? lines : [text];
}

/**
 * Draws the secondary (translated) lyric track directly below the original line.
 * Fully style-independent from the karaoke renderer: own size, colour, alignment,
 * outline, shadow and background, but it inherits the parent fade alpha so both
 * tracks appear and disappear together.
 */
export function drawTranslationLine(ctx, w, h, text, anchorY, baseFontSize) {
  const tr = state.translation;
  if (!tr) return;
  const clean = (text || '').trim();
  if (!clean) return;

  const st = tr.style || {};
  const sizeRatio = Math.max(0.25, Math.min(1.2, Number(st.sizeRatio) || 0.55));
  const offsetRatio = Math.max(0.0, Math.min(3.0, Number(st.offsetRatio)));
  const color = st.color || '#ffffff';
  const align = st.align || 'center';

  ctx.save();

  let trSize = Math.max(11, Math.floor(baseFontSize * sizeRatio));
  const locale = detectLanguageLocale(clean);
  const families = translationFontStack(locale);
  ctx.font = `600 ${trSize}px ${families}`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = align === 'left' ? 'left' : (align === 'right' ? 'right' : 'center');

  const maxWidth = w * 0.92;
  // Progressive shrink for very long translations, then wrap into at most 2 lines
  if (ctx.measureText(clean).width > maxWidth) {
    const shrink = maxWidth / ctx.measureText(clean).width;
    const minSize = Math.max(11, Math.floor(baseFontSize * Math.min(0.40, sizeRatio * 0.72)));
    trSize = Math.max(minSize, Math.floor(trSize * shrink));
    ctx.font = `600 ${trSize}px ${families}`;
  }
  const lines = wrapTranslationLines(ctx, clean, maxWidth, 2);

  const padX = trSize * 0.55;
  const padY = trSize * 0.38;
  const lineHeight = trSize * 1.30;
  const topY = anchorY + trSize * (0.42 + offsetRatio);
  let ax;
  if (align === 'left') ax = Math.max(24, w * 0.04);
  else if (align === 'right') ax = w - Math.max(24, w * 0.04);
  else ax = w / 2;

  // Optional glass background covering every wrapped line
  if (st.background) {
    let widest = 0;
    for (const l of lines) widest = Math.max(widest, ctx.measureText(l).width);
    const boxW = widest + padX * 2;
    const boxH = lines.length * lineHeight + padY * 2;
    let bx;
    if (align === 'left') bx = ax - padX;
    else if (align === 'right') bx = ax - boxW + padX;
    else bx = w / 2 - boxW / 2;
    const by = topY - padY;
    ctx.save();
    ctx.fillStyle = 'rgba(8, 12, 22, 0.78)';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
    ctx.lineWidth = 1;
    safeRoundRect(ctx, bx, by, boxW, boxH, Math.min(padY + 4, boxH / 2));
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  for (let i = 0; i < lines.length; i++) {
    const ly = topY + i * lineHeight;
    if (st.shadow) {
      ctx.shadowColor = 'rgba(0, 0, 0, 0.85)';
      ctx.shadowBlur = Math.max(4, trSize * 0.42);
      ctx.shadowOffsetY = Math.max(1, trSize * 0.06);
    } else {
      ctx.shadowBlur = 0;
      ctx.shadowOffsetY = 0;
    }
    if (st.outline) {
      ctx.lineJoin = 'round';
      ctx.miterLimit = 2;
      ctx.lineWidth = Math.max(1.5, trSize * 0.14);
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.92)';
      ctx.strokeText(lines[i], ax, ly);
    }
    ctx.fillStyle = color;
    ctx.fillText(lines[i], ax, ly);
  }

  ctx.restore();
}

export function drawLyrics(ctx, w, h) {
  if (!activeLyricState || state.showLyrics === false || state.lyricStyle === 'none') return;

  try {
    const style = state.lyricStyle || 'karaoke';
    const pal = PALETTES[state.palette] || PALETTES['cyberpunk'];
    const primaryRGB = (pal && Array.isArray(pal.primary)) ? pal.primary.join(',') : '0,240,255';

    // Handle instrumental breaks gracefully with glassmorphism
    if (activeLyricState.isInstrumental) {
      if (!state.lyrics || state.lyrics.length === 0) return;
      // Only show instrumental indicator for real musical breaks (>= 3.5s), not short breath pauses
      if (activeLyricState.diffToNext > 0 && activeLyricState.diffToNext < 3.5) return;

      const next = activeLyricState.nextLine;
      ctx.save();
      let fontSize = Math.max(13, Math.floor(h * 0.030));
      ctx.font = `600 ${fontSize}px 'Outfit', 'Inter', 'Kantumruy Pro', sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      let text = "♪ Instrumental Break ♪";
      if (next && activeLyricState.diffToNext > 0) {
        const s = Math.ceil(activeLyricState.diffToNext);
        if (s <= 60) {
          text = `♪ Instrumental Break (Next vocal in ${s}s) ♪`;
        } else {
          const m = Math.floor(next.start / 60);
          const sec = Math.floor(next.start % 60).toString().padStart(2, '0');
          text = `♪ Instrumental Break (Next vocal at ${m}:${sec}) ♪`;
        }
      } else if (!next) {
        text = "♪ Instrumental Outro ♪";
      }

      const textY = h * 0.86;
      const textWidth = ctx.measureText(text).width + 44;
      const padY = fontSize * 0.85;

      // Premium glassmorphic badge
      const grad = ctx.createLinearGradient(0, textY - padY, 0, textY + padY);
      grad.addColorStop(0, 'rgba(15, 23, 42, 0.85)');
      grad.addColorStop(1, 'rgba(6, 9, 18, 0.92)');
      ctx.fillStyle = grad;
      ctx.strokeStyle = `rgba(${primaryRGB}, 0.50)`;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = `rgba(${primaryRGB}, 0.35)`;
      ctx.shadowBlur = 16;
      safeRoundRect(ctx, w / 2 - textWidth / 2, textY - padY, textWidth, padY * 2, padY);
      ctx.fill();
      ctx.stroke();

      ctx.shadowBlur = 0;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
      ctx.fillText(text, w / 2, textY);
      ctx.restore();
      return;
    }

    const { line, nextLine, alpha } = activeLyricState;
    let activeWordIndex = activeLyricState.activeWordIndex;
    let wordProgress = activeLyricState.wordProgress;
    if (!line || !line.text) return;

  // ============ Lyrics Display Mode (original | translation | both) ============
  // Resolved once per frame. The original cue list is only ever READ here — switching
  // modes never mutates state.lyrics, word timings, or the original SRT on disk.
  const trCfg = state.translation || {};
  const trMode = trCfg.displayMode || (trCfg.visible === false ? 'original_only' : 'bilingual');
  const trLines = Array.isArray(trCfg.lines) ? trCfg.lines : [];
  const trIdx = typeof activeLyricState.lineIndex === 'number' ? activeLyricState.lineIndex : -1;
  const trEntry = trIdx >= 0 ? trLines[trIdx] : null;
  const trText = ((typeof trEntry === 'string' ? trEntry : (trEntry && trEntry.text)) || '').trim();
  const hasTranslation = trText.length > 0 && trMode !== 'original_only';
  // Missing translated lines fall back to the original so the stage is never blank mid-song
  const translationOnly = trMode === 'translation_only' && hasTranslation;
  const showBelow = trMode === 'bilingual' && hasTranslation && trCfg.visible !== false;

  const fullText = (translationOnly ? trText : line.text).trim();
  if (!fullText) return;

  ctx.save();
  ctx.globalAlpha = alpha;

  const isKhmer = /[\u1780-\u17FF]/.test(fullText);
  let fontSize = Math.floor(h * 0.054);

  // Khmer-first typography stack for breathtaking rendering
  const fontFamilies = isKhmer
    ? "'Kantumruy Pro', 'Battambang', 'Siemreap', 'Noto Sans Khmer', 'Outfit', 'Inter', sans-serif"
    : "'Outfit', 'Inter', 'Noto Sans SC', 'Noto Sans JP', 'Noto Sans KR', 'Segoe UI', sans-serif";

  ctx.font = `700 ${fontSize}px ${fontFamilies}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  const textY = h * 0.85;

  let words = [];
  if (translationOnly) {
    // Word-level karaoke timing for the translated line, spread across the ORIGINAL line's
    // vocal window (line.start → line.end) so it stays locked to the singer. Cached on the
    // translation entry only — the original line object is never modified.
    if (trEntry && typeof trEntry === 'object') {
      if (!trEntry.words || trEntry.wordsSrc !== trText) {
        trEntry.words = splitLineIntoWords(trText, line.start, line.end);
        trEntry.wordsSrc = trText;
      }
      words = trEntry.words;
    } else {
      words = splitLineIntoWords(trText, line.start, line.end);
    }
    const tNow = typeof activeLyricState.currentTime === 'number' ? activeLyricState.currentTime : line.start;
    let wIdx = -1, wProg = 0;
    if (tNow >= line.start) {
      for (let i = 0; i < words.length; i++) {
        const w = words[i];
        if (tNow >= w.start && tNow <= w.end) {
          wIdx = i;
          wProg = (tNow - w.start) / Math.max(0.04, w.end - w.start);
          break;
        } else if (tNow > w.end) {
          wIdx = i;
          wProg = 1.0;
        }
      }
    }
    activeWordIndex = wIdx;
    wordProgress = Math.max(0, Math.min(1, wProg));
  } else {
    words = line.words || [];
    if (words.length === 0) {
      words = splitLineIntoWords(fullText, line.start, line.end);
      line.words = words;
    }
  }

  // Measure total width of the authentic, unbroken text string
  let totalWidth = ctx.measureText(fullText).width;

  // Auto-scale font size if text exceeds 86% of screen width
  if (totalWidth > w * 0.86) {
    const scale = (w * 0.86) / totalWidth;
    fontSize = Math.max(15, Math.floor(fontSize * scale));
    ctx.font = `700 ${fontSize}px ${fontFamilies}`;
    totalWidth = ctx.measureText(fullText).width;
  }

  const startX = Math.max(24, (w - totalWidth) / 2);
  const paddingX = fontSize * 0.80;
  const paddingY = fontSize * 0.72;

  // ============ Render Glassmorphism Container ============
  if (style !== 'cinematic') {
    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.85)';
    ctx.shadowBlur = 24;
    ctx.shadowOffsetY = 6;

    // Multi-stop glass gradient
    const pillGrad = ctx.createLinearGradient(0, textY - paddingY, 0, textY + paddingY);
    pillGrad.addColorStop(0, 'rgba(15, 23, 42, 0.88)');
    pillGrad.addColorStop(1, 'rgba(5, 8, 16, 0.94)');
    ctx.fillStyle = pillGrad;

    const cornerRadius = paddingY;
    safeRoundRect(ctx, startX - paddingX, textY - paddingY, totalWidth + paddingX * 2, paddingY * 2, cornerRadius);
    ctx.fill();

    // Luminescent neon border with palette color
    ctx.strokeStyle = `rgba(${primaryRGB}, 0.45)`;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Specular top highlight sheen
    safeRoundRect(ctx, startX - paddingX + 2, textY - paddingY + 1, Math.max(0, totalWidth + paddingX * 2 - 4), paddingY * 0.65, Math.max(0, cornerRadius - 1));
    ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.fill();

    ctx.restore();
  } else {
    // Cinematic style: deep drop shadow
    ctx.shadowColor = 'rgba(0, 0, 0, 0.95)';
    ctx.shadowBlur = 14;
    ctx.shadowOffsetY = 3;
  }

  // ============ Draw Next Line Preview (Floating Above) ============
  if (nextLine && nextLine.text && (!line || nextLine.start - line.end <= 6.0)) {
    let nextPreviewText = nextLine.text.trim();
    if (translationOnly) {
      const nextEntry = trIdx + 1 >= 0 ? trLines[trIdx + 1] : null;
      const nextTr = ((typeof nextEntry === 'string' ? nextEntry : (nextEntry && nextEntry.text)) || '').trim();
      if (nextTr) nextPreviewText = nextTr;
    }
    if (nextPreviewText) {
      ctx.save();
      const nextFontSize = Math.max(12, Math.floor(fontSize * 0.58));
      const nextFamilies = /[\u1780-\u17FF]/.test(nextPreviewText)
        ? "'Kantumruy Pro', 'Battambang', 'Siemreap', 'Noto Sans Khmer', 'Outfit', 'Inter', sans-serif"
        : fontFamilies;
      ctx.font = `600 ${nextFontSize}px ${nextFamilies}`;
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
      ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
      ctx.shadowBlur = 8;
      const nextY = textY - paddingY - nextFontSize * 0.9;
      ctx.fillText(nextPreviewText, w / 2, nextY);
      ctx.restore();
    }
  }

  // ============ Compute Active Word Coordinates ============
  let currentSweepX = startX;
  let activeWordBox = null;

  if (words.length > 0) {
    if (activeWordIndex >= 0 && activeWordIndex < words.length) {
      const curW = words[activeWordIndex];
      const sIdx = curW.startIndex !== undefined ? curW.startIndex : 0;
      const eIdx = curW.endIndex !== undefined ? curW.endIndex : fullText.length;
      const x0 = startX + ctx.measureText(fullText.substring(0, sIdx)).width;
      const x1 = startX + ctx.measureText(fullText.substring(0, eIdx)).width;
      const p = Math.max(0, Math.min(1, wordProgress));
      currentSweepX = x0 + (x1 - x0) * p;
      activeWordBox = { x0, x1, width: x1 - x0, wordText: curW.word, p };
    } else if (activeWordIndex >= words.length) {
      currentSweepX = startX + totalWidth;
    }
  }

  // ============ Draw Base Lyrics Text (Unhighlighted) ============
  ctx.save();
  ctx.fillStyle = style === 'cinematic' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(255, 255, 255, 0.72)';
  ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
  ctx.shadowBlur = 6;
  ctx.fillText(fullText, startX, textY);
  ctx.restore();

  // ============ Render Kinetic Animations per Style ============
  if (style === 'highlight' && activeWordBox) {
    // Glowing capsule pill around active word
    ctx.save();
    ctx.fillStyle = `rgba(${primaryRGB}, 0.38)`;
    safeRoundRect(ctx, activeWordBox.x0 - 5, textY - fontSize * 0.68, Math.max(0, activeWordBox.width + 10), fontSize * 1.36, 6);
    ctx.fill();

    // Highlight text of active word
    ctx.beginPath();
    ctx.rect(activeWordBox.x0 - 6, textY - fontSize * 1.5, Math.max(0, activeWordBox.width + 12), fontSize * 3.0);
    ctx.clip();
    ctx.fillStyle = pal.highlight;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 18;
    ctx.fillText(fullText, startX, textY);
    ctx.restore();
  } else if (style === 'glow' && activeWordBox) {
    // Neon bloom pulse on active word
    ctx.save();
    ctx.beginPath();
    ctx.rect(activeWordBox.x0 - 2, textY - fontSize * 1.5, Math.max(0, activeWordBox.width + 4), fontSize * 3.0);
    ctx.clip();
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 20 + Math.sin(activeWordBox.p * Math.PI) * 12;
    ctx.fillText(fullText, startX, textY);
    ctx.restore();
  } else if (style === 'bounce' && activeWordBox) {
    // Kinetic vertical scale bounce on active word
    const bounceH = Math.sin(activeWordBox.p * Math.PI) * (fontSize * 0.28);
    ctx.save();
    ctx.fillStyle = pal.highlight;
    ctx.shadowColor = pal.glow;
    ctx.shadowBlur = 16;
    ctx.fillText(activeWordBox.wordText, activeWordBox.x0, textY - bounceH);
    ctx.restore();
  } else if (style === 'cinematic') {
    // Cinematic gold progressive reveal
    if (currentSweepX > startX) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(startX - 20, textY - fontSize * 1.5, (currentSweepX - startX) + 20, fontSize * 3.0);
      ctx.clip();
      ctx.fillStyle = '#ffd700'; // Pure polished gold
      ctx.shadowColor = 'rgba(255, 215, 0, 0.75)';
      ctx.shadowBlur = 16;
      ctx.fillText(fullText, startX, textY);
      ctx.restore();
    }
  } else {
    // Default & Typewriter: Continuous progressive karaoke sweep with luminous beam
    if (currentSweepX > startX) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(startX - 20, textY - fontSize * 1.5, (currentSweepX - startX) + 20, fontSize * 3.0);
      ctx.clip();

      // Glowing primary karaoke color
      ctx.fillStyle = pal.highlight;
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 18;
      ctx.fillText(fullText, startX, textY);

      // Top specular sheen
      ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
      ctx.shadowBlur = 4;
      ctx.fillText(fullText, startX, textY);
      ctx.restore();

      // Brilliant leading edge light ray / glowing beam
      if (currentSweepX < startX + totalWidth) {
        ctx.save();
        const beamGrad = ctx.createLinearGradient(0, textY - fontSize * 0.65, 0, textY + fontSize * 0.65);
        beamGrad.addColorStop(0, 'rgba(255, 255, 255, 0)');
        beamGrad.addColorStop(0.5, pal.highlight);
        beamGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = beamGrad;
        ctx.shadowColor = pal.glow;
        ctx.shadowBlur = 14;
        ctx.fillRect(currentSweepX - 1.5, textY - fontSize * 0.65, 3, fontSize * 1.3);
        ctx.restore();
      }
    }
  }

  // ============ Second Track: Translated Line (rendered below the original) ============
  // Only in "Original + Translation" mode. Index-mapped 1:1 to the original cue list;
  // original lyrics, timings and SRT files are never touched.
  if (showBelow) {
    drawTranslationLine(ctx, w, h, trText, textY + paddingY, fontSize);
  }

  ctx.restore();
  } catch (lyricErr) {
    console.error('[VIDA Lyrics Draw Error]', lyricErr);
  }
}
