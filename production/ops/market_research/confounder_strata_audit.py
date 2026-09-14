"""Confounder strata audit on the juiced replay taken set.

Same-subset rule (SOP 8): every headline claim is re-cut WITHIN strata.
An effect that dies inside strata was never real.

Tests (all $0, on disk, no live change):
  A. Edge-band ROI within book-group x snap (is edge really book softness / clock?).
  B. Side ROI within each line cell (is overs-bleed really the lines?).
  C. Book ROI within snap (is book edge really clock?).
  D. Matched pairs: same ticket, different book / different clock, paired pnl diff.
  E. Shuffle negative control: permute outcomes within (line, side) strata;
     if noise "wins" too, the measurement is rigged.

Reads: artifacts/odds_log/juiced_replay_candidates.parquet
Writes: artifacts/odds_log/confounder_strata_report.json (+ .md)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "Python"))

import polars as pl

from market import american_to_decimal

import importlib.util as _ilu

REPO = Path(__file__).resolve().parents[3]
_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_join_keys = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_join_keys)
load_event_date_map = _join_keys.load_event_date_map
sorted_key = _join_keys.sorted_key

CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT_JSON = REPO / "artifacts" / "odds_log" / "confounder_strata_report.json"
OUT_MD = REPO / "artifacts" / "odds_log" / "confounder_strata_report.md"

EDGE_BINS = [(0.08, 0.12), (0.12, 0.18), (0.18, 0.24), (0.24, 9.0)]
N_SHUFFLE = 2000


def book_group(book: str | None) -> str:
    b = (book or "").lower()
    if b in ("draftkings", "fanduel"):
        return "DK+FD"
    if b == "betrivers":
        return "BR"
    return "other"


def edge_bin(e: float) -> str:
    for lo, hi in EDGE_BINS:
        if lo <= e < hi:
            return f"{lo:.2f}-{hi:.2f}" if hi < 9 else f"{lo:.2f}+"
    return "out_of_range"


def roi(rows) -> dict:
    n = len(rows)
    stake = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pnl = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    wins = sum(1 for r in rows if r["won"])
    return {
        "n": n,
        "wr": (wins / n) if n else None,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / stake, 4) if stake else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-shuffle", type=int, default=N_SHUFFLE)
    args = ap.parse_args()

    df = pl.read_parquet(CAND)
    taken = (
        df.filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
        .with_columns(
            pl.col("book").map_elements(book_group, return_dtype=pl.String).alias("book_group"),
            pl.col("edge").map_elements(edge_bin, return_dtype=pl.String).alias("edge_band"),
        )
        .to_dicts()
    )
    report: dict = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "candidates_file": str(CAND),
        "taken_n": len(taken),
        "overall": roi(taken),
    }

    # A. Edge-band ROI within book_group x snap.
    test_a: dict = {}
    for band in sorted({r["edge_band"] for r in taken}):
        test_a[band] = {}
        for bg in ("DK+FD", "BR", "other"):
            test_a[band][bg] = {}
            for snap in ("open", "morning"):
                cell = [r for r in taken if r["edge_band"] == band and r["book_group"] == bg and r["snap"] == snap]
                if cell:
                    test_a[band][bg][snap] = roi(cell)
    report["A_edge_band_within_book_x_snap"] = test_a

    # B. Side ROI within each line cell.
    test_b: dict = {}
    for line in sorted({r["line"] for r in taken}):
        test_b[str(line)] = {}
        for side in ("over", "under"):
            cell = [r for r in taken if r["line"] == line and r["side"] == side]
            if len(cell) >= 10:
                test_b[str(line)][side] = roi(cell)
    report["B_side_within_line"] = test_b

    # C. Book ROI within snap.
    test_c: dict = {}
    for snap in ("open", "morning"):
        test_c[snap] = {}
        for bg in ("DK+FD", "BR", "other"):
            cell = [r for r in taken if r["snap"] == snap and r["book_group"] == bg]
            if cell:
                test_c[snap][bg] = roi(cell)
    report["C_book_within_snap"] = test_c

    # D. Matched pairs via the book_lines panel (not candidates: candidates
    # hold ONE row per ticket at the chosen book, so cross-book pairs cannot
    # exist there — first version of this test returned 0 pairs by design).
    # D1: same ticket+clock quoted at DK/FD and at BR (morning, K market):
    #     paired payout diff in decimal units (positive = DK+FD pays better).
    # D2: same ticket take-price vs close (paired CLV from candidates).
    book_lines = pl.read_parquet(
        REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet"
    )
    evdate = load_event_date_map()
    bl = (
        book_lines.filter(
            (pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "morning")
        )
        .with_columns(
            pl.col("event_id").map_elements(lambda e: evdate.get(str(e), ""), return_dtype=pl.String).alias("gd"),
            pl.col("player").map_elements(sorted_key, return_dtype=pl.String).alias("skey"),
        )
        .to_dicts()
    )
    bl_index: dict = {}
    for r in bl:
        bl_index.setdefault((r["gd"], r["skey"], float(r["line"]), r["side"]), {})[str(r["book"]).lower()] = float(r["price"])
    d1_diffs = []
    d1_n_taken_morning = 0
    for r in taken:
        if r["snap"] != "morning" or r["side"] not in ("over", "under"):
            continue
        d1_n_taken_morning += 1
        key = (str(r["gd"]), sorted_key(r["player_name"]), float(r["line"]), r["side"])
        quotes = bl_index.get(key, {})
        dkfd = [quotes[b] for b in ("draftkings", "fanduel") if b in quotes]
        if dkfd and "betrivers" in quotes:
            best_dkfd = max(dkfd)  # best payout on the taken side
            d_dkfd = american_to_decimal(best_dkfd) - 1.0
            d_br = american_to_decimal(quotes["betrivers"]) - 1.0
            d1_diffs.append(d_dkfd - d_br)
    d2_by_book: dict = {}
    for r in taken:
        if r["side"] not in ("over", "under") or r.get("close_invalid"):
            continue
        try:
            clv = float(r["clv_pp"])
        except (TypeError, ValueError):
            continue
        d2_by_book.setdefault(r["book_group"], []).append(clv)

    report["D1_matched_morning_DKFD_minus_BR_payout"] = {
        "n_taken_morning": d1_n_taken_morning,
        "n_pairs": len(d1_diffs),
        "mean_payout_diff_decimal": round(sum(d1_diffs) / len(d1_diffs), 4) if d1_diffs else None,
        "frac_DKFD_pays_better": round(sum(1 for d in d1_diffs if d > 0) / len(d1_diffs), 3) if d1_diffs else None,
        "note": "positive = same ticket pays better at DK/FD than BR (BR softer against us)",
    }
    report["D2_paired_CLV_take_vs_close_by_book"] = {
        bg: {
            "n": len(v),
            "mean_clv_pp": round(sum(v) / len(v), 4),
            "frac_positive": round(sum(1 for x in v if x > 0) / len(v), 3),
        }
        for bg, v in sorted(d2_by_book.items())
    }

    # E. Shuffle negative control within (line, side) strata.
    rng = random.Random(args.seed)
    strata: dict = {}
    for r in taken:
        strata.setdefault((r["line"], r["side"]), []).append(r)
    obs_pnl = sum(float(r["pnl_flat1u"] or 0.0) for r in taken)
    null_pnls = []
    for _ in range(args.n_shuffle):
        tot = 0.0
        for members in strata.values():
            outcomes = [bool(m["won"]) for m in members]
            rng.shuffle(outcomes)
            for m, w in zip(members, outcomes):
                s = float(m["stake_flat1u"] or 0.0)
                if w:
                    tot += s * (american_to_decimal(float(m["price"])) - 1.0)
                else:
                    tot -= s
        null_pnls.append(tot)
    null_pnls.sort()
    ge = sum(1 for v in null_pnls if v >= obs_pnl)
    # E. Shuffle negative control within (line, side) strata. Win COUNT per
    # stratum is preserved, so this does NOT test "is ROI real" — it tests
    # WHERE wins land: null >> observed means our wins land on the
    # worst-paying tickets within each cell (favorite concentration: small
    # wins, full-stake losses). Recompute is exact vs stored pnl (verified).
    report["E_shuffle_negative_control"] = {
        "n_shuffle": args.n_shuffle,
        "observed_pnl": round(obs_pnl, 2),
        "null_p50": round(null_pnls[len(null_pnls) // 2], 2),
        "null_p95": round(null_pnls[int(0.95 * len(null_pnls))], 2),
        "p_value": round(ge / args.n_shuffle, 4),
        "verdict": "PRICE-ADVERSE (wins land on low-payout tickets within cells)"
        if ge / args.n_shuffle > 0.95
        else ("PASS (no within-cell price adversity)" if ge / args.n_shuffle >= 0.05 else "BELOW-NULL (check recompute)"),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2))
    lines = [
        "# Confounder strata audit",
        "",
        f"taken n={report['taken_n']}, overall ROI={report['overall']['roi']} (WR {report['overall']['wr']})",
        "",
        "## A. Edge-band ROI within book x snap",
        "",
    ]
    for band, bgs in test_a.items():
        for bg, snaps in bgs.items():
            for snap, m in snaps.items():
                lines.append(f"- {band} / {bg} / {snap}: n={m['n']} ROI={m['roi']} WR={m['wr']}")
    lines += ["", "## B. Side within line (n>=10)", ""]
    for line, sides in test_b.items():
        for side, m in sides.items():
            lines.append(f"- line {line} {side}: n={m['n']} ROI={m['roi']} WR={m['wr']}")
    lines += ["", "## C. Book within snap", ""]
    for snap, bgs in test_c.items():
        for bg, m in bgs.items():
            lines.append(f"- {snap} / {bg}: n={m['n']} ROI={m['roi']} WR={m['wr']}")
    lines += [
        "",
        "## D. Matched pairs",
        f"- D1 morning DK+FD minus BR payout: {report['D1_matched_morning_DKFD_minus_BR_payout']}",
        f"- D2 paired CLV by book: {report['D2_paired_CLV_take_vs_close_by_book']}",
        "",
        "## E. Shuffle negative control (win count preserved per cell)",
        f"- observed {report['E_shuffle_negative_control']['observed_pnl']}, "
        f"null p50 {report['E_shuffle_negative_control']['null_p50']}, "
        f"null p95 {report['E_shuffle_negative_control']['null_p95']}, "
        f"p={report['E_shuffle_negative_control']['p_value']} — "
        f"{report['E_shuffle_negative_control']['verdict']}",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_JSON} + {OUT_MD}")


if __name__ == "__main__":
    main()
