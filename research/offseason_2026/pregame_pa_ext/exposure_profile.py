"""C-B1: exposure-profile heterogeneity (Question B, candidate 1).

RESEARCH-ONLY, synthetic-first. Implements the FIRST candidate of
card_workload_dependence_B_2026-10-20.md: per-BF-INDEX K probability
profile q_j, piecewise-constant on registered bands, estimated from the
FROZEN realized-PA training lineage with band-level shrinkage toward
the frozen cycled prefix mean, aggregated through the MERGED Question A
exact Poisson-Binomial machinery mixed over the REGISTERED BF workload.

What changes vs the frozen baseline: ONLY the per-PA probability
sequence generator (frozen cycled prefix means -> estimated exposure
profile). N unchanged; lineup construction unchanged; eligibility
unchanged. Count-RPS is the primary metric; Holm m=1.

The K label is the pa_table's frozen binary y (1 = strikeout event);
the M0 v2 receipt verified label-integrity (y == 1 iff taxonomy
class_label == 0) across the whole table, so the frozen y IS the M0
class-0 label.

No real-data execution without --i-accept-outcome-evaluation and
explicit owner authorization (same gate pattern as M0 v2).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pregame_pa_ext import adapter as ad  # noqa: F401
from pregame_pa_ext import batt_recency as br
from pregame_pa_ext import count_aggregation_exact as ex
from pregame_pa_ext import m0_multiclass as m0

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import kcount_combiner as kc  # noqa: E402  (registered count metrics)

DEV_BLOCK_TRAIN_END = m0.DEV_BLOCK_TRAIN_END
PROTECTED_BLOCK = m0.PROTECTED_BLOCK

# registered bands (BF index 1..60, inclusive bounds)
BANDS = ((1, 9), (10, 18), (19, 27), (28, 36), (37, 60))
N_BANDS = len(BANDS)

# pre-registered shrinkage weight (w150 convention): the band rate is
# pulled toward the frozen profile with the weight of 150 pseudo-PAs
SHRINKAGE_N = 150

# pre-registered estimation-stop tolerance (card C-B1 stop condition a)
ESTIMATION_TOLERANCE = 0.005

K_MAX = ex.ad.K_MAX
KCOUNT_CAP = ad.KCOUNT_CAP


def band_for_bf(j: int) -> int:
    """Band index (0-based) for a 1-based BF index."""
    if not 1 <= j <= KCOUNT_CAP:
        raise ValueError(f"BF index out of range 1..{KCOUNT_CAP}: {j}")
    for b, (lo, hi) in enumerate(BANDS):
        if lo <= j <= hi:
            return b
    raise AssertionError("unreachable band lookup")


def assign_bf_bands(pa: "pl.DataFrame") -> "pl.DataFrame":
    """Attach bf_index (1-based position of the PA within its pitcher's
    start, ordered by at_bat_number) and band (0-based) to realized PA
    rows. Identity grain: (game_pk, pitcher) - a starting pitcher's PAs
    all belong to one side of one game, so this IS the start's PA
    sequence."""
    import polars as pl

    need = {"game_pk", "pitcher", "at_bat_number"}
    if not need.issubset(set(pa.columns)):
        raise ValueError(f"pa frame missing columns: {sorted(need)}")
    return pa.sort("at_bat_number").with_columns(
        pl.int_range(pl.len()).over("game_pk", "pitcher")
        .add(1).alias("bf_index")
    ).with_columns(
        pl.col("bf_index").map_elements(
            lambda j: band_for_bf(int(j)), return_dtype=pl.Int8)
        .alias("band")
    )


def frozen_band_prior(pa_bands: "pl.DataFrame", slot_col: str = "p_slot",
                      ) -> np.ndarray:
    """The FROZEN cycled prefix-mean profile: per band, the mean over
    the band's lineage PAs of the frozen cycled slot probability at
    that PA's position (p_slot = the cycled tile value for the PA's
    BF index, supplied by the caller from the preserved ledger's slot
    probabilities). Returns the 5-band prior rate vector."""
    import polars as pl

    rates = np.zeros(N_BANDS)
    for b in range(N_BANDS):
        sub = pa_bands.filter(pl.col("band") == b)
        if sub.height == 0:
            raise ValueError(f"band {b} has no lineage rows: the frozen "
                             "prior is undefined (stop condition c)")
        rates[b] = float(sub[slot_col].mean())
    return rates


def shrink_band_rates(k_counts: np.ndarray, n_counts: np.ndarray,
                      prior: np.ndarray,
                      w: int = SHRINKAGE_N) -> np.ndarray:
    """q_band = (w * prior + k) / (w + n) - the pre-registered w150
    shrinkage of the empirical band K rate toward the frozen profile."""
    k_counts = np.asarray(k_counts, dtype=np.float64)
    n_counts = np.asarray(n_counts, dtype=np.float64)
    prior = np.asarray(prior, dtype=np.float64)
    if k_counts.shape != (N_BANDS,) or n_counts.shape != (N_BANDS,) \
            or prior.shape != (N_BANDS,):
        raise ValueError("band vectors must be length 5")
    if np.any(n_counts < 0) or np.any(k_counts > n_counts):
        raise ValueError("invalid band counts")
    if np.any((prior < 0) | (prior > 1)):
        raise ValueError("prior rates out of [0, 1]")
    return (w * prior + k_counts) / (w + n_counts)


def band_counts(pa_bands: "pl.DataFrame", label_col: str = "y",
                ) -> tuple[np.ndarray, np.ndarray]:
    """Per-band (K successes, total PAs) from the labeled lineage."""
    import polars as pl

    k = np.zeros(N_BANDS)
    n = np.zeros(N_BANDS)
    for b in range(N_BANDS):
        sub = pa_bands.filter(pl.col("band") == b)
        n[b] = sub.height
        k[b] = int(sub[label_col].sum())
    return k, n


def profile_from_bands(band_rates: np.ndarray) -> np.ndarray:
    """Expand the 5 band rates to the 60-slot per-BF-index profile
    (piecewise-constant on the registered bands)."""
    band_rates = np.asarray(band_rates, dtype=np.float64)
    if band_rates.shape != (N_BANDS,):
        raise ValueError("band rate vector must be length 5")
    q = np.zeros(KCOUNT_CAP)
    for b, (lo, hi) in enumerate(BANDS):
        q[lo - 1:hi] = band_rates[b]
    return q


def poisson_binomial_pmf_profile(q: np.ndarray, n: int,
                                 k_max: int = K_MAX) -> np.ndarray:
    """Exact Poisson-Binomial count PMF over the FIRST n entries of the
    exposure profile (NO cycling - the profile is already per-BF-index),
    with the registered bucket convention: k = 0..k_max-2 exact, tail
    absorbed at k = k_max-1."""
    q = np.asarray(q, dtype=np.float64)
    if q.shape != (KCOUNT_CAP,):
        raise ValueError(f"profile must have {KCOUNT_CAP} slots")
    if not 1 <= n <= KCOUNT_CAP:
        raise ValueError(f"n out of range 1..{KCOUNT_CAP}: {n}")
    if np.any((q < 0) | (q > 1)):
        raise ValueError("profile rates out of [0, 1]")
    ps = q[:n]
    dp = np.zeros(n + 1)
    dp[0] = 1.0
    for i, p in enumerate(ps, 1):
        nxt = np.zeros(i + 1)
        nxt[:i] += dp[:i] * (1.0 - p)
        nxt[1:i + 1] += dp[:i] * p
        dp = nxt
    out = np.zeros(k_max)
    top = min(len(dp), k_max - 1)
    out[:top] = dp[:top]
    out[k_max - 1] += dp[k_max - 1:].sum()
    return out


def profile_count_pmf(q: np.ndarray, bf_ext: np.ndarray,
                      k_max: int = K_MAX) -> np.ndarray:
    """C-B1 count PMF: P(K=k) = sum_n bf_ext[n-1] * PB(q_1..q_n).
    bf_ext: P(N=n) for n=1..60 (registered bf_pmf_from_37 extension)."""
    bf_ext = np.asarray(bf_ext, dtype=np.float64)
    if bf_ext.shape != (KCOUNT_CAP,):
        raise ValueError(
            f"bf_ext must have {KCOUNT_CAP} entries, got {bf_ext.shape}")
    if abs(float(bf_ext.sum()) - 1.0) > 1e-9:
        raise ValueError("bf_ext must sum to 1")
    out = np.zeros(k_max)
    for n in range(1, KCOUNT_CAP + 1):
        w = bf_ext[n - 1]
        if w > 0:
            out += w * poisson_binomial_pmf_profile(q, n, k_max=k_max)
    return out


def estimation_stop(q: np.ndarray, prior: np.ndarray,
                    tol: float = ESTIMATION_TOLERANCE) -> bool:
    """Card stop condition (a): every band within tol of the frozen
    profile -> declare no exposure signal WITHOUT evaluation."""
    q = np.asarray(q, dtype=np.float64)
    prior = np.asarray(prior, dtype=np.float64)
    if q.shape != (N_BANDS,) or prior.shape != (N_BANDS,):
        raise ValueError("band vectors must be length 5")
    return bool(np.all(np.abs(q - prior) < tol))

# ----------------------------------------------------------------- runner
def _slot_for_bf(j: int) -> int:
    """The registered cycling rule: BF index j (1-based) reads slot
    ((j-1) mod 9) + 1 of the start's nine slot probabilities."""
    return (j - 1) % 9 + 1


def frozen_prior_from_ledger(ledger: "pl.DataFrame") -> np.ndarray:
    """The FROZEN cycled prefix-mean exposure profile: per band, the
    mean over eligible starts and over the band's BF positions of the
    start's projected slot probability p_h3_raw at the cycled position.
    This is the shrinkage target - exactly the per-PA generator the
    frozen baseline uses, so C-B1's q replaces it like-for-like."""
    import polars as pl

    slots = ledger.filter(pl.col("exclusion_reason").is_null())
    per_start = slots.group_by("game_pk", "side", "pitcher").agg(
        pl.col("p_h3_raw").sort_by("slot"))
    if per_start.height == 0:
        raise ValueError("no eligible starts in the ledger: the frozen "
                         "prior is undefined (stop condition c)")
    p9_all = np.vstack(per_start["p_h3_raw"].to_list())
    if p9_all.shape[1] != 9:
        raise ValueError(
            f"expected 9 slots per start, got {p9_all.shape[1]}")
    prior = np.zeros(N_BANDS)
    for b, (lo, hi) in enumerate(BANDS):
        pos = np.arange(lo, hi + 1)
        slot_idx = np.array([(p - 1) % 9 for p in pos])
        prior[b] = float(p9_all[:, slot_idx].mean())
    return prior


def _block_for_date(d) -> str:
    """Development block for a start/lineage date (registered block
    boundaries; confirm_2025H2 never returned - it is protected)."""
    import datetime as _dt

    d = d if isinstance(d, _dt.date) else d.date()
    if d <= _dt.date(2024, 6, 30):
        return "block_2024H2"
    if d <= _dt.date(2025, 6, 30):
        return "block_2025H1"
    return PROTECTED_BLOCK


def run_cb1_eval(pa: "pl.DataFrame", ledger: "pl.DataFrame",
                 bf: "pl.DataFrame", realized: "pl.DataFrame", out_dir, *,
                 n_boot: int = 2000, seed: int = 20261001,
                 ) -> dict:
    """GATED C-B1 evaluation runner (synthetic-tested; real-data
    execution requires the registered gate AND explicit owner
    authorization). Write-once; immutable initial receipt; failure
    records preserved.

    pa: frozen realized-PA training lineage (game_pk, pitcher,
        at_bat_number, game_date, y); the K label is the frozen binary
        y (receipt-verified equivalent to the M0 class-0 label).
    ledger: preserved-run ledger slots (game_pk, side, pitcher, slot,
        game_date, p_h3_raw, exclusion_reason).
    bf: registered BF PMF artifact (game_pk, side, pitcher, pmf37_*).
    realized: registered realized-K-per-start source (start_metrics_v2
        lineage: game_pk, side, pitcher, realized_k).

    One pre-declared contrast (C-B1 vs the frozen baseline, paired
    count-RPS on the identical eligible starts), slate-date bootstrap
    (n_boot, seed), Holm m=1. ESTIMATION STOP (a) fires before any
    evaluation if every band is within tolerance of the frozen
    profile."""
    import polars as pl

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    initial = {
        "inputs": {
            "consumed": {
                "lineage_pa": m0._frame_sha(pa),
                "preserved_run_ledger": m0._frame_sha(ledger),
                "bf_pmf": m0._frame_sha(bf),
                "realized_counts_source": m0._frame_sha(realized),
            },
            "context_identities": {},
        },
        "code_config": {
            "exposure_profile_py_lf_sha256": m0.sha256_stream(
                m0._lf_bytes(Path(__file__))),
            "bands": [list(b) for b in BANDS],
            "shrinkage_n": SHRINKAGE_N,
            "estimation_stop_tolerance": ESTIMATION_TOLERANCE,
            "prior_definition": ("per band: mean over eligible starts "
                                 "of the projected p_h3_raw at the "
                                 "band's cycled BF positions"),
            "endpoint": ("paired count-RPS, C-B1 exposure profile vs "
                         "the frozen cycled prefix-mean baseline, "
                         "slate-date bootstrap, Holm m=1"),
            "bootstrap": {"n": n_boot, "seed": seed},
            "protected_block": PROTECTED_BLOCK,
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        # stage 1: the frozen prior (shrinkage target)
        prior = frozen_prior_from_ledger(ledger)

        # stage 2: per-block estimated profiles from the frozen lineage
        banded = assign_bf_bands(pa)
        banded = banded.with_columns(
            pl.col("game_date").map_elements(
                _block_for_date, return_dtype=pl.Utf8).alias("fit_block"))
        blocks_fit = {}
        for b in DEV_BLOCK_TRAIN_END:
            te_y, te_m, te_d = DEV_BLOCK_TRAIN_END[b]
            te = pl.date(te_y, te_m, te_d)
            lin = banded.filter(
                (pl.col("fit_block") == b)
                & (pl.col("game_date") <= te))
            k_counts, n_counts = band_counts(lin)
            q = shrink_band_rates(k_counts, n_counts, prior)
            blocks_fit[b] = {
                "k_counts": k_counts.tolist(),
                "n_counts": n_counts.tolist(),
                "prior": prior.tolist(),
                "q_band": q.tolist(),
                "estimation_stop": estimation_stop(q, prior),
                "lineage_rows": int(lin.height),
            }
        if all(v["estimation_stop"] for v in blocks_fit.values()):
            final = dict(initial)
            final["estimation_stop"] = {
                "status": "ESTIMATION STOP (card C-B1 condition a): "
                          "every band within tolerance of the frozen "
                          "profile in every block; no exposure signal; "
                          "evaluation NOT run",
                "blocks": blocks_fit,
            }
            final["acceptance"] = {
                "receipt_chain": initial_sha,
                "evaluation_run": False,
                "block_isolation": True,
            }
            (out_dir / "receipt_final.json").write_text(
                json.dumps(final, indent=1, sort_keys=True),
                encoding="utf-8")
            if ad.sha256_file(initial_path) != initial_sha:
                raise ValueError("IMMUTABLE initial receipt modified")
            return {"out_dir": str(out_dir), "receipt_final": final,
                    "receipt_initial_sha256": initial_sha,
                    "estimation_stop": True}

        # stage 3: paired per-start count-RPS, both arms
        slots = ledger.filter(pl.col("exclusion_reason").is_null())
        p9_rows = slots.sort("game_pk", "side", "slot").group_by(
            "game_pk", "side", "pitcher").agg(
            pl.col("p_h3_raw").sort_by("slot").alias("p9"),
            pl.col("game_date").first().alias("game_date"))
        bf37 = bf.select("game_pk", "side", "pitcher",
                         *[f"pmf37_{j}" for j in range(37)])
        desc = p9_rows.join(bf37, on=["game_pk", "side", "pitcher"],
                            how="inner")
        rps_cb1, rps_frozen, keys = [], [], []
        for r in desc.iter_rows(named=True):
            blk = _block_for_date(r["game_date"])
            if blk == PROTECTED_BLOCK:
                raise ValueError("protected confirm block in evaluation")
            q = np.array(blocks_fit[blk]["q_band"])
            q60 = profile_from_bands(q)
            p9 = np.asarray(r["p9"], dtype=np.float64)
            b37 = np.asarray([r[f"pmf37_{j}"] for j in range(37)])
            b37 = b37 / b37.sum()
            bf_ext = ad.bf_pmf_from_37(b37)
            pmf_cb1 = profile_count_pmf(q60, bf_ext)
            pmf_frz = ad.count_pmf_from_mixture(
                bf_ext, ad.cycled_cond_mean(p9))
            rrow = realized.filter(
                (pl.col("game_pk") == r["game_pk"])
                & (pl.col("side") == r["side"])
                & (pl.col("pitcher") == r["pitcher"]))
            if rrow.height != 1:
                raise ValueError(
                    f"realized count mismatch for start "
                    f"{r['game_pk']}/{r['side']} ({rrow.height} rows)")
            k_real = int(rrow["realized_k"][0])
            rps_cb1.append(float(kc.count_rps(pmf_cb1, k_real)))
            rps_frozen.append(float(kc.count_rps(pmf_frz, k_real)))
            keys.append((r["game_pk"], r["side"], r["pitcher"]))
        rps_cb1 = np.asarray(rps_cb1)
        rps_frozen = np.asarray(rps_frozen)

        # stage 4: slate-date bootstrap, one pre-declared contrast
        cmp_mod = br.load_registered_comparison()
        dates = desc["game_date"].to_list()
        blocks = [_block_for_date(d) for d in dates]
        res = cmp_mod.slate_date_draws(
            {"cb1": rps_cb1, "frozen": rps_frozen},
            dates, blocks, n_boot=n_boot, seed=seed)
        d_rep = res[:, 0] - res[:, 1]
        delta = float(rps_cb1.mean() - rps_frozen.mean())
        ci = [float(np.percentile(d_rep, 2.5)),
              float(np.percentile(d_rep, 97.5))]
        p = cmp_mod.null_centered_p_value(delta, d_rep)
        holm = cmp_mod.holm_adjust({"cb1_vs_frozen": p})
        metrics = {
            "n_starts": int(desc.height),
            "count_rps_cb1_mean": float(rps_cb1.mean()),
            "count_rps_frozen_mean": float(rps_frozen.mean()),
            "delta": delta,
            "ci95": ci,
            "p_null_centered": p,
            "holm": holm,
            "decision": ("cb1_beats_baseline" if ci[1] < 0
                         else "cb1_not_better"),
            "blocks_fit": blocks_fit,
        }
        ev = pl.DataFrame({
            "game_pk": [k[0] for k in keys],
            "side": [k[1] for k in keys],
            "pitcher": [k[2] for k in keys],
            "game_date": dates,
            "rps_cb1": rps_cb1,
            "rps_frozen": rps_frozen,
        })
        ev_path = out_dir / "cb1_eval_v1.parquet"
        ev.write_parquet(ev_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "cb1_eval_v1.parquet": ad.sha256_file(ev_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
    except Exception as exc:
        failure = {"stage": "cb1_exposure_profile", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = metrics
    final["outputs"] = outputs
    final["acceptance"] = {
        "receipt_chain": initial_sha,
        "evaluation_run": True,
        "block_isolation": True,
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final, "receipt_initial_sha256": initial_sha,
            "estimation_stop": False}
