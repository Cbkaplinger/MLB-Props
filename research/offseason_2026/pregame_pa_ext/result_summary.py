"""Reusable result-summary renderer for declared experiment reports.

SYNTHETIC-TESTED ONLY. Pure functions over injected dicts; no I/O, no
model code, no new dependency.

Reads a declared report JSON (from temporal_robustness_evaluation.py,
platoon_comparison.py, lgbm_multiclass_comparison.py, or
binary_k_comparison.py) and returns a structured summary dict that
distinguishes:

- identities and provenance;
- population/period/coverage;
- pooled descriptive metrics vs registered weighted contrasts;
- statistical direction vs practical threshold;
- point-estimate guards vs inferential claims;
- execution, verification, and promotion status;
- development/exposure limitations.

Does NOT infer VERIFIED or promotion status from exit code alone.
Does NOT hard-code temporal conclusions into a generic renderer.
"""
from __future__ import annotations

PRACTICAL_LOGLOSS_THRESHOLD = 0.0005
K_GUARD_MARGIN = 0.002

_REQUIRED_KEYS = {"experiment_identity"}
_REQUIRED_PERIOD_KEYS = {"id", "paired"}


def _require(d: dict, keys: set, ctx: str) -> None:
    missing = keys - set(d.keys())
    if missing:
        raise KeyError(f"{ctx}: missing required key(s) {sorted(missing)}")


def classify_direction(delta: float, ci_low: float, ci_high: float,
                       practical_threshold: float) -> dict:
    """Separate statistical direction from practical magnitude."""
    if ci_high < 0:
        direction = "challenger_favored"
    elif ci_low > 0:
        direction = "control_favored"
    else:
        direction = "inconclusive"
    return {
        "statistical_direction": direction,
        "point_estimate": delta,
        "ci95": [ci_low, ci_high],
        "practical_threshold": practical_threshold,
        "point_below_threshold": abs(delta) < practical_threshold,
        "note": ("statistical direction and practical magnitude are "
                 "reported separately; point below threshold does not "
                 "justify complexity regardless of CI direction"),
    }


def classify_k_guard(point_estimate: float, margin: float) -> dict:
    """Separate the point-estimate acceptance guard from inferential
    claims."""
    return {
        "guard_type": "point_estimate_acceptance_guard",
        "margin": margin,
        "point_estimate": point_estimate,
        "passes": point_estimate <= margin,
        "not_a_noninferiority_claim": True,
        "note": ("point-estimate acceptance guard; NOT a statistical "
                 "noninferiority test; CI reported as context"),
    }


def summarize_temporal_report(report: dict) -> dict:
    """Render a structured comparison summary from a
    temporal_robustness_report.json dict.

    Raises on missing/insufficient required metadata. Does not modify
    the input; does not infer VERIFIED or promotion status.
    """
    _require(report, _REQUIRED_KEYS, "report")

    periods_raw = report.get("periods", [])
    if not periods_raw:
        raise ValueError("report has no periods")

    periods_out = []
    for p in periods_raw:
        _require(p, _REQUIRED_PERIOD_KEYS, f"period {p.get('id', '?')}")
        paired = p["paired"]
        _require(paired, {"delta_a_minus_b", "ci95"}, f"period {p['id']} paired")

        delta = paired["delta_a_minus_b"]
        ci = paired["ci95"]
        direction = classify_direction(delta, ci[0], ci[1],
                                       PRACTICAL_LOGLOSS_THRESHOLD)

        kc = p.get("k_count", {})
        nd = kc.get("non_degradation", {})
        k_guard = classify_k_guard(
            nd.get("point_estimate", float("nan")),
            nd.get("margin", K_GUARD_MARGIN)) if nd else None

        coverage = p.get("coverage", {})
        r1_ident = p.get("r1_cohort_identity")

        periods_out.append({
            "id": p["id"],
            "n_starts": p["n_starts"],
            "n_matched_pas": p["n_matched_pas"],
            "resolved_fit_start": p.get("resolved_fit_start"),
            "coverage": coverage,
            "r1_cohort_identity": r1_ident,
            "pooled_pa_logloss": {
                "control": p["mean_logloss_control"],
                "platoon": p["mean_logloss_platoon"],
                "note": "pooled descriptive means; NOT the contrast "
                        "statistic",
            },
            "registered_contrast": {
                "delta": delta,
                "ci95": ci,
                "classification": direction,
                "practical_threshold_exceeded":
                    abs(delta) >= PRACTICAL_LOGLOSS_THRESHOLD,
            },
            "k_count_guard": k_guard,
            "classwise": p.get("classwise"),
        })

    recon = report.get("reconstruction", {})
    feasibility = report.get("feasibility", [])
    label_years = report.get("training_label_coverage_by_year", [])
    structural = report.get("structural_limits", {})

    return {
        "experiment_identity": report["experiment_identity"],
        "summary_type": "temporal_robustness",
        "identities_and_provenance": {
            "experiment_identity": report["experiment_identity"],
            "reconstruction": reconstruction_summary(recon),
        },
        "population_period_coverage": {
            "periods": periods_out,
            "feasibility": feasibility,
            "label_years": label_years,
        },
        "pooled_descriptive_metrics": {
            "note": ("pooled PA log-loss levels are descriptive; the "
                     "registered contrast statistic is the per-start "
                     "mean paired delta"),
            "per_period_pooled": [
                {"id": p["id"],
                 "control": p["pooled_pa_logloss"]["control"],
                 "platoon": p["pooled_pa_logloss"]["platoon"]}
                for p in periods_out
            ],
        },
            "registered_weighted_contrasts": {
            "note": ("contrast statistic = per-start mean of per-PA log "
                     "loss; each start equally weighted, PAs equally "
                     "weighted within a start"),
            "per_period": [
                {"id": p["id"],
                 "delta": p["registered_contrast"]["delta"],
                 "ci95": p["registered_contrast"]["ci95"],
                 "direction":
                     p["registered_contrast"]["classification"][
                         "statistical_direction"],
                 "practical_threshold_exceeded":
                     p["registered_contrast"][
                         "practical_threshold_exceeded"]}
                for p in periods_out
            ],
        },
        "structural_limits": structural,
        "limitations": (
            "development evidence on the registered source; R1/R2 score "
            "windows are EXPOSED - NOT fresh final tests; matched-"
            "matchup PA coverage limitation carries over; 2026 untouched"),
    }


def reconstruction_summary(recon: dict) -> dict:
    _require(recon, {"verified", "max_abs_rps_diff", "n_keys",
                     "reference_column", "reference_sha256"},
             "reconstruction")
    return {
        "verified": recon["verified"],
        "max_abs_rps_diff": recon["max_abs_rps_diff"],
        "n_keys": recon["n_keys"],
        "reference_column": recon["reference_column"],
        "reference_sha256": recon["reference_sha256"],
        "tolerance": recon.get("tolerance"),
    }


def summarize_lgbm_report(report: dict) -> dict:
    """Render a structured comparison summary from an
    lgbm_comparison_report.json dict.

    Raises on missing/insufficient required metadata. Does not modify
    the input; does not infer VERIFIED or promotion status.
    """
    _require(report, {"experiment_identity", "tuning"}, "report")

    periods = report.get("periods", [])
    tuning = report.get("tuning", {})
    recon = report.get("reconstruction", {})

    k_count = report.get("k_count", {})
    nd = k_count.get("non_degradation", {})
    k_guard = classify_k_guard(
        nd.get("point_estimate", float("nan")),
        nd.get("margin", K_GUARD_MARGIN)) if nd else None

    return {
        "experiment_identity": report["experiment_identity"],
        "summary_type": "lgbm_multiclass",
        "identities_and_provenance": {
            "experiment_identity": report["experiment_identity"],
            "reconstruction": reconstruction_summary(recon),
            "tuning_selected_config": tuning.get("selected_config"),
            "tuning_n_fits": tuning.get("n_fits"),
        },
        "population_period_coverage": {
            "periods": [
                {"id": p["id"], "n_starts": p["n_starts"],
                 "n_matched_pas": p["n_matched_pas"]}
                for p in periods
            ],
        },
        "k_count_guard": k_guard,
        "limitations": (
            "development evidence on the registered 2025H1 cohort; "
            "equal-information design; small chronological tuning "
            "budget; no production, betting-value, or causal claims"),
    }
