"""Scoring report v3 for the BF A/B 2026 seal package (corrected + completed).

v3 adds to the corrected v2 report:
  (a) RMSE of the collapsed-support mean-K for both arms in BOTH views
      (all-eligible 134; usable-B 11 = rows with arm_B_status "ok_confirmed"),
      frozen convention: mean over 24 buckets, bucket 23 = >=23 absorbing,
      meanK = sum(k * P[k]).
  (b) milestone Brier at K>=6, 8, 10, 12 for both arms both views:
      Brier = (P(K>=m) - 1{K>=m})^2, P(K>=m) = sum of buckets m..23 per the
      frozen convention (m=12 stays within exact support).
  (c) the complete pitcher-game actual_K records keyed "game_pk|pitcher"
      (carried from v2, 134 unique keys).

Provenance: the executed v2 runner was archived BEFORE any v3 edit to
C:\\Users\\ckaplinger\\MLB-Props-Research\\bf-ab-score-2026-v2\\runner_executed_v2_archive.py
(sha256 recorded in the report). The historical PRE-fix scoring source was
never preserved (unavailable), so this archive establishes current provenance
only and cannot retrospectively prove the pre-fix diff.

v3 imports and re-runs the v2 computation module unchanged, so the primary
RPS estimates/CIs and the verified secondaries (logscore/MAE/bias) are
identical to v2 by construction; the completeness check verifies max diff
0.0 against the preserved v2 report.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kcount_combiner as kc
import run_bf_ab_score_v2 as s2

V2_ARCHIVE = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\bf-ab-score-2026-v2"
    r"\runner_executed_v2_archive.py")
MILESTONES = (6, 8, 10, 12)


def mean_k(pmf: np.ndarray) -> float:
    """Collapsed-support mean: sum(k * P[k]) over 24 buckets, bucket 23
    treated as k=23 (absorbing >=23). Frozen convention."""
    pk = np.asarray(pmf, dtype=float)
    return float((pk * np.arange(len(pk))).sum())


def rmse_mean_k(pmfs: np.ndarray, K: np.ndarray) -> float:
    """RMSE between the frozen collapsed-support mean-K and actual K."""
    errs = np.array([mean_k(pmfs[i]) - float(K[i]) for i in range(len(K))])
    return float(np.sqrt(np.mean(errs ** 2)))


def milestone_brier_mean(pmfs: np.ndarray, K: np.ndarray,
                         milestones=MILESTONES) -> dict:
    """Mean milestone Brier over rows: (P(K>=m) - 1{K>=m})^2, with
    P(K>=m) = sum(pk[m:]) per the frozen collapsed-support convention."""
    out = {}
    for m in milestones:
        per_row = [float(kc.exceedance(pmfs[i], m)) for i in range(len(K))]
        briers = [(p_ge - (1.0 if int(K[i]) >= m else 0.0)) ** 2
                  for i, p_ge in enumerate(per_row)]
        out["ge%d" % m] = float(np.mean(briers))
    return out


def views(keys: list, A: np.ndarray, B: np.ndarray, K: np.ndarray) -> dict:
    """Both declared views: all-eligible 134 and usable-B 11."""
    usable = np.array([k["arm_B_status"] == "ok_confirmed" for k in keys])
    return {
        "all_eligible_134": {
            "n": int(len(K)),
            "A": {"rmse_meanK": rmse_mean_k(A, K),
                  "milestone_brier": milestone_brier_mean(A, K)},
            "B": {"rmse_meanK": rmse_mean_k(B, K),
                  "milestone_brier": milestone_brier_mean(B, K)},
        },
        "usable_B_11": {
            "n": int(usable.sum()),
            "A": {"rmse_meanK": rmse_mean_k(A[usable], K[usable]),
                  "milestone_brier": milestone_brier_mean(A[usable],
                                                          K[usable])},
            "B": {"rmse_meanK": rmse_mean_k(B[usable], K[usable]),
                  "milestone_brier": milestone_brier_mean(B[usable],
                                                          K[usable])},
        },
    }


def bootstrap_date_draw_fraction(keys: list) -> dict:
    """Reproduce the v2 usable-B bootstrap date draws (same seed, same
    procedure) and report the observed fraction of resamples that contain
    both distinct dates. With 2 distinct dates the effective independent
    denominator is 2 dates."""
    usable = [k for k in keys if k["arm_B_status"] == "ok_confirmed"]
    ds = np.array([k["forecast_cutoff"][:10] for k in usable])
    uds = np.unique(ds)
    rng = np.random.default_rng(20261001)
    both = 0
    for _ in range(2000):
        pick = rng.choice(uds, size=len(uds), replace=True)
        if len(np.unique(pick)) == len(uds):
            both += 1
    return {"n_dates": int(len(uds)),
            "dates": [str(u) for u in uds],
            "observed_both_dates_fraction": float(both / 2000.0),
            "effective_independent_denominator": int(len(uds))}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def correction_note(v2_stats: dict) -> dict:
    return {
        "v1_superseded_for": "outcome details/completeness (actual_K was "
                             "keyed by game_pk only in v1); scoring "
                             "statistics themselves were computed from the "
                             "correct per-(game_pk, pitcher) join",
        "primary_metrics_remain_valid": "primary RPS estimates/CIs "
                                        "(population_all, "
                                        "population_usable_B) and the "
                                        "previously verified secondaries "
                                        "(logscore/meanK_mae/meanK_bias) are "
                                        "unchanged and remain valid",
        "rmse_and_milestone_brier": "declared in the frozen plan but omitted "
                                    "from v1/v2 reporting; added in v3 for "
                                    "both arms in both views",
        "calibration_check": "no calibration check was declared in the "
                             "frozen plan and none was executed",
        "arm_A_is_i1_ref": "Arm A is I1_ref; no I3b or production-selection "
                           "decision follows from this report",
        "usable_B_two_dates": "usable-B inference rests on 2 dates; observed "
                              "bootstrap date-draw fraction and the "
                              "effective independent denominator are "
                              "reported under bootstrap_date_draw",
        "pre_fix_runner_history": "the historical PRE-fix scoring source was "
                                  "never preserved (unavailable); the v2 "
                                  "runner archive establishes current "
                                  "provenance only and cannot "
                                  "retrospectively prove the pre-fix diff",
        "affected_rows_v1_wrong_outcome": int(
            v2_stats["rows_with_wrong_v1_value"]),
        "v2_runner_archive": {"path": str(V2_ARCHIVE),
                              "sha256": sha256_file(V2_ARCHIVE)},
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal-dir", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seal = Path(a.seal_dir)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    v2_stats = s2.compute_stats(seal, Path(a.data_root))
    keys = json.load(open(seal / "row_keys.json"))
    A = np.load(seal / "arm_A_pmf.npy")
    B = np.load(seal / "arm_B_pmf.npy")
    K = np.array([v2_stats["actual_K"]["%s|%s" % (k["game_pk"],
                                                  k["pitcher"])]
                  for k in keys])
    rep = {
        "version": "v3",
        "seal_dir": str(seal),
        "population_all": v2_stats["population_all"],
        "population_usable_B": v2_stats["population_usable_B"],
        "secondary": v2_stats["secondary"],
        "actual_K": v2_stats["actual_K"],
        "v1_actual_K_by_game_pk": v2_stats["v1_actual_K_by_game_pk"],
        "rows_with_wrong_v1_value": v2_stats["rows_with_wrong_v1_value"],
        "unmatched": v2_stats["unmatched"],
        "n_rows": v2_stats["n_rows"],
        "rmse_and_milestone_brier": views(keys, A, B, K),
        "bootstrap_date_draw": bootstrap_date_draw_fraction(keys),
        "correction_note": correction_note(v2_stats),
        "note": v2_stats["note"],
    }
    (out / "scoring_report_v3.json").write_text(
        json.dumps(rep, indent=1), encoding="ascii")
    print(json.dumps({
        "out": str(out / "scoring_report_v3.json"),
        "n_actual_K_keys": len(rep["actual_K"]),
        "rows_with_wrong_v1_value": rep["rows_with_wrong_v1_value"],
        "usable_B_n": rep["rmse_and_milestone_brier"]["usable_B_11"]["n"],
        "bootstrap_both_dates_fraction":
            rep["bootstrap_date_draw"]["observed_both_dates_fraction"],
    }, indent=1))


if __name__ == "__main__":
    main()
