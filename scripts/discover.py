#!/usr/bin/env python3
"""Discover videos from local recordings.

Scans biliup.rs backup directory and emits a JSON list of candidates that
still need processing. State (data/state.json) is consulted to skip
terminal entries and to drop entries that have exceeded max_retries.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 终态：已处理完成或主动跳过，不再重新返回
TERMINAL_STATES = {"done", "skipped_too_short", "skipped_no_audio"}

# 录播扫描覆盖的容器格式
LOCAL_VIDEO_EXTS = ("*.flv", "*.mp4", "*.mkv")

DEFAULT_MAX_RETRIES = 3


def scan_local_recordings(base_dir: Path) -> list[dict]:
    """Scan biliup backup directory for recordings.

    Returns all candidates; state filtering happens in diff_against_state.
    """
    if not base_dir.exists():
        return []

    candidates = []
    for room_dir in base_dir.iterdir():
        if not room_dir.is_dir():
            continue
        room_id = room_dir.name

        for pattern in LOCAL_VIDEO_EXTS:
            for video_file in room_dir.glob(pattern):
                file_id = f"local_{room_id}_{video_file.stem}"
                mtime = datetime.fromtimestamp(video_file.stat().st_mtime)
                candidates.append({
                    "bvid": file_id,
                    "title": video_file.stem,
                    "pubdate": int(mtime.timestamp()),
                    "owner_mid": int(room_id) if room_id.isdigit() else 0,
                    "is_self": True,
                    "file_path": str(video_file),
                    "source": "local",
                })

    return candidates


def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        return json.loads(state_file.read_text() or "{}")
    return {}


def diff_against_state(candidates: list[dict], state_file: Path,
                       max_retries: int) -> list[dict]:
    """Return candidates not in a terminal state and within retry budget.

    Active intermediate states (discovered/transcribed/analyzed/notified)
    are returned with their current entry attached as `_state` so the
    workflow can resume from the right step instead of restarting.

    Entries whose retry_count >= max_retries are skipped (treated as
    permanently failed).
    """
    state = _load_state(state_file)
    out: list[dict] = []
    for c in candidates:
        entry = state.get(c["bvid"], {})
        status = entry.get("status")
        if status in TERMINAL_STATES:
            continue
        if entry.get("retry_count", 0) >= max_retries:
            continue
        if status:
            c["_state"] = entry
        out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Discover local recordings to process")
    p.add_argument("--config", type=Path, required=True,
                   help="up-list.yaml 路径")
    p.add_argument("--state-file", type=Path, required=True)
    args = p.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())

    biliup_cfg = cfg.get("biliup") or {}
    base_dir = Path(biliup_cfg.get("base_dir", "~/Movies/bilive-recoder/backup")).expanduser()
    max_retries = int((cfg.get("discover") or {}).get("max_retries", DEFAULT_MAX_RETRIES))

    candidates = scan_local_recordings(base_dir=base_dir)
    if candidates:
        print(f"[INFO] 扫描到 {len(candidates)} 个本地录播文件", file=sys.stderr)

    new_videos = diff_against_state(candidates, args.state_file, max_retries)

    json.dump(new_videos, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    print(f"[SUMMARY] 共 {len(new_videos)} 个待处理视频（max_retries={max_retries}）",
          file=sys.stderr)
    return 0 if new_videos else 1


if __name__ == "__main__":
    raise SystemExit(main())
