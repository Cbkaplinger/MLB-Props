"""Showdown metric tests: Poisson survival, Brier/logloss/ECE (pure)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "calibrate_showdown",
        ROOT / "production" / "ops" / "market_research" / "calibrate_showdown.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibrate_showdown"] = mod
    spec.loader.exec_module(mod)
    return mod


cs = _load()


def test_poisson_over_known_values() -> None:
    # P(K > 4.5) at lam=5 = P(K>=5) = 1 - P(K<=4) ≈ 0.5595.
    assert abs(cs.poisson_over(5.0, 4.5) - 0.5595) < 0.005
    assert cs.poisson_over(0.0, 4.5) == 0.0
    assert cs.poisson_over(5.0, 4.5) > cs.poisson_over(5.0, 6.5)


def test_brier_logloss_ece() -> None:
    assert cs.brier([1.0, 0.0], [1, 0]) == 0.0
    assert cs.brier([0.5, 0.5], [1, 0]) == 0.25
    assert cs.logloss([1.0, 0.0], [1, 0]) < 0.001
    assert cs.logloss([0.0, 1.0], [1, 0]) > 10.0
    assert cs.ece([0.9, 0.1], [1, 0]) < 0.11
    assert cs.ece([0.5, 0.5], [1, 1]) == 0.5  # confident half, all hit = max error


def test_kalshi_bridge_parses_tickers(tmp_path, monkeypatch) -> None:
    import polars as pl

    lad = pl.DataFrame([{
        "event_ticker": "KXMLBKS-26AUG041835LAABAL", "rung": 6,
        "game_date": "2026-08-04", "player_norm": "Cade Povich"}])
    clo = pl.DataFrame([{
        "market_ticker": "KXMLBKS-26AUG041835LAABAL-LAAGRODRIGUEZ21-6",
        "close_fair_over": 0.42}])
    lad.write_parquet(tmp_path / "k_ladder.parquet")
    clo.write_parquet(tmp_path / "k_closes.parquet")
    monkeypatch.setattr(cs, "K_LADDER", tmp_path / "k_ladder.parquet")
    monkeypatch.setattr(cs, "K_CLOSES", tmp_path / "k_closes.parquet")
    m = cs.kalshi_close_map()
    assert m == {("2026-08-04", "cade povich", 5.5): 0.42}
