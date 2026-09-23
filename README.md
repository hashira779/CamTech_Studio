# CamTech_Studio
## VIDA — Visual Intelligent Dynamic Audio-Video Studio

> **DROP A SONG OR YOUTUBE LINK → AI AUTOMATICALLY CREATES A COMPLETE, POLISHED LYRIC MUSIC VIDEO.**

**VIDA — Visual Intelligent Dynamic Audio-Video Studio** is a professional Windows desktop application engineered with high-performance **Python 3.12 + FastAPI + Web Audio 60 FPS Canvas Engine + FFmpeg + yt-dlp**. Designed around the philosophy of **AUTO PERFECT**, it delivers an end-to-end automated pipeline requiring zero manual editing from the user, while preserving deep visual, audio, and kinetic typography customization.

---

## 🌟 Core Highlights

### 1. One-Click Auto Mode
- **Zero-Friction Drop Zone**: Supports `MP3`, `WAV`, `M4A`, `FLAC`, `AAC`, and `MP4` with audio.
- **12-Step Visual Progress Pipeline**:
  1. Analyzing song
  2. Detecting vocals
  3. Transcribing Khmer lyrics
  4. Correcting Khmer lyrics
  5. Synchronizing lyrics
  6. Detecting beats
  7. Detecting song sections
  8. Planning visuals
  9. Creating lyric animations
  10. Rendering video
  11. Final quality check
  12. Complete

### 2. Auto Perfect Khmer Lyrics
- **Khmer Unicode & Coeng Subscript Protection**: Respects Khmer orthography, preserving base consonants (`ក`, `ល`, `ម`, `ឃ`), sub-consonants (`ជើង` `\u17D2`), and vowels with intelligent syllable segmentation and zero-width spaces (`\u200B`).
- **Word & Line Confidence Scoring**:
  ```text
  ខ្ញុំស្រឡាញ់អ្នក
  ██████████████
  98% confidence

  ខ្ញុំ [ស្រឡាញ់] អ្នក
         ⚠ 71%
  ```
- **Double-Check Lyrics Verification**: Compares raw vocal frequency energy (300 Hz – 3,400 Hz) against transcribed segments, detecting missing words, timing drift, and repeated chorus sections, repairing boundaries automatically.

### 3. 9 Auto Khmer Karaoke Animation Styles
1. **Karaoke**: Classic fill-sweep progress on active word.
2. **Word Highlight**: Active word glow with smooth color ramp.
3. **Glow**: Soft neon aura on active singing word.
4. **Bounce**: Kinetic upward bounce and scale on syllable onset.
5. **Typewriter**: Real-time character-by-character Khmer reveal.
6. **Fade**: Gentle opacity transitions across lyrical phrases.
7. **Modern Khmer Pop**: High-contrast vibrant pop aesthetics with micro-scaling.
8. **Cinematic**: Elegant golden gradient typography with letter-spacing.
9. **Emotional Ballad**: Ambient trailing glow and soft breathing motion.

### 4. 18 Visual Styles + Custom AI Director
- **18 Curated Styles**: Khmer Cinematic, Romantic, Sad, Emotional, Love, Traditional Khmer, Cambodian Countryside, Phnom Penh, Night City, Luxury, Travel, Nature, Wedding, Festival, Dark Cinematic, Dreamy, Anime-Inspired, Abstract, Music Performance.
- **Natural Language Prompt Director**: e.g. *"Romantic Khmer song about missing someone at night in Phnom Penh."*
- **Auto Song Understanding**: Segments track into `INTRO`, `VERSE`, `PRE-CHORUS`, `CHORUS`, `BRIDGE`, `FINAL CHORUS`, and `OUTRO` with dynamic pacing (slow zooms for ballad intros, rapid beat cuts for climaxes).

### 5. User Photos & Videos Ingestion
- Ingest collections (e.g. 20 photos + 5 videos + 1 Khmer song).
- Automatic smart framing, Ken Burns pan & zoom, beat-synced shot transitions, and lyric overlay placement.

### 6. ✨ AUTO PERFECT Quality Control Engine
- One-click comprehensive quality-control audit inspecting:
  - Khmer transcription & orthography context
  - Word & line timing drift
  - Karaoke synchronization alignment
  - Safe-area margins for subtitles
  - Beat transition synchronization
  - Audio/video timing phase
  - Title & artist card placement
- Automatically repairs identified defects without altering locked sections.

### 7. 🔒 Keep This Lock System & Granular Regeneration
- Lock any section, shot, or lyric line (`🔒 Keep This`).
- Granular regeneration actions:
  - 🔄 Regenerate lyrics
  - 🔄 Regenerate timing
  - 🔄 Regenerate visuals
  - 🔄 Regenerate chorus
  - 🔄 Regenerate transition
  - 🔄 Regenerate title
  - 🔄 Regenerate entire video

### 8. Auto Title Cards & AI Thumbnail Generator
- **Opening Title**: Elegant animated Khmer typography displaying `[SONG TITLE]` and `[ARTIST NAME]`.
- **Thumbnail Studio**: Generates 3 distinct composition concepts (Centered Artist, Typography Split, Cinematic Wide) ready for YouTube and social media.

### 9. Social Media Multi-Format Export
- **16:9 Landscape**: YouTube, TV displays (1920x1080 / 3840x2160).
- **9:16 Vertical**: TikTok, YouTube Shorts, Instagram Reels (1080x1920) with automatic safe-area reframing (protecting top status icons and bottom captions).
- **1:1 Square**: Instagram feed (1080x1080).

---

## 🚀 Quick Start (Windows Desktop)

### Double-Click Launcher
Double-click `run_kmvm.bat` in the project root:
```bat
run_kmvm.bat
```

### Python Command
```powershell
.\venv\Scripts\python.exe -m kmvm.main
```

---

## 📁 Modular AI Architecture

Clean C++ and Python interfaces under `/ai`:

```text
/ai
  /speech          # ISpeechRecognizer: Local Whisper / Cloud speech-to-text
  /lyrics          # ILyricProcessor: Khmer Unicode segmentation & confidence scoring
  /alignment       # IAudioAligner: Double-check verification pass & vocal alignment
  /beat            # IBeatDetector: Spectral flux BPM & beat onset tracking
  /song_structure  # ISongSegmenter: Intro, Verse, Chorus, Bridge, Outro detection
  /mood            # IMoodClassifier: Energy, valence, tempo, and mood labeling
  /visual_planner  # ISceneDirector: 18 visual styles & custom prompt parser
  /editing         # ICinematicEditor: Beat-synced cuts, transitions, Ken Burns motion
  /subtitles       # ISubtitleEngine: 9 karaoke styles & safe-area validation
  /thumbnail       # IThumbnailGenerator: 3-concept thumbnail generation
  /reframe         # IReframeEngine: 16:9, 9:16 Shorts, and 1:1 safe framing
```

---

## 🛠️ C++ Qt 6 & CMake Build

```powershell
cmake -B build -S . -DCMAKE_PREFIX_PATH="C:/Qt/6.5.0/msvc2019_64"
cmake --build build --config Release
```

---

## 🧪 Automated Tests

Run the full end-to-end integration test suite:
```powershell
.\venv\Scripts\python.exe tests/test_kmvm.py
```

Tests verify:
- Khmer Unicode Coeng clustering & syllable segmentation
- Audio analysis, BPM, vocal energy & song structure detection
- Visual shot planning with Ken Burns effects
- 3-concept thumbnail generation
- Full 1080p video export via FFmpeg pipe with karaoke rendering

---

## 📄 License
MIT License. Khmer Music Video Maker (KMVM).
