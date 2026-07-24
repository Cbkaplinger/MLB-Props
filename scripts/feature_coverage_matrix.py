"""Build a conceptual Level 1-3 feature-coverage inventory.

This script is documentation-only: it reads source-of-truth research artifacts
and groups model columns into conceptual metrics. It does not create model
features or alter pipeline data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Python import config


OUTPUT = config.OUTPUT_DIR / "feature_research" / "feature_coverage_matrix.csv"
EXPANDED = config.OUTPUT_DIR / "feature_research" / "expanded"
PITCH_TYPES = {"ff", "si", "fc", "sl", "st", "cu", "ch", "fs"}


@dataclass(frozen=True)
class Gap:
    entity: str
    metric: str
    numerator: str
    denominator: str
    level1: str
    level2: str
    level3: str
    status: str
    reason: str
    stabilization: str = "no"
    ablation: str = "no"


RATE_COUNTS = {
    "k_rate": ("K", "PA"),
    "bb_rate": ("BB", "PA"),
    "csw_rate": ("CSW", "Pitches"),
    "swstr_rate": ("Whiffs", "Pitches"),
    "whiff_rate": ("Whiffs", "Swings"),
    "ball_rate": ("Balls", "Pitches"),
    "cs_rate": ("CS", "Pitches"),
    "chase_rate": ("Chases", "OutZone"),
    "zone_rate": ("InZone", "Pitches"),
    "contact_rate": ("Contacts", "Swings"),
    "zcontact_rate": ("ZContacts", "ZSwings"),
    "ocontact_rate": ("OContacts", "Chases"),
    "zswing_rate": ("ZSwings", "InZone"),
    "swing_rate": ("Swings", "Pitches"),
    "gb_rate": ("GB", "BIP"),
    "fb_rate": ("FB", "BIP"),
    "hr_rate": ("HR", "PA"),
    "hr_fb_rate": ("HR", "FB"),
    "bip_rate": ("BIP", "Pitches"),
    "babip": ("BABIP_num", "BABIP_den"),
    "hard_hit_rate": ("HardHit", "EV_den"),
    "barrel_rate": ("Barrels", "xBA_den"),
    "sweet_spot_rate": ("SweetSpot", "LA_den"),
    "avg_exit_velocity": ("EV_num", "EV_den"),
    "avg_launch_angle": ("LA_num", "LA_den"),
    "xBA": ("xBA_num", "xBA_den"),
    "wOBA": ("wOBA_num", "wOBA_den"),
    "xwOBA": ("xwOBA_num", "wOBA_den"),
    "pull_air_rate": ("PullAir", "BIP"),
    "rv_per_pitch": ("RV_num", "RV_den"),
    "rv_per_100": ("100 * RV_num", "RV_den"),
    "first_pitch_strike_rate": ("FirstPitchStrikes", "FirstPitches"),
    "ahead_rate": ("AheadPitches", "Pitches"),
    "behind_rate": ("BehindPitches", "Pitches"),
    "two_strike_reach_rate": ("TwoStrikePA", "PA"),
    "putaway_rate": ("PutAwayK", "TwoStrikePitches"),
    "k_rate versus starter hand": ("K_vL/K_vR", "PA_vL/PA_vR"),
}

LINEUP_TO_SOURCE = {
    "k": "k_rate",
    "k_vs_hand": "k_rate versus starter hand",
    "whiff": "whiff_rate",
    "swstr": "swstr_rate",
    "chase": "chase_rate",
    "zswing": "zswing_rate",
    "swing": "swing_rate",
    "zcontact": "zcontact_rate",
    "bb": "bb_rate",
    "babip": "babip",
    "hard_hit": "hard_hit_rate",
    "barrel": "barrel_rate",
    "sweet_spot": "sweet_spot_rate",
    "avg_ev": "avg_exit_velocity",
    "avg_la": "avg_launch_angle",
    "xba": "xBA",
    "woba": "wOBA",
    "xwoba": "xwOBA",
    "hr": "hr_rate",
    "fb": "fb_rate",
    "hr_fb": "hr_fb_rate",
    "pull_air": "pull_air_rate",
    "rv_per_pitch": "rv_per_pitch",
}

GAPS = (
    Gap(
        "batter",
        "zone_rate",
        "InZone",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 rate exists; omitted from batter rolling candidate set.",
    ),
    Gap(
        "batter",
        "ocontact_rate",
        "OContacts",
        "Chases",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 rate exists; sparse chase denominator has not been screened.",
    ),
    Gap(
        "batter",
        "contact_rate",
        "Contacts",
        "Swings",
        "yes",
        "not rolled",
        "not joined",
        "rejected",
        "Exact complement of Whiff%; deterministic redundancy.",
    ),
    Gap(
        "batter",
        "called_strike_rate",
        "CS",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Called-strike count exists but has no batter rolling transform.",
    ),
    Gap(
        "batter",
        "csw_rate",
        "CSW",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "rejected",
        "CSW is exactly called-strike rate plus SwStr%; keep components.",
    ),
    Gap(
        "batter",
        "hbp_rate",
        "HBP",
        "PA",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Count exists but relevance to pitcher K/PA has not justified creation.",
    ),
    Gap(
        "batter",
        "hit_rate",
        "Hits",
        "PA",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Count exists; overlaps wOBA/xwOBA/xBA and has not been nominated.",
    ),
    Gap(
        "batter",
        "bip_rate",
        "BIP",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Count exists; denominator/target relevance remains to be specified.",
    ),
    Gap(
        "batter",
        "gb_rate",
        "GB",
        "BIP",
        "no",
        "not rolled",
        "not joined",
        "not created",
        "Batter Level 1 currently retains FB but not GB count.",
    ),
    Gap(
        "batter",
        "discipline_by_pitcher_hand",
        "metric numerator versus L/R",
        "matching opportunities versus L/R",
        "no",
        "not rolled",
        "not joined",
        "not created",
        "Only batter K% currently has pitcher-handedness count pairs.",
    ),
    Gap(
        "batter",
        "pitch_type_matchup_features",
        "pitch-type result counts",
        "pitch-type pitches/opportunities",
        "no",
        "not rolled into Level 2",
        "not joined",
        "research",
        "Rich pitch-type table exists, but prior run-value reliability failed.",
        "yes — artifacts/stabilization/expanded/batter_pitch_type/",
        "no",
    ),
    Gap(
        "pitcher",
        "csw_rate",
        "CSW",
        "Pitches",
        "yes",
        "P5, P10, P20, season-to-date",
        "excluded by feature-safety gate",
        "rejected",
        "Exactly cs_rate + swstr_rate; component rates are retained.",
        "yes — artifacts/stabilization/expanded/crossings_summary.csv",
        "no",
    ),
    Gap(
        "pitcher",
        "contact_rate",
        "Contacts",
        "Swings",
        "yes",
        "P5, P10, P20, season-to-date",
        "excluded by feature-safety gate",
        "rejected",
        "Exact complement of Whiff%; deterministic redundancy.",
    ),
    Gap(
        "pitcher",
        "strike_rate",
        "Strikes + BIP",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "rejected",
        "Exact complement of ball_rate under the project pitch classification.",
    ),
    Gap(
        "pitcher",
        "neutral_rate",
        "NeutralPitches",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "rejected",
        "Omitted reference for ahead/behind count-state composition.",
    ),
    Gap(
        "pitcher",
        "zswing_rate",
        "ZSwings",
        "InZone",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 discipline rate exists but is outside DEFAULT_RATE_STATS.",
    ),
    Gap(
        "pitcher",
        "swing_rate",
        "Swings",
        "Pitches",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 discipline rate exists but is outside DEFAULT_RATE_STATS.",
    ),
    Gap(
        "pitcher",
        "zcontact_rate",
        "ZContacts",
        "ZSwings",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 discipline rate exists but is outside DEFAULT_RATE_STATS.",
    ),
    Gap(
        "pitcher",
        "ocontact_rate",
        "OContacts",
        "Chases",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Level 1 discipline rate exists but is outside DEFAULT_RATE_STATS.",
    ),
    Gap(
        "pitcher",
        "fb_rate",
        "FB",
        "BIP",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "FB count exists; GB% currently represents batted-ball composition.",
    ),
    Gap(
        "pitcher",
        "popup_rate",
        "PU",
        "BIP",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Popup count supports SIERA but is not exposed as a standalone rate.",
    ),
    Gap(
        "pitcher",
        "outfield_fly_rate",
        "OFB",
        "BIP",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Outfield-fly count supports SIERA but is not exposed as a rate.",
    ),
    Gap(
        "pitcher",
        "hbp_rate",
        "HBP",
        "PA",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "HBP count supports FIP/xFIP but has no standalone rolling rate.",
    ),
    Gap(
        "pitcher",
        "hit_rate",
        "Hits",
        "PA",
        "yes",
        "not rolled",
        "not joined",
        "not rolled",
        "Count exists; expected-contact metrics are the preferred representation.",
    ),
    Gap(
        "pitcher",
        "FIP_season_to_date",
        "13*HR + 3*(BB+HBP) - 2*K",
        "IP from Outs",
        "yes",
        "not rolled; P3/P5/P10 only",
        "not joined",
        "not created",
        "Season-to-date composite is a queued targeted candidate.",
    ),
    Gap(
        "pitcher",
        "xFIP_season_to_date",
        "13*(FB*prior league HR/FB) + 3*(BB+HBP) - 2*K",
        "IP from Outs",
        "yes",
        "not rolled; P3/P5/P10 only",
        "not joined",
        "not created",
        "Requires leakage-safe prior-date league HR/FB and targeted ablation.",
    ),
    Gap(
        "pitcher",
        "k_minus_bb_rate",
        "K - BB",
        "PA",
        "yes",
        "not materialized",
        "not joined",
        "rejected",
        "Exactly k_rate - bb_rate; test only as a replacement representation.",
    ),
    Gap(
        "pitcher",
        "physics_usage_season_to_date",
        "pitch-weighted metric sum",
        "matching pitch count",
        "yes",
        "not rolled; P3/P5/P10 only",
        "not joined",
        "not created",
        "Do not use flat start means; natural-denominator weighting is required.",
    ),
    Gap(
        "lineup",
        "announced_lineup_training_membership",
        "",
        "",
        "no",
        "not applicable",
        "historical first-nine proxy",
        "not created",
        "Live announced lineups exist, but historical training uses first-AB order.",
    ),
    Gap(
        "lineup",
        "robust_dispersion_iqr_or_threat_max",
        "",
        "",
        "no",
        "not applicable",
        "not joined",
        "not created",
        "Weighted SD exists; IQR/max are parked to avoid post-hoc operator search.",
    ),
    Gap(
        "park",
        "neutral_site_venue_override",
        "",
        "",
        "no",
        "not applicable",
        "not joined",
        "not created",
        "Team-keyed park factors can misclassify neutral/international venues.",
    ),
)


def _strip_window(feature: str) -> str:
    value = re.sub(r"_order_(?:weighted|sd)$", "", feature)
    value = re.sub(r"_P\d+$", "", value)
    value = re.sub(r"_std(?:_vL|_vR|_shrunk)?$", "", value)
    return value


def conceptual_key(feature: str) -> tuple[str, str]:
    if feature == "park_k_factor":
        return "park", "strikeout_factor"
    if feature == "is_home":
        return "pitcher", "home_game_context"
    if feature.startswith("opp_lineup_"):
        return "lineup", _strip_window(feature.removeprefix("opp_lineup_"))
    base = _strip_window(feature)
    if base.startswith("has_thrown_"):
        return "pitcher", "pitch_type_arsenal_presence"
    match = re.match(r"^([a-z]{2})_(.+)$", base)
    if match and match.group(1) in PITCH_TYPES:
        detail = match.group(2)
        if detail.startswith("usage_v"):
            detail = "usage_by_batter_hand"
        elif detail == "usage":
            detail = "usage"
        elif detail.startswith("rv_shrunk"):
            detail = "run_value_shrunk"
        return "pitcher", f"pitch_type_{detail}"
    return "pitcher", base


def _windows(features: list[str]) -> str:
    windows = sorted(
        {int(match.group(1)) for feature in features if (match := re.search(r"_P(\d+)", feature))}
    )
    has_std = any(re.search(r"_std(?:_|$)", feature) for feature in features)
    parts = [*(f"P{window}" for window in windows)]
    if has_std:
        parts.append("season-to-date")
    return ", ".join(parts) if parts else "static/direct"


def _aggregation(entity: str, features: list[str]) -> str:
    if entity == "lineup":
        methods = ["flat mean"]
        if any(feature.endswith("_order_weighted") for feature in features):
            methods.append("prior-date batting-order weighted mean")
        if any(feature.endswith("_order_sd") for feature in features):
            methods.append("prior-date batting-order weighted SD")
        return "; ".join(methods)
    if entity == "park":
        return "prior-season park dimension join"
    return "direct pitcher pregame feature"


def _status(registry: pd.DataFrame, features: list[str]) -> str:
    eligibility = set(
        registry.loc[registry["feature"].isin(features), "eligibility"].dropna()
    )
    if eligibility == {"production_baseline"}:
        return "production"
    if eligibility == {"research_only"}:
        return "research"
    if eligibility == {"rejected"}:
        return "rejected"
    if "production_baseline" in eligibility and "research_only" in eligibility:
        return "production + research variants"
    return "research"


def _evidence(entity: str, metric: str) -> tuple[str, str]:
    source = LINEUP_TO_SOURCE.get(metric, metric) if entity == "lineup" else metric
    stabilization = "no"
    ablation = "no"
    pitcher_overall = set(RATE_COUNTS) | {
        "popup_rate",
        "outfield_fly_rate",
        "arm_angle",
    }
    batter_discipline = {
        "zswing_rate",
        "swing_rate",
        "zcontact_rate",
        "bb_rate",
    }
    batter_quality = {
        "babip",
        "hard_hit_rate",
        "barrel_rate",
        "sweet_spot_rate",
        "avg_exit_velocity",
        "avg_launch_angle",
        "xBA",
        "wOBA",
        "xwOBA",
        "hr_rate",
        "fb_rate",
        "hr_fb_rate",
        "pull_air_rate",
        "rv_per_pitch",
    }
    batter_core = {"k_rate", "whiff_rate", "swstr_rate", "chase_rate"}
    if entity == "pitcher" and source in pitcher_overall:
        stabilization = "yes — artifacts/stabilization/expanded/crossings_summary.csv"
    elif entity == "lineup" and source in batter_discipline:
        stabilization = (
            "yes — artifacts/stabilization/expanded/batter_discipline/"
            "batter_discipline_crossings_summary.csv"
        )
        ablation = "yes — artifacts/feature_research/batter_discipline_ablation_*"
    elif entity == "lineup" and source in batter_quality:
        stabilization = (
            "yes — artifacts/stabilization/expanded/batter_quality/"
            "batter_quality_crossings_summary.csv"
        )
        ablation = "yes — artifacts/feature_research/batter_quality_ablation_*"
    elif entity == "lineup" and source in batter_core:
        stabilization = "yes — artifacts/stabilization/expanded/crossings_summary.csv"
    if entity == "pitcher" and source in {
        "babip",
        "arm_angle",
        "rv_per_100",
    }:
        ablation = "yes — artifacts/feature_research/targeted_window_ablation_*"
    elif entity == "pitcher" and source not in {
        "home_game_context",
        "pitch_type_arsenal_presence",
    }:
        ablation = "yes — artifacts/feature_research/expanded/*ablation_*"
    return stabilization, ablation


def build_matrix() -> pd.DataFrame:
    dictionary = pd.read_csv(EXPANDED / "feature_dictionary.csv")
    missingness = pd.read_csv(EXPANDED / "feature_missingness.csv")
    registry = pd.read_csv(EXPANDED / "candidate_feature_registry.csv")
    expected = set(dictionary["feature"])
    if len(expected) != 563:
        raise ValueError(f"expected current 563-feature dictionary, found {len(expected)}")

    missing_map = missingness.set_index("feature")["missing_pct"].to_dict()
    groups: dict[tuple[str, str], list[str]] = {}
    for feature in dictionary["feature"]:
        groups.setdefault(conceptual_key(feature), []).append(feature)

    rows: list[dict[str, object]] = []
    accounted: set[str] = set()
    for (entity, metric), features in sorted(groups.items()):
        features = sorted(features)
        accounted.update(features)
        source_metric = LINEUP_TO_SOURCE.get(metric, metric)
        numerator, denominator = RATE_COUNTS.get(source_metric, ("", ""))
        stabilization, ablation = _evidence(entity, metric)
        values = [float(missing_map[feature]) for feature in features]
        rows.append(
            {
                "entity": entity,
                "metric": metric,
                "numerator": numerator,
                "denominator": denominator,
                "available_at_level_1": (
                    "yes"
                ),
                "level_2_transform_windows": _windows(features),
                "level_3_aggregation": _aggregation(entity, features),
                "missingness_pct_min": min(values),
                "missingness_pct_max": max(values),
                "stabilization_evidence": stabilization,
                "nested_ablation_evidence": ablation,
                "status": _status(registry, features),
                "reason_for_omission": "",
                "level3_feature_count": len(features),
                "level3_columns": ";".join(features),
            }
        )

    if accounted != expected:
        missing = sorted(expected - accounted)
        extra = sorted(accounted - expected)
        raise ValueError(f"feature accounting mismatch; missing={missing}; extra={extra}")

    # Batter Level 2 histories are inputs to lineup aggregation, not direct
    # pitcher-training columns. Keep them visible as their own entity rows while
    # assigning Level 3 column accounting only to the lineup rows above.
    lineup_rows = {
        row["metric"]: row for row in rows if row["entity"] == "lineup"
    }
    production_sources = {"k", "k_vs_hand", "whiff", "swstr", "chase"}
    for lineup_metric, source_metric in LINEUP_TO_SOURCE.items():
        lineup_row = lineup_rows.get(lineup_metric)
        if lineup_row is None:
            continue
        numerator, denominator = RATE_COUNTS.get(source_metric, ("", ""))
        rows.append(
            {
                "entity": "batter",
                "metric": source_metric,
                "numerator": numerator,
                "denominator": denominator,
                "available_at_level_1": "yes",
                "level_2_transform_windows": (
                    "season-to-date only"
                    if lineup_metric == "k_vs_hand"
                    else "P5, P10, P20, season-to-date"
                ),
                "level_3_aggregation": f"feeds lineup metric: {lineup_metric}",
                "missingness_pct_min": lineup_row["missingness_pct_min"],
                "missingness_pct_max": lineup_row["missingness_pct_max"],
                "stabilization_evidence": lineup_row["stabilization_evidence"],
                "nested_ablation_evidence": lineup_row["nested_ablation_evidence"],
                "status": (
                    "production"
                    if lineup_metric in production_sources
                    else "research"
                ),
                "reason_for_omission": "",
                "level3_feature_count": 0,
                "level3_columns": "",
            }
        )

    existing_keys = {(row["entity"], row["metric"]) for row in rows}
    for gap in GAPS:
        if (gap.entity, gap.metric) in existing_keys:
            continue
        rows.append(
            {
                "entity": gap.entity,
                "metric": gap.metric,
                "numerator": gap.numerator,
                "denominator": gap.denominator,
                "available_at_level_1": gap.level1,
                "level_2_transform_windows": gap.level2,
                "level_3_aggregation": gap.level3,
                "missingness_pct_min": "",
                "missingness_pct_max": "",
                "stabilization_evidence": gap.stabilization,
                "nested_ablation_evidence": gap.ablation,
                "status": gap.status,
                "reason_for_omission": gap.reason,
                "level3_feature_count": 0,
                "level3_columns": "",
            }
        )
    return pd.DataFrame(rows).sort_values(["entity", "metric"]).reset_index(drop=True)


def main() -> None:
    matrix = build_matrix()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(OUTPUT, index=False)
    print(
        {
            "conceptual_rows": len(matrix),
            "level3_features_accounted": int(matrix["level3_feature_count"].sum()),
            "non_direct_level3_rows": int(matrix["level3_feature_count"].eq(0).sum()),
            "documented_omission_rows": int(
                matrix["reason_for_omission"].fillna("").ne("").sum()
            ),
            "output": str(OUTPUT),
        }
    )


if __name__ == "__main__":
    main()
