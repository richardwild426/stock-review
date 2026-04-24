---
name: stock-review
description: 分析股市复盘视频（B站直播录播 + 本地 mp4），产出结构化摘要并推送飞书群。触发方式：`/stock-review scan`（批量处理本地录播）或 `/stock-review <本地路径|B站URL>`（单条处理）。
---

# Stock Review Skill

## Purpose
把股市复盘直播/视频自动转录、按固定模板摘要，推送到飞书。日常由 launchd 每晚定时调用 `scan` 模式扫描本地录播目录，临时也可以手动喂单条。

## Inputs
- `scan` 模式：无参数；脚本扫描 `biliup.base_dir` 目录下的 FLV 录播文件。
- 单条模式：
  - 本地绝对路径（`.flv`/`.mp4`）→ 直接分析
  - `https://www.bilibili.com/video/BVxxx/...` → 使用 yt-dlp 下载后分析

## 主要文件
- 配置：`references/up-list.yaml`
- 复盘提示词：`references/review-prompt.md`
- FunASR 热词：`references/funasr-hotwords.txt`
- 脚本目录：`scripts/`（`state.py` / `discover.py` / `fetch.py` / `transcribe.py`）
- B 站 cookie：`config/cookies.txt`（用于 yt-dlp 下载私密视频；gitignore）
- 数据目录：项目根下 `data/`（state.json / videos/ / subtitles/ / reports/）

## 编排流程

### `scan` 模式

1. 读 `references/up-list.yaml`，确认关键配置都已填（`biliup.base_dir`、`notify.lark_chat_id`）。若任一为空，**直接报错停止**并提示用户配置。
2. 调 `scripts/discover.py --config references/up-list.yaml --state-file data/state.json --cookies config/cookies.txt --skip-api`。
3. 解析 stdout JSON 得到未处理视频列表（包含 `file_path` 的本地录播）。
4. 对每条视频**串行**处理：
   - 调 `state.py mark <bvid> --status discovered --source local`
   - **本地文件直通**：直接用 `file_path`，跳过 fetch.py
   - 调 `transcribe.py <file_path> --out-dir data/subtitles --hotwords references/funasr-hotwords.txt`；若返回 `skipped_*` 标记对应 state 跳过；失败标 `transcribe_err` 跳过；成功后 `state.py mark <bvid> --status transcribed --method <L1|L2|L3>`
   - **读取** `{txt_path}`；若内容少于 500 字符，产出占位报告，否则读 `references/review-prompt.md`，把 txt 内容和 prompt 拼接，生成 markdown 报告保存到 `data/reports/{YYYY-MM-DD}_{owner_mid}_{title}.md`，标 `analyzed`
   - 调 lark-im skill 发送报告；标 `notified` 后标 `done`
5. 所有视频处理结束，汇总成功/失败，调 lark-im 发一条"扫描汇总"消息。

### 单条模式
- 本地路径：跳过 `discover`；**不写 state**（一次性场景）；直接从 `transcribe.py` 走到结束。
- B站 URL：使用 yt-dlp 下载后处理；不写 state。

## 飞书发送规则
- 发送目标：`notify.lark_chat_id`
- 单条报告 `len(markdown) <= notify.max_message_chars` → 直接发文本消息
- 超长 → 发 markdown 文件（`lark-im +send-file`）

## 前置检查
第一次运行前确认：
- `uv sync` 通过
- `ffmpeg -version` 可用（用于 FLV 转 WAV）
- `uv run python -c "import funasr"` 不报错（或系统 Python 3.12 安装 FunASR）
- `references/up-list.yaml` 的 `biliup.base_dir`、`notify.lark_chat_id` 都填好
- `data/` 及其子目录可写

## 注意事项
- **B站 API 风控问题**：WBI 签名虽已实现但仍可能被封锁，建议使用本地录播扫描作为主要输入源
- **FLV 文件处理**：transcribe.py 会自动将 FLV 转为 WAV 进行 ASR
- **FunASR 首次运行**：需下载约 2-3GB 模型，请耐心等待