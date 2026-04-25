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