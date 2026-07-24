from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

reduction = importlib.import_module("vif_cluster_reduction")


def _crossings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "population": "pitcher",
                "stat": "ball_rate",
                "threshold": 0.5,
                "typical_starts_at_median_crossing": 3.33,
                "reliably_estimable": True,
            },
            {
                "population": "pitcher",
                "stat": "hr_fb",
                "threshold": 0.5,
                "typical_starts_at_median_crossing": float("nan"),
                "reliably_estimable": False,
            },
        ]
    )


def test_reliability_precedes_missingness() -> None:
    cluster = pd.DataFrame(
        {
            "feature": ["ball_rate_P5", "ball_rate_P20"],
            "missing_pct": [50.0, 0.0],
        }
    )
    choice = reduction.choose_representative(cluster, _crossings())
    assert choice.feature == "ball_rate_P5"
    assert choice.tie_breaker == "a_reliability_positive"


def test_negative_reliability_rejects_unstable_family() -> None:
    cluster = pd.DataFrame(
        {
            "feature": ["hr_rate_P5", "FIP_P5"],
            "missing_pct": [0.0, 0.0],
        }
    )
    choice = reduction.choose_representative(cluster, _crossings())
    assert choice.feature == "FIP_P5"
    assert choice.tie_breaker == "a_reliability_negative_related"


def test_missingness_then_simplicity_break_ties() -> None:
    crossings = _crossings().iloc[0:0]
    missingness_cluster = pd.DataFrame(
        {
            "feature": ["ff_velo_P3", "ff_velo_P10"],
            "missing_pct": [20.0, 10.0],
        }
    )
    assert (
        reduction.choose_representative(missingness_cluster, crossings).feature
        == "ff_velo_P10"
    )

    tied_cluster = pd.DataFrame(
        {
            "feature": ["xFIP_P5", "xFIP_P10"],
            "missing_pct": [10.0, 10.0],
        }
    )
    choice = reduction.choose_representative(tied_cluster, crossings)
    assert choice.feature == "xFIP_P5"
    assert choice.tie_breaker == "c_simplicity"
