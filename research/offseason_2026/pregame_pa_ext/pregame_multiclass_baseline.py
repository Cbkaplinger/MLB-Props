"""End-to-end pregame multiclass baseline runner (baseline ID
pregame_multiclass_baseline_v1).

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
One invocation connects the EXISTING components under the APPROVED
forecast-cutoff state contract (forecast_states_v2.STATES_V2_ID):

    completed-PA labels (m0 four-class taxonomy, K_CLASS=0 strikeout)
      -> training-only population class proportions   (Reference 0)
      -> cutoff-correct pitcher/batter/league states  (states v2)
      -> frozen attach_prior_features feature construction
      -> m0 fit_multinomial / apply_multinomial       (Reference 1)
      -> K marginal (= strikeout class probability)
      -> fixed-workload count aggregation (start_count_pmfs)
      -> PA log-loss + count-RPS vs separate assessment outcomes
      -> report + receipts

Retained references: population multiclass reference (Ref 0) and the
regularized multinomial baseline (Ref 1). The legacy binary checkpoint
is NOT consumed here (historical control, limitations disclosed).
Projected lineups (wide, u_slot_1..9) are the ONLY request source; the
oracle-lineage manifest mode is never accepted here.

ASSESSMENT OUTCOMES enter ONLY the scoring stage: they are a separate
input, never touched by estimation, states, or features. State
construction is cutoff-correct by construction (forecast_states_v2).

Exit codes: 0 completed; 2 ack refused (zero side effects); fail-loud
guards write failure_record.json and raise. No retry, no repair.
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
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-PREGAME-MULTICLASS-BASELINE-V1"
BASELINE_ID = "pregame_multiclass_baseline_v1"
K_CLASS = m0.K_CLASS
CLASS_NAMES = list(m0.CLASS_NAMES)
N_CLASSES = m0.N_CLASSES
FEATURES = list(m0.FEATURES)

PA_COLUMNS = ["game_date", "game_pk", "pitcher", "batter", "events"]
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
REQ_KEYS = ["game_pk", "side", "pitcher"]


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_columns(frame: pl.DataFrame, required: list, name: str) -> None:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


def run_pregame_multiclass_baseline(pa: pl.DataFrame, lineups: pl.DataFrame,
                                    assessment: pl.DataFrame, bf: pl.DataFrame,
                                    out_dir, *,
                                    train_start: str, train_end: str,
                                    execution_ack: str,
                                    ack_route: str = "direct-call") -> dict:
    """Execute the synthetic-capable end-to-end multiclass baseline.

    pa: completed-PA source (game_date, game_pk, pitcher, batter, events).
    lineups: projected-lineup requests (wide: game_pk, side, pitcher,
        game_date, nine_distinct, u_slot_1..9) -- the declared actionable
        request source; oracle realized-lineup mode is not accepted here.
    assessment: separate per-PA outcome rows (game_pk, side, pitcher,
        slot, batter, class_label) used ONLY for scoring.
    bf: registered bf-workload-v1 start-grain pmf37 frame.
    """
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid: refusing "
            "before any input handling (technical gate only, not owner "
            "authorization)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    code_identity = {
        "runner_sha256": _file_sha(Path(__file__)),
        "forecast_states_v2_sha256": _file_sha(Path(fv.__file__)),
        "m0_multiclass_sha256": _file_sha(Path(m0.__file__)),
        "adapter_sha256": _file_sha(Path(ad.__file__)),
        "kcount_combiner_sha256": _file_sha(Path(kc.__file__)),
    }
    config = {
        "baseline_identity": BASELINE_ID,
        "state_contract": fv.STATES_V2_ID,
        "taxonomy": {"n_classes": N_CLASSES, "names": CLASS_NAMES,
                     "k_class": K_CLASS},
        "train_window": [train_start, train_end],
        "feature_construction": ("adapter.attach_prior_features over "
                                 "forecast_states_v2 cutoff states; "
                                 "identical constructor for training "
                                 "and inference"),
        "lineup_source": "projected lineups (actionable; never oracle)",
        "references": ["population_training_proportions",
                       "regularized_multinomial"],
    }
    initial = {"execution_acknowledgement": {
        "route": ack_route, "token": execution_ack},
        "code_identity": code_identity, "config": config,
        "counts": None}
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- labels + split (assessment outcomes never enter here) ----
        _require_columns(pa, ["game_date", "game_pk", "at_bat_number",
                              "pitcher", "batter", "events"],
                         "PA source")
        labeled = m0.build_multiclass_labels(pa)
        train = labeled.filter(
            (pl.col("game_date") >= pl.date(*map(int,
                                              train_start.split("-"))))
            & (pl.col("game_date") <= pl.date(*map(int,
                                                   train_end.split("-"))))
            & (pl.col("class_label") >= 0))
        if train.height == 0:
            raise ValueError(
                "empty training population in the declared window: "
                "refusing rather than producing a vacuous baseline")
        train_cutoffs = train["game_date"].unique().to_list()

        # ---- requests through the real projected-lineup interface -----
        _require_columns(lineups, REQ_KEYS + ["game_date", "nine_distinct"]
                         + [f"u_slot_{i}" for i in range(1, 10)],
                         "projected lineups")
        long, n_uncovered = ad.projected_long(lineups)
        if long.height == 0:
            raise ValueError("empty projection request population: "
                             "refusing a vacuous baseline")
        if long.select(*REQ_KEYS, "slot").n_unique() != long.height:
            raise ValueError("duplicate (start, slot) request keys")
        request_cutoffs = long["game_date"].unique().to_list()
        request_dates = {(int(r["game_pk"]), str(r["side"]),
                          int(r["pitcher"])): r["game_date"]
                         for r in long.select(*REQ_KEYS, "game_date")
                         .unique().iter_rows(named=True)}

        # ---- cutoff-correct states (v2) for training AND inference ----
        p_v2, b_v2, lg_v2, state_meta = fv.build_v2_states(
            labeled, train_cutoffs + request_cutoffs)
        # class_label rides through the attach so rows stay aligned with
        # their features (attach sorts internally; never zip positionally)
        feat_train = ad.attach_prior_features(
            train.select("game_date", "pitcher", "batter", "class_label"),
            p_v2, b_v2, lg_v2)
        feat_req = ad.attach_prior_features(
            long.select("game_date", "pitcher", "batter", "game_pk",
                        "side", "slot"),
            p_v2, b_v2, lg_v2)
        for fname, fframe in (("training", feat_train),
                              ("request", feat_req)):
            nulls = {c: fframe[c].null_count() for c in FEATURES}
            bad = {c: n for c, n in nulls.items() if n}
            if bad:
                raise ValueError(
                    f"{fname} features contain nulls {bad}: the declared "
                    "history window does not precede the earliest cutoff; "
                    "refusing rather than fitting on imputed features")

        # ---- Reference 0: training-only population proportions --------
        k_rate = float((train["class_label"] == K_CLASS).mean())
        pop = np.zeros(N_CLASSES)
        for c in range(N_CLASSES):
            pop[c] = float((train["class_label"] == c).mean())
        if abs(pop.sum() - 1.0) > 1e-12 or not np.all(pop >= 0):
            raise ValueError("population class proportions invalid")

        # ---- Reference 1: regularized multinomial (existing) ----------
        model = m0.fit_multinomial(feat_train)
        probs_ref1 = m0.apply_multinomial(feat_req, model)

        # ---- K marginal = strikeout class probability -----------------
        p_k_ref1 = probs_ref1[:, K_CLASS]
        p_k_ref0 = np.full(long.height, k_rate)

        # ---- fixed-workload count aggregation --------------------------
        _require_columns(bf, REQ_KEYS + [f"pmf37_{j}" for j in range(37)],
                         "BF workload")
        # workload coverage is bucketed per start (missing_bf); the
        # registered validator then enforces distribution validity on the
        # COVERED subset only (fail-loud per scored start)
        bf_starts = set(map(tuple, bf.select(*REQ_KEYS).unique()
                            .iter_rows()))

        def _start_pmfs(p_k_vec: np.ndarray, keys: dict) -> dict:
            """Build count PMFs only for the requested starts (count-
            scoring population); a requested start lacking 9 usable
            slots or BF coverage must have been excluded upstream."""
            by_start = {}
            for r in long.with_columns(
                    pl.Series("p_k", p_k_vec)).iter_rows(named=True):
                key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
                if key not in keys:
                    continue
                by_start.setdefault(key, {})[int(r["slot"])] = r["p_k"]
            out = {}
            for key in keys:
                slots = by_start.get(key, {})
                if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                    raise ValueError(
                        f"count-scored start {key} lost slot coverage "
                        f"({len(slots)}); internal accounting error")
                if key not in bf_lookup:
                    raise ValueError(
                        f"count-scored start {key} lacks workload; "
                        "internal accounting error")
                p9 = np.asarray([slots[i] for i in range(1, 10)])
                out[key] = ad.start_count_pmfs(
                    p9, p9, bf_lookup[key])["pmf_h3_raw"]
            return out

        # ---- assessment scoring (outcomes enter ONLY here) -------------
        # Forecast-slot identity (projected (start, slot, batter)) is kept
        # separate from ACTUAL PA identity (game_pk, side, pitcher,
        # at_bat_number, batter). Actual PAs carry repeated encounters and
        # replacement batters; they are joined to forecasts by the
        # matchup key (game_pk, side, pitcher, batter) -- one forecast
        # probability per projected matchup, applied to every actual PA
        # of that matchup. Realized starter K is derived from ALL actual
        # completed PAs, independently of projected-lineup coverage.
        _require_columns(assessment, ASSESS_COLUMNS, "assessment outcomes")
        if assessment.height == 0:
            raise ValueError("empty assessment outcome population: "
                             "refusing a vacuous baseline")
        actual = assessment.select(
            "game_pk", "side", "pitcher", "at_bat_number", "batter",
            "class_label").with_columns(
            (pl.col("class_label") == K_CLASS).cast(pl.Int64)
            .alias("is_k"))
        if actual.select("game_pk", "side", "pitcher", "at_bat_number",
                         "batter").n_unique() != actual.height:
            raise ValueError("duplicate actual-PA identity rows "
                             "(game_pk, side, pitcher, at_bat_number, "
                             "batter)")
        # realized starter K from ALL valid completed PAs (independent of
        # projected-lineup coverage: replacement batters count)
        k_real = actual.group_by(*REQ_KEYS).agg(
            realized_k=pl.col("is_k").sum(),
            actual_pas=pl.len())
        realized = {(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"])): int(r["realized_k"])
                    for r in k_real.iter_rows(named=True)}

        # ---- explicit matchup alignment (never slot-keyed) -------------
        matchup = ["game_pk", "side", "pitcher", "batter"]
        fc = long.with_columns(
            pl.Series("p_k_fc", probs_ref1[:, K_CLASS]),
            pl.Series("row_ix", np.arange(long.height)))
        j = actual.join(fc.select("game_pk", "side", "pitcher", "slot",
                                  "batter", "p_k_fc", "row_ix"),
                        on=matchup, how="left", validate="m:1")
        matched = j.filter(pl.col("p_k_fc").is_not_null())
        n_unmatched_actual = j.height - matched.height
        fc_keys = set(map(tuple, fc.select(matchup).unique().iter_rows()))
        actual_keys = set(map(tuple, actual.select(matchup).unique()
                              .iter_rows()))
        n_proj_without_actual = len(fc_keys - actual_keys)
        y_pa = matched["class_label"].to_numpy()
        ix = matched["row_ix"].to_numpy()

        pa_ll_ref0 = float(-np.mean(np.log(np.clip(
            np.tile(pop, (long.height, 1))[ix], 1e-15, 1.0)[
                np.arange(matched.height), y_pa])))
        pa_ll_ref1 = float(m0.multiclass_log_loss(
            y_pa, probs_ref1[ix]))

        # ---- count-scoring coverage: explicit buckets, separate from
        # PA-exclusion accounting (realized K is independent of lineup
        # coverage: replacement batters count) ---------------------------
        lin_starts = set(map(tuple, long.select(*REQ_KEYS).unique()
                             .iter_rows()))
        bf_starts = set(map(tuple, bf.select(*REQ_KEYS).unique()
                            .iter_rows()))
        count_scored, count_excluded = {}, {}
        for key, k_tot in realized.items():
            if key not in lin_starts:
                count_excluded[key] = "no_projected_lineup_request"
            elif key not in bf_starts:
                count_excluded[key] = "missing_bf"
            elif sum(1 for r in long.iter_rows(named=True)
                     if (int(r["game_pk"]), str(r["side"]),
                         int(r["pitcher"])) == key) != 9:
                count_excluded[key] = "slot_coverage_below_9"
            else:
                count_scored[key] = k_tot
        if not count_scored:
            raise ValueError("empty count-scoring population: refusing a "
                             "vacuous baseline")
        covered = pl.DataFrame(
            [{"game_pk": k[0], "side": k[1], "pitcher": k[2],
              "game_date": request_dates[k]} for k in count_scored],
            schema={"game_pk": pl.Int64, "side": pl.Utf8,
                    "pitcher": pl.Int64, "game_date": pl.Date},
            orient="row")
        bf_val, bf_meta = ad.validate_bf37_by_start(
            bf, covered.sort(*REQ_KEYS))
        bf_lookup = {(int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"])): np.asarray(
            [r[f"pmf37_{j}"] for j in range(37)], dtype=np.float64)
            for r in bf_val.iter_rows(named=True)}
        pmfs_ref0 = _start_pmfs(p_k_ref0, count_scored)
        pmfs_ref1 = _start_pmfs(p_k_ref1, count_scored)
        count_scores = {}
        for name, pmfs in (("ref0_population", pmfs_ref0),
                           ("ref1_multinomial", pmfs_ref1)):
            count_scores[name] = float(np.mean([
                kc.count_rps(pmfs[k], realized[k])
                for k in sorted(count_scored)]))

        # ---- K-marginal binary probability scores (separate from the
        # multiclass score: coherence does not prove K quality) ---------
        y_k = (y_pa == K_CLASS).astype(int)
        clip = lambda p: np.clip(p, 1e-15, 1.0 - 1e-15)

        def _binary(p_vec):
            return {
                "log_loss": float(-np.mean(
                    y_k * np.log(clip(p_vec))
                    + (1 - y_k) * np.log(1 - clip(p_vec)))),
                "brier": float(np.mean((p_vec - y_k) ** 2)),
            }

        k_scores = {
            "ref0_population": _binary(np.full(matched.height,
                                               pop[K_CLASS])),
            "ref1_multinomial": _binary(matched["p_k_fc"].to_numpy()),
        }

        # ---- paired count-RPS uncertainty (registered slate-date
        # bootstrap on identical scored keys) ----------------------------
        start_dates = {k: request_dates[k] for k in count_scored}
        rps_ref0 = {k: kc.count_rps(pmfs_ref0[k], realized[k])
                    for k in count_scored}
        rps_ref1 = {k: kc.count_rps(pmfs_ref1[k], realized[k])
                    for k in count_scored}
        blocks = {k: ad.add_block(pl.DataFrame(
            {"game_date": [d]}))["block"][0] for k, d in start_dates.items()}
        paired_raw = bl.paired_contrast(
            rps_ref1, rps_ref0, start_dates, blocks, n_boot=2000,
            seed=20261001)
        paired = dict(paired_raw)
        paired["primary_pair"] = "ref1_multinomial_vs_ref0_population"
        paired["contrast"] = "RPS(Ref1) - RPS(Ref0) per start"
        paired["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; here delta_a_minus_b = RPS(Ref1) - RPS(Ref0)")
        paired["interpretation"] = (
            "delta < 0: multinomial beats population under the same "
            "workload; CI overlapping zero is inconclusive")

        # ---- outputs ----------------------------------------------------
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(count_scored)],
            "side": [k[1] for k in sorted(count_scored)],
            "pitcher": [k[2] for k in sorted(count_scored)],
            "realized_k": [count_scored[k] for k in sorted(count_scored)],
            "rps_ref0_population": [
                kc.count_rps(pmfs_ref0[k], count_scored[k])
                for k in sorted(count_scored)],
            "rps_ref1_multinomial": [
                kc.count_rps(pmfs_ref1[k], count_scored[k])
                for k in sorted(count_scored)],
        })
        per_start_path = out_dir / "multiclass_baseline_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)
        report = {
            "baseline_identity": BASELINE_ID,
            "state_contract": fv.STATES_V2_ID,
            "state_meta": state_meta,
            "taxonomy": {"names": CLASS_NAMES, "k_class": K_CLASS},
            "counts": {
                "pa_source_rows": labeled.height,
                "train_rows": train.height,
                "request_slots": long.height,
                "lineup_uncovered_slots": n_uncovered,
                "assessment_pas": assessment.height,
                "assessment_pas_matched_to_projections": matched.height,
                "assessment_pas_excluded_no_projected_matchup":
                    n_unmatched_actual,
                "projections_without_actual_pa": n_proj_without_actual,
                "assessment_starts": len(realized),
                "count_scored_starts": len(count_scored),
                "count_excluded_starts": {
                    r: sum(1 for v in count_excluded.values() if v == r)
                    for r in sorted(set(count_excluded.values()))},
            },
            "model_identity": {"family": "sklearn multinomial logistic "
                                         "(existing m0.fit_multinomial, "
                                         "C=1.0)",
                               "features": FEATURES,
                               "fitted_rows": int(train.height)},
            "workload": {"sha256_verified": bf_meta.get("n_starts_bf_matched"),
                         "refit": False,
                         "artifact": "bf-workload-v1 lineage"},
            "results": {
                "population_class_proportions": pop.tolist(),
                "pa_multiclass_log_loss": {"ref0_population": pa_ll_ref0,
                                           "ref1_multinomial": pa_ll_ref1},
                "mean_count_rps": count_scores,
                "k_marginal_binary": k_scores,
                "paired_count_rps_delta": paired,
                "k_marginal_column": K_CLASS,
            },
            "limitations": [
                "synthetic/development evidence only; not a production "
                "or betting claim",
                "population reference is training-only proportions",
                "multinomial baseline is regularized; coherence does not "
                "prevent overfitting",
            ],
        }
        report_path = out_dir / "multiclass_baseline_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                          sort_keys=True, default=str),
                               encoding="utf-8")
        outputs = {
            "multiclass_baseline_per_start_v1.parquet":
                ad.sha256_file(per_start_path),
            "multiclass_baseline_report.json": ad.sha256_file(report_path),
        }
        final = dict(initial)
        final["counts"] = report["counts"]
        final["state_meta"] = state_meta
        final["outputs"] = outputs
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        final_path = out_dir / "receipt_final.json"
        final_path.write_text(json.dumps(final, indent=1, sort_keys=True,
                                         default=str),
                              encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "pregame_multiclass_baseline", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir), "baseline_identity": BASELINE_ID,
            "results": report["results"], "counts": report["counts"],
            "outputs": outputs, "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="End-to-end pregame multiclass baseline (synthetic "
                    "or authorized real data). Technical ack gate only.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--assessment", required=True)
    p.add_argument("--bf-source", required=True)
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
    bf = pl.read_parquet(args.bf_source)
    res = run_pregame_multiclass_baseline(
        pa, lineups, assessment, bf, args.out_dir,
        train_start=args.train_start, train_end=args.train_end,
        execution_ack=args.execution_ack, ack_route="cli")
    print(json.dumps({"baseline_identity": res["baseline_identity"],
                      "results": res["results"],
                      "counts": res["counts"],
                      "out_dir": res["out_dir"]},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
