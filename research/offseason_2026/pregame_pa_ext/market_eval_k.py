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


# ----------------------------------------------------- ladder benchmark
def book_margins_from_two_sided(nc_main: "pl.DataFrame") -> "pl.DataFrame":
    """Per (game_pk, book): the book's vig margin (o_raw + u_raw - 1)
    from the PRINCIPAL market's two-sided near-close quotes. Falls back
    to the pooled median margin for books/starts without a two-sided
    quote (disclosed)."""
    import polars as pl

    wide = nc_main.pivot(values="price", index=["game_pk", "book"],
                         on="side", aggregate_function="first")
    if "over" not in wide.columns or "under" not in wide.columns:
        raise ValueError("principal near-close missing over/under sides")
    wide = wide.filter(pl.col("over").is_not_null()
                       & pl.col("under").is_not_null())
    margins = wide.with_columns(
        pl.struct(["over", "under"]).map_elements(
            lambda s: american_to_raw(s["over"])
            + american_to_raw(s["under"]) - 1.0,
            return_dtype=pl.Float64).alias("margin"))
    pooled = float(margins["margin"].median())
    return margins.select("game_pk", "book", "margin"), pooled


def ladder_rung_probs(nc_alt: "pl.DataFrame",
                      margins: "pl.DataFrame", pooled_margin: float,
                      ) -> "pl.DataFrame":
    """Per (start, line): the consensus over probability from the
    ALTERNATE ladder's OVER-side quotes, de-vigged with each book's own
    principal-market margin (the archived alternate ladder is over-side
    only - the under side was never captured). raw = fair * (1 + margin)
    under proportional vig, so fair = raw / (1 + margin). Consensus =
    median across books (same rule as the principal market)."""
    import polars as pl

    joined = nc_alt.filter(pl.col("side") == "over").join(
        margins, on=["game_pk", "book"], how="left").with_columns(
        pl.col("margin").fill_null(pooled_margin))
    per_rung = joined.with_columns(
        pl.struct(["price", "margin"]).map_elements(
            lambda s: american_to_raw(s["price"]) / (1.0 + s["margin"]),
            return_dtype=pl.Float64).alias("p_over_book"))
    return per_rung.group_by("game_pk", "line").agg(
        pl.col("p_over_book").median().alias("p_over"),
        pl.col("book").n_unique().alias("n_books"))


def ladder_implied_pmf(rungs: "pl.DataFrame",
                       k_max: int = None) -> "pl.DataFrame":
    """Derive each start's implied count PMF from its ladder rungs.

    Input rungs: (game_pk, line, p_over) with half lines; p_over(L) =
    P(K > L) - non-increasing in L. Implied probabilities:
    P(K=0) = 1 - p_over(first rung); P(K=k) = p_over(k-1.5) -
    p_over(k-0.5). Beyond the last rung the over-probability curve is
    continued GEOMETRICALLY (ratio of the last two rungs, clipped to
    [0, 0.5]) down to the tail bucket - a disclosed continuation
    needed because the archived ladder rarely reaches k=22.5.
    Monotonicity is enforced and the vector renormalized to exactly 1;
    starts with fewer than two usable rungs get status='no_ladder'."""
    import polars as pl

    k_max = k_max or ad.K_MAX
    out_rows = []
    for gpk, g in rungs.group_by("game_pk"):
        if isinstance(gpk, (tuple, list)):
            gpk = gpk[0]
        rr = g.sort("line")
        lines = rr["line"].to_numpy()
        p = rr["p_over"].to_numpy()
        # enforce non-increasing over probabilities in the line
        # (running minimum from the left floors any crossed rung)
        p = np.minimum.accumulate(p)
        p = np.clip(p, 0.0, 1.0)
        if len(p) < 2 or lines[0] != 0.5:
            out_rows.append({"game_pk": gpk, "pmf": None,
                             "n_rungs": int(len(lines)),
                             "status": "no_ladder"})
            continue
        # geometric continuation beyond the last rung
        ratio = min(max(p[-1] / max(p[-2], 1e-9), 0.0), 0.5)
        p_ext = list(p)
        cur = p[-1]
        while len(p_ext) < k_max - 1:
            cur = cur * ratio
            p_ext.append(cur)
        p_ext = np.clip(np.asarray(p_ext), 0.0, 1.0)
        pmf = np.zeros(k_max)
        pmf[0] = 1.0 - p_ext[0]
        for k in range(1, k_max - 1):
            pmf[k] = max(p_ext[k - 1] - p_ext[k], 0.0)
        pmf[k_max - 1] = p_ext[-1]
        if pmf.sum() <= 0 or np.isnan(pmf).any():
            out_rows.append({"game_pk": gpk, "pmf": None,
                             "n_rungs": int(len(lines)),
                             "status": "no_ladder"})
            continue
        pmf = pmf / pmf.sum()
        out_rows.append({"game_pk": gpk, "pmf": pmf.tolist(),
                         "n_rungs": int(len(lines)),
                         "status": "ok"})
    return pl.DataFrame(out_rows)


def distribution_log_loss(pmf: np.ndarray, k_real: int) -> float:
    """Categorical log loss of a count distribution at the realized
    count (registered bucket convention)."""
    pmf = np.asarray(pmf, dtype=np.float64)
    k = min(int(k_real), len(pmf) - 1)
    if not 0 <= k_real <= len(pmf) - 1:
        raise ValueError(f"realized count {k_real} outside support")
    p = max(float(pmf[k]), 1e-12)
    return float(-np.log(p))


def compare_model_vs_ladder(model_pmf: np.ndarray, ladder_pmf: np.ndarray,
                            k_real: int) -> dict:
    """One start's head-to-head: log loss and RPS for the model vs the
    ladder-implied distribution (both 24-bucket registered support)."""
    return {
        "ll_model": distribution_log_loss(model_pmf, k_real),
        "ll_ladder": distribution_log_loss(ladder_pmf, k_real),
        "rps_model": float(kc.count_rps(model_pmf, k_real)),
        "rps_ladder": float(kc.count_rps(ladder_pmf, k_real)),
    }


def placebo_lines(joined: "pl.DataFrame", seed: int = 20261001
                  ) -> "pl.DataFrame":
    """Placebo control: shuffle which start each (line, p_over) pair is
    matched to (seeded permutation). The model-vs-close gap under the
    shuffled mapping should be ~0; a persistent gap means the matched
    line itself carries outcome-correlated information (leak)."""
    import polars as pl

    rng = np.random.default_rng(seed)
    idx = rng.permutation(joined.height)
    shuf = joined.with_columns(
        pl.Series("line", joined["line"].to_numpy()[idx]),
        pl.Series("p_over", joined["p_over"].to_numpy()[idx]),
        pl.Series("n_books", joined["n_books"].to_numpy()[idx]),
    )
    return shuf


def run_ladder_benchmark(model_pmfs: "pl.DataFrame", out_dir, *,
                         book_lines_path: str,
                         envelope_path: str,
                         n_boot: int = 2000, seed: int = 20261001,
                         tier_a_only: bool = True,
                         placebo: bool = True,
                         ) -> dict:
    """Ladder-implied benchmark runner (write-once receipts): the
    alternate market's rungs -> implied per-start count distribution ->
    head-to-head vs the model's PMF (log loss + RPS). Dev window only;
    tier A (true T-5 closes) by default. Optional placebo variant with
    line-to-start shuffling."""
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
            "market": "pitcher_strikeouts_alternate (ladder)",
            "dev_window": [DEV_WINDOW_START, DEV_WINDOW_END],
            "tier_a_only": tier_a_only,
            "implied_pmf": ("P(K=0)=1-p_over(0.5); P(K=k)=p_over(k-1.5)"
                            "-p_over(k-0.5); last-rung over = tail; "
                            "monotone-enforced, renormalized"),
            "bootstrap": {"n": n_boot, "seed": seed},
            "placebo": placebo,
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)
    try:
        # the alternate ladder is OVER-SIDE ONLY in the archive; the
        # per-book de-vig margin comes from the principal market's
        # two-sided near-close quotes
        starts_m, odds_m, meta_m = jc.build_task_frames(
            Path(book_lines_path), Path(envelope_path),
            ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet",
            ["pitcher_strikeouts"],
            window_start=DEV_WINDOW_START, window_end=DEV_WINDOW_END)
        odds_m = odds_m.join(
            starts_m.select("game_pk", "first_pitch_ts", "has_commence"),
            on="game_pk", how="inner")
        if tier_a_only:
            odds_m = odds_m.filter(pl.col("has_commence"))
        nc_main = select_near_close(odds_m)
        margins, pooled_margin = book_margins_from_two_sided(nc_main)

        starts_out, odds, join_meta = jc.build_task_frames(
            Path(book_lines_path), Path(envelope_path),
            ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet",
            ["pitcher_strikeouts_alternate"],
            window_start=DEV_WINDOW_START, window_end=DEV_WINDOW_END)
        odds = odds.join(
            starts_out.select("game_pk", "first_pitch_ts", "has_commence",
                              "game_date"),
            on="game_pk", how="inner")
        if tier_a_only:
            odds = odds.filter(pl.col("has_commence"))
        nc = select_near_close(odds)
        rungs = ladder_rung_probs(nc, margins, pooled_margin)
        implied = ladder_implied_pmf(rungs)
        ok = implied.filter(pl.col("status") == "ok")
        pmfs = model_pmfs.filter(pl.col("block") != m0.PROTECTED_BLOCK)
        if tier_a_only:
            pmfs = pmfs.filter(pl.col("game_date")
                               >= pl.date(2025, 1, 1))
        joined = pmfs.join(ok.select("game_pk", "pmf", "n_rungs"),
                           on="game_pk", how="inner")
        coverage = {
            "model_starts": int(pmfs.height),
            "starts_with_ladder_pmf": int(joined.height),
            "join_meta": join_meta,
            "median_rungs": (float(ok["n_rungs"].median())
                             if ok.height else None),
        }
        if joined.height == 0:
            raise ValueError("no starts with a usable ladder PMF")
        ll_m, ll_l, rps_m, rps_l = [], [], [], []
        for r in joined.iter_rows(named=True):
            k_real = int(r["realized_k"])
            cmp1 = compare_model_vs_ladder(
                np.asarray(r["pmf_baseline"], dtype=np.float64),
                np.asarray(r["pmf"], dtype=np.float64), k_real)
            ll_m.append(cmp1["ll_model"])
            ll_l.append(cmp1["ll_ladder"])
            rps_m.append(cmp1["rps_model"])
            rps_l.append(cmp1["rps_ladder"])
        ll_m, ll_l = np.asarray(ll_m), np.asarray(ll_l)
        rps_m, rps_l = np.asarray(rps_m), np.asarray(rps_l)
        cmp_mod = br.load_registered_comparison()
        dates = joined["game_date"].to_list()
        blocks = joined["block"].to_list()
        res_ll = cmp_mod.slate_date_draws({"model": ll_m, "ladder": ll_l},
                                          dates, blocks, n_boot=n_boot,
                                          seed=seed)
        d_ll = res_ll[:, 0] - res_ll[:, 1]
        res_rp = cmp_mod.slate_date_draws({"model": rps_m,
                                           "ladder": rps_l},
                                          dates, blocks, n_boot=n_boot,
                                          seed=seed)
        d_rp = res_rp[:, 0] - res_rp[:, 1]
        metrics = {
            "n": int(joined.height),
            "ll_model": float(ll_m.mean()),
            "ll_ladder": float(ll_l.mean()),
            "ll_delta_model_minus_ladder": float(ll_m.mean() - ll_l.mean()),
            "ll_delta_ci95": [float(np.percentile(d_ll, 2.5)),
                              float(np.percentile(d_ll, 97.5))],
            "rps_model": float(rps_m.mean()),
            "rps_ladder": float(rps_l.mean()),
            "rps_delta_model_minus_ladder": float(rps_m.mean()
                                                  - rps_l.mean()),
            "rps_delta_ci95": [float(np.percentile(d_rp, 2.5)),
                               float(np.percentile(d_rp, 97.5))],
            "decision_ladder": ("model_better_than_ladder"
                                if np.percentile(d_ll, 97.5) < 0
                                else "ladder_not_beaten"),
            "coverage": coverage,
        }
        ev = joined.select(
            "game_pk", "side", "pitcher", "game_date", "block",
            "realized_k", "n_rungs").with_columns(
            pl.Series("ll_model", ll_m), pl.Series("ll_ladder", ll_l),
            pl.Series("rps_model", rps_m), pl.Series("rps_ladder", rps_l))
        ev_path = out_dir / "ladder_benchmark_v1.parquet"
        ev.write_parquet(ev_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "ladder_benchmark_v1.parquet": ad.sha256_file(ev_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
        placebo_metrics = None
        if placebo:
            # shuffle the LADDER-PMF-to-start mapping (seeded); ~0 gap
            # expected if the matched ladder carries the information
            rng = np.random.default_rng(seed)
            idx = rng.permutation(joined.height)
            shuf = joined.with_columns(
                pl.Series("pmf", joined["pmf"].to_numpy()[idx]),
                pl.Series("n_rungs", joined["n_rungs"].to_numpy()[idx]))
            ll_ms, ll_ls = [], []
            for r in shuf.iter_rows(named=True):
                k_real = int(r["realized_k"])
                ll_ms.append(distribution_log_loss(
                    np.asarray(r["pmf_baseline"], dtype=np.float64),
                    k_real))
                ll_ls.append(distribution_log_loss(
                    np.asarray(r["pmf"], dtype=np.float64), k_real))
            placebo_metrics = {
                "ll_delta_model_minus_ladder_placebo":
                    float(np.mean(ll_ms) - np.mean(ll_ls)),
                "note": ("shuffled ladder-to-start mapping; ~0 expected "
                         "if the matched ladder carries the info"),
            }
    except Exception as exc:
        failure = {"stage": "ladder_benchmark", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = metrics
    if placebo_metrics is not None:
        final["placebo"] = placebo_metrics
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
    return {"out_dir": str(out_dir), "metrics": metrics,
            "placebo": placebo_metrics, "receipt_final": final,
            "receipt_initial_sha256": initial_sha}
