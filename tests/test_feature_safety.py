import pandas as pd
import pytest

from mlb_props.features import model_feature_names, validate_pregame_features


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


def test_model_feature_names_excludes_labels_ids_and_strings() -> None:
    frame = pd.DataFrame(
        {
            "game_pk": [1],
            "pitcher": [10],
            "player_name": ["Ace"],
            "K": [8],
            "PA": [24],
            "Outs": [18],
            "k_rate": [1 / 3],
            "k_rate_P5": [0.30],
            "is_home": [True],
        }
    )
    assert model_feature_names(frame) == ("k_rate_P5", "is_home")
