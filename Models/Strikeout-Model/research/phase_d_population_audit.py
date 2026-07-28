"""Phase D — population hygiene audit for the PA>=9 starter filter.

Rebuilds *all* first-pitcher-of-half appearances (``min_batters_faced=0``) from
Statcast and compares them to the research cohort (``PA >= 9``). This does not
leak features; it quantifies selection bias and freezes an interim policy until
pregame-observable role labels exist.

Examples:
    python models/Strikeout-Model/research/phase_d_population_audit.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from Python import config
from Python.pitcher_features import BUILD_COLUMNS, build_pitcher_starts
from Python.statcast import load_statcast_years

# Heuristic buckets (postgame observables — diagnostic only, not live features).
OPENER_LIKE_MAX_PA = 6  # typical planned opener length
SHORT_EXIT_MAX_PA = 8  # PA in {7,8}: often early hook / injury / weather


def _summarize(frame: pl.DataFrame, label: str) -> dict:
    if frame.is_empty():
        return {"label": label, "n": 0}
    work = frame.with_columns(
        (pl.col("K") / pl.max_horizontal(pl.col("PA"), pl.lit(1))).alias("k_rate")
    )
    return {
        "label": label,
        "n": int(work.height),
        "share_of_all_starters": None,  # filled by caller
        "pa_mean": float(work["PA"].mean()),
        "pa_median": float(work["PA"].median()),
        "pa_p10": float(work["PA"].quantile(0.10)),
        "pa_p90": float(work["PA"].quantile(0.90)),
        "k_mean": float(work["K"].mean()),
        "k_rate_mean": float(work["k_rate"].mean()),
        "outs_mean": float(work["Outs"].mean()) if "Outs" in work.columns else None,
    }


def main(*, seasons: tuple[int, ...], write_parquet: bool) -> None:
    print(f"Loading Statcast {seasons}...", flush=True)
    raw = load_statcast_years(seasons, columns=BUILD_COLUMNS)
    print(f"Building all first-pitcher appearances (min_batters_faced=0)...", flush=True)
    all_starts = build_pitcher_starts(raw, min_batters_faced=0)
    all_starts = all_starts.filter(pl.col("season").is_in(list(seasons)))

    research = all_starts.filter(pl.col("PA") >= config.MIN_STARTER_BATTERS_FACED)
    excluded = all_starts.filter(pl.col("PA") < config.MIN_STARTER_BATTERS_FACED)
    opener_like = excluded.filter(pl.col("PA") <= OPENER_LIKE_MAX_PA)
    short_exit = excluded.filter(
        (pl.col("PA") > OPENER_LIKE_MAX_PA) & (pl.col("PA") <= SHORT_EXIT_MAX_PA)
    )

    n_all = all_starts.height
    cohorts = {
        "all_first_pitchers": _summarize(all_starts, "all_first_pitchers"),
        "research_pa_ge_9": _summarize(research, "research_pa_ge_9"),
        "excluded_pa_lt_9": _summarize(excluded, "excluded_pa_lt_9"),
        "opener_like_pa_le_6": _summarize(opener_like, "opener_like_pa_le_6"),
        "short_exit_pa_7_8": _summarize(short_exit, "short_exit_pa_7_8"),
    }
    for key, block in cohorts.items():
        block["share_of_all_starters"] = (
            float(block["n"] / n_all) if n_all else 0.0
        )

    # PA histogram for excluded appearances.
    hist = (
        excluded.group_by("PA")
        .agg(pl.len().alias("n"))
        .sort("PA")
        .to_dicts()
        if not excluded.is_empty()
        else []
    )

    by_season = []
    for season in seasons:
        season_all = all_starts.filter(pl.col("season") == season)
        season_ex = season_all.filter(
            pl.col("PA") < config.MIN_STARTER_BATTERS_FACED
        )
        n = season_all.height
        by_season.append(
            {
                "season": int(season),
                "n_all": int(n),
                "n_research": int(
                    season_all.filter(
                        pl.col("PA") >= config.MIN_STARTER_BATTERS_FACED
                    ).height
                ),
                "n_excluded": int(season_ex.height),
                "excluded_share": float(season_ex.height / n) if n else 0.0,
                "excluded_pa_mean": (
                    float(season_ex["PA"].mean()) if season_ex.height else None
                ),
            }
        )

    # Honest estimand language + interim policy.
    policy = {
        "research_estimand": (
            "Conditional on first-pitcher appearances that ultimately faced "
            f">= {config.MIN_STARTER_BATTERS_FACED} batters (postgame filter)."
        ),
        "not_claimed": (
            "Coverage of every announced starter, planned openers, piggybacks, "
            "or early injury exits."
        ),
        "interim_live_policy": (
            "Score any announced starter with the frozen stack, but treat "
            "short-workload / opener designations as out-of-support until a "
            "pregame role flag exists. Do not claim prop calibration for "
            "planned openers."
        ),
        "required_before_pristine_v1": [
            "Pregame-observable role label (announced starter vs opener vs "
            "piggyback) from lineup/news source — not inferred from same-game PA.",
            "Report metrics separately for conventional-starter subgroup vs "
            "all announced starters.",
            "Keep PA>=9 cohort as conditional research estimand in model card.",
        ],
        "heuristic_note": (
            f"opener_like uses postgame PA<= {OPENER_LIKE_MAX_PA} among first "
            "pitchers — mixes true openers with early hooks; not a training label."
        ),
    }

    output_dir = config.OUTPUT_DIR / "model_quality" / "phase_d_population"
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "phase": "11.D / Phase D",
        "seasons": list(seasons),
        "min_starter_batters_faced": config.MIN_STARTER_BATTERS_FACED,
        "opener_like_max_pa": OPENER_LIKE_MAX_PA,
        "n_all_first_pitchers": n_all,
        "excluded_share": cohorts["excluded_pa_lt_9"]["share_of_all_starters"],
        "cohorts": cohorts,
        "excluded_pa_histogram": hist,
        "by_season": by_season,
        "policy": policy,
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    pl.DataFrame(
        [
            {k: v for k, v in block.items()}
            for block in cohorts.values()
        ]
    ).write_csv(output_dir / "cohort_summary.csv")

    if write_parquet:
        tagged = all_starts.with_columns(
            (pl.col("PA") >= config.MIN_STARTER_BATTERS_FACED).alias(
                "in_research_cohort"
            ),
            (pl.col("PA") <= OPENER_LIKE_MAX_PA).alias("opener_like_heuristic"),
        )
        tagged.write_parquet(output_dir / "all_first_pitchers.parquet")

    compact = {
        "n_all_first_pitchers": n_all,
        "excluded_share": metadata["excluded_share"],
        "research_n": cohorts["research_pa_ge_9"]["n"],
        "excluded_n": cohorts["excluded_pa_lt_9"]["n"],
        "opener_like_n": cohorts["opener_like_pa_le_6"]["n"],
        "short_exit_7_8_n": cohorts["short_exit_pa_7_8"]["n"],
        "excluded_pa_mean": cohorts["excluded_pa_lt_9"]["pa_mean"],
        "research_pa_mean": cohorts["research_pa_ge_9"]["pa_mean"],
        "excluded_k_rate_mean": cohorts["excluded_pa_lt_9"]["k_rate_mean"],
        "research_k_rate_mean": cohorts["research_pa_ge_9"]["k_rate_mean"],
        "by_season": by_season,
    }
    print(json.dumps(compact, indent=2))
    print(f"Wrote {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(config.FEATURE_RESEARCH_SEASONS),
    )
    parser.add_argument(
        "--no-parquet",
        action="store_true",
        help="Skip writing all_first_pitchers.parquet.",
    )
    args = parser.parse_args()
    main(seasons=tuple(args.seasons), write_parquet=not args.no_parquet)
