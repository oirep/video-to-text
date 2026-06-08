---
name: video-to-text
version: 1.1.0
description: "从本地会议视频（MP4/M4A/MOV）提取屏幕共享内容（PPT/代码/白板/表格）并转写语音，输出带时间戳的 Markdown 供 Agent 使用。两种用途：①主动增强 — 当飞书/企微会议有屏幕共享演示时，在 API 文字稿基础上叠加视觉内容；②兜底替代 — 妙记/文档 API 全部失败时，同时提供语音逐字稿 + 屏幕内容。仅摄像头画面（无共享屏幕讲解）时跳过，不增加价值。当用户说「把这个视频转文字」「录制转文本」「分析这个MP4」「提取屏幕内容」「这个会议有屏幕共享」时触发；meeting-context 获取到 API 文字稿后如检测到会议含屏幕共享也应主动建议使用。"
metadata:
  requires:
    bins: ["ffmpeg", "python3"]
    pip: ["faster-whisper>=1.2.0", "anthropic>=0.40.0"]
    env: ["ANTHROPIC_API_KEY"]
---

# video-to-text

本地视频 → 屏幕内容 + 语音逐字稿（Markdown，带时间戳）。

## 何时使用

| 场景 | 操作 |
|------|------|
| 会议有屏幕共享（PPT 演示、代码 demo、白板、表格讲解） | **主动使用** — 在 API 文字稿基础上叠加屏幕视觉内容，丰富上下文 |
| 仅摄像头画面、无屏幕内容 | **跳过** — 视觉信息对上下文价值低，不建议跑 |
| 飞书妙记 API 失败 / 腾讯会议录制（无飞书 API） | **兜底** — 同时提供语音转写 + 屏幕内容 |

**主动使用时的判断依据**（满足任一可建议运行）：
- 用户提到会议中有演示、PPT 分享、代码展示、白板讨论
- 会议主题涉及产品评审、技术 demo、数据分析展示等场景
- 用户说「会议中有屏幕共享」或直接提供了录制文件路径



## 前置检查

### 1. 检查 ffmpeg

```bash
command -v ffmpeg || echo "NOT_INSTALLED"
```

未安装时引导用户：
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
pip install faster-whisper
```

### 3. 确认 ANTHROPIC_API_KEY

```bash
echo ${ANTHROPIC_API_KEY:0:10}…   # 只显示前10位，确认已设置
```

未设置时屏幕内容分析会跳过（仅语音转写）。若需要屏幕内容：
```bash
export ANTHROPIC_API_KEY=sk-ant-…
```

### 4. 定位 video_to_text.py

按顺序查找，取第一个存在的路径：

```bash
for p in \
  ~/leap-bound/leapboundai-workspace/base/tools/video-to-text/video_to_text.py \
  ~/.agents/tools/video-to-text/video_to_text.py \
  ~/base/tools/video-to-text/video_to_text.py; do
  [ -f "$p" ] && echo "$p" && break
done
```

若未找到，提示用户确认 `base` 仓库克隆路径，然后手动指定脚本路径。

---

## 标准执行流程

### Step 1：获取视频文件路径

用户应提供本地文件路径（已下载的 MP4/M4A/MOV）。

- 飞书会议录制下载：妙记页面 → 右上角「…」→「下载原始录像」
- 腾讯会议录制下载：[腾讯会议网页](https://meeting.tencent.com) → 录制管理 → 下载

### Step 2：运行转写

```bash
python3 <SCRIPT_PATH> "<VIDEO_PATH>" [OPTIONS]
```

常用选项：

| 选项 | 说明 | 默认 |
|------|------|------|
| `--audio-only` | 跳过屏幕内容分析（仅语音） | 关闭 |
| `--model` | Whisper 模型：`tiny`/`base`/`small`/`medium`/`large-v3` | `medium` |
| `--frame-interval N` | 屏幕帧采样间隔（秒） | `30` |
| `-o OUTPUT` | 输出文件路径 | 打印到 stdout |

**典型命令**（含屏幕共享的完整会议）：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4"
```

**仅语音（速度更快，无 API 费用）**：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4" --audio-only
```

**大文件 / 精度要求高（更精准，速度略慢）**：
```bash
python3 <SCRIPT_PATH> "/Users/me/Downloads/meeting.mp4" --model large-v3
```

### Step 3：读取并注入输出

脚本输出标准 Markdown，直接注入当前对话上下文：

```markdown
## 视频内容 — {文件名} ({时长})

[00:00:00] 发言人A 的语音内容…
[00:01:00] 📺 *屏幕内容*：展示了 PPT 幻灯片「Q2 产品规划」，含 5 个待办…
[00:02:30] 发言人B 的语音内容…
```

若脚本将输出写入文件（`-o` 指定或默认 `/tmp/*.md`），用 Read 工具读取后注入。

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `ffmpeg: command not found` | ffmpeg 未安装 | `brew install ffmpeg` |
| `ModuleNotFoundError: faster_whisper` | pip 包未安装 | `pip install faster-whisper` |
| 首次运行 Whisper 模型下载缓慢（~1.4GB） | 首次自动下载 medium 模型 | 等待完成，后续复用缓存（~2-5s 加载） |
| 屏幕内容分析跳过 / `ANTHROPIC_API_KEY not set` | 环境变量未设置 | 设置 API key 后重跑，或用 `--audio-only` 跳过 |
| `No audio stream found` | 文件无音轨（纯视频或损坏） | 检查文件完整性；可用 `ffprobe` 诊断 |
| 转写结果乱码 / 语言错误 | 音频非中文或质量差 | 尝试 `--model large-v3`；确认录制质量 |
| 屏幕内容全部被过滤（`仅摄像头` 判断误杀） | 所有帧被识别为纯摄像头画面 | 增大 `--frame-interval` 减少帧数，或检查视频确认是否真的无屏幕共享 |

---

## 性能参考（中文会议录制）

| 场景 | 速度 | 备注 |
|------|------|------|
| 30 分钟录制（语音，medium 模型） | ~36 分钟（1.2x 实时） | Apple M 系列 CPU，int8 量化 |
| 30 分钟录制（含屏幕，30s 帧间隔） | +2-5 分钟 | 60 帧并发分析，~$0.03-0.05 |
| 30 分钟录制（large-v3 模型） | ~60-90 分钟 | 精度更高，适合方言/专业术语 |

---

## 使用示例

```
用户: 把这个视频转成文字
      /Users/me/Downloads/TM-recording.mp4

用户: 分析这个会议录制，里面有屏幕共享
      ~/Downloads/meeting-2026-06-03.mp4

用户: 这个视频只需要语音，不要屏幕内容
      [文件路径] --audio-only
```
