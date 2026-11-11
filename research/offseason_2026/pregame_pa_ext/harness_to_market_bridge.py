"""Harness-to-market shadow bridge (research-side; no live-path change).

ONE THIN ADAPTER: converts the shared prediction harness's keyed
24-bucket K-count PMFs into the production count layer's
line-probability column contract - one row per start with the eight
production-style ``p_over_2_5 ... p_over_9_5`` columns.

This is a probability-column contract only, NOT market readiness: no
``k_rate`` / ``projected_tbf`` / ``expected_K`` fields are manufactured,
no live file is edited, and no market scoring happens here.

Reused registered machinery (no second marginalization algorithm):
- ``market_eval_k.model_p_over`` - the registered 24-bucket -> over
  probability marginalization. Its semantics (k = 0..22 exact,
  overflow tail at 23) match the actual harness producer:
  ``adapter.count_pmf_from_mixture`` absorbs residual mass into
  k = 23 (``adapter.K_MAX = 24`` - "last PMF bucket absorbs >= 23"),
  so the tail bucket contributes to every half-integer line in scope.
- ``adapter.check_pmf`` - the registered PMF validity gate: finite,
  within [0, 1], sum within 1e-9 of 1 (the documented existing
  tolerance). Malformed PMFs REFUSE here; they are never silently
  normalized or clipped.
- ``count_layer.PROJECTION_K_LINES`` - the canonical live line set
  (2.5 ... 9.5). Importing it loads no model artifacts and performs no
  I/O; the live model stack (live_assembly) is NOT imported.

Input contract (validated, then refused on violation):
- required columns: game_pk, side, pitcher, bucket, and the PMF value
  column (default ``pmf_h3_raw``, the harness producer's column);
- bucket labels STRICTLY validated before integer conversion: null,
  nonfinite, fractional, and non-numeric labels refuse; valid
  integer-typed producer output is preserved unchanged;
- non-null start identity (game_pk, side, pitcher);
- null PMF mass refuses (clear validation error, never a TypeError);
- unique (game_pk, side, pitcher, bucket) pairs;
- exactly the declared 24 buckets (0..23) globally AND per start;
- per-start PMFs finite, within [0, 1], normalized within 1e-9 of 1
  (the documented existing ``adapter.check_pmf`` tolerance).
"""
from __future__ import annotations

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

START_KEYS = ("game_pk", "side", "pitcher")
BUCKET_COL = "bucket"
DEFAULT_PMF_COLUMN = "pmf_h3_raw"
# explicit supported numeric dtypes (pl.INTEGER_DTYPES / pl.FLOAT_DTYPES
# are deprecated/removed across supported Polars versions; Boolean and
# string labels must not become integer buckets through coercion)
_INTEGER_DTYPES = (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                   pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64)
_FLOAT_DTYPES = (pl.Float32, pl.Float64)


def _line_column(line: float) -> str:
    """Production naming convention (count_layer.attach_count_predictions):
    ``p_over_{line with dot replaced by underscore}``."""
    return f"p_over_{str(line).replace('.', '_')}"


def _validate_bucket_labels(k_pmf: pl.DataFrame) -> None:
    """Strict bucket-label validation BEFORE integer conversion: null,
    nonfinite, fractional, and non-numeric labels refuse; valid
    integer-typed producer output passes unchanged."""
    col = k_pmf[BUCKET_COL]
    if col.null_count() > 0:
        raise ValueError("null bucket label(s) present")
    dtype = k_pmf.schema[BUCKET_COL]
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


def bridge_pmf_to_lines(
    k_pmf: pl.DataFrame,
    *,
    pmf_column: str = DEFAULT_PMF_COLUMN,
    lines: tuple[float, ...] = PROJECTION_K_LINES,
) -> pl.DataFrame:
    """Keyed 24-bucket harness PMFs -> one row per start with the
    production ``p_over_*`` columns for the requested half-integer
    lines. Validates and refuses; never repairs."""
    required = [*START_KEYS, BUCKET_COL, pmf_column]
    missing = [c for c in required if c not in k_pmf.columns]
    if missing:
        raise ValueError(
            f"k_pmf frame missing required column(s): {missing}")
    _validate_bucket_labels(k_pmf)
    if k_pmf[pmf_column].null_count() > 0:
        raise ValueError(
            f"null PMF mass in {pmf_column!r}: every (start, bucket) "
            "row must carry a present mass value")
    identity = [*START_KEYS, BUCKET_COL]
    null_mask = pl.any_horizontal(
        [pl.col(c).is_null() for c in identity])
    if k_pmf.filter(null_mask).height > 0:
        raise ValueError("null identity/bucket key(s) present")
    dups = (k_pmf.group_by((*START_KEYS, BUCKET_COL)).agg(n=pl.len())
            .filter(pl.col("n") > 1))
    if dups.height > 0:
        sample = dups.select((*START_KEYS, BUCKET_COL)).head(3).rows()
        raise ValueError(
            f"{dups.height} duplicate (start, bucket) pair(s) "
            f"(sample: {sample})")
    declared = set(range(ad.K_MAX))
    present = set(int(b) for b in k_pmf[BUCKET_COL].unique().to_list())
    if present != declared:
        raise ValueError(
            f"bucket set != declared 0..{ad.K_MAX - 1}: "
            f"missing={sorted(declared - present)[:5]} "
            f"extra={sorted(present - declared)[:5]}")
    per_start = k_pmf.group_by(START_KEYS).agg(n=pl.len())
    incomplete = per_start.filter(pl.col("n") != ad.K_MAX)
    if incomplete.height > 0:
        raise ValueError(
            f"{incomplete.height} start(s) without exactly "
            f"{ad.K_MAX} buckets (sample: "
            f"{incomplete.head(3).select(START_KEYS).rows()})")

    # per-start PMF vectors in bucket order (0..23); masses validated by
    # the registered gate (refuses on finite/range/normalization faults)
    by_start: dict[tuple, dict[int, float]] = {}
    for r in k_pmf.sort([*START_KEYS, BUCKET_COL]).iter_rows(named=True):
        key = (r["game_pk"], r["side"], r["pitcher"])
        by_start.setdefault(key, {})[int(r[BUCKET_COL])] = \
            float(r[pmf_column])

    starts = k_pmf.select(START_KEYS).unique().sort(START_KEYS)
    out_cols = {name: [] for name in
                (_line_column(float(ln)) for ln in lines)}
    for r in starts.iter_rows(named=True):
        key = (r["game_pk"], r["side"], r["pitcher"])
        buckets = by_start[key]
        pmf = np.asarray([buckets[b] for b in range(ad.K_MAX)],
                         dtype=np.float64)
        ad.check_pmf(pmf, ctx=f"start {key}")
        for line in lines:
            name = _line_column(float(line))
            out_cols[name].append(mk.model_p_over(pmf, float(line)))

    out = starts.with_columns(
        [pl.Series(name, vals) for name, vals in out_cols.items()])
    if out.height != starts.height:
        raise ValueError("start identity lost in bridge output")
    return out
