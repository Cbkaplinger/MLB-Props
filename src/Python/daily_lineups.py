"""Daily MLB lineup ingestion with ID-safe player matching.

RotoGrinders supplies projected/confirmed batting orders. MLB's Stats API
supplies canonical game, team, probable-pitcher, and player identifiers.
Names are used only to resolve a scraped row against an official team roster;
all returned model-facing rows retain MLB numeric IDs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Mapping
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import polars as pl

from . import config, identity


ROTOGRINDERS_LINEUPS_URL = "https://rotogrinders.com/lineups/mlb?site=draftkings"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_TEAM_ROSTER_URL = "https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
_USER_AGENT = "MLB-Props/0.1 (daily lineup research)"

# Fuzzy fallback thresholds (team-scoped only).
# Last name must be nearly exact before we allow soft given-name hits (nicknames /
# DFS truncations). Full-name similarity alone is not enough — e.g. Kong↔King
# can score ~0.91 on the concatenated string.
_FUZZY_LAST_STRICT = 0.98
_FUZZY_LAST_SOFT = 0.88
_FUZZY_GIVEN_WITH_STRICT_LAST = 0.55
_FUZZY_GIVEN_WITH_SOFT_LAST = 0.84
_FUZZY_FULL_WITH_STRICT_LAST = 0.70
_FUZZY_MARGIN = 0.08
_FUZZY_PREFIX_SCORE = 0.92
_FUZZY_EDIT1_SCORE = 0.90

# DFS scrapes often use nicknames MLB does not store (Mike≠Michael; ratio ~0.55).
# Groups are bidirectional and applied only within a team-scoped match.
_GIVEN_NAME_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"mike", "michael", "mick"}),
    frozenset({"matt", "matthew"}),
    frozenset({"alex", "alexander", "alexandre"}),
    frozenset({"chris", "christopher"}),
    frozenset({"dan", "daniel", "danny"}),
    frozenset({"dave", "david"}),
    frozenset({"jim", "james", "jimmy"}),
    frozenset({"joe", "joseph", "joey"}),
    frozenset({"bob", "robert", "bobby", "rob", "robbie", "robby"}),
    frozenset({"bill", "william", "will", "billy"}),
    frozenset({"tony", "anthony"}),
    frozenset({"nick", "nicholas", "nicolas"}),
    frozenset({"josh", "joshua"}),
    frozenset({"jon", "john", "johnny", "jonathan"}),
    frozenset({"tom", "thomas", "tommy"}),
    frozenset({"steve", "stephen", "steven"}),
    frozenset({"rich", "richard", "rick", "ricky"}),
    frozenset({"ron", "ronald", "ronnie"}),
    frozenset({"andy", "andrew", "drew"}),
    frozenset({"ben", "benjamin", "benny"}),
    frozenset({"sam", "samuel", "sammy"}),
    frozenset({"ted", "theodore", "theo"}),
    frozenset({"ed", "edward", "eddie"}),
    frozenset({"gabe", "gabriel"}),
    frozenset({"nate", "nathan", "nathaniel"}),
    frozenset({"zach", "zack", "zachary"}),
    frozenset({"jake", "jacob"}),
    frozenset({"pat", "patrick", "paddy"}),
    frozenset({"tim", "timothy"}),
    frozenset({"greg", "gregory"}),
    frozenset({"jeff", "jeffrey", "geoff", "geoffrey"}),
    frozenset({"ken", "kenneth", "kenny"}),
    frozenset({"larry", "lawrence"}),
    frozenset({"terry", "terence", "terrence"}),
    frozenset({"vince", "vincent"}),
    frozenset({"dom", "dominic", "dominick"}),
    frozenset({"fran", "francisco", "frank", "francis"}),
)

# Stable MLB Stats API team IDs. Aliases account for common DFS abbreviations.
TEAM_IDS: dict[str, int] = {
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHC": 112,
    "CWS": 145,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "HOU": 117,
    "KC": 118,
    "LAA": 108,
    "LAD": 119,
    "MIA": 146,
    "MIL": 158,
    "MIN": 142,
    "NYM": 121,
    "NYY": 147,
    "ATH": 133,
    "PHI": 143,
    "PIT": 134,
    "SD": 135,
    "SF": 137,
    "SEA": 136,
    "STL": 138,
    "TB": 139,
    "TEX": 140,
    "TOR": 141,
    "WSH": 120,
}
TEAM_ALIASES: dict[str, str] = {
    "AZ": "ARI",
    "ARI": "ARI",
    "CHW": "CWS",
    "CWS": "CWS",
    "KAN": "KC",
    "KCR": "KC",
    "KC": "KC",
    "OAK": "ATH",
    "ATH": "ATH",
    "SDP": "SD",
    "SD": "SD",
    "SFG": "SF",
    "SF": "SF",
    "TBR": "TB",
    "TB": "TB",
    "WAS": "WSH",
    "WSN": "WSH",
    "WSH": "WSH",
}
_TEAM_CODES_BY_ID = {team_id: code for code, team_id in TEAM_IDS.items()}


@dataclass(frozen=True)
class DailySlate:
    """Resolved daily batter lineups and starting pitchers."""

    lineups: pl.DataFrame
    starters: pl.DataFrame


def canonical_team_code(value: str) -> str:
    """Normalize a DFS team abbreviation to the project convention."""
    raw = value.strip().upper()
    code = TEAM_ALIASES.get(raw, raw)
    if code not in TEAM_IDS:
        raise ValueError(f"Unknown MLB team abbreviation: {value!r}")
    return code


def _ascii_name_tokens(value: str) -> list[str]:
    """Lowercased alphanumeric tokens with suffixes stripped."""
    ascii_name = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    ascii_name = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", ascii_name)
    return re.findall(r"[a-z0-9]+", ascii_name)


def _name_key(value: str) -> str:
    """Create a conservative comparison key for roster-bound name matching."""
    return "".join(_ascii_name_tokens(value))


def _split_name_keys(value: str) -> tuple[str, str]:
    """Return ``(given_key, last_key)`` from a display name."""
    tokens = _ascii_name_tokens(value)
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return "", tokens[0]
    return "".join(tokens[:-1]), tokens[-1]


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` differ by at most one insert/delete/substitute."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    # a is shorter or equal.
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) <= 1
    # One insertion into a to make b.
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def _token_similarity(query: str, candidate: str, *, allow_nicknames: bool) -> float:
    """Similarity between two name tokens with nickname / typo / prefix boosts."""
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    best = _similarity(query, candidate)
    if allow_nicknames and _given_names_equivalent(query, candidate):
        return 1.0
    shorter, longer = (query, candidate) if len(query) <= len(candidate) else (candidate, query)
    if len(shorter) >= 3 and longer.startswith(shorter):
        best = max(best, _FUZZY_PREFIX_SCORE)
    if len(query) >= 3 and len(candidate) >= 3 and _edit_distance_at_most_one(query, candidate):
        best = max(best, _FUZZY_EDIT1_SCORE)
    return best


def _given_name_aliases(token: str) -> set[str]:
    """Return ``token`` plus known nickname/legal peers (lowercase ASCII)."""
    key = token.strip().lower()
    if not key:
        return set()
    for group in _GIVEN_NAME_GROUPS:
        if key in group:
            return set(group)
    return {key}


def _given_names_equivalent(a: str, b: str) -> bool:
    """True when given tokens share a nickname group or are identical."""
    left = a.strip().lower()
    right = b.strip().lower()
    if not left or not right:
        return False
    return right in _given_name_aliases(left)


def _best_given_similarity(query_given: str, official_tokens: list[str]) -> float:
    """Best given-name score against official first/use/full tokens."""
    if not query_given:
        return 0.0
    tokens = [tok for tok in official_tokens if tok]
    if not tokens:
        return 0.0
    # Also compare against concatenated multi-token givens (e.g. junghoo).
    joined = "".join(tokens)
    pool = tokens + ([joined] if joined and joined not in tokens else [])
    return max(_token_similarity(query_given, tok, allow_nicknames=True) for tok in pool)


def _best_last_similarity(query_last: str, last_candidates: list[str]) -> float:
    """Best last-name score (conservative typos; no nickname aliases)."""
    if not query_last:
        return 0.0
    cands = [c for c in last_candidates if c]
    if not cands:
        return 0.0
    best = 0.0
    for cand in cands:
        if query_last == cand:
            return 1.0
        score = _similarity(query_last, cand)
        # Longer surnames: allow a single edit (insert/delete/substitute).
        if (
            len(query_last) >= 5
            and len(cand) >= 5
            and _edit_distance_at_most_one(query_last, cand)
        ):
            score = max(score, _FUZZY_EDIT1_SCORE)
        # Short surnames: only a final-letter typo (Kinq↔King), not Kong↔King.
        elif (
            len(query_last) >= 4
            and len(cand) >= 4
            and len(query_last) == len(cand)
            and query_last[:-1] == cand[:-1]
            and query_last[-1] != cand[-1]
        ):
            score = max(score, _FUZZY_EDIT1_SCORE)
        best = max(best, score)
    return best


def _roster_display_variants(row: dict[str, object]) -> list[str]:
    return _name_variant_strings(
        full_name=str(row.get("player_name") or ""),
        first_name=str(row.get("first_name") or "") or None,
        use_name=str(row.get("use_name") or "") or None,
        nick_name=str(row.get("nick_name") or "") or None,
        last_name=str(row.get("last_name") or "") or None,
        map_name=str(row.get("map_name") or "") or None,
    )


def _score_roster_name_match(
    player_name: str,
    row: dict[str, object],
) -> tuple[float, float, float, float] | None:
    """Return ``(composite, last, given, full)`` scores for one roster row."""
    query_given, query_last = _split_name_keys(player_name)
    if not query_last:
        return None
    query_key = _name_key(player_name)
    full = str(row.get("player_name") or "")
    first = str(row.get("first_name") or "")
    use = str(row.get("use_name") or "")
    nick = str(row.get("nick_name") or "")
    last = str(row.get("last_name") or "")
    full_tokens = _ascii_name_tokens(full)
    roster_last = full_tokens[-1] if full_tokens else ""
    given_from_full = full_tokens[:-1] if len(full_tokens) > 1 else []
    last_key = _name_key(last) if last else roster_last

    official_given_tokens = [
        tok
        for tok in (
            _ascii_name_tokens(first)
            + _ascii_name_tokens(use)
            + _ascii_name_tokens(nick)
            + given_from_full
        )
        if tok and tok != last_key
    ]
    last_sim = _best_last_similarity(
        query_last,
        [last_key, roster_last, _name_key(last)],
    )
    given_sim = _best_given_similarity(query_given, official_given_tokens)
    variants = _roster_display_variants(row)
    full_sim = 0.0
    for variant in variants:
        full_sim = max(full_sim, _similarity(query_key, _name_key(variant)))
    # Weighted composite for ranking among accepted candidates.
    composite = 0.50 * last_sim + 0.35 * given_sim + 0.15 * full_sim
    return composite, last_sim, given_sim, full_sim


def _fuzzy_accept(last_sim: float, given_sim: float, full_sim: float) -> bool:
    """Gate fuzzy hits so wrong last names cannot win on full-string similarity."""
    if last_sim >= _FUZZY_LAST_STRICT:
        return (
            given_sim >= _FUZZY_GIVEN_WITH_STRICT_LAST
            or full_sim >= _FUZZY_FULL_WITH_STRICT_LAST
        )
    if last_sim >= _FUZZY_LAST_SOFT:
        return given_sim >= _FUZZY_GIVEN_WITH_SOFT_LAST
    return False


def _fuzzy_match_roster_id(
    player_name: str,
    team_id: int,
    roster_rows: list[dict[str, object]],
) -> int | None:
    """Team-scoped fuzzy match on last, given, and whole name.

    Scores every same-team roster player. Accepts only when last name is nearly
    exact (nicknames / DFS truncations / small given typos) or when both last
    and given are strong typos. Requires a clear margin over the runner-up.
    """
    _, query_last = _split_name_keys(player_name)
    if not query_last:
        return None

    scored: list[tuple[float, float, float, float, int]] = []
    for row in roster_rows:
        if int(row["team_id"]) != int(team_id):
            continue
        parts = _score_roster_name_match(player_name, row)
        if parts is None:
            continue
        composite, last_sim, given_sim, full_sim = parts
        if not _fuzzy_accept(last_sim, given_sim, full_sim):
            continue
        scored.append((composite, last_sim, given_sim, full_sim, int(row["mlb_id"])))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[4]))
    best = scored[0]
    if len(scored) > 1 and best[0] - scored[1][0] < _FUZZY_MARGIN:
        return None
    return best[4]


def _name_variant_strings(
    *,
    full_name: str,
    first_name: str | None = None,
    use_name: str | None = None,
    nick_name: str | None = None,
    last_name: str | None = None,
    map_name: str | None = None,
) -> list[str]:
    """Official + legal/use/nick/map display strings for one roster person."""
    names: list[str] = []
    for value in (full_name, map_name):
        if value:
            names.append(value)
    last = (last_name or "").strip()
    if not last and full_name and " " in full_name.strip():
        last = full_name.strip().rsplit(" ", 1)[-1]
    givens = [
        (first_name or "").strip(),
        (use_name or "").strip(),
        (nick_name or "").strip(),
    ]
    if full_name and " " in full_name.strip():
        givens.append(full_name.strip().rsplit(" ", 1)[0])
    if last:
        for given in givens:
            if not given:
                continue
            names.append(f"{given} {last}")
            for token in _ascii_name_tokens(given):
                names.append(f"{token} {last}")
                for alias in _given_name_aliases(token):
                    if alias != token:
                        names.append(f"{alias} {last}")
    # Preserve order while dropping empties/dupes.
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def fetch_mlb_person_name_parts(
    player_ids: tuple[int, ...],
    *,
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Fetch legal/use/nick name parts for roster ID enrichment."""
    rows: list[dict[str, int | str | None]] = []
    unique_ids = tuple(sorted(set(player_ids)))
    for start in range(0, len(unique_ids), 100):
        chunk = unique_ids[start : start + 100]
        query = urlencode({"personIds": ",".join(map(str, chunk))})
        payload = json.loads(
            _fetch_bytes(f"{MLB_PEOPLE_URL}?{query}", timeout=timeout)
        )
        for person in payload.get("people", []):
            person_id = person.get("id")
            if person_id is None:
                continue
            rows.append(
                {
                    "mlb_id": int(person_id),
                    "first_name": person.get("firstName"),
                    "use_name": person.get("useName"),
                    "nick_name": person.get("nickName"),
                    "last_name": person.get("lastName"),
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "mlb_id": pl.Int64,
            "first_name": pl.String,
            "use_name": pl.String,
            "nick_name": pl.String,
            "last_name": pl.String,
        },
        orient="row",
    )


def enrich_rosters_for_matching(
    rosters: pl.DataFrame,
    *,
    timeout: float = 30.0,
    player_map: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Attach MLB person name parts and optional local player-map display names."""
    if rosters.is_empty():
        return rosters.with_columns(
            pl.lit(None, dtype=pl.String).alias("first_name"),
            pl.lit(None, dtype=pl.String).alias("use_name"),
            pl.lit(None, dtype=pl.String).alias("nick_name"),
            pl.lit(None, dtype=pl.String).alias("last_name"),
            pl.lit(None, dtype=pl.String).alias("map_name"),
        )
    ids = tuple(int(value) for value in rosters["mlb_id"].unique().to_list())
    people = fetch_mlb_person_name_parts(ids, timeout=timeout)
    enriched = rosters.join(people, on="mlb_id", how="left")
    if player_map is None:
        try:
            player_map = identity.load_player_map()
        except Exception:  # noqa: BLE001 - matching still works without the cache
            player_map = pl.DataFrame(
                schema={"mlb_id": pl.Int64, "player_name": pl.String}
            )
    map_names = player_map.select(
        pl.col("mlb_id").cast(pl.Int64),
        pl.col("player_name").alias("map_name"),
    ).unique(subset=["mlb_id"], keep="first")
    return enriched.join(map_names, on="mlb_id", how="left")


def build_roster_name_index(rosters: pl.DataFrame) -> pl.DataFrame:
    """Explode roster rows into normalized name keys (exact + legal/use/map)."""
    rows: list[dict[str, int | str]] = []
    for record in rosters.to_dicts():
        variants = _name_variant_strings(
            full_name=str(record.get("player_name") or ""),
            first_name=record.get("first_name"),
            use_name=record.get("use_name"),
            nick_name=record.get("nick_name"),
            last_name=record.get("last_name"),
            map_name=record.get("map_name"),
        )
        team_id = int(record["team_id"])
        mlb_id = int(record["mlb_id"])
        for variant in variants:
            key = _name_key(variant)
            if key:
                rows.append(
                    {
                        "team_id": team_id,
                        "_name_key": key,
                        "mlb_id": mlb_id,
                    }
                )
    if not rows:
        return pl.DataFrame(
            schema={
                "team_id": pl.Int64,
                "_name_key": pl.String,
                "mlb_id": pl.Int64,
            }
        )
    index = pl.DataFrame(rows).unique(subset=["team_id", "_name_key", "mlb_id"])
    ambiguous = (
        index.group_by(["team_id", "_name_key"])
        .agg(pl.col("mlb_id").n_unique().alias("_ids"))
        .filter(pl.col("_ids") > 1)
    )
    if not ambiguous.is_empty():
        # Drop only the colliding keys; exact fullName keys still resolve.
        bad_keys = ambiguous.select("team_id", "_name_key")
        index = index.join(bad_keys, on=["team_id", "_name_key"], how="anti")
    return index


def _fetch_bytes(url: str, *, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def fetch_rotogrinders_html(*, timeout: float = 30.0) -> bytes:
    """Download the current DraftKings MLB lineup page."""
    return _fetch_bytes(ROTOGRINDERS_LINEUPS_URL, timeout=timeout)


def _lineup_schema() -> dict[str, pl.DataType]:
    return {
        "game_date": pl.Date,
        "slate_game_key": pl.Int64,
        "rg_game_time": pl.Datetime(time_zone="UTC"),
        "rg_game_number": pl.Int64,
        "away_team": pl.String,
        "home_team": pl.String,
        "away_team_id": pl.Int64,
        "home_team_id": pl.Int64,
        "team": pl.String,
        "team_id": pl.Int64,
        "opponent": pl.String,
        "opponent_team_id": pl.Int64,
        "is_home": pl.Boolean,
        "batting_order": pl.Int64,
        "player_name": pl.String,
        "bats": pl.String,
        "position": pl.String,
        "salary": pl.Int64,
        "lineup_status": pl.String,
        "source": pl.String,
        "source_player_path": pl.String,
        "fetched_at": pl.Datetime(time_zone="UTC"),
    }


def _starter_schema() -> dict[str, pl.DataType]:
    return {
        "game_date": pl.Date,
        "slate_game_key": pl.Int64,
        "rg_game_time": pl.Datetime(time_zone="UTC"),
        "rg_game_number": pl.Int64,
        "away_team": pl.String,
        "home_team": pl.String,
        "away_team_id": pl.Int64,
        "home_team_id": pl.Int64,
        "team": pl.String,
        "team_id": pl.Int64,
        "opponent": pl.String,
        "opponent_team_id": pl.Int64,
        "is_home": pl.Boolean,
        "player_name": pl.String,
        "throws": pl.String,
        "lineup_status": pl.String,
        "source": pl.String,
        "source_player_path": pl.String,
        "fetched_at": pl.Datetime(time_zone="UTC"),
    }


_RG_GAME_NUMBER_RE = re.compile(
    r"(?:#{2,3}\s*([12])\b)|(?:\bgame\s*([12])\b)",
    re.IGNORECASE,
)
_RG_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*[AP]M)\s*ET\b", re.IGNORECASE)


def _parse_rg_game_meta(
    card: object,
    *,
    game_date: date,
) -> tuple[datetime | None, int]:
    """Extract start time and DH game number from a RotoGrinders game card.

    Prefers explicit markers (``###2``, ``Game 2``). Falls back to the card's
    ``H:MM PM ET`` clock time so doubleheaders with distinct tips still match
    the MLB schedule without colliding on team pair alone.
    """
    text = " ".join(card.stripped_strings)
    game_number = 1
    match = _RG_GAME_NUMBER_RE.search(text)
    if match:
        game_number = int(next(g for g in match.groups() if g))

    rg_time: datetime | None = None
    time_match = _RG_TIME_RE.search(text)
    if time_match:
        local = datetime.strptime(
            f"{game_date.isoformat()} {time_match.group(1).upper()}",
            "%Y-%m-%d %I:%M %p",
        ).replace(tzinfo=ZoneInfo("America/New_York"))
        rg_time = local.astimezone(timezone.utc)
    return rg_time, game_number


def _player_values(nameplate: object) -> tuple[str | None, str | None, str | None]:
    if nameplate is None:
        return None, None, None
    anchor = nameplate.select_one("a.player-nameplate-name")
    if anchor is None:
        return None, None, None
    name = anchor.get_text(" ", strip=True)
    if not name or name.upper() == "TBD":
        return None, None, None
    hand_node = nameplate.select_one(".player-nameplate-stats > span.small")
    hand = hand_node.get_text(" ", strip=True).strip("()") if hand_node else None
    return name, hand or None, anchor.get("href")


def parse_rotogrinders_html(
    html: bytes | str,
    *,
    game_date: date,
    fetched_at: datetime | None = None,
) -> DailySlate:
    """Parse RotoGrinders markup without performing identity joins."""
    fetched_at = (fetched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    soup = BeautifulSoup(html, "html.parser")
    lineup_rows: list[dict[str, object]] = []
    starter_rows: list[dict[str, object]] = []

    for card_index, card in enumerate(soup.select(".module.game-card")):
        team_nodes = card.select(".game-card-teams .team-nameplate-title")
        lineup_cards = card.select(".game-card-lineups > .lineup-card")
        if len(team_nodes) != 2 or len(lineup_cards) != 2:
            continue

        away_team = canonical_team_code(str(team_nodes[0].get("data-abbr", "")))
        home_team = canonical_team_code(str(team_nodes[1].get("data-abbr", "")))
        away_team_id = TEAM_IDS[away_team]
        home_team_id = TEAM_IDS[home_team]
        rg_game_time, rg_game_number = _parse_rg_game_meta(card, game_date=game_date)

        for index, lineup_card in enumerate(lineup_cards):
            is_home = index == 1
            team = home_team if is_home else away_team
            opponent = away_team if is_home else home_team
            team_id = home_team_id if is_home else away_team_id
            opponent_team_id = away_team_id if is_home else home_team_id
            body = lineup_card.select_one(".lineup-card-body")
            body_classes = set(body.get("class", [])) if body else set()
            lineup_status = "projected" if "unconfirmed" in body_classes else "confirmed"
            common = {
                "game_date": game_date,
                "slate_game_key": card_index,
                "rg_game_time": rg_game_time,
                "rg_game_number": rg_game_number,
                "away_team": away_team,
                "home_team": home_team,
                "away_team_id": away_team_id,
                "home_team_id": home_team_id,
                "team": team,
                "team_id": team_id,
                "opponent": opponent,
                "opponent_team_id": opponent_team_id,
                "is_home": is_home,
                "lineup_status": lineup_status,
                "source": "rotogrinders",
                "fetched_at": fetched_at,
            }

            pitcher_container = lineup_card.select_one(".lineup-card-pitcher")
            pitcher_plate = (
                pitcher_container.find(
                    "span", class_="player-nameplate", recursive=False
                )
                if pitcher_container
                else None
            )
            pitcher_name, pitcher_hand, pitcher_path = _player_values(pitcher_plate)
            starter_rows.append(
                {
                    **common,
                    "player_name": pitcher_name,
                    "throws": pitcher_hand,
                    "source_player_path": pitcher_path,
                }
            )

            if body is None:
                continue
            for player_row in body.select("li.lineup-card-player"):
                nameplate = player_row.select_one("span.player-nameplate")
                player_name, bats, player_path = _player_values(nameplate)
                order_node = nameplate.find("span", class_="small") if nameplate else None
                try:
                    batting_order = int(order_node.get_text(strip=True))
                except (AttributeError, TypeError, ValueError):
                    batting_order = None
                salary_raw = nameplate.get("data-salary") if nameplate else None
                try:
                    salary = int(salary_raw)
                except (TypeError, ValueError):
                    salary = None
                lineup_rows.append(
                    {
                        **common,
                        "batting_order": batting_order,
                        "player_name": player_name,
                        "bats": bats,
                        "position": (
                            str(nameplate.get("data-position"))
                            if nameplate and nameplate.get("data-position")
                            else None
                        ),
                        "salary": salary,
                        "source_player_path": player_path,
                    }
                )

    return DailySlate(
        lineups=pl.DataFrame(
            lineup_rows,
            schema=_lineup_schema(),
            orient="row",
            strict=False,
        ),
        starters=pl.DataFrame(
            starter_rows,
            schema=_starter_schema(),
            orient="row",
            strict=False,
        ),
    )


def fetch_mlb_schedule(
    game_date: date,
    *,
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Fetch the official daily schedule and probable-pitcher IDs."""
    query = urlencode(
        {
            "sportId": 1,
            "date": game_date.isoformat(),
            "hydrate": "probablePitcher",
        }
    )
    payload = json.loads(
        _fetch_bytes(f"{MLB_SCHEDULE_URL}?{query}", timeout=timeout)
    )
    rows: list[dict[str, object]] = []
    for date_group in payload.get("dates", []):
        for game in date_group.get("games", []):
            away = game["teams"]["away"]
            home = game["teams"]["home"]
            away_id = int(away["team"]["id"])
            home_id = int(home["team"]["id"])
            if away_id not in _TEAM_CODES_BY_ID or home_id not in _TEAM_CODES_BY_ID:
                continue
            rows.append(
                {
                    "game_pk": int(game["gamePk"]),
                    "game_date": game_date,
                    "game_time": datetime.fromisoformat(
                        game["gameDate"].replace("Z", "+00:00")
                    ),
                    "game_status": game.get("status", {}).get("detailedState"),
                    "game_number": int(game.get("gameNumber") or 1),
                    "double_header": str(game.get("doubleHeader") or "N"),
                    "away_team": _TEAM_CODES_BY_ID[away_id],
                    "home_team": _TEAM_CODES_BY_ID[home_id],
                    "away_team_id": away_id,
                    "home_team_id": home_id,
                    "away_probable_pitcher_id": (
                        int(away["probablePitcher"]["id"])
                        if away.get("probablePitcher", {}).get("id") is not None
                        else None
                    ),
                    "home_probable_pitcher_id": (
                        int(home["probablePitcher"]["id"])
                        if home.get("probablePitcher", {}).get("id") is not None
                        else None
                    ),
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "game_pk": pl.Int64,
            "game_date": pl.Date,
            "game_time": pl.Datetime(time_zone="UTC"),
            "game_status": pl.String,
            "game_number": pl.Int64,
            "double_header": pl.String,
            "away_team": pl.String,
            "home_team": pl.String,
            "away_team_id": pl.Int64,
            "home_team_id": pl.Int64,
            "away_probable_pitcher_id": pl.Int64,
            "home_probable_pitcher_id": pl.Int64,
        },
        orient="row",
        strict=False,
    )


def fetch_mlb_rosters(
    team_ids: tuple[int, ...],
    game_date: date,
    *,
    roster_type: str = "active",
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Fetch official team rosters containing MLB person IDs."""
    rows: list[dict[str, int | str]] = []
    for team_id in sorted(set(team_ids)):
        query = urlencode(
            {"rosterType": roster_type, "date": game_date.isoformat()}
        )
        url = f"{MLB_TEAM_ROSTER_URL.format(team_id=team_id)}?{query}"
        payload = json.loads(_fetch_bytes(url, timeout=timeout))
        rows.extend(
            {
                "team_id": team_id,
                "mlb_id": int(item["person"]["id"]),
                "player_name": item["person"]["fullName"],
            }
            for item in payload.get("roster", [])
            if item.get("person", {}).get("id") is not None
            and item.get("person", {}).get("fullName")
        )
    return pl.DataFrame(
        rows,
        schema={
            "team_id": pl.Int64,
            "mlb_id": pl.Int64,
            "player_name": pl.String,
        },
        orient="row",
    ).unique(subset=["team_id", "mlb_id"])


def resolve_player_ids(
    frame: pl.DataFrame,
    rosters: pl.DataFrame,
    *,
    output_column: str,
    aliases: Mapping[tuple[int, str], int] | None = None,
    require_complete: bool = True,
    timeout: float = 30.0,
    enrich: bool = True,
) -> pl.DataFrame:
    """Resolve scraped names within an official team roster, then retain IDs.

    Matching order (always team-scoped):
    1. Exact normalized key against roster ``fullName``
    2. Legal/use/nick + nickname peers + local player-map variants
    3. Explicit aliases
    4. Fuzzy last + given + whole-name similarity (nicknames, typos,
       DFS truncations), gated so wrong last names cannot win on full string
    """
    if frame.is_empty():
        return frame.with_columns(pl.lit(None, dtype=pl.Int64).alias(output_column))

    working = rosters
    if enrich and "first_name" not in working.columns:
        working = enrich_rosters_for_matching(working, timeout=timeout)

    name_index = build_roster_name_index(working)
    ambiguous = (
        name_index.group_by(["team_id", "_name_key"])
        .agg(pl.col("mlb_id").n_unique().alias("_ids"))
        .filter(pl.col("_ids") > 1)
    )
    if not ambiguous.is_empty():
        raise ValueError(
            "Official roster contains ambiguous normalized player names: "
            f"{ambiguous.head(10).to_dicts()}"
        )

    keyed = frame.with_columns(
        pl.col("player_name")
        .fill_null("")
        .map_elements(_name_key, return_dtype=pl.String)
        .alias("_name_key")
    )
    resolved = keyed.join(
        name_index.select("team_id", "_name_key", "mlb_id"),
        on=["team_id", "_name_key"],
        how="left",
        validate="m:1",
    )
    if aliases:
        alias_rows = [
            {
                "team_id": team_id,
                "_name_key": _name_key(name),
                "_alias_mlb_id": mlb_id,
            }
            for (team_id, name), mlb_id in aliases.items()
        ]
        alias_frame = pl.DataFrame(alias_rows)
        resolved = (
            resolved.join(
                alias_frame,
                on=["team_id", "_name_key"],
                how="left",
                validate="m:1",
            )
            .with_columns(
                pl.coalesce("mlb_id", "_alias_mlb_id").alias("mlb_id")
            )
            .drop("_alias_mlb_id")
        )

    # Fuzzy fill remaining misses against the same-team roster only.
    if resolved.filter(pl.col("mlb_id").is_null()).height:
        roster_rows = working.to_dicts()
        fuzzy_ids: list[int | None] = []
        for row in resolved.select("team_id", "player_name", "mlb_id").iter_rows(
            named=True
        ):
            if row["mlb_id"] is not None:
                fuzzy_ids.append(None)
                continue
            fuzzy_ids.append(
                _fuzzy_match_roster_id(
                    str(row["player_name"] or ""),
                    int(row["team_id"]),
                    roster_rows,
                )
            )
        resolved = resolved.with_columns(
            pl.coalesce(
                pl.col("mlb_id"),
                pl.Series("_fuzzy_mlb_id", fuzzy_ids, dtype=pl.Int64),
            ).alias("mlb_id")
        )

    missing = resolved.filter(pl.col("mlb_id").is_null()).select(
        "team", "player_name"
    )
    if require_complete and not missing.is_empty():
        raise ValueError(
            f"Could not resolve {missing.height} lineup players to MLB IDs: "
            f"{missing.unique().head(20).to_dicts()}"
        )
    return resolved.rename({"mlb_id": output_column}).drop("_name_key")


def attach_schedule(slate: DailySlate, schedule: pl.DataFrame) -> DailySlate:
    """Attach official game IDs and probable pitchers to parsed source rows.

    Single games join on team pair. Doubleheaders disambiguate by explicit
    ``rg_game_number`` / schedule ``game_number`` when present, otherwise by
    nearest ``rg_game_time`` ↔ ``game_time``. Each RotoGrinders card maps to at
    most one ``game_pk``, so same-day rematches do not duplicate starters.
    """
    if "game_number" not in schedule.columns:
        schedule = schedule.with_columns(pl.lit(1).cast(pl.Int64).alias("game_number"))
    if "double_header" not in schedule.columns:
        schedule = schedule.with_columns(pl.lit("N").alias("double_header"))

    # Unique RG cards (one row per slate_game_key).
    cards = (
        slate.starters.select(
            "slate_game_key",
            "game_date",
            "away_team_id",
            "home_team_id",
            "away_team",
            "home_team",
            "rg_game_time",
            "rg_game_number",
        )
        .unique(subset=["slate_game_key"])
        .sort("slate_game_key")
    )

    assignments: list[dict[str, object]] = []
    used_game_pks: set[int] = set()
    unmatched: list[dict[str, object]] = []
    for card in cards.to_dicts():
        candidates = schedule.filter(
            (pl.col("game_date") == card["game_date"])
            & (pl.col("away_team_id") == card["away_team_id"])
            & (pl.col("home_team_id") == card["home_team_id"])
        ).sort(["game_number", "game_time"])
        if candidates.is_empty():
            unmatched.append(
                {
                    "away_team": card["away_team"],
                    "home_team": card["home_team"],
                    "rg_game_number": card.get("rg_game_number"),
                }
            )
            continue
        available = candidates.filter(~pl.col("game_pk").is_in(list(used_game_pks)))
        if available.is_empty():
            unmatched.append(
                {
                    "away_team": card["away_team"],
                    "home_team": card["home_team"],
                    "rg_game_number": card.get("rg_game_number"),
                    "reason": "all schedule games already assigned",
                }
            )
            continue

        chosen = None
        rg_num = card.get("rg_game_number")
        if rg_num is not None and available.filter(pl.col("game_number") == rg_num).height:
            # Prefer explicit ###2 / Game 2 markers when the schedule agrees.
            by_num = available.filter(pl.col("game_number") == rg_num)
            if by_num.height == 1 or card.get("rg_game_time") is None:
                chosen = by_num.row(0, named=True)
            else:
                available = by_num

        if chosen is None and card.get("rg_game_time") is not None and available.height > 1:
            rg_ts = card["rg_game_time"]
            with_delta = available.with_columns(
                (pl.col("game_time") - pl.lit(rg_ts))
                .dt.total_seconds()
                .abs()
                .alias("_time_delta")
            ).sort("_time_delta")
            chosen = with_delta.row(0, named=True)
        elif chosen is None:
            chosen = available.row(0, named=True)

        used_game_pks.add(int(chosen["game_pk"]))
        assignments.append(
            {
                "slate_game_key": card["slate_game_key"],
                "game_pk": int(chosen["game_pk"]),
                "game_time": chosen["game_time"],
                "game_status": chosen["game_status"],
                "game_number": int(chosen.get("game_number") or 1),
                "double_header": chosen.get("double_header") or "N",
                "away_probable_pitcher_id": chosen.get("away_probable_pitcher_id"),
                "home_probable_pitcher_id": chosen.get("home_probable_pitcher_id"),
            }
        )

    if not assignments:
        raise ValueError(
            "Could not attach any RotoGrinders cards to the MLB schedule: "
            f"{unmatched}"
        )
    if unmatched:
        print(
            "Warning: skipped RotoGrinders cards with no MLB schedule match: "
            f"{unmatched}"
        )

    map_frame = pl.DataFrame(assignments)
    matched_keys = map_frame["slate_game_key"].to_list()
    starters = slate.starters.filter(
        pl.col("slate_game_key").is_in(matched_keys)
    ).join(map_frame, on="slate_game_key", how="left")
    lineups = slate.lineups.filter(
        pl.col("slate_game_key").is_in(matched_keys)
    ).join(map_frame, on="slate_game_key", how="left")

    starters = starters.with_columns(
        pl.when(pl.col("is_home"))
        .then(pl.col("home_probable_pitcher_id"))
        .otherwise(pl.col("away_probable_pitcher_id"))
        .alias("official_probable_pitcher_id")
    )
    return DailySlate(lineups=lineups, starters=starters)


def validate_daily_slate(
    slate: DailySlate,
    *,
    require_confirmed: bool = False,
    require_probable_match: bool = False,
) -> None:
    """Reject malformed, incomplete, duplicate, or unresolved daily rows.

    RotoGrinders vs MLB probable disagreements are common overnight / for early
    projections. Warn by default; pass ``require_probable_match=True`` to fail.
    """
    if slate.lineups.is_empty():
        raise ValueError("RotoGrinders returned no MLB batting-order rows")
    if slate.starters.is_empty():
        raise ValueError("RotoGrinders returned no MLB starting pitchers")

    invalid_orders = slate.lineups.filter(
        pl.col("batting_order").is_null()
        | ~pl.col("batting_order").is_between(1, 9)
    )
    if not invalid_orders.is_empty():
        raise ValueError("Daily lineup contains a missing/invalid batting-order slot")

    coverage = slate.lineups.group_by(["game_pk", "team_id"]).agg(
        pl.len().alias("rows"),
        pl.col("batting_order").n_unique().alias("spots"),
        pl.col("batter").n_unique().alias("batters"),
    )
    invalid_coverage = coverage.filter(
        (pl.col("rows") != 9)
        | (pl.col("spots") != 9)
        | (pl.col("batters") != 9)
    )
    if not invalid_coverage.is_empty():
        raise ValueError(
            "Daily lineup must contain nine unique resolved batters per team: "
            f"{invalid_coverage.to_dicts()}"
        )
    if slate.starters.filter(pl.col("pitcher").is_null()).height:
        raise ValueError("Daily slate contains an unresolved starting pitcher")
    starter_coverage = slate.starters.group_by(["game_pk", "team_id"]).agg(
        pl.len().alias("rows"),
        pl.col("pitcher").n_unique().alias("pitchers"),
    )
    if starter_coverage.filter(
        (pl.col("rows") != 1) | (pl.col("pitchers") != 1)
    ).height:
        raise ValueError("Daily slate must contain one resolved starter per team")
    probable_mismatch = slate.starters.filter(
        pl.col("official_probable_pitcher_id").is_not_null()
        & (pl.col("pitcher") != pl.col("official_probable_pitcher_id"))
    )
    if not probable_mismatch.is_empty():
        detail = probable_mismatch.select(
            "team", "player_name", "pitcher", "official_probable_pitcher_id"
        ).to_dicts()
        message = (
            "RotoGrinders starter disagrees with MLB probable pitcher: "
            f"{detail}"
        )
        if require_probable_match:
            raise ValueError(message)
        print(f"Warning: {message}")
    if require_confirmed and (
        slate.lineups.filter(pl.col("lineup_status") != "confirmed").height
        or slate.starters.filter(pl.col("lineup_status") != "confirmed").height
    ):
        raise ValueError("Daily slate still contains projected lineups")


def build_daily_slate(
    *,
    game_date: date | None = None,
    timeout: float = 30.0,
    require_confirmed: bool = False,
    require_probable_match: bool = False,
    aliases: Mapping[tuple[int, str], int] | None = None,
) -> DailySlate:
    """Fetch, resolve, validate, and return today's daily projection inputs."""
    game_date = game_date or datetime.now(ZoneInfo("America/New_York")).date()
    parsed = parse_rotogrinders_html(
        fetch_rotogrinders_html(timeout=timeout),
        game_date=game_date,
    )
    scheduled = attach_schedule(
        parsed,
        fetch_mlb_schedule(game_date, timeout=timeout),
    )
    team_ids = tuple(
        sorted(
            set(scheduled.lineups["team_id"].to_list())
            | set(scheduled.starters["team_id"].to_list())
        )
    )
    # Active first; widen to 40-man then full-season for IL / non-40 catchups
    # (e.g. Chadwick Tromp on BAL fullSeason only while still on RG cards).
    roster_frames: list[pl.DataFrame] = []
    lineups: pl.DataFrame | None = None
    starters: pl.DataFrame | None = None
    last_err: ValueError | None = None
    for roster_type in ("active", "40Man", "fullSeason"):
        batch = fetch_mlb_rosters(
            team_ids,
            game_date,
            roster_type=roster_type,
            timeout=timeout,
        )
        batch = enrich_rosters_for_matching(batch, timeout=timeout)
        roster_frames.append(batch)
        rosters = pl.concat(roster_frames).unique(subset=["team_id", "mlb_id"])
        try:
            lineups = resolve_player_ids(
                scheduled.lineups,
                rosters,
                output_column="batter",
                aliases=aliases,
                enrich=False,
                timeout=timeout,
            )
            starters = resolve_player_ids(
                scheduled.starters,
                rosters,
                output_column="pitcher",
                aliases=aliases,
                enrich=False,
                timeout=timeout,
            )
            last_err = None
            break
        except ValueError as exc:
            last_err = exc
            continue
    if lineups is None or starters is None:
        assert last_err is not None
        raise last_err

    resolved = DailySlate(lineups=lineups, starters=starters)
    validate_daily_slate(
        resolved,
        require_confirmed=require_confirmed,
        require_probable_match=require_probable_match,
    )
    return resolved


def write_daily_slate(
    slate: DailySlate,
    *,
    output_dir: Path = config.PROCESSED_DATA_DIR,
) -> tuple[Path, Path]:
    """Persist ID-resolved daily inputs as separate batter/pitcher parquets."""
    game_dates = slate.lineups["game_date"].unique().to_list()
    if len(game_dates) != 1:
        raise ValueError(f"Expected one slate date, found {game_dates}")
    stamp = game_dates[0].isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    lineup_path = output_dir / f"daily_lineups_{stamp}.parquet"
    starter_path = output_dir / f"daily_starters_{stamp}.parquet"
    slate.lineups.write_parquet(lineup_path)
    slate.starters.write_parquet(starter_path)
    return lineup_path, starter_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-confirmed",
        action="store_true",
        help="Fail until every RotoGrinders lineup is marked confirmed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.PROCESSED_DATA_DIR,
    )
    args = parser.parse_args()
    slate = build_daily_slate(require_confirmed=args.require_confirmed)
    lineup_path, starter_path = write_daily_slate(
        slate,
        output_dir=args.output_dir,
    )
    print(f"Wrote {slate.lineups.height} lineup rows to {lineup_path}")
    print(f"Wrote {slate.starters.height} starter rows to {starter_path}")


if __name__ == "__main__":
    main()
