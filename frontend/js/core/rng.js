/**
 * Seeded PRNG shared by every stochastic element of the render path (particles,
 * camera shake, director triggers). Preview and export re-seed with the same
 * value, so both reproduce the identical ambient motion from t = 0.
 */
const DEFAULT_SEED = 0x5EED1337;
let seed = DEFAULT_SEED >>> 0;

export function setRenderSeed(s) {
  seed = (s >>> 0) || DEFAULT_SEED;
}

export function resetRenderSeed() {
  seed = DEFAULT_SEED >>> 0;
}

/** mulberry32 — fast, deterministic, uniform in [0, 1). */
export function renderRand() {
  seed |= 0;
  seed = (seed + 0x6D2B79F5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
