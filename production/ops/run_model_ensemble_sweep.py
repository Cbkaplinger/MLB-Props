"""Sweep weighted model ensembles and rank by profit-first policy metrics.

This runner:
1) Loads top model-family ablation summary (for context table).
2) Scores settled-ledger rows for selected feature-set models.
3) Builds weighted blends of model probabilities on the same row universe.
4) Sweeps edge floors and ranks blends by ROI + risk profile.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl

from compare_feature_set_market_skill import _prob_metrics
from edge_floor_sweep_governance import (
    _apply_recent_window,
    _load_settled_ledger,
    _risk_metrics,
    _score_model_rows,
)
from Python import config

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "artifacts" / "odds_log"
ABLATION_DEFAULT = (
    ROOT
    / "artifacts"
    / "model_quality"
    / "sparse72_model_family_ablation"
    / "xgb_full_aug21"
    / "ablation_summary_ranked.csv"
)


def _weight_grid(n_models: int, step: float) -> Iterable[tuple[float, ...]]:
    units = int(round(1.0 / step))
    if n_models == 2:
        for i in range(units + 1):
            w0 = i / units
            yield (w0, 1.0 - w0)
        return
    if n_models == 3:
        for i in range(units + 1):
            for j in range(units + 1 - i):
                k = units - i - j
                yield (i / units, j / units, k / units)
        return
    raise ValueError("Weight grid currently supports 2 or 3 models.")


def _fingerprint(df: pd.DataFrame) -> pd.Series:
    cols = ["game_date", "game_pk", "pitcher", "line", "side", "bet_price"]
    return (
        df[cols]
        .astype(str)
        .agg("|".join, axis=1)
        .rename("row_id")
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--feature-set",
        action="append",
        default=[],
    )
    p.add_argument("--calibration-mode", default="isotonic", choices=["raw", "platt", "isotonic"])
    p.add_argument("--weight-step", type=float, default=0.1)
    p.add_argument("--floor-min", type=float, default=0.005)
    p.add_argument("--floor-max", type=float, default=0.08)
    p.add_argument("--floor-step", type=float, default=0.005)
    p.add_argument("--min-bets", type=int, default=25)
    p.add_argument("--recent-settled", type=int, default=0)
    p.add_argument(
        "--dedupe-manual",
        action="store_true",
        help="Use one ticket per (game_date, player_name, line, side) via highest edge, best price, largest stake.",
    )
    p.add_argument("--ablation-summary-csv", default=str(ABLATION_DEFAULT))
    p.add_argument("--output-tag", default="")
    args = p.parse_args()

    feature_sets = args.feature_set if args.feature_set else [
        "production_sparse72",
        "production_sparse72_monotone",
        "production_final58_consensus",
    ]
    if len(feature_sets) not in (2, 3):
        raise SystemExit("Use 2 or 3 --feature-set values for ensemble sweep.")

    floors = np.arange(args.floor_min, args.floor_max + 1e-12, args.floor_step)
    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Datetime, strict=False)
    )
    settled_all = _load_settled_ledger()
    settled = _apply_recent_window(settled_all, args.recent_settled if args.recent_settled > 0 else None)

    scored_parts: dict[str, pd.DataFrame] = {}
    for fs in feature_sets:
        scored = _score_model_rows(frame_all_pl, settled, fs, args.calibration_mode)
        if scored.empty:
            raise SystemExit(f"No scored rows for {fs}.")
        scored = scored.copy()
        scored["row_id"] = _fingerprint(scored)
        scored_parts[fs] = scored

    anchor = feature_sets[0]
    base_cols = [
        "row_id",
        "y",
        "p_market",
        "stake",
        "game_date",
        "clv_pp",
        "player_name",
        "line",
        "side",
        "bet_price",
    ]
    base = scored_parts[anchor][[c for c in base_cols if c in scored_parts[anchor].columns]].copy()
    for fs, df in scored_parts.items():
        base = base.merge(
            df[["row_id", "p_model", "rpd"]].rename(
                columns={"p_model": f"p_model__{fs}", "rpd": f"rpd__{fs}"}
            ),
            on="row_id",
            how="inner",
        )

    all_rows: list[dict[str, object]] = []
    for weights in _weight_grid(len(feature_sets), args.weight_step):
        label_bits = [f"{fs}:{w:.2f}" for fs, w in zip(feature_sets, weights)]
        blend_label = "blend|" + ",".join(label_bits)
        probs = np.zeros(len(base), dtype=np.float64)
        for fs, w in zip(feature_sets, weights):
            probs += float(w) * base[f"p_model__{fs}"].to_numpy(dtype=np.float64)
        work = base.copy()
        work["p_model"] = np.clip(probs, 1e-6, 1 - 1e-6)
        # Realized return per ticket is market-realized and model-invariant.
        work["rpd"] = base[f"rpd__{anchor}"].to_numpy(dtype=np.float64)
        work["edge"] = work["p_model"] - work["p_market"]
        if args.dedupe_manual:
            keep_cols = ["game_date", "player_name", "line", "side", "edge", "bet_price", "stake"]
            if all(c in work.columns for c in keep_cols):
                work = (
                    work.sort_values(
                        by=["edge", "bet_price", "stake"],
                        ascending=[False, False, False],
                    )
                    .drop_duplicates(
                        subset=["game_date", "player_name", "line", "side"],
                        keep="first",
                    )
                    .reset_index(drop=True)
                )

        skill = _prob_metrics(
            work["y"].to_numpy(dtype=np.float64),
            work["p_model"].to_numpy(dtype=np.float64),
            work["p_market"].to_numpy(dtype=np.float64),
        )
        for floor in floors:
            scoped = work[work["edge"] >= float(floor)].copy()
            risk = _risk_metrics(scoped)
            all_rows.append(
                {
                    "blend_label": blend_label,
                    "feature_sets": ",".join(feature_sets),
                    "weights_json": json.dumps({fs: float(w) for fs, w in zip(feature_sets, weights)}),
                    "calibration_mode": args.calibration_mode,
                    "edge_floor": float(floor),
                    **skill,
                    **risk,
                }
            )

    out = pd.DataFrame(all_rows)
    if out.empty:
        raise SystemExit("No ensemble rows produced.")
    out["eligible"] = out["n_bets"] >= int(args.min_bets)
    out["profit_score"] = (
        out["roi"].fillna(-999.0) * 4.0
        + out["sortino"].fillna(-999.0) * 2.5
        + out["sharpe"].fillna(-999.0) * 1.5
        + out["positive_clv_share"].fillna(0.0) * 0.75
        - out["max_drawdown_pct"].fillna(9.0) * 1.0
    )
    eligible = out[out["eligible"]].copy()
    if eligible.empty:
        eligible = out.copy()
    best = (
        eligible.sort_values(
            [
                "profit_score",
                "roi",
                "sortino",
                "brier_skill_vs_market",
                "logloss_skill_vs_market",
                "n_bets",
            ],
            ascending=[False, False, False, False, False, False],
        )
        .reset_index(drop=True)
    )
    best["rank"] = np.arange(1, len(best) + 1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.output_tag.strip() or ts
    out_csv = OUT_DIR / f"ensemble_sweep_{tag}.csv"
    best_csv = OUT_DIR / f"ensemble_sweep_ranked_{tag}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    best.to_csv(best_csv, index=False)

    ablation_note: dict[str, object] = {"ablation_summary_csv": args.ablation_summary_csv, "loaded": False}
    ablation_path = Path(args.ablation_summary_csv)
    if ablation_path.exists():
        ab = pd.read_csv(ablation_path)
        idx = ab.groupby("model_family")["mean_expected_k_mae"].idxmin()
        top = (
            ab.loc[idx, ["model_family", "feature_set", "mean_expected_k_mae", "mean_k_rate_mae"]]
            .sort_values("mean_expected_k_mae")
            .to_dict(orient="records")
        )
        ablation_note["loaded"] = True
        ablation_note["top_by_family"] = top

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": feature_sets,
        "calibration_mode": args.calibration_mode,
        "weight_step": args.weight_step,
        "edge_floors": {"min": args.floor_min, "max": args.floor_max, "step": args.floor_step},
        "min_bets_gate": args.min_bets,
        "dedupe_manual": bool(args.dedupe_manual),
        "rows_total": int(len(out)),
        "winner": best.iloc[0].to_dict(),
        "files": {"full_csv": str(out_csv), "ranked_csv": str(best_csv)},
        "ablation_context": ablation_note,
    }
    json_path = OUT_DIR / f"ensemble_sweep_{tag}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(best.head(20).to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

