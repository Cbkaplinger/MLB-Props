"""Canonical ablation count-RPS computation on the INTENDED cohort
(all 4,823 eligible development starts, ledger-projected nine slots).

RESEARCH-ONLY, write-once outputs. v2 repairs (owner order 2026-10-22):
- training cutoff derived from the ACTUAL max game_date in the block's
  training range (rows strictly before cutoff - 59d), recorded in the
  receipt; PA-table postseason status stated;
- frozen-binary comparison: loads the REGISTERED per-start frozen PMFs
  (count_agg_eval_v1 pmf_baseline), asserts key-set equality, paired
  FULL - frozen_binary via the registered slate-date bootstrap;
- per-start output keyed on (game_pk, side, pitcher), one row per key,
  no nulls;
- confirm_2025H2 excluded before fitting/scoring; mutually exclusive
  drop counters that sum to (ledger starts - scored);
- no hardcoded frozen-binary numbers.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import ablation_features as ab  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

import kcount_combiner as kc  # noqa: E402

N_BOOT = 2000
SEED = 20261001
PROTECTED_BLOCK = "confirm_2025H2"


def run_ablation_count_rps(feat: "pl.DataFrame", pa: "pl.DataFrame",
                           ledger: "pl.DataFrame",
                           pmfs: "pl.DataFrame",
                           realized: "pl.DataFrame",
                           bf: "pl.DataFrame", out_dir, *,
                           n_boot: int = N_BOOT, seed: int = SEED,
                           ) -> dict:
    import polars as pl

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"
    initial = {
        "inputs": {
            "consumed": {
                "pa_features": m0._frame_sha(feat),
                "preserved_run_ledger": m0._frame_sha(ledger),
                "model_cohort_frame": m0._frame_sha(pmfs),
                "realized_counts_source": m0._frame_sha(realized),
                "bf_pmf": m0._frame_sha(bf),
            },
            "context_identities": {},
        },
        "code_config": {
            "feature_sets": {"PITCHER": ab.FEATURE_SETS["PITCHER"],
                             "FULL": ab.FEATURE_SETS["FULL"]},
            "population": ("the ledger's nine PROJECTED slot rows per "
                           "eligible DEV start (confirm_2025H2 excluded "
                           "before fitting/scoring)"),
            "bootstrap": {"n": n_boot, "seed": seed},
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        # mutually exclusive drop accounting, start-level
        ledger_starts = (ledger.filter(
            pl.col("exclusion_reason").is_null())
            .select("game_pk", "side", "pitcher", "block", "game_date")
            .unique(subset=["game_pk", "side", "pitcher"]))
        n_ledger_starts = ledger_starts.height
        confirm = ledger_starts.filter(pl.col("block") == PROTECTED_BLOCK)
        dev = ledger_starts.filter(pl.col("block") != PROTECTED_BLOCK)
        drops = {
            "confirm_block_excluded": confirm.height,
            "out_of_dev_window": 0,
            "nonfinite_feature_slot": 0,
            "fewer_than_9_slots": 0,
            "missing_bf": 0,
            "missing_realized_k": 0,
        }
        # training windows: cutoff derived from the ACTUAL max game_date
        # in each block's training range (rows strictly before cutoff-59d)
        train_windows = {}
        windows = {}
        for b in ("block_2024H2", "block_2025H1"):
            te = (date(2024, 6, 30) if b == "block_2024H2"
                  else date(2024, 12, 31))
            in_range = pa.filter(
                (pl.col("game_date") >= date(2023, 1, 1))
                & (pl.col("game_date") <= te))
            actual_max = in_range["game_date"].max()
            cutoff = actual_max - timedelta(days=59)
            ev_lo, ev_hi = ((date(2024, 7, 1), date(2024, 12, 31))
                            if b == "block_2024H2"
                            else (date(2025, 1, 1), date(2025, 6, 30)))
            windows[b] = {"train_lo": date(2023, 1, 1),
                          "cutoff": cutoff, "actual_max": actual_max,
                          "eval": (ev_lo, ev_hi)}
        # the pa_table covers REGULAR-SEASON files only (raw Savant
        # statcast_YYYY_regular); no postseason rows exist in it.
        postseason_note = ("pa_table is built from statcast_YYYY_regular "
                           "files only; it contains no postseason rows")
        bf_lookup = {(r["game_pk"], r["side"], r["pitcher"]):
                     np.asarray([r[f"pmf37_{k}"] for k in range(37)])
                     for r in bf.select(
                         "game_pk", "side", "pitcher",
                         *[f"pmf37_{k}" for k in range(37)])
                     .iter_rows(named=True)}
        realized_map = {(r["game_pk"], r["side"], r["pitcher"]):
                        int(r["realized_k"])
                        for r in realized.iter_rows(named=True)}

        arms = {}
        ledger_slots = (ledger.filter(
            pl.col("exclusion_reason").is_null()))
        for arm, features in (("PITCHER", ab.FEATURE_SETS["PITCHER"]),
                              ("FULL", ab.FEATURE_SETS["FULL"])):
            lslots = (ledger_slots.join(
                dev.select("game_pk", "side", "pitcher"),
                on=["game_pk", "side", "pitcher"], how="inner")
                .sort("game_pk", "side", "slot"))
            lslots = (lslots.select(
                "game_pk", "side", "pitcher", "slot", "game_date",
                *features)
                .filter(pl.all_horizontal([pl.col(c).is_finite()
                                           for c in features])))
            probs = np.full((lslots.height, m0.N_CLASSES), np.nan)
            idx = lslots.with_row_index("_i")
            for b, w in windows.items():
                train = feat.filter(
                    (pl.col("game_date") >= w["train_lo"])
                    & (pl.col("game_date") < w["cutoff"]))
                lo, hi = w["eval"]
                blk = idx.filter((pl.col("game_date") >= lo)
                                 & (pl.col("game_date") <= hi))
                model = ab.fit_multinomial_features(train, features)
                probs[blk["_i"].to_numpy()] = \
                    ab.apply_multinomial_features(blk.drop("_i"), model)
            lslots = lslots.with_columns(
                pl.Series("p_k", probs[:, m0.K_CLASS]))
            per_start = []
            n_fewer9 = 0
            n_bad_probs = 0
            n_missing_bf = 0
            n_missing_rk = 0
            for g in lslots.partition_by(["game_pk", "side", "pitcher"]):
                gpk = int(g["game_pk"][0])
                side = g["side"][0]
                pitcher = int(g["pitcher"][0])
                if g.height != 9:
                    n_fewer9 += 1
                    drops["fewer_than_9_slots"] += 1
                    continue
                p9 = np.asarray(g.sort("slot")["p_k"].to_list(),
                                dtype=np.float64)
                if (not np.all(np.isfinite(p9)) or p9.min() < 0
                        or p9.max() > 1):
                    n_bad_probs += 1
                    drops["nonfinite_feature_slot"] += 1
                    continue
                key = (gpk, side, pitcher)
                b37 = bf_lookup.get(key)
                if b37 is None:
                    n_missing_bf += 1
                    drops["missing_bf"] += 1
                    continue
                k_real = realized_map.get(key)
                if k_real is None:
                    n_missing_rk += 1
                    drops["missing_realized_k"] += 1
                    continue
                b37 = b37 / b37.sum()
                bf_ext = ad.bf_pmf_from_37(b37)
                pmf = ad.count_pmf_from_mixture(
                    bf_ext, ad.cycled_cond_mean(p9))
                gdate = g["game_date"][0]
                per_start.append({
                    "game_pk": gpk, "side": side, "pitcher": pitcher,
                    "game_date": str(gdate),
                    "block": ("block_2024H2" if gdate <= date(2024, 12, 31)
                              else "block_2025H1"),
                    "realized_k": k_real,
                    "rps": float(kc.count_rps(pmf, k_real)),
                })
            arms[arm] = per_start

        # keyed join: one row per (game_pk, side, pitcher), no nulls
        keys_p = {(r["game_pk"], r["side"], r["pitcher"])
                  for r in arms["PITCHER"]}
        keys_f = {(r["game_pk"], r["side"], r["pitcher"])
                  for r in arms["FULL"]}
        if keys_p != keys_f:
            raise ValueError(
                f"arm key mismatch: {len(keys_p ^ keys_f)} keys differ")
        common = sorted(keys_p)
        lookup_p = {(r["game_pk"], r["side"], r["pitcher"]): r
                    for r in arms["PITCHER"]}
        lookup_f = {(r["game_pk"], r["side"], r["pitcher"]): r
                    for r in arms["FULL"]}
        rows_out = []
        for k in common:
            a, b = lookup_p[k], lookup_f[k]
            assert a["rps"] is not None and b["rps"] is not None
            rows_out.append({
                "game_pk": a["game_pk"], "side": a["side"],
                "pitcher": a["pitcher"], "block": a["block"],
                "game_date": a["game_date"],
                "realized_k": a["realized_k"],
                "rps_pitcher": a["rps"], "rps_full": b["rps"],
            })
        out_df = pl.DataFrame(rows_out)
        if out_df.height != len(common) \
                or out_df.select(["game_pk", "side", "pitcher"]).unique(
                    ).height != len(common):
            raise ValueError("per-start output fan-out or nulls")
        null_counts = out_df.select(
            ["rps_pitcher", "rps_full", "realized_k"]).null_count()
        if any(v > 0 for v in null_counts.row(0, named=True).values()):
            raise ValueError("nulls in per-start output")

        rP = np.asarray([r["rps_pitcher"] for r in rows_out])
        rF = np.asarray([r["rps_full"] for r in rows_out])
        dates = [r["game_date"] for r in rows_out]
        blocks = [r["block"] for r in rows_out]

        # frozen-binary comparison: REGISTERED per-start PMFs, keys asserted
        frozen = (pmfs.select("game_pk", "side", "pitcher", "pmf_baseline")
                  .rename({"pitcher": "pitcher_id"}))
        fk = {(r["game_pk"], r["side"], r["pitcher_id"])
              for r in frozen.iter_rows(named=True)}
        keys_equal = (fk == {(r["game_pk"], r["side"], r["pitcher"])
                             for r in rows_out})
        frozen_rps = {}
        if keys_equal:
            fmap = {(r["game_pk"], r["side"], r["pitcher_id"]):
                    r["pmf_baseline"] for r in frozen.iter_rows(named=True)}
            for r in rows_out:
                key = (r["game_pk"], r["side"], r["pitcher"])
                pmf = np.asarray(fmap[key], dtype=np.float64)
                frozen_rps[key] = float(kc.count_rps(pmf,
                                                     r["realized_k"]))
        rB = np.asarray([frozen_rps[k] for k in common])

        cmp_mod = br.load_registered_comparison()
        res_f = cmp_mod.slate_date_draws({"full": rF, "pitcher": rP},
                                         dates, blocks, n_boot=n_boot,
                                         seed=seed)
        ci_f = [float(np.percentile(res_f[:, 0] - res_f[:, 1], 2.5)),
                float(np.percentile(res_f[:, 0] - res_f[:, 1], 97.5))]
        res_b = cmp_mod.slate_date_draws({"full": rF, "frozen": rB},
                                         dates, blocks, n_boot=n_boot,
                                         seed=seed)
        ci_b = [float(np.percentile(res_b[:, 0] - res_b[:, 1], 2.5)),
                float(np.percentile(res_b[:, 0] - res_b[:, 1], 97.5))]
        per_block = {}
        for b in ("block_2024H2", "block_2025H1"):
            mask = np.asarray([x == b for x in blocks])
            per_block[b] = {
                "n": int(mask.sum()),
                "rps_pitcher": float(rP[mask].mean()),
                "rps_full": float(rF[mask].mean()),
                "rps_frozen_binary": float(rB[mask].mean()),
            }
        metrics = {
            "n_scored_dev_starts": len(common),
            "scored_equals_4823": len(common) == 4823,
            "train_windows": {b: {"train_lo": str(w["train_lo"]),
                                  "actual_max_game_date":
                                      str(w["actual_max"]),
                                  "cutoff_rows_strictly_before":
                                      str(w["cutoff"])}
                              for b, w in windows.items()},
            "postseason_note": postseason_note,
            "drop_table": drops,
            "drops_sum_matches": (
                n_ledger_starts - len(common)
                == sum(drops.values())),
            "per_block": per_block,
            "rps_pitcher_projected": float(rP.mean()),
            "rps_full_projected": float(rF.mean()),
            "diff_full_minus_pitcher": float((rF - rP).mean()),
            "diff_full_minus_pitcher_ci95": ci_f,
            "frozen_binary_comparison": {
                "keys_equal": bool(keys_equal),
                "rps_frozen_binary": float(rB.mean()),
                "diff_full_minus_frozen": float((rF - rB).mean()),
                "diff_full_minus_frozen_ci95": ci_b,
            },
        }
        per_start_path = out_dir / "ablation_count_rps_per_start_v2.parquet"
        out_df.write_parquet(per_start_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "ablation_count_rps_per_start_v2.parquet":
                ad.sha256_file(per_start_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
    except Exception as exc:
        failure = {"stage": "ablation_count_rps", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise
    final = dict(initial)
    final["metrics"] = metrics
    final["outputs"] = outputs
    final["acceptance"] = {"receipt_chain": initial_sha}
    (out_dir / "receipt_final.json").write_text(
        json.dumps(final, indent=1, sort_keys=True), encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final,
            "receipt_initial_sha256": initial_sha}
