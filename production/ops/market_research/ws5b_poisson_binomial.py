"""WS5b Poisson-binomial count layer (post hoc, research; KSplit homework).

Per start: 9 first-9 slot K-probs (batter k_rate vs pitcher hand blended
50/50 with pitcher k_rate_pred), trials = round(projected_tbf) cycling slots
by lineup order, K-dist via Poisson-binomial DP. More spread by construction;
direct attack on the under-dispersion bias flip (+4.8pp @2.5 -> -14.5pp @9.5).

Eval on universe test split (cut 2026-05-23): Brier per line 2.5-9.5 vs
binomial/poisson/book-close. Writes artifacts/odds_log/ws5b_report.json.
No live change. KILL: no Brier gain vs Poisson on held-out.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.count_layer import over_threshold  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ODDS_DIR / "universe_panel.parquet"
BAT = ROOT / "data" / "processed" / "batter_rolling.parquet"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"
EPS = 1e-9


def pb_sf(probs: np.ndarray, line: float) -> float:
    """P(sum Bernoulli(probs) > line) via DP convolution."""
    t = over_threshold(line)
    dp = np.zeros(len(probs) + 1)
    dp[0] = 1.0
    for i, p in enumerate(probs):
        p = min(max(float(p), 0.0), 1.0)
        ndp = np.zeros(len(probs) + 1)
        ndp[0:i + 2] = dp[0:i + 2] * (1 - p)
        ndp[1:i + 2] += dp[0:i + 1] * p
        dp = ndp
    return float(dp[t:].sum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    sc = pl.scan_parquet(SCORED).select(
        ["gd", "game_pk", "pitcher", "player_name", "p_throws", "K",
         "k_rate_pred", "projected_tbf", "is_home", "home_team", "away_team"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("k_rate_pred").is_not_null()
        & pl.col("projected_tbf").is_not_null() & (pl.col("projected_tbf") > 0))
    bat = pl.scan_parquet(BAT).select(
        ["game_pk", "bat_team", "lineup_slot", "stand", "is_initial_lineup",
         "k_rate_std_vL", "k_rate_std_vR", "lineup_pa_weight"]).collect().filter(
        pl.col("is_initial_lineup"))
    print(f"scored {sc.height}, slot rows {bat.height}")

    panel = pl.read_parquet(PANEL).filter(pl.col("p_book_close").is_not_null()).select(
        ["gd", "key", "line", "y", "p_book_close"])
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "per_line": [], "coverage": {}}
    tes, tes_y, tlines, tgd, tkey = [], [], [], [], []
    n_noslot = 0
    from join_keys import sorted_key as _sk
    for r in sc.to_dicts():
        opp = r["away_team"] if r["is_home"] else r["home_team"]
        slots = bat.filter((pl.col("game_pk") == r["game_pk"]) & (pl.col("bat_team") == opp)).sort("lineup_slot")
        if slots.height < 9:
            n_noslot += 1
            continue
        hand = "vR" if str(r["p_throws"]).upper().startswith("R") else "vL"
        kr = float(r["k_rate_pred"])
        tbf = int(round(float(r["projected_tbf"])))
        probs = []
        for s in slots.head(9).to_dicts():
            br = s[f"k_rate_std_{hand}"]
            br = float(br) if br is not None else kr
            probs.append(0.5 * br + 0.5 * kr)
        trials = [probs[i % 9] for i in range(max(tbf, 1))]
        tarr = np.array(trials)
        key = _sk(r["player_name"])
        for ln in LINES:
            tes.append(pb_sf(tarr, ln))
        tes_y.extend([1.0 if float(r["K"]) > ln else 0.0 for ln in LINES])
        tlines.extend(LINES)
        tgd.extend([r["gd"]] * len(LINES))
        tkey.extend([key] * len(LINES))
    rep["coverage"] = {"starts_used": len(tes_y) // len(LINES), "starts_noslot": n_noslot}
    print(f"starts scored-pb: {rep['coverage']}")
    tes = np.array(tes)
    tes_y = np.array(tes_y)
    tlines = np.array(tlines)
    for ln in LINES:
        m = (tlines == ln)
        y = tes_y[m]
        p = tes[m]
        rep["per_line"].append({"line": ln, "n": int(m.sum()),
                                "brier_pb": float(np.mean((p - y) ** 2)),
                                "base_rate": float(y.mean())})
    pbframe = pl.DataFrame({"gd": tgd, "key": tkey, "line": tlines, "p_pb": tes, "y": tes_y})
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "p_ours", "p_book_close"])
    cmpf = pbframe.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_ours").is_not_null() & pl.col("p_book_close").is_not_null())
    print(f"compare rows: {cmpf.height}")
    for ln in LINES:
        s = cmpf.filter(pl.col("line") == ln)
        if s.height < 50:
            continue
        y = s["y"].to_numpy()
        for name, col in [("pb_sub", "p_pb"), ("binom", "p_ours"), ("book", "p_book_close")]:
            b = float(np.mean((s[col].to_numpy() - y) ** 2))
            for e in rep["per_line"]:
                if e["line"] == ln:
                    e[f"brier_{name}"] = b
    for e in rep["per_line"]:
        if "brier_binom" in e:
            e["n_apples"] = int(cmpf.filter(pl.col("line") == e["line"]).height)
            print("line=%.1f apples n=%d: pb=%.4f binom=%.4f book=%.4f" % (
                e["line"], e["n_apples"], e["brier_pb_sub"], e["brier_binom"], e["brier_book"]))
    out = ODDS_DIR / "ws5b_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    for e in rep["per_line"]:
        print("line=%.1f n=%d pb=%.4f base=%.3f" % (e["line"], e["n"], e["brier_pb"], e["base_rate"]))
    print(f"wrote {out} (book compare = next: join panel)")


if __name__ == "__main__":
    main()
