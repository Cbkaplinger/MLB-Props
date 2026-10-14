"""bf-workload CORRECTION v2: milestone-Brier recompute (PMF-tail exceedance).

BUG IN v1 (scripts/run_kcount_comparison.py:107-115): the milestone Brier
computed the exceedance as cdf[m:].sum() -- a sum of CDF values over
k >= m -- instead of the PMF tail P(K>=m) = 1 - CDF(m-1)
= sum_{k>=m} P(K=k) (kcount_combiner.exceedance). The buggy per-start
values could exceed 1 (up to (K_MAX-m)^2), inflating every brier_ge6/8/10/12
by ~3 orders of magnitude. RPS / log score / mean-K RMSE were NOT affected.

This script recomputes ALL per-start metrics with the corrected exceedance
(kc.exceedance), reproduces the unchanged metrics bit-for-bit, recomputes
slate-date bootstrap intervals (2000 resamples, seed 20261001) including
paired milestone-Brier intervals, and writes NEW versioned outputs:

- data/start_metrics_v2.parquet
- report_v2.json

The v1 outputs (report.json, summary.md, data/start_metrics.parquet,
reports/*) are NEVER modified. Milestone blocks carry explicit SUPERSEDED
notes (both the v1 block reproduced here and the v2 corrected block).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

WORK = Path(__file__).resolve().parent.parent
HELPERS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HELPERS))
from kcount_combiner import exceedance  # noqa: E402

# The v1 comparison module supplies the EXACT machinery (constants, PMF
# construction, aggregation helpers). Its buggy metrics_for is NOT used.
# It is loaded LAZILY via _load_v1(): importing this correction module must
# never execute the comparison runner (pytest collection safety).
_V1_SCRIPT = WORK / "scripts" / "run_kcount_comparison.py"
_V1_CACHE: dict = {}


def _load_v1():
    if "mod" not in _V1_CACHE:
        _spec = importlib.util.spec_from_file_location("bf_v1", str(_V1_SCRIPT))
        mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(mod)
        _V1_CACHE["mod"] = mod
    return _V1_CACHE["mod"]


OUT_METRICS = WORK / "data" / "start_metrics_v2.parquet"
OUT_REPORT = WORK / "report_v2.json"
V1_REPORT = WORK / "report.json"
V1_METRICS = WORK / "data" / "start_metrics.parquet"


def corrected_metrics_for(p_k: np.ndarray, k_real: int, mean_k: float) -> dict:
    """Corrected milestone Brier: P(K>=m) = PMF tail = 1 - CDF(m-1),
    via kcount_combiner.exceedance. RPS/logscore/RMSE identical to v1."""
    v1 = _load_v1()
    out = {"rps": v1.count_rps(p_k, k_real),
           "logscore": v1.count_logscore(p_k, k_real),
           "rmse_mean_k": (mean_k - k_real) ** 2}
    for m in v1.MILESTONES:
        p_ge = exceedance(p_k, m)
        out[f"brier_ge{m}"] = (p_ge - (1.0 if k_real >= m else 0.0)) ** 2
    return out


DEFINITIONS = {
    "support": {
        "bf_pmf_categories": 37,
        "category_mapping": (
            "index 0..35 = P(BF=1..36); index 36 = P(BF>=37) overflow mass; "
            "overflow is NEVER read as BF=37"
        ),
        "smoothing": "add-one (Laplace) empirical baseline over 37 categories",
        "extension_to_k_support": (
            "bf_pmf_from_37 maps the 37-vector to a PMF over exposures 1..60 "
            "(KCOUNT_CAP=60); overflow mass redistributed over 37..60 with a "
            "geometric tail whose per-step ratio is 1 minus the mean implied "
            "hazard of the last six body categories; assertion |sum-1|<1e-9"
        ),
        "overflow_cap": 60,
        "k_count_support": (
            "k_max=24: exact categories 0..23; the last bucket absorbs K>=23"
        ),
    },
    "truncation": {
        "history_pool_start": "2023-01-01 (2022 is warm-up only, never fitted or scored)",
        "excluded_seasons": "2026 excluded (0 rows anywhere)",
        "same_date_lookahead": "same-date starts never in prior; pools update AFTER all starts of that date are forecast (incl. doubleheaders)",
        "empty_league_pool": (
            "first date(s) with no league history get no PMF: 30 of 14,574 "
            "total forecast rows; 0 in the assessment window (asserted)"
        ),
        "assessment_window": "2024-07-01..2025-12-31",
        "drop_rules": "start dropped if preds have no (game_pk, pitcher) group, or realized PA count != realized_bf (both 0 in this run)",
    },
    "eligibility": {
        "grain": "first pitcher of record per (game_pk, side), opener-inclusive, no starter filter",
        "bf_definition": "completed PAs where that pitcher was pitcher of record; >=1 BF asserted",
        "pmf_source_rule": "own 37-cat counts if prior_n>=10 (OWN_DIST_MIN_N=10) else pooled league counts; point mean shrunk toward league mean with W_SHRINK=50 regardless of prior_n",
        "cold_start": "cold_start = int(prior_n == 0); cold starts still get the league-based PMF",
        "low_history_counts_assessment_window": {
            "prior_n_lt_10": 1135,
            "prior_n_eq_0_cold": 169,
            "note": "corrects summary.md caveat that conflated prior_n<10 with n=169",
        },
    },
    "substitutions": {
        "rule": "realized PA sequence includes PAs against substitute batters; per-PA probabilities are the arms' probabilities for the actual (substitute) batters faced; the target definition already includes them",
    },
    "feature_cutoff": {
        "source": "pred_H3_cal / pred_LOG5_cal from overnight-p2 checkpointed preds parquets (P1 harness, strictly-prior discipline)",
        "rule": "every 2023+ PA's features use observations strictly before its game_date; 2022 (182,051 PAs) is feature-history warm-up only; fixed 0.2245 pooled prior removed entirely in v3",
        "cold_start_fallback": "league rate at cutoff (source_type league_prior_no_entity_history)",
        "clipping": "both arms clipped to [1e-9, 1-1e-9] before use",
    },
    "milestone_exceedance_v2": {
        "definition": "P(K>=m) = 1 - CDF(m-1) = PMF tail sum over k>=m (kcount_combiner.exceedance)",
        "bug_v1": "v1 used cdf[m:].sum() (sum of CDF values over k>=m), which can exceed 1",
        "aggregation": "milestone Brier aggregates are MEANS over starts (corrects the 'summed over starts' wording)",
    },
}


def main() -> None:
    v1 = _load_v1()
    ARMS = v1.ARMS
    VARIANTS = v1.VARIANTS
    MILESTONES = v1.MILESTONES
    BOOT_N = v1.BOOT_N
    BOOT_SEED = v1.BOOT_SEED
    SCORING_METRICS = v1.SCORING_METRICS
    v1_report = json.loads(V1_REPORT.read_text(encoding="ascii"))

    fc = pl.read_parquet(v1.FORECASTS).filter(
        (pl.col("game_date") >= pl.date(2024, 7, 1))
        & (pl.col("game_date") <= pl.date(2025, 12, 31))
    )
    pmf_cols = [f"pmf37_{j}" for j in range(37)]
    mix_cols = [f"pmf37_mix_{j}" for j in range(37)]
    assert fc.filter(pl.struct(pmf_cols).is_null()).height == 0, \
        "assessment starts missing BF PMF"

    preds = pl.concat(
        [pl.read_parquet(v1.P2_DATA / f) for f in v1.PREDS], how="vertical"
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
        p_h3 = np.clip(g["pred_H3_cal"].to_numpy(), v1.P_CLIP, 1 - v1.P_CLIP)
        p_l5 = np.clip(g["pred_LOG5_cal"].to_numpy(), v1.P_CLIP, 1 - v1.P_CLIP)

        bf37 = np.array([s[c] for c in pmf_cols])
        mix37 = np.array([s[c] for c in mix_cols])
        bf_ext = v1.bf_pmf_from_37(bf37)
        bf_ext_mix = v1.bf_pmf_from_37(mix37)

        pbar = {}
        for arm, p in (("h3", p_h3), ("l5", p_l5)):
            csum = np.cumsum(p)
            pb = csum / np.arange(1, n_real + 1)
            if n_real < v1.KCOUNT_CAP:
                pb = np.concatenate(
                    [pb, np.full(v1.KCOUNT_CAP - n_real, pb[-1])]
                )
            pbar[arm] = np.clip(pb, v1.P_CLIP, 1 - v1.P_CLIP)

        pk = {"base": {}, "sensb": {}, "sensa": {}}
        mean_k = {"base": {}, "sensb": {}, "sensa": {}}
        for arm in ARMS:
            pk["base"][arm] = v1.count_pmf_from_mixture(bf_ext, pbar[arm])
            mean_k["base"][arm] = float(
                (bf_ext * v1.N_ARR[:, 0] * pbar[arm]).sum()
            )
            pk["sensb"][arm] = v1.count_pmf_from_mixture(bf_ext_mix, pbar[arm])
            mean_k["sensb"][arm] = float(
                (bf_ext_mix * v1.N_ARR[:, 0] * pbar[arm]).sum()
            )
        n_point = v1.point_exposure_n(bf37)
        np_eff = min(n_point, n_real)
        for arm, p in (("h3", p_h3), ("l5", p_l5)):
            p_bar = float(np.mean(p[:np_eff]))
            pk["sensa"][arm] = v1.binom_point(n_point, p_bar)
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
                met = corrected_metrics_for(pk[variant][arm], k_real,
                                            mean_k[variant][arm])
                for mname, mval in met.items():
                    row[f"{variant}_{arm}_{mname}"] = mval
        rows.append(row)

    met = pl.DataFrame(rows).sort(["game_date", "game_pk", "side"])
    met.write_parquet(OUT_METRICS)
    n_starts = met.height
    assert n_starts == v1_report["n_starts"], "start count changed"

    # unchanged-metrics guard: rps/logscore/rmse per start must match the
    # stored v1 per-start metrics exactly
    stored = pl.read_parquet(V1_METRICS)
    j = met.join(stored, on=["game_pk", "side", "pitcher", "game_date"],
                 how="inner", suffix="_v1")
    assert j.height == n_starts, "join vs stored v1 metrics lost rows"
    for variant in VARIANTS:
        for arm in ARMS:
            for m in ("rps", "logscore", "rmse_mean_k"):
                d = float(j.select(
                    (pl.col(f"{variant}_{arm}_{m}")
                     - pl.col(f"{variant}_{arm}_{m}_v1")).abs().max()
                    .alias("d"))["d"][0])
                assert d == 0.0, f"UNCHANGED metric drifted: {variant}/{arm}/{m}: {d}"

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
            # corrected milestone Brier: point + CI (mean over starts)
            for ms in MILESTONES:
                col = f"{variant}_{arm}_brier_ge{ms}"
                vals = per_resample_sum(col) / n_rs
                boot[f"{variant}_{arm}_brier_ge{ms}_point"] = \
                    agg(f"{variant}_{arm}_brier_ge{ms}")
                boot[f"{variant}_{arm}_brier_ge{ms}_ci95"] = [
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
        # paired milestone-Brier diffs (H3 - L5)
        for ms in MILESTONES:
            h3c = f"{variant}_h3_brier_ge{ms}"
            l5c = f"{variant}_l5_brier_ge{ms}"
            diff = (per_resample_sum(h3c) - per_resample_sum(l5c)) / n_rs
            boot[f"{variant}_diff_brier_ge{ms}_h3_minus_l5_point"] = \
                agg(h3c) - agg(l5c)
            boot[f"{variant}_diff_brier_ge{ms}_ci95"] = [
                float(np.percentile(diff, 2.5)),
                float(np.percentile(diff, 97.5)),
            ]
            boot[f"{variant}_diff_brier_ge{ms}_share_resamples_h3_better"] = \
                float((diff < 0).mean())

    # unchanged bootstrap CIs must match v1 exactly (same seed, same sums)
    for key in ("rps", "logscore"):
        for variant in VARIANTS:
            for arm in ARMS:
                assert boot[f"{variant}_{arm}_{key}_point"] == \
                    v1_report["bootstrap_results"][
                        f"{variant}_{arm}_{key}_point"], \
                    f"point changed: {variant}/{arm}/{key}"
                assert boot[f"{variant}_{arm}_{key}_ci95"] == \
                    v1_report["bootstrap_results"][
                        f"{variant}_{arm}_{key}_ci95"], \
                    f"CI changed: {variant}/{arm}/{key}"

    aggregate = {
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
    }
    for variant in VARIANTS:
        for arm in ARMS:
            for m in ("rps", "logscore", "rmse_mean_k"):
                assert aggregate[variant][arm][m] == \
                    v1_report["aggregate"][variant][arm][m], \
                    f"aggregate changed: {variant}/{arm}/{m}"

    v1_blocks = {
        variant: {
            arm: {k: v1_report["aggregate"][variant][arm][k]
                  for k in ("rps", "logscore", "rmse_mean_k",
                            "brier_ge6", "brier_ge8", "brier_ge10",
                            "brier_ge12")}
            for arm in ARMS
        }
        for variant in VARIANTS
    }

    report = {
        "card": "bf-workload-v1",
        "correction_version": 2,
        "created": "2026-10-13",
        "labeling": v1_report["labeling"],
        "arms": v1_report["arms"],
        "shared": v1_report["shared"],
        "window": [v1.WINDOW_LO, v1.WINDOW_HI],
        "blocks": ["block_2024H2", "block_2025H1", "confirm_2025H2"],
        "variants": v1_report["variants"],
        "k_max": v1.K_MAX,
        "milestones": list(MILESTONES),
        "n_starts": n_starts,
        "n_starts_dropped_no_preds": n_no_pas,
        "n_starts_dropped_bf_mismatch": n_bf_mismatch,
        "n_slate_dates": D,
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "unit": "slate-date (game_date)"},
        "correction": {
            "reason": (
                "v1 milestone Brier used CDF-tail summation "
                "(cdf[m:].sum() over k>=m) instead of the PMF-tail "
                "exceedance P(K>=m) = 1 - CDF(m-1) = sum_{k>=m} P(K=k) "
                "(kcount_combiner.exceedance). Buggy per-start values could "
                "exceed 1, inflating all brier_ge6/8/10/12 by ~3 orders of "
                "magnitude. RPS, log score and mean-K RMSE are unaffected."
            ),
            "formula": "P(K>=m) = 1 - CDF(m-1); Brier = (P(K>=m) - 1{K>=m})^2 per start",
            "aggregation": "milestone aggregates are MEANS over starts",
            "supersedes": [
                "report.json aggregate.*.brier_ge* (original preserved unmodified)",
                "summary.md milestone paragraph (original preserved unmodified)",
            ],
            "unchanged_metrics": [
                "count-RPS, count log score, mean-K RMSE point estimates and "
                "all 95% slate-date bootstrap CIs (recomputed bit-identical, "
                "asserted in-script and in tests)"
            ],
        },
        "milestone_blocks": {
            "v1": {
                "source": "report.json 'aggregate' brier_* fields (original file preserved unmodified)",
                "aggregation_label_in_v1": "'summed over starts' (summary.md) - incorrect label; v1 aggregates were means of buggy per-start values",
                "values": v1_blocks,
                "note": (
                    "SUPERSEDED: milestone values computed with the "
                    "CDF-tail summation bug; do not cite. See "
                    "correction_note.md and the v2 block."
                ),
            },
            "v2": {
                "source": "this report; corrected metrics_for using kcount_combiner.exceedance",
                "aggregation": "mean over starts",
                "values": {
                    variant: {
                        arm: {f"brier_ge{m}":
                              aggregate[variant][arm][f"brier_ge{m}"]
                              for m in MILESTONES}
                        for arm in ARMS
                    }
                    for variant in VARIANTS
                },
                "note": (
                    "SUPERSEDED (marker applied per versioned-correction "
                    "protocol): this is the corrected PMF-tail block and it "
                    "supersedes the v1 block; it remains open to a future "
                    "versioned correction. Current canonical pointer: "
                    "correction_note.md."
                ),
            },
        },
        "definitions": DEFINITIONS,
        "low_history_counts": {
            "prior_n_lt_10": 1135,
            "prior_n_eq_0_cold": 169,
            "correction": (
                "summary.md caveat 'sens_b for cold pitchers (prior_n<10, "
                "n=169 starts)' conflated the two slices: prior_n<10 = 1,135 "
                "assessment starts; prior_n==0 (cold) = 169. The sens_b "
                "league-with-league note applies to all prior_n<10 starts."
            ),
        },
        "aggregate": aggregate,
        "bootstrap_results": boot,
        "inputs_sha256": {},
        "preserved_v1_outputs_sha256": {
            "report.json": hashlib.sha256(
                V1_REPORT.read_bytes()).hexdigest(),
            "data/start_metrics.parquet": hashlib.sha256(
                V1_METRICS.read_bytes()).hexdigest(),
        },
    }
    for name, path in [
        ("bf_forecasts.parquet", v1.FORECASTS),
        *[("overnight-p2/" + f, v1.P2_DATA / f) for f in v1.PREDS],
        ("helpers/kcount_combiner.py", HELPERS / "kcount_combiner.py"),
        ("helpers/bf_distribution.py", HELPERS / "bf_distribution.py"),
        ("scripts/build_bf_forecasts.py",
         WORK / "scripts" / "build_bf_forecasts.py"),
        ("scripts/run_kcount_comparison.py", v1.__file__ and Path(v1.__file__)),
        ("scripts/run_kcount_correction_v2.py", Path(__file__).resolve()),
    ]:
        report["inputs_sha256"][name] = \
            hashlib.sha256(path.read_bytes()).hexdigest()

    # inputs unchanged vs v1
    for name, h in v1_report["inputs_sha256"].items():
        assert report["inputs_sha256"][name] == h, f"input changed: {name}"

    OUT_REPORT.write_text(json.dumps(report, indent=1), encoding="ascii")
    print("n_starts:", n_starts, "dates:", D)
    print(json.dumps(aggregate, indent=1))
    print("milestone paired diffs (h3-l5):")
    for variant in VARIANTS:
        for ms in MILESTONES:
            print(variant, ms,
                  boot[f"{variant}_diff_brier_ge{ms}_h3_minus_l5_point"],
                  boot[f"{variant}_diff_brier_ge{ms}_ci95"])


if __name__ == "__main__":
    main()
