"""Deeper post-freeze diagnosis before any live recommendation change.

Covers edge↔ROI correlation, floor grids, line×side, CLV links, reliability,
and Brier skill vs market. Does NOT edit KING_PROFILE / floors.

Example:
  python production/ops/run_postfreeze_deep_diagnosis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props, settled_bets  # noqa: E402

LEDGER = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "postfreeze_deep_diagnosis_20260901.json"
OUT_REPORT = (
    ROOT / "docs" / "reference" / "reports" / "postfreeze_deep_diagnosis_2026-09-01.md"
)
FREEZE = "2026-08-21"


def roi(frame: pl.DataFrame) -> float | None:
    if frame.is_empty():
        return None
    stake = float(frame["stake"].sum())
    pnl = float(frame["pnl"].sum())
    return round(pnl / stake, 4) if stake else None


def wr(frame: pl.DataFrame) -> float | None:
    if frame.is_empty():
        return None
    return round(frame.filter(pl.col("result") == "win").height / frame.height, 4)


def clv_stats(frame: pl.DataFrame) -> dict:
    if "clv_pp" not in frame.columns or frame.is_empty():
        return {"clv_n": 0, "clv_mean_pp": None, "clv_gt0_share": None}
    clv = frame["clv_pp"].drop_nulls()
    if clv.len() == 0:
        return {"clv_n": 0, "clv_mean_pp": None, "clv_gt0_share": None}
    return {
        "clv_n": int(clv.len()),
        "clv_mean_pp": round(float(clv.mean()), 4),
        "clv_gt0_share": round(float((clv > 0).sum() / clv.len()), 4),
    }


def corr_edge_roi(frame: pl.DataFrame) -> dict:
    if frame.height < 8:
        return {"n": frame.height, "note": "insufficient"}
    try:
        from scipy import stats
    except ImportError:
        return {"n": frame.height, "note": "scipy_missing"}
    ae = frame["abs_edge"].to_numpy()
    bet_roi = (frame["pnl"] / frame["stake"]).to_numpy()
    pear = stats.pearsonr(ae, bet_roi)
    spear = stats.spearmanr(ae, bet_roi)
    return {
        "n": frame.height,
        "pearson_r": round(float(pear.statistic), 4),
        "pearson_p": round(float(pear.pvalue), 4),
        "spearman_r": round(float(spear.statistic), 4),
        "spearman_p": round(float(spear.pvalue), 4),
    }


def edge_buckets(frame: pl.DataFrame, bins: list[tuple[float, float]]) -> list[dict]:
    rows = []
    for lo, hi in bins:
        sub = frame.filter((pl.col("abs_edge") >= lo) & (pl.col("abs_edge") < hi))
        rows.append(
            {
                "abs_edge_lo": lo,
                "abs_edge_hi": hi,
                "n": sub.height,
                "roi": roi(sub),
                "win_rate": wr(sub),
                "pnl": None if sub.is_empty() else round(float(sub["pnl"].sum()), 2),
                **clv_stats(sub),
            }
        )
    return rows


def reliability(frame: pl.DataFrame, n_bins: int = 4) -> list[dict] | dict:
    d = frame.filter(pl.col("p_model").is_not_null())
    if d.height < n_bins * 3:
        return {"n": d.height, "note": "insufficient"}
    d = d.with_columns(
        (pl.col("p_model").rank(method="average") / d.height).alias("p_rank")
    )
    rows = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        if i == 0:
            sub = d.filter(pl.col("p_rank") <= hi)
        else:
            sub = d.filter((pl.col("p_rank") > lo) & (pl.col("p_rank") <= hi))
        if sub.is_empty():
            continue
        mean_p = float(sub["p_model"].mean())
        hit = sub.filter(pl.col("result") == "win").height / sub.height
        rows.append(
            {
                "bin": i + 1,
                "n": sub.height,
                "mean_p_model": round(mean_p, 4),
                "hit_rate": round(hit, 4),
                "gap_hit_minus_p": round(hit - mean_p, 4),
                "roi": roi(sub),
            }
        )
    return rows


def brier_skill(frame: pl.DataFrame) -> dict | None:
    d = frame.filter(
        pl.col("p_model").is_not_null()
        & pl.col("p_market").is_not_null()
        & pl.col("result").is_in(["win", "loss"])
    )
    if d.height < 8:
        return None
    y = (d["result"] == "win").cast(pl.Float64)
    bm = float(((d["p_model"] - y) ** 2).mean())
    bk = float(((d["p_market"] - y) ** 2).mean())
    return {
        "n": d.height,
        "brier_model": round(bm, 5),
        "brier_market": round(bk, 5),
        "skill_vs_market": round(1.0 - bm / bk, 5) if bk else None,
    }


def main() -> None:
    ded = dedupe_ledger_props(settled_bets(pl.read_parquet(LEDGER))).with_columns(
        pl.col("game_date").cast(pl.Utf8),
        pl.col("edge").abs().alias("abs_edge"),
    )
    post = ded.filter((pl.col("game_date") > FREEZE) & pl.col("edge").is_not_null())
    king = post.filter((pl.col("passes_floor") == True) & (pl.col("stake") > 0))  # noqa: E712
    staked = post.filter(pl.col("stake") > 0)

    bins = [(0.12, 0.14), (0.14, 0.16), (0.16, 0.18), (0.18, 0.22), (0.22, 1.0)]
    edge_corr = {
        "king_all": corr_edge_roi(king),
        "king_over": corr_edge_roi(king.filter(pl.col("side") == "over")),
        "king_under": corr_edge_roi(king.filter(pl.col("side") == "under")),
    }
    buckets = {
        "all": edge_buckets(king, bins),
        "over": edge_buckets(king.filter(pl.col("side") == "over"), bins),
        "under": edge_buckets(king.filter(pl.col("side") == "under"), bins),
    }

    floor_sweep = []
    for fl in [0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20]:
        sub = staked.filter(pl.col("abs_edge") >= fl)
        floor_sweep.append(
            {
                "abs_edge_floor": fl,
                "n": sub.height,
                "roi": roi(sub),
                "pnl": None if sub.is_empty() else round(float(sub["pnl"].sum()), 2),
                "n_over": sub.filter(pl.col("side") == "over").height,
                "n_under": sub.filter(pl.col("side") == "under").height,
                **clv_stats(sub),
            }
        )

    asym_grid = []
    for of in [0.12, 0.14, 0.16, 0.18]:
        for uf in [0.10, 0.12, 0.14]:
            sub = staked.filter(
                ((pl.col("side") == "over") & (pl.col("abs_edge") >= of))
                | ((pl.col("side") == "under") & (pl.col("abs_edge") >= uf))
            )
            asym_grid.append(
                {
                    "over_floor": of,
                    "under_floor": uf,
                    "n": sub.height,
                    "roi": roi(sub),
                    "pnl": None if sub.is_empty() else round(float(sub["pnl"].sum()), 2),
                    **clv_stats(sub),
                }
            )

    line_side = []
    for keys, sub in king.group_by(["line", "side"]):
        line, side = keys
        line_side.append(
            {
                "line": float(line),
                "side": str(side),
                "n": sub.height,
                "roi": roi(sub),
                "win_rate": wr(sub),
                "pnl": round(float(sub["pnl"].sum()), 2),
                **clv_stats(sub),
            }
        )
    line_side = sorted(line_side, key=lambda r: (r["line"], r["side"]))

    veto = []
    for veto_lines in ([4.5], [3.5, 4.5], [2.5, 3.5, 4.5], [4.5, 5.5]):
        sub = king.filter(
            ~((pl.col("side") == "over") & (pl.col("line").is_in(veto_lines)))
        )
        veto.append(
            {
                "veto_over_lines": veto_lines,
                "n": sub.height,
                "roi": roi(sub),
                "pnl": round(float(sub["pnl"].sum()), 2),
                **clv_stats(sub),
            }
        )

    high_edge_over = []
    for lo in [0.12, 0.14, 0.16, 0.18, 0.20]:
        sub = king.filter((pl.col("side") == "over") & (pl.col("abs_edge") >= lo))
        high_edge_over.append(
            {
                "abs_edge_min": lo,
                "n": sub.height,
                "roi": roi(sub),
                "win_rate": wr(sub),
            }
        )

    clv_link: dict = {}
    kclv = king.filter(pl.col("clv_pp").is_not_null())
    if kclv.height >= 8:
        try:
            from scipy import stats

            y = (kclv["result"] == "win").cast(pl.Float64).to_numpy()
            c = kclv["clv_pp"].to_numpy()
            r = (kclv["pnl"] / kclv["stake"]).to_numpy()
            sw = stats.spearmanr(c, y)
            sr = stats.spearmanr(c, r)
            clv_link["clv_vs_win_spearman"] = {
                "r": round(float(sw.statistic), 4),
                "p": round(float(sw.pvalue), 4),
                "n": kclv.height,
            }
            clv_link["clv_vs_bet_roi_spearman"] = {
                "r": round(float(sr.statistic), 4),
                "p": round(float(sr.pvalue), 4),
                "n": kclv.height,
            }
        except ImportError:
            clv_link["note"] = "scipy_missing"
        for side in ("over", "under"):
            s = kclv.filter(pl.col("side") == side)
            clv_link[f"{side}_when_clv_gt0"] = {
                "n": s.filter(pl.col("clv_pp") > 0).height,
                "roi": roi(s.filter(pl.col("clv_pp") > 0)),
            }
            clv_link[f"{side}_when_clv_le0"] = {
                "n": s.filter(pl.col("clv_pp") <= 0).height,
                "roi": roi(s.filter(pl.col("clv_pp") <= 0)),
            }

    payload = {
        "generated": "2026-09-01",
        "freeze": FREEZE,
        "n_king": king.height,
        "n_post_staked": staked.height,
        "king_roi": roi(king),
        "edge_roi_correlation": edge_corr,
        "edge_buckets_king": buckets,
        "floor_sweep_staked": floor_sweep,
        "asym_floor_grid_staked": asym_grid,
        "line_side_king": line_side,
        "veto_over_lines": veto,
        "high_edge_overs": high_edge_over,
        "clv_outcome_link": clv_link,
        "reliability_king": {
            "all": reliability(king),
            "over": reliability(king.filter(pl.col("side") == "over")),
            "under": reliability(king.filter(pl.col("side") == "under")),
        },
        "brier_skill": {
            "all": brier_skill(king),
            "over": brier_skill(king.filter(pl.col("side") == "over")),
            "under": brier_skill(king.filter(pl.col("side") == "under")),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    viable = [
        r for r in asym_grid if r["n"] >= 25 and r["roi"] is not None
    ]
    viable = sorted(viable, key=lambda r: r["roi"], reverse=True)[:8]

    def corr_md(label: str, d: dict) -> str:
        if "note" in d:
            return f"| {label} | {d.get('n')} | — | {d.get('note')} |"
        return (
            f"| {label} | {d['n']} | {d['pearson_r']} (p={d['pearson_p']}) | "
            f"{d['spearman_r']} (p={d['spearman_p']}) |"
        )

    eb = []
    for side, rows in buckets.items():
        for r in rows:
            eb.append(
                f"| {side} | {r['abs_edge_lo']}–{r['abs_edge_hi']} | {r['n']} | "
                f"{r['roi']} | {r['win_rate']} | {r['clv_gt0_share']} |"
            )

    over_c = edge_corr["king_over"]
    under_c = edge_corr["king_under"]
    b_over = payload["brier_skill"]["over"]
    b_under = payload["brier_skill"]["under"]

    memo = [
        f"- KING post-freeze: n={king.height}, ROI={roi(king)}, PnL={round(float(king['pnl'].sum()), 2)}.",
        f"- Edge↔ROI Spearman overs: {over_c}.",
        f"- Edge↔ROI Spearman unders: {under_c}.",
        f"- Brier skill vs market: over={b_over}, under={b_under}.",
        "- If over edge↔ROI is flat/negative, raising a universal floor will not heal overs.",
        "- Prefer side/line gates; keep CLV as a skill check alongside ROI/PnL.",
        "- Do not promote on this single ~10-day window alone.",
    ]

    md = "\n".join(
        [
            "# Post-freeze deep diagnosis (2026-09-01)",
            "",
            "Analysis-only. **No live KING / floor change.**",
            "",
            "Producer: `production/ops/run_postfreeze_deep_diagnosis.py`",
            "",
            "## Executive memo",
            "",
            *memo,
            "",
            "## Edge% vs per-bet ROI",
            "",
            "| Slice | n | Pearson | Spearman |",
            "| --- | ---: | --- | --- |",
            corr_md("king_all", edge_corr["king_all"]),
            corr_md("king_over", edge_corr["king_over"]),
            corr_md("king_under", edge_corr["king_under"]),
            "",
            "## Abs-edge buckets (KING)",
            "",
            "| Side | Edge bucket | n | ROI | WR | CLV>0 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
            *eb,
            "",
            "## Universal floor sweep (stake>0 post-freeze)",
            "",
            "| Floor | n | ROI | PnL | n_over/under | CLV>0 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            *[
                f"| {r['abs_edge_floor']} | {r['n']} | {r['roi']} | {r['pnl']} | "
                f"{r['n_over']}/{r['n_under']} | {r['clv_gt0_share']} |"
                for r in floor_sweep
            ],
            "",
            "## Asymmetric floor grid (best ROI, n≥25)",
            "",
            "| Over floor | Under floor | n | ROI | PnL | CLV>0 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            *[
                f"| {r['over_floor']} | {r['under_floor']} | {r['n']} | {r['roi']} | "
                f"{r['pnl']} | {r['clv_gt0_share']} |"
                for r in viable
            ],
            "",
            "## Line × side (KING)",
            "",
            "| Line | Side | n | ROI | WR | CLV>0 | PnL |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
            *[
                f"| {r['line']} | {r['side']} | {r['n']} | {r['roi']} | {r['win_rate']} | "
                f"{r['clv_gt0_share']} | {r['pnl']} |"
                for r in line_side
            ],
            "",
            "## Over-line veto sensitivity",
            "",
            "| Veto over lines | n | ROI | PnL | CLV>0 |",
            "| --- | ---: | ---: | ---: | ---: |",
            *[
                f"| {r['veto_over_lines']} | {r['n']} | {r['roi']} | {r['pnl']} | {r['clv_gt0_share']} |"
                for r in veto
            ],
            "",
            "## High-|edge| overs",
            "",
            "```json",
            json.dumps(high_edge_over, indent=2),
            "```",
            "",
            "## CLV ↔ outcome",
            "",
            "```json",
            json.dumps(clv_link, indent=2),
            "```",
            "",
            "## Reliability bins",
            "",
            "```json",
            json.dumps(payload["reliability_king"], indent=2),
            "```",
            "",
            "## Brier skill vs market",
            "",
            "```json",
            json.dumps(payload["brier_skill"], indent=2),
            "```",
            "",
            "## Adjustment principles (still not live edits)",
            "",
            "1. No universal floor raise to fix overs if edge↔ROI on overs is flat/negative.",
            "2. Side-aware + line-aware gates beat one knobs-for-all floor.",
            "3. Optimize ROI/PnL and CLV jointly; do not buy a one-week ROI spike with CLV collapse.",
            "4. Recalibrate only under a pre-registered split that excludes this eval window.",
            "5. Re-run weekly; promote only under interim stance gates.",
            "",
            f"JSON: `{OUT_JSON.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "edge_corr": edge_corr,
                "brier": payload["brier_skill"],
                "veto_head": veto[:3],
                "top_asym": viable[:5],
                "king_roi": roi(king),
                "high_edge_over": high_edge_over,
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
