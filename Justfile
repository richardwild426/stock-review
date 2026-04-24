set shell := ["bash", "-cu"]

test:
    uv run pytest

test-one name:
    uv run pytest -k {{name}}

lint:
    uv run ruff check .

fmt:
    uv run ruff format .

# 手动扫描
scan:
    claude -p "/stock-review scan"

# 手动分析单条
analyze target:
    claude -p "/stock-review {{target}}"
