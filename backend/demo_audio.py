"""
Procedural Demo Audio Generator for VIDA
Generates a synthwave / electronic beat track with punchy kicks, snares,
deep bass, and arpeggiated synth leads using Python's standard library.
Ensures VIDA works immediately even without user-supplied files.
"""

import os
import wave
import struct
import math
import random

def generate_demo_track(output_path: str = "uploads/demo_track.wav", duration_sec: float = 12.0, sr: int = 44100):
    """Generates a high-energy 120 BPM synthwave/EDM demo audio file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    bpm = 124.0
    beat_dur = 60.0 / bpm
    total_samples = int(duration_sec * sr)
    buffer = [0.0] * total_samples

    def add_kick(start_time):
        kick_dur = 0.28
        start_idx = int(start_time * sr)
        n_samples = min(int(kick_dur * sr), total_samples - start_idx)
        for i in range(n_samples):
            t = i / sr
            # Pitch drop from 160Hz down to 42Hz
            freq = 160.0 * math.exp(-t * 26.0) + 42.0
            env = math.exp(-t * 12.0)
            val = math.sin(2.0 * math.pi * freq * t) * env * 0.75
            buffer[start_idx + i] += val

    def add_snare(start_time):
        snare_dur = 0.22
        start_idx = int(start_time * sr)
        n_samples = min(int(snare_dur * sr), total_samples - start_idx)
        for i in range(n_samples):
            t = i / sr
            tone = math.sin(2.0 * math.pi * 180.0 * t) * math.exp(-t * 18.0) * 0.35
            noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 22.0) * 0.45
            buffer[start_idx + i] += tone + noise

    def add_hihat(start_time):
        hh_dur = 0.06
        start_idx = int(start_time * sr)
        n_samples = min(int(hh_dur * sr), total_samples - start_idx)
        for i in range(n_samples):
            t = i / sr
            noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 60.0) * 0.2
            buffer[start_idx + i] += noise

    def add_synth_note(start_time, freq, dur=0.18):
        start_idx = int(start_time * sr)
        n_samples = min(int(dur * sr), total_samples - start_idx)
        for i in range(n_samples):
            t = i / sr
            env = math.exp(-t * 6.0)
            # Sawtooth-like rich harmonics
            h1 = math.sin(2.0 * math.pi * freq * t) * 0.35
            h2 = math.sin(2.0 * math.pi * freq * 2.0 * t) * 0.18
            h3 = math.sin(2.0 * math.pi * freq * 3.0 * t) * 0.09
            buffer[start_idx + i] += (h1 + h2 + h3) * env

    def add_bass_note(start_time, freq, dur=0.45):
        start_idx = int(start_time * sr)
        n_samples = min(int(dur * sr), total_samples - start_idx)
        for i in range(n_samples):
            t = i / sr
            env = math.exp(-t * 3.5)
            val = (math.sin(2.0 * math.pi * freq * t) + 0.3 * math.sin(2.0 * math.pi * freq * 2.0 * t)) * env * 0.5
            buffer[start_idx + i] += val

    # Sequence beats
    cur_time = 0.0
    step = beat_dur / 4.0  # 16th note
    step_idx = 0

    scale_freqs = [220.0, 261.63, 293.66, 329.63, 392.0, 440.0, 523.25]
    bass_scale = [55.0, 65.4, 73.4, 82.4]

    while cur_time < duration_sec - 0.2:
        # Drum pattern
        if step_idx % 4 == 0:
            # Beat 1 & 3: Kick
            if (step_idx // 4) % 2 == 0:
                add_kick(cur_time)
            # Beat 2 & 4: Snare
            else:
                add_snare(cur_time)

        # Hi-hats on 8th notes
        if step_idx % 2 == 0:
            add_hihat(cur_time)

        # Arpeggiated melody
        note_freq = scale_freqs[(step_idx * 2) % len(scale_freqs)]
        add_synth_note(cur_time, note_freq, dur=0.14)

        # Bassline
        if step_idx % 4 == 0:
            bass_f = bass_scale[(step_idx // 8) % len(bass_scale)]
            add_bass_note(cur_time, bass_f, dur=beat_dur * 0.9)

        cur_time += step
        step_idx += 1

    # Normalize audio
    max_val = max(max(map(abs, buffer)), 1e-5)
    scale = 0.92 / max_val

    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        packed_frames = bytearray()
        for sample in buffer:
            norm_sample = max(-1.0, min(1.0, sample * scale))
            int_sample = int(norm_sample * 32767.0)
            packed_frames.extend(struct.pack("<h", int_sample))
        wav_file.writeframes(packed_frames)

    return output_path


def generate_khmer_60s_demo(output_path: str = "uploads/demo_sinisamut.wav", duration_sec: float = 18.0, sr: int = 44100):
    """Generates an authentic 1960s Cambodian ballad / rumba instrumental track (86 BPM)
    reminiscent of Sinn Sisamouth's legendary masterpieces like 'Champa Battambang'.
    Features warm acoustic guitar arpeggios, vintage warm bass, Latin-Khmer percussion,
    melancholic flute motif, and subtle authentic vinyl warmth.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    bpm = 86.0
    beat_dur = 60.0 / bpm
    total_samples = int(duration_sec * sr)
    buffer = [0.0] * total_samples

    # Subtle vinyl analog noise / crackle
    for i in range(total_samples):
        # Warm low-frequency floor rumble
        buffer[i] += (random.random() * 2.0 - 1.0) * 0.003
        # Occasional microscopic dust crackle
        if random.random() < 0.0003:
            crackle_val = (random.random() * 2.0 - 1.0) * 0.02
            buffer[i] += crackle_val

    def add_soft_kick(start_time):
        kick_dur = 0.22
        start_idx = int(start_time * sr)
        n = min(int(kick_dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            freq = 95.0 * math.exp(-t * 18.0) + 48.0
            env = math.exp(-t * 9.0)
            buffer[start_idx + i] += math.sin(2.0 * math.pi * freq * t) * env * 0.65

    def add_rimshot(start_time):
        dur = 0.12
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            tone = math.sin(2.0 * math.pi * 380.0 * t) * math.exp(-t * 28.0) * 0.35
            snap = (random.random() * 2.0 - 1.0) * math.exp(-t * 40.0) * 0.3
            buffer[start_idx + i] += tone + snap

    def add_clave(start_time):
        dur = 0.08
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            val = math.sin(2.0 * math.pi * 2200.0 * t) * math.exp(-t * 55.0) * 0.22
            buffer[start_idx + i] += val

    def add_shaker(start_time):
        dur = 0.07
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 45.0) * 0.12
            buffer[start_idx + i] += noise

    def add_guitar_pluck(start_time, freq, dur=0.55, amp=0.25):
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 4.2)
            f1 = math.sin(2.0 * math.pi * freq * t) * 0.55
            f2 = math.sin(2.0 * math.pi * freq * 2.0 * t) * 0.28
            f3 = math.sin(2.0 * math.pi * freq * 3.0 * t) * 0.12
            buffer[start_idx + i] += (f1 + f2 + f3) * env * amp

    def add_warm_bass(start_time, freq, dur=0.85):
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 2.2)
            val = (math.sin(2.0 * math.pi * freq * t) + 0.25 * math.sin(2.0 * math.pi * freq * 2.0 * t)) * env * 0.55
            buffer[start_idx + i] += val

    def add_khmer_flute(start_time, freq, dur=0.8, amp=0.28):
        start_idx = int(start_time * sr)
        n = min(int(dur * sr), total_samples - start_idx)
        for i in range(n):
            t = i / sr
            # Smooth attack and gentle release with vibrato
            attack = min(1.0, t / 0.06)
            decay = math.exp(-max(0.0, t - 0.3) * 2.5)
            vibrato = 1.0 + 0.012 * math.sin(2.0 * math.pi * 5.2 * t) if t > 0.15 else 1.0
            cur_freq = freq * vibrato
            harm = (math.sin(2.0 * math.pi * cur_freq * t) +
                    0.28 * math.sin(2.0 * math.pi * cur_freq * 2.0 * t) +
                    0.12 * math.sin(2.0 * math.pi * cur_freq * 3.0 * t))
            buffer[start_idx + i] += harm * attack * decay * amp

    # Chords (D minor, G minor, A major, D minor)
    # Dm: D3, F3, A3, D4
    # Gm: G2, D3, G3, Bb3
    # A7: A2, E3, A3, C#4
    chords = [
        {"root": 73.42, "notes": [220.0, 261.63, 293.66, 349.23]},  # Dm (D, F, A, D)
        {"root": 73.42, "notes": [220.0, 261.63, 293.66, 349.23]},  # Dm
        {"root": 98.00, "notes": [196.0, 293.66, 392.00, 466.16]},  # Gm (G, Bb, D)
        {"root": 110.00, "notes": [220.0, 277.18, 329.63, 440.00]}  # A7 (A, C#, E)
    ]

    # Legendary 60s Khmer Melodic Motif (inspired by Sinn Sisamouth ballads)
    # D minor pentatonic: D4 (293.66), F4 (349.23), G4 (392.0), A4 (440.0), C5 (523.25), D5 (587.33)
    melody = [
        # Measure 1: ឱ! ដួងចំប៉ា...
        (0.8, 293.66, 0.6), (1.4, 349.23, 0.5), (1.9, 392.00, 0.8), (2.8, 440.00, 0.6), (3.4, 392.00, 1.1),
        # Measure 2: ឆ្លងស្ទឹងសង្កែ...
        (5.0, 392.00, 0.5), (5.5, 440.00, 0.6), (6.2, 523.25, 0.7), (6.9, 440.00, 0.5), (7.4, 349.23, 0.6), (8.0, 293.66, 1.0),
        # Measure 3: រៀមនឹកស្រណោះ...
        (9.2, 349.23, 0.5), (9.7, 392.00, 0.5), (10.2, 440.00, 0.9), (11.2, 523.25, 0.7), (12.0, 440.00, 1.0),
        # Measure 4: ក្រោមម្លប់ចំប៉ា...
        (13.5, 392.00, 0.6), (14.1, 349.23, 0.6), (14.8, 293.66, 0.9), (15.8, 261.63, 0.6), (16.4, 293.66, 1.3)
    ]

    for (m_time, m_freq, m_dur) in melody:
        if m_time + m_dur < duration_sec:
            add_khmer_flute(m_time, m_freq, dur=m_dur)

    # Rumba drum & guitar accompaniment loop
    cur_time = 0.0
    measure = 0
    step = beat_dur / 4.0  # 16th note
    step_idx = 0

    while cur_time < duration_sec - 0.2:
        chord = chords[(step_idx // 16) % len(chords)]

        # Soft Rumba percussion
        beat_in_measure = (step_idx // 4) % 4
        sub_beat = step_idx % 4

        # Kick on beat 1 & subtle pickup on 3-and
        if sub_beat == 0 and beat_in_measure in [0, 2]:
            add_soft_kick(cur_time)
        elif sub_beat == 2 and beat_in_measure == 3:
            add_soft_kick(cur_time)

        # Clave pattern: 3-2 Rumba clave (1, 1-and, 2-and, 3, 4)
        if step_idx % 16 in [0, 3, 6, 10, 12]:
            add_clave(cur_time)

        # Gentle rimshot on beat 4
        if sub_beat == 0 and beat_in_measure == 3:
            add_rimshot(cur_time)

        # Constant soft shaker on 8th notes
        if step_idx % 2 == 0:
            add_shaker(cur_time)

        # Acoustic guitar fingerpicking arpeggio
        note_idx = (step_idx % 4)
        note_f = chord["notes"][note_idx]
        add_guitar_pluck(cur_time, note_f, dur=0.45, amp=0.22)

        # Warm double-bass on beats 1 and 3
        if sub_beat == 0 and beat_in_measure == 0:
            add_warm_bass(cur_time, chord["root"], dur=beat_dur * 1.5)
        elif sub_beat == 0 and beat_in_measure == 2:
            add_warm_bass(cur_time, chord["root"] * 1.5, dur=beat_dur * 1.2)

        cur_time += step
        step_idx += 1

    # Normalize audio nicely
    max_val = max(max(map(abs, buffer)), 1e-5)
    scale = 0.88 / max_val

    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        packed_frames = bytearray()
        for sample in buffer:
            norm_sample = max(-1.0, min(1.0, sample * scale))
            int_sample = int(norm_sample * 32767.0)
            packed_frames.extend(struct.pack("<h", int_sample))
        wav_file.writeframes(packed_frames)

    return output_path


if __name__ == "__main__":
    generate_demo_track()
    generate_khmer_60s_demo()
