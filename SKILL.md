---
name: stock-review
description: Analyze stock market replay videos from Bilibili or local files, generate structured summaries and push to Feishu. Use when asked to analyze stock videos, 复盘, or the user mentions 复盘视频、股市直播、B站录播.
---

# Stock Review Skill

## Purpose
自动分析股市复盘直播/视频：转录、结构化摘要、推送飞书。

## Quick Start
直接用自然语言触发（本 Skill 靠 description 关键词匹配，没有注册 slash 命令）：
- "复盘 scan" / "扫描录播复盘" - 扫描本地录播目录批量处理
- "复盘 <本地路径>" / "复盘 https://www.bilibili.com/video/BVxxx" - 分析单个视频

## Workflow

### Scan Mode

#### Configuration Check
1. 检查配置：`references/up-list.yaml` 的 `biliup.base_dir` 和 `notify.lark_chat_id`

#### Video Discovery
2. 运行发现：`scripts/discover.py --config references/up-list.yaml --state-file data/state.json`
   （只扫本地录播目录；终态与重试超限的条目自动跳过）

#### Video Processing
3. 对每条视频，按 entry 现有 status 续跑（`scripts/state.py get <bvid>` 读取）：
   - 无记录 / `*_err`：从头开始，先 mark `discovered`
   - `discovered` → 调 `scripts/transcribe.py` → mark `transcribed`
   - `transcribed` → 读字幕 + `references/review-prompt.md` 生成报告 → mark `analyzed`
   - `analyzed` → 通过 lark-im skill 发送飞书消息 → mark `notified` → mark `done`

   不要无脑回退已有的中间态，否则会重复转录/通知。

#### Summary and Notification
4. 汇总结果发送飞书

### Single Video Mode
不进 state 机；不写飞书除非用户要求。
- 本地路径：直接 `scripts/transcribe.py <path> --out-dir data/subtitles --hotwords references/funasr-hotwords.txt`
- B 站 URL：先 `yt-dlp -f bv*+ba/best --merge-output-format mp4 -o 'data/videos/%(id)s.%(ext)s' --cookies config/cookies.txt <URL>`，得到本地文件后再走 transcribe

## Gotchas
- **FunASR 首次运行**：需下载 2-3GB 模型，耐心等待
- **FLV / MKV**：transcribe.py 自动抽 16k mono WAV
- **字幕提取**：L1 嵌入 → L2 OCR(未启用) → L3 ASR 降级
- **飞书发送**：报告 ≤ `notify.max_message_chars` 发文本，超长发文件
- **重试上限**：`discover.max_retries`（默认 3）。失败累计达到上限后，discover 不再返回；如需重跑，手动清掉 `data/state.json` 里对应条目的 `retry_count`

## Key Files
- 配置：`references/up-list.yaml`（必填 base_dir、lark_chat_id）
- 提示词：`references/review-prompt.md`
- 热词：`references/funasr-hotwords.txt`
- Cookies：`config/cookies.txt`（可选，Netscape 格式，仅在用 yt-dlp 下载需登录的 B 站视频时使用）

## Prerequisites
- Python 3.11
- `uv sync` 或 `pip install funasr modelscope torch`
- `ffmpeg -version` 可用
- `yt-dlp --version` 可用（仅用于 B 站 URL 单条模式）
- lark-cli 已认证（飞书发送）

## References
详见 `references/workflow-detail.md`（完整编排流程）。