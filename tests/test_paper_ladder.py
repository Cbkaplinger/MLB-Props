"""Paper ladder tests: rung hit logic (pure)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "paper_ladder",
        ROOT / "production" / "ops" / "market_research" / "paper_ladder.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paper_ladder"] = mod
    spec.loader.exec_module(mod)
    return mod


pl = _load()


def test_rung_hits_side_logic() -> None:
    assert pl.rung_hits(7.0, 6.5, "over") is True
    assert pl.rung_hits(6.0, 6.5, "over") is False
    assert pl.rung_hits(4.0, 4.5, "under") is True
    assert pl.rung_hits(5.0, 4.5, "under") is False
    # Pushes are losses for rung purposes (no whole-number rungs exist,
    # but exact-line equality must not count as a hit either side).
    assert pl.rung_hits(4.5, 4.5, "over") is False
    assert pl.rung_hits(4.5, 4.5, "under") is False
