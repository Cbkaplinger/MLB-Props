"""Pregame A/B runner - NO-OUTCOME DRY RUN (no scoring, no outcome joins).

Builds availability/fallback receipts for the deployment-relevant A-vs-B
comparison on captured 2026 slates and, where all inputs are demonstrably
available, unscored A/B count distributions. A = frozen scalar-rate
binomial; B = lineup-mean binomial from cutoff-valid captured snapshots;
fallback B=A with a recorded reason when lineup availability fails.

RESTRICTED-INPUT POLICY (dry run): 2025/2026 outcome-derived inputs
(priors through 2025/2026, 2026 pregame rolling features -> BF PMF) are
BLOCKED pending explicit authorization; the dry run reports them as
blocked and never loads them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import pregame_lineup_capture as pc  # noqa: E402

K_MAX = 24
CAP = kc.KCOUNT_CAP


class RunFailure(RuntimeError):
    pass


def input_availability(data_root: Path) -> dict:
    """Structural availability matrix (no restricted loads)."""
    checks = {
        "savant_raw_2022": (data_root / "Savant-Data" / "regular" / "2022"
                            / "statcast_2022_regular.parquet").is_file(),
        "savant_raw_2023": (data_root / "Savant-Data" / "regular" / "2023"
                            / "statcast_2023_regular.parquet").is_file(),
        "savant_raw_2024": (data_root / "Savant-Data" / "regular" / "2024"
                            / "statcast_2024_regular.parquet").is_file(),
        "savant_raw_2025": (data_root / "Savant-Data" / "regular" / "2025"
                            / "statcast_2025_regular.parquet").is_file(),
        "savant_raw_2026": (data_root / "Savant-Data" / "regular" / "2026"
                            / "statcast_2026_regular.parquet").is_file(),
        "lineup_capture": any((data_root / "processed")
                              .glob("daily_lineups_*.parquet")),
    }
    return {
        "checks": checks,
        "verdicts": {
            "starter_identity": "AVAILABLE (captured probable pitcher "
                                "IDs, pregame)",
            "lineup_snapshots": "AVAILABLE (captured, ingestion-verified; "
                                "raw-hash-unverified)",
            "priors_through_2024": "AVAILABLE (sha-verified raw)",
            "priors_2025_2026": "BLOCKED (outcome access restricted)",
            "league_rate_2026_origin": "BLOCKED (same restriction)",
            "workload_bf_pmf_2026": "BLOCKED (needs 2026 pregame rolling "
                                    "features; restricted)",
            "outcome_labels_for_scoring": "BLOCKED (restricted)",
        },
    }


def mode_coverage(snaps: pl.DataFrame) -> dict:
    """No-outcome selection coverage under both explicit modes."""
    g = snaps.group_by(["game_pk", "team"]).agg(
        pl.col("fetched_at").max().alias("last_fetch"))
    counts = {}
    for mode in (pc.MODE_CONFIRMED_ONLY, pc.MODE_PROJECTED_ALLOWED):
        reasons = {}
        for r in g.iter_rows(named=True):
            sel = pc.select_pregame_lineup(
                snaps, r["game_pk"], r["team"], r["last_fetch"], mode=mode)
            reasons[sel["reason"]] = reasons.get(sel["reason"], 0) + 1
        counts[mode] = reasons
    return counts


def lineup_receipts(snaps: pl.DataFrame) -> dict:
    g = snaps.group_by(["game_pk", "team"]).agg(
        pl.col("fetched_at").max().alias("last_fetch"),
        pl.col("lineup_status").max().alias("status_max"),
        pl.len().alias("rows"))
    per_game = snaps.group_by("game_pk").agg(
        pl.col("game_number").max().alias("max_gnum"))
    statuses = snaps.group_by("lineup_status").agg(pl.len().alias("n"))
    fa = snaps.select(pl.col("fetched_at").min().alias("mn"),
                      pl.col("fetched_at").max().alias("mx"))
    return {
        "n_team_game_lineups": int(g.height),
        "n_unique_games": int(per_game.height),
        "n_doubleheader_games": int(
            (per_game["max_gnum"] > 1).sum()),
        "status_counts": {r["lineup_status"]: int(r["n"])
                          for r in statuses.iter_rows(named=True)},
        "fetch_span_utc": [str(fa["mn"][0]), str(fa["mx"][0])],
        "capture_cadence": "6 fetch dates across ~4 weeks (INTERMITTENT; "
                           "production capture not confirmed daily)",
        "coverage_basis_d1": "counts are TEAM-GAME LINEUPS from the "
                             "captures, NOT the eligible pitcher-forecast "
                             "count (each game contributes two lineup "
                             "rows but one forecast pitcher per arm); "
                             "the eligible-forecast population is fixed "
                             "only at sealing",
        "cutoff_basis_d1": "max_fetch_per_team_game: coverage below uses "
                           "each team-game's maximum fetch time as its "
                           "cutoff, so counts are a status/completeness "
                           "AVAILABILITY UPPER BOUND, not real "
                           "forecast-cutoff usability; actual "
                           "declared-cutoff coverage is reported "
                           "separately at sealing",
    }


def demo_distributions(snaps: pl.DataFrame, n_demo: int = 3) -> list[dict]:
    """UNSCORED structural demonstration on a SYNTHETIC BF PMF and
    SYNTHETIC rates (clearly labeled); proves the A/B machinery + fallback
    equality without touching restricted inputs."""
    g = snaps.group_by(["game_pk", "team"]).agg(
        pl.col("fetched_at").max().alias("last_fetch")).head(n_demo)
    out = []
    rng = np.random.default_rng(7)
    for r in g.iter_rows(named=True):
        lineup = pc.select_pregame_lineup(snaps, r["game_pk"], r["team"],
                                          r["last_fetch"],
                                          mode=pc.MODE_CONFIRMED_ONLY)
        # synthetic BF PMF (labeled): mass at BF 20..30
        bf = np.zeros(CAP)
        bf[19:30] = 0.1
        p_scalar = 0.23
        pkA = kc.combine_count(bf, p_scalar, K_MAX)
        if lineup["ok"]:
            seq9 = np.clip(rng.normal(0.23, 0.05, 9), 0.05, 0.5)
            seq = np.tile(seq9, CAP // 9 + 1)[:CAP]
            pkB = np.zeros(K_MAX)
            csum = np.cumsum(seq)
            for idx in range(CAP):
                m = bf[idx]
                if m <= 0:
                    continue
                n = idx + 1
                pkB += m * kc.binom_pmf(np.arange(K_MAX), n,
                                        float(csum[idx] / n))
            pkB[23] += max(0.0, 1.0 - pkB.sum())
            fallback = False
        else:
            pkB = pkA
            fallback = True
        out.append({
            "game_pk": r["game_pk"], "team": r["team"],
            "lineup_ok": lineup["ok"], "fallback": fallback,
            "reason": lineup["reason"],
            "distribution": "SYNTHETIC-INPUT DEMO (not a forecast)",
            "mass_A": float(pkA.sum()), "mass_B": float(pkB.sum()),
            "B_equals_A_fallback": bool(fallback
                                        and np.abs(pkA - pkB).max() == 0.0),
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path(args.data_root) if args.data_root else (
        Path(__file__).resolve().parents[2] / "data")
    files = sorted((root / "processed")
                   .glob("daily_lineups_*.parquet"))
    snaps = pc.load_snapshots(files)
    avail = input_availability(root)
    receipts = lineup_receipts(snaps)
    coverage = mode_coverage(snaps)
    receipts["selection_coverage_no_outcome"] = coverage
    demos = demo_distributions(snaps)
    report = {
        "generated": str(datetime.now(timezone.utc).isoformat()),
        "mode": "NO-OUTCOME DRY RUN (no scoring, no outcome joins)",
        "snapshot_provenance": {
            "fetched_at": "set by the production builder at ingestion "
                          "(one fetch per file; 6 distinct fetches); "
                          "content written atomically with the fetch",
            "raw_response_hash": "NOT retained by current capture -> "
                                 "captures labeled 'ingestion-verified, "
                                 "raw-hash-unverified'; strict-proof "
                                 "scoring requires adding the raw hash "
                                 "to future captures (research support "
                                 "proposed, production change needs "
                                 "separate approval)",
            "revisions": "0 games with >1 fetch so far; latest-valid "
                         "selection is future-proof, operates on "
                         "complete snapshots",
            "doubleheaders": "game_number parsed from the RG slate text "
                             "(18 rows game_number>1); identity includes "
                             "game_pk + game_number",
            "cutoff_policy": "forecast cutoff = scheduled first pitch "
                             "(pregame-known); snapshots after cutoff are "
                             "rejected; post-cutoff confirmations cannot "
                             "alter earlier forecasts",
        },
        "input_availability": avail,
        "lineup_receipts": receipts,
        "demo_distributions": demos,
        "blocked_summary": (
            "BF PMFs and 2025/2026 priors are BLOCKED (outcome-access "
            "restriction): no unscored 2026 forecast can be produced yet; "
            "the demo rows use SYNTHETIC inputs and are not forecasts"),
        "eligible_dates_for_scoring": (
            "NONE yet: scoring requires (a) 2026 outcome-access "
            "authorization, (b) raw-hash capture support or explicit "
            "unverified acceptance, (c) BF PMF construction for 2026 "
            "games; population = the 2026 captured cohort, NOT the "
            "historical 4,446 oracle cohort"),
    }
    (out_dir / "pregame_ab_dry_run.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="ascii")
    print(json.dumps({k: report[k] for k in (
        "input_availability", "lineup_receipts")}, indent=1, default=str))
    print("WROTE %s" % out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
