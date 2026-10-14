"""Market-layer evaluation v1 - PREP (matched-contract table).

Registered spec: EXPERIMENT_CARD.md (this directory). This script builds the
matched-contract table and all derived fields ONLY:

  - frozen H3-raw / LOG5-raw projected-state K PMFs (pregame-state-v1 accepted
    projected-batter-state v2 payload)
  - timestamped The Odds API archive quotes (odds-coverage-v1 join lineage)
  - pre-cutoff actionable price per (start, line, book) + de-vig market probs
  - closing reference (CLV benchmark), reported separately, never mixed into
    the actionable set
  - registered paper-bet selection (fixed rule, one research rule)

NO outcome join. NO scoring run. NO fitting/calibration/policy search.
Outputs are write-once (a rerun into a populated prep dir fails loudly).

ASCII only (cp1252 console).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

# ---------------------------------------------------------------------------
# Registered constants (mirrored verbatim in EXPERIMENT_CARD.md)
# ---------------------------------------------------------------------------

K_MARKETS = ["pitcher_strikeouts", "pitcher_strikeouts_alternate"]

# Book priority for observation tie-breaks and "first qualifying book" paper
# bets. Order registered before execution; unknown books sort last
# (alphabetically among themselves).
BOOK_PRIORITY = [
    "draftkings",
    "fanduel",
    "betmgm",
    "williamhill_us",
    "betrivers",
    "bovada",
    "fanatics",
    "betonlineag",
    "mybookieag",
    "superbook",
    "pointsbetus",
    "barstool",
    "unibet_us",
]

MARGIN = 0.02              # paper-bet edge margin over break-even
STAKE_UNITS = 1.0          # flat stake per paper bet
VALID_PRICE_ABS_MAX = 100000  # drop vendor junk outside this American-odds bound
PMF_SUPPORT = 24           # payload K PMFs cover k = 0..23

TIER_A = "A_verified_clock"
TIER_B = "B_clock_proxy"

ET = ZoneInfo("America/New_York")


def predictor_available_ts(forecast_cutoff) -> datetime:
    """First UTC instant at which the frozen predictor payload for a start is
    available: 00:00 ET on the forecast_cutoff (scheduled game_date). Quotes
    earlier than this are reference-only, not actionable (C2 registered
    quote-time rule: prediction-information time <= selected quote time)."""
    d = forecast_cutoff
    return datetime(d.year, d.month, d.day, tzinfo=ET).astimezone(ZoneInfo("UTC"))

PREP_FILES = [
    "matched_contracts.parquet",
    "actionable_pairs.parquet",
    "closing_refs.parquet",
    "paper_bets.parquet",
    "prep_summary.json",
    "manifest.json",
]

# Read-only sources (frozen inputs; hashes recorded in manifest.json)
DEFAULT_BOOK_LINES = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet"
)
DEFAULT_ENVELOPE = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi\snapshot_envelope.parquet"
)
# Accepted projected-batter-state v2 payload (7,194 starts; per-PA probs
# H3-raw/LOG5-raw + count PMFs + BF PMFs). Referenced by pregame-state-v1 as
# the accepted v2 artifact; the file lives under pregame-pa-ext-v1.
DEFAULT_PAYLOAD = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\data\predictor_payload.parquet"
)
DEFAULT_ID_MAP = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\dimensions\player_id_map.parquet"
)
DEFAULT_OUT_DIR = Path(__file__).parent / "outputs" / "prep_v2"


class WriteOnceError(RuntimeError):
    """Raised when a prep run would overwrite existing outputs."""


class MissingColumnsError(ValueError):
    """Raised when an input frame lacks required columns (fail loud)."""


# ---------------------------------------------------------------------------
# Small pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def norm_name(value: object) -> str:
    """Mirror of canonical ``norm_player_name`` in src/Python/odds_ledger.py:
    NFKD-fold accents to ASCII, lowercase, keep [a-z ] only, strip."""
    ascii_s = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return re.sub(r"[^a-z ]", "", ascii_s.lower()).strip()


def sorted_name(value: object) -> str:
    """Token-sorted normalized name, the join-key convention used across
    production/ops/market_research scripts."""
    return " ".join(sorted(norm_name(value).split()))


def to_decimal(price: int) -> float:
    """American odds -> decimal odds. Validity: 1 <= |price| <= 100000.

    p > 0: decimal = 1 + p/100 (stake 100 to win p).
    p < 0: decimal = 1 + 100/|p| (stake |p| to win 100).
    """
    p = int(price)
    if p == 0 or abs(p) > VALID_PRICE_ABS_MAX:
        raise ValueError("invalid American price: %r" % price)
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / (-p))


def pmf_contract_probs(pmf: dict, line: float) -> tuple:
    """Contract probabilities from a frozen K PMF (support 0..PMF_SUPPORT-1).

    Half-line L (e.g. 5.5):  p_over = P(K >= ceil(L)), p_under = P(K <= floor(L)), push = 0.
    Integer line L:          push = P(K = L), p_over = P(K >= L+1), p_under = P(K <= L-1).
    Returns (p_over_win, p_under_win, p_push), clipped to [0, 1].
    """
    L = float(line)
    if L != L or L in (float("inf"), float("-inf")):
        raise ValueError("invalid line: %r" % line)
    if L < 0:
        raise ValueError("invalid line: %r" % line)

    def cdf(k: int) -> float:
        if k < 0:
            return 0.0
        return sum(pmf.get(i, 0.0) for i in range(0, min(k, PMF_SUPPORT - 1) + 1))

    if L.is_integer():
        li = int(L)
        p_push = cdf(li) - cdf(li - 1)
        p_over = 1.0 - cdf(li)
        p_under = cdf(li - 1)
    else:
        fl = math.floor(L)
        p_push = 0.0
        p_over = 1.0 - cdf(fl)
        p_under = cdf(fl)
    clip = lambda x: min(1.0, max(0.0, x))
    return clip(p_over), clip(p_under), clip(p_push)


def devig_proportional(decimal_over: float, decimal_under: float) -> tuple:
    """Proportional no-vig market probabilities from a paired contemporaneous
    over/under quote (same book, same snapshot).

    p_over_mkt = (1/d_over) / (1/d_over + 1/d_under); p_under_mkt = 1 - p_over_mkt.
    """
    if decimal_over <= 1.0 or decimal_under <= 1.0:
        raise ValueError("decimal odds must exceed 1.0")
    inv_o = 1.0 / decimal_over
    inv_u = 1.0 / decimal_under
    p_over = inv_o / (inv_o + inv_u)
    return p_over, 1.0 - p_over


def ev_per_unit(p_win: float, p_lose: float, p_push: float, decimal: float) -> float:
    """Expected PnL per 1-unit stake under refund (push) semantics:
    win -> +(d-1), lose -> -1, push -> 0."""
    if p_push < 0 or p_win < 0 or p_lose < 0:
        raise ValueError("probabilities must be non-negative")
    return p_win * (decimal - 1.0) - p_lose


def bet_qualifies(p_win: float, decimal: float, margin: float = MARGIN) -> bool:
    """Registered paper-bet rule: model p_win must exceed break-even + margin."""
    return bool(p_win > (1.0 / decimal) + margin)


def book_priority_index(book: str, priority: list = None) -> int:
    prio = BOOK_PRIORITY if priority is None else priority
    try:
        return prio.index(str(book))
    except ValueError:
        return len(prio)


def choose_observation_pair(rows: list, priority: list = None) -> dict:
    """Registered dedup rule: ONE observation per (start, line).

    Among paired (book, snapshot) candidates pick:
      1. max total decimal (d_over + d_under)  [best price on both sides]
      2. tie -> lowest book-priority index
      3. tie -> latest pair timestamp
    Each input row: dict with book, pair_ts, d_over, d_under.
    """
    if not rows:
        raise ValueError("no candidate pairs")
    prio = BOOK_PRIORITY if priority is None else priority

    def key(r):
        return (
            -(r["d_over"] + r["d_under"]),
            book_priority_index(r["book"], prio),
            "",
            r["book"],
        )

    best_total = min(-(r["d_over"] + r["d_under"]) for r in rows)
    tied = [r for r in rows if abs((r["d_over"] + r["d_under"]) + best_total) < 1e-12]
    best_prio = min(book_priority_index(r["book"], prio) for r in tied)
    tied = [r for r in tied if book_priority_index(r["book"], prio) == best_prio]
    return max(tied, key=lambda r: r["pair_ts"])


# ---------------------------------------------------------------------------
# Polars frame helpers
# ---------------------------------------------------------------------------


def require_columns(df: pl.DataFrame, cols: list, name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise MissingColumnsError(
            "%s missing required columns: %s (has: %s)"
            % (name, missing, list(df.columns))
        )


def _to_utc_expr(name: str, dtype) -> pl.Expr:
    if dtype == pl.String:
        return pl.col(name).str.to_datetime(time_zone="UTC", strict=False)
    if isinstance(dtype, pl.Datetime):
        if dtype.time_zone is not None:
            return pl.col(name).dt.convert_time_zone("UTC")
        return pl.col(name).dt.replace_time_zone("UTC")
    raise MissingColumnsError(
        "column '%s' has unsupported dtype %s" % (name, dtype)
    )


def decimal_expr(price_col: str) -> pl.Expr:
    return (
        pl.when(pl.col(price_col) > 0)
        .then(1.0 + pl.col(price_col) / 100.0)
        .otherwise(1.0 + 100.0 / (-pl.col(price_col)))
    )


def load_quotes(path: Path) -> tuple:
    """Load + validate the archive quotes for the K markets.

    Fixed tie rules (registered; C2 correction - deterministic):
      - drop quotes with |price| outside [1, VALID_PRICE_ABS_MAX] (count them)
      - duplicate (event, snapshot, book, market, player_norm, line, side)
        rows: keep the max price (bettor-best); price ties keep the FIRST
        file row (enforced via a file-row index, not sort stability)
      - market pooling: one row per (event, snapshot, book, player_norm,
        line, side) at the max price across pitcher_strikeouts / _alternate.
        C2: player_norm added to the pooling key - pooling is WITHIN a
        pitcher; the v1 key omitted it, which arbitrarily deleted one
        pitcher's quotes whenever two pitchers shared an
        (event, snapshot, book, line, side) key (750k+ such keys in the
        archive) and made the pipeline nondeterministic run to run.
    """
    q = pl.read_parquet(path)
    require_columns(
        q,
        ["event_id", "snapshot", "snapshot_ts", "game_date", "season_type",
         "book", "market", "player", "player_norm", "line", "side", "price"],
        "book_lines",
    )
    q = q.filter(
        pl.col("market").is_in(K_MARKETS) & (pl.col("season_type") == "regular")
    ).with_columns(
        pl.col("game_date").str.to_date().alias("vendor_game_date"),
        _to_utc_expr("snapshot_ts", q.schema["snapshot_ts"]).alias("quote_ts"),
    ).drop("game_date")
    n_market_rows = q.height
    valid = (
        (pl.col("price").abs() >= 1) & (pl.col("price").abs() <= VALID_PRICE_ABS_MAX)
    )
    q = q.filter(valid)
    n_price_dropped = n_market_rows - q.height
    n_null_ts = int(q["quote_ts"].is_null().sum())
    # Deterministic max-price dedup: (price ASC, file-row DESC) is a total
    # order, so keep="last" always selects (max price, first file row on ties)
    # regardless of parallel sort stability.
    q = q.with_row_index("_row")
    quote_key = ["event_id", "snapshot", "book", "market", "player_norm", "line", "side"]
    q = q.sort(["price", "_row"], descending=[False, True]).unique(
        subset=quote_key, keep="last", maintain_order=True
    )
    pooled_key = ["event_id", "snapshot", "book", "player_norm", "line", "side"]
    q = q.sort(["price", "_row"], descending=[False, True]).unique(
        subset=pooled_key, keep="last", maintain_order=True
    ).drop("_row")
    return q, {
        "k_market_rows": n_market_rows,
        "price_dropped": n_price_dropped,
        "null_quote_ts": n_null_ts,
    }


def build_event_map(quotes: pl.DataFrame) -> tuple:
    """event_id map + ambiguous (vendor_game_date, pitcher_key) keys."""
    em = quotes.select("event_id", "vendor_game_date", "player_norm").unique().with_columns(
        pl.col("player_norm")
        .map_elements(sorted_name, return_dtype=pl.String)
        .alias("pitcher_key")
    )
    dup_keys = (
        em.group_by("vendor_game_date", "pitcher_key")
        .agg(pl.col("event_id").n_unique().alias("n_events"))
        .filter(pl.col("n_events") > 1)
    )
    return em, dup_keys


def load_commence(envelope_path: Path) -> pl.DataFrame:
    """event_id -> earliest vendor commence_time (UTC), the scheduled-first-
    pitch proxy for Tier A (verified-clock) rows."""
    env = pl.read_parquet(envelope_path)
    require_columns(env, ["event_id", "commence_time"], "envelope")
    return (
        env.with_columns(
            _to_utc_expr("commence_time", env.schema["commence_time"]).alias("ts")
        )
        .group_by("event_id")
        .agg(pl.col("ts").min().alias("first_pitch_ts"))
    )


def load_payload(path: Path) -> pl.DataFrame:
    p = pl.read_parquet(path)
    pmf_cols = (
        ["pmf_h3_raw_%d" % i for i in range(PMF_SUPPORT)]
        + ["pmf_l5_raw_%d" % i for i in range(PMF_SUPPORT)]
    )
    require_columns(
        p,
        ["game_pk", "pitcher", "game_date", "block", "side"] + pmf_cols,
        "predictor payload",
    )
    return p.select(
        "game_pk", "pitcher", "game_date", "block",
        pl.col("side").alias("pitch_half"),
        "forecast_cutoff",
        *pmf_cols,
    )


def match_starts(payload: pl.DataFrame, event_map: pl.DataFrame,
                 dup_keys: pl.DataFrame, id_map_path: Path) -> dict:
    """Identity resolution + fixed exclusion rules.

    Exclusion 1 (62-class): pitcher MLBAM id unresolved in player_id_map
    (no name key) -> excluded, counted.
    Exclusion 2 (54-class): the archive (vendor_game_date, pitcher_key) maps
    to 2+ events (doubleheaders/reschedules). The envelope carries no
    game_pk and the payload carries no team labels, so no event_id maps
    unambiguously to one game_pk -> excluded, counted.
    Date tolerance: vendor game_date is UTC while the payload game_date is
    local (ET) -> match pitcher name with dates within +/-1 day, closest
    first, deterministic by (date_dist, event_id).
    """
    id_map = pl.read_parquet(id_map_path).select(
        pl.col("mlb_id").alias("pitcher"),
        pl.col("player_name")
        .map_elements(sorted_name, return_dtype=pl.String)
        .alias("pitcher_key"),
    )
    starts = payload.select(
        "game_pk", "pitcher", "game_date", "block", "pitch_half", "forecast_cutoff"
    ).unique()
    s = starts.join(id_map, on="pitcher", how="left")
    unresolved = s.filter(pl.col("pitcher_key").is_null())
    s_res = s.filter(pl.col("pitcher_key").is_not_null())

    ev = event_map.select("event_id", "vendor_game_date", "pitcher_key")
    matched = (
        s_res.join(ev, on="pitcher_key", how="inner")
        .with_columns(
            (pl.col("vendor_game_date") - pl.col("game_date"))
            .dt.total_days()
            .abs()
            .alias("date_dist")
        )
        .filter(pl.col("date_dist") <= 1)
        # C2: full-column sort + maintain_order unique -> deterministic
        # candidate choice even when the archive carries duplicate
        # (event_id, pitcher_key) rows at different vendor_game_dates (the
        # UTC-midnight flip) or several events tie on date_dist.
        .sort(["game_pk", "pitcher", "date_dist", "event_id", "vendor_game_date"])
        .unique(subset=["game_pk", "pitcher"], keep="first", maintain_order=True)
    )
    matched = (
        matched.join(dup_keys, on=["vendor_game_date", "pitcher_key"], how="left")
        .with_columns(pl.col("n_events").is_not_null().alias("is_ambiguous"))
    )
    ambiguous = matched.filter(pl.col("is_ambiguous"))
    eligible = matched.filter(~pl.col("is_ambiguous"))
    return {
        "eligible": eligible,
        "unresolved_ids": unresolved.select("game_pk", "pitcher"),
        "ambiguous_starts": ambiguous.select("game_pk", "pitcher", "vendor_game_date", "pitcher_key", "n_events"),
    }


def attach_quotes(quotes: pl.DataFrame, eligible_starts: pl.DataFrame,
                  event_map: pl.DataFrame) -> pl.DataFrame:
    """Attach matched starts to pooled quotes on (event_id, pitcher_key)."""
    em_key = event_map.select("event_id", "player_norm", "pitcher_key")
    q = quotes.join(em_key, on=["event_id", "player_norm"], how="inner")
    keys = eligible_starts.select(
        "game_pk", "pitcher", "pitcher_key", "game_date", "block", "pitch_half",
        "event_id", "vendor_game_date", "first_pitch_ts", "tier",
        "predictor_available_ts",
    )
    return q.join(keys, on=["event_id", "pitcher_key"], how="inner")


def closing_eligible(joined: pl.DataFrame) -> pl.DataFrame:
    """Quotes eligible to be the closing reference (benchmark/CLV only):

    Tier A (verified clock): every quote strictly before first_pitch_ts; the
    latest of these per (book, line, side) IS the closing reference (the
    last quote before the vendor commence).
    Tier B (clock proxy): the `close`-clock snapshot (pregame by the
    acceptance-audit timing contract).
    """
    return joined.filter(
        (
            (pl.col("tier") == TIER_A)
            & (pl.col("quote_ts") < pl.col("first_pitch_ts"))
        )
        | ((pl.col("tier") == TIER_B) & (pl.col("snapshot") == "close"))
    )


def split_actionable_closing(joined: pl.DataFrame) -> tuple:
    """Split quotes into the actionable set and the closing reference.

    Registered timing contract (C2: predictor-availability floor added):
      closing_ref(book, line, side) = latest quote in closing_eligible set
      (closing refs are benchmark/CLV-only; predating quotes stay eligible
      there because reference-only rows may serve as benchmarks).
      actionable = pre-cutoff, predictor-aware quotes MINUS the
      closing-reference row itself:
        tier A: first_pitch_ts > quote_ts >= predictor_available_ts AND
                (no closing ref OR quote_ts < closing_ref_ts)
        tier B: snapshot != 'close' AND quote_ts >= predictor_available_ts
      The predictor-availability floor enforces the C2 quote-time rule:
      prediction-information time <= selected quote time; earlier quotes are
      reference-only, not actionable.
    Returns (actionable, closing_side_refs, closing_eligible_set).
    """
    pre = closing_eligible(joined)
    if pre.height == 0:
        empty_side = joined.clear().select(
            "game_pk", "pitcher", "line", "book", "side",
            pl.lit(None, dtype=joined.schema["quote_ts"]).alias("quote_ts"),
            pl.lit(None, dtype=joined.schema["price"]).alias("price"),
            "tier",
        )
        return pre, empty_side, pre
    closing_side = latest_per_side(pre)
    keys = ["game_pk", "pitcher", "line", "book", "side"]
    clo_ts = closing_side.select(
        keys + [pl.col("quote_ts").alias("closing_ts")]
    )
    act = (
        joined.join(clo_ts, on=keys, how="left")
        .filter(
            (
                (pl.col("tier") == TIER_A)
                & (pl.col("quote_ts") < pl.col("first_pitch_ts"))
                & (pl.col("quote_ts") >= pl.col("predictor_available_ts"))
                & (
                    pl.col("closing_ts").is_null()
                    | (pl.col("quote_ts") < pl.col("closing_ts"))
                )
            )
            | (
                (pl.col("tier") == TIER_B)
                & (pl.col("snapshot") != "close")
                & (pl.col("quote_ts") >= pl.col("predictor_available_ts"))
            )
        )
        .drop("closing_ts")
    )
    return act, closing_side, pre


def latest_per_side(quotes: pl.DataFrame) -> pl.DataFrame:
    """Latest quote per (start, line, book, side) within the given set."""
    if quotes.height == 0:
        return quotes
    # C2: the archive can carry several snapshot labels at ONE quote_ts;
    # drop exact-duplicate rows so the max-ts semi join cannot fan out.
    quotes = quotes.unique(keep="first", maintain_order=True)
    keys = ["game_pk", "pitcher", "line", "book", "side"]
    latest_ts = quotes.group_by(keys).agg(pl.col("quote_ts").max().alias("quote_ts"))
    return quotes.join(latest_ts, on=keys + ["quote_ts"], how="semi")


def pair_sides(quotes: pl.DataFrame) -> pl.DataFrame:
    """Pair contemporaneous over/under prices (same book, same snapshot ts).

    Registered pairing rule: per (start, line, book) the pair timestamp is
    the LATEST clock in the given set at which the book quotes BOTH sides;
    books without a both-sides clock contribute no pair. De-vig uses the
    paired prices (proportional method).
    """
    if quotes.height == 0:
        return quotes
    keys = ["game_pk", "pitcher", "line", "book"]
    both = (
        quotes.group_by(keys + ["quote_ts"])
        .agg(pl.col("side").n_unique().alias("n_sides"))
        .filter(pl.col("n_sides") == 2)
    )
    if both.height == 0:
        return both
    pair_ts = both.group_by(keys).agg(pl.col("quote_ts").max().alias("pair_ts"))
    at_pair = (
        quotes.join(pair_ts, on=keys, how="inner")
        .filter(pl.col("quote_ts") == pl.col("pair_ts"))
    )
    ov = (
        at_pair.filter(pl.col("side") == "over")
        .drop("side", "snapshot", "quote_ts", "market")
        .rename({"price": "price_over"})
        .with_columns(decimal_expr("price_over").alias("d_over"))
    )
    un = (
        at_pair.filter(pl.col("side") == "under")
        .select(keys + ["price"])
        .rename({"price": "price_under"})
        .with_columns(decimal_expr("price_under").alias("d_under"))
    )
    paired = ov.join(un, on=keys, how="inner")
    # C2: same-ts multi-label rows can duplicate the pair row; collapse them
    if paired.height:
        paired = paired.unique(keep="first", maintain_order=True)
    if paired.height == 0:
        return paired
    inv_o = 1.0 / pl.col("d_over")
    inv_u = 1.0 / pl.col("d_under")
    return paired.with_columns(
        (inv_o / (inv_o + inv_u)).alias("p_over_mkt"),
        (inv_u / (inv_o + inv_u)).alias("p_under_mkt"),
    )


def choose_eval_pairs(paired: pl.DataFrame) -> pl.DataFrame:
    """Registered observation selection: ONE pair per (start, line) by
    max total decimal, then book priority, then latest ts."""
    if paired.height == 0:
        return paired
    prio_map = {b: i for i, b in enumerate(BOOK_PRIORITY)}
    ranked = paired.with_columns(
        pl.col("book")
        .replace_strict(prio_map, default=len(BOOK_PRIORITY), return_dtype=pl.Int64)
        .alias("_prio")
    ).with_columns(
        (pl.col("d_over") + pl.col("d_under")).alias("_total_dec")
    ).sort(
        ["_total_dec", "_prio", "pair_ts"], descending=[True, False, True]
    )
    return ranked.unique(subset=["game_pk", "pitcher", "line"], keep="first",
                         maintain_order=True).drop(
        "_prio", "_total_dec"
    )


def build_prob_table(payload: pl.DataFrame, lines: list) -> pl.DataFrame:
    """Contract probabilities per (start, line) from the frozen PMFs.

    For each registered line L:
      p_over  = P(K >= ceil(L))          (half)   /  P(K >= L+1)   (integer)
      p_under = P(K <= floor(L))         (half)   /  P(K <= L-1)   (integer)
      p_push  = 0                        (half)   /  P(K = L)      (integer)
    Both frozen arms: pmf_h3_raw_* (H3-raw) and pmf_l5_raw_* (LOG5-raw).
    """
    frames = []
    for L in sorted(set(float(x) for x in lines)):
        exprs = []
        for model, pre in (("h3", "pmf_h3_raw_"), ("l5", "pmf_l5_raw_")):
            def cdf(k: int) -> pl.Expr:
                ks = range(0, min(k, PMF_SUPPORT - 1) + 1)
                return pl.sum_horizontal([pl.col(pre + str(i)) for i in ks])

            if float(L).is_integer():
                li = int(L)
                push = (cdf(li) - cdf(li - 1)).clip(0.0, 1.0) if li >= 1 else pl.lit(0.0)
                over = (1.0 - cdf(li)).clip(0.0, 1.0)
                under = cdf(li - 1).clip(0.0, 1.0) if li >= 1 else pl.lit(0.0)
            else:
                fl = math.floor(L)
                push = pl.lit(0.0)
                over = (1.0 - cdf(fl)).clip(0.0, 1.0)
                under = cdf(fl).clip(0.0, 1.0)
            exprs += [
                over.alias("p_%s_over" % model),
                under.alias("p_%s_under" % model),
                push.alias("p_%s_push" % model),
            ]
        frames.append(
            payload.select("game_pk", "pitcher", *exprs).with_columns(
                pl.lit(L).alias("line")
            )
        )
    return pl.concat(frames, how="vertical")


def build_matched_contracts(eval_pairs: pl.DataFrame, probs: pl.DataFrame) -> pl.DataFrame:
    """One row per (start, line, side) with model probabilities, de-vig market
    probabilities, offered-price break-even, and expected payout as separate
    named fields."""
    base_cols = [
        "game_pk", "pitcher", "pitcher_key", "game_date", "block", "pitch_half",
        "tier", "first_pitch_ts", "line", "book", "pair_ts",
        "price_over", "price_under", "d_over", "d_under",
        "p_over_mkt", "p_under_mkt", "event_id",
    ]
    base = eval_pairs.select(base_cols).join(
        probs, on=["game_pk", "pitcher", "line"], how="inner"
    )
    sides = []
    for side, p_col, q_col in (
        ("over", "p_h3_over", "p_h3_under"),
        ("under", "p_h3_under", "p_h3_over"),
    ):
        d = "d_over" if side == "over" else "d_under"
        price = "price_over" if side == "over" else "price_under"
        mkt = "p_over_mkt" if side == "over" else "p_under_mkt"
        sides.append(
            base.select(
                [c for c in base_cols if c not in ("price_over", "price_under", "d_over", "d_under")]
                + [
                    pl.lit(side).alias("side"),
                    pl.col(price).alias("price"),
                    pl.col(d).alias("decimal_odds"),
                    pl.col(p_col).alias("p_h3_win"),
                    pl.col(q_col).alias("p_h3_lose"),
                    pl.col("p_h3_push"),
                    pl.col("p_l5_over" if side == "over" else "p_l5_under").alias("p_l5_win"),
                    pl.col("p_l5_under" if side == "over" else "p_l5_over").alias("p_l5_lose"),
                    pl.col("p_l5_push"),
                    pl.col(mkt).alias("p_market"),
                ]
            )
            .with_columns(
                (1.0 / pl.col("decimal_odds")).alias("break_even"),
                (
                    pl.col("p_h3_win") * (pl.col("decimal_odds") - 1.0)
                    - pl.col("p_h3_lose")
                ).alias("ev_h3"),
                (
                    pl.col("p_l5_win") * (pl.col("decimal_odds") - 1.0)
                    - pl.col("p_l5_lose")
                ).alias("ev_l5"),
            )
        )
    return pl.concat(sides, how="vertical")


def build_paper_bets(eval_pairs: pl.DataFrame, probs: pl.DataFrame,
                     closing_side_refs: pl.DataFrame) -> pl.DataFrame:
    """Registered paper-bet rule (fixed, no optimization):

    Bet a side when model p_win (H3-raw) > break-even + 0.02, 1 unit flat,
    at the FIRST qualifying book by BOOK_PRIORITY among paired actionable
    quotes. Over and under are independent bets. Closing reference for CLV =
    the bet book's own closing side price (may be missing; disclosed).
    """
    if eval_pairs.height == 0:
        return eval_pairs.clear()
    base_cols = [
        "game_pk", "pitcher", "pitcher_key", "game_date", "block", "tier",
        "first_pitch_ts", "line", "event_id",
    ]
    cand = eval_pairs.join(probs, on=["game_pk", "pitcher", "line"], how="inner")
    prio_map = {b: i for i, b in enumerate(BOOK_PRIORITY)}
    rows = []
    for side in ("over", "under"):
        d = "d_over" if side == "over" else "d_under"
        price = "price_over" if side == "over" else "price_under"
        p_win = "p_h3_over" if side == "over" else "p_h3_under"
        rows.append(
            cand.select(
                base_cols
                + [
                    pl.lit(side).alias("side"),
                    pl.col("book"),
                    pl.col("pair_ts").alias("quote_ts"),
                    pl.col(price).alias("price"),
                    pl.col(d).alias("decimal_odds"),
                    pl.col(p_win).alias("p_h3_win"),
                    pl.col("book")
                    .replace_strict(prio_map, default=len(BOOK_PRIORITY), return_dtype=pl.Int64)
                    .alias("_prio"),
                ]
            )
            .with_columns((1.0 / pl.col("decimal_odds")).alias("break_even"))
            .with_columns(
                (
                    pl.col("p_h3_win")
                    > pl.col("break_even") + pl.lit(MARGIN)
                ).alias("_qual")
            )
            .filter(pl.col("_qual"))
        )
    cands = pl.concat(rows, how="vertical")
    if cands.height == 0:
        return cands.drop(["_prio", "_qual"])
    bets = (
        cands.sort(["game_pk", "pitcher", "line", "side", "_prio", "book"])
        .unique(subset=["game_pk", "pitcher", "line", "side"], keep="first",
                maintain_order=True)
        .drop("_prio", "_qual")
        .with_columns(pl.lit(STAKE_UNITS).alias("stake_units"))
        .with_columns(
            (
                pl.col("p_h3_win") * (pl.col("decimal_odds") - 1.0)
                - (1.0 - pl.col("p_h3_win"))
            ).alias("ev_h3")
        )
        .join(
            closing_side_refs.select(
                ["game_pk", "pitcher", "line", "book", "side", "quote_ts", "price"]
            ).rename(
                {"quote_ts": "close_quote_ts", "price": "close_price"}
            ),
            on=["game_pk", "pitcher", "line", "book", "side"],
            how="left",
        )
        .with_columns(
            pl.when(pl.col("close_price").is_not_null())
            .then(
                (
                    pl.col("decimal_odds") - decimal_expr("close_price")
                )
                / decimal_expr("close_price")
            )
            .otherwise(None)
            .alias("clv_pct")
        )
    )
    return bets


def per_start_coverage(eligible_starts: pl.DataFrame, actionable: pl.DataFrame,
                       closing_side_refs: pl.DataFrame,
                       closing_eligible_set: pl.DataFrame) -> pl.DataFrame:
    """Coverage flags per eligible start (tier-specific definitions).

    has_precutoff_quote : >=1 actionable (pre-cutoff, non-closing) quote
    has_any_precutoff   : >=1 pre-cutoff quote even if it is the closing ref
    has_closing_ref     : a closing-reference quote exists
    """
    act = actionable.select("game_pk", "pitcher").unique().with_columns(
        pl.lit(True).alias("has_precutoff_quote")
    )
    any_pre = closing_eligible_set.select("game_pk", "pitcher").unique().with_columns(
        pl.lit(True).alias("has_any_precutoff")
    )
    clo = closing_side_refs.select("game_pk", "pitcher").unique().with_columns(
        pl.lit(True).alias("has_closing_ref")
    )
    return (
        eligible_starts.select("game_pk", "pitcher", "tier")
        .join(act, on=["game_pk", "pitcher"], how="left")
        .join(any_pre, on=["game_pk", "pitcher"], how="left")
        .join(clo, on=["game_pk", "pitcher"], how="left")
        .with_columns(
            pl.col("has_precutoff_quote").fill_null(False),
            pl.col("has_any_precutoff").fill_null(False),
            pl.col("has_closing_ref").fill_null(False),
        )
    )


def coverage_counts(cov: pl.DataFrame) -> dict:
    n = cov.height
    return {
        "eligible_starts": n,
        "with_precutoff_quote": int(cov["has_precutoff_quote"].sum()),
        "with_any_precutoff_quote": int(cov["has_any_precutoff"].sum()),
        "with_closing_ref": int(cov["has_closing_ref"].sum()),
        "with_both": int(
            (cov["has_precutoff_quote"] & cov["has_closing_ref"]).sum()
        ),
    }


# ---------------------------------------------------------------------------
# Prep run
# ---------------------------------------------------------------------------


def run_prep(book_lines: Path, envelope: Path, payload_path: Path,
             id_map: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    existing = [f for f in PREP_FILES if (out_dir / f).exists()]
    if existing:
        raise WriteOnceError(
            "write-once violation: %s already contains %s "
            "(prep outputs are immutable; use a new directory)"
            % (out_dir, ", ".join(existing))
        )

    summary = {
        "spec": "market-eval-v1 prep (EXPERIMENT_CARD.md)",
        "registered_constants": {
            "markets": K_MARKETS,
            "book_priority": BOOK_PRIORITY,
            "paper_bet_rule": "bet side when H3-raw p_win > break_even + %.2f, "
                              "1 unit, first qualifying book by priority" % MARGIN,
            "margin": MARGIN,
            "stake_units": STAKE_UNITS,
            "devig": "proportional, paired same-book same-snapshot over/under",
            "observation_dedup": "one pair per (start, line): max total decimal, "
                                 "then book priority, then latest ts",
            "pmf_support": PMF_SUPPORT,
            "bootstrap_registered_only": {
                "n_resamples": 2000, "seed": 20261001, "unit": "slate date (game_date)",
            },
        },
        "inputs": {},
        "identity": {},
        "coverage": {},
        "contracts": {},
        "paper_bets": {},
    }

    # --- load inputs -------------------------------------------------------
    quotes, quote_meta = load_quotes(book_lines)
    summary["inputs"]["book_lines"] = str(book_lines)
    summary["inputs"]["book_lines_meta"] = quote_meta

    payload = load_payload(payload_path)
    summary["inputs"]["payload"] = str(payload_path)
    summary["identity"]["starts_total"] = payload.height

    event_map, dup_keys = build_event_map(quotes)
    summary["identity"]["ambiguous_archive_keys"] = dup_keys.height

    # --- identity resolution ----------------------------------------------
    resolved = match_starts(payload, event_map, dup_keys, id_map)
    eligible = resolved["eligible"]
    commence = load_commence(envelope)
    eligible = eligible.join(commence, on="event_id", how="left").with_columns(
        pl.col("first_pitch_ts").is_not_null().alias("has_commence"),
    ).with_columns(
        pl.when(pl.col("has_commence"))
        .then(pl.lit(TIER_A))
        .otherwise(pl.lit(TIER_B))
        .alias("tier")
    ).with_columns(
        pl.col("forecast_cutoff")
        .map_elements(predictor_available_ts, return_dtype=pl.Datetime("us", "UTC"))
        .alias("predictor_available_ts")
    )
    summary["identity"]["unresolved_ids_excluded"] = resolved["unresolved_ids"].height
    summary["identity"]["doubleheader_ambiguous_excluded"] = resolved["ambiguous_starts"].height
    summary["identity"]["eligible_starts"] = eligible.height
    tier_counts = (
        eligible.group_by("tier").agg(pl.len().alias("starts")).sort("tier")
    )
    summary["identity"]["eligible_by_tier"] = {
        r["tier"]: int(r["starts"]) for r in tier_counts.iter_rows(named=True)
    }

    # --- quotes -> actionable / closing ------------------------------------
    joined = attach_quotes(quotes, eligible, event_map)
    act, closing_side_refs, pre = split_actionable_closing(joined)

    # paired actionable quotes (one per start/line/book at the latest
    # both-sides actionable clock), then the registered one-observation rule
    paired_all = pair_sides(act)
    eval_pairs = choose_eval_pairs(paired_all)
    summary["contracts"]["paired_book_lines"] = paired_all.height
    summary["contracts"]["eval_pairs_one_per_start_line"] = eval_pairs.height

    # closing refs: paired de-vig benchmark (tier A = last pre-commence pair;
    # tier B = close clock) + single-side refs for CLV
    closing_refs = pair_sides(pre)
    summary["contracts"]["closing_paired_refs"] = closing_refs.height

    # --- contract probabilities from frozen PMFs ---------------------------
    if eval_pairs.height:
        lines = eval_pairs["line"].unique().to_list()
        probs = build_prob_table(payload, lines)
    else:
        probs = pl.DataFrame()
    matched = build_matched_contracts(eval_pairs, probs) if eval_pairs.height else eval_pairs

    # --- paper bets ---------------------------------------------------------
    bets = build_paper_bets(eval_pairs, probs, closing_side_refs) if eval_pairs.height else eval_pairs

    # --- coverage recalculation after exclusions ----------------------------
    cov = per_start_coverage(eligible, act, closing_side_refs, pre)
    tier_a_cov = cov.filter(pl.col("tier") == TIER_A)
    tier_b_cov = cov.filter(pl.col("tier") == TIER_B)
    summary["coverage"]["after_exclusions_tier_A"] = coverage_counts(tier_a_cov)
    summary["coverage"]["after_exclusions_tier_B"] = coverage_counts(tier_b_cov)
    summary["coverage"]["after_exclusions_all"] = coverage_counts(cov)

    if matched.height:
        summary["contracts"]["contract_side_rows"] = matched.height
        summary["contracts"]["distinct_lines"] = int(matched["line"].n_unique())
        summary["contracts"]["starts_with_contracts"] = int(
            matched.select("game_pk", "pitcher").n_unique()
        )
        by_tier = matched.group_by("tier").agg(pl.len().alias("rows")).sort("tier")
        summary["contracts"]["rows_by_tier"] = {
            r["tier"]: int(r["rows"]) for r in by_tier.iter_rows(named=True)
        }
        half = matched.filter((pl.col("line") % 1.0) != 0.0)
        summary["contracts"]["half_line_rows"] = int(half.height)
        summary["contracts"]["integer_line_rows"] = int(matched.height - half.height)
        summary["contracts"]["integer_push_expected_nonzero"] = int(
            matched.filter((pl.col("line") % 1.0) == 0.0)
            .filter((pl.col("p_h3_push") > 0.0) | (pl.col("p_l5_push") > 0.0))
            .height
        )

    if bets.height:
        summary["paper_bets"]["bets"] = bets.height
        summary["paper_bets"]["with_closing_ref"] = int(bets["close_price"].is_not_null().sum())
        summary["paper_bets"]["missing_closing_ref"] = int(bets["close_price"].is_null().sum())
        by_side = bets.group_by("side").agg(pl.len().alias("bets")).sort("side")
        summary["paper_bets"]["bets_by_side"] = {
            r["side"]: int(r["bets"]) for r in by_side.iter_rows(named=True)
        }
        by_tier = bets.group_by("tier").agg(pl.len().alias("bets")).sort("tier")
        summary["paper_bets"]["bets_by_tier"] = {
            r["tier"]: int(r["bets"]) for r in by_tier.iter_rows(named=True)
        }
    else:
        summary["paper_bets"]["bets"] = 0

    # --- write-once outputs --------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    matched.write_parquet(out_dir / "matched_contracts.parquet")
    if paired_all.height:
        keys = ["game_pk", "pitcher", "line", "book"]
        paired_out = paired_all.join(
            eval_pairs.select(keys).with_columns(
                pl.lit(True).alias("chosen_for_eval")
            ),
            on=keys, how="left",
        ).with_columns(pl.col("chosen_for_eval").fill_null(False))
    else:
        paired_out = paired_all
    paired_out.write_parquet(out_dir / "actionable_pairs.parquet")
    closing_refs.write_parquet(out_dir / "closing_refs.parquet")
    bets.write_parquet(out_dir / "paper_bets.parquet")

    # --- manifest + summary --------------------------------------------------
    manifest = {
        "inputs_sha256_16": {
            "book_lines_pitcher.parquet": sha256_16(book_lines),
            "snapshot_envelope.parquet": sha256_16(envelope),
            "predictor_payload.parquet": sha256_16(payload_path),
            "player_id_map.parquet": sha256_16(id_map),
        },
        "outputs_sha256_16": {
            f: sha256_16(out_dir / f)
            for f in PREP_FILES
            if f.endswith(".parquet")
        },
        "registered_constants": summary["registered_constants"],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (out_dir / "prep_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    manifest["outputs_sha256_16"]["manifest.json"] = None
    return summary


# ---------------------------------------------------------------------------
# Scoring run (IMPLEMENTED under correction C2; EXECUTION still gated on
# owner approval - no outcome join has been run against the frozen prep)
# ---------------------------------------------------------------------------

DEFAULT_START_METRICS = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet"
)
DEFAULT_SCORE_DIR = Path(__file__).parent / "outputs" / "score_v2"

SCORE_FILES = [
    "bets_ledger.parquet",
    "clv_table.parquet",
    "skill_metrics.json",
    "bootstrap.json",
    "score_summary.json",
    "score_manifest.json",
]

LOG_FLOOR = 1e-12

# Persisted count-layer error columns in start_metrics_v2 (REUSED, not
# recomputed; produced by bf-workload-v1 run_kcount_correction_v2 against the
# same frozen PMFs and realized K).
PERSISTED_COUNT_COLS = [
    "rps", "logscore", "rmse_mean_k",
    "brier_ge6", "brier_ge8", "brier_ge10", "brier_ge12",
]


class ScoreReadError(RuntimeError):
    """Raised when scoring inputs are missing or fail verification."""


def settle_result(line: float, side: str, realized_k: int) -> str:
    """Registered settlement: half line L -> over wins at K >= ceil(L),
    under wins at K <= floor(L); integer line L -> push at K == L (stake
    refunded), over wins at K >= L+1, under wins at K <= L-1."""
    L = float(line)
    if side not in ("over", "under"):
        raise ValueError("invalid side: %r" % side)
    if realized_k is None or realized_k < 0:
        raise ValueError("realized K must be a non-negative integer")
    if L.is_integer():
        li = int(L)
        if realized_k == li:
            return "push"
        over_wins = realized_k >= li + 1
    else:
        import math as _math
        over_wins = realized_k >= _math.ceil(L)
    if side == "over":
        return "win" if over_wins else "lose"
    return "lose" if over_wins else "win"


def payout_units(result: str, decimal_odds: float,
                 stake: float = STAKE_UNITS) -> float:
    """PnL in units: win -> +stake*(d-1); lose -> -stake; push -> 0."""
    if result == "win":
        return stake * (decimal_odds - 1.0)
    if result == "lose":
        return -stake
    if result == "push":
        return 0.0
    raise ValueError("invalid result: %r" % result)


def mc_brier_row(p_win: float, p_push: float, p_lose: float,
                 y_win: int, y_push: int, y_lose: int) -> float:
    """Multi-class Brier contribution of one contract-side row:
    sum_c (p_c - y_c)^2 over classes {win, push, lose}."""
    return ((p_win - y_win) ** 2 + (p_push - y_push) ** 2
            + (p_lose - y_lose) ** 2)


def _side_probs(df: pl.DataFrame, arm: str) -> tuple:
    """Per-row (p_win, p_push, p_lose) for an arm at the row's own side."""
    if arm == "market":
        return (
            pl.when(pl.col("side") == "over").then(pl.col("p_over_mkt"))
            .otherwise(pl.col("p_under_mkt")),
            pl.lit(0.0),
            pl.when(pl.col("side") == "over").then(pl.col("p_under_mkt"))
            .otherwise(pl.col("p_over_mkt")),
        )
    return (
        pl.col("p_%s_win" % arm), pl.col("p_%s_push" % arm),
        pl.col("p_%s_lose" % arm),
    )


def _brier_logloss(df: pl.DataFrame, arm: str) -> dict:
    """Brier (all rows) + binary log loss (non-push rows) for one arm."""
    pw, pp, pl_ = _side_probs(df, arm)
    d = df.with_columns(
        pw.alias("_pw"), pp.alias("_pp"), pl_.alias("_pl"),
        pl.when(pl.col("side") == "over")
        .then(pl.col("y_over_win")).otherwise(pl.col("y_under_win"))
        .alias("_y_win"),
        pl.col("y_push").alias("_y_push"),
        pl.when(pl.col("side") == "over")
        .then(pl.col("y_under_win")).otherwise(pl.col("y_over_win"))
        .alias("_y_lose"),
    )
    b = d.select(
        (
            (pl.col("_pw") - pl.col("_y_win")) ** 2
            + (pl.col("_pp") - pl.col("_y_push")) ** 2
            + (pl.col("_pl") - pl.col("_y_lose")) ** 2
        ).alias("_b")
    )["_b"].mean()
    npush = d.filter(pl.col("_y_push") == 0)
    ll = npush.select(
        (
            -(pl.col("_y_win") * pl.col("_pw").clip(LOG_FLOOR, 1.0).log()
              + (1 - pl.col("_y_win"))
              * (1.0 - pl.col("_pw")).clip(LOG_FLOOR, 1.0).log())
        ).alias("_ll")
    )["_ll"].mean()
    return {"brier": float(b), "log_loss_non_push": float(ll)}


def _outcome_frame(matched: pl.DataFrame) -> pl.DataFrame:
    """Add realized outcome one-hot columns to the matched contracts."""
    L = pl.col("line")
    K = pl.col("realized_k")
    is_int = (L % 1.0) == 0.0
    over_win = (
        pl.when(is_int).then(K >= L + 1.0).otherwise(K >= pl.col("line").ceil())
    )
    push = pl.when(is_int).then(K == L).otherwise(pl.lit(False))
    return matched.with_columns(
        over_win.cast(pl.Int8).alias("y_over_win"),
        push.cast(pl.Int8).alias("y_push"),
        (pl.lit(1) - over_win.cast(pl.Int8) - push.cast(pl.Int8))
        .alias("y_under_win"),
    )


def _slate_bootstrap(values: dict, dates: list, blocks: list, n_boot: int,
                     seed: int) -> dict:
    """Paired slate-date bootstrap, BLOCK-STRATIFIED (C3 repair, matching
    run_paired_uncertainty.py).

    Defect fixed: the original pooled bootstrap drew n_dates dates from ONE
    unstratified pool, so a replicate could draw arbitrary date counts per
    development block AND divided per-date sums by the date count, which is
    not on the per-row scale of the point estimate when dates carry unequal
    row counts. Repair: within each block the replicate draws exactly that
    block's original slate-date count of dates (with replacement), then
    blocks are combined ROW-WEIGHTED (numerator = sum of the per-row metric
    over sampled-date rows, denominator = count of sampled rows) so every
    replicate is on the same scale as the point estimate and block weights
    cannot shift.

    Resampling unit = slate date (game_date); ONE draw of date indices per
    block per resample is shared across ALL competitors (identical resample
    indices). values: name -> per-row metric array aligned with `dates` and
    `blocks` (per-row slate + development block).
    Returns percentiles per name plus pairwise diffs named 'a_minus_b'.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    names = list(values)
    mat = np.vstack([np.asarray(values[n], dtype=np.float64) for n in names])
    blocks_arr = np.asarray(blocks, dtype=object)
    num = np.zeros((n_boot, mat.shape[0]), dtype=np.float64)
    den = np.zeros(n_boot, dtype=np.float64)
    for b in sorted(set(blocks)):
        mask = np.array([x == b for x in blocks], dtype=bool)
        row_idx = np.nonzero(mask)[0]
        b_dates = sorted(set(dates[i] for i in row_idx))
        idx_of = {d: i for i, d in enumerate(b_dates)}
        d_idx = np.array([idx_of[dates[i]] for i in row_idx], dtype=np.int64)
        n_dates_b = len(b_dates)
        b_sums = np.vstack([
            np.bincount(d_idx, weights=mat[m][mask], minlength=n_dates_b)
            for m in range(mat.shape[0])
        ])
        b_counts = np.bincount(d_idx, minlength=n_dates_b).astype(np.float64)
        draws = rng.multinomial(
            n_dates_b, np.full(n_dates_b, 1.0 / n_dates_b), size=n_boot
        )
        num += draws @ b_sums.T
        den += draws @ b_counts
    res = num / den[:, None]
    out = {}
    for j, n in enumerate(names):
        v = res[:, j]
        out[n] = {
            "point": float(mat[j].mean()),
            "p2.5": float(np.percentile(v, 2.5)),
            "p97.5": float(np.percentile(v, 97.5)),
        }
    for a, b in (("h3", "market"), ("l5", "market"), ("h3", "l5")):
        if a in names and b in names:
            ia, ib = names.index(a), names.index(b)
            diff = res[:, ia] - res[:, ib]
            out["%s_minus_%s" % (a, b)] = {
                "point": float(mat[ia].mean() - mat[ib].mean()),
                "p2.5": float(np.percentile(diff, 2.5)),
                "p97.5": float(np.percentile(diff, 97.5)),
            }
    return out


def _prep_hash_check(prep_dir: Path) -> None:
    mpath = prep_dir / "manifest.json"
    if not mpath.exists():
        raise ScoreReadError("prep manifest missing: %s" % mpath)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    for fname, want in manifest.get("outputs_sha256_16", {}).items():
        f = prep_dir / fname
        if not f.exists():
            raise ScoreReadError("prep output missing: %s" % f)
        got = sha256_16(f)
        if got != want:
            raise ScoreReadError(
                "prep hash mismatch for %s: manifest %s != actual %s"
                % (fname, want, got)
            )


def run_score(prep_dir: Path, start_metrics_path: Path, out_dir: Path,
              seed: int = 20261001, n_boot: int = 2000) -> dict:
    """Authorized-scoring implementation (correction C2).

    Joins realized K (start_metrics_v2) to the frozen prep contracts, settles
    the registered paper bets, computes the PIN primary metric (paired
    contract-level multi-class Brier; H3-raw vs LOG5-raw vs de-vig market on
    identical matched contracts), reuses the persisted count-layer errors,
    and runs the registered slate-date bootstrap (2000 resamples, seed
    20261001, identical resample indices across competitors).
    """
    out_dir = Path(out_dir)
    existing = [f for f in SCORE_FILES if (out_dir / f).exists()]
    if existing:
        raise WriteOnceError(
            "write-once violation: %s already contains %s"
            % (out_dir, ", ".join(existing))
        )
    _prep_hash_check(prep_dir)

    matched = pl.read_parquet(prep_dir / "matched_contracts.parquet")
    bets = pl.read_parquet(prep_dir / "paper_bets.parquet")
    sm = pl.read_parquet(start_metrics_path).select(
        ["game_pk", "side", "pitcher", "realized_k"]
        + ["base_h3_" + c for c in PERSISTED_COUNT_COLS]
        + ["base_l5_" + c for c in PERSISTED_COUNT_COLS]
    )
    labeled = matched.join(
        sm.rename({"side": "pitch_half"}),
        on=["game_pk", "pitcher", "pitch_half"], how="left",
    )
    n_unmatched = int(labeled["realized_k"].is_null().sum())
    if n_unmatched:
        raise ScoreReadError(
            "%d matched-contract rows have no realized K; refusing to score"
            % n_unmatched
        )
    obs = _outcome_frame(labeled)

    # ---- contract-level probability skill (PIN primary) --------------------
    skill = {a: _brier_logloss(obs, a) for a in ("h3", "l5", "market")}
    n_push = int(obs["y_push"].sum())
    n_rows = obs.height
    slates = obs["game_date"].to_list()
    slate_blocks = obs["block"].to_list()
    boot_vals = {}
    for a in ("h3", "l5", "market"):
        pw, pp, pl_ = _side_probs(obs, a)
        boot_vals[a] = obs.select(
            (
                (pw - pl.when(pl.col("side") == "over")
                 .then(pl.col("y_over_win")).otherwise(pl.col("y_under_win"))) ** 2
                + (pp - pl.col("y_push")) ** 2
                + (pl_ - pl.when(pl.col("side") == "over")
                   .then(pl.col("y_under_win")).otherwise(pl.col("y_over_win"))) ** 2
            ).alias("_b")
        )["_b"].to_numpy()
    boot_skill = _slate_bootstrap(boot_vals, slates, slate_blocks, n_boot, seed)

    per_tier = {}
    for t in obs["tier"].unique().to_list():
        sub = obs.filter(pl.col("tier") == t)
        per_tier[t] = {a: _brier_logloss(sub, a) for a in ("h3", "l5", "market")}
        per_tier[t]["n_rows"] = sub.height
    per_book = {}
    for bk in obs["book"].unique().to_list():
        sub = obs.filter(pl.col("book") == bk)
        per_book[bk] = {a: _brier_logloss(sub, a)["brier"] for a in ("h3", "l5", "market")}
        per_book[bk]["n_rows"] = sub.height

    # ---- count layer: REUSE persisted errors -------------------------------
    start_level = obs.select(
        ["game_pk", "pitcher", "pitch_half", "tier", "game_date"]
        + ["base_h3_" + c for c in PERSISTED_COUNT_COLS]
        + ["base_l5_" + c for c in PERSISTED_COUNT_COLS]
    ).unique()
    count_metrics = {"n_starts": start_level.height}
    for arm in ("h3", "l5"):
        count_metrics[arm] = {
            c: float(start_level["base_%s_%s" % (arm, c)].mean())
            for c in PERSISTED_COUNT_COLS
        }

    # ---- paper bets ---------------------------------------------------------
    # (game_pk, pitcher) is unique in start_metrics_v2 (7,194/7,194) and the
    # registered paper_bets rows do not carry pitch_half.
    ledger = bets.join(
        sm.select(["game_pk", "pitcher", "realized_k"]),
        on=["game_pk", "pitcher"], how="left",
    )
    if ledger["realized_k"].is_null().any():
        raise ScoreReadError("paper bets with no realized K; refusing to score")
    ledger = ledger.with_columns(
        pl.struct("line", "side", "realized_k")
        .map_elements(
            lambda s: settle_result(s["line"], s["side"], s["realized_k"]),
            return_dtype=pl.String,
        )
        .alias("result")
    ).with_columns(
        pl.struct("result", "decimal_odds", "stake_units")
        .map_elements(
            lambda s: payout_units(s["result"], s["decimal_odds"],
                                   float(s["stake_units"])),
            return_dtype=pl.Float64,
        )
        .alias("pnl_units")
    )
    n_bets = ledger.height
    wins = int((ledger["result"] == "win").sum())
    losses = int((ledger["result"] == "lose").sum())
    pushes = int((ledger["result"] == "push").sum())
    pnl = float(ledger["pnl_units"].sum())
    roi = pnl / n_bets if n_bets else 0.0
    wr = wins / max(1, wins + losses)

    clv = ledger.filter(pl.col("clv_pct").is_not_null())
    clv_table = clv.select(
        ["game_pk", "pitcher", "line", "side", "book", "tier", "game_date",
         "quote_ts", "price", "decimal_odds", "close_quote_ts", "close_price",
         "clv_pct", "result", "pnl_units"]
    )
    clv_summary = {
        "n_bets": n_bets,
        "n_with_close": clv_table.height,
        "n_missing_close": n_bets - clv_table.height,
        "clv_mean": float(clv_table["clv_pct"].mean()) if clv_table.height else None,
        "clv_median": float(clv_table["clv_pct"].median()) if clv_table.height else None,
        "clv_mean_by_side": {
            r["side"]: float(r["m"]) for r in clv_table.group_by("side").agg(
                pl.col("clv_pct").mean().alias("m")).iter_rows(named=True)
        },
        "clv_mean_by_tier": {
            r["tier"]: float(r["m"]) for r in clv_table.group_by("tier").agg(
                pl.col("clv_pct").mean().alias("m")).iter_rows(named=True)
        },
    }

    bet_dates = ledger["game_date"].to_list()
    bet_blocks = ledger["block"].to_list()
    pnl_arr = ledger["pnl_units"].to_numpy()
    bet_boot = _roi_bootstrap(pnl_arr, bet_dates, bet_blocks, n_boot, seed)

    # ---- outputs ------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger.write_parquet(out_dir / "bets_ledger.parquet")
    clv_table.write_parquet(out_dir / "clv_table.parquet")

    effective = {
        "contract_side_rows": n_rows,
        "distinct_start_line_pairs": int(
            obs.select("game_pk", "pitcher", "line").n_unique()),
        "distinct_starts": int(obs.select("game_pk", "pitcher").n_unique()),
        "distinct_slate_dates": int(obs["game_date"].n_unique()),
        "push_rows": n_push,
        "note": "complementary over/under sides share one realization and are "
                "NOT independent; the slate-date bootstrap is the declared "
                "correlation handling; effective counts reported alongside",
    }
    skill_out = {
        "primary_metric": "multi-class Brier at matched contracts, classes "
                          "{win, push, lose}; identical matched contracts "
                          "across H3-raw / LOG5-raw / de-vig market",
        "brier": {a: skill[a]["brier"] for a in skill},
        "brier_skill_vs_market": {
            a: skill["market"]["brier"] - skill[a]["brier"] for a in ("h3", "l5")
        },
        "log_loss_non_push": {a: skill[a]["log_loss_non_push"] for a in skill},
        "per_tier": per_tier,
        "per_book_brier": per_book,
        "count_layer_persisted_reused": count_metrics,
        "count_layer_source": str(start_metrics_path),
        "effective_counts": effective,
    }
    (out_dir / "skill_metrics.json").write_text(
        json.dumps(skill_out, indent=2), encoding="utf-8")
    (out_dir / "bootstrap.json").write_text(json.dumps({
        "params": {"seed": seed, "n_boot": n_boot, "unit": "slate date",
                   "block_stratified": True,
                   "identical_indices_across_competitors": True},
        "brier": boot_skill,
        "brier_skill_vs_market_ci": {
            a: boot_skill["%s_minus_market" % a] for a in ("h3", "l5")},
        "paper_roi": bet_boot,
    }, indent=2), encoding="utf-8")

    summary = {
        "spec": "market-eval-v1 score (EXPERIMENT_CARD.md correction C2)",
        "prep_dir": str(prep_dir),
        "bets": {"n": n_bets, "wins": wins, "losses": losses, "pushes": pushes,
                 "pnl_units": pnl, "roi_per_bet": roi, "win_rate": wr,
                 "missing_close": clv_summary["n_missing_close"]},
        "skill_headline": {
            "brier_h3": skill["h3"]["brier"],
            "brier_l5": skill["l5"]["brier"],
            "brier_market": skill["market"]["brier"],
        },
        "count_layer": count_metrics,
    }
    (out_dir / "score_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "inputs_sha256_16": {
            "matched_contracts.parquet": sha256_16(prep_dir / "matched_contracts.parquet"),
            "paper_bets.parquet": sha256_16(prep_dir / "paper_bets.parquet"),
            "start_metrics_v2.parquet": sha256_16(start_metrics_path),
        },
        "outputs_sha256_16": {
            f: sha256_16(out_dir / f) for f in SCORE_FILES
            if f.endswith(".parquet")
        },
        "params": {"seed": seed, "n_boot": n_boot},
    }
    (out_dir / "score_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return summary


def _roi_bootstrap(pnl: "np.ndarray", dates: list, blocks: list,
                   n_boot: int, seed: int) -> dict:
    """Slate-date bootstrap of paper ROI (sum pnl / n bets), ratio estimator,
    BLOCK-STRATIFIED (C3 repair matching _slate_bootstrap): each replicate
    draws exactly each block's original slate-date count of dates within the
    block, then combines per-block numerators/denominators, so block weights
    cannot shift across replicates.
    Separate draw stream from the skill bootstrap (same seed, documented)."""
    import numpy as np
    pnl = np.asarray(pnl, dtype=np.float64)
    rng = np.random.default_rng(seed + 1)
    num = np.zeros(n_boot, dtype=np.float64)
    den = np.zeros(n_boot, dtype=np.float64)
    for b in sorted(set(blocks)):
        mask = np.array([x == b for x in blocks], dtype=bool)
        row_idx = np.nonzero(mask)[0]
        b_dates = sorted(set(dates[i] for i in row_idx))
        idx_of = {d: i for i, d in enumerate(b_dates)}
        d_idx = np.array([idx_of[dates[i]] for i in row_idx], dtype=np.int64)
        n_dates_b = len(b_dates)
        s = np.bincount(d_idx, weights=pnl[mask], minlength=n_dates_b)
        c = np.bincount(d_idx, minlength=n_dates_b).astype(np.float64)
        draws = rng.multinomial(
            n_dates_b, np.full(n_dates_b, 1.0 / n_dates_b), size=n_boot
        )
        num += draws @ s
        den += draws @ c
    roi = np.where(den > 0, num / np.maximum(den, 1.0), np.nan)
    return {
        "point": float(np.sum(pnl) / len(pnl)) if len(pnl) else 0.0,
        "p2.5": float(np.nanpercentile(roi, 2.5)),
        "p97.5": float(np.nanpercentile(roi, 97.5)),
    }



def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Market-layer evaluation v1 (prep + gated scoring)"
    )
    ap.add_argument("--book-lines", type=Path, default=DEFAULT_BOOK_LINES)
    ap.add_argument("--envelope", type=Path, default=DEFAULT_ENVELOPE)
    ap.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    ap.add_argument("--id-map", type=Path, default=DEFAULT_ID_MAP)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--prep-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help="(scoring run only) prep outputs to read")
    ap.add_argument("--start-metrics", type=Path, default=DEFAULT_START_METRICS,
                    help="(scoring run only) realized K + persisted count errors")
    ap.add_argument("--score-dir", type=Path, default=DEFAULT_SCORE_DIR,
                    help="(scoring run only) output directory (write-once)")
    ap.add_argument("--seed", type=int, default=20261001,
                    help="(scoring run only) registered bootstrap seed")
    ap.add_argument("--n-boot", type=int, default=2000,
                    help="(scoring run only) registered bootstrap resamples")
    ap.add_argument("--score", action="store_true",
                    help="scoring run: joins realized K, settles paper bets, "
                         "computes the PIN skill metrics + bootstrap. Code is "
                         "IMPLEMENTED (correction C2); execution remains gated "
                         "on owner approval and has NOT been run here.")
    args = ap.parse_args(argv)
    if args.score:
        summary = run_score(
            args.prep_dir, args.start_metrics, args.score_dir,
            seed=args.seed, n_boot=args.n_boot,
        )
        print(json.dumps(summary, indent=2))
        print("wrote score outputs to %s" % args.score_dir)
        return 0

    summary = run_prep(
        args.book_lines, args.envelope, args.payload, args.id_map, args.out_dir
    )
    print(json.dumps({
        "eligible_starts": summary["identity"]["eligible_starts"],
        "unresolved_ids_excluded": summary["identity"]["unresolved_ids_excluded"],
        "doubleheader_ambiguous_excluded": summary["identity"]["doubleheader_ambiguous_excluded"],
        "coverage": summary["coverage"]["after_exclusions_all"],
        "eval_pairs": summary["contracts"]["eval_pairs_one_per_start_line"],
        "contract_side_rows": summary["contracts"].get("contract_side_rows", 0),
        "paper_bets": summary["paper_bets"]["bets"],
    }, indent=2))
    print("wrote prep outputs to %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
