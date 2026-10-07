"""PA-K baseline: identity, target, pregame features, two arms.

Implements `research/offseason_2026/pa-k-baseline-prereg-draft.md`.
Pure functions over injected frames; NO file I/O, NO real-data fitting
or scoring. Real-data execution requires separate authorization.

Conventions (frozen):
- PA identity (game_pk, at_bat_number), unique - duplicates raise.
- Target: events in K_EVENTS -> 1; truncated_pa never enters.
- Features strictly pregame (prior game_dates only); cold starts fall
  back to the training league rate with prior_n = 0.
- Arms: A = shrunk log5 blend (w=150 frozen); B = L2 logistic (C=1.0).
"""

from __future__ import annotations

import numpy as np
import polars as pl

K_EVENTS = frozenset({"strikeout", "strikeout_double_play"})
EXCLUDED_EVENTS = frozenset({"truncated_pa"})
W_SHRINK = 150.0
LOGISTIC_C = 1.0
CLIP_LO = 1e-6
CLIP_HI = 1.0 - 1e-6
FEATURES = ["logit_p_pitcher", "logit_p_batter", "logit_league",
            "log1p_pitcher_prior_pa", "log1p_batter_prior_pa",
            "p_throws_right", "stand_left", "hand_mismatch"]


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def build_pa_table(pa_rows, first_pitcher_keys) -> "pl.DataFrame":
    """Filter terminal PAs to first-pitcher rows; add y; assert identity.

    pa_rows: frame with game_pk, game_date, pitcher, batter, stand,
    p_throws, at_bat_number, events (terminal rows only, incl.
    truncated_pa so the exclusion is explicit and counted).
    first_pitcher_keys: frame with game_pk, pitcher.
    """
    import polars as pl

    bad = pa_rows.filter(pl.col("events").is_in(list(EXCLUDED_EVENTS)))
    kept = pa_rows.filter(~pl.col("events").is_in(list(EXCLUDED_EVENTS)))
    dup = kept.select(["game_pk", "at_bat_number"]).n_unique()
    if dup != kept.height:
        raise ValueError("duplicate PA identity (game_pk, at_bat_number)")
    joined = kept.join(first_pitcher_keys.select(
        ["game_pk", pl.col("pitcher").alias("fp_pitcher")]),
        on="game_pk", how="inner").filter(
        pl.col("pitcher") == pl.col("fp_pitcher")).drop("fp_pitcher")
    out = joined.with_columns(
        pl.col("events").is_in(list(K_EVENTS)).cast(pl.Int8).alias("y"))
    out = out.with_columns(
        (pl.col("p_throws") == "R").cast(pl.Int8).alias("p_throws_right"),
        (pl.col("stand") == "L").cast(pl.Int8).alias("stand_left"),
        ((pl.col("p_throws") == "R") & (pl.col("stand") == "L"))
        .cast(pl.Int8).alias("hand_mismatch"))
    out = out.with_columns(
        pl.lit(int(bad.height)).alias("n_truncated_excluded"))
    return out


def prior_rates(train_pa, as_of, entity_col: str, w: float = W_SHRINK):
    """Train-only shrunk K rates as of `as_of` (strictly prior game_dates).

    Returns (dict entity -> (rate, prior_n), league_rate, league_n).
    """
    prior = train_pa.filter(
        (pl.col("game_date") < as_of) & (pl.col(entity_col).is_not_null()))
    league_n = prior.height
    league_k = prior["y"].sum()
    lg = float(league_k) / league_n if league_n else float("nan")
    g = (prior.group_by(entity_col)
         .agg(pl.col("y").sum().alias("k"), pl.len().alias("n")))
    rates = {r[0]: ((r[1] + w * lg) / (r[2] + w), int(r[2]))
             for r in g.iter_rows()}
    return rates, lg, league_n


def arm_a_probs(pa_eval, train_pa, as_of, w: float = W_SHRINK):
    """Shrunk log5 blend; cold starts -> league rate, prior_n = 0."""
    pr, lg, _ = prior_rates(train_pa, as_of, "pitcher", w)
    br, _, _ = prior_rates(train_pa, as_of, "batter", w)
    cols = {"pitcher": pr, "batter": br}
    p_p, n_p, p_b, n_b = [], [], [], []
    for r in pa_eval.iter_rows(named=True):
        pr_e = cols["pitcher"].get(r["pitcher"], (lg, 0))
        br_e = cols["batter"].get(r["batter"], (lg, 0))
        p_p.append(pr_e[0]); n_p.append(pr_e[1])
        p_b.append(br_e[0]); n_b.append(br_e[1])
    lg_safe = lg if lg == lg else 0.2
    z = (_logit(p_p) + _logit(p_b) - _logit(lg_safe))
    p = np.clip(_sigmoid(z), CLIP_LO, CLIP_HI)
    return p, lg_safe, (n_p, n_b)


def arm_b_features(pa_eval, train_pa, as_of, w: float = W_SHRINK):
    """Frozen pregame feature matrix (training-only rate inputs)."""
    pr, lg, _ = prior_rates(train_pa, as_of, "pitcher", w)
    br, _, _ = prior_rates(train_pa, as_of, "batter", w)
    lg_safe = lg if lg == lg else 0.2
    rows = []
    for r in pa_eval.iter_rows(named=True):
        pr_e = pr.get(r["pitcher"], (lg_safe, 0))
        br_e = br.get(r["batter"], (lg_safe, 0))
        rows.append([
            float(_logit(pr_e[0])), float(_logit(br_e[0])),
            float(_logit(lg_safe)),
            float(np.log1p(pr_e[1])), float(np.log1p(br_e[1])),
            float(r["p_throws_right"]), float(r["stand_left"]),
            float(r["hand_mismatch"])])
    return np.asarray(rows, dtype=float)


def _fit_preprocess(X):
    med = np.nanmedian(X, axis=0)
    filled = np.where(np.isnan(X), med, X)
    mu = filled.mean(axis=0)
    sd = filled.std(axis=0)
    sd[sd == 0.0] = 1.0
    return {"medians": med, "means": mu, "scales": sd}


def _apply_preprocess(st, X):
    filled = np.where(np.isnan(X), st["medians"], X)
    return (filled - st["means"]) / st["scales"]


def arm_b_probs(pa_eval, train_rows, as_of, rates_source=None,
                w: float = W_SHRINK, c: float = LOGISTIC_C):
    """L2 logistic (C frozen) on standardized frozen features.

    rates_source: frame the prior-rate aggregates come from (may include
    prior-season rows, e.g. 2022); defaults to train_rows. The logistic
    FITS on train_rows only (2023 labels convention); rate inputs for
    train and eval rows come from rates_source filtered strictly < as_of.
    """
    from sklearn.linear_model import LogisticRegression

    src = train_rows if rates_source is None else rates_source
    tr = train_rows.filter(pl.col("game_date") < as_of)
    Xtr = arm_b_features(tr, src, as_of, w)
    ytr = tr["y"].to_numpy()
    st = _fit_preprocess(Xtr)
    model = LogisticRegression(C=c, max_iter=5000)
    model.fit(_apply_preprocess(st, Xtr), ytr)
    Xev = arm_b_features(pa_eval, src, as_of, w)
    p = model.predict_proba(_apply_preprocess(st, Xev))[:, 1]
    return np.clip(p, CLIP_LO, CLIP_HI), {"preprocess": st, "model": model}


def logloss(p, y, clip_lo=CLIP_LO, clip_hi=CLIP_HI):
    p = np.clip(np.asarray(p, dtype=float), clip_lo, clip_hi)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(p, y):
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return (p - y) ** 2
