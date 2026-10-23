"""Feature-set ablation harness (dev blocks, walk-forward).

RESEARCH-ONLY, synthetic-first. Scores candidate feature sets by the
four registered metrics on IDENTICAL dev keys:
  1. multiclass log loss (the 4-class proper score),
  2. K-marginal log loss (vs the frozen binary y),
  3. count-RPS (per-start PMF through the REGISTERED aggregation),
  4. market log loss vs the de-vigged near-close consensus (reuse of
     the market-eval consensus; the join machinery is unchanged).

Feature sets (owner-ordered rows):
  LEAGUE   - league-constant baseline (no features)
  PITCHER  - the five pitcher-side FEAT_H3 features
  FULL     - the frozen eight (FEAT_H3)
  EW-30 / EW-180 - the full set with the EW half-life varied (90d is
             the registered default; never ablated before)

Park/context and lineup rows require NEW feature construction and are
NOT in this harness until their groups are built.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

import kcount_combiner as kc  # noqa: E402

FEATURE_SETS = {
    "LEAGUE": [],
    "PITCHER": ["p_pitcher_prior_w150", "lg_rate", "n_prior_pitcher",
                "cold_start", "ew_pitcher"],
    "FULL": list(ad.FEAT_H3),
}


# ------------------------------------------------- EW half-life variants
def entity_daily_state_hl(pa: "pl.DataFrame", ent: str,
                          half_life_days: float) -> "pl.DataFrame":
    """adapter.entity_daily_state with a PARAMETERIZED half-life (the
    registered function pins 90.0; this research shadow exists only for
    the EW ablation). Strictly-prior (shift(1)) - identical machinery."""
    import polars as pl

    return (
        pa.group_by(ent, "game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort(ent, "game_date")
        .with_columns(
            (pl.col("game_date") - pl.date(1970, 1, 1))
            .dt.total_days().cast(pl.Float64).alias("dnum"),
        )
        .with_columns(
            pl.col("k").cum_sum().over(ent).alias("cum_k"),
            pl.col("n").cum_sum().over(ent).alias("cum_n"),
            ((2.0 ** (pl.col("dnum") / half_life_days))
             * pl.col("k").cast(pl.Float64))
            .cum_sum().over(ent).alias("ew_k_cum"),
            ((2.0 ** (pl.col("dnum") / half_life_days))
             * pl.col("n").cast(pl.Float64))
            .cum_sum().over(ent).alias("ew_den_cum"),
        )
        .with_columns(
            pl.col("cum_k").shift(1).over(ent).fill_null(0).alias("prior_k"),
            pl.col("cum_n").shift(1).over(ent).fill_null(0).alias("prior_n"),
            pl.col("game_date").shift(1).over(ent).alias("src_date"),
            pl.col("ew_k_cum").shift(1).over(ent).fill_null(0.0)
            .alias("ew_k"),
            pl.col("ew_den_cum").shift(1).over(ent).fill_null(0.0)
            .alias("ew_den"),
            pl.col("game_date").shift(1).over(ent).alias("ew_src"),
        )
        .select(ent, "game_date", "prior_k", "prior_n", "src_date",
                "ew_k", "ew_den", "ew_src")
        .sort("game_date")
    )


def build_features_with_half_life(pa: "pl.DataFrame",
                                  half_life_days: float) -> "pl.DataFrame":
    """The frozen FEAT_H3 construction with a custom EW half-life:
    p_daily/b_daily rebuilt with entity_daily_state_hl, everything else
    identical (attach_prior_features consumes the state frames as-is)."""
    import polars as pl

    p_daily = entity_daily_state_hl(pa, "pitcher", half_life_days)
    b_daily = entity_daily_state_hl(pa, "batter", half_life_days)
    lg = ad.league_daily_state(pa)
    long = pa.select("game_pk", "at_bat_number", "batter", "pitcher",
                     "game_date", "y")
    return ad.attach_prior_features(long, p_daily, b_daily, lg)


# ------------------------------------------------------------ fit/apply
def fit_multinomial_features(train: "pl.DataFrame",
                             features: list[str]) -> dict:
    """The registered model family (StandardScaler + multinomial
    LogisticRegression C=1.0) on a FEATURE SUBSET."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    if not features:
        raise ValueError("LEAGUE row has no fit (use the baseline)")
    scaler = StandardScaler().fit(
        train.select(features).to_numpy())
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(scaler.transform(train.select(features).to_numpy()),
           train["class_label"].to_numpy())
    return {"features": list(features), "scaler": scaler, "lr": lr,
            "classes": [int(c) for c in lr.classes_]}


def apply_multinomial_features(feat: "pl.DataFrame", model: dict
                               ) -> np.ndarray:
    X = feat.select(model["features"]).to_numpy()
    return model["lr"].predict_proba(
        model["scaler"].transform(X))


def league_constant_probs(train: "pl.DataFrame",
                          n_rows: int) -> np.ndarray:
    """LEAGUE row: every PA predicted with the training class
    frequencies (m0.league_constant_baseline's definition)."""
    counts = train["class_label"].value_counts().sort("class_label")
    freqs = np.zeros(m0.N_CLASSES)
    for r in counts.to_dicts():
        freqs[int(r["class_label"])] = r["count"] / train.height
    return np.tile(freqs, (n_rows, 1))


# ------------------------------------------------------------- scoring
def evaluate_set(feat_eval: "pl.DataFrame", probs: np.ndarray) -> dict:
    """Multiclass log loss + K-marginal log loss on the identical eval
    PAs (the same definitions m0's endpoints use)."""
    y_multi = feat_eval["class_label"].to_numpy().astype(int)
    y_bin = feat_eval["y"].to_numpy().astype(int)
    eps = 1e-12
    mc_ll = float(-np.log(np.clip(
        probs[np.arange(len(y_multi)), y_multi], eps, 1)).mean())
    p_k = probs[:, m0.K_CLASS]
    k_ll = float(-(y_bin * np.log(p_k + eps)
                   + (1 - y_bin) * np.log(1 - p_k + eps)).mean())
    return {"multiclass_log_loss": mc_ll, "k_marginal_log_loss": k_ll,
            "n_eval_pa": int(len(y_multi))}


def count_rps_from_eval(probs: np.ndarray, feat_eval: "pl.DataFrame",
                        bf: "pl.DataFrame",
                        realized: "pl.DataFrame") -> dict:
    """Per-start count-RPS for a feature set: the set's per-PA K
    probability (class 0) grouped into the start's slot vector, then
    through the REGISTERED aggregation (cycled prefix-mean binomial
    mixed over the registered BF workload), scored against the
    registered realized K. Returns the per-start rps array plus the
    start keys for the identical-keys guarantee."""
    import polars as pl

    need = {"game_pk", "side", "pitcher", "slot", "game_date",
            "at_bat_number"}
    missing = need - set(feat_eval.columns)
    if missing:
        raise ValueError(f"eval frame missing columns: {sorted(missing)}")
    # one probability per SLOT (the slot's first realized PA, in bat
    # order) - the projected-lineup frame carries multiple PAs per slot
    p9 = (feat_eval.select("game_pk", "side", "pitcher", "slot",
                           "game_date", "at_bat_number")
          .with_columns(pl.Series("p_k", probs[:, m0.K_CLASS]))
          .sort("game_pk", "side", "slot", "at_bat_number")
          .unique(subset=["game_pk", "side", "pitcher", "slot"],
                  keep="first")
          .sort("game_pk", "side", "slot")
          .group_by("game_pk", "side", "pitcher")
          .agg(pl.col("p_k").sort_by("slot").alias("p9"),
               pl.col("game_date").first().alias("game_date")))
    bf37 = bf.select("game_pk", "side", "pitcher",
                     *[f"pmf37_{j}" for j in range(37)])
    desc = p9.join(bf37, on=["game_pk", "side", "pitcher"], how="inner")
    rps, keys, dates = [], [], []
    for r in desc.iter_rows(named=True):
        p9v = np.asarray(r["p9"], dtype=np.float64)
        if p9v.shape != (9,):
            raise ValueError(
                f"start {r['game_pk']}/{r['side']}: expected 9 slots, "
                f"got {p9v.shape}")
        b37 = np.asarray([r[f"pmf37_{j}"] for j in range(37)])
        b37 = b37 / b37.sum()
        bf_ext = ad.bf_pmf_from_37(b37)
        pmf = ad.count_pmf_from_mixture(bf_ext,
                                        ad.cycled_cond_mean(p9v))
        rrow = realized.filter(
            (pl.col("game_pk") == r["game_pk"])
            & (pl.col("side") == r["side"])
            & (pl.col("pitcher") == r["pitcher"]))
        if rrow.height != 1:
            raise ValueError(
                f"realized count mismatch for start "
                f"{r['game_pk']}/{r['side']} ({rrow.height} rows)")
        k_real = int(rrow["realized_k"][0])
        rps.append(float(kc.count_rps(pmf, k_real)))
        keys.append((r["game_pk"], r["side"], r["pitcher"]))
        dates.append(r["game_date"])
    return {"rps": np.asarray(rps), "keys": keys, "dates": dates}
