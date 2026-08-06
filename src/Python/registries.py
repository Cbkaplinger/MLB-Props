"""Explicit feature-set registries for LightGBM production and Ridge VIF research.

Step 7 froze LightGBM production as the Step 4 mean-window thin (drop P10 on
physics/usage/mechanics/FIP). Step 9c amends that thin with a five-stem
last-start ``P1`` swap (``step10_180``).

2026-08-03 promotes four opposing-lineup discipline nominees into
``production`` (184). ``step10_180`` keeps the prior freeze for bake-offs.
``production_plus_discipline`` remains as a backward-compatible alias of
``production``.

``step7_185`` keeps the pre-P1 list. ``pre_freeze_248`` remains the full
safety-gated allow-list. Ridge uses the separate VIF registry.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from Python import config
from Python.features import model_feature_names, validate_pregame_features

FEATURE_SETS = (
    "production",
    "production_plus_discipline",  # alias of production (post 2026-08-03 freeze)
    "step10_180",
    "step7_185",
    "pre_freeze_248",
    "ridge_vif",
)

# Phase-3 / 2026-08-03 LGBM lift nominees (nested both-fold + 2025 confirm).
DISCIPLINE_LIFT_FEATURES = (
    "opp_lineup_zswing_P10",
    "opp_lineup_swing_P10",
    "opp_lineup_zcontact_P20",
    "opp_lineup_bb",
)

# Mean-window families thinned at LightGBM freeze (Step 4): drop P10.
_MEAN_WINDOW_FAMILIES = frozenset(
    {"pitch_physics", "pitch_usage", "mechanics", "fip_xfip"}
)
_P10_RE = re.compile(r"_P10$")

# Step 9c: both-fold P1 winners — replace P3/P5 with P1 for these stems.
_P1_PHYSICS_SWAP_STEMS = frozenset(
    {
        "ff_velo",
        "cu_vaa",
        "cu_usage_vR",
        "fs_usage_vR",
        "sl_vaa",
    }
)
_P1_SWAP_DROP = frozenset(
    {
        f"{stem}_P{window}"
        for stem in _P1_PHYSICS_SWAP_STEMS
        for window in (3, 5)
    }
)
_P1_SWAP_ADD = tuple(f"{stem}_P1" for stem in sorted(_P1_PHYSICS_SWAP_STEMS))

# Ridge VIF proposal amendment (Step 1): drop xFIP when FIP already represents
# the cluster; keep xwOBA_P5 and accept one residual VIF > 10.
_RIDGE_VIF_EXPLICIT_DROPS = frozenset({"xFIP_P5"})

_DICTIONARY_PATH = config.OUTPUT_DIR / "feature_research" / "feature_dictionary.csv"
_VIF_REDUCED_PATH = (
    config.OUTPUT_DIR / "feature_research" / "vif_reduced_features.csv"
)


def _family_map() -> dict[str, str]:
    if not _DICTIONARY_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_DICTIONARY_PATH}. Run feature diagnostics first."
        )
    dictionary = pd.read_csv(_DICTIONARY_PATH)
    return dictionary.set_index("feature")["family"].astype(str).to_dict()


def eligible_baseline_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Full safety-gated allow-list before the Step 7 window thin (248).

    Excludes the Step-11 discipline-lift columns so historical ``pre_freeze_248``
    / ``step7_185`` / ``step10_180`` sizes stay comparable; production re-adds
    them explicitly.
    """
    return tuple(
        feature
        for feature in model_feature_names(frame)
        if feature not in DISCIPLINE_LIFT_FEATURES
    )


def pre_freeze_248_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Alias for the pre-freeze 248-feature LightGBM allow-list."""
    return eligible_baseline_features(frame)


def step7_185_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Pre-Step-9c production: mean-window thin only (drop family P10).

    Explicitly excludes ``*_P1`` columns so Level-2 generation of last-start
    means for research does not inflate this comparison registry.
    """
    families = _family_map()
    selected = [
        feature
        for feature in eligible_baseline_features(frame)
        if not (
            families.get(feature) in _MEAN_WINDOW_FAMILIES
            and _P10_RE.search(feature)
        )
        and not feature.endswith("_P1")
    ]
    return validate_pregame_features(selected)


def _apply_p1_physics_swap(
    features: tuple[str, ...],
    frame: pd.DataFrame,
) -> tuple[str, ...]:
    """Swap five Step-9c stems onto P1; require those P1 columns on the frame."""
    missing = [column for column in _P1_SWAP_ADD if column not in frame.columns]
    if missing:
        raise ValueError(
            "Step 9c production registry requires P1 mean-window columns on the "
            "Level 3 frame (rebuild Level 2 rolling with DEFAULT_MEAN_WINDOWS "
            f"including 1). Missing: {missing}"
        )
    # Drop P3/P5 for swap stems and any stray non-swap P1s.
    selected = [
        feature
        for feature in features
        if feature not in _P1_SWAP_DROP
        and not (
            feature.endswith("_P1") and feature not in _P1_SWAP_ADD
        )
    ]
    selected_set = set(selected)
    for column in _P1_SWAP_ADD:
        if column not in selected_set:
            selected.append(column)
            selected_set.add(column)
    return validate_pregame_features(selected)


def step10_180_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Prior frozen LightGBM spine (Step 7 thin + Step 9c P1 swap; 180)."""
    return _apply_p1_physics_swap(step7_185_features(frame), frame)


def production_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Frozen LightGBM production registry (step10_180 + discipline lift)."""
    core = list(step10_180_features(frame))
    missing = [
        feature for feature in DISCIPLINE_LIFT_FEATURES if feature not in frame.columns
    ]
    if missing:
        raise ValueError(
            "production registry requires opposing-lineup discipline columns "
            f"on the Level 3 frame. Missing: {missing}"
        )
    return validate_pregame_features([*core, *DISCIPLINE_LIFT_FEATURES])


def production_plus_discipline_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Backward-compatible alias of :func:`production_features` (184)."""
    return production_features(frame)


# Backward-compatible alias used in Step 1 docs/scripts.
lightgbm_freeze_proposal_features = production_features


def ridge_vif_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Adopted Ridge research registry: Phase-1 VIF reduction minus xFIP_P5."""
    if not _VIF_REDUCED_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_VIF_REDUCED_PATH}. Run scripts/vif_cluster_reduction.py "
            "against the Phase-1 (248-feature) dictionary artifacts first."
        )
    proposal = pd.read_csv(_VIF_REDUCED_PATH)
    if "feature" not in proposal.columns:
        raise ValueError(f"{_VIF_REDUCED_PATH} must contain a 'feature' column")
    baseline = set(eligible_baseline_features(frame))
    selected = [
        feature
        for feature in proposal["feature"].astype(str).tolist()
        if feature not in _RIDGE_VIF_EXPLICIT_DROPS
    ]
    missing = [feature for feature in selected if feature not in baseline]
    if missing:
        raise ValueError(
            "ridge_vif registry contains features outside the baseline allow-list: "
            f"{missing[:10]}"
        )
    return validate_pregame_features(selected)


def resolve_feature_names(
    frame: pd.DataFrame,
    feature_set: str = "production",
) -> tuple[str, ...]:
    """Resolve a named feature set against the current Level 3 frame."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(
            f"unsupported feature set {feature_set!r}; expected one of {FEATURE_SETS}"
        )
    if feature_set in {"production", "production_plus_discipline"}:
        return production_features(frame)
    if feature_set == "step10_180":
        return step10_180_features(frame)
    if feature_set == "step7_185":
        return step7_185_features(frame)
    if feature_set == "pre_freeze_248":
        return pre_freeze_248_features(frame)
    return ridge_vif_features(frame)


def registry_metadata(feature_set: str, features: tuple[str, ...]) -> dict[str, object]:
    """Small metadata block for trainer reports and registry exports."""
    return {
        "feature_set": feature_set,
        "n_features": len(features),
        "ridge_vif_explicit_drops": sorted(_RIDGE_VIF_EXPLICIT_DROPS),
        "mean_window_families_thinned_at_freeze": sorted(_MEAN_WINDOW_FAMILIES),
        "p1_physics_swap_stems": sorted(_P1_PHYSICS_SWAP_STEMS),
        "discipline_lift_features": list(DISCIPLINE_LIFT_FEATURES),
        "dictionary_path": str(_DICTIONARY_PATH),
        "vif_reduced_path": str(_VIF_REDUCED_PATH),
    }


def write_registry_csv(path: Path, features: tuple[str, ...], **extra: object) -> None:
    """Write a simple feature registry CSV for artifacts / handoff."""
    rows = [{"feature": feature, **extra} for feature in features]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
