"""Lineup diagnostic runner (paired 2x2): PITCHER/FULL feature sets x
projected/oracle batting orders, on identical eligible starts.

RESEARCH-ONLY, write-once outputs. Design contract (owner order
2026-10-22):
- ONE feature-construction function (ab.build_features_with_half_life
  on the frozen pa_table lineage) feeds BOTH conditions; the conditions
  differ ONLY in batter identity/order:
    * PROJECTED: the preserved ledger's nine projected slot rows,
      scored by the arm's per-block fits (available for every eligible
      start - no realized-PA requirement);
    * ORACLE: the ACTUAL PAs (any batter) of the same starts, first
      appearance per distinct batter = the realized batting order.
- Fits, BF distributions, aggregation, and scoring are held fixed.
- CONTROL INVARIANT: PITCHER-only per-PA probabilities are batter-
  independent, so the projected and oracle count PMFs must be IDENTICAL
  within a declared numerical tolerance. A violation stops any
  lineup-effect interpretation.
- The frozen binary count layer is rescored on the exact same keys when
  used as a baseline (never compared across cohorts).

The oracle condition uses realized lineup identity; it is a diagnostic
ceiling, never deployable pregame.
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

CONTROL_TOLERANCE = 1e-12
N_BOOT = 2000
SEED = 20261001
K_MAX = ad.K_MAX


def _slot_order_p9(slot_p_k: "pl.DataFrame") -> list | None:
    """Projected condition: the nine slot probabilities in slot order.
    None if any slot is missing."""
    import polars as pl

    if slot_p_k.height != 9:
        return None
    return slot_p_k.sort("slot")["p_k"].to_list()


def _appearance_order_p9(feat_start: "pl.DataFrame",
                         p_k_col: str = "p_k") -> list | None:
    """Oracle condition: distinct batters in actual first-appearance
    order; their first-PA probabilities. None if fewer than nine
    distinct batters were faced."""
    import polars as pl

    firsts = (feat_start.sort("at_bat_number")
              .unique(subset=["batter"], keep="first")
              .sort("at_bat_number"))
    if firsts.height < 9:
        return None
    return firsts[p_k_col].head(9).to_list()


def _block_windows():
    out = {}
    for b, (te_y, te_m, te_d) in m0.DEV_BLOCK_TRAIN_END.items():
        te = date(te_y, te_m, te_d)
        cal_first = te - timedelta(days=59)
        train_lo = date(2023, 1, 1)
        if b == "block_2024H2":
            lo, hi = date(2024, 7, 1), date(2024, 12, 31)
        else:
            lo, hi = date(2025, 1, 1), date(2025, 6, 30)
        out[b] = {"train": (train_lo, cal_first), "eval": (lo, hi)}
    return out


def run_lineup_diagnostic(feat: "pl.DataFrame", ledger: "pl.DataFrame",
                          pmfs: "pl.DataFrame", realized: "pl.DataFrame",
                          bf: "pl.DataFrame", out_dir, *,
                          n_boot: int = N_BOOT, seed: int = SEED,
                          ) -> dict:
    """Write-once diagnostic runner (real-data execution requires the
    registered gate AND the delegated owner order; receipts identical
    to the lane pattern)."""
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
            "control_tolerance": CONTROL_TOLERANCE,
            "bootstrap": {"n": n_boot, "seed": seed},
            "oracle_status": ("realized lineup identity; diagnostic "
                              "ceiling, never deployable pregame"),
            "projected_source": ("the preserved ledger's nine projected "
                                 "slot rows (no realized-PA "
                                 "requirement)"),
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        start_keys = pmfs.select("game_pk", "pitcher").unique()
        side_map = {(r["game_pk"], r["pitcher"]): r["side"]
                    for r in pmfs.select("game_pk", "side", "pitcher")
                    .unique().iter_rows(named=True)}
        realized_map = {(r["game_pk"], r["side"], r["pitcher"]):
                        int(r["realized_k"])
                        for r in realized.iter_rows(named=True)}
        bf37 = bf.select("game_pk", "side", "pitcher",
                         *[f"pmf37_{k}" for k in range(37)])
        bf_lookup = {(r["game_pk"], r["side"], r["pitcher"]):
                     np.asarray([r[f"pmf37_{k}"] for k in range(37)])
                     for r in bf37.iter_rows(named=True)}
        ledger_slots = (ledger.filter(
            pl.col("exclusion_reason").is_null())
            .sort("game_pk", "side", "slot"))
        windows = _block_windows()

        arms = {}
        for arm, features in (("PITCHER", ab.FEATURE_SETS["PITCHER"]),
                              ("FULL", ab.FEATURE_SETS["FULL"])):
            # PROJECTED: the ledger's nine projected slot rows per
            # start, through the SAME feature frame's fits
            lslots = (ledger_slots.select(
                "game_pk", "side", "pitcher", "slot", "game_date",
                *features)
                .filter(pl.all_horizontal([pl.col(c).is_finite()
                                           for c in features])))
            proj_probs = np.full((lslots.height, m0.N_CLASSES), np.nan)
            pidx = lslots.with_row_index("_pi")
            # ORACLE: the ACTUAL PAs (any batter) of the eval starts,
            # same feature frame, first appearance per distinct batter
            orows = (feat.join(start_keys, on=["game_pk", "pitcher"],
                               how="inner")
                     .sort("game_pk", "pitcher", "at_bat_number"))
            oprobs = np.full((orows.height, m0.N_CLASSES), np.nan)
            oidx = orows.with_row_index("_oi")
            for b, w in windows.items():
                lo_t, hi_t = w["train"]
                train = feat.filter(
                    (pl.col("game_date") >= lo_t)
                    & (pl.col("game_date") < hi_t))
                lo, hi = w["eval"]
                model = ab.fit_multinomial_features(train, features)
                pvb = pidx.filter((pl.col("game_date") >= lo)
                                  & (pl.col("game_date") <= hi))
                proj_probs[pvb["_pi"].to_numpy()] = \
                    ab.apply_multinomial_features(pvb.drop("_pi"), model)
                ovb = oidx.filter((pl.col("game_date") >= lo)
                                  & (pl.col("game_date") <= hi))
                oprobs[ovb["_oi"].to_numpy()] = \
                    ab.apply_multinomial_features(ovb.drop("_oi"), model)

            # per-start p9 under both conditions
            per_start = []
            n_drop_proj = n_drop_orac = 0
            lslots = lslots.with_columns(
                pl.Series("p_k", proj_probs[:, m0.K_CLASS]))
            # rows outside the dev windows (confirm block) have no
            # model probability - drop them, disclosed
            n_outside = lslots.filter(pl.col("p_k").is_nan()).height
            lslots = lslots.filter(pl.col("p_k").is_not_nan())
            orows = orows.with_columns(
                pl.Series("p_k", oprobs[:, m0.K_CLASS]))
            for key_parts, g in lslots.group_by(
                    ["game_pk", "side", "pitcher"], maintain_order=True):
                gpk = int(g["game_pk"][0])
                side = g["side"][0]
                pitcher = int(g["pitcher"][0])
                p_proj = _slot_order_p9(g)
                if p_proj is None:
                    n_drop_proj += 1
                    continue
                key = (gpk, side, pitcher)
                b37 = bf_lookup.get(key)
                k_real = realized_map.get(key)
                if b37 is None or k_real is None:
                    n_drop_proj += 1
                    continue
                b37 = b37 / b37.sum()
                bf_ext = ad.bf_pmf_from_37(b37)
                pmf_proj = ad.count_pmf_from_mixture(
                    bf_ext, ad.cycled_cond_mean(np.asarray(p_proj)))
                per_start.append({
                    "game_pk": gpk, "side": side, "pitcher": pitcher,
                    "game_date": str(g["game_date"][0]),
                    "rps_proj": float(kc.count_rps(pmf_proj, k_real)),
                    "pmf_proj": pmf_proj.tolist(),
                })
            for g in orows.partition_by(["game_pk", "pitcher"]):
                gpk = int(g["game_pk"][0])
                pitcher = int(g["pitcher"][0])
                side = side_map.get((gpk, pitcher))
                p_orac = _appearance_order_p9(g)
                if p_orac is None:
                    n_drop_orac += 1
                    continue
                # attach to the matching projected row (same start)
                match = [r for r in per_start
                         if (r["game_pk"], r["side"],
                             r["pitcher"]) == (gpk, side, pitcher)]
                if not match:
                    n_drop_orac += 1
                    continue
                key = (gpk, side, pitcher)
                b37 = bf_lookup.get(key)
                k_real = realized_map.get(key)
                if b37 is None or k_real is None:
                    n_drop_orac += 1
                    continue
                b37 = b37 / b37.sum()
                bf_ext = ad.bf_pmf_from_37(b37)
                pmf_orac = ad.count_pmf_from_mixture(
                    bf_ext, ad.cycled_cond_mean(np.asarray(p_orac)))
                match[0]["rps_orac"] = float(
                    kc.count_rps(pmf_orac, k_real))
                match[0]["pmf_orac"] = pmf_orac.tolist()
            # drop starts missing either condition
            complete = [r for r in per_start if "rps_orac" in r]
            n_drop_orac += len(per_start) - len(complete)
            arms[arm] = {"per_start": complete,
                         "n_drop_proj": n_drop_proj,
                         "n_drop_orac": n_drop_orac}
            if arm == "PITCHER":
                # CONTROL INVARIANT: batter-independent probabilities
                # => identical PMFs under both orderings
                max_diff = 0.0
                for r in complete:
                    d = float(np.max(np.abs(
                        np.asarray(r["pmf_proj"])
                        - np.asarray(r["pmf_orac"]))))
                    max_diff = max(max_diff, d)
                control_max_diff = max_diff
                control_ok = control_max_diff <= CONTROL_TOLERANCE

        keys_p = {(r["game_pk"], r["side"], r["pitcher"])
                  for r in arms["PITCHER"]["per_start"]}
        keys_f = {(r["game_pk"], r["side"], r["pitcher"])
                  for r in arms["FULL"]["per_start"]}
        if keys_p != keys_f:
            raise ValueError(
                f"arm key mismatch: {len(keys_p ^ keys_f)} keys differ")
        common = sorted(keys_p)
        lookup_p = {(r["game_pk"], r["side"], r["pitcher"]): r
                    for r in arms["PITCHER"]["per_start"]}
        lookup_f = {(r["game_pk"], r["side"], r["pitcher"]): r
                    for r in arms["FULL"]["per_start"]}
        rpP = np.asarray([lookup_p[k]["rps_proj"] for k in common])
        rpF = np.asarray([lookup_f[k]["rps_proj"] for k in common])
        roP = np.asarray([lookup_p[k]["rps_orac"] for k in common])
        roF = np.asarray([lookup_f[k]["rps_orac"] for k in common])
        dates = [lookup_p[k]["game_date"] for k in common]
        blocks = ["block_2024H2" if date.fromisoformat(d)
                  <= date(2024, 12, 31) else "block_2025H1"
                  for d in dates]

        cmp_mod = br.load_registered_comparison()
        res_p = cmp_mod.slate_date_draws({"full": rpF, "pitcher": rpP},
                                         dates, blocks, n_boot=n_boot,
                                         seed=seed)
        res_o = cmp_mod.slate_date_draws({"full": roF, "pitcher": roP},
                                         dates, blocks, n_boot=n_boot,
                                         seed=seed)
        ci_p = [float(np.percentile(res_p[:, 0] - res_p[:, 1], 2.5)),
                float(np.percentile(res_p[:, 0] - res_p[:, 1], 97.5))]
        ci_o = [float(np.percentile(res_o[:, 0] - res_o[:, 1], 2.5)),
                float(np.percentile(res_o[:, 0] - res_o[:, 1], 97.5))]
        res_c = cmp_mod.slate_date_draws(
            {"oracle_diff": roF - roP, "proj_diff": rpF - rpP},
            dates, blocks, n_boot=n_boot, seed=seed)
        d_c = res_c[:, 0] - res_c[:, 1]
        ci_c = [float(np.percentile(d_c, 2.5)),
                float(np.percentile(d_c, 97.5))]
        metrics = {
            "n_common": len(common),
            "control_invariant": bool(control_ok),
            "control_max_abs_pmf_diff": control_max_diff,
            "rps_pitcher_projected": float(rpP.mean()),
            "rps_full_projected": float(rpF.mean()),
            "rps_pitcher_oracle": float(roP.mean()),
            "rps_full_oracle": float(roF.mean()),
            "diff_full_minus_pitcher_projected": float((rpF - rpP).mean()),
            "diff_full_minus_pitcher_projected_ci95": ci_p,
            "diff_full_minus_pitcher_oracle": float((roF - roP).mean()),
            "diff_full_minus_pitcher_oracle_ci95": ci_o,
            "interaction_change_in_diff": float(((roF - roP)
                                                 - (rpF - rpP)).mean()),
            "interaction_change_in_diff_ci95": ci_c,
            "drops": {"projected_condition":
                      arms["PITCHER"]["n_drop_proj"],
                      "oracle_condition":
                      arms["PITCHER"]["n_drop_orac"]},
        }
        per_start_path = out_dir / "lineup_diagnostic_per_start_v1.parquet"
        pl.DataFrame(arms["PITCHER"]["per_start"]).with_columns(
            pl.Series("rps_full_projected", rpF),
            pl.Series("rps_full_oracle", roF),
        ).write_parquet(per_start_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "lineup_diagnostic_per_start_v1.parquet":
                ad.sha256_file(per_start_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
    except Exception as exc:
        failure = {"stage": "lineup_diagnostic", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = metrics
    final["outputs"] = outputs
    final["acceptance"] = {
        "receipt_chain": initial_sha,
        "control_invariant": metrics["control_invariant"],
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final,
            "receipt_initial_sha256": initial_sha}
