#!/usr/bin/env python3
"""
video_to_text — Convert meeting recording to structured Markdown text.

Usage:
  python3 video_to_text.py <file>                   # speech + screen
  python3 video_to_text.py <file> --audio-only      # speech only (faster)
  python3 video_to_text.py <file> --model large-v3  # higher accuracy
  python3 video_to_text.py <file> -o out.md         # save to file

Supported inputs: MP4, M4V, MOV, M4A, WAV, MP3, AAC
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import audio_pipe
import merge as merge_mod
import screen_pipe


def _duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _is_audio(path: str) -> bool:
    return Path(path).suffix.lower() in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert meeting video to Markdown transcript + screen content"
    )
    parser.add_argument("input", help="Input video or audio file")
    parser.add_argument("--audio-only", action="store_true",
                        help="Skip screen content analysis (faster)")
    parser.add_argument("--vision-backend", default="auto",
                        choices=["claude", "qwen", "ocr", "auto"],
                        help="Vision backend: claude/qwen/ocr/auto (default: auto)")
    parser.add_argument("--model", default="medium",
                        help="Whisper model: tiny/base/small/medium/large-v3 (default: medium)")
    parser.add_argument("--frame-interval", type=int, default=30,
                        help="Screen frame sample interval in seconds (default: 30)")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    title = Path(args.input).stem
    duration = _duration(args.input)
    is_audio = _is_audio(args.input)

    try:
        # ── Audio pipeline ────────────────────────────────────────────────────────
        t0 = time.time()
        print(f"[audio] Transcribing {args.input} ...", file=sys.stderr)
        speech = audio_pipe.transcribe(args.input, model=args.model)
        print(f"[audio] {len(speech)} segments in {time.time()-t0:.1f}s", file=sys.stderr)

        # Use last segment end time as duration fallback
        if duration == 0 and speech:
            duration = speech[-1].end

        # ── Screen pipeline ───────────────────────────────────────────────────────
        screen: list[screen_pipe.ScreenFrame] = []
        if not args.audio_only and not is_audio:
            t1 = time.time()
            print(f"[screen] Analyzing frames (every {args.frame_interval}s) ...", file=sys.stderr)
            screen = screen_pipe.analyze(args.input, frame_interval=args.frame_interval, backend=args.vision_backend)
            print(f"[screen] {len(screen)} screen frames in {time.time()-t1:.1f}s", file=sys.stderr)

        # ── Merge & output ────────────────────────────────────────────────────────
        output = merge_mod.to_markdown(title, duration, speech, screen)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            total = time.time() - t0
            print(f"[done] Written to {args.output} ({total:.1f}s total)", file=sys.stderr)
        else:
            print(output)

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ModuleNotFoundError as e:
        pkg = str(e).split("'")[1] if "'" in str(e) else str(e)
        print(f"Error: missing dependency '{pkg}'. Run: pip install {pkg}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
