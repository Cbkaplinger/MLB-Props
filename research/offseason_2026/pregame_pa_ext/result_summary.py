"""Reusable result-summary renderer for the declared temporal-robustness
report schema.

SYNTHETIC-TESTED ONLY. Pure dict-in, dict-out functions; no I/O, no
model code, no new dependency.

Reads a declared report JSON (from temporal_robustness_evaluation.py)
and returns a structured summary dict that distinguishes:

- identities and provenance;
- population/period/coverage;
- pooled descriptive metrics vs registered weighted contrasts;
- statistical direction vs practical threshold;
- point-estimate guards vs inferential claims;
- execution, verification, and promotion statuses (explicitly
  injected; never inferred from process completion);
- development/exposure limitations.

Missing information is explicit; never inferred. Metadata used for
classifications is validated (nonfinite/inconsistent values refuse).
Matches the declared threshold and sign conventions exactly.

The retained recipe (12-feature multinomial-plus-platoon) is fixed.
No new framework, dependency, CLI, real-data execution, raw-data
access, or scientific experiment.
"""
from __future__ import annotations

import math

PRACTICAL_LOGLOSS_THRESHOLD = 0.0005
K_GUARD_MARGIN = 0.002

_REQUIRED_REPORT_KEYS = {"experiment_identity", "reconstruction",
                         "periods"}


def _require(d: dict, keys: set, ctx: str) -> None:
    missing = keys - set(d.keys())
    if missing:
        raise KeyError(f"{ctx}: missing required key(s) {sorted(missing)}")


def _require_finite(value, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name}: expected numeric, got {type(value).__name__}")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name}: nonfinite value {v}")
    return v


def classify_direction(delta: float, ci_low: float, ci_high: float,
                       practical_threshold: float) -> dict:
    """Separate statistical direction from practical magnitude.

    Sign convention: delta = challenger - control.
    Negative delta favors the challenger; positive favors the control.
    CI entirely below zero -> challenger_favored; entirely above ->
    control_favored; overlapping zero -> inconclusive.
    Practical magnitude: |delta| >= practical_threshold -> exceeded.
    """
    delta = _require_finite(delta, "delta")
    ci_low = _require_finite(ci_low, "ci_low")
    ci_high = _require_finite(ci_high, "ci_high")
    if ci_low > ci_high:
        raise ValueError(f"CI bounds inverted: low={ci_low} > high={ci_high}")
    if ci_high < 0:
        direction = "challenger_favored"
    elif ci_low > 0:
        direction = "control_favored"
    else:
        direction = "inconclusive"
    below_threshold = abs(delta) < practical_threshold
    return {
        "statistical_direction": direction,
        "point_estimate": delta,
        "ci95": [ci_low, ci_high],
        "practical_threshold": practical_threshold,
        "point_below_threshold": below_threshold,
        "note": ("statistical direction and practical magnitude are "
                 "reported separately; point below threshold does not "
                 "justify complexity regardless of CI direction"),
    }


def classify_k_guard(point_estimate: float, margin: float) -> dict:
    """Separate the point-estimate acceptance guard from inferential
    claims."""
    point_estimate = _require_finite(point_estimate, "point_estimate")
    margin = _require_finite(margin, "margin")
    if margin <= 0:
        raise ValueError(f"K guard margin must be positive, got {margin}")
    return {
        "guard_type": "point_estimate_acceptance_guard",
        "margin": margin,
        "point_estimate": point_estimate,
        "passes": point_estimate <= margin,
        "not_a_noninferiority_claim": True,
        "note": ("point-estimate acceptance guard; NOT a statistical "
                 "noninferiority test; CI reported as context"),
    }


def summarize_temporal_report(report: dict, *,
                              context: dict | None = None) -> dict:
    """Render a structured comparison summary from a
    temporal_robustness_report.json dict.

    `context` (optional, injected): explicit provenance and status
    fields that the report itself does not carry. Missing context
    fields are surfaced as explicit nulls; never inferred.

    Expected context keys (all optional):
      "executed_by": str (who ran the command)
      "execution_date": str
      "verification_status": str | None ("VERIFIED", "PENDING", etc.)
      "authorization_status": str | None
      "promotion_status": str | None
      "pr_status": str | None (open, merged, etc.)
      "pr_number": int | None
    """
    _require(report, _REQUIRED_REPORT_KEYS, "report")

    periods_raw = report.get("periods", [])
    if not periods_raw:
        raise ValueError("report has no periods")

    ctx = context or {}
    injected_status = {
        "execution_status": ctx.get("execution_status", "completed"),
        "verification_status": ctx.get("verification_status"),
        "authorization_status": ctx.get("authorization_status"),
        "promotion_status": ctx.get("promotion_status", "never_automatic"),
        "note": ("verification/authorization/promotion statuses are "
                 "explicitly injected; never inferred from exit code "
                 "or process completion"),
    }

    periods_out = []
    for p in periods_raw:
        _require(p, {"id", "paired"}, f"period {p.get('id', '?')}")
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

        pooled_pa = p.get("pooled_pa_logloss", {})
        ctrl_ll = pooled_pa.get("control", p.get("mean_logloss_control"))
        plat_ll = pooled_pa.get("platoon", p.get("mean_logloss_platoon"))
        for v in (ctrl_ll, plat_ll):
            if v is not None:
                _require_finite(v, "pooled_pa_logloss")

        periods_out.append({
            "id": p["id"],
            "n_starts": p["n_starts"],
            "n_matched_pas": p["n_matched_pas"],
            "resolved_fit_start": p.get("resolved_fit_start"),
            "coverage": p.get("coverage"),
            "r1_cohort_identity": p.get("r1_cohort_identity"),
            "pooled_pa_logloss": {
                "control": ctrl_ll,
                "platoon": plat_ll,
                "note": ("pooled descriptive means; NOT the contrast "
                         "statistic"),
            },
            "registered_contrast": {
                "delta": delta,
                "ci95": ci,
                "direction": direction["statistical_direction"],
                "practical_threshold_exceeded":
                    direction["point_below_threshold"] is False and
                    abs(delta) >= PRACTICAL_LOGLOSS_THRESHOLD,
                "point_below_threshold":
                    direction["point_below_threshold"],
            },
            "k_count_guard": k_guard,
            "classwise": p.get("classwise"),
        })

    recon = report.get("reconstruction", {})
    _require(recon, {"verified", "max_abs_rps_diff", "n_keys",
                     "reference_column", "reference_sha256"},
             "reconstruction")

    return {
        "experiment_identity": report["experiment_identity"],
        "summary_type": "temporal_robustness",
        "identities_and_provenance": {
            "experiment_identity": report["experiment_identity"],
            "reconstruction": {
                "verified": recon["verified"],
                "max_abs_rps_diff": recon["max_abs_rps_diff"],
                "n_keys": recon["n_keys"],
                "reference_column": recon["reference_column"],
                "reference_sha256": recon["reference_sha256"],
                "tolerance": recon.get("tolerance"),
            },
        },
        "population_period_coverage": {
            "periods": periods_out,
            "feasibility": report.get("feasibility", []),
            "label_years": report.get("training_label_coverage_by_year", []),
        },
        "pooled_descriptive_metrics": {
            "note": ("pooled PA log-loss levels are descriptive; the "
                     "registered contrast statistic is the per-start "
                     "mean paired delta"),
            "per_period_pooled": [
                {"id": po["id"],
                 "control": po["pooled_pa_logloss"]["control"],
                 "platoon": po["pooled_pa_logloss"]["platoon"]}
                for po in periods_out
            ],
        },
        "registered_weighted_contrasts": {
            "note": ("contrast statistic = per-start mean of per-PA log "
                     "loss; each start equally weighted, PAs equally "
                     "weighted within a start"),
            "per_period": [
                {"id": po["id"],
                 "delta": po["registered_contrast"]["delta"],
                 "ci95": po["registered_contrast"]["ci95"],
                 "direction":
                     po["registered_contrast"]["direction"],
                 "practical_threshold_exceeded":
                     po["registered_contrast"][
                         "practical_threshold_exceeded"]}
                for po in periods_out
            ],
        },
        "injected_status": injected_status,
        "structural_limits": report.get("structural_limits", {}),
        "limitations": (
            "development evidence on the registered source; R1/R2 score "
            "windows are EXPOSED - NOT fresh final tests; matched-"
            "matchup PA coverage limitation carries over; 2026 untouched"),
    }
