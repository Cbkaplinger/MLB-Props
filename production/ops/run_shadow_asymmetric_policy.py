"""Shadow post-freeze asymmetric / line-veto policies vs locked KING floor.

Does NOT edit KING_PROFILE or live floors. Scores counterfactual gates on the
deduped settled ledger for game_date > FREEZE.

Example:
  python production/ops/run_shadow_asymmetric_policy.py
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
OUT_JSON = ROOT / "artifacts" / "odds_log" / "shadow_asymmetric_policy_20260901.json"
OUT_REPORT = (
    ROOT / "docs" / "reference" / "reports" / "shadow_asymmetric_policy_2026-09-01.md"
)
FREEZE = "2026-08-21"
UNDER_FLOOR = 0.12
OVER_FLOOR_ASYM = 0.16
LOW_OVER_LINES = (2.5, 3.5, 4.5)


def summarize(name: str, frame: pl.DataFrame) -> dict:
    if frame.is_empty():
        return {
            "name": name,
            "n": 0,
            "stake": 0.0,
            "pnl": 0.0,
            "roi": None,
            "win_rate": None,
            "clv_mean_pp": None,
            "clv_gt0_share": None,
            "clv_n": 0,
            "n_over": 0,
            "n_under": 0,
            "date_min": None,
            "date_max": None,
        }
    stake = float(frame["stake"].sum())
    pnl = float(frame["pnl"].sum())
    clv = frame["clv_pp"].drop_nulls()
    wins = frame.filter(pl.col("result") == "win").height
    return {
        "name": name,
        "n": frame.height,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / stake, 4) if stake else None,
        "win_rate": round(wins / frame.height, 4),
        "clv_mean_pp": None if clv.len() == 0 else round(float(clv.mean()), 4),
        "clv_gt0_share": None
        if clv.len() == 0
        else round(float((clv > 0).sum() / clv.len()), 4),
        "clv_n": int(clv.len()),
        "n_over": frame.filter(pl.col("side") == "over").height,
        "n_under": frame.filter(pl.col("side") == "under").height,
        "date_min": str(frame["game_date"].min()),
        "date_max": str(frame["game_date"].max()),
    }


def line_side_table(frame: pl.DataFrame) -> list[dict]:
    rows: list[dict] = []
    if frame.is_empty():
        return rows
    for keys, sub in frame.group_by(["line", "side"]):
        line, side = keys
        stake = float(sub["stake"].sum())
        pnl = float(sub["pnl"].sum())
        clv = sub["clv_pp"].drop_nulls()
        rows.append(
            {
                "line": float(line),
                "side": str(side),
                "n": sub.height,
                "roi": round(pnl / stake, 4) if stake else None,
                "win_rate": round(
                    sub.filter(pl.col("result") == "win").height / sub.height, 4
                ),
                "clv_mean_pp": None if clv.len() == 0 else round(float(clv.mean()), 4),
                "clv_n": int(clv.len()),
                "pnl": round(pnl, 2),
            }
        )
    return sorted(rows, key=lambda r: (r["line"], r["side"]))


def brier_skill_vs_market(frame: pl.DataFrame) -> dict | None:
    cols = set(frame.columns)
    if not {"p_model", "p_market", "result"}.issubset(cols):
        return {"available": False, "reason": "missing p_model/p_market columns"}
    x = frame.filter(
        pl.col("p_model").is_not_null()
        & pl.col("p_market").is_not_null()
        & pl.col("result").is_in(["win", "loss"])
    )
    if x.height < 10:
        return {"available": True, "n": x.height, "note": "insufficient_rows"}
    y = (x["result"] == "win").cast(pl.Float64)
    pm = x["p_model"].cast(pl.Float64)
    mk = x["p_market"].cast(pl.Float64)
    brier_m = float(((pm - y) ** 2).mean())
    brier_k = float(((mk - y) ** 2).mean())
    return {
        "available": True,
        "n": x.height,
        "brier_model": round(brier_m, 5),
        "brier_market": round(brier_k, 5),
        "brier_skill_vs_market": round(1.0 - brier_m / brier_k, 5)
        if brier_k
        else None,
    }


def main() -> None:
    led = pl.read_parquet(LEDGER)
    ded = dedupe_ledger_props(settled_bets(led)).with_columns(
        pl.col("game_date").cast(pl.Utf8),
        pl.col("edge").abs().alias("abs_edge"),
    )
    post = ded.filter(pl.col("game_date") > FREEZE)
    status_quo = post.filter(
        (pl.col("passes_floor") == True) & (pl.col("stake") > 0)  # noqa: E712
    )

    med_stake = float(status_quo["stake"].median()) if status_quo.height else 50.0
    candidates = post.filter(pl.col("edge").is_not_null()).with_columns(
        pl.when(pl.col("stake") > 0)
        .then(pl.col("stake"))
        .otherwise(pl.lit(med_stake))
        .alias("stake_eff")
    ).with_columns(
        pl.when(pl.col("stake") > 0)
        .then(pl.col("pnl"))
        .otherwise(
            pl.when(pl.col("result") == "win")
            .then(pl.col("stake_eff") * 0.91)
            .when(pl.col("result") == "loss")
            .then(-pl.col("stake_eff"))
            .otherwise(0.0)
        )
        .alias("pnl_eff")
    )

    asymmetric = candidates.filter(
        ((pl.col("side") == "under") & (pl.col("abs_edge") >= UNDER_FLOOR))
        | ((pl.col("side") == "over") & (pl.col("abs_edge") >= OVER_FLOOR_ASYM))
    ).with_columns(
        pl.col("stake_eff").alias("stake"),
        pl.col("pnl_eff").alias("pnl"),
    )

    policies: dict[str, pl.DataFrame] = {
        "status_quo_king_floor": status_quo,
        "veto_4_5_over": status_quo.filter(
            ~((pl.col("side") == "over") & (pl.col("line") == 4.5))
        ),
        "veto_low_line_overs": status_quo.filter(
            ~(
                (pl.col("side") == "over")
                & (pl.col("line").is_in(list(LOW_OVER_LINES)))
            )
        ),
        "asym_over16_under12": asymmetric,
        "asym16_plus_veto_4_5": asymmetric.filter(
            ~((pl.col("side") == "over") & (pl.col("line") == 4.5))
        ),
    }

    lanes = [summarize(name, frame) for name, frame in policies.items()]
    line_side = line_side_table(status_quo)
    payload = {
        "generated": "2026-09-01",
        "freeze": FREEZE,
        "note": (
            "Shadow only — does not modify KING_PROFILE. "
            "asym_* may include stake-imputed candidates; prefer status_quo / veto_* "
            "for money comparisons when possible."
        ),
        "lanes": lanes,
        "status_quo_line_side": line_side,
        "brier_skill": {
            "status_quo": brier_skill_vs_market(status_quo),
            "status_quo_over": brier_skill_vs_market(
                status_quo.filter(pl.col("side") == "over")
            ),
            "status_quo_under": brier_skill_vs_market(
                status_quo.filter(pl.col("side") == "under")
            ),
        },
        "promotion_gates": {
            "min_weeks_or_n": ">=3 weeks post-freeze OR >=40 tickets under candidate",
            "roi": "candidate ROI >= status_quo on same dates (prefer >= 0)",
            "clv": "gated CLV>0 share >= 0.52 or no material regression",
            "signoff": "explicit user edit of KING_PROFILE / live floors",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def lane_row(lane: dict) -> str:
        return (
            f"| `{lane.get('name')}` | {lane.get('n', 0)} | {lane.get('roi')} | "
            f"{lane.get('win_rate')} | {lane.get('clv_mean_pp')} | "
            f"{lane.get('clv_gt0_share')} | {lane.get('n_over')}/{lane.get('n_under')} |"
        )

    ls_lines = [
        f"| {row['line']} | {row['side']} | {row['n']} | {row['roi']} | "
        f"{row['win_rate']} | {row['clv_mean_pp']} | {row['clv_n']} |"
        for row in line_side
    ]

    report = "\n".join(
        [
            "# Shadow asymmetric / line-veto policy (2026-09-01)",
            "",
            "Post-freeze counterfactuals vs locked KING floor. **No live config change.**",
            "",
            "Producer: `production/ops/run_shadow_asymmetric_policy.py`",
            "Stance: `docs/reference/reports/interim_postfreeze_ops_stance_2026-09-01.md`",
            "",
            "## Policy lanes",
            "",
            "| Lane | n | ROI | WR | CLV mean | CLV>0 | n_over/under |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *[lane_row(lane) for lane in lanes],
            "",
            "## Status-quo side × line (KING floor)",
            "",
            "| Line | Side | n | ROI | WR | CLV mean | CLV n |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
            *ls_lines,
            "",
            "## Brier skill vs market (status quo)",
            "",
            "```json",
            json.dumps(payload["brier_skill"], indent=2),
            "```",
            "",
            "## Read carefully",
            "",
            "- `status_quo` / `veto_*` use real KING `passes_floor` stakes.",
            "- `asym_*` may impute stake on non-bet candidates that clear the asymmetric edge gate — treat as directional shadow, not bankroll truth.",
            "- Promote only under gates in the interim stance doc.",
            "",
            f"JSON: `{OUT_JSON.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(json.dumps({"lanes": lanes, "brier_skill": payload["brier_skill"]}, indent=2))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
