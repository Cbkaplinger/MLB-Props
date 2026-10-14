"""PA aggregation A/B/C scored runner (contract + Amendment 1 + CORRECTION-1).

ONE canonical scored run on the 4,446 canonical kcount-integration eval
starts, IDENTICAL rows and IDENTICAL BF PMFs across arms:
   A (I1_ref) = scalar-rate/binomial reference: frozen kcount-integration
       I1 structure - scalar log5 p* (league-average batter, the canonical
       p_bar_l1 = w=150 shrunk pitcher rate, pa-k convention) + BF PMF +
       binomial mixture via kcount_combiner.combine_count. NOT the retained
       I3b recipe (see CORRECTION-1 note; no I3b superiority claim).
   A_v1 = CORRECTION-1 sensitivity arm: same BF PMFs, scalar shrunk pitcher
       rate built from the exact pa_completed_v1 priors used by B/C.
   B = matchup-mean binomial: p_bar_n = mean of the first n cycled
       9-slot oracle-lineup log5 probabilities.
   C = matchup Poisson-binomial: exact incremental DP over the same p_i.
ORACLE-LINEUP DIAGNOSTIC: mode-3 realized initial lineups; non-deployable.
Primary family {B-A, C-B, C-A}; paired count-RPS; Holm; seed 20261001.
Sensitivity family {B-A_v1, A_v1-A}: post-review development sensitivity,
separate Holm, never merged with the primary family (CORRECTION-1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import pa_lgbm_scaffold as sc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_pa_lgbm_comparison as base  # noqa: E402

W = sc.W_SHRINK
K_MAX = 24
CAP = kc.KCOUNT_CAP
KC_DIR = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
              r"\kcount-integration-20261008_152747")
BF_DIR = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
              r"\workload-training-policy-20261007_090000")
SEED = 20261001
MEAN_TOL = 1e-9


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pb_pmf_seq(p_seq: np.ndarray) -> np.ndarray:
    """Exact Poisson-binomial distribution over 0..len(p_seq)."""
    n = len(p_seq)
    dist = np.zeros(n + 1)
    dist[0] = 1.0
    for i in range(n):
        p = min(max(float(p_seq[i]), 0.0), 1.0)
        new = np.zeros(i + 2)
        new[:i + 1] = dist[:i + 1] * (1.0 - p)
        new[1:i + 2] += dist[:i + 1] * p
        dist[:i + 2] = new
    return dist


def map24(dist: np.ndarray) -> np.ndarray:
    """Uncollapsed 0..n distribution -> canonical 24-bucket support."""
    out = np.zeros(K_MAX)
    for k in range(min(len(dist), K_MAX)):
        out[k] += dist[k]
    if len(dist) > K_MAX:
        out[K_MAX - 1] += float(dist[K_MAX:].sum())
    return out


def mixture_b(bf_ext: np.ndarray, seq: np.ndarray,
              means_out: list | None = None) -> np.ndarray:
    out = np.zeros(K_MAX)
    csum = np.cumsum(seq)
    for idx in range(CAP):
        mass = bf_ext[idx]
        if mass <= 0.0:
            continue
        n = idx + 1
        p_bar = float(csum[idx] / n)
        # full conditional on 0..n (no truncation); tail mapped to the
        # >=23 absorbing bucket by map24, matching C's construction.
        # n=0 unreachable (idx>=0 -> n>=1); p=0/1 handled by the builder.
        full = kc.binom_pmf(np.arange(n + 1), n, p_bar)
        if means_out is not None:
            # gate A: expectation from the ACTUAL uncollapsed conditional
            # via fsum (acc summation error removed)
            means_out.append((n, math.fsum(
                (np.arange(n + 1) * full).tolist())))
        out += mass * map24(full)
    out[K_MAX - 1] += max(0.0, 1.0 - out.sum())
    return out


def mixture_c(bf_ext: np.ndarray, seq: np.ndarray,
              means_out: list | None = None) -> np.ndarray:
    out = np.zeros(K_MAX)
    dist = np.zeros(CAP + 1)
    dist[0] = 1.0
    for idx in range(CAP):
        p = min(max(float(seq[idx]), 0.0), 1.0)
        new = np.zeros(idx + 2)
        new[:idx + 1] = dist[:idx + 1] * (1.0 - p)
        new[1:idx + 2] += dist[:idx + 1] * p
        dist[:idx + 2] = new
        mass = bf_ext[idx]
        if mass > 0.0:
            if means_out is not None:
                # gate A: expectation from the ACTUAL uncollapsed DP state
                # (before tail mapping), support 0..n
                ks = np.arange(idx + 2)
                means_out.append((idx + 1, float((ks * dist[:idx + 2]).sum())))
            out += mass * map24(dist[:idx + 2])
    out[K_MAX - 1] += max(0.0, 1.0 - out.sum())
    return out


def assert_mean_gate(bf_ext: np.ndarray, seq: np.ndarray,
                     means_b: list, means_c: list,
                     tol: float = MEAN_TOL) -> None:
    """Gate A: per supported n (including coverage of every n with BF
    mass), mu_B and mu_C (computed from the actual uncollapsed PMFs) must
    agree with each other and with sum(p_1..p_n). Explicit exceptions,
    never silent; probability mass is checked separately and never
    normalized away."""
    csum = np.cumsum(seq)
    n_supported = {int(i) + 1 for i in range(CAP) if bf_ext[i] > 0.0}
    if len(means_b) != len(n_supported) or len(means_c) != len(n_supported):
        raise RunFailure("mean gate: supported-n coverage mismatch "
                         "(%d/%d checked vs %d supported)"
                         % (len(means_b), len(means_c), len(n_supported)))
    for (nb, mu_b), (nc, mu_c) in zip(means_b, means_c):
        if nb != nc or nb not in n_supported:
            raise RunFailure("mean gate: n mismatch %d/%d" % (nb, nc))
        target = float(csum[nb - 1])
        if abs(mu_b - target) > tol or abs(mu_c - target) > tol \
                or abs(mu_b - mu_c) > tol:
            raise RunFailure(
                "mean gate failed at n=%d: mu_B=%.12f mu_C=%.12f "
                "sum_p=%.12f" % (nb, mu_b, mu_c, target))


def check_mass(pmf: np.ndarray, label: str) -> None:
    """Separate mass check: never normalize away errors."""
    if abs(float(np.asarray(pmf).sum()) - 1.0) > 1e-9:
        raise RunFailure("mass check failed for %s: sum=%r"
                         % (label, float(np.asarray(pmf).sum())))


def row_seq9(p_p: float, bks: list, bns: list, lg: float,
             w: float = W) -> np.ndarray:
    """Factored rate-sequence construction (own pitcher prior + own
    lineup batters + league rate only; opposing-starter identity cannot
    enter)."""
    seq9 = np.zeros(9)
    for j in range(9):
        kb, nb = int(bks[j]), int(bns[j])
        p_b = (kb + w * lg) / (nb + w) if nb > 0 else lg
        z = (np.log(p_p / (1 - p_p))
             + np.log(p_b / (1 - p_b)) - np.log(lg / (1 - lg)))
        seq9[j] = 1.0 / (1.0 + np.exp(-z))
    return seq9


def assert_no_slot_conflicts(init: pl.DataFrame) -> int:
    """Gate: reject conflicting duplicate lineup slots (same slot,
    different batter) BEFORE deduplication; returns conflict count (0)."""
    slot_conf = (init.group_by(["game_pk", "bat_team", "lineup_slot"])
                 .agg(pl.col("batter").n_unique().alias("nb")))
    n_conf = int((slot_conf["nb"] > 1).sum())
    if n_conf:
        raise RunFailure(
            "lineup slot conflict: %d (game_pk,bat_team,slot) groups "
            "carry multiple distinct batters" % n_conf)
    return n_conf


def cond24_binom(n: int, p: float) -> np.ndarray:
    return kc.binom_pmf(np.arange(0, K_MAX), n, p)


def preflight(preds: pl.DataFrame, label23: pl.DataFrame,
              joined: pl.DataFrame) -> dict:
    n_unique_pa = label23.select(
        pl.struct(["game_pk", "at_bat_number"]).n_unique()).item()
    keys = preds.select(["game_pk", "pitcher"]).unique()
    ledger = {
        "n_eval_rows": int(preds.height),
        "n_unique_game_pitcher": int(keys.height),
        "n_joined_rows": int(joined.height),
        "join_expansion": int(joined.height - preds.height),
        "n_duplicate_eval_keys": int(preds.height - keys.height),
        "n_unique_pa_2023_label": int(n_unique_pa),
        "n_label_duplicate_pa": int(label23.height - n_unique_pa),
    }
    if ledger["join_expansion"] != 0 or ledger["n_duplicate_eval_keys"] != 0 \
            or ledger["n_label_duplicate_pa"] != 0:
        raise RunFailure("preflight guard failed: %s" % ledger)
    return ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    ap.add_argument("--kc-dir", default=None)
    ap.add_argument("--bf-dir", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kc_dir = Path(args.kc_dir) if args.kc_dir else KC_DIR
    bf_dir = Path(args.bf_dir) if args.bf_dir else BF_DIR
    try:
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        preds = pl.read_csv(kc_dir / "predictions.csv")
        bf = pl.read_parquet(bf_dir / "pmfs.parquet")
        if bf.height != preds.height:
            raise RunFailure("BF pmf row count mismatch")
        bf_np = bf.select(sorted(c for c in bf.columns
                                 if c.startswith("pmfB_"))).to_numpy()
        pk_i1 = (pl.read_parquet(kc_dir / "pmfs.parquet")
                 .select(["pkI1_%02d" % k for k in range(K_MAX)])
                 .to_numpy())
        bg = pl.read_parquet(root / "processed" / "batter_games.parquet")
        raw23 = pl.read_parquet(
            root / "Savant-Data" / "regular" / "2023"
            / "statcast_2023_regular.parquet")
        raw22 = pl.read_parquet(
            root / "Savant-Data" / "regular" / "2022"
            / "statcast_2022_regular.parquet")
        label23 = sc.build_pa_label_table(raw23)
        pooled_label = pl.concat([sc.build_pa_label_table(raw22), label23],
                                 how="vertical")

        # lineups (gate C receipt re-asserted in-runner)
        init = bg.filter((pl.col("is_initial_lineup") == 1)
                         & pl.col("lineup_slot").is_not_null())
        # CORRECTION-1 gate: reject conflicting duplicate lineup slots
        # (same slot, different batter) BEFORE deduplication (helper C).
        assert_no_slot_conflicts(init)
        slots = (init.select(["game_pk", "bat_team", "lineup_slot",
                              "batter"])
                 .unique(["game_pk", "bat_team", "lineup_slot"],
                         keep="last")
                 .sort(["game_pk", "bat_team", "lineup_slot"]))
        bad = (slots.group_by(["game_pk", "bat_team"])
               .agg(pl.len().alias("n"),
                    pl.col("lineup_slot").n_unique().alias("nu"))
               .filter((pl.col("n") != 9) | (pl.col("nu") != 9)))
        if bad.height:
            raise RunFailure("lineup gate failed: %d team-games"
                             % bad.height)
        arr = (slots.group_by(["game_pk", "bat_team"])
               .agg(pl.col("batter").alias("batters")))
        joined = preds.join(arr, left_on=["game_pk", "batting_team"],
                            right_on=["game_pk", "bat_team"], how="left")
        ledger = preflight(preds, label23, joined)
        if joined["batters"].is_null().any():
            raise RunFailure("missing lineup rows")
        print("preflight ok:", {k: ledger[k] for k in (
            "n_eval_rows", "join_expansion", "n_duplicate_eval_keys")})

        # priors (pa_completed_v1, strictly prior dates)
        keys = sc.pitcher_snapshot_keys(
            preds.select(["game_pk", "game_date", "pitcher"]).unique())
        pp = (keys.join(sc.pitcher_rate_priors(pooled_label, keys),
                        on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
              .with_columns([pl.col("k_prior").fill_null(0).cast(pl.Int64),
                             pl.col("n_prior").fill_null(0).cast(pl.Int64)]))
        joined = joined.join(
            pp.select(["key_game_pk", "pitcher", "k_prior", "n_prior"]),
            left_on=["game_pk", "pitcher"],
            right_on=["key_game_pk", "pitcher"], how="left")
        bexp = (joined.with_row_index("row_idx")
                .explode("batters")
                .select(["row_idx", "batters", "game_date"])
                .with_columns(pl.col("game_date").cast(pl.Date)
                              .alias("game_date")))
        bpr = base.batter_rate_priors_fast(
            pooled_label,
            bexp.select(pl.col("batters").alias("batter"),
                        pl.col("game_date").alias("cutoff_date"))
            .unique())
        bexp = bexp.join(bpr, left_on=["batters", "game_date"],
                         right_on=["batter", "cutoff_date"], how="left")
        lists = bexp.group_by("row_idx").agg(
            pl.col("b_k_prior").alias("bks"), pl.col("b_n_prior").alias("bns"))
        joined = joined.with_row_index("row_idx").join(
            lists, on="row_idx", how="left")
        # lg per origin
        origins = preds.select(["origin", "game_date"]).unique().sort(
            "game_date")
        lg_map = {}
        for r in origins.iter_rows(named=True):
            o = date.fromisoformat(str(r["origin"])[:10])
            prior = pooled_label.filter(
                (pl.col("pa_class") == sc.CLASS_COMPLETED)
                & (pl.col("game_date") < o))
            lg_map[str(r["origin"])] = float(prior["y"].mean())

        rows_out = []
        repro_max = 0.0
        for i, r in enumerate(joined.iter_rows(named=True)):
            bf37 = bf_np[i]
            if abs(bf37.sum() - 1.0) > 1e-9:
                raise RunFailure("BF37 mass %r at row %d" % (bf37.sum(), i))
            bf_ext = kc.bf_pmf_from_37(bf37)
            lg = lg_map[str(r["origin"])[:10]]
            kp, npit = r["k_prior"], r["n_prior"]
            p_p = (kp + W * lg) / (npit + W) if npit > 0 else lg
            bks = r["bks"]
            bns = r["bns"]
            seq9 = row_seq9(p_p, bks, bns, lg, W)
            seq = np.tile(seq9, CAP // 9 + 1)[:CAP]
            p_v1 = (kp + W * lg) / (npit + W) if npit > 0 else lg
            pkA = kc.combine_count(bf_ext, float(r["p_bar_l1"]), K_MAX)
            pkAv1 = kc.combine_count(bf_ext, float(p_v1), K_MAX)
            means_b, means_c = [], []
            pkB = mixture_b(bf_ext, seq, means_b)
            pkC = mixture_c(bf_ext, seq, means_c)
            # Gate A: real PMF expectations vs sum(p_1..p_n), explicit
            assert_mean_gate(bf_ext, seq, means_b, means_c)
            check_mass(pkA, "A"); check_mass(pkAv1, "A_v1")
            check_mass(pkB, "B"); check_mass(pkC, "C")
            # reproduction gate vs stored canonical I1
            stored = pk_i1[i]
            repro_max = max(repro_max, float(np.abs(pkA - stored).max()))
            K = int(r["K"])
            rec = {"row_idx": i, "K": K,
                   "game_date": str(r["game_date"]),
                   "PA": int(r["PA"]),
                   "oracle_lineup": True,
                   "input_status": "i1_ref_p_bar_l1+bf_pmfs+v1_priors",
                   "lineup_status": "oracle_mode3_initial",
                   "n_prior_pitcher": int(npit),
                   "rps_A": kc.count_rps(pkA, K),
                   "rps_Av1": kc.count_rps(pkAv1, K),
                   "rps_B": kc.count_rps(pkB, K),
                   "rps_C": kc.count_rps(pkC, K),
                   "ls_A": kc.count_logscore(pkA, K),
                   "ls_Av1": kc.count_logscore(pkAv1, K),
                   "ls_B": kc.count_logscore(pkB, K),
                   "ls_C": kc.count_logscore(pkC, K),
                   "mA": float((np.arange(K_MAX) * pkA).sum()),
                   "mAv1": float((np.arange(K_MAX) * pkAv1).sum()),
                   "mB": float((np.arange(K_MAX) * pkB).sum()),
                   "mC": float((np.arange(K_MAX) * pkC).sum()),
                   "p_bar_l1": float(r["p_bar_l1"]),
                   "p_v1": float(p_v1),
                   "denom_gap": float(p_v1 - float(r["p_bar_l1"])),
                   "xK_diff_CB": float((np.arange(K_MAX)
                                        * (pkC - pkB)).sum()),
                   "mean_p9": float(seq9.mean()),
                   "var_gap": float(np.sum((seq9 - seq9.mean()) ** 2) / 9.0),
                   }
            for m in (6, 8, 10, 12):
                rec["mb%d_A" % m] = kc.milestone_brier(pkA, K)["ge%d" % m]
                rec["mb%d_Av1" % m] = kc.milestone_brier(pkAv1, K)["ge%d" % m]
                rec["mb%d_B" % m] = kc.milestone_brier(pkB, K)["ge%d" % m]
                rec["mb%d_C" % m] = kc.milestone_brier(pkC, K)["ge%d" % m]
            rows_out.append(rec)
            if i % 1000 == 0:
                print("scored %d/%d" % (i, joined.height))
        if repro_max > 1e-9:
            raise RunFailure("canonical A reproduction failed: max diff %g"
                             % repro_max)
        print("canonical A reproduction vs stored I1: max diff %.2e"
              % repro_max)

        res = pl.DataFrame(rows_out)
        res.write_csv(out_dir / "predictions_abc.csv")
        dates = res["game_date"].to_numpy().astype(str)

        def paired(col_chal, col_ref):
            d = res[col_chal].to_numpy() - res[col_ref].to_numpy()
            return base.cluster_bootstrap_p(d, dates)

        fam = {"B-A": paired("rps_B", "rps_A"),
               "C-B": paired("rps_C", "rps_B"),
               "C-A": paired("rps_C", "rps_A")}
        holm = base.holm({k: v["p_two_sided"] for k, v in fam.items()})
        # CORRECTION-1 sensitivity family (frozen in CORRECTION-1 note):
        # separate Holm; never merged with the primary family.
        fam2 = {"B-A_v1": paired("rps_B", "rps_Av1"),
                "A_v1-A": paired("rps_Av1", "rps_A")}
        holm2 = base.holm({k: v["p_two_sided"] for k, v in fam2.items()})
        denom = {
            "n": int(res.height),
            "mean_abs_gap": float(res["denom_gap"].abs().mean()),
            "p90_abs_gap": float(res["denom_gap"].abs().quantile(0.9)),
            "max_abs_gap": float(res["denom_gap"].abs().max()),
            "n_gt_0p01": int((res["denom_gap"].abs() > 0.01).sum()),
            "by_origin_mean_gap": {
                str(k): float(v) for k, v in
                res.group_by("game_date").agg(
                    pl.col("denom_gap").mean())
                .sort("game_date").iter_rows()},
        }
        meanll = {"A": float(res["ls_A"].mean()),
                  "B": float(res["ls_B"].mean()),
                  "C": float(res["ls_C"].mean())}
        mae = {"A": float((res["mA"] - res["K"]).abs().mean()),
               "B": float((res["mB"] - res["K"]).abs().mean()),
               "C": float((res["mC"] - res["K"]).abs().mean())}
        bias = {"A": float((res["mA"] - res["K"]).mean()),
                "B": float((res["mB"] - res["K"]).mean()),
                "C": float((res["mC"] - res["K"]).mean())}
        slices = {}
        for name, mask in (("short_outing", res["PA"] < 9),
                           ("september", res["game_date"] >= "2023-09-01"),
                           ("debut_n_prior_0", res["n_prior_pitcher"] == 0),
                           ("sparse_history_lt150",
                            (res["n_prior_pitcher"] > 0)
                            & (res["n_prior_pitcher"] < 150))):
            sub = res.filter(mask)
            slices[name] = {
                "n": int(sub.height),
                "mean_rps": {"A": float(sub["rps_A"].mean()),
                             "A_v1": float(sub["rps_Av1"].mean()),
                             "B": float(sub["rps_B"].mean()),
                             "C": float(sub["rps_C"].mean())}}
        summary = {
            "n": int(res.height),
            "mean_rps": {"A": float(res["rps_A"].mean()),
                         "A_v1": float(res["rps_Av1"].mean()),
                         "B": float(res["rps_B"].mean()),
                         "C": float(res["rps_C"].mean())},
            "paired": fam, "holm": holm,
            "sensitivity_family": {
                "label": "post-review development sensitivity "
                         "(CORRECTION-1; not promotion evidence; "
                         "separate Holm; original p-values not reused)",
                "paired": fam2, "holm": holm2},
            "denominator_comparison": denom,
            "count_logscore": meanll,
            "xK_mae": mae, "xK_bias": bias,
            "xK_diff_CB_mean": float(res["xK_diff_CB"].mean()),
            "xK_diff_CB_abs_max": float(res["xK_diff_CB"].abs().max()),
            "milestone_brier": {
                m: {"A": float(res["mb%d_A" % m].mean()),
                    "B": float(res["mb%d_B" % m].mean()),
                    "C": float(res["mb%d_C" % m].mean())}
                for m in (6, 8, 10, 12)},
            "slices": slices,
            "preflight": ledger,
            "oracle_lineup_label": (
                "mode-3 ORACLE realized initial lineups; NON-DEPLOYABLE; "
                "no oracle-lineup result can authorize promotion"),
        }
        manifest = {
            "lane": "pa_aggregation_abc",
            "status": "COMPLETE",
            "correction": "CORRECTION-1 linked (baseline renamed I1_ref; "
                          "A_v1 sensitivity arm; gates added); original "
                          "run pa-aggregation-abc-20261009_173155 "
                          "preserved untouched",
            "contract": "research/offseason_2026/"
                        "pa-aggregation-contract-2026-10-09.md "
                        "(Amendment 1; CORRECTION-1: baseline identity, "
                        "sensitivity spec, gates)",
            "primary": "paired count-RPS, Holm family {B-A, C-B, C-A}, "
                       "slate-date bootstrap 2000 seed 20261001",
            "support": "0..22 exact + >=23 absorbing (combine_count "
                       "k_max=24); BF extended 1..60 via bf_pmf_from_37",
            "arms": {"A": "I1_ref scalar-rate/binomial reference "
                          "(frozen kcount-integration I1 structure; NOT "
                          "retained I3b; no I3b superiority claim)",
                     "A_v1": "sensitivity: scalar shrunk pitcher rate "
                             "from exact v1 priors (same BF PMFs)",
                     "B": "matchup-mean binomial (cycled lineup)",
                     "C": "Poisson-binomial (same sequence)"},
            "retained_i3b_note": (
                "Retained I3b research recipe = hazard BF PMF + binomial "
                "combiner + log5 scalar (as scored in the 2024 workload "
                "transfer); construction documented in CORRECTION-1; no "
                "I3b comparison is run here and no new fitting is done"),
            "canonical_reproduction_max_diff": repro_max,
            "gates": {"mean_equality_tol": MEAN_TOL,
                      "lineup_slot_conflicts_rejected": True,
                      "input_roots_parameterized": True},
            "inputs": {
                "predictions": sha256_file(kc_dir / "predictions.csv"),
                "stored_count_pmfs": sha256_file(kc_dir / "pmfs.parquet"),
                "bf_pmfs": sha256_file(bf_dir / "pmfs.parquet"),
                "batter_games": sha256_file(root / "processed"
                                            / "batter_games.parquet"),
                "savant_2023": "verified known sha",
                "savant_2022": "verified known sha",
            },
            "no_2025_2026_access": True,
            "results": summary,
            "code": {p.name: sha256_file(p) for p in [
                HERE / "run_pa_aggregation_abc.py",
                HERE / "kcount_combiner.py"]},
        }
        (out_dir / "pa_aggregation_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps(summary["mean_rps"], indent=1))
        for k, g in holm.items():
            pr = fam[k]
            print("  %s: est %.6f CI [%.6f, %.6f] p_adj %.4f%s" % (
                k, pr["estimate"], pr["lo95"], pr["hi95"], g["p_adj"],
                " *" if g["significant"] else ""))
        print("WROTE %s" % out_dir)
        return 0
    except (RunFailure, rch.MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
