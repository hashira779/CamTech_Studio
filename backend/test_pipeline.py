"""
Automated Test Pipeline for VIDA
Validates:
1. Procedural demo audio generation
2. Audio spectrum & beat onset analysis
3. VideoRenderer frame generation and FFmpeg streaming pipe
4. Output MP4 integrity
"""

import os
import sys

# Ensure project root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.demo_audio import generate_demo_track
from backend.audio_analyzer import AudioAnalyzer
from backend.renderer import VideoRenderer
from backend.lyric_engine import parse_lrc_file

def run_tests():
    print(">>> [TEST 1/4] Generating 5s test audio track...")
    test_audio = os.path.join(BASE_DIR, "uploads", "test_beat.wav")
    generate_demo_track(test_audio, duration_sec=5.0)
    assert os.path.exists(test_audio), "Audio generation failed"
    print(f"    OK: Generated {test_audio} ({os.path.getsize(test_audio)} bytes)")

    print(">>> [TEST 2/4] Testing AudioAnalyzer FFT & Beat Detection...")
    analyzer = AudioAnalyzer(test_audio, fps=30, num_bars=32)
    analysis = analyzer.analyze()
    assert analysis["spectrum"].shape == (analysis["total_frames"], 32), "Spectrum shape mismatch"
    assert len(analysis["bass"]) == analysis["total_frames"], "Bass curve mismatch"
    print(f"    OK: Computed {analysis['total_frames']} frames of 32-band spectrum and bass signal")

    print(">>> [TEST 3/4] Testing LRC Parser & Word Timestamps...")
    sample_lrc = "[00:01.00] Electric city glowing\n[00:03.50] Bass beats dropping high"
    parsed_lyrics = parse_lrc_file(sample_lrc)
    assert len(parsed_lyrics) == 2, "LRC line count mismatch"
    assert len(parsed_lyrics[0]["words"]) > 0, "Word interpolation failed"
    print(f"    OK: Parsed {len(parsed_lyrics)} lyric lines with word-level interpolation")

    print(">>> [TEST 4/4] Testing VideoRenderer Full 1080p MP4 Pipe...")
    test_output = os.path.join(BASE_DIR, "outputs", "test_video.mp4")
    if os.path.exists(test_output):
        os.remove(test_output)

    renderer = VideoRenderer(
        audio_path=test_audio,
        output_path=test_output,
        width=1920,
        height=1080,
        fps=30,
        theme="trap_circle",
        palette_name="cyberpunk",
        song_title="Cyber Test",
        artist_name="VIDA Studio",
        lyrics_data=parsed_lyrics,
        bar_count=32
    )

    rendered_path = renderer.render_video()
    assert os.path.exists(rendered_path), "Rendered video file not found"
    assert os.path.getsize(rendered_path) > 10000, f"Video file too small ({os.path.getsize(rendered_path)} bytes)"
    print(f"    OK: Successfully rendered video {rendered_path} ({os.path.getsize(rendered_path)} bytes)")

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! VIDA IS FULLY OPERATIONAL. <<<")

if __name__ == "__main__":
    run_tests()
