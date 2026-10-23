"""Market-evaluation path (pitcher_strikeouts): the REGISTERED model K
distribution vs the de-vigged near-close sportsbook line.

RESEARCH-ONLY, synthetic-first. Dev blocks only (2024-07-01..2025-06-30);
confirm_2025H2 is never joined, never scored. The join chain reuses the
TESTED odds-coverage machinery (build_task_frames, 16 passing tests in
MLB-Props-Research/odds-coverage-v1) unchanged; this module adds the
de-vig, near-close selection, consensus, and scoring layers with
write-once receipts (initial-first, chained, failure records preserved).

De-vig: two-way half-line market (no push), multiplicative method -
each book's over/under American prices -> raw implied shares ->
normalized. Consensus per start: the line with the most books quoting
BOTH sides near close; consensus over probability = the MEDIAN across
books of the de-vigged over probability at that line.

Scoring: per-start log loss and Brier of the model vs the close on the
realized over/under outcome, paired slate-date bootstrap (registered
harness), Holm m=1; reliability by decile bucket of the model
probability. The model's registered count-RPS is reported on the same
joined subset; the close cannot produce a full count PMF from one line
(disclosed - the close comparison is at the line, not the distribution).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

import kcount_combiner as kc  # noqa: E402  (registered count metrics)

# the TESTED odds-coverage join machinery (reused unchanged)
_COV_DIR = Path(r"C:\Users\ckaplinger\MLB-Props-Research\odds-coverage-v1")
sys.path.insert(0, str(_COV_DIR))
import join_coverage as jc  # noqa: E402

MARKET = "pitcher_strikeouts"
DEV_WINDOW_START = "2024-07-01"
DEV_WINDOW_END = "2025-06-30"  # confirm_2025H2 excluded from the join
CLOSE_WINDOW_MIN = 60.0  # registered closing policy (tier A)
N_BUCKETS_RELIABILITY = 10


# ------------------------------------------------------------ de-vig
def american_to_raw(price: float) -> float:
    """American odds -> raw implied probability (with vig)."""
    price = float(price)
    if price == 0 or not np.isfinite(price):
        raise ValueError(f"invalid American price: {price}")
    if price > 0:
        return 100.0 / (price + 100.0)
    return (-price) / (-price + 100.0)


def devig_over(over_price: float, under_price: float) -> float:
    """Multiplicative de-vig of a two-way market -> fair over
    probability. Half-lines carry no push risk (K lines are X.5)."""
    o = american_to_raw(over_price)
    u = american_to_raw(under_price)
    s = o + u
    if s <= 0:
        raise ValueError("degenerate book shares")
    return o / s


# --------------------------------------------------- near-close select
def select_near_close(odds: "pl.DataFrame") -> "pl.DataFrame":
    """Latest near-close quote per (game_pk, book, line, side).

    Tier A (start has a vendor commence time): pre-cutoff quotes within
    CLOSE_WINDOW_MIN of first pitch; the LATEST such quote wins.
    Tier B (no local commence time, 2024 events): the vendor `close`
    snapshot; the latest snapshot_ts wins. Mirrors the registered
    closing policy in odds-coverage-v1."""
    import polars as pl

    need = {"game_pk", "book", "line", "side", "price", "quote_timestamp",
            "snapshot", "first_pitch_ts", "has_commence"}
    missing = need - set(odds.columns)
    if missing:
        raise ValueError(f"odds frame missing columns: {sorted(missing)}")
    cutoff = pl.duration(minutes=CLOSE_WINDOW_MIN)
    # dtype coercion: the archive's snapshot_ts arrives as a string;
    # unparseable timestamps drop out (never silently re-timed)
    if not isinstance(odds.schema["quote_timestamp"], pl.Datetime):
        odds = odds.with_columns(
            pl.col("quote_timestamp")
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("quote_timestamp"))
        odds = odds.filter(pl.col("quote_timestamp").is_not_null())
    if odds.schema["first_pitch_ts"] == pl.Utf8:
        odds = odds.with_columns(
            pl.col("first_pitch_ts")
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("first_pitch_ts"))
    # filter in stages: null first_pitch_ts (tier B rows) must never
    # enter the tier-A datetime arithmetic; a Null-dtype column (no
    # commence times at all) makes tier A empty by construction
    commencing = odds.filter(pl.col("has_commence"))
    if commencing.height == 0 or odds.schema["first_pitch_ts"] == pl.Null:
        tier_a = commencing.head(0)
    else:
        tier_a = commencing.filter(
            (pl.col("quote_timestamp") < pl.col("first_pitch_ts"))
            & ((pl.col("first_pitch_ts") - pl.col("quote_timestamp"))
               <= cutoff)
        ).sort("quote_timestamp").unique(
            subset=["game_pk", "book", "line", "side"], keep="last")
    tier_b = odds.filter(
        ~pl.col("has_commence") & (pl.col("snapshot") == "close")
    ).sort("quote_timestamp").unique(
        subset=["game_pk", "book", "line", "side"], keep="last")
    return pl.concat([tier_a, tier_b])


def consensus_over_probs(near_close: "pl.DataFrame") -> "pl.DataFrame":
    """Per start: the consensus line (most books quoting BOTH sides at
    that line; ties -> line closest to the median quoted line) and the
    consensus over probability (median across books of the de-vigged
    over probability at that line)."""
    import polars as pl

    wide = near_close.pivot(
        values="price", index=["game_pk", "book", "line"],
        on="side", aggregate_function="first")
    if "over" not in wide.columns or "under" not in wide.columns:
        raise ValueError("near-close quotes missing over/under sides")
    wide = wide.filter(pl.col("over").is_not_null()
                       & pl.col("under").is_not_null())
    if wide.height == 0:
        raise ValueError("no two-sided near-close quotes")
    wide = wide.with_columns(
        pl.struct(["over", "under"]).map_elements(
            lambda s: devig_over(s["over"], s["under"]),
            return_dtype=pl.Float64).alias("p_over_book"))
    per_line = wide.group_by("game_pk", "line").agg(
        pl.col("p_over_book").median().alias("p_over"),
        pl.col("book").n_unique().alias("n_books"))
    line_counts = per_line.group_by("game_pk").agg(
        pl.col("n_books").max().alias("max_books"),
        pl.col("line").median().alias("median_line"))
    per_line = per_line.join(line_counts, on="game_pk", how="left")
    chosen = per_line.filter(
        (pl.col("n_books") == pl.col("max_books"))
    ).with_columns(
        (pl.col("line") - pl.col("median_line")).abs().alias("dist"))
    chosen = chosen.sort("dist").unique(subset=["game_pk"], keep="first")
    return chosen.select("game_pk", "line", "p_over", "n_books")


def model_p_over(pmf: np.ndarray, line: float) -> float:
    """P(K > line) from a 24-bucket count PMF (k = 0..22 exact, tail at
    23). A half line X.5 makes this P(K >= X+1); for lines >= 22.5 the
    tail bucket IS the over probability."""
    pmf = np.asarray(pmf, dtype=np.float64)
    if pmf.ndim != 1 or pmf.shape[0] != ad.K_MAX:
        raise ValueError(f"expected a {ad.K_MAX}-bucket PMF, got "
                         f"{pmf.shape}")
    k_over = np.arange(ad.K_MAX) > line
    return float(pmf[k_over].sum())


# ------------------------------------------------------------- scoring
def score_starts(joined: "pl.DataFrame") -> dict:
    """Per-start model-vs-close scoring on the realized over/under
    outcome + reliability buckets. `joined` needs: game_pk, game_date,
    block, realized_k, line, p_over (close), pmf_baseline (24-bucket
    list), n_books."""
    import polars as pl

    if joined.height == 0:
        raise ValueError("empty joined frame")
    rows = []
    for r in joined.iter_rows(named=True):
        line = float(r["line"])
        o = int(r["realized_k"] > line)
        p_m = model_p_over(r["pmf_baseline"], line)
        p_c = float(r["p_over"])
        if not 0.0 < p_c < 1.0:
            raise ValueError(f"close probability out of (0,1): {p_c}")
        rows.append((o, p_m, p_c, float(kc.count_rps(
            np.asarray(r["pmf_baseline"], dtype=np.float64),
            int(r["realized_k"])))))
    o = np.array([r[0] for r in rows])
    p_m = np.array([r[1] for r in rows])
    p_c = np.array([r[2] for r in rows])
    rps = np.array([r[3] for r in rows])
    eps = 1e-12
    ll_m = float(-(o * np.log(p_m + eps)
                   + (1 - o) * np.log(1 - p_m + eps)).mean())
    ll_c = float(-(o * np.log(p_c + eps)
                   + (1 - o) * np.log(1 - p_c + eps)).mean())
    br_m = float(((p_m - o) ** 2).mean())
    br_c = float(((p_c - o) ** 2).mean())
    # reliability: decile buckets of the model probability
    qs = np.quantile(p_m, np.linspace(0, 1, N_BUCKETS_RELIABILITY + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    buckets = []
    for i in range(N_BUCKETS_RELIABILITY):
        mask = (p_m >= qs[i]) & (p_m < qs[i + 1])
        if mask.sum():
            buckets.append({
                "bucket": i,
                "n": int(mask.sum()),
                "p_model_mean": float(p_m[mask].mean()),
                "observed_over_rate": float(o[mask].mean()),
            })
    return {
        "n": int(joined.height),
        "log_loss_model": ll_m,
        "log_loss_close": ll_c,
        "log_loss_delta_model_minus_close": ll_m - ll_c,
        "brier_model": br_m,
        "brier_close": br_c,
        "brier_delta_model_minus_close": br_m - br_c,
        "count_rps_model_mean": float(rps.mean()),
        "reliability_buckets": buckets,
        "_per_start": {
            "o": o, "p_m": p_m, "p_c": p_c, "rps": rps,
        },
    }


def run_market_eval_k(model_pmfs: "pl.DataFrame", out_dir, *,
                      book_lines_path: str | None = None,
                      envelope_path: str | None = None,
                      n_boot: int = 2000, seed: int = 20261001,
                      ) -> dict:
    """GATED market-eval runner (synthetic-tested; real-data execution
    requires the registered gate AND the delegated owner order).
    Write-once receipts; failure records preserved.

    model_pmfs: the registered per-start K distribution frame
    (count_agg_eval_v1 lineage: game_pk, side, pitcher, game_date,
    block, realized_k, pmf_baseline) - dev blocks only."""
    import polars as pl

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    initial = {
        "inputs": {
            "consumed": {
                "model_pmfs": m0._frame_sha(model_pmfs),
                "book_lines_pitcher": str(book_lines_path),
                "snapshot_envelope": str(envelope_path),
            },
            "context_identities": {},
        },
        "code_config": {
            "market": MARKET,
            "dev_window": [DEV_WINDOW_START, DEV_WINDOW_END],
            "close_window_minutes": CLOSE_WINDOW_MIN,
            "devig": "multiplicative (two-way half-line, no push)",
            "consensus": ("line with the most two-sided books; median "
                          "de-vigged over probability across books"),
            "benchmark": "near-close line (tier A strict cutoff / "
                         "tier B close snapshot)",
            "bootstrap": {"n": n_boot, "seed": seed},
            "protected_block": m0.PROTECTED_BLOCK,
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        # stage 1: the tested odds-coverage join (dev window only)
        starts_out, odds, join_meta = jc.build_task_frames(
            Path(book_lines_path), Path(envelope_path),
            ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet",
            [MARKET], window_start=DEV_WINDOW_START,
            window_end=DEV_WINDOW_END)
        odds = odds.join(
            starts_out.select("game_pk", "first_pitch_ts", "has_commence"),
            on="game_pk", how="inner")

        # stage 2: near-close + consensus
        near_close = select_near_close(odds)
        consensus = consensus_over_probs(near_close)

        # stage 3: join the registered model PMFs (identity:
        # game_pk + side + pitcher via the join's game_pk-grain)
        pmfs = model_pmfs.filter(
            pl.col("block") != m0.PROTECTED_BLOCK)
        joined = (pmfs.join(
            consensus.select("game_pk", "line", "p_over", "n_books"),
            on="game_pk", how="inner"))
        coverage = {
            "model_starts_total": int(pmfs.height),
            "starts_with_near_close_consensus": int(joined.height),
            "joined_start_keys": int(joined.select(
                "game_pk", "side", "pitcher").unique().height),
            "join_meta": join_meta,
            "median_books_per_start": (float(consensus["n_books"].median())
                                       if consensus.height else None),
        }
        if joined.height == 0:
            raise ValueError("no starts joined to a near-close consensus")

        # stage 4: score
        sc = score_starts(joined)
        per = sc.pop("_per_start")
        res = cmp_bootstrap(per, joined, n_boot=n_boot, seed=seed)
        sc.update(res)

        # stage 5: write-once outputs
        ev = joined.select(
            "game_pk", "side", "pitcher", "game_date", "block",
            "realized_k", "line", "p_over", "n_books").with_columns(
            pl.Series("p_over_model", per["p_m"]),
            pl.Series("over_hit", per["o"]),
            pl.Series("count_rps_model", per["rps"]))
        ev_path = out_dir / "market_eval_k_v1.parquet"
        ev.write_parquet(ev_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(
            {**sc, "coverage": coverage}, indent=1, sort_keys=True),
            encoding="utf-8")
        outputs = {
            "market_eval_k_v1.parquet": ad.sha256_file(ev_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
    except Exception as exc:
        failure = {"stage": "market_eval_k", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = {**sc, "coverage": coverage}
    final["outputs"] = outputs
    final["acceptance"] = {
        "receipt_chain": initial_sha,
        "evaluation_run": True,
        "block_isolation": True,
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": {**sc, "coverage": coverage},
            "receipt_final": final,
            "receipt_initial_sha256": initial_sha}


def cmp_bootstrap(per: dict, joined: "pl.DataFrame", *, n_boot: int,
                  seed: int) -> dict:
    """Paired slate-date bootstrap of the model-vs-close log-loss delta
    (registered harness primitives; Holm m=1)."""
    import polars as pl

    o, p_m, p_c = per["o"], per["p_m"], per["p_c"]
    dates = joined["game_date"].to_list()
    blocks = joined["block"].to_list()
    ll_m = -(o * np.log(p_m + 1e-12)
             + (1 - o) * np.log(1 - p_m + 1e-12))
    ll_c = -(o * np.log(p_c + 1e-12)
             + (1 - o) * np.log(1 - p_c + 1e-12))
    cmp_mod = br.load_registered_comparison()
    res = cmp_mod.slate_date_draws({"model": ll_m, "close": ll_c},
                                   dates, blocks, n_boot=n_boot,
                                   seed=seed)
    d_rep = res[:, 0] - res[:, 1]
    delta = float(ll_m.mean() - ll_c.mean())
    ci = [float(np.percentile(d_rep, 2.5)),
          float(np.percentile(d_rep, 97.5))]
    p = cmp_mod.null_centered_p_value(delta, d_rep)
    holm = cmp_mod.holm_adjust({"model_vs_close_logloss": p})
    return {"log_loss_delta_ci95": ci,
            "log_loss_delta_p": p,
            "holm": holm,
            "decision": ("model_better_than_close" if ci[1] < 0
                         else "model_not_better_than_close")}
