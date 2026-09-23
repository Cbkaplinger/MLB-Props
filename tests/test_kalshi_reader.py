"""Kalshi K-ladder reader tests (keyless elections host; no network)."""

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


def _mkt(**kw):
    base = {"ticker": "KX", "title": "Framber Valdez: 9+ strikeouts?",
            "floor_strike": 8.5, "event_ticker": "KXMLBKS-26SEP231310WSHDET"}
    base.update(kw)
    return base


def test_parse_last_and_bid_fallback() -> None:
    row = kr.parse_k_market(_mkt(last_price_dollars="0.0100"), now_utc="t")
    assert row is not None and row["player_name"] == "Framber Valdez"
    assert row["line"] == 8.5 and row["over_prob"] == 0.01
    assert row["under_prob"] == 0.99 and row["source"] == "kalshi"
    mid = kr.parse_k_market(_mkt(last_price_dollars=None, title="Tarik Skubal: 7+ strikeouts?",
                                 floor_strike=6.5, yes_bid_dollars="0.52",
                                 no_bid_dollars="0.50"), now_utc="t")
    assert mid is not None and mid["over_prob"] == 0.51
    assert kr.parse_k_market(_mkt(title="Yankees win pennant")) is None
    assert kr.parse_k_market(_mkt(title="Gerrit Cole over 5.5 Ks",
                                  last_price_dollars="0.5")) is None
    assert kr.parse_k_market(_mkt(title="Max Fried: 6+ strikeouts?",
                                  floor_strike=None,
                                  last_price_dollars="0.5")) is None


def test_event_game_date() -> None:
    assert kr.event_game_date("KXMLBKS-26SEP231310WSHDET") == "2026-09-23"
    assert kr.event_game_date("KXMLBKS-26SEP221835TORBAL") == "2026-09-22"
    assert kr.event_game_date("garbage") is None


def test_panel_write_roundtrip(tmp_path) -> None:
    rows = [kr.parse_k_market(_mkt(last_price_dollars="0.99"), now_utc="t")]
    path = kr.write_panel([r for r in rows if r], game_date="2026-09-23",
                          out_dir=tmp_path)
    assert path.name == "kalshi_panel_2026-09-23.parquet"
    import polars as pl

    back = pl.read_parquet(path)
    assert back.height == 1 and back["player_name"][0] == "Framber Valdez"
