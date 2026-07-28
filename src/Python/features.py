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
        "opp_lineup_swstr",
        "opp_lineup_chase",
        # TBF covariates (experimental for k-rate; allowed when include_experimental).
        "days_rest",
        "days_rest_capped",
        "is_season_debut",
        "rest_is_long_gap",
        "rest_gap_severity",
        "is_career_mlb_debut",
        "bullpen_pitches_L1d",
        "bullpen_pitches_L2d",
        "bullpen_pitches_L3d",
        "bullpen_pitchers_used_L1d",
        "bullpen_pitchers_used_L2d",
        "bullpen_pitchers_used_L3d",
        "bullpen_unique_arms_L1d",
        "bullpen_unique_arms_L2d",
        "bullpen_unique_arms_L3d",
        "bullpen_appearances_L1d",
        "bullpen_appearances_L2d",
        "bullpen_appearances_L3d",
        "bullpen_L_pitches_L1d",
        "bullpen_L_pitches_L2d",
        "bullpen_L_pitches_L3d",
        "bullpen_R_pitches_L1d",
        "bullpen_R_pitches_L2d",
        "bullpen_R_pitches_L3d",
        "bullpen_b2b_arms_L1d",
        "bullpen_b2b_arms_L2d",
        "bullpen_b2b_arms_L3d",
        "bullpen_max_pitches_L1d",
        "bullpen_max_pitches_L2d",
        "bullpen_max_pitches_L3d",
        "bullpen_heavy_outings_L1d",
        "bullpen_heavy_outings_L2d",
        "bullpen_heavy_outings_L3d",
    }
) | frozenset(
    {
        f"opp_lineup_{metric}{suffix}"
        for metric in ("zswing", "swing", "zcontact", "bb")
        for suffix in ("", "_P5", "_P10", "_P20")
    }
)
_PRODUCTION_LINEUP_FEATURES = frozenset(
    {
        "opp_lineup_k",
        "opp_lineup_k_vs_hand",
        "opp_lineup_whiff",
        "opp_lineup_swstr",
        "opp_lineup_chase",
    }
)
_ROLLING_FEATURE_RE = re.compile(r"(_P\d+|_std(?:_vL|_vR|_shrunk)?)$")
_DETERMINISTIC_REDUNDANCY_RE = re.compile(
    r"^(?:[a-z]{2}_)?(?:contact_rate|csw_rate|strike_rate|neutral_rate)(?:_|$)"
)
_EXPERIMENTAL_FEATURE_RE = re.compile(
    r"^(?:"
    r"has_thrown_[a-z]{2}_P2|"
    r"[a-z]{2}_usage_P2|"
    r"[a-z]{2}_rv_shrunk_P\d+|"
    r"(?:bip_rate|babip|first_pitch_strike_rate|ahead_rate|behind_rate|"
    r"two_strike_reach_rate|putaway_rate|arm_angle|siera_mlb|rv_per_100)"
    r"_(?:P\d+|std)|"
    # TBF spine: lagged volume + rest stay out of frozen k-rate until promoted.
    r"(?:PA|Outs|Pitches)_P\d+|"
    r"days_rest(?:_capped)?|is_season_debut|rest_is_long_gap|"
    r"rest_gap_severity|is_career_mlb_debut|"
    r"bullpen_(?:pitches|pitchers_used|unique_arms|appearances|"
    r"L_pitches|R_pitches|b2b_arms|max_pitches|heavy_outings)_L\d+d"
    r")$"
)
_EXPERIMENTAL_LINEUP_DISCIPLINE_RE = re.compile(
    r"^opp_lineup_(?:zswing|swing|zcontact|bb)(?:_P(?:5|10|20))?$"
)
_LINEUP_RESEARCH_FEATURE_RE = re.compile(
    r"^opp_lineup_(?:"
    r"k(?:_vs_hand)?|whiff|swstr|chase|zswing|swing|zcontact|bb|"
    r"babip|hard_hit|barrel|sweet_spot|avg_ev|avg_la|xba|woba|xwoba|"
    r"hr|fb|hr_fb|pull_air|rv_per_pitch"
    r")(?:_P(?:5|10|20))?(?:_order_(?:weighted|sd))?$"
)


def is_deterministically_redundant(feature: str) -> bool:
    """Return whether a feature is an excluded exact algebraic identity.

    Whiff rate is retained instead of contact rate, separate swinging/called
    strike rates replace CSW, ball rate replaces conventional strike rate, and
    neutral count share is the omitted reference for count-state composition.
    """
    return _DETERMINISTIC_REDUNDANCY_RE.match(feature) is not None


def is_experimental_feature(feature: str) -> bool:
    """Return whether a candidate failed or has not cleared promotion gates."""
    if feature in _PRODUCTION_LINEUP_FEATURES:
        return False
    return (
        _EXPERIMENTAL_FEATURE_RE.match(feature) is not None
        or _EXPERIMENTAL_LINEUP_DISCIPLINE_RE.match(feature) is not None
        or _LINEUP_RESEARCH_FEATURE_RE.match(feature) is not None
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
    redundant = sorted(
        feature for feature in normalized if is_deterministically_redundant(feature)
    )

    errors: list[str] = []
    if duplicates:
        errors.append(f"duplicate features: {duplicates}")
    if forbidden:
        errors.append(f"same-game features: {forbidden}")
    if redundant:
        errors.append(f"deterministically redundant features: {redundant}")
    if errors:
        raise ValueError("Invalid pregame feature list (" + "; ".join(errors) + ")")

    return normalized


def model_feature_names(
    frame: pd.DataFrame,
    *,
    include_experimental: bool = False,
) -> tuple[str, ...]:
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
        and not is_deterministically_redundant(column)
        and (include_experimental or not is_experimental_feature(column))
    )
    unexpected = sorted(
        column
        for column in candidates
        if column not in APPROVED_CONTEXT_FEATURES
        and not _ROLLING_FEATURE_RE.search(column)
        and not _LINEUP_RESEARCH_FEATURE_RE.match(column)
    )
    if unexpected:
        raise ValueError(
            "Unexpected numeric columns are not approved pregame features: "
            f"{unexpected}"
        )
    return validate_pregame_features(candidates)
