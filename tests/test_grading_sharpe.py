"""Grading Sharpe tests: window Sharpe labeled, zero-variance safe (mine)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "send_daily_grading",
        ROOT / "production" / "ops" / "send_daily_grading.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["send_daily_grading_sharpe"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def _frame():
    import polars as pl

    return pl.DataFrame([
        {"stake": 50.0, "pnl": 45.0, "edge": 0.15, "result": "win", "clv_pp": 0.02},
        {"stake": 50.0, "pnl": -50.0, "edge": 0.13, "result": "loss", "clv_pp": -0.01},
        {"stake": 50.0, "pnl": 60.0, "edge": 0.20, "result": "win", "clv_pp": None},
    ])


def test_summarize_window_sharpe_labeled() -> None:
    import polars as pl

    # Owner 2026-09-24: phone alert shows window Sharpe (per-bet, never
    # annualized) next to ROI — method profitability, not one ticket.
    s = _mod.summarize(_frame())
    assert isinstance(s["sharpe"], float)
    flat = pl.DataFrame([
        {"stake": 50.0, "pnl": 45.0, "edge": 0.15, "result": "win"},
        {"stake": 50.0, "pnl": 45.0, "edge": 0.15, "result": "win"},
    ])
    assert _mod.summarize(flat)["sharpe"] is None  # zero variance: no Sharpe
    assert _mod.summarize(_frame().head(0))["n"] == 0
