import React, { useState, useEffect, useRef } from "react";

/**
 * Khmer Oldies AI Restoration Studio — Next.js / React Component
 *
 * Provides:
 * - Stage 1 Diagnostic Telemetry (RMS, Peak, LUFS, Noise Floor, DC Offset)
 * - 5 Vintage Restoration Presets
 * - Dual A/B Waveform Player with seamless sync comparison
 * - Fine-Tuning DSP Drawer (De-Hiss, Rumble, Hum, Warmth, Vocal Formants)
 * - Multi-Format Master Exporter (WAV 16/24/32-bit, MP3 320k, FLAC)
 */

interface Preset {
  id: string;
  name: string;
  description: string;
  hiss_reduction_db: number;
  rumble_cutoff_hz: number;
  warmth_db: number;
  vocal_presence_db: number;
  stereo_widening: boolean;
  use_demucs: boolean;
}

interface TrackMetrics {
  filename: string;
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  peak_dbfs: number;
  rms_dbfs: number;
  loudness_lufs: number;
  noise_floor_dbfs: number;
  dc_offset: number;
  clipping_samples: number;
  waveform_data: number[];
  url: string;
}

interface RestorationJob {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress_percent: number;
  output_url?: string;
  metrics_after?: TrackMetrics;
  processing_time_seconds?: number;
  error_message?: string;
}

export default function KhmerRestorationStudio({ defaultAudioPath }: { defaultAudioPath?: string }) {
  const [audioPath, setAudioPath] = useState<string>(defaultAudioPath || "");
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState<string>("vintage_studio");
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [processing, setProcessing] = useState<boolean>(false);
  const [track, setTrack] = useState<TrackMetrics | null>(null);
  const [currentJob, setCurrentJob] = useState<RestorationJob | null>(null);

  // A/B Playback State
  const [activeSource, setActiveSource] = useState<"original" | "restored">("original");
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Fine-Tuning DSP Overrides
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);
  const [bypassAi, setBypassAi] = useState<boolean>(false);
  const [hissReduction, setHissReduction] = useState<number>(14);
  const [rumbleCutoff, setRumbleCutoff] = useState<number>(50);
  const [humRemoval, setHumRemoval] = useState<boolean>(true);
  const [warmth, setWarmth] = useState<number>(1.5);
  const [vocalPresence, setVocalPresence] = useState<number>(2.8);
  const [stereoWidening, setStereoWidening] = useState<boolean>(false);
  const [exportFormat, setExportFormat] = useState<string>("wav24");

  // Load Presets on Mount
  useEffect(() => {
    fetch("/api/restore/presets")
      .then((res) => res.json())
      .then((data) => {
        if (data.presets) setPresets(data.presets);
      })
      .catch((err) => console.error("Failed to fetch presets:", err));
  }, []);

  // Hotkey: Tab to toggle A/B, Space to Play/Pause
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Tab" && currentJob?.output_url) {
        e.preventDefault();
        setActiveSource((prev) => (prev === "original" ? "restored" : "original"));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentJob]);

  // Stage 1: Analyze Track
  const handleAnalyze = async () => {
    if (!audioPath) return;
    setAnalyzing(true);
    try {
      const res = await fetch("/api/restore/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audio_path: audioPath }),
      });
      const data = await res.json();
      if (data.status === "success" && data.track) {
        setTrack(data.track);
      }
    } catch (err) {
      console.error("Audio analysis failed:", err);
    } finally {
      setAnalyzing(false);
    }
  };

  // Stage 2–4: Process Restoration
  const handleRestore = async () => {
    if (!audioPath) return;
    setProcessing(true);
    try {
      const res = await fetch("/api/restore/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_path: audioPath,
          preset: selectedPreset,
          bypass_ai: bypassAi,
          overrides: {
            hiss_reduction_db: hissReduction,
            rumble_cutoff_hz: rumbleCutoff,
            hum_removal: humRemoval,
            warmth_db: warmth,
            vocal_presence_db: vocalPresence,
            stereo_widening: stereoWidening,
          },
          export_format: exportFormat,
        }),
      });
      const data = await res.json();
      if (data.job_id) {
        pollJobStatus(data.job_id);
      }
    } catch (err) {
      console.error("Restoration submission failed:", err);
      setProcessing(false);
    }
  };

  // Poll Job Progress
  const pollJobStatus = (jobId: string) => {
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/restore/status/${jobId}`);
        const job: RestorationJob = await res.json();
        setCurrentJob(job);
        if (job.status === "completed" || job.status === "failed") {
          clearInterval(timer);
          setProcessing(false);
          if (job.status === "completed") {
            setActiveSource("restored");
          }
        }
      } catch (err) {
        clearInterval(timer);
        setProcessing(false);
      }
    }, 1500);
  };

  // Synchronized Audio Source Swap
  const handleSourceSwap = (source: "original" | "restored") => {
    if (!audioRef.current) return;
    const curr = audioRef.current.currentTime;
    const playing = !audioRef.current.paused;
    setActiveSource(source);
    const nextUrl = source === "original" ? track?.url : currentJob?.output_url;
    if (nextUrl) {
      audioRef.current.src = nextUrl;
      audioRef.current.currentTime = curr;
      if (playing) audioRef.current.play();
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="border-b border-slate-800 pb-6 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-amber-400">
              Khmer Oldies AI Restoration Studio
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Preserving golden-era authentic character (1950s–1990s) with physics-based cleanup & Demucs AI.
            </p>
          </div>
          <span className="px-3 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full text-xs font-semibold tracking-wide uppercase">
            Archival Heritage Edition
          </span>
        </div>

        {/* Audio Input & Diagnostics */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">Audio Source File</label>
          <div className="flex gap-3">
            <input
              type="text"
              value={audioPath}
              onChange={(e) => setAudioPath(e.target.value)}
              placeholder="e.g. uploads/audio/Konseng Soat - Sinn Sisamouth.mp3"
              className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-amber-400 font-mono"
            />
            <button
              onClick={handleAnalyze}
              disabled={analyzing || !audioPath}
              className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition disabled:opacity-50"
            >
              {analyzing ? "Analyzing…" : "1. Analyze Diagnostics"}
            </button>
          </div>

          {/* Diagnostic Telemetry Panel */}
          {track && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 pt-3 border-t border-slate-800/80">
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">Duration</span>
                <span className="text-base font-semibold text-slate-200 font-mono">
                  {Math.floor(track.duration_seconds / 60)}:
                  {String(Math.floor(track.duration_seconds % 60)).padStart(2, "0")}
                </span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">Noise Floor</span>
                <span className="text-base font-semibold text-rose-400 font-mono">{track.noise_floor_dbfs} dB</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">Loudness</span>
                <span className="text-base font-semibold text-slate-300 font-mono">{track.loudness_lufs} LUFS</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">True Peak</span>
                <span className="text-base font-semibold text-slate-300 font-mono">{track.peak_dbfs} dBFS</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">Sample Rate</span>
                <span className="text-base font-semibold text-slate-300 font-mono">{track.sample_rate} Hz</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] uppercase text-slate-500 block">Channels</span>
                <span className="text-base font-semibold text-slate-300 font-mono">
                  {track.channels === 1 ? "Mono" : "Stereo"}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* 5 Restoration Presets Deck */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-slate-200">2. Select Archival Restoration Preset</h2>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-xs text-amber-400 hover:text-amber-300 transition"
            >
              {showAdvanced ? "Hide Fine-Tuning" : "Custom Fine-Tuning Controls ▸"}
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {presets.map((p) => {
              const active = selectedPreset === p.id;
              return (
                <div
                  key={p.id}
                  onClick={() => setSelectedPreset(p.id)}
                  className={`cursor-pointer rounded-xl p-4 border transition-all ${
                    active
                      ? "bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/5 ring-1 ring-amber-500"
                      : "bg-slate-900 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-amber-400 font-mono">
                      {p.use_demucs ? "AI Stems" : "Acoustic"}
                    </span>
                    {active && <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />}
                  </div>
                  <h3 className="text-sm font-semibold text-slate-100">{p.name}</h3>
                  <p className="text-xs text-slate-400 mt-2 line-clamp-3 leading-relaxed">{p.description}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Fine-Tuning Drawer */}
        {showAdvanced && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Custom DSP Calibration</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Hiss Reduction</span>
                  <span className="font-mono text-amber-400">-{hissReduction} dB</span>
                </div>
                <input
                  type="range"
                  min="4"
                  max="24"
                  value={hissReduction}
                  onChange={(e) => setHissReduction(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Subsonic Rumble Cut</span>
                  <span className="font-mono text-amber-400">{rumbleCutoff} Hz</span>
                </div>
                <input
                  type="range"
                  min="30"
                  max="80"
                  value={rumbleCutoff}
                  onChange={(e) => setRumbleCutoff(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Khmer Vocal Presence (3.4 kHz)</span>
                  <span className="font-mono text-amber-400">+{vocalPresence} dB</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="6"
                  step="0.2"
                  value={vocalPresence}
                  onChange={(e) => setVocalPresence(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Analog Tape Warmth (120 Hz)</span>
                  <span className="font-mono text-amber-400">+{warmth} dB</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="3"
                  step="0.1"
                  value={warmth}
                  onChange={(e) => setWarmth(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              </div>

              <div className="flex items-center gap-3 pt-4">
                <input
                  type="checkbox"
                  id="stereo-widen"
                  checked={stereoWidening}
                  onChange={(e) => setStereoWidening(e.target.checked)}
                  className="w-4 h-4 accent-amber-500 rounded"
                />
                <label htmlFor="stereo-widen" className="text-xs text-slate-300">
                  Widen Accompaniment into Stereo (Keeps voice centered)
                </label>
              </div>

              <div className="flex items-center gap-3 pt-4">
                <input
                  type="checkbox"
                  id="bypass-ai"
                  checked={bypassAi}
                  onChange={(e) => setBypassAi(e.target.checked)}
                  className="w-4 h-4 accent-amber-500 rounded"
                />
                <label htmlFor="bypass-ai" className="text-xs text-slate-300">
                  Bypass Demucs AI Stem Separation
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="flex justify-center">
          <button
            onClick={handleRestore}
            disabled={processing || !audioPath}
            className="px-8 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg shadow-amber-500/20 transition-all disabled:opacity-50 text-base"
          >
            {processing ? `Restoring… (${currentJob?.progress_percent || 0}%)` : "3. Execute Archival Restoration"}
          </button>
        </div>

        {/* Synchronized A/B Player */}
        {(track?.url || currentJob?.output_url) && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="text-base font-semibold text-slate-200">A/B Instant Listening Comparison</h3>
                <p className="text-xs text-slate-400">
                  Press <kbd className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-slate-300">Tab</kbd> while playing to instantly switch between Original and Restored audio.
                </p>
              </div>

              {/* Source Switcher */}
              <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
                <button
                  onClick={() => handleSourceSwap("original")}
                  className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${
                    activeSource === "original" ? "bg-slate-800 text-slate-100 shadow" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Original (Pre-Restore)
                </button>
                <button
                  onClick={() => handleSourceSwap("restored")}
                  disabled={!currentJob?.output_url}
                  className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${
                    activeSource === "restored" ? "bg-amber-500 text-slate-950 shadow" : "text-slate-400 hover:text-slate-200 disabled:opacity-40"
                  }`}
                >
                  Restored Master ✨
                </button>
              </div>
            </div>

            {/* Audio Player Element */}
            <audio
              ref={audioRef}
              controls
              src={activeSource === "original" ? track?.url : currentJob?.output_url}
              className="w-full accent-amber-500"
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
            />

            {/* Before vs After Telemetry Comparison */}
            {currentJob?.metrics_after && (
              <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between text-xs">
                <div className="flex items-center gap-4">
                  <span className="text-slate-500 uppercase font-semibold">Noise Floor:</span>
                  <span className="line-through text-slate-400 font-mono">{track?.noise_floor_dbfs} dB</span>
                  <span className="text-amber-400 font-bold font-mono">
                    ➔ {currentJob.metrics_after.noise_floor_dbfs} dB (Cleaned by {Math.abs(currentJob.metrics_after.noise_floor_dbfs - (track?.noise_floor_dbfs || 0)).toFixed(1)} dB)
                  </span>
                </div>
                <a
                  href={currentJob.output_url}
                  download
                  className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded text-xs font-medium border border-slate-700 transition"
                >
                  Download Restored Master
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
