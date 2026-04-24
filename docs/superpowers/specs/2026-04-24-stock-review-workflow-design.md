# 股市复盘工作流 设计文档

**日期**: 2026-04-24
**状态**: Draft (待审核)
**作者**: @richardwild426 + Claude
**路径**: `/Users/zvector/ws/workflow/stock-review/`

## 1. 背景与目标

### 1.1 背景

- 使用者每天跟踪 1-2 位 B 站股市复盘**直播** up 主 + 1-2 位发**视频**的 up 主
- 直播录制已用 [biliup.rs](https://docs.biliup.rs/) 自动完成，录播落地 `~/Movies/bilive-recoder/backup/`，并由 biliup 自动投稿到自己 B 站账号（私密投稿）
- 痛点：直播/视频本身 1-3 小时，逐条观看效率低；希望自动把"直播/视频内容"转成结构化复盘摘要推到飞书

### 1.2 目标

构建一个由 Claude Code Skill 驱动的本地流水线：

```
B 站视频（自己录播私密投稿 + 关注 up 主公开视频）
    或 本地 mp4 文件
        ↓
  字幕提取（三级策略）
        ↓
  Claude 应用股市复盘提示词生成结构化摘要
        ↓
  飞书群消息通知
```

### 1.3 非目标

- **不**实时分析直播流（录制/投稿链路由 biliup.rs 负责，分析在视频落地后异步触发）
- **不**抓取行情/K 线做交叉验证（纯文本摘要）
- **不**多 up 主观点交叉比对（V1 只做单视频摘要）
- **不**上云；**不**用 Docker；纯 macOS 本地运行
- **不**配 CI

## 2. 总体架构

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────────┐
│          Claude Skill: stock-review (SKILL.md)                │
│                                                                │
│   入口:  /stock-review scan           (自动, launchd 调用)      │
│          /stock-review <BVID|URL|path> (手动)                  │
└─────────────┬────────────────────────────────────────────────┘
              │
      ┌───────┴───────┐
      │               │
      ▼               ▼
   [scan 流]       [单条流]
      │               │
      ▼               │
┌──────────────┐      │
│ discover.py  │      │  # 拉自己 + up 主最近 N 条 → 对比 state
└──────┬───────┘      │  # 输出未处理 BVID 列表
       │              │
       └───────┬──────┘
               ▼
        ┌──────────────┐
        │  fetch.py    │  # 本地 mp4 路径 → 直接用
        │              │  # 自己录播 BVID → 扫 biliup base_dir 对齐 pubdate
        │              │  # 其他 → yt-dlp 下载（带 cookie）
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ transcribe.py│  # L1 嵌入字幕 → L2 RapidOCR → L3 FunASR
        └──────┬───────┘
               ▼ (srt + txt)
        ┌──────────────┐
        │ Claude 本体   │  # 读 txt + review-prompt.md → md 报告
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ lark-im skill│  # 发飞书群（超长转文件）
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   state.py   │  # 标记 BVID 已处理
        └──────────────┘
```

### 2.2 设计原则

1. **Claude 做语义活，脚本做确定性活**：发现/下载/字幕提取用 Python 脚本；读字幕判断干货段落、套复盘 prompt、编排失败重试用 Claude 本体
2. **输入源归一**：本地 mp4 和 B 站 URL 在 `fetch.py` 之后归并成"本地绝对路径"，后续组件无感知
3. **单条失败不阻塞整批**：每步落 `state.json`，scan 完发汇总
4. **幂等 + 断点续跑**：状态机允许重跑从最后成功阶段继续

### 2.3 目录布局

```
stock-review/
├── .claude/
│   └── skills/
│       └── stock-review/
│           ├── SKILL.md                    # 主入口
│           ├── scripts/
│           │   ├── discover.py
│           │   ├── fetch.py
│           │   ├── transcribe.py
│           │   └── state.py
│           ├── references/
│           │   ├── review-prompt.md        # 复盘提示词
│           │   ├── up-list.yaml            # up 主配置
│           │   └── funasr-hotwords.txt     # 股市术语热词表
│           └── config/
│               └── cookies.txt             # B 站 cookie（gitignore）
├── data/
│   ├── state.json                          # 已处理 BVID 状态库
│   ├── videos/                             # yt-dlp 下载目录（2 个月 TTL）
│   ├── subtitles/                          # 字幕长期保留
│   └── reports/                            # 分析报告长期保留
├── docs/
│   └── superpowers/specs/
└── tests/
    ├── test_discover.py
    ├── test_fetch.py
    ├── test_transcribe.py
    └── test_state.py
```

## 3. 组件职责

### 3.1 `SKILL.md`

Claude 本体读取的 skill 入口，描述：

- 两种触发模式：`scan`（launchd 调用）/ 单条（BVID / URL / 本地路径自动判别）
- 主编排流程：调 discover → 逐条 fetch → transcribe → 读取字幕 → 套 `review-prompt.md` → 写 report → 调 lark-im → 调 state
- 错误处理策略（见 §6）

### 3.2 `scripts/discover.py`

- **输入**：`up-list.yaml` + `cookies.txt` + `state.json`
- **逻辑**：
  - 对每个 up 调 B 站 `/x/space/wbi/arc/search`（匿名）或 `/x/space/wbi/arc/search?pn=1&ps=30&mid=<self.mid>` 含 cookie（private 可见）
  - 拉最近 5 条投稿
  - 与 `state.json` 对比，输出未处理的
- **输出**（stdout JSON）：
  ```json
  [{"bvid": "BV1xx", "title": "...", "pubdate": 1745472000,
    "owner_mid": 123456, "is_self": true}]
  ```
- **副作用**：对新发现的 BVID 在 `state.json` 写 `discovered`
- **cookie 过期检测**：若 self 源返回 `code=-101` 或空列表但配置 `needs_cookie: true`，抛 `CookieExpired`

### 3.3 `scripts/fetch.py`

- **输入**：BVID、B 站 URL、本地路径（任意其一）
- **分支**：
  - 本地路径：校验存在 → 直接返回
  - BVID 在 up-list 的 `self` 名下 且 `prefer_local: true`：
    - 递归扫 `biliup.base_dir/**/*.mp4`
    - 取 `mtime` 与 `pubdate` 偏差 ≤ `mtime_tolerance_hours`（默认 6）的候选
    - 唯一命中 → 返回；0 或多命中 → fallback 到 yt-dlp
  - 其他情况：`yt-dlp -f 'bv*+ba/best' --cookies config/cookies.txt -o 'data/videos/%(id)s.%(ext)s' <URL>`
- **输出**：视频文件绝对路径
- **错误**：下载失败重试 3 次（指数退避），最终抛 `FetchError`

### 3.4 `scripts/transcribe.py`

复刻 [ALBEDO-TABAI/video-copy-analyzer](https://github.com/ALBEDO-TABAI/video-copy-analyzer/tree/master) 三级策略：

- **L1 嵌入字幕**：`ffprobe` 检测是否有 subtitle stream → `ffmpeg -map 0:s:0` 导出 srt
- **L2 RapidOCR**：`ffmpeg` 每 5s 采一帧 → RapidOCR 扫下方 1/4 区域，命中率 >30% 则全量 OCR → 时间对齐生成 srt
- **L3 FunASR**：`ffmpeg -ar 16000 -ac 1` 抽 wav → `funasr` paraformer-zh 模型 + `funasr-hotwords.txt` → srt
- **输出**：`{srt_path, txt_path, method: "L1"|"L2"|"L3", duration_sec}` JSON
- **跳过条件**：时长 < 60s → 返回 `{skipped: "too_short"}`；无音频轨 → 返回 `{skipped: "no_audio"}`

### 3.5 `scripts/state.py`

CLI 两个命令：

```
state.py mark <key> --status <status> [--report <path>] [--source <src>] [--error <msg>]
state.py list-unprocessed         # 输出所有 status != 'done' 的 key
state.py get <key>                # 查单条
```

- **存储**：`data/state.json`，格式：
  ```json
  {
    "BV1xxxxx": {
      "status": "done",
      "processed_at": "2026-04-24T21:30:00+08:00",
      "report_path": "data/reports/2026-04-24_up1_BV1xxxxx.md",
      "source": "local|ytdlp",
      "method": "L3",
      "error": null,
      "retry_count": 0
    }
  }
  ```

### 3.6 `references/up-list.yaml`

```yaml
biliup:
  base_dir: ~/Movies/bilive-recoder/backup
  mtime_tolerance_hours: 6

self:
  mid: 123456
  needs_cookie: true
  prefer_local: true

ups:
  - name: "某 up 主 A"
    mid: 987654
    needs_cookie: false
  - name: "某 up 主 B"
    mid: 876543
    needs_cookie: false

notify:
  lark_chat_id: ""    # 实施时填入飞书股市复盘群的 chat_id（例 oc_xxxxxxxx）
  video_retention_days: 60
  max_message_chars: 30000
```

### 3.7 `references/review-prompt.md`

（复盘提示词原文见附录 A）

## 4. 数据流 & 状态机

### 4.1 单条视频状态机

```
  discovered ──► fetched ──► transcribed ──► analyzed ──► notified ──► done
      │            │             │              │            │
      └─ *_err 分支：记录 error 和 retry_count，scan 结束汇总上报
```

**状态推进即写 `state.json`**。中断重跑从最后成功状态继续（fetch 已完成则不重下，transcribe 已完成则不重跑 ASR）。

### 4.2 scan 流时序

```
Claude (SKILL.md 编排)
│
├─ 1. discover.py → new_videos[]
│       (每条立即落 state.json: discovered)
│
├─ 2. for v in new_videos: (串行)
│       │
│       ├─ fetch.py → local_path       (state: fetched)
│       │
│       ├─ transcribe.py → txt_path    (state: transcribed)
│       │
│       ├─ Claude 读 txt + prompt → md (state: analyzed)
│       │
│       ├─ lark-im +send               (state: notified)
│       │
│       └─ state.py mark done          (state: done)
│
└─ 3. 汇总发飞书: 成功 N / 失败 M（含重试命令）
```

### 4.3 单条流（手动触发）

跳过 discover；若 `<arg>` 是本地 mp4 路径，**不写 state**（允许重复分析，一次性场景）；若是 BVID/URL，按 BVID 维护 state。

## 5. 关键决策摘要

| 决策点 | 选择 | 理由 |
|---|---|---|
| 架构形态 | Claude Skill + Python 脚本 | 贴合现有 skill 生态；语义/确定性分工清晰 |
| 字幕提取 | 三级策略（L1/L2/L3） | 成本最低到最高递进；中文优先 FunASR |
| 触发方式 | launchd 定时 `scan` + 手动单条 | 日常自动；补漏手动 |
| 自己录播定位 | pubdate ± mtime 匹配 | 不依赖 biliup 命名规则，可迁移 |
| 本地 mp4 的 state | 不写 state | 临时场景，简化特殊逻辑 |
| 并发度 | 串行 | 规模小（每天 ≤ 5 条新视频） |
| 视频清理期 | 2 个月 | 空间和回溯的平衡 |
| 通知目标 | 飞书群 | 多设备可查；群 ID 配置 |

## 6. 错误处理

### 6.1 各阶段失败分类

| 阶段 | 场景 | 策略 |
|---|---|---|
| discover | B 站 API 超时/限流 | 3 次重试，指数退避 1s/3s/9s |
| | cookie 过期（`code=-101` 或 self 源空）| 飞书单独告警 "请更新 cookies.txt"；跳过 self；继续 up 主源 |
| | up 主列表返回空 | 静默跳过，不计失败 |
| fetch | `prefer_local` 未命中 / 多命中 | fallback yt-dlp（不计失败）|
| | yt-dlp 下载失败 | 3 次重试 → `fetch_err` |
| | 磁盘剩余 < 5GB | 立即中断 scan + 飞书严重告警 |
| transcribe | L1/L2 都无命中 | 正常 fall 到 L3 |
| | 视频 < 60s / 无音频轨 | 标 `skipped_*`，不分析 |
| | FunASR 加载/推理失败 | `transcribe_err` |
| analyze | 字幕字数 < 500 | Claude 产出 "内容不足" 占位报告 |
| | 手动中断（Ctrl+C） | state 停在 `transcribed`，下次 scan 拾起 |
| notify | 消息超 `max_message_chars` | 转为 markdown 文件附件（`lark-im +send-file`） |
| | lark API 失败 | 3 次重试 → `notify_err` |

### 6.2 scan 结束汇总格式

```
## [2026-04-24] 股市复盘扫描汇总

成功 3 / 失败 1 / 跳过 0

✓ [自己录播] 《XXXX 盘后复盘》  → 报告
✓ [某 up 主 A] 《XXXX 板块分析》 → 报告
✓ [某 up 主 B] 《XXXX 尾盘观察》 → 报告
✗ [自己录播] 《XXXX》  fetch_err: yt-dlp HTTP 403
   → 重试: /stock-review BV1xxxxx
```

### 6.3 文件清理

- `data/videos/`：`find ... -mtime +60 -delete`（60 天），launchd daily job（与主 `scan` job 独立）
- `data/subtitles/` / `data/reports/`：长期保留

## 7. 测试策略

### 7.1 组件级（pytest）

I/O 全部 mock，只测纯逻辑：

| 组件 | 测试点 |
|---|---|
| `discover.py` | API 响应 → 新增 BVID 计算；cookie 过期检测 |
| `fetch.py` | pubdate ± mtime 匹配（单/多/0 命中）；URL 解析 |
| `transcribe.py` | L1/L2/L3 路由决策（mock ffprobe / RapidOCR 返回）|
| `state.py` | mark / list-unprocessed 幂等性 |

**不测**：真实 yt-dlp / 真实 FunASR / 真实 B 站 API。

### 7.2 端到端烟雾测试（手动）

三条 fixture 覆盖三种字幕路径：

1. 官方带字幕的 B 站视频 → L1
2. 带硬烧字幕的视频 → L2
3. 纯音频录播 → L3

重大改动后人工跑一遍，验证全链路无报错。

### 7.3 分析质量人工抽检

`references/analysis-rubric.md` 列检查项（大盘/板块/操作/纪律每段是否达标）。前 2 周每日检查，后续抽检；发现系统性问题反馈到 prompt 或 hotwords。

### 7.4 CI

不配。

## 8. 实施路线图（粗粒度，详细版由 writing-plans 生成）

1. **环境准备**：安装 yt-dlp / ffmpeg / FunASR / RapidOCR；配置 B 站 cookie；确认飞书群
2. **脚本层**：discover / fetch / transcribe / state + 对应 pytest
3. **Skill 层**：写 `SKILL.md` 编排逻辑 + `review-prompt.md` 入库
4. **端到端烟雾测试**：三条 fixture 跑通
5. **launchd 接入**：plist 每晚 21:00 / 23:00 跑 `scan`
6. **抽检迭代**：2 周观察期，调 prompt / hotwords

## 9. 附录 A：复盘提示词

````markdown
请对这段股票复盘直播内容做**超精简干货总结**，输出格式如下：

## [日期] 复盘 & 实盘公开

## 大盘
[指数强弱、关键支撑压力位、量能、风险点，字数 300 字内]
要求：包含具体点位数值、涨跌幅数据、量能变化百分比、基差状态
例：创业板跌 2% 涨 2% 拉回，权重小票未跌，缩量但盘面结构好转

## 板块
1. **[板块名]**：[走势 + 操作 + 风险，字数 200 字以内]
2. **[板块名]**：[走势 + 操作 + 风险，字数 200 字以内]
...（每个板块前用序号标注，板块间留空行）
要求：每个板块必须包含①当前走势描述（涨跌幅、形态、量能）②具体操作建议（买/卖/持有/观望 + 仓位比例）③关键价位或风险提示（支撑/压力/止损位）

## 操作
1. [仓位控制要点，包含具体仓位比例或加减仓条件]
2. [加仓/减仓时机，包含触发条件]
3. [止损条件，包含具体点位或百分比]

## 核心纪律
1. [主播强调的核心规则 1，原话或近原话]
2. [主播强调的核心规则 2，原话或近原话]
3. [主播强调的核心规则 3，原话或近原话]

**格式要求**：
- 语言精炼、直接、不带情绪
- 纯文本为主，不要 emoji、表格
- 板块前用序号标注（1. 2. 3.）
- 板块间不留空行
- 只在必要时区分 1、2、3 点
- 数据优先，避免模糊描述
````

## 10. 附录 B：参考实现

- 视频下载 + 字幕提取 技术参考：https://github.com/ALBEDO-TABAI/video-copy-analyzer
- biliup.rs：https://docs.biliup.rs/
- FunASR：https://github.com/modelscope/FunASR
- RapidOCR：https://github.com/RapidAI/RapidOCR
