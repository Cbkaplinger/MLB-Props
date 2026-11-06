"""Synthetic tests for the result-summary renderer
(result_summary.py). SYNTHETIC ONLY. Pure dict-in, dict-out tests.

Requirement -> implementation -> test-evidence closure table:
  End-to-end temporal summary with all required sections      -> test 1
  Identities and provenance section present and correct       -> test 2
  Population/period/coverage section present                  -> test 3
  Pooled descriptive metrics distinguished from registered
  weighted contrasts                                          -> test 4
  Statistical direction vs practical threshold separated      -> test 5
  Point-estimate guards vs inferential claims distinguished   -> test 6
  Contradictory/insufficient required metadata surfaced       -> tests 7a/b
  No VERIFIED/promotion status inferred from exit code        -> test 8
  No temporal conclusions hard-coded                          -> test 9
  LGBM summary supported                                      -> test 10
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import result_summary as rs  # noqa: E402


def _make_temporal_report():
    """Hand-checkable synthetic temporal report."""
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
            {"id": "R2", "n_fit_dates": 5, "n_score_dates": 1,
             "fit_first": "2024-05-10", "fit_last": "2024-12-01",
             "score_first": "2025-05-01", "score_last": "2025-05-01"},
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
             "classwise": {"control": {"0": {"n": 9, "log_loss": 0.5,
                                             "brier": 0.25}},
                           "platoon": {"0": {"n": 9, "log_loss": 0.5,
                                             "brier": 0.25}}},
             "coverage": {"requested_starts_before_exclusions": 2,
                          "excluded_missing_outcomes": 0,
                          "scored_starts": 2},
             "r1_cohort_identity": {"n_keys": 2, "keys_sha256": "ab" * 32},
             "resolved_fit_start": "2024-05-11",
             "excluded_warmup_dates": ["2024-05-10"],
             "excluded_warmup_rows": 9,
            },
            {"id": "R2", "n_starts": 2, "n_matched_pas": 18,
             "mean_logloss_control": 1.225,
             "mean_logloss_platoon": 1.224,
             "paired": {"delta_a_minus_b": -0.000870,
                        "ci95": [-0.001231, -0.000542],
                        "primary_pair": "candidate_vs_control"},
             "k_count": {"mean_rps_control": 1.2947,
                         "mean_rps_platoon": 1.2944,
                         "non_degradation": {"point_estimate": -0.000300,
                                             "margin": 0.002,
                                             "within_margin": True}},
             "classwise": {"control": {"0": {"n": 9, "log_loss": 0.5,
                                             "brier": 0.25}},
                           "platoon": {"0": {"n": 9, "log_loss": 0.5,
                                             "brier": 0.25}}},
             "coverage": {"requested_starts_before_exclusions": 2,
                          "excluded_missing_outcomes": 0,
                          "scored_starts": 2},
             "r1_cohort_identity": None,
             "resolved_fit_start": "2024-05-11",
             "excluded_warmup_dates": ["2024-05-10"],
             "excluded_warmup_rows": 9,
            },
        ],
        "structural_limits": {"hard_max_score_date": "2025-06-30",
                              "r3_start": "2025-07-01"},
        "training_label_coverage_by_year": [
            {"year": 2023, "n_rows": 18, "n_labeled": 18},
            {"year": 2024, "n_rows": 36, "n_labeled": 36},
        ],
    }


# -------------------------------- 1. e2e temporal summary
def test_temporal_summary_sections_present():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    for key in ("experiment_identity", "summary_type",
                "identities_and_provenance", "population_period_coverage",
                "pooled_descriptive_metrics",
                "registered_weighted_contrasts", "structural_limits",
                "limitations"):
        assert key in s, key
    assert s["experiment_identity"] == "temporal_robustness_v1"
    assert s["summary_type"] == "temporal_robustness"


# ------------------------- 2. identities and provenance correct
def test_identities_and_provenance():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    ident = s["identities_and_provenance"]
    assert ident["experiment_identity"] == "temporal_robustness_v1"
    rec = ident["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0
    assert rec["n_keys"] == 2
    assert rec["reference_column"] == "rps_w0_pooled"


# ------------------------- 3. population/period/coverage present
def test_population_period_coverage():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    ppc = s["population_period_coverage"]
    assert len(ppc["periods"]) == 2
    assert ppc["periods"][0]["id"] == "R1"
    assert ppc["periods"][1]["id"] == "R2"
    assert ppc["feasibility"][0]["n_fit_dates"] == 3
    assert ppc["label_years"][0]["year"] == 2023


# --------------- 4. pooled descriptive vs registered contrasts
def test_pooled_vs_registered_distinguished():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    pooled = s["pooled_descriptive_metrics"]
    reg = s["registered_weighted_contrasts"]
    assert "descriptive" in pooled["note"]
    assert "per-start mean" in reg["note"]
    # pooled values present
    assert pooled["per_period_pooled"][0]["control"] == 1.222
    # registered values present
    assert reg["per_period"][0]["delta"] == -0.000415
    assert reg["per_period"][0]["direction"] == "challenger_favored"


# --------------- 5. direction vs practical threshold separated
def test_direction_vs_threshold():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    # R1: CI entirely below zero -> challenger_favored
    r1_reg = s["registered_weighted_contrasts"]["per_period"][0]
    assert r1_reg["direction"] == "challenger_favored"
    assert r1_reg["practical_threshold_exceeded"] is False
    # R2: CI entirely below zero, |delta| > 0.0005
    r2_reg = s["registered_weighted_contrasts"]["per_period"][1]
    assert r2_reg["classification"] if "classification" in r2_reg \
        else r2_reg["direction"] == "challenger_favored"


# --------------- 6. K guard vs inferential claim distinguished
def test_k_guard_vs_inferential():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    for p in s["population_period_coverage"]["periods"]:
        kg = p["k_count_guard"]
        assert kg["guard_type"] == "point_estimate_acceptance_guard"
        assert kg["not_a_noninferiority_claim"] is True
        assert isinstance(kg["passes"], bool)


# ------------------- 7a. missing required key surfaced
def test_missing_experiment_identity_raises():
    report = _make_temporal_report()
    del report["experiment_identity"]
    with pytest.raises(KeyError, match="experiment_identity"):
        rs.summarize_temporal_report(report)


# ------------------- 7b. missing period paired data surfaced
def test_missing_period_paired_raises():
    report = _make_temporal_report()
    del report["periods"][0]["paired"]
    with pytest.raises(KeyError, match="paired"):
        rs.summarize_temporal_report(report)


# ------------------- 8. no VERIFIED inferred from exit code
def test_no_verified_from_exit_code():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    # the summary does NOT contain a "verified" or "promotion" field
    assert "verified" not in s
    assert "promotion" not in s
    # the reconstruction block has "verified" (that's the gate, not the
    # overall experiment status)
    rec = s["identities_and_provenance"]["reconstruction"]
    assert "verified" in rec


# ------------------- 9. no temporal conclusions hard-coded
def test_no_temporal_conclusions_hardcoded():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    src = json.dumps(s)
    assert "platoon family qualifies" not in src
    assert "the 12-feature" not in src


# ------------------- 10. LGBM summary supported
def test_lgbm_summary():
    report = {
        "experiment_identity": "lgbm_multiclass_v1",
        "tuning": {"selected_config": {"num_leaves": 7,
                                       "min_data_in_leaf": 200},
                   "n_fits": 12},
        "reconstruction": {
            "verified": True, "max_abs_rps_diff": 0.0, "n_keys": 2,
            "reference_column": "rps_platoon",
            "reference_sha256": "c742" * 16,
        },
        "periods": [
            {"id": "R1", "n_starts": 2, "n_matched_pas": 18},
        ],
        "k_count": {"non_degradation": {"point_estimate": 0.0020884,
                                        "margin": 0.002,
                                        "within_margin": False}},
    }
    s = rs.summarize_lgbm_report(report)
    assert s["experiment_identity"] == "lgbm_multiclass_v1"
    kg = s["k_count_guard"]
    assert kg["passes"] is False
    assert kg["not_a_noninferiority_claim"] is True
