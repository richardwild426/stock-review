# Skill 仓库重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `stock-review` 从「项目内嵌 .claude/skills/」改造成「仓库即 Skill」，clone 到 `~/.claude/skills/stock-review/` 即可直接使用。

**Architecture:** 用 `git mv` 把 `.claude/skills/stock-review/` 下的 12 个被追踪文件原样提到仓库根；同步更新 `pyproject.toml`、`README.md`、`.gitignore`、`.claude/settings.local.json` 中的路径引用；删除 `tests/`、`Justfile`、`launchd/`、空 `.claude/skills/`；最后把 `docs/superpowers/` 决策合并入 README 末尾、删除 `docs/`。所有修改通过 4 个独立 commit 交付，文件历史通过 git mv 保留，整体可 `git revert` 回滚。

**Tech Stack:** Git (mv / rm) · sed/Edit · Python 3.11+ (uv) · 无新增依赖

---

## Pre-flight

- [ ] **Step 0.1：确认起点干净**

Run: `git status && git log --oneline -3`

Expected:
```
On branch main
nothing to commit, working tree clean
fdd0ebe docs: 写入 skill 仓库重构 spec
b264ada feat: 多输入源支持 + 安装指引 + 去敏感
2593830 fix: 修复 discover WBI 签名和 transcribe FunASR 调用
```

如果有未提交变更，先 stash 或 commit 后再开始。

- [ ] **Step 0.2：（可选）建分支**

按用户全局规约 "功能开发在 feature/<task-name> 分支"，建议：

```bash
git checkout -b refactor/skill-as-repo
```

若用户明确允许在 main 上直接做（前置对话中已默认在 main），则跳过此步。下面所有 commit 默认推到当前分支。

- [ ] **Step 0.3：列出当前 .claude/skills/ 被追踪文件，作为基准**

Run: `git ls-files .claude/skills/`

Expected（恰好 12 行）:
```
.claude/skills/stock-review/SKILL.md
.claude/skills/stock-review/config/.gitkeep
.claude/skills/stock-review/config/cookies.txt.example
.claude/skills/stock-review/references/analysis-rubric.md
.claude/skills/stock-review/references/funasr-hotwords.txt
.claude/skills/stock-review/references/review-prompt.md
.claude/skills/stock-review/references/up-list.yaml
.claude/skills/stock-review/scripts/__init__.py
.claude/skills/stock-review/scripts/discover.py
.claude/skills/stock-review/scripts/fetch.py
.claude/skills/stock-review/scripts/state.py
.claude/skills/stock-review/scripts/transcribe.py
```

如果数目不一致，停下排查（可能有未追踪/已 stage 的额外文件）。

---

## File Structure（重构后）

迁移后仓库根从 git 视角包含：

| 路径 | 责任 |
|---|---|
| `SKILL.md` | Claude Code Skill 入口（frontmatter + 编排说明） |
| `README.md` | 使用文档 + 设计决策（合并自 docs/） |
| `pyproject.toml` | 依赖声明（去掉 pytest/pythonpath 配置） |
| `uv.lock` | 锁定版本（不动） |
| `.python-version` | Python 版本（不动） |
| `.gitignore` | 忽略规则（cookies 路径前缀更新） |
| `scripts/__init__.py` `scripts/discover.py` `scripts/fetch.py` `scripts/state.py` `scripts/transcribe.py` | CLI 脚本（仅迁移位置，逻辑不动） |
| `references/up-list.yaml` `references/review-prompt.md` `references/analysis-rubric.md` `references/funasr-hotwords.txt` | Skill 知识库（仅迁移） |
| `config/.gitkeep` `config/cookies.txt.example` | 凭证目录占位（仅迁移） |
| `.claude/settings.local.json` | Claude Code 项目级权限（保留，更新内部路径） |

工作树额外存在但不入 git：`.git/`、`.venv/`、`data/`（含子目录）、`__pycache__/`。

---

## Task 1: git mv 主迁移（spec commit 2）

**Files:**
- Modify (move): `.claude/skills/stock-review/SKILL.md` → `SKILL.md`
- Modify (move): `.claude/skills/stock-review/scripts/*` → `scripts/*`
- Modify (move): `.claude/skills/stock-review/references/*` → `references/*`
- Modify (move): `.claude/skills/stock-review/config/*` → `config/*`

- [ ] **Step 1.1：确认目标位置是否冲突**

Run:
```bash
ls SKILL.md scripts references config 2>&1 | head
```

Expected: 全部 `No such file or directory`。如果任何目标已存在，停下检查（说明有遗漏）。

- [ ] **Step 1.2：git mv SKILL.md**

Run:
```bash
git mv .claude/skills/stock-review/SKILL.md SKILL.md
```

- [ ] **Step 1.3：git mv scripts/ 目录下所有文件**

Run:
```bash
mkdir -p scripts
git mv .claude/skills/stock-review/scripts/__init__.py scripts/__init__.py
git mv .claude/skills/stock-review/scripts/discover.py scripts/discover.py
git mv .claude/skills/stock-review/scripts/fetch.py scripts/fetch.py
git mv .claude/skills/stock-review/scripts/state.py scripts/state.py
git mv .claude/skills/stock-review/scripts/transcribe.py scripts/transcribe.py
```

- [ ] **Step 1.4：git mv references/ 目录下所有文件**

Run:
```bash
mkdir -p references
git mv .claude/skills/stock-review/references/up-list.yaml references/up-list.yaml
git mv .claude/skills/stock-review/references/review-prompt.md references/review-prompt.md
git mv .claude/skills/stock-review/references/analysis-rubric.md references/analysis-rubric.md
git mv .claude/skills/stock-review/references/funasr-hotwords.txt references/funasr-hotwords.txt
```

- [ ] **Step 1.5：git mv config/ 目录下所有文件**

Run:
```bash
mkdir -p config
git mv .claude/skills/stock-review/config/.gitkeep config/.gitkeep
git mv .claude/skills/stock-review/config/cookies.txt.example config/cookies.txt.example
```

- [ ] **Step 1.6：清理 .claude/skills/ 残壳与未追踪副产物（如 .DS_Store）**

Run:
```bash
# 列出该目录下还残留什么（应该只剩未追踪文件，比如 .DS_Store）
ls -laR .claude/skills 2>/dev/null | head -30

# 物理删除整个 .claude/skills/ 子树（递归，包括 .DS_Store 等）
rm -rf .claude/skills
```

注意：`rm -rf` 仅删除工作树中的物理目录与未追踪文件；已追踪文件已经被前面 `git mv` 处理过。如果此时 `git status` 显示 `.claude/skills/` 下仍有"deleted"项，说明前面有遗漏，停下排查。

- [ ] **Step 1.7：验证迁移结果**

Run:
```bash
git status
```

Expected（重命名应该被识别为 rename，不是 delete+add）:
```
Changes to be committed:
	renamed:    .claude/skills/stock-review/SKILL.md -> SKILL.md
	renamed:    .claude/skills/stock-review/config/.gitkeep -> config/.gitkeep
	renamed:    .claude/skills/stock-review/config/cookies.txt.example -> config/cookies.txt.example
	renamed:    .claude/skills/stock-review/references/analysis-rubric.md -> references/analysis-rubric.md
	renamed:    .claude/skills/stock-review/references/funasr-hotwords.txt -> references/funasr-hotwords.txt
	renamed:    .claude/skills/stock-review/references/review-prompt.md -> references/review-prompt.md
	renamed:    .claude/skills/stock-review/references/up-list.yaml -> references/up-list.yaml
	renamed:    .claude/skills/stock-review/scripts/__init__.py -> scripts/__init__.py
	renamed:    .claude/skills/stock-review/scripts/discover.py -> scripts/discover.py
	renamed:    .claude/skills/stock-review/scripts/fetch.py -> scripts/fetch.py
	renamed:    .claude/skills/stock-review/scripts/state.py -> scripts/state.py
	renamed:    .claude/skills/stock-review/scripts/transcribe.py -> scripts/transcribe.py
```

如果显示的是 `deleted:` + `new file:`（而非 `renamed:`），说明 git 没识别为重命名 —— 历史会断开。这种情况下检查文件内容是否一致，如有问题用 `git mv -f` 重做。

- [ ] **Step 1.8：验证新结构下脚本可执行（无 import 错误）**

Run:
```bash
uv run python -c "import importlib.util, sys
for name in ['discover', 'fetch', 'state', 'transcribe']:
    spec = importlib.util.spec_from_file_location(name, f'scripts/{name}.py')
    importlib.util.module_from_spec(spec)
    print(f'{name}.py loadable')
"
```

Expected: 4 行 `xxx.py loadable`，无异常（仅做 spec 加载，不执行 main 逻辑，因此不需要 ffmpeg/funasr 在场）。

如失败：检查是否有脚本顶层就 import 了 funasr 等重依赖；如有，改为延迟 import，或用替代验证方式（`python -c "open('scripts/discover.py').read()"`）。

- [ ] **Step 1.9：commit**

Run:
```bash
git commit -m "$(cat <<'EOF'
refactor: 把 SKILL 主体从 .claude/skills/ 提到仓库根

仓库即 Skill：SKILL.md、scripts/、references/、config/
均通过 git mv 提到根目录，文件历史保留。
EOF
)"
```

Expected: `[main <hash>] refactor: 把 SKILL 主体从 .claude/skills/ 提到仓库根` + ` 12 files changed, 0 insertions(+), 0 deletions(-)`（纯 rename）。

---

## Task 2: 更新内部路径引用（spec commit 3）

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `.claude/settings.local.json`

- [ ] **Step 2.1：修改 `pyproject.toml`，去掉 pytest 配置和 dev 依赖中的 pytest**

用 Edit 工具进行三处替换：

替换 1（删除 `[tool.pytest.ini_options]` 整块）：

old_string:
```
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".claude/skills/stock-review"]
addopts = "-v --tb=short"

[tool.ruff]
```

new_string:
```
[tool.ruff]
```

替换 2（dev 依赖去 pytest）：

old_string:
```
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "ruff>=0.5",
]
```

new_string:
```
[dependency-groups]
dev = [
    "ruff>=0.5",
]
```

- [ ] **Step 2.2：验证 pyproject.toml 仍可解析**

Run:
```bash
uv lock --check 2>&1 | head -5
```

Expected: 无报错（或只是提示 lock 与 pyproject 不完全一致 —— 删除依赖后 uv.lock 可保持，pip 解析时只是多余条目）。

如果报错，运行：
```bash
uv lock
```
重新生成 `uv.lock`。这一步即使更新了 lock，也保留进同一个 commit。

- [ ] **Step 2.3：修改 `.gitignore`，更新 cookies 路径前缀**

用 Edit 工具：

old_string:
```
.claude/skills/stock-review/config/cookies.txt
**/cookies.txt
```

new_string:
```
config/cookies.txt
**/cookies.txt
```

`**/cookies.txt` 通配仍然保留，作为防御性兜底。

- [ ] **Step 2.4：修改 `README.md` —— 重写"作为 Claude Code Skill 安装"章节**

用 Edit 工具：

old_string:
```
### 2. 作为 Claude Code Skill 安装

将本项目克隆到你的 Claude Code skills 目录：

```bash
# 方式A：全局 skills 目录
mkdir -p ~/.claude/skills
cd ~/.claude/skills
git clone https://github.com/your-repo/stock-review.git

# 方式B：项目级 skills 目录
cp -r stock-review /path/to/your-project/.claude/skills/
```

### 3. 配置

编辑 `.claude/skills/stock-review/references/up-list.yaml`：
```

new_string:
```
### 2. 作为 Claude Code Skill 安装

本仓库即 Skill，clone 到 Claude Code skills 目录：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/your-repo/stock-review.git ~/.claude/skills/stock-review
```

### 3. 配置

编辑 `references/up-list.yaml`：
```

- [ ] **Step 2.5：修改 `README.md` —— 重写命令行直接调用章节，去 `.claude/skills/stock-review/` 前缀**

用 Edit 工具：

old_string:
```
### 命令行直接调用

```bash
# 扫描本地录播
python3 .claude/skills/stock-review/scripts/discover.py \
  --config .claude/skills/stock-review/references/up-list.yaml \
  --state-file data/state.json \
  --cookies .claude/skills/stock-review/config/cookies.txt \
  --skip-api

# 转录单个视频
python3 .claude/skills/stock-review/scripts/transcribe.py video.mp4 \
  --out-dir data/subtitles
```
```

new_string:
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
```

- [ ] **Step 2.6：修改 `README.md` —— 删除 Just 命令章节**

用 Edit 工具：

old_string:
```
### Just 命令

```bash
# 自动扫描（launchd 每晚调用）
just scan

# 手动分析单条
just analyze BVxxx
just analyze https://bilibili.com/video/BVxxx
just analyze /path/to/video.mp4
```

### 命令行直接调用
```

new_string:
```
### 命令行直接调用
```

- [ ] **Step 2.7：修改 `README.md` —— 更新前置检查中的配置路径**

用 Edit 工具：

old_string:
```
grep -E "(base_dir|lark_chat_id)" .claude/skills/stock-review/references/up-list.yaml
```

new_string:
```
grep -E "(base_dir|lark_chat_id)" references/up-list.yaml
```

- [ ] **Step 2.8：修改 `README.md` —— 更新"目录结构"展示**

用 Edit 工具：

old_string:
```
## 目录结构

```
stock-review/
├── SKILL.md                 # Skill 定义（Claude Code 读取）
├── references/
│   ├── up-list.yaml         # 配置文件
│   ├── review-prompt.md     # 分析模板
│   └── funasr-hotwords.txt  # ASR 热词
├── scripts/
│   ├── discover.py          # 视频发现
│   ├── transcribe.py        # 语音转录
│   ├── fetch.py             # 视频下载
│   └── state.py             # 状态管理
├── config/
│   └── cookies.txt          # B站 cookies（gitignore）
└── data/                    # 数据目录（gitignore）
    ├── videos/
    ├── subtitles/
    ├── reports/
    └── state.json
```
```

new_string:
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
```

- [ ] **Step 2.9：修改 `.claude/settings.local.json`，清掉旧路径权限规则**

用 Edit 工具，把整个文件替换：

old_string:
```
{
  "permissions": {
    "allow": [
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/.claude/skills/stock-review/scripts)",
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/.claude/skills/stock-review/references)",
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/.claude/skills/stock-review/config)",
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/tests)",
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/data/videos)",
      "Bash(rm .claude/skills/stock-review/references/.gitkeep)",
      "Bash(git add *)",
      "Bash(git commit -m ' *)"
    ]
  }
}
```

new_string:
```
{
  "permissions": {
    "allow": [
      "Bash(mkdir -p /Users/zvector/ws/workflow/stock-review/data/videos)",
      "Bash(git add *)",
      "Bash(git commit -m ' *)"
    ]
  }
}
```

注意：此文件可能被 Claude Code 自身改动；执行 Edit 前用 Read 读最新内容；如果实际 old_string 与上面不同，按"删除所有指向 `.claude/skills/...` 的规则、保留其他规则"的原则手动调整，不必死板对齐。

- [ ] **Step 2.10：扫描确认无残留 `.claude/skills/stock-review` 字符串**

Run:
```bash
git grep -n "\.claude/skills/stock-review" -- ':(exclude)docs/' ':(exclude)tests/'
```

Expected: 无输出（exit 1）。

如果有命中：定位文件，按上面同样的模式修补。`docs/` 排除是因为整个 docs/ 会在 Task 4 删除；`tests/` 排除是因为整个 tests/ 会在 Task 3 删除。

- [ ] **Step 2.11：commit**

Run:
```bash
git add pyproject.toml .gitignore README.md .claude/settings.local.json
# 如果 Step 2.2 重新生成了 uv.lock，也加进来
git add uv.lock 2>/dev/null || true
git commit -m "$(cat <<'EOF'
chore: 更新内部路径引用至仓库根

去掉 pyproject.toml 的 pytest 配置和 pythonpath 钩子，
README 中安装/命令路径全部去掉 .claude/skills/stock-review 前缀，
.gitignore 与 .claude/settings.local.json 中相应路径同步更新。
EOF
)"
```

Expected: 提交成功，diff 涉及 4-5 个文件。

---

## Task 3: 删除 tests / Justfile / launchd / .claude/skills/ 残壳（spec commit 4）

**Files:**
- Delete: `tests/`（整目录）
- Delete: `Justfile`
- Delete: `launchd/`（空目录）
- Delete: `.claude/skills/`（已是空壳，但 git 视角下仍可能残留）

- [ ] **Step 3.1：删除 tests/ 整目录**

Run:
```bash
git rm -r tests
```

Expected: 输出 5-6 行 `rm 'tests/...'`（`__init__.py`、`conftest.py`、4 个 `test_*.py`）。

- [ ] **Step 3.2：删除 Justfile**

Run:
```bash
git rm Justfile
```

Expected: `rm 'Justfile'`

- [ ] **Step 3.3：删除 launchd/（如果在 git 中）**

Run:
```bash
# launchd 可能未被追踪（空目录 git 不追），先用 ls 看物理是否存在
ls -la launchd 2>&1 | head -3

# 如果存在，物理删除
rm -rf launchd
```

git 不追踪空目录，所以这一步通常不会进入 commit；ls 应给出 `total 0` 或 `No such file or directory`。

- [ ] **Step 3.4：清理 .claude/skills/ 残壳**

Run:
```bash
# git 视角下 .claude/skills/ 已没有被追踪文件（Task 1 全部 mv 走了），但物理目录可能还在
ls .claude 2>&1
rm -rf .claude/skills
```

Expected: `.claude/` 下只剩 `settings.local.json`。

- [ ] **Step 3.5：验证清理结果**

Run:
```bash
ls -A .claude
git status
```

Expected:
- `ls .claude` 输出仅 `settings.local.json`
- `git status` 显示 `tests/` 与 `Justfile` 的 deletion 已 staged，无其他未预期变更

- [ ] **Step 3.6：commit**

Run:
```bash
git commit -m "$(cat <<'EOF'
chore: 删除 tests/Justfile/launchd 与 .claude/skills/ 残壳

测试已删除（用户决定不保留单元测试），Justfile 删除（仅是 claude -p 包装），
launchd 空目录与 .claude/skills/ 旧嵌套残壳一并清理。
EOF
)"
```

Expected: `7 files changed, X deletions(-)`（5 个 test 文件 + Justfile + 可能的 conftest）。

---

## Task 4: README 加设计决策区 + 删 docs/（spec commit 5）

**Files:**
- Modify: `README.md`（在 License 之前插入"设计决策"区）
- Delete: `docs/`（整目录，含本 spec 与 plan）

- [ ] **Step 4.1：在 README.md License 之前插入"设计决策"区**

用 Edit 工具：

old_string:
```
## License

MIT
```

new_string:
```
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

### B 站接入：本地录播优先
WBI 签名虽实现，仍可能被风控。日常输入源以 biliup 本地录播扫描为主，
URL / 单条作为补充。

### 状态机
`scripts/state.py` 维护 `data/state.json`，按 BVID 幂等推进：
discovered → transcribed → analyzed → notified → done。
失败标记 `*_err` 后跳过，下一轮重试。

### 飞书发送阈值
报告 ≤ `notify.max_message_chars` 走文本消息，超长走文件上传
（通过 lark-im skill 的 `+send-file`）。

### 数据目录归属
`data/` 位于仓库根、git 忽略。Skill 假设「仓库根 == 工作根」——
若部署到其他位置，需调整或在 `references/up-list.yaml` 中显式指定路径。

## License

MIT
```

- [ ] **Step 4.2：删除 docs/ 整目录**

Run:
```bash
git rm -r docs
```

Expected: 输出多行 `rm 'docs/...'`，包括两个 spec、两个 plan（`2026-04-24-...` 和本 plan `2026-04-25-...`）。

> 注：本 plan 文件本身也被删，但 git log 中通过 `fdd0ebe`（spec commit）和本 commit 的前置 commit 仍可追溯。如需在删除前再次确认，先 `git log --all -- docs/` 看一下。

- [ ] **Step 4.3：commit**

Run:
```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: 把设计决策合并入 README，删除 docs/

仓库重构告一段落：spec/plan 通过 git log 永久可查，
关键决策提炼到 README 末尾的「设计决策」区，
docs/superpowers/ 整目录清理。
EOF
)"
```

Expected: `5 files changed, ~25 insertions(+), Y deletions(-)`（README 增删 + 4 个 docs 文件删除）。

---

## Final Verification

- [ ] **Step 5.1：git 视角下根目录正好是这些条目**

Run:
```bash
git ls-tree HEAD --name-only | sort
```

Expected:
```
.claude
.gitignore
.python-version
README.md
SKILL.md
config
pyproject.toml
references
scripts
uv.lock
```

任何额外条目（如 `tests`、`Justfile`、`launchd`、`docs`、`Skill.md` 拼写错的复本）都是 bug，停下排查。

- [ ] **Step 5.2：禁忌路径全部消失**

Run:
```bash
git grep -n "\.claude/skills/stock-review" || echo "OK: 无残留"
```

Expected: `OK: 无残留`

- [ ] **Step 5.3：SKILL.md 内的所有相对路径在新结构下解析得到**

Run:
```bash
# 提取 SKILL.md 中提到的相对路径，逐一检查存在
grep -oE '(scripts|references|config|data)/[A-Za-z0-9_./-]+' SKILL.md | sort -u | while read p; do
  if [ -e "$p" ] || [[ "$p" == data/* ]]; then
    echo "OK $p"
  else
    echo "MISSING $p"
  fi
done
```

Expected: 全部 `OK ...`，无 `MISSING`。`data/` 子路径例外 —— 它们是运行时产物，存在与否不重要，脚本侧自行 mkdir。

- [ ] **Step 5.4：脚本仍可加载（不依赖重型 ASR/网络）**

Run:
```bash
uv run python -c "import importlib.util
for n in ['discover','fetch','state','transcribe']:
    importlib.util.spec_from_file_location(n, f'scripts/{n}.py')
    print(f'{n} OK')
"
```

Expected: 4 行 `xxx OK`。

- [ ] **Step 5.5：discover.py --help 实际执行**

Run:
```bash
uv run python scripts/discover.py --help 2>&1 | head -20
```

Expected: 输出 argparse 的 usage 与 options 列表，无 `ModuleNotFoundError` 或 `FileNotFoundError`。

如果失败：检查 `discover.py` 顶层 import 是否引用了 `.claude/skills/stock-review/...`（理论上不应该，但需确认）。

- [ ] **Step 5.6：commit 链审视**

Run:
```bash
git log --oneline -8
```

Expected（自上而下）:
```
<hash> docs: 把设计决策合并入 README，删除 docs/
<hash> chore: 删除 tests/Justfile/launchd 与 .claude/skills/ 残壳
<hash> chore: 更新内部路径引用至仓库根
<hash> refactor: 把 SKILL 主体从 .claude/skills/ 提到仓库根
fdd0ebe docs: 写入 skill 仓库重构 spec
b264ada feat: 多输入源支持 + 安装指引 + 去敏感
2593830 fix: 修复 discover WBI 签名和 transcribe FunASR 调用
b01e978 feat(skill): 写 stock-review skill 编排说明
```

- [ ] **Step 5.7：（可选）push**

按用户 CLAUDE.md「禁止 force push、修改已 push 历史」与"非用户明确要求不 push"原则，**默认不 push**。

如果用户明确要求 push：
```bash
git push origin <branch>
```

---

## Self-Review

- [x] **Spec coverage**：spec 中所有目标（仓库即 Skill / 保留 pyproject+uv / 删 tests+Justfile / 引用更新 / README 决策区 / docs 收尾删除）在 Task 1-4 中均有对应步骤。✅

- [x] **Placeholder scan**：每个 Edit 步骤均给出完整 old_string + new_string；没有 "TODO"、"实现错误处理"、"类似 Task N" 等。✅

- [x] **Type / 路径一致性**：12 个 git mv 文件清单与 Pre-flight Step 0.3 的输出一致；Task 2 中 README 的引用与 spec 中"内部引用更新清单"一致。✅

- [x] **Spec 的 .DS_Store 假设修正**：Task 1.6 用条件检查 + `rm -rf .claude/skills` 替代了 spec 中"git rm --cached"的硬假设（实际未追踪）。✅

- [x] **新增的 .claude/settings.local.json 路径更新**：spec 风险节有提到，Task 2.9 落实。✅
