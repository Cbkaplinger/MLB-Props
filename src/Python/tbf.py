"""Projected TBF (batters faced) feature sets and safety helpers.

Target is same-game ``PA`` as the historical TBF oracle. Predictors are
pregame only: lagged volume, rest, optional light context, and optional
bullpen lookbacks. Same-game ``PA`` / ``Outs`` / ``Pitches`` never enter the
feature list.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from Python.bullpen import bullpen_lookback_column_names
from Python.features import FORBIDDEN_PREGAME_FEATURES, validate_pregame_features

TBF_TARGET = "PA"
# Default / frozen spine uses the thin bullpen block (best chrono MAE/RMSE/R²).
TBF_DEFAULT_FEATURE_SET = "workload_context_bullpen"
TBF_FEATURE_SETS = (
    "workload",
    "workload_context",
    "workload_context_bullpen",
    "workload_context_bullpen_rich",
)

_WORKLOAD_VOLUME = tuple(
    f"{stat}_P{window}"
    for stat in ("PA", "Outs", "Pitches")
    for window in (5, 10, 20)
)
_REST = (
    "days_rest_capped",
    "is_season_debut",
    "rest_is_long_gap",
    "rest_gap_severity",
    "is_career_mlb_debut",
)
# Prefer capped rest; raw days_rest is available for diagnostics but redundant
# with the cap + long-gap / severity flags for the spine.
_CONTEXT = (
    "is_home",
    "park_k_factor",
    "opp_lineup_k",
    "opp_lineup_k_vs_hand",
)
# Thin pen won the bake-off; rich block kept for ablation / live UI context.
_BULLPEN_THIN = (
    "bullpen_pitches_L1d",
    "bullpen_pitches_L2d",
    "bullpen_pitches_L3d",
    "bullpen_pitchers_used_L1d",
    "bullpen_pitchers_used_L2d",
    "bullpen_pitchers_used_L3d",
)
_BULLPEN_RICH = bullpen_lookback_column_names()

_FEATURE_SET_MEMBERS: dict[str, tuple[str, ...]] = {
    "workload": (*_REST, *_WORKLOAD_VOLUME),
    "workload_context": (*_REST, *_WORKLOAD_VOLUME, *_CONTEXT),
    "workload_context_bullpen": (*_REST, *_WORKLOAD_VOLUME, *_CONTEXT, *_BULLPEN_THIN),
    "workload_context_bullpen_rich": (
        *_REST,
        *_WORKLOAD_VOLUME,
        *_CONTEXT,
        *_BULLPEN_RICH,
    ),
}


def tbf_feature_names(
    frame: pd.DataFrame,
    feature_set: str = TBF_DEFAULT_FEATURE_SET,
) -> tuple[str, ...]:
    """Return the TBF feature list present on ``frame`` for ``feature_set``."""
    if feature_set not in TBF_FEATURE_SETS:
        raise ValueError(
            f"unsupported TBF feature set {feature_set!r}; "
            f"expected one of {TBF_FEATURE_SETS}"
        )
    wanted = _FEATURE_SET_MEMBERS[feature_set]
    missing = [name for name in wanted if name not in frame.columns]
    if missing:
        raise ValueError(
            "TBF training frame is missing required columns: "
            f"{missing[:10]}. Rebuild Level 1–3 after Phase A.1 / C."
        )
    forbidden = sorted(set(wanted) & FORBIDDEN_PREGAME_FEATURES)
    if forbidden:
        raise ValueError(f"TBF feature set includes forbidden labels: {forbidden}")
    return validate_pregame_features(wanted)


def assert_tbf_label_not_in_features(
    features: Iterable[str],
    *,
    target: str = TBF_TARGET,
) -> None:
    """Fail loudly if the TBF label leaked into predictors."""
    features = list(features)
    if target in features:
        raise RuntimeError(
            f"{target} leaked into TBF model features; refuse to train. "
            f"{target} is the label/oracle only."
        )
    leaked = sorted(set(features) & FORBIDDEN_PREGAME_FEATURES)
    if leaked:
        raise RuntimeError(
            f"forbidden same-game columns in TBF features: {leaked}"
        )
