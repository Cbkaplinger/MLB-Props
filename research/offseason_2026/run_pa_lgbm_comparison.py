"""PA-LGBM frozen comparison runner (pa-lgbm contract 2026-10-09 + Amendments 3-5).

ONE scored run under the owner conditional authorization 2026-10-09.
Arms: A = shrunk log5 (w=150, pa-k heritage); B = LightGBM binary logistic
WITHOUT log5-derived features; C = B + [p_A, logit(p_A)];
D = stored L3 ridge logistic (logistic_pa, fit 2023 -> out-of-sample on
2024) joined on (game_pk, at_bat_number), 2024 block ONLY.

Primary: opportunity-weighted (per-PA mean) paired log loss, slate-date
clustered bootstrap (2000, seed 20261001), Holm within block. 2023 family
{B-A, C-A, C-B}; 2024 family {B-A, C-A, C-B, D-A, C-D} (D comparisons on
D-matched rows). No tuning, no class balancing, no calibration layer.
2024 = chronological DEVELOPMENT TRANSFER. PA probabilities ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
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

SEED = 20261001
N_BOOT = 2000
W = sc.W_SHRINK
VAL_FRAC = 0.15
ES_ROUNDS = 200
LGBM_PARAMS = {
    "objective": "binary", "learning_rate": 0.03, "num_leaves": 31,
    "min_data_in_leaf": 50, "feature_fraction": 0.8,
    "bagging_fraction": 0.7, "bagging_freq": 1, "lambda_l2": 2.0,
    "seed": 42, "verbosity": -1,
}
BLOCKS = {
    2023: {"origins": (date(2023, 4, 15), date(2023, 7, 1),
                       date(2023, 8, 1), date(2023, 9, 1)),
           "final": date(2023, 10, 1), "train_seasons": (2023,),
           "pool_seasons": (2022, 2023)},
    2024: {"origins": (date(2024, 4, 15), date(2024, 7, 1),
                       date(2024, 8, 1), date(2024, 9, 1)),
           "final": date(2024, 10, 1), "train_seasons": (2023, 2024),
           "pool_seasons": (2022, 2023, 2024)},
}
L3_PRED = HERE / "experiments" / "logistic_pa" / "pa_predictions.parquet"
COUNT_FILL_COLS = (
    "k_prior", "n_prior", "n_prior_season", "n_prior_starts",
    "n_prior_pa", "n_prior_short_starts", "n_swings", "n_whiffs",
    "n_contacts", "n_eligible", "ff_n_valid", "ff_n_missing",
)


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cluster_bootstrap_p(diffs: np.ndarray, cluster_ids: np.ndarray,
                        n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """rch.cluster_bootstrap + two-sided bootstrap p-value for Holm."""
    out = rch.cluster_bootstrap(diffs, cluster_ids, n_boot=n_boot, seed=seed)
    diffs = np.asarray(diffs, dtype=float)
    ids = np.asarray(cluster_ids)
    unique = np.unique(ids)
    by_cluster = [diffs[ids == c] for c in unique]
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(unique), len(unique))
        stats[b] = np.concatenate([by_cluster[i] for i in pick]).mean()
    n_le = int((stats <= 0).sum())
    n_ge = int((stats >= 0).sum())
    out["p_two_sided"] = float(2 * min(n_le, n_ge) + 1) / (n_boot + 1)
    return out


def holm(pvals: dict, alpha: float = 0.05) -> dict:
    m = len(pvals)
    order = sorted(pvals, key=lambda k: pvals[k])
    adj = {}
    running = 0.0
    for i, name in enumerate(order):
        running = max(running, (m - i) * pvals[name])
        adj[name] = min(1.0, running)
    return {name: {"p": pvals[name], "p_adj": adj[name],
                   "significant": adj[name] < alpha} for name in pvals}


# --- Batter priors via cumulative as-of tables ------------------------------


def _asof_prior(per_day: pl.DataFrame, cutoffs: pl.DataFrame,
                by) -> pl.DataFrame:
    match_date = pl.col("cutoff_date") - pl.duration(days=1)
    return (cutoffs.with_columns(match_date.alias("match_date"))
            .sort("match_date")
            .join_asof(per_day.sort("game_date"), left_on="match_date",
                       right_on="game_date", by=by, strategy="backward"))


def batter_rate_priors_fast(label_pool: pl.DataFrame,
                            cutoffs: pl.DataFrame) -> pl.DataFrame:
    """cutoffs: distinct (batter, cutoff_date). Strictly-prior counts."""
    lab = label_pool.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    per_day = lab.group_by(["batter", "game_date"]).agg(
        pl.col("y").sum().alias("k_day"), pl.len().alias("n_day"))
    per_day = (per_day.sort(["batter", "game_date"]).with_columns(
        pl.col("k_day").cum_sum().over("batter").alias("cum_k"),
        pl.col("n_day").cum_sum().over("batter").alias("cum_n")))
    j = _asof_prior(per_day, cutoffs, by="batter")
    return j.select(
        "batter", "cutoff_date",
        pl.col("cum_k").fill_null(0).cast(pl.Int64).alias("b_k_prior"),
        pl.col("cum_n").fill_null(0).cast(pl.Int64).alias("b_n_prior"),
        (pl.col("cutoff_date") - pl.col("game_date")).dt.total_days()
        .fill_null(-1).alias("b_days_since_last_pa"),
    )


def batter_hand_priors_fast(label_pool: pl.DataFrame,
                            cutoffs: pl.DataFrame) -> pl.DataFrame:
    """Hand-split prior K counts per (batter, cutoff); null-p_throws rows
    still count in the overall b_n_prior but not in the hand split."""
    lab = label_pool.filter(
        (pl.col("pa_class") == sc.CLASS_COMPLETED)
        & pl.col("p_throws").is_not_null())
    per_day = lab.group_by(["batter", "p_throws", "game_date"]).agg(
        pl.col("y").sum().alias("k_day"), pl.len().alias("n_day"))
    per_day = (per_day.sort(["batter", "p_throws", "game_date"])
               .with_columns(
                   pl.col("k_day").cum_sum().over(["batter", "p_throws"])
                   .alias("cum_k"),
                   pl.col("n_day").cum_sum().over(["batter", "p_throws"])
                   .alias("cum_n")))
    cut2 = cutoffs.join(pl.DataFrame({"p_throws": ["R", "L"]}),
                        how="cross")
    j = _asof_prior(per_day, cut2, by=["batter", "p_throws"])
    wide = j.pivot(values=["cum_k", "cum_n"],
                   index=["batter", "cutoff_date"], on="p_throws")
    renames = {}
    for side, tag in (("R", "rhp"), ("L", "lhp")):
        renames["cum_k_%s" % side] = "b_k_vs_%s" % tag
        renames["cum_n_%s" % side] = "b_n_vs_%s" % tag
    wide = wide.rename(renames)
    out = wide.select(["batter", "cutoff_date"]
                      + [c for c in renames.values() if c in wide.columns])
    for c in renames.values():
        if c not in out.columns:
            out = out.with_columns(pl.lit(0, dtype=pl.Int64).alias(c))
    return out.fill_null(0)


# --- Feature frame assembly ---------------------------------------------------


def guarded_ratio(num: str, den: str) -> pl.Expr:
    return (pl.when(pl.col(den) > 0)
            .then(pl.col(num).cast(pl.Float64)
                  / pl.col(den).cast(pl.Float64))
            .otherwise(None))


def build_season_features(fp_label: pl.DataFrame,
                          pooled_label: pl.DataFrame,
                          pooled_raw: pl.DataFrame,
                          pitcher_types: list[str]) -> pl.DataFrame:
    """Per-season PA-level frame with per-game snapshot counts (no lg yet).

    One row per v1 completed first-pitcher PA; lg/p_A/shrunk rates are
    added per origin by the caller.
    """
    keys = sc.pitcher_snapshot_keys(
        fp_label.select(["game_pk", "game_date", "pitcher"]).unique())
    rates = sc.pitcher_rate_priors(pooled_label, keys)
    workload = sc.pitcher_workload_priors(pooled_label, keys)
    swings = sc.pitcher_swing_priors(pooled_raw, keys)
    types = sc.pitcher_pitchtype_priors(pooled_raw, keys)
    totals = types.group_by(sc.PITCHER_SNAPSHOT_COLUMNS).agg(
        pl.col("n_type").sum().alias("n_eligible"))
    fin = sc.finalize_type_stats(types, totals)
    ff = (fin.filter(pl.col("pitch_type") == "FF")
          .select(list(sc.PITCHER_SNAPSHOT_COLUMNS)
                  + ["n_valid", "n_missing_velocity", "mean_speed",
                     "sd_speed", "days_since_last_valid"])
          .rename({"n_valid": "ff_n_valid",
                   "n_missing_velocity": "ff_n_missing",
                   "mean_speed": "ff_mean_speed", "sd_speed": "ff_sd_speed",
                   "days_since_last_valid": "ff_days_since_last_valid"}))
    usage = (fin.select(list(sc.PITCHER_SNAPSHOT_COLUMNS)
                        + ["pitch_type", "n_type", "usage_share"])
             .filter(pl.col("pitch_type").is_in(pitcher_types)))
    usage_wide = usage.pivot(values=["n_type", "usage_share"],
                             index=list(sc.PITCHER_SNAPSHOT_COLUMNS),
                             on="pitch_type")
    usage_wide.columns = [
        (c[len("n_type_"):] + "_n") if c.startswith("n_type_")
        else (c[len("usage_share_"):] + "_usage")
        if c.startswith("usage_share_") else c
        for c in usage_wide.columns]
    for t in pitcher_types:  # guarantee the frozen type-column universe
        if "%s_n" % t not in usage_wide.columns:
            usage_wide = usage_wide.with_columns(
                pl.lit(0, dtype=pl.Int64).alias("%s_n" % t))
        if "%s_usage" % t not in usage_wide.columns:
            usage_wide = usage_wide.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("%s_usage" % t))

    snap = (keys.join(rates, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
            .join(workload, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
            .join(swings, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
            .join(totals, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
            .join(ff, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
            .join(usage_wide, on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left"))
    fill_cols = [c for c in COUNT_FILL_COLS if c in snap.columns]
    fill_cols += [c for c in snap.columns
                  if c.endswith("_n") and c not in fill_cols
                  and not c.startswith(("ff_", "b_"))]
    snap = snap.with_columns([pl.col(c).fill_null(0).cast(pl.Int64)
                              for c in fill_cols])
    snap = snap.with_columns(
        (pl.col("ff_n_valid").fill_null(0) > 0).cast(pl.Int8)
        .alias("has_ff_history"),
        guarded_ratio("n_whiffs", "n_swings").alias("whiff_rate"),
        guarded_ratio("n_contacts", "n_swings").alias("contact_rate"),
    )
    snap = (snap.rename({"key_game_pk": "game_pk"})
            .drop(["cutoff_date"]))
    # Join on (game_pk, pitcher): snapshot keys cover BOTH teams' starters
    # per game (pa-k 4,860-appearance semantics); a game_pk-only join would
    # attach the other starter's snapshot to every PA row (2x duplication).
    rows = fp_label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED).select(
        "game_pk", "game_date", "at_bat_number", "pitcher", "batter", "y")
    bcut = rows.select(pl.col("batter"),
                       pl.col("game_date").alias("cutoff_date")).unique()
    btab = batter_rate_priors_fast(pooled_label, bcut).join(
        batter_hand_priors_fast(pooled_label, bcut),
        on=["batter", "cutoff_date"], how="left")
    out = (rows.join(snap, on=["game_pk", "pitcher"], how="left")
           .join(btab, left_on=["batter", "game_date"],
                 right_on=["batter", "cutoff_date"], how="left"))
    if out.height != rows.height or out.select(
            pl.struct(["game_pk", "at_bat_number"]).n_unique()).item() \
            != rows.height:
        raise RunFailure(
            "feature join changed row cardinality: %d -> %d"
            % (rows.height, out.height))
    return out


def feature_columns(pitcher_types: list[str]) -> tuple[list[str], list[str]]:
    """(arm_B_features, arm_C_extra) frozen order."""
    base = ["k_prior", "n_prior", "n_prior_season", "n_prior_starts",
            "n_prior_pa", "days_since_prev_start", "n_prior_short_starts",
            "n_swings", "n_whiffs", "n_contacts", "whiff_rate",
            "contact_rate", "n_eligible"]
    for t in pitcher_types:
        base += ["%s_n" % t, "%s_usage" % t]
    base += ["ff_n_valid", "ff_n_missing", "ff_mean_speed", "ff_sd_speed",
             "ff_days_since_last_valid", "has_ff_history"]
    base += ["b_k_prior", "b_n_prior", "b_days_since_last_pa",
             "b_k_vs_rhp", "b_n_vs_rhp", "b_k_vs_lhp", "b_n_vs_lhp",
             "lg_rate"]
    return base, ["p_A", "logit_p_A"]


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def arm_a_probs(frame: pl.DataFrame, lg: float, w: float = W) -> np.ndarray:
    """Shrunk log5 per PA from snapshot counts (cold start -> league)."""
    kp = frame["k_prior"].to_numpy().astype(float)
    npit = frame["n_prior"].to_numpy().astype(float)
    kb = frame["b_k_prior"].to_numpy().astype(float)
    nb = frame["b_n_prior"].to_numpy().astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        pp = np.where(npit > 0, (kp + w * lg) / (npit + w), lg)
        pb = np.where(nb > 0, (kb + w * lg) / (nb + w), lg)
    z = logit(pp) + logit(pb) - logit(lg)
    return 1.0 / (1.0 + np.exp(-z))


def fit_lgbm(Xtr, ytr, Xev):
    """Chronological early stop: last VAL_FRAC of training rows (ordered by
    game_date within origin) is the internal validation block, entirely
    pre-origin by construction."""
    from lightgbm import LGBMClassifier

    n = Xtr.shape[0]
    n_val = max(1, int(n * VAL_FRAC))
    model = LGBMClassifier(n_estimators=5000,
                           early_stopping_rounds=ES_ROUNDS, **LGBM_PARAMS)
    model.fit(Xtr[:n - n_val], ytr[:n - n_val],
              eval_set=[(Xtr[n - n_val:], ytr[n - n_val:])],
              eval_metric="binary_logloss")
    p = model.predict_proba(Xev)[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6), int(model.best_iteration_ or 0)


def logloss(p, y):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(p, y):
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


# --- Block runner --------------------------------------------------------------


def attach_origin_context(frame: pl.DataFrame, lg: float) -> pl.DataFrame:
    pA = arm_a_probs(frame, lg)
    return frame.with_columns([
        pl.lit(lg).alias("lg_rate"),
        pl.Series("p_A", pA),
        pl.Series("logit_p_A", logit(pA)),
    ])


def run_block(block_season: int, frames: dict, label_tables: dict,
              keys_tables: dict, pitcher_types: list[str]) -> dict:
    cfg = BLOCKS[block_season]
    pool_seasons = cfg["pool_seasons"]
    pooled_label = pl.concat([label_tables[y] for y in pool_seasons],
                             how="vertical")
    pooled_raw = pl.concat([frames[y] for y in pool_seasons],
                           how="diagonal_relaxed")

    feats_by_season = {}
    for season in cfg["train_seasons"]:
        fp = sc.first_pitcher_filter(label_tables[season],
                                     keys_tables[season])
        feats_by_season[season] = build_season_features(
            fp, pooled_label, pooled_raw, pitcher_types)
    eval_feat = feats_by_season[block_season]

    bfeats, cextra = feature_columns(pitcher_types)
    all_feats = bfeats + cextra
    snap_cols = [c for c in eval_feat.columns if c not in (
        "game_pk", "game_date", "at_bat_number", "pitcher", "batter", "y")]
    train_parts = []
    for season in cfg["train_seasons"]:
        f = feats_by_season[season].select(
            ["game_pk", "game_date", "at_bat_number", "pitcher", "batter",
             "y"] + snap_cols)
        train_parts.append(f)
    train_all = pl.concat(train_parts, how="vertical")

    stored_l3 = None
    if block_season == 2024:
        stored_l3 = pl.read_parquet(L3_PRED).select(
            ["game_pk", "at_bat_number", "L3"])

    origins = list(cfg["origins"]) + [cfg["final"]]
    per_rows, per_origin_meta = [], []
    for i, origin in enumerate(cfg["origins"]):
        window_end = origins[i + 1]
        lg = float(pooled_label.filter(
            (pl.col("pa_class") == sc.CLASS_COMPLETED)
            & (pl.col("game_date") < origin))["y"].mean())
        if lg != lg:
            raise RunFailure("league rate NaN at origin %s" % origin)

        ev = eval_feat.filter((pl.col("game_date") >= origin)
                              & (pl.col("game_date") < window_end))
        tr = train_all.filter(pl.col("game_date") < origin)
        if ev.height == 0 or tr.height == 0:
            raise RunFailure("empty split at origin %s" % origin)
        ev = attach_origin_context(ev, lg)
        tr = attach_origin_context(tr, lg)

        y_ev = ev["y"].to_numpy().astype(int)
        Xb_tr = tr.select(bfeats).to_numpy().astype(np.float64)
        y_tr = tr["y"].to_numpy().astype(int)
        Xc_tr = tr.select(all_feats).to_numpy().astype(np.float64)
        pB, best_b = fit_lgbm(Xb_tr, y_tr,
                              ev.select(bfeats).to_numpy().astype(np.float64))
        pC, best_c = fit_lgbm(Xc_tr, y_tr,
                              ev.select(all_feats).to_numpy()
                              .astype(np.float64))

        block = ev.select(["game_pk", "game_date", "at_bat_number",
                           "pitcher", "batter", "y"]).with_columns([
            pl.Series("p_A", ev["p_A"].to_numpy()),
            pl.Series("p_B", pB), pl.Series("p_C", pC),
            pl.Series("best_iter_B", [best_b] * ev.height),
            pl.Series("best_iter_C", [best_c] * ev.height),
            pl.lit(origin).alias("origin"),
        ])
        if stored_l3 is not None:
            block = block.join(stored_l3, on=["game_pk", "at_bat_number"],
                               how="left")
        per_rows.append(block)
        per_origin_meta.append({
            "origin": str(origin), "n_eval": int(ev.height),
            "n_train": int(tr.height), "lg": lg,
            "best_iter_B": best_b, "best_iter_C": best_c,
            "n_cold_pitchers_eval": int(
                (ev["n_prior"].fill_null(0) == 0).sum()),
            "n_cold_batters_eval": int(
                (ev["b_n_prior"].fill_null(0) == 0).sum()),
        })
        print("  origin %s: eval %d train %d lg %.5f" % (
            origin, ev.height, tr.height, lg))

    return {"rows": pl.concat(per_rows, how="vertical"),
            "meta": per_origin_meta}


# --- Metrics --------------------------------------------------------------------


def block_metrics(rows: pl.DataFrame, has_d: bool) -> dict:
    y = rows["y"].to_numpy().astype(int)
    dates = rows["game_date"].to_numpy().astype(str)
    arms = ["A", "B", "C"]
    ll = {a: logloss(rows["p_%s" % a].to_numpy(), y) for a in arms}
    out = {
        "n": int(rows.height),
        "mean_ll": {a: float(ll[a].mean()) for a in arms},
        "mean_brier": {a: float(brier(rows["p_%s" % a].to_numpy(), y)
                                .mean()) for a in arms},
    }
    family = {"B-A": ll["B"] - ll["A"], "C-A": ll["C"] - ll["A"],
              "C-B": ll["C"] - ll["B"]}
    out["paired"] = {k: cluster_bootstrap_p(v, dates)
                     for k, v in family.items()}
    if has_d:
        matched = rows.filter(pl.col("L3").is_not_null())
        if matched.height == 0:
            raise RunFailure("no D-matched rows")
        ym = matched["y"].to_numpy().astype(int)
        dm_dates = matched["game_date"].to_numpy().astype(str)
        dm = {a: logloss(matched["p_%s" % a].to_numpy(), ym) for a in arms}
        lld = logloss(matched["L3"].to_numpy(), ym)
        out["d_matched_rows"] = int(matched.height)
        out["d_unmatched_rows"] = int(rows.height - matched.height)
        out["d_unmatched_reason"] = (
            "eval rows whose (game_pk, at_bat_number) is absent from the "
            "stored L3 prediction population (their primary-row convention; "
            "v1 rows are all completed, so unmatched rows reflect stored-"
            "population definition differences, not missing features)")
        # COMMON-ROW comparison: A/B/C on the exact D-matched subset
        out["matched_metrics"] = {
            "n": int(matched.height),
            "mean_ll": {a: float(dm[a].mean()) for a in arms},
            "mean_brier": {a: float(brier(matched["p_%s" % a].to_numpy(),
                                          ym).mean()) for a in arms},
            "mean_ll_D": float(lld.mean()),
        }
        out["mean_ll_D_matched"] = float(lld.mean())
        out["mean_brier_D_matched"] = float(
            brier(matched["L3"].to_numpy(), ym).mean())
        fam_d = {"D-A": lld - dm["A"], "C-D": dm["C"] - lld}
        out["paired_D_matched"] = {k: cluster_bootstrap_p(v, dm_dates)
                                   for k, v in fam_d.items()}
        fam_m = {"B-A": dm["B"] - dm["A"], "C-A": dm["C"] - dm["A"],
                 "C-B": dm["C"] - dm["B"]}
        out["paired_matched_secondary"] = {
            k: cluster_bootstrap_p(v, dm_dates) for k, v in fam_m.items()}
        all_paired = {**out["paired"], **out["paired_D_matched"]}
        out["holm"] = holm({k: v["p_two_sided"]
                            for k, v in all_paired.items()})
    else:
        out["holm"] = holm({k: v["p_two_sided"]
                            for k, v in out["paired"].items()})
    per_start = rows.group_by("game_pk").agg(
        [pl.col("y").cast(pl.Float64).mean().alias("_y")]
        + [pl.col("p_%s" % a).mean().alias("_p%s" % a) for a in arms])
    ys = per_start["_y"].to_numpy()
    out["start_weighted_brier"] = {
        a: float(brier(per_start["_p%s" % a].to_numpy(), ys).mean())
        for a in arms}
    return out


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
                digest = sha256_file(path)
                mode = "registered_first_hash"
            else:
                if sha256_file(path) != digest:
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

        pt = set()
        for season in (2022, 2023, 2024):
            pt |= set(frames[season]["pitch_type"].drop_nulls().unique()
                      .to_list())
        pitcher_types = sorted(pt)
        print("pitch types: %s" % pitcher_types)

        results = {}
        for block in (2023, 2024):
            print("BLOCK %d" % block)
            blk = run_block(block, frames, label_tables, keys_tables,
                            pitcher_types)
            results[str(block)] = {
                "metrics": block_metrics(blk["rows"], block == 2024),
                "per_origin": blk["meta"],
            }
            blk["rows"].write_csv(out_dir / ("predictions_%d.csv" % block))

        manifest = {
            "lane": "pa_lgbm_comparison",
            "status": "COMPLETE",
            "contract":
                "research/offseason_2026/pa-lgbm-contract-2026-10-09.md"
                " (Amendments 3-5)",
            "arms": {
                "A": "shrunk log5 w=150 (pa-k heritage), no fit",
                "B": "LightGBM binary, frozen legacy hyperparams, "
                     "no log5 features",
                "C": "B + [p_A, logit(p_A)]",
                "D": "stored L3 ridge logistic (logistic_pa; fit 2023 -> "
                     "out-of-sample 2024), 2024 block only, matched rows",
            },
            "primary": "opportunity-weighted paired PA log loss; "
                       "slate-date clustered bootstrap 2000 seed 20261001; "
                       "Holm within block",
            "label": "pa_completed_v1, first-pitcher completed PAs",
            "training_row_policy": "unweighted per PA; 2023 block trains on "
                                   "2023 pre-origin only (2022 via "
                                   "aggregates); 2024 block trains on 2023 "
                                   "+ 2024 pre-origin; chronological "
                                   "development transfer only",
            "no_2025_2026_access": True,
            "inputs": input_records,
            "pitcher_types": pitcher_types,
            "lgbm_params": {**LGBM_PARAMS, "n_estimators": 5000,
                            "early_stopping_rounds": ES_ROUNDS,
                            "val_frac": VAL_FRAC},
            "l3_predictions_sha256": sha256_file(L3_PRED),
            "results": results,
            "code": {p.name: sha256_file(p) for p in [
                HERE / "run_pa_lgbm_comparison.py",
                HERE / "pa_lgbm_scaffold.py"]},
        }
        (out_dir / "pa_lgbm_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        for block, res in results.items():
            m = res["metrics"]
            print("BLOCK %s: n=%d A %.5f B %.5f C %.5f%s" % (
                block, m["n"], m["mean_ll"]["A"], m["mean_ll"]["B"],
                m["mean_ll"]["C"],
                (" D %.5f" % m["mean_ll_D_matched"])
                if "mean_ll_D_matched" in m else ""))
            for k, g in m["holm"].items():
                pr = m["paired"].get(k) or m["paired_D_matched"][k]
                print("  %s: est %.6f CI [%.6f, %.6f] p_adj %.4f%s" % (
                    k, pr["estimate"], pr["lo95"], pr["hi95"], g["p_adj"],
                    " *" if g["significant"] else ""))
        print("WROTE %s" % out_dir)
        return 0
    except (RunFailure, rch.MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
