"""Score one pitcher against every other MLB club (counterfactual).

Prints a ranked table to stdout. Does **not** write parquet unless you pass
``--write``.

Examples:
    python playground/whatif_pitcher.py --pitcher-id 519242
    python playground/whatif_pitcher.py --name "Chris Sale" --away
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import identity  # noqa: E402
from Python.whatif import score_pitcher_vs_league  # noqa: E402


def _resolve_pitcher_id(name: str) -> int:
    players = identity.load_player_map()
    key = name.strip().lower()
    hits = players.filter(pl.col("player_name").str.to_lowercase() == key)
    if hits.is_empty():
        hits = players.filter(pl.col("player_name").str.to_lowercase().str.contains(key))
    if hits.is_empty():
        raise SystemExit(f"No player_map match for {name!r}")
    if hits.height > 1:
        preview = hits.head(8).to_dicts()
        raise SystemExit(f"Ambiguous name {name!r}; matches={preview}")
    return int(hits["mlb_id"][0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pitcher-id", type=int, default=None)
    parser.add_argument("--name", type=str, default=None, help='e.g. "Chris Sale"')
    parser.add_argument(
        "--asof",
        type=date.fromisoformat,
        default=None,
        help="As-of date (YYYY-MM-DD). Default: today ET.",
    )
    parser.add_argument(
        "--away",
        action="store_true",
        help="Pitcher as visitor (default: home).",
    )
    parser.add_argument(
        "--no-live-lineups",
        action="store_true",
        help="Skip RG fetch; use recent batting orders only.",
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        default=True,
        help="Allow rolling >1 day behind asof (default on for demos).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Optional: write parquet/json under artifacts/playground/.",
    )
    args = parser.parse_args()

    if args.pitcher_id is None and not args.name:
        raise SystemExit("Pass --pitcher-id or --name")
    pitcher_id = args.pitcher_id or _resolve_pitcher_id(args.name)

    scored, report = score_pitcher_vs_league(
        pitcher_id,
        asof=args.asof,
        pitcher_is_home=not args.away,
        allow_stale=args.allow_stale,
        use_live_lineups=not args.no_live_lineups,
    )
    keep = [
        c
        for c in (
            "player_name",
            "pitcher",
            "pitch_team",
            "opp_team",
            "home_team",
            "is_home",
            "lineup_source",
            "k_rate_pred",
            "projected_tbf",
            "expected_K",
            "p_over_4_5",
            "p_over_5_5",
            "p_over_6_5",
            "opp_lineup_k",
            "opp_lineup_size",
        )
        if c in scored.columns
    ]
    out = pl.from_pandas(scored[keep]).sort("expected_K", descending=True)

    show = out.select(
        "opp_team", "expected_K", "p_over_5_5", "projected_tbf", "k_rate_pred"
    )
    for row in show.iter_rows(named=True):
        print(
            f"{row['opp_team']:>3}  expected_K={row['expected_K']:5.2f}  "
            f"p_over_5.5={row['p_over_5_5']:.3f}  "
            f"TBF={row['projected_tbf']:6.2f}  k_rate={row['k_rate_pred']:.3f}"
        )
    print(
        f"\n{report['whatif']['n_opponents']} opponents | "
        f"mean expected_K={float(out['expected_K'].mean()):.2f}"
    )

    if args.write:
        from Python import config

        stamp = report["whatif"]["asof"]
        dest = config.OUTPUT_DIR / "playground"
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"whatif_{pitcher_id}_{stamp}.parquet"
        meta_path = dest / f"whatif_{pitcher_id}_{stamp}.json"
        out.write_parquet(out_path)
        meta_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
