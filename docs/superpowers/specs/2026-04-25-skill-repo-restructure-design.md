# Skill 仓库重构设计：从「项目内嵌 Skill」到「仓库即 Skill」

- 日期：2026-04-25
- 作者：Claude（与用户协作）
- 状态：已通过，待实施
- 参考项目：[ALBEDO-TABAI/video-copy-analyzer](https://github.com/ALBEDO-TABAI/video-copy-analyzer)

## 背景与动机

当前仓库 `stock-review` 同时承担两种身份：

1. **Python 工程**：根目录有 `pyproject.toml`、`uv.lock`、`tests/`、`Justfile`
2. **Claude Code Skill 包**：`.claude/skills/stock-review/` 下有 `SKILL.md` + `scripts/` + `references/` + `config/`

这种"双重身份"导致几个具体问题：

- 测试在根 `tests/`，被测代码却深埋 `.claude/skills/stock-review/scripts/`，路径不对称，`pyproject.toml` 不得不写 `pythonpath = [".claude/skills/stock-review"]` 绕路。
- `SKILL.md` 第 23 行假设"项目根下 `data/`"，把 Skill 与"被部署到的项目根"绑死；一旦把 Skill 复制到别人的项目，`data/` 应落到何处变得含糊。
- README 的"作为 Skill 安装"流程提供了"全局 / 项目级"两种方式，但都需要用户在目标位置再嵌套一层 `.claude/skills/<name>/`，分发体验冗余。
- `launchd/` 是空目录、`.claude/skills/stock-review/.DS_Store` 已被错误追踪，反映出当前结构在维护层面也偶有疏漏。

参考项目 `ALBEDO-TABAI/video-copy-analyzer` 给出了一种更干净的范式：**仓库本身就是一个 Skill**，clone 到 `~/.claude/skills/<name>/` 即可被 Claude Code 直接加载。本设计将本仓库改造为这种形态。

## 目标

1. 仓库根 == Skill 根，消除 `.claude/skills/<name>/` 的嵌套层。
2. 保留依赖管理（`pyproject.toml` + `uv.lock` + `.python-version`），便于环境重现。
3. 删除阻碍分发的开发遗物（`tests/`、`Justfile`、`launchd/`、`docs/superpowers/`）。
4. 在 README 中保留关键设计决策，使重构后的仓库自包含、可对外分发。
5. 用 `git mv` 完成迁移，保留文件历史。

## 非目标

- 不重写脚本逻辑，只做位置迁移和路径引用更新。
- 不引入 `src/stock_review/` 包形态（保持 `scripts/` 平铺，与参考项目一致）。
- 不改变 Skill 的对外行为：`/stock-review scan` 与 `/stock-review <target>` 触发方式不变。
- 不改变运行时数据 `data/` 的位置（仍在仓库根，gitignore），不引入用户家目录可配置项。

## 重构后的目录结构

```
stock-review/                    ← 仓库根 == Skill 根
├── SKILL.md                     ← Skill 入口（Claude Code 读取）
├── README.md                    ← 文档入口（含「设计决策」区）
├── pyproject.toml               ← 依赖管理
├── uv.lock                      ← 锁定版本
├── .python-version
├── .gitignore
├── scripts/
│   ├── __init__.py
│   ├── discover.py
│   ├── fetch.py
│   ├── state.py
│   └── transcribe.py
├── references/
│   ├── up-list.yaml
│   ├── review-prompt.md
│   ├── analysis-rubric.md
│   └── funasr-hotwords.txt
├── config/
│   ├── cookies.txt.example
│   └── .gitkeep
└── data/                        ← gitignore
    ├── videos/
    ├── subtitles/
    ├── reports/
    └── state.json
```

`.claude/settings.local.json` 保留（Claude Code 项目级配置，与 Skill 分发无关）；`.claude/skills/` 整层被移除。

## 文件迁移映射（git mv，保留历史）

| 旧路径 | 新路径 |
|---|---|
| `.claude/skills/stock-review/SKILL.md` | `SKILL.md` |
| `.claude/skills/stock-review/scripts/__init__.py` | `scripts/__init__.py` |
| `.claude/skills/stock-review/scripts/discover.py` | `scripts/discover.py` |
| `.claude/skills/stock-review/scripts/fetch.py` | `scripts/fetch.py` |
| `.claude/skills/stock-review/scripts/state.py` | `scripts/state.py` |
| `.claude/skills/stock-review/scripts/transcribe.py` | `scripts/transcribe.py` |
| `.claude/skills/stock-review/references/up-list.yaml` | `references/up-list.yaml` |
| `.claude/skills/stock-review/references/review-prompt.md` | `references/review-prompt.md` |
| `.claude/skills/stock-review/references/analysis-rubric.md` | `references/analysis-rubric.md` |
| `.claude/skills/stock-review/references/funasr-hotwords.txt` | `references/funasr-hotwords.txt` |
| `.claude/skills/stock-review/config/cookies.txt.example` | `config/cookies.txt.example` |
| `.claude/skills/stock-review/config/.gitkeep` | `config/.gitkeep` |

## 删除项清单

| 路径 | 理由 |
|---|---|
| `tests/`（含 4 个 `test_*.py` + `conftest.py` + `__init__.py`） | 用户已选删；Skill 多为脚本集合，手动 smoke test 足够 |
| `Justfile` | 用户已选删；仅是 `claude -p` 的薄包装 |
| `launchd/` | 空目录，README 提到的 launchd 调度由用户自行配置 |
| `docs/superpowers/specs/`、`docs/superpowers/plans/`（重构最后一步删除） | 关键决策合并进 README |
| `.claude/skills/`（迁移完后整层删除） | 仓库即 Skill，不再嵌套 |
| `.claude/skills/stock-review/.DS_Store`（已被错误追踪） | `git rm --cached` 清理 |
| `.claude/skills/stock-review/config/cookies.txt`（若被误追踪） | 检查后 `git rm --cached` |

## 内部引用更新清单

### `pyproject.toml`

- 删除整个 `[tool.pytest.ini_options]` 块。
- 移除 `pythonpath = [".claude/skills/stock-review"]`。
- 移除 `dev` 依赖组中的 `pytest`、`pytest-mock`（保留 `ruff`）。

### `SKILL.md`

迁移后所有内部路径已自动正确（原本就是相对 SKILL.md 的相对路径，如 `references/up-list.yaml`、`scripts/discover.py`）。

需确认一处文案：第 23 行"项目根下 `data/`" 含义不变（仓库根 == Skill 根 == 项目根）。

### `README.md`

- **安装方式重写**：`git clone <repo> ~/.claude/skills/stock-review` 一步到位；删除"全局 / 项目级"双方式对比。
- **命令行示例**去掉 `.claude/skills/stock-review/` 前缀，例如：
  - 旧：`python3 .claude/skills/stock-review/scripts/discover.py --config .claude/skills/stock-review/references/up-list.yaml ...`
  - 新：`python3 scripts/discover.py --config references/up-list.yaml ...`
- **删除 Just 命令章节**。
- **新增「设计决策」区**（详见下节）。

### `.gitignore`

- 替换 `.claude/skills/stock-review/config/cookies.txt` → `config/cookies.txt`。
- 保留 `**/cookies.txt` 通配作为防御性兜底。
- `data/*` 条目保持不变。

## README「设计决策」区内容

在 README 末尾、License 之前插入：

```markdown
## 设计决策（Design Notes）

### 为什么是「仓库即 Skill」
本仓库直接作为 Claude Code Skill 分发：clone 到 `~/.claude/skills/stock-review/`
即可使用，不再嵌套 `.claude/skills/<name>/`。SKILL 元数据、脚本、参考材料、
配置和运行时数据全部位于仓库根。

### 三级字幕提取策略
- L1 嵌入字幕：ffmpeg 抽取字幕流（最快、零成本）
- L2 OCR：RapidOCR 识别硬字幕（占位，未默认启用）
- L3 ASR：FunASR 中文识别 + VAD + 标点恢复（兜底）
`transcribe.py` 自动按 L1 → L3 降级。

### B 站接入：本地录播优先
WBI 签名虽实现，仍可能被风控。日常输入源以 biliup 本地录播扫描为主，
URL / 单条作为补充。

### 状态机
`scripts/state.py` 维护 `data/state.json`，按 BVID 幂等推进：
discovered → transcribed → analyzed → notified → done。
失败标记 `*_err` 后跳过，下一轮重试。

### 飞书发送阈值
报告 ≤ `notify.max_message_chars` 走文本消息，超长走文件上传。

### 数据目录归属
`data/` 位于仓库根、git 忽略。Skill 假设「仓库根 == 工作根」——
若部署到其他位置，需调整或在 up-list.yaml 中显式指定路径。
```

最终落地时会从现有 `docs/superpowers/specs/2026-04-24-stock-review-workflow-design.md` 提炼并校正。

## 重构提交策略

按 brainstorming 流程，本设计文档（即本文件）会先 commit 到 `docs/superpowers/specs/`，重构最后一步统一删除 docs/。完整 commit 序列：

1. `docs: 写入 skill 仓库重构 spec`（提交本设计文档）
2. `refactor: 把 SKILL 主体从 .claude/skills/ 提到仓库根`（git mv 主迁移）
3. `chore: 更新内部路径引用`（pyproject.toml / README.md / .gitignore）
4. `chore: 删除 tests / Justfile / launchd / .claude/skills/ 残留`
5. `docs: 把设计决策合并进 README，删除 docs/superpowers/`

git log 永久保留 spec，工作树最终干净。

## 验收清单

重构完成后，仓库根从 git 视角（`git ls-tree HEAD`）应正好包含：

```
.gitignore  .python-version
README.md  SKILL.md  pyproject.toml  uv.lock
scripts/  references/  config/
```

工作树会额外存在 gitignore 项（`.git/`、`.venv/`、`data/`、`.claude/settings.local.json`、`__pycache__/` 等本地副产物），属正常。

**必须不再出现于 git 视角**：`tests/`、`Justfile`、`launchd/`、`docs/`、`.claude/skills/`、`.DS_Store`

**功能验证**：

- `python3 scripts/discover.py --help` 可执行（路径已迁移）。
- `SKILL.md` 内部所有相对路径（`references/...`、`scripts/...`、`config/...`、`data/...`）均能在新结构下解析。
- `git log --follow scripts/discover.py` 能看到迁移前的历史。
- `cat .gitignore | grep cookies` 不再含 `.claude/` 前缀。

## 风险与回滚

- **风险**：若有外部 launchd plist 或 cron 任务硬编码了 `.claude/skills/stock-review/scripts/...`，迁移后会失效。
  - 缓解：README 明确告知路径变更；用户需手动更新自己的调度配置。
- **风险**：`.claude/settings.local.json` 中可能含有指向旧路径的权限规则。
  - 缓解：迁移前检查并就地更新。
- **回滚**：所有迁移均通过 git，回滚执行 `git revert <range>` 即可。

## 不做（YAGNI）

- 不引入 `~/stock-review/` 这种用户家目录默认数据位置（用户明确要求保留仓库根 `data/`）。
- 不引入 `src/stock_review/` 包形态（保持脚本平铺与参考项目一致）。
- 不重写任何脚本的业务逻辑。
- 不引入 LICENSE、README.zh-CN.md（仅迁移和清理，新增文件由用户后续自行决定）。
