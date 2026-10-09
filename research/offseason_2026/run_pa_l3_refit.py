"""PA L3-style chronological refit (pa-l3-refit-contract-2026-10-09, FROZEN).

ONE scored run: newly fitted L3-style logistic (24-column manifest,
C=0.01 lbfgs max_iter=2000, per-origin train-only scaler) per chronological
origin inside the pa_completed_v1 lane, versus arm A (shrunk log5 w=150)
on identical rows. Stored L3 (D) = matched-row diagnostic reference only.

This is an L3-style v1 ADAPTATION, not a reproduction (contract deviation
ledger). Preflight join guards asserted fail-loud. No tuning, no feature
search, no multiclass, no aggregation, no production edits.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import pa_lgbm_scaffold as sc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_pa_lgbm_comparison as base  # noqa: E402

W = sc.W_SHRINK
PARK_W = 500.0
BLOCKS = base.BLOCKS
L3_PRED = base.L3_PRED
L3_FEATURES = [
    "same_hand", "b_hand_rate", "b_whiff", "b_swstr", "b_chase",
    "p_whiff_P5", "p_swstr_P5", "p_chase_P5", "p_zone_P5", "p_contact_P5",
    "p_whiff_std", "p_swstr_std", "p_chase_std", "p_zone_std",
    "p_contact_std", "log_pa_curr", "log_pa_prior", "park_k", "rest",
    "debut", "trip_eq_2", "trip_eq_3", "trip_ge_4", "spi_over_9",
]
CNT = ("sw", "wh", "cs", "ch", "iz", "ct", "np")


class RunFailure(RuntimeError):
    pass


def preflight_ledger(label: pl.DataFrame, fp: pl.DataFrame,
                     feat: pl.DataFrame) -> dict:
    """Permanent join guards (contract section 'Permanent join guards')."""
    n_pa_input = label.height
    n_unique_pa = label.select(
        pl.struct(["game_pk", "at_bat_number"]).n_unique()).item()
    snap_keys = fp.select(["game_pk", "pitcher"]).unique()
    row_keys = feat.select(["game_pk", "pitcher"]).unique()
    mismatch = row_keys.join(snap_keys, on=["game_pk", "pitcher"],
                             how="anti").height
    ledger = {
        "n_pa_input": int(n_pa_input),
        "n_unique_pa": int(n_unique_pa),
        "n_duplicate_pa": int(n_pa_input - n_unique_pa),
        "n_snapshot_keys": int(snap_keys.height),
        "n_duplicate_snapshot_keys": int(
            snap_keys.height - snap_keys.n_unique()),
        "n_snapshot_pitcher_mismatch": int(mismatch),
        "n_excluded_incomplete": int(
            (label["pa_class"] == sc.CLASS_INCOMPLETE).sum()),
        "n_excluded_baserunning": int(
            (label["pa_class"] == sc.CLASS_BASERUNNING).sum()),
        "n_mixed_batter": int(label["mixed_batter"].sum()),
        "n_feat_rows": int(feat.height),
        "join_expansion": int(feat.height - feat.select(
            pl.struct(["game_pk", "at_bat_number"]).n_unique()).item()),
    }
    for key in ("n_duplicate_pa", "n_duplicate_snapshot_keys",
                "n_snapshot_pitcher_mismatch", "join_expansion"):
        if ledger[key] != 0:
            raise RunFailure("preflight guard failed: %s = %d"
                             % (key, ledger[key]))
    return ledger


# --- Discipline accumulators (contract Amendment 1) ---------------------------


def _pitch_flags():
    swing = pl.col("description").is_in(list(sc.SWING_DESCRIPTIONS))
    contact = pl.col("description").is_in(list(sc.CONTACT_DESCRIPTIONS))
    zone = pl.col("zone")
    return swing, contact, zone


def pitcher_per_start_discipline(pooled_raw: pl.DataFrame) -> pl.DataFrame:
    """Per pitcher-start discipline counts + career/season/trailing-5 cum"""
    swing, contact, zone = _pitch_flags()
    ps = pooled_raw.select(
        "game_pk", "game_date", "pitcher", "description", "zone"
    ).with_columns(pl.col("game_date").cast(pl.Date)).group_by(
        ["pitcher", "game_pk", "game_date"]).agg(
        swing.sum().alias("sw"),
        (swing & ~contact).sum().alias("wh"),
        (pl.col("description") == "called_strike").sum().alias("cs"),
        (swing & zone.is_not_null() & (zone >= 11)).sum().alias("ch"),
        (zone.is_not_null() & (zone <= 9)).sum().alias("iz"),
        contact.sum().alias("ct"),
        pl.len().alias("np"),
    )
    ps = ps.with_columns(pl.col("game_date").dt.year().alias("season"))
    ps = ps.sort(["pitcher", "game_date"]).with_columns(
        [pl.col(c).cum_sum().over("pitcher").alias("c_" + c) for c in CNT])
    ps = ps.with_columns(
        [pl.col("c_" + c).shift(5).over("pitcher").fill_null(0)
         .alias("p5_" + c) for c in CNT])
    ps = ps.with_columns(
        [(pl.col("c_" + c) - pl.col("p5_" + c)).alias("w5_" + c)
         for c in CNT])
    ps = ps.with_columns(
        [pl.col(c).cum_sum().over(["pitcher", "season"]).alias("s_" + c)
         for c in CNT])
    return ps


def attach_pitcher_discipline(ps: pl.DataFrame,
                              keys: pl.DataFrame) -> pl.DataFrame:
    """As-of the last start strictly before the cutoff; P5 + season-std."""
    match = pl.col("cutoff_date") - pl.duration(days=1)
    j = (keys.with_columns(match.alias("match_date")).sort("match_date")
         .join_asof(ps.sort("game_date"), left_on="match_date",
                    right_on="game_date", by="pitcher", strategy="backward"))
    same_season = (pl.col("season")
                   == pl.col("cutoff_date").dt.year())
    out = j.select(
        list(sc.PITCHER_SNAPSHOT_COLUMNS)
        + ["w5_" + c for c in CNT]
        + [pl.col("s_" + c).alias("std_" + c) for c in CNT]
        + ["season"],
    )
    out = out.with_columns(
        [pl.when(same_season).then(pl.col("std_" + c)).otherwise(None)
         .alias("std_" + c) for c in CNT])
    return out.drop("season")


def batter_discipline_asof(pooled_raw: pl.DataFrame,
                           cutoffs: pl.DataFrame) -> pl.DataFrame:
    swing, contact, zone = _pitch_flags()
    per_day = pooled_raw.select(
        "game_pk", "game_date", "batter", "description", "zone"
    ).with_columns(pl.col("game_date").cast(pl.Date)).group_by(
        ["batter", "game_date"]).agg(
        swing.sum().alias("sw"),
        (swing & ~contact).sum().alias("wh"),
        (pl.col("description") == "called_strike").sum().alias("cs"),
        (swing & zone.is_not_null() & (zone >= 11)).sum().alias("ch"),
        pl.len().alias("np"),
    )
    per_day = (per_day.sort(["batter", "game_date"]).with_columns(
        [pl.col(c).cum_sum().over("batter").alias("c_" + c)
         for c in ("sw", "wh", "cs", "ch", "np")]))
    match = pl.col("cutoff_date") - pl.duration(days=1)
    j = (cutoffs.with_columns(match.alias("match_date")).sort("match_date")
         .join_asof(per_day.sort("game_date"), left_on="match_date",
                    right_on="game_date", by="batter", strategy="backward"))
    return j.select(
        "batter", "cutoff_date",
        pl.col("c_sw").fill_null(0).cast(pl.Int64).alias("b_sw"),
        pl.col("c_wh").fill_null(0).cast(pl.Int64).alias("b_wh"),
        pl.col("c_cs").fill_null(0).cast(pl.Int64).alias("b_cs"),
        pl.col("c_ch").fill_null(0).cast(pl.Int64).alias("b_ch"),
        pl.col("c_np").fill_null(0).cast(pl.Int64).alias("b_np"),
    )


def park_factors_prior(prior_label: pl.DataFrame,
                       prior_raw: pl.DataFrame) -> pl.DataFrame:
    """Prior-season EB park K factor per home team (w=500; contract F5)."""
    parks = prior_raw.select("game_pk", "home_team").unique()
    lab = prior_label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    lg = float(lab["y"].mean())
    by_park = (lab.join(parks, on="game_pk", how="inner")
               .group_by("home_team").agg(
                   pl.col("y").sum().alias("k"), pl.len().alias("n")))
    return by_park.select(
        "home_team",
        ((pl.col("k") + PARK_W * lg) / (pl.col("n") + PARK_W) / lg)
        .alias("park_k"))


def with_spi(feat: pl.DataFrame) -> pl.DataFrame:
    spi = (feat.select(["game_pk", "pitcher", "at_bat_number"])
           .sort(["game_pk", "pitcher", "at_bat_number"])
           .with_columns(pl.int_range(pl.len())
                         .over(["game_pk", "pitcher"]).add(1).alias("spi")))
    return feat.join(spi, on=["game_pk", "pitcher", "at_bat_number"],
                     how="left")


# --- Frozen 24-column matrix ----------------------------------------------------


def l3_matrix(frame: pl.DataFrame, lg: float) -> np.ndarray:
    def ratio(num: str, den: str) -> pl.Expr:
        return (pl.when(pl.col(den) > 0)
                .then(pl.col(num).cast(pl.Float64)
                      / pl.col(den).cast(pl.Float64))
                .otherwise(None))

    def ratio2(num_a: str, num_b: str, den: str) -> pl.Expr:
        return (pl.when(pl.col(den) > 0)
                .then((pl.col(num_a) + pl.col(num_b)).cast(pl.Float64)
                      / pl.col(den).cast(pl.Float64))
                .otherwise(None))

    f = frame.with_columns([
        (pl.col("p_throws") == pl.col("stand")).cast(pl.Float64)
        .alias("same_hand"),
        pl.when(pl.col("p_throws") == "L")
        .then(pl.when(pl.col("b_n_vs_lhp") > 0)
              .then((pl.col("b_k_vs_lhp").cast(pl.Float64) + W * lg)
                    / (pl.col("b_n_vs_lhp") + W)).otherwise(lg))
        .otherwise(pl.when(pl.col("b_n_vs_rhp") > 0)
                   .then((pl.col("b_k_vs_rhp").cast(pl.Float64) + W * lg)
                         / (pl.col("b_n_vs_rhp") + W)).otherwise(lg))
        .alias("b_hand_rate"),
        ratio("b_wh", "b_sw").alias("b_whiff"),
        ratio2("b_cs", "b_wh", "b_np").alias("b_swstr"),
        ratio("b_ch", "b_sw").alias("b_chase"),
        ratio("w5_wh", "w5_sw").alias("p_whiff_P5"),
        ratio2("w5_cs", "w5_wh", "w5_np").alias("p_swstr_P5"),
        ratio("w5_ch", "w5_sw").alias("p_chase_P5"),
        ratio("w5_iz", "w5_np").alias("p_zone_P5"),
        ratio("w5_ct", "w5_sw").alias("p_contact_P5"),
        ratio("std_wh", "std_sw").alias("p_whiff_std"),
        ratio2("std_cs", "std_wh", "std_np").alias("p_swstr_std"),
        ratio("std_ch", "std_sw").alias("p_chase_std"),
        ratio("std_iz", "std_np").alias("p_zone_std"),
        ratio("std_ct", "std_sw").alias("p_contact_std"),
        (pl.col("n_prior_season").cast(pl.Float64) + 1.0).log()
        .alias("log_pa_curr"),
        (pl.col("n_prior").cast(pl.Float64) + 1.0).log()
        .alias("log_pa_prior"),
        pl.col("park_k").fill_null(1.0).alias("park_k"),
        pl.col("days_since_prev_start").fill_null(15)
        .clip(1, 15).cast(pl.Float64).alias("rest"),
        (pl.col("n_prior_season") == 0).cast(pl.Float64).alias("debut"),
        (pl.col("spi") >= 10).cast(pl.Float64).alias("trip_ge_4"),
        (pl.col("spi") == 2).cast(pl.Float64).alias("trip_eq_2"),
        (pl.col("spi") == 3).cast(pl.Float64).alias("trip_eq_3"),
        (pl.col("spi").cast(pl.Float64) / 9.0).alias("spi_over_9"),
    ])
    # Contract fills: nan_to_num(0) everywhere except b_hand_rate (lg
    # fallback built into the expression), park_k (1.0) and rest (15),
    # which are filled in-frame and can never be NaN here.
    X = f.select(L3_FEATURES).to_numpy().astype(np.float64)
    return np.nan_to_num(X, nan=0.0)


def fit_logistic(Xtr, ytr, Xev):
    from sklearn.linear_model import LogisticRegression

    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0) + 1e-9
    model = LogisticRegression(penalty="l2", C=0.01, solver="lbfgs",
                               max_iter=2000)
    model.fit((Xtr - mu) / sd, ytr)
    n_iter = int(model.n_iter_[0])
    p = model.predict_proba((Xev - mu) / sd)[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6), {"converged": n_iter < 2000,
                                        "n_iter": n_iter}


# --- Block execution ---------------------------------------------------------------


def run_block(block: int, frames: dict, label_tables: dict,
              keys_tables: dict) -> tuple[dict, dict]:
    cfg = BLOCKS[block]
    pool_seasons = cfg["pool_seasons"]
    pooled_label = pl.concat([label_tables[y] for y in pool_seasons],
                             how="vertical")
    pooled_raw = pl.concat([frames[y] for y in pool_seasons],
                           how="diagonal_relaxed")
    ps = pitcher_per_start_discipline(pooled_raw)
    park = park_factors_prior(
        label_tables[min(pool_seasons)],
        frames[min(pool_seasons)])
    feats_by_season, ledgers = {}, {}
    for season in cfg["train_seasons"]:
        fp = sc.first_pitcher_filter(label_tables[season],
                                     keys_tables[season])
        f = base.build_season_features(fp, pooled_label, pooled_raw, ["FF"])
        ledgers["%d_%d" % (block, season)] = preflight_ledger(
            label_tables[season], fp, f)
        gp = frames[season].select("game_pk", "home_team").unique()
        f = (f.join(gp, on="game_pk", how="left")
             .join(park, on="home_team", how="left"))
        sk = sc.pitcher_snapshot_keys(
            fp.select(["game_pk", "game_date", "pitcher"]).unique())
        disc = attach_pitcher_discipline(ps, sk)
        disc = disc.rename({"key_game_pk": "game_pk"}).drop("cutoff_date")
        f = f.join(disc, on=["game_pk", "pitcher"], how="left")
        bcut = f.select(pl.col("batter"),
                        pl.col("game_date").alias("cutoff_date")).unique()
        f = with_spi(f.join(
            batter_discipline_asof(pooled_raw, bcut),
            left_on=["batter", "game_date"],
            right_on=["batter", "cutoff_date"], how="left"))
        feats_by_season[season] = f
    eval_feat = feats_by_season[block]
    keep = (["game_pk", "game_date", "at_bat_number", "pitcher", "batter",
             "y", "stand", "p_throws", "spi", "park_k"]
            + [c for c in eval_feat.columns if c.startswith(
                ("k_prior", "n_prior", "b_k", "b_n", "b_sw", "b_wh",
                 "b_cs", "b_ch", "b_np", "w5_", "std_", "days_since"))])
    train_all = pl.concat(
        [feats_by_season[s].select(keep) for s in cfg["train_seasons"]],
        how="vertical")
    stored_l3 = (pl.read_parquet(L3_PRED).select(
        ["game_pk", "at_bat_number", "L3"]) if block == 2024 else None)

    origins = list(cfg["origins"]) + [cfg["final"]]
    per_rows, per_origin = [], []
    for i, origin in enumerate(cfg["origins"]):
        lg = float(pooled_label.filter(
            (pl.col("pa_class") == sc.CLASS_COMPLETED)
            & (pl.col("game_date") < origin))["y"].mean())
        ev = eval_feat.filter((pl.col("game_date") >= origin)
                              & (pl.col("game_date") < origins[i + 1]))
        tr = train_all.filter(pl.col("game_date") < origin)
        ev = base.attach_origin_context(ev, lg)
        y_ev = ev["y"].to_numpy().astype(int)
        y_tr = tr["y"].to_numpy().astype(int)
        Xtr = l3_matrix(tr, lg)
        Xev = l3_matrix(ev, lg)
        pD3, fitinfo = fit_logistic(Xtr, y_tr, Xev)
        blk = ev.select(["game_pk", "game_date", "at_bat_number",
                         "pitcher", "batter", "y"]).with_columns([
            pl.Series("p_A", ev["p_A"].to_numpy()),
            pl.Series("p_D3", pD3),
            pl.lit(origin).alias("origin"),
            pl.lit(fitinfo["converged"]).alias("converged"),
            pl.lit(fitinfo["n_iter"]).alias("n_iter"),
        ])
        if stored_l3 is not None:
            blk = blk.join(stored_l3, on=["game_pk", "at_bat_number"],
                           how="left")
        per_rows.append(blk)
        per_origin.append({
            "origin": str(origin), "n_eval": int(ev.height),
            "n_train": int(tr.height), "lg": lg, **fitinfo,
            "n_cold_pitchers_eval": int(
                (ev["n_prior"].fill_null(0) == 0).sum()),
        })
        print("  origin %s: eval %d train %d conv %s" % (
            origin, ev.height, tr.height, fitinfo["converged"]))
    rows = pl.concat(per_rows, how="vertical")
    y = rows["y"].to_numpy().astype(int)
    dates = rows["game_date"].to_numpy().astype(str)
    llA = base.logloss(rows["p_A"].to_numpy(), y)
    llD3 = base.logloss(rows["p_D3"].to_numpy(), y)
    paired = base.cluster_bootstrap_p(llD3 - llA, dates)
    out = {
        "n": int(rows.height),
        "mean_ll": {"A": float(llA.mean()), "D3": float(llD3.mean())},
        "mean_brier": {
            "A": float(base.brier(rows["p_A"].to_numpy(), y).mean()),
            "D3": float(base.brier(rows["p_D3"].to_numpy(), y).mean())},
        "paired_D3_minus_A": paired,
        "holm": base.holm({"D3-A": paired["p_two_sided"]}),
        "per_origin": per_origin,
    }
    if stored_l3 is not None:
        matched = rows.filter(pl.col("L3").is_not_null())
        ym = matched["y"].to_numpy().astype(int)
        mdates = matched["game_date"].to_numpy().astype(str)
        llA_m = base.logloss(matched["p_A"].to_numpy(), ym)
        llD3_m = base.logloss(matched["p_D3"].to_numpy(), ym)
        llD_m = base.logloss(matched["L3"].to_numpy(), ym)
        out["d_reference_matched"] = {
            "n": int(matched.height),
            "mean_ll": {"A": float(llA_m.mean()),
                        "D3": float(llD3_m.mean()),
                        "D": float(llD_m.mean())},
            "paired_D_minus_A": base.cluster_bootstrap_p(llD_m - llA_m,
                                                         mdates),
            "paired_D3_minus_A": base.cluster_bootstrap_p(llD3_m - llA_m,
                                                          mdates),
        }
    return {"out": out, "rows": rows, "ledgers": ledgers}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        shas = {}
        for item in args.season_sha:
            yy, d = item.split(":", 1)
            shas[int(yy)] = d.lower()
        frames, input_records = {}, {}
        for season in (2022, 2023, 2024):
            path = (root / "Savant-Data" / "regular" / str(season)
                    / ("statcast_%d_regular.parquet" % season))
            if not path.is_file():
                raise RunFailure("missing input %s" % path)
            digest = shas.get(season, rch.SEASON_SHA_KNOWN.get(season))
            if digest is None:
                digest = base.sha256_file(path)
                mode = "registered_first_hash"
            else:
                if base.sha256_file(path) != digest:
                    raise RunFailure("hash mismatch %d" % season)
                mode = "verified"
            frames[season] = pl.read_parquet(path)
            input_records["savant_%d" % season] = {
                "path": str(path.resolve()), "sha256": digest, "mode": mode}

        label_tables, keys_tables = {}, {}
        for season in (2022, 2023, 2024):
            keys, _q = rch.audit_identity(
                rch._unified_pitches([frames[season]]))
            keys_tables[season] = keys
            label_tables[season] = sc.build_pa_label_table(frames[season])

        results, ledgers = {}, {}
        for block in (2023, 2024):
            print("BLOCK %d" % block)
            res = run_block(block, frames, label_tables, keys_tables)
            results[str(block)] = res["out"]
            ledgers.update(res["ledgers"])
            res["rows"].write_csv(out_dir / ("predictions_%d.csv" % block))
            o = res["out"]
            print("BLOCK %d: A %.5f D3 %.5f | D3-A %.6f CI [%.6f, %.6f]"
                  % (block, o["mean_ll"]["A"], o["mean_ll"]["D3"],
                     o["paired_D3_minus_A"]["estimate"],
                     o["paired_D3_minus_A"]["lo95"],
                     o["paired_D3_minus_A"]["hi95"]))

        manifest = {
            "lane": "pa_l3_refit",
            "status": "COMPLETE",
            "contract": "research/offseason_2026/"
                        "pa-l3-refit-contract-2026-10-09.md "
                        "(incl. Amendment 1 discipline denominators)",
            "label": "L3-style v1 ADAPTATION, not reproduction",
            "primary": "paired PA log loss D3-A, slate-date clustered "
                       "bootstrap 2000 seed 20261001",
            "estimator": "LogisticRegression(l2, C=0.01, lbfgs, "
                         "max_iter=2000), per-origin scaler (train-only)",
            "features": L3_FEATURES,
            "inputs": input_records,
            "preflight_ledgers": ledgers,
            "no_2025_2026_access": True,
            "results": results,
            "code": {p.name: base.sha256_file(p) for p in [
                HERE / "run_pa_l3_refit.py", HERE / "pa_lgbm_scaffold.py",
                HERE / "run_pa_lgbm_comparison.py"]},
        }
        (out_dir / "pa_l3_refit_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print("WROTE %s" % out_dir)
        return 0
    except (RunFailure, rch.MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
