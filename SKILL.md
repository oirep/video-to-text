---
name: video-to-text
version: 1.3.0
description: "将本地会议视频（MP4/M4A/MOV）转换为带时间戳的 Markdown 文字稿。语音识别使用本地 faster-whisper（中文 medium 模型，无需联网），屏幕共享内容（PPT/代码/白板/表格）使用 Claude Vision 分析，两路合并输出。独立工具，不依赖任何其他 skill。当用户说「把这个视频转文字」「录制转文本」「分析这个MP4」「提取屏幕内容」「视频转文字稿」「这个会议有屏幕共享，帮我整理」时触发。会议含屏幕共享演示时最有价值；仅摄像头画面（无共享屏幕讲解）时可跳过。"
metadata:
  requires:
    bins: ["ffmpeg", "python3"]
    pip: ["faster-whisper>=1.2.0", "anthropic>=0.40.0"]
    env: ["ANTHROPIC_API_KEY"]
---

# video-to-text

本地视频 → 语音逐字稿 + 屏幕内容（Markdown，带时间戳）。

## 何时使用

| 场景 | 建议 |
|------|------|
| 会议有屏幕共享（PPT 演示、代码 demo、白板、表格讲解） | **运行** — 语音 + 视觉双通道，内容最完整 |
| 仅语音、无屏幕共享 | **可选** — 加 `--audio-only`，只输出逐字稿 |
| 仅摄像头画面、无屏幕内容 | **跳过** — 视觉信息对上下文价值低 |

## 前置检查

### 1. 检查 ffmpeg

```bash
command -v ffmpeg || echo "NOT_INSTALLED"
```

未安装时：
```bash
brew install ffmpeg   # macOS
# 或从 https://ffmpeg.org/download.html 下载
```

### 2. 检查 Python 与 faster-whisper

```bash
python3 -c "import faster_whisper; print('ok')" 2>&1
```

若报 ModuleNotFoundError：
```bash
pip install -r "$(dirname $0)/requirements.txt"
# 或单独安装：pip install faster-whisper anthropic
```

### 3. 确认 ANTHROPIC_API_KEY（屏幕内容分析用）

```bash
echo ${ANTHROPIC_API_KEY:0:10}…
```

未设置时屏幕分析默认 `auto` 模式会尝试本地后端（qwen/ocr）；如两者均未安装则跳过屏幕分析，仅输出语音稿。需要 Claude Vision 时：
```bash
export ANTHROPIC_API_KEY=sk-ant-…
```

### 4. 确认脚本路径

脚本与本 SKILL.md 同目录。安装后路径为：

```bash
# symlink 安装（推荐）
~/.agents/skills/video-to-text/video_to_text.py

# npx skills add 安装
~/.claude/skills/video-to-text/video_to_text.py
```

用变量引用，避免硬编码：
```bash
SCRIPT="$(dirname "$(realpath ~/.agents/skills/video-to-text/SKILL.md)")/video_to_text.py"
```

---

## 标准执行流程

### Step 1：获取视频文件路径

用户提供本地文件路径（MP4/M4A/MOV）。常见下载渠道：
- 飞书会议：妙记页面 → 右上角「…」→「下载原始录像」
- 腾讯会议：[会议网页](https://meeting.tencent.com) → 录制管理 → 下载

### Step 2：运行转写

```bash
python3 <SCRIPT_PATH> "<VIDEO_PATH>" [OPTIONS]
```

| 选项 | 说明 | 默认 |
|------|------|------|
| `--audio-only` | 跳过屏幕内容分析（仅语音） | 关闭 |
| `--vision-backend` | 视觉分析后端：`claude`/`qwen`/`ocr`/`auto` | `auto` |
| `--model` | Whisper 模型：`tiny`/`base`/`small`/`medium`/`large-v3` | `medium` |
| `--frame-interval N` | 屏幕帧采样间隔（秒） | `30` |
| `-o OUTPUT` | 输出文件路径 | 打印到 stdout |

**视觉后端说明（`--vision-backend`）**：

| 后端 | 条件 | 质量 |
|------|------|------|
| `claude`（推荐） | 需要 `ANTHROPIC_API_KEY`，并发调用 | ★★★★★ |
| `qwen` | 本地 HuggingFace，无 API key，~8GB RAM | ★★★★☆ |
| `ocr` | 纯文字 OCR，无 API key，~500MB | ★★★☆☆ |
| `auto`（默认） | 自动检测：claude → qwen → ocr → skip | — |

**典型命令**（含屏幕共享）：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4"
```

**仅语音**：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4" --audio-only
```

**高精度**（方言/专业术语多）：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4" --model large-v3
```

### Step 3：读取并注入输出

输出为标准 Markdown，直接注入对话上下文：

```markdown
## 视频内容 — {文件名} ({时长})

[00:00:00] 发言人A 的语音内容…
[00:01:00] 📺 *屏幕内容*：展示了 PPT 幻灯片「Q2 产品规划」，含 5 个待办…
[00:02:30] 发言人B 的语音内容…
```

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `ffmpeg: command not found` | ffmpeg 未安装 | `brew install ffmpeg` |
| `ModuleNotFoundError: faster_whisper` | pip 包未安装 | `pip install faster-whisper` |
| 首次运行 Whisper 模型下载缓慢（~1.4GB） | 首次自动下载 medium 模型 | 等待完成，后续复用缓存 |
| `ANTHROPIC_API_KEY not set` / 屏幕分析跳过 | 环境变量未设置 | 设置 key 后重跑，或用 `--audio-only` |
| `Error: Cannot read audio from '…'` | 非媒体文件或无音轨 | 用 `ffprobe -v error -show_streams <file>` 诊断 |
| 转写结果乱码 / 语言错误 | 音频质量差或非中文 | 尝试 `--model large-v3` |
| 屏幕内容全部被过滤 | 所有帧被判定为仅摄像头 | 加大 `--frame-interval`，或确认视频确实有屏幕共享 |

---

## 性能参考（中文会议录制，Apple M 系列）

| 场景 | 速度 | 费用 |
|------|------|------|
| 30 分钟（语音，medium 模型） | ~36 分钟（1.2x 实时） | $0 |
| 30 分钟（含屏幕，30s 帧间隔） | +2-5 分钟 | ~$0.03-0.05 |
| 30 分钟（large-v3 模型） | ~60-90 分钟 | $0 |

---

## 使用示例

```
用户: 把这个视频转成文字
      /Users/me/Downloads/TM-recording.mp4

用户: 分析这个会议录制，里面有屏幕共享
      ~/Downloads/meeting-2026-06-03.mp4

用户: 这个视频只需要语音
      ~/Downloads/meeting.mp4 --audio-only
```
