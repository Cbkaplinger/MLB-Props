"""Keyed K-PMF diagnostic (research-side; no live-path change).

ONE THIN KEYED DIAGNOSTIC over the REGISTERED scoring utilities - no
duplicated math, no new evaluation framework. For a keyed forecast
K-count PMF frame (one row per (start, bucket) per arm) and a keyed
observed-K frame, it reports per-arm and paired diagnostics.

Reused registered machinery (no duplicated math):
- ``kcount_combiner.count_logscore``: count log score, natural log,
  clip 1e-12 (its default). SIGN CONFIRMED FROM CODE: it returns
  ``-log(p_k[observed])`` - the POSITIVE log loss - despite the
  "logscore" name; overflow K >= 23 reads bucket 23 (min(k, last)).
- ``kcount_combiner.count_rps``: summed-CDF-squared RPS, no clip,
  tail-aware (observed K > 23 scores the overflow bucket as observed).
- ``market_eval_k.model_p_over``: predicted over probability at each
  canonical half-integer line (``count_layer.PROJECTION_K_LINES``).
- ``adapter.check_pmf``: registered PMF validity gate (finite, [0,1],
  sum within 1e-9 of 1). Malformed PMFs refuse; never repaired.
- ``harness_to_market_bridge._validate_bucket_labels``: strict
  bucket-label validation before integer conversion (reused).

Conventions (declared, returned with every result):
- complete start identity (game_pk, side, pitcher); equal weight per
  MATCHED start; denominators = matched starts;
- exact forecast/observation key equality is REQUIRED: mismatch
  reports BOTH directions (counts + samples) and refuses - there is
  no silent inner join;
- K >= 23 belongs to the declared overflow category (bucket 23):
  observed K >= 23 scores the overflow bucket in the log score and
  RPS and counts as observed-over at every in-scope line;
- paired deltas = challenger (second requested arm) minus control
  (first arm) per matched start;
- reliability summary: FIXED declared equal-width bins [0,.1),
  [.1,.2), ... [.9,1] (p = 1 included in the last bin); per (line,
  bin): count, mean forecast, observed frequency; empty bins report
  null means, never zero.

This module does NOT fit, calibrate, tune, repair probabilities, or
touch the live path. Real-data use requires its own owner
authorization (see the proposed execution packet in the backlog).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import polars as pl

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[3] / "src"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402

from kcount_combiner import count_logscore, count_rps  # noqa: E402

DIAGNOSTIC_ID = "count_pmf_diagnostic_v1"
ACK_ROUTE = "EXECUTE-COUNT-PMF-DIAGNOSTIC-V1"
EXECUTION_ACK_TOKEN = ACK_ROUTE

START_KEYS = ("game_pk", "side", "pitcher")
BUCKET_COL = "bucket"
K_CLASS = 0
LOG_CLIP = 1e-12
LINES = PROJECTION_K_LINES
RELIABILITY_BIN_EDGES = tuple(np.round(np.linspace(0.0, 1.0, 11), 1))
PA_IDENTITY = (*START_KEYS, "at_bat_number", "batter")
_INTEGER_DTYPES = (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                   pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64)
_FLOAT_DTYPES = (pl.Float32, pl.Float64)


def _reject_null(frame: pl.DataFrame, cols, ctx: str) -> None:
    null_mask = pl.any_horizontal([pl.col(c).is_null() for c in cols])
    if frame.filter(null_mask).height > 0:
        raise ValueError(f"{ctx}: null value(s) present")


def _reject_duplicates(frame: pl.DataFrame, cols, ctx: str) -> None:
    dups = frame.group_by(cols).agg(n=pl.len()).filter(pl.col("n") > 1)
    if dups.height > 0:
        sample = frame.select(cols).head(3).rows()
        raise ValueError(
            f"{ctx}: {dups.height} duplicate identity key(s) "
            f"(sample: {sample})")


def _validate_bucket_labels(k_pmf: pl.DataFrame,
                            bucket_col: str = BUCKET_COL) -> None:
    """Strict bucket-label validation BEFORE integer conversion: null,
    nonfinite, fractional, and non-numeric labels refuse; valid
    integer-typed producer output passes unchanged."""
    col = k_pmf[bucket_col]
    if col.null_count() > 0:
        raise ValueError("null bucket label(s) present")
    dtype = k_pmf.schema[bucket_col]
    if dtype in _INTEGER_DTYPES:
        return
    if dtype not in _FLOAT_DTYPES:
        raise ValueError(
            f"bucket column dtype {dtype} is neither integer nor "
            "float; refusing non-numeric bucket labels")
    for v in col.to_list():
        if not np.isfinite(v):
            raise ValueError(f"nonfinite bucket label: {v!r}")
        if float(v) != int(v):
            raise ValueError(
                f"fractional bucket label: {v!r}; buckets must be "
                "integers 0..23")


def _validate_forecast(k_pmf: pl.DataFrame,
                       pmf_columns: list) -> None:
    """Required columns; strict bucket labels; non-null start
    identity; unique (start, bucket) pairs; complete 24-bucket
    support per start; per-start PMFs pass the registered validity
    gate."""
    required = [*START_KEYS, BUCKET_COL, *pmf_columns]
    missing = [c for c in required if c not in k_pmf.columns]
    if missing:
        raise ValueError(
            f"k_pmf frame missing required column(s): {missing}")
    _validate_bucket_labels(k_pmf)
    _reject_null(k_pmf, START_KEYS, "forecast start identity")
    _reject_duplicates(k_pmf, (*START_KEYS, BUCKET_COL),
                       "forecast (start, bucket)")
    present = set(int(b) for b in k_pmf[BUCKET_COL].unique().to_list())
    if present != set(range(ad.K_MAX)):
        raise ValueError(
            f"bucket set != declared 0..{ad.K_MAX - 1}")
    per_start = k_pmf.group_by(START_KEYS).agg(n=pl.len())
    incomplete = per_start.filter(pl.col("n") != ad.K_MAX)
    if incomplete.height > 0:
        raise ValueError(
            f"{incomplete.height} start(s) without exactly "
            f"{ad.K_MAX} buckets")


def derive_observed_k(assessment: pl.DataFrame) -> pl.DataFrame:
    """Prepared per-PA assessment rows -> one row per start with
    realized_k = count of registered strikeout labels (class_label ==
    0) plus the per-start PA denominator. The preparation contract
    preserves EVERY completed PA of the requested starters (including
    replacement batters and repeated encounters), so this derivation
    is complete full-start realized K."""
    required = [*PA_IDENTITY, "class_label"]
    missing = [c for c in required if c not in assessment.columns]
    if missing:
        raise ValueError(
            f"assessment frame missing required column(s): {missing}")
    _reject_null(assessment, PA_IDENTITY, "observed PA identity")
    _reject_duplicates(assessment, PA_IDENTITY, "observed PA")
    invalid = assessment.filter(
        ~pl.col("class_label").is_in(list(range(4))))
    if invalid.height > 0:
        raise ValueError(
            f"{invalid.height} assessment PA(s) carry class labels "
            "outside 0..3; refusing rather than scoring unknown "
            "labels")
    obs = assessment.group_by(START_KEYS).agg(
        realized_k=(pl.col("class_label") == K_CLASS).cast(pl.Int64)
        .sum(),
        n_observed_pas=pl.len())
    bad = obs.filter((pl.col("realized_k") < 0)
                     | (pl.col("realized_k")
                        > pl.col("n_observed_pas")))
    if bad.height > 0:
        raise ValueError(
            "realized K outside [0, n_observed_pas]; refusing")
    return obs.sort(START_KEYS)


def _require_exact_key_match(forecast_keys: set,
                             observed_keys: set) -> None:
    """Exact key equality is REQUIRED: both directions are reported
    (counts + samples) and the run REFUSES - no silent inner join."""
    if forecast_keys == observed_keys:
        return
    missing_from_observed = sorted(forecast_keys - observed_keys)
    missing_from_forecast = sorted(observed_keys - forecast_keys)
    raise ValueError(
        "forecast/observation key mismatch; exact equality required - "
        f"missing_from_observed={len(missing_from_observed)} "
        f"(sample: {missing_from_observed[:5]}); "
        f"missing_from_forecast={len(missing_from_forecast)} "
        f"(sample: {missing_from_forecast[:5]}); refusing")


def _fixed_reliability(pred: np.ndarray, obs: np.ndarray) -> list:
    """Fixed declared reliability summary: equal-width bins
    [0,.1), [.1,.2), ... [.9,1] (p = 1 included in the last bin).
    Per bin: count, mean forecast, observed frequency; empty bins
    report null means, never zero."""
    edges = RELIABILITY_BIN_EDGES
    summary = []
    for i in range(len(edges) - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i < len(edges) - 2:
            members = (pred >= lo) & (pred < hi)
        else:
            members = (pred >= lo) & (pred <= hi)
        n = int(members.sum())
        if n == 0:
            summary.append({"bin_lo": lo, "bin_hi": hi, "n": 0,
                            "mean_forecast": None,
                            "observed_frequency": None})
        else:
            summary.append({"bin_lo": lo, "bin_hi": hi, "n": n,
                            "mean_forecast": float(pred[members]
                                                   .mean()),
                            "observed_frequency": float(
                                np.asarray(obs,
                                           dtype=float)[members]
                                .mean())})
    return summary


def _arm_scores(pmf_by_key: dict, observed_by_key: dict,
                lines: tuple) -> dict:
    """Per-arm diagnostic on the MATCHED keys (equal weight per
    start), reusing the existing registered scorers."""
    keys = sorted(observed_by_key)
    log_losses = []
    rps_values = []
    for key in keys:
        k = observed_by_key[key]
        pmf = pmf_by_key[key]
        log_losses.append(count_logscore(pmf, int(k), clip=LOG_CLIP))
        rps_values.append(count_rps(pmf, int(k)))
    line_summary = {}
    for line in lines:
        preds = np.asarray(
            [mk.model_p_over(pmf_by_key[key], float(line))
             for key in keys], dtype=float)
        overs = np.asarray(
            [1.0 if int(observed_by_key[key]) > float(line) else 0.0
             for key in keys], dtype=float)
        line_summary[_line_name(line)] = {
            "line": float(line),
            "predicted_over_mean": float(preds.mean()),
            "observed_over_frequency": float(overs.mean()),
            "brier": float(((preds - overs) ** 2).mean()),
            "reliability": _fixed_reliability(preds, overs),
        }
    return {
        "n_matched_starts": len(keys),
        "count_logloss_mean": float(np.mean(log_losses)),
        "count_rps_mean": float(np.mean(rps_values)),
        "per_start_count_logloss": {
            str(k): v for k, v in zip(keys, log_losses)},
        "per_start_count_rps": {
            str(k): v for k, v in zip(keys, rps_values)},
        "lines": line_summary,
    }


def _line_name(line: float) -> str:
    return str(float(line))


def diagnose(k_pmf: pl.DataFrame, observed: pl.DataFrame, *,
             pmf_columns: list,
             lines: tuple = LINES) -> dict:
    """Keyed diagnostic for one or two arms on IDENTICAL start keys.
    Arms stay separate; with exactly two arms a paired
    challenger-minus-control section is returned (second arm minus
    first arm, equal weight, same matched keys)."""
    if len(pmf_columns) < 1 or len(set(pmf_columns)) != len(
            pmf_columns):
        raise ValueError(
            "pmf_columns must be one or more DISTINCT column names")
    missing = [c for c in pmf_columns if c not in k_pmf.columns]
    if missing:
        raise ValueError(f"k_pmf missing arm column(s): {missing}")
    _reject_null(observed, START_KEYS, "observed start identity")
    _reject_duplicates(observed, START_KEYS, "observed start")
    bad_k = [v for v in observed["realized_k"].to_list()
             if v is None or not np.isfinite(v) or v < 0
             or float(v) != int(v)]
    if bad_k:
        raise ValueError(
            f"observed K must be finite, nonnegative, integer-valued; "
            f"offending value(s): {bad_k[:5]}")
    _validate_bucket_labels(k_pmf)
    _validate_forecast(k_pmf, pmf_columns)

    observed_by_key = {
        (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
            int(r["realized_k"])
        for r in observed.iter_rows(named=True)}
    forecast_keys = {
        (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        for r in k_pmf.select(START_KEYS).unique().iter_rows(
            named=True)}
    _require_exact_key_match(forecast_keys, set(observed_by_key))

    pmf_by_start_arm: dict[str, dict[tuple, np.ndarray]] = {
        arm: {} for arm in pmf_columns}
    for r in k_pmf.sort([*START_KEYS, BUCKET_COL]).iter_rows(
            named=True):
        key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        bucket = int(r[BUCKET_COL])
        for arm in pmf_columns:
            vec = pmf_by_start_arm[arm].setdefault(
                key, [None] * ad.K_MAX)
            vec_val = float(r[arm])
            vec_key = int(r[BUCKET_COL])
            vec = pmf_by_start_arm[arm][key]
            vec[vec_key] = vec_val
    arm_pmfs = {}
    for arm in pmf_columns:
        arm_pmfs[arm] = {}
        for key in observed_by_key:
            pmf = np.asarray(pmf_by_start_arm[arm][key],
                             dtype=np.float64)
            ad.check_pmf(pmf, ctx=f"start {key} arm {arm}")
            arm_pmfs[arm][key] = pmf
    arms = {}
    for arm in pmf_columns:
        arms[arm] = _arm_scores(arm_pmfs[arm], observed_by_key, lines)

    paired = None
    if len(pmf_columns) == 2:
        challenger, control = pmf_columns[1], pmf_columns[0]
        delta_log = []
        delta_rps = []
        delta_brier = {_line_name(float(l)): []
                       for l in lines}
        for key, k in observed_by_key.items():
            pmf_c = arm_pmfs[control][key]
            pmf_h = arm_pmfs[challenger][key]
            delta_log.append(
                count_logscore(pmf_h, k, clip=LOG_CLIP)
                - count_logscore(pmf_c, k, clip=LOG_CLIP))
            delta_rps.append(count_rps(pmf_h, k) - count_rps(pmf_c, k))
            for line in lines:
                y = 1.0 if k > float(line) else 0.0
                delta_brier[_line_name(line)].append(
                    (mk.model_p_over(pmf_h, float(line)) - y) ** 2
                    - (mk.model_p_over(pmf_c, float(line)) - y) ** 2)
        paired = {
            "definition": ("challenger minus control, per matched "
                           "start, equal weight"),
            "challenger": challenger,
            "control": control,
            "n_paired_starts": len(observed_by_key),
            "count_logloss_delta_mean": float(np.mean(delta_log)),
            "count_rps_delta_mean": float(np.mean(delta_rps)),
            "per_line_brier_delta_mean": {
                name: float(np.mean(v))
                for name, v in delta_brier.items()},
        }
    accounting = {
        "n_forecast_starts": len(forecast_keys),
        "n_observed_starts": len(observed_by_key),
        "n_matched_starts": len(observed_by_key),
        "key_matching": ("exact equality required; mismatch reports "
                         "both directions and refuses (no silent "
                         "inner join)"),
        "weighting": "equal weight per matched start",
        "log": (f"natural log; clip {LOG_CLIP} (existing "
                "count_logscore default); returns POSITIVE log loss "
                "(confirmed from code, not the name)"),
        "rps": "summed-CDF-squared (existing count_rps); no clip",
        "overflow": ("K >= 23 belongs to the declared overflow "
                     "category (bucket 23); the existing log score, "
                     "RPS, and over probabilities are tail-aware"),
        "lines": [float(l) for l in lines],
        "reliability_bins": list(RELIABILITY_BIN_EDGES),
        "denominators": ("per-arm aggregates over matched starts; "
                         "paired deltas over the same matched "
                         "starts"),
    }
    return {"accounting": accounting, "arms": arms, "paired": paired}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Keyed K-PMF diagnostic: registered count scores "
                    "per arm + paired deltas + fixed-bin line "
                    "reliability")
    ap.add_argument("--k-pmf", required=True,
                    help="keyed forecast PMF parquet (start x bucket "
                         "rows; one column per arm)")
    ap.add_argument("--assessment", required=True,
                    help="prepared per-PA assessment parquet "
                         "(class_label column; registered label "
                         "source)")
    ap.add_argument("--arms", required=True,
                    help="comma-separated PMF columns; order = "
                         "[control, challenger] for the paired delta")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--execution-ack", required=True)
    args = ap.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(f"execution acknowledgement required: "
                         f"{ACK_ROUTE}")
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        raise ValueError(
            f"destination exists (write-once policy): {out_dir}")
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if not arms:
        raise ValueError("no arms requested")
    k_pmf = pl.read_parquet(args.k_pmf)
    assessment = pl.read_parquet(args.assessment)
    observed = derive_observed_k(assessment)
    result = diagnose(k_pmf, observed, pmf_columns=arms, lines=LINES)
    result["diagnostic_id"] = DIAGNOSTIC_ID
    result["execution_acknowledgement"] = {
        "route": ACK_ROUTE, "token": args.execution_ack}
    out_dir.mkdir(parents=True)
    payload = json.dumps(result, indent=1, sort_keys=True,
                         default=str)
    tmp = out_dir / "count_pmf_diagnostic.json.tmp"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, out_dir / "count_pmf_diagnostic.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
