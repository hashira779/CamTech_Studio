/**
 * Deterministic offline audio features — the single source of truth for the
 * spectrum/bass that drives themes, VFX and the director, in BOTH the live
 * preview and the offline exporter. Replaces the live AnalyserNode so a frame
 * at time t always looks identical no matter who asks for it.
 *
 * Mirrors the Web Audio AnalyserNode contract: 2048-sample Hann window ending at
 * t, radix-2 FFT, magnitude -> dB -> byte mapping with minDecibels = -100 and
 * maxDecibels = -30 (Chrome defaults), 1024 bins.
 */
import { getAudioContext } from './audio.js';

const FFT_N = 2048;
const MIN_DB = -100;
const MAX_DB = -30;

let cacheKey = null;
let mono = null;          // Float32Array @ buffer.sampleRate
let sampleRate = 48000;
let duration = 0;
const specCache = new Map(); // quantized t -> Uint8Array

// Precomputed FFT tables
const revBits = new Uint16Array(FFT_N);
const cosT = new Float32Array(FFT_N / 2);
const sinT = new Float32Array(FFT_N / 2);
(() => {
  const bits = Math.log2(FFT_N);
  for (let i = 0; i < FFT_N; i++) {
    let r = 0;
    for (let b = 0; b < bits; b++) r = (r << 1) | ((i >> b) & 1);
    revBits[i] = r;
  }
  for (let i = 0; i < FFT_N / 2; i++) {
    cosT[i] = Math.cos(-2 * Math.PI * i / FFT_N);
    sinT[i] = Math.sin(-2 * Math.PI * i / FFT_N);
  }
})();

const win = new Float32Array(FFT_N);
for (let i = 0; i < FFT_N; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (FFT_N - 1));

const re = new Float32Array(FFT_N);
const im = new Float32Array(FFT_N);

function fft() {
  for (let i = 0; i < FFT_N; i++) {
    const j = revBits[i];
    if (j > i) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (let size = 2; size <= FFT_N; size <<= 1) {
    const half = size >> 1;
    const step = FFT_N / size;
    for (let i = 0; i < FFT_N; i += size) {
      for (let j = i, k = 0; j < i + half; j++, k += step) {
        const c = cosT[k], s = sinT[k];
        const tr = re[j + half] * c - im[j + half] * s;
        const ti = re[j + half] * s + im[j + half] * c;
        re[j + half] = re[j] - tr; im[j + half] = im[j] - ti;
        re[j] += tr; im[j] += ti;
      }
    }
  }
}

export async function ensureAudioFeatures(url) {
  if (!url) return false;
  if (cacheKey === url && mono) return true;
  const res = await fetch(url);
  const buf = await res.arrayBuffer();
  let ctx = getAudioContext();
  let decoded;
  if (ctx && ctx.decodeAudioData) {
    decoded = await ctx.decodeAudioData(buf.slice(0));
  } else {
    const OCtor = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    const tmp = new OCtor(1, 1, 44100);
    decoded = await tmp.decodeAudioData(buf.slice(0));
  }
  const ch0 = decoded.getChannelData(0);
  if (decoded.numberOfChannels > 1) {
    const ch1 = decoded.getChannelData(1);
    const m = new Float32Array(ch0.length);
    for (let i = 0; i < ch0.length; i++) m[i] = (ch0[i] + ch1[i]) * 0.5;
    mono = m;
  } else {
    mono = ch0;
  }
  sampleRate = decoded.sampleRate;
  duration = decoded.duration;
  cacheKey = url;
  specCache.clear();
  return true;
}

export function getFeatureDuration() {
  return duration;
}

export function hasFeatures() {
  return !!mono;
}

/** Byte spectrum (1024 bins, 0..255) for the analysis window ending at time t. */
export function getFrameSpectrum(t) {
  if (!mono) return null;
  const q = Math.round(t * 1000) / 1000;
  const hit = specCache.get(q);
  if (hit) return hit;

  const out = new Uint8Array(FFT_N / 2);
  const end = Math.min(mono.length, Math.max(0, Math.round(q * sampleRate)));
  const start = end - FFT_N;
  for (let i = 0; i < FFT_N; i++) {
    const idx = start + i;
    re[i] = (idx >= 0 && idx < mono.length) ? mono[idx] * win[i] : 0;
    im[i] = 0;
  }
  fft();
  const range = MAX_DB - MIN_DB;
  for (let i = 0; i < FFT_N / 2; i++) {
    const mag = Math.sqrt(re[i] * re[i] + im[i] * im[i]) / (FFT_N / 2);
    const db = 20 * Math.log10(mag + 1e-9);
    let v = (db - MIN_DB) / range;
    v = v < 0 ? 0 : (v > 1 ? 1 : v);
    out[i] = (v * 255) | 0;
  }
  if (specCache.size > 240) specCache.clear();
  specCache.set(q, out);
  return out;
}
