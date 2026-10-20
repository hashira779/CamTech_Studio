/**
 * Translation Track controller — the second (translated) lyric line.
 *
 * Design guarantees:
 *  - state.lyrics (original cues + word timings) is ONLY ever read, never mutated.
 *  - The translated track lives in state.translation.lines, mapped 1:1 by line index,
 *    and is persisted as a SEPARATE companion file "<song>.<lang>-tr.srt" (the "-tr" tag
 *    keeps it out of original-subtitle discovery).
 *  - Three display modes: original_only (default) | translation_only | bilingual.
 *    The chosen mode is stored with the project session and restored on reopen.
 */
import { state } from './state.js';
import { downloadFile, generateSRT } from './srt_editor.js';

const LANG_NAMES = {
  km: 'Khmer', en: 'English', th: 'Thai', vi: 'Vietnamese', zh: 'Chinese',
  ja: 'Japanese', ko: 'Korean', fr: 'French', es: 'Spanish'
};
const KHMER_RE = /[ក-៿]/;
const MODE_LABELS = {
  original_only: 'Original only',
  translation_only: 'Translation only',
  bilingual: 'Original + Translation'
};
const SESSION_KEY = 'vida_project_session';
/** Songs whose Khmer track was already built automatically — never re-bill the API on reload. */
const AUTO_BUILT_KEY = 'vida_auto_khmer_built';

let toast = () => {};
let modalEl = null;
let draftLines = [];
let autoBuildInFlight = false;
let sessionModeAppliedKey = '';

function fmtTime(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r < 10 ? '0' : ''}${r.toFixed(2)}`;
}

function getAudioKey() {
  return state.audioServerPath || state.audioPath || state.audioUrl || '';
}

function targetLangName() {
  const code = (state.translation.lang || 'en').toLowerCase();
  return LANG_NAMES[code] || 'English';
}

/** Fraction of the loaded ORIGINAL lyric lines written in Khmer script (0..1). */
export function khmerSourceRatio() {
  const lyrics = state.lyrics || [];
  let seen = 0, khmer = 0;
  for (const l of lyrics) {
    const t = String((l && l.text) || '').trim();
    if (!t) continue;
    seen++;
    if (KHMER_RE.test(t)) khmer++;
    if (seen >= 20) break;
  }
  return seen ? khmer / seen : 0;
}

/** True when the loaded ORIGINAL lyrics are already Khmer script — then Khmer is not a target. */
export function sourceIsKhmer() {
  return khmerSourceRatio() >= 0.5;
}

/** True when the song is singable but in a foreign language, so Khmer is the useful second track. */
export function sourceIsForeign() {
  const lyrics = state.lyrics || [];
  let seen = 0;
  for (const l of lyrics) {
    if (String((l && l.text) || '').trim()) seen++;
    if (seen >= 20) break;
  }
  return seen >= 3 && khmerSourceRatio() < 0.5;
}

/** User preference: build the Khmer second track automatically for foreign-language songs. */
export function autoKhmerEnabled() {
  return state.translation.autoTranslate !== false;
}

export function setAutoKhmer(on) {
  state.translation.autoTranslate = !!on;
  saveProjectSession();
}

function autoBuiltMarks() {
  try {
    const raw = localStorage.getItem(AUTO_BUILT_KEY);
    const obj = raw ? JSON.parse(raw) : null;
    return obj && typeof obj === 'object' ? obj : {};
  } catch (_) { return {}; }
}

function isAutoBuilt(key) {
  return !!key && autoBuiltMarks()[key] === true;
}

/** Claiming the mark BEFORE translating is what stops a double-fire across reloads. */
function markAutoBuilt(key, claimed) {
  if (!key) return;
  const marks = autoBuiltMarks();
  if (claimed) marks[key] = true; else delete marks[key];
  try { localStorage.setItem(AUTO_BUILT_KEY, JSON.stringify(marks)); } catch (_) {}
}

/** 1:1 translated line entries built from the ORIGINAL cue timings. */
function buildLines(texts) {
  const lyrics = state.lyrics || [];
  const out = [];
  for (let i = 0; i < lyrics.length; i++) {
    const l = lyrics[i] || {};
    out.push({
      index: i,
      text: String((texts && texts[i]) || '').trim(),
      start: Number(l.start) || 0,
      end: Number(l.end) || 0
    });
  }
  return out;
}

/**
 * A translated track only belongs to the song + language it was made for. Storing who owns the
 * current lines lets us drop them the moment either changes, so the previous song's translation
 * can never be drawn as the second line of the song you just loaded.
 */
function trackOwner() {
  return `${getAudioKey()}::${state.translation.lang || 'en'}`;
}

function setTrackOwner() {
  state.translation.ownerKey = trackOwner();
}

/** Drops a track that belongs to another song/language before anything else reads it. */
function dropStaleTrack() {
  const hadLines = (state.translation.lines || []).some(l => l && String(l.text || '').trim());
  const stale = state.translation.ownerKey !== undefined && state.translation.ownerKey !== trackOwner();
  if (stale) {
    state.translation.lines = [];
    state.translation.loaded = false;
  }
  return stale && hadLines;
}

/** Translated cues (original timestamps) for SRT export / server rendering. */
export function getTranslationCues() {
  return (state.translation.lines || [])
    .filter(l => l && String(l.text || '').trim())
    .map(l => ({ line_id: l.index, start: Number(l.start) || 0, end: Number(l.end) || 0, text: String(l.text).trim() }));
}

function translationCount() {
  return (state.translation.lines || []).filter(l => String(l.text || '').trim()).length;
}

/** Does the translated track line up with the currently loaded lyrics? */
export function hasValidTranslation() {
  const total = (state.lyrics || []).length;
  if (!total) return false;
  const lines = state.translation.lines || [];
  if (!lines.length) return false;
  let filled = 0;
  for (let i = 0; i < total; i++) if (lines[i] && String(lines[i].text || '').trim()) filled++;
  return filled >= Math.max(1, Math.floor(total * 0.5));
}

// ============ Project session persistence (display mode + track style) ============
export function saveProjectSession() {
  try {
    const payload = {
      audioKey: getAudioKey(),
      displayMode: state.translation.displayMode,
      lang: state.translation.lang,
      visible: state.translation.visible,
      autoTranslate: autoKhmerEnabled(),
      style: state.translation.style,
      savedAt: Date.now()
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
    // Whatever we just stored IS the current choice, so a later reconcile must not re-apply an old one
    sessionModeAppliedKey = getAudioKey();
  } catch (_) {}
}

function restoreProjectSession() {
  let raw = null;
  try { raw = localStorage.getItem(SESSION_KEY); } catch (_) { return null; }
  if (!raw) return null;
  let data = null;
  try { data = JSON.parse(raw); } catch (_) { return null; }
  if (!data || typeof data !== 'object') return null;
  // A session from a different song keeps only the style, never the mode of another track
  const sameSong = data.audioKey && data.audioKey === getAudioKey();
  if (data.style && typeof data.style === 'object') {
    state.translation.style = { ...state.translation.style, ...data.style };
  }
  // Auto-Khmer is a workspace preference, so it survives switching songs
  if (typeof data.autoTranslate === 'boolean') state.translation.autoTranslate = data.autoTranslate;
  if (sameSong) {
    if (data.lang) state.translation.lang = data.lang;
    if (typeof data.visible === 'boolean') state.translation.visible = data.visible;
    if (MODE_LABELS[data.displayMode]) state.translation.displayMode = data.displayMode;
  }
  return data;
}

function notifyTranslationChanged() {
  try { window.dispatchEvent(new CustomEvent('vida:translation-changed')); } catch (_) {}
}

// ============ Display mode ============
export function setDisplayMode(mode, notify = true) {
  const valid = ['original_only', 'translation_only', 'bilingual'];
  if (!valid.includes(mode)) return false;
  if (mode !== 'original_only' && !hasValidTranslation()) {
    toast('⚠️ No Translation Yet', `Mode "${MODE_LABELS[mode]}" needs translated lines first — click 🌐 Translate or ✏️ Edit Translation. Original lyrics are still shown.`, 'warning', 5000);
    state.translation.displayMode = 'original_only';
    syncUI();
    saveProjectSession();
    return false;
  }
  state.translation.displayMode = mode;
  state.translation.visible = mode !== 'original_only';
  syncUI();
  saveProjectSession();
  notifyTranslationChanged();
  if (notify) {
    const note = mode === 'original_only'
      ? 'Original lyrics only — the existing SRT is untouched.'
      : (mode === 'translation_only'
        ? 'Translated line only, locked to the original SRT timings.'
        : 'Original on line 1, translation directly below.');
    toast('🎬 Display Mode', `${MODE_LABELS[mode]} — ${note}`, 'success', 3200);
  }
  return true;
}

export function getDisplayMode() {
  return state.translation.displayMode || 'original_only';
}

// ============ UI sync ============
function syncUI() {
  const mode = getDisplayMode();
  const group = document.getElementById('translation-mode-group');
  if (group) {
    group.querySelectorAll('.trans-mode-btn').forEach(btn => {
      const m = btn.dataset.mode;
      const active = m === mode;
      btn.classList.toggle('is-active', active);
      const needsTrack = m !== 'original_only';
      btn.classList.toggle('is-disabled', needsTrack && !hasValidTranslation());
    });
  }

  // Status chip: paint with variant classes only — no inline colours.
  const badge = document.getElementById('translation-status-badge');
  if (badge) {
    const n = translationCount();
    badge.textContent = n > 0 ? `${MODE_LABELS[mode]} · ${n} translated` : 'No translation';
    badge.classList.toggle('ui-chip--info', n > 0);
  }

  const langSel = document.getElementById('select-translation-lang');
  if (langSel) {
    const kmOpt = langSel.querySelector('option[value="km"]');
    if (kmOpt) {
      const srcKm = sourceIsKhmer();
      kmOpt.disabled = srcKm;
      kmOpt.title = srcKm
        ? 'The original lyrics are already Khmer — pick a language to translate INTO'
        : 'Translate the lyrics into Khmer (saved as <song>.km-tr.srt, original files untouched)';
      if (srcKm && state.translation.lang === 'km') state.translation.lang = 'en';
    }
    if (langSel.value !== state.translation.lang) langSel.value = state.translation.lang;
  }

  const st = state.translation.style || {};
  const size = document.getElementById('range-trans-size');
  const offset = document.getElementById('range-trans-offset');
  const color = document.getElementById('color-trans');
  const align = document.getElementById('select-trans-align');
  const outline = document.getElementById('check-trans-outline');
  const shadow = document.getElementById('check-trans-shadow');
  const bg = document.getElementById('check-trans-background');
  if (size) size.value = String(Math.round((st.sizeRatio ?? 0.55) * 100));
  if (offset) offset.value = String(Math.round((st.offsetRatio ?? 0.55) * 100));
  if (color) color.value = st.color || '#ffffff';
  if (align) align.value = st.align || 'center';
  if (outline) outline.checked = st.outline !== false;
  if (shadow) shadow.checked = st.shadow !== false;
  if (bg) bg.checked = !!st.background;
}

// ============ Network helpers ============
async function postJSON(url, body, timeoutMs = 120000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function translateViaAI(texts) {
  const data = await postJSON('/api/lyrics/translate-lines', {
    lines: texts,
    target_lang: targetLangName()
  }, 180000);
  if (data.status !== 'success' || !Array.isArray(data.lines)) {
    throw new Error(data.detail || 'Translation service returned no lines');
  }
  return data.lines;
}

async function persistTranslation() {
  const cues = getTranslationCues();
  if (!cues.length) return null;
  // Preserve 1:1 index mapping on disk: send the full line list in original order
  const lines = (state.translation.lines || []).map(l => String(l.text || '').trim());
  return await postJSON('/api/lyrics/translation/save', {
    audio_path: getAudioKey(),
    lang: state.translation.lang,
    lines,
    lyrics_data: (state.lyrics || []).map(l => ({ start: l.start, end: l.end, text: l.text }))
  }, 30000);
}

/** Reconciles stored SRT text back onto original indices by timestamp (gap-safe). */
function mapCuesOntoLyrics(cues) {
  const lyrics = state.lyrics || [];
  const texts = new Array(lyrics.length).fill('');
  const used = new Set();
  for (let i = 0; i < lyrics.length; i++) {
    const t0 = Number(lyrics[i].start) || 0;
    const hit = cues.find((c, ci) => !used.has(ci) && Math.abs((Number(c.start) || 0) - t0) < 0.06);
    if (hit) {
      used.add(cues.indexOf(hit));
      texts[i] = String(hit.text || '').trim();
    }
  }
  // Fallback: if almost nothing matched by time, assume the file is in original order
  if (texts.every(t => !t) && cues.length) {
    cues.slice(0, lyrics.length).forEach((c, i) => { texts[i] = String(c.text || '').trim(); });
  }
  return texts;
}

// ============ Load a saved track for the current song ============

/** Explicit saved session for the song that is loaded right now (null = belongs to another song). */
function sessionForCurrentSong() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    const d = raw ? JSON.parse(raw) : null;
    if (d && typeof d === 'object' && d.audioKey && d.audioKey === getAudioKey()) return d;
  } catch (_) {}
  return null;
}

/** Explicit target language saved for the song that is loaded right now (null = never chosen). */
function sessionLangForCurrentSong() {
  const d = sessionForCurrentSong();
  return d && d.lang ? String(d.lang) : null;
}

/** Khmer should be the automatic second track: user opted in and the song is not Khmer. */
export function wantsAutoKhmer() {
  return autoKhmerEnabled() && !sourceIsKhmer() && sourceIsForeign();
}

/**
 * The saved display mode is re-applied once per song, here rather than only at boot, because on
 * reopen the audio key is usually not known until after initTranslationTrack() has read the
 * session. Applies at most the first time each song is reconciled, so later manual clicks stick.
 */
function applySavedModeForSong(key) {
  if (sessionModeAppliedKey === key) return;
  sessionModeAppliedKey = key;
  const d = sessionForCurrentSong();
  if (!d || !MODE_LABELS[d.displayMode]) return;
  if (d.displayMode !== 'original_only' && translationCount() === 0) return;
  state.translation.displayMode = d.displayMode;
  state.translation.visible = typeof d.visible === 'boolean' ? d.visible : d.displayMode !== 'original_only';
}

export async function loadTranslationForSong() {
  const key = getAudioKey();
  if (!key || !(state.lyrics || []).length) return false;
  try {
    const droppedStale = dropStaleTrack();
    if (droppedStale) {
      syncUI();
      // Repaint before the network round-trip so the previous song/language sublines
      // disappear immediately instead of lingering while the new track loads.
      notifyTranslationChanged();
    }
    const listRes = await fetch(`/api/lyrics/translation/list?audio_path=${encodeURIComponent(key)}`);
    const list = await listRes.json().catch(() => ({}));
    const langs = Array.isArray(list.langs) ? list.langs : [];
    const autoKm = wantsAutoKhmer();
    const sessLang = sessionLangForCurrentSong();

    // An explicit choice saved for this song always wins; otherwise a foreign song targets Khmer.
    let lang = null;
    if (sessLang && langs.includes(sessLang)) lang = sessLang;
    else if (autoKm) lang = 'km';
    else if (langs.includes(state.translation.lang)) lang = state.translation.lang;
    else if (langs.length) lang = langs[0];

    if (lang) {
      if (lang !== state.translation.lang) { state.translation.lang = lang; dropStaleTrack(); }
      else state.translation.lang = lang;
      if (langs.includes(lang)) {
        const res = await fetch(`/api/lyrics/translation?audio_path=${encodeURIComponent(key)}&lang=${encodeURIComponent(lang)}`);
        const data = await res.json().catch(() => ({}));
        const cues = Array.isArray(data.cues) ? data.cues : null;
        const rawLines = Array.isArray(data.lines) ? data.lines : [];
        if (cues && cues.length) state.translation.lines = buildLines(mapCuesOntoLyrics(cues));
        else if (rawLines.length) state.translation.lines = buildLines(rawLines);
        setTrackOwner();
      }
    }
    state.translation.loaded = translationCount() > 0;
    applySavedModeForSong(key);
    syncUI();
    // Redraw the teleprompter so it shows the track that was just loaded — or drops the
    // previous song's sublines when this song has no translation.
    if (state.translation.loaded || droppedStale) notifyTranslationChanged();

    if (state.translation.loaded) {
      // A Khmer track already on disk means the work is done — mark it so we never re-translate.
      if (autoKm && state.translation.lang === 'km') markAutoBuilt(key, true);
      return true;
    }
    if (autoKm && !isAutoBuilt(key)) return await autoBuildKhmerTrack(key);
    return false;
  } catch (e) {
    console.warn('[VIDA Translation] load failed:', e);
    return false;
  }
}

/**
 * Builds the Khmer track once per foreign-language song. The marker is claimed BEFORE the API
 * call, so a crash or reload mid-run cannot bill twice; a clean failure releases it.
 */
async function autoBuildKhmerTrack(key) {
  if (autoBuildInFlight || !key || !wantsAutoKhmer() || isAutoBuilt(key)) return false;
  autoBuildInFlight = true;
  markAutoBuilt(key, true);
  const prevLang = state.translation.lang;
  state.translation.lang = 'km';
  const sel = document.getElementById('select-translation-lang');
  if (sel) sel.value = 'km';
  syncUI();
  toast('🇰🇭 Auto Khmer track',
    `Foreign lyrics detected — building the Khmer second line (${(state.lyrics || []).length} cues). Original lyrics, timings and SRT are untouched.`,
    'info', 4200);
  try {
    const ok = await translateAll(null, { preferBilingual: true });
    if (!ok) {
      markAutoBuilt(key, false);
      state.translation.lang = prevLang;
      return false;
    }
    return true;
  } catch (e) {
    console.warn('[VIDA Translation] auto Khmer build failed:', e);
    markAutoBuilt(key, false);
    state.translation.lang = prevLang;
    return false;
  } finally {
    autoBuildInFlight = false;
    syncUI();
    saveProjectSession();
  }
}

// ============ Actions ============
/** Translates the loaded lines into the current target language. Resolves true only on success. */
async function translateAll(btn, opts = {}) {
  if (!(state.lyrics || []).length) {
    toast('⚠️ No Lyrics', 'Load or sync lyrics first — the translation maps 1:1 onto the original lines.', 'warning', 3500);
    return false;
  }
  const langAtStart = state.translation.lang;
  const prevMode = state.translation.displayMode;
  const texts = (state.lyrics || []).map(l => (l.text || '').trim());
  const label = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Translating…'; }
  try {
    const out = await translateViaAI(texts);
    // The user may have switched language while the AI ran — never write into another track
    if (state.translation.lang !== langAtStart) {
      toast('⚠️ Superseded', `Translation finished after the target changed to ${targetLangName()} — press 🌐 Translate to build it.`, 'warning', 4000);
      return false;
    }
    state.translation.lines = buildLines(out);
    state.translation.loaded = true;
    setTrackOwner();
    // Manual translating keeps the mode you were in; the auto Khmer track always shows both lines
    const keep = !opts.preferBilingual && (prevMode === 'translation_only' || prevMode === 'bilingual') ? prevMode : null;
    const target = keep || ((prevMode === 'original_only' && !wantsAutoKhmer()) ? 'original_only' : 'bilingual');
    try { await persistTranslation(); } catch (e) { console.warn('[VIDA Translation] save failed:', e); }
    setDisplayMode(target, false);
    toast('🌐 Translated', `${translationCount()} lines → ${targetLangName()} saved as a separate track. Original lyrics & timings untouched.`, 'success', 4500);
    return true;
  } catch (e) {
    toast('❌ Translation Failed', e.message || String(e), 'error', 5000);
    syncUI();
    return false;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

async function exportTranslationSRT(btn) {
  const cues = getTranslationCues();
  if (!cues.length) {
    toast('⚠️ Nothing to Export', 'Translate or type the lyric lines first.', 'warning', 3500);
    return;
  }
  const label = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Exporting…'; }
  try {
    let content = generateSRT(getTranslationCues());
    let name = `${(state.songTitle || 'lyrics').replace(/[^\w\u1780-\u17FF\- ]/g, '').trim().replace(/\s+/g, '_') || 'lyrics'}.${state.translation.lang}.srt`;
    try {
      const saved = await persistTranslation();
      if (saved && saved.srt_content) content = saved.srt_content;
    } catch (e) { console.warn('[VIDA Translation] server copy failed:', e); }
    downloadFile(content, name, 'application/x-subrip');
    toast('📤 Translated SRT Exported', `${cues.length} cues with the original timestamps → ${name} (stored beside the audio too)`, 'success', 4500);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

// ============ Translation editor modal ============
// The shell is painted by ui.css (.ui-modal / .ui-modal-card); JS only owns the
// open/close inline `display` value, which is the contract the rest of the app uses.
function ensureModal() {
  if (modalEl) return modalEl;
  modalEl = document.createElement('div');
  modalEl.id = 'translation-editor-modal';
  modalEl.className = 'ui-modal ui-modal--te';
  modalEl.style.display = 'none';
  modalEl.innerHTML = `
    <div class="ui-modal-card ui-modal-card--te">
      <div class="ui-modal-hd">
        <div class="ui-modal-titlerow">
          <span class="ui-modal-ico">🌐</span>
          <h3 class="ui-modal-name">Translation Line Editor</h3>
          <span id="te-summary" class="ui-chip">—</span>
        </div>
        <div class="ui-row">
          <button id="te-translate-all" class="ui-btn ui-btn--ai ui-btn--sm">🌐 AI Translate All</button>
          <button id="te-save" class="ui-btn ui-btn--go ui-btn--sm">💾 Apply &amp; Save</button>
          <button id="te-close" class="ui-btn ui-btn--icon ui-modal-x" title="Close">✕</button>
        </div>
      </div>
      <div class="ui-note">Original cues and timestamps are never modified — each translated line is mapped by its line index and reuses the original timing.</div>
      <div class="ui-modal-body" id="te-body"></div>
    </div>`;
  document.body.appendChild(modalEl);
  modalEl.addEventListener('click', (e) => { if (e.target === modalEl) closeModal(); });
  modalEl.querySelector('#te-close').addEventListener('click', closeModal);
  modalEl.querySelector('#te-save').addEventListener('click', applyDraft);
  modalEl.querySelector('#te-translate-all').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const texts = (state.lyrics || []).map(l => (l.text || '').trim());
    btn.disabled = true; btn.textContent = '⏳ Translating…';
    try {
      const out = await translateViaAI(texts);
      draftLines = buildLines(out);
      renderRows();
      toast('🌐 AI Pass Complete', `${translationCount()} lines refreshed in the editor — review then Apply & Save.`, 'success', 3500);
    } catch (err) {
      toast('❌ Translation Failed', err.message || String(err), 'error', 5000);
    } finally {
      btn.disabled = false; btn.textContent = '🌐 AI Translate All';
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalEl && modalEl.style.display !== 'none') closeModal();
  });
  return modalEl;
}

function closeModal() {
  if (modalEl) modalEl.style.display = 'none';
}

function renderRows() {
  const body = modalEl.querySelector('#te-body');
  if (!body) return;
  const lyrics = state.lyrics || [];
  body.innerHTML = '';
  lyrics.forEach((l, i) => {
    const row = document.createElement('div');
    row.className = 'trans-editor-row';
    const entry = draftLines[i] || { text: '' };
    row.innerHTML = `
      <div class="te-idx">${i + 1}</div>
      <div class="te-orig">${escapeHtml((l.text || '').trim())}<span class="te-time">${fmtTime(l.start)} → ${fmtTime(l.end)}</span></div>
      <textarea class="te-input" rows="2" placeholder="Translated line ${i + 1}"></textarea>
      <button class="te-redo" title="Re-translate only this line">🔁</button>`;
    const ta = row.querySelector('.te-input');
    ta.value = entry.text || '';
    ta.addEventListener('input', () => {
      if (!draftLines[i]) draftLines[i] = { index: i, text: '', start: Number(l.start) || 0, end: Number(l.end) || 0 };
      draftLines[i].text = ta.value;
      updateSummary();
    });
    row.querySelector('.te-redo').addEventListener('click', async (e) => {
      const b = e.currentTarget;
      b.disabled = true; b.textContent = '⏳';
      try {
        const out = await translateViaAI([(l.text || '').trim()]);
        const txt = String(out[0] || '').trim();
        if (!draftLines[i]) draftLines[i] = { index: i, text: '', start: Number(l.start) || 0, end: Number(l.end) || 0 };
        draftLines[i].text = txt;
        ta.value = txt;
        updateSummary();
      } catch (err) {
        toast('❌ Line Re-translate Failed', err.message || String(err), 'error', 4000);
      } finally {
        b.disabled = false; b.textContent = '🔁';
      }
    });
    body.appendChild(row);
  });
  updateSummary();
}

function updateSummary() {
  const s = modalEl.querySelector('#te-summary');
  if (!s) return;
  const filled = draftLines.filter(l => String(l.text || '').trim()).length;
  s.textContent = `${(state.lyrics || []).length} original lines · ${filled} translated · ${targetLangName()}`;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function openEditor() {
  if (!(state.lyrics || []).length) {
    toast('⚠️ No Lyrics', 'Load or sync lyrics before editing a translation.', 'warning', 3500);
    return;
  }
  ensureModal();
  draftLines = (state.translation.lines || []).map(l => ({ ...l }));
  while (draftLines.length < (state.lyrics || []).length) {
    const i = draftLines.length;
    draftLines.push({ index: i, text: '', start: Number(state.lyrics[i].start) || 0, end: Number(state.lyrics[i].end) || 0 });
  }
  renderRows();
  modalEl.style.display = 'flex';
}

async function applyDraft() {
  state.translation.lines = buildLines(draftLines.map(l => (l && l.text) || ''));
  state.translation.loaded = translationCount() > 0;
  setTrackOwner();
  try {
    await persistTranslation();
    toast('💾 Saved', `${translationCount()} translated lines stored as ${state.translation.lang} track (separate file, original SRT intact).`, 'success', 4000);
  } catch (e) {
    toast('⚠️ Saved in Studio only', `The lyrics are applied to preview/export, but the .srt copy failed: ${e.message || e}`, 'warning', 5000);
  }
  closeModal();
  if (translationCount() > 0 && getDisplayMode() === 'original_only') setDisplayMode('bilingual', false);
  else syncUI();
}

// ============ Init ============
export function initTranslationTrack(showToastFn) {
  if (typeof showToastFn === 'function') toast = showToastFn;
  restoreProjectSession();

  const group = document.getElementById('translation-mode-group');
  if (group) {
    group.querySelectorAll('.trans-mode-btn').forEach(btn => {
      btn.addEventListener('click', () => setDisplayMode(btn.dataset.mode));
    });
  }

  const langSel = document.getElementById('select-translation-lang');
  if (langSel) {
    langSel.value = state.translation.lang;
    langSel.addEventListener('change', (e) => {
      state.translation.lang = e.target.value;
      saveProjectSession();
      syncUI();
      if (translationCount() > 0) {
        toast('🌐 Language Changed', `Track language is now ${targetLangName()}. Click 🌐 Translate to regenerate the lines.`, 'info', 4000);
      } else {
        toast('🌐 Target Language', `${targetLangName()} — press 🌐 Translate to build the track.`, 'info', 3000);
      }
      loadTranslationForSong();
    });
  }

  const btnAll = document.getElementById('btn-translate-all');
  if (btnAll) btnAll.addEventListener('click', () => translateAll(btnAll));

  const autoChk = document.getElementById('chk-auto-khmer');
  if (autoChk) {
    autoChk.checked = autoKhmerEnabled();
    autoChk.addEventListener('change', async (e) => {
      const on = !!e.target.checked;
      setAutoKhmer(on);
      if (!on) {
        toast('🇰🇭 Auto Khmer off', 'Foreign songs keep the language you pick. Existing Khmer tracks are untouched.', 'info', 3500);
        syncUI();
        return;
      }
      if (sourceIsKhmer()) {
        toast('ℹ️ Nothing to auto-translate', 'These lyrics are already Khmer. Pick a target language to translate them into.', 'info', 3800);
        syncUI();
        return;
      }
      if (state.translation.lang === 'km' && translationCount() > 0) { syncUI(); return; }
      await autoBuildKhmerTrack(getAudioKey());
    });
  }

  const btnEdit = document.getElementById('btn-edit-translation');
  if (btnEdit) btnEdit.addEventListener('click', openEditor);

  const btnExp = document.getElementById('btn-export-translation-srt');
  if (btnExp) btnExp.addEventListener('click', () => exportTranslationSRT(btnExp));

  const styleBindings = [
    ['range-trans-size', v => { state.translation.style.sizeRatio = Math.max(0.3, Math.min(0.9, v / 100)); }],
    ['range-trans-offset', v => { state.translation.style.offsetRatio = Math.max(0.1, Math.min(1.4, v / 100)); }],
    ['color-trans', v => { state.translation.style.color = v; }],
    ['select-trans-align', v => { state.translation.style.align = v; }],
    ['check-trans-outline', v => { state.translation.style.outline = v; }, true],
    ['check-trans-shadow', v => { state.translation.style.shadow = v; }, true],
    ['check-trans-background', v => { state.translation.style.background = v; }, true]
  ];
  styleBindings.forEach(([id, setter, isCheck]) => {
    const el = document.getElementById(id);
    if (!el) return;
    const evt = isCheck || el.type === 'color' ? 'change' : 'input';
    el.addEventListener(evt, () => {
      setter(isCheck ? el.checked : (el.type === 'range' ? Number(el.value) : el.value));
      saveProjectSession();
    });
  });

  syncUI();
}

/** Rendering payload for the server-side (fallback) renderer. */
export function getTranslationRenderOptions() {
  const mode = getDisplayMode();
  if (mode === 'original_only') {
    return { display_mode: 'original_only', translation_lines: [], translation_lang: state.translation.lang };
  }
  return {
    display_mode: mode,
    translation_lines: (state.translation.lines || []).map(l => String((l && l.text) || '')),
    translation_lang: state.translation.lang,
    translation_style: { ...(state.translation.style || {}), color: (state.translation.style || {}).color || '#ffffff' }
  };
}
