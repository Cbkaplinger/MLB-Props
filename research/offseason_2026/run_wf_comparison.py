"""Chronological WF comparison - four fixed arms (contract 2026-10-09).

Arms: REF (canonical log5 p*), A (new 72-feature monotone LGBM),
B (new 58-feature LGBM), BLEND (fixed 0.60 A + 0.40 B). All arms use
identical I3b ext60 BF PMFs and the same count combiner on common
scored rows. Development evidence only - no promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, "research/offseason_2026")
sys.path.insert(0, "src")
sys.path.insert(0, ".")

import kcount_combiner as kc  # noqa: E402
import run_i3_transfer_2024 as rt  # noqa: E402
import run_lgbm_bridge as rb  # noqa: E402

import lightgbm as lgb  # noqa: E402

SEASONS = ("2022", "2023", "2024")
DATA = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data")
SPINE_PATH = Path(r"C:\Users\ckaplinger\MLB-Props-Research\wf_spine_2024"
                  "\pitcher_training.parquet")
REF_DIR = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
               r"\transfer-2024-i3b-20261008_224538")
WINDOWS = (
    ("wf_2024_apr_may", "2024-04-01", "2024-06-01"),
    ("wf_2024_jun_jul", "2024-06-01", "2024-08-01"),
    ("wf_2024_aug_sep", "2024-08-01", "2025-01-01"),
)
VAL_FRACTION = 0.15
BLEND_W = (0.60, 0.40)
SEED = 42
ES_ROUNDS = 200
BOOT_N = 2_000
BOOT_SEED = 20261001
FROZEN_PARAMS = {
    "objective": "regression",
    "n_estimators": 5_000,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
    "random_state": SEED,
    "verbosity": -1,
    "n_jobs": -1,
}
RPS_FLOOR = -0.0005
XK_BIAS_TOL = 0.05
XK_MAE_TOL = 0.02
MILESTONE_BRIER_CAP = 0.0002
ALPHA = 0.05

_MONO_POSITIVE_STEMS = ("k_rate", "swstr", "whiff", "putaway", "cs_rate",
                        "k_minus_swstr")
_MONO_NEGATIVE_STEMS = ("hit_rate", "bb_rate", "opp_lineup_obp", "zcontact",
                        "contact_rate")


def _feature_constraints(features: list[str]) -> list[int]:
    out: list[int] = []
    for feature in features:
        if any(feature == s or feature.startswith(s)
               for s in _MONO_POSITIVE_STEMS):
            out.append(1)
        elif any(feature == s or feature.startswith(s)
                 for s in _MONO_NEGATIVE_STEMS):
            out.append(-1)
        else:
            out.append(0)
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_rps_vec(pmfs: np.ndarray, k_real: np.ndarray) -> np.ndarray:
    cdf = np.cumsum(pmfs, axis=1)
    n = pmfs.shape[1] - 1
    kk = np.minimum(k_real, n)
    idx = np.arange(n + 1)[None, :]
    over = np.sum((cdf - (idx > kk[:, None])) ** 2, axis=1)
    return over


def _slate_bootstrap(diff: np.ndarray, dates: np.ndarray) -> dict:
    uniq = np.unique(dates)
    rng = np.random.default_rng(BOOT_SEED)
    by_date = [diff[dates == d] for d in uniq]
    stats = np.empty(BOOT_N)
    for b in range(BOOT_N):
        pick = rng.integers(0, len(uniq), len(uniq))
        parts = [by_date[i] for i in pick]
        stats[b] = np.concatenate(parts).mean() if parts else 0.0
    return {"estimate": float(np.mean(diff)),
            "lo95": float(np.percentile(stats, 2.5)),
            "hi95": float(np.percentile(stats, 97.5))}


def _holm(pvals: list[float]) -> list[float]:
    order = np.argsort(pvals)
    m = len(pvals)
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj


def _pval_from_boot(stats: np.ndarray) -> float:
    """One-sided paired-bootstrap p for H0: diff >= 0 (improvement)."""
    return float(max(1e-6, float(np.mean(stats >= 0.0))))


def fit_arms(spine: pl.DataFrame) -> tuple[dict, dict]:
    members, _ = rb.load_frozen_ensemble(
        Path("artifacts") / "models")
    f72 = members[0]["features"]
    f58 = members[1]["features"]
    mono = _feature_constraints(f72)
    fits: dict = {"f72": f72, "f58": f58, "per_window": {}}
    dates = spine["game_date"]
    for name, start, end in WINDOWS:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        tr = spine.filter(pl.col("game_date") < s)
        sc = spine.filter((pl.col("game_date") >= s)
                          & (pl.col("game_date") < e))
        cut = int(len(tr) * (1.0 - VAL_FRACTION))
        val = tr[cut:]
        trn = tr[:cut]
        y_tr = trn["k_rate"].to_numpy()
        y_val = val["k_rate"].to_numpy()
        win: dict = {}
        for tag, feats, use_mono in (("A", f72, True), ("B", f58, False)):
            params = dict(FROZEN_PARAMS)
            if use_mono:
                params["monotone_constraints"] = mono
                params["monotone_constraints_method"] = "advanced"
            model = lgb.LGBMRegressor(**params)
            model.fit(trn.select(feats).to_numpy(), y_tr,
                      eval_set=[(val.select(feats).to_numpy(), y_val)],
                      eval_metric="l2",
                      callbacks=[lgb.early_stopping(ES_ROUNDS,
                                                    verbose=False)])
            win[tag] = {
                "model": model,
                "best_iter": int(model.best_iteration_ or
                                 params["n_estimators"]),
                "pred": np.clip(model.predict(
                    sc.select(feats).to_numpy()), 0.0, 1.0),
                "scored_keys": list(zip(
                    sc["game_pk"].to_list(), sc["pitcher"].to_list())),
            }
        fits["per_window"][name] = win
    return fits, None


def run(out_dir: Path, contract: Path) -> dict:
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    contract_sha = _sha256_file(contract)

    spine = pl.read_parquet(SPINE_PATH)
    ref = pl.read_csv(REF_DIR / "predictions.csv")
    ref_pmfs = pl.read_parquet(REF_DIR / "pmfs.parquet")

    members, _ = rb.load_frozen_ensemble(Path("artifacts") / "models")
    raw = {y: pl.read_parquet(
        DATA / "Savant-Data" / "regular" / y
        / f"statcast_{y}_regular.parquet") for y in SEASONS}
    ext60 = rb.rebuild_ref_ext60(raw["2022"], raw["2023"], raw["2024"],
                                 21.94, ref)
    p_star = ref["p_star"].to_numpy()
    k_real = ref["K"].to_numpy().astype(np.int64)
    dates = np.array([str(d)[:10] for d in ref["game_date"].to_list()])

    fits, _ = fit_arms(spine)

    # Each scored block belongs to exactly one window; map keys to that
    # window's predictions directly (windows do not overlap).
    key_to_pred: dict = {}
    for wname, win in fits["per_window"].items():
        for i, key in enumerate(win["A"]["scored_keys"]):
            key_to_pred[key] = {
                "A": win["A"]["pred"][i], "B": win["B"]["pred"][i]}

    pa = np.full(len(ref), np.nan)
    pb = np.full(len(ref), np.nan)
    matched = np.zeros(len(ref), dtype=bool)
    for i, key in enumerate(zip(ref["game_pk"].to_list(),
                                ref["pitcher"].to_list())):
        d = key_to_pred.get(key)
        if d is not None:
            pa[i] = d["A"]
            pb[i] = d["B"]
            matched[i] = True
    if matched.sum() < 0.95 * len(ref):
        raise rt.RunFailure(
            "coverage below 95%%: %d/%d" % (matched.sum(), len(ref)))
    blend = np.clip(BLEND_W[0] * pa + BLEND_W[1] * pb, 0.0, 1.0)

    arms = {"REF": p_star, "A": pa, "B": pb, "BLEND": blend}
    scored = np.where(matched)[0]
    cdf_cache = {}
    rps = {}
    for tag, pvec in arms.items():
        pk = np.array([kc.combine_count(ext60[i], pvec[i])
                       for i in scored])
        cdf_cache[tag] = pk
        rps[tag] = _count_rps_vec(pk, k_real[scored])

    results: dict = {"n_population": int(len(ref)),
                     "n_matched": int(matched.sum()),
                     "coverage": float(matched.mean()),
                     "arms": {}}
    base = rps["REF"]
    sd = dates[scored]
    comparisons = {}
    boot_stats = {}
    for tag in ("A", "B", "BLEND"):
        diff = rps[tag] - base
        ci = _slate_bootstrap(diff, sd)
        comparisons[tag] = ci
        boot_stats[tag] = diff  # re-sampled inside _slate_bootstrap
    pvals = []
    for tag in ("A", "B", "BLEND"):
        uniq = np.unique(sd)
        rng = np.random.default_rng(BOOT_SEED)
        by_date = {d: (rps[tag] - base)[sd == d] for d in uniq}
        stats = np.empty(BOOT_N)
        for b in range(BOOT_N):
            pick = rng.integers(0, len(uniq), len(uniq))
            stats[b] = np.concatenate(
                [by_date[uniq[i]] for i in pick]).mean()
        pvals.append(_pval_from_boot(stats))
    holm = _holm(pvals)
    for j, tag in enumerate(("A", "B", "BLEND")):
        results["arms"][tag] = {
            "mean_rps": float(np.mean(rps[tag])),
            "ci": comparisons[tag],
            "holm_p": holm[j], "raw_p": pvals[j],
            "mean_rps_REF": float(np.mean(base)),
        }
    logscore = {}
    for tag, pk in cdf_cache.items():
        pr = np.array([pk[i, min(k, pk.shape[1] - 1)]
                       for i, k in enumerate(k_real[scored])])
        logscore[tag] = float(np.mean(-np.log(np.maximum(pr, 1e-12))))
    results["logscore"] = logscore

    xk = {}
    for tag, pk in cdf_cache.items():
        means = pk @ np.arange(pk.shape[1])
        xk[tag] = means
    k_real_s = k_real[scored].astype(float)
    for tag in ("A", "B", "BLEND"):
        d_bias = abs(np.mean(xk[tag] - k_real_s)) \
            - abs(np.mean(xk["REF"] - k_real_s))
        d_mae = np.mean(np.abs(xk[tag] - k_real_s)) \
            - np.mean(np.abs(xk["REF"] - k_real_s))
        results["arms"][tag]["xk_bias_delta"] = float(d_bias)
        results["arms"][tag]["xk_mae_delta"] = float(d_mae)
        results["arms"][tag]["xk_bias_delta_ok"] = bool(
            abs(d_bias) <= XK_BIAS_TOL)
        results["arms"][tag]["xk_mae_delta_ok"] = bool(
            abs(d_mae) <= XK_MAE_TOL)
        results["arms"][tag]["xk_bias"] = float(
            np.mean(xk[tag] - k_real_s))
        results["arms"][tag]["xk_mae"] = float(
            np.mean(np.abs(xk[tag] - k_real_s)))

    safety_ok = True
    for tag in ("A", "B", "BLEND"):
        ci = comparisons[tag]
        results["arms"][tag]["rps_floor_ok"] = bool(ci["lo95"]
                                                    <= RPS_FLOOR)
        if ci["lo95"] > RPS_FLOOR:
            safety_ok = False
        if not (results["arms"][tag]["xk_bias_delta_ok"]
                and results["arms"][tag]["xk_mae_delta_ok"]):
            safety_ok = False
    results["safety_ok"] = safety_ok
    results["gates"] = {
        "coverage_ge_95": bool(matched.mean() >= 0.95),
        "holm_blend_significant":
            bool(holm[2] < ALPHA
                 and comparisons["BLEND"]["estimate"] < 0),
        "safety": safety_ok,
    }
    results["pass"] = all(results["gates"].values())

    pred_out = ref.with_columns([
        pl.Series("p_hat_A", pa), pl.Series("p_hat_B", pb),
        pl.Series("p_hat_BLEND", blend),
        pl.Series("wf_matched", matched),
        pl.Series("mean_REF",
                  [float(kc.expected_bf(ext60[i]))
                   for i in range(len(ref))]),
    ])
    pk_out = {}
    for tag, pk in cdf_cache.items():
        for j, row in enumerate(scored):
            pk_out.setdefault(int(row), {})["pk_" + tag] = pk[j]
    rows = []
    for i in sorted(pk_out):
        rec = {"game_pk": ref["game_pk"][i],
               "pitcher": ref["pitcher"][i],
               "K": int(k_real[i]), "game_date": dates[i]}
        rec.update({k: list(v) for k, v in pk_out[i].items()})
        rows.append(rec)
    pl.DataFrame(rows,
                 schema_overrides={"game_pk": pl.Int64,
                                   "K": pl.Int64}).write_parquet(
        out_dir / "pmfs.parquet")
    pred_out.write_csv(out_dir / "predictions.csv")

    manifest = {
        "run": "wf-comparison-2026-10-09",
        "contract": str(contract), "contract_sha256": contract_sha,
        "spine": str(SPINE_PATH),
        "spine_sha256": _sha256_file(SPINE_PATH),
        "windows": [list(w) for w in WINDOWS],
        "frozen_params": FROZEN_PARAMS,
        "blend_weights": BLEND_W, "val_fraction": VAL_FRACTION,
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "unit": "slate_date"},
        "holm_alpha": ALPHA,
        "best_iterations": {
            w[0]: {t: fits["per_window"][w[0]][t]["best_iter"]
                   for t in ("A", "B")} for w in WINDOWS},
        "results": results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out_dir / "wf_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    args = ap.parse_args()
    m = run(Path(args.out), Path(args.contract))
    print(json.dumps({"status": "COMPLETE", "gates": m["results"]["gates"],
                      "results": m["results"]["arms"],
                      "coverage": m["results"]["coverage"],
                      "n_matched": m["results"]["n_matched"]}))


if __name__ == "__main__":
    main()
