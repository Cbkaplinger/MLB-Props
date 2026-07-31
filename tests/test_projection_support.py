"""Tests for out-of-support projection gates."""

from __future__ import annotations

from Python.projection_support import (
    MIN_STARTER_EXPECTED_K,
    MIN_STARTER_PROJECTED_TBF,
    projection_oos_reason,
)


def test_irvin_style_low_tbf_is_oos() -> None:
    # Jake Irvin 2026-07-30: TBF~4.2, xK~0.85, rest=68 → fake 55% under edge
    assert (
        projection_oos_reason(projected_tbf=4.17, expected_K=0.85, days_rest=68.0)
        == f"projected_tbf<{MIN_STARTER_PROJECTED_TBF:g}"
    )


def test_normal_starter_in_support() -> None:
    assert (
        projection_oos_reason(projected_tbf=22.0, expected_K=5.2, days_rest=5.0)
        is None
    )


def test_extreme_rest_oos() -> None:
    assert projection_oos_reason(projected_tbf=22.0, expected_K=5.0, days_rest=120) is not None


def test_min_expected_k_oos() -> None:
    reason = projection_oos_reason(
        projected_tbf=MIN_STARTER_PROJECTED_TBF + 1,
        expected_K=MIN_STARTER_EXPECTED_K - 0.1,
        days_rest=5,
    )
    assert reason is not None and reason.startswith("expected_K")


def test_abbreviated_outing_opener_and_injury() -> None:
    from Python.projection_support import abbreviated_outing_reason, mark_abbreviated_outing
    import polars as pl

    assert abbreviated_outing_reason(actual_PA=3) == "actual_PA<9"
    assert abbreviated_outing_reason(actual_PA=9) is None
    assert abbreviated_outing_reason(actual_PA=None) is None

    df = pl.DataFrame(
        {
            "player_name": ["Opener", "Starter", "Pending"],
            "actual_PA": [4.0, 22.0, None],
        }
    )
    out = mark_abbreviated_outing(df)
    assert out.filter(pl.col("player_name") == "Opener")["is_abbreviated_outing"][0] is True
    assert out.filter(pl.col("player_name") == "Starter")["is_abbreviated_outing"][0] is False
    assert out.filter(pl.col("player_name") == "Pending")["is_abbreviated_outing"][0] is False
