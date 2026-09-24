"""
Unit tests for Stage 3 & Stage 3.5 improvements:
- Khmer Unicode normalization
- Common spelling correction
- Repetition suppression
- Word segmentation with khmer-nltk
- Two-pass transcription parameter validation
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stages.stage3_5_postprocess import (
    normalize_unicode,
    remove_repetitions,
    correct_spelling,
    segment_words,
    post_process_khmer_text,
    post_process_segments,
)
import config


class TestKhmerPostProcess(unittest.TestCase):

    def test_unicode_normalization(self):
        raw = "  បង  ស្រឡាញ់  អូន...  "
        clean = normalize_unicode(raw)
        self.assertEqual(clean, "បង ស្រឡាញ់ អូន.")

    def test_spelling_corrections(self):
        # "បេស្ដូង" -> "បេះដូង", "ស្រាលាញ" -> "ស្រឡាញ់"
        raw = "បេស្ដូង បង ស្រាលាញ អូន"
        corrected = correct_spelling(raw)
        self.assertEqual(corrected, "បេះដូង បង ស្រឡាញ់ អូន")

    def test_repetition_removal(self):
        # Repeated phrase hallucination loop
        raw = "បងស្រឡាញ់អូន បងស្រឡាញ់អូន បងស្រឡាញ់អូន"
        cleaned = remove_repetitions(raw, max_consecutive_repeats=2)
        # Should reduce repeated runs
        self.assertNotIn("បងស្រឡាញ់អូន បងស្រឡាញ់អូន បងស្រឡាញ់អូន", cleaned)

    def test_word_segmentation(self):
        raw = "គាត់ទៅផ្សារ"
        tokens = segment_words(raw)
        self.assertTrue(len(tokens) >= 2)
        self.assertIn("ផ្សារ", tokens)

    def test_post_process_segments(self):
        mock_segments = [
            {
                "id": 1,
                "start": 0.0,
                "end": 2.5,
                "text": "  បេស្ដូង របស់បង  ",
                "words": [
                    {"word": "បេស្ដូង", "start": 0.0, "end": 1.0, "probability": 0.8},
                    {"word": "របស់បង", "start": 1.0, "end": 2.5, "probability": 0.9},
                ],
                "avg_logprob": -1.2,
                "no_speech_prob": 0.1,
                "compression_ratio": 1.1,
            }
        ]
        processed = post_process_segments(mock_segments)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["text"], "បេះដូង របស់បង")
        self.assertEqual(processed[0]["words"][0]["word"], "បេះដូង")

    def test_config_values(self):
        self.assertEqual(config.WHISPER_MODEL, "large-v3-turbo")
        self.assertTrue(config.WHISPER_TWO_PASS)
        self.assertIn("ទំនុកច្រៀងខ្មែរ", config.WHISPER_INITIAL_PROMPT)


if __name__ == "__main__":
    unittest.main()
