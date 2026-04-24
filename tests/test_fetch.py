import importlib.util
import os
import time
from pathlib import Path
from unittest.mock import patch

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