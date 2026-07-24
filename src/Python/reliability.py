"""Stat reliability / stabilization helpers.

Extracted from the original ``Strikeouts.ipynb`` exploratory notebook so the
same logic can be reused by the EDA notebook and by feature-selection code, and
covered by unit tests.

All functions expect a tidy per-start DataFrame with at least these columns:
``player_name`` (pitcher id), ``game_date`` (sortable date), ``PA`` (plate
appearances, used as the denominator for rate stats), plus whatever ``stat``
column is being measured.

Terminology
-----------
* **rate stat** – a per-PA counting stat (K, BB, Whiffs, ...). Aggregated as
  ``sum(stat) / sum(PA)`` within a window.
* **mean stat** – a value that is already a rate or a per-start measurement
  (velocity, usage %, ...). Aggregated as ``mean(stat)`` within a window.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

try:  # ICC is optional; pingouin is not a hard dependency.
    import pingouin as pg

    HAS_PINGOUIN = True
except ImportError:  # pragma: no cover - depends on optional install
    HAS_PINGOUIN = False


# Counting stats measured per plate appearance (denominator = PA).
RATE_STATS: tuple[str, ...] = (
    "K", "BB", "Whiffs", "HR", "Hits", "GB", "FB", "HBP", "BIP",
    "CS", "CSW", "Strikes", "Balls", "Outs", "Pitches", "Runs",
)

# Stats that are already rates / per-start measurements (use the mean).
MEAN_STATS: tuple[str, ...] = (
    "throws_ff", "throws_si", "throws_fc", "throws_sl",
    "throws_st", "throws_cu", "throws_ch", "k_rate",
    "ff_velo", "ff_spinrate", "ff_ivb", "ff_hb", "ff_vaa",
    "si_velo", "si_spinrate", "si_ivb", "si_hb", "si_vaa",
    "sl_velo", "sl_spinrate", "sl_ivb", "sl_hb", "sl_vaa",
    "fc_velo", "fc_spinrate", "fc_ivb", "fc_hb", "fc_vaa",
    "st_velo", "st_spinrate", "st_ivb", "st_hb", "st_vaa",
    "cu_velo", "cu_spinrate", "cu_ivb", "cu_hb", "cu_vaa",
    "ch_velo", "ch_spinrate", "ch_ivb", "ch_hb", "ch_vaa",
    "ff_usage_vR", "ff_usage_vL", "si_usage_vR", "si_usage_vL",
    "fc_usage_vR", "fc_usage_vL", "sl_usage_vR", "sl_usage_vL",
    "st_usage_vR", "st_usage_vL", "cu_usage_vR", "cu_usage_vL",
    "ch_usage_vR", "ch_usage_vL",
    # plate-discipline rates (already rates -> use the mean)
    "zone_rate", "swing_rate", "chase_rate", "zswing_rate",
    "contact_rate", "zcontact_rate", "ocontact_rate", "swstr_rate", "whiff_rate",
    # release / mechanics
    "extension", "rel_x", "rel_z", "rel_x_sd", "rel_z_sd",
    # ERA estimators (per-start values)
    "FIP", "xFIP",
)


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson r via NumPy."""
    if a.size < 2 or a.std() < 1e-9 or b.std() < 1e-9:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rho via average ranks and NumPy Pearson correlation."""
    ranks_a = pd.Series(a).rank(method="average").to_numpy()
    ranks_b = pd.Series(b).rank(method="average").to_numpy()
    return _pearson(ranks_a, ranks_b)


def _slope(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope of ``y`` on ``x``."""
    variance = float(np.var(x))
    return float(np.cov(x, y, ddof=0)[0, 1] / variance) if variance > 0 else np.nan


def _aggregate(window: pd.DataFrame, stat: str, use_rate: bool) -> float:
    """Collapse a window of starts into a single value for ``stat``."""
    if use_rate:
        denom = float(window["PA"].sum())
        return window[stat].sum() / max(denom, 1.0)
    return float(window[stat].mean())


def _split_half_pairs(
    df: pd.DataFrame,
    stat: str,
    n_games_per_half: int,
    use_rate: bool,
) -> pd.DataFrame:
    """Return per-pitcher (first-half, second-half) value pairs."""
    results = []
    for _, grp in df.groupby("player_name"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        grp = grp.dropna(subset=[stat])
        if len(grp) < 2 * n_games_per_half:
            continue
        first = grp.iloc[:n_games_per_half]
        second = grp.iloc[n_games_per_half : 2 * n_games_per_half]
        results.append(
            {
                "first": _aggregate(first, stat, use_rate),
                "second": _aggregate(second, stat, use_rate),
            }
        )
    return pd.DataFrame(results).dropna()


def split_half_reliability(
    df: pd.DataFrame,
    stat: str,
    n_games_per_half: int,
    use_rate: bool = True,
    min_pitchers: int = 50,
) -> float:
    """Pearson split-half correlation for ``stat`` at a given window size.

    Returns ``np.nan`` when there are too few qualified pitchers or no
    variance in either half.
    """
    if stat not in df.columns:
        return np.nan
    pairs = _split_half_pairs(df, stat, n_games_per_half, use_rate)
    if len(pairs) < min_pitchers:
        return np.nan
    if pairs["first"].std() < 1e-6 or pairs["second"].std() < 1e-6:
        return np.nan
    return _pearson(
        pairs["first"].to_numpy(dtype=float),
        pairs["second"].to_numpy(dtype=float),
    )


def split_half_enhanced(
    df: pd.DataFrame,
    stat: str,
    n_games_per_half: int,
    use_rate: bool = True,
    min_pitchers: int = 50,
) -> dict[str, float]:
    """Split-half reliability plus Spearman, SEM, slope, and sample size."""
    null = {k: np.nan for k in ("pearson_r", "spearman_rho", "sem", "beta1", "n")}
    if stat not in df.columns:
        return null
    pairs = _split_half_pairs(df, stat, n_games_per_half, use_rate)
    if len(pairs) < min_pitchers:
        return null
    if pairs["first"].std() < 1e-6 or pairs["second"].std() < 1e-6:
        return null

    first = pairs["first"].to_numpy(dtype=float)
    second = pairs["second"].to_numpy(dtype=float)
    r = _pearson(first, second)
    rho = _spearman(first, second)
    sem = pairs["first"].std() * np.sqrt(1 - r) if r < 1.0 else 0.0
    slope = _slope(first, second)
    return {
        "pearson_r": float(r),
        "spearman_rho": float(rho),
        "sem": float(sem),
        "beta1": float(slope),
        "n": int(len(pairs)),
    }


def compute_icc(
    df: pd.DataFrame,
    stat: str,
    n_games_per_half: int = 10,
    use_rate: bool = True,
    min_pitchers: int = 50,
) -> float:
    """ICC(2,1) between first- and second-half values (needs ``pingouin``)."""
    if not HAS_PINGOUIN or stat not in df.columns:
        return np.nan

    rows = []
    for pitcher, grp in df.groupby("player_name"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        grp = grp.dropna(subset=[stat])
        if len(grp) < 2 * n_games_per_half:
            continue
        first = grp.iloc[:n_games_per_half]
        second = grp.iloc[n_games_per_half : 2 * n_games_per_half]
        rows.append({"pitcher": pitcher, "half": "first", "val": _aggregate(first, stat, use_rate)})
        rows.append({"pitcher": pitcher, "half": "second", "val": _aggregate(second, stat, use_rate)})

    if len(rows) // 2 < min_pitchers:
        return np.nan

    icc_df = pd.DataFrame(rows).dropna()
    icc_result = pg.intraclass_corr(
        data=icc_df, targets="pitcher", raters="half", ratings="val"
    )
    row = icc_result[icc_result["Type"] == "ICC2"]
    return float(row["ICC"].values[0]) if len(row) else np.nan


def yoy_reliability(
    df: pd.DataFrame,
    stat: str,
    use_rate: bool = True,
    min_pairs: int = 30,
    min_starts_per_year: int = 5,
) -> float:
    """Year-over-year Pearson correlation of ``stat`` across consecutive seasons."""
    if stat not in df.columns:
        return np.nan
    df = df.copy()
    df["year"] = pd.to_datetime(df["game_date"]).dt.year
    years = sorted(df["year"].dropna().unique())

    rows = []
    for _, grp in df.groupby("player_name"):
        grp = grp.dropna(subset=[stat])
        for y in years[:-1]:
            y1 = grp[grp["year"] == y]
            y2 = grp[grp["year"] == y + 1]
            if len(y1) < min_starts_per_year or len(y2) < min_starts_per_year:
                continue
            rows.append(
                {"y1": _aggregate(y1, stat, use_rate), "y2": _aggregate(y2, stat, use_rate)}
            )

    res = pd.DataFrame(rows).dropna()
    if len(res) < min_pairs:
        return np.nan
    return _pearson(
        res["y1"].to_numpy(dtype=float),
        res["y2"].to_numpy(dtype=float),
    )


def stabilization_curve(
    df: pd.DataFrame,
    rate_stats: Iterable[str] = RATE_STATS,
    mean_stats: Iterable[str] = MEAN_STATS,
    windows: Iterable[int] = range(1, 40),
    min_pitchers: int = 50,
) -> pd.DataFrame:
    """Split-half reliability vs window size for many stats at once.

    Equivalent to calling :func:`split_half_reliability` for every
    ``(stat, window)`` pair, but groups the data a single time and uses
    cumulative sums so each window is an O(1) slice. Returns a DataFrame
    indexed by window size with one column per stat.
    """
    windows = list(windows)
    plan = [(s, True) for s in rate_stats if s in df.columns]
    plan += [(s, False) for s in mean_stats if s in df.columns]
    stat_cols = [s for s, _ in plan]
    if not stat_cols:
        return pd.DataFrame(index=windows)

    ordered = df.sort_values(["player_name", "game_date"])
    # Per-pitcher numpy views of PA and each stat column (grouped once).
    groups: list[tuple[np.ndarray, dict[str, np.ndarray]]] = []
    for _, g in ordered.groupby("player_name", sort=False):
        pa = g["PA"].to_numpy(dtype=float)
        groups.append((pa, {s: g[s].to_numpy(dtype=float) for s in stat_cols}))

    result: dict[str, list[float]] = {}
    for stat, use_rate in plan:
        # Precompute per-pitcher cumulative sums over the stat's non-null rows.
        cached: list[tuple[int, np.ndarray, np.ndarray]] = []
        for pa, arrs in groups:
            vals = arrs[stat]
            mask = ~np.isnan(vals)
            v = vals[mask]
            if v.size == 0:
                continue
            cs_v = np.concatenate(([0.0], np.cumsum(v)))
            cs_p = np.concatenate(([0.0], np.cumsum(pa[mask])))
            cached.append((v.size, cs_v, cs_p))

        col: list[float] = []
        for n in windows:
            first, second = [], []
            for length, cs_v, cs_p in cached:
                if length < 2 * n:
                    continue
                if use_rate:
                    d1 = cs_p[n]
                    d2 = cs_p[2 * n] - cs_p[n]
                    first.append(cs_v[n] / (d1 if d1 >= 1 else 1.0))
                    second.append((cs_v[2 * n] - cs_v[n]) / (d2 if d2 >= 1 else 1.0))
                else:
                    first.append(cs_v[n] / n)
                    second.append((cs_v[2 * n] - cs_v[n]) / n)
            if len(first) < min_pitchers:
                col.append(np.nan)
                continue
            fa, sa = np.asarray(first), np.asarray(second)
            if fa.std() < 1e-6 or sa.std() < 1e-6:
                col.append(np.nan)
                continue
            col.append(_pearson(fa, sa))
        result[stat] = col

    return pd.DataFrame(result, index=windows)


# Default plans for denominator-aware stabilization. Each entry is
# (stat, denominator_column, use_rate).
#   - pitch-denominated: measured per pitch thrown (physics + swing decisions)
#   - PA-denominated: measured per plate appearance (outcome counts)
PITCH_DENOM_PLAN: tuple[tuple[str, str, bool], ...] = (
    ("Whiffs", "Pitches", True), ("CSW", "Pitches", True), ("CS", "Pitches", True),
    ("Chases", "OutZone", True), ("ZSwings", "InZone", True),
    ("Contacts", "Swings", True), ("ZContacts", "ZSwings", True),
    ("Swings", "Pitches", True), ("InZone", "Pitches", True),
    ("ff_velo", "Pitches", False), ("ff_spinrate", "Pitches", False),
    ("ff_ivb", "Pitches", False), ("ff_hb", "Pitches", False), ("ff_vaa", "Pitches", False),
)
PA_DENOM_PLAN: tuple[tuple[str, str, bool], ...] = (
    ("K", "PA", True), ("BB", "PA", True), ("HR", "PA", True),
    ("Hits", "PA", True), ("HBP", "PA", True), ("BIP", "PA", True),
    ("xBA_num", "xBA_den", True),
    ("wOBA_num", "wOBA_den", True),
    ("xwOBA_num", "wOBA_den", True),
)


def _two_bucket_values(
    num: np.ndarray, den: np.ndarray, target: float, use_rate: bool
) -> tuple[float, float] | None:
    """Split one player's chronological starts into two equal denominator buckets.

    Walk the starts forward, accumulating ``den`` until it reaches ``target``
    (bucket 1), then again for bucket 2. Returns the two aggregated values, or
    ``None`` if the player lacks ``2 * target`` denominator units.
    """
    cs = np.cumsum(den)
    if cs.size == 0 or cs[-1] < 2 * target:
        return None
    i1 = int(np.searchsorted(cs, target))  # first start reaching the target
    d1_num, d1_den = num[: i1 + 1].sum(), den[: i1 + 1].sum()
    rest_cs = cs[i1 + 1 :] - cs[i1]
    i2_rel = int(np.searchsorted(rest_cs, target))
    if i2_rel >= rest_cs.size:
        return None
    i2 = i1 + 1 + i2_rel
    d2_num, d2_den = num[i1 + 1 : i2 + 1].sum(), den[i1 + 1 : i2 + 1].sum()
    if use_rate:
        return d1_num / max(d1_den, 1.0), d2_num / max(d2_den, 1.0)
    # mean stats: denominator-weighted average over the bucket's starts
    return d1_num / max(d1_den, 1.0), d2_num / max(d2_den, 1.0)


def stabilization_by_denominator(
    df: pd.DataFrame,
    plan: Iterable[tuple[str, str, bool]],
    targets: Iterable[int],
    id_col: str = "player_name",
    date_col: str = "game_date",
    min_players: int = 50,
) -> pd.DataFrame:
    """Split-half reliability vs sample size measured in the stat's own unit.

    Unlike :func:`stabilization_curve` (which splits by a fixed number of
    *games*), this expresses the x-axis in the stat's natural denominator so
    pitch-level and PA-level stats are each measured honestly:

    - Physics / swing-decision stats -> denominator is pitches (or InZone /
      OutZone / Swings for zone-conditional rates).
    - Outcome stats (K, BB, HR, Hits) -> denominator is PA.

    For each ``(stat, denom_col, use_rate)`` in ``plan`` and each ``target`` in
    ``targets``, every player's starts are split into two consecutive buckets
    that each accumulate ``target`` denominator units; the split-half Pearson r
    across players is reported. Use the target where r crosses ~0.5 as the
    stabilization sample size, then divide by the average denominator-per-start
    to translate it into a rolling **game** window.

    For ``use_rate`` stats the bucket value is ``sum(stat)/sum(denom)``; for mean
    stats it is the denominator-weighted mean (``sum(stat*?)`` is not needed
    because ``stat`` is already per-start, so we weight by denom via the same
    ratio form). Returns a DataFrame indexed by ``target`` with one column per
    stat.
    """
    targets = list(targets)
    plan = [(s, d, r) for (s, d, r) in plan if s in df.columns and d in df.columns]
    if not plan:
        return pd.DataFrame(index=targets)

    needed = sorted({c for s, d, _ in plan for c in (s, d)})
    ordered = df.sort_values([id_col, date_col])
    groups = [
        {c: g[c].to_numpy(dtype=float) for c in needed}
        for _, g in ordered.groupby(id_col, sort=False)
    ]

    result: dict[str, list[float]] = {}
    for stat, denom_col, use_rate in plan:
        col: list[float] = []
        for target in targets:
            firsts, seconds = [], []
            for arrs in groups:
                num, den = arrs[stat], arrs[denom_col]
                mask = ~np.isnan(num) & ~np.isnan(den)
                num, den = num[mask], den[mask]
                # For a mean stat, weight each start's value by its denominator.
                weighted_num = num * den if not use_rate else num
                pair = _two_bucket_values(weighted_num, den, float(target), use_rate)
                if pair is not None:
                    firsts.append(pair[0])
                    seconds.append(pair[1])
            col.append(
                _pearson(np.asarray(firsts), np.asarray(seconds))
                if len(firsts) >= min_players
                else np.nan
            )
        result[stat] = col

    return pd.DataFrame(result, index=targets)


def feature_tier(r: float) -> str:
    """Bucket a reliability coefficient into a coarse stability tier."""
    if pd.isna(r):
        return "Unknown"
    if r >= 0.70:
        return "Tier 1 - stable"
    if r >= 0.50:
        return "Tier 2 - moderate"
    return "Tier 3 - noisy"


def reliability_table(
    df: pd.DataFrame,
    n_games_per_half: int = 10,
    rate_stats: Iterable[str] = RATE_STATS,
    mean_stats: Iterable[str] = MEAN_STATS,
    min_pitchers: int = 50,
    min_pairs: int = 30,
    min_starts_per_year: int = 5,
) -> pd.DataFrame:
    """Build a per-stat reliability table (split-half, ICC, YoY, SEM, slope).

    Groups the data a single time and reuses per-pitcher numpy views for every
    stat, which is dramatically faster than re-grouping per metric.
    """
    plan = [(s, True) for s in rate_stats if s in df.columns]
    plan += [(s, False) for s in mean_stats if s in df.columns]
    stat_cols = [s for s, _ in plan]
    if not stat_cols:
        return pd.DataFrame()

    ordered = df.sort_values(["player_name", "game_date"]).copy()
    ordered["_year"] = pd.to_datetime(ordered["game_date"]).dt.year
    groups = [
        (g["PA"].to_numpy(dtype=float), g["_year"].to_numpy(), {s: g[s].to_numpy(dtype=float) for s in stat_cols})
        for _, g in ordered.groupby("player_name", sort=False)
    ]

    n = n_games_per_half
    records = []
    for stat, use_rate in plan:
        first, second, yoy1, yoy2 = [], [], [], []
        for pa, yr, arrs in groups:
            vals = arrs[stat]
            mask = ~np.isnan(vals)
            v, p, y = vals[mask], pa[mask], yr[mask]
            if v.size == 0:
                continue

            if v.size >= 2 * n:
                if use_rate:
                    d1, d2 = p[:n].sum(), p[n : 2 * n].sum()
                    first.append(v[:n].sum() / (d1 if d1 >= 1 else 1.0))
                    second.append(v[n : 2 * n].sum() / (d2 if d2 >= 1 else 1.0))
                else:
                    first.append(v[:n].mean())
                    second.append(v[n : 2 * n].mean())

            aggs = {}
            for yy in np.unique(y):
                m = y == yy
                aggs[yy] = (v[m].sum(), p[m].sum(), int(m.sum()))
            for yy in aggs:
                nxt = aggs.get(yy + 1)
                if nxt is None:
                    continue
                c1, c2 = aggs[yy][2], nxt[2]
                if c1 < min_starts_per_year or c2 < min_starts_per_year:
                    continue
                if use_rate:
                    yoy1.append(aggs[yy][0] / max(aggs[yy][1], 1.0))
                    yoy2.append(nxt[0] / max(nxt[1], 1.0))
                else:
                    yoy1.append(aggs[yy][0] / c1)
                    yoy2.append(nxt[0] / c2)

        pearson_r = spearman_rho = sem = beta1 = np.nan
        fa, sa = np.asarray(first), np.asarray(second)
        if fa.size >= min_pitchers and fa.std() > 1e-6 and sa.std() > 1e-6:
            pearson_r = _pearson(fa, sa)
            spearman_rho = _spearman(fa, sa)
            sem = float(fa.std() * np.sqrt(1 - pearson_r)) if pearson_r < 1.0 else 0.0
            beta1 = _slope(fa, sa)

        yoy_r = np.nan
        ya, yb = np.asarray(yoy1), np.asarray(yoy2)
        if ya.size >= min_pairs and ya.std() > 1e-6 and yb.std() > 1e-6:
            yoy_r = _pearson(ya, yb)

        records.append(
            {
                "stat": stat,
                "use_rate": use_rate,
                "pearson_r": pearson_r,
                "spearman_rho": spearman_rho,
                "icc2": compute_icc(df, stat, n_games_per_half=n, use_rate=use_rate),
                "yoy_r": yoy_r,
                "sem": sem,
                "beta1": beta1,
                "n_pitchers": int(fa.size),
            }
        )

    table = pd.DataFrame(records)
    if not table.empty:
        table["feature_tier"] = table["yoy_r"].apply(feature_tier)
        table = table.sort_values("yoy_r", ascending=False, na_position="last")
    return table.reset_index(drop=True)
