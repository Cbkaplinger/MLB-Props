"""Platoon feature family (platoon-features-v1) for the multiclass
predictor.

SYNTHETIC-TESTED ONLY until separately authorized. Pure functions over
injected frames; no I/O, no model code.

Declared family (card PROPOSED-platoon-information-multiclass.md): four
per-class columns, one per registered outcome class:

    p_platoon_c = (count_hist(c, split) + alpha * q_global_c(cutoff))
                  / (n_hist(split, cutoff) + alpha)

- Split = (batter `stand`, pitcher `p_throws`); cells {L,R}x{L,R}.
- Pooling population = ALL labeled rows (class_label >= 0) with game_date
  STRICTLY BEFORE the row's cutoff (same-date and future rows cannot enter
  by construction; a row's own outcome is never in its own feature).
- q_global_c(cutoff) = global strictly-prior class proportions (all splits
  pooled).
- Unseen split (n_hist = 0) or unknown/missing stand or hand: the feature
  equals q_global_c(cutoff) exactly (full shrinkage).
- Forecast rows (switch hitters): the batter's stand is NOT pregame-known,
  so `forecast_matchup_hands` derives the pregame-observable stand = the
  batter's modal strictly-prior stand CONDITIONAL on the opposing pitcher's
  hand (verified stable per pitcher); tie -> lexicographically smallest
  stand; no conditional history -> modal stand overall; no batter history
  -> unknown -> global fallback. The pitcher's hand is their strictly-prior
  modal p_throws.

All cumulative quantities are computed with per-group cumulative sums over
date-sorted daily counts (vectorized; no per-cutoff rescan of the PA
frame), then read at each cutoff from rows strictly before it.
"""
from __future__ import annotations

import polars as pl

VERSION = "platoon-features-v1"
CELLS = [("L", "L"), ("L", "R"), ("R", "L"), ("R", "R")]
PLATOON_COLS = ["p_platoon_0", "p_platoon_1", "p_platoon_2", "p_platoon_3"]
DEFAULT_ALPHA = 40.0


def _require_columns(frame, required, name):
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


def _labeled(pa_labeled: pl.DataFrame) -> pl.DataFrame:
    _require_columns(pa_labeled,
                     ["game_date", "stand", "p_throws", "class_label",
                      "pitcher", "batter"],
                     "labeled PA source")
    return pa_labeled.filter(pl.col("class_label") >= 0)


def _cum_daily(frame: pl.DataFrame, keys: list) -> pl.DataFrame:
    """Daily counts cumulatively summed over `keys`, date-sorted."""
    return (frame.group_by(["game_date"] + keys).agg(n=pl.len())
            .sort("game_date")
            .with_columns(cum=pl.col("n").cum_sum().over(keys)))


def _at_cutoffs(cum: pl.DataFrame, cutoffs: list, keys: list) -> pl.DataFrame:
    """Last cumulative value per key-combination at each cutoff, from
    rows STRICTLY BEFORE the cutoff."""
    out = None
    for t in sorted(set(cutoffs)):
        part = (cum.filter(pl.col("game_date") < t)
                .group_by(keys, maintain_order=True).agg(
                    n=pl.col("cum").max())
                .with_columns(pl.lit(t).alias("cutoff_date")))
        out = part if out is None else pl.concat([out, part])
    if out is None:
        raise ValueError(
            "no cutoffs supplied for the platoon feature construction")
    return out


def build_split_class_rates(pa_labeled: pl.DataFrame, cutoffs: list,
                            alpha: float = DEFAULT_ALPHA,
                            n_classes: int = 4) -> pl.DataFrame:
    """Per (cutoff, stand, p_throws) shrunk class rates + the per-cutoff
    global priors used for unseen splits. Refuses when a cutoff has no
    strictly-prior labeled rows (mirrors the registered null-feature
    refusal: the history window must precede the earliest cutoff)."""
    labeled = _labeled(pa_labeled)
    cell_cum = _cum_daily(labeled, ["stand", "p_throws", "class_label"])
    cls_cum = _cum_daily(labeled, ["class_label"])
    cells_at = _at_cutoffs(cell_cum, cutoffs,
                           ["stand", "p_throws", "class_label"])
    cls_at = _at_cutoffs(cls_cum, cutoffs, ["class_label"])
    rows = []
    for t in sorted(set(cutoffs)):
        ct = cells_at.filter(pl.col("cutoff_date") == t)
        gt = cls_at.filter(pl.col("cutoff_date") == t)
        total = float(gt["n"].sum())
        if total <= 0:
            raise ValueError(
                f"cutoff {t} has no strictly-prior labeled rows: "
                "platoon history window does not precede the earliest "
                "cutoff")
        q = {int(r["class_label"]): float(r["n"]) / total
             for r in gt.iter_rows(named=True)}
        cell_n = {}
        cell_c = {}
        for r in ct.iter_rows(named=True):
            key = (r["stand"], r["p_throws"])
            cell_n[key] = cell_n.get(key, 0) + int(r["n"])
            cell_c.setdefault(key, {})[int(r["class_label"])] = int(r["n"])
        for (stand, throws) in CELLS:
            n_hist = cell_n.get((stand, throws), 0)
            counts = cell_c.get((stand, throws), {})
            row = {"cutoff_date": t, "stand": stand, "p_throws": throws,
                   "n_hist": n_hist}
            for c in range(n_classes):
                q_c = q.get(c, 0.0)
                row[f"p_class_{c}"] = (
                    (counts.get(c, 0) + alpha * q_c) / (n_hist + alpha))
                row[f"_q_{c}"] = q_c
            rows.append(row)
    return pl.DataFrame(rows)


def pitcher_hands(pa_labeled: pl.DataFrame) -> pl.DataFrame:
    """Stable per-pitcher hand (verified: zero pitchers with >1 value).
    A pitcher with >1 distinct p_throws refuses (data-quality guard)."""
    labeled = _labeled(pa_labeled)
    g = labeled.group_by("pitcher").agg(
        k=pl.col("p_throws").n_unique(), hand=pl.col("p_throws").first())
    bad = g.filter(pl.col("k") > 1)
    if bad.height > 0:
        raise ValueError(
            f"{bad.height} pitcher(s) carry more than one p_throws "
            "value; refusing rather than guessing")
    return g.select("pitcher", "hand")


def forecast_matchup_hands(pa_labeled: pl.DataFrame,
                           requests: pl.DataFrame) -> pl.DataFrame:
    """Pregame-observable (stand, p_throws) for each unique
    (batter, pitcher, cutoff) request row.

    Cutoff-aware: the pitcher's hand is their modal strictly-prior
    p_throws AT THE CUTOFF (a pitcher with no rows strictly before the
    cutoff has NO known hand -> None); the batter's stand is their modal
    strictly-prior stand CONDITIONAL on that hand (tie ->
    lexicographically smallest stand); no conditional history -> modal
    stand overall; no batter history -> None (unknown -> global fallback
    downstream). Returns the input frame plus `f_stand` and `f_hand`."""
    _require_columns(requests, ["batter", "pitcher", "cutoff"],
                     "requests")
    labeled = _labeled(pa_labeled)
    req = requests.select("batter", "pitcher", "cutoff").unique()
    hand_cum = _cum_daily(labeled, ["pitcher", "p_throws"])
    cond_cum = _cum_daily(labeled, ["batter", "p_throws", "stand"])
    overall_cum = _cum_daily(labeled, ["batter", "stand"])

    hand_parts = []
    cond_parts = []
    overall_parts = []
    for t in sorted(set(req["cutoff"].unique().to_list())):
        hand_parts.append(
            hand_cum.filter(pl.col("game_date") < t)
            .sort(["pitcher", "cum", "p_throws"],
                  descending=[False, True, False])
            .group_by(["pitcher"], maintain_order=True)
            .first()
            .with_columns(pl.lit(t).alias("cutoff_date")))
        cond_parts.append(
            cond_cum.filter(pl.col("game_date") < t)
            .sort(["batter", "p_throws", "cum", "stand"],
                  descending=[False, False, True, False])
            .group_by(["batter", "p_throws"], maintain_order=True)
            .first()
            .with_columns(pl.lit(t).alias("cutoff_date")))
        overall_parts.append(
            overall_cum.filter(pl.col("game_date") < t)
            .sort(["batter", "cum", "stand"],
                  descending=[False, True, False])
            .group_by(["batter"], maintain_order=True)
            .first()
            .with_columns(pl.lit(t).alias("cutoff_date")))
    hands = (pl.concat(hand_parts)
             .select(pl.col("cutoff_date"), pl.col("pitcher"),
                     pl.col("p_throws").alias("hand"))
             if hand_parts else None)
    cond = (pl.concat(cond_parts)
            if cond_parts else None)
    overall = pl.concat(overall_parts) if overall_parts else None
    out = req
    if hands is not None:
        out = out.join(
            hands.select(pl.col("cutoff_date"), pl.col("pitcher"),
                         pl.col("hand").alias("f_hand")),
            left_on=["cutoff", "pitcher"],
            right_on=["cutoff_date", "pitcher"], how="left")
    else:
        out = out.with_columns(pl.lit(None, dtype=pl.Utf8).alias("f_hand"))
    if cond is not None:
        out = out.join(
            cond.select(pl.col("cutoff_date"), pl.col("batter"),
                        pl.col("p_throws"),
                        pl.col("stand").alias("cond_stand")),
            left_on=["cutoff", "batter", "f_hand"],
            right_on=["cutoff_date", "batter", "p_throws"], how="left")
    else:
        out = out.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("cond_stand"))
    if overall is not None:
        out = out.join(
            overall.select(pl.col("cutoff_date"), pl.col("batter"),
                           pl.col("stand").alias("overall_stand")),
            left_on=["cutoff", "batter"],
            right_on=["cutoff_date", "batter"], how="left")
    else:
        out = out.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("overall_stand"))
    out = out.with_columns(
        pl.coalesce(["cond_stand", "overall_stand"]).alias("f_stand"))
    return out.drop(["cond_stand", "overall_stand"])


def attach_platoon_features(frame: pl.DataFrame, rates: pl.DataFrame,
                            n_classes: int = 4) -> pl.DataFrame:
    """Attach the 4 platoon columns to `frame` (which carries `cutoff`,
    `stand`, `p_throws`). Unknown stand/hand (null) or an unseen cell ->
    the global prior for that cutoff (full shrinkage). Original frame
    order and row multiplicity are preserved exactly."""
    _require_columns(frame, ["cutoff", "stand", "p_throws"],
                     "feature frame")
    rate_cols = [f"p_class_{c}" for c in range(n_classes)]
    _require_columns(rates,
                     ["cutoff_date", "stand", "p_throws", "n_hist"]
                     + rate_cols, "platoon rates")
    q = rates.group_by("cutoff_date").agg(
        **{f"_gp_{c}": pl.col(f"_q_{c}").first()
           for c in range(n_classes)})
    idx = frame.with_row_index("__rid__")
    known = idx.filter(pl.col("stand").is_not_null()
                       & pl.col("p_throws").is_not_null())
    unknown = idx.filter(pl.col("stand").is_null()
                         | pl.col("p_throws").is_null())
    parts = []
    if known.height > 0:
        kj = known.join(
            rates.select(["cutoff_date", "stand", "p_throws", "n_hist"]
                         + rate_cols),
            left_on=["cutoff", "stand", "p_throws"],
            right_on=["cutoff_date", "stand", "p_throws"], how="left")
        kj = kj.join(q, left_on="cutoff", right_on="cutoff_date",
                     how="left")
        if kj.filter(pl.col("_gp_0").is_null()).height > 0:
            raise ValueError(
                "platoon rates missing for a cutoff: the rates table "
                "does not cover every cutoff in the feature frame")
        for c in range(n_classes):
            kj = kj.with_columns(
                pl.coalesce([f"p_class_{c}", f"_gp_{c}"])
                .alias(f"p_platoon_{c}"))
        parts.append(kj.drop(["n_hist"] + rate_cols
                             + [f"_gp_{c}" for c in range(n_classes)]))
    if unknown.height > 0:
        uk = unknown.join(q, left_on="cutoff", right_on="cutoff_date",
                          how="left")
        if uk.filter(pl.col("_gp_0").is_null()).height > 0:
            raise ValueError(
                "platoon rates missing for a cutoff: the rates table "
                "does not cover every cutoff in the feature frame")
        for c in range(n_classes):
            uk = uk.with_columns(
                pl.col(f"_gp_{c}").alias(f"p_platoon_{c}"))
        parts.append(uk.drop([f"_gp_{c}" for c in range(n_classes)]))
    out = pl.concat(parts)
    return out.sort("__rid__").drop("__rid__")
