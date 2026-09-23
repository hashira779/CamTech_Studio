import { state, PALETTES } from './state.js';

let activeLyricState = null;

export function getActiveLyricState() {
  return activeLyricState;
}

/**
 * Splits text into words with native Khmer language support.
 * Modern browsers support Intl.Segmenter('km') which handles unspaced Khmer script seamlessly.
 */
function splitLineIntoWords(text, lineStart, lineEnd) {
  if (!text) return [];
  const clean = text.trim();
  if (!clean) return [];

  const isKhmer = /[\u1780-\u17FF]/.test(clean);
  let tokens = [];

  if (isKhmer && typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      const segmenter = new Intl.Segmenter('km', { granularity: 'word' });
      tokens = Array.from(segmenter.segment(clean))
        .map(s => s.segment.trim())
        .filter(t => t.length > 0 && !/^[\s\p{P}]+$/u.test(t));
    } catch(e) {}
  }

  if (!tokens || tokens.length === 0) {
    tokens = clean.split(/\s+/).filter(Boolean);
  }
  if (!tokens || tokens.length === 0) {
    tokens = [clean];
  }

  const dur = Math.max(0.4, lineEnd - lineStart);
  const wDur = dur / tokens.length;

  return tokens.map((token, i) => ({
    word: token,
    start: Number((lineStart + i * wDur).toFixed(2)),
    end: Number((lineStart + (i + 1) * wDur).toFixed(2))
  }));
}

export function updateLyricState(currentTime) {
  const lyrics = state.lyrics;
  if (!lyrics || lyrics.length === 0) {
    activeLyricState = null;
    return;
  }

  const leadTime = 0.25;
  const fadeDuration = 0.35;
  let activeLine = null;
  let nextLine = null;

  for (let i = 0; i < lyrics.length; i++) {
    const line = lyrics[i];
    if (currentTime >= line.start - leadTime && currentTime <= line.end + fadeDuration) {
      activeLine = line;
      if (i + 1 < lyrics.length) nextLine = lyrics[i + 1];
      break;
    } else if (currentTime < line.start) {
      nextLine = line;
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

  // Ensure words are always populated (especially for Khmer / imported subtitles)
  if (!activeLine.words || activeLine.words.length === 0) {
    activeLine.words = splitLineIntoWords(activeLine.text, activeLine.start, activeLine.end);
  }

  const words = activeLine.words || [];
  let activeWordIndex = -1;
  let wordProgress = 0.0;

  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (currentTime >= w.start && currentTime <= w.end) {
      activeWordIndex = i;
      const dur = Math.max(0.05, w.end - w.start);
      wordProgress = (currentTime - w.start) / dur;
      break;
    } else if (currentTime > w.end) {
      activeWordIndex = i;
      wordProgress = 1.0;
    }
  }

  let alpha = 1.0;
  if (currentTime < activeLine.start) {
    alpha = Math.max(0, (currentTime - (activeLine.start - leadTime)) / leadTime);
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

export function drawLyrics(ctx, w, h) {
  if (!activeLyricState || state.showLyrics === false || state.lyricStyle === 'none') return;

  const style = state.lyricStyle || 'karaoke';
  const pal = PALETTES[state.palette] || PALETTES['cyberpunk'];

  // Handle instrumental breaks gracefully
  if (activeLyricState.isInstrumental) {
    if (!state.lyrics || state.lyrics.length === 0) return;
    const next = activeLyricState.nextLine;
    ctx.save();
    let fontSize = Math.max(13, Math.floor(h * 0.032));
    ctx.font = `600 ${fontSize}px 'Outfit', 'Inter', sans-serif`;
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

    const textY = h * 0.88;
    const textWidth = ctx.measureText(text).width + 36;

    ctx.fillStyle = 'rgba(10, 15, 25, 0.78)';
    ctx.strokeStyle = `rgba(${pal.primary.join(',')}, 0.45)`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(w / 2 - textWidth / 2, textY - fontSize * 0.9, textWidth, fontSize * 1.8, fontSize * 0.9);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.fillText(text, w / 2, textY);
    ctx.restore();
    return;
  }

  const { line, activeWordIndex, wordProgress, alpha } = activeLyricState;
  if (!line) return;

  ctx.save();
  ctx.globalAlpha = alpha;

  let fontSize = Math.floor(h * 0.052);
  const fontFamilies = "'Kantumruy Pro', 'Khmer OS Battambang', 'Leelawadee UI', 'Khmer UI', 'Battambang', 'Siemreap', 'Outfit', 'Inter', sans-serif";
  ctx.font = `700 ${fontSize}px ${fontFamilies}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  const textY = h * 0.88; // Pill box bottom

  let words = line.words || [];
  if (words.length === 0 && line.text) {
    words = splitLineIntoWords(line.text, line.start, line.end);
  }

  const isKhmer = /[\u1780-\u17FF]/.test(line.text || '');
  const spaceWidth = isKhmer ? Math.round(fontSize * 0.10) : ctx.measureText(" ").width;

  // Calculate total width of the line to center it properly
  let totalWidth = 0;
  let wordWidths = [];
  
  for (let i = 0; i < words.length; i++) {
    const width = ctx.measureText(words[i].word).width; 
    wordWidths.push(width);
    totalWidth += width + (i < words.length - 1 ? spaceWidth : 0);
  }

  // Auto-scale if text exceeds 88% of screen width
  if (totalWidth > w * 0.88) {
    const scale = (w * 0.88) / totalWidth;
    fontSize = Math.max(14, Math.floor(fontSize * scale));
    ctx.font = `700 ${fontSize}px ${fontFamilies}`;
    totalWidth = 0;
    wordWidths = [];
    for (let i = 0; i < words.length; i++) {
      const width = ctx.measureText(words[i].word).width; 
      wordWidths.push(width);
      totalWidth += width + (i < words.length - 1 ? spaceWidth : 0);
    }
  }

  let startX = Math.max(20, (w - totalWidth) / 2);
  const paddingX = fontSize * 0.65;
  const paddingY = fontSize * 0.70;

  // Render background according to style
  if (style !== 'cinematic') {
    ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
    ctx.shadowBlur = 12;
    if (style === 'pop') {
      ctx.fillStyle = 'rgba(15, 15, 25, 0.88)';
      ctx.strokeStyle = pal.highlight;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(startX - paddingX, textY - paddingY, totalWidth + paddingX * 2, paddingY * 2, paddingY);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.72)';
      ctx.beginPath();
      ctx.roundRect(startX - paddingX, textY - paddingY, totalWidth + paddingX * 2, paddingY * 2, paddingY);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
  } else {
    // Cinematic: deep text drop shadow, no pill
    ctx.shadowColor = 'rgba(0, 0, 0, 0.95)';
    ctx.shadowBlur = 12;
  }

  // Draw Words with style-specific kinetic effects
  let currentX = startX;
  for (let i = 0; i < words.length; i++) {
    const wordText = words[i].word;
    const wordW = wordWidths[i];
    const isPast = i < activeWordIndex;
    const isCurrent = i === activeWordIndex;

    ctx.save();
    let wordY = textY;

    if (style === 'bounce' && isCurrent) {
      const bounceH = Math.sin(wordProgress * Math.PI) * (fontSize * 0.28);
      wordY -= bounceH;
    }

    if (style === 'typewriter' && isCurrent) {
      const charCount = Math.max(1, Math.floor(wordText.length * wordProgress));
      const partialText = wordText.substring(0, charCount);
      ctx.fillStyle = pal.highlight;
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 10;
      ctx.fillText(partialText, currentX, wordY);
    } else if (style === 'highlight' && isCurrent) {
      ctx.fillStyle = `rgba(${pal.primary.join(',')}, 0.30)`;
      ctx.beginPath();
      ctx.roundRect(currentX - 2, wordY - fontSize * 0.65, wordW + 4, fontSize * 1.3, 4);
      ctx.fill();

      ctx.fillStyle = pal.highlight;
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 14;
      ctx.fillText(wordText, currentX, wordY);
    } else if (style === 'glow' && isCurrent) {
      ctx.fillStyle = '#ffffff';
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 16 + Math.sin(wordProgress * Math.PI) * 8;
      ctx.fillText(wordText, currentX, wordY);
    } else if (style === 'cinematic') {
      if (isPast || isCurrent) {
        ctx.fillStyle = '#ffd700'; // Gold
        ctx.shadowColor = 'rgba(255, 215, 0, 0.6)';
        ctx.shadowBlur = 10;
      } else {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
      }
      ctx.fillText(wordText, currentX, wordY);
    } else {
      // Default: Karaoke fill-sweep with left alignment
      ctx.fillStyle = 'rgba(255, 255, 255, 0.88)';
      if (isPast) {
        ctx.fillStyle = pal.highlight;
        ctx.shadowColor = pal.glow;
        ctx.shadowBlur = 8;
        ctx.fillText(wordText, currentX, wordY);
      } else if (isCurrent) {
        // Base muted word
        ctx.fillText(wordText, currentX, wordY);

        // Sweeping highlight overlay
        ctx.save();
        ctx.beginPath();
        ctx.rect(currentX, wordY - fontSize * 1.1, wordW * wordProgress, fontSize * 2.2);
        ctx.clip();
        ctx.fillStyle = pal.highlight;
        ctx.shadowColor = pal.glow;
        ctx.shadowBlur = 14;
        ctx.fillText(wordText, currentX, wordY);
        ctx.restore();
      } else {
        ctx.fillText(wordText, currentX, wordY);
      }
    }

    ctx.restore();
    currentX += wordW + spaceWidth;
  }

  ctx.restore();
}
