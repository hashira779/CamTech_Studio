"""
Audio Analyzer Module for VIDA
Extracts frequency spectrum, beat onsets, and bass energy per video frame
using fast FFT and physics-based attack/decay smoothing.
"""

import os
import subprocess
import numpy as np

def get_ffmpeg_exe():
    """Locate ffmpeg executable using imageio_ffmpeg or system path."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def decode_audio_to_numpy(audio_path: str, target_sr: int = 22050) -> tuple[np.ndarray, int, float]:
    """
    Decodes any audio file (MP3, WAV, FLAC, M4A, OGG) to mono float32 numpy array
    via ffmpeg pipe, ensuring maximum compatibility without format restrictions.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    ffmpeg_exe = get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-i", audio_path,
        "-vn",
        "-ac", "1",               # Mono
        "-ar", str(target_sr),    # Sample rate
        "-f", "f32le",            # 32-bit float Little-Endian
        "-"
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_bytes, _ = proc.communicate()
        if proc.returncode != 0 or len(raw_bytes) == 0:
            raise RuntimeError(f"FFmpeg failed to decode audio: {audio_path}")

        audio_data = np.frombuffer(raw_bytes, dtype=np.float32)
        duration = len(audio_data) / target_sr
        return audio_data, target_sr, duration
    except Exception as e:
        # Fallback to soundfile if available
        try:
            import soundfile as sf
            data, sr = sf.read(audio_path)
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            duration = len(data) / sr
            return data.astype(np.float32), sr, duration
        except Exception:
            raise RuntimeError(f"Failed to load audio {audio_path}: {e}")

class AudioAnalyzer:
    """Analyzes audio to produce frame-by-frame spectrum and beat-reactive signals."""

    def __init__(self, audio_path: str, fps: int = 60, num_bars: int = 64, target_sr: int = 22050):
        self.audio_path = audio_path
        self.fps = fps
        self.num_bars = num_bars
        self.target_sr = target_sr
        self.audio_data, self.sr, self.duration = decode_audio_to_numpy(audio_path, target_sr)
        self.total_frames = int(np.ceil(self.duration * self.fps))

    def analyze(
        self,
        min_freq: float = 30.0,
        max_freq: float = 12000.0,
        smoothing_attack: float = 0.85,
        smoothing_decay: float = 0.70,
        bass_boost: float = 1.3
    ) -> dict:
        """
        Computes log-spaced frequency spectrum for every video frame,
        plus bass intensity and beat onsets.
        """
        n_fft = 2048
        hop_samples = int(self.sr / self.fps)
        window = np.hanning(n_fft)

        # Precompute logarithmic frequency bins
        # Mel/Log scale gives natural musical perception (more bars in bass & mids)
        log_freq_bins = np.logspace(np.log10(min_freq), np.log10(max_freq), self.num_bars + 1)
        freq_step = (self.sr / 2.0) / (n_fft // 2)
        fft_freqs = np.linspace(0, self.sr / 2.0, n_fft // 2 + 1)

        # Allocate arrays
        spectrum_matrix = np.zeros((self.total_frames, self.num_bars), dtype=np.float32)
        bass_curve = np.zeros(self.total_frames, dtype=np.float32)
        onset_curve = np.zeros(self.total_frames, dtype=np.float32)

        prev_spectrum = np.zeros(self.num_bars, dtype=np.float32)
        prev_fft = None

        # Pad audio for edge frames
        pad_len = n_fft // 2
        padded_audio = np.pad(self.audio_data, (pad_len, pad_len), mode="constant")

        # Bass band: 30Hz - 160Hz
        bass_mask = (fft_freqs >= 30) & (fft_freqs <= 160)

        for f_idx in range(self.total_frames):
            center_sample = f_idx * hop_samples + pad_len
            start = center_sample - n_fft // 2
            end = start + n_fft

            if end > len(padded_audio):
                break

            frame_audio = padded_audio[start:end] * window
            fft_mag = np.abs(np.fft.rfft(frame_audio))

            # Spectral flux / Onset detection
            if prev_fft is not None:
                flux = np.sum(np.maximum(0, fft_mag - prev_fft))
                onset_curve[f_idx] = flux
            prev_fft = fft_mag

            # Bass energy calculation
            bass_energy = np.mean(fft_mag[bass_mask]) if np.any(bass_mask) else 0.0
            bass_curve[f_idx] = bass_energy

            # Group FFT bins into musical frequency bars
            raw_bars = np.zeros(self.num_bars, dtype=np.float32)
            for b in range(self.num_bars):
                low_f = log_freq_bins[b]
                high_f = log_freq_bins[b + 1]
                idx_low = max(0, int(low_f / freq_step))
                idx_high = min(len(fft_mag) - 1, int(high_f / freq_step))
                if idx_high <= idx_low:
                    idx_high = idx_low + 1

                val = np.mean(fft_mag[idx_low:idx_high + 1])
                # Equal loudness contour approximation (boost bass/highs slightly)
                eq_factor = 1.0 + (1.0 - (b / self.num_bars)) * 0.5
                raw_bars[b] = val * eq_factor

            # Convert to decibels with floor
            db_bars = 20 * np.log10(np.maximum(raw_bars, 1e-5))
            # Normalize between -60dB and 0dB to [0.0, 1.0]
            norm_bars = np.clip((db_bars + 60.0) / 60.0, 0.0, 1.0)
            norm_bars = np.power(norm_bars, 1.8) * bass_boost

            # Physics-based attack & decay smoothing
            smooth_bars = np.zeros(self.num_bars, dtype=np.float32)
            for b in range(self.num_bars):
                if norm_bars[b] > prev_spectrum[b]:
                    # Instant punchy rise
                    smooth_bars[b] = prev_spectrum[b] * (1.0 - smoothing_attack) + norm_bars[b] * smoothing_attack
                else:
                    # Smooth falling gravity
                    smooth_bars[b] = prev_spectrum[b] * smoothing_decay

            spectrum_matrix[f_idx] = np.clip(smooth_bars, 0.0, 1.0)
            prev_spectrum = smooth_bars

        # Normalize bass and onset curves
        if np.max(bass_curve) > 0:
            bass_curve = bass_curve / np.percentile(bass_curve, 98)
            bass_curve = np.clip(bass_curve, 0.0, 1.5)
            # Smooth bass curve slightly
            kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
            bass_curve = np.convolve(bass_curve, kernel, mode="same")

        if np.max(onset_curve) > 0:
            onset_curve = onset_curve / np.percentile(onset_curve, 98)
            onset_curve = np.clip(onset_curve, 0.0, 1.5)

        return {
            "duration": self.duration,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "num_bars": self.num_bars,
            "spectrum": spectrum_matrix,
            "bass": bass_curve,
            "onsets": onset_curve
        }
