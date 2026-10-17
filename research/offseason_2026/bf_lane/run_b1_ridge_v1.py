"""bf-lane-v1 B1: Ridge workload challenger - REGISTERED EXECUTION (one pass).

Executes the frozen registration
C:\\Users\\ckaplinger\\MLB-Props-Research\\bf-lane-v1\\b1_registration.json
(sha256 e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d)
EXACTLY ONCE into the write-once run dir
C:\\Users\\ckaplinger\\MLB-Props-Research\\bf-lane-v1\\b1_run_v1\\.

Registered procedure (verbatim from the registration):
- One chronological Ridge workload challenger (alpha 1.0 fixed, NO search,
  NO calibration stage), 5 predeclared strictly-prior features
  (prior_mean_bf, prior_n, lg_mean, rest_days_since_last_start,
  season_progression), StandardScaler fit on base_train ONLY (one scaler
  per fold), career-debut rows (prior_n==0) excluded before fitting and
  from Ridge scoring (B1 forecast = B0 PMF unchanged there).
- Folds verbatim from specs/count-eval-v2-spec/harness/comparison.py BLOCKS:
  dev-scored = block_2024H2 + block_2025H1; block_2024H1 declared 0 cohort
  starts; confirm_2025H2 EXCLUDED-NOT-SCORED; 2026 CLOSED.
- Uncertainty = B0 BASE empirical BF PMF (stored pmf37, unmodified)
  RECENTERED on the Ridge predicted mean: deterministic integer shift
  s = round_half_away(m1 - m0) of the cap-60 extension
  (kcount_combiner.bf_pmf_from_37), dropped mass renormalized, registered
  guard: dropped mass > 0.01 -> recenter_mass_loss_flag (reported, never
  silent); s == 0 -> row unchanged.
- Registered pregame p_bar = frozen scalar shrunk pitcher K rate, w=150
  log5 form (kcount-integration I3b construction; pa-k prior_rates W=150,
  pool = first-pitcher-of-record completed PAs strictly before game_date
  under the pa-k label convention), rebuilt per start, hash-recorded.
  IDENTICAL for both arms (the paired contrast is invariant to it). The
  realized-sequence diagnostic's realized-PA p_bar is NOT reused.
- Count integration: BF PMF -> combine_count (k_max 24) -> count_rps
  (summed convention) + count_logscore + milestone Brier 6/8/10/12.
- Paired slate-date bootstrap 2000, seed 20261001, block-stratified, ONE
  shared draw stream (harness comparison.py slate_date_draws, verbatim);
  predeclared contrast C_b1_ridge_vs_b0_empirical on count-RPS,
  null-centered approximate bootstrap test + Holm at family level 0.05
  (harness null_centered_contrast_test, verbatim); ordinary percentile
  CIs UNADJUSTED.
- Persistence: forecast-row IDs + as-of timestamps, availability states +
  per-row feature values, FULL predictive distributions both arms, observed
  BF (and K), mean bias/MAE/RMSE both arms (per fold + pooled dev),
  calibration (decile reliability + milestone Brier), interval
  coverage/width (P10-P90, P25-P75), count-integration inputs/outputs,
  paired RPS evidence (per-date paired sums + replicate deltas), per-fold
  row-count assertions, write-once chain via track_and_verify
  (compare once -> save -> log MLflow -> verify), sha256 inventory in
  metrics.json.

Hard rules honored: no current/eventual BF in features; no lineup input;
no outcome-dependent availability; short prior outings (1<=prior_n<=9)
preserved and scored; career-debut exclusion decided by strictly-prior
history only; failure preserves partials + error log, no silent retry.

ASCII-only (cp1252 consoles).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import traceback
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

LAKE = Path(r"C:\Users\ckaplinger\MLB-Props-Research")
BF_DIR = LAKE / "bf-workload-v1"
OUT_DIR = LAKE / "bf-lane-v1" / "b1_run_v1"
REPO = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\market-eval-v2"
)
HARNESS = REPO / "research" / "offseason_2026" / "specs" / "count-eval-v2-spec" / "harness"
HELPERS = REPO / "research" / "offseason_2026"
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(HARNESS))

from kcount_combiner import (  # noqa: E402
    KCOUNT_CAP, bf_pmf_from_37, combine_count, count_logscore, count_rps,
    expected_bf, exceedance,
)
import comparison as cmp  # noqa: E402
from track_and_verify import track_and_verify  # noqa: E402

REG_PATH = LAKE / "bf-lane-v1" / "b1_registration.json"
REG_SHA = "e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d"
AUDIT_PATH = LAKE / "bf-lane-v1" / "b0_audit.json"
PA_TABLE_PATH = LAKE / "p1-harness-v2" / "data" / "pa_table.parquet"

W0, W1 = date(2024, 7, 1), date(2025, 12, 31)
PMF_COLS = [f"pmf37_{j}" for j in range(37)]
FEATURES = ["prior_mean_bf", "prior_n", "lg_mean",
            "rest_days_since_last_start", "season_progression"]
RIDGE_ALPHA = 1.0
PBAR_W = 150.0
K_MAX = 24
MILESTONES = (6, 8, 10, 12)
MASS_LOSS_GUARD = 0.01
DEbut = "career_debut_league_pool"

FOLD_DEFS = {
    "block_2024H2": {"train": (date(2023, 1, 1), date(2024, 6, 30)),
                     "assess": (date(2024, 7, 1), date(2024, 12, 31)),
                     "role": "dev-scored"},
    "block_2025H1": {"train": (date(2023, 1, 1), date(2024, 12, 31)),
                     "assess": (date(2025, 1, 1), date(2025, 6, 30)),
                     "role": "dev-scored"},
    "block_2024H1": {"train": (date(2023, 1, 1), date(2023, 12, 31)),
                     "assess": (date(2024, 1, 1), date(2024, 6, 30)),
                     "role": "0 cohort starts (declared empty)"},
    "confirm_2025H2": {"assess": (date(2025, 7, 1), date(2025, 9, 28)),
                       "role": "EXCLUDED - NOT SCORED in dev run"},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a, dtype=np.float64).tobytes()).hexdigest()


def py(o):
    """Recursively convert numpy scalars/arrays to plain python for JSON."""
    if isinstance(o, dict):
        return {str(k): py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [py(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return py(o.tolist())
    if isinstance(o, date):
        return o.isoformat()
    return o


def round_half_away(x: float) -> int:
    """Round-half-away-from-zero (registered deterministic integer shift)."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return -int(math.floor(-x + 0.5))


def recenter_ext(p_ext: np.ndarray, s: int) -> tuple[np.ndarray, float]:
    """Registered recentering: p'[n] = p[n-s] for n=1..60 (0-based
    out[i] = p[i-s]); mass shifted out of range dropped, then renormalized
    to sum 1. Returns (pmf, dropped_mass_before_renorm)."""
    if s == 0:
        return p_ext.copy(), 0.0
    out = np.zeros(KCOUNT_CAP)
    for i in range(KCOUNT_CAP):
        j = i - s
        if 0 <= j < KCOUNT_CAP:
            out[i] = p_ext[j]
    dropped = 1.0 - float(out.sum())
    tot = float(out.sum())
    if tot <= 0:
        raise ValueError("recentering dropped all mass (s=%d)" % s)
    return out / tot, max(0.0, dropped)


def pmf_quantile(p_ext: np.ndarray, tau: float) -> int:
    """Smallest n in 1..60 with CDF >= tau."""
    cdf = np.cumsum(p_ext)
    return int(np.searchsorted(cdf, tau - 1e-12, side="left") + 1)


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def fail(msg: str) -> None:
    raise RuntimeError("B1 RUN ABORT: " + msg)


# ---------------------------------------------------------------------------
# identity gates (fail loud BEFORE any fitting)
# ---------------------------------------------------------------------------

def check_identities() -> dict:
    if OUT_DIR.exists():
        fail("write-once run dir %s already exists; single-run contract "
             "refuses to re-execute" % OUT_DIR)
    got = sha256_file(REG_PATH)
    if got != REG_SHA:
        fail("registration sha256 mismatch: %s != %s" % (got, REG_SHA))
    audit = json.loads(AUDIT_PATH.read_text(encoding="ascii"))
    if not audit["verdict"].startswith("PASS"):
        fail("b0_audit verdict is not PASS")
    reg_hashes = audit["hashes_sha256"]
    inputs = {
        "bf_forecasts.parquet": BF_DIR / "data" / "bf_forecasts.parquet",
        "start_metrics_v2.parquet": BF_DIR / "data" / "start_metrics_v2.parquet",
        "build_bf_forecasts.py": BF_DIR / "scripts" / "build_bf_forecasts.py",
        "kcount_combiner.py": HELPERS / "kcount_combiner.py",
    }
    identities = {"b1_registration.json": got}
    for name, path in inputs.items():
        h = sha256_file(path)
        if h != reg_hashes[name]:
            fail("input hash mismatch for %s: %s != registered %s"
                 % (name, h, reg_hashes[name]))
        identities[name] = h
    identities["pa_table.parquet"] = sha256_file(PA_TABLE_PATH)
    identities["run_b1_ridge_v1.py"] = sha256_file(Path(__file__).resolve())
    return identities


# ---------------------------------------------------------------------------
# strictly-prior verification + feature derivation (builder frame)
# ---------------------------------------------------------------------------

def build_features(bf: pl.DataFrame) -> pl.DataFrame:
    full = bf.sort(["game_date", "game_pk", "side"])
    date_groups = full.partition_by("game_date", as_dict=True)
    pitcher_state: dict[int, dict] = {}
    lg_sum = 0.0
    lg_n = 0
    prior_n_bad = prior_mean_dev = lg_mean_dev = 0.0
    rest_vals: list[int | None] = []
    doy_vals: list[int] = []
    for d in sorted(full["game_date"].unique().to_list()):
        day = date_groups[(d,)]
        for rec in day.iter_rows(named=True):
            st = pitcher_state.get(rec["pitcher"])
            rebuilt_n = st["n"] if st is not None else 0
            if rebuilt_n != rec["prior_n"]:
                prior_n_bad += 1
            if st is not None and st["n"] > 0 and rec["prior_mean"] is not None:
                prior_mean_dev = max(prior_mean_dev,
                                     abs(st["sum"] / st["n"] - rec["prior_mean"]))
            if lg_n > 0 and rec["lg_mean"] is not None:
                lg_mean_dev = max(lg_mean_dev,
                                  abs(lg_sum / lg_n - rec["lg_mean"]))
            rest_vals.append((d - st["last_date"]).days
                             if st is not None else None)
            doy_vals.append(d.timetuple().tm_yday)
        # pools update AFTER all starts of this date (same-date never prior)
        for rec in day.iter_rows(named=True):
            pid = rec["pitcher"]
            st = pitcher_state.get(pid)
            if st is None:
                pitcher_state[pid] = {"n": 1, "sum": float(rec["realized_bf"]),
                                      "last_date": d}
            else:
                st["n"] += 1
                st["sum"] += float(rec["realized_bf"])
                st["last_date"] = d
            lg_sum += float(rec["realized_bf"])
            lg_n += 1
    if prior_n_bad or prior_mean_dev > 1e-12 or lg_mean_dev > 1e-12:
        fail("strictly-prior verification failed: prior_n mismatches=%d, "
             "prior_mean max dev=%g, lg_mean max dev=%g"
             % (prior_n_bad, prior_mean_dev, lg_mean_dev))
    out = full.with_columns([
        pl.Series("rest_days_since_last_start", rest_vals, dtype=pl.Int64),
        pl.Series("season_progression", doy_vals, dtype=pl.Int64),
    ])
    return out, {"prior_n_mismatches": int(prior_n_bad),
                 "prior_mean_max_abs_dev": float(prior_mean_dev),
                 "lg_mean_max_abs_dev": float(lg_mean_dev)}


# ---------------------------------------------------------------------------
# registered p_bar (I3b: w=150 log5 form, first-pitcher PA pools)
# ---------------------------------------------------------------------------

def build_p_bar(bf_feat: pl.DataFrame, cohort: pl.DataFrame) -> pl.DataFrame:
    pa = (pl.read_parquet(PA_TABLE_PATH)
          .filter(pl.col("pitcher_role") == "starter_pa")
          .select("game_pk", "game_date", "pitcher", "y")
          .sort("game_date"))
    pa_dates = pa["game_date"].to_list()
    pa_pids = pa["pitcher"].to_list()
    pa_y = pa["y"].to_list()
    cohort_dates = sorted(cohort["game_date"].unique().to_list())
    state: dict[int, tuple[int, int]] = {}
    lg_k = 0
    lg_n = 0
    ptr = 0
    n = pa.height
    pbar_by_row: dict[tuple, float] = {}
    for d in cohort_dates:
        # pools advance strictly before game_date (same-date never prior)
        while ptr < n and pa_dates[ptr] < d:
            pid, y = pa_pids[ptr], int(pa_y[ptr])
            k0, n0 = state.get(pid, (0, 0))
            state[pid] = (k0 + y, n0 + 1)
            lg_k += y
            lg_n += 1
            ptr += 1
        lg = lg_k / lg_n if lg_n else float("nan")
        lg_safe = lg if lg == lg else 0.2
        day = cohort.filter(pl.col("game_date") == d)
        for rec in day.iter_rows(named=True):
            k0, n0 = state.get(rec["pitcher"], (0, 0))
            p_p = (k0 + PBAR_W * lg_safe) / (n0 + PBAR_W)  # pa-k prior_rates
            # log5 L1 form (league-average batter): collapses to p_p
            p_bar = float(np.clip(_sigmoid(_logit(p_p) + _logit(lg_safe)
                                           - _logit(lg_safe)), 1e-6, 1 - 1e-6))
            pbar_by_row[(rec["game_pk"], rec["side"], rec["pitcher"])] = p_bar
    out = cohort.with_columns(
        pl.Series("p_bar", [pbar_by_row[(r["game_pk"], r["side"], r["pitcher"])]
                            for r in cohort.iter_rows(named=True)],
                  dtype=pl.Float64))
    return out, {"n_pa_pool_rows_first_pitcher": int(n),
                 "pool_span": [pa["game_date"].min().isoformat(),
                               pa["game_date"].max().isoformat()],
                 "pool_note": "first-pitcher-of-record completed PAs "
                 "(pa-k label convention, truncated_pa excluded), strictly "
                 "before game_date, 2022 onward (I3b rate-pool heritage)",
                 "formula": "prior_rates W=150 shrunk pitcher rate, log5 L1 "
                 "form (league-average batter), clip [1e-6, 1-1e-6]"}


# ---------------------------------------------------------------------------
# main scored run (invoked EXACTLY ONCE by track_and_verify)
# ---------------------------------------------------------------------------

def run_compare() -> dict:
    OUT_DIR.mkdir(parents=True)
    (OUT_DIR / "models").mkdir(exist_ok=True)

    bf = pl.read_parquet(BF_DIR / "data" / "bf_forecasts.parquet")
    if bf.height != 14574:
        fail("builder frame rows %d != 14574" % bf.height)
    n26 = bf.filter(pl.col("game_date") >= pl.date(2026, 1, 1)).height
    if n26:
        fail("2026 rows are CLOSED: %d present" % n26)

    bf_feat, prior_check = build_features(bf)

    # cohort + fold row-count assertions
    cohort_full = bf_feat.filter((pl.col("game_date") >= W0)
                                 & (pl.col("game_date") <= W1))
    if cohort_full.height != 7194:
        fail("cohort rows %d != 7194" % cohort_full.height)
    if cohort_full["game_date"].n_unique() != 272:
        fail("cohort slate dates %d != 272" % cohort_full["game_date"].n_unique())
    fold_rows = {}
    for fname, fd in FOLD_DEFS.items():
        a0, a1 = fd["assess"]
        fold_rows[fname] = int(cohort_full.filter(
            (pl.col("game_date") >= a0) & (pl.col("game_date") <= a1)).height)
    if fold_rows["block_2024H1"] != 0:
        fail("block_2024H1 declared 0 cohort starts, found %d"
             % fold_rows["block_2024H1"])
    dev_folds = ["block_2024H2", "block_2025H1"]
    dev_rows = sum(fold_rows[f] for f in dev_folds)
    if dev_rows + fold_rows["confirm_2025H2"] != 7194:
        fail("fold row counts do not partition the cohort: %s" % fold_rows)

    cohort = cohort_full.filter(
        (pl.col("game_date") >= FOLD_DEFS["block_2024H2"]["assess"][0])
        & (pl.col("game_date") <= FOLD_DEFS["block_2025H1"]["assess"][1])
    ).sort(["game_date", "game_pk", "side"])
    if cohort.height != dev_rows:
        fail("dev cohort rows %d != %d" % (cohort.height, dev_rows))

    cohort, pbar_meta = build_p_bar(bf_feat, cohort)
    p_bar_arr = cohort["p_bar"].to_numpy()

    # realized K from the pa-k PA table (identity: game_pk + pitcher)
    pa_all = pl.read_parquet(PA_TABLE_PATH).select(
        "game_pk", "pitcher", "y")
    rk = (pa_all.group_by("game_pk", "pitcher")
          .agg(pl.col("y").sum().alias("realized_k"), pl.len().alias("n_pa")))
    cohort = cohort.join(rk, on=["game_pk", "pitcher"], how="left")
    if cohort["realized_k"].null_count():
        fail("realized-K join misses: %d" % cohort["realized_k"].null_count())
    if int((cohort["n_pa"] != cohort["realized_bf"]).sum()):
        n_bad = int((cohort["n_pa"] != cohort["realized_bf"]).sum())
        fail("PA-count vs realized_bf mismatch on %d rows" % n_bad)

    # ---- per-fold Ridge fit + scoring + recentering + integration --------
    rows: list[dict] = []
    fold_fit_meta: dict[str, dict] = {}
    for fname in dev_folds:
        fd = FOLD_DEFS[fname]
        t0, t1 = fd["train"]
        tr = bf_feat.filter((pl.col("game_date") >= t0)
                            & (pl.col("game_date") <= t1))
        tr_fit = tr.filter(pl.col("prior_n") >= 1)  # career debuts excluded
        Xtr = np.column_stack([
            tr_fit["prior_mean"].to_numpy().astype(float),
            tr_fit["prior_n"].to_numpy().astype(float),
            tr_fit["lg_mean"].to_numpy().astype(float),
            tr_fit["rest_days_since_last_start"].to_numpy().astype(float),
            tr_fit["season_progression"].to_numpy().astype(float),
        ])
        if not np.isfinite(Xtr).all():
            fail("%s: non-finite training features (no imputation registered)"
                 % fname)
        ytr = tr_fit["realized_bf"].to_numpy().astype(float)

        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        import joblib
        scaler = StandardScaler().fit(Xtr)  # base_train ONLY
        ridge = Ridge(alpha=RIDGE_ALPHA, fit_intercept=True).fit(
            scaler.transform(Xtr), ytr)
        joblib.dump({"scaler": scaler, "ridge": ridge,
                     "features": FEATURES, "alpha": RIDGE_ALPHA},
                    OUT_DIR / "models" / ("%s_ridge.joblib" % fname))
        n_train_total = int(tr.height)
        n_train_fit = int(tr_fit.height)

        ev = cohort.filter(
            (pl.col("game_date") >= fd["assess"][0])
            & (pl.col("game_date") <= fd["assess"][1]))
        n_debut = int((ev["prior_n"] == 0).sum())
        ev_ridge = ev.filter(pl.col("prior_n") >= 1)
        if ev_ridge.height + n_debut != ev.height:
            fail("%s: scored/debut rows do not partition eval rows" % fname)
        Xev = np.column_stack([
            ev_ridge["prior_mean"].to_numpy().astype(float),
            ev_ridge["prior_n"].to_numpy().astype(float),
            ev_ridge["lg_mean"].to_numpy().astype(float),
            ev_ridge["rest_days_since_last_start"].to_numpy().astype(float),
            ev_ridge["season_progression"].to_numpy().astype(float),
        ])
        if not np.isfinite(Xev).all():
            fail("%s: non-finite eval features" % fname)
        m1_ridge = np.clip(ridge.predict(scaler.transform(Xev)), 1.0, 60.0)
        m1_map = {(r["game_pk"], r["side"], r["pitcher"]): float(m1_ridge[i])
                  for i, r in enumerate(ev_ridge.iter_rows(named=True))}

        fold_fit_meta[fname] = {
            "base_train_window": [t0.isoformat(), t1.isoformat()],
            "n_base_train_rows": n_train_total,
            "n_ridge_fit_rows": n_train_fit,
            "n_career_debut_excluded_from_fit": n_train_total - n_train_fit,
            "n_assess_rows": int(ev.height),
            "n_ridge_scored_rows": int(ev_ridge.height),
            "n_career_debut_b1_equals_b0": n_debut,
            "scaler": "StandardScaler fit on base_train only",
            "estimator": "sklearn Ridge(alpha=1.0, fit_intercept=True)",
        }

        for rec in ev.iter_rows(named=True):
            key = (rec["game_pk"], rec["side"], rec["pitcher"])
            bf37 = np.array([rec[c] for c in PMF_COLS], dtype=float)
            p_ext = bf_pmf_from_37(bf37)
            m0 = expected_bf(p_ext)
            if rec["prior_n"] == 0:
                state = DEbut
                m1 = m0
                s = 0
                p1_ext = p_ext.copy()
                mass_loss = 0.0
            else:
                state = ("own_distribution" if rec["prior_n"] >= 10
                         else "insufficient_history_league_pool")
                m1 = m1_map[key]
                s = round_half_away(m1 - m0)
                p1_ext, mass_loss = recenter_ext(p_ext, s)
            pk0 = combine_count(p_ext, float(rec["p_bar"]), k_max=K_MAX)
            pk1 = combine_count(p1_ext, float(rec["p_bar"]), k_max=K_MAX)
            k_real = int(rec["realized_k"])
            b0_mean = expected_bf(p1_ext) if s == 0 else expected_bf(p_ext)
            row = {
                "game_pk": rec["game_pk"], "side": rec["side"],
                "pitcher": rec["pitcher"], "game_date": rec["game_date"],
                "forecast_as_of": rec["game_date"],
                "as_of_note": "reconstructed deterministic cutoff "
                              "(game_date); no captured pregame timestamps "
                              "in this 2024-25 lineage",
                "fold": fname, "availability_state": state,
                "prior_n": int(rec["prior_n"]),
                "prior_mean_bf": rec["prior_mean"],
                "lg_mean": rec["lg_mean"],
                "rest_days_since_last_start": rec["rest_days_since_last_start"],
                "season_progression": int(rec["season_progression"]),
                "p_bar": float(rec["p_bar"]),
                "b0_mean": m0, "ridge_mean": m1, "shift_s": s,
                "recenter_mass_loss": mass_loss,
                "recenter_mass_loss_flag": bool(mass_loss > MASS_LOSS_GUARD),
                "b1_mean": expected_bf(p1_ext),
                "realized_bf": int(rec["realized_bf"]),
                "realized_k": k_real,
            }
            for j in range(37):
                row["b0_pmf37_%d" % j] = float(bf37[j])
            for j in range(KCOUNT_CAP):
                row["b1_ext_%d" % j] = float(p1_ext[j])
            for j in range(K_MAX):
                row["b0_count_%d" % j] = float(pk0[j])
                row["b1_count_%d" % j] = float(pk1[j])
            row["b0_rps"] = count_rps(pk0, k_real)
            row["b1_rps"] = count_rps(pk1, k_real)
            row["b0_logscore"] = count_logscore(pk0, k_real)
            row["b1_logscore"] = count_logscore(pk1, k_real)
            for m in MILESTONES:
                row["b0_brier_ge%d" % m] = (
                    exceedance(pk0, m) - (1.0 if k_real >= m else 0.0)) ** 2
                row["b1_brier_ge%d" % m] = (
                    exceedance(pk1, m) - (1.0 if k_real >= m else 0.0)) ** 2
            for arm, p_ext_a in (("b0", p_ext), ("b1", p1_ext)):
                q10 = pmf_quantile(p_ext_a, 0.10)
                q90 = pmf_quantile(p_ext_a, 0.90)
                q25 = pmf_quantile(p_ext_a, 0.25)
                q75 = pmf_quantile(p_ext_a, 0.75)
                row["%s_q10" % arm] = q10
                row["%s_q90" % arm] = q90
                row["%s_q25" % arm] = q25
                row["%s_q75" % arm] = q75
            rows.append(row)

    rdf = pl.DataFrame(rows).sort(["game_date", "game_pk", "side"])
    if rdf.height != dev_rows:
        fail("scored rows %d != dev rows %d" % (rdf.height, dev_rows))
    n_flag = int(rdf["recenter_mass_loss_flag"].sum())
    max_loss = float(rdf["recenter_mass_loss"].max())
    n_shift = int((rdf["shift_s"] != 0).sum())
    rdf.write_parquet(OUT_DIR / "b1_per_row_forecasts.parquet")

    # p_bar hash (registered: hash-recorded)
    pbar_sha = sha256_array(p_bar_arr)

    # per-date paired sums (paired RPS evidence)
    met_cols = ["b0_rps", "b1_rps", "b0_logscore", "b1_logscore"]
    per_date = (rdf.group_by("game_date")
                .agg([pl.len().alias("n")]
                     + [pl.col(c).sum().alias(c) for c in met_cols]
                     + [pl.col("b0_mean").sum().alias("b0_mean_sum"),
                        pl.col("b1_mean").sum().alias("b1_mean_sum"),
                        ((pl.col("b0_mean") - pl.col("realized_bf")) ** 2).sum().alias("b0_se_sum"),
                        ((pl.col("b1_mean") - pl.col("realized_bf")) ** 2).sum().alias("b1_se_sum"),
                        (pl.col("b0_mean") - pl.col("realized_bf")).abs().sum().alias("b0_ae_sum"),
                        (pl.col("b1_mean") - pl.col("realized_bf")).abs().sum().alias("b1_ae_sum")])
                .sort("game_date"))
    per_date.write_csv(OUT_DIR / "b1_per_date_paired_sums.csv")

    # ---- aggregate metrics (per fold + pooled dev) ------------------------
    def agg_block(df: pl.DataFrame) -> dict:
        out = {}
        for arm in ("b0", "b1"):
            mean_col = "%s_mean" % arm
            err = df[mean_col].to_numpy() - df["realized_bf"].to_numpy()
            out[arm] = {
                "n": int(df.height),
                "count_rps": float(df["%s_rps" % arm].mean()),
                "count_logscore": float(df["%s_logscore" % arm].mean()),
                "mean_forecast_bias": float(err.mean()),
                "mean_forecast_mae": float(np.abs(err).mean()),
                "mean_forecast_rmse": float(np.sqrt((err ** 2).mean())),
                **{"brier_ge%d" % m: float(df["%s_brier_ge%d" % (arm, m)].mean())
                   for m in MILESTONES},
            }
            q10, q90 = df["%s_q10" % arm], df["%s_q90" % arm]
            q25, q75 = df["%s_q25" % arm], df["%s_q75" % arm]
            rb = df["realized_bf"]
            out[arm]["coverage_p10_p90"] = float(
                ((rb >= q10) & (rb <= q90)).mean())
            out[arm]["width_p10_p90_mean"] = float((q90 - q10).mean())
            out[arm]["coverage_p25_p75"] = float(
                ((rb >= q25) & (rb <= q75)).mean())
            out[arm]["width_p25_p75_mean"] = float((q75 - q25).mean())
        # secondary reference: the builder's persisted shrunk mean (w=50)
        if "prior_mean_shrunk_w50" in df.columns:
            err_s = (df["prior_mean_shrunk_w50"].to_numpy()
                     - df["realized_bf"].to_numpy())
            m = df["prior_mean_shrunk_w50"].is_not_null()
            out["reference_prior_mean_shrunk_w50"] = {
                "n": int(m.sum()),
                "bias": float(err_s[m.to_numpy()].mean()),
                "mae": float(np.abs(err_s[m.to_numpy()]).mean()),
                "rmse": float(np.sqrt((err_s[m.to_numpy()] ** 2).mean())),
            }
        out["paired_b1_minus_b0"] = {
            "count_rps_delta": float(df["b1_rps"].mean() - df["b0_rps"].mean()),
            "count_logscore_delta": float(df["b1_logscore"].mean()
                                          - df["b0_logscore"].mean()),
            "mae_delta": float(np.abs(df["b1_mean"].to_numpy()
                                      - df["realized_bf"].to_numpy()).mean()
                               - np.abs(df["b0_mean"].to_numpy()
                                        - df["realized_bf"].to_numpy()).mean()),
            "rmse_delta": float(
                np.sqrt(((df["b1_mean"].to_numpy()
                          - df["realized_bf"].to_numpy()) ** 2).mean())
                - np.sqrt(((df["b0_mean"].to_numpy()
                            - df["realized_bf"].to_numpy()) ** 2).mean())),
            "bias_delta": float(
                (df["b1_mean"].to_numpy() - df["realized_bf"].to_numpy()).mean()
                - (df["b0_mean"].to_numpy()
                   - df["realized_bf"].to_numpy()).mean()),
        }
        return out

    aggregate = {"pooled_dev": agg_block(rdf)}
    for fname in dev_folds:
        aggregate[fname] = agg_block(rdf.filter(pl.col("fold") == fname))

    # decile reliability (10 quantile bins on predicted mean, per arm)
    calibration = {}
    for scope, df in [("pooled_dev", rdf)] + [
            (f, rdf.filter(pl.col("fold") == f)) for f in dev_folds]:
        calibration[scope] = {}
        for arm in ("b0", "b1"):
            pm = df["%s_mean" % arm].to_numpy()
            obs = df["realized_bf"].to_numpy()
            edges = np.quantile(pm, np.linspace(0.0, 1.0, 11))
            bins = np.clip(np.digitize(pm, edges[1:-1], right=True), 0, 9)
            dec = []
            for b in range(10):
                m = bins == b
                dec.append({
                    "bin": b, "n": int(m.sum()),
                    "mean_pred": float(pm[m].mean()) if m.any() else None,
                    "mean_obs": float(obs[m].mean()) if m.any() else None,
                })
            calibration[scope][arm] = dec

    # ---- paired slate-date bootstrap (shared stream) ----------------------
    dates = rdf["game_date"].to_list()
    blocks = rdf["fold"].to_list()
    values = {
        "b0_rps": rdf["b0_rps"].to_numpy(),
        "b1_rps": rdf["b1_rps"].to_numpy(),
        "b0_logscore": rdf["b0_logscore"].to_numpy(),
        "b1_logscore": rdf["b1_logscore"].to_numpy(),
        "b0_abs_err": np.abs(rdf["b0_mean"].to_numpy()
                             - rdf["realized_bf"].to_numpy()),
        "b1_abs_err": np.abs(rdf["b1_mean"].to_numpy()
                             - rdf["realized_bf"].to_numpy()),
        "b0_sq_err": (rdf["b0_mean"].to_numpy()
                      - rdf["realized_bf"].to_numpy()) ** 2,
        "b1_sq_err": (rdf["b1_mean"].to_numpy()
                      - rdf["realized_bf"].to_numpy()) ** 2,
        "b0_signed_err": rdf["b0_mean"].to_numpy()
                         - rdf["realized_bf"].to_numpy(),
        "b1_signed_err": rdf["b1_mean"].to_numpy()
                         - rdf["realized_bf"].to_numpy(),
    }
    res = cmp.slate_date_draws(values, dates, blocks,
                               n_boot=cmp.N_BOOT, seed=cmp.SEED_BOOTSTRAP)
    names = list(values)
    idx = {nm: i for i, nm in enumerate(names)}

    boot = {"_meta": {"method": "slate-date, block-stratified, row-weighted "
                      "ratio (num/den); ONE shared draw stream across arms "
                      "and metrics", "n_resamples": int(cmp.N_BOOT),
                      "seed": int(cmp.SEED_BOOTSTRAP), "unit": "game_date"}}
    for nm in names:
        v = res[:, idx[nm]]
        boot[nm] = {"point": float(np.asarray(values[nm]).mean()),
                    "ci95": [float(np.percentile(v, 2.5)),
                             float(np.percentile(v, 97.5))]}
    deltas = {}
    for metric in ("rps", "logscore", "abs_err", "sq_err", "signed_err"):
        d_rep = res[:, idx["b1_" + metric]] - res[:, idx["b0_" + metric]]
        d_obs = float(np.asarray(values["b1_" + metric]).mean()
                      - np.asarray(values["b0_" + metric]).mean())
        rec = {"delta_obs": d_obs,
               "ci95": [float(np.percentile(d_rep, 2.5)),
                        float(np.percentile(d_rep, 97.5))]}
        if metric == "sq_err":
            rec["delta_obs_rmse_scale"] = float(
                np.sqrt(np.asarray(values["b1_sq_err"]).mean())
                - np.sqrt(np.asarray(values["b0_sq_err"]).mean()))
            rec["ci95_rmse_scale"] = [
                float(np.percentile(np.sqrt(res[:, idx["b1_sq_err"]]), 2.5)
                      - np.percentile(np.sqrt(res[:, idx["b0_sq_err"]]), 2.5)),
                float(np.percentile(np.sqrt(res[:, idx["b1_sq_err"]]), 97.5)
                      - np.percentile(np.sqrt(res[:, idx["b0_sq_err"]]), 2.5))]
            rec["note"] = "sq_err deltas are on the MSE scale; rmse_scale " \
                          "entries are differences of bootstrap RMSE " \
                          "replicates (descriptive)"
        deltas[metric] = rec
    boot["paired_deltas_b1_minus_b0"] = deltas
    np.save(OUT_DIR / "b1_bootstrap_replicates.npy", res)

    contrast = cmp.null_centered_contrast_test(
        {"b0_rps": values["b0_rps"], "b1_rps": values["b1_rps"]},
        [("C_b1_ridge_vs_b0_empirical", "b1_rps", "b0_rps")],
        dates, blocks, n_boot=cmp.N_BOOT, seed=cmp.SEED_BOOTSTRAP, res=res)

    # per-row counts vs registration (never silent)
    state_counts = (rdf.group_by("availability_state").len()
                    .sort("availability_state"))
    row_count_assertions = {
        "n_dev_rows": int(rdf.height),
        "n_career_debut_b1_equals_b0": int(
            (rdf["availability_state"] == DEbut).sum()),
        "n_ridge_scored_rows": int(
            (rdf["availability_state"] != DEbut).sum()),
        "registration_full_window_reference": {
            "n_starts": 7194, "own_distribution": 6059,
            "insufficient_history": 966, "career_debut": 169,
            "n_ridge_scored_rows": 7025,
            "note": "registration counts cover the FULL window "
                    "2024-07-01..2025-12-31 incl. the confirm_2025H2 rows "
                    "that are EXCLUDED-NOT-SCORED in this dev run"},
        "state_counts": {r["availability_state"]: int(r["len"])
                         for r in state_counts.iter_rows(named=True)},
    }

    # artifact inventory (sha256)
    inventory = {}
    for p in sorted(OUT_DIR.rglob("*")):
        if p.is_file():
            inventory[str(p.relative_to(OUT_DIR))] = sha256_file(p)

    config = {
        "run_id": "bf-lane-v1-b1_run_v1",
        "registration_id": "bf-lane-v1-b1-ridge-workload-challenger",
        "registration_sha256": REG_SHA,
        "registration_path": str(REG_PATH),
        "challenger": "B1_ridge_workload_v1",
        "ridge_alpha": RIDGE_ALPHA,
        "features": FEATURES,
        "folds_dev_scored": dev_folds,
        "folds_excluded_not_scored": ["confirm_2025H2"],
        "folds_declared_empty": ["block_2024H1"],
        "2026": "CLOSED",
        "uncertainty": "B0 BASE empirical PMF recentered on Ridge mean "
                       "(deterministic integer shift, cap-60 extension, "
                       "mass-loss guard 0.01)",
        "p_bar": pbar_meta,
        "p_bar_sha256": pbar_sha,
        "count_integration": {"k_max": K_MAX, "milestones": list(MILESTONES),
                              "combiner": "kcount_combiner.combine_count"},
        "paired_uncertainty": {"n_boot": int(cmp.N_BOOT),
                               "seed": int(cmp.SEED_BOOTSTRAP),
                               "predeclared_contrasts":
                                   ["C_b1_ridge_vs_b0_empirical on count-RPS"],
                               "test": "null-centered approximate bootstrap, "
                                       "Holm family 0.05; percentile CIs "
                                       "UNADJUSTED"},
        "inputs_sha256": json.loads((OUT_DIR / ".." / "b0_audit.json")
                                    .read_text(encoding="ascii"))["hashes_sha256"]
        | {"pa_table.parquet": sha256_file(PA_TABLE_PATH)},
    }

    result = {
        "config": config,
        "strictly_prior_verification": prior_check,
        "fold_fit_meta": fold_fit_meta,
        "fold_rows": fold_rows,
        "row_count_assertions": row_count_assertions,
        "recenter": {"n_rows_shifted_s_nonzero": n_shift,
                     "n_rows_flagged_mass_loss": n_flag,
                     "max_mass_loss": max_loss,
                     "guard": MASS_LOSS_GUARD,
                     "guard_note": "flagged rows reported, never silently "
                                   "accepted; renormalized regardless"},
        "aggregate": aggregate,
        "calibration_deciles": calibration,
        "bootstrap": boot,
        "contrast": contrast,
        "artifact_inventory_sha256": inventory,
    }
    return py(result)


def describe(result: dict, out_dir, saved=None, extra_params=None):
    cfg = result["config"]
    params = {
        "registration_id": cfg["registration_id"],
        "challenger": cfg["challenger"],
        "ridge_alpha": cfg["ridge_alpha"],
        "features": ",".join(cfg["features"]),
        "folds_dev": ",".join(cfg["folds_dev_scored"]),
        "n_boot": cfg["paired_uncertainty"]["n_boot"],
        "seed": cfg["paired_uncertainty"]["seed"],
        "run_dir": str(OUT_DIR),
    }
    agg = result["aggregate"]["pooled_dev"]
    metrics = {
        "pooled_count_rps_b0": agg["b0"]["count_rps"],
        "pooled_count_rps_b1": agg["b1"]["count_rps"],
        "pooled_count_logscore_b0": agg["b0"]["count_logscore"],
        "pooled_count_logscore_b1": agg["b1"]["count_logscore"],
        "pooled_mae_b0": agg["b0"]["mean_forecast_mae"],
        "pooled_mae_b1": agg["b1"]["mean_forecast_mae"],
        "pooled_rmse_b0": agg["b0"]["mean_forecast_rmse"],
        "pooled_rmse_b1": agg["b1"]["mean_forecast_rmse"],
        "contrast_delta_count_rps": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["delta"],
        "contrast_p_null_centered": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["p_value"],
        "contrast_p_holm": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["p_holm"],
    }
    artifacts = [(saved["config_artifact_path"], "config")]
    return params, metrics, artifacts


def main() -> int:
    identities = check_identities()
    print("identity gates PASS; registration sha256 verified")
    try:
        t = track_and_verify(
            run_compare, OUT_DIR,
            "sqlite:///" + str(LAKE / "mlflow.db"),
            experiment="bf-lane-v1", run_name="b1_ridge_v1",
            describe=describe)
    except Exception as exc:
        err = {"status": "FAILED",
               "written_utc": __import__("datetime").datetime.now(
                   __import__("datetime").timezone.utc).isoformat(),
               "error": "%s: %s" % (type(exc).__name__, exc),
               "traceback": traceback.format_exc(),
               "note": "single run; partials preserved; NO silent retry"}
        log_dir = OUT_DIR if OUT_DIR.exists() else LAKE / "bf-lane-v1"
        (log_dir / "b1_run_v1_error_log.json").write_text(
            json.dumps(err, indent=2), encoding="ascii")
        print("RUN FAILED - partials preserved in %s" % log_dir)
        print(err["error"])
        return 1
    print("track_and_verify:", t["status"], "run_id", t["run_id"])
    print("metrics.json sha256:", t["metrics_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
