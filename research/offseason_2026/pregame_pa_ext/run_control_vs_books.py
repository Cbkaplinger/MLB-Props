"""Thin control-vs-books orchestration (research-side; no live-path
change). Completes the wiring identified in
docs/reference/reports/control_vs_books_evaluation_packet_2026-11-12.md:
declared start_dates from the registered count_agg_eval_v1 artifact,
then the ordered call into the EXISTING market-benchmark seam with the
REGISTERED control arm. No new evaluation framework: all scoring,
de-vig, consensus, timestamp and bootstrap math stays in the
registered modules (market_benchmark_seam / market_eval_k /
count_pmf_diagnostic / join_coverage).

Scientific contract (timing + identity):
- envelope ``commence_time`` is the vendor-scheduled commence. It is
  called "commence" throughout; it is NOT an observed first pitch and
  is never equated to one.
- This is the NEAR-CLOSE BENCHMARK contract (tier A: latest quote at
  or before each start's commence within the registered 60-minute
  window; tier B: vendor close snapshot). A near-close label alone
  does NOT establish that confirmed-lineup model inputs existed before
  every selected quote: model inputs are strictly-prior pregame
  states, and morning decision-time availability is unestablished for
  2025H1. This comparison is therefore NOT a morning trading replay.
- The event->game mapping tie-break (closest date, then event_id
  order) is NOT independent identity validation. Aggregate tie-break
  counts are recorded (archive_event_map_duplicate_keys); per-mapping
  uniquely-supported-vs-tie-broken status is NOT carried by existing
  metadata and is declared as a gap rather than inferred.

Registered inputs (byte-pinned, fail on mismatch):
- k-PMF control artifact (byte-identical platoon reproduction;
  receipt_final b1b91357...224ba; pin 8c5c849c...);
- pinned 2025H1 assessment (observed K via registered
  derive_observed_k);
- registered eligible cohort (content hash f77d7a66... enforced by
  cpd.validate_cohort; the cohort content hash is also recorded);
- declared start_dates from the registered count_agg_eval_v1 model
  frame (the ONLY wiring addition; exact cohort cover asserted by the
  seam - no date invention);
- quotes + starts bridge via the registered join context
  (build_task_frames; dev window 2024-07-01..2025-06-30).

Separation guarantees: ONLY the declared arm ``pmf_multinomial_control``
is scored; the legacy live-model panel column ``p_ours_cal`` is never
read; model-only and market-only artifacts stay separate.

Output discipline:
- tables persist as parquet (registered atomic-write convention);
- scores/coverage persist as JSON through an explicit fail-loud
  converter - default=str NEVER serializes scientific results;
- ``receipt_final.json`` is written LAST, only after every declared
  output succeeded; any failure preserves ``failure_record.json``
  and never leaves a completed receipt.

Gated real-data runner (synthetic-tested with injected frames; the
private-lake join context is imported lazily exactly as in the
registered market-eval lane):

  python research/offseason_2026/pregame_pa_ext/run_control_vs_books.py \
      --execution-ack EXECUTE-CONTROL-VS-BOOKS-V1 \
      --out-dir <fresh write-once directory> \
      --book-lines <book_lines_pitcher.parquet> \
      --envelope <snapshot_envelope.parquet>

No fitting, no calibration, no staking, no live-path edit.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[3] / "src"))

from pregame_pa_ext import market_benchmark_seam as seam  # noqa: E402
from pregame_pa_ext import count_pmf_diagnostic as cpd  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    atomic_write_parquet,
)

START_KEYS = ("game_pk", "side", "pitcher")
CONTROL_ARM = "pmf_multinomial_control"
ACK_ROUTE = "EXECUTE-CONTROL-VS-BOOKS-V1"
EXECUTION_ACK_TOKEN = ACK_ROUTE

_DIAG = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
             r"\pregame-pa-ext-v2\diagnostics")
K_PMF_PATH = _DIAG / "platoon_information_v1_reproduction_20261110" / "k_pmf_per_start_v1.parquet"
ASSESSMENT_PATH = _DIAG / "pregame_multiclass_baseline_v1_inputs_v2" / "assessment_2025H1_v1.parquet"
COHORT_PATH = _DIAG / "pregame_multiclass_baseline_v1_inputs_v2" / "eligible_cohort_keys_2025H1.parquet"
DATES_PATH = _DIAG / "count_agg_eval_v1" / "count_agg_eval_v1.parquet"
EXPECTED_COHORT_HASH = ("f77d7a66639ee94a9157244b357487d5f462c6cb0bd"
                        "4909bbffb44b924db41b7")

FILE_PINS = {
    "k_pmf_per_start_v1": (K_PMF_PATH,
                           "8c5c849c289ecd65a561719d9ca7e9ce0975e6e0c37"
                           "7107fb6587c475b3a4916"),
    "assessment_2025H1_v1": (ASSESSMENT_PATH,
                             "464fe1922c4aa3090f46b43cdce4949a888ad0c20"
                             "ccd269d5c2cce671a1b80aa"),
    "count_agg_eval_v1_dates": (DATES_PATH,
                                "afc94ad74f824b73d29e9069e17f16824786a1e"
                                "8dda6395213beea64a2afaf34"),
    "cohort": (COHORT_PATH, None),  # content hash enforced downstream
}

# output tables + summary + receipts (receipt_final LAST)
OUTPUT_TABLES = ("benchmark_model_rows.parquet",
                 "benchmark_consensus.parquet",
                 "benchmark_book_probs.parquet",
                 "benchmark_ltbo.parquet")
OUTPUT_SUMMARY = "benchmark_summary.json"
OUTPUT_FINAL_RECEIPT = "receipt_final.json"
OUTPUT_INITIAL_RECEIPT = "receipt_initial.json"
OUTPUT_FAILURE_RECORD = "failure_record.json"

TIMING_CONTRACT = {
    "comparison_label": ("NEAR-CLOSE BENCHMARK - not a morning trading "
                         "replay"),
    "commence_semantics": ("envelope commence_time is the vendor-"
                           "scheduled commence; it is NOT an observed "
                           "first pitch and is never equated to one"),
    "timing_interpretation": ("market quotes selected under the "
                              "registered near-close rules (tier A: "
                              "latest quote at or before the start's "
                              "commence within 60 minutes; tier B: "
                              "vendor close snapshot); the comparison "
                              "time is the near-close cutoff, not a "
                              "T-5h decision"),
    "model_input_limitation": ("model inputs are strictly-prior "
                               "pregame states; a near-close label does "
                               "NOT establish that confirmed-lineup "
                               "inputs existed before every selected "
                               "quote; morning decision-time "
                               "availability is unestablished for "
                               "2025H1"),
    "tiebreak_status": ("event->game mapping uses the registered "
                        "closest-date + event_id-order tiebreak, which "
                        "is NOT independent identity validation; "
                        "existing metadata records tie-broken "
                        "(game_date, pitcher_key) sets in AGGREGATE "
                        "only (archive_event_map_duplicate_keys); "
                        "per-mapping uniquely-supported vs tie-broken "
                        "status is NOT recorded by existing machinery "
                        "- declared gap"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_pin(name: str, path: Path, expected: str) -> None:
    got = sha256_file(path)
    if got != expected:
        raise ValueError(
            f"pinned input {name} changed: expected {expected[:16]}..., "
            f"got {got[:16]}...; refusing")


def _jsonable(obj):
    """Explicit, fail-loud JSON conversion. Scientific results are
    NEVER serialized through default=str: numpy scalars convert to
    Python scalars; anything unknown REFUSES."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    raise TypeError(
        f"non-JSON-serializable type {type(obj)!r} in scientific "
        "output; refusing (default=str is never used for results)")


def derive_start_dates(count_agg_eval: "pl.DataFrame",
                       cohort: "pl.DataFrame") -> "pl.DataFrame":
    """Declared start dates for the cohort from the REGISTERED
    count_agg_eval_v1 model-frame artifact (game_pk, side, pitcher,
    game_date). Restricted to the cohort keys; conflicting declared
    dates for one start REFUSE; exact cohort cover is asserted again
    inside the seam (no date invention is possible)."""
    missing = [c for c in [*START_KEYS, "game_date"]
               if c not in count_agg_eval.columns]
    if missing:
        raise ValueError(
            "declared-dates source missing column(s): "
            f"{sorted(missing)}; refusing")
    d = count_agg_eval.select([*START_KEYS, "game_date"]).unique()
    dup = d.group_by(list(START_KEYS)).agg(
        n_dates=pl.col("game_date").n_unique()).filter(
        pl.col("n_dates") > 1)
    if dup.height:
        raise ValueError(
            f"{dup.height} start(s) with conflicting declared "
            f"game_date in count_agg_eval_v1 (sample: "
            f"{dup.head(3).rows()}); refusing")
    return d.join(cohort, on=list(START_KEYS), how="semi")


def _cohort_content_hash(cohort: "pl.DataFrame") -> str:
    """Registered cohort content hash (bk._cohort_hash over the sorted
    unique start keys) - the same recipe cpd.validate_cohort enforces."""
    from pregame_pa_ext import binary_k_comparison as bk
    keys = sorted({tuple(r) for r
                   in cohort.select(START_KEYS).unique().iter_rows()})
    return bk._cohort_hash(keys)


def _bridge_identity() -> dict:
    """Consumed identity of the private join context + its manifest
    (existing provenance machinery: the card's own manifest pins).
    Records actual availability honestly when the card is absent."""
    from pregame_pa_ext import market_eval_k as mk
    try:
        jc = mk._get_jc()
    except Exception as exc:  # recorded, never invented
        return {"join_coverage": f"unavailable: {exc!r}"}
    jc_path = Path(jc.__file__)
    card = jc_path.parent
    manifest = card / "manifest.json"
    out = {"join_coverage_py_sha256": sha256_file(jc_path),
           "join_coverage_path": str(jc_path)}
    if manifest.exists():
        out["card_manifest_sha256"] = sha256_file(manifest)
    return out


def build_quotes(book_lines_path: Path, envelope_path: Path):
    """Registered join context (lazy private-lake import, exactly as in
    the gated market-eval runner): dev-window task frames used as the
    near-close quote source and the starts bridge."""
    from pregame_pa_ext import market_eval_k as mk
    from pregame_pa_ext import adapter as ad
    workload = ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet"
    starts_out, odds, join_meta = mk._get_jc().build_task_frames(
        Path(book_lines_path), Path(envelope_path), workload,
        [mk.MARKET], window_start=mk.DEV_WINDOW_START,
        window_end=mk.DEV_WINDOW_END)
    join_meta = dict(join_meta)
    join_meta["workload_path"] = str(workload)
    return starts_out, odds, join_meta


def _validate_args(args) -> None:
    """Validate EVERY required input BEFORE output creation or any
    frame decoding."""
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            f"execution acknowledgement required: {ACK_ROUTE}")
    if not args.out_dir:
        raise ValueError("--out-dir is required")
    if Path(args.out_dir).exists():
        raise ValueError(
            f"destination exists (write-once policy): {args.out_dir}")
    for label, val in (("--book-lines", args.book_lines),
                       ("--envelope", args.envelope)):
        if not val:
            raise ValueError(f"{label} is required")
        if not Path(val).exists():
            raise FileNotFoundError(
                f"{label} does not exist: {val}; refusing before any "
                "output creation or decoding")
    if args.n_boot < 1:
        raise ValueError("--n-boot must be >= 1")


def _persist_results(out_dir: Path, result: dict) -> None:
    """Persist ALL declared outputs. Tables as parquet (registered
    atomic write); scores/coverage as explicit JSON (fail-loud
    conversion). Matched/unmatched start keys are persisted BEFORE the
    summary when the declared shared-population policy ran. Receipt
    final is written by the CALLER only after this succeeds."""
    atomic_write_parquet(result["model_rows"],
                         out_dir / OUTPUT_TABLES[0])
    atomic_write_parquet(result["consensus"],
                         out_dir / OUTPUT_TABLES[1])
    atomic_write_parquet(result["book_probs"],
                         out_dir / OUTPUT_TABLES[2])
    atomic_write_parquet(result["ltbo"],
                         out_dir / OUTPUT_TABLES[3])
    cov = result["coverage"]
    if cov.get("consensus_shared_population") is not None:
        atomic_write_parquet(
            pl.DataFrame(cov["consensus_matched_starts"]),
            out_dir / "consensus_matched_starts.parquet")
        atomic_write_parquet(
            pl.DataFrame(cov["consensus_unmatched_starts"]),
            out_dir / "consensus_unmatched_starts.parquet")
    summary = {
        "contract": TIMING_CONTRACT,
        "model_vs_consensus": _jsonable(result["model_vs_consensus"]),
        "book_scores": _jsonable(result["book_scores"]),
        "coverage": _jsonable(cov),
    }
    (out_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execution-ack", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--book-lines", default=None)
    ap.add_argument("--envelope", default=None)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--consensus-policy", choices=("refuse",
                                                   "shared_population"),
                    default="refuse",
                    help="refuse = exact-cohort consensus coverage is a "
                         "hard gate (any model start without an all-book "
                         "near-close consensus refuses); "
                         "shared_population = score model-vs-consensus "
                         "on the declared shared population only, keep "
                         "the ORIGINAL cohort as the coverage "
                         "denominator, and persist matched/unmatched "
                         "start keys with reason codes before scoring; "
                         "book/LTBO populations stay separate")
    args = ap.parse_args(argv)
    # ---- validate BEFORE any output creation or frame decoding
    _validate_args(args)
    out_dir = Path(args.out_dir)

    # ---- declared pins (hash reads only; None pin = content-checked)
    for name, (path, pin) in FILE_PINS.items():
        if not Path(path).exists():
            raise FileNotFoundError(
                f"registered input {name} missing: {path}; refusing")
        if pin is not None:
            _require_pin(name, Path(path), pin)
    receipt = {
        "runner": "run_control_vs_books_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "declared_inputs": {name: {"path": str(path), "sha256": pin}
                            for name, (path, pin) in FILE_PINS.items()},
        "cohort_expected_content_hash": EXPECTED_COHORT_HASH,
        "control_arm": CONTROL_ARM,
        "legacy_panel_used": False,
        "timing_contract": TIMING_CONTRACT,
    }
    out_dir.mkdir(parents=True)
    (out_dir / OUTPUT_INITIAL_RECEIPT).write_text(
        json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")
    try:
        path_by_name = {name: path
                        for name, (path, _pin) in FILE_PINS.items()}
        k_pmf = pl.read_parquet(path_by_name["k_pmf_per_start_v1"])
        assessment = pl.read_parquet(path_by_name["assessment_2025H1_v1"])
        cohort = pl.read_parquet(path_by_name["cohort"])
        dates_src = pl.read_parquet(path_by_name["count_agg_eval_v1_dates"])
        start_dates = derive_start_dates(dates_src, cohort)
        starts_bridge, quotes, join_meta = build_quotes(
            Path(args.book_lines), Path(args.envelope))
        from pregame_pa_ext import count_pmf_diagnostic as cpd
        observed = cpd.derive_observed_k(assessment)
        result = seam.benchmark_contract_rows(
            k_pmf, observed, start_dates, cohort, EXPECTED_COHORT_HASH,
            CONTROL_ARM, quotes, starts_bridge,
            n_boot=args.n_boot,
            consensus_policy=args.consensus_policy)
        # ---- ACTUAL consumed identities (recorded, not re-derived)
        from pregame_pa_ext import market_eval_k as mk
        join_meta["book_lines_sha256"] = sha256_file(Path(args.book_lines))
        join_meta["envelope_sha256"] = sha256_file(Path(args.envelope))
        join_meta["bridge"] = _bridge_identity()
        receipt["consensus_policy"] = args.consensus_policy
        receipt["consumed_identities"] = {
            "cohort_content_hash": _cohort_content_hash(cohort),
            "pinned_artifacts": {name: pin
                                 for name, (_p, pin)
                                 in FILE_PINS.items()},
            "join_context": join_meta,
        }
        # ---- ALL declared outputs first; receipt_final LAST
        _persist_results(out_dir, result)
        (out_dir / OUTPUT_FINAL_RECEIPT).write_text(
            json.dumps({**receipt, "status": "completed"},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        return 0
    except Exception as exc:  # failure record preserved, never silent
        (out_dir / OUTPUT_FAILURE_RECORD).write_text(
            json.dumps({**receipt, "status": "failed",
                        "error": repr(exc)},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
