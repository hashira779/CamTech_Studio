"""
VIDA CLI — Command Line Automation Tool
Enables automated batch rendering of music videos with audio spectrums
and synchronized Whisper AI lyrics from scripts and terminal.
"""

import os
import sys
import argparse
from backend.renderer import VideoRenderer
from backend.lyric_engine import WhisperTranscriber, parse_lrc_file

def main():
    parser = argparse.ArgumentParser(
        description="VIDA CLI — Batch Audio-to-Video Automation Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--audio", "-a", required=True, help="Path to input audio file (MP3, WAV, FLAC, M4A)")
    parser.add_argument("--output", "-o", default="output.mp4", help="Path for generated video output")
    parser.add_argument("--theme", "-t", choices=["trap_circle", "neon_bars", "horizon_wave", "ocean_wave", "spectrum"], default="trap_circle", help="Visualizer style")
    parser.add_argument("--palette", "-p", choices=["cyberpunk", "sunset", "matrix", "electric", "angkor", "bloodmoon", "pastel", "monochrome"], default="cyberpunk", help="Color palette")
    parser.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9", help="Video aspect ratio (16:9 for YouTube, 9:16 for Shorts)")
    parser.add_argument("--fps", type=int, choices=[30, 60], default=60, help="Output frame rate")
    parser.add_argument("--transcribe", action="store_true", help="Auto-transcribe lyrics using Whisper AI")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small"], help="Whisper model size")
    parser.add_argument("--lrc", help="Path to LRC lyrics file to sync")
    parser.add_argument("--bg", help="Path to custom background image")
    parser.add_argument("--logo", help="Path to center logo/cover image")
    parser.add_argument("--title", default="VIDA Visualizer", help="Song title to display")
    parser.add_argument("--artist", default="Official Audio", help="Artist name to display")
    parser.add_argument("--bars", type=int, default=64, help="Number of frequency spectrum bars")
    parser.add_argument("--bass", type=float, default=1.3, help="Bass reactivity scale")

    args = parser.parse_args()

    if not os.path.exists(args.audio):
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)

    lyrics_data = []

    # 1. Lyric Handling
    if args.lrc and os.path.exists(args.lrc):
        print(f"Parsing LRC file: {args.lrc}")
        with open(args.lrc, "r", encoding="utf-8", errors="ignore") as f:
            lyrics_data = parse_lrc_file(f.read())
        print(f"Loaded {len(lyrics_data)} lyric lines from LRC.")
    elif args.transcribe:
        print(f"Transcribing audio with Whisper AI (model={args.model})...")
        transcriber = WhisperTranscriber(model_size=args.model)
        lyrics_data = transcriber.transcribe(args.audio)
        print(f"Transcribed {len(lyrics_data)} lyric lines with word-level sync.")

    # 2. Resolution setup
    if args.aspect == "9:16":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    print("=" * 60)
    print(f"Starting Video Automation Render:")
    print(f"  Input Audio:   {args.audio}")
    print(f"  Output Video:  {args.output}")
    print(f"  Theme:         {args.theme} ({args.palette})")
    print(f"  Resolution:    {width}x{height} @ {args.fps} FPS")
    print(f"  Lyrics Count:  {len(lyrics_data)} lines")
    print("=" * 60)

    def on_progress(p):
        sys.stdout.write(f"\rRendering: {p['percent']}% | Frame: {p['frame']}/{p['total_frames']} | Speed: {p['fps']} fps | ETA: {p['eta_seconds']}s   ")
        sys.stdout.flush()

    renderer = VideoRenderer(
        audio_path=args.audio,
        output_path=args.output,
        width=width,
        height=height,
        fps=args.fps,
        theme=args.theme,
        palette_name=args.palette,
        background_image=args.bg,
        logo_image=args.logo,
        song_title=args.title,
        artist_name=args.artist,
        lyrics_data=lyrics_data,
        bar_count=args.bars,
        bass_boost=args.bass
    )

    renderer.render_video(progress_callback=on_progress)
    print(f"\nRender completed successfully -> {args.output}")

if __name__ == "__main__":
    main()
