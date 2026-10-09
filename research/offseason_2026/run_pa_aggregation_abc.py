"""PA aggregation A/B/C scored runner (pa-aggregation-contract-2026-10-09 + Amendment 1).

ONE canonical scored run on the 4,446 canonical kcount-integration eval
starts, IDENTICAL rows and IDENTICAL BF PMFs across arms:
  A = canonical I3b reconstruction: scalar log5 p* (league-average batter,
      the canonical p_bar_l1) + BF PMF + binomial mixture via
      kcount_combiner.combine_count (support 0..22, >=23 absorbing).
  B = matchup-mean binomial: p_bar_n = mean of the first n cycled
      9-slot oracle-lineup log5 probabilities.
  C = matchup Poisson-binomial: exact incremental DP over the same p_i.
ORACLE-LINEUP DIAGNOSTIC: mode-3 realized initial lineups; non-deployable.
Family {B-A, C-B, C-A}; paired count-RPS; Holm; seed 20261001.
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


def mixture_b(bf_ext: np.ndarray, seq: np.ndarray) -> np.ndarray:
    out = np.zeros(K_MAX)
    csum = np.cumsum(seq)
    for idx in range(CAP):
        mass = bf_ext[idx]
        if mass <= 0.0:
            continue
        n = idx + 1
        p_bar = float(csum[idx] / n)
        out += mass * cond24_binom(n, p_bar)
    out[K_MAX - 1] += max(0.0, 1.0 - out.sum())
    return out


def mixture_c(bf_ext: np.ndarray, seq: np.ndarray) -> np.ndarray:
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
            out += mass * map24(dist[:idx + 2])
    out[K_MAX - 1] += max(0.0, 1.0 - out.sum())
    return out


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
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        preds = pl.read_csv(KC_DIR / "predictions.csv")
        bf = pl.read_parquet(BF_DIR / "pmfs.parquet")
        if bf.height != preds.height:
            raise RunFailure("BF pmf row count mismatch")
        bf_np = bf.select(sorted(c for c in bf.columns
                                 if c.startswith("pmfB_"))).to_numpy()
        pk_i1 = (pl.read_parquet(KC_DIR / "pmfs.parquet")
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
            seq9 = np.zeros(9)
            for j in range(9):
                kb, nb = int(bks[j]), int(bns[j])
                p_b = (kb + W * lg) / (nb + W) if nb > 0 else lg
                z = (np.log(p_p / (1 - p_p))
                     + np.log(p_b / (1 - p_b)) - np.log(lg / (1 - lg)))
                seq9[j] = 1.0 / (1.0 + np.exp(-z))
            seq = np.tile(seq9, CAP // 9 + 1)[:CAP]
            pkA = kc.combine_count(bf_ext, float(r["p_bar_l1"]), K_MAX)
            pkB = mixture_b(bf_ext, seq)
            pkC = mixture_c(bf_ext, seq)
            # reproduction gate vs stored canonical I1
            stored = pk_i1[i]
            repro_max = max(repro_max, float(np.abs(pkA - stored).max()))
            K = int(r["K"])
            rec = {"row_idx": i, "K": K,
                   "game_date": str(r["game_date"]),
                   "PA": int(r["PA"]),
                   "rps_A": kc.count_rps(pkA, K),
                   "rps_B": kc.count_rps(pkB, K),
                   "rps_C": kc.count_rps(pkC, K),
                   "ls_A": kc.count_logscore(pkA, K),
                   "ls_B": kc.count_logscore(pkB, K),
                   "ls_C": kc.count_logscore(pkC, K),
                   "mA": float((np.arange(K_MAX) * pkA).sum()),
                   "mB": float((np.arange(K_MAX) * pkB).sum()),
                   "mC": float((np.arange(K_MAX) * pkC).sum()),
                   "xK_diff_CB": float((np.arange(K_MAX)
                                        * (pkC - pkB)).sum()),
                   "p_bar_l1": float(r["p_bar_l1"]),
                   "mean_p9": float(seq9.mean()),
                   "var_gap": float(np.sum((seq9 - seq9.mean()) ** 2) / 9.0),
                   }
            for m in (6, 8, 10, 12):
                rec["mb%d_A" % m] = kc.milestone_brier(pkA, K)["ge%d" % m]
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
                           ("september", res["game_date"] >= "2023-09-01")):
            sub = res.filter(mask)
            slices[name] = {
                "n": int(sub.height),
                "mean_rps": {"A": float(sub["rps_A"].mean()),
                             "B": float(sub["rps_B"].mean()),
                             "C": float(sub["rps_C"].mean())}}
        summary = {
            "n": int(res.height),
            "mean_rps": {"A": float(res["rps_A"].mean()),
                         "B": float(res["rps_B"].mean()),
                         "C": float(res["rps_C"].mean())},
            "paired": fam, "holm": holm,
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
            "contract": "research/offseason_2026/"
                        "pa-aggregation-contract-2026-10-09.md "
                        "(Amendment 1: support 0..22 + >=23; frozen "
                        "decision rule)",
            "primary": "paired count-RPS, Holm family {B-A, C-B, C-A}, "
                       "slate-date bootstrap 2000 seed 20261001",
            "support": "0..22 exact + >=23 absorbing (combine_count "
                       "k_max=24); BF extended 1..60 via bf_pmf_from_37",
            "arms": {"A": "canonical I3b scalar p_bar_l1 binomial",
                     "B": "matchup-mean binomial (cycled lineup)",
                     "C": "Poisson-binomial (same sequence)"},
            "canonical_reproduction_max_diff": repro_max,
            "equal_mean_note": "C-B pre-collapse E[K|n] equal by "
                               "construction (same sequence); asserted "
                               "per row via xK_diff_CB (post-collapse "
                               "residual reported)",
            "inputs": {
                "predictions": sha256_file(KC_DIR / "predictions.csv"),
                "stored_count_pmfs": sha256_file(KC_DIR / "pmfs.parquet"),
                "bf_pmfs": sha256_file(BF_DIR / "pmfs.parquet"),
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
