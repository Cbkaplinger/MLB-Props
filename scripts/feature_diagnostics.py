"""Reproduce feature redundancy and target-dispersion diagnostics.

All fitted statistics use only the chronological training partition from
``Models/Strikeout-Model/train.py``. Correlation analysis is intentionally
sequenced Pearson -> targeted Spearman -> narrow Kendall, followed by VIF
grouping that reloads the saved Pearson matrix.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config  # noqa: E402


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "expanded"
CORRELATION_THRESHOLD = 0.80
SERIOUS_VIF_THRESHOLD = 10.0
PA_BIN_EDGES = (8, 12, 16, 20, 24, 28, math.inf)
PITCH_TYPES = ("ff", "si", "fc", "sl", "st", "cu", "ch", "fs")
WINDOW_RE = re.compile(r"_(P\d+|std(?:_vL|_vR|_shrunk)?)$")


def _load_train_module() -> ModuleType:
    """Load the production trainer so its exact season and split policy is reused."""
    path = PROJECT_ROOT / "Models" / "Strikeout-Model" / "train.py"
    spec = importlib.util.spec_from_file_location("mlb_props_train", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load trainer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_training_partition() -> tuple[pd.DataFrame, list[str], dict[str, object]]:
    """Return only the production chronological training partition."""
    trainer = _load_train_module()
    frame, _production_features = trainer.load_frame()
    features = trainer.model_feature_names(
        frame,
        include_experimental=True,
    )
    train, validation, test = trainer.chronological_split(frame)
    split = {
        "configured_training_seasons": list(config.TRAIN_SEASONS),
        "full_rows": len(frame),
        "training_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
        "training_start": str(train["game_date"].min().date()),
        "training_end": str(train["game_date"].max().date()),
        "validation_start": str(validation["game_date"].min().date()),
        "validation_end": str(validation["game_date"].max().date()),
        "test_start": str(test["game_date"].min().date()),
        "test_end": str(test["game_date"].max().date()),
    }
    return train.copy(), list(features), split


def missingness_table(train: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Return one reproducible missingness row per eligible feature."""
    rows = len(train)
    missing = train[features].isna().sum()
    return pd.DataFrame(
        {
            "feature": features,
            "missing_rows": [int(missing[feature]) for feature in features],
            "training_rows": rows,
            "missing_pct": [
                float(100.0 * missing[feature] / rows) for feature in features
            ],
        }
    ).sort_values(["missing_pct", "feature"], ascending=[False, True])


def dispersion_table(train: pd.DataFrame) -> pd.DataFrame:
    """Compare observed K and K/PA variance with binomial sampling variance.

    PA bins are (8,12], (12,16], ..., (28,infinity]. Within each bin, pooled
    strikeout probability is sum(K)/sum(PA). Expected count variance is
    mean(PA)*p*(1-p); expected rate variance is p*(1-p)*mean(1/PA).
    """
    required = train.dropna(subset=["K", "PA", "k_rate"]).copy()
    required["pa_bin"] = pd.cut(required["PA"], bins=PA_BIN_EDGES)
    rows: list[dict[str, object]] = []
    for interval, group in required.groupby("pa_bin", observed=True):
        pooled_p = float(group["K"].sum() / group["PA"].sum())
        observed_count_variance = float(group["K"].var(ddof=1))
        expected_count_variance = float(group["PA"].mean() * pooled_p * (1 - pooled_p))
        observed_rate_variance = float(group["k_rate"].var(ddof=1))
        expected_rate_variance = float(
            pooled_p * (1 - pooled_p) * (1 / group["PA"]).mean()
        )
        rows.append(
            {
                "pa_bin": str(interval),
                "rows": len(group),
                "pooled_k_probability": pooled_p,
                "observed_k_variance": observed_count_variance,
                "expected_binomial_k_variance": expected_count_variance,
                "k_variance_ratio": observed_count_variance
                / expected_count_variance,
                "observed_k_rate_variance": observed_rate_variance,
                "expected_binomial_k_rate_variance": expected_rate_variance,
                "k_rate_variance_ratio": observed_rate_variance
                / expected_rate_variance,
            }
        )
    return pd.DataFrame(rows)


def _flagged_pairs(
    matrix: pd.DataFrame,
    *,
    method: str,
    threshold: float = CORRELATION_THRESHOLD,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    columns = list(matrix.columns)
    for index, left in enumerate(columns):
        for right in columns[index + 1 :]:
            correlation = matrix.at[left, right]
            if pd.notna(correlation) and abs(correlation) > threshold:
                rows.append(
                    {
                        "method": method,
                        "left": left,
                        "right": right,
                        "correlation": float(correlation),
                        "abs_correlation": float(abs(correlation)),
                        "threshold": threshold,
                    }
                )
    columns_out = [
        "method",
        "left",
        "right",
        "correlation",
        "abs_correlation",
        "threshold",
    ]
    return pd.DataFrame(rows, columns=columns_out).sort_values(
        "abs_correlation", ascending=False
    )


def _base_name(feature: str) -> str:
    return WINDOW_RE.sub("", feature)


def spearman_features(features: list[str]) -> list[str]:
    """Select window, shrinkage, and xFIP families for targeted Spearman."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for feature in features:
        if WINDOW_RE.search(feature):
            grouped[_base_name(feature)].append(feature)

    selected: set[str] = set()
    for base, members in grouped.items():
        rolling = [feature for feature in members if re.search(r"_P\d+$", feature)]
        shrinkage = [
            feature
            for feature in members
            if feature.endswith("_std") or feature.endswith("_std_shrunk")
        ]
        if len(rolling) >= 2:
            selected.update(rolling)
        if len(shrinkage) >= 2 or "xfip" in base.lower():
            selected.update(members)
    selected.update(feature for feature in features if "xfip" in feature.lower())
    return [feature for feature in features if feature in selected]


def kendall_pairs(train: pd.DataFrame, features: list[str]) -> list[tuple[str, str]]:
    """Return same-family low-count pairs with enough ties for Kendall."""
    low_count_tokens = ("whiff_rate", "cs_rate", "hr_rate", "fip", "xfip")
    grouped: dict[str, list[str]] = defaultdict(list)
    for feature in features:
        base = _base_name(feature).lower()
        if any(token in base for token in low_count_tokens):
            grouped[base].append(feature)

    pairs: list[tuple[str, str]] = []
    for members in grouped.values():
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                left_valid = train[left].dropna()
                right_valid = train[right].dropna()
                left_tie_fraction = (
                    1 - left_valid.nunique() / len(left_valid) if len(left_valid) else 0
                )
                right_tie_fraction = (
                    1 - right_valid.nunique() / len(right_valid)
                    if len(right_valid)
                    else 0
                )
                if max(left_tie_fraction, right_tie_fraction) >= 0.10:
                    pairs.append((left, right))
    return pairs


def correlation_artifacts(
    train: pd.DataFrame,
    features: list[str],
) -> dict[str, object]:
    """Write full Pearson, targeted Spearman, and narrow Kendall artifacts."""
    pearson = train[features].corr(method="pearson", min_periods=100)
    pearson.to_csv(OUTPUT_DIR / "pearson_correlation_matrix.csv")
    pearson_flagged = _flagged_pairs(pearson, method="pearson")
    pearson_flagged.to_csv(OUTPUT_DIR / "pearson_flagged_pairs.csv", index=False)

    spearman_columns = spearman_features(features)
    spearman = train[spearman_columns].corr(method="spearman", min_periods=100)
    spearman.to_csv(OUTPUT_DIR / "spearman_correlation_matrix.csv")
    spearman_flagged = _flagged_pairs(spearman, method="spearman")
    spearman_flagged.to_csv(OUTPUT_DIR / "spearman_flagged_pairs.csv", index=False)

    pairs = kendall_pairs(train, features)
    kendall_columns = [
        feature
        for feature in features
        if any(feature in pair for pair in pairs)
    ]
    kendall = pd.DataFrame(
        np.nan,
        index=kendall_columns,
        columns=kendall_columns,
        dtype=float,
    )
    for feature in kendall_columns:
        kendall.at[feature, feature] = 1.0
    for left, right in pairs:
        value = train[[left, right]].corr(method="kendall").iloc[0, 1]
        kendall.at[left, right] = value
        kendall.at[right, left] = value
    kendall.to_csv(OUTPUT_DIR / "kendall_correlation_matrix.csv")
    kendall_flagged = _flagged_pairs(kendall, method="kendall")
    kendall_flagged.to_csv(OUTPUT_DIR / "kendall_flagged_pairs.csv", index=False)

    return {
        "pearson_features": len(features),
        "pearson_flagged_pairs": len(pearson_flagged),
        "spearman_features": len(spearman_columns),
        "spearman_flagged_pairs": len(spearman_flagged),
        "kendall_features": len(kendall_columns),
        "kendall_tested_pairs": len(pairs),
        "kendall_flagged_pairs": len(kendall_flagged),
        "flag_threshold_abs_correlation": CORRELATION_THRESHOLD,
        "method_note": (
            "Pairwise correlation cannot detect multivariate redundancy. "
            "The subsequent VIF analysis is required and is not optional."
        ),
    }


def usage_composition_audit(
    train: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    """Test whether pitch-type usage groups form exact sum-to-one identities."""
    rows: list[dict[str, object]] = []
    for hand in ("R", "L"):
        for window in ("P3", "P5", "P10"):
            columns = [
                f"{pitch_type}_usage_v{hand}_{window}"
                for pitch_type in PITCH_TYPES
                if f"{pitch_type}_usage_v{hand}_{window}" in features
            ]
            complete = train[columns].dropna()
            if complete.empty:
                rank = 0
                maximum_sum_error = np.nan
                mean_sum = np.nan
                rows_within_one_pct = 0
            else:
                values = complete.to_numpy(dtype=float)
                rank = int(np.linalg.matrix_rank(values))
                sums = values.sum(axis=1)
                maximum_sum_error = float(np.max(np.abs(sums - 1.0)))
                mean_sum = float(np.mean(sums))
                rows_within_one_pct = int((np.abs(sums - 1.0) <= 0.01).sum())
            rows.append(
                {
                    "group": f"usage_v{hand}_{window}",
                    "features": "|".join(columns),
                    "feature_count": len(columns),
                    "complete_rows": len(complete),
                    "matrix_rank": rank,
                    "mean_row_sum": mean_sum,
                    "max_abs_sum_minus_one": maximum_sum_error,
                    "rows_within_one_pct_of_sum_one": rows_within_one_pct,
                    "pct_rows_within_one_pct_of_sum_one": (
                        100.0 * rows_within_one_pct / len(complete)
                        if len(complete)
                        else np.nan
                    ),
                    "exact_sum_to_one": bool(
                        len(complete)
                        and maximum_sum_error <= 1e-12
                    ),
                    "composition_note": (
                        "An exact row sum of one makes the intercept plus all "
                        "usage shares rank-deficient."
                    ),
                }
            )
    return pd.DataFrame(rows)


def vif_table(train: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, int]:
    """Compute generalized VIF from a median-imputed standardized design.

    If the correlation matrix is singular, the Moore-Penrose pseudoinverse is
    used and the values are explicitly labeled generalized diagnostics.
    """
    numeric = train[features].astype(float)
    all_missing = numeric.columns[numeric.isna().all()].tolist()
    usable = [feature for feature in features if feature not in all_missing]
    imputed = numeric[usable].fillna(numeric[usable].median())
    standard_deviation = imputed.std(ddof=0)
    constant = standard_deviation[standard_deviation <= 1e-12].index.tolist()
    modeled = [feature for feature in usable if feature not in constant]
    standardized = (
        imputed[modeled] - imputed[modeled].mean()
    ) / imputed[modeled].std(ddof=0)
    correlation = standardized.corr().to_numpy(dtype=float)
    rank = int(np.linalg.matrix_rank(correlation))
    inverse = (
        np.linalg.inv(correlation)
        if rank == len(modeled)
        else np.linalg.pinv(correlation, hermitian=True)
    )
    generalized_vif = dict(zip(modeled, np.diag(inverse), strict=True))

    rows: list[dict[str, object]] = []
    for feature in features:
        if feature in all_missing:
            status = "all_missing"
            value = np.nan
        elif feature in constant:
            status = "constant_after_imputation"
            value = np.inf
        else:
            status = (
                "ordinary_vif"
                if rank == len(modeled)
                else "generalized_pseudoinverse_vif"
            )
            value = float(generalized_vif[feature])
        rows.append(
            {
                "feature": feature,
                "vif": value,
                "vif_above_5": bool(pd.notna(value) and value > 5),
                "vif_above_10": bool(pd.notna(value) and value > 10),
                "status": status,
                "design_rank": rank,
                "modeled_features": len(modeled),
            }
        )
    return (
        pd.DataFrame(rows).sort_values("vif", ascending=False, na_position="last"),
        rank,
    )


def _connected_components(
    nodes: list[str],
    pearson: pd.DataFrame,
) -> dict[str, str]:
    """Group serious-VIF features connected by |Pearson r| above threshold."""
    remaining = set(nodes)
    components: list[list[str]] = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        frontier = [seed]
        while frontier:
            left = frontier.pop()
            neighbors = {
                right
                for right in remaining
                if left in pearson.index
                and right in pearson.columns
                and pd.notna(pearson.at[left, right])
                and abs(pearson.at[left, right]) > CORRELATION_THRESHOLD
            }
            component.update(neighbors)
            remaining.difference_update(neighbors)
            frontier.extend(neighbors)
        components.append(sorted(component))
    components.sort(key=lambda values: (-len(values), values[0]))
    return {
        feature: f"VIF_{index:03d}"
        for index, component in enumerate(components, start=1)
        for feature in component
    }


def feature_family(feature: str) -> str:
    """Infer a stable high-level family from the current naming contract."""
    base = _base_name(feature)
    if feature.startswith("opp_lineup_"):
        return "lineup"
    if feature == "park_k_factor":
        return "park"
    if feature == "is_home":
        return "context"
    if "usage_" in base:
        return "pitch_usage"
    if re.match(rf"^({'|'.join(PITCH_TYPES)})_(velo|spinrate|ivb|hb|vaa)$", base):
        return "pitch_physics"
    if base in {"extension", "rel_x", "rel_z", "rel_x_sd", "rel_z_sd"}:
        return "mechanics"
    if "xfip" in base.lower() or base.lower() == "fip":
        return "fip_xfip"
    if base in {"xBA", "wOBA", "xwOBA"}:
        return "expected_contact"
    if base.endswith("_rate"):
        return "rates"
    return "other"


def feature_definition(feature: str) -> str:
    """Return a concise generated definition suitable for a research dictionary."""
    base = _base_name(feature)
    suffix_match = WINDOW_RE.search(feature)
    window = suffix_match.group(1) if suffix_match else "static"
    definitions = {
        "k_rate": "prior strikeouts / prior batters faced",
        "bb_rate": "prior walks / prior batters faced",
        "swstr_rate": "prior whiffs / prior pitches",
        "whiff_rate": "prior whiffs / prior swings",
        "ball_rate": "prior balls / prior pitches",
        "cs_rate": "prior called strikes / prior pitches",
        "chase_rate": "prior chases / prior out-of-zone pitches",
        "zone_rate": "prior in-zone pitches / prior pitches",
        "gb_rate": "prior ground balls / prior balls in play",
        "hr_rate": "prior home runs / prior batters faced",
    }
    detail = definitions.get(base, base.replace("_", " "))
    return f"{detail}; window={window}"


def source_function(feature: str) -> str:
    """Map a generated feature to the function that introduces its family."""
    family = feature_family(feature)
    if family == "lineup":
        return "Python.pipeline.training.opposing_lineup_features"
    if family == "park":
        return "Python.pipeline.training._join_park_factors"
    if family == "context":
        return "Python.pipeline.training.build_pitcher_training"
    return "Python.pitcher_rolling.add_rolling_pitcher_features"


def feature_dictionary(
    features: list[str],
    missingness: pd.DataFrame,
    vif: pd.DataFrame,
    pearson: pd.DataFrame,
) -> pd.DataFrame:
    """Build the pre-registry feature dictionary and VIF groups."""
    serious = vif.loc[vif["vif_above_10"], "feature"].tolist()
    clusters = _connected_components(serious, pearson)
    dictionary = pd.DataFrame(
        {
            "feature": features,
            "family": [feature_family(feature) for feature in features],
            "definition": [feature_definition(feature) for feature in features],
            "source_function": [source_function(feature) for feature in features],
            "vif_cluster": [clusters.get(feature, "") for feature in features],
        }
    )
    dictionary = dictionary.merge(
        missingness[["feature", "missing_pct"]], on="feature", how="left"
    ).merge(vif[["feature", "vif", "status"]], on="feature", how="left")
    return dictionary.sort_values(["family", "vif_cluster", "feature"])


def _finite_range(values: pd.Series) -> list[float] | None:
    finite = values[np.isfinite(values)]
    if finite.empty:
        return None
    return [float(finite.min()), float(finite.max())]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    train, features, split = load_training_partition()

    missingness = missingness_table(train, features)
    missingness.to_csv(OUTPUT_DIR / "feature_missingness.csv", index=False)

    dispersion = dispersion_table(train)
    dispersion.to_csv(OUTPUT_DIR / "dispersion_ratios.csv", index=False)

    correlation_summary = correlation_artifacts(train, features)

    usage = usage_composition_audit(train, features)
    usage.to_csv(OUTPUT_DIR / "usage_composition_rank_audit.csv", index=False)

    # Task sequencing is explicit: VIF grouping reloads Task 4's Pearson output.
    pearson = pd.read_csv(
        OUTPUT_DIR / "pearson_correlation_matrix.csv",
        index_col=0,
    )
    vif, design_rank = vif_table(train, features)
    vif.to_csv(OUTPUT_DIR / "vif.csv", index=False)

    dictionary = feature_dictionary(features, missingness, vif, pearson)
    dictionary.to_csv(OUTPUT_DIR / "feature_dictionary.csv", index=False)

    metadata = {
        "split": split,
        "eligible_features_after_deterministic_pruning": len(features),
        "correlation": correlation_summary,
        "vif": {
            "method": (
                "median-imputed standardized inverse-correlation VIF"
                if design_rank == int(vif["modeled_features"].max())
                else "median-imputed standardized correlation pseudoinverse"
            ),
            "design_rank": design_rank,
            "modeled_features": int(vif["modeled_features"].max()),
            "above_5": int(vif["vif_above_5"].sum()),
            "above_10": int(vif["vif_above_10"].sum()),
            "important_caveat": (
                "The de-duplicated design is full rank, so ordinary inverse-"
                "correlation VIF is defined. If a future design is rank deficient, "
                "the script falls back to pseudoinverse VIF as a severity "
                "diagnostic rather than an inferential coefficient statistic."
            ),
        },
        "missingness": {
            "above_20_pct": int((missingness["missing_pct"] > 20).sum()),
            "above_50_pct": int((missingness["missing_pct"] > 50).sum()),
            "above_80_pct": int((missingness["missing_pct"] > 80).sum()),
        },
        "dispersion": {
            "pa_bin_edges": [str(edge) for edge in PA_BIN_EDGES],
            "k_variance_ratio_range": _finite_range(
                dispersion["k_variance_ratio"]
            ),
            "k_rate_variance_ratio_range": _finite_range(
                dispersion["k_rate_variance_ratio"]
            ),
            "historical_report_claim": {
                "scope": "2023-2025, bin definition previously undocumented",
                "k_variance_ratio_range": [1.38, 1.53],
                "k_rate_variance_ratio_range": [1.35, 1.52],
            },
            "comparison_note": (
                "The historical cited ranges are not directly reproducible under "
                "the required corrected training-only scope because they used "
                "2023-2025 and did not document PA-bin edges. This run is the new "
                "reproducible definition; differences must not be silently edited."
            ),
        },
        "usage_composition": {
            "groups_audited": len(usage),
            "exact_sum_to_one_groups": int(usage["exact_sum_to_one"].sum()),
        },
    }
    (OUTPUT_DIR / "feature_diagnostics_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))
    print(f"Wrote diagnostics to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
