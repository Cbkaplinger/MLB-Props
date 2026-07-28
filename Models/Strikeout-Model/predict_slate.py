"""Score a daily slate with frozen k-rate × TBF → count-layer probs.

Modes:
- ``--historical-date``: score Level 3 rows already in pitcher_training (wiring
  proof; no scrape).
- default / ``--live``: fetch today's RotoGrinders slate and assemble as-of
  features. Requires Level 1–2 refreshed through yesterday unless
  ``--allow-stale``.

Examples:
    python Models/Strikeout-Model/predict_slate.py --historical-date 2025-09-20
    python Models/Strikeout-Model/predict_slate.py --dry-run
    python Models/Strikeout-Model/predict_slate.py --live --allow-stale
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import polars as pl

from Python.config import OUTPUT_DIR, ensure_output_directories
from Python.daily_lineups import build_daily_slate, write_daily_slate
from Python.live_assembly import (
    DEFAULT_KRATE_STEM,
    DEFAULT_TBF_JOBLIB,
    build_live_feature_frame,
    historical_training_rows,
    load_krate_booster,
    score_frame,
)
from Python.count_layer import PROJECTION_K_LINES


_OUT_DIR = OUTPUT_DIR / "live_scores"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Live slate date (YYYY-MM-DD). Default: today ET via slate builder.",
    )
    parser.add_argument(
        "--historical-date",
        type=date.fromisoformat,
        default=None,
        help="Score pitcher_training rows for this date (no live scrape).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch slate and score with as-of Level 2 features.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch slate + validate freeze metadata only.",
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Allow live scoring when rolling history is >1 day behind the slate.",
    )
    parser.add_argument(
        "--require-confirmed",
        action="store_true",
        help="Fail unless RotoGrinders marks every lineup confirmed.",
    )
    parser.add_argument(
        "--require-probable-match",
        action="store_true",
        help="Fail when RG starter IDs disagree with MLB announced probables.",
    )
    parser.add_argument(
        "--no-dual-starters",
        action="store_true",
        help="Score only RotoGrinders starters (skip MLB probable dual rows).",
    )
    parser.add_argument(
        "--k-rate-stem",
        type=Path,
        default=DEFAULT_KRATE_STEM,
        help="Frozen LightGBM stem (.txt + .json).",
    )
    parser.add_argument(
        "--tbf-joblib",
        type=Path,
        default=DEFAULT_TBF_JOBLIB,
        help="Persisted Ridge TBF joblib.",
    )
    args = parser.parse_args()
    ensure_output_directories()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    _, features, _ = load_krate_booster(args.k_rate_stem)
    p1 = [name for name in features if name.endswith("_P1")]
    print(f"Frozen production features: {len(features)} (P1 stems: {len(p1)})")

    if args.historical_date is not None:
        frame = historical_training_rows(args.historical_date)
        print(f"Historical rows for {args.historical_date}: {len(frame)}")
        scored, report = score_frame(
            frame,
            krate_stem=args.k_rate_stem,
            tbf_joblib=args.tbf_joblib,
        )
        stamp = args.historical_date.isoformat()
        out_parquet = _OUT_DIR / f"historical_scores_{stamp}.parquet"
        out_json = _OUT_DIR / f"historical_scores_{stamp}.json"
        pl.from_pandas(scored).write_parquet(out_parquet)
        report["mode"] = "historical"
        report["game_date"] = stamp
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"Wrote {out_parquet}")
        return

    slate = build_daily_slate(
        game_date=args.date,
        require_confirmed=args.require_confirmed,
        require_probable_match=args.require_probable_match,
    )
    lineup_path, starter_path = write_daily_slate(slate)
    print(f"Starters: {slate.starters.height} -> {starter_path}")
    print(f"Lineup batters: {slate.lineups.height} -> {lineup_path}")
    if "player_name" in slate.starters.columns:
        names = slate.starters.select("player_name").to_series().to_list()
        preview = ", ".join(str(name) for name in names[:12])
        extra = f", ... (+{len(names) - 12})" if len(names) > 12 else ""
        print(f"Starters: {preview}{extra}")

    if args.dry_run and not args.live:
        print("dry-run complete — pass --live to score (or --historical-date).")
        return

    if not args.live and not args.dry_run:
        # Default after Phase 11: live score when invoked without --dry-run.
        args.live = True

    features_frame, build_meta = build_live_feature_frame(
        slate,
        allow_stale=args.allow_stale,
        dual_starters=not args.no_dual_starters,
    )
    print(json.dumps(build_meta, indent=2))
    scored, report = score_frame(
        features_frame,
        krate_stem=args.k_rate_stem,
        tbf_joblib=args.tbf_joblib,
        lines=PROJECTION_K_LINES,
    )
    report["build"] = build_meta
    stamp = build_meta["slate_date"]
    out_parquet = _OUT_DIR / f"live_scores_{stamp}.parquet"
    out_json = _OUT_DIR / f"live_scores_{stamp}.json"
    # Keep a readable projection of key columns.
    keep = [
        c
        for c in (
            "game_pk",
            "game_date",
            "player_name",
            "pitcher",
            "starter_source",
            "starter_disagreement",
            "is_preferred",
            "rg_pitcher_id",
            "mlb_probable_pitcher_id",
            "home_team",
            "away_team",
            "is_home",
            "k_rate_pred",
            "projected_tbf",
            "expected_K",
            "p_over_3_5",
            "p_over_4_5",
            "p_over_5_5",
            "p_over_6_5",
            "p_over_7_5",
            "p_over_8_5",
            "fair_amer_3_5",
            "fair_amer_4_5",
            "fair_amer_5_5",
            "fair_amer_6_5",
            "fair_amer_7_5",
            "fair_amer_8_5",
            "opp_lineup_size",
            "days_rest",
            "prior_start_date",
        )
        if c in scored.columns
    ]
    # Keep results in memory / optional write — notebook is the primary viewer.
    # CLI still writes one dated parquet for ops reuse (not playground clutter).
    pl.from_pandas(scored[keep]).write_parquet(out_parquet)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "build"}, indent=2))
    if "starter_disagreement" in scored.columns:
        n_dis = int(scored["starter_disagreement"].sum())
        print(f"Disagreement rows scored: {n_dis}")
    print(f"Wrote {out_parquet}")


if __name__ == "__main__":
    main()
