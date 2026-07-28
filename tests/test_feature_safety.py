import pandas as pd
import pytest

from Python.features import model_feature_names, validate_pregame_features


def test_valid_pregame_features_are_preserved() -> None:
    features = ("k_rate_P5", "PA_P5", "ff_velo_P5")
    assert validate_pregame_features(features) == features


@pytest.mark.parametrize(
    "feature",
    ["PA", "K", "Outs", "k_rate", "actual_pa", "actual_tbf"],
)
def test_same_game_features_are_rejected(feature: str) -> None:
    with pytest.raises(ValueError, match="same-game features"):
        validate_pregame_features(["k_rate_P5", feature])


def test_duplicate_features_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate features"):
        validate_pregame_features(["k_rate_P5", "k_rate_P5"])


@pytest.mark.parametrize(
    "feature",
    [
        "contact_rate_P5",
        "csw_rate_std",
        "ff_contact_rate_P3",
        "sl_csw_rate_P10",
        "strike_rate_P5",
        "neutral_rate_std",
    ],
)
def test_deterministically_redundant_features_are_rejected(feature: str) -> None:
    with pytest.raises(ValueError, match="deterministically redundant features"):
        validate_pregame_features(["whiff_rate_P5", feature])


def test_model_feature_names_excludes_labels_ids_and_strings() -> None:
    frame = pd.DataFrame(
        {
            "game_pk": [1],
            "pitcher": [10],
            "player_name": ["Ace"],
            "pitcher_name": ["Ace Pitcher"],
            "batter_name": ["A Hitter"],
            "K": [8],
            "PA": [24],
            "Outs": [18],
            "k_rate": [1 / 3],
            "k_rate_P5": [0.30],
            "is_home": [True],
        }
    )
    assert model_feature_names(frame) == ("k_rate_P5", "is_home")


def test_model_feature_names_excludes_deterministically_redundant_columns() -> None:
    frame = pd.DataFrame(
        {
            "k_rate": [0.25],
            "whiff_rate_P5": [0.30],
            "contact_rate_P5": [0.70],
            "swstr_rate_P5": [0.12],
            "cs_rate_P5": [0.08],
            "csw_rate_P5": [0.20],
            "ff_contact_rate_P3": [0.65],
            "ff_csw_rate_P3": [0.21],
        }
    )
    assert model_feature_names(frame) == (
        "whiff_rate_P5",
        "swstr_rate_P5",
        "cs_rate_P5",
    )


def test_experimental_candidates_require_explicit_research_opt_in() -> None:
    frame = pd.DataFrame(
        {
            "k_rate": [0.25],
            "whiff_rate_P5": [0.30],
            "has_thrown_ff_P2": [1],
            "ff_usage_P2": [0.55],
            "arm_angle_P3": [45.0],
            "putaway_rate_P10": [0.18],
            "opp_lineup_zswing_P10": [0.66],
            "opp_lineup_bb": [0.08],
            "opp_lineup_xwoba_P20": [0.35],
            "opp_lineup_k_order_weighted": [0.24],
            "opp_lineup_hard_hit_order_sd": [0.08],
            "PA_P5": [22.0],
            "days_rest_capped": [4],
            "is_season_debut": [0],
        }
    )
    assert model_feature_names(frame) == ("whiff_rate_P5",)
    assert model_feature_names(frame, include_experimental=True) == (
        "whiff_rate_P5",
        "has_thrown_ff_P2",
        "ff_usage_P2",
        "arm_angle_P3",
        "putaway_rate_P10",
        "opp_lineup_zswing_P10",
        "opp_lineup_bb",
        "opp_lineup_xwoba_P20",
        "opp_lineup_k_order_weighted",
        "opp_lineup_hard_hit_order_sd",
        "PA_P5",
        "days_rest_capped",
        "is_season_debut",
    )


def test_model_feature_names_rejects_unapproved_numeric_columns() -> None:
    frame = pd.DataFrame(
        {
            "game_pk": [1],
            "k_rate": [0.25],
            "k_rate_P5": [0.22],
            "Whiffs": [12],
        }
    )
    with pytest.raises(ValueError, match="Unexpected numeric columns"):
        model_feature_names(frame)
