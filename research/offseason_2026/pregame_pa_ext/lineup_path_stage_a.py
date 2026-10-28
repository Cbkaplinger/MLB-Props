"""Stage A prediction-path reconciliation runner (registered).

Implements Stage A of lineup_path_reconciliation_spec_2026-10-27.md:
demonstrate that the preserved ledger representation (Route A) and the
reconstructed attachment representation (Route B) of the same
pregame per-(start, slot) probabilities come from ONE feature-construction
path, keyed on (game_pk, side, pitcher, slot).

PREGAME-ONLY, OUTCOME-SCORE-FREE, write-once outputs:
- NO realized-K labels are consumed (input gate refuses them).
- NO scoring, bootstrap, or Stage B computation happens here.
- The PA-history table's ``y`` column is the declared pregame
  player-history input (strictly-prior use verified by the synthetic
  smoke suite); it is never a scored-start outcome label.

Routes (never both sides from one computed object):
- Route A: the preserved ledger artifact's stored per-slot features and
  ``p_h3_raw`` (registered input, byte-pinned by the CLI).
- Route B: fresh reconstruction -- PA history -> entity/league daily
  states -> projected lineups -> attach_prior_features -> frozen
  checkpoint coefficients (apply_h3_raw).

Gate sequence (registered):
- I1 keyed per-slot feature + batter comparison, tolerance 0 (exact).
- I2 keyed per-slot p_h3_raw comparison, tolerance 1e-12.
- I3 per-start 24-bucket PMF comparison, both routes aggregated by the
  registered machinery from their own p9 and the SAME keyed BF row.
- I4 control gate: max I3 diff <= 1e-12 across all compared starts.
  PMFs are compared ONLY under identical semantic slot order (I1 batter
  equality per slot) and identical workload/aggregation settings.

Any I1/I2/I4 violation = FAIL: write-once failure receipt, no PASS
receipt, no Stage B. Structural exclusions (missing lineup coverage,
slot coverage below 9, missing BF row) are counted in mutually exclusive
buckets with a mandatory sum check over the dev-start population.
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
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

PROHIBITED_LABELS = {"realized_k", "y_true", "k_actual", "outcome_k"}
PERMITTED_HISTORY_LABEL = "y"  # PA-history table only (strictly-prior input)
DEV_BLOCKS = tuple(br.DEV_BLOCKS)  # registered dev blocks (reuse)
PROTECTED_BLOCK = "confirm_2025H2"
# target-date boundaries: identical to ad.add_block's registered bounds
DEV_LAST_DATE = (2025, 6, 30)  # anything later is protected partition
FEATURES = list(ad.FEAT_H3)
TOL = 1e-12
SLOTS = tuple(range(1, 10))
STAGE = "lineup_path_stage_a"


class StageAFailure(RuntimeError):
    """A registered gate (I1/I2/I4 or population) failed; the failure
    receipt has been written and no PASS receipt exists."""


def _sha_file(path) -> str:  # noqa: ANN001
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _code_identity() -> dict:
    return {
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(
            Path(ad.__file__).read_bytes()).hexdigest(),
    }


def assert_no_realized_labels(frame: pl.DataFrame, name: str) -> None:
    """Stage A input gate: the consumed frame must not carry realized-K
    label columns. The PA-history table's ``y`` is the one permitted
    history label (strictly-prior player-history input)."""
    present = PROHIBITED_LABELS & set(frame.columns)
    if present:
        raise RuntimeError(
            f"PROHIBITED_REALIZED_LABELS in {name}: {sorted(present)}; "
            "Stage A is outcome-score-free")


def _route_a(ledger: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame,
                                            dict]:
    """Preserved ledger representation.

    POPULATION DENOMINATOR FIRST (registered rule): the dev-start
    denominator is established from ALL dev-block rows BEFORE any
    null-probability filtering, so a start whose slots are all unusable
    still appears in the population and is excluded with a reason.

    Protected partition + target-date boundaries (explicit):
    - block labels outside DEV_BLOCKS + {confirm_2025H2} -> FAIL;
    - every consumed dev row's block label must equal the label derived
      from its game_date by the registered ``ad.add_block`` bounds
      (block/date inconsistency fails loud);
    - ``confirm_2025H2`` rows (and any row dated after the dev boundary)
      are dropped and only their COUNT is recorded (never compared).
    """
    blocks = set(ledger["block"].unique().to_list())
    unexpected = blocks - set(DEV_BLOCKS) - {PROTECTED_BLOCK}
    if unexpected:
        raise StageAFailure(
            f"unexpected block labels in the ledger frame: "
            f"{sorted(unexpected)}; allowed: {sorted(DEV_BLOCKS)} + "
            f"protected {PROTECTED_BLOCK} (dropped, never compared)")
    # population denominator BEFORE any null-probability filtering
    dev = ledger.filter(pl.col("block").is_in(list(DEV_BLOCKS)))
    dev_starts = (dev.select("game_pk", "side", "pitcher")
                  .unique().sort("game_pk", "side", "pitcher"))
    # block/date consistency via the registered bounds (helper reuse:
    # ad.add_block IS the registered block rule). Gate order:
    # (a) target-date boundary -- a DEV-labeled row dated past the
    #     2025-06-30 boundary is refused (protected partition);
    # (b) label/date consistency -- a DEV-labeled row inside the window
    #     whose label contradicts its date is refused.
    derived = ad.add_block(dev.select("game_date"))["block"].alias(
        "_expected_block")
    labeled = dev.with_columns(derived)
    over_boundary = labeled.filter(
        pl.col("_expected_block") == PROTECTED_BLOCK)
    if over_boundary.height:
        raise StageAFailure(
            "dev_rows_past_target_date_boundary: dev-labeled rows with "
            f"game_date after {DEV_LAST_DATE}: {over_boundary.height}")
    inconsistent = labeled.filter(
        pl.col("_expected_block") != pl.col("block"))
    if inconsistent.height:
        examples = inconsistent.head(5).select(
            "game_pk", "slot", "block", "_expected_block").rows()
        raise StageAFailure(
            f"block_date_inconsistent: {examples}")
    # protected partition: confirm-labeled rows are dropped BEFORE any
    # comparison; only their count is recorded
    protected_rows = int((ledger["block"] == PROTECTED_BLOCK).sum())
    dev = dev.filter(pl.col("block") != PROTECTED_BLOCK)
    usable = dev.filter(pl.col("p_h3_raw").is_not_null())
    dropped_unusable = int(dev.height - usable.height)
    route_a = usable.select(
        "game_pk", "side", "pitcher", "game_date", "slot", "batter",
        "block", *FEATURES, "p_h3_raw",
    )
    dup = route_a.group_by("game_pk", "side", "pitcher", "slot").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    if dup:
        raise StageAFailure(
            f"route A (start, slot) keys not unique: {dup} duplicates")
    meta = {"protected_rows_dropped": protected_rows,
            "unusable_slot_rows_dropped": dropped_unusable,
            "n_dev_rows_unfiltered": int(ledger.filter(
                pl.col("block").is_in(list(DEV_BLOCKS))).height)}
    return route_a, dev_starts, meta


def _route_b(lineups: pl.DataFrame, pa_table: pl.DataFrame,
             models: dict) -> pl.DataFrame:
    """Reconstructed attachment representation: pregame PA history ->
    daily states -> projected lineups -> attach_prior_features -> frozen
    checkpoint coefficients. Shares NO computed object with route A."""
    p_daily = ad.entity_daily_state(pa_table, "pitcher")
    b_daily = ad.entity_daily_state(pa_table, "batter")
    lg = ad.league_daily_state(pa_table)
    long, _n_uncovered = ad.projected_long(lineups)
    pf = ad.attach_prior_features(long, p_daily, b_daily, lg)
    pf = ad.add_block(pf)
    probs = np.full(pf.height, np.nan, dtype=np.float64)
    for block in pf["block"].unique().to_list():
        if block not in models:
            raise StageAFailure(
                f"checkpoint models missing block {block}")
        mask = (pf["block"] == block).to_numpy()
        probs[mask] = ad.apply_h3_raw(
            pf.filter(pl.col("block") == block), models[block])
    route_b = pf.with_columns(
        pl.Series("p_h3_raw", probs)).select(
        "game_pk", "side", "pitcher", "game_date", "slot", "batter",
        "block", *FEATURES, "p_h3_raw")
    dup = route_b.group_by("game_pk", "side", "pitcher", "slot").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    if dup:
        raise StageAFailure(
            f"route B (start, slot) keys not unique: {dup} duplicates")
    return route_b


def _write_json(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload, indent=1, sort_keys=True),
                    encoding="utf-8")
    return ad.sha256_file(path)


def run_stage_a(ledger: pl.DataFrame, lineups: pl.DataFrame,
                pa_table: pl.DataFrame, bf: pl.DataFrame,
                models: dict, out_dir, *, tol: float = TOL,
                file_sha256: dict | None = None,
                checkpoint_meta: dict | None = None) -> dict:
    """Execute the Stage A prediction-path reconciliation (synthetic or
    real frames; pure over injected frames)."""
    # ---- stage 0: prohibited-input gates (BEFORE any output creation)
    for name, frame in (("ledger", ledger), ("lineups", lineups),
                        ("bf", bf)):
        assert_no_realized_labels(frame, name)
    assert_no_realized_labels(
        pa_table.select(
            [c for c in pa_table.columns if c != PERMITTED_HISTORY_LABEL]),
        "pa_table")

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)

    initial = {
        "stage": STAGE,
        "inputs": {
            "consumed": {
                "ledger_frame_sha256": m0._frame_sha(ledger),
                "lineups_frame_sha256": m0._frame_sha(lineups),
                "pa_table_frame_sha256": m0._frame_sha(pa_table),
                "bf_frame_sha256": m0._frame_sha(bf),
            },
            "file_sha256": dict(file_sha256 or {}),
        },
        "code_config": {
            "code_identity": _code_identity(),
            "method": ("keyed prediction-path reconciliation: preserved "
                       "ledger representation vs reconstructed attachment "
                       "representation"),
            "features": FEATURES,
            "blocks": list(DEV_BLOCKS),
            "tolerance": tol,
            "feature_tolerance": 0.0,
            "checkpoint_meta": checkpoint_meta or {},
            "outcome_score_free": True,
        },
    }
    initial_path = out_dir / "receipt_initial.json"
    initial_sha = _write_json(initial_path, initial)

    def fail(gate: str, detail: dict) -> None:
        rec = {"stage": STAGE, "failure": True, "gate": gate,
               "detail": detail, "initial_receipt_sha256": initial_sha}
        _write_json(out_dir / "failure_record.json", rec)
        raise StageAFailure(json.dumps(rec, sort_keys=True))

    try:
        # ---- routes ----------------------------------------------------
        # Population denominator FIRST (registered rule): dev_starts comes
        # from the unfiltered dev-block rows, before any null-probability
        # filtering, so starts whose slots are all unusable still appear
        # in the denominator and their exclusion bucket.
        route_a, dev_starts, a_meta = _route_a(ledger)
        route_b = _route_b(lineups, pa_table, models)

        # ---- mutually exclusive exclusion accounting -------------------
        start_key = ["game_pk", "side", "pitcher"]
        lineup_starts = set(map(tuple, lineups.select(
            "game_pk", "side", "pitcher").unique().iter_rows()))
        bf_starts = set(map(tuple, bf.select(*start_key).unique()
                            .iter_rows()))
        slots_a = route_a.group_by(*start_key).agg(
            n=pl.len(), min_slot=pl.col("slot").min(),
            max_slot=pl.col("slot").max())
        full_a = set(map(tuple, slots_a.filter(
            (pl.col("n") == 9) & (pl.col("min_slot") == 1)
            & (pl.col("max_slot") == 9)).select(*start_key).iter_rows()))
        excluded = {}  # exclusive buckets, first-match priority
        compared = []
        for key in dev_starts.iter_rows():
            if key not in lineup_starts:
                excluded[key] = "missing_lineup_coverage"
            elif key not in full_a:
                excluded[key] = "slot_coverage_below_9"
            elif key not in bf_starts:
                excluded[key] = "missing_bf"
            else:
                compared.append(key)
        n_total = dev_starts.height
        if len(excluded) + len(compared) != n_total:
            fail("population_sum_check", {
                "n_dev_starts": n_total,
                "n_compared": len(compared),
                "n_excluded": len(excluded)})

        # ---- I1: keyed per-slot feature + batter comparison (exact) ----
        a = route_a.join(pl.DataFrame(compared, schema={
            "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64},
            orient="row"), on=start_key, how="semi")
        b = route_b.join(a.select(*start_key).unique(), on=start_key,
                         how="semi")
        j = a.join(b, on=start_key + ["slot"], suffix="_rb",
                   validate="1:1")
        if j.height != a.height:
            fail("I1_keying", {"route_a_rows": a.height,
                               "joined_rows": j.height})
        i1_rows = []
        i1_bad = []
        for r in j.iter_rows(named=True):
            bad = []
            if r["batter"] != r["batter_rb"]:
                bad.append("batter")
            for f in FEATURES:
                if float(r[f]) != float(r[f + "_rb"]):
                    bad.append(f)
            i1_rows.append({
                "game_pk": r["game_pk"], "side": r["side"],
                "pitcher": r["pitcher"], "slot": r["slot"],
                "batter_match": "batter" not in bad,
                "features_match": not bad or bad == ["batter"],
                "mismatched_fields": sorted(bad)})
            if bad:
                i1_bad.append((r["game_pk"], r["side"], r["pitcher"],
                               r["slot"], sorted(bad)))
        pl.DataFrame(i1_rows).write_parquet(
            out_dir / "i1_feature_comparison.parquet")
        if i1_bad:
            fail("I1_feature_mismatch", {
                "n_mismatched_slots": len(i1_bad),
                "examples": i1_bad[:20]})

        # ---- I2: keyed per-slot p_h3_raw comparison (<= tol) -----------
        j = j.with_columns(
            (pl.col("p_h3_raw") - pl.col("p_h3_raw_rb")).abs()
            .alias("abs_diff"))
        i2_max = float(j["abs_diff"].max())
        i2_bad = j.filter(pl.col("abs_diff") > tol)
        j.select("game_pk", "side", "pitcher", "slot", "p_h3_raw",
                 "p_h3_raw_rb", "abs_diff").write_parquet(
            out_dir / "i2_prob_comparison.parquet")
        if i2_bad.height:
            fail("I2_prob_mismatch", {
                "n_slots_over_tol": i2_bad.height,
                "max_abs_diff": i2_max,
                "examples": i2_bad.head(20).select(
                    *start_key, "slot", "abs_diff").rows()})

        # ---- I3/I4: PMF comparison under identical semantic order ------
        bf37_cols = [f"pmf37_{k}" for k in range(37)]
        cmp_starts = pl.DataFrame(compared, schema={
            "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64},
            orient="row")
        bf_cmp = bf.join(cmp_starts, on=start_key, how="semi")
        ad.validate_bf37_by_start(bf_cmp, cmp_starts)
        bf_lookup = {(r["game_pk"], r["side"], r["pitcher"]): np.asarray(
            [r[c] for c in bf37_cols], dtype=np.float64)
            for r in bf_cmp.iter_rows(named=True)}
        i3_rows = []
        i4_max = 0.0
        for key in compared:
            gk, side, pid = key
            p9_a = (route_a.filter(
                (pl.col("game_pk") == gk) & (pl.col("side") == side)
                & (pl.col("pitcher") == pid))
                .sort("slot")["p_h3_raw"].to_numpy())
            p9_b = (route_b.filter(
                (pl.col("game_pk") == gk) & (pl.col("side") == side)
                & (pl.col("pitcher") == pid))
                .sort("slot")["p_h3_raw"].to_numpy())
            if p9_a.shape != (9,) or p9_b.shape != (9,):
                fail("I3_slot_shape", {"key": key,
                                       "a": p9_a.shape, "b": p9_b.shape})
            # semantic order already proven identical by I1 (batter per
            # slot); workload: the SAME bf37 row feeds both arms
            bf37 = bf_lookup[key]
            pmf_a = ad.start_count_pmfs(p9_a, p9_a, bf37)["pmf_h3_raw"]
            pmf_b = ad.start_count_pmfs(p9_b, p9_b, bf37)["pmf_h3_raw"]
            d = np.abs(pmf_a - pmf_b)
            i4_max = max(i4_max, float(d.max()))
            for k in range(24):
                i3_rows.append({
                    "game_pk": gk, "side": side, "pitcher": pid,
                    "bucket": k, "pmf_route_a": float(pmf_a[k]),
                    "pmf_route_b": float(pmf_b[k]),
                    "abs_diff": float(d[k])})
        pl.DataFrame(i3_rows).write_parquet(
            out_dir / "i3_pmf_comparison.parquet")
        if i4_max > tol:
            fail("I4_control_max_diff", {
                "control_max_abs_pmf_diff": i4_max, "tolerance": tol})

        # ---- PASS receipt ----------------------------------------------
        exclusions_frame = pl.DataFrame(
            [{"game_pk": k[0], "side": k[1], "pitcher": k[2],
              "reason": v} for k, v in excluded.items()],
            schema={"game_pk": pl.Int64, "side": pl.Utf8,
                    "pitcher": pl.Int64, "reason": pl.Utf8},
        ) if excluded else pl.DataFrame(
            schema={"game_pk": pl.Int64, "side": pl.Utf8,
                    "pitcher": pl.Int64, "reason": pl.Utf8})
        exclusions_frame.write_parquet(out_dir / "exclusions.parquet")
        bucket_counts = {}
        for v in excluded.values():
            bucket_counts[v] = bucket_counts.get(v, 0) + 1
        metrics = {
            "n_dev_starts": n_total,
            "n_compared": len(compared),
            "n_excluded": len(excluded),
            "exclusion_buckets": bucket_counts,
            "population_sum_check": len(excluded) + len(compared)
            == n_total,
            "route_a_protected_rows_dropped": a_meta[
                "protected_rows_dropped"],
            "route_a_unusable_slot_rows_dropped": a_meta[
                "unusable_slot_rows_dropped"],
            "n_dev_rows_unfiltered": a_meta["n_dev_rows_unfiltered"],
            "i1_mismatched_slots": 0,
            "i2_max_abs_diff": i2_max,
            "i4_control_max_abs_pmf_diff": i4_max,
            "tolerance": tol,
            "acceptance": "prediction_path_equivalent",
        }
        final = dict(initial)
        final["metrics"] = metrics
        final["outputs"] = {
            "i1_feature_comparison.parquet": ad.sha256_file(
                out_dir / "i1_feature_comparison.parquet"),
            "i2_prob_comparison.parquet": ad.sha256_file(
                out_dir / "i2_prob_comparison.parquet"),
            "i3_pmf_comparison.parquet": ad.sha256_file(
                out_dir / "i3_pmf_comparison.parquet"),
            "exclusions.parquet": ad.sha256_file(
                out_dir / "exclusions.parquet"),
        }
        final["acceptance"] = {
            "receipt_chain": initial_sha,
            "status": "PASS"}
        _write_json(out_dir / "receipt_final.json", final)
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
        return {"out_dir": str(out_dir), "metrics": metrics,
                "status": "PASS", "receipt_initial_sha256": initial_sha}
    except StageAFailure as exc:
        # route-stage gate failures (raised inside _route_a/_route_b)
        # must also leave a failure receipt chained to the initial one
        fr = out_dir / "failure_record.json"
        if not fr.exists():
            _write_json(fr, {"stage": STAGE, "failure": True,
                             "gate": "route_stage",
                             "detail": {"error": str(exc)[:500]},
                             "initial_receipt_sha256": initial_sha})
        raise
    except Exception as exc:
        fail("unexpected_error", {"error": repr(exc)})


def _load_models(path) -> tuple[dict, dict]:  # noqa: ANN001
    """Checkpoint loader seam (real path: the registered-pin-enforced
    serialized-checkpoint loader). Tests may monkeypatch this single seam
    to inject synthetic models while exercising the identical CLI path."""
    return ad.load_serialized_checkpoint(path)


def main(argv=None) -> int:
    """Registered Stage A CLI. Exit codes: 0 PASS; 1 registered gate
    failure (failure receipt written); 2 refusal (prohibited labels,
    write-once violation, missing/mismatched input identity)."""
    p = argparse.ArgumentParser(
        description=("Stage A prediction-path reconciliation (registered, "
                     "write-once, outcome-score-free)."))
    p.add_argument("--ledger", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--pa-table", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--bf", required=True)
    p.add_argument("--out-dir", required=True)
    for name in ("ledger", "lineups", "pa-table", "bf", "checkpoint"):
        p.add_argument(f"--expected-{name}-sha", required=True)
    args = p.parse_args(argv)

    files = {"ledger": Path(args.ledger), "lineups": Path(args.lineups),
             "pa-table": Path(args.pa_table),
             "checkpoint": Path(args.checkpoint), "bf": Path(args.bf)}
    expected = {"ledger": args.expected_ledger_sha,
                "lineups": args.expected_lineups_sha,
                "pa-table": args.expected_pa_table_sha,
                "checkpoint": args.expected_checkpoint_sha,
                "bf": args.expected_bf_sha}
    file_sha = {}
    for name, path in files.items():
        if not path.exists():
            print(f"INPUT MISSING: {name}: {path}", file=sys.stderr)
            return 2
        sha = _sha_file(path)
        if sha != expected[name].lower():
            print(f"INPUT IDENTITY MISMATCH: {name}: sha256 {sha} != "
                  f"expected {expected[name]}", file=sys.stderr)
            return 2
        file_sha[name] = sha

    ledger = pl.read_parquet(files["ledger"])
    lineups = pl.read_parquet(files["lineups"])
    pa_table = pl.read_parquet(files["pa-table"])
    bf = pl.read_parquet(files["bf"])
    try:
        models, checkpoint_meta = _load_models(files["checkpoint"])
    except ad.AdapterError as exc:
        print(f"CHECKPOINT REFUSED: {exc}", file=sys.stderr)
        return 2
    try:
        result = run_stage_a(
            ledger, lineups, pa_table, bf, models, args.out_dir,
            file_sha256=file_sha, checkpoint_meta=checkpoint_meta)
    except StageAFailure as exc:
        print(f"STAGE A FAIL: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"STAGE A REFUSED: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"STAGE A REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["metrics"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
