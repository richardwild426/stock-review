import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_state_file(tmp_path: Path) -> Path:
    """Empty state.json for per-test isolation."""
    f = tmp_path / "state.json"
    f.write_text("{}")
    return f


@pytest.fixture
def sample_state_file(tmp_path: Path) -> Path:
    """Preloaded state.json with a mix of statuses."""
    f = tmp_path / "state.json"
    f.write_text(json.dumps({
        "BV1AAA": {"status": "done", "processed_at": "2026-04-23T21:30:00+08:00",
                    "report_path": "data/reports/x.md", "source": "local",
                    "method": "L3", "error": None, "retry_count": 0},
        "BV1BBB": {"status": "fetched", "processed_at": "2026-04-23T22:00:00+08:00",
                    "report_path": None, "source": "ytdlp",
                    "method": None, "error": None, "retry_count": 0},
        "BV1CCC": {"status": "fetch_err", "processed_at": "2026-04-23T22:05:00+08:00",
                    "report_path": None, "source": "ytdlp",
                    "method": None, "error": "HTTP 403", "retry_count": 3},
    }))
    return f
