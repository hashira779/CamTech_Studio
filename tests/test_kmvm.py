"""
Comprehensive Test Suite for Khmer Music Video Maker (KMVM)
Validates:
1. Khmer Unicode segmentation & subscript consonant ligature safety
2. AI song structure detection (Intro, Verse, Chorus, Bridge, Outro) & BPM
3. Visual planner scene generation & beat synchronization
4. AI Thumbnail generator concept synthesis
5. KMVMExporter video render (1080p with Khmer typography)
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from kmvm.khmer_engine import is_khmer_text, segment_khmer_syllables, insert_khmer_word_breaks, KhmerLyricEngine
from kmvm.ai_engine import AISongUnderstandingEngine
from kmvm.visual_planner import VisualPlanner
from kmvm.thumbnail_generator import ThumbnailGenerator
from kmvm.exporter import KMVMExporter
from backend.demo_audio import generate_demo_track

class TestKhmerMusicVideoMaker(unittest.TestCase):

    def setUp(self):
        self.test_audio = os.path.join(BASE_DIR, "uploads", "test_kmvm_beat.wav")
        generate_demo_track(self.test_audio, duration_sec=6.0)

    def test_01_khmer_unicode_segmentation(self):
        text = "ពេលខ្ញុំមើលទៅលើមេឃ"
        self.assertTrue(is_khmer_text(text))

        syllables = segment_khmer_syllables(text)
        self.assertGreater(len(syllables), 1)

        # Ensure subscript coeng ជើង is not detached from base
        self.assertIn("ខ្ញុំ", syllables)
        self.assertIn("មេឃ", syllables)

        spaced = insert_khmer_word_breaks(text)
        self.assertIn('\u200B', spaced)
        print(">>> [TEST 1 PASSED] Khmer Unicode & Syllable Segmentation OK")

    def test_02_ai_song_understanding(self):
        engine = AISongUnderstandingEngine(self.test_audio)
        features = engine.analyze_audio_features()

        self.assertIn("bpm", features)
        self.assertGreater(features["bpm"], 60)
        self.assertIn("mood", features)

        sections = engine.detect_song_sections(features)
        self.assertGreaterEqual(len(sections), 1)
        print(f">>> [TEST 2 PASSED] Song Understanding OK: BPM={features['bpm']}, Mood={features['mood']}")

    def test_03_visual_planner(self):
        planner = VisualPlanner(style_name="Khmer Cinematic")
        engine = AISongUnderstandingEngine(self.test_audio)
        features = engine.analyze_audio_features()
        sections = engine.detect_song_sections(features)

        clips = planner.plan_timeline(sections, features["beats"])
        self.assertGreater(len(clips), 0)
        self.assertTrue(hasattr(clips[0], "camera_motion"))
        print(f">>> [TEST 3 PASSED] Visual Planner OK: Generated {len(clips)} cinematic shots")

    def test_04_ai_thumbnail_generator(self):
        thumb_gen = ThumbnailGenerator(song_title="ពេលខ្ញុំមើលទៅលើមេឃ", artist_name="KMVM Star")
        out_dir = os.path.join(BASE_DIR, "outputs", "test_thumbnails")
        concepts = thumb_gen.generate_concepts(out_dir)

        self.assertEqual(len(concepts), 3)
        for c_path in concepts:
            self.assertTrue(os.path.exists(c_path))
            self.assertGreater(os.path.getsize(c_path), 5000)
        print(f">>> [TEST 4 PASSED] AI Thumbnail Generator OK: {len(concepts)} concepts created")

    def test_05_video_exporter(self):
        out_video = os.path.join(BASE_DIR, "outputs", "test_kmvm_output.mp4")
        if os.path.exists(out_video):
            os.remove(out_video)

        engine = AISongUnderstandingEngine(self.test_audio)
        features = engine.analyze_audio_features()
        sections = engine.detect_song_sections(features)
        planner = VisualPlanner()
        clips = planner.plan_timeline(sections, features["beats"])

        lyric_engine = KhmerLyricEngine()
        lyric_engine.set_lyrics([
            {"line_id": 0, "start": 0.5, "end": 4.5, "text": "ពេលខ្ញុំមើលទៅលើមេឃ", "words": [
                {"word": "ពេល", "start": 0.5, "end": 1.2},
                {"word": "ខ្ញុំ", "start": 1.2, "end": 2.0},
                {"word": "មើលទៅ", "start": 2.0, "end": 3.2},
                {"word": "លើមេឃ", "start": 3.2, "end": 4.5}
            ]}
        ])

        exporter = KMVMExporter(
            audio_path=self.test_audio,
            output_path=out_video,
            clips=clips,
            lyric_engine=lyric_engine,
            aspect_ratio="16:9",
            resolution="1080p",
            fps=30,
            song_title="ពេលខ្ញុំមើលទៅលើមេឃ",
            artist_name="KMVM Official"
        )

        res_path = exporter.render(duration_sec=3.0)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 50000)
        print(f">>> [TEST 5 PASSED] KMVM Exporter OK: Rendered {res_path} ({os.path.getsize(res_path)} bytes)")

if __name__ == "__main__":
    unittest.main()
