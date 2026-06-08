"""
audio_pipe.py — Audio extraction and transcription module.

Public API:
  transcribe(input_path, model="medium") -> list[Segment]

Segment = {"start": float, "end": float, "text": str}

Large file handling: audio > SPLIT_THRESHOLD_MB is chunked into
CHUNK_MINUTES-minute pieces, transcribed separately, then merged with
correct time offsets so the final segment list looks like one pass.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SPLIT_THRESHOLD_MB = 200
CHUNK_MINUTES = 10


@dataclass
class Segment:
    start: float
    end: float
    text: str


def transcribe(input_path: str, model: str = "medium") -> list[Segment]:
    """
    Extract audio from input_path (video or audio) and transcribe with Whisper.
    Returns segments sorted by start time with absolute timestamps.
    """
    with tempfile.TemporaryDirectory(prefix="vtt-audio-") as tmpdir:
        wav_path = os.path.join(tmpdir, "audio.wav")
        _to_wav(input_path, wav_path)
        return _transcribe_wav(wav_path, model=model)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_wav(src: str, dst: str) -> None:
    """Convert any audio/video to 16kHz mono WAV."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", dst],
            check=True, capture_output=True
        )
    except subprocess.CalledProcessError:
        raise RuntimeError(
            f"Cannot read audio from '{src}': not a valid media file or no audio stream.\n"
            "Run: ffprobe -v error -show_streams <file>  to diagnose."
        )


def _wav_duration(wav_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", wav_path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def _transcribe_wav(wav_path: str, model: str) -> list[Segment]:
    size_mb = os.path.getsize(wav_path) / 1e6
    if size_mb > SPLIT_THRESHOLD_MB:
        return _transcribe_chunked(wav_path, model)
    return _run_whisper(wav_path, model, offset=0.0)


def _transcribe_chunked(wav_path: str, model: str) -> list[Segment]:
    """Split wav into CHUNK_MINUTES-minute pieces and transcribe each."""
    chunk_sec = CHUNK_MINUTES * 60
    duration = _wav_duration(wav_path)
    all_segments: list[Segment] = []

    with tempfile.TemporaryDirectory(prefix="vtt-chunks-") as chunkdir:
        chunk_idx = 0
        offset = 0.0
        while offset < duration:
            chunk_path = os.path.join(chunkdir, f"chunk_{chunk_idx:04d}.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path,
                 "-ss", str(offset), "-t", str(chunk_sec),
                 "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                 chunk_path],
                check=True, capture_output=True
            )
            segs = _run_whisper(chunk_path, model, offset=offset)
            all_segments.extend(segs)
            offset += chunk_sec
            chunk_idx += 1

    return all_segments


def _run_whisper(wav_path: str, model: str, offset: float) -> list[Segment]:
    from faster_whisper import WhisperModel  # lazy import

    _model = _get_model(model)
    raw_segments, _ = _model.transcribe(wav_path, language="zh", beam_size=5)
    return [
        Segment(start=seg.start + offset, end=seg.end + offset, text=seg.text.strip())
        for seg in raw_segments
        if seg.text.strip()
    ]


_model_cache: dict[str, object] = {}

def _get_model(name: str):
    if name not in _model_cache:
        from faster_whisper import WhisperModel
        _model_cache[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _model_cache[name]
