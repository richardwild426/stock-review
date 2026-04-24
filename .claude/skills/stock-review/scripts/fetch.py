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