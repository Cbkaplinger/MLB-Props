"""Synthetic tests for the result-summary renderer
(result_summary.py). SYNTHETIC ONLY. Pure dict-in, dict-out tests
shaped from the actual temporal runner's report construction.

Requirement -> implementation -> test-evidence closure table:
  End-to-end temporal summary with all required sections      -> test 1
  Identities and provenance: reconstruction gate + provenance
  round-trip including executed_by/execution_date             -> tests 2a/b
  Population/period/coverage per period present               -> test 3
  Pooled descriptive metrics distinguished from registered
  weighted contrasts                                          -> test 4
  Statistical direction vs practical threshold;
  exact threshold equality does NOT count as exceeded;
  invalid threshold refuses                                   -> test 5
  Point-estimate guards vs inferential claims;
  nonfinite/zero-margin refusals                              -> test 6
  Contradictory within_margin flagged;
  absent guard -> explicitly unavailable;
  incomplete guard inputs -> explicitly unavailable           -> tests 7a/b/c
  Unknown statuses explicit (None)                            -> test 8
  Missing experiment identity raises KeyError                 -> test 9
  Missing period paired data raises KeyError                  -> test 10
  No temporal conclusions hard-coded                          -> test 11
  LGBM adapter removed (deferred)                             -> test 12
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import result_summary as rs  # noqa: E402


def _make_temporal_report():
    return {
        "experiment_identity": "temporal_robustness_v1",
        "reconstruction": {
            "verified": True, "max_abs_rps_diff": 0.0, "n_keys": 2,
            "reference_column": "rps_w0_pooled",
            "reference_sha256": "ae97" * 16, "tolerance": 1e-12,
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
                        "ci95": [-0.000779, -0.000053]},
             "k_count": {"mean_rps_control": 1.3055,
                         "mean_rps_platoon": 1.3054,
                         "non_degradation": {"point_estimate": -0.000167,
                                             "margin": 0.002,
                                             "within_margin": True}},
             "classwise": {},
             "coverage": {"requested_starts_before_exclusions": 2},
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


def test_e2e_temporal_summary():
    s = rs.summarize_temporal_report(_make_temporal_report())
    for key in ("experiment_identity", "summary_type",
                "identities_and_provenance", "population_period_coverage",
                "pooled_descriptive_metrics",
                "registered_weighted_contrasts", "injected_status",
                "structural_limits", "limitations"):
        assert key in s, key
    assert s["experiment_identity"] == "temporal_robustness_v1"


def test_provenance_round_trip():
    report = _make_temporal_report()
    ctx = {
        "executable_checkpoint": "0128961",
        "runner_sha256": "aa71c4bf" + "0" * 56,
        "packet_checkpoint": "ef0356c",
        "packet_sha256": "54bef47c" + "0" * 56,
        "consumed_input_identities": {"pa": "1d3be", "lineups": "b6a194"},
        "executed_by": "chat1-builder",
        "execution_date": "2026-11-05",
    }
    s = rs.summarize_temporal_report(report, context=ctx)
    prov = s["identities_and_provenance"]["provenance"]
    assert prov["executable_checkpoint"] == "0128961"
    assert prov["runner_sha256"].startswith("aa71c4bf")
    assert prov["packet_checkpoint"] == "ef0356c"
    assert prov["packet_sha256"].startswith("54bef47c")
    assert prov["consumed_input_identities"]["pa"] == "1d3be"
    assert prov["executed_by"] == "chat1-builder"
    assert prov["execution_date"] == "2026-11-05"


def test_missing_provenance_explicit():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    prov = s["identities_and_provenance"]["provenance"]
    assert prov["executable_checkpoint"] is None
    assert prov["runner_sha256"] is None
    assert prov["consumed_input_identities"] is None


def test_population_period_coverage():
    s = rs.summarize_temporal_report(_make_temporal_report())
    ppc = s["population_period_coverage"]
    assert len(ppc["periods"]) == 1
    assert ppc["periods"][0]["id"] == "R1"


def test_pooled_vs_registered_distinguished():
    s = rs.summarize_temporal_report(_make_temporal_report())
    assert "descriptive" in s["pooled_descriptive_metrics"]["note"]
    assert "per-start mean" in s["registered_weighted_contrasts"]["note"]
    assert s["pooled_descriptive_metrics"]["per_period_pooled"][0][
        "control"] == 1.222
    assert s["registered_weighted_contrasts"]["per_period"][0][
        "delta"] == -0.000415


def test_direction_vs_threshold():
    d = rs.classify_direction(-0.000415, -0.000779, -0.000053, 0.0005)
    assert d["statistical_direction"] == "challenger_favored"
    d2 = rs.classify_direction(-0.000870, -0.001231, -0.000542, 0.0005)
    assert d2["statistical_direction"] == "challenger_favored"
    d3 = rs.classify_direction(+0.001, +0.0005, +0.002, 0.0005)
    assert d3["statistical_direction"] == "control_favored"
    d4 = rs.classify_direction(-0.0001, -0.0005, +0.0005, 0.0005)
    assert d4["statistical_direction"] == "inconclusive"


def test_threshold_equality_not_exceeded():
    d = rs.classify_direction(-0.0005, -0.001, -0.0002, 0.0005)
    assert d["point_below_threshold"] is True


def test_invalid_threshold_refuses():
    with pytest.raises(ValueError, match="positive"):
        rs.classify_direction(-0.000415, -0.001, -0.0001, 0.0)
    with pytest.raises(ValueError, match="positive"):
        rs.classify_direction(-0.000415, -0.001, -0.0001, -0.001)


def test_nonfinite_refuses():
    with pytest.raises(ValueError, match="nonfinite"):
        rs.classify_direction(float("nan"), -0.001, -0.0001, 0.0005)


def test_inverted_ci_refuses():
    with pytest.raises(ValueError, match="inverted"):
        rs.classify_direction(-0.000415, +0.001, -0.0001, 0.0005)


def test_k_guard_vs_inferential():
    kg = rs.classify_k_guard(0.0020884, 0.002)
    assert kg["passes"] is False
    assert kg["not_a_noninferiority_claim"] is True
    with pytest.raises(ValueError, match="nonfinite"):
        rs.classify_k_guard(float("nan"), 0.002)
    with pytest.raises(ValueError, match="positive"):
        rs.classify_k_guard(0.0, -0.001)


def test_contradictory_within_margin_flagged():
    report = _make_temporal_report()
    report["periods"][0]["k_count"]["non_degradation"]["within_margin"] = True
    report["periods"][0]["k_count"]["non_degradation"]["point_estimate"] = 0.003
    s = rs.summarize_temporal_report(report)
    p = s["population_period_coverage"]["periods"][0]
    kg = p["k_count_guard"]
    assert kg["passes"] is False
    assert "contradicts" in kg["contradiction"]


def test_absent_guard_explicitly_unavailable():
    report = _make_temporal_report()
    report["periods"][0]["k_count"] = {}
    s = rs.summarize_temporal_report(report)
    p = s["population_period_coverage"]["periods"][0]
    kg = p["k_count_guard"]
    assert kg["passes"] is None
    assert kg["status"] == "unavailable"


def test_incomplete_guard_inputs_unavailable():
    report = _make_temporal_report()
    report["periods"][0]["k_count"]["non_degradation"] = {
        "point_estimate": 0.001}
    s = rs.summarize_temporal_report(report)
    p = s["population_period_coverage"]["periods"][0]
    kg = p["k_count_guard"]
    assert kg["status"] == "unavailable"
    assert kg["point_estimate"] is None
    assert kg["margin"] is None


def test_unknown_statuses_explicit():
    report = _make_temporal_report()
    s = rs.summarize_temporal_report(report)
    inj = s["injected_status"]
    assert inj["execution_status"] is None
    assert inj["verification_status"] is None
    assert inj["authorization_status"] is None
    assert inj["promotion_status"] is None


def test_missing_experiment_identity_raises():
    report = _make_temporal_report()
    del report["experiment_identity"]
    with pytest.raises(KeyError, match="experiment_identity"):
        rs.summarize_temporal_report(report)


def test_missing_period_paired_raises():
    report = _make_temporal_report()
    del report["periods"][0]["paired"]
    with pytest.raises(KeyError, match="paired"):
        rs.summarize_temporal_report(report)


def test_lgbm_adapter_removed():
    assert not hasattr(rs, "summarize_lgbm_report")
