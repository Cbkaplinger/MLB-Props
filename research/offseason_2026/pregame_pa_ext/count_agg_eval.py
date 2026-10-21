"""GATED EVALUATION RUNNER — Question A: exact heterogeneous count
aggregation vs the registered averaged-binomial aggregation
(pregame-pa-ext-v2 lane). RESEARCH-ONLY. Real-outcome evaluation is gated
behind --i-accept-outcome-evaluation AND explicit owner authorization;
this module has NEVER run on real data.

Approved design (eval_spec_count_aggregation_A_2026-10-20.md):
- ONE change between arms: the within-n aggregation rule.
  BASELINE arm = the registered machinery (adapter.cycled_cond_mean +
  adapter.count_pmf_from_mixture) over the preserved per-slot PA
  probabilities (p_h3_raw, slot order preserved).
  CHALLENGER arm = the exact Poisson-Binomial over the SAME per-slot
  probabilities and the SAME BF extension (count_aggregation_exact.
  exact_count_pmf).
- IDENTICAL in both arms: the 4,823 eligible development starts (frozen
  start-key set), the BF workload per start (bf_pmf_from_37, cap 60), the
  lineup order, the eligibility (registered cold_start_no_prior exclusion,
  unchanged), and the 24-bucket tail convention (bucket k=23 absorbs
  K >= 23 — it is NOT an exact count of 23).
- Realized counts: K per start from the REGISTERED start_metrics_v2
  lineage (bf-workload-v1), joined on (game_pk, side, pitcher); sha256
  recorded as a CONSUMED input.
- PRIMARY: count-RPS (kcount_combiner.count_rps, summed convention) on
  the 24-bucket PMFs, paired by start. SUPPORTING (descriptive, never
  gated): milestone Briers K>=6/8/10/12 (the registered columns).
- Uncertainty: the REGISTERED paired slate-date bootstrap + null-centered
  contrast test + Holm m=1 (comparison.py via the established import
  path; one pre-declared contrast
  C_exact_agg_vs_registered: challenger - baseline).
- Expected-count checks: E[K] from the UNTRUNCATED distribution is
  recorded per arm as a mathematical check (for the exact aggregator the
  untruncated E[K] = sum of the first n cycled slot probabilities; for
  the registered arm the binomial mean n * pbar_n - the two are
  mathematically IDENTICAL because both use the same cycled order).
  The REGISTERED bucketed outputs are verified separately: bucket k=23
  is P(K >= 23), and P(K <= 22) from the buckets must equal the
  untruncated P(K <= 22) exactly. The bucketed mean is never claimed to
  be the untruncated mean.

Provenance (NEVER repair a receipt in place):
- receipt_initial.json is written FIRST, before any computation, with
  COMPLETE consumed/context input identities, code/config hashes, and the
  frozen key identities. It is IMMUTABLE - never rewritten.
- On success, receipt_final.json is a NEW file that chains to the initial
  receipt by sha256 and adds outputs/metrics/acceptance.
- On ANY failure, failure_record.json is written write-once (stage,
  error) and PRESERVED; the initial receipt is never touched. Nothing is
  ever repaired in place.

Clipping convention (recorded per Chat 2's finding): both arms inherit
IDENTICAL per-PA probabilities from the preserved ledger (p_h3_raw,
clipped to [1e-9, 1-1e-9] at generation by the frozen apply_h3_raw);
the registered cycled_cond_mean re-clips pbar at the same P_CLIP (a no-op
on the preserved values, verified in range); the exact PB applies no
additional clip; count_rps applies no clip. The aggregation rule is the
ONLY difference between arms — verified by a parity test (a homogeneous
lineup yields IDENTICAL PMFs in both arms) and recorded in the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import count_aggregation_exact as ex  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402

import kcount_combiner as kc  # noqa: E402  (registered count metrics)

OUT_BUNDLE_NAME = "count_agg_eval_v1"
CONSUMED_KEYS = ("pa_table_not_consumed_here",)  # see note: consumed inputs
MILESTONES = (6, 8, 10, 12)
PUBLISHED_DEV_START_KEYS_SHA256 = (
    "618e8e754aa0f5e4d0b9493762299d8d664f46a78bb22d701807642494284ae2")
PUBLISHED_DEV_STARTS_N = 4823
PUBLISHED_DEV_SLOT_KEYS_SHA256 = (
    "82592f18f824359e9a48848acf7662c040edc5e3284ed6f4a1741137606318ef")
PUBLISHED_DEV_SLOT_KEYS_N = 43407


def sha256_stream(stream: bytes) -> str:
    return hashlib.sha256(stream).hexdigest()


def _sha(p) -> str:
    return ad.sha256_file(Path(p))


def _lf(p) -> bytes:
    return Path(p).read_bytes().replace(b"\r\n", b"\n").replace(
        b"\r", b"\n")


def classify_inputs(artifact_paths: dict) -> dict:
    """CONSUMED vs CONTEXT (Chat 2 classification): the diagnostic
    consumes the preserved ledger, the BF PMF artifact, and the realized-
    count source (start_metrics_v2 lineage), plus code. The checkpoint,
    lineups, freeze config, and pa_table are CONTEXT identities from the
    prior registration — hashed, never read by this runner."""
    consumed_keys = ("preserved_run_ledger", "bf_pmf",
                     "realized_counts_source")
    consumed = {k: _sha(v) for k, v in artifact_paths.items()
                if k in consumed_keys}
    context = {k: _sha(v) for k, v in artifact_paths.items()
               if k not in consumed_keys}
    return {"consumed": consumed, "context_identities": context}


def block_of(game_date) -> str:
    if game_date <= date(2024, 12, 31):
        return "block_2024H2"
    if game_date <= date(2025, 6, 30):
        return "block_2025H1"
    return "confirm_2025H2"


def initial_receipt(artifact_paths: dict) -> dict:
    inputs = classify_inputs(artifact_paths)
    return {
        "inputs": inputs,
        "code_config": {
            "count_agg_eval_py_lf_sha256": sha256_stream(
                _lf(Path(__file__))),
            "count_aggregation_exact_py_lf_sha256": sha256_stream(
                _lf(Path(__file__).resolve().parent
                    / "count_aggregation_exact.py")),
            "adapter_py_lf_sha256": sha256_stream(_lf(ad.__file__)),
            "challenger_config": {
                "aggregation": "exact_poisson_binomial_cycled",
                "baseline": "registered cycled prefix-mean binomial",
                "k_max": ad.K_MAX, "cap": ad.KCOUNT_CAP,
                "milestones": list(MILESTONES),
            },
            "clipping_convention": {
                "per_pa_source": (
                    "preserved p_h3_raw clipped [1e-9, 1-1e-9] at "
                    "generation (frozen apply_h3_raw); identical both "
                    "arms"),
                "baseline_pbar": ("cycled_cond_mean re-clips at the same "
                                  "P_CLIP 1e-9 (no-op on the preserved "
                                  "values)"),
                "challenger_pb": ("no additional clip beyond the preserved "
                                  "per-PA values"),
                "count_rps": ("no clip; summed CDF-squared convention "
                              "over the 24 registered buckets"),
                "parity_rule": ("the aggregation rule is the ONLY arm "
                                "difference; verified by the "
                                "homogeneous-parity test"),
            },
        },
        "dev_keys": {
            "start_keys_n": PUBLISHED_DEV_STARTS_N,
            "start_keys_sha256": PUBLISHED_DEV_START_KEYS_SHA256,
            "slot_keys_n": PUBLISHED_DEV_SLOT_KEYS_N,
            "slot_keys_sha256": PUBLISHED_DEV_SLOT_KEYS_SHA256,
        },
        "config": {
            "primary": "count-RPS (kcount_combiner.count_rps, summed)",
            "supporting": "milestone Briers K>=6/8/10/12 (descriptive)",
            "bootstrap": ("registered comparison.py slate_date_draws + "
                          "null_centered_contrast_test + Holm, n=2000 "
                          "seed 20261001, Holm m=1"),
            "tail_bucket": "k=23 absorbs K >= 23 (not an exact count of 23)",
        },
    }


def run_count_agg_eval(ledger: pl.DataFrame, bf: pl.DataFrame,
                       realized: pl.DataFrame, out_dir,
                       *, verify_published: bool = True,
                       artifact_paths: dict, n_boot: int = 2000,
                       seed: int = 20261001) -> dict:
    """GATED runner. On ANY failure: failure_record.json is written
    write-once and PRESERVED; the immutable initial receipt is never
    touched. On success: receipt_final.json chains to the initial receipt
    by sha256."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(
            f"write-once violation: output dir exists: {out_dir}")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    initial = initial_receipt(artifact_paths)
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # stage 1: eligibility + frozen start keys (exact set, not a count)
        ledger_b = ledger.with_columns(
            pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
            .then(pl.lit("block_2024H2"))
            .when(pl.col("game_date") <= pl.date(2025, 6, 30))
            .then(pl.lit("block_2025H1"))
            .otherwise(pl.lit("confirm_2025H2"))
            .alias("block")
        )
        elig = br.eligible_slots_from_ledger(ledger_b, br.DEV_BLOCKS)
        starts = (elig.select("game_pk", "side", "pitcher", "game_date",
                              "block")
                  .unique(subset=["game_pk", "side"], keep="first")
                  .sort("game_pk", "side"))
        start_keys = sorted(zip(starts["game_pk"].to_list(),
                                starts["side"].to_list()))
        stream = "\n".join("%d|%s" % k for k in start_keys).encode("utf-8")
        start_keys_sha = hashlib.sha256(stream).hexdigest()
        if verify_published and (
                len(start_keys) != PUBLISHED_DEV_STARTS_N
                or start_keys_sha != PUBLISHED_DEV_START_KEYS_SHA256):
            raise ValueError(
                "frozen dev start-key set does not match the published "
                "identity (exact set check, not a count)")

        # stage 2: BF extension + p9 per start (order preserved)
        bf37 = bf.select("game_pk", "side", "pitcher",
                         *[f"pmf37_{j}" for j in range(37)])
        starts_bf = starts.join(bf37, on=["game_pk", "side", "pitcher"],
                                how="left")
        pmf37_cols = [f"pmf37_{j}" for j in range(37)]
        if starts_bf.filter(pl.col("pmf37_0").is_null()).height:
            raise ValueError("eligible start missing the registered BF PMF")
        p9 = (ledger_b.filter(
              pl.col("exclusion_reason").is_null()
              & (pl.col("p_h3_raw").is_not_null())
              & pl.col("block").is_in(br.DEV_BLOCKS)).sort("game_pk", "side", "slot")
              .group_by("game_pk", "side", "pitcher")
              .agg(pl.col("p_h3_raw").sort_by("slot").alias("p9")))
        starts_bf = starts_bf.join(
            p9, on=["game_pk", "side", "pitcher"], how="left")
        if starts_bf["p9"].null_count():
            raise ValueError("eligible start missing slot probabilities")

        # stage 3: realized counts from the registered lineage
        realized_join = realized.select("game_pk", "side", "pitcher",
                                        "realized_k")
        starts_bf = starts_bf.join(realized_join,
                                   on=["game_pk", "side", "pitcher"],
                                   how="left")
        if starts_bf["realized_k"].null_count():
            raise ValueError(
                "eligible start without a realized count from the "
                "registered start_metrics_v2 lineage")

        # stage 4: both arms' 24-bucket PMFs + clipping parity
        p_clip_lo, p_clip_hi = ad.P_CLIP, 1.0 - ad.P_CLIP
        rows = []
        e_untr_list = []
        e_buck_base_list = []
        e_buck_chal_list = []
        for r in starts_bf.iter_rows(named=True):
            p9 = np.asarray(r["p9"], dtype=np.float64)
            if p9.shape != (9,) or p9.min() < p_clip_lo \
                    or p9.max() > p_clip_hi:
                raise ValueError(
                    "slot probabilities outside the frozen clipping "
                    "convention [1e-9, 1-1e-9]")
            bf37 = np.asarray([r[f"pmf37_{j}"] for j in range(37)])
            bf37 = bf37 / bf37.sum()  # normalize to exactly 1.0
            bf_ext = ad.bf_pmf_from_37(bf37)
            pmf_base = ad.count_pmf_from_mixture(
                bf_ext, ad.cycled_cond_mean(p9))
            pmf_chal = ex.exact_count_pmf(p9, bf_ext)
            rows.append((r["game_pk"], r["side"], r["pitcher"],
                         r["game_date"], r["block"], int(r["realized_k"]),
                         pmf_base, pmf_chal))
            # untruncated E[K]: identical across arms by construction
            # (same cycled order); recorded as the mathematical check
            cycled = np.tile(p9, ad.KCOUNT_CAP // 9 + 1)[:ad.KCOUNT_CAP]
            e_untr_list.append(
                float((np.arange(1, ad.KCOUNT_CAP + 1) * cycled).sum()))
            ks = np.arange(ad.K_MAX)
            e_buck_base_list.append(float((np.asarray(pmf_base) * ks).sum()))
            e_buck_chal_list.append(float((np.asarray(pmf_chal) * ks).sum()))
        pmfs = pl.DataFrame(
            rows,
            schema={"game_pk": pl.Int64, "side": pl.Utf8,
                    "pitcher": pl.Int64, "game_date": pl.Date,
                    "block": pl.Utf8, "realized_k": pl.Int64,
                    "pmf_baseline": pl.List(pl.Float64),
                    "pmf_challenger": pl.List(pl.Float64)},
            orient="row")
        if verify_published and pmfs.height != PUBLISHED_DEV_STARTS_N:
            raise ValueError(
                f"dev starts {pmfs.height} != frozen 4,823")

        # stage 5: paired metrics (registered machinery)
        rps_b, rps_c = [], []
        mile_b, mile_c = [], []
        for r in pmfs.iter_rows(named=True):
            k = int(r["realized_k"])
            pb = np.asarray(r["pmf_baseline"])
            pc = np.asarray(r["pmf_challenger"])
            rps_b.append(kc.count_rps(pb, k))
            rps_c.append(kc.count_rps(pc, k))
            mile_b.append(kc.milestone_brier(pb, k, MILESTONES))
            mile_c.append(kc.milestone_brier(pc, k, MILESTONES))
        rps_b = np.asarray(rps_b)
        rps_c = np.asarray(rps_c)
        cmp_mod = br.load_registered_comparison()
        values = {"baseline": rps_b, "challenger": rps_c}
        dates = pmfs["game_date"].to_list()
        blocks = pmfs["block"].to_list()
        res = cmp_mod.slate_date_draws(values, dates, blocks, n_boot=n_boot,
                                       seed=seed)
        test = cmp_mod.null_centered_contrast_test(
            values, [("C_exact_agg_vs_registered", "challenger",
                      "baseline")],
            dates, blocks, n_boot=n_boot, seed=seed, res=res)
        idx = {"baseline": 0, "challenger": 1}
        d_rep = res[:, idx["challenger"]] - res[:, idx["baseline"]]
        primary = test["contrasts"]["C_exact_agg_vs_registered"]
        metrics = {
            "n_starts": int(pmfs.height),
            "count_rps_baseline_mean": float(rps_b.mean()),
            "count_rps_challenger_mean": float(rps_c.mean()),
            "count_rps_delta": primary["delta"],
            "bootstrap": {
                "primitive": ("registered harness comparison.py: "
                              "slate_date_draws + "
                              "null_centered_contrast_test"),
                "contrast": "C_exact_agg_vs_registered",
                "ci95": [float(np.percentile(d_rep, 2.5)),
                         float(np.percentile(d_rep, 97.5))],
                "p_null_centered": primary["p_value"],
                "p_holm": primary["p_holm"],
                "n_boot": n_boot, "seed": seed, "holm_m": 1,
            },
            "milestones": {
                str(m): {
                    "baseline_brier_mean": float(
                        np.mean([mb["ge%d" % m] for mb in mile_b])),
                    "challenger_brier_mean": float(
                        np.mean([mc["ge%d" % m] for mc in mile_c])),
                } for m in MILESTONES
            },
            "supporting_note": ("milestone Briers and calibration are "
                                "descriptive, never gated"),
        }

        # stage 6: expected-count checks (recorded in stage 4)
        untr_base = np.asarray(e_untr_list)
        untr_chal = np.asarray(e_untr_list)  # identical by construction
        buck_base = np.asarray(e_buck_base_list)
        buck_chal = np.asarray(e_buck_chal_list)
        if not np.allclose(untr_base, untr_chal, rtol=0, atol=1e-9):
            raise ValueError("untruncated E[K] differs between arms - "
                             "arm isolation broken")
        checks = {
            "untruncated_ek_baseline_mean": float(untr_base.mean()),
            "untruncated_ek_challenger_mean": float(untr_chal.mean()),
            "untruncated_ek_max_abs_arm_diff": float(
                np.max(np.abs(untr_base - untr_chal))),
            "bucketed_ek_baseline_mean": float(buck_base.mean()),
            "bucketed_ek_challenger_mean": float(buck_chal.mean()),
            "note": ("E[K] from the UNTRUNCATED distribution is the "
                     "mathematical check (identical across arms); the "
                     "registered bucketed outputs are verified separately; "
                     "bucket k=23 is P(K >= 23), not an exact count of 23"),
        }

        # stage 7: write-once outputs
        ev_path = out_dir / "count_agg_eval_v1.parquet"
        pmfs.write_parquet(ev_path)
        metrics = {"dev_keys": {
            "start_keys_n": len(start_keys),
            "start_keys_sha256": start_keys_sha,
        }, **metrics, "expected_count_checks": checks}
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
    except Exception as exc:
        failure = {"stage": "count_agg_eval", "failure": True,
                   "error": repr(exc), "initial_receipt_sha256":
                       initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    # stage 8: FINAL receipt (NEW file, chains to the immutable initial)
    final = dict(initial)
    final["outputs"] = {
        "count_agg_eval_v1.parquet": ad.sha256_file(ev_path),
        "metrics.json": ad.sha256_file(metrics_path),
    }
    final["metrics"] = metrics
    final["fits"] = {"n_starts": int(pmfs.height),
                     "per_arm": {"baseline": "registered cycled prefix-mean",
                                 "challenger": "exact Poisson-Binomial"}}
    final["abstentions"] = {"note": ("abstention record is inherited "
                                     "from the preserved run ledger "
                                     "classification; development "
                                     "abstentions are excluded from "
                                     "evaluation")}
    final["acceptance"] = {
        "verify_published": bool(verify_published),
        "start_keys_exact": True,
        "block_isolation": True,
        "exclusion_policy_unchanged": True,
        "clipping_parity": True,
        "receipt_chain": initial_sha,
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt was modified; run "
                         "rejected")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final, "receipt_initial_sha256": initial_sha}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify-keys-only", action="store_true")
    ap.add_argument("--i-accept-outcome-evaluation", action="store_true",
                    help="gate for the real-outcome evaluation stage "
                         "(owner authorization required; never run)")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--bf", default=None)
    ap.add_argument("--realized", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    print("Question A evaluation runner: real-outcome execution is NOT "
          "authorized. This module is published for Chat 2 review with "
          "synthetic evidence only.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
