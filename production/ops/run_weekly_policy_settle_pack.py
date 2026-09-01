"""Weekly policy settle pack: parallel ledgers + game_date block bootstrap.

Scores status-quo KING floor vs veto / asym candidates on the deduped settled
ledger. Research / ops only — does NOT edit KING_PROFILE or live floors.

Example:
  python production/ops/run_weekly_policy_settle_pack.py
  python production/ops/run_weekly_policy_settle_pack.py --n-boot 2000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props, settled_bets  # noqa: E402

LEDGER = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "weekly_policy_settle_pack_latest.json"
OUT_PARQUET = ROOT / "artifacts" / "odds_log" / "weekly_policy_parallel_ledgers.parquet"
OUT_REPORT = (
    ROOT / "docs" / "reference" / "reports" / "weekly_policy_settle_pack_latest.md"
)
FREEZE = "2026-08-21"
UNDER_FLOOR = 0.12
OVER_FLOOR_ASYM = 0.16
LOW_OVER_LINES = (2.5, 3.5, 4.5)


def _roi(stake: float, pnl: float) -> float | None:
    return round(pnl / stake, 4) if stake else None


def summarize(name: str, frame: pl.DataFrame) -> dict[str, Any]:
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
    clv = (
        frame["clv_pp"].drop_nulls()
        if "clv_pp" in frame.columns
        else pl.Series([], dtype=pl.Float64)
    )
    wins = frame.filter(pl.col("result") == "win").height
    return {
        "name": name,
        "n": frame.height,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": _roi(stake, pnl),
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


def line_side_table(frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if frame.is_empty():
        return rows
    for keys, sub in frame.group_by(["line", "side"]):
        line, side = keys
        stake = float(sub["stake"].sum())
        pnl = float(sub["pnl"].sum())
        rows.append(
            {
                "line": float(line),
                "side": str(side),
                "n": sub.height,
                "stake": round(stake, 2),
                "pnl": round(pnl, 2),
                "roi": _roi(stake, pnl),
                "win_rate": round(
                    sub.filter(pl.col("result") == "win").height / sub.height, 4
                ),
            }
        )
    return sorted(rows, key=lambda r: (r["line"], r["side"]))


def brier_skill(frame: pl.DataFrame) -> dict[str, Any]:
    need = {"p_model", "p_market", "result"}
    if not need.issubset(set(frame.columns)):
        return {"available": False, "reason": "missing p_model/p_market"}
    x = frame.filter(
        pl.col("p_model").is_not_null()
        & pl.col("p_market").is_not_null()
        & pl.col("result").is_in(["win", "loss"])
    )
    if x.height < 8:
        return {"available": True, "n": x.height, "note": "insufficient_rows"}
    y = (x["result"] == "win").cast(pl.Float64).to_numpy()
    pm = x["p_model"].cast(pl.Float64).to_numpy()
    mk = x["p_market"].cast(pl.Float64).to_numpy()
    brier_m = float(np.mean((pm - y) ** 2))
    brier_k = float(np.mean((mk - y) ** 2))
    return {
        "available": True,
        "n": int(x.height),
        "brier_model": round(brier_m, 5),
        "brier_market": round(brier_k, 5),
        "brier_skill_vs_market": round(1.0 - brier_m / brier_k, 5)
        if brier_k > 0
        else None,
    }


def block_bootstrap_roi(
    frame: pl.DataFrame,
    *,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    if frame.is_empty() or "game_date" not in frame.columns:
        return {
            "n_boot": 0,
            "n_blocks": 0,
            "roi_p025": None,
            "roi_p50": None,
            "roi_p975": None,
        }
    blocks = {str(d): sub for d, sub in frame.group_by("game_date")}
    keys = list(blocks.keys())
    if len(keys) < 3:
        return {
            "n_boot": 0,
            "n_blocks": len(keys),
            "note": "need >=3 game_date blocks",
            "roi_p025": None,
            "roi_p50": None,
            "roi_p975": None,
        }
    rng = np.random.default_rng(seed)
    rois: list[float] = []
    for _ in range(n_boot):
        draw = rng.choice(keys, size=len(keys), replace=True)
        stake = 0.0
        pnl = 0.0
        for k in draw:
            stake += float(blocks[k]["stake"].sum())
            pnl += float(blocks[k]["pnl"].sum())
        if stake > 0:
            rois.append(pnl / stake)
    if not rois:
        return {
            "n_boot": n_boot,
            "n_blocks": len(keys),
            "roi_p025": None,
            "roi_p50": None,
            "roi_p975": None,
        }
    arr = np.asarray(rois, dtype=np.float64)
    return {
        "n_boot": n_boot,
        "n_blocks": len(keys),
        "roi_p025": round(float(np.quantile(arr, 0.025)), 4),
        "roi_p50": round(float(np.quantile(arr, 0.50)), 4),
        "roi_p975": round(float(np.quantile(arr, 0.975)), 4),
    }


def build_policies(post: pl.DataFrame) -> dict[str, pl.DataFrame]:
    status_quo = post.filter(
        (pl.col("passes_floor") == True) & (pl.col("stake") > 0)  # noqa: E712
    )
    if "edge" not in post.columns:
        asymmetric = status_quo.clear()
    else:
        med_stake = float(status_quo["stake"].median()) if status_quo.height else 50.0
        candidates = (
            post.filter(pl.col("edge").is_not_null())
            .with_columns(
                pl.col("edge").abs().alias("abs_edge"),
                pl.when(pl.col("stake") > 0)
                .then(pl.col("stake"))
                .otherwise(pl.lit(med_stake))
                .alias("stake_eff"),
            )
            .with_columns(
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
        )
        asymmetric = candidates.filter(
            ((pl.col("side") == "under") & (pl.col("abs_edge") >= UNDER_FLOOR))
            | ((pl.col("side") == "over") & (pl.col("abs_edge") >= OVER_FLOOR_ASYM))
        ).with_columns(
            pl.col("stake_eff").alias("stake"),
            pl.col("pnl_eff").alias("pnl"),
        )

    return {
        "status_quo_king_floor": status_quo,
        "veto_4_5_over": status_quo.filter(
            ~((pl.col("side") == "over") & (pl.col("line") == 4.5))
        ),
        "veto_2_5_over": status_quo.filter(
            ~((pl.col("side") == "over") & (pl.col("line") == 2.5))
        ),
        "probation_skip_2_5_3_5_over": status_quo.filter(
            ~((pl.col("side") == "over") & (pl.col("line").is_in([2.5, 3.5])))
        ),
        "veto_low_line_overs_le4_5": status_quo.filter(
            ~((pl.col("side") == "over") & (pl.col("line").is_in(list(LOW_OVER_LINES))))
        ),
        "asym_over16_under12": asymmetric,
        "asym16_plus_veto_4_5": asymmetric.filter(
            ~((pl.col("side") == "over") & (pl.col("line") == 4.5))
        ),
    }


def write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# Weekly policy settle pack",
        "",
        f"**Generated:** {payload['generated_at'][:19]}Z  ",
        f"**Window:** game_date > {payload['freeze']} (post-freeze)  ",
        "**Status:** ops / shadow — does not edit live KING.",
        "",
        "## Locked live skip plan (2026-09-01)",
        "",
        "| Line / side | Live action | Why |",
        "| --- | --- | --- |",
        "| **4.5 over** | **HARD SKIP** | Clearest bleed |",
        "| 2.5 over | Soft probation | Tiny n, red |",
        "| 3.5 over | Soft probation | Mild red; no hard veto yet |",
        "| 5.5 over | Watch / discretionary | All-time ugly, post-freeze thin |",
        "| Unders (incl. 4.5 under) | Keep | Unders carrying results |",
        "| Book-quality filter | WONT_DO | Lines usually synced |",
        "",
        "## Policy lanes (point estimates)",
        "",
        "| Lane | n | ROI | WR | CLV>0 | over/under |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for lane in payload["lanes"]:
        lines.append(
            f"| `{lane['name']}` | {lane['n']} | {lane['roi']} | {lane['win_rate']} | "
            f"{lane['clv_gt0_share']} | {lane['n_over']}/{lane['n_under']} |"
        )
    lines += [
        "",
        "## Block-bootstrap ROI (by game_date)",
        "",
        "| Lane | blocks | p2.5 | p50 | p97.5 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, boot in payload["bootstrap"].items():
        lines.append(
            f"| `{name}` | {boot.get('n_blocks')} | {boot.get('roi_p025')} | "
            f"{boot.get('roi_p50')} | {boot.get('roi_p975')} |"
        )
    lines += [
        "",
        "## Status-quo line × side",
        "",
        "| Line | Side | n | ROI | WR |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for row in payload["status_quo_line_side"]:
        lines.append(
            f"| {row['line']} | {row['side']} | {row['n']} | {row['roi']} | {row['win_rate']} |"
        )
    bs = payload["brier_skill"]
    lines += [
        "",
        "## Brier skill vs market (status quo)",
        f"- All: `{bs.get('all')}`",
        f"- Over: `{bs.get('over')}`",
        f"- Under: `{bs.get('under')}`",
        "",
        "## Reproduce",
        "```bash",
        "python production/ops/run_weekly_policy_settle_pack.py",
        "```",
        "",
        f"Artifacts: `{OUT_JSON.relative_to(ROOT).as_posix()}`, "
        f"`{OUT_PARQUET.relative_to(ROOT).as_posix()}`.",
        "",
    ]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260901)
    args = parser.parse_args()

    led = pl.read_parquet(LEDGER)
    post = (
        dedupe_ledger_props(settled_bets(led))
        .with_columns(pl.col("game_date").cast(pl.Utf8))
        .filter(pl.col("game_date") > FREEZE)
    )
    policies = build_policies(post)
    lanes = [summarize(name, frame) for name, frame in policies.items()]
    boot_names = (
        "status_quo_king_floor",
        "veto_4_5_over",
        "asym16_plus_veto_4_5",
        "veto_low_line_overs_le4_5",
    )
    bootstrap = {
        name: block_bootstrap_roi(
            policies[name], n_boot=args.n_boot, seed=args.seed + i
        )
        for i, name in enumerate(boot_names)
    }

    keep_pref = (
        "game_date",
        "player_name",
        "pitcher",
        "line",
        "side",
        "stake",
        "pnl",
        "result",
        "edge",
        "clv_pp",
        "p_model",
        "p_market",
        "bet_price",
    )
    parts: list[pl.DataFrame] = []
    for name, frame in policies.items():
        if frame.is_empty():
            continue
        cols = [c for c in keep_pref if c in frame.columns]
        parts.append(frame.select(cols).with_columns(pl.lit(name).alias("policy")))
    parallel = pl.concat(parts, how="diagonal_relaxed") if parts else pl.DataFrame()

    status_quo = policies["status_quo_king_floor"]
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freeze": FREEZE,
        "n_boot": args.n_boot,
        "live_skip_plan": {
            "hard_skip": ["4.5_over"],
            "soft_probation": ["2.5_over", "3.5_over"],
            "watch": ["5.5_over"],
            "keep": ["unders", "4.5_under"],
            "wont_do": ["book_quality_filter"],
        },
        "lanes": lanes,
        "bootstrap": bootstrap,
        "status_quo_line_side": line_side_table(status_quo),
        "brier_skill": {
            "all": brier_skill(status_quo),
            "over": brier_skill(status_quo.filter(pl.col("side") == "over")),
            "under": brier_skill(status_quo.filter(pl.col("side") == "under")),
        },
        "note": (
            "asym_* may include stake-imputed non-KING candidates; "
            "prefer veto_4_5_over for live-money comparison."
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not parallel.is_empty():
        parallel.write_parquet(OUT_PARQUET)
    write_report(payload)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_PARQUET}")
    print(f"Wrote {OUT_REPORT}")
    for lane in lanes:
        if lane["name"] in {"status_quo_king_floor", "veto_4_5_over"}:
            print(f"  {lane['name']}: n={lane['n']} roi={lane['roi']}")


if __name__ == "__main__":
    main()
