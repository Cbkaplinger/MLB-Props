"""Shared feature-safety rules for pregame projections."""

from __future__ import annotations

from collections.abc import Iterable


TARGET = "k_rate"

# Values observed during the game being projected must never enter the model.
# Lagged versions such as PA_P5 are valid because they are known pregame.
FORBIDDEN_PREGAME_FEATURES = frozenset(
    {
        "PA",
        "K",
        "actual_k",
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
