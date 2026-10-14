"""Versioned correction of run_bf_ab_score.py reporting (scoring v2).

Defect in v1: the `actual_K` reporting dict was keyed by game_pk only, so rows
sharing a game_pk overwrote each other (54/134 entries reported the wrong
pitcher's K). The scored statistics (rps/logscore/MAE/bias) were computed from
the per-(game_pk, pitcher) joined vector and were always correct.

This script re-runs the identical join + metric code with the reporting dict
keyed by "game_pk|pitcher", verifies the recomputed statistics match the v1
report exactly, and writes scoring_report_v2.json. The v1 output directory is
never touched.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np, polars as pl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kcount_combiner as kc


def actual_K_by_pitcher(lab: pl.DataFrame, keys: list) -> dict:
    """Build the reporting dict keyed by (game_pk, pitcher).

    lab: grouped frame with columns [game_pk, pitcher, K] (one row per
    pitcher-game, as produced by run_bf_ab_score.py). keys: the seal package
    row_keys entries. Key format is "game_pk|pitcher".
    """
    lut = {
        (int(r["game_pk"]), int(r["pitcher"])): int(r["K"])
        for r in lab.iter_rows(named=True)
    }
    out = {}
    for k in keys:
        key = "%s|%s" % (k["game_pk"], k["pitcher"])
        out[key] = lut[(int(k["game_pk"]), int(k["pitcher"]))]
    return out


def actual_K_by_game_pk_only(keys: list, per_pitcher: dict) -> dict:
    """Reproduce the v1 (defective) keying: last row per game_pk wins."""
    out = {}
    for k in keys:
        out[str(k["game_pk"])] = per_pitcher["%s|%s" % (k["game_pk"], k["pitcher"])]
    return out


def compute_stats(seal_dir: Path, data_root: Path):
    A = np.load(seal_dir / "arm_A_pmf.npy")
    B = np.load(seal_dir / "arm_B_pmf.npy")
    keys = json.load(open(seal_dir / "row_keys.json"))
    raw = pl.read_parquet(
        Path(data_root) / "Savant-Data" / "regular" / "2026"
        / "statcast_2026_regular.parquet")
    lab = raw.group_by(["game_pk", "pitcher"]).agg(
        pl.col("events").is_in(["strikeout", "strikeout_double_play"])
        .sum().alias("K"))
    j = pl.DataFrame({"game_pk": [k["game_pk"] for k in keys],
                      "pitcher": [k["pitcher"] for k in keys]}).join(
        lab, on=["game_pk", "pitcher"], how="left")
    unmatched = int(j["K"].is_null().sum())
    assert unmatched == 0, "unmatched rows: %d" % unmatched
    n = len(keys)
    assert j.height == n == A.shape[0] == B.shape[0] == 134
    K = j["K"].to_numpy().astype(int)
    rpsA = np.array([kc.count_rps(A[i], K[i]) for i in range(n)])
    rpsB = np.array([kc.count_rps(B[i], K[i]) for i in range(n)])
    dates = np.array([k["forecast_cutoff"][:10] for k in keys])
    fb = np.array([k["arm_B_status"].startswith("A_fallback") for k in keys])

    def boot(mask):
        d = rpsB[mask] - rpsA[mask]
        ds = dates[mask]
        uds = np.unique(ds)
        rng = np.random.default_rng(20261001)
        boots = np.empty(2000)
        for b in range(2000):
            pick = rng.choice(uds, size=len(uds), replace=True)
            idx = np.concatenate([np.where(ds == u)[0] for u in pick])
            boots[b] = d[idx].mean()
        lo, hi = np.percentile(boots, [2.5, 97.5])
        return {"est": float(d.mean()), "lo95": float(lo), "hi95": float(hi),
                "n": int(mask.sum()), "n_dates": int(len(uds))}

    usable = ~fb
    sec = {}
    for name, P in (("A", A), ("B", B)):
        ks = np.arange(24)
        meanK = (P * ks).sum(axis=1)
        sec[name] = {
            "logscore": float(np.mean([-np.log(max(P[i, K[i]], 1e-12))
                                       for i in range(n)])),
            "meanK_mae": float(np.mean(np.abs(meanK - K))),
            "meanK_bias": float(np.mean(meanK - K))}
    per_pitcher = actual_K_by_pitcher(lab, keys)
    by_game = actual_K_by_game_pk_only(keys, per_pitcher)
    wrong = sum(1 for k in keys
                if by_game[str(k["game_pk"])]
                != per_pitcher["%s|%s" % (k["game_pk"], k["pitcher"])])
    return {
        "population_all": boot(np.ones(n, bool)),
        "population_usable_B": boot(usable),
        "secondary": sec,
        "actual_K": per_pitcher,
        "v1_actual_K_by_game_pk": by_game,
        "rows_with_wrong_v1_value": int(wrong),
        "unmatched": unmatched,
        "n_rows": n,
        "note": "usable-B subset has 11 rows; bootstrap cannot create independent evidence",
    }


def verify_against_v1(v2: dict, v1_report: dict) -> dict:
    """Compare every reported statistic; require exact (0.0) agreement."""
    diffs = {}
    for sec_name in ("population_all", "population_usable_B"):
        for stat in ("est", "lo95", "hi95"):
            diffs["%s.%s" % (sec_name, stat)] = abs(
                v2[sec_name][stat] - v1_report[sec_name][stat])
    for arm in ("A", "B"):
        for stat in ("logscore", "meanK_mae", "meanK_bias"):
            diffs["secondary.%s.%s" % (arm, stat)] = abs(
                v2["secondary"][arm][stat] - v1_report["secondary"][arm][stat])
    max_diff = max(diffs.values())
    return {
        "v1_report": "C:\\Users\\ckaplinger\\MLB-Props-Research\\bf-ab-score-2026\\scoring_report.json",
        "stat_diffs_abs": {k: float(v) for k, v in diffs.items()},
        "max_abs_diff": float(max_diff),
        "identical": bool(max_diff == 0.0),
        "method": "recomputed rps/logscore/MAE/bias with corrected per-pitcher keying; compared each reported statistic to the v1 report; rps arrays feed population_all/population_usable_B, so exact agreement there verifies the arrays",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal-dir", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--v1-report", required=True)
    a = ap.parse_args()
    seal = Path(a.seal_dir)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    v2 = compute_stats(seal, Path(a.data_root))
    v1_report = json.load(open(a.v1_report, encoding="ascii"))
    verification = verify_against_v1(v2, v1_report)
    rep = {
        "version": "v2",
        "seal_dir": str(seal),
        "population_all": v2["population_all"],
        "population_usable_B": v2["population_usable_B"],
        "secondary": v2["secondary"],
        "actual_K": v2["actual_K"],
        "v1_actual_K_by_game_pk": v2["v1_actual_K_by_game_pk"],
        "rows_with_wrong_v1_value": v2["rows_with_wrong_v1_value"],
        "unmatched": v2["unmatched"],
        "n_rows": v2["n_rows"],
        "deviation_note": "v1 actual_K was keyed by game_pk only (54/134 entries wrong); scored statistics unchanged and verified identical; v1 preserved untouched",
        "verification": verification,
        "note": v2["note"],
    }
    assert verification["identical"], "v2 stats differ from v1: %s" % verification
    (out / "scoring_report_v2.json").write_text(
        json.dumps(rep, indent=1), encoding="ascii")
    print(json.dumps({"out": str(out / "scoring_report_v2.json"),
                      "max_abs_diff": verification["max_abs_diff"],
                      "rows_with_wrong_v1_value": rep["rows_with_wrong_v1_value"],
                      "n_actual_K_keys": len(rep["actual_K"])}, indent=1))


if __name__ == "__main__":
    main()
