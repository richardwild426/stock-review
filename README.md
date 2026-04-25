# Stock Review - 股市复盘视频自动分析工具

自动分析 B 站股市复盘直播/视频，生成结构化摘要并推送到飞书群。

## 功能

- **语音转录**：FunASR 高速中文 ASR（10分钟音频约22秒）
- **结构化摘要**：大盘/板块/操作/纪律四维度分析
- **飞书推送**：自动发送到指定群聊
- **多输入源**：本地录播扫描 + B站URL + 本地文件

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
git clone https://github.com/your-repo/stock-review.git ~/.claude/skills/stock-review
```

### 3. 配置

编辑 `references/up-list.yaml`：

```yaml
biliup:
  base_dir: ~/Movies/bilive-recoder/backup  # 本地录播目录

self:
  mid: 你的B站UID
  needs_cookie: true

notify:
  lark_chat_id: "oc_xxxxxx"  # 飞书群 chat_id
```

创建 B站 cookies 文件（用于下载私密视频）：

```bash
# 使用 Chrome 扩展 "Get cookies.txt LOCALLY" 导出
# 保存到 config/cookies.txt（Netscape 格式）
```

## 使用

### Claude Code 中触发

在 Claude Code 对话中直接说：

```
/stock-review scan                    # 扫描本地录播目录批量处理
/stock-review https://bilibili.com/video/BVxxx  # 分析单个B站视频
/stock-review /path/to/video.mp4      # 分析本地文件
```

### 命令行直接调用

```bash
# 扫描本地录播
python3 scripts/discover.py \
  --config references/up-list.yaml \
  --state-file data/state.json \
  --cookies config/cookies.txt \
  --skip-api

# 转录单个视频
python3 scripts/transcribe.py video.mp4 \
  --out-dir data/subtitles
```

## 目录结构

```
stock-review/                ← 仓库根 == Skill 根
├── SKILL.md                 # Skill 定义（Claude Code 读取）
├── README.md
├── pyproject.toml           # 依赖管理
├── uv.lock
├── .python-version
├── scripts/
│   ├── discover.py          # 视频发现
│   ├── transcribe.py        # 语音转录
│   ├── fetch.py             # 视频下载
│   └── state.py             # 状态管理
├── references/
│   ├── up-list.yaml         # 配置文件
│   ├── review-prompt.md     # 分析模板
│   ├── analysis-rubric.md   # 分析评分细则
│   └── funasr-hotwords.txt  # ASR 热词
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
## [2026-04-24] 复盘 & 实盘公开

## 大盘
创业板跌2%拉回，权重小票未跌，缩量但盘面结构好转...

## 板块
1. **电力**：近期大涨，建议已买减仓锁定利润...
2. **创新药**：ETF抛盘冲击，不要大跌第一天加仓...

## 操作
1. 单方向仓位不超20%
2. 大跌放量不要第一天加仓

## 核心纪律
1. "不会超过20%，超过多的我都觉得算重仓了"
```

## 注意事项

- **FunASR 首次运行**：需下载约2-3GB模型，耐心等待
- **B站 API 风控**：建议使用本地录播作为主要输入源
- **飞书权限**：确保 lark-cli 已配置且有群消息发送权限

## License

MIT