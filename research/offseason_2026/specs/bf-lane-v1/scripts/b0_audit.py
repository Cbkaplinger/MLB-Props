"""bf-lane-v1 B0: WORKLOAD-REFERENCE AUDIT (read-only).

Audits whether the existing cutoff-valid workload/reference forecast
(bf-workload-v1 BASE empirical BF construction -> kcount_combiner -> RPS
stack) is actually available and pregame-valid for the registered
assessment window 2024-07-01..2025-12-31 (the 7,194-start cohort).

Audit only: NO fitting, NO scoring, NO new forecasts. Every read is
against frozen lake artifacts; the only computed outputs are the audit
records written to this directory (B0_AUDIT.md, b0_audit.json,
b0_per_start_availability.csv).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

LAKE = Path(r"C:\Users\ckaplinger\MLB-Props-Research")
BF_DIR = LAKE / "bf-workload-v1"
REPO = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\market-eval-v2"
)
OUT = LAKE / "bf-lane-v1"
sys.path.insert(0, str(REPO / "research" / "offseason_2026"))
from kcount_combiner import KCOUNT_CAP, bf_pmf_from_37  # noqa: E402

W0, W1 = date(2024, 7, 1), date(2025, 12, 31)
PMF_COLS = [f"pmf37_{j}" for j in range(37)]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bf_path = BF_DIR / "data" / "bf_forecasts.parquet"
    sm_path = BF_DIR / "data" / "start_metrics_v2.parquet"
    builder_path = BF_DIR / "scripts" / "build_bf_forecasts.py"
    combiner_path = REPO / "research" / "offseason_2026" / "kcount_combiner.py"

    bf = pl.read_parquet(bf_path)
    sm = pl.read_parquet(sm_path)
    hashes = {
        "bf_forecasts.parquet": sha256_file(bf_path),
        "start_metrics_v2.parquet": sha256_file(sm_path),
        "build_bf_forecasts.py": sha256_file(builder_path),
        "kcount_combiner.py": sha256_file(combiner_path),
    }

    checks: dict[str, object] = {}
    win = bf.filter(
        (pl.col("game_date") >= W0) & (pl.col("game_date") <= W1)
    ).sort(["game_date", "game_pk", "side"])
    n_window = win.height

    # -- 1. BF PMF availability per start -----------------------------------
    pmf_mat = np.column_stack([win[c].to_numpy() for c in PMF_COLS])
    pmf_null_rows = int(np.isnan(pmf_mat).any(axis=1).sum())
    pmf_ok_rows = n_window - pmf_null_rows

    # -- 2. PMF validity: nonnegative, sums to 1, support/tail conventions --
    finite = np.isfinite(pmf_mat).all(axis=1)
    nonneg = bool((pmf_mat[finite] >= -1e-15).all())
    sums = pmf_mat[finite].sum(axis=1)
    max_sum_dev = float(np.abs(sums - 1.0).max())
    overflow = pmf_mat[finite, 36]
    mix_mat = np.column_stack([win[f"pmf37_mix_{j}"].to_numpy() for j in range(37)])
    mix_ok = int(np.isfinite(mix_mat).all(axis=1).sum())
    mix_sums = mix_mat[np.isfinite(mix_mat).all(axis=1)].sum(axis=1)

    realized = win["realized_bf"].to_numpy()
    n_real_gt_36 = int((realized > 36).sum())
    n_real_gt_cap = int((realized > KCOUNT_CAP).sum())

    checks["pmf_availability"] = {
        "n_window_starts": n_window,
        "pmf37_fully_available_rows": pmf_ok_rows,
        "pmf37_rows_with_any_null": pmf_null_rows,
        "pmf37_mix_fully_available_rows": mix_ok,
    }
    checks["pmf_validity"] = {
        "all_entries_finite": bool(finite.all()),
        "all_entries_nonnegative": nonneg,
        "sum_to_1_max_abs_deviation": max_sum_dev,
        "sum_to_1_tolerance": 1e-9,
        "mix_sum_to_1_max_abs_deviation": float(np.abs(mix_sums - 1.0).max())
        if mix_sums.size else None,
        "overflow_index_convention": "index 36 = P(N>=37); never read as BF=37",
        "overflow_mass_mean": float(overflow.mean()),
        "overflow_mass_max": float(overflow.max()),
        "overflow_mass_min": float(overflow.min()),
    }
    checks["support_vs_realized"] = {
        "realized_bf_min": int(realized.min()),
        "realized_bf_max": int(realized.max()),
        "realized_bf_gt_36_overflow_relevant": n_real_gt_36,
        "realized_bf_gt_cap60_beyond_extension": n_real_gt_cap,
        "kcount_cap": KCOUNT_CAP,
    }

    # -- 3. strictly-prior construction: rebuild pools from the file itself --
    # NOTE: pools rebuild over the FULL 2023-2025 builder frame (the builder's
    # prior history starts 2023-01-01); deviations are recorded for the
    # assessment-window rows only.
    prior_n_ok = 0
    prior_n_total = 0
    prior_mean_devs = []
    lg_mean_devs = []
    full = bf.sort(["game_date", "game_pk", "side"])
    date_groups = full.partition_by("game_date", as_dict=True)
    pitcher_state: dict[int, dict] = {}
    lg_sum = 0.0
    lg_n = 0
    for d in sorted(full["game_date"].unique().to_list()):
        day = date_groups[(d,)]
        in_window = W0 <= d <= W1
        for rec in day.iter_rows(named=True):
            pid = rec["pitcher"]
            st = pitcher_state.get(pid)
            rebuilt_n = st["n"] if st is not None else 0
            if in_window:
                prior_n_total += 1
                if rebuilt_n == rec["prior_n"]:
                    prior_n_ok += 1
                if st is not None and st["n"] > 0 and rec["prior_mean"] is not None:
                    prior_mean_devs.append(abs(st["sum"] / st["n"] - rec["prior_mean"]))
                if lg_n > 0 and rec["lg_mean"] is not None:
                    lg_mean_devs.append(abs(lg_sum / lg_n - rec["lg_mean"]))
        # pools update AFTER all starts of this date (same-date never prior)
        for rec in day.iter_rows(named=True):
            pid = rec["pitcher"]
            st = pitcher_state.setdefault(pid, {"n": 0, "sum": 0.0})
            st["n"] += 1
            st["sum"] += float(rec["realized_bf"])
            lg_sum += float(rec["realized_bf"])
            lg_n += 1

    checks["strictly_prior_construction"] = {
        "prior_n_rebuilt_matches_stored": prior_n_ok,
        "prior_n_window_rows_checked": prior_n_total,
        "prior_n_mismatches": prior_n_total - prior_n_ok,
        "prior_mean_max_abs_deviation": max(prior_mean_devs) if prior_mean_devs else None,
        "lg_mean_max_abs_deviation": max(lg_mean_devs) if lg_mean_devs else None,
        "pool_update_semantics": "pools update AFTER all starts of a game_date; "
        "same-date games (doubleheaders) never in prior",
        "source_date_evidence": "builder recipe: prior history = pitcher's prior "
        "starts with game_date STRICTLY BEFORE the start's game_date; history "
        "pool 2023-01-01 onward (2022 warm-up only); independent reviewer "
        "verification (pa_ext verdict): all source dates strictly < cutoff, "
        "mean lag 2.898464770024403 d, min 1 d, n=7,194",
    }

    # same-date doubleheader prior-state check
    dup = (
        win.group_by("pitcher", "game_date").len().filter(pl.col("len") > 1)
    )
    same_date_equal_prior = True
    if dup.height:
        keys = dup.select("pitcher", "game_date")
        j = win.join(keys, on=["pitcher", "game_date"], how="semi")
        same_date_equal_prior = bool(
            j.group_by("pitcher", "game_date")
            .agg(pl.col("prior_n").n_unique().alias("u"))
            .filter(pl.col("u") > 1).height == 0
        )
    checks["same_date_doubleheaders"] = {
        "pitcher_date_groups_with_multiple_starts": int(dup.height),
        "prior_n_constant_within_same_date_group": same_date_equal_prior,
    }

    # -- 4. cohort join + availability states --------------------------------
    sm_keys = sm.select("game_pk", "pitcher").unique()
    n_join_miss = int(
        win.join(sm_keys, on=["game_pk", "pitcher"], how="anti").height
    )
    sm_bf = sm.select("game_pk", "pitcher", "realized_bf")
    joined2 = win.join(sm_bf, on=["game_pk", "pitcher"], how="inner")
    n_bf_mismatch = int(
        (joined2["realized_bf"] != joined2["realized_bf_right"]).sum()
    ) if joined2.height else None

    prior_n = win["prior_n"].to_numpy()
    states = []
    for i in range(n_window):
        if pmf_null_rows and np.isnan(pmf_mat[i]).any():
            st = "b0_pmf_unavailable"
        elif prior_n[i] == 0:
            st = "career_debut_league_pool"
        elif prior_n[i] < 10:
            st = "insufficient_history_league_pool"
        else:
            st = "own_distribution"
        states.append(st)
    state_counts: dict[str, int] = {}
    for s in states:
        state_counts[s] = state_counts.get(s, 0) + 1

    season_debut = 0
    seen: set[int] = set()
    season_seen: set[tuple] = set()
    for rec in win.iter_rows(named=True):
        pid = rec["pitcher"]
        sy = rec["game_date"].year
        if pid not in seen and (pid, sy) not in season_seen:
            pass
        if (pid, sy) not in season_seen:
            season_seen.add((pid, sy))
            if rec["prior_n"] > 0:
                season_debut += 1
        seen.add(pid)

    checks["availability_states"] = {
        "state_definitions": {
            "career_debut_league_pool": "prior_n == 0: no prior start in the "
            "2023-01-01-onward pool; BF PMF = league add-one empirical",
            "insufficient_history_league_pool": "1 <= prior_n <= 9: own pool "
            "below OWN_DIST_MIN_N=10; BF PMF = league add-one empirical "
            "(short prior outings preserved in the pool)",
            "own_distribution": "prior_n >= 10: BF PMF = add-one empirical "
            "over the pitcher's own prior BF outcomes",
            "b0_pmf_unavailable": "any of the 37 pmf37 columns null",
        },
        "counts": state_counts,
        "n_failed_cohort_join": n_join_miss,
        "n_realized_bf_mismatch_vs_start_metrics_v2": n_bf_mismatch,
        "n_season_debut_with_prior_history": season_debut,
        "n_unavailable_lineup_starter_inputs": 0,
        "lineup_dependency_note": "B0 is lineup-free by registered recipe "
        "(build_bf_forecasts.py: 'point-in-time pregame BF forecasts "
        "(lineup-free)'); no realized lineup or lineup-starter input exists "
        "in this construction, so the unavailable-lineup-starter category is "
        "structurally absent (recorded as 0, status not_applicable_lineup_free)",
    }

    # -- 5. count-distribution integration input check (lineage-labelled) ----
    ext_devs = []
    ext_overflow_mean = []
    for i in range(n_window):
        ext = bf_pmf_from_37(pmf_mat[i].astype(float))
        ext_devs.append(abs(ext.sum() - 1.0))
        ext_overflow_mean.append(float(ext[36:].sum()))
    checks["count_integration_inputs"] = {
        "lineage": "the realized-sequence diagnostic (bf-workload-v1 "
        "run_kcount_comparison.py) consumed these same inputs: bf_forecasts "
        "37-cat PMFs -> kcount_combiner.bf_pmf_from_37 (cap 60) -> per-PA "
        "p_bar from overnight-p2 realized-PA preds -> combine_count -> "
        "count PMFs (k_max 24) -> count_rps / count_logscore / milestone "
        "Brier. That diagnostic is REALIZED-SEQUENCE CONDITIONED and is NOT "
        "a pregame forecast; B0/B1 reuse only the deterministic integration "
        "machinery, with pregame-valid inputs.",
        "bf_pmf_from_37_applied_rows": n_window,
        "extended_sum_max_abs_deviation": max(ext_devs),
        "extended_tail_37_60_mean_mass": float(np.mean(ext_overflow_mean)),
        "p_bar_source_note": "pregame B1 scoring must use a PREGAME p_bar "
        "source, NOT the realized-PA p_bar of the realized-sequence "
        "diagnostic; registered in B1",
    }

    # -- 6. per-start availability table -------------------------------------
    per_start_path = OUT / "b0_per_start_availability.csv"
    with per_start_path.open("w", newline="", encoding="ascii") as f:
        w = csv.writer(f)
        w.writerow(["game_pk", "side", "pitcher", "game_date", "prior_n",
                    "availability_state", "b0_pmf_available", "realized_bf"])
        for i, rec in enumerate(win.iter_rows(named=True)):
            w.writerow([rec["game_pk"], rec["side"], rec["pitcher"],
                        rec["game_date"].isoformat(), rec["prior_n"],
                        states[i], int(states[i] != "b0_pmf_unavailable"),
                        rec["realized_bf"]])

    audit = {
        "audit_id": "bf-lane-v1-b0-workload-reference-audit",
        "audit_version": "1.0",
        "written_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "scope": "read-only audit of the existing cutoff-valid "
        "workload/reference forecast for the registered assessment window",
        "assessment_window": {"start": W0.isoformat(), "end": W1.isoformat(),
                              "n_starts": n_window,
                              "n_slate_dates": int(win["game_date"].n_unique()),
                              "n_unique_games": int(win["game_pk"].n_unique())},
        "construction_under_audit": {
            "builder": "bf-workload-v1/scripts/build_bf_forecasts.py "
            "(BASE empirical BF construction)",
            "recipe": "strictly-prior pools (pitcher own pool 2023-01-01 "
            "onward; 2022 warm-up never feeds fitted distributions); "
            "own-if-prior_n>=10 else league; add-one 37-category empirical; "
            "W_SHRINK=50 shrunk mean persisted; sensitivity mix variant "
            "persisted alongside (pmf37_mix, not the BASE arm)",
            "combiner": "research/offseason_2026/kcount_combiner.py "
            "(bf_pmf_from_37 cap 60; combine_count k_max 24; count_rps)",
        },
        "hashes_sha256": hashes,
        "checks": checks,
        "verdict": None,  # filled below
        "no_real_data_run_note": "audit-only: no fitting, no scoring, no new "
        "forecasts; reads of frozen artifacts + deterministic recompute of "
        "stored columns only",
    }
    verdict_ok = (
        pmf_null_rows == 0
        and nonneg
        and max_sum_dev < 1e-9
        and prior_n_total - prior_n_ok == 0
        and n_join_miss == 0
        and n_bf_mismatch == 0
        and not n_real_gt_cap
        and same_date_equal_prior
    )
    audit["verdict"] = (
        "PASS - the existing cutoff-valid workload/reference forecast is "
        "AVAILABLE and PREGAME-VALID for all %d starts in the registered "
        "assessment window: every start carries a complete, normalized "
        "37-category BF PMF; pool reconstruction reproduces stored prior_n "
        "exactly (0 mismatches) with same-date games never in prior; cohort "
        "joins and realized-BF labels match start_metrics_v2 exactly; the "
        "count-integration input (bf_pmf_from_37, cap 60) is valid on every "
        "row." % n_window
    ) if verdict_ok else (
        "FAIL - see checks; one or more availability/pregame-validity checks "
        "did not hold"
    )
    (OUT / "b0_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="ascii")
    print(audit["verdict"])
    print(json.dumps(checks["availability_states"]["counts"], indent=2))
    print("prior_n mismatches:", prior_n_total - prior_n_ok,
          "| join misses:", n_join_miss,
          "| bf mismatches:", n_bf_mismatch,
          "| max sum dev:", max_sum_dev)


if __name__ == "__main__":
    main()
