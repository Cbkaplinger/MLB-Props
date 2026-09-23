"""DATA-1A serving gates: fail-LOUD, never raise, never block."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.serving_gates import check_serving  # noqa: E402

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _odds(tmp_path: Path, *, slate: str = "2026-09-23",
          rolling_max: str = "2026-09-22") -> Path:
    d = tmp_path / "odds"
    d.mkdir()
    pl.DataFrame({"game_date": [slate]}).write_parquet(d / "recommendations.parquet")
    (d / "last_log.json").write_text(json.dumps(
        {"build_meta": {"rolling_max_date": rolling_max}}))
    return d


def test_fresh_serving_is_ok(tmp_path) -> None:
    out = check_serving(_odds(tmp_path), "2026-09-23", now_utc=NOW)
    assert out == {"ok": True, "warnings": []}


def test_stale_and_missing_warn_but_never_raise(tmp_path) -> None:
    d = _odds(tmp_path, slate="2026-09-20", rolling_max="2026-09-18")
    old = time.time() - 30 * 3600  # 30h: safely stale vs any pinned now_utc
    os.utime(d / "recommendations.parquet", (old, old))
    out = check_serving(d, "2026-09-23", now_utc=NOW)
    assert out["ok"] is False
    assert len(out["warnings"]) >= 3  # wrong slate + old mtime + stale rolling
    empty = tmp_path / "empty"
    empty.mkdir()
    out2 = check_serving(empty, "2026-09-23", now_utc=NOW)
    assert out2["ok"] is False and len(out2["warnings"]) == 2
    # Garbage input still returns (fail-open), never raises.
    out3 = check_serving(tmp_path / "nope", "garbage", now_utc=NOW)
    assert out3["ok"] is False and out3["warnings"]
