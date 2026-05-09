# Stock Review - 股市复盘视频自动分析工具

自动分析 B 站股市复盘直播/视频，生成结构化摘要并推送到飞书群。

## 功能

- **运行环境**：Python 3.11（见 `.python-version`）
- **语音转录**：FunASR 高速中文 ASR（10分钟音频约22秒）
- **结构化摘要**：大盘/外围/板块/纪律/明日 五段分析
- **飞书推送**：自动发送到指定群聊
- **输入源**：本地录播目录批量扫描；单条支持本地文件或 B 站 URL（yt-dlp 下载）

## 兼容性

本 Skill 按 [Agent Skills 开放规范](https://agentskills.io/) 构建，兼容多种智能体：

| 智能体 | 安装路径 |
|--------|----------|
| Claude Code | `~/.claude/skills/stock-review/` |
| Cursor | `.agents/skills/stock-review/` |
| VS Code Copilot | `.agents/skills/stock-review/` |
| Codex | `~/.codex/skills/stock-review/` |
| OpenHands, Goose, Junie 等 | 按各自 skills 目录规范 |

详见 [Agent Skills Clients](https://agentskills.io/clients)。

## 安装

### 1. 系统依赖

```bash
# macOS
brew install ffmpeg yt-dlp

# FunASR（语音转录引擎）
pip install funasr modelscope torch torchaudio
```

### 2. 作为 Claude Code Skill 安装

本仓库即 Skill，clone 到 Claude Code skills 目录：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/richardwild426/stock-review.git ~/.claude/skills/stock-review
```

**智能体一键安装**：将下面这段话发给你的智能体（Claude Code、Codex 等）：

```
以 skill/plugin 形式安装 https://github.com/richardwild426/stock-review.git，按你支持的插件安装机制处理。
```

### 3. 配置

编辑 `references/up-list.yaml`：

```yaml
biliup:
  base_dir: ~/Movies/bilive-recoder/backup  # 本地录播目录

notify:
  lark_chat_id: "oc_xxxxxx"  # 飞书群 chat_id
  max_message_chars: 30000

discover:
  max_retries: 3                            # 失败次数上限
```

可选——B 站 cookies（仅在用 yt-dlp 下载需要登录可见的视频时用到）：

```bash
# 用 Chrome 扩展 "Get cookies.txt LOCALLY" 导出
# 保存到 config/cookies.txt（Netscape 格式）
```

## 使用

### Claude Code 中触发

本 Skill 通过 description 关键词自动匹配，没有注册 slash 命令。在对话里用自然语言触发即可：

```
复盘 scan                                      # 扫描本地录播目录批量处理
复盘 https://www.bilibili.com/video/BVxxx     # 分析单个B站视频
复盘 /path/to/video.mp4                       # 分析本地文件
```

### 命令行直接调用

```bash
# 扫描本地录播
python3 scripts/discover.py \
  --config references/up-list.yaml \
  --state-file data/state.json

# 转录单个视频
python3 scripts/transcribe.py video.mp4 \
  --out-dir data/subtitles \
  --hotwords references/funasr-hotwords.txt
```

## 目录结构

```
stock-review/                ← 仓库根 == Skill 根
├── SKILL.md                 # Skill 定义（Agent Skills 规范）
├── README.md
├── pyproject.toml           # 依赖管理
├── uv.lock
├── .python-version
├── scripts/
│   ├── discover.py          # 本地录播扫描
│   ├── transcribe.py        # 语音转录（FunASR）
│   └── state.py             # 状态管理
├── references/
│   ├── up-list.yaml         # 配置文件
│   ├── review-prompt.md     # 分析模板
│   ├── workflow-detail.md   # 详细工作流程
│   ├── analysis-rubric.md   # 分析评分细则
│   └── funasr-hotwords.txt  # ASR 热词
├── assets/
│   └── report-template.md   # 报告输出模板
├── config/
│   ├── cookies.txt.example  # cookies 模板
│   └── cookies.txt          # B站 cookies（gitignore）
└── data/                    # 数据目录（gitignore）
    ├── videos/
    ├── subtitles/
    ├── reports/
    └── state.json
```

## 前置检查

首次使用前确认：

```bash
# 检查依赖
ffmpeg -version
yt-dlp --version
python3 -c "from funasr import AutoModel; print('OK')"

# 检查配置
grep -E "(base_dir|lark_chat_id)" references/up-list.yaml
```

## 输出示例

```markdown
# [2026-04-24] 复盘

## 一、当日大盘整体研判
创业板跌 2.1% 收 2780，权重小票未跌，量能较前日缩 12%。结构性赚钱效应延续...

## 二、外围联动分析
（字幕未提及，省略）

## 三、各板块逐条复盘
1. **电力**：当日 +3.4%，主线持续性强，建议已买仓位减半锁定利润，关键支撑 X.XX...
2. **创新药**：ETF 抛盘冲击 -2%，逻辑未破但情绪降温，不要大跌第一天加仓...

## 四、实操买卖纪律
1. 单方向仓位不超 20%
2. 大跌放量不要第一天加仓，等缩量再分批

## 五、明日重点 + 后市展望
关注煤炭板块能否放量突破，触发条件：上证指数站稳 3200。
```

报告完整结构与字数要求详见 `references/review-prompt.md`。

## 注意事项

- **FunASR 首次运行**：需下载约 2-3GB 模型，耐心等待
- **录播来源**：依赖 [biliup.rs](https://github.com/biliup/biliup-rs) 一类工具自动落盘到 `biliup.base_dir`；脚本只负责扫描与转录
- **飞书权限**：确保 lark-cli 已配置且有群消息发送权限
- **重跑失败条目**：`retry_count` 达到 `discover.max_retries` 后 discover 不再返回，需手工编辑 `data/state.json` 把对应 `retry_count` 清零

## 设计决策（Design Notes）

### 为什么是「仓库即 Skill」
本仓库直接作为 Claude Code Skill 分发：clone 到 `~/.claude/skills/stock-review/`
即可使用，不再嵌套 `.claude/skills/<name>/`。SKILL 元数据、脚本、参考材料、
配置和运行时数据全部位于仓库根。

### 三级字幕提取策略
- **L1 嵌入字幕**：ffmpeg 抽取字幕流（最快、零成本）
- **L2 OCR**：RapidOCR 识别硬字幕（占位，未默认启用）
- **L3 ASR**：FunASR 中文识别 + VAD + 标点恢复（兜底）

`scripts/transcribe.py` 自动按 L1 → L3 降级。

### 不再走 B 站 API
之前实现过 WBI 签名拉某 up 投稿列表，签名规则会随 B 站更新失效，长期维护成本
太高。当前只保留两条路径：
- 主路径：`biliup.rs` 把直播录播持续落到 `biliup.base_dir`，discover 扫描
- 单条：B 站视频 URL 由 `yt-dlp` 下载

如需重新接入 API，再按需补回（当前脚本已不带任何 B 站 API 代码）。

### 状态机
`scripts/state.py` 维护 `data/state.json`，按 key 幂等推进：
`discovered → transcribed → analyzed → notified → done`。
失败标记 `*_err` 后 `retry_count++`；达到 `discover.max_retries` 后 discover
不再返回。

### 飞书发送阈值
报告 ≤ `notify.max_message_chars` 走文本消息，超长走文件上传
（通过 lark-im skill 的 `+send-file`）。

### 数据目录归属
`data/` 位于仓库根、git 忽略。Skill 假设「仓库根 == 工作根」——
若部署到其他位置，需调整或在 `references/up-list.yaml` 中显式指定路径。

## License

MIT