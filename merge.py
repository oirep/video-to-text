"""
merge.py — Merge speech segments and screen frames into Markdown output.
"""

from __future__ import annotations

from audio_pipe import Segment
from screen_pipe import ScreenFrame


def to_markdown(
    title: str,
    duration: float,
    speech: list[Segment],
    screen: list[ScreenFrame],
) -> str:
    mins = int(duration // 60)
    secs = int(duration % 60)

    events: list[dict] = []
    for seg in speech:
        events.append({"time": seg.start, "kind": "speech", "text": seg.text})
    for frame in screen:
        events.append({"time": frame.timestamp, "kind": "screen", "text": frame.description})
    events.sort(key=lambda e: e["time"])

    lines = [
        f"## 视频内容 — {title} ({mins}分{secs}秒)",
        "",
        "---",
        "",
        "### 逐字稿 + 屏幕内容（时间线）",
        "",
    ]

    for ev in events:
        ts = _fmt_ts(ev["time"])
        if ev["kind"] == "speech":
            lines.append(f"[{ts}] {ev['text']}")
        else:
            lines.append(f"\n[{ts}] 📺 *屏幕内容*：{ev['text']}\n")

    return "\n".join(lines)


def _fmt_ts(seconds: float) -> str:
    t = int(seconds)
    return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"
