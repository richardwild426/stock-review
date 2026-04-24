#!/usr/bin/env python3
"""Discover videos from multiple sources: local recordings, manual URLs, or Bilibili API."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

BILI_API = "https://api.bilibili.com/x/space/wbi/arc/search"
WBI_KEY_URL = "https://api.bilibili.com/x/web-interface/nav"


class CookieExpired(Exception):
    pass


def scan_local_recordings(base_dir: Path, state_file: Path,
                          mtime_tolerance_hours: int = 6) -> list[dict]:
    """Scan biliup backup directory for new recordings.

    Returns list of candidates with file_path and estimated pubdate.
    """
    if not base_dir.exists():
        return []

    candidates = []
    state = _load_state(state_file)

    # 遍历子目录（每个子目录对应一个直播间）
    for room_dir in base_dir.iterdir():
        if not room_dir.is_dir():
            continue
        room_id = room_dir.name  # 直播间号作为标识

        # 遍历 FLV 文件
        for flv_file in room_dir.glob("*.flv"):
            file_id = f"local_{room_id}_{flv_file.stem}"
            # 检查是否已处理
            if state.get(file_id, {}).get("status") == "done":
                continue

            # 用文件修改时间作为 pubdate
            mtime = datetime.fromtimestamp(flv_file.stat().st_mtime)
            pubdate = int(mtime.timestamp())

            candidates.append({
                "bvid": file_id,
                "title": flv_file.stem,
                "pubdate": pubdate,
                "owner_mid": int(room_id) if room_id.isdigit() else 0,
                "is_self": True,
                "file_path": str(flv_file),
                "source": "local",
            })

    return candidates


def parse_manual_input(input_path: Path) -> list[dict]:
    """Parse manual input file containing video URLs or file paths.

    Supports:
    - Bilibili video URLs (https://www.bilibili.com/video/BVxxx)
    - Local video file paths
    """
    if not input_path.exists():
        return []

    candidates = []
    for line in input_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Bilibili URL
        if "bilibili.com/video/" in line:
            match = re.search(r"(BV[\w]+|av\d+)", line)
            if match:
                video_id = match.group(1)
                candidates.append({
                    "bvid": video_id,
                    "title": f"Manual: {video_id}",
                    "pubdate": int(time.time()),
                    "is_self": False,
                    "url": line,
                    "source": "url",
                })
        # Local file path
        elif Path(line).exists():
            file_path = Path(line)
            file_id = f"manual_{file_path.stem}"
            candidates.append({
                "bvid": file_id,
                "title": file_path.stem,
                "pubdate": int(time.time()),
                "is_self": True,
                "file_path": str(file_path),
                "source": "local",
            })

    return candidates


def _get_wbi_keys(cookie: str | None, timeout: float) -> tuple[str, str]:
    """获取 WBI 签名所需的 key 和 val（从 nav 接口）。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    with httpx.Client(timeout=timeout, headers=headers) as client:
        r = client.get(WBI_KEY_URL)
        r.raise_for_status()
        data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"nav api error: {data}")
    img = data["data"]["wbi_img"]
    # key: img_url 的文件名去掉后缀，val: sub_url 的文件名去掉后缀
    key = img["img_url"].split("/")[-1].split(".")[0]
    val = img["sub_url"].split("/")[-1].split(".")[0]
    return key, val


def _wbi_sign(params: dict[str, Any], key: str, val: str) -> str:
    """WBI 签名算法：字典序排序 + 特殊字符转义 + MD5 + 截取前32位。"""
    # 排序参数
    sorted_params = sorted(params.items())
    # 拼接 query string
    query = urllib.parse.urlencode(sorted_params)
    # B站 WBI 需要对特殊字符进行替换（保持 % 编码一致性）
    # 将 !'()* 替换为对应的 %XX 编码
    query = query.replace("'", "%27").replace("!", "%21").replace("*", "%2A")
    # 加上 val 后缀
    to_sign = query + val
    # MD5 截取前32位
    md5 = hashlib.md5(to_sign.encode()).hexdigest()
    return md5[:32]


def _call_bili_api(mid: int, count: int, cookie: str | None,
                   timeout: float) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{mid}/",
    }
    if cookie:
        headers["Cookie"] = cookie

    # 获取 WBI keys
    wbi_key, wbi_val = _get_wbi_keys(cookie, timeout)

    # 构建基础参数
    params = {
        "mid": mid,
        "ps": count,
        "pn": 1,
        "order": "pubdate",
        "platform": "web",
        "web_location": 1550101,
    }
    # 添加 wts 时间戳
    params["wts"] = int(time.time())
    # 计算 w_rid 签名
    params["w_rid"] = _wbi_sign(params, wbi_key, wbi_val)

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


def _load_state(state_file: Path) -> dict:
    """Load state file or return empty dict."""
    if state_file.exists():
        return json.loads(state_file.read_text() or "{}")
    return {}


def diff_against_state(candidates: list[dict], state_file: Path) -> list[dict]:
    """Return candidates whose BVID isn't in state with status='done'."""
    state = _load_state(state_file)
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
    p = argparse.ArgumentParser(description="Discover videos from multiple sources")
    p.add_argument("--config", type=Path, required=True,
                   help="up-list.yaml 路径")
    p.add_argument("--state-file", type=Path, required=True)
    p.add_argument("--cookies", type=Path, required=True)
    p.add_argument("--manual-input", type=Path, default=None,
                   help="手动输入文件路径（包含URL或本地文件路径）")
    p.add_argument("--skip-api", action="store_true",
                   help="跳过B站API获取（因风控问题）")
    args = p.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    cookie = _load_cookie(args.cookies)

    results: list[dict] = []
    errors: list[str] = []

    # 1. 扫描本地录播文件
    biliup_cfg = cfg.get("biliup") or {}
    base_dir = Path(biliup_cfg.get("base_dir", "~/Movies/bilive-recoder/backup")).expanduser()
    if base_dir.exists():
        local_videos = scan_local_recordings(
            base_dir=base_dir,
            state_file=args.state_file,
            mtime_tolerance_hours=biliup_cfg.get("mtime_tolerance_hours", 6),
        )
        results.extend(local_videos)
        if local_videos:
            print(f"[INFO] 发现 {len(local_videos)} 个本地录播文件", file=sys.stderr)

    # 2. 解析手动输入
    if args.manual_input and args.manual_input.exists():
        manual_videos = parse_manual_input(args.manual_input)
        results.extend(manual_videos)
        if manual_videos:
            print(f"[INFO] 发现 {len(manual_videos)} 个手动输入视频", file=sys.stderr)

    # 3. B站 API（可选，因风控问题可能失败）
    if not args.skip_api:
        # self 源
        self_cfg = cfg.get("self") or {}
        if self_cfg.get("mid") and not self_cfg.get("prefer_local"):
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
                    r["source"] = "api"
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
                for r in rows:
                    r["source"] = "api"
                results.extend(rows)
            except Exception as e:
                errors.append(f"UP_{up['mid']}_FAILED: {e}")

    # 过滤已处理的视频
    new_videos = diff_against_state(results, args.state_file)

    # 输出结果
    json.dump(new_videos, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)

    # 打印统计
    print(f"[SUMMARY] 共发现 {len(new_videos)} 个待处理视频", file=sys.stderr)

    return 0 if new_videos else 1


if __name__ == "__main__":
    raise SystemExit(main())