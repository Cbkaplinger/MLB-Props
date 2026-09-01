"""Null / placebo decision lanes on the settled odds ledger (SSAC27 item 8).

Builds matched-count null bettors against the frozen KING floor (0.12) on the
same deduped settled opportunity universe:

1. random_prob — p_model ~ U(0,1), edge vs market, take top-k by |edge|
2. naive_prior — p_model = season-to-date pitcher k_rate (fallback: league mean)
   mapped through a crude normal-ish line probability using line as threshold
   on E[K]=k_rate_hat * typical_PA (uses PA=22.5 if unknown)
3. market_mirror — bet the market favorite side with no model (edge = |0.5-p_mkt|)

Compares ROI / win rate / CLV vs the frozen profile lane (passes_floor).

Example:
  python production/ops/run_null_decision_lane.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props, settled_bets  # noqa: E402

LEDGER = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "null_decision_lane_20260901.json"
OUT_REPORT = ROOT / "docs" / "reference" / "reports" / "ssac27_null_decision_lane_2026-09-01.md"
FREEZE = "2026-08-21"
FLOOR = 0.12
RNG = np.random.default_rng(5161)


def _summarize(name: str, d: pl.DataFrame) -> dict:
    if d.is_empty():
        return {"name": name, "n": 0}
    stake = float(d["stake"].sum())
    pnl = float(d["pnl"].sum())
    clv = d["clv_pp"].drop_nulls() if "clv_pp" in d.columns else pl.Series([], dtype=pl.Float64)
    return {
        "name": name,
        "n": d.height,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / stake, 4) if stake else None,
        "win_rate": round(d.filter(pl.col("result") == "win").height / d.height, 4),
        "clv_mean_pp": None if clv.len() == 0 else round(float(clv.mean()), 4),
        "clv_gt0_share": None if clv.len() == 0 else round(float((clv > 0).sum() / clv.len()), 4),
        "clv_n": int(clv.len()),
        "date_min": str(d["game_date"].min()),
        "date_max": str(d["game_date"].max()),
    }


def _attach_naive_edge(df: pl.DataFrame) -> pl.DataFrame:
    """Crude naive edge: pitcher prior k_rate vs line using fixed PA=22.5."""
    pa = 22.5
    # Use rolling feature if present else fall back later
    prior = None
    for c in ("k_rate_P20", "k_rate_P10", "k_rate_P5"):
        if c in df.columns:
            prior = c
            break
    if prior is None:
        # ledger may not have priors — use constant league-ish 0.22
        df = df.with_columns(pl.lit(0.22).alias("_k_hat"))
    else:
        df = df.with_columns(pl.col(prior).fill_null(0.22).alias("_k_hat"))

    # P(K > line) ≈ 1 - Phi((line+0.5 - mu)/sqrt(mu*(1-p)*n approx)) — too heavy;
    # use soft logistic on (mu - line)
    df = df.with_columns((pl.col("_k_hat") * pa).alias("_ek"))
    # p_over = sigmoid(ek - line)
    df = df.with_columns(
        (1.0 / (1.0 + (-(pl.col("_ek") - pl.col("line"))).exp())).alias("_p_over_naive")
    )
    df = df.with_columns(
        pl.when(pl.col("side") == "over")
        .then(pl.col("_p_over_naive") - pl.col("p_market"))
        .otherwise((1.0 - pl.col("_p_over_naive")) - pl.col("p_market"))
        .alias("edge_naive")
    )
    return df


def _pick_topk_by_edge(df: pl.DataFrame, edge_col: str, k: int, floor: float) -> pl.DataFrame:
    scored = df.filter(pl.col(edge_col).abs() >= floor).sort(pl.col(edge_col).abs(), descending=True)
    if scored.height <= k:
        return scored
    return scored.head(k)


def main() -> None:
    led = pl.read_parquet(LEDGER)
    ded = dedupe_ledger_props(settled_bets(led)).with_columns(pl.col("game_date").cast(pl.Utf8))
    # Opportunity universe: post-freeze settled rows with market probs
    univ = ded.filter(
        (pl.col("game_date") > FREEZE)
        & pl.col("p_market").is_not_null()
        & pl.col("stake").is_not_null()
    )
    king = univ.filter(pl.col("passes_floor") == True)  # noqa: E712
    k = king.height

    # 1) KING reference
    lanes = [_summarize("king_passes_floor_postfreeze", king)]

    # 2) random_prob: random p_side, edge vs market, match n and floor
    u = univ.with_columns(
        pl.Series("p_rand", RNG.random(univ.height)),
    ).with_columns(
        (pl.col("p_rand") - pl.col("p_market")).alias("edge_rand")
    )
    # assign synthetic stake = median king stake for nulls with stake==0
    med_stake = float(king["stake"].median()) if k else 50.0
    u = u.with_columns(
        pl.when(pl.col("stake") > 0).then(pl.col("stake")).otherwise(med_stake).alias("stake_eff")
    )
    rand_picks = _pick_topk_by_edge(u, "edge_rand", k, FLOOR)
    # PnL for random picks: use actual result if stake>0 else reconstruct from rpd-like
    # For stake==0 candidates, approximate pnl from american via result only if present
    rand_eval = rand_picks.with_columns(
        pl.when(pl.col("stake") > 0)
        .then(pl.col("pnl"))
        .otherwise(
            pl.when(pl.col("result") == "win")
            .then(pl.col("stake_eff") * 0.91)  # approx -110
            .when(pl.col("result") == "loss")
            .then(-pl.col("stake_eff"))
            .otherwise(0.0)
        )
        .alias("pnl_eval"),
        pl.col("stake_eff").alias("stake"),
    )
    lanes.append(
        {
            **_summarize("random_prob_matched_n_floor", rand_eval.with_columns(pl.col("pnl_eval").alias("pnl"))),
            "note": "p_model~U(0,1); top-|edge| with |edge|>=0.12 matched to king n",
        }
    )

    # 3) naive prior edge
    if "line" in univ.columns and "p_market" in univ.columns:
        naive_u = _attach_naive_edge(u)
        naive_picks = _pick_topk_by_edge(naive_u, "edge_naive", k, FLOOR)
        naive_eval = naive_picks.with_columns(
            pl.when(pl.col("stake") > 0)
            .then(pl.col("pnl"))
            .otherwise(
                pl.when(pl.col("result") == "win")
                .then(pl.col("stake_eff") * 0.91)
                .when(pl.col("result") == "loss")
                .then(-pl.col("stake_eff"))
                .otherwise(0.0)
            )
            .alias("pnl_eval"),
            pl.col("stake_eff").alias("stake"),
        )
        lanes.append(
            {
                **_summarize(
                    "naive_prior_matched_n_floor",
                    naive_eval.with_columns(pl.col("pnl_eval").alias("pnl")),
                ),
                "note": "sigmoid(E[K]-line) prior with k_hat from rolling k_rate or 0.22; matched n/floor",
            }
        )

    # 4) shuffle-edge null: permute king edges onto same dates pool size
    if k > 0:
        shuffled = king.with_columns(
            pl.Series("edge_shuf", RNG.permutation(king["edge"].to_numpy()))
        )
        # keep rows that still clear floor under shuffled edge (may be fewer)
        shuf_keep = shuffled.filter(pl.col("edge_shuf").abs() >= FLOOR)
        lanes.append(
            {
                **_summarize("shuffle_edge_on_king_set", shuf_keep),
                "note": "permute realized KING edges within the KING set; keep |edge|>=0.12",
            }
        )

    payload = {
        "generated": "2026-09-01",
        "freeze": FREEZE,
        "floor": FLOOR,
        "matched_n": k,
        "definition": (
            "Post-freeze null lanes matched to KING passes_floor count where possible. "
            "Random/naive may include stake-imputed candidates; interpret ROI cautiously."
        ),
        "lanes": lanes,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def row(L: dict) -> str:
        return (
            f"| {L.get('name','')} | {L.get('n',0)} | {L.get('roi')} | {L.get('win_rate')} | "
            f"{L.get('clv_mean_pp')} | {L.get('clv_gt0_share')} |"
        )

    md = "\n".join(
        [
            "# SSAC27 Item 8 — Null / placebo decision lanes (2026-09-01)",
            "",
            "Post-freeze matched nulls vs locked KING floor gate.",
            "",
            "| Lane | n | ROI | Win rate | CLV mean | CLV>0 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *[row(L) for L in lanes],
            "",
            "Source JSON: `artifacts/odds_log/null_decision_lane_20260901.json`.",
            "",
            "## Read carefully",
            "",
            "- KING lane uses real stakes (`passes_floor`).",
            "- Random/naive may impute stake for logged non-bet candidates; they are **null references**, not production policies.",
            "- If KING does not beat these nulls on ROI *and* CLV with margin, do not claim decision-layer edge.",
            "",
        ]
    )
    OUT_REPORT.write_text(md, encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
