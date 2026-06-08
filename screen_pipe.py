"""
screen_pipe.py — Keyframe extraction and vision analysis.

Public API:
  analyze(video_path, frame_interval=30, backend="auto") -> list[ScreenFrame]

Backends:
  auto    — Detect best available: claude > qwen > ocr > skip
  claude  — Claude Vision API (requires ANTHROPIC_API_KEY, concurrent)
  qwen    — Qwen2-VL-2B-Instruct local model (requires transformers, serial)
  ocr     — PaddleOCR text extraction (requires paddleocr, serial)

ScreenFrame = {"timestamp": float, "description": str}
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

# Lazy-loaded globals — shared across frames within a single run
_qwen_model = None
_qwen_processor = None
_ocr_engine = None


@dataclass
class ScreenFrame:
    timestamp: float
    description: str

    @property
    def ts_str(self) -> str:
        t = int(self.timestamp)
        return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def analyze(video_path: str, frame_interval: int = 30, backend: str = "auto") -> list[ScreenFrame]:
    """Extract keyframes and analyze with the selected vision backend."""
    if backend == "auto":
        backend = _auto_backend()
        print(f"[screen] auto-detected backend: {backend}", flush=True)

    if backend == "skip":
        print("[screen] No vision backend available. Skipping screen analysis.", flush=True)
        print("[screen] Set ANTHROPIC_API_KEY or install requirements-local.txt to enable.", flush=True)
        return []

    _check_backend(backend)

    with tempfile.TemporaryDirectory(prefix="vtt-frames-") as frames_dir:
        frames = _extract_frames(video_path, frames_dir, frame_interval)
        if not frames:
            return []
        results = _analyze_batch(frames, backend=backend)
    return [f for f in results if "仅摄像头" not in f.description]


# ── Backend detection ─────────────────────────────────────────────────────────

def _auto_backend() -> str:
    """Return best available backend: claude > qwen > ocr > skip."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    try:
        import importlib
        importlib.import_module("transformers")
        return "qwen"
    except ImportError:
        pass
    try:
        import importlib
        importlib.import_module("paddleocr")
        return "ocr"
    except ImportError:
        pass
    return "skip"


def _check_backend(backend: str) -> None:
    """Raise RuntimeError with install instructions if the backend is unavailable."""
    if backend == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set.\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "Or use a local backend: --vision-backend qwen/ocr/auto"
            )
    elif backend == "qwen":
        try:
            import importlib
            importlib.import_module("transformers")
        except ImportError:
            raise RuntimeError(
                "Qwen backend requires 'transformers'.\n"
                "  pip install -r requirements-local.txt\n"
                "  (~4.7GB model download on first run)"
            )
    elif backend == "ocr":
        try:
            import importlib
            importlib.import_module("paddleocr")
        except ImportError:
            raise RuntimeError(
                "OCR backend requires 'paddleocr'.\n"
                "  pip install paddleocr paddlepaddle\n"
                "  (~300MB model download on first run)"
            )


# ── Frame extraction ──────────────────────────────────────────────────────────

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


# ── Backend implementations ───────────────────────────────────────────────────

def _analyze_one_claude(timestamp: float, image_path: str) -> ScreenFrame:
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


def _analyze_one_qwen(timestamp: float, image_path: str) -> ScreenFrame:
    """Analyze using local Qwen2-VL-2B-Instruct (~4.7GB, loaded once, CPU/GPU)."""
    global _qwen_model, _qwen_processor
    from PIL import Image
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    import torch

    if _qwen_model is None:
        print("[screen] Loading Qwen2-VL model (first call: ~30s + ~4.7GB download on first run)...", flush=True)
        _qwen_model = Qwen2VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2-VL-2B-Instruct",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        _qwen_model.eval()
        _qwen_processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")

    image = Image.open(image_path).convert("RGB")
    messages = [{
        "role": "user",
        "content": [
            {"type": "image"},
            {"type": "text", "text": VISION_PROMPT},
        ]
    }]
    text = _qwen_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _qwen_processor(text=[text], images=[image], return_tensors="pt")

    with torch.no_grad():
        generated_ids = _qwen_model.generate(**inputs, max_new_tokens=256)

    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)]
    output = _qwen_processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return ScreenFrame(timestamp=timestamp, description=output[0].strip())


def _analyze_one_ocr(timestamp: float, image_path: str) -> ScreenFrame:
    """Extract text using PaddleOCR (CPU-only, no API key required)."""
    global _ocr_engine
    from paddleocr import PaddleOCR

    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    result = _ocr_engine.ocr(image_path, cls=True)
    if not result or not result[0]:
        return ScreenFrame(timestamp=timestamp, description="仅摄像头画面")

    texts = [line[1][0] for line in result[0] if line[1][1] > 0.5]
    if not texts:
        return ScreenFrame(timestamp=timestamp, description="仅摄像头画面")

    description = "【OCR 文字识别】\n" + "\n".join(texts[:40])
    return ScreenFrame(timestamp=timestamp, description=description)


_BACKENDS = {
    "claude": _analyze_one_claude,
    "qwen": _analyze_one_qwen,
    "ocr": _analyze_one_ocr,
}


def _analyze_batch(frames: list[tuple[float, str]], backend: str = "claude") -> list[ScreenFrame]:
    _analyze_fn = _BACKENDS[backend]
    results: list[ScreenFrame] = []

    if backend in ("qwen", "ocr"):
        # Serial: qwen model is not thread-safe; ocr uses a single engine instance
        for ts, path in frames:
            try:
                results.append(_analyze_fn(ts, path))
            except Exception as e:
                print(f"[screen] frame @{ts:.0f}s failed: {e}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
            futures = {pool.submit(_analyze_fn, ts, path): (ts, path) for ts, path in frames}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    ts, _ = futures[future]
                    print(f"[screen] frame @{ts:.0f}s failed: {e}", flush=True)

    results.sort(key=lambda f: f.timestamp)
    return results
