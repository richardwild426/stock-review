---
name: stock-review
description: Analyze stock market replay videos from Bilibili or local files, generate structured summaries and push to Feishu. Use when asked to analyze stock videos, 复盘, or the user mentions 复盘视频、股市直播、B站录播.
compatibility: Requires ffmpeg, yt-dlp, FunASR (paraformer-zh), Python 3.11+, and lark-cli for Feishu messaging
metadata:
  author: richardwild426
  version: "2.0"
  repository: https://github.com/richardwild426/stock-review
---

# Stock Review Skill

## Purpose
自动分析股市复盘直播/视频：转录、结构化摘要、推送飞书。

## Quick Start
- `/stock-review scan` - 扫描本地录播目录批量处理
- `/stock-review <本地路径|B站URL>` - 分析单个视频

## Workflow

### Scan Mode

#### Configuration Check
1. 检查配置：`references/up-list.yaml` 的 `biliup.base_dir` 和 `notify.lark_chat_id`

#### Video Discovery
2. 运行发现：`scripts/discover.py --config references/up-list.yaml --state-file data/state.json --cookies config/cookies.txt --skip-api`

#### Video Processing
3. 对每条视频：
   - 标记 discovered → 调用 `scripts/transcribe.py` → 标记 transcribed
   - 读取字幕，结合 `references/review-prompt.md` 生成报告
   - 通过 lark-im skill 发送飞书消息

#### Summary and Notification
4. 汇总结果发送飞书

### Single Video Mode
- 本地路径：直接调用 `scripts/transcribe.py`
- B站 URL：用 yt-dlp 下载后处理

## Gotchas
- **B站 API 风控**：WBI 签名可能失效，优先用本地录播扫描
- **FunASR 首次运行**：需下载 2-3GB 模型，耐心等待
- **FLV 文件**：transcribe.py 自动转为 WAV
- **字幕提取**：L1 嵌入 → L2 OCR(未启用) → L3 ASR 降级
- **飞书发送**：报告 ≤ 30000 字符发文本，超长发文件

## Key Files
- 配置：`references/up-list.yaml`（必填 base_dir、lark_chat_id）
- 提示词：`references/review-prompt.md`
- 热词：`references/funasr-hotwords.txt`
- Cookies：`config/cookies.txt`（Netscape 格式，用于私密视频）

## Prerequisites
- `uv sync` 或 `pip install funasr modelscope torch`
- `ffmpeg -version` 可用
- `yt-dlp --version` 可用
- lark-cli 已认证（飞书发送）

## References
详见 `references/workflow-detail.md`（完整编排流程）。