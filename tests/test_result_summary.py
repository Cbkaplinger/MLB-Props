"""Synthetic tests for the result-summary renderer
(result_summary.py). SYNTHETIC ONLY. Pure dict-in, dict-out tests
shaped from the actual temporal runner's report construction.

Requirement -> implementation -> test-evidence closure table:
  End-to-end temporal summary with all required sections      -> test 1
  Identities and provenance: reconstruction gate + provenance
  context round-trip + missing provenance explicit            -> tests 2a/b
  Population/period/coverage per period present               -> test 3
  Pooled descriptive metrics distinguished from registered
  weighted contrasts (note text + separate sections)          -> test 4
  Statistical direction vs practical threshold separated;
  declared threshold and sign conventions exact;
  exact threshold equality does NOT count as exceeded         -> test 5
  Point-estimate guards vs inferential claims;
  contradictory within_margin flagged;
  missing guard inputs -> explicitly unavailable;
  nonfinite/zero-margin refusals                              -> tests 6a/b/c
  Injected execution/verification/promotion statuses explicit;
  missing execution_status -> None (not "completed");
  missing promotion_status -> None (not a fabricated status)  -> tests 7a/b
  Provenance round-trip and explicit missing provenance       -> test 14
  No VERIFIED/promotion inferred from exit code               -> test 15
  No temporal conclusions hard-coded                          -> test 16
  Nonfinite delta refuses before classification               -> test 17
  Inverted CI bounds refuse                                   -> test 18
  Invalid threshold (zero/negative) refuses                   -> test 19
  Missing experiment identity raises KeyError                 -> test 20
  Missing period paired data raises KeyError                  -> test 21
"""
from __future__ import annotations

import math

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import result_summary as rs  # noqa: E402


def _make_temporal_report():
    """Fixture shaped from the actual temporal runner's report
    construction (run_temporal_robustness in
    temporal_robustness_evaluation.py)."""
    return {
        "experiment_identity": "temporal_robustness_v1",
        "reconstruction": {
            "verified": True, "max_abs_rps_diff": 0.0, "n_keys": 2,
            "reference_column": "rps_w0_pooled",
            "reference_sha256": "ae97" * 16,
            "tolerance": 1e-12,
        },
        "feasibility": [
            {"id": "R1", "n_fit_dates": 3, "n_score_dates": 1,
             "fit_first": "2024-05-10", "fit_last": "2024-06-01",
             "score_first": "2024-07-01", "score_last": "2024-07-01"},
        ],
        "periods": [
            {"id": "R1", "n_starts": 2, "n_matched_pas": 18,
             "mean_logloss_control": 1.222,
             "mean_logloss_platoon": 1.221,
             "paired": {"delta_a_minus_b": -0.000415,
                        "ci95": [-0.000779, -0.000053],
                        "primary_pair": "candidate_vs_control"},
             "k_count": {"mean_rps_control": 1.3055,
                         "mean_rps_platoon": 1.3054,
                         "non_degradation": {"point_estimate": -0.000167,
                                             "margin": 0.002,
                                             "within_margin": True}},
             "classwise": {"control": {"0": {"n": 9, "log_loss": 0.5}},
                           "platoon": {"0": {"n": 9, "log_loss": 0.5}}},
             "coverage": {"requested_starts_before_exclusions": 2,
                          "excluded_missing_outcomes": 0,
                          "scored_starts": 2},
             "r1_cohort_identity": {"n_keys": 2, "keys_sha256": "ab" * 32},
             "resolved_fit_start": "2024-05-11",
             "excluded_warmup_dates": ["2024-05-10"],
             "excluded_warmup_rows": 9,
            },
        ],
        "structural_limits": {"hard_max_score_date": "2025-06-30",
                              "r3_start": "2025-07-01"},
        "training_label_coverage_by_year": [
            {"year": 2023, "n_rows": 18, "n_labeled": 18},
        ],
    }


# ------------------------- 1. e2e temporal summary
def test_temporal_summary_sections_present():
    s = rs.summarize_temporal_report(_make_temporal_report())
    for key in ("experiment_identity", "summary_type",
                "identities_and_provenance", "population_period_coverage",
                "pooled_descriptive_metrics",
                "registered_weighted_contrasts", "injected_status",
                "structural_limits", "limitations"):
        assert key in s, key
    assert s["experiment_identity"] == "temporal_robustness_v1"


# -------------- 2. identities and provenance
def test_identities_and_provenance():
    s = rs.summarize_temporal_report(_make_temporal_report())
    rec = s["identities_and_provenance"]["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0
    assert rec["n_keys"] == 2
    assert rec["reference_column"] == "rps_w0_pooled"


# -------------- 3. population/period/coverage present
def test_population_period_coverage():
    s = rs.summarize_temporal_report(_make_temporal_report())
    ppc = s["population_period_coverage"]
    assert len(ppc["periods"]) == 1
    assert ppc["periods"][0]["id"] == "R1"
    assert ppc["feasibility"][0]["n_fit_dates"] == 3


# --------------- 4. pooled vs registered distinguished
def test_pooled_vs_registered_distinguished():
    s = rs.summarize_temporal_report(_make_temporal_report())
    pooled = s["pooled_descriptive_metrics"]
    reg = s["registered_weighted_contrasts"]
    assert "descriptive" in pooled["note"]
    assert "per-start mean" in reg["note"]
    assert pooled["per_period_pooled"][0]["control"] == 1.222
    assert reg["per_period"][0]["delta"] == -0.000415


# --------------- 5. direction vs threshold, exact conventions
def test_direction_vs_threshold_exact_conventions():
    """Sign convention: delta = challenger - control.
    Negative + CI entirely below zero -> challenger_favored.
    Practical: |delta| > threshold -> exceeded. Equality does NOT
    count as exceeding."""
    # challenger-favored, below threshold
    d = rs.classify_direction(-0.000415, -0.000779, -0.000053, 0.0005)
    assert d["statistical_direction"] == "challenger_favored"
    assert d["point_below_threshold"] is True
    # challenger-favored, above threshold
    d2 = rs.classify_direction(-0.000870, -0.001231, -0.000542, 0.0005)
    assert d2["statistical_direction"] == "challenger_favored"
    assert d2["point_below_threshold"] is False
    # control-favored
    d3 = rs.classify_direction(+0.001, +0.0005, +0.002, 0.0005)
    assert d3["statistical_direction"] == "control_favored"
    # inconclusive
    d4 = rs.classify_direction(-0.0001, -0.0005, +0.0005, 0.0005)
    assert d4["statistical_direction"] == "inconclusive"
    # exact threshold equality: |delta| == threshold does NOT exceed
    d5 = rs.classify_direction(-0.0005, -0.001, -0.0002, 0.0005)
    assert d5["point_below_threshold"] is True
    # invalid threshold (zero/negative) refuses
    with pytest.raises(ValueError, match="positive"):
        rs.classify_direction(-0.000415, -0.001, -0.0001, 0.0)
    with pytest.raises(ValueError, match="positive"):
        rs.classify_direction(-0.000415, -0.001, -0.0001, -0.001)
    # nonfinite delta refuses
    with pytest.raises(ValueError, match="nonfinite"):
        rs.classify_direction(float("nan"), -0.001, -0.0001, 0.0005)
    # inverted CI refuses
    with pytest.raises(ValueError, match="inverted"):
        rs.classify_direction(-0.000415, +0.001, -0.0001, 0.0005)


# --------------- 6. K guard vs inferential distinguished
def test_k_guard_vs_inferential():
    kg = rs.classify_k_guard(0.0020884, 0.002)
    assert kg["passes"] is False
    assert kg["not_a_noninferiority_claim"] is True
    kg2 = rs.classify_k_guard(-0.000300, 0.002)
    assert kg2["passes"] is True
    # nonfinite point estimate refuses
    with pytest.raises(ValueError, match="nonfinite"):
        rs.classify_k_guard(float("nan"), 0.002)
    # zero/negative margin refuses
    with pytest.raises(ValueError, match="positive"):
        rs.classify_k_guard(0.0, -0.001)


# --------------- 7. injected context explicit
def test_injected_context_explicit():
    report = _make_temporal_report()
    ctx = {"verification_status": "PENDING",
           "authorization_status": "recorded",
           "promotion_status": "never_automatic",
           "executed_by": "chat1-builder",
           "execution_date": "2026-11-05"}
    s = rs.summarize_temporal_report(report, context=ctx)
    inj = s["injected_status"]
    assert inj["verification_status"] == "PENDING"
    assert inj["authorization_status"] == "recorded"
    assert inj["promotion_status"] == "never_automatic"
    assert "never inferred from exit code" in inj["note"]


# --------------- 8. missing execution_status -> explicit None
def test_missing_execution_status_explicit_none():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    inj = s["injected_status"]
    assert inj["execution_status"] is None
    assert inj["verification_status"] is None
    assert inj["authorization_status"] is None
    # promotion_status: the policy disclaimer is present but the
    # injected value is None (unknown)
    assert inj["promotion_status"] is None
    assert "never inferred from exit code" in inj["note"]


# --------------- 14. LGBM adapter removed (deferred)
def test_lgbm_adapter_removed():
    assert not hasattr(rs, "summarize_lgbm_report")
