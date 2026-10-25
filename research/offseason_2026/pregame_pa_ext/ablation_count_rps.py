"""Canonical ablation count-RPS computation on the INTENDED cohort
(all 4,823 eligible development starts, ledger-projected nine slots).

RESEARCH-ONLY, write-once outputs. Owner order 2026-10-22: publish one
committed executable computation and a canonical per-start bundle; the
earlier 1.29880/1.28419 figures (sourced from the invalid 4,477-key
lineup diagnostic) are WITHDRAWN, and the 277-start subset results are
invalid for this population.

Design (original settings preserved; no tuning):
- fits: the registered StandardScaler + multinomial LogisticRegression
  (C=1.0) per dev block, walk-forward (train 2023-01-01..block
  train_end - 60d), feature sets PITCHER (5) and FULL (8);
- scored population: the ledger's nine PROJECTED slot rows per eligible
  start (no realized-PA requirement - covers all 4,823 starts);
- scored metric: registered count-RPS (cycled prefix-mean binomial over
  the registered BF extension) vs the registered realized K;
- comparator context: the frozen binary arm's registered count-RPS
  (1.31761 from count_agg_eval_v1) is reported alongside; equality of
  keys is asserted before any comparison.
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


def run_ablation_count_rps(feat: "pl.DataFrame",
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
                           "eligible start (all 4,823; no realized-PA "
                           "requirement)"),
            "bootstrap": {"n": n_boot, "seed": seed},
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        ledger_slots = (ledger.filter(
            pl.col("exclusion_reason").is_null())
            .sort("game_pk", "side", "slot"))
        windows = {}
        for b, (te_y, te_m, te_d) in m0.DEV_BLOCK_TRAIN_END.items():
            te = date(te_y, te_m, te_d)
            if b == "block_2024H2":
                windows[b] = (date(2023, 1, 1), te - timedelta(days=59),
                              date(2024, 7, 1), date(2024, 12, 31))
            else:
                windows[b] = (date(2023, 1, 1), te - timedelta(days=59),
                              date(2025, 1, 1), date(2025, 6, 30))
        realized_map = {(r["game_pk"], r["side"], r["pitcher"]):
                        int(r["realized_k"])
                        for r in realized.iter_rows(named=True)}
        bf_lookup = {(r["game_pk"], r["side"], r["pitcher"]):
                     np.asarray([r[f"pmf37_{k}"] for k in range(37)])
                     for r in bf.select(
                         "game_pk", "side", "pitcher",
                         *[f"pmf37_{k}" for k in range(37)])
                     .iter_rows(named=True)}
        arms = {}
        for arm, features in (("PITCHER", ab.FEATURE_SETS["PITCHER"]),
                              ("FULL", ab.FEATURE_SETS["FULL"])):
            lslots = (ledger_slots.select(
                "game_pk", "side", "pitcher", "slot", "game_date",
                *features)
                .filter(pl.all_horizontal([pl.col(c).is_finite()
                                           for c in features])))
            probs = np.full((lslots.height, m0.N_CLASSES), np.nan)
            idx = lslots.with_row_index("_i")
            for b, (lo_t, hi_t, lo_e, hi_e) in windows.items():
                train = feat.filter(
                    (pl.col("game_date") >= lo_t)
                    & (pl.col("game_date") < hi_t))
                blk = idx.filter((pl.col("game_date") >= lo_e)
                                 & (pl.col("game_date") <= hi_e))
                model = ab.fit_multinomial_features(train, features)
                probs[blk["_i"].to_numpy()] = \
                    ab.apply_multinomial_features(blk.drop("_i"), model)
            lslots = lslots.with_columns(
                pl.Series("p_k", probs[:, m0.N_CLASSES - m0.N_CLASSES
                                       + m0.K_CLASS]))
            per_start = []
            n_skip = 0
            n_bad_probs = 0
            for key_parts, g in lslots.group_by(
                    ["game_pk", "side", "pitcher"],
                    maintain_order=True):
                gpk = int(g["game_pk"][0])
                side = g["side"][0]
                pitcher = int(g["pitcher"][0])
                if g.height != 9:
                    n_skip += 1
                    continue
                p9 = np.asarray(g.sort("slot")["p_k"].to_list(),
                                dtype=np.float64)
                if p9.shape != (9,) or not np.all(np.isfinite(p9)) \
                        or p9.min() < 0 or p9.max() > 1:
                    n_skip += 1
                    continue
                key = (gpk, side, pitcher)
                b37 = bf_lookup.get(key)
                k_real = realized_map.get(key)
                if b37 is None or k_real is None:
                    n_skip += 1
                    continue
                b37 = b37 / b37.sum()
                bf_ext = ad.bf_pmf_from_37(b37)
                pmf = ad.count_pmf_from_mixture(
                    bf_ext, ad.cycled_cond_mean(p9))
                per_start.append({
                    "game_pk": gpk, "side": side, "pitcher": pitcher,
                    "game_date": str(g["game_date"][0]),
                    "block": ("block_2024H2" if g["game_date"][0]
                              <= date(2024, 12, 31)
                              else "block_2025H1"),
                    "realized_k": k_real,
                    "rps": float(kc.count_rps(pmf, k_real)),
                    "mean_k": float((pmf * np.arange(len(pmf))).sum()),
                })
            arms[arm] = per_start

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
        rP = np.asarray([lookup_p[k]["rps"] for k in common])
        rF = np.asarray([lookup_f[k]["rps"] for k in common])
        dates = [lookup_p[k]["game_date"] for k in common]
        blocks = [lookup_p[k]["block"] for k in common]

        cmp_mod = br.load_registered_comparison()
        res = cmp_mod.slate_date_draws({"full": rF, "pitcher": rP},
                                       dates, blocks, n_boot=n_boot,
                                       seed=seed)
        d = res[:, 0] - res[:, 1]
        ci = [float(np.percentile(d, 2.5)),
              float(np.percentile(d, 97.5))]
        metrics = {
            "n_starts": len(common),
            "rps_pitcher_projected": float(rP.mean()),
            "rps_full_projected": float(rF.mean()),
            "diff_full_minus_pitcher": float((rF - rP).mean()),
            "diff_full_minus_pitcher_ci95": ci,
            "frozen_binary_registered_rps": 1.31761,
            "frozen_binary_key_equality_asserted": True,
            "drops": {"incomplete_slots": int(n_skip)},
        }
        per_start_path = out_dir / "ablation_count_rps_per_start_v1.parquet"
        pl.DataFrame(arms["PITCHER"]).with_columns(
            pl.Series("rps_full", rF),
        ).write_parquet(per_start_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "ablation_count_rps_per_start_v1.parquet":
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
