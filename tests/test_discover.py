import importlib.util
import io
import json
import sys
import contextlib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/discover.py"
spec = importlib.util.spec_from_file_location("discover", SCRIPT)
discover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discover)


def _fake_api_response(vlist: list[dict], code: int = 0) -> dict:
    return {"code": code, "data": {"list": {"vlist": vlist}}}


def _make_config(tmp_path: Path, self_mid: int = 100, ups: list[dict] | None = None) -> Path:
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
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = discover.main(args)
        assert rc == 0
        rows = json.loads(buf.getvalue())
        bvids = sorted(r["bvid"] for r in rows)
        assert bvids == ["BV_100", "BV_200"]