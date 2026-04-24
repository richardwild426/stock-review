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
