"""Unit tests for the champion grader (pure grading math)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "grade_champion_2026",
        ROOT / "production" / "ops" / "market_research" / "grade_champion_2026.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grade_champion_2026"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def _frame() -> pl.DataFrame:
    return pl.DataFrame([
        {"gd": "2026-04-01", "side": "under", "snap": "open", "edge": 0.15,
         "won": 1, "clv_pp": 2.0, "stake_flat1u": 50.0, "pnl_flat1u": 45.0},
        {"gd": "2026-04-02", "side": "under", "snap": "morning", "edge": 0.13,
         "won": 0, "clv_pp": -1.0, "stake_flat1u": 50.0, "pnl_flat1u": -50.0},
        {"gd": "2026-05-01", "side": "over", "snap": "open", "edge": 0.20,
         "won": 1, "clv_pp": None, "stake_flat1u": 50.0, "pnl_flat1u": 60.0},
    ])


def test_top_level_numbers() -> None:
    g = _mod.grade_frame(_frame(), "pnl_flat1u", "stake_flat1u")
    assert g["n"] == 3
    assert g["roi"] == (45.0 - 50.0 + 60.0) / 150.0
    assert abs(g["wr"] - 2 / 3) < 1e-12
    assert abs(g["xroi_edge"] - (0.15 + 0.13 + 0.20) / 3) < 1e-12
    assert g["n_clv"] == 2
    assert g["mean_clv_pp"] == 0.5
    assert g["beat_rate"] == 0.5


def test_splits_and_monthly() -> None:
    g = _mod.grade_frame(_frame(), "pnl_flat1u", "stake_flat1u")
    assert g["by_side"]["under"]["n"] == 2
    assert g["by_side"]["over"]["n"] == 1
    assert g["by_snap"]["open"]["n"] == 2
    assert set(g["monthly"]) == {"2026-04", "2026-05"}
    assert g["monthly"]["2026-04"]["n"] == 2


def test_empty_frame() -> None:
    assert _mod.grade_frame(_frame().head(0), "pnl_flat1u", "stake_flat1u") == {"n": 0}


def test_attach_ensemble() -> None:
    taken = pl.DataFrame([
        {"gd": "2026-04-01", "key": "a", "line": 6.5, "side": "under",
         "p_mkt": 0.60, "edge": 0.15, "won": 1,
         "stake_flat1u": 50.0, "pnl_flat1u": 45.0},
        {"gd": "2026-04-02", "key": "b", "line": 5.5, "side": "over",
         "p_mkt": 0.55, "edge": 0.13, "won": 0,
         "stake_flat1u": 50.0, "pnl_flat1u": -50.0},
    ])
    ens = pl.DataFrame([
        {"gd": "2026-04-01", "key": "a", "line": 6.5,
         "ens_over": 0.40, "ens_under": 0.62, "n_books": 5},
    ])
    out = _mod.attach_ensemble(taken, ens).sort("gd")
    vals = out["ens_clv_pp"].to_list()
    assert abs(vals[0] - (0.62 - 0.60) * 100.0) < 1e-9
    assert vals[1] is None
