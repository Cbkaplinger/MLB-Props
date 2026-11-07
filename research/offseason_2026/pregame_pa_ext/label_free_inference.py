"""Label-free inference from the retained 12-feature candidate model.

SYNTHETIC-TESTED ONLY. Pure dict-in, dict-out; no I/O, no fitting, no
outcome assessment, no comparison scoring, no bootstrap, no real-data
run. Reuses the reviewed retained-candidate class-probability
calculation (`pc._softmax_full`), the registered K-class mapping
(`m0.K_CLASS`), `adapter.start_count_pmfs`, and the registered BF
representation/support.

This module does NOT construct or certify cutoff-correct features.
Prepared-feature provenance and actual historical availability remain
upstream responsibilities. Assessment/realized-outcome columns present
in the prepared feature frame are refused at this boundary.

Inputs:
1. A fitted model dictionary matching the retained 12-feature contract
   (`platoon_comparison.CHALLENGE_FEATURES`), including declared
   ordered features and classes.
2. A prepared feature frame keyed by (game_pk, side, pitcher, slot,
   batter) with the 12 declared feature columns and the model's
   ordered class set as a `class_label` column (used only for class-set
   compatibility verification, never for scoring).
3. Keyed BF37 distributions for the same forecast starts.

Outputs:
- keyed full class-probability vectors;
- keyed 24-bucket K-count PMFs;
- explicit shape/identity metadata.
"""
from __future__ import annotations

import re

import numpy as np
import polars as pl

from pregame_pa_ext import adapter as ad
from pregame_pa_ext import m0_multiclass as m0
from pregame_pa_ext import platoon_comparison as pc
from pregame_pa_ext import platoon_features as pf
from pregame_pa_ext.m0_multiclass import K_CLASS

KEY_COLS = ["game_pk", "side", "pitcher", "slot", "batter"]
START_KEY = ["game_pk", "side", "pitcher"]

# assessment/realized-outcome column names refused at this boundary
_PROHIBITED_COLS = re.compile(
    r"^(realized_k|realized_bf|y_true|k_actual|outcome_k|class_label)$",
    re.IGNORECASE)


def _require_cols(frame: pl.DataFrame, cols: list, ctx: str) -> None:
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise ValueError(f"{ctx}: missing required column(s) {missing}")


def validate_feature_contract(frame: pl.DataFrame,
                              model: dict) -> None:
    """Reject a prepared feature frame that does not match the model's
    declared 12-feature contract."""
    declared = model["features"]
    missing = [c for c in declared if c not in frame.columns]
    if missing:
        raise ValueError(
            f"feature contract mismatch: declared features {missing} "
            "are absent from the prepared feature frame")
    extra_numeric = [c for c in frame.columns
                     if c not in declared and c not in KEY_COLS
                     and frame[c].dtype.is_numeric()
                     and not c.startswith("p_class_")]
    if extra_numeric:
        raise ValueError(
            f"feature contract mismatch: undeclared numeric columns "
            f"{extra_numeric} present in the prepared feature frame")


def refuse_outcome_columns(frame: pl.DataFrame) -> None:
    """Refuse assessment/realized-outcome columns at this inference
    boundary."""
    hits = [c for c in frame.columns if _PROHIBITED_COLS.match(c)]
    if hits:
        raise ValueError(
            f"assessment/realized-outcome column(s) {hits} present in "
            "the prepared feature frame; label-free inference refuses "
            "outcome-bearing inputs")


def validate_keys(frame: pl.DataFrame) -> None:
    """Reject duplicate or missing identity keys."""
    n_unique = frame.select(KEY_COLS).n_unique()
    if frame.height != n_unique:
        dup = frame.group_by(KEY_COLS).agg(
            n=pl.len()).filter(pl.col("n") > 1).head(5)
        raise ValueError(
            f"duplicate identity keys: {dup.rows()}")
    null_keys = frame.filter(pl.any_horizontal(
        [pl.col(c).is_null() for c in KEY_COLS]))
    if null_keys.height > 0:
        raise ValueError(
            f"null identity key(s) in {null_keys.height} row(s)")


def validate_slot_coverage(frame: pl.DataFrame) -> dict:
    """Every start must have exactly 9 slots (1..9). Returns the
    scored-start key set."""
    starts = frame.select(*START_KEY).unique()
    per_start = frame.group_by(START_KEY).agg(
        n=pl.len(), min_slot=pl.col("slot").min(),
        max_slot=pl.col("slot").max())
    complete = per_start.filter(
        (pl.col("n") == 9) & (pl.col("min_slot") == 1)
        & (pl.col("max_slot") == 9))
    incomplete = per_start.filter(
        ~((pl.col("n") == 9) & (pl.col("min_slot") == 1)
          & (pl.col("max_slot") == 9)))
    if incomplete.height > 0:
        examples = incomplete.head(5).select(*START_KEY).rows()
        raise ValueError(
            f"{incomplete.height} start(s) with incomplete nine-slot "
            f"coverage: {examples}")
    return set(map(tuple, complete.select(*START_KEY).iter_rows()))


def run_label_free_inference(model: dict, features: pl.DataFrame,
                             bf37_by_start: pl.DataFrame) -> dict:
    """Produce keyed class probabilities and K-count PMFs from an
    already-fitted retained-candidate model and prepared prediction
    inputs, without consuming scored-start outcomes or fitting.

    Returns a dict with:
      - keyed_pa_probabilities: full class-probability vectors
      - k_pmf_per_start: 24-bucket K-count PMFs
      - scored_starts: sorted scored-start key list
      - n_starts, n_slots
    """
    refuse_outcome_columns(features)
    validate_feature_contract(features, model)
    validate_keys(features)
    scored_starts = validate_slot_coverage(features)

    # workload validation via existing machinery
    bf_req = bf37_by_start.select(*START_KEY).unique()
    ad.validate_bf37_by_start(bf37_by_start, bf_req)

    # keyed full class-probability vectors (reviewed softmax)
    probs = pc._softmax_full(features, model, model["features"])
    classes = list(model["classes"])
    keyed = features.select(KEY_COLS)
    for j, c in enumerate(classes):
        keyed = keyed.with_columns(
            pl.Series(f"p_class_{c}", probs[:, j]))

    # validate finite/nonnegative/normalized
    prob_cols = [f"p_class_{c}" for c in classes]
    for c in prob_cols:
        v = keyed[c]
        if v.null_count() > 0:
            raise ValueError(f"{c}: null probabilities")
        if not np.all(np.isfinite(v.to_numpy())):
            raise ValueError(f"{c}: non-finite probabilities")
    sums = keyed.select(pl.sum_horizontal(prob_cols).alias("s"))["s"]
    if not np.allclose(sums.to_numpy(), 1.0, atol=1e-9):
        raise ValueError("class probabilities do not sum to 1")

    # keyed 24-bucket K-count PMFs
    fc = {}
    for r in keyed.iter_rows(named=True):
        key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        fc.setdefault(key, {})[int(r["slot"])] = float(r[f"p_class_{K_CLASS}"])

    bf_lookup = {}
    for r in bf37_by_start.iter_rows(named=True):
        key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        bf_lookup[key] = np.asarray(
            [r[f"pmf37_{k}"] for k in range(37)], dtype=np.float64)

    pmf_rows = []
    for key in sorted(fc):
        slots = fc[key]
        if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
            raise ValueError(
                f"start {key} does not have 9 usable slots")
        if key not in bf_lookup:
            raise ValueError(
                f"start {key} has no keyed BF37 distribution")
        p9 = np.asarray([slots[i] for i in range(1, 10)])
        pmf = ad.start_count_pmfs(p9, p9, bf_lookup[key])["pmf_h3_raw"]
        for k in range(24):
            pmf_rows.append({
                "game_pk": key[0], "side": key[1], "pitcher": key[2],
                "bucket": k, "pmf_h3_raw": float(pmf[k])})

    pmf_frame = pl.DataFrame(pmf_rows)
    return {
        "keyed_pa_probabilities": keyed,
        "k_pmf_per_start": pmf_frame,
        "scored_starts": sorted(fc.keys()),
        "n_starts": len(fc),
        "n_slots": len(keyed),
        "classes": classes,
    }
