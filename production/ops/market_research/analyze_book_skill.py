"""Side-by-side skill on the bought book closes: model vs consensus vs Kalshi.

Inputs (all local, post hoc only):
  data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet (K closes+mornings)
  data/Odds-Historical/kalshi/k_closes.parquet + k_ladder.parquet
  artifacts/odds_log/ledger.parquet (settled = ground truth + model probs)
  artifacts/projection_log/graded.parquet (calibration-regime tags)

Consensus: devig each book (multiplicative, 2-way), median across books.
Labels: consensus = "beat soft consensus" (never true prob); Kalshi = sharp
anchor (exchange); Novig fills (real_bets) = money truth (not touched here).

Outputs: artifacts/odds_log/book_skill_report.json + stdout summary.
Covers user Qs: over/under edges, line cells, edge floors, platt-vs-iso-vs-raw,
Sharpe/Sortino/Sharpe-decay/CLV/xCLV/ROI/xROI on the big-N panel.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.market import american_to_decimal  # noqa: E402
from Python.odds_ledger import atomic_write_text, norm_player_name  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
HIST = ROOT / "data" / "Odds-Historical"


def _devig_pair(over_amer: float | None, under_amer: float | None) -> tuple[float | None, float | None]:
    """Multiplicative devig (fine for 2-way props). Returns fair (over, under)."""
    try:
        if over_amer is None or under_amer is None:
            return None, None
        po = 1.0 / american_to_decimal(float(over_amer))
        pu = 1.0 / american_to_decimal(float(under_amer))
        tot = po + pu
        if tot <= 0:
            return None, None
        return po / tot, pu / tot
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None


def build_consensus(min_books: int = 2, snapshot: str = "close") -> pl.DataFrame:
    """Per (event, player, line) consensus fair-over from all books' closes."""
    lf = pl.scan_parquet(HIST / "theoddsapi" / "book_lines_pitcher.parquet")
    k = lf.filter((pl.col("market") == "pitcher_strikeouts")
                  & (pl.col("snapshot") == snapshot)
                  & pl.col("line").is_not_null()
                  & pl.col("price").is_not_null()).collect()
    if k.is_empty():
        raise SystemExit(f"No K {snapshot} in book_lines_pitcher.parquet; run pull+normalize first.")
    over = k.filter(pl.col("side") == "over").select(
        ["event_id", "player_norm", "line", "book", "price"])
    under = k.filter(pl.col("side") == "under").select(
        ["event_id", "player_norm", "line", "book", "price"])
    pairs = over.join(under, on=["event_id", "player_norm", "line", "book"],
                      suffix="_u")
    rows: list[dict] = []
    for r in pairs.to_dicts():
        fo, _ = _devig_pair(r["price"], r["price_u"])
        if fo is None:
            continue
        rows.append({"event_id": r["event_id"], "player_norm": r["player_norm"],
                     "line": float(r["line"]), "book": r["book"],
                     "fair_over": fo})
    pf = pl.DataFrame(rows)
    agg = pf.group_by(["event_id", "player_norm", "line"]).agg(
        pl.col("fair_over").median().alias("consensus_over"),
        pl.col("fair_over").mean().alias("consensus_mean"),
        pl.len().alias("n_books"),
        pl.col("book").unique().alias("books"),
    ).filter(pl.col("n_books") >= min_books)
    dk = pf.filter(pl.col("book").is_in(["draftkings", "fanduel"])).group_by(
        ["event_id", "player_norm", "line"]).agg(
        pl.col("fair_over").median().alias("dkfd_over"))
    return agg.join(dk, on=["event_id", "player_norm", "line"], how="left")


def _sharpe(vals: list[float]) -> float | None:
    import statistics as st
    if len(vals) < 5:
        return None
    m = st.fmean(vals)
    try:
        s = st.pstdev(vals)
    except st.StatisticsError:
        return None
    return m / s if s > 0 else None


def _sortino(vals: list[float]) -> float | None:
    import statistics as st
    if len(vals) < 5:
        return None
    m = st.fmean(vals)
    dd = [v for v in vals if v < 0]
    if len(dd) < 2:
        return None
    s = st.pstdev(dd)
    return m / s if s > 0 else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min-books", type=int, default=2)
    args = p.parse_args()

    consensus = build_consensus(args.min_books)
    print(f"consensus props: {consensus.height}")

    led = pl.read_parquet(ODDS_DIR / "ledger.parquet")
    settled = led.filter((pl.col("status") == "settled")
                         & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(norm_player_name,
                                           return_dtype=pl.Utf8).alias("pnorm"),
    )
    # Event linkage: OddsAPI event ids aren't in the ledger; join on date+name+line.
    book = pl.read_parquet(HIST / "theoddsapi" / "book_lines_pitcher.parquet",
                           columns=["event_id", "player_norm", "line", "snapshot_ts"])
    keymap = (book.filter(pl.col("snapshot") == "close")
              if "snapshot" in book.columns else book)
    # attach one event date per event_id via snapshot files is expensive; instead
    # join consensus (event-scoped) through player+line+date using event index.
    import json as _json
    evdate: dict[str, str] = {}
    for fp in sorted((HIST / "theoddsapi" / "raw" / "event_index").glob("*.json")):
        try:
            d = _json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ev in d.get("data", d.get("events", [])):
            if isinstance(ev, dict) and ev.get("id"):
                ct = str(ev.get("commence_time", ""))[:10]
                if ct:
                    evdate[ev["id"]] = ct
    consensus = consensus.with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""),
                                        return_dtype=pl.Utf8).alias("gd"))
    j = settled.join(consensus,
                     left_on=["gd", "pnorm", "line"],
                     right_on=["gd", "player_norm", "line"], how="inner")
    print(f"joined settled w/ consensus: {j.height} / {settled.height}")

    # Calibration regime tags from graded log.
    graded = pl.read_parquet(ROOT / "artifacts" / "projection_log" / "graded.parquet")
    greg = graded.group_by([pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
                            pl.col("player_name").map_elements(norm_player_name,
                                                               return_dtype=pl.Utf8).alias("pnorm")]).agg(
        pl.col("calibration_method").first().alias("calib"))
    j = j.join(greg, on=["gd", "pnorm"], how="left")
    j = j.with_columns(pl.col("calib").fill_null("raw"))

    rows = j.to_dicts()
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "n": len(rows)}
    if not rows:
        print("nothing joined; check event-date mapping")
        return

    def brier(pkey, ykey="won"):
        sub = [(r[pkey], r[ykey]) for r in rows
               if r.get(pkey) is not None and r.get(ykey) is not None]
        if not sub:
            return None, 0
        n = len(sub)
        return sum((p - y) ** 2 for p, y in sub) / n, n

    for r in rows:
        r["won"] = 1.0 if (r["side"] == "over") == (float(r["settle_value"]) > float(r["line"])) else 0.0
        # model prob of the TAKEN side
        pm = r.get("p_model")
        r["p_side"] = float(pm) if r["side"] == "over" and pm is not None else (
            1.0 - float(pm) if pm is not None else None)
        co = r.get("consensus_over")
        r["c_side"] = float(co) if r["side"] == "over" and co is not None else (
            1.0 - float(co) if co is not None else None)

    for key in ("p_side", "c_side"):
        b, n = brier(key)
        rep[f"{key}_brier"] = b
        rep[f"{key}_n"] = n
    if rep.get("p_side_brier") is not None and rep.get("c_side_brier") is not None:
        rep["brier_skill_vs_consensus"] = rep["c_side_brier"] - rep["p_side_brier"]

    # Over/under + line cells + floors.
    rep["by_side"] = {}
    for side in ("over", "under"):
        sub = [r for r in rows if r["side"] == side]
        if not sub:
            continue
        pnls = [float(r["pnl"]) for r in sub if r.get("pnl") is not None]
        stakes = [float(r["stake"]) for r in sub if r.get("stake") is not None]
        rep["by_side"][side] = {
            "n": len(sub),
            "wr": sum(r["won"] for r in sub) / len(sub),
            "roi": (sum(pnls) / sum(stakes)) if stakes and sum(stakes) else None,
            "pnl": sum(pnls),
            "brier_model": (sum((r["p_side"] - r["won"]) ** 2 for r in sub
                                if r.get("p_side") is not None)
                            / max(1, sum(1 for r in sub if r.get("p_side") is not None))),
            "brier_cons": (sum((r["c_side"] - r["won"]) ** 2 for r in sub
                               if r.get("c_side") is not None)
                           / max(1, sum(1 for r in sub if r.get("c_side") is not None))),
        }
    rep["by_line_side"] = {}
    for (line, side) in sorted({(r["line"], r["side"]) for r in rows}):
        sub = [r for r in rows if r["line"] == line and r["side"] == side]
        if len(sub) < 10:
            continue
        pnls = [float(r["pnl"]) for r in sub if r.get("pnl") is not None]
        stakes = [float(r["stake"]) for r in sub if r.get("stake") is not None]
        rep["by_line_side"][f"{side} {line}"] = {
            "n": len(sub),
            "wr": sum(r["won"] for r in sub) / len(sub),
            "roi": (sum(pnls) / sum(stakes)) if stakes and sum(stakes) else None,
        }
    # Edge-floor sweep on realized ROI (big-N panel).
    rep["floor_sweep"] = []
    edges = sorted({round(float(r["edge"]), 3) for r in rows if r.get("edge") is not None})
    for f in [0.05, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20]:
        sub = [r for r in rows if r.get("edge") is not None and float(r["edge"]) >= f]
        pnls = [float(r["pnl"]) for r in sub if r.get("pnl") is not None]
        stakes = [float(r["stake"]) for r in sub if r.get("stake") is not None]
        rep["floor_sweep"].append({
            "floor": f, "n": len(sub),
            "roi": (sum(pnls) / sum(stakes)) if stakes and sum(stakes) else None,
            "wr": (sum(r["won"] for r in sub) / len(sub)) if sub else None,
        })
    # Calibration regime split.
    rep["by_calib"] = {}
    for cx in sorted({r.get("calib") or "raw" for r in rows}):
        sub = [r for r in rows if (r.get("calib") or "raw") == cx
               and r.get("p_side") is not None]
        if not sub:
            continue
        rep["by_calib"][cx] = {
            "n": len(sub),
            "brier_model": sum((r["p_side"] - r["won"]) ** 2 for r in sub) / len(sub),
        }
    # Money panel: Sharpe / Sortino / CLV / ROI / xROI + Sharpe-decay (rolling Sharpe).
    seq = sorted(rows, key=lambda r: (str(r.get("game_date", "")),
                                      str(r.get("ticket_id", ""))))
    rpnl = [float(r["pnl"]) for r in seq if r.get("pnl") is not None]
    stakes = [float(r["stake"]) for r in seq if r.get("stake") is not None]
    clvs = [float(r["clv_pp"]) for r in seq if r.get("clv_pp") is not None]
    # xROI: model-implied ROI per ticket = p_side*decimal - 1 at taken price.
    from Python.market import american_to_decimal as _a2d
    xrois = []
    for r in seq:
        try:
            if r.get("p_side") is None or r.get("bet_price") is None:
                continue
            xrois.append(float(r["p_side"]) * _a2d(float(r["bet_price"])) - 1.0)
        except (TypeError, ValueError):
            continue
    rep["money"] = {
        "n": len(rpnl),
        "roi": (sum(rpnl) / sum(stakes)) if stakes and sum(stakes) else None,
        "pnl": sum(rpnl),
        "sharpe": _sharpe(rpnl),
        "sortino": _sortino(rpnl),
        "mean_clv": (sum(clvs) / len(clvs)) if clvs else None,
        "beat_close": (sum(1 for c in clvs if c > 0) / len(clvs)) if clvs else None,
        "xroi_mean": (sum(xrois) / len(xrois)) if xrois else None,
    }
    # Sharpe decay: rolling Sharpe over trailing-200 ticket windows.
    decay = []
    for i in range(200, len(rpnl) + 1, 100):
        w = rpnl[i - 200:i]
        decay.append({"end_idx": i, "sharpe": _sharpe(w)})
    rep["money"]["sharpe_decay"] = decay

    out = ODDS_DIR / "book_skill_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({k: v for k, v in rep.items()
                      if k in ("n", "p_side_brier", "c_side_brier",
                               "brier_skill_vs_consensus", "money")},
                     indent=2, default=str))
    print("by_side:", json.dumps(rep["by_side"], indent=2, default=str))
    print("floor_sweep:", json.dumps(rep["floor_sweep"], indent=2, default=str))
    print("by_calib:", json.dumps(rep["by_calib"], indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
