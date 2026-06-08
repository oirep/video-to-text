"""
screen_pipe.py — Keyframe extraction and Claude Vision analysis.

Public API:
  analyze(video_path, frame_interval=30) -> list[ScreenFrame]

ScreenFrame = {"timestamp": float, "description": str}

Frames are deduplicated by scene change detection. If scene detection
yields > 3× the fixed-interval count, we fall back to fixed interval.
Camera-only frames (no screen share) are filtered from the result.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

MAX_CONCURRENT = 10
VISION_MODEL = "claude-sonnet-4-6"
VISION_PROMPT = (
    "这张会议截图展示了什么内容？"
    "如果有屏幕共享内容（PPT、文档、代码、网页、表格等），详细描述其内容：标题、主要条目、关键数字或文字。"
    "如果只有摄像头人物画面（无屏幕共享），回复：仅摄像头画面。"
    "用中文回答，150字以内。"
)


@dataclass
class ScreenFrame:
    timestamp: float
    description: str

    @property
    def ts_str(self) -> str:
        t = int(self.timestamp)
        return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def analyze(video_path: str, frame_interval: int = 30) -> list[ScreenFrame]:
    """Extract keyframes and analyze each with Claude Vision."""
    with tempfile.TemporaryDirectory(prefix="vtt-frames-") as frames_dir:
        frames = _extract_frames(video_path, frames_dir, frame_interval)
        if not frames:
            return []
        results = _analyze_batch(frames)
    # Filter camera-only frames
    return [f for f in results if "仅摄像头" not in f.description]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _video_duration(video_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _extract_frames(video_path: str, out_dir: str, interval: int) -> list[tuple[float, str]]:
    """
    Try scene-change detection first; fall back to fixed interval.
    Returns list of (timestamp_sec, frame_path).
    """
    duration = _video_duration(video_path)
    expected_fixed = max(1, int(duration / interval))

    # Attempt scene detection
    scene_dir = os.path.join(out_dir, "scene")
    os.makedirs(scene_dir, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vf", "select='gt(scene,0.05)',scale=1280:-1",
         "-vsync", "vfr", f"{scene_dir}/f_%08d.jpg"],
        capture_output=True
    )
    scene_frames = sorted(Path(scene_dir).glob("f_*.jpg"))

    if 0 < len(scene_frames) <= expected_fixed * 3:
        # Scene detection gave a sensible count — use it with approximate timestamps
        step = duration / max(len(scene_frames), 1)
        return [(i * step, str(p)) for i, p in enumerate(scene_frames)]

    # Fall back to fixed interval
    fixed_dir = os.path.join(out_dir, "fixed")
    os.makedirs(fixed_dir, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vf", f"fps=1/{interval},scale=1280:-1",
         f"{fixed_dir}/f_%08d.jpg"],
        check=True, capture_output=True
    )
    fixed_frames = sorted(Path(fixed_dir).glob("f_*.jpg"))
    return [(i * interval, str(p)) for i, p in enumerate(fixed_frames)]


def _analyze_one(timestamp: float, image_path: str) -> ScreenFrame:
    import anthropic
    client = anthropic.Anthropic()

    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=VISION_MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
                {"type": "text", "text": VISION_PROMPT},
            ]
        }]
    )
    return ScreenFrame(timestamp=timestamp, description=response.content[0].text.strip())


def _analyze_batch(frames: list[tuple[float, str]]) -> list[ScreenFrame]:
    results: list[ScreenFrame] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {pool.submit(_analyze_one, ts, path): (ts, path) for ts, path in frames}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                ts, _ = futures[future]
                print(f"[screen] frame @{ts:.0f}s failed: {e}", flush=True)
    results.sort(key=lambda f: f.timestamp)
    return results
