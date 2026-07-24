"""Select one reliability-guided representative per Phase 1 VIF cluster.

This script is proposal-only: it does not change the production trainer's
feature list. It consumes the Phase 1 feature dictionary, VIF, Pearson, and
missingness artifacts, then recomputes VIF on the proposed reduced set.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from feature_diagnostics import OUTPUT_DIR, _base_name, load_training_partition, vif_table


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STABILIZATION_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "stabilization"
    / "expanded"
    / "crossings_summary.csv"
)
SERIOUS_VIF_THRESHOLD = 10.0
WINDOW_NUMBER_RE = re.compile(r"_P(\d+)$")


@dataclass(frozen=True)
class Choice:
    """One representative choice and its governing evidence."""

    feature: str
    tie_breaker: str
    reason: str
    evidence_source: str


def _window_number(feature: str) -> int | None:
    match = WINDOW_NUMBER_RE.search(feature)
    return int(match.group(1)) if match else None


def _documented_stat(feature: str) -> tuple[str, str] | None:
    """Map an eligible feature to comparable stabilization evidence."""
    if feature == "opp_lineup_whiff":
        return "batter", "whiff_rate"
    if feature == "opp_lineup_swstr":
        return "batter", "swstr_rate"
    base = _base_name(feature)
    if base in {
        "k_rate",
        "whiff_rate",
        "swstr_rate",
        "ball_rate",
        "chase_rate",
        "bb_rate",
        "gb_rate",
        "bip_rate",
        "babip",
        "first_pitch_strike_rate",
        "ahead_rate",
        "behind_rate",
        "two_strike_reach_rate",
        "putaway_rate",
        "arm_angle",
        "rv_per_100",
    }:
        return "pitcher", (
            "rv_per_pitch" if base == "rv_per_100" else base
        )
    return None


def _reliability_choice(
    members: list[str],
    crossings: pd.DataFrame,
) -> Choice | None:
    """Apply documented positive or negative reliability before other rules."""
    hr_members = [member for member in members if _base_name(member) == "hr_rate"]
    hr_fb_evidence = crossings[
        (crossings["population"] == "pitcher")
        & (crossings["stat"] == "hr_fb")
    ]
    hr_alternatives = [member for member in members if member not in hr_members]
    if (
        hr_members
        and hr_alternatives
        and not hr_fb_evidence.empty
        and not hr_fb_evidence["reliably_estimable"].astype(bool).any()
    ):
        chosen = min(hr_alternatives, key=_simplicity_score)
        return Choice(
            feature=chosen,
            tie_breaker="a_reliability_negative_related",
            reason=(
                "HR/FB—not HR/PA—failed stabilization; treated as related "
                "family-level caution against a raw short-window HR signal, "
                "not as denominator-equivalent evidence; selected the simplest "
                "non-HR alternative in the cluster"
            ),
            evidence_source="artifacts/stabilization/crossings_summary.csv",
        )

    evidence_by_stat: dict[tuple[str, str], pd.DataFrame] = {}
    for member in members:
        key = _documented_stat(member)
        if key is None:
            continue
        population, stat = key
        evidence_by_stat[key] = crossings[
            (crossings["population"] == population)
            & (crossings["stat"] == stat)
        ]

    evidence_by_stat = {
        key: evidence for key, evidence in evidence_by_stat.items() if not evidence.empty
    }
    if not evidence_by_stat:
        return None

    reliable_candidates: list[tuple[float, float, str, str, pd.Series]] = []
    for (population, stat), evidence in evidence_by_stat.items():
        reliable = evidence[evidence["reliably_estimable"].astype(bool)]
        if reliable.empty:
            continue
        strongest_threshold = float(reliable["threshold"].max())
        row = reliable[reliable["threshold"] == strongest_threshold].iloc[0]
        starts = float(row["typical_starts_at_median_crossing"])
        reliable_candidates.append(
            (-strongest_threshold, starts, population, stat, row)
        )

    if reliable_candidates:
        _, starts, population, stat, row = min(reliable_candidates)
        eligible = [
            member
            for member in members
            if _documented_stat(member) == (population, stat)
        ]
        with_windows = [
            member for member in eligible if _window_number(member) is not None
        ]
        if with_windows:
            chosen = min(
                with_windows,
                key=lambda feature: (
                    abs((_window_number(feature) or 0) - starts),
                    _window_number(feature) or 0,
                    feature,
                ),
            )
        else:
            chosen = min(eligible)
        return Choice(
            feature=chosen,
            tie_breaker="a_reliability_positive",
            reason=(
                f"{population} {stat} reached reliable r={row['threshold']:.1f} "
                f"at {starts:.2f} typical starts; selected the nearest available "
                "window"
            ),
            evidence_source="artifacts/stabilization/crossings_summary.csv",
        )

    # A documented failure to stabilize is still governing evidence: use the
    # longest available history rather than allowing missingness to select a
    # noisy short window.
    documented_members = [
        member for member in members if _documented_stat(member) in evidence_by_stat
    ]
    alternatives = [
        member for member in members if member not in set(documented_members)
    ]
    if alternatives:
        chosen = min(alternatives, key=_simplicity_score)
        unstable = ", ".join(
            sorted({(_documented_stat(member) or ("", ""))[1] for member in documented_members})
        )
        return Choice(
            feature=chosen,
            tie_breaker="a_reliability_negative",
            reason=(
                f"documented {unstable} stabilization failed; rejected that "
                "unstable raw family and selected the simplest alternative "
                "within the Pearson/VIF cluster"
            ),
            evidence_source="artifacts/stabilization/crossings_summary.csv",
        )
    season_to_date = [
        member for member in documented_members if member.endswith("_std")
    ]
    if season_to_date:
        chosen = min(season_to_date)
    else:
        rolling = [
            member for member in documented_members if _window_number(member) is not None
        ]
        chosen = max(
            rolling,
            key=lambda feature: (_window_number(feature) or 0, feature),
        )
    population, stat = _documented_stat(chosen) or ("unknown", "unknown")
    return Choice(
        feature=chosen,
        tie_breaker="a_reliability_negative",
        reason=(
            f"{population} {stat} has documented stabilization results but no "
            "reliable threshold; selected the longest available history"
        ),
        evidence_source="artifacts/stabilization/crossings_summary.csv",
    )


def _simplicity_score(feature: str) -> tuple[int, int, int, str]:
    """Prefer raw finite-window rates over derived/expanding variants."""
    lowered = feature.lower()
    derived = sum(
        token in lowered
        for token in ("shrunk", "xfip", "fip", "woba", "xwoba")
    )
    expanding = int("_std" in feature)
    window = _window_number(feature)
    return derived, expanding, window if window is not None else math.inf, feature


def choose_representative(
    cluster: pd.DataFrame,
    crossings: pd.DataFrame,
) -> Choice:
    """Choose a cluster representative using the required ordered priorities."""
    members = sorted(cluster["feature"].tolist())
    reliability = _reliability_choice(members, crossings)
    if reliability is not None:
        return reliability

    minimum_missingness = float(cluster["missing_pct"].min())
    least_missing = sorted(
        cluster.loc[
            np.isclose(cluster["missing_pct"], minimum_missingness),
            "feature",
        ].tolist()
    )
    if len(least_missing) == 1:
        return Choice(
            feature=least_missing[0],
            tie_breaker="b_missingness",
            reason=(
                f"no comparable stabilization result; selected minimum training-"
                f"split missingness ({minimum_missingness:.6f}%)"
            ),
            evidence_source="artifacts/feature_research/feature_missingness.csv",
        )

    chosen = min(least_missing, key=_simplicity_score)
    return Choice(
        feature=chosen,
        tie_breaker="c_simplicity",
        reason=(
            "no comparable stabilization result and missingness tied; selected "
            "the least-derived finite-window definition (stable name as final tie)"
        ),
        evidence_source="artifacts/feature_research/feature_dictionary.csv",
    )


def main() -> None:
    dictionary_path = OUTPUT_DIR / "feature_dictionary.csv"
    vif_path = OUTPUT_DIR / "vif.csv"
    pearson_path = OUTPUT_DIR / "pearson_correlation_matrix.csv"
    missingness_path = OUTPUT_DIR / "feature_missingness.csv"
    required = (
        dictionary_path,
        vif_path,
        pearson_path,
        missingness_path,
        STABILIZATION_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing Phase 1/reliability artifacts: {missing}")

    dictionary = pd.read_csv(dictionary_path)
    phase1_vif = pd.read_csv(vif_path)
    # Reading these artifacts is intentional: they are required Phase 1 inputs
    # even where the dictionary already carries derived columns.
    pd.read_csv(pearson_path, index_col=0)
    missingness = pd.read_csv(missingness_path)
    crossings = pd.read_csv(STABILIZATION_PATH)
    crossings["reliably_estimable"] = crossings["reliably_estimable"].map(
        {"True": True, "False": False, True: True, False: False}
    )

    serious = set(
        phase1_vif.loc[
            phase1_vif["vif"] > SERIOUS_VIF_THRESHOLD,
            "feature",
        ]
    )
    clustered = dictionary[
        dictionary["feature"].isin(serious)
        & dictionary["vif_cluster"].notna()
        & dictionary["vif_cluster"].ne("")
    ].copy()
    if set(clustered["feature"]) != serious:
        unclustered = sorted(serious - set(clustered["feature"]))
        raise ValueError(f"serious-VIF features lack Phase 1 clusters: {unclustered}")

    rows: list[dict[str, object]] = []
    representatives: list[str] = []
    for cluster_name, cluster in clustered.groupby("vif_cluster", sort=True):
        cluster = cluster.merge(
            missingness[["feature", "missing_pct"]],
            on="feature",
            how="left",
            suffixes=("", "_artifact"),
        )
        if cluster["missing_pct_artifact"].isna().any():
            raise ValueError(f"{cluster_name} has missing missingness evidence")
        cluster["missing_pct"] = cluster["missing_pct_artifact"]
        choice = choose_representative(cluster, crossings)
        representatives.append(choice.feature)
        rows.append(
            {
                "vif_cluster": cluster_name,
                "cluster_size": len(cluster),
                "members": "|".join(sorted(cluster["feature"])),
                "representative": choice.feature,
                "dropped_features": "|".join(
                    sorted(set(cluster["feature"]) - {choice.feature})
                ),
                "tie_breaker": choice.tie_breaker,
                "reason": choice.reason,
                "evidence_source": choice.evidence_source,
                "representative_phase1_vif": float(
                    cluster.loc[
                        cluster["feature"] == choice.feature,
                        "vif",
                    ].iloc[0]
                ),
                "representative_missing_pct": float(
                    cluster.loc[
                        cluster["feature"] == choice.feature,
                        "missing_pct",
                    ].iloc[0]
                ),
            }
        )

    nonclustered = [
        feature
        for feature in dictionary["feature"]
        if feature not in set(clustered["feature"])
    ]
    proposed = [*nonclustered, *representatives]
    train, eligible, split = load_training_partition()
    if set(eligible) != set(dictionary["feature"]):
        raise ValueError("current eligible features differ from Phase 1 dictionary")
    proposed = [feature for feature in eligible if feature in set(proposed)]

    reduced_vif, reduced_rank = vif_table(train, proposed)
    reduced_vif.to_csv(OUTPUT_DIR / "vif_reduced.csv", index=False)
    pd.DataFrame(
        {
            "feature": proposed,
            "source": [
                "cluster_representative"
                if feature in set(representatives)
                else "phase1_vif_at_or_below_10"
                for feature in proposed
            ],
        }
    ).to_csv(OUTPUT_DIR / "vif_reduced_features.csv", index=False)

    selection = pd.DataFrame(rows)
    reduced_lookup = reduced_vif.set_index("feature")["vif"]
    selection["representative_reduced_vif"] = selection["representative"].map(
        reduced_lookup
    )
    selection["still_above_10_after_reduction"] = (
        selection["representative_reduced_vif"] > SERIOUS_VIF_THRESHOLD
    )
    selection.to_csv(OUTPUT_DIR / "vif_cluster_selection.csv", index=False)

    finite_vif = reduced_vif.loc[np.isfinite(reduced_vif["vif"]), "vif"]
    metadata = {
        "split": split,
        "phase1_features": len(eligible),
        "phase1_vif_above_10": len(serious),
        "phase1_clusters": int(selection["vif_cluster"].nunique()),
        "proposed_features": len(proposed),
        "cluster_representatives": len(representatives),
        "unclustered_features_retained": len(nonclustered),
        "reduced_design_rank": reduced_rank,
        "reduced_vif_max": float(finite_vif.max()),
        "reduced_vif_median": float(finite_vif.median()),
        "reduced_vif_above_10": int(
            (reduced_vif["vif"] > SERIOUS_VIF_THRESHOLD).sum()
        ),
        "clusters_still_above_10": int(
            selection["still_above_10_after_reduction"].sum()
        ),
        "meaningful_reduction": bool(
            len(proposed) < len(eligible)
            and (reduced_vif["vif"] > SERIOUS_VIF_THRESHOLD).sum() < len(serious)
        ),
        "scope_note": (
            "This is a proposal artifact only. The production trainer feature "
            "list is unchanged. VIF below 10 across the board is not the target; "
            "the target is one evidence-based representative per correlated "
            "cluster while retaining intentional standalone predictors."
        ),
    }
    (OUTPUT_DIR / "vif_reduction_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
