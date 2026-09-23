"""Kalshi K-reader tests: parser aliases, panel write, auth gating (no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "kalshi_k_reader",
        ROOT / "production" / "ops" / "market_research" / "kalshi_k_reader.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_k_reader"] = mod
    spec.loader.exec_module(mod)
    return mod


kr = _load()


def test_parse_last_price_and_aliases() -> None:
    row = kr.parse_k_market(
        {"title": "Chris Sale over 7.5 Ks", "ticker": "KX-1",
         "last_price": 58, "event_ticker": "E-1"}, now_utc="t")
    assert row is not None and row["player_name"] == "Chris Sale"
    assert row["line"] == 7.5 and row["over_prob"] == 0.58
    assert row["under_prob"] == 0.42 and row["source"] == "kalshi"
    # Bid-midpoint fallback when no last price.
    mid = kr.parse_k_market(
        {"name": "Tarik Skubal 6.5 strikeouts", "yes_bid": 52, "no_bid": 50},
        now_utc="t")
    assert mid is not None and mid["over_prob"] == 0.51
    # Non-K and priceless markets skip loud (None, counted by caller).
    assert kr.parse_k_market({"title": "Yankees win pennant"}) is None
    assert kr.parse_k_market({"title": "Gerrit Cole over 5.5 Ks"}) is None


def test_panel_write_roundtrip(tmp_path) -> None:
    rows = [kr.parse_k_market(
        {"title": "Zack Wheeler under 6.5 Ks", "ticker": "KX-2",
         "yes_bid": 60, "no_bid": 44}, now_utc="t")]
    path = kr.write_panel([r for r in rows if r], game_date="2026-09-23",
                          out_dir=tmp_path)
    assert path.name == "kalshi_panel_2026-09-23.parquet"
    import polars as pl

    back = pl.read_parquet(path)
    assert back.height == 1 and back["player_name"][0] == "Zack Wheeler"


def test_missing_key_fails_closed_loud(monkeypatch) -> None:
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    try:
        kr.api_key()
        raise AssertionError("expected KalshiAuthError")
    except kr.KalshiAuthError as exc:
        assert "kalshi.com" in str(exc).lower()
