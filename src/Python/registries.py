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

import json
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
    "research_csw_finish_all",
    "research_csw_finish_p5",
    "research_csw_finish_p10",
    "research_csw_finish_p20",
    "research_xwoba_luck_all",
    "production_plus_xwoba_luck",
    "production_plus_xwoba_luck_air_profile_p5",
    "production_sparse40",
    "production_sparse72",
    "production_sparse72_monotone",
    "production_oof72",
    "production_oof72_monotone",
    "production_stable12",
    "production_refine_keep12",
    "production_refine_balanced30",
    "production_final42_fast",
    "production_final58_consensus",
    "production_final58_refined",
    "production_final58_greedy_refined",
    "production_final58_combo_refined",
    "production_frontier60_aug20",
    "production_frontier42_aug20",
    "research_air_profile_all",
    "research_air_profile_p5",
    "research_air_profile_p10",
    "research_air_profile_p20",
    "research_interactions_all",
    "research_interactions_p5",
    "research_interactions_p10",
    "research_interactions_p20",
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
_CSW_FINISH_STEMS = (
    "two_strike_csw_rate",
    "csw_two_strike_gap",
    "csw_putaway_gap",
    "k_minus_swstr_x2",
)
_XWOBA_LUCK_STEM = "xwoba_minus_woba"
_AIR_PROFILE_STEMS = (
    "pull_air_allowed_rate",
    "oppo_air_allowed_rate",
    "center_air_allowed_rate",
    "iffb_rate",
)
_INTERACTION_STEMS = (
    "two_strike_csw_rate",
    "csw_two_strike_gap",
    "csw_putaway_gap",
    "two_strike_csw_minus_first_pitch",
    "putaway_over_two_strike_reach",
    "k_minus_swstr_x2",
    "xwoba_minus_woba",
    "xba_minus_hit_rate",
    "xba_minus_babip",
    "zone_swstr_interaction",
    "chase_whiff_interaction",
    "hr_fb_minus_luck_proxy",
    "hit_rate",
    "hr_fb_rate",
)

_DICTIONARY_PATH = config.OUTPUT_DIR / "feature_research" / "feature_dictionary.csv"
_VIF_REDUCED_PATH = (
    config.OUTPUT_DIR / "feature_research" / "vif_reduced_features.csv"
)
_SPARSE40_ATTRIBUTION_PATH = (
    config.OUTPUT_DIR / "model_quality" / "deep_feature_review" / "legacy_feature_attribution.csv"
)
_SPARSE40_STABILITY_SUMMARY_PATH = (
    config.OUTPUT_DIR / "model_quality" / "deep_feature_review" / "production_sparse40_stability_summary.json"
)
_OOF72_RANKING_PATH = (
    config.OUTPUT_DIR / "model_quality" / "anti_leak_final_suite" / "oof_permutation_ranking.csv"
)
_REFINE_TOP220_DIR = (
    config.OUTPUT_DIR / "model_quality" / "full_feature_importance_screen" / "refine_top220"
)
_REFINE_KEEP12_PATH = _REFINE_TOP220_DIR / "recommended_top72_features.csv"
_REFINE_BALANCED30_PATH = _REFINE_TOP220_DIR / "recommended_balanced_features.csv"
_FINAL42_FAST_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final_feature_dataset_search"
    / "fast_targeted"
    / "best_features.csv"
)
_FINAL58_CONSENSUS_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final_feature_dataset_search"
    / "consensus_v1_phase2_deep"
    / "best_features.csv"
)
_FINAL58_REFINED_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final58_refined_registry"
    / "best_features.csv"
)
_FINAL58_GREEDY_REFINED_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final58_greedy_refined_registry"
    / "best_features.csv"
)
_FINAL58_COMBO_REFINED_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final58_combo_refined_registry"
    / "best_features.csv"
)
_FRONTIER60_AUG20_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final_feature_dataset_search"
    / "frontier_focus_aug20"
    / "best_features.csv"
)
_FRONTIER42_AUG20_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "final_feature_dataset_search"
    / "frontier_aug20"
    / "best_features.csv"
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


def _research_stem_features(
    frame: pd.DataFrame,
    *,
    stems: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> tuple[str, ...]:
    base = list(production_features(frame))
    base_set = set(base)
    extras: list[str] = []
    for stem in stems:
        for suffix in suffixes:
            col = f"{stem}_{suffix}"
            if col in frame.columns and col not in base_set:
                extras.append(col)
                base_set.add(col)
    return validate_pregame_features([*base, *extras])


def research_csw_finish_all_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_CSW_FINISH_STEMS,
        suffixes=("P5", "P10", "P20", "std"),
    )


def research_csw_finish_p5_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_CSW_FINISH_STEMS,
        suffixes=("P5",),
    )


def research_csw_finish_p10_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_CSW_FINISH_STEMS,
        suffixes=("P10",),
    )


def research_csw_finish_p20_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_CSW_FINISH_STEMS,
        suffixes=("P20",),
    )


def research_xwoba_luck_all_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=(_XWOBA_LUCK_STEM,),
        suffixes=("P5", "P10", "P20", "std"),
    )


def production_plus_xwoba_luck_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Production candidate: add xwOBA-luck residual windows to production."""
    return _research_stem_features(
        frame,
        stems=(_XWOBA_LUCK_STEM,),
        suffixes=("P5", "P10", "P20", "std"),
    )


def production_plus_xwoba_luck_air_profile_p5_features(
    frame: pd.DataFrame,
) -> tuple[str, ...]:
    """Production candidate: production + xwOBA luck + air profile P5 only."""
    return _research_stem_features(
        frame,
        stems=(_XWOBA_LUCK_STEM, *_AIR_PROFILE_STEMS),
        suffixes=("P5",),
    )


def production_sparse40_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Sparse production candidate from legacy production SHAP ranking (top-40)."""
    if not _SPARSE40_ATTRIBUTION_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_SPARSE40_ATTRIBUTION_PATH}. Run deep_feature_review first."
        )
    ranked = pd.read_csv(_SPARSE40_ATTRIBUTION_PATH)
    if "feature" not in ranked.columns:
        raise ValueError(f"{_SPARSE40_ATTRIBUTION_PATH} must contain 'feature'")
    prod = set(production_features(frame))
    selected: list[str] = []
    for feature in ranked["feature"].astype(str).tolist():
        if feature in prod and feature not in selected:
            selected.append(feature)
        if len(selected) >= 40:
            break
    if len(selected) < 40:
        raise ValueError(
            f"Expected at least 40 production-ranked features, got {len(selected)}"
        )
    return validate_pregame_features(selected)


def production_sparse72_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Sparse production candidate from legacy production SHAP ranking (top-72)."""
    if not _SPARSE40_ATTRIBUTION_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_SPARSE40_ATTRIBUTION_PATH}. Run deep_feature_review first."
        )
    ranked = pd.read_csv(_SPARSE40_ATTRIBUTION_PATH)
    if "feature" not in ranked.columns:
        raise ValueError(f"{_SPARSE40_ATTRIBUTION_PATH} must contain 'feature'")
    prod = set(production_features(frame))
    selected: list[str] = []
    for feature in ranked["feature"].astype(str).tolist():
        if feature in prod and feature not in selected:
            selected.append(feature)
        if len(selected) >= 72:
            break
    if len(selected) < 72:
        raise ValueError(
            f"Expected at least 72 production-ranked features, got {len(selected)}"
        )
    return validate_pregame_features(selected)


def production_oof72_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Sparse production candidate from nested inner OOF permutation ranking (top-72)."""
    if not _OOF72_RANKING_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_OOF72_RANKING_PATH}. Run anti_leak_final_suite first."
        )
    ranked = pd.read_csv(_OOF72_RANKING_PATH)
    if "feature" not in ranked.columns:
        raise ValueError(f"{_OOF72_RANKING_PATH} must contain 'feature'")
    prod = set(production_features(frame))
    selected: list[str] = []
    for feature in ranked["feature"].astype(str).tolist():
        if feature in prod and feature not in selected:
            selected.append(feature)
        if len(selected) >= 72:
            break
    if len(selected) < 72:
        raise ValueError(
            f"Expected at least 72 production-ranked features, got {len(selected)}"
        )
    return validate_pregame_features(selected)


def production_stable12_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Stable-core candidate from sparse40 permutation stability filter."""
    if not _SPARSE40_STABILITY_SUMMARY_PATH.exists():
        raise FileNotFoundError(
            "Missing sparse40 stability summary. Run sparse40_stability_filter first: "
            f"{_SPARSE40_STABILITY_SUMMARY_PATH}"
        )
    payload = json.loads(_SPARSE40_STABILITY_SUMMARY_PATH.read_text(encoding="utf-8"))
    stable = payload.get("stable_features", [])
    if not isinstance(stable, list):
        raise ValueError(
            f"{_SPARSE40_STABILITY_SUMMARY_PATH} must contain list field 'stable_features'"
        )
    selected = [str(feature) for feature in stable if str(feature) in frame.columns]
    if len(selected) < 8:
        raise ValueError(
            "production_stable12 expected at least 8 stable features present on frame; "
            f"found {len(selected)}"
        )
    return validate_pregame_features(selected)


def _feature_list_from_csv(path: Path, frame: pd.DataFrame, *, label: str) -> tuple[str, ...]:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run refinement screening first for {label}.")
    table = pd.read_csv(path)
    if "feature" not in table.columns:
        raise ValueError(f"{path} must contain 'feature'")
    selected = [str(f) for f in table["feature"].tolist() if str(f) in frame.columns]
    if not selected:
        raise ValueError(f"{label} resolved zero in-frame features from {path}")
    return validate_pregame_features(selected)


def production_refine_keep12_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Strict shortlist from refine_top220 keep criteria."""
    return _feature_list_from_csv(
        _REFINE_KEEP12_PATH,
        frame,
        label="production_refine_keep12",
    )


def production_refine_balanced30_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Balanced shortlist from refine_top220 keep criteria."""
    return _feature_list_from_csv(
        _REFINE_BALANCED30_PATH,
        frame,
        label="production_refine_balanced30",
    )


def production_final42_fast_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Best MAE candidate from fast targeted LGBM-only feature dataset search."""
    return _feature_list_from_csv(
        _FINAL42_FAST_PATH,
        frame,
        label="production_final42_fast",
    )


def production_final58_consensus_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Best expected-K MAE feature set from merged-pool consensus search."""
    return _feature_list_from_csv(
        _FINAL58_CONSENSUS_PATH,
        frame,
        label="production_final58_consensus",
    )


def production_final58_refined_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Refined final58 with targeted rolling-window swap improvements."""
    return _feature_list_from_csv(
        _FINAL58_REFINED_PATH,
        frame,
        label="production_final58_refined",
    )


def production_final58_greedy_refined_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Greedy-refined final58 using one-swap-at-a-time walk-forward gains."""
    return _feature_list_from_csv(
        _FINAL58_GREEDY_REFINED_PATH,
        frame,
        label="production_final58_greedy_refined",
    )


def production_final58_combo_refined_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Combo-refined final58 from constrained 1-3 swap neighborhood search."""
    return _feature_list_from_csv(
        _FINAL58_COMBO_REFINED_PATH,
        frame,
        label="production_final58_combo_refined",
    )


def production_frontier60_aug20_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Frontier-selected best set from focused size/window search (Aug 20)."""
    return _feature_list_from_csv(
        _FRONTIER60_AUG20_PATH,
        frame,
        label="production_frontier60_aug20",
    )


def production_frontier42_aug20_features(frame: pd.DataFrame) -> tuple[str, ...]:
    """Frontier winner from broad size/window search (Aug 20)."""
    return _feature_list_from_csv(
        _FRONTIER42_AUG20_PATH,
        frame,
        label="production_frontier42_aug20",
    )


def research_air_profile_all_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_AIR_PROFILE_STEMS,
        suffixes=("P5", "P10", "P20", "std"),
    )


def research_air_profile_p5_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_AIR_PROFILE_STEMS,
        suffixes=("P5",),
    )


def research_air_profile_p10_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_AIR_PROFILE_STEMS,
        suffixes=("P10",),
    )


def research_air_profile_p20_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_AIR_PROFILE_STEMS,
        suffixes=("P20",),
    )


def research_interactions_all_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_INTERACTION_STEMS,
        suffixes=("P5", "P10", "P20", "std"),
    )


def research_interactions_p5_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_INTERACTION_STEMS,
        suffixes=("P5",),
    )


def research_interactions_p10_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_INTERACTION_STEMS,
        suffixes=("P10",),
    )


def research_interactions_p20_features(frame: pd.DataFrame) -> tuple[str, ...]:
    return _research_stem_features(
        frame,
        stems=_INTERACTION_STEMS,
        suffixes=("P20",),
    )


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
    if feature_set == "ridge_vif":
        return ridge_vif_features(frame)
    if feature_set == "research_csw_finish_all":
        return research_csw_finish_all_features(frame)
    if feature_set == "research_csw_finish_p5":
        return research_csw_finish_p5_features(frame)
    if feature_set == "research_csw_finish_p10":
        return research_csw_finish_p10_features(frame)
    if feature_set == "research_csw_finish_p20":
        return research_csw_finish_p20_features(frame)
    if feature_set == "research_xwoba_luck_all":
        return research_xwoba_luck_all_features(frame)
    if feature_set == "production_plus_xwoba_luck":
        return production_plus_xwoba_luck_features(frame)
    if feature_set == "production_plus_xwoba_luck_air_profile_p5":
        return production_plus_xwoba_luck_air_profile_p5_features(frame)
    if feature_set == "production_sparse40":
        return production_sparse40_features(frame)
    if feature_set in {"production_sparse72", "production_sparse72_monotone"}:
        return production_sparse72_features(frame)
    if feature_set in {"production_oof72", "production_oof72_monotone"}:
        return production_oof72_features(frame)
    if feature_set == "production_stable12":
        return production_stable12_features(frame)
    if feature_set == "production_refine_keep12":
        return production_refine_keep12_features(frame)
    if feature_set == "production_refine_balanced30":
        return production_refine_balanced30_features(frame)
    if feature_set == "production_final42_fast":
        return production_final42_fast_features(frame)
    if feature_set == "production_final58_consensus":
        return production_final58_consensus_features(frame)
    if feature_set == "production_final58_refined":
        return production_final58_refined_features(frame)
    if feature_set == "production_final58_greedy_refined":
        return production_final58_greedy_refined_features(frame)
    if feature_set == "production_final58_combo_refined":
        return production_final58_combo_refined_features(frame)
    if feature_set == "production_frontier60_aug20":
        return production_frontier60_aug20_features(frame)
    if feature_set == "production_frontier42_aug20":
        return production_frontier42_aug20_features(frame)
    if feature_set == "research_air_profile_all":
        return research_air_profile_all_features(frame)
    if feature_set == "research_air_profile_p5":
        return research_air_profile_p5_features(frame)
    if feature_set == "research_air_profile_p10":
        return research_air_profile_p10_features(frame)
    if feature_set == "research_air_profile_p20":
        return research_air_profile_p20_features(frame)
    if feature_set == "research_interactions_all":
        return research_interactions_all_features(frame)
    if feature_set == "research_interactions_p5":
        return research_interactions_p5_features(frame)
    if feature_set == "research_interactions_p10":
        return research_interactions_p10_features(frame)
    return research_interactions_p20_features(frame)


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
