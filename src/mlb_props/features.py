"""Shared feature-safety rules for pregame projections."""

from __future__ import annotations

from collections.abc import Iterable

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
        "p_throws",
        "stand",
        "home_team",
        "away_team",
        "opp_team",
        "bat_team",
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
    """Return numeric/bool Level 3 columns safe to use as model inputs."""
    excluded = LABEL_COLUMNS | MODEL_METADATA_COLUMNS
    candidates = (
        column
        for column in frame.select_dtypes(include=["number", "bool"]).columns
        if column not in excluded
    )
    return validate_pregame_features(candidates)
