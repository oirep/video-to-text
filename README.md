# video-to-text

将会议录制视频（含屏幕共享）转换为带时间戳的 Markdown 文字稿。

- **语音逐字稿**：本地 `faster-whisper`（中文 medium 模型，无需联网）
- **屏幕共享内容**：ffmpeg 关键帧 + Claude Vision（PPT、代码、白板、表格）
- **合并输出**：语音与屏幕内容按时间线交织

独立工具，不依赖其他 skill。可与 `meeting-context` 配合使用（API 文字稿 + 视觉内容双通道）。

---

## 安装

**symlink（推荐，SSoT 始终最新）：**
```bash
ln -s /path/to/leapboundai-workspace/base/skills/video-to-text ~/.agents/skills/video-to-text
```

**公开镜像（无内部权限时）：**
```bash
npx skills add oirep/video-to-text
```

**内部协作者：**
```bash
npx skills add kevinw99/base --path skills/video-to-text
```

---

## 依赖安装

```bash
# 运行时依赖
brew install ffmpeg
pip install -r requirements.txt
```

| 依赖 | 用途 |
|------|------|
| `ffmpeg` | 音频提取 + 关键帧截取 |
| `faster-whisper` | 本地语音识别 |
| `anthropic` | Claude Vision 屏幕内容分析 |
| `ANTHROPIC_API_KEY` | 屏幕分析（不需要时可跳过） |

---

## 用法

```bash
SCRIPT=~/.agents/skills/video-to-text/video_to_text.py

# 语音 + 屏幕内容（完整，推荐含屏幕共享的录制）
python3 "$SCRIPT" meeting.mp4

# 本地视觉分析（无 API key，Qwen2-VL 本地模型）
python3 "$SCRIPT" meeting.mp4 --vision-backend qwen

# 纯文字 OCR（无 API key，最轻量）
python3 "$SCRIPT" meeting.mp4 --vision-backend ocr

# 仅语音（速度快，无 API 费用）
python3 "$SCRIPT" meeting.mp4 --audio-only

# 输出到文件
python3 "$SCRIPT" meeting.mp4 -o output.md

# 高精度模型
python3 "$SCRIPT" meeting.mp4 --model large-v3
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--audio-only` | off | 跳过屏幕内容分析 |
| `--vision-backend` | `auto` | 视觉后端：`claude`/`qwen`/`ocr`/`auto`（auto 自动检测最优） |
| `--model` | `medium` | Whisper 模型：`tiny/base/small/medium/large-v3` |
| `--frame-interval` | `30` | 屏幕帧采样间隔（秒） |
| `-o / --output` | stdout | 输出文件路径 |

---

## 费用说明

| 功能 | 运行方式 | 费用 |
|------|---------|------|
| 语音转写（faster-whisper） | 本地 CPU，无网络 | **$0，完全免费** |
| 屏幕内容分析（Claude Vision） | 调用 Anthropic API | **按帧计费**，从 `ANTHROPIC_API_KEY` 所绑定的 Anthropic 账户扣除 |

屏幕分析费用参考（claude-sonnet-4-6，30s 帧间隔）：
- 30 分钟录制 ≈ 30–50 帧 → **约 $0.03–0.05/次**
- 不需要屏幕内容时加 `--audio-only`，**完全免费**

> 账单去向：`console.anthropic.com → Billing`。与 Claude Code 使用同一 API key 时共享额度。

---

## 性能参考（Apple M 系列，30 分钟录制）

| 场景 | 耗时 | 费用 |
|------|------|------|
| 仅语音，medium 模型 | ~36 分钟 | $0 |
| 语音 + 屏幕（30s 帧间隔） | ~40 分钟 | ~$0.03–0.05（屏幕分析部分）|
