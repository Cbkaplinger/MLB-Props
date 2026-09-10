"""Pull Kalshi pitcher-strikeout ladder history (FREE, keyless) for sharp-reference backtest.

Source: KXMLBKS series (per-pitcher whole-number rungs, e.g. "Brandon Young: 6+").
Why Kalshi: free keyless historical API (markets + trades + 1-min candlesticks),
per-pitcher full price paths back to >=May 2026, graded outcomes included.
Why NOT a book-CLV substitute: exchange microstructure (fees, binary 0-100c,
thin getaway-day rungs) != DK/FD book lines. Label it sharp-reference everywhere.

Stages (run independently, all checkpointed/resumable):
  1. events   : paginate KXMLBKS settled events -> raw JSON cache
  2. ladders  : nested rung markets -> normalized ladder parquet
                (player, game_date, rung, fair_over_prob, volume, result)
  3. closes   : 1-min candlesticks per rung -> close-anchored fair probs
                (last candle ending <= market close_time, i.e. first pitch;
                odd start times handled by construction, never by cron
                alignment). REQUIRED for honest skill: last_price on a settled
                market is the post-game converged price (Brier ~0.06 lookahead
                trap), not the pre-game close.
  4. report   : join vs ledger/projections -> Brier skill vs Kalshi,
                calibration buckets, coverage stats

For a .5 book line L, fair P(over L) = Yes price of rung floor(L)+1
(e.g. line 5.5 -> "6+" rung). No interpolation needed; whole-number book
lines (none in the live ledger) would interpolate between adjacent rungs.

Outputs (all under ignored data/Odds-Historical/kalshi/):
  raw/events/*.json, k_ladder.parquet, k_closes.parquet, k_skill_report.json

Examples:
  python production/ops/market_research/pull_kalshi_k_history.py --stage events --since 2026-08-01 --until 2026-08-29
  python production/ops/market_research/pull_kalshi_k_history.py --stage ladders --since 2026-08-01 --until 2026-08-29
  python production/ops/market_research/pull_kalshi_k_history.py --stage report --min-volume 100
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_parquet, atomic_write_text, norm_player_name  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXMLBKS"
OUT_DIR = ROOT / "data" / "Odds-Historical" / "kalshi"
RAW_EVENTS = OUT_DIR / "raw" / "events"
CHECKPOINT = OUT_DIR / "events_checkpoint.json"
RATE_SLEEP_S = 0.25  # ~4 rps, polite on a keyless endpoint
MIN_VOLUME_DEFAULT = 100.0  # contracts; below this a rung is noise, not signal

EVENT_RE = re.compile(r"^KXMLBKS-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})([A-Z]{2,3})([A-Z]{2,3})$")
RUNG_RE = re.compile(r"^(.*?):\s*(\d+)\+\s*$")

# Vendor nickname map (Kalshi roster names -> ledger/RG/MLBAM canonical).
# Applied AFTER norm_player_name so both sides share one key space.
# Extend when the report's unmatched list shows a new regular, not a call-up.
NAME_ALIASES = {
    "joey cantillo": "joseph cantillo",
    "mike king": "michael king",
    "mike soroka": "michael soroka",
    "zac thornton": "zach thornton",
}


def kalshi_player_norm(raw: str) -> str:
    key = norm_player_name(raw)
    return NAME_ALIASES.get(key, key)


def _get(session, path: str, params: dict, retries: int = 4):
    url = BASE + path
    for attempt in range(retries):
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2.0 * (attempt + 1))
            continue
        resp.raise_for_status()
        time.sleep(RATE_SLEEP_S)
        return resp.json()
    resp.raise_for_status()
    raise RuntimeError("unreachable")


def _parse_event_ticker(ticker: str) -> dict:
    """KXMLBKS-26SEP081835CLEBAL -> date 2026-09-08, teams CLE/BAL (first pitch 18:35 ET-ish).

    Month is a 3-letter code; times are venue-local wall times as listed.
    """
    m = EVENT_RE.match(ticker or "")
    if not m:
        return {}
    yy, mon, dd, hh, mm, away, home = m.groups()
    months = {v: k for k, v in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
    try:
        game_date = f"20{yy}-{months[mon]:02d}-{int(dd):02d}"
    except KeyError:
        return {}
    return {"game_date": game_date, "away": away, "home": home,
            "listed_time": f"{hh}:{mm}"}


def _parse_rung(subtitle: str) -> tuple[str, int] | tuple[None, None]:
    m = RUNG_RE.match(subtitle or "")
    if not m:
        return None, None
    return m.group(1).strip(), int(m.group(2))


def _load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_checkpoint(state: dict) -> None:
    atomic_write_text(CHECKPOINT, json.dumps(state, indent=2))


def stage_events(since: str, until: str) -> int:
    """Paginate settled KXMLBKS events (newest first) until past `since`."""
    if requests is None:
        raise SystemExit("requests is required")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_EVENTS.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    state = _load_checkpoint()
    cursor = state.get("cursor", "")
    done: set[str] = set(state.get("done", []))
    n_new = 0
    while True:
        params: dict = {"series_ticker": SERIES, "status": "settled",
                        "with_nested_markets": True}
        if cursor:
            params["cursor"] = cursor
        data = _get(session, "/events", params)
        events = data.get("events", [])
        if not events:
            break
        for ev in events:
            tick = ev.get("event_ticker", "")
            parsed = _parse_event_ticker(tick)
            gd = parsed.get("game_date", "")
            if tick and tick not in done:
                (RAW_EVENTS / f"{tick}.json").write_text(
                    json.dumps(ev), encoding="utf-8")
                done.add(tick)
                n_new += 1
            if gd and gd < since:
                _save_checkpoint({"cursor": "", "done": sorted(done)})
                print(f"reached {gd} (< {since}); events cached: {len(done)} (+{n_new} new)")
                return n_new
        cursor = data.get("cursor", "")
        _save_checkpoint({"cursor": cursor, "done": sorted(done)})
        print(f"paged: {len(done)} events cached (+{n_new} new)")
        if not cursor:
            break
    _save_checkpoint({"cursor": "", "done": sorted(done)})
    print(f"done: {len(done)} events cached (+{n_new} new)")
    return n_new


def _c_to_prob(cents: object) -> float | None:
    # Kalshi FixedPointDollars are dollars per $1-notional contract, i.e. the
    # number IS the probability ("0.8900" = 89c = P 0.89). Do NOT divide by 100.
    try:
        return float(str(cents))
    except (TypeError, ValueError):
        return None


def stage_ladders(since: str, until: str) -> pl.DataFrame:
    """Nested rung markets -> one normalized ladder parquet."""
    rows: list[dict] = []
    for fp in sorted(RAW_EVENTS.glob("KXMLBKS-*.json")):
        ev = json.loads(fp.read_text(encoding="utf-8"))
        parsed = _parse_event_ticker(ev.get("event_ticker", ""))
        gd = parsed.get("game_date", "")
        if not gd or not (since <= gd <= until):
            continue
        for m in ev.get("markets", []) or []:
            player, rung = _parse_rung(m.get("yes_sub_title", ""))
            if player is None or rung is None:
                continue
            try:
                volume = float(m.get("volume_fp") or 0.0)
            except (TypeError, ValueError):
                volume = 0.0
            rows.append({
                "event_ticker": ev.get("event_ticker"),
                "game_date": gd,
                "away": parsed.get("away"),
                "home": parsed.get("home"),
                "player": player,
                "player_norm": kalshi_player_norm(player),
                "rung": rung,  # P(K >= rung) = yes price
                "yes_price": _c_to_prob(m.get("last_price_dollars")),
                "prev_yes_price": _c_to_prob(m.get("previous_price_dollars")),
                "volume": volume,
                "result": m.get("result") or "",
                "status": m.get("status") or "",
                "market_ticker": m.get("ticker"),
            })
    frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    out = OUT_DIR / "k_ladder.parquet"
    if not frame.is_empty():
        atomic_write_parquet(frame, out)
    print(f"ladder rows: {frame.height} -> {out}")
    return frame


def _parse_ts(raw: str) -> int | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (TypeError, ValueError):
        return None


SCHED_DIR = OUT_DIR / "raw" / "mlb_schedule"

MLB_CODE_FIX = {"CWS": "CWS", "CHW": "CWS", "ATH": "ATH", "OAK": "ATH",
                "ARZ": "ARI", "TAM": "TB", "KCR": "KC", "SDP": "SD",
                "SFG": "SF", "NYY": "NYY", "NYM": "NYM", "CHC": "CHC",
                "LAA": "LAA", "WSH": "WSH", "WSN": "WSH"}


def _mlb_scheduled_first_pitch(session, game_date: str,
                               away: str, home: str) -> int | None:
    """Scheduled first-pitch ts (UTC) from the free MLB schedule API.

    Conservative anchor: trades at/after the MLB-listed start are excluded, so
    rain-delay late steam is sacrificed but in-play leakage is impossible.
    Per-date JSON cached under raw/mlb_schedule/.
    """
    SCHED_DIR.mkdir(parents=True, exist_ok=True)
    fp = SCHED_DIR / f"{game_date}.json"
    try:
        sched = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
    except Exception:
        sched = None
    if sched is None:
        r = session.get("https://statsapi.mlb.com/api/v1/schedule",
                        params={"sportId": 1, "date": game_date, "hydrate": "team"},
                        timeout=30)
        r.raise_for_status()
        sched = r.json()
        fp.write_text(json.dumps(sched), encoding="utf-8")
        time.sleep(0.2)
    want_a = MLB_CODE_FIX.get((away or "").upper(), (away or "").upper())
    want_h = MLB_CODE_FIX.get((home or "").upper(), (home or "").upper())
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            try:
                ta = g["teams"]["away"]["team"].get("abbreviation", "").upper()
                th = g["teams"]["home"]["team"].get("abbreviation", "").upper()
            except KeyError:
                continue
            ta = MLB_CODE_FIX.get(ta, ta)
            th = MLB_CODE_FIX.get(th, th)
            if ta == want_a and th == want_h:
                return _parse_ts(g.get("gameDateTime") or g.get("gameDate") or "")
    return None


def _trades_before(session, ticker: str, day_start: int,
                   cutoff_ts: int, live_cutoff: int) -> list[dict]:
    """All trades for ticker in [day_start, cutoff_ts], live then historical."""
    out: list[dict] = []
    paths = (["/markets/trades", "/historical/trades"]
             if cutoff_ts >= live_cutoff else ["/historical/trades"])
    for path in paths:
        cursor = ""
        try:
            while True:
                params: dict = {"ticker": ticker, "min_ts": day_start,
                                "max_ts": cutoff_ts, "limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                data = _get(session, path, params)
                for t in data.get("trades", []):
                    ts = _parse_ts(t.get("created_time", ""))
                    if ts is not None and ts <= cutoff_ts:
                        out.append(t)
                cursor = data.get("cursor", "")
                if not cursor:
                    break
        except Exception as exc:
            if "404" not in str(exc) or path == paths[-1]:
                if "404" not in str(exc):
                    print(f"trades failed {ticker}: {str(exc)[:100]}")
            if out:
                break
            continue
        if out:
            break
    return out


def stage_closes(only_joined: bool = False) -> pl.DataFrame:
    """Close-anchored fair prob per rung via pre-first-pitch TRADES.

    For each rung market: last trade with ts <= MLB-scheduled first pitch.
    Trade price (yes_price_dollars) is the fair prob — no devig needed on an
    exchange. In-play trades are excluded by construction (conservative:
    rain-delay late steam is sacrificed, leakage is impossible).

    With only_joined=True, fetch only the (player, date, rung) triples a
    ledger join can actually consume (rung = floor(line)+1).
    """
    if requests is None:
        raise SystemExit("requests is required")
    ladder_path = OUT_DIR / "k_ladder.parquet"
    if not ladder_path.exists():
        raise SystemExit(f"Missing {ladder_path}; run --stage ladders first.")
    ladder = pl.read_parquet(ladder_path)

    # market close_time lives in the cached event JSONs.
    close_ts: dict[str, int] = {}
    game_day: dict[str, str] = {}
    for fp in sorted(RAW_EVENTS.glob("KXMLBKS-*.json")):
        try:
            ev = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in ev.get("markets", []) or []:
            tick = m.get("ticker", "")
            ts = _parse_ts(m.get("close_time", ""))
            if tick and ts:
                close_ts[tick] = ts
                parsed = _parse_event_ticker(ev.get("event_ticker", ""))
                if parsed.get("game_date"):
                    game_day[tick] = parsed["game_date"]

    live_cutoff = _parse_ts("2026-07-10T00:00:00Z") or 0
    ck_path = OUT_DIR / "closes_checkpoint.json"
    done: dict[str, dict] = {}
    if ck_path.exists():
        try:
            done = json.loads(ck_path.read_text(encoding="utf-8"))
        except Exception:
            done = {}

    session = requests.Session()
    tickers = [t for t in ladder["market_ticker"].unique().to_list() if t]
    if only_joined:
        try:
            led = pl.read_parquet(ROOT / "artifacts" / "odds_log" / "ledger.parquet")
            settled = led.filter(
                (pl.col("status") == "settled")
                & pl.col("settle_value").is_not_null()
            )
            need = set()
            for r in settled.to_dicts():
                need.add((norm_player_name(str(r["player_name"] or "")),
                          str(r["game_date"])[:10], int(float(r["line"])) + 1))
            keep = ladder.filter(
                pl.struct(["player_norm", "game_date", "rung"]).map_elements(
                    lambda s: (s["player_norm"], str(s["game_date"])[:10],
                               int(s["rung"])) in need,
                    return_dtype=pl.Boolean,
                )
            )
            tickers = [t for t in keep["market_ticker"].unique().to_list() if t]
            print(f"only_joined: {len(tickers)} tickers needed")
        except Exception as exc:
            print(f"only_joined filter failed ({exc}); fetching all")
    rows: list[dict] = []
    # rung meta for date/teams lookup
    meta = {r["market_ticker"]: r for r in
            ladder.select(["market_ticker", "game_date", "away", "home"])
            .unique(subset=["market_ticker"]).to_dicts()}
    for i, tick in enumerate(tickers):
        if tick in done and "n_trades" in done[tick]:
            rows.append(done[tick])
            continue
        m = meta.get(tick, {})
        gd = str(m.get("game_date", ""))[:10]
        if not gd:
            continue
        day_start = _parse_ts(f"{gd}T00:00:00Z")
        first_pitch = _mlb_scheduled_first_pitch(
            session, gd, str(m.get("away") or ""), str(m.get("home") or ""))
        if not first_pitch or not day_start:
            continue
        trades = _trades_before(session, tick, day_start, first_pitch,
                                live_cutoff)
        if not trades:
            continue
        last = max(trades, key=lambda t: _parse_ts(t.get("created_time", "")) or 0)
        try:
            price = float(last["yes_price_dollars"])
        except (KeyError, TypeError, ValueError):
            continue
        row = {"market_ticker": tick, "close_ts": first_pitch,
               "close_fair_over": price,
               "n_trades": len(trades)}
        done[tick] = row
        rows.append(row)
        if len(rows) % 100 == 0:
            atomic_write_text(ck_path, json.dumps(done))
            print(f"closes: {len(rows)}/{len(tickers)}")
    atomic_write_text(ck_path, json.dumps(done))
    frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    out = OUT_DIR / "k_closes.parquet"
    if not frame.is_empty():
        atomic_write_parquet(frame, out)
    print(f"close rows: {frame.height} / {len(tickers)} tickers -> {out}")
    return frame


def fair_prob_at_line(ladder: pl.DataFrame, line: float) -> float | None:
    """Fair P(over) at a .5 book line from whole-number rungs (no interpolation)."""
    need = int(line) + 1  # line 5.5 -> rung 6 ("6+" = P(K>=6) = P(K>5.5))
    hit = ladder.filter(pl.col("rung") == need).head(1)
    if hit.is_empty():
        return None
    return hit["fair_over"][0] if "fair_over" in hit.columns else hit["yes_price"][0]


def stage_report(min_volume: float = MIN_VOLUME_DEFAULT) -> dict:
    """Join Kalshi fair probs vs ledger/projections; Brier skill + coverage."""
    ladder_path = OUT_DIR / "k_ladder.parquet"
    if not ladder_path.exists():
        raise SystemExit(f"Missing {ladder_path}; run --stage ladders first.")
    ladder = pl.read_parquet(ladder_path)
    ladder = ladder.filter(
        pl.col("yes_price").is_not_null() & (pl.col("volume") >= min_volume))
    # Prefer close-anchored fair probs (pre-game) over final last_price
    # (post-game converged — lookahead trap). Fall back only if closes missing.
    closes_path = OUT_DIR / "k_closes.parquet"
    using_closes = closes_path.exists()
    if using_closes:
        closes = pl.read_parquet(closes_path)
        ladder = ladder.join(closes.select(["market_ticker", "close_fair_over"]),
                             on="market_ticker", how="left")
        ladder = ladder.with_columns(
            pl.when(pl.col("close_fair_over").is_not_null())
            .then(pl.col("close_fair_over"))
            .otherwise(pl.col("yes_price"))
            .alias("fair_over")
        )
    else:
        ladder = ladder.with_columns(pl.col("yes_price").alias("fair_over"))

    led = pl.read_parquet(ROOT / "artifacts" / "odds_log" / "ledger.parquet")
    settled = led.filter(
        (pl.col("status") == "settled")
        & pl.col("settle_value").is_not_null()
        & pl.col("side").is_not_null()
    )
    if settled.is_empty():
        raise SystemExit("Ledger has no settled rows to compare.")

    joined: list[dict] = []
    for r in settled.to_dicts():
        line = float(r["line"])
        cand = ladder.filter(
            (pl.col("game_date").cast(pl.Utf8) == str(r["game_date"])[:10])
            & (pl.col("player_norm") == norm_player_name(str(r["player_name"] or "")))
        )
        fp = fair_prob_at_line(cand, line)
        if fp is None:
            continue
        actual_over = float(r["settle_value"]) > line
        p_model = r.get("p_model")
        joined.append({
            "game_date": str(r["game_date"])[:10],
            "player": r["player_name"],
            "line": line,
            "side": r["side"],
            "kalshi_fair_over": fp,
            "p_model_over": float(p_model) if p_model is not None else None,
            "actual_over": actual_over,
        })
    rep: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "min_volume": min_volume,
        "using_close_anchored": using_closes,
        "n_settled_ledger": settled.height,
        "n_joined": len(joined),
        "join_rate": (len(joined) / settled.height) if settled.height else 0.0,
    }
    if joined:
        jf = pl.DataFrame(joined)
        for col in ("kalshi_fair_over", "p_model_over"):
            sub = jf.filter(
                pl.col(col).is_not_null() & pl.col("actual_over").is_not_null())
            if sub.is_empty():
                continue
            y = sub["actual_over"].cast(pl.Float64)
            p = sub[col].cast(pl.Float64)
            rep[f"{col}_n"] = sub.height
            rep[f"{col}_brier"] = float(((p - y) ** 2).mean())
            rep[f"{col}_mean_p"] = float(p.mean())
            rep[f"{col}_emp_rate"] = float(y.mean())
        if "p_model_over_brier" in rep and "kalshi_fair_over_brier" in rep:
            rep["brier_skill_vs_kalshi"] = (
                rep["kalshi_fair_over_brier"] - rep["p_model_over_brier"])
    out = OUT_DIR / "k_skill_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2, default=str))
    return rep


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stage", choices=["events", "ladders", "closes", "report"],
                   required=True)
    p.add_argument("--since", default="2025-01-01")
    p.add_argument("--until", default="2026-12-31")
    p.add_argument("--min-volume", type=float, default=MIN_VOLUME_DEFAULT)
    p.add_argument("--only-joined", action="store_true",
                   help="closes stage: fetch candles only for rungs the ledger join consumes")
    args = p.parse_args()

    if args.stage == "events":
        stage_events(args.since, args.until)
    elif args.stage == "ladders":
        stage_ladders(args.since, args.until)
    elif args.stage == "closes":
        stage_closes(only_joined=args.only_joined)
    elif args.stage == "report":
        stage_report(args.min_volume)


if __name__ == "__main__":
    main()
