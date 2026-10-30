"""History-sensitivity scorecard runner (S_v2 vs S_v1), thin I/O wrapper.

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
This module adds NO statistical machinery. It wraps the REGISTERED
construction unchanged:

    baseline_ladder.build_arms          (shared P/S arm construction,
                                         v1 contract window guard)
    starter_outcomes.build_arms_v2      (expanded-history adapter; same
                                         shared machinery via the v2
                                         versioned guard)
    kcount_combiner.count_rps           (registered count-RPS scorer)
    adapter.validate_bf37_by_start      (registered workload wiring)
    bl.paired_contrast                  (registered slate-date bootstrap,
                                         n_boot=2000, seed=20261001)

REGISTERED SCORECARD IDENTITY: "baseline_history_sensitivity_scorecard_v1"
pinned by scorecard_contract_sha() below. This is a NEW comparison
identity: the legacy primary contract (S vs F) and the derivation
contract (baseline_v2_derived_starts_v1) remain intact and are only
referenced, never rewritten.

Primary contrast (declared before any scoring):
    delta = RPS(S_v2) - RPS(S_v1) per start on IDENTICAL assessment
    keys. S_v1 is estimated on the REGISTERED 2024-07-01..2024-12-31
    start outcomes; S_v2 on the ACCEPTED derived 2023-01-01..2024-12-31
    artifact. Estimator, w150 shrinkage, workload input, 24-bucket
    support, and assessment population are held FIXED; only the
    estimation history differs. delta < 0 with the entire 95% CI below
    zero favors the longer history; the whole CI above zero favors the
    shorter history; an interval overlapping zero is INCONCLUSIVE --
    not equivalence and not a win for either side.

Inputs (each a caller-supplied path verified against its
caller-declared SHA-256 BEFORE any frame is decoded; every input is
read IN FULL -- all rows and columns are decoded; this is not
restricted reading):
    s_v1_path: registered start outcomes (start_metrics_v2.parquet
        lineage); estimation slice 2024-07-01..2024-12-31.
    s_v2_path: accepted derived artifact (contract
        baseline_v2_derived_starts_v1); estimation slice
        2023-01-01..2024-12-31.
    eval_pmfs_path: registered per-start PMF artifact
        (count_agg_eval_v1 lineage: game_pk, side, pitcher, game_date,
        block, realized_k, pmf_baseline). The block_2025H1 slice IS the
        registered eligible assessment cohort; its sorted-key SHA-256
        is verified against the predeclared value. It supplies
        assessment keys, game_date, realized assessment outcomes, and
        the frozen-incumbent per-start PMFs (pmf_baseline) used ONLY
        for the descriptive anchor.
    bf_path: registered bf-workload-v1 bf_forecasts.parquet (start
        grain, pmf37_0..36), wiring-validated per start by the
        registered validator; FIXED for both arms; never refit.

Assessment outcomes never enter estimation: estimation frames are
separate inputs guarded by their own windows, and the assessment slice
is dated 2025-01-01..2025-06-30 only. Rows of any input outside the
selected windows are counted and excluded; null-game_date rows are
UNDATEABLE and refuse the run. confirm_2025H2 and later partitions are
decoded by the full-file load but never selected, scored, or carried
forward; whether full-file decoding is permitted is a separate owner
decision recorded in the execution packet, not asserted here.

Outputs (write-once destination, refused if it exists):
    history_sensitivity_per_start_v1.parquet
    history_sensitivity_report.json
    receipt_initial.json (immutable; sha recorded by receipt_final)
    receipt_final.json
    failure_record.json on any exception (stage, error, initial-receipt
    sha), then re-raise: no repair, no retry, no rerun.

Exit codes: 0 completed; 2 execution acknowledgement refused (zero side
effects); exceptions fail loud after preserving failure evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402
from pregame_pa_ext import starter_outcomes as so  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-HISTORY-SENSITIVITY-SCORECARD-V1"
SCORECARD_ID = "baseline_history_sensitivity_scorecard_v1"

S_V1_TRAIN_START = "2024-07-01"
S_V1_TRAIN_END = "2024-12-31"
S_V2_TRAIN_START = so.V2_TRAIN_START   # 2023-01-01
S_V2_TRAIN_END = so.V2_TRAIN_END       # 2024-12-31
EVAL_BLOCK = "block_2025H1"
EVAL_START = "2025-01-01"
EVAL_END = "2025-06-30"
N_BOOT = 2000
SEED = 20261001

ESTIMATION_COLUMNS = ["game_pk", "side", "pitcher", "game_date",
                      "realized_bf", "realized_k"]
EVAL_COLUMNS = ["game_pk", "side", "pitcher", "game_date", "block",
                "realized_k", "pmf_baseline"]
BF_COLUMNS = ["game_pk", "side", "pitcher"] + [
    f"pmf37_{j}" for j in range(37)]

INTERPRETATION_LIMITS = [
    "primary contrast: per-start RPS(S_v2) - RPS(S_v1); entire CI "
    "below zero favors the longer history, entire CI above zero "
    "favors the shorter history",
    "a CI overlapping zero is INCONCLUSIVE, not evidence of "
    "equivalence",
    "S_v2 vs S_v1 holds estimator, shrinkage (w150), workload, "
    "support, and assessment population fixed: it isolates "
    "estimation-history sensitivity, not a new method",
    "the frozen incumbent anchor is descriptive only (disclosed "
    "UNACCEPTED cold-start status); it never selects a winner",
    "all inspected development data remain development data; nothing "
    "here is a fresh final test",
]


def scorecard_contract_sha() -> str:
    blob = json.dumps({
        "scorecard": SCORECARD_ID,
        "s_v1_train": [S_V1_TRAIN_START, S_V1_TRAIN_END],
        "s_v2_train": [S_V2_TRAIN_START, S_V2_TRAIN_END],
        "eval_block": EVAL_BLOCK,
        "eval_bounds": [EVAL_START, EVAL_END],
        "primary_pair": ["S_v2", "S_v1"],
        "metric": "count_rps",
        "n_boot": N_BOOT, "seed": SEED,
        "w_prior": ad.W_PRIOR, "support_buckets": ad.K_MAX,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cohort_hash(frame: "pl.DataFrame") -> str:
    """Registered recipe (count_pmf_calibration_runner): sorted
    'game_pk|side|pitcher' lines joined by newline, SHA-256 hex."""
    rows = sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        for r in frame.select("game_pk", "side", "pitcher")
        .iter_rows(named=True))
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _date_filter(frame: "pl.DataFrame", lo: str, hi: str
                 ) -> "pl.DataFrame":
    return frame.filter(
        (pl.col("game_date") >= pl.date(*map(int, lo.split("-"))))
        & (pl.col("game_date") <= pl.date(*map(int, hi.split("-")))))


def _require_schema(frame: "pl.DataFrame", required: list,
                    source_name: str) -> None:
    """Column-presence check only (schema-level, whole source; NOT
    row-level validation and not described as restricted reading)."""
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise bl.BaselineError(
            f"{source_name}: missing field(s) {missing} (field/schema "
            "gap); expected columns: " + str(required))


def _require_undateable(frame: "pl.DataFrame", source_name: str) -> None:
    n = frame["game_date"].null_count()
    if n:
        raise bl.BaselineError(
            f"{source_name}: {n} rows carry null game_date (undateable "
            "rows cannot be assigned to an authorized window); "
            "refusing instead of silently excluding or imputing")


def _require_fields(frame: "pl.DataFrame", required: list,
                    source_name: str) -> None:
    """Row-level null check, applied ONLY to an already-selected window
    or the assessment slice (never to a full frame)."""
    for c in required:
        n = frame[c].null_count()
        if n:
            raise bl.BaselineError(
                f"{source_name}: null values in required field "
                f"'{c}': {n} rows (within the selected window)")


def run_history_sensitivity(s_v1_path, s_v2_path, eval_pmfs_path,
                            bf_path, out_dir, *,
                            expected_s_v1_sha256: str,
                            expected_s_v2_sha256: str,
                            expected_eval_pmfs_sha256: str,
                            expected_bf_sha256: str,
                            expected_eval_cohort_hash: str,
                            execution_ack: str,
                            ack_route: str = "direct-call") -> dict:
    """Execute the pre-declared history-sensitivity scorecard.

    s_v1_path: registered start outcomes; S_v1 estimates from the
        2024-07-01..2024-12-31 slice only (registered v1 guard).
    s_v2_path: accepted derived artifact (contract
        baseline_v2_derived_starts_v1); estimation slice
        2023-01-01..2024-12-31 (registered v2 guard).
    eval_pmfs_path: registered per-start PMF artifact; its
        block_2025H1 slice is the assessment cohort (keys, game_date,
        realized_k, frozen pmf_baseline anchor).
    bf_path: registered bf-workload-v1 per-start BF PMF artifact
        (fixed workload for both arms; never refit).
    expected_*: caller-declared SHA-256 of each input FILE's bytes and
        of the assessment cohort's sorted start keys; verified before
        any frame is decoded.
    execution_ack: REQUIRED technical gate token; checked before any
        input handling or output creation.
    """
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid: refusing "
            "to run before loading input, estimating, scoring, or "
            "creating output; supply the registered "
            "EXECUTION_ACK_TOKEN (technical gate only, not owner "
            "authorization)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    code_identity = {
        "runner_sha256": _file_sha(Path(__file__)),
        "baseline_ladder_sha256": _file_sha(Path(bl.__file__)),
        "starter_outcomes_sha256": _file_sha(Path(so.__file__)),
        "adapter_sha256": _file_sha(Path(ad.__file__)),
        "kcount_combiner_sha256": _file_sha(Path(kc.__file__)),
    }
    config = {
        "scorecard_identity": SCORECARD_ID,
        "scorecard_contract_sha256": scorecard_contract_sha(),
        "s_v1_estimation_window": [S_V1_TRAIN_START, S_V1_TRAIN_END],
        "s_v2_estimation_window": [S_V2_TRAIN_START, S_V2_TRAIN_END],
        "assessment_block": EVAL_BLOCK,
        "assessment_window": [EVAL_START, EVAL_END],
        "primary_pair": ["S_v2", "S_v1"],
        "primary_contrast": "RPS(S_v2) - RPS(S_v1) per start",
        "n_boot": N_BOOT,
        "seed": SEED,
        "interpretation_limits": INTERPRETATION_LIMITS,
        "access_boundary": (
            "all four input files are decoded IN FULL (all rows and "
            "columns); out-of-window rows are counted and excluded; "
            "null game_date rows refuse the run; assessment outcomes "
            "never enter estimation; the frozen incumbent is never "
            "refit"),
    }
    initial = {
        "execution_acknowledgement": {
            "route": ack_route,
            "token": execution_ack,
            "note": ("technical execution-acceptance gate only; NOT "
                     "proof of owner authorization, which remains a "
                     "separate procedural requirement"),
        },
        "code_identity": code_identity,
        "config": config,
        "expected_input_identities": {
            "s_v1_registered_starts_sha256": expected_s_v1_sha256,
            "s_v2_derived_sha256": expected_s_v2_sha256,
            "eval_pmfs_sha256": expected_eval_pmfs_sha256,
            "bf_forecasts_sha256": expected_bf_sha256,
            "assessment_cohort_keys_sha256": expected_eval_cohort_hash,
        },
        "actual_input_identities": None,
        "counts": None,
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- verify input file identities BEFORE decoding -----------
        s_v1_path = Path(s_v1_path)
        s_v2_path = Path(s_v2_path)
        eval_pmfs_path = Path(eval_pmfs_path)
        bf_path = Path(bf_path)
        actual = {
            "s_v1_registered_starts_sha256": _file_sha(s_v1_path),
            "s_v2_derived_sha256": _file_sha(s_v2_path),
            "eval_pmfs_sha256": _file_sha(eval_pmfs_path),
            "bf_forecasts_sha256": _file_sha(bf_path),
        }
        expected_files = {
            "s_v1_registered_starts_sha256": expected_s_v1_sha256,
            "s_v2_derived_sha256": expected_s_v2_sha256,
            "eval_pmfs_sha256": expected_eval_pmfs_sha256,
            "bf_forecasts_sha256": expected_bf_sha256,
        }
        for name, exp in expected_files.items():
            if actual[name] != exp:
                raise ValueError(
                    f"input identity mismatch for {name}: "
                    f"actual={actual[name]} expected={exp}")

        # ---- S_v1 estimation input (registered start outcomes) ------
        s1_full = pl.read_parquet(s_v1_path)
        _require_schema(s1_full, ESTIMATION_COLUMNS, "S_v1 source")
        _require_undateable(s1_full, "S_v1 source")
        n_s1_source = s1_full.height
        s1_sel = s1_full.select(ESTIMATION_COLUMNS)
        s1_train = _date_filter(s1_sel, S_V1_TRAIN_START,
                                S_V1_TRAIN_END)
        if s1_train.height == 0:
            raise bl.BaselineError(
                "empty S_v1 estimation window (2024-07-01..2024-12-31): "
                "refusing rather than producing a successful empty "
                "analysis")
        _require_fields(s1_train, ESTIMATION_COLUMNS, "S_v1 window")
        s1_train = s1_train.with_columns(
            ad.add_block(s1_train.select("game_date"))["block"]
            .alias("block"))
        n_s1_excluded = n_s1_source - s1_train.height

        # ---- S_v2 estimation: accepted derived artifact --------------
        s2_full = pl.read_parquet(s_v2_path)
        _require_schema(s2_full, ESTIMATION_COLUMNS, "S_v2 source")
        _require_undateable(s2_full, "S_v2 source")
        s2_train = _date_filter(s2_full.select(ESTIMATION_COLUMNS),
                                S_V2_TRAIN_START, S_V2_TRAIN_END)
        n_s2_excluded = s2_full.height - s2_train.height
        if s2_train.height == 0:
            raise bl.BaselineError(
                "empty S_v2 estimation window "
                f"({S_V2_TRAIN_START}..{S_V2_TRAIN_END}): refusing "
                "rather than producing a successful empty analysis")
        _require_fields(s2_train, ESTIMATION_COLUMNS, "S_v2 window")

        # ---- assessment cohort: registered eligible block_2025H1 -----
        ev_full = pl.read_parquet(eval_pmfs_path)
        _require_schema(ev_full, EVAL_COLUMNS, "assessment PMF artifact")
        _require_undateable(ev_full, "assessment PMF artifact")
        ev = ev_full.filter(pl.col("block") == EVAL_BLOCK)
        ev = _date_filter(ev, EVAL_START, EVAL_END)
        if ev.height == 0:
            raise bl.BaselineError(
                "empty assessment cohort (block_2025H1): refusing "
                "rather than producing a successful empty analysis")
        ev_blocks = set(ev["block"].unique().to_list())
        if ev_blocks != {EVAL_BLOCK}:
            raise bl.BaselineError(
                f"assessment cohort rejected: unexpected block labels "
                f"{sorted(ev_blocks)} after the window filter")
        cohort_hash = _cohort_hash(ev)
        if cohort_hash != expected_eval_cohort_hash:
            raise bl.BaselineError(
                "assessment cohort identity mismatch: "
                f"actual={cohort_hash} "
                f"expected={expected_eval_cohort_hash}")
        eval_keys = ev.select("game_pk", "side", "pitcher")
        if (eval_keys.select("game_pk", "side", "pitcher").n_unique()
                != eval_keys.height):
            raise bl.BaselineError(
                "duplicate assessment start keys (silent "
                "deduplication is forbidden)")
        if ev["realized_k"].null_count():
            raise bl.BaselineError(
                "null realized_k in the assessment cohort: scoring "
                "requires complete assessment outcomes")
        realized = {(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"])): int(r["realized_k"])
                    for r in ev.select("game_pk", "side", "pitcher",
                                       "realized_k")
                    .iter_rows(named=True)}
        dates = {}
        for r in ev.select("game_pk", "side", "pitcher", "game_date") \
                .sort("game_pk", "side", "pitcher").iter_rows(named=True):
            dates[(int(r["game_pk"]), str(r["side"]),
                   int(r["pitcher"]))] = r["game_date"]

        # ---- workload: registered bf37 per start key (FIXED) --------
        bf_full = pl.read_parquet(bf_path)
        bf_val, bf_meta = ad.validate_bf37_by_start(
            bf_full, ev.select("game_pk", "side", "pitcher",
                               "game_date"))
        bf_lookup = {}
        for r in bf_val.select(
                "game_pk", "side", "pitcher",
                *[f"pmf37_{j}" for j in range(37)]).iter_rows(named=True):
            bf_lookup[(int(r["game_pk"]), str(r["side"]),
                       int(r["pitcher"]))] = np.asarray(
                [r[f"pmf37_{j}"] for j in range(37)], dtype=np.float64)

        # ---- arm construction through the REGISTERED entry points ---
        arms_v1 = bl.build_arms(s1_train, eval_keys, bf_lookup)
        arms_v2 = so.build_arms_v2(s2_train, eval_keys, bf_lookup)
        arm_pmfs = {
            "S_v1": arms_v1["pitcher"],
            "S_v2": arms_v2["pitcher"],
            "P_v1": arms_v1["population"],
            "P_v2": arms_v2["population"],
        }

        # ---- per-start count-RPS on identical assessment keys -------
        scores = {}
        for name, arm in arm_pmfs.items():
            arm_keys = set(arm)
            if arm_keys != set(realized):
                raise bl.BaselineError(
                    f"arm {name} scored-key set differs from the "
                    "assessment cohort (no silent intersection): "
                    f"missing={len(set(realized) - arm_keys)} "
                    f"extra={len(arm - set(realized))}")
            scores[name] = {k: kc.count_rps(
                np.asarray(arm[k], dtype=np.float64), realized[k])
                for k in arm}

        # ---- frozen-incumbent descriptive anchor ---------------------
        f_scores = {}
        f_missing = 0
        for r in ev.select("game_pk", "side", "pitcher", "realized_k",
                           "pmf_baseline").iter_rows(named=True):
            k = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            if r["pmf_baseline"] is None:
                f_missing += 1
                continue
            f_scores[k] = kc.count_rps(
                np.asarray(r["pmf_baseline"], dtype=np.float64),
                realized[k])

        # ---- PRIMARY contrast: RPS(S_v2) - RPS(S_v1) -----------------
        # The registered helper's internal primary_pair label is a
        # fixed legacy string ("S_vs_F"); the arithmetic (paired
        # slate-date bootstrap on identical keys) is reused unchanged
        # while this runner records its OWN truthful contrast identity.
        primary_raw = bl.paired_contrast(
            scores["S_v2"], scores["S_v1"], dates,
            {k: EVAL_BLOCK for k in realized},
            n_boot=N_BOOT, seed=SEED)
        primary = dict(primary_raw)
        primary["primary_pair"] = "S_v2_vs_S_v1"
        primary["contrast"] = "RPS(S_v2) - RPS(S_v1) per start"
        primary["direction"] = ("delta < 0 favors the LONGER "
                                "estimation history; delta > 0 favors "
                                "the shorter history; CI overlapping "
                                "zero is inconclusive, not equivalence")
        primary["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; in THIS scorecard scores_a=RPS(S_v2) and "
            "scores_b=RPS(S_v1), so delta_a_minus_b is "
            "RPS(S_v2)-RPS(S_v1) as recorded above")

        # ---- descriptive diagnostics ---------------------------------
        descriptive = {}
        for name in ("P_v1", "P_v2"):
            vals = list(scores[name].values())
            descriptive[f"mean_rps_{name}"] = float(np.mean(vals))
        descriptive["f_anchor"] = {
            "n_scored": len(f_scores),
            "n_missing_pmf": f_missing,
            "mean_rps": (float(np.mean(list(f_scores.values())))
                         if f_scores else None),
            "note": ("descriptive anchor only; frozen incumbent "
                     "carries the disclosed UNACCEPTED cold-start "
                     "limitation and is never repaired or refit here"),
        }

        # ---- write outputs (write-once) ------------------------------
        ordered = sorted(realized)
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in ordered],
            "side": [k[1] for k in ordered],
            "pitcher": [k[2] for k in ordered],
            "game_date": [dates[k] for k in ordered],
            "realized_k": [realized[k] for k in ordered],
            "rps_s_v1": [scores["S_v1"][k] for k in ordered],
            "rps_s_v2": [scores["S_v2"][k] for k in ordered],
            "rps_p_v1": [scores["P_v1"][k] for k in ordered],
            "rps_p_v2": [scores["P_v2"][k] for k in ordered],
            "rps_f_anchor": [f_scores.get(k) for k in ordered],
        })
        per_start_path = out_dir / "history_sensitivity_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)
        report = {
            "scorecard_identity": SCORECARD_ID,
            "scorecard_contract_sha256": scorecard_contract_sha(),
            "windows": {
                "s_v1_estimation": [S_V1_TRAIN_START, S_V1_TRAIN_END],
                "s_v2_estimation": [S_V2_TRAIN_START, S_V2_TRAIN_END],
                "assessment": [EVAL_START, EVAL_END],
            },
            "counts": {
                "s_v1_source_rows": n_s1_source,
                "s_v1_train_rows": s1_train.height,
                "s_v1_rows_excluded_out_of_window": n_s1_excluded,
                "s_v2_train_rows": s2_train.height,
                "s_v2_rows_excluded_out_of_window": n_s2_excluded,
                "assessment_source_rows": ev_full.height,
                "assessment_starts": len(realized),
                "assessment_rows_excluded_from_cohort":
                    ev_full.height - ev.height,
            },
            "assessment_cohort_sha256": cohort_hash,
            "arm_settings_v1": arms_v1["settings"],
            "arm_settings_v2": arms_v2["settings"],
            "workload": {
                "artifact": "bf-workload-v1/data/bf_forecasts.parquet",
                "sha256_verified": actual["bf_forecasts_sha256"],
                "registered_pin": ad.REGISTERED_BF_FORECASTS_SHA256,
                "n_starts_bf_matched": bf_meta["n_starts_bf_matched"],
                "refit": False,
            },
            "primary_contrast": primary,
            "descriptive": descriptive,
            "interpretation_limits": INTERPRETATION_LIMITS,
        }
        report_path = out_dir / "history_sensitivity_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                          sort_keys=True, default=str),
                               encoding="utf-8")
        outputs = {
            "history_sensitivity_per_start_v1.parquet":
                ad.sha256_file(per_start_path),
            "history_sensitivity_report.json":
                ad.sha256_file(report_path),
        }

        final = dict(initial)
        final["actual_input_identities"] = actual
        final["counts"] = report["counts"]
        final["assessment_cohort_sha256"] = cohort_hash
        final["outputs"] = outputs
        final["primary_contrast"] = primary
        final["descriptive"] = report["descriptive"]
        final["acceptance"] = {"receipt_chain": initial_sha}
        final_path = out_dir / "receipt_final.json"
        final_path.write_text(json.dumps(final, indent=1, sort_keys=True,
                                         default=str),
                              encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "history_sensitivity_scorecard",
                   "failure": True, "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    return {"out_dir": str(out_dir),
            "scorecard_identity": SCORECARD_ID,
            "primary_contrast": primary,
            "descriptive": report["descriptive"],
            "counts": report["counts"],
            "assessment_cohort_sha256": cohort_hash,
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    """Registered CLI entry point. Acknowledgement gate runs before any
    input read or output creation (exit 2, zero side effects)."""
    p = argparse.ArgumentParser(
        description=("History-sensitivity baseline scorecard: S_v2 "
                     "(2023-2024) vs S_v1 (2024H2) on identical "
                     "assessment keys; registered machinery unchanged. "
                     "Technical ack gate only, NOT owner "
                     "authorization."))
    p.add_argument("--s-v1-source", required=True,
                   help="registered start-outcomes parquet "
                        "(start_metrics_v2 lineage)")
    p.add_argument("--s-v2-source", required=True,
                   help="accepted derived start-outcome artifact "
                        "(baseline_v2_derived_starts_v1)")
    p.add_argument("--eval-pmfs", required=True,
                   help="registered per-start PMF artifact "
                        "(count_agg_eval_v1 lineage)")
    p.add_argument("--bf-source", required=True,
                   help="registered bf-workload-v1 bf_forecasts.parquet")
    p.add_argument("--expected-s-v1-sha256", required=True)
    p.add_argument("--expected-s-v2-sha256", required=True)
    p.add_argument("--expected-eval-pmfs-sha256", required=True)
    p.add_argument("--expected-bf-sha256", required=True)
    p.add_argument("--expected-eval-cohort-hash", required=True,
                   help="registered sorted-start-key SHA-256 of the "
                        "assessment cohort")
    p.add_argument("--out-dir", required=True,
                   help="fresh write-once output directory")
    p.add_argument("--execution-ack", required=True,
                   help="registered EXECUTION_ACK_TOKEN")
    args = p.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: missing or invalid execution "
              "acknowledgement. No input was read, nothing was "
              "estimated or scored, and no output was created.",
              file=sys.stderr)
        return 2
    result = run_history_sensitivity(
        args.s_v1_source, args.s_v2_source, args.eval_pmfs,
        args.bf_source, args.out_dir,
        expected_s_v1_sha256=args.expected_s_v1_sha256,
        expected_s_v2_sha256=args.expected_s_v2_sha256,
        expected_eval_pmfs_sha256=args.expected_eval_pmfs_sha256,
        expected_bf_sha256=args.expected_bf_sha256,
        expected_eval_cohort_hash=args.expected_eval_cohort_hash,
        execution_ack=args.execution_ack, ack_route="cli")
    print(json.dumps({"scorecard_identity": result["scorecard_identity"],
                      "primary": result["primary_contrast"],
                      "counts": result["counts"],
                      "out_dir": result["out_dir"],
                      "outputs": result["outputs"]},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
