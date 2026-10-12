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

    const { line, nextLine, activeWordIndex, wordProgress, alpha } = activeLyricState;
    if (!line || !line.text) return;

  const fullText = line.text.trim();
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

  let words = line.words || [];
  if (words.length === 0) {
    words = splitLineIntoWords(fullText, line.start, line.end);
    line.words = words;
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
    ctx.save();
    const nextFontSize = Math.max(12, Math.floor(fontSize * 0.58));
    ctx.font = `600 ${nextFontSize}px ${fontFamilies}`;
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
    ctx.shadowBlur = 8;
    const nextY = textY - paddingY - nextFontSize * 0.9;
    ctx.fillText(nextLine.text.trim(), w / 2, nextY);
    ctx.restore();
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

  ctx.restore();
  } catch (lyricErr) {
    console.error('[VIDA Lyrics Draw Error]', lyricErr);
  }
}
