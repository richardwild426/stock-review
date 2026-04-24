#!/usr/bin/env python3
"""Discover new uploads from Bilibili and diff against local state."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import yaml

BILI_API = "https://api.bilibili.com/x/space/wbi/arc/search"
WBI_KEY_URL = "https://api.bilibili.com/x/web-interface/nav"


class CookieExpired(Exception):
    pass


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