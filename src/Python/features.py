"""Shared feature-safety rules for pregame projections."""

from __future__ import annotations

from collections.abc import Iterable
import re

import pandas as pd


TARGET = "k_rate"
LABEL_COLUMNS = frozenset({"K", "PA", "Outs", TARGET})
MODEL_METADATA_COLUMNS = frozenset(
    {
        "game_pk",
        "game_date",
        "season",
        "pitcher",
        "batter",
        "player_name",
        "pitcher_name",
        "batter_name",
        "p_throws",
        "stand",
        "home_team",
        "away_team",
        "opp_team",
        "bat_team",
        "is_initial_lineup",
        "opp_lineup_size",
    }
)

# Values observed during the game being projected must never enter the model.
# Lagged versions such as PA_P5 are valid because they are known pregame.
FORBIDDEN_PREGAME_FEATURES = frozenset(
    {
        "PA",
        "K",
        "Outs",
        TARGET,
        "actual_k",
        "actual_outs",
        "actual_pa",
        "actual_tbf",
    }
)

APPROVED_CONTEXT_FEATURES = frozenset(
    {
        "is_home",
        "park_k_factor",
        "opp_lineup_k",
        "opp_lineup_k_vs_hand",
        "opp_lineup_whiff",
        "opp_lineup_chase",
    }
)
_ROLLING_FEATURE_RE = re.compile(r"(_P\d+|_std(?:_vL|_vR|_shrunk)?)$")


def validate_pregame_features(features: Iterable[str]) -> tuple[str, ...]:
    """Validate and normalize a pregame feature list.

    Raises:
        ValueError: If features are duplicated or include same-game outcomes.
    """
    normalized = tuple(features)
    duplicates = sorted(
        feature for feature in set(normalized) if normalized.count(feature) > 1
    )
    forbidden = sorted(set(normalized) & FORBIDDEN_PREGAME_FEATURES)

    errors: list[str] = []
    if duplicates:
        errors.append(f"duplicate features: {duplicates}")
    if forbidden:
        errors.append(f"same-game features: {forbidden}")
    if errors:
        raise ValueError("Invalid pregame feature list (" + "; ".join(errors) + ")")

    return normalized


def model_feature_names(frame: pd.DataFrame) -> tuple[str, ...]:
    """Return approved numeric/bool Level 3 model inputs.

    Unexpected numeric columns fail loudly rather than becoming features
    automatically. This prevents a newly retained same-game aggregate from
    bypassing the explicit label/metadata exclusions.
    """
    excluded = LABEL_COLUMNS | MODEL_METADATA_COLUMNS
    candidates = tuple(
        column
        for column in frame.select_dtypes(include=["number", "bool"]).columns
        if column not in excluded
    )
    unexpected = sorted(
        column
        for column in candidates
        if column not in APPROVED_CONTEXT_FEATURES
        and not _ROLLING_FEATURE_RE.search(column)
    )
    if unexpected:
        raise ValueError(
            "Unexpected numeric columns are not approved pregame features: "
            f"{unexpected}"
        )
    return validate_pregame_features(candidates)
