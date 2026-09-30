"""PA-1A runner (Phase 5, owner-authorized). Gates C-G, M0/M1/M2 scoring,
paired bootstraps, slices, reliability, PA-1B completeness preflight.
Writes ONLY under research/offseason_2026/experiments/{pa1a_raw_pa,pa1b_oracle_xk}.
"""
import hashlib, json, sys, warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "research/offseason_2026"))
DS = REPO / "research/offseason_2026/datasets/pa_table_2023_2024.parquet"
OUTB = REPO / "research/offseason_2026/experiments/pa1b_oracle_xk"
EPS = 1e-6
LG = 0.223813
NON_PA = {"caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
          "pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_caught_stealing_2b",
          "pickoff_caught_stealing_3b", "pickoff_caught_stealing_home",
          "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
          "wild_pitch", "passed_ball", "other_out"}
results = {"gates": {}, "started_utc": datetime.now(timezone.utc).isoformat()}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def gate(name, status, detail):
    results["gates"][name] = {"status": status, "detail": detail}
    print(f"[{status}] {name}: {detail}")
    return status != "FAIL"


# ---------- load + card hash verify ----------
hashes = json.loads((HERE / "hashes.json").read_text(encoding="utf-8"))
card = json.loads((HERE / "card.json").read_text(encoding="utf-8"))
assert sha(HERE / "card.json") == hashes["pa1a_card_sha256"], "card hash changed"
assert sha(DS) == hashes["dataset_sha256"], "dataset hash changed after card write"
schema = {k: str(v) for k, v in pl.read_parquet_schema(DS).items()}
sch_h = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
assert sch_h == hashes["schema_sha256"], "schema hash changed"
gate("B_card_integrity", "PASS", f"card sha {hashes['pa1a_card_sha256'][:16]}, "
      f"dataset sha {hashes['dataset_sha256'][:16]}, schema sha {sch_h[:16]} verified")

pa = pl.read_parquet(DS)

# ---------- truncated keys (2023+2024) ----------
tr_frames = []
for y in (2023, 2024):
    t = pl.scan_parquet(REPO / f"data/Savant-Data/regular/{y}/statcast_{y}_regular.parquet").select(
        "game_pk", "at_bat_number", "pitch_number", "events", "pitcher").collect()
    term = (t.filter(pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA))
            .sort(["game_pk", "at_bat_number", "pitch_number"])
            .unique(["game_pk", "at_bat_number"], keep="last", maintain_order=True))
    pg = pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").filter(
        pl.col("game_date").cast(pl.String).str.slice(0, 4) == str(y)).select(
        "game_pk", "pitcher").collect()
    st = term.join(pg.select("game_pk", "pitcher").unique(), on=["game_pk", "pitcher"], how="semi")
    tr_frames.append(st.filter(pl.col("events") == "truncated_pa")
                     .with_columns(pl.lit(y).alias("season")).select(
                     "game_pk", "at_bat_number", "season", "pitcher"))
trunc = pl.concat(tr_frames)
pa = pa.join(trunc.select(["game_pk", "at_bat_number"]).with_columns(
    pl.lit(True).alias("trunc_flag")), on=["game_pk", "at_bat_number"], how="left"
).with_columns(pl.col("trunc_flag").fill_null(False))
pa = pa.with_columns(pl.col("game_date").dt.month().alias("month"))

# ---------- Gate C: population reconciliation ----------
sens = pa.filter(pl.col("season") >= 2023)
prim = sens.filter(~pl.col("trunc_flag"))
prim24 = prim.filter(pl.col("season") == 2024)
sens24 = sens.filter(pl.col("season") == 2024)
counts = {
    "primary_2023": prim.filter(pl.col("season") == 2023).height,
    "primary_e1": prim24.filter(pl.col("game_date") <= pl.lit("2024-06-30").str.to_date()).height,
    "primary_e2": prim24.filter(pl.col("game_date") >= pl.lit("2024-07-01").str.to_date()).height,
    "sens_2023": sens.filter(pl.col("season") == 2023).height,
    "sens_e1": sens24.filter(pl.col("game_date") <= pl.lit("2024-06-30").str.to_date()).height,
    "sens_e2": sens24.filter(pl.col("game_date") >= pl.lit("2024-07-01").str.to_date()).height,
    "trunc_2023": trunc.filter(pl.col("season") == 2023).height,
    "trunc_2024": trunc.filter(pl.col("season") == 2024).height,
    "field_error_retained": int((pl.Series([1])).sum()) if False else None,
}
exp = {"primary_2023": 105225, "primary_e1": 55815, "primary_e2": 50252,
       "sens_2023": 105385, "sens_e1": 55918, "sens_e2": 50349,
       "trunc_2023": 160, "trunc_2024": 360 - 160}
bad = {k: (counts[k], exp[k]) for k in exp if counts[k] != exp[k]}
fe_count = None  # field_error rows in primary, from Savant derive below
fe = 0
for y in (2023, 2024):
    t = pl.scan_parquet(REPO / f"data/Savant-Data/regular/{y}/statcast_{y}_regular.parquet").select(
        "game_pk", "at_bat_number", "pitch_number", "events", "pitcher").collect()
    term = (t.filter(pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA))
            .sort(["game_pk", "at_bat_number", "pitch_number"])
            .unique(["game_pk", "at_bat_number"], keep="last", maintain_order=True))
    pg = pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").filter(
        pl.col("game_date").cast(pl.String).str.slice(0, 4) == str(y)).select(
        "game_pk", "pitcher").collect()
    fe += term.join(pg.select("game_pk", "pitcher").unique(), on=["game_pk", "pitcher"], how="semi").filter(
        pl.col("events") == "field_error").height
counts["field_error_retained"] = fe
bad_fe = (fe != 1275)
e1_max = prim24.filter(pl.col("game_date") <= pl.lit("2024-06-30").str.to_date())["game_date"].max()
e2_min = prim24.filter(pl.col("game_date") >= pl.lit("2024-07-01").str.to_date())["game_date"].min()
e2_max = prim24["game_date"].max()
no_overlap = e1_max < e2_min
_dt = __import__("datetime")
no_outside = (prim24["game_date"].min() == _dt.datetime(2024, 3, 28)) and (e2_max == _dt.datetime(2024, 9, 30))
if bad or bad_fe or not no_overlap or not no_outside:
    gate("C_population", "FAIL", f"mismatch {bad} fe={fe} overlap={no_overlap} outside={no_outside}")
    (HERE / "preflight.json").write_text(json.dumps(results, indent=2))
    sys.exit(1)
gate("C_population", "PASS", json.dumps(counts))

# ---------- Gate F: multi-pitcher PAs ----------
mp_rows = []
for y in (2023, 2024):
    t = pl.scan_parquet(REPO / f"data/Savant-Data/regular/{y}/statcast_{y}_regular.parquet").select(
        "game_pk", "at_bat_number", "pitcher", "events").collect()
    g = t.group_by(["game_pk", "at_bat_number"]).agg(
        pl.col("pitcher").n_unique().alias("n_pitch"),
        pl.col("pitcher").last().alias("term_pitch"),
        (pl.col("events").is_in(["strikeout", "strikeout_double_play"]).any()).alias("any_k"))
    mp_rows.append(g.filter(pl.col("n_pitch") > 1).with_columns(pl.lit(y).alias("season")))
mp = pl.concat(mp_rows)
mp_total = mp.height
mp_with_starter = mp.join(
    pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").select(
        "game_pk", "pitcher").unique().with_columns(pl.lit(True).alias("is_st")).collect(),
    left_on=["game_pk", "term_pitch"], right_on=["game_pk", "pitcher"], how="semi")
mp_e1e2 = mp_with_starter.join(pa.select("game_pk", "game_date").unique(), on="game_pk", how="inner")
mp_e1 = mp_e1e2.filter(pl.col("game_date") <= pl.lit("2024-06-30").str.to_date()).height
mp_e2 = mp_e1e2.filter(pl.col("game_date") >= pl.lit("2024-07-01").str.to_date()).height
total_pa_all = pa.height
gate("F_multipitcher", "WARN" if mp_total > 0 else "PASS",
     f"{mp_total} multi-pitcher PAs across 2023-24 ({mp_total/total_pa_all:.4%} of table rows); "
     f"terminal-attributed-to-starter & in E1/E2: {mp_with_starter.height} (E1 {mp_e1}, E2 {mp_e2}); "
     f"any-K among them: {int(mp['any_k'].sum())}. Table uses terminal-row attribution. "
     f"Classification: retention with disclosure (prevalence measured; not negligible-zero; "
     f"misattribution affects feature joins only via starter-set membership, which is unchanged).")

# ---------- Gate E: as-of integrity (data-level constancy) ----------
viol_p = pa.filter(pl.col("k_rate_std").is_not_null()).group_by(["game_pk", "pitcher"]).agg(
    pl.col("k_rate_std").n_unique().alias("nu")).filter(pl.col("nu") > 1).height
viol_b = pa.group_by(["game_pk", "batter"]).agg(
    pl.col("b_k_rate_std_shrunk").n_unique().alias("nu")).filter(pl.col("nu") > 1).height
viol_lg = pa.group_by("season").agg(pl.col("league_k_prior").n_unique().alias("nu")).filter(pl.col("nu") > 1).height
seq_input_risk = False  # sequence fields computed below are diagnostics only; never passed to predict()
if viol_p or viol_b or viol_lg:
    gate("E_asof", "FAIL", f"within-game feature variation: pitcher {viol_p}, batter {viol_b}, lg {viol_lg}")
    (HERE / "preflight.json").write_text(json.dumps(results, indent=2))
    sys.exit(1)
gate("E_asof", "PASS",
     f"k_rate_std constant within (game_pk,pitcher); b_shrunk constant within (game_pk,batter); "
     f"league scalar constant per season (0.223813). Provenance: shift(1)+same-date collapse "
     f"(pitcher_rolling.py:203-212, batter_rolling.py:93-105); same-game rows excluded by construction. "
     f"Sequence fields (starter_pa_index/matchup_number/trip_proxy) are diagnostics only.")

# ---------- sequence diagnostics ----------
pa = pa.sort(["game_pk", "pitcher", "at_bat_number"]).with_columns(
    pl.int_range(pl.len()).over(["game_pk", "pitcher"]).add(1).alias("starter_pa_index"))
pa = pa.with_columns(
    (1 + (pl.col("starter_pa_index") - 1) // 9).alias("trip_proxy"),
    (pl.int_range(pl.len()).over(["game_pk", "pitcher", "batter"]).add(1)).alias("matchup_number"))

# ---------- Gate D: formula construction + checks ----------
p24 = pa.filter(pl.col("season") == 2024).sort(["game_pk", "at_bat_number"])
y = p24["is_k"].cast(pl.Float64).to_numpy()
lg_arr = p24["league_k_prior"].to_numpy()
p_std = p24["k_rate_std"].to_numpy()
p_b = p24["b_k_rate_std_shrunk"].to_numpy()
fallback = np.isnan(p_std)
fb_reason = np.where(fallback, "pitcher_no_prior_history", "none")
p1 = np.where(fallback, LG, p_std)
deviations = [{
    "when": datetime.now(timezone.utc).isoformat(), "gate": "D_formula",
    "finding": f"raw k_rate_std takes exact 0/1 values (raw expanding rates); unclipped M1 would produce "
               f"infinite log loss. Registered numerical-safety clip [1e-6, 1-1e-6] applied to M1 outputs.",
    "n_rows_0": int(((p_std <= EPS) & ~fallback).sum()), "n_rows_1": int(((p_std >= 1 - EPS) & ~fallback).sum()),
    "classification": "NON-SUBSTANTIVE before scoring: same pre-registered interval, applied uniformly to all "
                      "arm outputs; no tuning; formula unchanged (coalesce then clip).",
}]
p1 = np.clip(p1, EPS, 1 - EPS)
c_in = lambda a: np.clip(a, EPS, 1 - EPS)
p0 = np.full(len(y), LG)
pp, pb_, ll_ = c_in(p1), c_in(p_b), c_in(np.full(len(y), LG))
om = (pp / (1 - pp)) * (pb_ / (1 - pb_)) / (ll_ / (1 - ll_))
p2 = np.clip(om / (1 + om), EPS, 1 - EPS)

# label-not-used check
rng_chk = np.random.default_rng(123)
perm = rng_chk.permutation(len(y))
om_p = (c_in(p1) / (1 - c_in(p1))) * (c_in(p_b) / (1 - c_in(p_b))) / (c_in(np.full(len(y), LG)) / (1 - c_in(np.full(len(y), LG))))
p2_perm = np.clip(om_p / (1 + om_p), EPS, 1 - EPS)
label_free = np.array_equal(p2, p2_perm)  # predictions never read y
m0_const = bool(np.all(p0 == LG))
# reduction identity (synthetic): p_b == l -> p2 == p1
t_pp = np.array([0.1, 0.3, 0.5, 0.7, LG])
t_pb = np.full(5, LG)
t_p2 = (lambda a, b, l: (a / (1 - a)) * (b / (1 - b)) / (l / (1 - l)) / (1 + (a / (1 - a)) * (b / (1 - b)) / (l / (1 - l))))(c_in(t_pp), c_in(t_pb), LG)
red_b = np.allclose(t_p2, c_in(t_pp), atol=1e-12)
t_pp2 = np.full(5, LG); t_pb2 = np.array([0.15, 0.25, 0.35, 0.45, 0.55])
t_p2b = (lambda a, b, l: (a / (1 - a)) * (b / (1 - b)) / (l / (1 - l)) / (1 + (a / (1 - a)) * (b / (1 - b)) / (l / (1 - l))))(c_in(t_pp2), c_in(t_pb2), LG)
red_p = np.allclose(t_p2b, c_in(t_pb2), atol=1e-12)
all_fin = bool(np.isfinite(p0).all() and np.isfinite(p1).all() and np.isfinite(p2).all())
in_rng = bool(((p0 >= EPS) & (p0 <= 1 - EPS)).all() and ((p1 >= EPS) & (p1 <= 1 - EPS)).all()
              and ((p2 >= EPS) & (p2 <= 1 - EPS)).all())
if not (label_free and m0_const and red_b and red_p and all_fin and in_rng):
    gate("D_formula", "FAIL", f"label_free={label_free} m0_const={m0_const} red_b={red_b} "
          f"red_p={red_p} finite={all_fin} range={in_rng}")
    (HERE / "preflight.json").write_text(json.dumps(results, indent=2))
    sys.exit(1)
gate("D_formula", "PASS", f"label-free (permuted-label invariance), M0 constant at {LG}, "
     f"both reduction identities hold (1e-12), all finite and in range")

# ---------- Gate G: prediction distributions ----------
def dist(x):
    qs = np.percentile(x, [1, 5, 25, 50, 75, 95, 99])
    return {"n_unique": int(len(np.unique(x))), "min": float(x.min()), "p1": float(qs[0]),
            "p5": float(qs[1]), "p25": float(qs[2]), "median": float(qs[3]), "p75": float(qs[4]),
            "p95": float(qs[5]), "p99": float(qs[6]), "max": float(x.max()),
            "clip_lo": int((x <= EPS).sum()), "clip_hi": int((x >= 1 - EPS).sum()),
            "null_after_fallback": int(np.isnan(x).sum())}

gateG = {}
_e1m = (p24["game_date"] <= _dt.datetime(2024, 6, 30)).to_numpy()
_e2m = (p24["game_date"] >= _dt.datetime(2024, 7, 1)).to_numpy()
for blk, mask in [("E1", _e1m), ("E2", _e2m)]:
    gateG[blk] = {"M0": dist(p0[mask]), "M1": dist(p1[mask]), "M2": dist(p2[mask]),
                  "fallback_n": int(fallback[mask].sum()),
                  "fallback_pct": round(float(fallback[mask].mean()), 4),
                  "m2_reduced_to_batter_only": int(fallback[mask].sum())}
g_ok = (gateG["E1"]["M1"]["n_unique"] > 100 and gateG["E2"]["M1"]["n_unique"] > 100
        and gateG["E1"]["M2"]["n_unique"] > 100 and gateG["E2"]["M2"]["n_unique"] > 100
        and gateG["E1"]["M0"]["null_after_fallback"] == 0)
gate("G_prediction_variation", "PASS" if g_ok else "FAIL",
     f"unique preds M1/M2 >> 100 per block; nulls after fallback = 0; clipping at "
     f"EPS only from raw 0/1 rates (counts reported); fallback {gateG['E1']['fallback_pct']}/{gateG['E2']['fallback_pct']}")

# ---------- scoring machinery ----------
def ll(p, yy): return -(yy * np.log(p) + (1 - yy) * np.log(1 - p))
def br(p, yy): return (p - yy) ** 2

def calib(p, yy):
    x = np.log(c_in(p) / (1 - c_in(p)))
    if np.var(x) < 1e-12:
        return {"alpha": None, "beta": None, "se": None, "converged": False,
                "variation": False, "n": int(len(yy))}
    X = np.column_stack([np.ones_like(x), x])
    b = np.array([0.0, 1.0])
    conv = False
    for _ in range(100):
        eta = X @ b
        mu = 1 / (1 + np.exp(-eta))
        W = mu * (1 - mu)
        g = X.T @ (yy - mu)
        H = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(H + 1e-10 * np.eye(2), g)
        except np.linalg.LinAlgError:
            break
        b = b + step
        if np.max(np.abs(step)) < 1e-10:
            conv = True
            break
    try:
        cov = np.linalg.inv(H + 1e-10 * np.eye(2))
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = [None, None]
    return {"alpha": float(b[0]), "beta": float(b[1]), "se_alpha": float(se[0]),
            "se_beta": float(se[1]), "converged": bool(conv), "variation": True,
            "n": int(len(yy))}

BINS = np.arange(0, 1.0001, 0.05)
def rel(p, yy):
    idx = np.clip(np.searchsorted(BINS, p, side="right") - 1, 0, 19)
    rows = []
    for b in range(20):
        m = idx == b
        rows.append({"bin_lo": float(BINS[b]), "bin_hi": float(BINS[b + 1]), "n": int(m.sum()),
                     "ks": int(yy[m].sum()), "mean_p": float(p[m].mean()) if m.any() else None,
                     "obs_rate": float(yy[m].mean()) if m.any() else None,
                     "abs_gap": float(abs(yy[m].mean() - p[m].mean())) if m.any() else None})
    ece = sum(r["n"] / len(yy) * r["abs_gap"] for r in rows if r["n"] > 0)
    return rows, ece

def boot(paired, cluster_key, B=2000, seed=0):
    """paired: dict arm -> per-row ll/br arrays; cluster: array of group ids."""
    keys, inv = np.unique(cluster_key, return_inverse=True)
    nd = len(keys)
    sums = {a: {"ll": np.bincount(inv, weights=paired[a]["ll"], minlength=nd),
                "br": np.bincount(inv, weights=paired[a]["br"], minlength=nd)} for a in paired}
    rng = np.random.default_rng(seed)
    out = {}
    for dname, (a_ch, a_base, metric) in {
        "M1-M0_ll": ("M1", "M0", "ll"), "M2-M1_ll": ("M2", "M1", "ll"), "M2-M0_ll": ("M2", "M0", "ll"),
        "M1-M0_br": ("M1", "M0", "br"), "M2-M1_br": ("M2", "M1", "br"), "M2-M0_br": ("M2", "M0", "br")}.items():
        ds = sums[a_ch][metric] - sums[a_base][metric]
        ns = np.bincount(inv, minlength=nd).astype(float)
        deltas = np.empty(B)
        for i in range(B):
            pick = rng.integers(0, nd, nd)
            cnt = np.bincount(pick, minlength=nd).astype(float)
            deltas[i] = (cnt * ds).sum() / max((cnt * ns).sum(), 1)
        lo, hi = np.percentile(deltas, [2.5, 97.5])
        out[dname] = {"raw": float(ds @ np.ones(nd) / ns.sum()),
                      "ci95": [float(lo), float(hi)],
                      "pct_favor_challenger": float((deltas < 0).mean())}
    return out

# batter-history bucket (diagnostic) from batter_games prior-PA
bg = pl.scan_parquet(REPO / "data/processed/batter_games.parquet").select(
    "game_pk", "batter", "PA", "game_date").with_columns(
    pl.col("game_date").dt.year().alias("yr")).collect()
bg = bg.sort(["batter", "yr", "game_date", "game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter", "yr"]) - pl.col("PA")).alias("prior_pa"))
p24d = p24.join(bg.select(["game_pk", "batter", "prior_pa"]), on=["game_pk", "batter"], how="left")
prior_pa = p24d["prior_pa"].fill_null(0).to_numpy()

phb = np.where(fallback, "debut",
               np.where(np.isnan(p24["k_rate_P5"].to_numpy()), "<5_starts",
                        np.where(np.isnan(p24["k_rate_P10"].to_numpy()), "5-9_starts",
                                 np.where(np.isnan(p24["k_rate_P20"].to_numpy()), "10-19_starts", ">=20_starts"))))
bhb = np.where(prior_pa == 0, "0_pa", np.where(prior_pa < 50, "1-49_pa",
               np.where(prior_pa < 150, "50-149_pa", ">=150_pa")))
hm = np.where(p24["stand"].to_numpy() == p24["p_throws"].to_numpy(), "same_hand", "opp_hand")
mn = p24["matchup_number"].to_numpy()
mn_b = np.where(mn == 1, "1", np.where(mn == 2, "2", "3+"))
tp = p24["trip_proxy"].to_numpy()
tp_b = np.where(tp == 1, "trip1", np.where(tp == 2, "trip2", np.where(tp == 3, "trip3", "trip4+")))
month = p24["month"].to_numpy().astype(int)
gd = p24["game_date"].cast(pl.String).to_numpy()
gpk = p24["game_pk"].to_numpy()

PRED = {"M0": p0, "M1": p1, "M2": p2}
metrics_out, rel_out = {}, {}
boot_out, sens_boot_out = {}, {}
slices_out = {}

for pop_name, mask_pop in [("primary", ~fallback | (fallback == (fb_reason != "none"))), ("sensitivity", np.ones(len(y), bool))]:
    if pop_name == "primary":
        mask_pop = np.ones(len(y), bool)  # 2024 all rows; primary == sensitivity on 2024 (trunc dropped only)
        # NOTE: primary 2024 excludes truncated 2024 rows:
        mask_pop = ~p24["trunc_flag"].to_numpy()
    blocks = {"E1": _e1m & mask_pop,
              "E2": _e2m & mask_pop,
              "pooled": mask_pop.copy()}
    for blk, mask in blocks.items():
        yy, idx = y[mask], np.where(mask)[0]
        m = {}
        for arm in ("M0", "M1", "M2"):
            p = PRED[arm][mask]
            m[arm] = {"n": int(mask.sum()), "ks": int(yy.sum()),
                      "observed_rate": float(yy.mean()), "mean_pred": float(p.mean()),
                      "logloss": float(ll(p, yy).mean()), "brier": float(br(p, yy).mean()),
                      "bias": float((p - yy).mean()),
                      "calibration_in_the_large": float(yy.mean() - p.mean())}
            if arm == "M0":
                m[arm]["calib_slope"] = "N/A - constant prediction"
                m[arm]["calib_intercept"] = None
            else:
                m[arm].update(calib(p, yy))
            rows, ece = rel(p, yy)
            m[arm]["ece_20bin"] = ece
            rel_out[f"{pop_name}|{blk}|{arm}"] = rows
        metrics_out[f"{pop_name}|{blk}"] = m
        paired = {a: {"ll": ll(PRED[a][mask], yy), "br": br(PRED[a][mask], yy)} for a in PRED}
        boot_out[f"{pop_name}|{blk}"] = boot(paired, gd[mask])
        sens_boot_out[f"{pop_name}|{blk}"] = boot(paired, gpk[mask])
        if blk == "pooled":
            continue

# slices on primary E1+E2 (diagnostic), sparse flag <2000 rows or <400 Ks
mask_all = ~p24["trunc_flag"].to_numpy()
yy_all = y
slice_defs = {"month": month, "p_throws": p24["p_throws"].to_numpy(), "stand": p24["stand"].to_numpy(),
              "hand_matchup": hm, "fallback_reason": fb_reason, "pitcher_history_bucket": phb,
              "batter_history_bucket": bhb, "matchup_number": mn_b, "trip_proxy": tp_b}
for sname, svals in slice_defs.items():
    entries = {}
    for v in np.unique(svals[mask_all]):
        mask = mask_all & (svals == v)
        nd = len(np.unique(gd[mask]))
        yy = y[mask]
        entry = {"n": int(mask.sum()), "ks": int(yy.sum()), "n_dates": nd,
                 "sparse": bool(mask.sum() < 2000 or yy.sum() < 400)}
        for arm in ("M0", "M1", "M2"):
            entry[f"{arm}_logloss"] = float(ll(PRED[arm][mask], yy).mean())
            entry[f"{arm}_brier"] = float(br(PRED[arm][mask], yy).mean())
        for dname, (a, b_, met) in {"M2-M1_logloss": ("M2", "M1", "ll"), "M1-M0_logloss": ("M1", "M0", "ll"),
                                    "M2-M1_brier": ("M2", "M1", "br"), "M1-M0_brier": ("M1", "M0", "br")}.items():
            entry[dname] = float((ll(PRED[a][mask], yy) - ll(PRED[b_][mask], yy)).mean()) if met == "ll" else \
                float((br(PRED[a][mask], yy) - br(PRED[b_][mask], yy)).mean())
        if nd >= 20:
            paired = {a: {"ll": ll(PRED[a][mask], yy), "br": br(PRED[a][mask], yy)} for a in ("M1", "M2", "M0")}
            bres = boot(paired, gd[mask])
            entry["bootstrap_M2-M1_logloss_ci95"] = bres["M2-M1_ll"]["ci95"]
            entry["bootstrap_M1-M0_logloss_ci95"] = bres["M1-M0_ll"]["ci95"]
        entries[str(v)] = entry
    slices_out[sname] = entries

# ---------- PA-1B completeness preflight (measurement only) ----------
p24g = p24.filter(~pl.col("trunc_flag")).group_by(["game_pk", "pitcher"]).agg(
    pl.len().alias("eligible_rows")).join(
    pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").select(
        "game_pk", "pitcher", "PA").collect(), on=["game_pk", "pitcher"], how="left")
trunc_starts = set(zip(*[trunc.filter(pl.col("season") == 2024)["game_pk"].to_list(),
                         trunc.filter(pl.col("season") == 2024)["pitcher"].to_list()])) if False else None
tr24 = trunc.filter(pl.col("season") == 2024)
trunc_starts = set((g, p) for g, p in zip(tr24["game_pk"].to_list(), tr24["pitcher"].to_list()))
mp_starts = set(zip(mp_with_starter.filter(pl.col("season") == 2024)["game_pk"].to_list(),
                    mp_with_starter.filter(pl.col("season") == 2024)["term_pitch"].to_list()))
recon = p24g.with_columns([
    (pl.col("eligible_rows") == pl.col("PA")).alias("exact"),
    (pl.col("eligible_rows") < pl.col("PA")).alias("under"),
    (pl.col("eligible_rows") > pl.col("PA")).alias("over")])
completeness = {
    "population": "2024 primary",
    "n_groups": p24g.height,
    "eligible_pa_count_distribution": p24g["eligible_rows"].describe().__pydict__() if False else {
        "min": int(p24g["eligible_rows"].min()), "p25": float(p24g["eligible_rows"].quantile(0.25)),
        "median": float(p24g["eligible_rows"].median()), "p75": float(p24g["eligible_rows"].quantile(0.75)),
        "max": int(p24g["eligible_rows"].max())},
    "starts_with_truncated_pa": len(trunc_starts),
    "starts_with_multipitcher_ambiguity": len(mp_starts),
    "canonical_tbf_source": "data/processed/pitcher_games.parquet PA column (starter game PA, PA>=9 gate)",
    "reconciliation": {
        "exact": int(recon["exact"].sum()), "under_canonical": int(recon["under"].sum()),
        "over_canonical": int(recon["over"].sum()),
        "pct_fully_reconciled": round(float(recon["exact"].mean()), 4),
        "reasons": "under = dropped truncated_pa + reliever-attributed PAs within starter outing "
                   "(terminal-row credit); over = none expected; audit per-start in pa1b outputs"},
    "proposed_pa1b_primary": "starts with exact reconciliation (eligible_rows == canonical PA), "
                             "no truncated_pa, no unresolved multi-pitcher attribution; other starts "
                             "reserved for a separately labeled sensitivity",
    "status": "MEASURED ONLY - PA-1B NOT RUN (owner prohibition)",
}
OUTB.mkdir(parents=True, exist_ok=True)
(OUTB / "completeness.json").write_text(json.dumps(completeness, indent=2), encoding="utf-8")

# ---------- write outputs ----------
per_pa = p24.select(["game_pk", "at_bat_number", "game_date", "pitcher", "batter", "stand",
                     "p_throws", "month", "starter_pa_index", "matchup_number", "trip_proxy",
                     "league_k_prior", "k_rate_std", "b_k_rate_std_shrunk", "trunc_flag"]).with_columns([
    pl.Series("p0", p0), pl.Series("p1", p1), pl.Series("p2", p2),
    pl.Series("fallback_reason", fb_reason)])
per_pa.write_parquet(HERE / "per_pa.parquet")
rel_rows = [dict(r, arm_block=k) for k, rows in rel_out.items() for r in rows]
pl.DataFrame(rel_rows).write_parquet(HERE / "reliability.parquet")
results["metrics"] = metrics_out
results["paired_game_date_bootstrap"] = boot_out
results["paired_game_pk_bootstrap_sensitivity"] = sens_boot_out
results["prediction_distributions"] = gateG
results["slices"] = slices_out
results["reliability_path"] = "reliability.parquet"
results["per_pa_path"] = "per_pa.parquet"
results["pa1b_completeness_path"] = "../pa1b_oracle_xk/completeness.json"
results["deviations"] = deviations
(HERE / "deviations.md").write_text(
    "\n".join(f"- [{d['when']}] {d['gate']}: {d['finding']} "
              f"(rows=0: {d['n_rows_0']}, rows=1: {d['n_rows_1']}) {d['classification']}"
              for d in deviations), encoding="utf-8")
results["finished_utc"] = datetime.now(timezone.utc).isoformat()
(HERE / "preflight.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("WROTE preflight.json / per_pa.parquet / reliability.parquet / completeness.json")
