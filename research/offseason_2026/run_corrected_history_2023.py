"""Corrected-history workload experiment (2023 origins, 2022 history).

Implements frozen preregistration
`research/offseason_2026/corrected-history-workload-prereg.md`.
ONE development diagnostic: corrected strictly-prior histories vs a
properly reconstructed trailing baseline. No 2025/2026 access, no
tuning, no promotion claims.

Reuse provenance (reviewed components, no blind copies):
- run_reconstruction_audit_2023 (COMMITTED main): audit_identity,
  bf_proxy_table, verify/hash/period patterns -> IMPORTED, not copied.
- workload_spine (COMMITTED main): build_appearance_history ->
  IMPORTED, not copied.
- tbf_reconstruct.py (preserved, distribution-spec): ALPHA_GRID,
  INNER_VAL_FRACTION, ORIGINS_2023, FINAL_EVAL_DATE, assign_origins,
  _inner_chrono_split, fit_origin -> COPIED VERBATIM (target column
  `PA` means BF per frozen target definition, identical to Run 1).
- tbf_nonoracle.py (preserved): BOOTSTRAP_*, TRAILING_MIN_HISTORY,
  TEAMRATE_FEATURES, build_rate_tables, team_rate,
  build_team_rate_features, prior_season_rates, build_batting_rows,
  evaluate_arm, cluster_bootstrap, assert_unique_predictions,
  assert_finite_predictions, evaluate_kill_rules -> COPIED VERBATIM,
  EXCEPT trailing baseline: reimplemented with strict date
  inequality (shift(1) admits same-date doubleheader rows; the
  corrected version excludes them; difference disclosed in prereg).
- src/Python/statcast.py NON_PA_EVENTS (tracked): imported, not copied.

Prohibited here: multi-season artifact opens (Savant 2022/2023 files
only), oracle lineup inputs, rolling-artifact histories.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import workload_spine as ws  # noqa: E402
from Python.statcast import NON_PA_EVENTS  # noqa: E402
from run_reconstruction_audit_2023 import (  # noqa: E402
    audit_identity,
    bf_proxy_table,
    build_history_appearances,
)

# ---------------------------------------------------------------------------
# Frozen constants (copied verbatim from preserved sources; see prereg)
# ---------------------------------------------------------------------------

ALPHA_GRID = tuple(float(x) for x in np.logspace(-2, 3, 12))
INNER_VAL_FRACTION = 0.2
ORIGINS_2023 = ("2023-07-01", "2023-08-01", "2023-09-01")
FINAL_EVAL_DATE = "2023-10-01"

BOOTSTRAP_SEED = 20261001
BOOTSTRAP_RESAMPLES = 2000
TRAILING_MIN_HISTORY = 3
TEAMRATE_FEATURES = ["opp_team_k_rate_std", "opp_team_k_rate_vs_hand"]

CHALLENGER_FEATURES = [
    "start_capacity_shrunk_bf",
    "start_capacity_median_bf_5",
    "start_capacity_mean_bf",
    "n_capacity_appearances",
    "relief_mean_bf",
    "actual_bf_mean_last5",
    "actual_expanding_mean_bf",
    "days_since_last_capacity",
    "opp_team_k_rate_std",
    "opp_team_k_rate_vs_hand",
]

SAVANT_2023_SHA = "b9f9db9923badca17e551cf23be8429bfba984361732a8911bf0d68a40d5285f"
SAVANT_2022_SHA = "63d40a4955da73ab8f9b01d87d90dd676acdf8b7447c574a5edf807897724ce4"
SEASON_SHA_KNOWN = {2022: SAVANT_2022_SHA, 2023: SAVANT_2023_SHA}

PITCH_KEY_COLUMNS = (
    "game_pk", "pitcher", "game_date", "inning",
    "inning_topbot", "at_bat_number", "pitch_number",
    "home_team", "away_team", "p_throws", "events",
)

INELIGIBLE_REASON = "retrospective_diagnostic_pregame_availability_unverified"
ERROR_SIGN_CONVENTION = (
    "error = prediction - expected; bias = mean(pred - y); paired "
    "per-start MAE diff = |y-pred_challenger| - |y-pred_comparator|, "
    "positive = challenger worse"
)


class MechanicalFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_external(path: Path) -> str:
    """Hash a preserved external dependency if present; otherwise an
    honest unavailable marker (CI checkouts lack the preserved worktree)."""
    if path.is_file():
        return sha256_file(path)
    return "external-preserved (not available on this machine)"


def verify_input(path: Path, expected_sha: str | None, label: str) -> dict:
    if expected_sha is None:
        raise MechanicalFailure(
            "BLOCKED: no approved digest for %s (%s); supply "
            "--season-sha" % (label, path))
    if not path.is_file():
        raise MechanicalFailure("missing input %s: %s" % (label, path))
    actual = sha256_file(path)
    if actual != expected_sha.lower():
        raise MechanicalFailure(
            "BLOCKED: source hash mismatch for %s: %s" % (label, actual))
    return {"path": str(path), "sha256": actual,
            "bytes": path.stat().st_size}


def frame_years(frame: pl.DataFrame) -> set[int]:
    col = frame["game_date"]
    if col.dtype == pl.Date:
        return set(d.year for d in col.to_list())
    return set(int(str(d)[:4]) for d in col.to_list())


def assert_years(frame: pl.DataFrame, year: int, label: str) -> None:
    years = frame_years(frame)
    if years != {year}:
        raise MechanicalFailure(
            "period violation in %s: years %s (fail-closed, not filtered)"
            % (label, sorted(years)))


# ---------------------------------------------------------------------------
# Canonical BF target (frozen section 2)
# ---------------------------------------------------------------------------


def terminal_rows(pitches: pl.DataFrame) -> pl.DataFrame:
    return (
        pitches.sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(["game_pk", "at_bat_number"], keep="last",
                maintain_order=True)
    )


def bf_table_canonical(pitches: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    term = terminal_rows(pitches)
    ok = term.filter(
        pl.col("events").is_not_null()
        & ~pl.col("events").is_in(list(NON_PA_EVENTS))
        & (pl.col("events") != "truncated_pa")
    )
    n_excluded = term.height - ok.height
    bf = (
        ok.group_by(["game_pk", "pitcher"])
        .agg(pl.col("at_bat_number").n_unique().alias("PA"))
    )
    return bf, {"n_terminal_at_bats": term.height,
                "n_excluded_non_pa": n_excluded}


# ---------------------------------------------------------------------------
# Origin assignment + fitting (verbatim semantics from tbf_reconstruct)
# ---------------------------------------------------------------------------


def assign_origins(frame: pd.DataFrame, origins: tuple[str, ...],
                   final_date: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    first = pd.Timestamp(origins[0])
    frame["role"] = "train_only"
    frame["origin"] = None
    in_window = (frame["game_date"] >= first) & (
        frame["game_date"] <= pd.Timestamp(final_date)
    )
    for origin in origins:
        o = pd.Timestamp(origin)
        mask = in_window & (frame["game_date"] >= o)
        frame.loc[mask, "origin"] = origin
        frame.loc[mask, "role"] = "eval"
    frame.loc[~in_window & (frame["game_date"] >= first), "role"] = (
        "excluded_after_final"
    )
    return frame


def _inner_chrono_split(train: pd.DataFrame) -> tuple | None:
    dates = np.sort(train["game_date"].unique())
    if len(dates) < 3:
        return None
    cut = dates[int(len(dates) * (1 - INNER_VAL_FRACTION))]
    inner_tr = train[train["game_date"] < cut]
    inner_val = train[train["game_date"] >= cut]
    if inner_tr.empty or inner_val.empty:
        return None
    return inner_tr, inner_val


def fit_origin(train: pd.DataFrame, features: list[str]) -> dict:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    split = _inner_chrono_split(train)
    if split is None:
        return {"status": "BLOCKED",
                "reason": "inner chronological split not formable"}
    inner_tr, inner_val = split
    best_alpha, best_mae, grid = ALPHA_GRID[0], float("inf"), []
    for alpha in ALPHA_GRID:
        model = make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(),
            Ridge(alpha=alpha),
        )
        model.fit(inner_tr[features], inner_tr["PA"])
        pred = np.maximum(model.predict(inner_val[features]), 0.0)
        mae = float(np.mean(np.abs(inner_val["PA"].to_numpy() - pred)))
        grid.append({"alpha": alpha, "inner_val_mae": mae})
        if mae < best_mae:
            best_mae, best_alpha = mae, alpha
    final = make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(),
        Ridge(alpha=best_alpha),
    )
    final.fit(train[features], train["PA"])
    learned_clip = float(train["PA"].quantile(0.999))
    return {
        "status": "OK",
        "train_max_date": str(train["game_date"].max().date()),
        "n_train": int(len(train)),
        "inner_train_max": str(inner_tr["game_date"].max().date()),
        "inner_val_start": str(inner_val["game_date"].min().date()),
        "selected_alpha": best_alpha,
        "best_inner_mae": best_mae,
        "alpha_grid": grid,
        "learned_clip": learned_clip,
        "train_mean": float(train["PA"].mean()),
        "model": final,
    }


# ---------------------------------------------------------------------------
# Team-rate machinery (verbatim from tbf_nonoracle, pure functions)
# ---------------------------------------------------------------------------


def build_rate_tables(batting: pl.DataFrame) -> dict:
    team_day = (
        batting.group_by(["team", "game_date"])
        .agg(pl.col("so").sum(), pl.col("pa").sum())
        .sort(["team", "game_date"])
    )
    team_hand_day = (
        batting.drop_nulls("hand_faced")
        .group_by(["team", "hand_faced", "game_date"])
        .agg(pl.col("so").sum(), pl.col("pa").sum())
        .sort(["team", "hand_faced", "game_date"])
    )
    league_day = (
        batting.group_by("game_date")
        .agg(pl.col("so").sum(), pl.col("pa").sum())
        .sort("game_date")
    )
    return {"team_day": team_day, "team_hand_day": team_hand_day,
            "league_day": league_day}


def _cum_lookup(table: pl.DataFrame, key_cols: list, key_vals: tuple,
                as_of) -> tuple[float, int, int] | None:
    sub = table
    for col, val in zip(key_cols, key_vals):
        sub = sub.filter(pl.col(col) == val)
    if sub.is_empty():
        return None
    sub = sub.with_columns(
        pl.col("so").cum_sum().alias("so_cum"),
        pl.col("pa").cum_sum().alias("pa_cum"),
    ).filter(pl.col("game_date") < as_of)
    if sub.is_empty():
        return None
    last = sub.tail(1)
    return (int(last["so_cum"][0]), int(last["pa_cum"][0]))


def _as_date(v):
    if hasattr(v, "year"):
        return v
    import datetime

    return datetime.date.fromisoformat(str(v)[:10])


def team_rate(tables_cur: dict, tables_prior: dict | None,
              opponent_team: str, as_of, pitcher_hand: str | None,
              prior_team_rates: dict,
              league_prior: float | None,
              cur_year: int = 2023, prior_year: int = 2022) -> dict:
    as_of = _as_date(as_of)
    hand_variant = pitcher_hand is not None
    preferred = ("team_hand_%d_prior" % cur_year if hand_variant
                 else "team_%d_prior" % cur_year)
    chains = []
    if hand_variant:
        chains.append(("team_hand_%d_prior" % cur_year,
                       (tables_cur, "team_hand_day", ["team", "hand_faced"],
                        (opponent_team, pitcher_hand)), None))
        prior_hand = (prior_team_rates.get(opponent_team, {})
                      .get("vs_hand", {}).get(pitcher_hand))
        if prior_hand is not None:
            chains.append(("team_hand_%d" % prior_year, None, prior_hand))
    else:
        chains.append(("team_%d_prior" % cur_year,
                       (tables_cur, "team_day", ["team"],
                        (opponent_team,)), None))
        prior = (prior_team_rates.get(opponent_team, {}) or {}).get("std")
        if prior is not None:
            chains.append(("team_%d" % prior_year, None, prior))
    if tables_cur is not None:
        chains.append(("league_%d_prior" % cur_year,
                       (tables_cur, "league_day", [], ()), None))
    if league_prior is not None:
        chains.append(("league_%d" % prior_year, None, league_prior))

    for name, lookup, fixed in chains:
        if lookup is not None:
            tables, table_name, key_cols, key_vals = lookup
            got = _cum_lookup(tables[table_name], key_cols, key_vals, as_of)
            if got is None:
                continue
            so, pa = got
            if pa <= 0:
                continue
            return {
                "rate": so / pa,
                "rate_source": name,
                "rate_numerator": so,
                "rate_denominator": pa,
                "rate_as_of_date": str(as_of),
                "used_fallback": name != preferred,
                "hand_variant": hand_variant,
                "hand_unknown": not hand_variant,
            }
        if fixed is not None:
            return {
                "rate": float(fixed),
                "rate_source": name,
                "rate_numerator": None,
                "rate_denominator": None,
                "rate_as_of_date": str(as_of),
                "used_fallback": name != preferred,
                "hand_variant": hand_variant,
                "hand_unknown": not hand_variant,
            }
    raise ValueError(
        "fallback chain exhausted: no approved prior-season league source"
    )


def build_team_rate_features(starts: pl.DataFrame,
                             batting_current: pl.DataFrame,
                             batting_prior: pl.DataFrame | None,
                             cur_year: int = 2023,
                             prior_year: int = 2022) -> pl.DataFrame:
    tables_cur = build_rate_tables(batting_current)
    tables_prior = (
        build_rate_tables(batting_prior) if batting_prior is not None
        else None
    )
    prior_rates, league_prior = (
        prior_season_rates(batting_prior) if batting_prior is not None
        else ({}, None)
    )
    std_cols, hand_cols = [], []
    for row in starts.iter_rows(named=True):
        r_std = team_rate(tables_cur, tables_prior, row["opponent_team"],
                          row["game_date"], None, prior_rates, league_prior,
                          cur_year, prior_year)
        r_hand = team_rate(tables_cur, tables_prior, row["opponent_team"],
                           row["game_date"], row["pitcher_hand"],
                           prior_rates, league_prior, cur_year, prior_year)
        std_cols.append(r_std)
        hand_cols.append(r_hand)
    return starts.with_columns([
        pl.Series("opp_team_k_rate_std", [r["rate"] for r in std_cols]),
        pl.Series("opp_team_k_rate_vs_hand", [r["rate"] for r in hand_cols]),
        pl.Series("rate_std_source", [r["rate_source"] for r in std_cols]),
        pl.Series("rate_hand_source", [r["rate_source"] for r in hand_cols]),
        pl.Series("rate_std_numerator", [r["rate_numerator"] for r in std_cols],
                  dtype=pl.Int64),
        pl.Series("rate_std_denominator",
                  [r["rate_denominator"] for r in std_cols], dtype=pl.Int64),
        pl.Series("rate_as_of_date", [r["rate_as_of_date"] for r in std_cols]),
        pl.Series("rate_std_used_fallback",
                  [r["used_fallback"] for r in std_cols]),
        pl.Series("rate_hand_unknown", [r["hand_unknown"] for r in hand_cols]),
    ])


def prior_season_rates(batting_prior: pl.DataFrame) -> tuple[dict, float]:
    league = float(
        batting_prior.select(
            pl.col("so").sum() / pl.col("pa").sum()
        ).item()
    )
    std = (
        batting_prior.group_by("team")
        .agg(pl.col("so").sum(), pl.col("pa").sum())
        .with_columns((pl.col("so") / pl.col("pa")).alias("rate"))
    )
    hand = (
        batting_prior.drop_nulls("hand_faced")
        .group_by(["team", "hand_faced"])
        .agg(pl.col("so").sum(), pl.col("pa").sum())
        .with_columns((pl.col("so") / pl.col("pa")).alias("rate"))
    )
    rates: dict = {
        row["team"]: {"std": float(row["rate"]), "vs_hand": {}}
        for row in std.iter_rows(named=True)
    }
    for row in hand.iter_rows(named=True):
        entry = rates.setdefault(row["team"], {"std": league, "vs_hand": {}})
        entry["vs_hand"][row["hand_faced"]] = float(row["rate"])
    return rates, league


def build_batting_rows(savant: pl.DataFrame) -> pl.DataFrame:
    from Python.statcast import NON_PA_EVENTS, STRIKEOUT_EVENTS

    return (
        savant.filter(
            pl.col("events").is_not_null()
            & ~pl.col("events").is_in(list(NON_PA_EVENTS))
        )
        .select([
            pl.col("home_team"),
            pl.col("away_team"),
            pl.col("game_date"),
            pl.col("inning_topbot"),
            pl.col("p_throws").alias("hand_faced"),
            pl.col("events").is_in(list(STRIKEOUT_EVENTS))
            .cast(pl.Int64).alias("so"),
            pl.lit(1, dtype=pl.Int64).alias("pa"),
        ])
        .with_columns(
            pl.when(pl.col("inning_topbot") == "Top")
            .then(pl.col("away_team"))
            .otherwise(pl.col("home_team"))
            .alias("team")
        )
        .select(["team", "game_date", "so", "pa", "hand_faced"])
    )


# ---------------------------------------------------------------------------
# Metrics, inference, kill rules (verbatim from tbf_nonoracle)
# ---------------------------------------------------------------------------


def evaluate_arm(y: np.ndarray, pred: np.ndarray) -> dict:
    return {
        "mae": float(np.mean(np.abs(y - pred))),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "bias": float(np.mean(pred - y)),
    }


def cluster_bootstrap(diffs: np.ndarray, cluster_ids: np.ndarray,
                      n_boot: int = BOOTSTRAP_RESAMPLES,
                      seed: int = BOOTSTRAP_SEED) -> dict:
    diffs = np.asarray(diffs, dtype=float)
    cluster_ids = np.asarray(cluster_ids)
    unique = np.unique(cluster_ids)
    by_cluster = [diffs[cluster_ids == c] for c in unique]
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(unique), len(unique))
        stats[b] = np.concatenate(
            [by_cluster[i] for i in pick]
        ).mean()
    return {
        "estimate": float(diffs.mean()),
        "lo95": float(np.percentile(stats, 2.5)),
        "hi95": float(np.percentile(stats, 97.5)),
        "n_rows": int(len(diffs)),
        "n_clusters": int(len(unique)),
        "n_boot": int(n_boot),
        "seed": int(seed),
    }


def assert_unique_predictions(frame: pl.DataFrame,
                              keys=("origin", "game_pk", "pitcher")) -> None:
    dups = (
        frame.group_by(list(keys)).len().filter(pl.col("len") > 1)
    )
    if dups.height > 0:
        raise ValueError("row pairing violated: %d duplicate keys"
                         % dups.height)


def assert_finite_predictions(pred: np.ndarray) -> None:
    if not np.isfinite(np.asarray(pred, dtype=float)).all():
        raise ValueError("nonfinite predictions produced")


def evaluate_kill_rules(
    origin_mae_challenger: dict,
    origin_mae_teamrate: dict,
    pooled_paired_mae_gap_vs_oracle: float | str = "NOT_COMPUTED",
    tail_paired_diff_pa_lt9: float | None = None,
) -> dict:
    origins = sorted(set(origin_mae_challenger) & set(origin_mae_teamrate))
    losses = [
        o for o in origins
        if origin_mae_challenger[o] >= origin_mae_teamrate[o]
    ]
    if pooled_paired_mae_gap_vs_oracle == "NOT_COMPUTED":
        gap_flag = "NOT_COMPUTED"
        gap_reason = "MATCHED_ORACLE_COMPARATOR_UNAVAILABLE"
        gap_value = None
    else:
        gap_value = float(pooled_paired_mae_gap_vs_oracle)
        gap_flag = gap_value > 0.50
        gap_reason = None
    tail_flag = None
    if tail_paired_diff_pa_lt9 is not None:
        tail_flag = {
            "slice": "PA<9",
            "paired_mae_diff_challenger_minus_comparator":
                float(tail_paired_diff_pa_lt9),
            "interpretation": "positive = challenger worse in slice; "
            "reversal of a pooled improvement; descriptive review flag "
            "only, not an executable kill rule",
        }
    return {
        "origins_compared": origins,
        "origins_lost_to_teamrate_baseline": losses,
        "baseline_kill": len(losses) >= 2,
        "oracle_gap_flag": gap_flag,
        "oracle_gap_reason": gap_reason,
        "pooled_paired_mae_gap_vs_oracle_ablation": gap_value,
        "tail_reversal_review_flag": tail_flag,
        "oracle_role": "no matched oracle ablation in this lane; "
        "historical PA>=9 reconstruction is reference only",
    }


# ---------------------------------------------------------------------------
# Corrected trailing baseline (strict date inequality; disclosed difference
# from the shift(1) version, which admits same-date doubleheader rows)
# ---------------------------------------------------------------------------


def corrected_trailing_baseline(eval_pdf: pd.DataFrame,
                                appearances: pl.DataFrame,
                                train_mean: float) -> tuple[np.ndarray, np.ndarray]:
    """Expanding strictly-prior START-appearance mean (pandas version).

    Same-date rows excluded by strict date inequality (doubleheaders
    excluded); history < 3 starts falls back to the origin train mean.
    """
    app = (
        appearances.filter(pl.col("is_start"))
        .select(pl.col("pitcher"),
                pl.col("game_date").alias("h_date"),
                pl.col("bf").alias("h_bf"))
        .to_pandas()
    )
    app["h_date"] = pd.to_datetime(app["h_date"]).dt.date
    ev = eval_pdf[["game_pk", "pitcher", "game_date"]].copy()
    ev["game_date"] = pd.to_datetime(ev["game_date"]).dt.date
    merged = ev.merge(app, on="pitcher", how="left")
    merged = merged[merged["h_date"].notna()
                    & (merged["h_date"] < merged["game_date"])]
    agg = (
        merged.groupby(["game_pk", "pitcher", "game_date"])
        .agg(trail=("h_bf", "mean"), n_hist=("h_bf", "size"))
        .reset_index()
    )
    out = ev.merge(agg, on=["game_pk", "pitcher", "game_date"], how="left")
    trail = out["trail"].to_numpy(dtype=float)
    n_hist = out["n_hist"].to_numpy(dtype=float)
    fallback = np.isnan(trail) | (n_hist < TRAILING_MIN_HISTORY)
    return np.where(fallback, train_mean, trail), fallback


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _require_temp_out(out_dir: Path) -> None:
    # Operational output gate (not science): system temp always
    # allowed; the task-authorized research root is allowed because the
    # owner order names the exact run directory beneath it. Deviation
    # from the temp-only convention is recorded in the manifest.
    temp = Path(tempfile.gettempdir()).resolve()
    research = Path("C:/Users/ckaplinger/MLB-Props-Research").resolve()
    resolved = out_dir.resolve()
    under_temp = temp in resolved.parents or resolved == temp
    under_research = research in resolved.parents or resolved == research
    if not (under_temp or under_research):
        raise SystemExit(
            "BLOCKED: outputs are authorized only under the system temp "
            "directory or the task-authorized research root; refusing %s"
            % resolved
        )


def default_sources(data_root: Path | None = None,
                    forecast_season: int = 2023,
                    history_seasons: tuple[int, ...] = (2022,),
                    season_shas: dict[int, str] | None = None) -> dict:
    root = Path(data_root) if data_root else REPO / "data"
    season_shas = dict(season_shas or {})
    sources: dict = {}

    def entry(year: int, role: str) -> dict:
        sha = season_shas.get(year, SEASON_SHA_KNOWN.get(year))
        return {
            "path": root / "Savant-Data" / "regular" / str(year)
            / ("statcast_%d_regular.parquet" % year),
            "sha256": sha,
            "period": "%d regular season" % year,
            "role": role,
        }

    sources["savant_%d" % forecast_season] = entry(
        forecast_season,
        "target/evaluation source; also current-season team-rate "
        "aggregates (strictly-prior date cutoffs)")
    for year in history_seasons:
        if year == forecast_season:
            continue
        sources["savant_%d" % year] = entry(
            year,
            "historical lookback ONLY: prior-season team/league "
            "fallbacks and pregame histories; no other use")
    return sources


def _parse_season_shas(items: list[str]) -> dict[int, str]:
    """Parse repeatable --season-sha YYYY:hex digest overrides."""
    out: dict[int, str] = {}
    for item in items or []:
        try:
            year_s, digest = item.split(":", 1)
            year = int(year_s)
        except ValueError:
            raise MechanicalFailure(
                "--season-sha must look like YYYY:hex, got %r" % (item,))
        if not digest or any(
                c not in "0123456789abcdefABCDEF" for c in digest):
            raise MechanicalFailure(
                "--season-sha digest must be hex, got %r" % (item,))
        out[year] = digest.lower()
    return out


def verify_and_load(spec: dict) -> pl.DataFrame:
    if spec.get("sha256") is None:
        raise MechanicalFailure(
            "BLOCKED: no approved digest for %s; supply --season-sha "
            "YYYY:hex" % (spec.get("path"),))
    resolved = Path(spec["path"]).resolve()
    if not resolved.is_file():
        raise MechanicalFailure("missing input %s" % (resolved,))
    actual = sha256_file(resolved)
    if actual != spec["sha256"]:
        raise MechanicalFailure(
            "BLOCKED: source hash mismatch for %s (%s): %s"
            % (spec.get("role", "source"), resolved, actual))
    return pl.read_parquet(resolved)


def derive_fallback_2022(savant_2022: pl.DataFrame) -> dict:
    """2022-only fallback constant (frozen section 6).

    Mean BF over the matching 2022 first-pitcher BF>=1 diagnostic
    population. All source dates precede 2023-01-01 by construction
    (caller asserts the 2022 period first).
    """
    keys, quarantine = audit_identity(savant_2022)
    if quarantine:
        raise MechanicalFailure(
            "2022 fallback population has quarantined games: %d"
            % len(quarantine))
    bf, excluded = bf_table_canonical(savant_2022)
    keyed = keys.select(
        pl.col("game_pk"),
        pl.col("forecast_pitcher").alias("pitcher")).join(
        bf, on=["game_pk", "pitcher"], how="left")
    zero_bf = keyed.filter(pl.col("PA").is_null() | (pl.col("PA") < 1))
    retained = keyed.filter(pl.col("PA").is_not_null()
                            & (pl.col("PA") >= 1))
    if retained.height + zero_bf.height != keyed.height:
        raise MechanicalFailure("2022 fallback zero-BF identity failed")
    n = retained.height
    if n == 0:
        raise MechanicalFailure("2022 fallback population empty")
    total = int(retained["PA"].sum())
    return {"n": n, "bf_sum": total, "mean_bf": total / n,
            "n_quarantined_zero_bf": int(zero_bf.height),
            "n_excluded_non_pa_at_bats": excluded["n_excluded_non_pa"],
            "source_cutoff": "all source observations strictly before "
            "2023-01-01 (2022-only artifact)",
            "mode": "derived_2022",
            "provenance": "derived in-run from the verified 2022-only "
            "artifact"}


def _validate_fallback_inputs(fallback_mean, fallback_source,
                                fallback_cutoff) -> dt.date:
    """Validate caller-supplied fallback triple; return parsed cutoff."""
    if not (fallback_mean == fallback_mean
            and fallback_mean not in (float("inf"), float("-inf"))):
        raise MechanicalFailure("fallback mean must be finite")
    if (not isinstance(fallback_source, str)
            or not fallback_source.strip()):
        raise MechanicalFailure(
            "fallback source must be a nonblank declared string")
    try:
        return dt.date.fromisoformat(fallback_cutoff)
    except (ValueError, TypeError):
        raise MechanicalFailure(
            "fallback cutoff must be an ISO date, got %r"
            % (fallback_cutoff,))


def _split_origin(assigned: pd.DataFrame, origin: str,
                  train_seasons: tuple[int, ...]) -> tuple:
    """Training partition uses ONLY train-season labels (never the
    forecast season or any other year)."""
    origin_ts = pd.Timestamp(origin)
    train = assigned[
        (assigned["origin"].isna())
        & (assigned["game_date"] < origin_ts)
        & (assigned["season_tag"].isin(train_seasons))
    ]
    ev = assigned[assigned["origin"] == origin]
    return train, ev


def _unified_pitches(frames: list[pl.DataFrame]) -> pl.DataFrame:
    """Vertically concatenate pitch frames under a canonical schema.

    Cross-season Savant exports drift in unrelated columns (e.g. a
    metric recorded as Int64 one year and Float64 the next). Only the
    columns this pipeline reads are kept, cast strictly to canonical
    types; anything uncastable or missing fails loud instead of being
    silently coerced.
    """
    schema = {"game_pk": pl.Int64, "pitcher": pl.Int64,
              "game_date": pl.Date, "inning": pl.Int64,
              "inning_topbot": pl.String, "at_bat_number": pl.Int64,
              "pitch_number": pl.Int64, "home_team": pl.String,
              "away_team": pl.String, "p_throws": pl.String,
              "events": pl.String}
    parts = []
    for frame in frames:
        missing = sorted(set(schema) - set(frame.columns))
        if missing:
            raise MechanicalFailure(
                "pitch frame missing columns: %s" % (missing,))
        try:
            parts.append(frame.select(
                [pl.col(c).cast(schema[c], strict=True).alias(c)
                 for c in schema]))
        except Exception as exc:
            raise MechanicalFailure(
                "pitch frame schema not unifiable: %s" % (exc,))
    return pl.concat(parts, how="vertical")


def run_pipeline(sources: dict, out_dir: Path,
                 prereg_path: Path,
                 origins: tuple[str, ...] = ORIGINS_2023,
                 final_date: str = FINAL_EVAL_DATE,
                 forecast_season: int = 2023,
                 history_seasons: tuple[int, ...] = (2022,),
                 train_seasons: tuple[int, ...] | None = None,
                 fallback_mean: float | None = None,
                 fallback_source: str | None = None,
                 fallback_cutoff: str | None = None) -> dict:
    out_dir = Path(out_dir)
    _require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if train_seasons is None:
        train_seasons = (forecast_season,)
    verified: dict = {}
    try:
        # 1. Verify + load every allowlisted input (hash before parse).
        pitches: dict[int, pl.DataFrame] = {}
        for name, spec in sources.items():
            frame = verify_and_load(spec)
            verified[name] = spec["sha256"]
            try:
                year = int(str(name).split("_")[1])
            except (IndexError, ValueError):
                raise MechanicalFailure(
                    "allowlist entry without season year: %s" % name)
            missing = sorted(
                set(PITCH_KEY_COLUMNS) - set(frame.columns))
            if missing:
                raise MechanicalFailure(
                    "%s missing columns: %s" % (name, missing))
            years = sorted(frame_years(frame))
            if years != [year]:
                raise MechanicalFailure(
                    "period violation in %s: years %s (fail-closed)"
                    % (name, years))
            pitches[year] = _unified_pitches([frame])
        if forecast_season not in pitches:
            raise MechanicalFailure(
                "no allowlisted source for forecast season %d"
                % forecast_season)

        # 2. Fallback: derived 2022-only (2023 lane) or caller-supplied
        #    with DECLARED provenance (transfer). Never invented.
        if fallback_mean is None:
            if tuple(sorted(history_seasons)) != (2022,):
                raise MechanicalFailure(
                    "no fallback derivation rule for history %s; "
                    "supply --fallback-mean/--fallback-source/"
                    "--fallback-cutoff" % (history_seasons,))
            if 2022 not in pitches:
                raise MechanicalFailure(
                    "2022 history frame required for fallback derivation")
            derived = derive_fallback_2022(pitches[2022])
            fallback = dict(derived, mode="derived_2022",
                            provenance="derived in-run from verified "
                            "2022-only artifact")
        else:
            for label, value, kind in (
                    ("mean", fallback_mean, "finite float"),
                    ("source", fallback_source, "nonblank string"),
                    ("cutoff", fallback_cutoff, "ISO date string")):
                if value is None:
                    raise MechanicalFailure(
                        "fallback %s required with --fallback-mean "
                        "(got none)" % label)
            cutoff_date = _validate_fallback_inputs(
                fallback_mean, fallback_source, fallback_cutoff)
            fallback = {"mean_bf": float(fallback_mean),
                        "population_mean_source": fallback_source,
                        "source_cutoff": str(cutoff_date),
                        "mode": "declared",
                        "provenance": "DECLARED by caller; not "
                        "independently verified"}

        # 3. Modeling frames per season (train seasons + forecast).
        modeled_years = sorted(set(train_seasons) | {forecast_season})
        for year in modeled_years:
            if year not in pitches:
                raise MechanicalFailure(
                    "no allowlisted source for modeling year %d" % year)
        pool_years = sorted(
            set(history_seasons) | {forecast_season})
        for year in pool_years:
            if year not in pitches:
                raise MechanicalFailure(
                    "no allowlisted source for history year %d" % year)
        if len(pool_years) < 2:
            raise MechanicalFailure(
                "history pool needs at least two seasons")
        first_pool = _unified_pitches(
            [pitches[y] for y in pool_years[:-1]])
        appearances, history_quarantine = build_history_appearances(
            first_pool, pitches[pool_years[-1]])

        per_year = {}
        for year in modeled_years:
            frame = pitches[year]
            keys, quarantine = audit_identity(frame)
            bf, excluded = bf_table_canonical(frame)
            keyed = keys.select(
                pl.col("game_pk"),
                pl.col("forecast_pitcher").alias("pitcher"),
                pl.col("game_date")).join(
                bf, on=["game_pk", "pitcher"], how="left")
            zero_bf = keyed.filter(pl.col("PA").is_null()
                                   | (pl.col("PA") < 1))
            starts = keyed.filter(pl.col("PA").is_not_null()
                                  & (pl.col("PA") >= 1))
            if starts.height + zero_bf.height != keyed.height:
                raise MechanicalFailure(
                    "zero-BF identity failed for %d" % year)
            per_year[year] = {"keys": keys, "quarantine": quarantine,
                              "bf": bf, "excluded": excluded,
                              "zero_bf": zero_bf, "starts": starts}
        if fallback.get("mode") == "declared":
            earliest = min(
                d for y in modeled_years
                for d in per_year[y]["keys"]["game_date"].to_list())
            cutoff = dt.date.fromisoformat(fallback["source_cutoff"])
            if not cutoff < earliest:
                raise MechanicalFailure(
                    "declared source cutoff %s does not precede "
                    "earliest modeled date %s" % (cutoff, earliest))

        # 4. Spine histories for all modeling rows (one builder call).
        forecast_all = pl.concat(
            [per_year[y]["keys"].select(
                pl.col("game_pk"),
                pl.col("forecast_pitcher").alias("pitcher"),
                pl.col("game_date"),
                pl.lit(y, dtype=pl.Int64).alias("season_tag"))
             for y in modeled_years], how="vertical")
        hist_all = ws.build_appearance_history(
            appearances, forecast_all.drop("season_tag"),
            fallback["mean_bf"],
            dt.date(min(pool_years), 1, 1),
            dt.date(max(modeled_years), 12, 31))

        # 5. Team-rate features per modeled year (Savant batting only).
        batting_by_year = {y: build_batting_rows(pitches[y])
                           for y in modeled_years}
        rated_parts = []
        for year in modeled_years:
            earlier = [y for y in modeled_years if y < year]
            earlier += [y for y in history_seasons
                        if y < year and y not in modeled_years]
            if not earlier:
                raise MechanicalFailure(
                    "no complete prior season for %d team rates" % year)
            prior_year = max(earlier)
            prior_batting = pl.concat(
                [batting_by_year[y] for y in modeled_years if y <= prior_year]
                + ([build_batting_rows(pitches[prior_year])]
                   if prior_year not in batting_by_year else []),
                how="vertical")
            fkeys = per_year[year]["keys"]
            game_meta = (
                pitches[year].select("game_pk", "home_team", "away_team")
                .unique(subset=["game_pk"])
            )
            hand = (
                pitches[year].select("game_pk", "pitcher", "p_throws")
                .unique(subset=["game_pk", "pitcher"])
            )
            lineup_free = (
                fkeys.select(
                    pl.col("game_pk"),
                    pl.col("forecast_pitcher").alias("pitcher"),
                    pl.col("game_date"))
                .join(game_meta, on="game_pk", how="left")
                .join(hand, on=["game_pk", "pitcher"], how="left")
                .join(fkeys.select(
                    "game_pk",
                    pl.col("forecast_pitcher").alias("pitcher"),
                    "is_home"),
                    on=["game_pk", "pitcher"], how="left")
                .with_columns(
                    pl.when(pl.col("is_home")).then(pl.col("away_team"))
                    .otherwise(pl.col("home_team")).alias("opponent_team"),
                    pl.col("p_throws").alias("pitcher_hand"))
            )
            rated = build_team_rate_features(
                lineup_free, batting_by_year[year], prior_batting,
                cur_year=year, prior_year=prior_year)
            rated_parts.append(
                rated.select(
                    ["game_pk", "pitcher"] + CHALLENGER_FEATURES[-2:]
                    + ["rate_std_source", "rate_hand_source",
                       "rate_std_used_fallback", "rate_hand_unknown",
                       "rate_as_of_date"])
                .with_columns(pl.lit(year, dtype=pl.Int64).alias(
                    "season_tag")))
        rated_all = pl.concat(rated_parts, how="vertical")

        # 6. Modeling frame: targets + spine features + team rates.
        starts_all = pl.concat(
            [per_year[y]["starts"].with_columns(
                pl.lit(y, dtype=pl.Int64).alias("season_tag"))
             for y in modeled_years], how="vertical")
        frame = (
            starts_all
            .join(hist_all.drop("game_date"), on=["game_pk", "pitcher"],
                  how="left")
            .join(rated_all.drop("rate_as_of_date"),
                  on=["game_pk", "pitcher", "season_tag"], how="left")
        )
        if frame.height != starts_all.height:
            raise MechanicalFailure("feature join dropped rows")
        for col in CHALLENGER_FEATURES:
            if frame[col].null_count() == frame.height:
                raise MechanicalFailure(
                    "feature entirely null: %s" % col)

        # 7. Rolling-origin design (exact frozen boundaries).
        pdf = frame.to_pandas()
        assigned = assign_origins(pdf, origins, final_date)
        train_only = assigned[assigned["role"] == "train_only"]
        _ = train_only
        per_start = []
        per_origin = {}
        blocked = None
        for origin in origins:
            train, ev = _split_origin(assigned, origin, train_seasons)
            if len(ev) == 0:
                raise MechanicalFailure(
                    "no evaluation rows for origin %s" % origin)
            fit_ch = fit_origin(train, list(CHALLENGER_FEATURES))
            fit_tr = fit_origin(train, list(TEAMRATE_FEATURES))
            if fit_ch["status"] != "OK" or fit_tr["status"] != "OK":
                blocked = {"origin": origin,
                           "reason": "inner chronological split "
                           "not formable"}
                break
            per_origin[origin] = _evaluate_origin(
                origin, ev, fit_ch, fit_tr, train, appearances,
                per_start)
        pooled = _pool(per_start, per_origin)
        kill = _kill_rules(per_origin, pooled)
        quarantined = any(len(per_year[y]["quarantine"]) for y in modeled_years)
        if blocked:
            overall, code = "BLOCKED", 1
        elif quarantined or history_quarantine:
            overall, code = "INCOMPLETE", 2
        else:
            overall, code = "COMPLETE", 0
        pop = {
            year: {
                "n_raw": int(per_year[year]["keys"].height),
                "n_retained": int(
                    per_year[year]["starts"].height),
                "n_zero": int(per_year[year]["zero_bf"].height),
                "n_terminal": int(
                    per_year[year]["excluded"]["n_terminal_at_bats"]),
                "n_excluded": int(
                    per_year[year]["excluded"]["n_excluded_non_pa"]),
                "quarantine": per_year[year]["quarantine"],
            } for year in modeled_years
        }
        manifest = _manifest(
            sources, verified, fallback,
            {"forecast_season": forecast_season,
             "history_seasons": list(history_seasons),
             "train_seasons": list(train_seasons),
             "origins": list(origins), "final_date": final_date},
            pop, history_quarantine, per_origin, pooled,
            kill, blocked, overall, per_start, prereg_path)
        _write_manifest(manifest, out_dir)
        _write_outputs(manifest, per_start, pooled, out_dir)
        return manifest, code
    except Exception as exc:  # noqa: BLE001 - receipt then re-raise
        receipt = {
            "status": "MECHANICAL_FAILURE",
            "stage": "run_pipeline",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc(),
            "sources_verified_before_failure": verified,
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "failed_run_policy": "output directory and receipt retained; "
            "rerun requires owner review (mechanical) or is forbidden "
            "(scientific)",
        }
        (out_dir / "failure_receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="ascii")
        raise


def _evaluate_origin(origin, ev, fit_ch, fit_tr, train, appearances,
                     per_start) -> dict:
    y = ev["PA"].to_numpy(dtype=float)
    pred_ch = np.clip(fit_ch["model"].predict(ev[CHALLENGER_FEATURES]),
                      0.0, fit_ch["learned_clip"])
    pred_tr = np.clip(fit_tr["model"].predict(ev[TEAMRATE_FEATURES]),
                      0.0, fit_tr["learned_clip"])
    for arr in (pred_ch, pred_tr):
        assert_finite_predictions(arr)
    train_mean = float(train["PA"].mean())
    pdf = ev.reset_index(drop=True)
    trail, trail_fb = corrected_trailing_baseline(pdf, appearances,
                                                  train_mean)
    rows = pd.DataFrame({
        "origin": origin,
        "season": pdf["season_tag"].to_numpy(),
        "game_pk": pdf["game_pk"].to_numpy(),
        "pitcher": pdf["pitcher"].to_numpy(),
        "game_date": pdf["game_date"].to_numpy(),
        "PA": y,
        "pred_challenger": pred_ch,
        "pred_trailing": trail,
        "pred_train_mean": np.full(len(y), train_mean),
        "pred_teamrate": pred_tr,
        "trailing_fallback": trail_fb,
        "spine_fallback": pdf["no_prior_start_fallback"].to_numpy(),
        "n_prior_all": pdf["n_prior_all_seasons"].to_numpy(),
        "spine_label": pdf["label"].to_numpy(),
    })
    per_start.append(rows)
    return {
        "n_eval": int(len(y)),
        "n_trailing_fallback": int(trail_fb.sum()),
        "n_spine_fallback": int(pdf["no_prior_start_fallback"].sum()),
        "challenger": evaluate_arm(y, pred_ch),
        "trailing_baseline": evaluate_arm(y, trail),
        "train_mean_baseline": evaluate_arm(y, np.full(len(y), train_mean)),
        "teamrate": evaluate_arm(y, pred_tr),
    }


ARMS = ("challenger", "trailing", "train_mean", "teamrate")
PRED_COLS = {"challenger": "pred_challenger", "trailing": "pred_trailing",
             "train_mean": "pred_train_mean", "teamrate": "pred_teamrate"}


def _slice_masks(all_rows: pd.DataFrame) -> dict[str, pd.Series]:
    y = all_rows["PA"].to_numpy(dtype=float)
    month = pd.to_datetime(all_rows["game_date"]).dt.strftime("%Y-%m")
    n_prior = all_rows["n_prior_all"].to_numpy()
    masks: dict[str, pd.Series] = {
        "bf_lt9": all_rows["PA"] < 9,
        "bf_le6": all_rows["PA"] <= 6,
        "bf_7_8": (all_rows["PA"] >= 7) & (all_rows["PA"] <= 8),
        "bf_ge9": all_rows["PA"] >= 9,
        "exp_debut": n_prior == 0,
        "exp_lt10": (n_prior >= 1) & (n_prior < 10),
        "exp_ge10": n_prior >= 10,
        "history_missing": n_prior == 0,
        "fallback_any": (all_rows["trailing_fallback"].to_numpy()
                         | all_rows["spine_fallback"].to_numpy()),
    }
    for m in sorted(month.unique()):
        masks["month_%s" % m] = month == m
    for o in sorted(all_rows["origin"].unique()):
        masks["origin_%s" % o] = all_rows["origin"] == o
    for s in sorted(all_rows["season"].unique()):
        masks["season_%s" % s] = all_rows["season"] == s
    return masks


def _pool(per_start, per_origin) -> dict:
    if not per_start:
        return {"pooled": False, "reason": "no evaluation rows"}
    all_rows = pd.concat(per_start, ignore_index=True)
    assert_unique_predictions(pl.from_pandas(all_rows))
    y = all_rows["PA"].to_numpy(dtype=float)
    pooled: dict = {
        "pooled": True,
        "n_eval": int(len(y)),
        "n_unique_dates": int(all_rows["game_date"].nunique()),
        "n_unique_pitchers": int(all_rows["pitcher"].nunique()),
        "row_pairing_verified": True,
    }
    for arm in ARMS:
        pooled[arm] = evaluate_arm(y, all_rows[PRED_COLS[arm]].to_numpy())
    dates = all_rows["game_date"].astype(str).to_numpy()
    pitchers = all_rows["pitcher"].to_numpy()
    pooled["paired"] = {}
    for comp, base in (("challenger_vs_trailing", "trailing"),
                       ("challenger_vs_teamrate", "teamrate"),
                       ("challenger_vs_trainmean", "train_mean")):
        d = (np.abs(y - all_rows["pred_challenger"].to_numpy())
             - np.abs(y - all_rows[PRED_COLS[base]].to_numpy()))
        pooled["paired"][comp] = {
            "comparison_id": "corrected_ridge_v1__vs__%s_v1" % base,
            "slate_date_primary": cluster_bootstrap(d, dates),
            "pitcher_sensitivity": cluster_bootstrap(d, pitchers),
        }
    pooled["slices"] = []
    for name, mask in _slice_masks(all_rows).items():
        sub = all_rows[mask]
        entry: dict = {"slice": name, "n": int(len(sub))}
        for arm in ARMS:
            if len(sub):
                entry[arm] = evaluate_arm(
                    sub["PA"].to_numpy(dtype=float),
                    sub[PRED_COLS[arm]].to_numpy())
            else:
                entry[arm] = {"mae": None, "rmse": None, "bias": None}
        pooled["slices"].append(entry)
    tail = all_rows[all_rows["PA"] < 9]
    if len(tail):
        yt = tail["PA"].to_numpy(dtype=float)
        pooled["tail_paired_diff_lt9_vs_teamrate"] = float(
            (np.abs(yt - tail["pred_challenger"].to_numpy())
             - np.abs(yt - tail["pred_teamrate"].to_numpy())).mean())
        pooled["n_slice_lt9"] = int(len(tail))
    else:
        pooled["tail_paired_diff_lt9_vs_teamrate"] = None
        pooled["n_slice_lt9"] = 0
    return pooled


def _kill_rules(per_origin, pooled) -> dict:
    mae_ch = {o: m["challenger"]["mae"] for o, m in per_origin.items()}
    mae_tr = {o: m["teamrate"]["mae"] for o, m in per_origin.items()}
    if pooled.get("pooled"):
        tail = pooled.get("tail_paired_diff_lt9_vs_teamrate")
    else:
        tail = None
    return evaluate_kill_rules(mae_ch, mae_tr, "NOT_COMPUTED", tail)


def _manifest(sources, verified, fallback, seasons, pop,
              history_quarantine, per_origin,
              pooled, kill, blocked, overall, per_start, prereg_path) -> dict:
    n_all = int(sum(v["n_raw"] for v in pop.values()))
    return {
        "lane": "corrected_history_workload_2023",
        "preregistration": str(prereg_path),
        "preregistration_sha256": sha256_file(prereg_path),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "dependency_hashes": {
            # Preserved external files (distribution-spec worktree): hash
            # when locally available; on machines without the preserved
            # worktree (e.g. CI checkouts) record their status honestly.
            "tbf_reconstruct.py": _hash_external(
                Path("C:/Users/ckaplinger/Downloads/Personal-Projects/"
                     "MLB-Props-worktrees/distribution-spec/research/"
                     "offseason_2026/tbf_reconstruct.py")),
            "tbf_nonoracle.py": _hash_external(
                Path("C:/Users/ckaplinger/Downloads/Personal-Projects/"
                     "MLB-Props-worktrees/distribution-spec/research/"
                     "offseason_2026/tbf_nonoracle.py")),
            "workload_spine.py": sha256_file(Path(ws.__file__)),
            "run_reconstruction_audit_2023.py": sha256_file(
                Path(sys.modules[
                    "run_reconstruction_audit_2023"].__file__)),
            "statcast.py": sha256_file(
                REPO / "src" / "Python" / "statcast.py"),
        },
        "status": overall,
        "blocked_reason": blocked,
        "independent_validation": "NOT PASSED (no approved BF reference; "
        "reference-free runs are diagnostic only)",
        "descriptive_only": True,
        "promotion_eligible": False,
        "ineligibility_reason": INELIGIBLE_REASON,
        "error_sign_convention": ERROR_SIGN_CONVENTION,
        "model_ids": {
            "challenger": "corrected_ridge_v1 (spine histories + "
            "team rates; same Ridge config as nonoracle_allbf_v1)",
            "trailing": "corrected trailing expanding mean "
            "(strictly-prior START appearances, min 3)",
            "train_mean": "origin training-partition mean",
            "teamrate": "nonoracle_teamrate_v1 (same machinery)",
            "oracle_ablation": "NOT_COMPUTED "
            "(MATCHED_ORACLE_COMPARATOR_UNAVAILABLE)",
            "historical_reference": "Run 1 nonoracle Ridge MAE 3.518 "
            "reported SEPARATELY; different histories, not a paired "
            "comparison",
        },
        "labels": {
            "availability": "unverified (retrospective actual first "
            "pitcher, not pregame announcement)",
            "role": "unverified (no opener vs early-hook inference)",
            "lineup_mode": "NOT_USED (no lineup evidence)",
            "hand_source": "realized game record p_throws; NOT a "
            "timestamped pregame record (limitation preserved)",
        },
        "source_allowlist": {
            name: {"path": str(Path(spec["path"]).resolve()),
                   "sha256_expected": spec["sha256"],
                   "sha256_verified": verified.get(name),
                   "period": spec["period"], "role": spec["role"]}
            for name, spec in sources.items()
        },
        "fallback": fallback,
        "seasons": seasons,
        "population": {
            "n_raw_first_pitchers": n_all,
            "by_season": {
                str(year): {
                    "n_raw": v["n_raw"],
                    "n_retained_bf_ge_1": v["n_retained"],
                    "n_zero_bf": v["n_zero"],
                    "zero_bf_identity": "raw = retained_bf_ge_1 + "
                    "quarantined_zero_bf",
                    "n_terminal_at_bats": v["n_terminal"],
                    "n_excluded_non_pa_at_bats": v["n_excluded"],
                    "n_quarantined_games": len(v["quarantine"]),
                    "quarantine": v["quarantine"],
                } for year, v in pop.items()
            },
            "n_history_quarantined_games": len(history_quarantine),
            "history_quarantine": history_quarantine,
        },
        "origins": {
            o: {"n_eval": m["n_eval"],
                "n_trailing_fallback": m["n_trailing_fallback"],
                "n_spine_fallback": m["n_spine_fallback"],
                "challenger": m["challenger"],
                "trailing_baseline": m["trailing_baseline"],
                "train_mean_baseline": m["train_mean_baseline"],
                "teamrate": m["teamrate"]}
            for o, m in per_origin.items()
        },
        "pooled": pooled,
        "kill_rules": kill,
        "n_prediction_rows": int(sum(len(r) for r in per_start)),
        "single_run_policy": {
            "mechanical_rerun_requires_owner_review": True,
            "scientific_rerun_forbidden": True,
        },
        "output_policy": {
            "convention": "system temp only (copied Run 1 rule)",
            "deviation": "task order mandates run directory under "
            "C:/Users/ckaplinger/MLB-Props-Research/; accepted as an "
            "operational path rule under owner authorization, no "
            "scientific policy changed; failed temp-only attempt "
            "preserved untouched",
        },
    }


def _write_manifest(manifest, out_dir) -> None:
    path = out_dir / "corrected_history_manifest.json"
    if path.exists():
        raise MechanicalFailure(
            "manifest already exists in output directory; refusing to "
            "overwrite a prior run (single-run policy)")
    path.write_text(json.dumps(manifest, indent=2, default=str),
                    encoding="ascii")


def _write_outputs(manifest, per_start, pooled, out_dir) -> None:
    keep = ["origin", "season", "game_pk", "pitcher", "game_date", "PA",
            "pred_challenger", "pred_trailing", "pred_train_mean",
            "pred_teamrate", "trailing_fallback", "spine_fallback",
            "n_prior_all", "spine_label"]
    if per_start:
        all_rows = pd.concat(per_start, ignore_index=True)
    else:
        all_rows = pd.DataFrame({c: [] for c in keep})
    all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
    mrows = []
    for o, m in manifest["origins"].items():
        for arm in ARMS:
            key = {"challenger": "challenger", "trailing": "trailing_baseline",
                   "train_mean": "train_mean_baseline",
                   "teamrate": "teamrate"}[arm]
            r = {"origin": o, "arm": arm, "n": m["n_eval"]}
            r.update(m[key])
            mrows.append(r)
    if pooled.get("pooled"):
        for arm in ARMS:
            r = {"origin": "pooled", "arm": arm, "n": pooled["n_eval"]}
            r.update(pooled[arm])
            mrows.append(r)
    pd.DataFrame(mrows).to_csv(out_dir / "metrics.csv", index=False)
    prows = []
    if pooled.get("pooled"):
        for comp, vals in pooled["paired"].items():
            for variant in ("slate_date_primary", "pitcher_sensitivity"):
                v = vals[variant]
                prows.append({"comparison": comp, "variant": variant,
                              "estimate": v["estimate"], "lo95": v["lo95"],
                              "hi95": v["hi95"], "n_rows": v["n_rows"],
                              "n_clusters": v["n_clusters"],
                              "n_boot": v["n_boot"], "seed": v["seed"]})
    pd.DataFrame(prows).to_csv(out_dir / "paired_comparisons.csv",
                               index=False)
    srows = []
    if pooled.get("pooled"):
        for s in pooled["slices"]:
            for arm in ARMS:
                m = s[arm]
                srows.append({"slice": s["slice"], "n": s["n"], "arm": arm,
                              "mae": m["mae"], "rmse": m["rmse"],
                              "bias": m["bias"]})
    pd.DataFrame(srows).to_csv(out_dir / "slices.csv", index=False)
    by_season = manifest["population"]["by_season"]
    excl = []
    for year in sorted(by_season):
        excl += [{"kind": "quarantined_game", "season": year,
                  "game_pk": q["game_pk"], "reason": q["reason"]}
                 for q in by_season[year]["quarantine"]]
    excl += [{"kind": "history_quarantined_game", "season": "",
              "game_pk": q["game_pk"], "reason": q["reason"]}
             for q in manifest["population"]["history_quarantine"]]
    pd.DataFrame(excl,
                 columns=["kind", "season", "game_pk", "reason"]).to_csv(
        out_dir / "exclusions.csv", index=False)
    (out_dir / "report.md").write_text(
        _report_text(manifest, pooled), encoding="ascii")
    (out_dir / "next_steps.md").write_text(
        _next_steps_text(manifest, pooled), encoding="ascii")


def _report_text(manifest, pooled) -> str:
    by_season = manifest["population"]["by_season"]
    n_retained = sum(v["n_retained_bf_ge_1"] for v in by_season.values())
    n_zero = sum(v["n_zero_bf"] for v in by_season.values())
    n_excluded = sum(v["n_excluded_non_pa_at_bats"]
                     for v in by_season.values())
    n_quar = sum(v["n_quarantined_games"] for v in by_season.values())
    lines = [
        "# Corrected-history workload diagnostic (one run)",
        "",
        "Status: %s. Development diagnostic only: not season-transfer "
        "validation, not a calibrated distribution, not a promotion, "
        "not betting evidence." % manifest["status"],
        "",
        "## Population",
        "Raw first-pitcher starts: %d; retained BF>=1: %d; zero-BF "
        "quarantined: %d; non-PA at_bats excluded: %d; quarantined "
        "games: %d."
        % (manifest["population"]["n_raw_first_pitchers"],
           n_retained, n_zero, n_excluded, n_quar),
        "Fallback mean BF: %.4f (n=%s, mode=%s, provenance=%s). "
        "Rows with spine fallback are counted per origin, never "
        "hidden."
        % (manifest["fallback"]["mean_bf"],
           manifest["fallback"].get("n", "n/a"),
           manifest["fallback"].get("mode", "unknown"),
           manifest["fallback"].get("provenance", "unknown")),
        "",
        "## Pooled metrics (n=%d)"
        % (pooled.get("n_eval", 0) if pooled.get("pooled") else 0),
    ]
    if pooled.get("pooled"):
        for arm in ("challenger", "trailing", "train_mean", "teamrate"):
            m = pooled[arm]
            lines.append(
                "- %s: MAE %.4f / RMSE %.4f / bias %+.4f"
                % (arm, m["mae"], m["rmse"], m["bias"]))
        for comp, vals in pooled["paired"].items():
            v = vals["slate_date_primary"]
            lines.append(
                "- paired %s: estimate %+.4f, 95%% [%+.4f, %+.4f] "
                "(n=%d, dates=%d; seed %d)" % (
                    comp, v["estimate"], v["lo95"], v["hi95"],
                    v["n_rows"], v["n_clusters"], v["seed"]))
        lines += [
            "",
            "## Kill rules",
            "baseline_kill=%s; lost origins=%s; oracle_gap=%s; tail flag=%s"
            % (manifest["kill_rules"]["baseline_kill"],
               manifest["kill_rules"][
                   "origins_lost_to_teamrate_baseline"],
               manifest["kill_rules"]["oracle_gap_flag"],
               ("SET" if manifest["kill_rules"][
                   "tail_reversal_review_flag"] else "not set")),
            "",
            "## Validity limitations (frozen)",
            "- Retrospective actual first-pitcher identity is NOT "
            "pregame knowability; availability/role UNVERIFIED.",
            "- No lineup evidence used anywhere; hand from realized "
            "game record (limitation preserved).",
            "- Origins %s (final %s): no coverage beyond the listed "
            "windows; retrospective diagnostic only."
            % (manifest["seasons"]["origins"],
               manifest["seasons"].get("final_date", "n/a")),
            "- Reference-free run: independent reconstruction-"
            "validation gate NOT passed by this diagnostic.",
            "- Compares methods on identical rows, not a clean causal "
            "ablation of history repair (legacy rolling trailing "
            "omitted: multi-season opens prohibited).",
        ]
    else:
        lines.append("No pooled evaluation rows: %s"
                     % pooled.get("reason", "unknown"))
    return "\n".join(lines) + "\n"


def _next_steps_text(manifest, pooled) -> str:
    if manifest["status"] != "COMPLETE":
        task = ("Resolve the BLOCKED/mechanical state per the failure "
                "receipt under owner review; no scientific rerun.")
    elif not pooled.get("pooled"):
        task = ("Investigate the empty evaluation set; no model "
                "iteration until rows reconcile.")
    else:
        task = ("Review this diagnostic against the preregistered kill "
                "rules; if the challenger survives, scope the NEXT "
                "preregistered step (early-season origins and season "
                "transfer per the dev spec) under a new authorization. "
                "Do not fit distribution candidates on these outputs.")
    return (
        "# Next step (one task)\n\n%s\n\nExact authorization needed: "
        "owner order naming the task, inputs, and stop conditions; "
        "no execution without it.\n"
        % task)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Corrected-history workload diagnostic (one run; "
                    "needs execution authorization).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--origins", default=",".join(ORIGINS_2023),
                        help="comma-separated origin dates; default is "
                             "the frozen Jul-Sep set")
    parser.add_argument("--final-date", default=FINAL_EVAL_DATE)
    parser.add_argument("--forecast-season", type=int, default=2023)
    parser.add_argument("--history-seasons", default="2022")
    parser.add_argument("--train-seasons", default=None,
                        help="comma-separated label-training seasons; "
                             "default is the forecast season only")
    parser.add_argument("--season-sha", action="append", default=[],
                        help="approved digest as YYYY:hex; repeatable")
    parser.add_argument("--fallback-mean", type=float, default=None)
    parser.add_argument("--fallback-source", default=None)
    parser.add_argument("--fallback-cutoff", default=None)
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    try:
        _require_temp_out(out_dir)
        root = Path(args.data_root) if args.data_root else REPO / "data"
        prereg_path = Path(args.prereg)
        if not prereg_path.is_file():
            raise MechanicalFailure(
                "missing preregistration file: %s" % prereg_path)
        sources = default_sources(
            root, args.forecast_season,
            tuple(int(y) for y in args.history_seasons.split(",") if y),
            _parse_season_shas(args.season_sha))
        origins = tuple(o for o in args.origins.split(",") if o)
        if not origins:
            raise MechanicalFailure("no origins supplied")
        train_seasons = (
            tuple(int(y) for y in args.train_seasons.split(",") if y)
            if args.train_seasons else None)
        manifest, code = run_pipeline(
            sources, out_dir, prereg_path,
            origins=origins, final_date=args.final_date,
            forecast_season=args.forecast_season,
            history_seasons=tuple(
                int(y) for y in args.history_seasons.split(",") if y),
            train_seasons=train_seasons,
            fallback_mean=args.fallback_mean,
            fallback_source=args.fallback_source,
            fallback_cutoff=args.fallback_cutoff)
        print(json.dumps({"status": manifest["status"],
                          "manifest": str(
                              out_dir / "corrected_history_manifest.json")}))
        return code
    except (MechanicalFailure, SystemExit) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
