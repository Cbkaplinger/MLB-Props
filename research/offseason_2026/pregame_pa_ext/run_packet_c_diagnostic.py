"""Packet C diagnostic: directional disagreement + extremity of the
frozen control versus the near-close consensus, on the EXACT preserved
2,154 paired starts from the verified Packet B run.

Implements the pre-registered definition set in
docs/reference/reports/control_vs_books_evaluation_packet_2026-11-12.md
section PACKET C (prepared/amended 2026-11-13) - NOTHING else:

- inputs: ONLY the two registered, hash-pinned saved Packet B artifacts
  (benchmark_model_rows.parquet + benchmark_summary.json); every
  preserved row kept, equal weights, no subgroups, no filtering;
- model over probability RECOMPUTED via the registered
  ``market_eval_k.model_p_over`` (half-line tail semantics) - no new
  math;
- directional disagreement: signed_diff = model_p_over - p_over
  (consensus); mean/median/sd/min/max (sd is the population sd,
  ddof=0); sign convention: positive = model rates the over HIGHER;
- mean(p - y) per source on the exact same rows, y = 1{realized_k >
  line}; positive mean(p - y) = probabilities exceed the realized over
  frequency on this population (descriptive; NOT a calibration claim);
- extremity = distance from 0.5 (mean |p - 0.5| per source + delta;
  fixed |p - 0.5| >= 0.25 share per source) - a descriptive spread
  measure, NOT proof of overconfidence;
- paired model-binned reliability: the EXISTING registered 10-bucket
  reliability convention (numpy quantile deciles of the model
  probability over these rows, end edges -inf/+inf, [lo, hi) buckets,
  empty buckets omitted - identical derivation to
  ``market_eval_k.score_starts``) applied to BOTH sources; NO quantile
  recomputation scheme, NO bin search; this is a PAIRED MODEL-BINNED
  diagnostic, not consensus calibration.

Receipt discipline: hash/schema validation BEFORE any output; outputs
write-once; receipt_final written LAST; failure_record on any error.
NO fitting, calibration, tuning, subgroup search, protected-data
access or lake query. Real-artifact execution requires its own owner
order; this script ships WITHOUT execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[3] / "src"))

from pregame_pa_ext import market_eval_k as mk  # noqa: E402

DIAG = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
            r"\pregame-pa-ext-v2\diagnostics")
BENCH_ROWS_PATH = DIAG / "control_vs_books_v2" / "benchmark_model_rows.parquet"
BENCH_SUMMARY_PATH = DIAG / "control_vs_books_v2" / "benchmark_summary.json"
ACK_ROUTE = "EXECUTE-PACKET-C-DIAGNOSTIC-V1"
EXECUTION_ACK_TOKEN = ACK_ROUTE
N_BUCKETS_RELIABILITY = 10
EXTREMITY_THRESHOLD = 0.25

FILE_PINS = {
    "benchmark_model_rows": (
        BENCH_ROWS_PATH,
        "1c0e7f4e3a83608fb0315b5ac4ca421ac4b3096e2ea63661e7dcda377d5de075"),
    "benchmark_summary": (
        BENCH_SUMMARY_PATH,
        "2fee0f1dcc2a3ee076434235fec16973dae2ee1985fbb3ad3f0b5012e6b5bce6"),
}
REQUIRED_COLUMNS = {"game_pk", "side", "pitcher", "game_date", "block",
                    "realized_k", "line", "pmf_baseline", "p_over",
                    "n_books"}

OUTPUT_SUMMARY = "directional_disagreement_extremity_summary.json"
OUTPUT_BUCKETS = "paired_model_binned_reliability.parquet"
OUTPUT_INITIAL_RECEIPT = "receipt_initial.json"
OUTPUT_FINAL_RECEIPT = "receipt_final.json"
OUTPUT_FAILURE_RECORD = "failure_record.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_args(args) -> None:
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            f"execution acknowledgement required: {ACK_ROUTE}")
    if not args.out_dir:
        raise ValueError("--out-dir is required")
    if Path(args.out_dir).exists():
        raise ValueError(
            f"destination exists (write-once policy): {args.out_dir}")
    for name, (path, pin) in FILE_PINS.items():
        if not Path(path).exists():
            raise FileNotFoundError(
                f"pinned Packet B artifact {name} missing: {path}; "
                "refusing before any output creation or decoding")
        got = sha256_file(Path(path))
        if got != pin:
            raise ValueError(
                f"pinned Packet B artifact {name} changed: expected "
                f"{pin[:16]}..., got {got[:16]}...; refusing")


def _registered_decile_edges(p_model: np.ndarray) -> np.ndarray:
    """EXACT registered bin-edge derivation from
    ``market_eval_k.score_starts`` (numpy quantile deciles of the model
    probability over these rows; end edges -inf/+inf). Retained
    convention: no new scheme, no search."""
    qs = np.quantile(p_model,
                     np.linspace(0, 1, N_BUCKETS_RELIABILITY + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    return qs


def _jsonable(obj):
    """Explicit fail-loud JSON conversion (no default=str)."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    raise TypeError(
        f"non-JSON-serializable type {type(obj)!r}; refusing "
        "(default=str is never used for results)")


def compute(rows: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    """Packet C fixed summaries + paired model-binned table."""
    missing = REQUIRED_COLUMNS - set(rows.columns)
    if missing:
        raise ValueError(
            f"preserved rows missing required column(s): "
            f"{sorted(missing)}; refusing")
    if rows.height == 0:
        raise ValueError("preserved rows are empty; refusing")
    if rows.select(START_KEYS := ["game_pk", "side", "pitcher"]).unique(
            subset=START_KEYS).height != rows.height:
        raise ValueError("duplicate start identity in preserved rows; "
                         "refusing")
    p_m = np.asarray(
        [mk.model_p_over(np.asarray(r, dtype=np.float64), float(line))
         for r, line in zip(rows["pmf_baseline"], rows["line"])],
        dtype=np.float64)
    p_c = np.asarray(rows["p_over"].to_list(), dtype=np.float64)
    y = np.asarray(
        [1.0 if float(k) > float(l) else 0.0
         for k, l in zip(rows["realized_k"], rows["line"])],
        dtype=np.float64)
    signed = p_m - p_c
    d = {
        "n_rows": int(rows.height),
        "definitions": {
            "y": "1{realized_k > line}",
            "signed_diff": "model_p_over - p_over (consensus); "
                           "positive = model rates the over HIGHER",
            "mean_p_minus_y_sign": "positive = probabilities exceed "
                                   "the realized over frequency on "
                                   "this population (descriptive; "
                                   "not a calibration claim)",
            "extremity": "distance from 0.5; a larger extremity is "
                         "NOT proof of overconfidence",
            "bins": ("paired MODEL-BINNED diagnostic: registered "
                     "decile edges of the model probability "
                     "([lo, hi), -inf/+inf ends, empty buckets "
                     "omitted) applied to BOTH sources; NOT "
                     "consensus calibration"),
            "extremity_threshold": EXTREMITY_THRESHOLD,
            "weights": "equal per preserved paired row",
        },
        "directional_disagreement": {
            "mean": float(np.mean(signed)),
            "mean_pp": float(np.mean(signed)) * 100.0,
            "median": float(np.median(signed)),
            "sd_ddof0": float(np.std(signed, ddof=0)),
            "min": float(np.min(signed)),
            "max": float(np.max(signed)),
        },
        "mean_p_minus_y": {
            "model": float(np.mean(p_m - y)),
            "consensus": float(np.mean(p_c - y)),
        },
        "extremity": {
            "model": float(np.mean(np.abs(p_m - 0.5))),
            "consensus": float(np.mean(np.abs(p_c - 0.5))),
            "delta_model_minus_consensus": float(
                np.mean(np.abs(p_m - 0.5)) - np.mean(np.abs(p_c - 0.5))),
            "share_abs_p_minus_half_gte_threshold": {
                "model": float(np.mean(np.abs(p_m - 0.5)
                                       >= EXTREMITY_THRESHOLD)),
                "consensus": float(np.mean(np.abs(p_c - 0.5)
                                           >= EXTREMITY_THRESHOLD)),
            },
        },
        "log_loss_registered": {
            "model": float(np.mean(-(y * np.log(p_m + 1e-12)
                                     + (1 - y) * np.log(1 - p_m
                                                        + 1e-12)))),
            "consensus": float(np.mean(-(y * np.log(p_c + 1e-12)
                                         + (1 - y) * np.log(1 - p_c
                                                            + 1e-12)))),
        },
    }
    # ---- paired model-binned table (registered edges, BOTH sources)
    qs = _registered_decile_edges(p_m)
    bucket_rows = []
    for i in range(N_BUCKETS_RELIABILITY):
        mask = (p_m >= qs[i]) & (p_m < qs[i + 1])
        if mask.sum():
            bucket_rows.append({
                "bucket": i,
                "n": int(mask.sum()),
                "p_model_mean": float(p_m[mask].mean()),
                "p_consensus_mean": float(p_c[mask].mean()),
                "observed_over_rate": float(y[mask].mean()),
                "mean_p_minus_y_model": float(np.mean(p_m[mask] - y[mask])),
                "mean_p_minus_y_consensus": float(np.mean(p_c[mask]
                                                          - y[mask])),
            })
    bins = pl.DataFrame(bucket_rows)
    return d, bins


def _persist(out_dir: Path, summary: dict, bins: pl.DataFrame) -> None:
    (out_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(_jsonable(summary), indent=1, sort_keys=True),
        encoding="utf-8")
    bins.write_parquet(out_dir / OUTPUT_BUCKETS)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execution-ack", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    _validate_args(args)
    out_dir = Path(args.out_dir)
    receipt = {
        "runner": "packet_c_diagnostic_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "declared_inputs": {name: {"path": str(path), "sha256": pin}
                            for name, (path, pin) in FILE_PINS.items()},
        "control_arm": "registered_8feat_multinomial_W0_control",
        "source_run": "Packet B verified run (control_vs_books_v2)",
        "definitions_source": ("control_vs_books_evaluation_packet_"
                               "2026-11-12.md section PACKET C"),
    }
    out_dir.mkdir(parents=True)
    (out_dir / OUTPUT_INITIAL_RECEIPT).write_text(
        json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")
    try:
        rows = pl.read_parquet(BENCH_ROWS_PATH)
        summary, bins = compute(rows)
        _persist(out_dir, summary, bins)
        (out_dir / OUTPUT_FINAL_RECEIPT).write_text(
            json.dumps({**receipt, "status": "completed"},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        return 0
    except Exception as exc:
        (out_dir / OUTPUT_FAILURE_RECORD).write_text(
            json.dumps({**receipt, "status": "failed",
                        "error": repr(exc)},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
