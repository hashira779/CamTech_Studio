/**
 * WYSIWYG Video Exporter — encodes the exact frames the studio preview draws.
 *
 * The preview and this exporter share one render function (renderScene) and one
 * audio-feature pipeline, so the exported video is the preview, frame for frame.
 * Frames are pushed through WebCodecs (hardware H.264 when available) at whatever
 * speed the machine manages — typically several times faster than real time —
 * then the server stream-copies the video and muxes the original audio.
 */
import { state } from './state.js';
import { renderScene, resetSceneState, stopVisualizer, startVisualizer } from './visualizer.js';
import { ensureAudioFeatures, getFeatureDuration } from './audio_features.js';
import { Muxer, ArrayBufferTarget } from '../../vendor/mp4-muxer.mjs';

const RES_HEIGHT = { '480p': 480, '720p': 720, '1080p': 1080 };

export function supportsFastExport() {
  return typeof window.VideoEncoder === 'function' && typeof window.VideoFrame === 'function';
}

export function exportDimensions() {
  const h = RES_HEIGHT[state.renderResolution] || 1080;
  const ar = state.aspectRatio || '16:9';
  let w;
  if (ar === '9:16') w = Math.round(h * 9 / 16);
  else if (ar === '1:1') w = h;
  else w = Math.round(h * 16 / 9);
  w += w % 2;
  return [w, h - (h % 2)];
}

function bitrateFor(w, h, fps) {
  const px = w * h;
  const base = px >= 1920 * 1080 ? 12e6 : (px >= 1280 * 720 ? 6e6 : 3e6);
  return Math.round(base * (fps > 30 ? 1.35 : 1));
}

async function pickConfig(w, h, fps) {
  const px = w * h * fps;
  const avcLevel = px <= 1920 * 1080 * 30 ? '640028' : (px <= 1920 * 1080 * 60 ? '64002a' : '640033');
  const candidates = [
    { codec: `avc1.${avcLevel}`, muxCodec: 'avc' },
    { codec: 'avc1.42001e', muxCodec: 'avc' },
    { codec: 'vp09.00.10.08', muxCodec: 'vp9' },
  ];
  for (const c of candidates) {
    const cfg = {
      codec: c.codec, width: w, height: h,
      bitrate: bitrateFor(w, h, fps), framerate: fps,
    };
    try {
      const sup = await VideoEncoder.isConfigSupported(cfg);
      if (sup.supported) return { cfg, muxCodec: c.muxCodec };
    } catch (e) { /* try next */ }
  }
  return null;
}

/**
 * Yields to the event loop as an *unthrottled* task.
 *
 * setTimeout(0) looks equivalent, but Chrome throttles timers to ~1/minute in
 * a hidden tab and freezes them entirely after a few minutes — which stalled
 * the encoder drain loop and froze exports whenever the user switched tabs or
 * minimized. A MessageChannel port message is a task that is never throttled,
 * so the export keeps running in the background.
 */
const nextTick = () => {
  const ch = new MessageChannel();
  return new Promise((resolve) => {
    ch.port1.onmessage = () => resolve();
    ch.port2.postMessage(0);
  });
};

/**
 * Offline (faster-than-realtime) export of the exact preview frames.
 * onProgress(pct0to1, label) is called throughout.
 */
export async function exportVideoWYSIWYG({ onProgress = () => {} } = {}) {
  if (!supportsFastExport()) throw new Error('WebCodecs unavailable');
  if (!state.audioUrl) throw new Error('No audio loaded');

  onProgress(0.01, 'Decoding audio for frame-accurate spectrum');
  await ensureAudioFeatures(state.audioUrl);
  const duration = state.audioDuration || getFeatureDuration();
  if (!duration) throw new Error('Audio duration unknown');

  const fps = state.renderFps || 30;
  const [W, H] = exportDimensions();
  const picked = await pickConfig(W, H, fps);
  if (!picked) throw new Error('No supported video encoder');

  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { alpha: false });

  const audioPlayer = document.getElementById('audio-player');
  const resumeTime = audioPlayer ? audioPlayer.currentTime : 0;
  const wasPlaying = audioPlayer ? !audioPlayer.paused : false;
  if (audioPlayer && wasPlaying) audioPlayer.pause();
  stopVisualizer();

  resetSceneState();

  const muxer = new Muxer({
    target: new ArrayBufferTarget(),
    video: { codec: picked.muxCodec, width: W, height: H, frameRate: fps },
    fastStart: 'in-memory',
  });
  let encError = null;
  const encoder = new VideoEncoder({
    output: (chunk, meta) => muxer.addVideoChunk(chunk, meta),
    error: (e) => { encError = e; },
  });
  encoder.configure({ ...picked.cfg, hardwareAcceleration: 'prefer-hardware', hardwarePreference: 'prefer-hardware' });

  // Back-pressure without a busy-wait.
  //
  // The queue depth matters twice: shallow (`> 6`) made the loop wait on the
  // encoder after nearly every frame, so rasterising frame i+1 could not
  // overlap encoding frame i; and the wait itself used to be
  // `while (queueSize > N) await nextTick()`, a postMessage spin that starves
  // the rest of the task queue — including the encoder's own output callbacks —
  // which froze the progress read-out and dragged throughput down to a crawl
  // (measured: 0.6x realtime with the UI stuck). `dequeue` is the event the
  // spec provides for exactly this: the loop parks until the encoder wakes it.
  const queueSize = () => (typeof encoder.queueSize === 'number' ? encoder.queueSize : encoder.encodeQueueSize);
  const QUEUE_HIGH = W * H >= 1500000 ? 12 : 24;   // frames in flight (~100 MB of 1080p RGBA at 12)
  const QUEUE_LOW = Math.max(2, Math.floor(QUEUE_HIGH / 2));

  async function waitForEncoderQueue() {
    while (queueSize() > QUEUE_LOW && !encError) {
      await new Promise((res) => {
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          encoder.removeEventListener('dequeue', onDequeue);
          clearTimeout(guard);
          res();
        };
        const onDequeue = () => { if (queueSize() <= QUEUE_LOW) done(); };
        encoder.addEventListener('dequeue', onDequeue);
        // Safety net: a stalled encoder that never dequeues must not hang the
        // export forever. Timers are throttled in a hidden tab, so this is a
        // backstop, not the normal path.
        const guard = setTimeout(done, 2000);
      });
    }
  }

  // Yield frequency: every hop lets the browser run its own tasks; the progress
  // line only needs a couple of updates per second.
  const tickEvery = Math.max(10, Math.round(fps / 2));

  const total = Math.ceil(duration * fps);
  const t0 = performance.now();
  try {
    for (let i = 0; i < total; i++) {
      if (encError) throw encError;
      const t = i / fps;
      renderScene(ctx, canvas, t, 1 / fps);
      const frame = new VideoFrame(canvas, {
        timestamp: Math.round(i * 1e6 / fps),
        duration: Math.round(1e6 / fps),
        alpha: 'discard',
      });
      encoder.encode(frame, { keyFrame: i % (fps * 2) === 0 });
      frame.close();
      if (queueSize() > QUEUE_HIGH) await waitForEncoderQueue();
      if (i % tickEvery === 0) {
        const el = (performance.now() - t0) / 1000;
        const speed = el > 0.5 ? (t / el).toFixed(1) : '…';
        const left = i > 20 && el > 0.5 ? ((el / i) * (total - i)) : null;
        const eta = left == null ? '' : ` — about ${left >= 90 ? `${(left / 60).toFixed(1)} min` : `${Math.round(left)}s`} left`;
        onProgress(0.05 + 0.8 * (i / total), `Rendering ${W}x${H}@${fps} — ${speed}x realtime${eta}`);
        await nextTick();
      }
    }
    onProgress(0.88, 'Finalizing encoder');
    await encoder.flush();
    encoder.close();
    muxer.finalize();
  } catch (err) {
    try { encoder.close(); } catch (e) {}
    if (wasPlaying && audioPlayer) audioPlayer.play().catch(() => {});
    startVisualizer();
    throw err;
  }

  const blob = new Blob([muxer.target.buffer], { type: 'video/mp4' });
  const wallSec = (performance.now() - t0) / 1000;
  // Remember what this machine actually managed, so the preset labels can show
  // a measured speed instead of a guessed one.
  state.lastExportSpeedX = wallSec > 0 ? duration / wallSec : 0;
  try {
    localStorage.setItem('vida_export_speed', JSON.stringify({
      key: `${W}x${H}@${fps}`, xRealtime: +state.lastExportSpeedX.toFixed(2),
      msPerFrame: +((wallSec * 1000) / total).toFixed(2), at: Date.now(),
    }));
  } catch (e) { /* storage full / disabled */ }
  onProgress(0.92, `Muxing original audio (${(blob.size / 1e6).toFixed(1)} MB video)`);

  const fd = new FormData();
  fd.append('video', blob, 'vida_preview_frames.mp4');
  fd.append('audio_path', state.audioServerPath || '');
  const res = await fetch('/api/export/mux', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Audio mux failed');

  if (audioPlayer) audioPlayer.currentTime = resumeTime;
  if (wasPlaying && audioPlayer) audioPlayer.play().catch(() => {});
  startVisualizer();
  onProgress(1, 'Done');
  return { ...data, blobSize: blob.size, seconds: duration, fps, width: W, height: H };
}

/**
 * Fallback for browsers without WebCodecs: real-time capture of the same render
 * loop via MediaRecorder (still WYSIWYG, but 1x speed).
 */
export async function exportVideoRealtime({ onProgress = () => {} } = {}) {
  const fps = state.renderFps || 30;
  const [W, H] = exportDimensions();
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { alpha: false });

  const audioPlayer = document.getElementById('audio-player');
  if (!audioPlayer) throw new Error('No audio loaded');

  const { getRecordStream } = await import('./audio.js');
  const vStream = canvas.captureStream(fps);
  const aStream = getRecordStream();
  const tracks = [...vStream.getVideoTracks(), ...(aStream ? aStream.getAudioTracks() : [])];
  const stream = new MediaStream(tracks);
  const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
    ? 'video/webm;codecs=vp9,opus'
    : 'video/webm';
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: bitrateFor(W, H, fps) });
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };

  resetSceneState();
  stopVisualizer();
  audioPlayer.currentTime = 0;
  await audioPlayer.play();

  const done = new Promise((resolve) => { rec.onstop = resolve; });
  rec.start(500);

  let raf = 0;
  let last = 0;
  const dur = state.audioDuration || getFeatureDuration();
  const loop = (ts) => {
    const dt = last ? Math.min(0.05, (ts - last) / 1000) : 1 / fps;
    last = ts;
    renderScene(ctx, canvas, audioPlayer.currentTime, dt);
    onProgress(Math.min(0.95, audioPlayer.currentTime / (dur || 1)), 'Recording preview in real time');
    if (!audioPlayer.paused && !audioPlayer.ended) raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  audioPlayer.onended = () => {
    cancelAnimationFrame(raf);
    setTimeout(() => rec.stop(), 250);
  };
  await done;
  audioPlayer.onended = null;

  const blob = new Blob(chunks, { type: 'video/webm' });
  onProgress(0.96, 'Muxing to MP4 on server');
  const fd = new FormData();
  fd.append('video', blob, 'vida_realtime.webm');
  fd.append('audio_path', '');
  fd.append('container', 'webm');
  const res = await fetch('/api/export/mux', { method: 'POST', body: fd });
  const data = await res.json();
  startVisualizer();
  if (!res.ok) throw new Error(data.detail || 'Mux failed');
  return data;
}
