"""Read-only board-clock coverage probe for the 2025H1 window.

DEVELOPMENT PROBE (execution requires owner authorization of exactly
the read declared in the coverage packet on PR #84). NOT RUN against
private data under implementation permission.

Question: does the existing paid lake support the recorded BOARD clock
(fixed 12:00Z = 8am ET, all-EDT) for game_date 2025-01-01..2025-06-30,
regular season?

Boundary (declared before any run):
- reads ONLY two local parquet files (book_lines_pitcher,
  snapshot_envelope) with column projection to the columns listed
  below; no Friend CSV; no outcomes/labels; no model artifacts; no
  network; no API calls;
- stage 0 reads PARQUET FOOTER METADATA ONLY (row-group boundaries +
  statistics; no data pages) and classifies each row group against the
  protected boundary (gd > 2025-06-30 = confirm_2025H2/2026):
    - statistics missing/unusable          -> UNVERIFIABLE
    - a group spanning window and protected dates -> NOT_SEPARABLE
    - otherwise (all rows <= boundary, or all > boundary)
      -> SEPARABLE (no protected rows mixed into decodable groups)
  Neither UNVERIFIABLE nor NOT_SEPARABLE may pass as safe: the script
  STOPS before any data-page read and writes the blocked evidence to
  the fresh report destination.
- Stage 1 (only when SEPARABLE) reads a restricted column projection
  (event_id, snapshot, snapshot_ts, game_date, season_type, book,
  player_norm, line, side, price) for the window and reports counts by
  clock/book, unique starts, two-sided exact contracts, and envelope
  timestamp availability/validity.

Row-level guarantee holds unconditionally (materialized frames contain
only window rows). Decode-level protection holds ONLY under the
SEPARABLE verdict; otherwise the precise permission gap (transient
in-memory decode of mixed row groups containing protected rows) is
disclosed in the report rather than assumed away.

Outputs: ONE fresh JSON report (write-once; refuses an existing
destination; atomic tmp+replace): row-group layout, per-clock counts
(quotes/events/unique starts/two-sided contracts/per-book two-sided),
envelope vendor_timestamp availability + lag percentiles, input
SHA-256 hashes, and the declared coverage verdict.
"""
import hashlib
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
BOOK_LINES = HIST / "book_lines_pitcher.parquet"
ENVELOPE = HIST / "snapshot_envelope.parquet"
OUT = HIST / "_probe" / "board_coverage_2025H1.json"
GD_LO, GD_HI = "2025-01-01", "2025-06-30"
PROTECTED_BOUNDARY = GD_HI  # gd > boundary = protected (2025H2 + 2026)
CLOCKS = ["board", "morning", "close"]
QUERY_ID = "board_coverage_2025H1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def row_group_separation(path: Path, protected_boundary: str) -> dict:
    """Footer-metadata-only classification of every row group against
    the protected date boundary (gd > boundary = protected). Missing
    or unusable game_date statistics -> UNVERIFIABLE; a group spanning
    the boundary -> NOT_SEPARABLE; neither may pass as safe."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    groups = []
    missing = False
    overlap = False
    for i in range(pf.metadata.num_row_groups):
        rg = pf.metadata.row_group(i)
        gd_min = gd_max = None
        for j in range(rg.num_columns):
            col = rg.column(j)
            path = col.path_in_schema
            name = path[0] if isinstance(path, list) else path
            if name != "game_date":
                continue
            st = col.statistics
            if st is not None and st.has_min_max \
                    and st.min is not None and st.max is not None:
                mn, mx = st.min, st.max
                if isinstance(mn, bytes):
                    mn = mn.decode("utf-8", errors="replace")
                if isinstance(mx, bytes):
                    mx = mx.decode("utf-8", errors="replace")
                gd_min, gd_max = str(mn)[:10], str(mx)[:10]
        if gd_min is None or gd_max is None:
            missing = True
            status = "UNVERIFIABLE"
        elif gd_max <= protected_boundary:
            status = "WINDOW_OR_EARLIER"
        elif gd_min > protected_boundary:
            status = "PROTECTED_ONLY"
        else:
            status = "OVERLAPS_PROTECTED"
            overlap = True
        groups.append({"row_group": i, "rows": rg.num_rows,
                       "game_date_min": gd_min, "game_date_max": gd_max,
                       "status": status})
    if missing:
        verdict = "UNVERIFIABLE"
    elif overlap:
        verdict = "NOT_SEPARABLE"
    else:
        verdict = "SEPARABLE"
    return {"verifiable": True, "verdict": verdict,
            "protected_boundary": protected_boundary,
            "row_groups": groups}


def _two_sided(book_lines_clock: pl.DataFrame) -> pl.DataFrame:
    wide = book_lines_clock.filter(pl.col("line").is_not_null()).pivot(
        values="price",
        index=["event_id", "player_norm", "line", "book"],
        on="side", aggregate_function="first")
    if "over" not in wide.columns or "under" not in wide.columns:
        return wide.head(0)
    return wide.filter(pl.col("over").is_not_null()
                       & pl.col("under").is_not_null())


def main() -> int:
    for p in (BOOK_LINES, ENVELOPE):
        if not p.exists():
            raise SystemExit(f"declared input missing: {p}")
    if OUT.exists():
        raise SystemExit(f"destination exists (write-once): {OUT}")
    hashes = {"book_lines_pitcher": hashlib.sha256(
        BOOK_LINES.read_bytes()).hexdigest(),
        "snapshot_envelope": hashlib.sha256(
            ENVELOPE.read_bytes()).hexdigest()}

    # ---- stage 0: row-group separation verdict (metadata only;
    #      NO data pages decoded in this stage)
    try:
        layout = row_group_separation(BOOK_LINES, PROTECTED_BOUNDARY)
    except Exception as exc:  # noqa: BLE001
        layout = {"verifiable": False, "verdict": "UNVERIFIABLE",
                  "reason": repr(exc)}
    report = {
        "query_id": QUERY_ID,
        "window": {"gd_start": GD_LO, "gd_end": GD_HI,
                   "season_type": "regular",
                   "market": "pitcher_strikeouts"},
        "input_sha256": hashes,
        "row_group_separation": layout,
        "stage1_executed": False,
    }

    if layout["verdict"] != "SEPARABLE":
        report["blocked"] = {
            "stage": "row_group_separation",
            "reason": ("row-group date statistics are missing/unusable "
                       "or a group spans the protected boundary; "
                       "pre-decode separation cannot be established "
                       "with current permissions; no data pages read")
            if layout["verdict"] == "UNVERIFIABLE" else
            ("a row group spans the protected boundary; transient "
             "decode of protected rows cannot be excluded under "
             "current permissions"),
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, indent=1, sort_keys=True)
        tmp = OUT.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(OUT)
        print(payload)
        return 1

    # ---- stage 1 (SEPARABLE only): window-restricted column read
    report["stage1_executed"] = True
    scan = pl.scan_parquet(BOOK_LINES).filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("season_type") == "regular")
        & (pl.col("game_date") >= GD_LO)
        & (pl.col("game_date") <= GD_HI)
        & pl.col("line").is_not_null()
        & pl.col("price").is_not_null()
    )
    rows = scan.select(["event_id", "snapshot", "snapshot_ts", "book",
                        "player_norm", "line", "side",
                        "price"]).collect()

    per_clock = {}
    for clock in CLOCKS:
        c = rows.filter(pl.col("snapshot") == clock)
        wide = c.filter(pl.col("line").is_not_null()).pivot(
            values="price",
            index=["event_id", "player_norm", "line", "book"],
            on="side", aggregate_function="first")
        two = (wide.filter(pl.col("over").is_not_null()
                           & pl.col("under").is_not_null())
               if ("over" in wide.columns and "under" in wide.columns)
               else wide.head(0))
        per_book = (two.group_by("book").agg(n=pl.len()).sort("book")
                    if two.height else
                    pl.DataFrame(schema={"book": pl.Utf8, "n": pl.UInt32}))
        books_per_event = (two.group_by(["event_id", "player_norm"])
                           .agg(pl.col("book").n_unique()
                                .alias("n_books")).sort("event_id"))
        per_clock[clock] = {
            "n_quotes": c.height,
            "n_events": c["event_id"].n_unique(),
            "n_unique_starts": c.select(["event_id", "player_norm"])
            .unique().height,
            "n_two_sided_contracts": two.height,
            "books_two_sided": {r["book"]: int(r["n"]) for r in
                                per_book.iter_rows(named=True)},
            "median_books_per_event": float(
                books_per_event["n_books"].median())
            if books_per_event.height else 0.0,
            "snapshot_ts_present_reconstructed": int(
                c["snapshot_ts"].is_not_null().sum()),
        }

    env = pl.scan_parquet(ENVELOPE).filter(
        (pl.col("snapshot").is_in(CLOCKS))
        & (pl.col("commence_time").str.slice(0, 10) >= GD_LO)
        & (pl.col("commence_time").str.slice(0, 10) <= GD_HI)
    ).select(["event_id", "snapshot", "vendor_timestamp", "commence_time",
              "lag_vendor_vs_commence_sec"]).collect()
    env_per_clock = {}
    for clock in CLOCKS:
        e = env.filter(pl.col("snapshot") == clock)
        lags = sorted(v for v in e["lag_vendor_vs_commence_sec"].to_list()
                      if v is not None)
        env_per_clock[clock] = {
            "n": e.height,
            "vendor_timestamp_present": int(
                e["vendor_timestamp"].is_not_null().sum()),
            "lag_p50_sec": lags[len(lags) // 2] if lags else None,
            "lag_p90_sec": (lags[int(0.9 * (len(lags) - 1))]
                            if lags else None),
            "n_vendor_at_or_after_commence": sum(1 for v in lags
                                                 if v >= 0),
        }

    b2 = per_clock["board"]["n_two_sided_contracts"]
    c2 = per_clock["close"]["n_two_sided_contracts"]
    median_books = per_clock["board"]["median_books_per_event"]
    report["declared_criterion"] = {
        "rule": ("board two-sided contracts >= 80% of close two-sided "
                 "contracts (same window, same contract granularity) "
                 "AND median books-per-event at board >= 2"),
        "board_two_sided": b2,
        "close_two_sided": c2,
        "median_books_per_event_board": median_books,
        "verdict": ("adequate" if c2 and b2 >= 0.8 * c2
                    and median_books >= 2 else "sparse_or_absent"),
        "label": ("OPERATIONAL COVERAGE HEURISTIC - not evidence of "
                  "market representativeness, edge, or CLV/ROI"),
    }
    report["per_clock_counts"] = per_clock
    report["envelope_timestamps"] = env_per_clock
    report["written_outputs"] = {"report": str(OUT)}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=1, sort_keys=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(OUT)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
