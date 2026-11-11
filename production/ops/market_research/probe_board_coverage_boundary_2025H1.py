"""Boundary-exception follow-up to the board-clock coverage probe.

DEVELOPMENT ARTIFACT (execution requires owner authorization of exactly
the access declared in the coverage packet on PR #84 and this file's
docstring). NOT RUN under implementation permission.

The original probe (probe_board_coverage_2025H1.py) correctly BLOCKED:
book_lines row groups 16-17 span the 2025-06-30 protected boundary, so
pre-decode separation could not be established. Its blocked report and
destination are preserved unchanged; this script NEVER writes there.

This follow-up re-runs the same coverage aggregation with ONE explicit,
minimal exception, declared here before any run:

- book_lines groups ALLOWED for decode: every row group whose recorded
  footer classification is WINDOW_OR_EARLIER, plus the two recorded
  OVERLAPS_PROTECTED boundary groups (rg16, rg17) — quote columns only.
  PROTECTED_ONLY groups (rg18+) are never decoded.
- snapshot_envelope groups ALLOWED for decode: WINDOW_OR_EARLIER
  groups, plus any OVERLAPS_PROTECTED boundary groups under the same
  exception — timestamp metadata columns only (no quote values).
  The envelope's row-group layout was NOT inspected by the blocked
  run, so a footer-only preflight establishes it here and the script
  FAILS CLOSED on any undeclared access requirement (missing/unusable
  envelope date statistics, layout mismatch, unexpected groups).

Binding and failure modes (all fail closed BEFORE any data-page read):
- the blocked report must exist and contain the recorded input
  SHA-256s and the book_lines row-group layout;
- both input files must hash to their recorded values;
- a fresh footer-only read must reproduce the recorded book_lines
  layout exactly (same row-group count, rows, and date bounds);
- missing/unusable date statistics anywhere -> fail closed.

After decode: rows are filtered to the 2025H1 window IMMEDIATELY
(game_date/commence date <= 2025-06-30) before any aggregation, and an
assertion verifies no protected-date rows survive. Protected-date
values are never persisted, printed, or summarized. The aggregation
reuses the registered per-clock coverage definitions extracted in
probe_board_coverage_2025H1 (aggregate_per_clock /
envelope_timestamp_summary) and the same declared criterion
(operational coverage heuristic — not market-representativeness
evidence).

Outputs: ONE fresh JSON report
(...\\_probe\\board_coverage_boundary_2025H1.json; write-once; refuses
an existing destination). The original blocked report destination is
never written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
BOOK_LINES = HIST / "book_lines_pitcher.parquet"
ENVELOPE = HIST / "snapshot_envelope.parquet"
BLOCKED_REPORT = HIST / "_probe" / "board_coverage_2025H1.json"
OUT = HIST / "_probe" / "board_coverage_boundary_2025H1.json"
BOUNDARY = "2025-06-30"
CLOCKS = ["board", "morning", "close"]
QUERY_ID = "board_coverage_boundary_2025H1"

from production.ops.market_research import (  # noqa: E402
    probe_board_coverage_2025H1 as base,
)
QUOTE_COLUMNS = ["event_id", "snapshot", "snapshot_ts", "game_date",
                 "season_type", "book", "player_norm", "line", "side",
                 "price"]
ENVELOPE_COLUMNS = ["event_id", "snapshot", "vendor_timestamp",
                    "commence_time", "lag_vendor_vs_commence_sec"]


def _fail(reason: str) -> None:
    raise SystemExit(f"BOUNDARY FOLLOW-UP REFUSED: {reason}")


def load_blocked_report(path: Path) -> dict:
    if not path.exists():
        _fail(f"blocked report missing: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _fail(f"blocked report unreadable: {exc}")
    for key in ("input_sha256", "row_group_separation"):
        if key not in report:
            _fail(f"blocked report missing key: {key}")
    return report


def verify_input_hashes(book_lines: Path, envelope: Path,
                        recorded: dict) -> None:
    import hashlib
    for path, key in ((book_lines, "book_lines_pitcher"),
                      (envelope, "snapshot_envelope")):
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = recorded.get(key)
        if actual != expected:
            _fail(f"input identity mismatch for {key}: "
                  f"actual={actual} expected={expected}")


def verify_layout_matches_recorded(fresh_groups: list[dict],
                                   recorded_groups: list[dict]) -> None:
    """Fail closed unless the fresh footer layout reproduces the
    recorded layout exactly (same row-group count, rows, and date
    bounds per group)."""
    if len(fresh_groups) != len(recorded_groups):
        _fail(f"layout mismatch: {len(fresh_groups)} fresh row groups "
              f"vs {len(recorded_groups)} recorded")
    for fresh, recorded in zip(fresh_groups, recorded_groups):
        for key in ("row_group", "rows", "game_date_min",
                    "game_date_max"):
            if fresh.get(key) != recorded.get(key):
                _fail(f"layout mismatch at row group "
                      f"{recorded.get('row_group')}: {key} "
                      f"fresh={fresh.get(key)!r} "
                      f"recorded={recorded.get(key)!r}")


def select_allowed_groups(groups: list[dict], *,
                          boundary_exception: bool) -> tuple:
    """Allowed = WINDOW_OR_EARLIER + OVERLAPS_PROTECTED (when the
    boundary exception is declared); PROTECTED_ONLY and UNVERIFIABLE
    are excluded. Returns (allowed indices, excluded indices)."""
    allowed, excluded = [], []
    for g in groups:
        status = g["status"]
        if status == "WINDOW_OR_EARLIER":
            allowed.append(g["row_group"])
        elif status == "OVERLAPS_PROTECTED" and boundary_exception:
            allowed.append(g["row_group"])
        else:
            excluded.append(g["row_group"])
    return allowed, excluded


def read_allowed_groups(path: Path, allowed: list[int],
                        columns: list[str]) -> pl.DataFrame:
    """Decode ONLY the allowed row groups, projecting only the declared
    columns (pyarrow row-group selection = the physical pre-decode
    guarantee)."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    table = pf.read_row_groups(sorted(allowed), columns=sorted(columns))
    return pl.from_arrow(table)


def main() -> int:
    blocked = load_blocked_report(BLOCKED_REPORT)
    recorded_hashes = blocked["input_sha256"]
    recorded_sep = blocked["row_group_separation"]
    recorded_groups = recorded_sep.get("row_groups") or []
    if recorded_sep.get("verdict") != "NOT_SEPARABLE":
        _fail("blocked report verdict is not NOT_SEPARABLE; refusing to "
              "interpret an unexpected provenance")
    if not recorded_groups:
        _fail("blocked report carries no row-group layout")

    verify_input_hashes(BOOK_LINES, ENVELOPE, recorded_hashes)

    # fresh footer-only layout for book_lines; must match recorded
    fresh_bl = base.row_group_separation(BOOK_LINES, BOUNDARY,
                                         date_column="game_date")
    if not fresh_bl["verifiable"]:
        _fail("book_lines footer layout unverifiable")
    verify_layout_matches_recorded(fresh_bl["row_groups"],
                                   recorded_groups)

    allowed_bl, excluded_bl = select_allowed_groups(
        fresh_bl["row_groups"], boundary_exception=True)

    # envelope: footer-only preflight (declared; its layout was not in
    # the blocked report). Fail closed on missing/unusable date stats.
    fresh_env = base.row_group_separation(ENVELOPE, BOUNDARY,
                                          date_column="commence_time")
    if not fresh_env["verifiable"] \
            or fresh_env["verdict"] == "UNVERIFIABLE":
        _fail("envelope footer layout unverifiable (missing/unusable "
              f"commence_time statistics): {fresh_env}")
    allowed_env, excluded_env = select_allowed_groups(
        fresh_env["row_groups"], boundary_exception=True)

    # ---- decode allowed groups only; project declared columns
    rows = read_allowed_groups(BOOK_LINES, allowed_bl, QUOTE_COLUMNS)
    expected_rows = sum(g["rows"] for g in fresh_bl["row_groups"]
                        if g["row_group"] in allowed_bl)
    if rows.height != expected_rows:
        _fail(f"decoded row count {rows.height} != expected "
              f"{expected_rows}")
    # filter to 2025H1 IMMEDIATELY after boundary-group decode
    rows = rows.filter(pl.col("game_date") <= BOUNDARY)
    if rows["game_date"].max() is not None \
            and rows["game_date"].max() > BOUNDARY:
        _fail("protected-date rows survived the window filter; refusing")

    env = read_allowed_groups(ENVELOPE, allowed_env, ENVELOPE_COLUMNS)
    env = env.filter(
        pl.col("commence_time").str.slice(0, 10) <= BOUNDARY)

    # ---- registered aggregation (reused, unchanged definitions)
    per_clock = base.aggregate_per_clock(rows, CLOCKS)
    env_summary = base.envelope_timestamp_summary(env, CLOCKS)

    b2 = per_clock["board"]["n_two_sided_contracts"]
    c2 = per_clock["close"]["n_two_sided_contracts"]
    med = per_clock["board"]["median_books_per_event"]
    criterion = {
        "rule": ("board two-sided contracts >= 80% of close two-sided "
                 "contracts (same window, same contract granularity) "
                 "AND median books-per-event at board >= 2"),
        "board_two_sided": b2,
        "close_two_sided": c2,
        "median_books_per_event_board": med,
        "verdict": ("adequate" if c2 and b2 >= 0.8 * c2 and med >= 2
                    else "sparse_or_absent"),
        "label": ("OPERATIONAL COVERAGE HEURISTIC - not evidence of "
                  "market representativeness, edge, or CLV/ROI"),
    }

    accounting = {
        "cohort_window": {"gd_start": "2025-01-01", "gd_end": BOUNDARY,
                          "note": "confirm_2025H2 (gd > 2025-06-30) "
                                  "excluded pre-decode via row-group "
                                  "selection + immediate filter"},
        "book_lines": {
            "row_groups_total": len(fresh_bl["row_groups"]),
            "row_groups_allowed": sorted(allowed_bl),
            "row_groups_excluded_protected_only": sorted(excluded_bl),
            "rows_decoded": expected_rows,
            "rows_after_window_filter": rows.height,
        },
        "snapshot_envelope": {
            "row_groups_allowed": sorted(allowed_env),
            "row_groups_excluded_protected_only": sorted(excluded_env),
            "rows_after_window_filter": env.height,
        },
        "protected_date_handling": ("boundary-group rows with gd > "
                                    "2025-06-30 are decoded transiently "
                                    "(declared exception), filtered "
                                    "IMMEDIATELY, and never persisted, "
                                    "printed, or summarized"),
    }
    report = {
        "query_id": QUERY_ID,
        "window": {"gd_start": "2025-01-01", "gd_end": BOUNDARY,
                   "season_type": "regular",
                   "market": "pitcher_strikeouts"},
        "input_sha256": {k: recorded_hashes[k]
                         for k in ("book_lines_pitcher",
                                   "snapshot_envelope")},
        "row_group_separation": fresh_bl,
        "envelope_row_groups": fresh_env,
        "accounting": accounting,
        "per_clock_counts": per_clock,
        "envelope_timestamps": env_summary,
        "declared_criterion": criterion,
        "provenance": {
            "blocked_run_report": str(BLOCKED_REPORT),
            "bound_hashes": recorded_hashes,
            "supersedes": "the inline script in the earlier coverage "
                          "packet comment (never executed)",
        },
        "written_outputs": {"report": str(OUT)},
    }

    if OUT.exists():
        raise SystemExit(f"destination exists (write-once): {OUT}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=1, sort_keys=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(OUT)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
