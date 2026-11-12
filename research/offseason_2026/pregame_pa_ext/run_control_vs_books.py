"""Thin control-vs-books orchestration (research-side; no live-path
change). Completes the ONE missing wiring step identified in
docs/reference/reports/control_vs_books_evaluation_packet_2026-11-12.md:
declared start_dates from the registered count_agg_eval_v1 artifact,
then the ordered call into the EXISTING market-benchmark seam with the
REGISTERED control arm. No new evaluation framework: all scoring,
de-vig, consensus, timestamp and bootstrap math stays in the
registered modules (market_benchmark_seam / market_eval_k /
count_pmf_diagnostic / join_coverage).

Registered inputs (byte-pinned, fail on mismatch):
- k-PMF control artifact (byte-identical platoon reproduction;
  receipt_final b1b91357...224ba; pin 8c5c849c...);
- pinned 2025H1 assessment (observed K via registered
  derive_observed_k);
- registered eligible cohort (content hash f77d7a66... enforced by
  the seam's cpd.validate_cohort);
- declared start_dates from the registered count_agg_eval_v1 model
  frame (the ONLY wiring addition; carries game_date for the dev
  window; exact cohort cover is asserted downstream by the seam - no
  date invention);
- quotes + starts bridge via the registered join context
  (build_task_frames; dev window 2024-07-01..2025-06-30).

Separation guarantees: ONLY the declared arm ``pmf_multinomial_control``
is scored; the legacy live-model panel column ``p_ours_cal`` is never
read; model-only and market-only artifacts stay separate. The
comparison is the NEAR-CLOSE BENCHMARK contract - morning decision-time
model-input availability is unestablished for 2025H1, so this is NOT a
morning trading replay.

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
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[3] / "src"))

from pregame_pa_ext import market_benchmark_seam as seam  # noqa: E402
from pregame_pa_ext import count_pmf_diagnostic as cpd  # noqa: E402

START_KEYS = ("game_pk", "side", "pitcher")
CONTROL_ARM = "pmf_multinomial_control"
ACK_ROUTE = "EXECUTE-CONTROL-VS-BOOKS-V1"
EXECUTION_ACK_TOKEN = ACK_ROUTE
CONTROL_LABEL = "registered_8feat_multinomial_W0_control"

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
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require(name: str, path: Path, expected: str) -> None:
    got = sha256_file(path)
    if got != expected:
        raise ValueError(
            f"pinned input {name} changed: expected {expected[:16]}..., "
            f"got {got[:16]}...; refusing")


def derive_start_dates(count_agg_eval: "pl.DataFrame",
                       cohort: "pl.DataFrame") -> "pl.DataFrame":
    """Declared start dates for the cohort from the REGISTERED
    count_agg_eval_v1 model-frame artifact (game_pk, side, pitcher,
    game_date). Restricted to the cohort keys; conflicting declared
    dates for one start REFUSE; exact cohort cover is asserted again
    inside the seam (no date invention is possible)."""
    import polars as pl

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


def build_quotes(book_lines_path: Path, envelope_path: Path):
    """Registered join context (lazy private-lake import, exactly as in
    the gated market-eval runner): dev-window task frames used as the
    near-close quote source and the starts bridge."""
    from pregame_pa_ext import market_eval_k as mk
    starts_out, odds, join_meta = mk._get_jc().build_task_frames(
        Path(book_lines_path), Path(envelope_path),
        __import__("pregame_pa_ext.adapter", fromlist=["ad"])
        .ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet",
        [mk.MARKET], window_start=mk.DEV_WINDOW_START,
        window_end=mk.DEV_WINDOW_END)
    return starts_out, odds, join_meta


def assemble_and_benchmark(k_pmf, assessment, cohort, start_dates,
                           quotes, starts_bridge, *,
                           expected_cohort_hash: str,
                           n_boot: int = 2000,
                           seed: int = 20261001) -> dict:
    """Ordered call into the EXISTING seam + registered scorers; no
    new scoring math (control arm only; legacy panel never read)."""
    from pregame_pa_ext import count_pmf_diagnostic as cpd
    observed = cpd.derive_observed_k(assessment)
    return seam.benchmark_contract_rows(
        k_pmf, observed, start_dates, cohort, expected_cohort_hash,
        CONTROL_ARM, quotes, starts_bridge,
        n_boot=n_boot, seed=seed)


def main(argv: list | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execution-ack", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--book-lines", default=None)
    ap.add_argument("--envelope", default=None)
    args = ap.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            f"execution acknowledgement required: {ACK_ROUTE}")
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        raise ValueError(
            f"destination exists (write-once policy): {out_dir}")

    # ---- pinned registered inputs (byte identity enforced)
    for name, (path, pin) in FILE_PINS.items():
        if not Path(path).exists():
            raise FileNotFoundError(
                f"registered input {name} missing: {path}; refusing")
        _require(name, Path(path), pin)
    receipt = {
        "runner": "run_control_vs_books_v1",
        "generated_utc": datetime.now(
            timezone.utc).isoformat(),
        "inputs": {name: {"path": str(path), "sha256": pin}
                   for name, (path, pin) in FILE_PINS.items()},
        "control_arm": CONTROL_ARM,
        "legacy_panel_used": False,
        "timing_label": "NEAR-CLOSE BENCHMARK (not a morning replay)",
    }
    out_dir.mkdir(parents=True)
    (out_dir / "receipt_initial.json").write_text(
        json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")
    try:
        import polars as pl
        k_pmf = pl.read_parquet(K_PMF_PATH)
        assessment = pl.read_parquet(ASSESSMENT_PATH)
        cohort = pl.read_parquet(COHORT_PATH)
        dates_src = pl.read_parquet(DATES_PATH)
        start_dates = derive_start_dates(dates_src, cohort)
        starts_bridge, quotes, join_meta = build_quotes(
            Path(args.book_lines), Path(args.envelope))
        result = assemble_and_benchmark(
            k_pmf, assessment, cohort, start_dates, quotes,
            starts_bridge, expected_cohort_hash=EXPECTED_COHORT_HASH)
        receipt["join_meta"] = join_meta
        (out_dir / "receipt_final.json").write_text(
            json.dumps({**receipt, "status": "completed"},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        (out_dir / "benchmark_result.json").write_text(
            json.dumps(result, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        return 0
    except Exception as exc:  # failure record preserved, never silent
        (out_dir / "failure_record.json").write_text(
            json.dumps({**receipt, "status": "failed",
                        "error": repr(exc)},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
