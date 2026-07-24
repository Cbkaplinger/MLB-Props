"""Build a scope-controlled candidate set for flagged rolling windows."""

from __future__ import annotations

import json

import pandas as pd

from Python import config


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research"
GAP_PATH = OUTPUT_DIR / "window_stabilization_gap.csv"
PHASE2_INNER_PATH = (
    OUTPUT_DIR / "expanded" / "window_ablation_inner_results.csv"
)
PHASE2_RESULTS_PATH = OUTPUT_DIR / "expanded" / "window_ablation_results.csv"
PHASE2_METADATA_PATH = OUTPUT_DIR / "expanded" / "window_ablation_metadata.json"
PROPOSAL_PATH = OUTPUT_DIR / "window_change_proposals.csv"
MAX_NEW_WINDOWS = 5

# Five total new windows across three metrics. Values are rounded game counts,
# not a search grid centered on the observed point estimate.
CANDIDATES = {
    "babip": (20, 30, 35),
    "arm_angle": (2, 3),
    "rv_per_100": (10, 20, 25),
}
PHASE2_PREFIXES = {
    "babip": ("batted_ball_",),
    "arm_angle": ("arm_angle_",),
    "rv_per_100": ("run_value_",),
}


def _phase2_summary(
    inner: pd.DataFrame,
    outer: pd.DataFrame,
    configurations: dict[str, list[str]],
    metric: str,
) -> tuple[str, set[int]]:
    subset = inner.loc[
        inner["configuration"].str.startswith(PHASE2_PREFIXES[metric])
    ]
    means = (
        subset.groupby(["model", "configuration"], as_index=False)["mae"]
        .mean()
        .sort_values(["model", "mae", "configuration"])
        .drop_duplicates("model")
    )
    selected_windows: set[int] = set()
    details: list[str] = []
    for row in means.itertuples(index=False):
        features = configurations[row.configuration]
        metric_features = [
            feature for feature in features if feature.startswith(f"{metric}_")
        ]
        windows = [
            int(feature.rsplit("_P", 1)[1])
            for feature in metric_features
            if "_P" in feature
        ]
        selected_windows.update(windows)
        details.append(f"{row.model}={row.configuration}")
    outer_matches = outer.loc[
        outer["selected_configuration"].str.startswith(PHASE2_PREFIXES[metric])
    ]
    confirmation = (
        "selected on an outer confirmation"
        if not outer_matches.empty
        else "not selected in window_ablation_results.csv"
    )
    return f"{'; '.join(details)}; {confirmation}", selected_windows


def main() -> None:
    gap = pd.read_csv(GAP_PATH)
    flagged = gap.loc[
        gap["gap_direction"].isin({"under-windowed", "over-windowed"})
    ].copy()
    if set(flagged["metric"]) != set(CANDIDATES):
        raise ValueError(
            "candidate policy must exactly cover the current flagged metrics: "
            f"flagged={sorted(flagged['metric'])}"
        )

    new_metric_windows = {
        (row.metric, window)
        for row in flagged.itertuples(index=False)
        for window in CANDIDATES[row.metric]
        if f"P{window}" not in row.current_default_window.split("/")
    }
    if len(new_metric_windows) > MAX_NEW_WINDOWS:
        raise ValueError(
            f"candidate set introduces {len(new_metric_windows)} new windows; "
            f"cap is {MAX_NEW_WINDOWS}"
        )

    phase2 = pd.read_csv(PHASE2_INNER_PATH)
    phase2_outer = pd.read_csv(PHASE2_RESULTS_PATH)
    metadata = json.loads(PHASE2_METADATA_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in flagged.itertuples(index=False):
        candidates = CANDIDATES[item.metric]
        phase2_text, phase2_windows = _phase2_summary(
            phase2,
            phase2_outer,
            metadata["configurations"],
            item.metric,
        )
        candidate_text = "/".join(f"P{window}" for window in candidates)
        crossing_games = float(item.typical_starts_at_crossing)
        overlaps = phase2_windows & set(candidates)
        disagreement = (
            not overlaps
            or any(window not in candidates for window in phase2_windows)
        )

        if item.metric == "babip":
            rationale = (
                f"The crossing is about {crossing_games:.1f} games. P20 is the "
                "closest existing default; P30 and P35 bracket a rounded long-window "
                f"neighborhood. Prior evidence was bundled with BIP ({phase2_text}), "
                "so it is not metric-isolated."
            )
        elif item.metric == "arm_angle":
            rationale = (
                f"The crossing is about {crossing_games:.1f} games. P3 is the "
                "closest existing default and P2 tests a modest shorter alternative "
                f"without overfitting to a one-start estimate. Phase 2: {phase2_text}."
            )
        else:
            rationale = (
                f"The crossing is about {crossing_games:.1f} games. P10 is the "
                "closest existing default; P20 and P25 add two rounded longer "
                f"alternatives. Phase 2 favored shorter windows ({phase2_text})."
            )

        rows.append(
            {
                "feature": item.feature,
                "current default": item.current_default_window,
                "stabilization crossing point": item.stabilization_crossing_point,
                "proposed candidate windows": candidate_text,
                "rationale": rationale,
                "disagreement flag (yes/no)": "yes" if disagreement else "no",
            }
        )

    proposals = pd.DataFrame(rows)
    proposals.to_csv(PROPOSAL_PATH, index=False)
    print(proposals.to_string(index=False))
    print(
        f"Wrote {len(proposals)} proposals with {len(new_metric_windows)} total new "
        f"window values to {PROPOSAL_PATH}"
    )


if __name__ == "__main__":
    main()
