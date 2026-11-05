"""Unit tests for monthly quant math ( Sharpe / Sortino / drawdown )."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "monthly_quant",
        ROOT / "production" / "ops" / "market_research" / "monthly_quant.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["monthly_quant"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def test_quant_block_known_series() -> None:
    import statistics
    r = [0.9, -1.0, 0.9, -1.0]  # per-ticket ROIs
    pnl = [45.0, -50.0, 45.0, -50.0]
    q = _mod.quant_block(r, pnl)
    assert q["n"] == 4
    assert q["sharpe_pb"] == round((sum(r) / 4) / statistics.stdev(r), 3)
    # downside MAR: sqrt((1+1)/4) = sqrt(0.5); mean -0.05
    import math
    assert q["sortino_pb"] == round((-0.05) / math.sqrt(0.5), 3)
    assert q["maxdd_dollars"] == 55.0  # cum 45,-5,40,-10: peak 45, worst 45-(-10)
    assert q["maxdd_u"] == round(q["maxdd_dollars"] / 50.0, 2)


def test_quant_block_drawdown_path() -> None:
    q = _mod.quant_block([0.5, -1.0, -1.0, 0.5], [50.0, -100.0, -100.0, 50.0])
    # cum: 50, -50, -150, -100 -> peak 50, max dd 200
    assert q["maxdd_dollars"] == 200.0
    assert q["maxdd_u"] == 4.0


def test_monthly_table_shape() -> None:
    df = pl.DataFrame([
        {"gd": "2026-04-01", "pnl": 45.0, "stake": 50.0},
        {"gd": "2026-04-02", "pnl": -50.0, "stake": 50.0},
        {"gd": "2026-05-01", "pnl": 60.0, "stake": 50.0},
    ])
    rep = _mod.monthly_table(df, "gd", "pnl", "stake")
    assert set(rep["monthly"]) == {"2026-04", "2026-05"}
    assert rep["monthly"]["2026-04"]["n"] == 2
    assert rep["expanding"]["2026-05"]["n"] == 3
