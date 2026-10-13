"""bf-workload-v1 step 2: paired downstream K-count comparison.

DIAGNOSTIC LABELING (mandatory): per-PA K probabilities exist only for
REALIZED PAs, so the conditional K distribution for exposure n uses the
mean PA probability over the start's first n ordered (by at_bat_number)
REALIZED PA probabilities; for n beyond the realized count it uses the
mean over all realized PAs. This conditions on the realized PA sequence
and realized exposure ordering -- it is NOT a pregame forecast. Both
arms share the SAME BF PMF; arms differ only in per-PA K probabilities
(H3 logistic vs cumulative log5, P1 calibrated columns pred_H3_cal /
pred_LOG5_cal).

Arms / variants:
- base:    BF PMF = 37-cat add-one empirical (own if prior_n>=10 else
           league), extended to 1..60 via bf_pmf_from_37.
- sens_a:  point exposure = point_exposure_n(BF PMF) (rounded mean),
           binomial with that fixed n.
- sens_b:  doubled-variance BF PMF = 50/50 count mix (source, league)
           then add-one, extended the same way.

Metrics per start/arm: count-RPS (k_max=24, summed convention),
count log score, squared error of exact mean-K (E[K] = sum_n P(N=n) *
n * p_bar_n; RMSE reported as sqrt of mean squared error),
milestone Brier 6/8/10/12. Bootstrap: slate-date, 2000 resamples,
seed 20261001.
"""
from __future__ import annotations

import hashlib
import json
import sys
from math import lgamma
from pathlib import Path

import numpy as np
import polars as pl

WORK = Path(__file__).resolve().parent.parent
HELPERS = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\main-active\research\offseason_2026"
)
sys.path.insert(0, str(HELPERS))
from kcount_combiner import (  # noqa: E402
    KCOUNT_CAP, bf_pmf_from_37, count_logscore, count_rps,
    point_exposure_n,
)

P2_DATA = Path(r"C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data")
PREDS = [
    "preds_block_2024H2.parquet",
    "preds_block_2025H1.parquet",
    "preds_confirm_2025H2.parquet",
]
FORECASTS = WORK / "data" / "bf_forecasts.parquet"
OUT_METRICS = WORK / "data" / "start_metrics.parquet"
OUT_REPORT = WORK / "report.json"
OUT_SUMMARY = WORK / "summary.md"

K_MAX = 24
MILESTONES = (6, 8, 10, 12)
BOOT_N = 2000
BOOT_SEED = 20261001
P_CLIP = 1e-9
WINDOW_LO = "2024-07-01"
WINDOW_HI = "2025-12-31"
VARIANTS = ("base", "sensa", "sensb")
ARMS = ("h3", "l5")
SCORING_METRICS = ("rps", "logscore", "rmse_mean_k",
                   "brier_ge6", "brier_ge8", "brier_ge10", "brier_ge12")

KS = np.arange(K_MAX)
N_ARR = np.arange(1, KCOUNT_CAP + 1)[:, None]
LOG_BINOM = np.full((KCOUNT_CAP + 1, K_MAX), -np.inf)
for _n in range(KCOUNT_CAP + 1):
    for _k in range(K_MAX):
        if _k <= _n:
            LOG_BINOM[_n, _k] = (
                lgamma(_n + 1) - lgamma(_k + 1) - lgamma(_n - _k + 1)
            )


def count_pmf_from_mixture(bf_ext: np.ndarray,
                           pbar_n: np.ndarray) -> np.ndarray:
    """P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n), k=0..K_MAX-1."""
    with np.errstate(divide="ignore"):
        logp = np.log(pbar_n)
        log1mp = np.log1p(-pbar_n)
    lp = LOG_BINOM[1:KCOUNT_CAP + 1] + logp[:, None] * KS[None, :] \
        + log1mp[:, None] * (N_ARR - KS[None, :])
    binom = np.exp(lp)
    binom[N_ARR - KS < 0] = 0.0  # k > n impossible
    out = (bf_ext[:, None] * binom).sum(axis=0)
    tail = max(0.0, 1.0 - out.sum())
    out[K_MAX - 1] += tail
    return out


def binom_point(n: int, p: float) -> np.ndarray:
    lp = LOG_BINOM[n, :] + KS * np.log(p) + (n - KS) * np.log1p(-p)
    out = np.where(KS <= n, np.exp(lp), 0.0)
    tail = max(0.0, 1.0 - out.sum())
    out[K_MAX - 1] += tail
    return out


def metrics_for(p_k: np.ndarray, k_real: int, mean_k: float) -> dict:
    out = {"rps": count_rps(p_k, k_real),
           "logscore": count_logscore(p_k, k_real),
           "rmse_mean_k": (mean_k - k_real) ** 2}
    cdf = np.cumsum(p_k)
    for m in MILESTONES:
        p_ge = float(cdf[m:].sum())
        out[f"brier_ge{m}"] = (p_ge - (1.0 if k_real >= m else 0.0)) ** 2
    return out


def main() -> None:
    fc = pl.read_parquet(FORECASTS).filter(
        (pl.col("game_date") >= pl.date(2024, 7, 1))
        & (pl.col("game_date") <= pl.date(2025, 12, 31))
    )
    pmf_cols = [f"pmf37_{j}" for j in range(37)]
    mix_cols = [f"pmf37_mix_{j}" for j in range(37)]
    assert fc.filter(pl.struct(pmf_cols).is_null()).height == 0, \
        "assessment starts missing BF PMF"

    preds = pl.concat(
        [pl.read_parquet(P2_DATA / f) for f in PREDS], how="vertical"
    ).filter(
        (pl.col("game_date") >= pl.date(2024, 7, 1))
        & (pl.col("game_date") <= pl.date(2025, 12, 31))
    )
    grouped = preds.partition_by(
        ["game_pk", "pitcher"], as_dict=True, maintain_order=False
    )
    grouped = {(k[0], k[1]): g for k, g in grouped.items()}

    rows = []
    n_no_pas = 0
    n_bf_mismatch = 0
    for s in fc.to_dicts():
        key = (s["game_pk"], s["pitcher"])
        g = grouped.get(key)
        if g is None:
            n_no_pas += 1
            continue
        g = g.sort("at_bat_number")
        n_real = g.height
        if n_real != s["realized_bf"]:
            n_bf_mismatch += 1
            continue
        k_real = int(g["y"].sum())
        p_h3 = np.clip(g["pred_H3_cal"].to_numpy(), P_CLIP, 1 - P_CLIP)
        p_l5 = np.clip(g["pred_LOG5_cal"].to_numpy(), P_CLIP, 1 - P_CLIP)

        bf37 = np.array([s[c] for c in pmf_cols])
        mix37 = np.array([s[c] for c in mix_cols])
        bf_ext = bf_pmf_from_37(bf37)
        bf_ext_mix = bf_pmf_from_37(mix37)

        pbar = {}
        for arm, p in (("h3", p_h3), ("l5", p_l5)):
            csum = np.cumsum(p)
            pb = csum / np.arange(1, n_real + 1)
            if n_real < KCOUNT_CAP:
                pb = np.concatenate(
                    [pb, np.full(KCOUNT_CAP - n_real, pb[-1])]
                )
            pbar[arm] = np.clip(pb, P_CLIP, 1 - P_CLIP)

        pk = {"base": {}, "sensb": {}, "sensa": {}}
        mean_k = {"base": {}, "sensb": {}, "sensa": {}}
        for arm in ARMS:
            pk["base"][arm] = count_pmf_from_mixture(bf_ext, pbar[arm])
            mean_k["base"][arm] = float(
                (bf_ext * N_ARR[:, 0] * pbar[arm]).sum()
            )
            pk["sensb"][arm] = count_pmf_from_mixture(bf_ext_mix, pbar[arm])
            mean_k["sensb"][arm] = float(
                (bf_ext_mix * N_ARR[:, 0] * pbar[arm]).sum()
            )
        n_point = point_exposure_n(bf37)
        np_eff = min(n_point, n_real)
        for arm, p in (("h3", p_h3), ("l5", p_l5)):
            p_bar = float(np.mean(p[:np_eff]))
            pk["sensa"][arm] = binom_point(n_point, p_bar)
            mean_k["sensa"][arm] = n_point * p_bar

        row = {
            "game_pk": s["game_pk"], "side": s["side"],
            "pitcher": s["pitcher"], "game_date": s["game_date"],
            "prior_n": s["prior_n"], "cold_start": s["cold_start"],
            "realized_bf": n_real, "realized_k": k_real,
            "n_point_exposure": n_point,
        }
        for variant in VARIANTS:
            for arm in ARMS:
                met = metrics_for(pk[variant][arm], k_real,
                                  mean_k[variant][arm])
                for mname, mval in met.items():
                    row[f"{variant}_{arm}_{mname}"] = mval
        rows.append(row)

    met = pl.DataFrame(rows).sort(["game_date", "game_pk", "side"])
    met.write_parquet(OUT_METRICS)
    n_starts = met.height

    dates = met["game_date"].unique().sort().to_list()
    D = len(dates)
    date_pos = {d: i for i, d in enumerate(dates)}
    d_idx = np.array([date_pos[d] for d in met["game_date"].to_list()])

    sums = {v + "_n": np.bincount(d_idx, minlength=D).astype(float)
            for v in VARIANTS}
    for variant in VARIANTS:
        for arm in ARMS:
            for m in SCORING_METRICS:
                col = f"{variant}_{arm}_{m}"
                sums[col] = np.bincount(
                    d_idx, weights=met[col].to_numpy(), minlength=D
                )

    def agg(col):
        return float(met[col].mean())

    def rmse_agg(variant, arm):
        return float(np.sqrt(met[f"{variant}_{arm}_rmse_mean_k"].mean()))

    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, D, size=(BOOT_N, D))

    def per_resample_sum(col):
        return sums[col][idx].sum(axis=1)

    def per_resample_n(variant):
        return sums[variant + "_n"][idx].sum(axis=1)

    boot = {}
    for variant in VARIANTS:
        n_rs = per_resample_n(variant)
        for arm in ARMS:
            for m in ("rps", "logscore"):
                col = f"{variant}_{arm}_{m}"
                vals = per_resample_sum(col) / n_rs
                boot[f"{variant}_{arm}_{m}_point"] = agg(col)
                boot[f"{variant}_{arm}_{m}_ci95"] = [
                    float(np.percentile(vals, 2.5)),
                    float(np.percentile(vals, 97.5)),
                ]
            col = f"{variant}_{arm}_rmse_mean_k"
            vals = np.sqrt(per_resample_sum(col) / n_rs)
            boot[f"{variant}_{arm}_rmse_mean_k_point"] = rmse_agg(variant, arm)
            boot[f"{variant}_{arm}_rmse_mean_k_ci95"] = [
                float(np.percentile(vals, 2.5)),
                float(np.percentile(vals, 97.5)),
            ]
        for m in ("rps", "logscore", "rmse_mean_k"):
            h3c = f"{variant}_h3_{m}"
            l5c = f"{variant}_l5_{m}"
            if m == "rmse_mean_k":
                diff = (np.sqrt(per_resample_sum(h3c) / n_rs)
                        - np.sqrt(per_resample_sum(l5c) / n_rs))
                point = rmse_agg(variant, "h3") - rmse_agg(variant, "l5")
            else:
                diff = (per_resample_sum(h3c) - per_resample_sum(l5c)) / n_rs
                point = agg(h3c) - agg(l5c)
            boot[f"{variant}_diff_{m}_h3_minus_l5_point"] = float(point)
            boot[f"{variant}_diff_{m}_ci95"] = [
                float(np.percentile(diff, 2.5)),
                float(np.percentile(diff, 97.5)),
            ]
            boot[f"{variant}_diff_{m}_share_resamples_h3_better"] = \
                float((diff < 0).mean())

    report = {
        "card": "bf-workload-v1",
        "created": "2026-10-13",
        "labeling": {
            "bf_forecast": (
                "Pregame point-in-time: BF PMF uses only starts strictly "
                "before game_date (lineup-free empirical + w=50 shrunk "
                "mean; own prior dist if prior_n>=10 else league)."
            ),
            "pa_probability_conditioning": (
                "DIAGNOSTIC ONLY, NOT a pregame K-count forecast: per-PA K "
                "probabilities exist only for REALIZED PAs, so the "
                "conditional K distribution for exposure n uses the mean "
                "of the start's first n ordered (by at_bat_number) "
                "REALIZED PA probabilities (mean over all realized PAs for "
                "n beyond the realized count). This conditions on the "
                "realized PA sequence and ordering; it compares PA "
                "probability quality under a shared, honestly-pregame BF "
                "PMF."
            ),
        },
        "arms": {
            "h3": "pred_H3_cal (P1 H3 logistic, calibrated)",
            "log5": "pred_LOG5_cal (cumulative log5 reference, calibrated)",
        },
        "shared": "identical BF PMF per start; arms differ only in PA probs",
        "window": [WINDOW_LO, WINDOW_HI],
        "blocks": ["block_2024H2", "block_2025H1", "confirm_2025H2"],
        "variants": {
            "base": "37-cat add-one empirical BF PMF (own if n>=10 else league)",
            "sensa": "point exposure = point_exposure_n(BF PMF), fixed-n binomial",
            "sensb": "doubled-variance: 50/50 count mix (source, league) + add-one",
        },
        "k_max": K_MAX,
        "milestones": list(MILESTONES),
        "n_starts": n_starts,
        "n_starts_dropped_no_preds": n_no_pas,
        "n_starts_dropped_bf_mismatch": n_bf_mismatch,
        "n_slate_dates": D,
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "unit": "slate-date (game_date)"},
        "aggregate": {
            variant: {
                arm: {
                    "rps": agg(f"{variant}_{arm}_rps"),
                    "logscore": agg(f"{variant}_{arm}_logscore"),
                    "rmse_mean_k": rmse_agg(variant, arm),
                    **{f"brier_ge{m}": agg(f"{variant}_{arm}_brier_ge{m}")
                       for m in MILESTONES},
                }
                for arm in ARMS
            }
            for variant in VARIANTS
        },
        "bootstrap_results": boot,
        "inputs_sha256": {},
    }
    for name, path in [
        ("bf_forecasts.parquet", FORECASTS),
        *[("overnight-p2/" + f, P2_DATA / f) for f in PREDS],
        ("helpers/kcount_combiner.py", HELPERS / "kcount_combiner.py"),
        ("helpers/bf_distribution.py", HELPERS / "bf_distribution.py"),
        ("scripts/build_bf_forecasts.py",
         WORK / "scripts" / "build_bf_forecasts.py"),
        ("scripts/run_kcount_comparison.py", Path(__file__).resolve()),
    ]:
        report["inputs_sha256"][name] = \
            hashlib.sha256(path.read_bytes()).hexdigest()

    OUT_REPORT.write_text(json.dumps(report, indent=1), encoding="ascii")
    print("n_starts:", n_starts, "no_preds:", n_no_pas,
          "bf_mismatch:", n_bf_mismatch, "dates:", D)
    print(json.dumps(report["aggregate"], indent=1))
    print(json.dumps({k: v for k, v in boot.items() if "diff" in k},
                     indent=1))


if __name__ == "__main__":
    main()
