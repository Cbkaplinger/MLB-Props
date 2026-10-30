"""Terminal-event label bridge (statcast-event-bridge-v1).

Bounded real-schema integration between the completed-PA table (which
carries the binary K indicator `y` but NO event column) and the
four-class multiclass taxonomy. Replaces the registered
m0.event_label_frame real-data path for the baseline consumers because
that path (a) searches every season directory by default, (b) resolves
duplicate terminal records with keep="first" (hiding conflicts), and
(c) silently drops null and unrecognized labels before any assertion
can see them.

Contract:
  - reads ONLY the explicitly supplied raw Statcast parquet files
    (columns: game_pk, at_bat_number, batter, events);
  - terminal-event semantics: a PA's event is carried on its terminal
    row (non-null `events`); ordinary pitch rows (null events) are not
    terminal records;
  - per PA identity, the non-null terminal values must be CONSISTENT:
    multiple distinct terminal events for one identity are a CONFLICT
    and are never resolved by first-row order;
  - PA identities absent from the raw files remain detectable (label
    null); unknown events map to class_label -1 (preserved);
  - LEFT-joined onto the declared PA population, so historical (y-based)
    support is never reduced by label availability.

The y-consistency check (class_label == K_CLASS  <=>  y == 1) is the
consumer's responsibility and must be executed wherever labels are
required (see pregame_multiclass_baseline / prepare_assessment_2025H1).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

STATCAST_EVENT_BRIDGE_ID = "statcast_event_bridge_v1"
RAW_COLUMNS = ["game_pk", "at_bat_number", "batter", "events"]
IDENTITY = ["game_pk", "at_bat_number", "batter"]


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def attach_terminal_event_labels(pa: pl.DataFrame, raw_files: list,
                                 *, require_complete: bool = False,
                                 out_dir=None) -> tuple[pl.DataFrame, dict]:
    """LEFT-join validated terminal-event class labels onto `pa`.

    raw_files: explicit list of raw Statcast parquet paths (the caller
        declares exactly which files are consumed; no directory scan).
    require_complete: when True, every PA row must receive a recognized
        label (missing or unknown labels refuse with evidence).

    Returns (pa_with_class_label, accounting). The returned frame keeps
    every input row (historical y-based support is preserved); rows
    without a recognized label carry class_label = -1 (unknown) or null
    (absent from the raw terminal records).
    """
    if not raw_files:
        raise ValueError("explicit raw Statcast file list is required; "
                         "refusing a directory scan")
    frames = []
    consumed = []
    for f in raw_files:
        p = Path(f)
        if not p.exists():
            raise ValueError(f"raw event file missing: {p}")
        df = pl.read_parquet(p, columns=RAW_COLUMNS)
        consumed.append({"path": str(p),
                         "sha256": _file_sha(p),
                         "rows": int(df.height)})
        frames.append(df.filter(pl.col("events").is_not_null())
                       .select(*IDENTITY, "events"))
    if not frames:
        raise ValueError("no terminal event rows found in the declared "
                         "raw files")
    terminal = pl.concat(frames)

    # conflict detection BEFORE any dedup: distinct non-null events per
    # PA identity; first-record resolution is forbidden
    conflicts = (terminal.group_by(IDENTITY)
                 .agg(n_distinct=pl.col("events").n_unique(),
                      events=pl.col("events").unique().sort())
                 .filter(pl.col("n_distinct") > 1))
    if conflicts.height:
        examples = conflicts.head(5).rows()
        detail = {"stage": STATCAST_EVENT_BRIDGE_ID,
                  "failure": True,
                  "gate": "conflicting_terminal_events",
                  "n_conflicting_pa_identities": int(conflicts.height),
                  "examples": examples,
                  "detail": ("conflicting terminal labels are never "
                             "resolved by first-record selection; "
                             "correct the source or obtain an explicit "
                             "owner decision")}
        if out_dir is not None:
            (Path(out_dir) / "failure_record.json").write_text(
                json.dumps(detail, indent=1, sort_keys=True, default=str),
                encoding="utf-8")
        raise ValueError(f"conflicting_terminal_events: {examples}")

    labeled = (terminal.unique(subset=IDENTITY, keep="any")
               .with_columns(
                   m0.map_statcast_events(pl.col("events"))
                   .alias("class_label"))
               .select(*IDENTITY, "class_label"))

    out = pa.join(labeled, on=IDENTITY, how="left")
    identities = pa.select(IDENTITY).unique()
    matched = out.filter(pl.col("class_label").is_not_null())
    accounting = {
        "bridge": STATCAST_EVENT_BRIDGE_ID,
        "raw_files": consumed,
        "pa_rows": int(pa.height),
        "pa_identities": int(pa.select(IDENTITY).unique().height),
        "terminal_rows": int(terminal.height),
        "identities_with_terminal_event": int(
            labeled.select(IDENTITY).unique().height),
        "identities_matched": int(matched.height),
        "identities_missing_from_raw": int(
            pa.select(IDENTITY).unique().height
            - identities_with_terminal_event_count(pa, out)),
        "label_counts": {
            str(label): int(
                out.filter(pl.col("class_label") == label).height)
            for label in [-1, 0, 1, 2, 3]},
        "rows_without_label": int(out.filter(
            pl.col("class_label").is_null()).height),
    }
    if require_complete:
        missing = out.filter(pl.col("class_label").is_null())
        unknown = out.filter(pl.col("class_label") == -1)
        if missing.height or unknown.height:
            raise ValueError(
                f"label integrity failure: {missing.height} PA rows have "
                f"no terminal event and {unknown.height} carry "
                "unrecognized events; preparation evidence preserved")
    return out, accounting


def identities_with_terminal_event_count(pa: pl.DataFrame,
                                         out: pl.DataFrame) -> int:
    return int(out.filter(pl.col("class_label").is_not_null())
               .select(IDENTITY).unique().height)
