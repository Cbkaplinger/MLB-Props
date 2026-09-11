"""Tests for the 2025-lock selector. Economics must match the ledger exactly."""
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from conftest import artifact_path  # noqa: E402
from Python.market import bet_pnl  # noqa: E402
from select_2025_champion import (  # noqa: E402
    apply_config,
    cell_concentration,
    floor_for,
    run_stress,
)


def test_artifact_path_helper() -> None:
    from conftest import artifact_path

    assert artifact_path("pyproject.toml").exists()
    try:
        artifact_path("artifacts", "does_not_exist_12345.parquet")
        raise AssertionError("should have skipped")
    except BaseException as exc:  # pytest Skipped
        assert type(exc).__name__ == "Skipped"


def test_canonical_money_math() -> None:
    assert abs(bet_pnl(50.0, -110, won=True) - 50.0 * (100.0 / 110.0)) < 1e-9
    assert bet_pnl(50.0, 150, won=True) == 75.0
    assert bet_pnl(50.0, -110, won=False) == -50.0


def test_selector_matches_ledger_on_canonical_taken() -> None:
    df = pl.read_parquet(
        artifact_path("artifacts", "odds_log", "juiced_replay_candidates.parquet")
    ).filter((pl.col("yr") == "2025") & (pl.col("accepted")))
    assert len(df) > 1000
    recomputed = sum(
        bet_pnl(50.0, float(r["price"]), won=bool(r["won"]))
        for r in df.iter_rows(named=True)
    )
    stored = float(df["pnl_flat1u"].sum())
    assert abs(recomputed - stored) < 1e-6


def test_floor_and_concentration_helpers() -> None:
    assert floor_for(2.5, "over", 0.08) == 0.18  # probation bump stands
    assert floor_for(6.5, "over", 0.08) == 0.08
    t = pl.DataFrame(
        {"line": [6.5, 6.5, 4.5], "side": ["over", "over", "under"],
         "pnl": [60.0, 60.0, -20.0]}
    )
    assert cell_concentration(t) == 1.2  # top cell exceeds total (mixed signs)


def test_loosest_config_is_a_superset() -> None:
    df = pl.read_parquet(
        artifact_path("artifacts", "odds_log", "juiced_replay_candidates.parquet")
    ).filter(pl.col("yr") == "2025")
    loose = apply_config(df, 0.08, 99.0, "both", "next")
    tight = apply_config(df, 0.12, 0.20, "lean", "dkfd")
    assert len(loose) >= len(tight)
    assert len(tight) >= 200


def test_stress_battery_structure() -> None:
    df = pl.read_parquet(
        artifact_path("artifacts", "odds_log", "juiced_replay_candidates.parquet")
    ).filter(pl.col("yr") == "2025")
    champ = {"floor": 0.12, "cap": 0.24, "side": "lean", "book": "dkfd"}
    s = run_stress(df, champ, n_boot=20)
    assert s["taken"]["n"] > 200
    assert 0.0 <= s["white_lite"]["p_value"] <= 1.0
    assert s["september"]["n"] > 0
    assert len(s["cell_exclusion"]) > 0 and len(s["month_exclusion"]) > 0
