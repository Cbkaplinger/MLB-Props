"""Juiced frozen-model replay: 2025-present open/morning, rejected candidates.

Measurement only. Frozen p_ours_cal. No live policy change.

Decision clock: friend OPEN pair if both sides exist, else paid MORNING pair.
Book pick (realistic): DraftKings else FanDuel else first remaining US book
with a two-way quote. Edge uses multiplicative de-vig (same as the live
board). PnL uses the juiced American on the taken side.

Live policy applied as a FILTER only (floors + 4.5-over veto + 2.5/3.5
probation bump). Four shadow sizing arms on accepted tickets; rejected
rows kept with a reason. 2026 numbers are confirmatory (prior harness
peek) -- do not retune floors from this run.

  python production/ops/market_research/juiced_replay_ledger.py
  python production/ops/market_research/juiced_replay_ledger.py --floor-uniform 0.08 --cap 0.20 --out-suffix __f008
  python production/ops/market_research/juiced_replay_ledger.py --under-lean --book-universe dkfd --out-suffix __dkfd_lean

Selection runs (any override flag) write sidecar outputs and must pass
--out-suffix. Bare run reproduces the canonical 2026-09-11 report.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.market import (  # noqa: E402
    DEFAULT_KELLY_FRACTION,
    bet_pnl,
    clv_pp,
    evaluate_side,
    size_in_units,
)
from Python.odds_ledger import atomic_write_parquet, atomic_write_text  # noqa: E402
from join_keys import (  # noqa: E402
    EVENT_DATE_MAP,
    HIST,
    ODDS_DIR,
    load_event_date_map,
    sorted_key,
)

FRIEND = (
    ROOT / "data" / "Odds-Open-Close-2025-2026"
    / "pitcher_strikeouts_early_open_2025_2026.csv"
)
FLOOR_PATH = Path(__file__).with_name("line_floor_policy.json")
PANEL = ODDS_DIR / "universe_panel_live.parquet"
OUT_PARQUET = ODDS_DIR / "juiced_replay_candidates.parquet"
OUT_REPORT = ODDS_DIR / "juiced_replay_report.json"
OUT_BASELINE = ODDS_DIR / "juiced_replay_baseline.parquet"
OUT_INTEGRITY = ODDS_DIR / "juiced_replay_quote_integrity.json"

# Declared decision clocks (see the snapshot reconstruction contract in
# production/ops/market_research): the
# morning decision is T-5h and the close benchmark is T-5min before
# commence. A vendor quote is decision-time available only if its
# AUTHORITATIVE timestamp is at or before the declared decision time
# (lag = commence - vendor >= decision lag). A T-1h quote is pregame
# but NOT available at the T-5h decision.
MORNING_DECISION_LAG_SEC = 5 * 3600
CLOSE_DECISION_LAG_SEC = 5 * 60

UNIT = 50.0
LIVE_BASE_FLOOR = 0.12
PROBATION_BUMP = 0.18
BOOK_PREF = {
    "draftkings": 0,
    "fanduel": 1,
    "betmgm": 2,
    "fanatics": 3,
    "bovada": 4,
    "betonlineag": 5,
    "betrivers": 6,
    "williamhill_us": 7,
    "mybookieag": 8,
}

# Pre-registered edge bands for the flat-unit arm (not a live rule).
BANDS = ((0.18, 2.0), (0.12, 1.5), (0.0, 1.0))

# Selection-engine (2025-lock prereg 2026-09-11): uniform floor candidates,
# edge-cap candidates, and the under-lean premium. Veto 4.5-over and the
# 2.5/3.5 probation bump are NOT searched (standing risk controls).
UNIFORM_FLOOR_CANDIDATES = (0.08, 0.10, 0.12)
CAP_CANDIDATES = (0.18, 0.20, 0.24)
UNDER_LEAN_PREMIUM = 0.04
SELECTION_LINES = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5)


def _floors() -> dict[float, float]:
    raw = json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
    return {float(k): float(v) for k, v in raw.get("line_edge_floors", {}).items()}


def _pref(book: str) -> int:
    return int(BOOK_PREF.get(str(book), 99))


def _event_frame(evdate: dict[str, str]) -> pl.DataFrame:
    return pl.DataFrame(
        {"event_id": list(evdate.keys()), "gd": list(evdate.values())}
    )


def _paid_scan(
    snapshot: str,
    ev: pl.DataFrame,
    allowed_books: set[str] | None = None,
    event_ids: set[str] | None = None,
    gd_window: tuple | None = None,
) -> pl.DataFrame:
    """Shared lazy scan + gd-attach for one paid snapshot (post-guards,
    pre-pairing). Used by pair construction AND identity screening so
    both see the same declared decode scope."""
    scan = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("snapshot") == snapshot)
        & pl.col("line").is_not_null()
        & pl.col("price").is_not_null()
    )
    if gd_window is not None:
        scan = scan.filter(
            (pl.col("game_date") >= gd_window[0])
            & (pl.col("game_date") <= gd_window[1]))
    if event_ids is not None:
        scan = scan.filter(pl.col("event_id").is_in(sorted(event_ids)))
    bk = scan.collect()
    return bk.join(ev, on="event_id", how="left").filter(
        pl.col("gd").is_not_null() & (pl.col("gd") != "")
    ).with_columns(
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key")
    )


def _ambiguous_from_bk(bk: pl.DataFrame) -> pl.DataFrame:
    """Reduced identities (gd, key, line) mapping to more than one
    event_id within an ALREADY-SCANNED frame (no second decode)."""
    return bk.group_by(["gd", "key", "line"]).agg(
        pl.col("event_id").n_unique().alias("n_ev"),
        pl.col("event_id").unique().sort().alias("event_ids"),
    ).filter(pl.col("n_ev") > 1).drop("n_ev")


def _ambiguous_reduced_keys(
    snapshot: str,
    ev: pl.DataFrame,
    allowed_books: set[str] | None = None,
    event_ids: set[str] | None = None,
    gd_window: tuple | None = None,
) -> pl.DataFrame:
    """Reduced identities (gd, key, line) that map to MORE THAN ONE
    event_id in the permitted inputs. Determined BEFORE book selection,
    outcome consumption or scoring. Never resolved -- only refused or
    excluded by declared policy."""
    return _ambiguous_from_bk(
        _paid_scan(snapshot, ev, allowed_books, event_ids, gd_window))


def _two_way_paid(
    snapshot: str,
    ev: pl.DataFrame,
    allowed_books: set[str] | None = None,
    event_ids: set[str] | None = None,
    gd_window: tuple | None = None,
    drop_keys: set | None = None,
    bk: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Two-sided juiced-pair construction for one snapshot. When
    ``event_ids`` is provided, the restriction is pushed INTO the lazy
    scan (pre-decode): row groups outside the declared event set are
    not decoded. This is the development boundary for year windows —
    2026 rows are never decoded into a frame under a 2025 window.
    ``gd_window`` additionally pushes the declared game_date bounds
    into the scan so row-group pruning is statistics-based and the
    decode scope is deterministic (rg11-rg17 for a 2025H1 window).
    ``drop_keys`` (opt-in exclusion policy) removes declared ambiguous
    reduced identities BEFORE pair construction; it is an EXCLUSION,
    never an identity resolution. ``bk`` supplies an ALREADY-SCANNED
    frame (single permitted input pass from main); when omitted the
    scan runs here. Quote multiplicity is classified with FULL
    identity retained (event_id on BOTH sides); findings refuse with
    the structured report; only the declared idempotent policy may
    collapse exact repeated observations."""
    if bk is None:
        bk = _paid_scan(snapshot, ev, allowed_books, event_ids,
                        gd_window)
    if drop_keys:
        # anti-join on the reduced key: excluded candidates never reach
        # pair construction, so no book selection can re-introduce them
        drop_frame = pl.DataFrame(
            [ {"gd": k[0], "key": k[1], "line": float(k[2])}
              for k in sorted(drop_keys) ],
            schema={"gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64})
        bk = bk.join(drop_frame, on=["gd", "key", "line"], how="anti")
    # --- identity guards (no silent ambiguity resolution). A reduced
    # (gd, key, line) that maps to more than one event_id would fan out
    # every downstream join; refuse instead of picking first().
    amb = _ambiguous_from_bk(bk)
    if amb.height:
        sample = amb.head(5).rows()
        raise SystemExit(
            f"ambiguous reduced-key join: {amb.height} (gd,key,line) "
            f"map to multiple event_id values, e.g. {sample}; refusing")
    # --- quote multiplicity: classified with FULL identity retained;
    # the caller may pre-classify (integrity pass); standalone calls
    # get the guard here. Default = refuse with the finding classes.
    findings = _classify_quote_multiplicity(bk)
    if findings:
        counts: dict = {}
        for f in findings:
            kk = f["class"]
            counts[kk] = counts.get(kk, 0) + 1
        raise SystemExit(
            f"quote multiplicity findings ({snapshot}): "
            f"{len(findings)} duplicated observation group(s) - "
            f"classes {counts}; refusing (run the integrity report "
            "for affected keys)")
    # event_id is retained on BOTH sides; pairs join on the full
    # supported contract key so a quote can never attach to another
    # event's counter-side
    over = bk.filter(pl.col("side") == "over").select(
        ["gd", "key", "line", "book", "event_id", "snapshot_ts", "price"]
    ).rename({"price": "over_amer"})
    under = bk.filter(pl.col("side") == "under").select(
        ["gd", "key", "line", "book", "event_id", "snapshot_ts", "price"]
    ).rename({"price": "under_amer"})
    # --- pairs: multi-book quotes for one (gd,key,line) are expected;
    # selection among books is the DECLARED registered rule (pref order
    # below), not silent ambiguity resolution
    pairs = over.join(under, on=["gd", "key", "line", "book", "event_id"])
    pairs = pairs.with_columns(
        pl.col("book").map_elements(_pref, return_dtype=pl.Int64).alias("pref")
    )
    # the .first() below implements the owner-declared book preference
    # (DK else FD else next US book, 2026-09-11) over a deterministic
    # (pref, book) sort -- not an ambiguity default
    return (
        pairs.sort(["gd", "key", "line", "pref", "book"])
        .group_by(["gd", "key", "line"], maintain_order=True)
        .first()
        .select(["gd", "key", "line", "book", "event_id", "over_amer", "under_amer"])
        .rename({
            "book": f"{snapshot}_book",
            "event_id": f"{snapshot}_event_id",
            "over_amer": f"{snapshot}_over",
            "under_amer": f"{snapshot}_under",
        })
    )


def _classify_quote_multiplicity(bk: pl.DataFrame) -> list[dict]:
    """Classify duplicated quote-side observations BEFORE any
    distinguishing field is discarded. One finding per observation
    group (gd, key, line, book, event_id, side) with more than one
    row. Classes:
    - identical_repeat: every field identical (price AND timestamp)
      -> idempotent-collapse candidate under the declared policy;
    - same_time_conflict: same observation identity AND same
      available timestamp, different price;
    - distinct_time: different snapshot_ts values (timestamp semantics
      are NOT inferred - a declared decision-time selector would be
      required and none exists);
    - insufficient_timestamp: null/missing timestamp information.
    """
    key = ["gd", "key", "line", "book", "event_id", "side", "snapshot"]
    g = bk.group_by(key).agg(
        n=pl.len(),
        n_prices=pl.col("price").n_unique(),
        n_ts=pl.col("snapshot_ts").n_unique(),
        n_ts_null=pl.col("snapshot_ts").null_count(),
        prices=pl.col("price").unique().sort(),
        timestamps=pl.col("snapshot_ts").unique(),
    )
    findings = []
    for r in g.filter(pl.col("n") > 1).iter_rows(named=True):
        if r["n_ts_null"] and r["n_ts_null"] == r["n"]:
            cls = "insufficient_timestamp"
        elif r["n_ts"] == 1 and r["n_prices"] == 1:
            cls = "identical_repeat"
        elif r["n_ts"] == 1:
            cls = "same_time_conflict"
        else:
            cls = "distinct_time"
        findings.append({
            "snapshot": r["snapshot"],
            "gd": r["gd"], "key": r["key"], "line": float(r["line"]),
            "book": r["book"], "event_id": r["event_id"],
            "side": r["side"], "n_observations": r["n"],
            "n_distinct_prices": r["n_prices"],
            "n_distinct_timestamps": r["n_ts"],
            "prices": [float(p) for p in r["prices"]],
            "timestamps": [str(t) for t in r["timestamps"]
                           if t is not None],
            "class": cls,
        })
    return findings


def _collapse_identical_copies(bk: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Narrowly specified idempotent normalization: collapse EXACT
    repeated observations (all retained fields identical, including
    snapshot_ts). Same-time conflicts, distinct-time rows and
    timestamp-unresolvable groups are NOT touched - they refuse
    upstream via the classifier."""
    key = ["gd", "key", "line", "book", "event_id", "side",
           "snapshot_ts", "price"]
    n0 = bk.height
    collapsed = bk.unique(subset=key)
    return collapsed, n0 - collapsed.height


def _integrity_report(findings_morning: list[dict],
                      findings_close: list[dict],
                      collapsed_counts: dict,
                      residual_morning: list[dict] | None = None,
                      residual_close: list[dict] | None = None) -> dict:
    """One structured integrity report covering BOTH snapshots,
    produced before outcomes/scoring: pre-normalization findings,
    the collapse counts, and any residual findings after the
    declared normalization policy."""
    def _pack(findings):
        classes: dict = {}
        for f in findings:
            classes[f["class"]] = classes.get(f["class"], 0) + 1
        return {"n_findings": len(findings), "classes": classes,
                "findings": findings[:50]}
    applied = (collapsed_counts.get("morning", 0)
               + collapsed_counts.get("close", 0)) > 0
    return {
        "report": "quote_multiplicity_integrity_v1",
        "stage": "pair_construction_pre_check",
        "morning": _pack(findings_morning),
        "close": _pack(findings_close),
        "normalization": {
            "applied": applied,
            "collapsed_identical_copies": collapsed_counts,
            "residual_findings": {
                "morning": _pack(residual_morning or []),
                "close": _pack(residual_close or [])},
        },
        "note": ("findings classify multiplicities on the full "
                 "observation identity (gd,key,line,book,event_id,"
                 "side,snapshot,snapshot_ts,price); timestamp semantics "
                 "are never inferred; no first()/best-price/latest "
                 "selection is made"),
    }


def _two_way_friend(allowed_books: set[str] | None = None,
                    gd_window: tuple | None = None) -> pl.DataFrame:
    if not FRIEND.exists():
        return pl.DataFrame(schema={
            "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
            "open_book": pl.Utf8, "open_over": pl.Int64, "open_under": pl.Int64,
        })
    fo = pl.read_csv(FRIEND).filter(
        pl.col("over_odds").is_not_null() & pl.col("under_odds").is_not_null()
        & pl.col("line").is_not_null()
    )
    if allowed_books is not None:
        fo = fo.filter(pl.col("bookmaker").is_in(sorted(allowed_books)))
    # declared boundary: the Friend CSV is small (26k rows) and carries
    # no event_id; the year restriction is applied to its game_date
    # column immediately after decode (the parquet scans above carry the
    # strict pre-decode pushdown)
    if gd_window is not None:
        fo = fo.filter(
            (pl.col("game_date").cast(pl.Utf8) >= gd_window[0])
            & (pl.col("game_date").cast(pl.Utf8) <= gd_window[1]))
    fo = fo.with_columns(
        pl.col("game_date").cast(pl.Utf8).alias("gd"),
        pl.col("player_name").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"),
        pl.col("bookmaker").map_elements(_pref, return_dtype=pl.Int64).alias("pref"),
    )
    if fo.height != fo.unique(
            subset=["gd", "key", "line", "bookmaker"]).height:
        raise SystemExit(
            "duplicate Friend quotes for the same "
            "(gd,key,line,bookmaker); refusing")
    return (
        fo.sort(["gd", "key", "line", "pref", "bookmaker"])
        .group_by(["gd", "key", "line"], maintain_order=True)
        .first()
        .select([
            "gd", "key", "line",
            pl.col("bookmaker").alias("open_book"),
            pl.col("over_odds").alias("open_over"),
            pl.col("under_odds").alias("open_under"),
        ])
    )


def live_floor(line: float, side: str, floors: dict[float, float]) -> float:
    fl = float(floors.get(round(float(line), 1), LIVE_BASE_FLOOR))
    if side == "over" and round(float(line), 1) in (2.5, 3.5):
        fl = max(fl, PROBATION_BUMP)
    return fl


def uniform_floors(value: float) -> dict[float, float]:
    """One floor for every selection line (probation bump still applies)."""
    return {line: float(value) for line in SELECTION_LINES}


def policy_reason(
    side: str,
    line: float,
    edge: float,
    floors: dict[float, float],
    *,
    cap: float | None = None,
    under_premium: float = 0.0,
) -> str:
    """Filter reason ("" = taken). Veto always on; cap/premium opt-in.

    Default (cap=None, premium=0) reproduces the canonical 2026-09-11 run.
    Selection runs pass --cap / --under-lean explicitly and write sidecar
    outputs, never the canonical paths.
    """
    if side == "over" and round(float(line), 1) == 4.5:
        return "veto_4_5_over"
    fl = live_floor(line, side, floors)
    if str(side) == "over" and float(under_premium) > 0:
        fl = fl + float(under_premium)
    if edge < fl:
        return "below_floor"
    if cap is not None and edge >= float(cap):
        return "edge_cap"
    return ""


def band_units(edge: float) -> float:
    for thresh, u in BANDS:
        if float(edge) >= thresh:
            return float(u)
    return 1.0


def size_arms(p_side: float, american: float, edge: float, floor: float) -> dict:
    flat = UNIT
    band = UNIT * band_units(edge)
    live = size_in_units(
        p_side, american, edge=edge, edge_floor=floor, unit_dollars=UNIT,
        kelly_frac=DEFAULT_KELLY_FRACTION,
    )
    # Robust: shrink p 50% toward a coin-flip, then half-size extreme edges.
    p_shrunk = 0.5 * float(p_side) + 0.5 * 0.5
    robust = size_in_units(
        p_shrunk, american, edge=edge, edge_floor=floor, unit_dollars=UNIT,
        kelly_frac=DEFAULT_KELLY_FRACTION,
    )
    r_stake = float(robust["stake"])
    if float(edge) >= 0.20:
        r_stake *= 0.5
    return {
        "stake_flat1u": flat,
        "stake_band": band,
        "stake_kelly": float(live["stake"]),
        "units_kelly": float(live["units"]),
        "stake_robust": r_stake,
    }


def _summarize(rows: list[dict], stake_key: str) -> dict:
    acc = [r for r in rows if r["accepted"] and r.get(stake_key)]
    if not acc:
        return {"n": 0}
    pnl_key = "pnl_" + stake_key.removeprefix("stake_")
    pnl = np.array([r[pnl_key] for r in acc], dtype=float)
    stake = np.array([r[stake_key] for r in acc], dtype=float)
    clv = np.array([r["clv_pp"] for r in acc if r.get("clv_pp") is not None], dtype=float)
    wr = float(np.mean([1.0 if r["won"] else 0.0 for r in acc]))
    out = {
        "n": len(acc),
        "n_reject": int(sum(1 for r in rows if not r["accepted"])),
        "stake_sum": round(float(stake.sum()), 2),
        "pnl": round(float(pnl.sum()), 2),
        "roi": float(pnl.sum() / stake.sum()) if float(stake.sum()) > 0 else None,
        "wr": wr,
        "over_share": float(np.mean([1.0 if r["side"] == "over" else 0.0 for r in acc])),
        "mean_edge": float(np.mean([r["edge"] for r in acc])),
        "n_clv": int(clv.size),
        "mean_clv_pp": float(np.mean(clv)) if clv.size else None,
        "open_share": float(np.mean([1.0 if r["snap"] == "open" else 0.0 for r in acc])),
    }
    return out


def _cell(rows: list[dict], line: float, side: str) -> dict:
    sub = [r for r in rows if r["accepted"] and r["side"] == side
           and round(float(r["line"]), 1) == line]
    skip = [r for r in rows if (not r["accepted"]) and r["side"] == side
            and round(float(r["line"]), 1) == line]
    if not sub:
        return {"n_taken": 0, "n_reject": len(skip)}
    pnl = sum(r["pnl_flat1u"] for r in sub)
    stake = sum(r["stake_flat1u"] for r in sub)
    wr = float(np.mean([1.0 if r["won"] else 0.0 for r in sub]))
    return {
        "n_taken": len(sub),
        "n_reject": len(skip),
        "roi_flat1u": float(pnl / stake) if stake else None,
        "wr": wr,
        "mean_edge": float(np.mean([r["edge"] for r in sub])),
        "pnl_flat1u": round(float(pnl), 2),
    }


def resolve_outputs(out_suffix: str, gd_restricted: bool,
                    paths: list[Path]) -> list[Path]:
    """Development-boundary guard. gd-restricted runs are
    development-only: they REQUIRE an explicit --out-suffix (the
    canonical report is never overwritten) and REFUSE existing
    destinations (write-once, every declared output). Canonical runs
    keep the historical bare-run behavior unchanged."""
    if gd_restricted and not out_suffix:
        raise SystemExit(
            "--gd-start/--gd-end require --out-suffix: development-"
            "only runs never overwrite the canonical report")
    existing = [str(p) for p in paths if p.exists()]
    if gd_restricted and existing:
        raise SystemExit(
            f"destination exists (write-once): {existing}")
    return paths


def _fail_date(flag: str, value: str) -> None:
    raise SystemExit(
        f"{flag} must be a valid YYYY-MM-DD date; got {value!r}; "
        "refusing before any input/output side effect")


def _check_exclusion_binding(excl: dict, path: str) -> None:
    """Bind the detected ambiguous reduced keys to a preserved receipt.
    A detected set different from the bound set REFUSES the run -- the
    exclusion list is never silently expanded."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {(str(e["gd"]), str(e["key"]), float(e["line"]))
                for e in spec["expected_excluded_keys"]}
    detected = set(excl)
    if expected != detected:
        missing = sorted(expected - detected)
        extra = sorted(detected - expected)
        raise SystemExit(
            "exclusion-set mismatch: the run is bound to a preserved "
            f"receipt ({path}); expected-only={missing} "
            f"detected-only={extra}; stopping (never silently expand "
            "exclusions)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--floor-uniform", type=float, default=None,
                    help="uniform floor for all lines (selection engine)")
    ap.add_argument("--cap", type=float, default=None,
                    help="edge cap HOLD (selection engine; live is 0.20)")
    ap.add_argument("--under-lean", action="store_true",
                    help="overs need floor+0.04 (selection engine)")
    ap.add_argument("--book-universe", choices=("next", "dkfd"), default="next",
                    help="next = DK else FD else next US book (canonical); "
                         "dkfd = DK else FD only")
    ap.add_argument("--entry-clock", choices=("registered", "morning_only"),
                    default="registered",
                    help="registered = Friend open else paid morning "
                         "(canonical decision clock); morning_only = "
                         "paid morning T-5h only (skips Friend CSV "
                         "read and Friend join entirely)")
    ap.add_argument("--identity-policy", choices=("refuse",
                                                  "exclude_ambiguous"),
                    default="refuse",
                    help="refuse = refuse the run when a reduced "
                         "(gd,key,line) identity maps to multiple "
                         "event_ids (default; exact-contract identity); "
                         "exclude_ambiguous = development-baseline "
                         "EXCLUSION policy: every affected candidate is "
                         "excluded with reason ambiguous_event_identity "
                         "and preserved in accounting with all "
                         "conflicting event_ids -- never resolved, "
                         "never first/cheapest/latest/most-favorable")
    ap.add_argument("--quote-policy", choices=("refuse",
                                               "normalize_idempotent"),
                    default="refuse",
                    help="quote multiplicity treatment: refuse = any "
                         "duplicated observation group refuses with the "
                         "structured integrity report (default); "
                         "normalize_idempotent = collapse ONLY exact "
                         "repeated observations (identical price AND "
                         "timestamp) -- same-time conflicts, distinct-"
                         "time rows and timestamp-unresolvable groups "
                         "STILL refuse (no first()/best-price/latest "
                         "selection; no timestamp semantics inferred)")
    ap.add_argument("--expected-excluded-keys", default=None,
                    help="JSON binding file listing the expected "
                         "excluded reduced keys (binds the run to a "
                         "preserved receipt); requires --identity-policy "
                         "exclude_ambiguous; a detected set different "
                         "from the bound set REFUSES the run")
    ap.add_argument("--out-suffix", default="",
                    help="sidecar suffix; empty reproduces canonical outputs")
    ap.add_argument("--gd-start", default=None,
                    help="DEVELOPMENT boundary: restrict event dates to "
                         "gd >= start (YYYY-MM-DD) via a pre-decode scan "
                         "filter; requires --out-suffix; confirm_2025H2 "
                         "(gd > 2025-06-30) is always excluded for a "
                         "2025-only window; 2026 stays closed unless "
                         "explicitly authorized")
    ap.add_argument("--gd-end", default=None,
                    help="DEVELOPMENT boundary: restrict event dates to "
                         "gd <= end (YYYY-MM-DD; a 2025-only packet uses "
                         "2025-06-30)")
    args = ap.parse_args(argv)
    gd_restricted = args.gd_start is not None or args.gd_end is not None
    if gd_restricted:
        # validate before any input/output side effect: shape AND a real
        # calendar date (2025-02-30 is correctly refused)
        for label, val in [("--gd-start", args.gd_start),
                           ("--gd-end", args.gd_end)]:
            if val is not None:
                parts = val.split("-")
                shape_ok = (len(parts) == 3 and len(parts[0]) == 4
                            and all(p.isdigit() for p in parts)
                            and all(len(p) == d for p, d
                                    in zip(parts, (4, 2, 2))))
                cal_ok = False
                if shape_ok:
                    try:
                        date.fromisoformat(val)
                        cal_ok = True
                    except ValueError:
                        cal_ok = False
                if not (shape_ok and cal_ok):
                    _fail_date(label, val)
        lo = args.gd_start or "0000-01-01"
        hi = args.gd_end or "9999-12-31"
        if lo > hi:
            _fail_date("--gd-start/--gd-end",
                       f"reversed window {lo}..{hi}")
    gd_window = None
    if gd_restricted:
        gd_window = (args.gd_start or "0000-01-01",
                     args.gd_end or "9999-12-31")
        if gd_window[1] >= "2026-01-01":
            raise SystemExit(
                "gd window extends into 2026: 2026 rows stay closed "
                "unless explicitly authorized (no authorization flag "
                "exists); refusing")
    market_only = args.entry_clock == "morning_only"
    floors = ({} if market_only else
              uniform_floors(args.floor_uniform)
              if args.floor_uniform is not None else _floors())
    cap = args.cap
    premium = UNDER_LEAN_PREMIUM if args.under_lean else 0.0
    allowed = {"draftkings", "fanduel"} if args.book_universe == "dkfd" else None
    out_parquet = OUT_PARQUET if not args.out_suffix else OUT_PARQUET.with_name(
        OUT_PARQUET.stem + args.out_suffix + OUT_PARQUET.suffix)
    out_report = OUT_REPORT if not args.out_suffix else OUT_REPORT.with_name(
        OUT_REPORT.stem + args.out_suffix + OUT_REPORT.suffix)
    out_base = OUT_BASELINE if not args.out_suffix else OUT_BASELINE.with_name(
        OUT_BASELINE.stem + args.out_suffix + OUT_BASELINE.suffix)
    out_integrity = OUT_INTEGRITY if not args.out_suffix else OUT_INTEGRITY.with_name(
        OUT_INTEGRITY.stem + args.out_suffix + OUT_INTEGRITY.suffix)
    # market-only mode writes only the baseline + report (no candidates
    # parquet), so only those destinations are declared
    declared = ([out_report, out_base] if market_only
                else [out_parquet, out_report, out_base])
    guarded = resolve_outputs(args.out_suffix, gd_restricted,
                              declared + [out_integrity])
    (out_integrity,) = guarded[-1:]
    if market_only:
        (out_report, out_base) = guarded[:-1]
    else:
        (out_parquet, out_report, out_base) = guarded[:-1]
    if market_only and not EVENT_DATE_MAP.exists():
        raise SystemExit(
            "cached event-date map missing; this order forbids a "
            "rebuild -- refusing (no network, no raw-index walk)")
    print(f"floors={'uniform %.2f' % args.floor_uniform if args.floor_uniform is not None else 'live-file'} "
          f"cap={cap} under_lean={args.under_lean} book={args.book_universe} out={args.out_suffix or 'canonical'}")
    if market_only and not EVENT_DATE_MAP.exists():
        raise SystemExit(
            "cached event-date map missing; rebuilding is not "
            "authorized for market-only runs -- refusing (no network, "
            "no raw-index walk)")
    evdate = load_event_date_map()
    ev = _event_frame(evdate)
    # ---- development boundary: pre-decode event restriction. The
    # allowed event set is computed from the CACHED date map (small
    # JSON) and pushed into the lazy book_lines scans; protected-year
    # row groups outside the window are not decoded. The event-date
    # cache may be (re)built locally from the raw event index when
    # missing (local file write; no network).
    allowed_event_ids = None
    if gd_restricted:
        allowed_event_ids = {
            eid for eid, gd in evdate.items()
            if gd_window[0] <= str(gd)[:10] <= gd_window[1]}
        if not allowed_event_ids:
            raise SystemExit(
                f"gd window {gd_window[0]}..{gd_window[1]} matches no "
                "cached event dates; refusing rather than decoding the "
                "full lake")
    print("attaching paid morning/close two-way pairs...")
    # ---- ONE permitted input pass: scan BOTH snapshots once, then run
    # identity screening and quote-multiplicity classification BEFORE
    # book selection, outcome consumption or scoring.
    bk_m = _paid_scan("morning", ev, allowed,
                      event_ids=allowed_event_ids, gd_window=gd_window)
    bk_c = _paid_scan("close", ev, allowed,
                      event_ids=allowed_event_ids, gd_window=gd_window)
    exclude_ambiguous = args.identity_policy == "exclude_ambiguous"
    if args.expected_excluded_keys and not exclude_ambiguous:
        raise SystemExit(
            "--expected-excluded-keys requires --identity-policy "
            "exclude_ambiguous")
    excl: dict[tuple, dict] = {}
    binding = None
    if exclude_ambiguous:
        excl = {}
        for snap, amb in (("morning", _ambiguous_from_bk(bk_m)),
                          ("close", _ambiguous_from_bk(bk_c))):
            for r in amb.iter_rows(named=True):
                kk = (r["gd"], r["key"], float(r["line"]))
                e = excl.setdefault(kk, {"event_ids": [], "snapshots": []})
                for eid in r["event_ids"]:
                    if eid not in e["event_ids"]:
                        e["event_ids"].append(eid)
                if snap not in e["snapshots"]:
                    e["snapshots"].append(snap)
        if args.expected_excluded_keys:
            _check_exclusion_binding(excl, args.expected_excluded_keys)
            binding = {"source_file": args.expected_excluded_keys,
                       "matched": True,
                       "lineage": "expected set bound to the preserved "
                                  "stopped-run receipts (PR #86 comment "
                                  "6816558623; PR #87 comment "
                                  "6829936974; both closed as "
                                  "executions of record)"}
        print(f"identity-policy exclude_ambiguous: "
              f"{len(excl)} excluded reduced keys")
    # ---- quote-multiplicity integrity pass (BOTH snapshots, structured)
    findings_m = _classify_quote_multiplicity(bk_m)
    findings_c = _classify_quote_multiplicity(bk_c)
    collapsed = {"morning": 0, "close": 0}
    if findings_m or findings_c:
        pre_m, pre_c = findings_m, findings_c
        non_idem = [f for f in (*findings_m, *findings_c)
                    if f["class"] != "identical_repeat"]
        residual_m, residual_c = findings_m, findings_c
        normalized = False
        if (args.quote_policy == "normalize_idempotent"
                and not non_idem):
            # ONLY exact repeated observations (identical price AND
            # timestamp) collapse; anything else refuses above
            bk_m, collapsed["morning"] = _collapse_identical_copies(bk_m)
            bk_c, collapsed["close"] = _collapse_identical_copies(bk_c)
            residual_m = _classify_quote_multiplicity(bk_m)
            residual_c = _classify_quote_multiplicity(bk_c)
            normalized = True
        if residual_m or residual_c or not normalized:
            report = _integrity_report(pre_m, pre_c, collapsed,
                                       residual_m, residual_c)
            atomic_write_text(out_integrity,
                              json.dumps(report, indent=1,
                                         sort_keys=True, default=str))
            classes: dict = {}
            for f in (*residual_m, *residual_c):
                classes[f["class"]] = classes.get(f["class"], 0) + 1
            raise SystemExit(
                f"quote integrity failure: {len(residual_m) + len(residual_c)} "
                f"unresolved duplicated observation group(s), classes "
                f"{classes}; structured report written: {out_integrity}; "
                "refusing (no first()/best-price/latest selection; "
                "unresolved cases remain unavailable)")
        report = _integrity_report(pre_m, pre_c, collapsed,
                                   residual_m, residual_c)
        atomic_write_text(out_integrity,
                          json.dumps(report, indent=1, sort_keys=True,
                                     default=str))
        print(f"quote integrity: collapsed {collapsed['morning']} morning "
              f"+ {collapsed['close']} close identical copies "
              f"(idempotent normalization); report: {out_integrity}")
    morning = _two_way_paid("morning", ev, allowed,
                            event_ids=allowed_event_ids,
                            gd_window=gd_window,
                            drop_keys=set(excl) if exclude_ambiguous else None,
                            bk=bk_m)
    close = _two_way_paid("close", ev, allowed,
                          event_ids=allowed_event_ids,
                          gd_window=gd_window,
                          drop_keys=set(excl) if exclude_ambiguous else None,
                          bk=bk_c)
    print(f"morning pairs {morning.height} close pairs {close.height}")
    if args.entry_clock == "registered":
        friend = _two_way_friend(
            allowed, gd_window=gd_window if gd_restricted else None)
        print(f"friend open pairs {friend.height}")
    else:
        # morning_only: Friend CSV is NEVER read; use an empty frame
        # with the correct schema so the left join produces null
        friend = pl.DataFrame(schema={
            "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
            "open_book": pl.Utf8, "open_over": pl.Int64,
            "open_under": pl.Int64,
        })
        print("entry_clock=morning_only: Friend CSV skipped")

    env_path = HIST / "snapshot_envelope.parquet"
    invalid: set[str] = set()
    env = None
    env_present = env_path.exists()
    if market_only and not env_present:
        # fail closed: without the envelope there is no authoritative
        # vendor timing, so decision-time availability cannot be
        # verified. Disclosure of disabled enforcement is insufficient.
        raise SystemExit(
            "market-only replay requires snapshot_envelope.parquet "
            "(fail closed: no envelope -> no verifiable decision-time "
            "vendor timing)")
    if env_present:
        env_scan = pl.scan_parquet(env_path).filter(
            pl.col("snapshot").is_in(("morning", "close"))
        )
        if allowed_event_ids is not None:
            env_scan = env_scan.filter(
                pl.col("event_id").is_in(sorted(allowed_event_ids)))
        env = env_scan.collect()
        # ambiguous envelope rows would fan out the timing join
        for s in ("morning", "close"):
            sub = env.filter(pl.col("snapshot") == s)
            if sub.height and sub["event_id"].n_unique() != sub.height:
                raise SystemExit(
                    f"ambiguous snapshot_envelope rows: duplicate "
                    f"event_id for snapshot={s}; refusing")
        # legacy close-invalid preflight: lag < 0 means the vendor
        # responded AFTER commence (lag = commence - vendor), so the
        # close snapshot is post-game, not a decision-time price
        invalid = set(env.filter(
            (pl.col("snapshot") == "close")
            & (pl.col("lag_vendor_vs_commence_sec") < 0)
        )["event_id"].to_list())
        print(f"close_invalid events {len(invalid)}")
    else:
        print("snapshot_envelope.parquet absent: vendor-timing "
              "enforcement disabled (legacy behavior)")
    if env_present:
        env_m = env.filter(pl.col("snapshot") == "morning").select(
            ["event_id",
             pl.col("vendor_timestamp").alias("morning_vendor_ts"),
             pl.col("lag_vendor_vs_commence_sec").alias("morning_lag_sec")])
        env_c = env.filter(pl.col("snapshot") == "close").select(
            ["event_id",
             pl.col("vendor_timestamp").alias("close_vendor_ts"),
             pl.col("lag_vendor_vs_commence_sec").alias("close_lag_sec")])
        morning = morning.join(env_m, left_on="morning_event_id",
                               right_on="event_id", how="left")
        close = close.join(env_c, left_on="close_event_id",
                           right_on="event_id", how="left")

    panel_scan = pl.scan_parquet(PANEL)
    if gd_restricted:
        panel_scan = panel_scan.filter(
            (pl.col("gd") >= gd_window[0])
            & (pl.col("gd") <= gd_window[1]))
    if market_only:
        # access boundary: market-only projects the panel's minimum
        # identity/date/line/settlement fields only; model probability
        # columns are never decoded in this mode
        panel_scan = panel_scan.select(
            ["gd", "key", "line", "y", "player_name"])
    uni_settled = panel_scan.filter(
        pl.col("y").is_not_null()
    ).collect()
    if args.entry_clock == "registered":
        uni = uni_settled.filter(
            pl.col("p_ours_cal").is_not_null()
            & pl.col("p_book_close").is_not_null()
        )
        print(f"universe close-matched {uni.height} "
              f"(baseline-settled {uni_settled.height})")
        j = (
            uni.join(morning, on=["gd", "key", "line"], how="left")
            .join(close, on=["gd", "key", "line"], how="left")
            .join(friend, on=["gd", "key", "line"], how="left")
        )
    else:
        # market-only path: the legacy model-selected pipeline (p_ours_cal
        # requirement, policy filter, sizing arms) is NOT executed at all
        print(f"market-only baseline-settled {uni_settled.height} "
              "(model probability not required)")

    rows: list[dict] = []
    if args.entry_clock == "registered":
        for rec in j.iter_rows(named=True):
            pm = float(rec["p_ours_cal"])
            line = float(rec["line"])
            y = float(rec["y"])
            use_open = rec.get("open_over") is not None and rec.get("open_under") is not None
            if use_open:
                snap, book = "open", rec.get("open_book")
                oa, ua = float(rec["open_over"]), float(rec["open_under"])
            elif rec.get("morning_over") is not None and rec.get("morning_under") is not None:
                snap, book = "morning", rec.get("morning_book")
                oa, ua = float(rec["morning_over"]), float(rec["morning_under"])
            else:
                rows.append({
                    "gd": rec["gd"], "key": rec["key"], "line": line,
                    "accepted": False, "reason": "no_two_way_price",
                    "side": "", "edge": None, "snap": None,
                })
                continue
            try:
                over_ev = evaluate_side(pm, oa, ua, "over")
                under_ev = evaluate_side(1.0 - pm, oa, ua, "under")
            except (ValueError, ZeroDivisionError):
                rows.append({
                    "gd": rec["gd"], "key": rec["key"], "line": line,
                    "accepted": False, "reason": "bad_price",
                    "side": "", "edge": None, "snap": snap,
                })
                continue
            best = over_ev if float(over_ev["edge"]) >= float(under_ev["edge"]) else under_ev
            side = str(best["side"])
            edge = float(best["edge"])
            p_side = float(best["p_model"])
            amer = float(best["price_american"])
            reason = policy_reason(side, line, edge, floors, cap=cap, under_premium=premium)
            accepted = reason == ""
            won = (y == 1.0) if side == "over" else (y == 0.0)
            fl = live_floor(line, side, floors)
            arms = size_arms(p_side, amer, edge, fl) if accepted else {
                "stake_flat1u": 0.0, "stake_band": 0.0,
                "stake_kelly": 0.0, "units_kelly": 0.0, "stake_robust": 0.0,
            }
            # Half-size counterfactual for 2.5/3.5 overs that would have been taken.
            half_ok = (side == "over" and round(line, 1) in (2.5, 3.5) and accepted)
            clv_val = None
            close_invalid = False
            ceid = rec.get("close_event_id")
            if ceid and ceid in invalid:
                close_invalid = True
            if rec.get("close_over") is not None and rec.get("close_under") is not None and not close_invalid:
                try:
                    c_over = evaluate_side(pm, float(rec["close_over"]), float(rec["close_under"]), "over")
                    p_close = float(c_over["p_market"]) if side == "over" else 1.0 - float(c_over["p_market"])
                    p_bet = float(best["p_market"])
                    clv_val = clv_pp(p_close, p_bet) * 100.0
                except (ValueError, ZeroDivisionError, TypeError):
                    clv_val = None
            row = {
                "gd": rec["gd"], "key": rec["key"], "player_name": rec.get("player_name"),
                "line": line, "side": side, "snap": snap, "book": book,
                "entry_clock": args.entry_clock,
                "yr": str(rec["gd"])[:4],
                "p_ours_cal": pm, "y": y, "won": bool(won),
                "edge": edge, "price": amer, "p_mkt": float(best["p_market"]),
                "accepted": accepted, "reason": reason or "taken",
                "floor": fl, "close_invalid": close_invalid, "clv_pp": clv_val,
                # raw two-way prices per snapshot: the market-only
                # movement baseline derives from these WITHOUT the model
                "open_over": rec.get("open_over"),
                "open_under": rec.get("open_under"),
                "morning_over": rec.get("morning_over"),
                "morning_under": rec.get("morning_under"),
                "close_over": rec.get("close_over"),
                "close_under": rec.get("close_under"),
                **arms,
                "pnl_flat1u": bet_pnl(arms["stake_flat1u"], amer, won=won) if accepted else 0.0,
                "pnl_band": bet_pnl(arms["stake_band"], amer, won=won) if accepted else 0.0,
                "pnl_kelly": bet_pnl(arms["stake_kelly"], amer, won=won) if accepted else 0.0,
                "pnl_robust": bet_pnl(arms["stake_robust"], amer, won=won) if accepted else 0.0,
                "half_size_2_5_3_5": half_ok,
            }
            rows.append(row)

    if args.entry_clock == "registered":
        taken = [r for r in rows if r.get("accepted")]
        frame = pl.DataFrame(rows)
        atomic_write_parquet(frame, out_parquet)

    # ---- baseline population: INDEPENDENT of the legacy p_ours_cal
    # accept/reject flag. One row per (start, line) in the window with
    # a settled outcome; per-row eligibility/exclusion reason; the
    # legacy model flag is preserved as a column, never a filter.
    j_base = (
        uni_settled.join(morning, on=["gd", "key", "line"], how="left")
        .join(close, on=["gd", "key", "line"], how="left")
        .join(friend, on=["gd", "key", "line"], how="left")
    )
    base_rows = []
    for rec in j_base.iter_rows(named=True):
        # ---- declared identity exclusion (BEFORE any outcome or
        # scoring consumption). Excluded candidates stay in coverage
        # accounting with their full reduced key, ALL conflicting
        # event_ids and affected snapshots; quote values are not
        # persisted; this is an EXCLUSION, not an identity resolution.
        xkey = (rec["gd"], rec["key"], float(rec["line"]))
        if xkey in excl:
            e = excl[xkey]
            base_rows.append({
                "gd": rec["gd"], "key": rec["key"],
                "player_name": rec.get("player_name"),
                "line": float(rec["line"]), "snap": None, "book": None,
                "entry_clock": args.entry_clock,
                "yr": str(rec["gd"])[:4],
                "entry_over": None, "entry_under": None,
                "fair_over_entry": None,
                "close_over": None, "close_under": None,
                "fair_over_close": None, "movement_pp": None,
                "clv_pp_over": None, "clv_pp_under": None,
                "over_hit": None, "won_over": None,
                "pnl_flat1u_over": None, "pnl_flat1u_under": None,
                "has_model_probability": None,
                "entry_eligible": False,
                "entry_reason": "ambiguous_event_identity",
                "settlement_available": None,
                "close_benchmark_available": False,
                "close_reason": "not_assessed_excluded",
                "baseline_reason": "ambiguous_event_identity",
                "conflicting_event_ids": ",".join(e["event_ids"]),
                "affected_snapshots": ",".join(e["snapshots"]),
            })
            continue
        line = float(rec["line"])
        y = float(rec["y"])
        won_over = (y == 1.0)
        snap = book = None
        oa = ua = None
        entry_reason = ""
        close_reason = ""
        # ---- entry side: price availability, price validity, and (for
        # paid-morning entries, when the envelope exists) decision-time
        # vendor-timestamp availability
        if (rec.get("open_over") is not None
                and rec.get("open_under") is not None):
            snap = "open"
            book = rec.get("open_book")
            oa = float(rec["open_over"])
            ua = float(rec["open_under"])
        elif (rec.get("morning_over") is not None
              and rec.get("morning_under") is not None):
            snap = "morning"
            book = rec.get("morning_book")
            oa = float(rec["morning_over"])
            ua = float(rec["morning_under"])
            if env_present:
                m_ts = rec.get("morning_vendor_ts")
                m_lag = rec.get("morning_lag_sec")
                if m_ts is None or m_lag is None:
                    entry_reason = "entry_timing_unavailable"
                elif float(m_lag) < 0:
                    # lag = commence - vendor: negative means the vendor
                    # quote is post-commence, not a decision-time price
                    entry_reason = "entry_timing_post_commence"
                elif float(m_lag) < MORNING_DECISION_LAG_SEC:
                    # quote exists but arrived AFTER the declared T-5h
                    # decision: unavailable at decision time even though
                    # it is pregame (a T-1h quote is not a T-5h input)
                    entry_reason = "entry_timing_after_decision"
        else:
            entry_reason = "no_two_way_entry_price"
        entry_eligible = entry_reason == ""
        fair_entry = None
        if entry_eligible:
            try:
                # the de-vigged market probability is model-independent;
                # evaluate_side is the registered construction
                fair_entry = float(evaluate_side(
                    0.0, oa, ua, "over")["p_market"])
            except (ValueError, ZeroDivisionError, TypeError):
                entry_reason = "bad_entry_price"
                entry_eligible = False
        # ---- settlement: independent of entry/close availability
        settlement_available = y is not None
        # ---- close benchmark: assessed independently of entry
        close_pair = (rec.get("close_over") is not None
                      and rec.get("close_under") is not None)
        if not close_pair:
            close_reason = "no_two_way_close"
        elif env_present:
            c_ts = rec.get("close_vendor_ts")
            c_lag = rec.get("close_lag_sec")
            if c_ts is None or c_lag is None:
                close_reason = "close_timing_unavailable"
            elif float(c_lag) < 0:
                close_reason = "close_invalid_vendor"
            elif float(c_lag) < CLOSE_DECISION_LAG_SEC:
                # vendor quote arrived after the declared T-5min close
                # benchmark time: not a close-decision-time price
                close_reason = "close_timing_after_decision"
        fair_close = None
        close_benchmark_available = False
        if close_reason == "":
            try:
                fair_close = float(evaluate_side(
                    0.0, float(rec["close_over"]),
                    float(rec["close_under"]), "over")["p_market"])
                close_benchmark_available = True
            except (ValueError, ZeroDivisionError, TypeError):
                close_reason = "bad_close_price"
        movement_pp = ((fair_close - fair_entry) * 100.0
                       if (fair_entry is not None
                           and close_benchmark_available) else None)
        base_rows.append({
            "gd": rec["gd"], "key": rec["key"],
            "player_name": rec.get("player_name"),
            "line": line, "snap": snap, "book": book,
            "entry_clock": args.entry_clock,
            "yr": str(rec["gd"])[:4],
            "entry_over": oa, "entry_under": ua,
            "fair_over_entry": fair_entry,
            "close_over": rec.get("close_over"),
            "close_under": rec.get("close_under"),
            "fair_over_close": fair_close,
            "movement_pp": movement_pp,
            "clv_pp_over": movement_pp,
            "clv_pp_under": (-movement_pp if movement_pp is not None
                             else None),
            # over_hit: BINARY over outcome at the line (panel `y`).
            # Full-start realized K is NOT carried by this panel; it is
            # only genuinely sourced in the assessment-derived paths
            # (market_benchmark_seam / count_pmf_diagnostic).
            "over_hit": int(y), "won_over": bool(won_over),
            "pnl_flat1u_over": (bet_pnl(1.0, oa, won=won_over)
                                if oa is not None else None),
            "pnl_flat1u_under": (bet_pnl(1.0, ua, won=(not won_over))
                                 if ua is not None else None),
            "has_model_probability": (
                rec["p_ours_cal"] is not None
                if "p_ours_cal" in rec else None),
            # ---- separated states with independent denominators
            "entry_eligible": entry_eligible,
            "entry_reason": entry_reason or "eligible",
            "settlement_available": settlement_available,
            "close_benchmark_available": close_benchmark_available,
            "close_reason": close_reason or "available",
            # combined gate kept for compatibility (entry side wins ties)
            "baseline_reason": (entry_reason or close_reason
                                or "eligible"),
        })
    base_frame = pl.DataFrame(base_rows)
    atomic_write_parquet(base_frame, out_base)
    n_candidates = len(base_rows)
    n_excluded_rows = sum(
        1 for r in base_rows
        if r["entry_reason"] == "ambiguous_event_identity")
    # post-screening population: excluded candidates remain in coverage
    # accounting but never re-enter entry/settlement/close denominators
    n_screened = n_candidates - n_excluded_rows
    entry_ok = [r for r in base_rows if r["entry_eligible"]]
    settled_ok = [r for r in base_rows if r["settlement_available"]]
    close_ok = [r for r in base_rows
                if r["entry_eligible"] and r["close_benchmark_available"]]
    entry_reason_counts: dict = {}
    for r in base_rows:
        k = r["entry_reason"]
        entry_reason_counts[k] = entry_reason_counts.get(k, 0) + 1
    close_reason_counts = {}
    for r in base_rows:
        k = r["close_reason"]
        close_reason_counts[k] = close_reason_counts.get(k, 0) + 1

    def _mean(vals: list) -> float | None:
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else None

    def _market_movement_stats() -> dict:
        mv = [float(r["movement_pp"]) for r in close_ok
              if r.get("movement_pp") is not None]
        n = len(mv)
        if not n:
            return {"n": 0}
        pnl_o = sum(r["pnl_flat1u_over"] for r in close_ok
                    if r["pnl_flat1u_over"] is not None)
        pnl_u = sum(r["pnl_flat1u_under"] for r in close_ok
                    if r["pnl_flat1u_under"] is not None)
        return {
            "n": n,
            "denominator": len(entry_ok),
            "mean_movement_pp": float(np.mean(mv)),
            "median_movement_pp": float(np.median(mv)),
            "positive_clv_share_over": float(
                np.mean([1.0 if v > 0 else 0.0 for v in mv])),
            "positive_clv_share_under": float(
                np.mean([1.0 if v < 0 else 0.0 for v in mv])),
            "mean_fair_over_entry": _mean([r["fair_over_entry"]
                                           for r in close_ok]),
            "mean_fair_over_close": _mean([r["fair_over_close"]
                                           for r in close_ok]),
            "entry_roi_flat1u_over": (
                float(pnl_o / n) if n else None),
            "entry_roi_flat1u_under": (
                float(pnl_u / n) if n else None),
            "over_hit_share": float(np.mean(
                [1.0 if r["over_hit"] == 1 else 0.0 for r in close_ok])),
        }

    base_summary = {
        "n_baseline_rows": n_candidates,
        "n_eligible": len([r for r in base_rows
                           if r["baseline_reason"] == "eligible"]),
        "reason_counts": {
            k: v for k, v in
            ((k, sum(1 for r in base_rows
                     if r["baseline_reason"] == k))
             for k in {r["baseline_reason"] for r in base_rows})},
        # ---- independent denominators (Req: separated states).
        # Post-screening population: excluded candidates (if any) stay
        # in coverage accounting but never re-enter these denominators.
        "entry": {
            "n_eligible": len(entry_ok),
            "denominator": n_screened,
            "reason_counts": entry_reason_counts,
        },
        "settlement": {
            "n_available": len(settled_ok),
            "denominator": n_screened,
        },
        "close_benchmark": {
            "n_available": len(close_ok),
            "denominator": len(entry_ok),
            "reason_counts": close_reason_counts,
        },
        "identity_screening": {
            "policy": args.identity_policy,
            "scope": ("per reduced (gd,key,line) start/line identity; "
                      "the minimum scope that makes the downstream "
                      "panel join unambiguous; an ambiguity at either "
                      "snapshot excludes the candidate from BOTH "
                      "(union across morning and close, no re-entry)"),
            "population_before_screening": n_candidates,
            "n_excluded_keys": len(excl),
            "n_excluded_rows": n_excluded_rows,
            "population_after_screening": n_screened,
            "excluded_keys": [
                {"gd": k[0], "key": k[1], "line": k[2],
                 "event_ids": v["event_ids"],
                 "snapshots": v["snapshots"]}
                for k, v in sorted(excl.items())],
            "binding": binding,
            "note": ("exclusion is a DECLARED DEVELOPMENT-BASELINE "
                     "EXCLUSION, not an identity resolution; no "
                     "first/cheapest/latest/most-favorable selection "
                     "is made and no excluded quote values persist"),
        },
        # model probability is not accessed in market-only mode
        "has_model_probability_share": (
            None if market_only else
            (float(np.mean([1.0 if r["has_model_probability"] else 0.0
                            for r in base_rows])) if base_rows else None)),
        "note": ("market-only movement baseline over ALL baseline-"
                 "eligible contracts; model-selected performance is "
                 "reported separately in the taken/selection sections"
                 if not market_only else
                 "market-only movement baseline over ALL candidates; "
                 "model probability, policy and sizing not accessed"),
    }

    # ---- market-only execution path: legacy model probability
    # requirements, policy filters and sizing execution are bypassed;
    # only the baseline construction and canonical de-vig math run.
    if args.entry_clock == "morning_only":
        rep = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "contract": {
                "mode": "market_only",
                "entry_clock": args.entry_clock,
                "decision": "paid morning T-5h only (Friend skipped)",
                "model": "bypassed (p_ours_cal not required)",
                "policy": "bypassed (no floors/veto/probation filter)",
                "sizing": "bypassed (no Kelly/edge-band execution)",
                "edge": "two-way multiplicative de-vig (registered)",
                "settlement": "panel y (binary over-hit at the line)",
                "book": "DK else FD else next US book with two-way quote",
                "vendor_timing_enforced": bool(env_present),
                "timing_note": (
                    "envelope present and required: morning/close "
                    "vendor timestamps must exist and be at or before "
                    "the declared decision times (morning T-5h, close "
                    "T-5min before commence); missing, post-commence "
                    "or post-decision timing is an explicit "
                    "unavailable/refusal state"
                    if env_present else
                    "envelope absent: timing enforcement disabled "
                    "(legacy behavior)"),
                "timing_reference": (
                    "commence_time (vendor convention); actual "
                    "first-pitch time is NOT supplied and is NOT "
                    "equated to commence"),
                "units": {
                    "fair_over_entry": "probability [0,1] (over-side "
                                       "multiplicative de-vig)",
                    "movement_pp": "percentage points of fair-over "
                                   "probability (close minus entry; "
                                   "positive = over side shortened)",
                    "clv_pp_over/under": "percentage points vs entry "
                                         "fair (over/under perspective)",
                    "entry_roi_flat1u_over/under": "units won or lost "
                                                   "per 1.0 unit flat "
                                                   "stake at entry price",
                    "over_hit_share": "fraction of contracts where the "
                                      "over won (panel y = 1)",
                },
                "gd_window": (f"{gd_window[0]}..{gd_window[1]} "
                              "(confirm_2025H2 excluded pre-decode)"
                              if gd_restricted else "full (canonical)"),
                "boundary": ("development market-only replay; "
                             "write-once sidecar destination; "
                             "baseline outputs only (no candidates "
                             "parquet)"),
            },
            "n_candidates": n_candidates,
            "baseline_market_only": base_summary,
            "market_movement": _market_movement_stats(),
        }
        atomic_write_text(out_report, json.dumps(rep, indent=2,
                                                 default=str))
        print(json.dumps({
            "mode": "market_only",
            "n_candidates": n_candidates,
            "entry_eligible": len(entry_ok),
            "settlement_available": len(settled_ok),
            "close_benchmark_available": len(close_ok),
            "market_movement": rep["market_movement"],
        }, indent=2, default=str))
        print(f"wrote {out_base}")
        print(f"wrote {out_report}")
        return 0

    def year_slice(yr: str | None) -> list[dict]:
        if yr is None:
            return rows
        return [r for r in rows if r.get("yr") == yr]

    # Probation counterfactuals on the SAME accepted-over-else universe:
    # A = live (2.5/3.5 overs taken if they clear floor)
    # B = skip all 2.5/3.5 overs
    # C = take them at 0.5u
    def probation_pack(src: list[dict]) -> dict:
        a = [r for r in src if r.get("accepted")]
        b = [r for r in a if not (
            r["side"] == "over" and round(float(r["line"]), 1) in (2.5, 3.5))]
        def roi(lst: list[dict], stake_mult: dict[str, float] | None = None) -> dict:
            if not lst:
                return {"n": 0}
            pnl = 0.0
            stake = 0.0
            wins = 0
            for r in lst:
                sm = 1.0
                if stake_mult and r["side"] == "over" and round(float(r["line"]), 1) in (2.5, 3.5):
                    sm = stake_mult.get("o2535", 1.0)
                pnl += float(r["pnl_flat1u"]) * sm
                stake += float(r["stake_flat1u"]) * sm
                wins += 1 if r["won"] else 0
            return {
                "n": len(lst),
                "roi": float(pnl / stake) if stake else None,
                "wr": wins / len(lst),
                "pnl": round(pnl, 2),
            }
        return {
            "A_live_take": roi(a),
            "B_skip_2_5_3_5_over": roi(b),
            "C_half_size_2_5_3_5_over": roi(a, {"o2535": 0.5}),
            "cell_2_5_over": _cell(src, 2.5, "over"),
            "cell_3_5_over": _cell(src, 3.5, "over"),
            "cell_2_5_under": _cell(src, 2.5, "under"),
            "cell_3_5_under": _cell(src, 3.5, "under"),
        }

    reasons = {}
    for r in rows:
        k = str(r.get("reason") or "")
        reasons[k] = reasons.get(k, 0) + 1

    n_open = sum(1 for r in taken if r.get("snap") == "open")
    n_morn = sum(1 for r in taken if r.get("snap") == "morning")
    books = {}
    for r in taken:
        b = str(r.get("book") or "")
        books[b] = books.get(b, 0) + 1

    fill_dkfd = []
    for r in rows:
        if r.get("accepted") and r.get("book") not in ("draftkings", "fanduel"):
            rr = dict(r)
            rr["accepted"] = False
            rr["reason"] = "book_not_dk_fd"
            fill_dkfd.append(rr)
        else:
            fill_dkfd.append(r)

    by_book = {}
    for b, _n in sorted(books.items(), key=lambda kv: -kv[1]):
        sub = [r for r in taken if r.get("book") == b]
        pnl = sum(float(r["pnl_flat1u"]) for r in sub)
        stake = sum(float(r["stake_flat1u"]) for r in sub)
        clvs = [r["clv_pp"] for r in sub if r.get("clv_pp") is not None]
        by_book[b] = {
            "n": len(sub),
            "roi": float(pnl / stake) if stake else None,
            "wr": float(np.mean([1.0 if r["won"] else 0.0 for r in sub])),
            "mean_clv_pp": float(np.mean(clvs)) if clvs else None,
            "open_share": float(np.mean([1.0 if r["snap"] == "open" else 0.0 for r in sub])),
        }

    rep = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "model": "frozen p_ours_cal universe_panel_live",
            "edge": "two-way multiplicative de-vig at juiced book pair",
            "decision": ("friend open else paid morning"
                         if args.entry_clock == "registered"
                         else "paid morning T-5h only (Friend skipped)"),
            "entry_clock": args.entry_clock,
            "book": "DK else FD else next US book with two-way quote (canonical per owner 2026-09-11)",
            "dk_fd_only": "sensitivity, not the headline",
            "policy": (
                "live floors + 4.5-over veto + 2.5/3.5 probation bump"
                if args.floor_uniform is None and cap is None and premium == 0.0
                and args.book_universe == "next"
                else f"SELECTION floors={args.floor_uniform} cap={cap} "
                     f"under_lean={args.under_lean} book={args.book_universe} "
                     f"(veto+probation on; prereg 2026-09-11)"
            ),
            "sizing_arms": ["flat1u", "edge_band", "kelly_1_16", "robust_kelly"],
            "label_2026": "confirmatory -- do not retune live policy",
            "fills": "unmodeled; paper juiced prices",
            "gd_window": (f"{gd_window[0]}..{gd_window[1]} "
                          "(confirm_2025H2 excluded pre-decode)"
                          if gd_restricted else "full (canonical)"),
            "boundary": ("development year-restricted runs push the "
                         "event/gd restriction into the lazy scans "
                         "pre-decode; network-free; write-once "
                         "sidecar destination; rejected contracts "
                         "preserved with reasons; raw two-way "
                         "prices per snapshot stored for the "
                         "market-only movement baseline"),
        },
        "n_candidates": len(rows),
        "n_taken": len(taken),
        "baseline_market_only": base_summary,
        "reject_reasons": reasons,
        "taken_by_snap": {"open": n_open, "morning": n_morn},
        "taken_by_book": books,
        "taken_by_book_flat1u": by_book,
        "n_close_invalid_flagged": int(sum(1 for r in rows if r.get("close_invalid"))),
        "n_taken_close_invalid": int(sum(1 for r in taken if r.get("close_invalid"))),
        "all": {
            "flat1u": _summarize(rows, "stake_flat1u"),
            "band": _summarize(rows, "stake_band"),
            "kelly_1_16": _summarize(rows, "stake_kelly"),
            "robust_kelly": _summarize(rows, "stake_robust"),
        },
        "realistic_dk_fd_only": {
            "note": "DK else FD; drop BetRivers/other fallback. Closer to live fill path.",
            "flat1u": _summarize(fill_dkfd, "stake_flat1u"),
            "kelly_1_16": _summarize(fill_dkfd, "stake_kelly"),
        },
        "y2025": {
            "flat1u": _summarize(year_slice("2025"), "stake_flat1u"),
            "kelly_1_16": _summarize(year_slice("2025"), "stake_kelly"),
        },
        "y2026_confirmatory": {
            "flat1u": _summarize(year_slice("2026"), "stake_flat1u"),
            "kelly_1_16": _summarize(year_slice("2026"), "stake_kelly"),
        },
        "probation_2_5_3_5": {
            "all": probation_pack(rows),
            "y2025": probation_pack(year_slice("2025")),
            "y2026_confirmatory": probation_pack(year_slice("2026")),
        },
    }
    atomic_write_text(out_report, json.dumps(rep, indent=2, default=str))
    print(json.dumps({
        "n_candidates": rep["n_candidates"],
        "n_taken": rep["n_taken"],
        "reasons": reasons,
        "all_flat1u": rep["all"]["flat1u"],
        "all_kelly": rep["all"]["kelly_1_16"],
        "y2025_flat": rep["y2025"]["flat1u"],
        "y2026_flat": rep["y2026_confirmatory"]["flat1u"],
        "dk_fd_only": rep["realistic_dk_fd_only"]["flat1u"],
        "by_book": by_book,
        "probation_all": rep["probation_2_5_3_5"]["all"],
    }, indent=2, default=str))
    print(f"wrote {out_parquet}")
    print(f"wrote {out_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
