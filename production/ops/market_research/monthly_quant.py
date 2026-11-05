"""Monthly quant surface: ROI/Sharpe/Sortino/drawdown per month + expanding Sharpe.

Doctrine: per-ticket simple returns r = pnl/stake. Sharpe_pb = mean(r)/std(r)
(sample std, dimensionless, NO annualization — labeled pb for per-bet).
Sortino_pb = mean(r)/downside-std(r<0). maxDD from the date-ordered cumulative
PnL curve (dollars + $50-units). Expanding Sharpe re-runs on all rows through
each month-end: the Sharpe-decay view. Thin months (n<10) still print but are
never cited alone.

Sources: (a) live ledger settled+staked+deduped (money truth, mixed Kelly/flat
eras — labeled); (b) champion replay taken set (flat $50, selector-exact).

Usage:
  python production/ops/market_research/monthly_quant.py [--out FILE]
Writes artifacts/odds_log/monthly_quant.json + prints markdown tables.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

import polars as pl  # noqa: E402

from Python.odds_ledger import (  # noqa: E402
    atomic_write_text,
    dedupe_ledger_props,
    settled_bets,
)

ODDS_DIR = ROOT / "artifacts" / "odds_log"
UNIT = 50.0
ANN = 162.0 ** 0.5  # season clock (golden_metrics: daily-PnL Sharpe convention)


def quant_block(r: list[float], pnl: list[float]) -> dict:
    """Quant block for one return series (pure, testable)."""
    import statistics

    n = len(r)
    if n == 0:
        return {"n": 0}
    mean = sum(r) / n
    sd = statistics.stdev(r) if n > 1 else None
    # Downside deviation vs a zero target over ALL observations (standard
    # Sortino denominator). NB: sample-stdev-of-losses is degenerate here —
    # flat-stake losses are all exactly -100% (stdev 0) — so use MAR form.
    dd_var = sum(min(0.0, x) ** 2 for x in r) / n if n else None
    dsd = math.sqrt(dd_var) if dd_var else None
    cum, peak, dd = 0.0, 0.0, 0.0
    for v in pnl:
        cum += v
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {
        "n": n,
        "sharpe_pb": round(mean / sd, 3) if sd else None,
        "sortino_pb": round(mean / dsd, 3) if dsd else None,
        "maxdd_dollars": round(dd, 2),
        "maxdd_u": round(dd / UNIT, 2),
    }


def monthly_table(df: pl.DataFrame, date_col: str, pnl_col: str,
                   stake_col: str) -> dict:
    """Per-month + expanding quant blocks (pure over rows, testable shape).

    Optional normalized columns (added by main, ignored when absent):
    `_w` bool won flag, `_clv` float CLV in percentage points.
    """
    rows = df.with_columns(pl.col(date_col).cast(pl.String).str.slice(0, 7).alias("_m"))
    months = sorted(rows["_m"].drop_nulls().unique().to_list())
    out: dict = {"monthly": {}, "expanding": {}}
    acc_r: list[float] = []
    acc_p: list[float] = []
    for m in months:
        tie = [c for c in ("ticket_id", "key", "line", "side", "book")
               if c in rows.columns]
        sub = rows.filter(pl.col("_m") == m).sort([date_col, *tie])
        r = [(float(p) / float(s)) if float(s) else 0.0
             for p, s in zip(sub[pnl_col].to_list(), sub[stake_col].to_list())]
        p = [float(x) for x in sub[pnl_col].to_list()]
        block: dict = {"pnl": round(sum(p), 2),
                       "roi": round(sum(p) / sum(float(x) for x in sub[stake_col].to_list()), 4),
                       **quant_block(r, p)}
        if "_w" in sub.columns:
            w = sub["_w"].to_list()
            block["wr"] = round(sum(1 for x in w if bool(x)) / len(w), 4) if w else None
        if "_clv" in sub.columns:
            cv = [float(x) for x in sub["_clv"].drop_nulls().to_list()]
            block["clv_n"] = len(cv)
            block["clv_mean_pp"] = round(sum(cv) / len(cv), 2) if cv else None
            block["clv_beat"] = round(sum(1 for x in cv if x > 0) / len(cv), 4) if cv else None
        block["days"] = sub.select(pl.col(date_col).cast(pl.String).str.slice(0, 10).n_unique()).item()
        block["bets_per_day"] = round(len(r) / block["days"], 2) if block["days"] else None
        pnl_u = sum(p) / UNIT
        block["calmar_u"] = round(pnl_u / block["maxdd_u"], 2) if block.get("maxdd_u") else None
        # Strategy clock (quant-firm convention): Sharpe/Sortino on the
        # daily-PnL series, annualized to the season (sample std). Monthly
        # cells are noisy by construction; YTD is the headline.
        import statistics as _st
        dayp = [float(x) for x in sub.group_by(
            pl.col(date_col).cast(pl.String).str.slice(0, 10).alias("_day")
        ).agg(pl.col(pnl_col).cast(pl.Float64).sum().alias("dp"))["dp"].to_list()]
        block["days"] = len(dayp)
        if len(dayp) > 2:
            _m = sum(dayp) / len(dayp)
            _sd = _st.stdev(dayp)
            block["sharpe_d"] = round(_m / _sd * ANN, 2) if _sd else None
            _dd = math.sqrt(sum(min(0.0, x) ** 2 for x in dayp) / len(dayp))
            block["sortino_d"] = round(_m / _dd * ANN, 2) if _dd else None
        else:
            block["sharpe_d"] = block["sortino_d"] = None
        out["monthly"][m] = block
        acc_r += r
        acc_p += p
        exp = quant_block(acc_r, acc_p)
        exp_pnl_u = sum(acc_p) / UNIT
        exp["calmar_u"] = round(exp_pnl_u / exp["maxdd_u"], 2) if exp.get("maxdd_u") else None
        out["expanding"][m] = exp
    return out


def load_selector():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "select_2025_champion",
        ROOT / "production" / "ops" / "market_research" / "select_2025_champion.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_2025_champion"] = mod
    spec.loader.exec_module(mod)
    return mod


def md_table(title: str, rep: dict) -> str:
    lines = [f"### {title}",
             "| Month | n | PnL | ROI | CLV | beat | Sharpe_pb | Sortino_pb | MaxDD(u) | Calmar | bets/day |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, b in rep["monthly"].items():
        clv = f"{b['clv_mean_pp']:+.2f}pp" if b.get("clv_mean_pp") is not None else "n/a"
        beat = f"{b['clv_beat']:.0%}" if b.get("clv_beat") is not None else "n/a"
        cal = f"{b['calmar_u']:.2f}" if b.get("calmar_u") is not None else "n/a"
        lines.append(
            f"| {m} | {b['n']} | ${b['pnl']:+.0f} | {b['roi']:+.1%} | "
            f"{clv} (n={b.get('clv_n', 0)}) | {beat} | "
            f"{b['sharpe_pb']} | {b['sortino_pb']} | {b['maxdd_u']} | "
            f"{cal} | {b.get('bets_per_day')} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ODDS_DIR / "monthly_quant.json"))
    args = ap.parse_args()

    led = pl.read_parquet(ODDS_DIR / "ledger.parquet")
    live = dedupe_ledger_props(
        settled_bets(led).filter(pl.col("stake").fill_null(0) > 0))
    live = live.with_columns(
        pl.col("game_date").cast(pl.String).alias("_d"),
        (pl.col("result") == "win").alias("_w"),
        (pl.col("clv_pp").cast(pl.Float64) * 100.0).alias("_clv"))
    rep: dict = {"live_paper": monthly_table(live, "_d", "pnl", "stake"),
                 "live_note": "money truth; mixed Kelly/flat stake eras; CLV = same-book fillable (fraction x100)"}

    sel = load_selector()
    cand = pl.read_parquet(ODDS_DIR / "juiced_replay_candidates.parquet")
    champ = sel.apply_config(
        cand.filter(pl.col("yr").cast(pl.String) == "2026"),
        0.12, 0.24, "lean", "dkfd")
    champ = champ.with_columns(
        pl.col("won").cast(pl.Boolean).alias("_w"),
        pl.col("clv_pp").cast(pl.Float64).alias("_clv"))
    rep["champion_replay"] = monthly_table(champ, "gd", "pnl", "stake")
    rep["champion_note"] = "selector-exact taken set, flat $50; CLV already pp"
    if {"pnl_kelly", "stake_kelly"}.issubset(set(champ.columns)):
        rep["champion_kelly"] = monthly_table(champ, "gd", "pnl_kelly", "stake_kelly")
        rep["champion_kelly_note"] = ("display-only benchmark on the same taken "
                                      "set (banked sizing arms); flat stays the rule")

    atomic_write_text(Path(args.out), json.dumps(rep, indent=2, default=str))
    print(md_table("Live paper 2026 (deduped, actual stakes)", rep["live_paper"]))
    print()
    print(md_table("Champion replay 2026 (flat $50)", rep["champion_replay"]))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
