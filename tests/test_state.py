import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/state.py"


def run_cli(args: list[str], state_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state-file", str(state_file), *args],
        capture_output=True, text=True,
    )


class TestMark:
    def test_mark_creates_entry(self, tmp_state_file: Path):
        r = run_cli(
            ["mark", "BV1XXX", "--status", "discovered", "--source", "ytdlp"],
            tmp_state_file,
        )
        assert r.returncode == 0, r.stderr
        state = json.loads(tmp_state_file.read_text())
        assert state["BV1XXX"]["status"] == "discovered"
        assert state["BV1XXX"]["source"] == "ytdlp"
        assert state["BV1XXX"]["retry_count"] == 0
        assert state["BV1XXX"]["processed_at"] is not None

    def test_mark_updates_existing_entry(self, sample_state_file: Path):
        r = run_cli(
            ["mark", "BV1BBB", "--status", "transcribed"],
            sample_state_file,
        )
        assert r.returncode == 0
        state = json.loads(sample_state_file.read_text())
        assert state["BV1BBB"]["status"] == "transcribed"
        # source 保留原值（没传就不覆盖）
        assert state["BV1BBB"]["source"] == "ytdlp"

    def test_mark_error_increments_retry(self, sample_state_file: Path):
        r = run_cli(
            ["mark", "BV1BBB", "--status", "fetch_err", "--error", "timeout"],
            sample_state_file,
        )
        assert r.returncode == 0
        state = json.loads(sample_state_file.read_text())
        assert state["BV1BBB"]["error"] == "timeout"
        assert state["BV1BBB"]["retry_count"] == 1


class TestGet:
    def test_get_existing(self, sample_state_file: Path):
        r = run_cli(["get", "BV1AAA"], sample_state_file)
        assert r.returncode == 0
        assert json.loads(r.stdout)["status"] == "done"

    def test_get_missing_exits_nonzero(self, tmp_state_file: Path):
        r = run_cli(["get", "BV_NOPE"], tmp_state_file)
        assert r.returncode != 0


class TestListUnprocessed:
    def test_excludes_done(self, sample_state_file: Path):
        r = run_cli(["list-unprocessed"], sample_state_file)
        assert r.returncode == 0
        unprocessed = json.loads(r.stdout)
        bvids = [item["bvid"] for item in unprocessed]
        assert "BV1AAA" not in bvids
        assert "BV1BBB" in bvids
        assert "BV1CCC" in bvids

    def test_empty_state(self, tmp_state_file: Path):
        r = run_cli(["list-unprocessed"], tmp_state_file)
        assert r.returncode == 0
        assert json.loads(r.stdout) == []