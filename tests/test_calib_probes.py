"""Unit tests for calibration probes (synthetic only, no data reads)."""

import importlib.util
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
MR = ROOT / "production" / "ops" / "market_research"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, MR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_spot = _load("highconf_spotcheck")
_drift = _load("calib_drift_sim")


def test_taken_p_sides() -> None:
    df = pl.DataFrame({"side": ["over", "under", "under"],
                       "p_ours_cal": [0.7, 0.7, 0.2]})
    got = df.select(_spot.taken_p()).to_series().to_list()
    assert [round(v, 9) for v in got] == [0.7, 0.3, 0.8]


def test_band_stats_empty() -> None:
    df = pl.DataFrame({"side": [], "p_ours_cal": [], "won": [], "pnl": [], "clv_pp": []},
                      schema={"side": pl.String, "p_ours_cal": pl.Float64,
                              "won": pl.Boolean, "pnl": pl.Float64, "clv_pp": pl.Float64})
    df = df.with_columns(_spot.taken_p())
    assert _spot.band_stats(df, 0.8) == {"lo": 0.8, "n": 0}


def test_band_stats_perfect() -> None:
    import numpy as np
    df = pl.DataFrame({"side": ["over"] * 4, "p_ours_cal": [0.9] * 4,
                       "won": [True] * 4, "pnl": [45.0] * 4, "clv_pp": [1.0] * 4})
    df = df.with_columns(_spot.taken_p())
    b = _spot.band_stats(df, 0.8)
    assert b["n"] == 4 and b["gap"] == round(0.9 - 1.0, 4)
    assert b["brier"] == round(float(np.mean((0.9 - 1.0) ** 2)), 4)


def test_ece_10_perfect_and_worst() -> None:
    import numpy as np
    p = np.array([0.05, 0.15, 0.85, 0.95])
    assert abs(_drift.ece_10(p, np.array([0, 0, 1, 1])) - 0.1) < 1e-9
    assert _drift.ece_10(np.array([0.9, 0.9]), np.array([0, 0])) == 0.9
    assert _drift.ece_10(np.array([]), np.array([])) == 0.0


def test_drift_row_zero_shift_identity() -> None:
    import numpy as np
    p = np.array([0.6, 0.4, 0.7])
    w = np.array([1.0, 0.0, 1.0])
    e = np.array([0.15, 0.12, 0.18])
    r = _drift.drift_row(p, w, e, 0.0)
    assert r["mean_edge_shift"] == 0.0 and r["edge_mean"] == round(float(e.mean()), 4)
