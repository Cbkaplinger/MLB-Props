"""Phase D follow-up — screen MIN_STARTER_BATTERS_FACED cutoffs in {5..10}.

Does not retrain models. Reports population composition and target stability at
each threshold so we can see whether 9 is an elbow or arbitrary.

Examples:
    python models/Strikeout-Model/research/phase_d_pa_cutoff_screen.py
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

CUTOFFS = (5, 6, 7, 8, 9, 10)


def _cohort_metrics(frame: pl.DataFrame) -> dict[str, float | int | None]:
    if frame.is_empty():
        return {
            "n": 0,
            "pa_mean": None,
            "pa_median": None,
            "k_mean": None,
            "k_rate_mean": None,
            "k_rate_std": None,
            "outs_mean": None,
        }
    work = frame.with_columns(
        (pl.col("K") / pl.max_horizontal(pl.col("PA"), pl.lit(1))).alias("k_rate")
    )
    return {
        "n": int(work.height),
        "pa_mean": float(work["PA"].mean()),
        "pa_median": float(work["PA"].median()),
        "k_mean": float(work["K"].mean()),
        "k_rate_mean": float(work["k_rate"].mean()),
        "k_rate_std": float(work["k_rate"].std()),
        "outs_mean": float(work["Outs"].mean()),
    }


def main(*, seasons: tuple[int, ...]) -> None:
    cached = (
        config.OUTPUT_DIR
        / "model_quality"
        / "phase_d_population"
        / "all_first_pitchers.parquet"
    )
    if cached.exists():
        print(f"Loading cached first-pitcher frame {cached}...", flush=True)
        all_starts = pl.read_parquet(cached).filter(
            pl.col("season").is_in(list(seasons))
        )
    else:
        print(f"Loading Statcast {seasons}...", flush=True)
        raw = load_statcast_years(seasons, columns=BUILD_COLUMNS)
        all_starts = build_pitcher_starts(raw, min_batters_faced=0).filter(
            pl.col("season").is_in(list(seasons))
        )

    n_all = all_starts.height
    rows: list[dict] = []
    for cutoff in CUTOFFS:
        included = all_starts.filter(pl.col("PA") >= cutoff)
        excluded = all_starts.filter(pl.col("PA") < cutoff)
        # Marginal: rows that would be dropped when raising from cutoff-1 to cutoff
        marginal = (
            all_starts.filter(pl.col("PA") == cutoff - 1)
            if cutoff > min(CUTOFFS)
            else all_starts.filter(pl.col("PA") < cutoff)
        )
        opener_like_ex = excluded.filter(pl.col("PA") <= 6)
        short_exit_ex = excluded.filter((pl.col("PA") >= 7) & (pl.col("PA") < cutoff))

        inc = _cohort_metrics(included)
        exc = _cohort_metrics(excluded)
        marg = _cohort_metrics(marginal)
        row = {
            "cutoff": cutoff,
            "n_all": n_all,
            "n_included": inc["n"],
            "n_excluded": exc["n"],
            "excluded_share": float(exc["n"] / n_all) if n_all else 0.0,
            "included_pa_mean": inc["pa_mean"],
            "included_k_rate_mean": inc["k_rate_mean"],
            "included_k_rate_std": inc["k_rate_std"],
            "excluded_pa_mean": exc["pa_mean"],
            "excluded_k_rate_mean": exc["k_rate_mean"],
            "opener_like_pa_le_6_in_excluded": int(opener_like_ex.height),
            "short_exit_pa_7_plus_in_excluded": int(short_exit_ex.height),
            "marginal_n_at_pa_eq_cutoff_minus_1": marg["n"],
            "marginal_k_rate_mean": marg["k_rate_mean"],
            "marginal_pa_mean": marg["pa_mean"],
        }
        rows.append(row)

    # Recommendation heuristic: prefer cutoff where excluded_share is small,
    # included k_rate std stabilizes, and marginal rows at PA=cutoff-1 look like
    # short-workload noise (low PA) rather than conventional starts.
    # Soft: keep 9 unless 8 or 10 clearly dominate on excluded_share elbow + stability.
    by_cut = {r["cutoff"]: r for r in rows}
    r8, r9, r10 = by_cut[8], by_cut[9], by_cut[10]
    # Elbow: largest drop in excluded_share when raising threshold.
    elbows = []
    for a, b in zip(CUTOFFS[:-1], CUTOFFS[1:]):
        drop = by_cut[a]["excluded_share"] - by_cut[b]["excluded_share"]
        elbows.append({"from": a, "to": b, "excluded_share_drop": drop})
    # Signal to reopen: if moving 9→8 adds mostly opener-like rows with very
    # different k_rate, or 9→10 cuts a large share of near-conventional starts.
    delta_9_to_8 = r8["n_included"] - r9["n_included"]  # rows gained by lowering
    delta_9_to_10 = r9["n_included"] - r10["n_included"]  # rows lost by raising
    recommendation = {
        "keep_default": 9,
        "reason": (
            "Default 9 ≈ one time through the order. Screen for a reopen only if "
            "excluded_share elbow or k_rate stability clearly favors a neighbor."
        ),
        "n_gained_if_lower_to_8": int(delta_9_to_8),
        "n_lost_if_raise_to_10": int(delta_9_to_10),
        "excluded_share_at_8": r8["excluded_share"],
        "excluded_share_at_9": r9["excluded_share"],
        "excluded_share_at_10": r10["excluded_share"],
        "included_k_rate_std_8": r8["included_k_rate_std"],
        "included_k_rate_std_9": r9["included_k_rate_std"],
        "included_k_rate_std_10": r10["included_k_rate_std"],
        "elbows": elbows,
        "reopen_suggested": False,
        "reopen_note": "",
    }
    # Reopen if lowering to 8 adds <1% population AND does not inflate k_rate std,
    # or raising to 10 removes <0.5% and materially lowers std — weak bar; else keep 9.
    std9 = float(r9["included_k_rate_std"] or 0)
    std8 = float(r8["included_k_rate_std"] or 0)
    std10 = float(r10["included_k_rate_std"] or 0)
    if (r8["excluded_share"] - r9["excluded_share"]) < 0.005 and abs(std8 - std9) < 0.001:
        recommendation["reopen_suggested"] = False
        recommendation["reopen_note"] = (
            "8 vs 9 is nearly identical on share/stability; prefer 9 for "
            "interpretability (full turn through order)."
        )
    elif (r9["excluded_share"] - r10["excluded_share"]) > 0.02 and std10 < std9 - 0.002:
        recommendation["reopen_suggested"] = True
        recommendation["keep_default"] = 10
        recommendation["reopen_note"] = (
            "Raising to 10 removes a material short-exit mass and stabilizes "
            "k_rate — consider nested confirmation before changing production."
        )
    else:
        recommendation["reopen_note"] = (
            "No strong elbow away from 9; keep MIN_STARTER_BATTERS_FACED=9."
        )

    output_dir = config.OUTPUT_DIR / "model_quality" / "phase_d_pa_cutoff"
    output_dir.mkdir(parents=True, exist_ok=True)
    table = pl.DataFrame(rows)
    table.write_csv(output_dir / "cutoff_summary.csv")
    metadata = {
        "phase": "D-cutoff-screen",
        "seasons": list(seasons),
        "cutoffs": list(CUTOFFS),
        "n_all_first_pitchers": n_all,
        "rows": rows,
        "recommendation": recommendation,
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps({"recommendation": recommendation, "rows": rows}, indent=2))
    print(f"Wrote {output_dir / 'cutoff_summary.csv'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(config.FEATURE_RESEARCH_SEASONS),
    )
    args = parser.parse_args()
    main(seasons=tuple(args.seasons))
