# video-to-text

> 一个 Claude Code **视频转文字 skill**：给一个本地会议录制文件（MP4/M4A/MOV），自动用本地 Whisper 转写语音、用 Claude Vision 分析屏幕共享内容（PPT/代码/白板），输出带时间戳的完整 Markdown 文字稿，直接注入对话上下文。

适用于：飞书妙记 API 失败时的兜底、腾讯会议录制（无飞书 API）、含屏幕共享需要视觉内容的录制。

---

## 安装

**若有 `kevinw99/base` 读权限（内部协作者，始终拿最新版）：**

```bash
npx skills add kevinw99/base --path skills/video-to-text
```

**公开镜像（无内部权限时）：**

```bash
npx skills add oirep/video-to-text
```

---

## 依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| `ffmpeg` | 音频提取 + 关键帧截取 | `brew install ffmpeg` |
| `faster-whisper` | 本地语音识别（中文 medium 模型）| `pip install faster-whisper` |
| `ANTHROPIC_API_KEY` | 屏幕内容 Claude Vision 分析 | 设置环境变量 |

**工具脚本**（需本地克隆）：`base/tools/video-to-text/video_to_text.py`

```bash
# 克隆 base 仓库后安装依赖
git clone https://github.com/kevinw99/base.git
pip install -r base/tools/video-to-text/requirements.txt
```

---

## 使用

触发词：「把这个视频转文字」「录制转文本」「分析这个MP4」  
提供本地录制文件路径，Claude 会自动完成所有步骤。

详细步骤见 [SKILL.md](SKILL.md)。

---

## 性能参考

| 场景 | 速度 |
|------|------|
| 30 分钟会议（语音，medium 模型） | ~36 分钟（1.2x 实时） |
| 30 分钟会议（含屏幕共享） | +2-5 分钟，~$0.03-0.05 API 费用 |
