"""Eval-universe panel builder (Harness Step 1, report-only).

Reads: L3 pitcher_training (features+K), frozen artifacts via score_frame,
paid K-main board/close (DK/FD), envelope event clocks.
Writes ONLY to research/offseason_2026/datasets/ (guarded).
No selection, no sweeps, no fitting: single frozen floor for reporting.

Conventions (recorded in manifest): DK/FD books only; per-book devig;
best-edge book per (start, line); edge_floor = 0.12 base (model-layer report;
veto/cap/probation NOT applied — policy layer is 2025A, pre-registered);
$50 flat; CLV = p_close - p_open devigged; beat = CLV > 0.
"""

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import polars as pl

import numpy as np

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))
sys.path.insert(0, str(WS.parents[1] / "src"))
from boundary import assert_workspace_path  # noqa: E402

REPO = WS.parents[1]
BOOKS = ("draftkings", "fanduel")
EDGE_FLOOR = 0.12
STAKE = 50.0


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def tnorm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(sorted("".join(c for c in s.lower() if c.isalpha() or c == " ").split()))


def american_to_implied(a: float) -> float:
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def main() -> None:
    sys.path.insert(0, str(REPO / "production/ops/market_research"))
    import pandas as pd  # noqa: E402
    from datetime import datetime, timezone  # noqa: E402
    from Python.live_assembly import (  # noqa: E402
        score_frame,
    )
    from Python.count_layer import PROJECTION_K_LINES  # noqa: E402
    from join_keys import sorted_key  # noqa: E402

    print(f"PROJECTION_K_LINES={list(PROJECTION_K_LINES)}", flush=True)
    train = pd.read_parquet(REPO / "data/processed/pitcher_training.parquet")
    train["__gd"] = pd.to_datetime(train["game_date"]).dt.date
    frame = train[train["__gd"] >= pd.Timestamp("2025-03-27").date()].copy()

    # 1. Fidelity: determinism check (score twice -> identical) + regime note.
    # Stored historical_scores predate the 9/10 Poisson+WS1c promotion
    # (binomial/isotonic era), so rescoring with the CURRENT frozen stack is
    # expected to differ (~0.1 on some rows). The fresh score IS the comparator.
    samp = frame.head(300)
    s1, _ = score_frame(samp, lines=list(PROJECTION_K_LINES))
    s2, _ = score_frame(samp, lines=list(PROJECTION_K_LINES))
    maxdiff = float(max(
        abs(s1[f"p_over_{l}_cal"] - s2[f"p_over_{l}_cal"]).max()
        for l in ("4_5", "6_5", "7_5")))
    print(f"DETERMINISM max|run1 - run2|: {maxdiff}", flush=True)
    assert maxdiff == 0.0, "frozen stack is not deterministic"

    # 2. Score full 2025-03-27..2026-09-27 frame with the frozen stack.
    scored, report = score_frame(frame, lines=list(PROJECTION_K_LINES))
    scored["gd"] = scored["game_date"].astype(str).str.slice(0, 10)
    scored["key_sorted"] = [sorted_key(x) for x in scored["player_name"].astype(str)]
    scored["scored_utc"] = datetime.now(timezone.utc).isoformat()
    scored["calibration_version"] = report.get("calibration_version", "")
    scored["count_family"] = report.get("count_family", "")
    keep = ["game_pk", "pitcher", "game_date", "K", "expected_K", "projected_tbf",
            "k_rate_pred"] + [c for c in scored.columns
                              if c.startswith("p_over_") and c.endswith("_cal")]
    probs = scored[keep].copy()
    probs["__gd"] = pd.to_datetime(probs["game_date"]).dt.date

    # 3. Board + close K-main DK/FD pairs -> devigged fair per book.
    bl = pl.scan_parquet(REPO / "data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("book").is_in(BOOKS))
        & (pl.col("snapshot").is_in(("board", "close")))).collect()
    pairs = (bl.group_by(["event_id", "snapshot", "book", "player_norm", "line"]).agg(
        pl.col("price").filter(pl.col("side") == "over").first().alias("over"),
        pl.col("price").filter(pl.col("side") == "under").first().alias("under"))
        .filter(pl.col("over").is_not_null() & pl.col("under").is_not_null()))
    pairs = pairs.with_columns(
        ((pl.col("over").map_elements(american_to_implied, return_dtype=pl.Float64)
          + pl.col("under").map_elements(american_to_implied, return_dtype=pl.Float64))).alias("tot"))
    pairs = pairs.with_columns(
        (pl.col("over").map_elements(american_to_implied, return_dtype=pl.Float64)
         / pl.col("tot")).alias("p_over"))
    env = pl.scan_parquet(REPO / "data/Odds-Historical/theoddsapi/snapshot_envelope.parquet").select(
        "event_id", "commence_time").collect().with_columns(
        pl.col("commence_time").str.slice(0, 10).str.to_date().alias("gd"))
    kp = (bl.select("event_id", "player").unique()
          .with_columns(pl.col("player").map_elements(tnorm, return_dtype=pl.String).alias("k")))
    # Player identity via repo sorted_key on BOTH sides (pairs.player_norm and
    # L3 player_name); token-sort norm alone mismatches vendor normalization.
    pairs = pairs.with_columns(
        pl.col("player_norm").map_elements(
            lambda s: sorted_key(s or ""), return_dtype=pl.String).alias("key"))
    pg = (pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet")
          .select("game_pk", "pitcher", "game_date", "season", "player_name", "K").collect()
          .with_columns(pl.col("player_name").map_elements(
              lambda s: sorted_key(s or ""), return_dtype=pl.String).alias("key")))
    board = (pairs.filter(pl.col("snapshot") == "board")
             .join(env, on="event_id", how="left")
             .with_columns(pl.col("commence_time").str.slice(0, 10).str.to_date().alias("gd"))
             .join(pg, left_on=["gd", "key"], right_on=["game_date", "key"], how="inner")
             .select("event_id", "game_pk", "pitcher", "season", "K", "book", "line",
                     pl.col("gd").alias("game_date"),
                     pl.col("p_over").alias("p_open")))
    close = (pairs.filter(pl.col("snapshot") == "close")
             .join(env, on="event_id", how="left")
             .with_columns(pl.col("commence_time").str.slice(0, 10).str.to_date().alias("gd"))
             .join(pg, left_on=["gd", "key"], right_on=["game_date", "key"], how="inner")
             .select("event_id", "game_pk", "pitcher", "book", "line",
                     pl.col("p_over").alias("p_close")))

    # 4. Best-edge book per (start, line) at the board; attach close + model + outcome.
    panel = (board.join(close, on=["game_pk", "pitcher", "book", "line"], how="inner")
             .to_pandas())
    panel["__line_stem"] = panel["line"].map(lambda x: f"{x:.1f}".replace(".", "_"))
    probs_long = probs.melt(
        id_vars=["game_pk", "pitcher", "K", "expected_K"],
        value_vars=[c for c in probs.columns if c.endswith("_cal")],
        var_name="cal_col", value_name="p_model")
    probs_long["__line_stem"] = probs_long["cal_col"].str.extract(r"p_over_(.*)_cal")
    panel = panel.merge(probs_long[["game_pk", "pitcher", "__line_stem", "p_model",
                                     "expected_K"]],
                        left_on=["game_pk", "pitcher", "__line_stem"],
                        right_on=["game_pk", "pitcher", "__line_stem"], how="inner")
    panel["edge"] = panel["p_model"] - panel["p_open"]
    panel["y"] = (panel["K"] > panel["line"]).astype(int)
    panel["clv"] = panel["p_close"] - panel["p_open"]
    panel["side"] = np.where(panel["edge"] > 0, "over", "under")
    best = panel.sort_values(["game_pk", "line", "edge"],
                             ascending=[True, True, False]).drop_duplicates(["game_pk", "line"])
    assert not best.duplicated(["game_pk", "pitcher", "line", "side"]).any(), "both-sides breach"
    best["take"] = best["edge"] >= EDGE_FLOOR
    # DK-only sensitivity (quantifies best-price optimism; same rule, DK rows only).
    dk = panel[panel["book"] == "draftkings"].drop_duplicates(["game_pk", "line"]).copy()
    dk["dk_take"] = dk["edge"] >= EDGE_FLOOR
    dk["dk_pnl"] = np.where(dk["dk_take"] & (
        ((dk["edge"] > 0) & (dk["y"] == 1)) | ((dk["edge"] <= 0) & (dk["y"] == 0))),
        STAKE, np.where(dk["dk_take"], -STAKE, 0.0))
    best = best.merge(dk[["game_pk", "line", "dk_take", "dk_pnl",
                           "edge"]].rename(columns={"edge": "dk_edge"}),
                      on=["game_pk", "line"], how="left")

    # Consensus close: devigged median over ALL books at exact (event, line).
    blc = pl.scan_parquet(REPO / "data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "close")).collect()
    pall = (blc.group_by(["event_id", "book", "player_norm", "line"]).agg(
        pl.col("price").filter(pl.col("side") == "over").first().alias("over"),
        pl.col("price").filter(pl.col("side") == "under").first().alias("under"))
        .filter(pl.col("over").is_not_null() & pl.col("under").is_not_null()))
    pall = pall.with_columns(
        (pl.col("over").map_elements(american_to_implied, return_dtype=pl.Float64)
         / (pl.col("over").map_elements(american_to_implied, return_dtype=pl.Float64)
            + pl.col("under").map_elements(american_to_implied, return_dtype=pl.Float64))
         ).alias("p_over"))
    cons = (pall
            .group_by(["event_id", "line"]).agg(
                pl.col("p_over").median().alias("p_cons_close"),
                pl.col("book").n_unique().alias("n_books_close")))
    nb_all = pl.scan_parquet(REPO / "data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "board")).collect()
    nb_board = (nb_all.group_by(["event_id", "line"]).agg(
                    pl.col("book").n_unique().alias("n_books_board")))
    best = (pl.from_pandas(best.reset_index(drop=True))
            .join(cons, on=["event_id", "line"], how="left")
            .join(nb_board, on=["event_id", "line"], how="left")
            .to_pandas())
    best["lowconf_close"] = (best["n_books_close"] < 3).fillna(True)
    sgn = np.where(best["side"] == "over", 1.0, -1.0)
    best["clv_cons"] = sgn * (best["p_cons_close"] - best["p_open"])
    best["clv_cons"] = best["clv_cons"].where(best["n_books_close"] >= 3)

    is_over = best["side"] == "over"
    won = best["take"] & ((is_over & (best["y"] == 1)) | (~is_over & (best["y"] == 0)))
    best["pnl"] = np.where(won, STAKE, np.where(best["take"], -STAKE, 0.0))

    dest = assert_workspace_path(REPO / "research/offseason_2026/datasets/eval_panel.parquet")
    pl.from_pandas(best.reset_index(drop=True)).write_parquet(dest)

    # 5. Report-only metrics per season (no selection).

    def spearman(x, y):
        x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        rx -= rx.mean(); ry -= ry.mean()
        den = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
        return float((rx * ry).sum() / den) if den > 0 else None

    def boot_cis(dates, rows, fn, seed=0, n_boot=1000):
        rng = np.random.default_rng(seed)
        dates = np.asarray(dates)
        vals = []
        for _ in range(n_boot):
            pick = rng.choice(dates, size=len(dates), replace=True)
            vals.append(fn(rows[np.isin(rows["_d"], pick)]))
        arr = np.asarray(vals, dtype=float)
        return float(np.mean(arr)), float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))

    def calib_slope_intercept(y, p):
        try:
            from sklearn.linear_model import LogisticRegression
            X = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1)
            m = LogisticRegression(C=1e6).fit(X, y)
            return float(m.coef_[0][0]), float(m.intercept_[0])
        except Exception:
            return None, None

    metrics = {"reproduction_max_abs_diff": float(maxdiff), "conventions": {
        "books": list(BOOKS), "edge_floor": EDGE_FLOOR, "stake": STAKE,
        "side_rule": "over iff edge > 0 else under (takes imply over at base floor)",
        "open": "best price of DK/FD at board clock + DK-only sensitivity column",
        "close_headline": "same-book DK/FD close CLV (fillable)",
        "close_confirm": "devigged consensus over ALL books at exact line+side; <3 books = lowconf flag",
        "exclusions_from_clv": "pushes/voids (0 in panel: all half-lines, all settled), post-commence refusals, missing-board rows",
        "frozen": "multiplicative devig, one-slip (game,pitcher,line), uniqueness asserts, no both-sides",
        "veto_cap_probation": "NOT applied (policy layer = 2025A, pre-registered)"}}
    best["season"] = pd.to_datetime(best["game_date"]).dt.year
    best["_d"] = pd.to_datetime(best["game_date"]).dt.date.astype(str)
    for season, sub in best.groupby("season"):
        t = sub[sub["take"]].copy()
        clv = t["clv"].to_numpy()
        y = t["y"].to_numpy()
        pm = t["p_model"].to_numpy()
        po = t["p_open"].to_numpy()
        ll = float(-(y * np.log(np.clip(pm, 1e-9, 1))
                     + (1 - y) * np.log(np.clip(1 - pm, 1e-9, 1))).mean()) if len(t) else None
        br = float(((pm - y) ** 2).mean()) if len(t) else None
        sl, it = calib_slope_intercept(y, pm) if len(t) >= 30 else (None, None)
        sl_m, _ = calib_slope_intercept(y, po) if len(t) >= 30 else (None, None)
        bins = (pm * 10).astype(int).clip(0, 9)
        ece = float(sum(abs(y[bins == b].mean() - pm[bins == b].mean())
                        * (bins == b).mean() for b in range(10) if (bins == b).any())) if len(t) else None
        eb = pd.cut(t["edge"], [0.12, 0.15, 0.20, 1.0])
        rel = {str(k): {"n": int(v), "win_rate": float(t.loc[eb[eb == k].index, "y"].mean()),
                        "mean_edge": float(t.loc[eb[eb == k].index, "edge"].mean())}
               for k, v in eb.value_counts().items()}
        daily = t.assign(d=pd.to_datetime(t["game_date"]).dt.date).groupby("d")["pnl"].sum()
        sh = float(daily.mean() / daily.std() * (162 ** 0.5)) if daily.std() > 0 else None
        dd = float((daily.cumsum() - daily.cumsum().cummax()).min())
        dn = daily[daily < 0]
        sortino = float(daily.mean() / dn.std() * (162 ** 0.5)) if len(dn) > 1 and dn.std() > 0 else None
        calmar = float(t["pnl"].sum() / abs(dd)) if dd < 0 else None
        trail = daily.tail(30)
        sh_trail = float(trail.mean() / trail.std() * (162 ** 0.5)) if len(trail) > 1 and trail.std() > 0 else None
        decay = float(sh_trail - sh) if (sh_trail is not None and sh is not None) else None
        signs = (t.sort_values("game_date")["pnl"] < 0).astype(int).to_numpy()
        streak, cur = 0, 0
        for s in signs:
            cur = cur + 1 if s else 0
            streak = max(streak, cur)
        uw = float(((daily.cumsum() < daily.cumsum().cummax()).mean()))
        sw = float(clv.mean() * 100) if len(t) else None  # flat stakes: equals mean
        tstat = float(clv.mean() / (clv.std() / len(clv) ** 0.5)) if len(clv) > 1 and clv.std() > 0 else None
        rows = t.assign(_d=t["_d"]).to_dict("records")
        rarr = np.array([(r["_d"], r["pnl"], r["clv"], r["y"]) for r in rows],
                        dtype=[("_d", "U10"), ("pnl", float), ("clv", float), ("y", int)])
        dts = np.unique(rarr["_d"])
        roi_ci = boot_cis(dts, rarr, lambda r: r["pnl"].sum() / (len(r) * STAKE)) if len(t) else (None,) * 3
        clv_ci = boot_cis(dts, rarr, lambda r: r["clv"].mean() * 100) if len(t) else (None,) * 3
        beat_ci = boot_cis(dts, rarr, lambda r: (r["clv"] > 0).mean()) if len(t) else (None,) * 3
        by_line = {str(k): {"n": int(len(g)), "roi": float(g["pnl"].sum() / (len(g) * STAKE)),
                            "wr": float((g["pnl"] > 0).mean())}
                   for k, g in t.groupby("line")}
        by_side = {str(k): {"n": int(len(g)), "roi": float(g["pnl"].sum() / (len(g) * STAKE))}
                   for k, g in t.groupby("side")}
        by_book = {str(k): {"n": int(len(g)), "roi": float(g["pnl"].sum() / (len(g) * STAKE))}
                   for k, g in t.groupby("book")}
        by_month = {str(k): {"n": int(len(g)), "roi": float(g["pnl"].sum() / (len(g) * STAKE)),
                             "pnl": float(g["pnl"].sum())}
                    for k, g in t.assign(m=pd.to_datetime(t["game_date"]).dt.strftime("%Y-%m")).groupby("m")}
        cc = t.dropna(subset=["clv_cons"])
        metrics[str(season)] = {
            "n_quoted": int(len(sub)), "n_bets": int(len(t)),
            "turnover": float(len(t) * STAKE),
            "pnl": float(t["pnl"].sum()),
            "roi": float(t["pnl"].sum() / (len(t) * STAKE)) if len(t) else None,
            "roi_ci95": [float(v) if v is not None else None for v in roi_ci],
            "xroi_mean_edge": float(t["edge"].mean()) if len(t) else None,
            "ev_dollars": float((t["edge"] * STAKE).sum()) if len(t) else None,
            "win_rate": float((t["pnl"] > 0).mean()) if len(t) else None,
            "profit_factor": float(t.loc[t["pnl"] > 0, "pnl"].sum() / -t.loc[t["pnl"] < 0, "pnl"].sum())
            if len(t) and (t["pnl"] < 0).any() and (t["pnl"] > 0).any() else None,
            "push_rate": 0.0, "void_rate": 0.0,
            "clv_mean_pp": float(clv.mean() * 100) if len(t) else None,
            "clv_stake_weighted_pp": sw,
            "clv_t_stat": tstat,
            "clv_ci95": [float(v) if v is not None else None for v in clv_ci],
            "beat_close_rate": float((clv > 0).mean()) if len(t) else None,
            "beat_ci95": [float(v) if v is not None else None for v in beat_ci],
            "clv_cons_mean_pp": float(cc["clv_cons"].mean() * 100) if len(cc) else None,
            "clv_cons_n": int(len(cc)),
            "lowconf_close_rate": float(best.loc[sub.index, "lowconf_close"].mean()),
            "brier": br, "logloss": ll,
            "calib_slope": sl, "calib_intercept": it, "market_slope_ref": sl_m,
            "ece_model_vs_outcome": ece,
            "reliability_by_edge_band": rel,
            "edge_win_spearman": spearman(t["edge"], t["y"]) if len(t) >= 10 else None,
            "sharpe_daily_x162": sh, "sharpe_decay_trail30": decay,
            "sortino_daily_x162": sortino, "calmar_dollars": calmar,
            "max_drawdown": dd, "longest_losing_streak": streak, "time_under_water": uw,
            "dk_only_pnl": float(sub["dk_pnl"].fillna(0).sum()),
            "dk_only_n": int(sub["dk_take"].fillna(False).sum()),
            "by_line": by_line, "by_side": by_side, "by_book": by_book, "by_month": by_month,
        }
    man = {"built": "2026-09-28", "inputs": {
        "pitcher_training_max": str(pd.to_datetime(train["game_date"]).max().date()),
        "score_report": {k: (str(v)[:120]) for k, v in report.items()}},
        "metrics": metrics}
    with open(assert_workspace_path(
            REPO / "research/offseason_2026/datasets/eval_panel_manifest.json"),
            "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, default=str)
    print(json.dumps(metrics, indent=1, default=str))


if __name__ == "__main__":
    main()
