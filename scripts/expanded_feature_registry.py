"""Build the versioned registry for the expanded pitcher-feature research."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from Python import config
from Python.features import is_experimental_feature, model_feature_names


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "expanded"
ROLLING_SUFFIX = re.compile(r"_(P\d+|std)$")

DEFINITIONS: dict[str, tuple[str, str, str, str]] = {
    "bip_rate": ("batted-ball", "balls in play per pitch", "BIP", "Pitches"),
    "babip": (
        "batted-ball",
        "hits excluding HR per standard BABIP opportunity",
        "BABIP_num",
        "BABIP_den",
    ),
    "first_pitch_strike_rate": (
        "count-state",
        "first pitches classified S or X per first pitch",
        "FirstPitchStrikes",
        "FirstPitches",
    ),
    "ahead_rate": (
        "count-state",
        "pitches entered with strikes greater than balls",
        "AheadPitches",
        "Pitches",
    ),
    "behind_rate": (
        "count-state",
        "pitches entered with balls greater than strikes",
        "BehindPitches",
        "Pitches",
    ),
    "two_strike_reach_rate": (
        "count-state",
        "plate appearances reaching a pre-pitch two-strike count",
        "TwoStrikePA",
        "PA",
    ),
    "putaway_rate": (
        "count-state",
        "strikeouts on two-strike pitches per two-strike pitch",
        "PutAwayK",
        "TwoStrikePitches",
    ),
    "arm_angle": (
        "mechanics",
        "pitch-weighted Statcast arm angle in degrees",
        "arm_angle_num",
        "arm_angle_den",
    ),
    "siera_mlb": (
        "run-estimator",
        "fixed published MLB-glossary SIERA from aggregate component counts",
        "K,BB,GB,OFB,PU",
        "PA",
    ),
    "rv_per_100": (
        "run-value",
        "negative batter run-expectancy change per 100 pitches",
        "RV_num",
        "RV_den",
    ),
}
LINEUP_DISCIPLINE_DEFINITIONS = {
    "zswing": "opposing-lineup mean batter Z-Swing%",
    "swing": "opposing-lineup mean batter Swing%",
    "zcontact": "opposing-lineup mean batter Z-Contact%",
    "bb": "opposing-lineup mean batter BB%",
}
LINEUP_METRIC_DEFINITIONS = {
    "k": "opposing-lineup batter K%",
    "k_vs_hand": "opposing-lineup batter K% versus starter hand",
    "whiff": "opposing-lineup batter Whiff%",
    "swstr": "opposing-lineup batter SwStr%",
    "chase": "opposing-lineup batter chase%",
    **LINEUP_DISCIPLINE_DEFINITIONS,
    "babip": "opposing-lineup batter BABIP",
    "hard_hit": "opposing-lineup batter hard-hit%",
    "barrel": "opposing-lineup batter barrel%",
    "sweet_spot": "opposing-lineup batter sweet-spot%",
    "avg_ev": "opposing-lineup batter average exit velocity",
    "avg_la": "opposing-lineup batter average launch angle",
    "xba": "opposing-lineup batter xBA",
    "woba": "opposing-lineup batter wOBA",
    "xwoba": "opposing-lineup batter xwOBA",
    "hr": "opposing-lineup batter HR%",
    "fb": "opposing-lineup batter FB%",
    "hr_fb": "opposing-lineup batter HR/FB",
    "pull_air": "opposing-lineup batter pulled-air balls per BIP",
    "rv_per_pitch": "opposing-lineup batter run value per pitch",
}


def _describe(feature: str) -> dict[str, object]:
    base = ROLLING_SUFFIX.sub("", feature)
    window_match = re.search(r"_P(\d+)$", feature)
    window = f"P{window_match.group(1)}" if window_match else (
        "season-to-date" if feature.endswith("_std") else ""
    )
    lineup = re.fullmatch(
        r"opp_lineup_("
        + "|".join(
            sorted(LINEUP_METRIC_DEFINITIONS, key=len, reverse=True)
        )
        + r")(?:_(P\d+))?(?:_order_(weighted|sd))?",
        feature,
    )
    if lineup:
        metric, candidate_window, aggregation = lineup.groups()
        family = (
            "batter-discipline-lineup"
            if metric in LINEUP_DISCIPLINE_DEFINITIONS
            else "batter-quality-lineup"
            if metric not in {"k", "k_vs_hand", "whiff", "swstr", "chase"}
            else "lineup"
        )
        aggregation_label = {
            None: "flat mean",
            "weighted": "batting-order opportunity weighted mean",
            "sd": "batting-order opportunity weighted standard deviation",
        }[aggregation]
        return {
            "family": family,
            "definition": (
                f"{LINEUP_METRIC_DEFINITIONS[metric]}; {aggregation_label}"
            ),
            "numerator": "",
            "denominator": "nine opposing batters",
            "candidate_window": candidate_window or "season-to-date",
        }
    if base.startswith("has_thrown_"):
        pitch = base.removeprefix("has_thrown_")
        return {
            "family": "p2-arsenal",
            "definition": f"threw {pitch.upper()} in either prior two starts",
            "numerator": f"max(throws_{pitch})",
            "denominator": "",
            "candidate_window": "P2",
        }
    usage = re.fullmatch(r"([a-z]{2})_usage", base)
    if usage and feature.endswith("_P2"):
        pitch = usage.group(1)
        return {
            "family": "p2-arsenal",
            "definition": f"{pitch.upper()} pitches per all pitches in prior two starts",
            "numerator": f"{pitch}_pitches",
            "denominator": "Pitches",
            "candidate_window": "P2",
        }
    for name, (family, definition, numerator, denominator) in DEFINITIONS.items():
        if base == name:
            return {
                "family": family,
                "definition": definition,
                "numerator": numerator,
                "denominator": denominator,
                "candidate_window": window,
            }
    return {
        "family": "existing",
        "definition": "existing registered pregame feature",
        "numerator": "",
        "denominator": "",
        "candidate_window": window,
    }


def build_registry() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame = frame.loc[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
    features = model_feature_names(frame, include_experimental=True)
    rows: list[dict[str, object]] = []
    for feature in features:
        description = _describe(feature)
        is_expanded = is_experimental_feature(feature)
        is_lineup_discipline = description["family"] == "batter-discipline-lineup"
        is_lineup = description["family"] in {
            "lineup",
            "batter-discipline-lineup",
            "batter-quality-lineup",
        }
        rows.append(
            {
                "feature": feature,
                **description,
                "source": (
                    "src/Python/batter_rolling.py;"
                    "src/Python/pipeline/training.py"
                    if is_lineup
                    else "src/Python/pitcher_features.py;"
                    "src/Python/pitcher_rolling.py"
                ),
                "missing_pct": float(frame[feature].isna().mean() * 100.0),
                "deterministic_status": "eligible",
                "eligibility": (
                    "research_only" if is_expanded else "production_baseline"
                ),
                "decision": (
                    "hold"
                    if is_lineup and is_expanded
                    else "drop"
                    if is_expanded
                    else "keep"
                ),
                "reason": (
                    "stabilization-nominated family improved both LightGBM outer "
                    "folds but Ridge support was mixed; retain as research-only "
                    "until registry freeze"
                    if is_lineup_discipline
                    else "stabilization-qualified weighted-dispersion family "
                    "improved both LightGBM outer folds but worsened Ridge MAE "
                    "in both; retain all variants as research-only"
                    if description["family"] == "batter-quality-lineup"
                    else "lineup construction candidate; retain as research-only "
                    "pending stabilization, grouped nested ablation, and registry "
                    "freeze"
                    if is_lineup and is_expanded
                    else "expanded family was not selected on inner folds for "
                    "either outer confirmation; no promotion"
                    if is_expanded
                    else "retained from the audit-corrected pre-expansion baseline"
                ),
            }
        )
    rows.extend(
        [
            {
                "feature": "strike_rate_*",
                "family": "deterministic-redundancy",
                "definition": "(S + X) / pitches",
                "numerator": "Strikes+BIP",
                "denominator": "Pitches",
                "candidate_window": "",
                "source": "src/Python/pitcher_features.py",
                "missing_pct": 0.0,
                "deterministic_status": "strike_rate = 1 - ball_rate",
                "eligibility": "rejected",
                "decision": "drop",
                "reason": "exact algebraic complement of ball_rate",
            },
            {
                "feature": "neutral_rate_*",
                "family": "deterministic-redundancy",
                "definition": "pre-pitch equal-ball/strike count share",
                "numerator": "NeutralPitches",
                "denominator": "Pitches",
                "candidate_window": "",
                "source": "src/Python/pitcher_features.py",
                "missing_pct": 0.0,
                "deterministic_status": "ahead + neutral + behind = 1",
                "eligibility": "rejected",
                "decision": "drop",
                "reason": "omitted reference for exact count-state composition",
            },
            {
                "feature": "WPA",
                "family": "context",
                "definition": "change in home win expectancy",
                "numerator": "delta_home_win_exp",
                "denominator": "",
                "candidate_window": "",
                "source": "Statcast",
                "missing_pct": 0.0,
                "deterministic_status": "not applicable",
                "eligibility": "rejected",
                "decision": "drop",
                "reason": "leverage-dependent context, not pitcher strikeout skill",
            },
        ]
    )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = build_registry()
    registry.to_csv(OUTPUT_DIR / "candidate_feature_registry.csv", index=False)
    production = registry.loc[
        registry["eligibility"] == "production_baseline",
        ["feature", "family", "definition", "reason"],
    ]
    production.to_csv(OUTPUT_DIR / "final_lightgbm_registry.csv", index=False)
    ridge_path = OUTPUT_DIR / "vif_reduced_features.csv"
    if ridge_path.exists():
        ridge = pd.read_csv(ridge_path)
        ridge.to_csv(OUTPUT_DIR / "final_ridge_registry.csv", index=False)
    print(
        registry.groupby(["eligibility", "family"], dropna=False)
        .size()
        .to_string()
    )


if __name__ == "__main__":
    main()
