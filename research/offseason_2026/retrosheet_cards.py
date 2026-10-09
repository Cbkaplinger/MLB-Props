"""Retrosheet previous-game starting-card source (I4 experiment).

Parses Retrosheet event files (start/sub/id/info records), builds
ACTUAL previous-game starting batting cards (slots 1..9; substitutes
and the non-batting pitcher slot excluded), maps player ids via the
Chadwick register (key_retro -> key_mlbam), and verifies schedule
correspondence. Frozen by
`research/offseason_2026/i4-card-source-experiment.md`.

Conventions (frozen):
- Card = the team's most recent PRIOR game in RETROSHEET chronology
  (date, game_number) - chronology is NEVER inferred from game_pk.
- Only gametype "regular" games are eligible (approved-input policy).
- A start record with fielding_position 1 (pitcher) in a batting slot
  invalidates that card (2022-23 universal DH: pitchers never bat) -
  card ineligible, fallback applies, flagged.
- Any failure (missing team/date coverage, <9 valid slots, unmapped
  player) -> frozen fallback to the I3b proxy card + flag. No
  outcome-based exclusions, never silent.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

# Statcast home/away abbreviations -> Retrosheet 3-letter team codes
STATCAST_TO_RETRO = {
    "LAA": "ANA", "OAK": "OAK", "HOU": "HOU", "TOR": "TOR",
    "ATL": "ATL", "MIA": "MIA", "NYY": "NYA", "BOS": "BOS",
    "CLE": "CLE", "DET": "DET", "KC": "KCA", "CWS": "CHA",
    "MIN": "MIN", "SEA": "SEA", "TEX": "TEX", "STL": "SLN",
    "MIL": "MIL", "CIN": "CIN", "CHC": "CHN", "PIT": "PIT",
    "SD": "SDN", "SF": "SFN", "LAD": "LAN", "AZ": "ARI",
    "COL": "COL", "NYM": "NYN", "WSH": "WAS", "PHI": "PHI",
    "BAL": "BAL", "TB": "TBA"}

_ID_RE = re.compile(r"^id,([A-Z]{3})(\d{8})(\d)$")
_START_RE = re.compile(
    r'^start,([a-z][a-z\-]*\d{3}),"([^"]*)",(\d),(\d+),(\d+)$')


class RetroCardFailure(RuntimeError):
    pass


def parse_event_file(path: Path) -> list[dict]:
    """Parse one Retrosheet event file -> per-game records with
    starting cards (home + away), slots 1..9 in batting order.

    Substitute records are parsed for accounting but NEVER enter the
    starting card. Pitcher-in-batting-slot invalidates the card."""
    games: list[dict] = []
    cur: dict | None = None
    with open(path, "r", encoding="latin-1") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("id,"):
                m = _ID_RE.match(line)
                if m is None:
                    raise RetroCardFailure(
                        "unparseable game id: %r (%s)" % (line, path.name))
                cur = {"retro_id": m.group(0)[3:], "home": m.group(1),
                       "date": "%s-%s-%s" % (m.group(2)[:4],
                                             m.group(2)[4:6],
                                             m.group(2)[6:]),
                       "game_number": int(m.group(3)),
                       "gametype": None, "away": None,
                       "slots": {0: {}, 1: {}}, "n_subs": 0}
                games.append(cur)
            elif cur is None:
                continue
            elif line.startswith("info,gametype,"):
                cur["gametype"] = line.split(",", 2)[2]
            elif line.startswith("info,visteam,"):
                cur["away"] = line.split(",", 2)[2]
            elif line.startswith("start,"):
                m = _START_RE.match(line)
                if m is None:
                    raise RetroCardFailure(
                        "unparseable start record: %r (%s)"
                        % (line, path.name))
                pid = m.group(1)
                home_flag = int(m.group(3))
                slot = int(m.group(4))
                fpos = int(m.group(5))
                if home_flag not in (0, 1):
                    raise RetroCardFailure("bad home flag: %r" % line)
                if slot == 0:
                    continue  # non-batting pitcher entry: excluded
                if not (1 <= slot <= 9):
                    raise RetroCardFailure("bad batting slot: %r" % line)
                side = cur["slots"][home_flag]
                if slot in side:
                    raise RetroCardFailure(
                        "duplicate start slot %d in %s" % (slot,
                                                           cur["retro_id"]))
                if fpos == 1:
                    side[slot] = None  # pitcher batting: invalid card
                else:
                    side[slot] = pid
            elif line.startswith("sub,"):
                if cur is not None:
                    cur["n_subs"] += 1
    out = []
    for g in games:
        # season zips (events/{year}eve.zip) are regular-season
        # archives by construction; 2022 files omit info,gametype.
        # Reject only EXPLICIT non-regular types (e.g. playoffs).
        if g["gametype"] not in (None, "regular"):
            continue
        rec = {"retro_id": g["retro_id"], "date": g["date"],
               "game_number": g["game_number"], "home": g["home"],
               "away": g["away"], "gametype": g["gametype"],
               "n_subs": g["n_subs"]}
        for side_key, side_name in ((0, "away_card"), (1, "home_card")):
            slots = g["slots"][side_key]
            if len(slots) != 9 or any(v is None for v in slots.values()):
                rec[side_name] = None  # ineligible -> fallback
            else:
                rec[side_name] = [slots[i] for i in range(1, 10)]
        out.append(rec)
    return out


def load_season(raw_dir: Path) -> pl.DataFrame:
    """Parse every .EVA/.EVN file in a season directory -> frame."""
    recs: list[dict] = []
    files = sorted(list(raw_dir.glob("*.EVA")) + list(raw_dir.glob("*.EVN"))
                   + list(raw_dir.glob("*.eva")) + list(raw_dir.glob("*.evn")))
    # Windows globbing is case-insensitive: dedupe resolved paths
    seen: set[Path] = set()
    uniq: list[Path] = []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    files = uniq
    if not files:
        raise RetroCardFailure("no event files in %s" % raw_dir)
    for f in files:
        recs.extend(parse_event_file(f))
    df = pl.DataFrame(recs)
    if "gametype" in df.columns:
        df = df.with_columns(pl.col("gametype").cast(pl.Utf8))
    return df


def load_register(register_dir: Path) -> dict[str, int]:
    """Chadwick people shards -> {key_retro: key_mlbam} (both present)."""
    mapping: dict[str, int] = {}
    files = sorted(register_dir.glob("people-*.csv"))
    if not files:
        raise RetroCardFailure("no register people-*.csv in %s"
                               % register_dir)
    for f in files:
        df = pl.read_csv(f, columns=["key_retro", "key_mlbam"],
                         infer_schema_length=0)
        for r in df.iter_rows(named=True):
            retro, mlbam = r["key_retro"], r["key_mlbam"]
            if retro and mlbam:
                try:
                    mapping[retro] = int(mlbam)
                except (TypeError, ValueError):
                    continue
    if not mapping:
        raise RetroCardFailure("register produced an empty mapping")
    return mapping


def schedule_match(retro: pl.DataFrame, statcast_sched: pl.DataFrame
                   ) -> dict:
    """Verify (home team, date) game-count correspondence against the
    Statcast schedule and report doubleheader coverage. Frozen
    verification: match rate >= 0.99 (else mapping readiness fails ->
    BLOCKED). Chronology is taken from Retrosheet (date, game_number)
    and NEVER inferred from game_pk (frozen contract); without start
    times, per-game order inside a doubleheader cannot be verified
    from these inputs - the card source does not need it (team-level
    previous-game selection only), and unmatched games are ineligible
    card sources -> fallback + flag."""
    sc_counts = (statcast_sched.with_columns(
                    pl.col("home").replace_strict(
                        STATCAST_TO_RETRO, default=None).alias("home"))
                 .group_by(["home", "d"]).agg(pl.len().alias("n_sc")))
    retro_counts = (retro.group_by(["home", "date"])
                    .agg(pl.len().alias("n_rs")))
    j = (sc_counts.join(retro_counts,
                        left_on=[pl.col("home"), pl.col("d").cast(pl.Utf8)],
                        right_on=[pl.col("home"), pl.col("date").cast(pl.Utf8)],
                        how="full", coalesce=True)
         .with_columns([
             pl.col("n_sc").fill_null(0), pl.col("n_rs").fill_null(0)]))
    n_sc_total = int(j["n_sc"].sum())
    n_rs_total = int(j["n_rs"].sum())
    # coverage: statcast games whose team-date has >=1 retrosheet game
    covered = int(j.filter(pl.col("n_rs") >= 1)["n_sc"].sum())
    dh_mismatch = int(j.filter((pl.col("n_sc") > 1)
                               & (pl.col("n_sc") != pl.col("n_rs"))).height)
    dh_groups = int((j["n_sc"] > 1).sum())
    match_rate = covered / n_sc_total if n_sc_total else 0.0
    return {"statcast_team_dates": int(j.height),
            "statcast_games": n_sc_total, "retrosheet_games": n_rs_total,
            "covered_games": covered, "match_rate": match_rate,
            "doubleheader_team_dates": dh_groups,
            "doubleheader_count_mismatches": dh_mismatch,
            "threshold_match": match_rate >= 0.99,
            "note": "coverage = statcast games whose (team, date) has "
                    "a retrosheet game; chronology from Retrosheet "
                    "(date, game_number), never inferred from game_pk; "
                    "per-DH-game order unverifiable without start "
                    "times and not needed (prior-CALENDAR-date card "
                    "rule); uncovered team-dates -> fallback + flag"}


def previous_game_cards(retro: pl.DataFrame,
                        mapping: dict[str, int]) -> pl.DataFrame:
    """Per (team, date) the team plays: its previous REGULAR game
    strictly before that date in Retrosheet chronology (date,
    game_number), the starting card of that previous game (slots
    1..9, mapped to MLBAM), and provenance fields. Exactly ONE row
    per (team, date) - same-date doubleheader games are never the
    previous game. Unmapped players or ineligible cards -> card =
    None (fallback)."""
    games = retro.select(["retro_id", "date", "game_number", "home",
                          "away", "home_card", "away_card"]
                         ).sort(["date", "game_number"])
    by_team: dict[str, list] = {}
    for r in games.iter_rows(named=True):
        by_team.setdefault(r["home"], []).append(
            {"date": r["date"], "game_number": r["game_number"],
             "retro_id": r["retro_id"], "card": r["home_card"]})
        by_team.setdefault(r["away"], []).append(
            {"date": r["date"], "game_number": r["game_number"],
             "retro_id": r["retro_id"], "card": r["away_card"]})
    rows = []
    for team, lst in by_team.items():
        dates = sorted({e["date"] for e in lst})
        for d in dates:
            prior = [e for e in lst if e["date"] < d]
            if not prior:
                rows.append({"team": team, "date": d,
                             "prev_retro_id": None, "prev_date": None,
                             "rs_card": None})
                continue
            prior.sort(key=lambda e: (e["date"], e["game_number"]))
            prev = prior[-1]  # latest prior game_number wins (frozen)
            card = None
            if prev["card"] is not None:
                mapped = [mapping.get(p) for p in prev["card"]]
                if all(v is not None for v in mapped):
                    card = mapped
            rows.append({"team": team, "date": d,
                         "prev_retro_id": prev["retro_id"],
                         "prev_date": prev["date"],
                         "rs_card": card})
    return pl.DataFrame(rows)
