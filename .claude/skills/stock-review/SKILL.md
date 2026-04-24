---
name: stock-review
description: 分析 B 站股市复盘视频（自己私密投稿的直播录播 + 关注 up 主的公开视频 / 本地 mp4），产出结构化摘要并推送飞书群。触发方式：`/stock-review scan`（批量处理所有未分析视频）或 `/stock-review <BVID|B站URL|本地路径>`（单条处理）。
---

# Stock Review Skill

## Purpose
把股市复盘直播/视频自动转录、按固定模板摘要，推送到飞书。日常由 launchd 每晚定时调用 `scan` 模式，临时也可以手动喂单条。

## Inputs
- `scan` 模式：无参数；脚本自动去 B 站拉 up 主最新投稿。
- 单条模式：
  - `BV[A-Za-z0-9]{10}` → B 站视频
  - `https://www.bilibili.com/video/BVxxx/...` → 同上
  - 本地绝对路径（`.mp4`）→ 直接分析

## 主要文件
- 本项目根：`/Users/zvector/ws/workflow/stock-review/`
- 配置：`references/up-list.yaml`
- 复盘提示词：`references/review-prompt.md`
- FunASR 热词：`references/funasr-hotwords.txt`
- 脚本目录：`scripts/`（`state.py` / `discover.py` / `fetch.py` / `transcribe.py`）
- B 站 cookie：`config/cookies.txt`（从 `cookies.txt.example` 复制并替换；gitignore）
- 数据目录：项目根下 `data/`（state.json / videos/ / subtitles/ / reports/）

## 编排流程

### `scan` 模式

1. 读 `references/up-list.yaml`，确认关键配置都已填（`self.mid`、关注 up 主、`notify.lark_chat_id`）。若任一为空，**直接报错停止**并提示用户配置。
2. 调 `scripts/discover.py --config references/up-list.yaml --state-file data/state.json --cookies config/cookies.txt`。
3. 解析 stdout JSON 得到未处理视频列表。若 stderr 出现 `SELF_COOKIE_EXPIRED`，调用 `lark-im` skill 立即发告警到群，本次扫描跳过 self 源继续处理公开源。
4. 对每条视频**串行**处理（规模小，无并发必要）：
   - 调 `state.py mark <bvid> --status discovered --source <local|ytdlp>`（若已是 discovered 则更新时间戳）
   - 调 `fetch.py <bvid> --config ... --cookies ... --videos-dir data/videos --pubdate <pubdate> [--is-self]`；解析 `{"path": "..."}`；失败调 `state.py mark <bvid> --status fetch_err --error <msg>`，跳到下一条
   - 调 `transcribe.py <path> --out-dir data/subtitles --hotwords references/funasr-hotwords.txt`；若返回 `skipped_*` 标记对应 state 跳过；失败标 `transcribe_err` 跳过；成功后 `state.py mark <bvid> --status transcribed --method <L1|L2|L3>`
   - **读取** `{txt_path}`；若内容少于 500 字符，产出占位报告（标题 + "内容不足"一行），否则读 `references/review-prompt.md`，把 txt 内容和 prompt 拼接，生成 markdown 报告保存到 `data/reports/{YYYY-MM-DD}_{owner_mid}_{bvid}.md`，标 `analyzed`
   - 调 lark-im skill 发送报告（见下）；标 `notified` 后标 `done`
5. 所有视频处理结束，汇总成功/失败，调 lark-im 发一条"扫描汇总"消息，含失败条的重试命令 `/stock-review <bvid>`。

### 单条模式
- 本地路径：跳过 `discover`；**不写 state**（一次性场景）；直接从 `fetch.py`（本地路径直通）走到结束。
- BVID/URL：若不在 state 或 state 非 `done`，直接按 scan 流单条处理；若 `done`，提示用户"已分析过，若要重新分析请先 `rm data/state.json` 对应字段或手动删除"，不擅自覆盖。

## 飞书发送规则
- 发送目标：`notify.lark_chat_id`
- 单条报告 `len(markdown) <= notify.max_message_chars` → 直接发文本消息
- 超长 → 发 markdown 文件（`lark-im +send-file`，文件名 `{YYYY-MM-DD}_{owner}_{bvid}.md`）

## 错误重试
- discover 的 HTTP 重试已在脚本内部完成（3 次指数退避）
- fetch 的 yt-dlp 重试同上
- lark-im 发送失败本 skill 层面重试 3 次，仍失败只更新 state 不中断整批

## 前置检查
第一次运行前确认：
- `uv sync` 通过
- `yt-dlp --version` / `ffmpeg -version` 可用
- `uv run python -c "import funasr"` 不报错
- `references/up-list.yaml` 的 `self.mid`、`ups[*].mid`、`notify.lark_chat_id` 都填好
- `config/cookies.txt` 存在且非空
- `data/` 及其子目录可写