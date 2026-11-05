"""Stacker ROI lane (shadow research, no live change).

Applies the PRE-REGISTERED frozen 4-param logit coefs from
distill_stacker_report.json to the bettable panel (settled ledger tickets
with 2+ book closes AND 2+ book mornings, n=981), replays the live policy
filter on stacker probs vs base probs, and compares taken-set ROI/PnL/WR/
CLV-proxy on the same panel.

Live policy filter replayed (read-only from kpi_policy.json and
line_floor_policy.json -- never edited here):
  line floors + over@4.5 hard veto + over@2.5/3.5 probation floor +
  edge cap 0.24 (reject edge >= cap) + under-lean premium 0.04 on overs.
Robust refusal is NOT live (research-done) and is NOT applied.

Market: per-ticket two-way devig at the ledger taken book pair
(devig_two_way on over_price/under_price -- live-board equivalent).
Edge_arm = p_taken_arm - p_mkt_taken. PnL via canonical bet_pnl on the
taken American price, flat $50. CLV-proxy = mean((p_taken_arm -
close_taken) * 100) vs consensus close fair (pp).

Same-subset note: each arm filters the same 981-row panel, so taken sets
are directly comparable; the intersection (common taken) is also scored
for Brier head-to-head (ROI on the intersection is identical by
construction -- same tickets, same prices, same outcomes).

Pre-registered kill: stacker-ROI SURVIVES only if stacker ROI >= base ROI
with stacker n >= 200. Else KILL.

Writes artifacts/odds_log/stacker_roi_report.json. No live change.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.market import bet_pnl, devig_two_way  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402
from join_keys import ODDS_DIR, read_consensus_cache, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
STACK_REP = ODDS_DIR / "distill_stacker_report.json"
KPI_PATH = ROOT / "production" / "ops" / "kpi_policy.json"
FLOOR_PATH = Path(__file__).with_name("line_floor_policy.json")
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
UNIT = 50.0
EPS = 1e-4
MIN_N = 200


def logit(p: float) -> float:
    pc = min(max(p, EPS), 1.0 - EPS)
    return float(np.log(pc / (1.0 - pc)))


def expit(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


def load_policy() -> dict:
    kpi = json.loads(KPI_PATH.read_text(encoding="utf-8"))
    rules = kpi.get("quality_gate", {}).get("rules", {})
    floors = {float(k): float(v) for k, v in
              json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
              .get("line_edge_floors", {}).items()}
    return {
        "floors": floors,
        "probation_floor": float(rules.get("probation_edge_floor", 0.18)),
        "probation_pairs": {(str(r.get("side", "")).lower(), float(r.get("line")))
                            for r in rules.get("side_line_probation", []) or []},
        "vetoes": {(str(r.get("side", "")).lower(), float(r.get("line")))
                   for r in rules.get("side_line_vetoes", []) or []},
        "edge_cap": float(rules.get("edge_cap", 0.24)),
        "under_lean": float(rules.get("under_lean_premium", 0.04)),
    }


def floor_for(side: str, line: float, pol: dict) -> float:
    fl = float(pol["floors"].get(round(float(line), 1), 0.12))
    if (str(side).lower(), float(line)) in pol["probation_pairs"]:
        fl = max(fl, pol["probation_floor"])
    if str(side).lower() == "over":
        fl += pol["under_lean"]
    return fl


def take_reason(side: str, line: float, edge: float, pol: dict) -> str | None:
    if (str(side).lower(), float(line)) in pol["vetoes"]:
        return "veto_4_5_over"
    if float(edge) < floor_for(side, line, pol):
        return "below_floor"
    if float(edge) >= pol["edge_cap"]:
        return "edge_cap"
    return None


def arm_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "roi": None, "pnl": 0.0, "wr": None,
                "mean_edge": None, "mean_clv_proxy_pp": None}
    pnl = sum(float(r["pnl"]) for r in rows)
    stake = UNIT * n
    return {
        "n": n,
        "roi": round(pnl / stake, 4),
        "pnl": round(pnl, 2),
        "wr": round(sum(1 for r in rows if r["won"]) / n, 4),
        "mean_edge": round(sum(float(r["edge"]) for r in rows) / n, 4),
        "mean_clv_proxy_pp": round(
            sum(float(r["clv_proxy_pp"]) for r in rows) / n, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    pol = load_policy()
    coef = json.loads(STACK_REP.read_text(encoding="utf-8"))["coef"]
    b0, b1, b2, b3 = (coef["b0"], coef["b1_model"],
                      coef["b2_morn"], coef["b3_line"])
    print(f"pre-registered coef: b0={b0:.4f} b1={b1:.4f} "
          f"b2={b2:.4f} b3={b3:.4f}")
    print(f"policy: floors={pol['floors']} probation={pol['probation_floor']} "
          f"cap={pol['edge_cap']} lean={pol['under_lean']}")

    cc = read_consensus_cache("pitcher_strikeouts", "close").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    cm = read_consensus_cache("pitcher_strikeouts", "morning").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled")
        & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    led = led.drop([c for c in ("close_over", "close_under", "close_status",
                                "closed_at_utc", "minutes_to_tip_at_close")
                    if c in led.columns])
    j = led.join(cc.select(["gd", "key", "line", "fair"])
                 .rename({"fair": "close_over"}),
                 on=["gd", "key", "line"], how="inner")
    print(f"ledger-close join: {j.height}")
    j = j.join(cm.select(["gd", "key", "line", "fair"])
               .rename({"fair": "morn_over"}),
               on=["gd", "key", "line"], how="inner")
    print(f"+morning join: {j.height}")

    gr = pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher", "k_rate_pred", "projected_tbf"]).collect()
    j = j.join(gr, on=["game_pk", "pitcher"], how="left")
    jj = j.filter(pl.col("k_rate_pred").is_not_null()
                  & pl.col("projected_tbf").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height}")

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def base_over(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]),
                                    family="poisson")[0])
        return float(maps[ln].transform(np.array([raw]))[0])

    taken_base: list[dict] = []
    taken_stack: list[dict] = []
    common_se = {"base": 0.0, "stacker": 0.0}
    common_n = 0
    reject_base: dict[str, int] = {}
    reject_stack: dict[str, int] = {}
    for r in jj.to_dicts():
        ln = float(r["line"])
        side = str(r["side"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        kr = float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))
        bo = base_over(kr, float(r["projected_tbf"]), ln)
        so = expit(b0 + b1 * logit(bo)
                   + b2 * logit(float(r["morn_over"])) + b3 * ln)
        co = float(r["close_over"])
        p_mkt_over, p_mkt_under = devig_two_way(float(r["over_price"]),
                                                float(r["under_price"]))
        won = bool((float(r["settle_value"]) > ln) if side == "over"
                   else (float(r["settle_value"]) < ln))
        price = float(r["bet_price"])
        pnl = bet_pnl(UNIT, price, won=won)
        arms = {}
        for name, p_over in (("base", bo), ("stacker", so)):
            p_taken = p_over if side == "over" else 1.0 - p_over
            p_mkt = p_mkt_over if side == "over" else p_mkt_under
            edge = float(p_taken) - float(p_mkt)
            close_taken = co if side == "over" else 1.0 - co
            clv_proxy = (float(p_taken) - float(close_taken)) * 100.0
            reason = take_reason(side, ln, edge, pol)
            y = y_over if side == "over" else 1.0 - y_over
            arms[name] = {"p_taken": float(p_taken), "edge": edge,
                          "clv_proxy_pp": clv_proxy, "reason": reason,
                          "se": (float(p_taken) - y) ** 2}
        rb = arms["base"]["reason"]
        rs = arms["stacker"]["reason"]
        if rb is None:
            taken_base.append({"won": won, "pnl": pnl,
                               "edge": arms["base"]["edge"],
                               "clv_proxy_pp": arms["base"]["clv_proxy_pp"]})
        else:
            reject_base[rb] = reject_base.get(rb, 0) + 1
        if rs is None:
            taken_stack.append({"won": won, "pnl": pnl,
                                "edge": arms["stacker"]["edge"],
                                "clv_proxy_pp": arms["stacker"]["clv_proxy_pp"]})
        else:
            reject_stack[rs] = reject_stack.get(rs, 0) + 1
        if rb is None and rs is None:
            common_n += 1
            common_se["base"] += arms["base"]["se"]
            common_se["stacker"] += arms["stacker"]["se"]

    m_base = arm_metrics(taken_base)
    m_stack = arm_metrics(taken_stack)
    survives = (m_stack["n"] >= MIN_N and m_base["roi"] is not None
                and m_stack["roi"] is not None
                and m_stack["roi"] >= m_base["roi"])
    rep = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": ("frozen stacker coefs on bettable ledger panel; live "
                     "policy filter replayed per arm (floors + 4.5-over "
                     "veto + 2.5/3.5 probation + cap 0.24 + lean 0.04); "
                     "market = ledger two-way devig; flat $50; same panel"),
        "coef": coef,
        "policy": {"line_floors": pol["floors"],
                   "probation_floor": pol["probation_floor"],
                   "edge_cap": pol["edge_cap"],
                   "under_lean_premium": pol["under_lean"]},
        "n_panel": int(jj.height),
        "base": {**m_base, "reject_reasons": reject_base},
        "stacker": {**m_stack, "reject_reasons": reject_stack},
        "common_taken": {
            "n": common_n,
            "brier_base": (common_se["base"] / common_n
                           if common_n else None),
            "brier_stacker": (common_se["stacker"] / common_n
                              if common_n else None),
            "note": ("ROI identical on intersection by construction "
                     "(same tickets/prices/outcomes)"),
        },
        "kill_rule": f"SURVIVE iff stacker ROI >= base ROI with n>={MIN_N}",
        "kill": "SURVIVE" if survives else "KILL",
    }
    out = ODDS_DIR / "stacker_roi_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"panel={rep['n_panel']} base={m_base} stacker={m_stack} "
          f"common_n={common_n}")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
