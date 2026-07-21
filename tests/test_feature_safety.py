import json
from pathlib import Path

import pytest

from mlb_props.config import PROJECT_ROOT
from mlb_props.features import validate_pregame_features


MODEL_NOTEBOOKS = (
    PROJECT_ROOT / "Models" / "Strikeout-Model" / "LightGBM.ipynb",
    PROJECT_ROOT / "Models" / "Strikeout-Model" / "Naive-Linear-Model.ipynb",
)


def _notebook_source(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", [])) for cell in notebook.get("cells", [])
    )


def test_valid_pregame_features_are_preserved() -> None:
    features = ("k_rate_P5", "PA_P5", "ff_velo_P5")
    assert validate_pregame_features(features) == features


@pytest.mark.parametrize("feature", ["PA", "K", "actual_pa", "actual_tbf"])
def test_same_game_features_are_rejected(feature: str) -> None:
    with pytest.raises(ValueError, match="same-game features"):
        validate_pregame_features(["k_rate_P5", feature])


def test_duplicate_features_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate features"):
        validate_pregame_features(["k_rate_P5", "k_rate_P5"])


@pytest.mark.parametrize("notebook_path", MODEL_NOTEBOOKS)
def test_model_notebooks_do_not_add_same_game_pa(notebook_path: Path) -> None:
    source = _notebook_source(notebook_path)
    assert "context_features = ['PA']" not in source
    assert 'context_features = ["PA"]' not in source
