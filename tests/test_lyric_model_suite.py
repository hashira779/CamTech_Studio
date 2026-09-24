import sys
sys.path.insert(0, ".")

from backend.llm_engine import llm_engine
from backend.lyric_engine import (
    normalize_khmer_orthography,
    clean_khmer_hallucination_loops,
    remove_repetitions,
    tokenize_line_words,
    double_check_lyrics,
    parse_subtitle_content,
    WhisperTranscriber
)

print("=" * 60)
print("TEST 1: Khmer AI Lyric Generation for All 6 Genres")
print("=" * 60)
for genre in ["romantic", "golden_era", "melancholy", "romvong", "modern_pop", "heritage"]:
    res = llm_engine.generate_khmer_lyrics(f"តែងបទ {genre}", genre=genre)
    print(f"[{genre.upper()}] Title: {res['title']} | Lines: {res['count']} | BPM: {res['bpm']}")
    assert res["count"] > 0, "Lines should be generated"
    assert len(res["lyrics_data"]) > 0, "Lyrics data should be populated"
    first_line = res["lyrics_data"][0]
    assert len(first_line["words"]) > 0, "Words should be tokenized"

print("\n" + "=" * 60)
print("TEST 2: Khmer Orthography & Singing Correction")
print("=" * 60)
test_cases = [
    ("បងស្រលាញ់អូន", "បងស្រឡាញ់អូន"),
    ("ស្នេហ៏", "ស្នេហ៍"),
    ("ដួងច័ន្ទ", "ដួងចន្ទ"),
    ("សង្ខារ", "សង្សារ"),
    ("កំសត់", "កម្សត់"),
    ("អនុសាវរីយ៍", "អនុស្សាវរីយ៍"),
]
for raw, expected in test_cases:
    norm = normalize_khmer_orthography(raw)
    print(f"Raw: '{raw}' -> Cleaned: '{norm}' (Expected: '{expected}')")
    assert norm == expected, f"Expected {expected}, got {norm}"

print("\n" + "=" * 60)
print("TEST 3: Repetition Loop and Hallucination Suppression")
print("=" * 60)
loop_raw = "ន្ររនងរានានារានារានានានានានានានានានានានានានានានានានានានានានានានានានានានានានាននានាននាននាននាននាននានននានននានននននននន"
cleaned_loop = clean_khmer_hallucination_loops(loop_raw)
print(f"Hallucination Loop Raw ({len(loop_raw)} chars)")
print(f"Cleaned ({len(cleaned_loop)} chars): '{cleaned_loop}'")
assert len(cleaned_loop) < len(loop_raw) // 2 or cleaned_loop == "", "Loop must be suppressed"

print("\n" + "=" * 60)
print("TEST 4: Linguistic Word & Syllable Tokenization for Karaoke")
print("=" * 60)
sentence = "ផែនដីវិលគ្មានថ្ងៃឈប់ដូចបងនិងអូនស្រឡាញ់គ្នា"
tokens = tokenize_line_words(sentence)
print(f"Sentence: {sentence}")
print(f"Tokenized ({len(tokens)} syllables/words): {tokens}")
assert len(tokens) >= 5, "Khmer sentence must be segmented into words/syllables, not 1 lump"

print("\n" + "=" * 60)
print("TEST 5: WhisperTranscriber Model Size & Defaults")
print("=" * 60)
t = WhisperTranscriber()
print("Default Whisper model size:", t.model_size)
assert t.model_size == "large-v3-turbo", "Default model should be large-v3-turbo"

print("\n" + "=" * 60)
print("TEST 6: Subtitle Parsing & Double-Check Verification API")
print("=" * 60)
lrc_sample = """[ti:Test Song]
[00:05.00]ផែនដីវិលគ្មានថ្ងៃឈប់ដូចបងនិងអូនស្រឡាញ់គ្នា
[00:10.50]រាត្រីស្រស់បំព្រងបំភ្លឺដួងចិត្ត
"""
parsed = parse_subtitle_content(lrc_sample)
verified, report = double_check_lyrics(parsed)
print("Verified report:", report["status"])
assert report["verified"] is True
assert report["total_lines"] == 2
print("All 6 test suites passed with 100% precision!")
