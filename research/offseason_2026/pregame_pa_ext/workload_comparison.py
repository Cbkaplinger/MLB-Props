"""Workload personalization comparison (W0 pooled vs W1 pitcher-specific
BF), thin wrapper around the REGISTERED machinery.

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Reuses: m0_multiclass (labels, fit_multinomial, apply_multinomial),
adapter (projected_long, attach_prior_features, start_count_pmfs,
validate_bf37_by_start, bf_pmf_from_37), statcast_event_bridge
(terminal-event labels), baseline_ladder.paired_contrast (slate-date
bootstrap), kc.count_rps. Adds NO statistical machinery.

Primary contrast: delta = RPS(W1) - RPS(W0) per start on identical
assessment keys. W0 uses pooled empirical BF37 (add-one smoothing,
registered tail); W1 uses registered bf-workload-v1 pitcher-specific
PMFs. Both arms share the same keyed PA probabilities, assessment
cohort, and aggregation. The ONLY difference is BF personalization.
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
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-WORKLOAD-PERSONALIZATION-V1"
EXPERIMENT_ID = "workload_personalization_w0v1"
K_CLASS = m0.K_CLASS
FEATURES = list(m0.FEATURES)
EVAL_BLOCK = "block_2025H1"
REQ_KEYS = ["game_pk", "side", "pitcher"]
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
LINEUP_COLUMNS = REQ_KEYS + ["game_date", "nine_distinct"] + [
    f"u_slot_{i}" for i in range(1, 10)]


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pooled_bf37(pa_rows: pl.DataFrame) -> np.ndarray:
    """Pooled empirical BF37 from starter-outing totals derived from
    PA-level rows, add-one smoothing, registered tail convention.

    Derives one observation per (game_pk, pitcher) outing by
    counting PAs per start, then builds the BF37 histogram from
    outing-level BF totals. Grouping by (game_pk, pitcher) avoids
    requiring a side column in the PA source; the (game_pk, pitcher)
    pair uniquely identifies a starter outing."""
    outings = pa_rows.group_by("game_pk", "pitcher").agg(
        realized_bf=pl.len()
    )
    v = outings["realized_bf"].to_numpy()
    counts = np.zeros(37)
    for b in v:
        counts[min(int(b), 37) - 1] += 1.0
    return (counts + 1.0) / (counts.sum() + 37.0)


def run_workload_comparison(
        pa: pl.DataFrame, lineups: pl.DataFrame,
        assessment: pl.DataFrame,
        bf_w1: pl.DataFrame,
        out_dir, *,
        train_start: str, train_end: str,
        execution_ack: str,
        raw_events: list | None = None,
        ack_route: str = "direct-call") -> dict:
    """Execute the workload personalization comparison."""
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid; refusing "
            "(technical gate only)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    failure_path = out_dir / "failure_record.json"
    initial_path = out_dir / "receipt_initial.json"

    code_identity = {
        "runner_sha256": _sha_file(Path(__file__)),
        "adapter_sha256": _sha_file(Path(ad.__file__)),
        "m0_multiclass_sha256": _sha_file(Path(m0.__file__)),
        "kcount_combiner_sha256": _sha_file(Path(kc.__file__)),
    }
    config = {
        "experiment_identity": EXPERIMENT_ID,
        "train_window": [train_start, train_end],
        "primary_pair": ["W1_pitcher_specific", "W0_pooled_league"],
        "primary_contrast": "RPS(W1) - RPS(W0) per start",
        "n_boot": 2000, "seed": 20261001,
        "interpretation": ("delta < 0: pitcher-specific workload improves "
                           "count forecasts; CI overlapping zero is "
                           "inconclusive"),
    }
    initial = {"execution_acknowledgement": {"route": ack_route,
               "token": execution_ack},
               "code_identity": code_identity, "config": config,
               "counts": None}
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- labels: bridge over the ACTUAL schema -------------------
        _require_columns(pa, ["game_date", "game_pk", "at_bat_number",
                              "pitcher", "batter", "y"], "PA source")
        if not raw_events:
            raise ValueError("raw_events required")
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, raw_events, out_dir=out_dir)

        # ---- training split -----------------------------------------
        train = pa_labeled.filter(
            (pl.col("game_date") >= pl.date(
                *map(int, train_start.split("-"))))
            & (pl.col("game_date") <= pl.date(
                *map(int, train_end.split("-"))))
            & (pl.col("class_label") >= 0))
        if train.height == 0:
            raise ValueError("empty training population")
        train_cutoffs = train["game_date"].unique().to_list()

        # ---- requests through projected_long ------------------------
        _require_columns(lineups, LINEUP_COLUMNS, "projected lineups")
        long, n_uncovered = ad.projected_long(lineups)
        if long.height == 0:
            raise ValueError("empty projection request population")
        request_cutoffs = long["game_date"].unique().to_list()

        # ---- states + features (v2 cutoff, full y-based population) --
        p_v2, b_v2, lg_v2, _ = fv.build_v2_states(
            pa, train_cutoffs + request_cutoffs)
        feat_train = ad.attach_prior_features(
            train.select("game_date", "pitcher", "batter", "class_label"),
            p_v2, b_v2, lg_v2)
        feat_req = ad.attach_prior_features(
            long.select("game_date", "pitcher", "batter", "game_pk",
                        "side", "slot"),
            p_v2, b_v2, lg_v2)
        for fname, fframe in (("training", feat_train),
                              ("request", feat_req)):
            bad = {c: fframe[c].null_count() for c in FEATURES
                   if c in fframe.columns and fframe[c].null_count() > 0}
            if bad:
                raise ValueError(
                    f"{fname} features contain nulls {bad}: history "
                    "window does not precede the earliest cutoff")

        # ---- multinomial fit (shared PA model) ----------------------
        model = m0.fit_multinomial(feat_train)
        probs = m0.apply_multinomial(feat_req, model)
        forecast_table = feat_req.with_columns(
            pl.Series("p_k", probs[:, K_CLASS]),
        ).select("game_pk", "side", "pitcher", "slot", "batter", "p_k")

        # ---- W0: pooled BF37 ----------------------------------------
        pooled_bf37 = _pooled_bf37(train)

        # ---- W1: registered BF workload ------------------------------
        bf_val, _ = ad.validate_bf37_by_start(
            bf_w1, long.select(*REQ_KEYS, "game_date").unique()
            .sort(*REQ_KEYS))
        bf_w1_lookup = {}
        for r in bf_val.select(
                "game_pk", "side", "pitcher",
                *[f"pmf37_{j}" for j in range(37)]).iter_rows(named=True):
            bf_w1_lookup[(int(r["game_pk"]), str(r["side"]),
                          int(r["pitcher"]))] = np.asarray(
                [r[f"pmf37_{j}"] for j in range(37)], dtype=np.float64)

        # ---- assessment cohort ---------------------------------------
        _require_columns(assessment, ASSESS_COLUMNS, "assessment outcomes")
        if assessment.height == 0:
            raise ValueError("empty assessment outcome population")
        actual = assessment.select(
            "game_pk", "side", "pitcher", "at_bat_number", "batter",
            "class_label").with_columns(
            (pl.col("class_label") == K_CLASS).cast(pl.Int64)
            .alias("is_k"))
        if actual.select("game_pk", "side", "pitcher", "at_bat_number",
                         "batter").n_unique() != actual.height:
            raise ValueError("duplicate actual-PA identity rows")
        k_real_df = actual.group_by(*REQ_KEYS).agg(
            realized_k=pl.col("is_k").sum())
        realized = {(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"])): int(r["realized_k"])
                    for r in k_real_df.iter_rows(named=True)}
        # dates from validated request keys (not assessment rows)
        dates = {}
        for r in long.select(*REQ_KEYS, "game_date").unique() \
                .sort(*REQ_KEYS).iter_rows(named=True):
            dates[(int(r["game_pk"]), str(r["side"]),
                   int(r["pitcher"]))] = r["game_date"]

        # ---- build W0 and W1 count PMFs ------------------------------
        fc_by_start = {}
        for r in forecast_table.iter_rows(named=True):
            key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            fc_by_start.setdefault(key, {})[int(r["slot"])] = r["p_k"]

        pmf_w0 = {}
        pmf_w1 = {}
        for key in sorted(realized):
            slots = fc_by_start.get(key, {})
            if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                raise ValueError(
                    f"start {key} does not have 9 usable slots "
                    f"({len(slots)}); count aggregation requires the "
                    "full key")
            p9 = np.asarray([slots[i] for i in range(1, 10)])
            # W1: pitcher-specific workload (BF37 passed directly;
            # start_count_pmfs internally converts to extended)
            pmf_w1[key] = ad.start_count_pmfs(
                p9, p9, bf_w1_lookup[key])["pmf_h3_raw"]
            # W0: pooled workload (same p9, pooled BF37)
            pmf_w0[key] = ad.start_count_pmfs(
                p9, p9, pooled_bf37)["pmf_h3_raw"]

        # ---- scores ---------------------------------------------------
        rps_w0 = {k: kc.count_rps(pmf_w0[k], realized[k])
                  for k in sorted(realized)}
        rps_w1 = {k: kc.count_rps(pmf_w1[k], realized[k])
                  for k in sorted(realized)}
        blocks = {k: "block_2025H1" for k in realized}
        paired_raw = bl.paired_contrast(rps_w1, rps_w0, dates, blocks,
                                        n_boot=2000, seed=20261001)
        paired = dict(paired_raw)
        paired["primary_pair"] = "W1_pitcher_specific_vs_W0_pooled_league"
        paired["contrast"] = "RPS(W1) - RPS(W0) per start"
        paired["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; here delta_a_minus_b = RPS(W1) - RPS(W0)")

        # ---- outputs ---------------------------------------------------
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(realized)],
            "side": [k[1] for k in sorted(realized)],
            "pitcher": [k[2] for k in sorted(realized)],
            "realized_k": [realized[k] for k in sorted(realized)],
            "rps_w0_pooled": [rps_w0[k] for k in sorted(realized)],
            "rps_w1_pitcher": [rps_w1[k] for k in sorted(realized)],
            "rps_diff": [rps_w1[k] - rps_w0[k] for k in sorted(realized)],
        })
        per_start_path = out_dir / "workload_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)

        report = {
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": "RPS(W1) - RPS(W0) per start",
            "n_starts": len(realized),
            "mean_rps_w0": float(np.mean(list(rps_w0.values()))),
            "mean_rps_w1": float(np.mean(list(rps_w1.values()))),
            "paired_contrast": paired,
        }
        report_path = out_dir / "workload_comparison_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                          sort_keys=True, default=str),
                               encoding="utf-8")
        outputs = {
            "workload_per_start_v1.parquet": ad.sha256_file(per_start_path),
            "workload_comparison_report.json": ad.sha256_file(report_path),
        }
        final = dict(initial)
        final["counts"] = {"n_starts": len(realized)}
        final["outputs"] = outputs
        final["primary_contrast"] = paired
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        (out_dir / "receipt_final.json").write_text(
            json.dumps(final, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "workload_personalization", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": paired,
            "mean_rps_w0": report["mean_rps_w0"],
            "mean_rps_w1": report["mean_rps_w1"],
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def _require_columns(frame, required, name):
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Workload personalization comparison (W0 vs W1). "
                    "Technical ack gate only.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--assessment", required=True)
    p.add_argument("--bf-source", required=True,
                   help="registered bf-workload-v1 per-start BF PMF artifact")
    p.add_argument("--raw-events", required=True,
                   help="comma-separated explicit raw Statcast parquet paths")
    p.add_argument("--train-start", required=True)
    p.add_argument("--train-end", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--execution-ack", required=True)
    args = p.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: invalid acknowledgement; no input "
              "read, nothing created.", file=sys.stderr)
        return 2
    pa = pl.read_parquet(args.pa_source)
    lineups = pl.read_parquet(args.lineups)
    assessment = pl.read_parquet(args.assessment)
    bf_w1 = pl.read_parquet(args.bf_source)
    raw_events = [s for s in args.raw_events.split(",") if s]
    res = run_workload_comparison(
        pa, lineups, assessment, bf_w1, args.out_dir,
        train_start=args.train_start, train_end=args.train_end,
        execution_ack=args.execution_ack, raw_events=raw_events,
        ack_route="cli")
    print(json.dumps({"experiment": res["experiment_identity"],
                      "primary_contrast": res["primary_contrast"],
                      "mean_rps_w0": res["mean_rps_w0"],
                      "mean_rps_w1": res["mean_rps_w1"],
                      "out_dir": res["out_dir"]},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
