# 股市复盘工作流 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个由 Claude Code Skill 驱动的本地流水线：把 B 站股市复盘直播/视频（自己私密投稿的录播 + 关注 up 主的公开视频）或本地 mp4 自动转录、摘要为结构化复盘报告，推送到飞书群。

**Architecture:** Claude Code 项目级 Skill `stock-review` 作为编排层；Python 脚本 `discover.py / fetch.py / transcribe.py / state.py` 负责确定性 I/O；Claude 本体负责读取字幕并套复盘 prompt 产出 markdown。字幕提取遵循三级策略（嵌入字幕 → RapidOCR → FunASR）。launchd 每晚定时触发 `scan`，手动触发单条走同一流水线。

**Tech Stack:** Python 3.11 + uv；pytest / pytest-mock / pyyaml / httpx；外部工具 ffmpeg / yt-dlp / FunASR (paraformer-zh) / RapidOCR (ONNX)；飞书通知用现有 `lark-im` skill；macOS launchd 做定时。

---

## 文件结构总览

**新建文件**（以项目根 `/Users/zvector/ws/workflow/stock-review/` 为基准）：

```
pyproject.toml                                  # uv + pytest + ruff 配置
Justfile                                        # 常用命令
README.md                                       # 快速索引
.python-version                                 # 3.11

.claude/skills/stock-review/
├── SKILL.md                                    # Claude 编排入口（主描述）
├── scripts/
│   ├── __init__.py
│   ├── state.py                                # BVID 状态读写 CLI
│   ├── discover.py                             # 拉 up 主投稿列表 + 比对 state
│   ├── fetch.py                                # 本地匹配 / yt-dlp 下载
│   └── transcribe.py                           # 三级字幕提取
├── references/
│   ├── review-prompt.md                        # 股市复盘提示词
│   ├── up-list.yaml                            # up 主配置模板
│   ├── funasr-hotwords.txt                     # 股市术语热词（种子）
│   └── analysis-rubric.md                      # 分析质量自查清单
└── config/
    ├── cookies.txt.example                     # cookie 文件模板
    └── .gitkeep

tests/
├── __init__.py
├── conftest.py                                 # 公共 fixture
├── test_state.py
├── test_discover.py
├── test_fetch.py
└── test_transcribe.py

launchd/
├── com.zvector.stock-review.scan.plist         # 每日定时扫描
├── com.zvector.stock-review.cleanup.plist      # 清理旧视频
└── cleanup.sh                                  # 清理脚本
```

**运行时生成目录**（被 `.gitignore` 排除）：

```
data/
├── state.json
├── videos/     # 2 个月 TTL
├── subtitles/  # 长期
└── reports/    # 长期
```

**每个文件的职责**：

| 文件 | 职责 |
|---|---|
| `scripts/state.py` | CLI：`mark` / `get` / `list-unprocessed`；读写 `data/state.json` |
| `scripts/discover.py` | CLI：拉每个 up 主最近 N 条投稿，对比 state，输出未处理 BVID 列表 JSON |
| `scripts/fetch.py` | CLI：给定 BVID/URL/路径，返回可分析的本地视频绝对路径 |
| `scripts/transcribe.py` | CLI：给定视频路径，走 L1/L2/L3 生成 srt + txt |
| `SKILL.md` | Claude 读取的编排说明；描述两种入口和主循环 |
| `references/review-prompt.md` | 套用的股市复盘提示词 |
| `references/up-list.yaml` | 自己账号 + 关注 up 主配置；biliup 目录路径；飞书群 ID |
| `references/funasr-hotwords.txt` | ASR 热词表，一行一个术语 |
| `launchd/*.plist` | macOS 定时任务描述 |
| `launchd/cleanup.sh` | 执行视频目录的 60 天清理 |
| `tests/*.py` | pytest 组件级测试 |

---

## 任务 1：工程骨架

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `Justfile`
- Create: `README.md`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.claude/skills/stock-review/scripts/__init__.py`
- Create: `.claude/skills/stock-review/config/.gitkeep`
- Create: `.claude/skills/stock-review/config/cookies.txt.example`

- [ ] **Step 1.1：写 `.python-version`**

```
3.11
```

- [ ] **Step 1.2：写 `pyproject.toml`**

```toml
[project]
name = "stock-review"
version = "0.1.0"
description = "Stock market replay analyzer driven by Claude Code"
requires-python = ">=3.11,<3.12"
dependencies = [
    "httpx>=0.27",
    "pyyaml>=6.0",
    "pysrt>=1.1",
    "python-dateutil>=2.9",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".claude/skills/stock-review"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

说明：FunASR / RapidOCR 较重，不进 `dependencies`，任务 6 单独以 optional group 或运行期按需提示安装（避免拖慢普通开发测试）。

- [ ] **Step 1.3：写 `Justfile`**

```makefile
set shell := ["bash", "-cu"]

test:
    uv run pytest

test-one name:
    uv run pytest -k {{name}}

lint:
    uv run ruff check .

fmt:
    uv run ruff format .

# 手动扫描
scan:
    claude -p "/stock-review scan"

# 手动分析单条
analyze target:
    claude -p "/stock-review {{target}}"
```

- [ ] **Step 1.4：写 `README.md`**

```markdown
# Stock Review

B 站股市复盘直播/视频自动分析工作流。设计文档：[`docs/superpowers/specs/2026-04-24-stock-review-workflow-design.md`](docs/superpowers/specs/2026-04-24-stock-review-workflow-design.md)

## 快速开始

```bash
uv sync
just test
```

## 触发方式

- 自动扫描：`just scan`（launchd 每晚自动调用）
- 手动分析：`just analyze <BVID|URL|本地路径>`

## 配置

- `.claude/skills/stock-review/references/up-list.yaml`：关注的 up 主
- `.claude/skills/stock-review/config/cookies.txt`：B 站 cookie（不入库）
```

- [ ] **Step 1.5：创建空占位**

```bash
mkdir -p .claude/skills/stock-review/scripts
mkdir -p .claude/skills/stock-review/references
mkdir -p .claude/skills/stock-review/config
mkdir -p tests data/videos data/subtitles data/reports launchd

touch .claude/skills/stock-review/scripts/__init__.py
touch .claude/skills/stock-review/config/.gitkeep
touch tests/__init__.py
```

- [ ] **Step 1.6：写 `tests/conftest.py`**

```python
import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_state_file(tmp_path: Path) -> Path:
    """Empty state.json for per-test isolation."""
    f = tmp_path / "state.json"
    f.write_text("{}")
    return f


@pytest.fixture
def sample_state_file(tmp_path: Path) -> Path:
    """Preloaded state.json with a mix of statuses."""
    f = tmp_path / "state.json"
    f.write_text(json.dumps({
        "BV1AAA": {"status": "done", "processed_at": "2026-04-23T21:30:00+08:00",
                    "report_path": "data/reports/x.md", "source": "local",
                    "method": "L3", "error": None, "retry_count": 0},
        "BV1BBB": {"status": "fetched", "processed_at": "2026-04-23T22:00:00+08:00",
                    "report_path": None, "source": "ytdlp",
                    "method": None, "error": None, "retry_count": 0},
        "BV1CCC": {"status": "fetch_err", "processed_at": "2026-04-23T22:05:00+08:00",
                    "report_path": None, "source": "ytdlp",
                    "method": None, "error": "HTTP 403", "retry_count": 3},
    }))
    return f
```

- [ ] **Step 1.7：写 `.claude/skills/stock-review/config/cookies.txt.example`**

```
# 从浏览器导出 B 站 cookies 到此文件（真实文件名为 cookies.txt，已被 gitignore）
# 推荐 yt-dlp 兼容格式（Netscape HTTP Cookie File）
# 用 Chrome 扩展 "Get cookies.txt LOCALLY" 导出
```

- [ ] **Step 1.8：生成 uv lock 并验证**

```bash
uv sync
uv run python -c "import httpx, yaml, pysrt; print('deps ok')"
uv run pytest --collect-only
```

预期：`deps ok`，pytest 报 "no tests ran"（目录存在但暂无用例）。

- [ ] **Step 1.9：提交**

```bash
git add pyproject.toml .python-version Justfile README.md uv.lock \
        .claude/skills/stock-review/config/cookies.txt.example \
        .claude/skills/stock-review/config/.gitkeep \
        .claude/skills/stock-review/scripts/__init__.py \
        tests/__init__.py tests/conftest.py
git commit -m "chore: 初始化 stock-review 项目骨架与依赖"
```

---

## 任务 2：`state.py`（状态读写）

先做 state 是因为它最简单、零外部依赖，也被后续所有模块复用。

**Files:**
- Create: `.claude/skills/stock-review/scripts/state.py`
- Create: `tests/test_state.py`

### 2.1 先写失败测试

- [ ] **Step 2.1.1：写 `tests/test_state.py`**

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/state.py"


def run_cli(args: list[str], state_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state-file", str(state_file), *args],
        capture_output=True, text=True,
    )


class TestMark:
    def test_mark_creates_entry(self, tmp_state_file: Path):
        r = run_cli(
            ["mark", "BV1XXX", "--status", "discovered", "--source", "ytdlp"],
            tmp_state_file,
        )
        assert r.returncode == 0, r.stderr
        state = json.loads(tmp_state_file.read_text())
        assert state["BV1XXX"]["status"] == "discovered"
        assert state["BV1XXX"]["source"] == "ytdlp"
        assert state["BV1XXX"]["retry_count"] == 0
        assert state["BV1XXX"]["processed_at"] is not None

    def test_mark_updates_existing_entry(self, sample_state_file: Path):
        r = run_cli(
            ["mark", "BV1BBB", "--status", "transcribed"],
            sample_state_file,
        )
        assert r.returncode == 0
        state = json.loads(sample_state_file.read_text())
        assert state["BV1BBB"]["status"] == "transcribed"
        # source 保留原值（没传就不覆盖）
        assert state["BV1BBB"]["source"] == "ytdlp"

    def test_mark_error_increments_retry(self, sample_state_file: Path):
        r = run_cli(
            ["mark", "BV1BBB", "--status", "fetch_err", "--error", "timeout"],
            sample_state_file,
        )
        assert r.returncode == 0
        state = json.loads(sample_state_file.read_text())
        assert state["BV1BBB"]["error"] == "timeout"
        assert state["BV1BBB"]["retry_count"] == 1


class TestGet:
    def test_get_existing(self, sample_state_file: Path):
        r = run_cli(["get", "BV1AAA"], sample_state_file)
        assert r.returncode == 0
        assert json.loads(r.stdout)["status"] == "done"

    def test_get_missing_exits_nonzero(self, tmp_state_file: Path):
        r = run_cli(["get", "BV_NOPE"], tmp_state_file)
        assert r.returncode != 0


class TestListUnprocessed:
    def test_excludes_done(self, sample_state_file: Path):
        r = run_cli(["list-unprocessed"], sample_state_file)
        assert r.returncode == 0
        unprocessed = json.loads(r.stdout)
        bvids = [item["bvid"] for item in unprocessed]
        assert "BV1AAA" not in bvids
        assert "BV1BBB" in bvids
        assert "BV1CCC" in bvids

    def test_empty_state(self, tmp_state_file: Path):
        r = run_cli(["list-unprocessed"], tmp_state_file)
        assert r.returncode == 0
        assert json.loads(r.stdout) == []
```

- [ ] **Step 2.1.2：运行测试确认失败**

```bash
uv run pytest tests/test_state.py -v
```

预期：`FileNotFoundError` 或 `SCRIPT` 不存在。

### 2.2 实现 state.py

- [ ] **Step 2.2.1：写 `.claude/skills/stock-review/scripts/state.py`**

```python
#!/usr/bin/env python3
"""State store for stock-review pipeline (JSON-backed CLI)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUSES = {
    "discovered", "fetched", "transcribed", "analyzed", "notified", "done",
    "fetch_err", "transcribe_err", "analyze_err", "notify_err",
    "skipped_too_short", "skipped_no_audio",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text() or "{}")


def _save(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_mark(args: argparse.Namespace) -> int:
    if args.status not in VALID_STATUSES:
        print(f"invalid status: {args.status}", file=sys.stderr)
        return 2
    state = _load(args.state_file)
    entry = state.get(args.key, {
        "status": "discovered", "processed_at": None, "report_path": None,
        "source": None, "method": None, "error": None, "retry_count": 0,
    })
    entry["status"] = args.status
    entry["processed_at"] = _now_iso()
    if args.source is not None:
        entry["source"] = args.source
    if args.method is not None:
        entry["method"] = args.method
    if args.report is not None:
        entry["report_path"] = args.report
    if args.error is not None:
        entry["error"] = args.error
        if args.status.endswith("_err"):
            entry["retry_count"] = entry.get("retry_count", 0) + 1
    state[args.key] = entry
    _save(args.state_file, state)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    state = _load(args.state_file)
    if args.key not in state:
        print(f"not found: {args.key}", file=sys.stderr)
        return 1
    json.dump(state[args.key], sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def cmd_list_unprocessed(args: argparse.Namespace) -> int:
    state = _load(args.state_file)
    rows = [{"bvid": k, **v} for k, v in state.items() if v.get("status") != "done"]
    json.dump(rows, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="state store CLI")
    p.add_argument("--state-file", type=Path, required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mark")
    m.add_argument("key")
    m.add_argument("--status", required=True)
    m.add_argument("--source")
    m.add_argument("--method")
    m.add_argument("--report")
    m.add_argument("--error")
    m.set_defaults(func=cmd_mark)

    g = sub.add_parser("get")
    g.add_argument("key")
    g.set_defaults(func=cmd_get)

    lu = sub.add_parser("list-unprocessed")
    lu.set_defaults(func=cmd_list_unprocessed)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.2.2：运行测试通过**

```bash
uv run pytest tests/test_state.py -v
```

预期：所有用例 PASS。

- [ ] **Step 2.2.3：提交**

```bash
git add .claude/skills/stock-review/scripts/state.py tests/test_state.py
git commit -m "feat(state): 增加 BVID 状态管理 CLI（mark/get/list-unprocessed）"
```

---

## 任务 3：配置文件（`up-list.yaml` / `review-prompt.md` / hotwords / rubric）

在写 discover/fetch 之前先把配置结构定下来，脚本直接引用。

**Files:**
- Create: `.claude/skills/stock-review/references/up-list.yaml`
- Create: `.claude/skills/stock-review/references/review-prompt.md`
- Create: `.claude/skills/stock-review/references/funasr-hotwords.txt`
- Create: `.claude/skills/stock-review/references/analysis-rubric.md`

- [ ] **Step 3.1：写 `up-list.yaml`**

```yaml
# 股市复盘工作流配置
# 修改后不需要重启任何进程，脚本每次运行读取最新版本

biliup:
  base_dir: ~/Movies/bilive-recoder/backup    # biliup.rs 的录播落盘目录
  mtime_tolerance_hours: 6                    # pubdate 与文件 mtime 允许偏差

self:
  mid: 0                                       # 运行前改为你的 B 站 UID
  needs_cookie: true
  prefer_local: true

ups:
  # 运行前改为你关注的 up 主列表
  - name: "示例 up 主 A"
    mid: 0
    needs_cookie: false

notify:
  lark_chat_id: ""                            # 运行前填飞书"股市复盘"群 chat_id
  video_retention_days: 60
  max_message_chars: 30000

discover:
  per_up_fetch_count: 5                       # 每个 up 拉最近 N 条
  http_timeout_seconds: 15
  http_retries: 3
```

- [ ] **Step 3.2：写 `review-prompt.md`**

```markdown
# 股市复盘提示词

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
```

- [ ] **Step 3.3：写 `funasr-hotwords.txt`（种子术语）**

```
沪深300
创业板
科创板
北证50
权重股
小盘股
大盘股
量能
均线
MACD
KDJ
RSI
布林带
支撑位
压力位
涨停
跌停
板块轮动
业绩预告
机构调仓
融资融券
北向资金
南向资金
龙头股
白马股
题材股
新能源
光伏
风电
储能
半导体
人工智能
机器人
军工
医药
消费
白酒
房地产
基建
有色金属
煤炭
石油
银行
券商
保险
基差
升水
贴水
分时图
日K
周K
年线
半年线
20日均线
60日均线
```

- [ ] **Step 3.4：写 `analysis-rubric.md`（分析质量自查清单）**

```markdown
# 复盘报告质量自查

每份报告人工打 0/1：

- [ ] 大盘段包含具体点位数值（如 3200、创业板 2800）
- [ ] 大盘段包含涨跌幅 / 量能变化百分比
- [ ] 板块段每条都有：走势描述 + 操作建议 + 风险/价位
- [ ] 操作段有具体仓位比例或加减仓条件
- [ ] 核心纪律保留了主播原话感（不是 AI 改写味）
- [ ] 全文无 emoji / 无多余寒暄
- [ ] 板块使用 1./2./3. 序号，板块间不空行（符合模板）
- [ ] 长度控制：大盘 ≤ 300 字，每个板块 ≤ 200 字

达标 ≥ 7/8 算合格。不达标 → 记录失败模式到 `discover.md` issue 里，周末统一调整 prompt 或 hotwords。
```

- [ ] **Step 3.5：提交**

```bash
git add .claude/skills/stock-review/references/
git commit -m "feat(config): 增加 up-list 配置模板、复盘提示词、ASR 热词与质量自查清单"
```

---

## 任务 4：`discover.py`（拉投稿列表）

**Files:**
- Create: `.claude/skills/stock-review/scripts/discover.py`
- Create: `tests/test_discover.py`

B 站公开投稿接口：`https://api.bilibili.com/x/space/wbi/arc/search?mid=<mid>&ps=5&pn=1`
返回结构（节选）：

```json
{
  "code": 0,
  "data": {
    "list": {
      "vlist": [
        {"bvid": "BV1xx", "title": "...", "created": 1745472000, "mid": 123456}
      ]
    }
  }
}
```

注意：该接口需要 WBI 签名（风控），简化方案是走旧接口 `https://api.bilibili.com/x/space/arc/search?mid=<mid>&ps=5&pn=1`（目前仍可用）；若被风控阻断，再切 WBI。私密投稿需 cookie，`code=-101` 表示未登录。

### 4.1 写失败测试

- [ ] **Step 4.1.1：写 `tests/test_discover.py`**

```python
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/discover.py"


def _fake_api_response(vlist: list[dict], code: int = 0) -> dict:
    return {"code": code, "data": {"list": {"vlist": vlist}}}


def _make_config(tmp_path: Path, self_mid: int = 100, ups: list[dict] | None = None) -> Path:
    import yaml
    cfg = {
        "biliup": {"base_dir": str(tmp_path), "mtime_tolerance_hours": 6},
        "self": {"mid": self_mid, "needs_cookie": True, "prefer_local": True},
        "ups": ups or [{"name": "up A", "mid": 200, "needs_cookie": False}],
        "notify": {"lark_chat_id": "oc_x", "video_retention_days": 60,
                   "max_message_chars": 30000},
        "discover": {"per_up_fetch_count": 5, "http_timeout_seconds": 5,
                     "http_retries": 1},
    }
    f = tmp_path / "up-list.yaml"
    f.write_text(yaml.safe_dump(cfg))
    return f


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )


# 以下测试通过 import 直接测内部纯函数以便 mock。
# 把脚本也设计成可 import 的模块。

import importlib.util

spec = importlib.util.spec_from_file_location("discover", SCRIPT)
discover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discover)


class TestFetchForUp:
    def test_returns_latest_videos(self):
        mock_response = _fake_api_response([
            {"bvid": "BV1AAA", "title": "盘后复盘 1", "created": 1745472000, "mid": 200},
            {"bvid": "BV1BBB", "title": "盘后复盘 2", "created": 1745385600, "mid": 200},
        ])
        with patch.object(discover, "_call_bili_api", return_value=mock_response):
            result = discover.fetch_for_up(mid=200, count=5, cookie=None, timeout=5, retries=1)
        assert len(result) == 2
        assert result[0]["bvid"] == "BV1AAA"
        assert result[0]["pubdate"] == 1745472000

    def test_cookie_expired_raises(self):
        with patch.object(discover, "_call_bili_api",
                          return_value={"code": -101, "message": "未登录"}):
            with pytest.raises(discover.CookieExpired):
                discover.fetch_for_up(mid=100, count=5, cookie="abc",
                                       timeout=5, retries=1, requires_cookie=True)

    def test_empty_list_raises_when_cookie_required(self):
        # self 源拿到空列表但需要 cookie → 视为 cookie 无效
        with patch.object(discover, "_call_bili_api",
                          return_value=_fake_api_response([])):
            with pytest.raises(discover.CookieExpired):
                discover.fetch_for_up(mid=100, count=5, cookie="abc",
                                       timeout=5, retries=1, requires_cookie=True)

    def test_empty_list_ok_for_public(self):
        # 公开 up 返回空列表是正常的（新号或全删）
        with patch.object(discover, "_call_bili_api",
                          return_value=_fake_api_response([])):
            result = discover.fetch_for_up(mid=200, count=5, cookie=None,
                                             timeout=5, retries=1, requires_cookie=False)
        assert result == []


class TestDiffAgainstState:
    def test_returns_only_new(self, sample_state_file: Path):
        candidates = [
            {"bvid": "BV1AAA", "title": "x", "pubdate": 1, "owner_mid": 200, "is_self": False},
            {"bvid": "BV1NEW", "title": "y", "pubdate": 2, "owner_mid": 200, "is_self": False},
        ]
        new = discover.diff_against_state(candidates, sample_state_file)
        assert [v["bvid"] for v in new] == ["BV1NEW"]

    def test_err_status_treated_as_unfinished(self, sample_state_file: Path):
        # BV1CCC 是 fetch_err 状态，应当被重新处理
        candidates = [{"bvid": "BV1CCC", "title": "x", "pubdate": 1,
                       "owner_mid": 200, "is_self": False}]
        new = discover.diff_against_state(candidates, sample_state_file)
        assert new[0]["bvid"] == "BV1CCC"


class TestCLI:
    def test_outputs_json_with_all_new(self, tmp_path: Path, monkeypatch):
        config = _make_config(tmp_path, self_mid=100)
        state = tmp_path / "state.json"
        state.write_text("{}")

        def fake_fetch(mid, count, cookie, timeout, retries, requires_cookie=False):
            return [{"bvid": f"BV_{mid}", "title": "t", "pubdate": 1,
                     "owner_mid": mid, "is_self": mid == 100}]

        monkeypatch.setattr(discover, "fetch_for_up", fake_fetch)
        args = ["--config", str(config), "--state-file", str(state),
                "--cookies", "/dev/null"]
        # 直接调 main(argv) 而不是 subprocess，便于 monkeypatch
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = discover.main(args)
        assert rc == 0
        rows = json.loads(buf.getvalue())
        bvids = sorted(r["bvid"] for r in rows)
        assert bvids == ["BV_100", "BV_200"]
```

- [ ] **Step 4.1.2：运行测试确认失败**

```bash
uv run pytest tests/test_discover.py -v
```

预期：`ModuleNotFoundError` 或脚本不存在。

### 4.2 实现 discover.py

- [ ] **Step 4.2.1：写 `.claude/skills/stock-review/scripts/discover.py`**

```python
#!/usr/bin/env python3
"""Discover new uploads from Bilibili and diff against local state."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

BILI_API = "https://api.bilibili.com/x/space/arc/search"


class CookieExpired(Exception):
    pass


def _call_bili_api(mid: int, count: int, cookie: str | None,
                   timeout: float) -> dict[str, Any]:
    headers = {"User-Agent":
               "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
    if cookie:
        headers["Cookie"] = cookie
    params = {"mid": mid, "ps": count, "pn": 1, "order": "pubdate"}
    with httpx.Client(timeout=timeout, headers=headers) as client:
        r = client.get(BILI_API, params=params)
        r.raise_for_status()
        return r.json()


def fetch_for_up(*, mid: int, count: int, cookie: str | None, timeout: float,
                  retries: int, requires_cookie: bool = False) -> list[dict]:
    """拉某 up 最近 count 条投稿。失败重试；cookie 失效抛 CookieExpired。"""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = _call_bili_api(mid=mid, count=count, cookie=cookie, timeout=timeout)
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(3 ** attempt)
            continue
        if resp.get("code") == -101:
            raise CookieExpired(f"mid={mid} needs cookie; code=-101")
        if resp.get("code") != 0:
            last_err = RuntimeError(f"bili api error: {resp}")
            time.sleep(3 ** attempt)
            continue
        vlist = resp.get("data", {}).get("list", {}).get("vlist", []) or []
        if not vlist and requires_cookie and not cookie:
            raise CookieExpired(f"empty list for private self mid={mid}; cookie likely missing")
        if not vlist and requires_cookie and cookie:
            raise CookieExpired(f"empty list for private self mid={mid} with cookie; cookie likely expired")
        return [
            {"bvid": v["bvid"], "title": v["title"],
             "pubdate": v["created"], "owner_mid": mid,
             "is_self": requires_cookie}
            for v in vlist
        ]
    raise RuntimeError(f"fetch_for_up failed after {retries} retries: {last_err}")


def diff_against_state(candidates: list[dict], state_file: Path) -> list[dict]:
    """Return candidates whose BVID isn't in state with status='done'."""
    if state_file.exists():
        state = json.loads(state_file.read_text() or "{}")
    else:
        state = {}
    return [c for c in candidates if state.get(c["bvid"], {}).get("status") != "done"]


def _load_cookie(path: Path) -> str | None:
    if not path.exists():
        return None
    # 支持简单 'name=value; name=value' 或 Netscape 格式
    txt = path.read_text().strip()
    if not txt:
        return None
    if txt.startswith("#") or "\t" in txt:
        # Netscape 格式：domain \t flag \t path \t secure \t expiry \t name \t value
        pairs = []
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                pairs.append(f"{parts[5]}={parts[6]}")
        return "; ".join(pairs) if pairs else None
    return txt  # 已是 'k=v; k=v' 形态


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Discover new uploads")
    p.add_argument("--config", type=Path, required=True,
                   help="up-list.yaml 路径")
    p.add_argument("--state-file", type=Path, required=True)
    p.add_argument("--cookies", type=Path, required=True)
    args = p.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    cookie = _load_cookie(args.cookies)

    results: list[dict] = []
    errors: list[str] = []

    # self 源
    self_cfg = cfg.get("self") or {}
    if self_cfg.get("mid"):
        try:
            rows = fetch_for_up(
                mid=self_cfg["mid"],
                count=cfg["discover"]["per_up_fetch_count"],
                cookie=cookie,
                timeout=cfg["discover"]["http_timeout_seconds"],
                retries=cfg["discover"]["http_retries"],
                requires_cookie=self_cfg.get("needs_cookie", False),
            )
            for r in rows:
                r["is_self"] = True
            results.extend(rows)
        except CookieExpired as e:
            errors.append(f"SELF_COOKIE_EXPIRED: {e}")
        except Exception as e:
            errors.append(f"SELF_FETCH_FAILED: {e}")

    # 关注 up
    for up in cfg.get("ups") or []:
        try:
            rows = fetch_for_up(
                mid=up["mid"],
                count=cfg["discover"]["per_up_fetch_count"],
                cookie=cookie if up.get("needs_cookie") else None,
                timeout=cfg["discover"]["http_timeout_seconds"],
                retries=cfg["discover"]["http_retries"],
                requires_cookie=up.get("needs_cookie", False),
            )
            results.extend(rows)
        except Exception as e:
            errors.append(f"UP_{up['mid']}_FAILED: {e}")

    new_videos = diff_against_state(results, args.state_file)
    output = {"new_videos": new_videos, "errors": errors}
    json.dump(new_videos, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4.2.2：运行测试通过**

```bash
uv run pytest tests/test_discover.py -v
```

预期：所有用例 PASS。如有失败，检查 mock 路径是否匹配。

- [ ] **Step 4.2.3：提交**

```bash
git add .claude/skills/stock-review/scripts/discover.py tests/test_discover.py
git commit -m "feat(discover): 拉 up 主投稿列表并与 state 比对，输出未处理 BVID"
```

---

## 任务 5：`fetch.py`（本地匹配 + yt-dlp 下载）

**Files:**
- Create: `.claude/skills/stock-review/scripts/fetch.py`
- Create: `tests/test_fetch.py`

### 5.1 写失败测试

- [ ] **Step 5.1.1：写 `tests/test_fetch.py`**

```python
import importlib.util
import os
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/fetch.py"
spec = importlib.util.spec_from_file_location("fetch", SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def _touch_mp4(path: Path, mtime_epoch: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake")
    os.utime(path, (mtime_epoch, mtime_epoch))
    return path


class TestLocalMatch:
    def test_single_hit(self, tmp_path: Path):
        pub = 1_745_472_000
        hit = _touch_mp4(tmp_path / "100" / "2026-04-24" / "rec.mp4", pub + 1800)
        result = fetch.match_local_by_pubdate(
            base_dir=tmp_path, pubdate_epoch=pub, tolerance_hours=6)
        assert result == hit

    def test_out_of_tolerance(self, tmp_path: Path):
        pub = 1_745_472_000
        _touch_mp4(tmp_path / "a.mp4", pub + 10 * 3600)  # 10 小时后
        result = fetch.match_local_by_pubdate(
            base_dir=tmp_path, pubdate_epoch=pub, tolerance_hours=6)
        assert result is None

    def test_multiple_hits_returns_none(self, tmp_path: Path):
        pub = 1_745_472_000
        _touch_mp4(tmp_path / "a.mp4", pub + 1800)
        _touch_mp4(tmp_path / "b.mp4", pub + 3600)
        result = fetch.match_local_by_pubdate(
            base_dir=tmp_path, pubdate_epoch=pub, tolerance_hours=6)
        assert result is None

    def test_base_dir_missing(self, tmp_path: Path):
        result = fetch.match_local_by_pubdate(
            base_dir=tmp_path / "missing", pubdate_epoch=1, tolerance_hours=6)
        assert result is None


class TestResolveTarget:
    def test_local_path_returned_verbatim(self, tmp_path: Path):
        f = tmp_path / "vid.mp4"
        f.write_bytes(b"x")
        kind, val = fetch.classify_target(str(f))
        assert kind == "local"
        assert val == str(f.resolve())

    def test_bvid(self):
        assert fetch.classify_target("BV1xyz123456") == ("bvid", "BV1xyz123456")

    def test_url_with_bvid(self):
        kind, val = fetch.classify_target("https://www.bilibili.com/video/BV1abc987654/")
        assert kind == "bvid"
        assert val == "BV1abc987654"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            fetch.classify_target("not a path or bvid")
```

- [ ] **Step 5.1.2：运行测试确认失败**

```bash
uv run pytest tests/test_fetch.py -v
```

预期：`ModuleNotFoundError` 或函数未定义。

### 5.2 实现 fetch.py

- [ ] **Step 5.2.1：写 `.claude/skills/stock-review/scripts/fetch.py`**

```python
#!/usr/bin/env python3
"""Resolve input (BVID / URL / local path) to a local mp4 ready for transcription."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

BVID_RE = re.compile(r"BV[A-Za-z0-9]{10}")


def classify_target(target: str) -> tuple[str, str]:
    """Return ('local', abs_path) | ('bvid', 'BV..')"""
    p = Path(os.path.expanduser(target))
    if p.exists():
        return "local", str(p.resolve())
    m = BVID_RE.search(target)
    if m:
        return "bvid", m.group(0)
    raise ValueError(f"cannot classify target: {target!r}")


def match_local_by_pubdate(*, base_dir: Path, pubdate_epoch: float,
                            tolerance_hours: float) -> Path | None:
    """Walk base_dir for *.mp4 with mtime within ±tolerance_hours of pubdate."""
    base = Path(os.path.expanduser(str(base_dir))).resolve()
    if not base.exists():
        return None
    tolerance_s = tolerance_hours * 3600
    candidates: list[Path] = []
    for p in base.rglob("*.mp4"):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if abs(mt - pubdate_epoch) <= tolerance_s:
            candidates.append(p)
    if len(candidates) == 1:
        return candidates[0]
    return None


def download_with_ytdlp(*, bvid: str, dest_dir: Path, cookies: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.bilibili.com/video/{bvid}"
    out_tpl = str(dest_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bv*+ba/best",
        "--merge-output-format", "mp4",
        "-o", out_tpl,
    ]
    if cookies.exists():
        cmd += ["--cookies", str(cookies)]
    cmd += [url]

    last_err: str = ""
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            for ext in ("mp4", "mkv", "flv"):
                cand = dest_dir / f"{bvid}.{ext}"
                if cand.exists():
                    return cand
            raise RuntimeError(f"yt-dlp succeeded but no file matched {bvid}.* in {dest_dir}")
        last_err = r.stderr
        time.sleep(3 ** attempt)
    raise RuntimeError(f"yt-dlp failed after 3 retries: {last_err[:500]}")


def resolve(target: str, *, config_path: Path, cookies_path: Path,
            videos_dir: Path, pubdate_epoch: int | None = None,
            is_self: bool = False) -> Path:
    kind, val = classify_target(target)
    if kind == "local":
        return Path(val)

    cfg = yaml.safe_load(config_path.read_text())
    self_cfg = cfg.get("self") or {}

    if kind == "bvid" and is_self and self_cfg.get("prefer_local"):
        base = Path(os.path.expanduser(cfg["biliup"]["base_dir"]))
        tol = float(cfg["biliup"].get("mtime_tolerance_hours", 6))
        if pubdate_epoch is not None:
            hit = match_local_by_pubdate(
                base_dir=base, pubdate_epoch=pubdate_epoch, tolerance_hours=tol)
            if hit:
                return hit
        # fallthrough to yt-dlp

    return download_with_ytdlp(bvid=val, dest_dir=videos_dir, cookies=cookies_path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target", help="BVID / 视频页 URL / 本地路径")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--cookies", type=Path, required=True)
    p.add_argument("--videos-dir", type=Path, required=True)
    p.add_argument("--pubdate", type=int, default=None,
                   help="若目标是自己账号录播的 BVID，传入 pubdate 秒以启用本地匹配")
    p.add_argument("--is-self", action="store_true")
    args = p.parse_args(argv)

    path = resolve(
        args.target, config_path=args.config, cookies_path=args.cookies,
        videos_dir=args.videos_dir, pubdate_epoch=args.pubdate,
        is_self=args.is_self,
    )
    json.dump({"path": str(path)}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5.2.2：运行测试通过**

```bash
uv run pytest tests/test_fetch.py -v
```

预期：所有用例 PASS。

- [ ] **Step 5.2.3：验证 yt-dlp 可用**

```bash
which yt-dlp || echo "need to install yt-dlp"
yt-dlp --version 2>/dev/null || pip install --user yt-dlp
```

（若已装过 biliup.rs，yt-dlp 通常也已有。）

- [ ] **Step 5.2.4：提交**

```bash
git add .claude/skills/stock-review/scripts/fetch.py tests/test_fetch.py
git commit -m "feat(fetch): 统一 BVID/URL/本地路径解析，支持 biliup 本地匹配与 yt-dlp 下载"
```

---

## 任务 6：`transcribe.py`（三级字幕提取）

先搭骨架（L1 嵌入字幕 + L3 FunASR 基线），L2 RapidOCR 作为后续增强（独立于主路径，可按需启用）。

**Files:**
- Create: `.claude/skills/stock-review/scripts/transcribe.py`
- Create: `tests/test_transcribe.py`

### 6.1 写失败测试

- [ ] **Step 6.1.1：写 `tests/test_transcribe.py`**

```python
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/transcribe.py"
spec = importlib.util.spec_from_file_location("transcribe", SCRIPT)
transcribe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcribe)


class TestRouting:
    def test_too_short_returns_skip(self, tmp_path: Path):
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 30, "has_audio": True,
                                         "embedded_subs": []}):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=False)
        assert result == {"skipped": "too_short"}

    def test_no_audio_returns_skip(self, tmp_path: Path):
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": False,
                                         "embedded_subs": []}):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=False)
        assert result == {"skipped": "no_audio"}

    def test_embedded_subs_use_L1(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": ["chi_sim"]}), \
             patch.object(transcribe, "extract_embedded",
                          return_value=tmp_path / "out" / "v.srt") as m1, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=False)
        assert result["method"] == "L1"
        assert m1.called

    def test_fallthrough_to_L3(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "run_asr",
                          return_value=tmp_path / "out" / "v.srt") as m3, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=False)
        assert result["method"] == "L3"
        assert m3.called

    def test_ocr_enabled_tries_L2_first(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "try_ocr",
                          return_value=tmp_path / "out" / "v.srt") as m2, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=True)
        assert result["method"] == "L2"
        assert m2.called

    def test_ocr_miss_falls_to_L3(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "try_ocr", return_value=None), \
             patch.object(transcribe, "run_asr",
                          return_value=tmp_path / "out" / "v.srt"), \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                      out_dir=tmp_path / "out",
                                      hotwords_path=None,
                                      enable_ocr=True)
        assert result["method"] == "L3"
```

- [ ] **Step 6.1.2：运行测试确认失败**

```bash
uv run pytest tests/test_transcribe.py -v
```

### 6.2 实现 transcribe.py

- [ ] **Step 6.2.1：写 `.claude/skills/stock-review/scripts/transcribe.py`**

```python
#!/usr/bin/env python3
"""Three-tier subtitle extraction: L1 embedded -> L2 OCR -> L3 ASR."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def probe_video(video_path: Path) -> dict:
    """Return {duration, has_audio, embedded_subs: [lang, ...]}."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_streams", "-show_format", str(video_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr}")
    data = json.loads(r.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    embedded_subs = [
        s.get("tags", {}).get("language", "und")
        for s in streams if s.get("codec_type") == "subtitle"
    ]
    return {"duration": duration, "has_audio": has_audio,
            "embedded_subs": embedded_subs}


def extract_embedded(video_path: Path, out_srt: Path, sub_index: int = 0) -> Path:
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video_path),
           "-map", f"0:s:{sub_index}", str(out_srt)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg subtitle extract failed: {r.stderr[:500]}")
    return out_srt


def try_ocr(video_path: Path, out_srt: Path) -> Path | None:
    """Stub: 占位 OCR 实现；未启用时直接返回 None。
    后续集成 RapidOCR 时替换此函数。"""
    return None


def run_asr(video_path: Path, out_srt: Path, hotwords_path: Path | None) -> Path:
    """Invoke FunASR paraformer-zh via CLI wrapper.

    Prerequisite: `pip install funasr modelscope` and model weights cached.
    """
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    wav_path = out_srt.with_suffix(".wav")
    # 抽 16k mono wav
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-ar", "16000", "-ac", "1", "-vn", str(wav_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {r.stderr[:500]}")

    hotwords: list[str] = []
    if hotwords_path and hotwords_path.exists():
        hotwords = [line.strip() for line in hotwords_path.read_text().splitlines()
                    if line.strip() and not line.startswith("#")]

    # 使用 funasr python API
    try:
        from funasr import AutoModel
    except ImportError as e:
        raise RuntimeError("FunASR not installed; pip install funasr modelscope") from e

    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                      punc_model="ct-punc")
    res = model.generate(input=str(wav_path),
                         hotword=" ".join(hotwords) if hotwords else None)
    # res: list[{"key": ..., "text": ..., "sentence_info": [{"start","end","text"}, ...]}]
    _write_srt(res, out_srt)
    wav_path.unlink(missing_ok=True)
    return out_srt


def _write_srt(asr_result: list[dict], out_srt: Path) -> None:
    def fmt_ts(ms: float) -> str:
        ms = int(ms)
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    idx = 1
    for item in asr_result:
        for seg in item.get("sentence_info") or []:
            start = seg.get("start", 0)
            end = seg.get("end", start + 1000)
            text = seg.get("text", "").strip()
            if not text:
                continue
            lines.append(f"{idx}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n")
            idx += 1
    out_srt.write_text("\n".join(lines), encoding="utf-8")


def srt_to_txt(srt_path: Path) -> Path:
    import pysrt
    txt_path = srt_path.with_suffix(".txt")
    subs = pysrt.open(str(srt_path), encoding="utf-8")
    text = "\n".join(s.text.strip() for s in subs if s.text.strip())
    txt_path.write_text(text, encoding="utf-8")
    return txt_path


def run(*, video_path: Path, out_dir: Path, hotwords_path: Path | None,
        enable_ocr: bool = False) -> dict:
    info = probe_video(video_path)
    if info["duration"] < 60:
        return {"skipped": "too_short"}
    if not info["has_audio"] and not info["embedded_subs"]:
        return {"skipped": "no_audio"}

    out_dir.mkdir(parents=True, exist_ok=True)
    # 用文件 sha1 前 12 位作 stem，避免同名冲突
    stem = hashlib.sha1(str(video_path).encode()).hexdigest()[:12]
    srt_out = out_dir / f"{stem}.srt"

    method: str
    if info["embedded_subs"]:
        srt = extract_embedded(video_path, srt_out)
        method = "L1"
    elif enable_ocr:
        srt = try_ocr(video_path, srt_out)
        if srt:
            method = "L2"
        else:
            srt = run_asr(video_path, srt_out, hotwords_path)
            method = "L3"
    else:
        srt = run_asr(video_path, srt_out, hotwords_path)
        method = "L3"

    txt = srt_to_txt(srt)
    return {"method": method, "srt_path": str(srt), "txt_path": str(txt),
            "duration_sec": info["duration"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--hotwords", type=Path, default=None)
    p.add_argument("--enable-ocr", action="store_true")
    args = p.parse_args(argv)

    result = run(video_path=args.video, out_dir=args.out_dir,
                 hotwords_path=args.hotwords, enable_ocr=args.enable_ocr)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6.2.2：运行测试通过**

```bash
uv run pytest tests/test_transcribe.py -v
```

- [ ] **Step 6.2.3：手工装 FunASR 与 ffmpeg**

```bash
brew install ffmpeg
uv pip install funasr modelscope   # 或者用独立 venv
ffmpeg -version
```

（FunASR 首次运行会从 modelscope 拉模型，约 200MB，保持网络畅通。）

- [ ] **Step 6.2.4：提交**

```bash
git add .claude/skills/stock-review/scripts/transcribe.py tests/test_transcribe.py
git commit -m "feat(transcribe): 实现三级字幕提取骨架（L1 嵌入 / L2 OCR 占位 / L3 FunASR）"
```

---

## 任务 7：`SKILL.md`（Claude 编排入口）

**Files:**
- Create: `.claude/skills/stock-review/SKILL.md`

- [ ] **Step 7.1：写 `SKILL.md`**

```markdown
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
```

- [ ] **Step 7.2：提交**

```bash
git add .claude/skills/stock-review/SKILL.md
git commit -m "feat(skill): 写 stock-review skill 编排说明"
```

---

## 任务 8：端到端烟雾测试（手动）

**Files:**
- Create: `tests/smoke/README.md`
- Create: `tests/smoke/fixtures.yaml`

- [ ] **Step 8.1：准备 fixture 清单**

写 `tests/smoke/fixtures.yaml`：

```yaml
# 手动维护的端到端烟雾测试 fixture
# 每次 skill/脚本有重大修改后手动跑一遍

fixtures:
  - id: L1_embedded
    desc: "有官方嵌入字幕的 B 站视频（某讲解视频）"
    target: "BV1xxxxxxxxxx"   # 首次运行前手动填入已知带字幕的视频 BVID
    expected_method: L1

  - id: L2_burned
    desc: "带硬烧字幕的视频（某 up 主的自制字幕）"
    target: "BV2xxxxxxxxxx"
    expected_method: L2  # 需启用 --enable-ocr；L2 未实装前此条可 skip

  - id: L3_asr
    desc: "纯音频直播录播 mp4"
    target: "/path/to/local/recording.mp4"  # 本地一条老录播文件
    expected_method: L3
```

- [ ] **Step 8.2：写 `tests/smoke/README.md`**

```markdown
# Smoke tests

手动端到端验证 skill 全链路。

## 跑法

1. 填 `fixtures.yaml` 的 `target` 字段
2. 对每条 fixture 执行：
   ```bash
   just analyze <target>
   ```
3. 检查：
   - [ ] `data/state.json` 出现对应条目且状态为 `done`
   - [ ] `data/reports/` 下有对应 md
   - [ ] 飞书群收到消息
   - [ ] 产出 `method` 字段与 `expected_method` 一致

## 触发条件

- 脚本有重大修改（discover/fetch/transcribe 的主逻辑变动）
- SKILL.md 编排流程变动
- 升级 FunASR / yt-dlp 等外部工具
```

- [ ] **Step 8.3：真实跑一条 L3 fixture**

实际准备一条本地 mp4（用 biliup 的历史录播或任意自录），填入 fixture；跑：

```bash
just analyze /path/to/recording.mp4
```

验收：
- 终端无异常退出
- `data/subtitles/` 下有新 srt
- `data/reports/` 下有 md
- 飞书群收到消息
- 报告按 `analysis-rubric.md` 打分 ≥ 7/8

如质量不佳，把具体 gap（如"某术语被识别成 XX"）加到 `references/funasr-hotwords.txt`，重跑验证改善。

- [ ] **Step 8.4：提交 smoke 测试资产**

```bash
git add tests/smoke/README.md tests/smoke/fixtures.yaml
git commit -m "test: 增加端到端烟雾测试 fixture 清单与 runner 说明"
```

---

## 任务 9：launchd 定时 `scan`

**Files:**
- Create: `launchd/com.zvector.stock-review.scan.plist`

- [ ] **Step 9.1：写 `launchd/com.zvector.stock-review.scan.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.zvector.stock-review.scan</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd /Users/zvector/ws/workflow/stock-review && /usr/local/bin/claude -p "/stock-review scan" &gt;&gt; data/scan.log 2&gt;&amp;1</string>
  </array>

  <key>StartCalendarInterval</key>
  <array>
    <dict>
      <key>Hour</key><integer>21</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
    <dict>
      <key>Hour</key><integer>23</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
  </array>

  <key>StandardOutPath</key>
  <string>/Users/zvector/ws/workflow/stock-review/data/launchd.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/zvector/ws/workflow/stock-review/data/launchd.stderr.log</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
```

说明：`claude` CLI 的绝对路径不同机器位置不同。首先在终端执行 `which claude` 确认，替换 `/usr/local/bin/claude`。

- [ ] **Step 9.2：安装 & 加载**

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.zvector.stock-review.scan.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.zvector.stock-review.scan.plist
launchctl list | grep stock-review
```

预期：看到一行 `- 0 com.zvector.stock-review.scan`。

- [ ] **Step 9.3：立即触发验证**

```bash
launchctl kickstart -k gui/$(id -u)/com.zvector.stock-review.scan
sleep 5
tail -n 50 data/launchd.stdout.log data/launchd.stderr.log
```

预期：日志里能看到 `/stock-review scan` 的输出（首次可能只是"无新视频"），无 `Permission denied` 或 `claude: command not found`。若报 claude 找不到，回 Step 9.1 修 PATH。

- [ ] **Step 9.4：提交**

```bash
git add launchd/com.zvector.stock-review.scan.plist
git commit -m "feat(launchd): 增加定时 scan 任务（每日 21:00 / 23:00）"
```

---

## 任务 10：`data/videos/` 清理任务

**Files:**
- Create: `launchd/cleanup.sh`
- Create: `launchd/com.zvector.stock-review.cleanup.plist`

- [ ] **Step 10.1：写 `launchd/cleanup.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/zvector/ws/workflow/stock-review"
VIDEOS_DIR="$ROOT/data/videos"
LOG="$ROOT/data/cleanup.log"

if [ ! -d "$VIDEOS_DIR" ]; then
  echo "[$(date)] videos dir not found, skip" >> "$LOG"
  exit 0
fi

BEFORE_BYTES=$(du -sk "$VIDEOS_DIR" | awk '{print $1}')
find "$VIDEOS_DIR" -type f -name "*.mp4" -mtime +60 -print -delete >> "$LOG" 2>&1
AFTER_BYTES=$(du -sk "$VIDEOS_DIR" | awk '{print $1}')
echo "[$(date)] cleanup done: ${BEFORE_BYTES}KB -> ${AFTER_BYTES}KB" >> "$LOG"
```

- [ ] **Step 10.2：赋可执行权限**

```bash
chmod +x launchd/cleanup.sh
```

- [ ] **Step 10.3：写 `launchd/com.zvector.stock-review.cleanup.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.zvector.stock-review.cleanup</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/zvector/ws/workflow/stock-review/launchd/cleanup.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>4</integer>
    <key>Minute</key><integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/zvector/ws/workflow/stock-review/data/cleanup.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/zvector/ws/workflow/stock-review/data/cleanup.stderr.log</string>
</dict>
</plist>
```

每日凌晨 4 点跑。

- [ ] **Step 10.4：安装 & 加载**

```bash
cp launchd/com.zvector.stock-review.cleanup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.zvector.stock-review.cleanup.plist
launchctl list | grep cleanup
```

- [ ] **Step 10.5：立即 dry-run**

```bash
bash launchd/cleanup.sh
cat data/cleanup.log
```

预期：日志出现一行 `cleanup done: XKB -> XKB`。首次 data/videos/ 为空是正常的。

- [ ] **Step 10.6：提交**

```bash
git add launchd/cleanup.sh launchd/com.zvector.stock-review.cleanup.plist
git commit -m "feat(launchd): 增加每日清理 videos 目录（60 天 TTL）"
```

---

## 任务 11：配置落实 & 首次真跑

这一组任务不写测试、不改代码，只做配置并完整跑一次。

- [ ] **Step 11.1：填写 `up-list.yaml`**

在 `.claude/skills/stock-review/references/up-list.yaml`：
- `self.mid`：你本人的 B 站 UID
- `ups[*].mid` 与 `name`：关注的 up 主 UID 与名字
- `notify.lark_chat_id`：股市复盘群 `chat_id`（`oc_` 开头）
  - 未建群：先建群，拉机器人进群，用 `lark-im` skill 拿 chat_id
- 确认 `biliup.base_dir` 是 `/Users/zvector/Movies/bilive-recoder/backup`（默认值已对，跳过）

提交：

```bash
git add .claude/skills/stock-review/references/up-list.yaml
git commit -m "chore: 填写 up-list.yaml 真实配置"
```

- [ ] **Step 11.2：放入 B 站 cookies**

从浏览器导出 Netscape 格式 cookies.txt 存到 `.claude/skills/stock-review/config/cookies.txt`（已被 gitignore）。验证：

```bash
head -n 3 .claude/skills/stock-review/config/cookies.txt
```

预期：看到 `# Netscape HTTP Cookie File` 或已包含 `bilibili.com` 行。

- [ ] **Step 11.3：手动单条跑通**

挑一条你自己的录播 BVID：

```bash
just analyze BV1xxxxxxxxxx
```

Claude 读取 SKILL.md 应该会依次调用脚本并最终发飞书。观察到飞书群收到报告 → 成功。

- [ ] **Step 11.4：scan 跑通**

```bash
just scan
```

预期：无新视频（因为刚刚的已处理过），汇总消息"成功 0 / 失败 0 / 跳过 0"或类似。再等次日有新视频时自动 scan（launchd 定时），飞书收到。

- [ ] **Step 11.5：初次质量抽检**

按 `references/analysis-rubric.md` 对前 3 条报告打分。问题 → 改 `review-prompt.md` 或 `funasr-hotwords.txt`，重跑对比。

---

## Self-Review

### 1. Spec coverage

| Spec 条目 | 对应任务 |
|---|---|
| §2 架构 + §3 组件 | 任务 2/3/4/5/6/7 |
| §3.3 fetch 的 pubdate±mtime 匹配 | Task 5.1 TestLocalMatch |
| §3.4 transcribe 三级策略 | Task 6（L1+L3 实装，L2 占位；在 fixture 中可启用 `--enable-ocr`） |
| §4 状态机 + scan 时序 | Task 2（state.py）+ Task 7（SKILL.md 编排）|
| §4.3 本地 mp4 不写 state | Task 7 SKILL.md 单条模式说明 |
| §6 错误处理 | Task 4 (discover 重试/cookie 检测)、Task 5 (yt-dlp 重试)、Task 7 (skill 层汇总)|
| §6.2 scan 汇总消息 | Task 7 SKILL.md "扫描汇总"段 |
| §6.3 清理策略 | Task 10 |
| §7 测试策略 | Task 2/4/5/6 单测 + Task 8 烟雾 |
| §8 路线图 | Task 1-11 总体对应 |
| §9 复盘提示词 | Task 3.2 |
| launchd 定时 scan | Task 9 |
| 质量 rubric | Task 3.4 + Task 11.5 |

覆盖完整。L2 RapidOCR 是 "骨架 + 占位"，spec 明确说明是递进策略，L1/L3 能满足 MVP，L2 可后续加，没有未覆盖的 spec 条目。

### 2. Placeholder scan

- ✓ 无 "TBD"、"TODO"、"implement later"、"similar to Task N"
- ✓ 每个代码步骤都有完整代码
- ✓ `up-list.yaml` 的 `mid: 0` 和 `lark_chat_id: ""` 是**刻意的配置占位**（Task 11 显式填入），不是"计划占位"
- ✓ `try_ocr` 返回 None 是明确的 stub，有 docstring 说明

### 3. Type consistency

- state.py 的 schema：`{status, processed_at, report_path, source, method, error, retry_count}` — 在测试、实现、SKILL.md 编排中引用方式一致
- `status` 合法值：`discovered/fetched/transcribed/analyzed/notified/done/*_err/skipped_*` — state.py `VALID_STATUSES` 常量与 SKILL.md 引用一致
- discover.py 返回结构：`{bvid, title, pubdate, owner_mid, is_self}` — 测试与实现一致
- fetch.py 的 `classify_target` 返回 `(kind, val)` — 测试与实现一致
- transcribe.py 的 `run` 返回 `{method, srt_path, txt_path, duration_sec}` 或 `{skipped: ...}` — 测试与实现一致

无不一致。

