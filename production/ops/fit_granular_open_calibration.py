"""Granular open-data calibration challenger (chrono-safe, research only).

Fits global / per-line / line-bucket isotonic (and global Platt) on early-open
2025–2026 rows using frozen live-ensemble raw P(over). Does NOT edit live
calibrators or KING_PROFILE.

Pre-registered selection: maximize late-open holdout Brier skill vs market.
Post-freeze KING metrics are scored once afterward as pure OOS — do not re-pick
by post-freeze ROI.

Example:
  python production/ops/fit_granular_open_calibration.py
  python production/ops/fit_granular_open_calibration.py --rebuild-cache
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES, over_threshold  # noqa: E402
from Python.live_assembly import (  # noqa: E402
    DEFAULT_KRATE_ENSEMBLE_CONFIG,
    score_frame,
)
from Python.market import american_to_decimal, devig_two_way  # noqa: E402
from Python.odds_ledger import dedupe_ledger_props, settled_bets  # noqa: E402
from Python.prob_calibration import p_over_col  # noqa: E402

OPEN_CSV = (
    ROOT
    / "data"
    / "Odds-Open-Close-2025-2026"
    / "pitcher_strikeouts_early_open_2025_2026.csv"
)
PITCHER_GAMES = config.PITCHER_GAMES_PATH
LEDGER = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
GRADED = ROOT / "artifacts" / "projection_log" / "graded.parquet"
CACHE = ROOT / "artifacts" / "odds_log" / "open_raw_p_over_blend_cache.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "granular_open_calibration_20260901.json"
OUT_REPORT = (
    ROOT / "docs" / "reference" / "reports" / "granular_open_calibration_2026-09-01.md"
)

FREEZE = date(2026, 8, 21)
HOLDOUT_START = date(2026, 5, 1)
MIN_N_LINE = 300
MIN_N_BUCKET = 500
LINES_MAIN = tuple(PROJECTION_K_LINES)


def _clip(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1.0 - 1e-6)


def _line_bucket(line: float) -> str:
    if line <= 3.5:
        return "low_le3_5"
    if line <= 5.5:
        return "mid_4_5_to_5_5"
    return "high_ge6_5"


def _y_over(actual_k: float, line: float) -> float:
    return 1.0 if float(actual_k) >= over_threshold(line) else 0.0


def _fit_iso(p: np.ndarray, y: np.ndarray) -> IsotonicRegression | None:
    p = _clip(p)
    y = np.asarray(y, dtype=np.float64)
    if len(p) < 100 or y.min() == y.max():
        return None
    iso = IsotonicRegression(y_min=1e-6, y_max=1.0 - 1e-6, out_of_bounds="clip")
    iso.fit(p, y)
    return iso


def _fit_platt(p: np.ndarray, y: np.ndarray) -> LogisticRegression | None:
    p = _clip(p)
    y = np.asarray(y, dtype=np.float64)
    if len(p) < 100 or y.min() == y.max():
        return None
    x = np.log(p / (1.0 - p)).reshape(-1, 1)
    clf = LogisticRegression(solver="lbfgs", max_iter=1000)
    clf.fit(x, y)
    return clf


def _apply_iso(cal: IsotonicRegression | None, p: np.ndarray) -> np.ndarray:
    p = _clip(p)
    if cal is None:
        return p
    return _clip(np.asarray(cal.predict(p), dtype=np.float64))


def _apply_platt(cal: LogisticRegression | None, p: np.ndarray) -> np.ndarray:
    p = _clip(p)
    if cal is None:
        return p
    x = np.log(p / (1.0 - p)).reshape(-1, 1)
    return _clip(cal.predict_proba(x)[:, 1])


def _prob_metrics(
    y: np.ndarray, p: np.ndarray, p_mkt: np.ndarray
) -> dict[str, float | int | None]:
    yv = np.asarray(y, dtype=np.float64)
    pm = _clip(p)
    pb = _clip(p_mkt)
    n = int(len(yv))
    if n < 20:
        return {
            "n": n,
            "brier": None,
            "ece": None,
            "brier_skill_vs_market": None,
            "logloss_skill_vs_market": None,
            "bias_pp": None,
        }
    brier = float(np.mean((pm - yv) ** 2))
    brier_m = float(np.mean((pb - yv) ** 2))
    ll = float(-np.mean(yv * np.log(pm) + (1.0 - yv) * np.log(1.0 - pm)))
    ll_m = float(-np.mean(yv * np.log(pb) + (1.0 - yv) * np.log(1.0 - pb)))
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for i in range(10):
        lo, hi = bins[i], bins[i + 1]
        mask = (pm >= lo) & (pm <= hi) if i == 9 else (pm >= lo) & (pm < hi)
        c = int(mask.sum())
        if c == 0:
            continue
        ece += abs(float(yv[mask].mean() - pm[mask].mean())) * (c / n)
    return {
        "n": n,
        "brier": round(brier, 5),
        "ece": round(float(ece), 5),
        "brier_skill_vs_market": round(1.0 - brier / brier_m, 4) if brier_m > 0 else None,
        "logloss_skill_vs_market": round(1.0 - ll / ll_m, 4) if ll_m > 0 else None,
        "bias_pp": round(100.0 * float(pm.mean() - yv.mean()), 2),
    }


@dataclass
class SegmentCal:
    name: str
    mode: str  # raw | global_iso | global_platt | segmented_iso
    global_iso: IsotonicRegression | None = None
    global_platt: LogisticRegression | None = None
    by_key_iso: dict[str, IsotonicRegression | None] = field(default_factory=dict)
    key_fn: Callable[[float], str] = field(default=lambda _ln: "all")
    min_n: int = 0


def fit_segment_cal(
    *,
    name: str,
    mode: str,
    p: np.ndarray,
    y: np.ndarray,
    lines: np.ndarray,
    key_fn: Callable[[float], str],
    min_n: int,
) -> SegmentCal:
    global_iso = _fit_iso(p, y)
    global_platt = _fit_platt(p, y)
    by_key: dict[str, IsotonicRegression | None] = {}
    if mode == "segmented_iso":
        for key in sorted({key_fn(float(x)) for x in lines}):
            m = np.array([key_fn(float(x)) == key for x in lines])
            by_key[key] = _fit_iso(p[m], y[m]) if int(m.sum()) >= min_n else None
    return SegmentCal(
        name=name,
        mode=mode,
        global_iso=global_iso,
        global_platt=global_platt,
        by_key_iso=by_key,
        key_fn=key_fn,
        min_n=min_n,
    )


def apply_segment_cal(cal: SegmentCal, p: np.ndarray, lines: np.ndarray) -> np.ndarray:
    if cal.mode == "raw":
        return _clip(p)
    if cal.mode == "global_platt":
        return _apply_platt(cal.global_platt, p)
    if cal.mode == "global_iso":
        return _apply_iso(cal.global_iso, p)
    out = np.empty(len(p), dtype=np.float64)
    base = _clip(p)
    for i, (pi, ln) in enumerate(zip(base, lines, strict=True)):
        key = cal.key_fn(float(ln))
        seg = cal.by_key_iso.get(key)
        if seg is not None:
            out[i] = float(_apply_iso(seg, np.array([pi]))[0])
        else:
            out[i] = float(_apply_iso(cal.global_iso, np.array([pi]))[0])
    return out


def build_open_cache(*, rebuild: bool) -> pl.DataFrame:
    if CACHE.exists() and not rebuild:
        return pl.read_parquet(CACHE)

    print("Building open raw-p cache via frozen ensemble score_frame…")
    opens = (
        pl.read_csv(OPEN_CSV, try_parse_dates=True, infer_schema_length=20000)
        .with_columns(
            pl.col("game_date").cast(pl.Utf8).str.to_date(strict=False).alias("game_date_d"),
            pl.col("pitcher_id").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("line").cast(pl.Float64),
            pl.col("over_odds").cast(pl.Float64),
            pl.col("under_odds").cast(pl.Float64),
            pl.col("fetched_at")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("fetched_at_ts"),
        )
        .filter(
            pl.col("game_date_d").is_not_null()
            & pl.col("pitcher_id_i").is_not_null()
            & pl.col("line").is_not_null()
            & pl.col("over_odds").is_not_null()
            & pl.col("under_odds").is_not_null()
            & pl.col("line").is_in(list(LINES_MAIN))
        )
        .sort("fetched_at_ts")
        .unique(
            subset=["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line"],
            keep="last",
        )
    )
    games = pl.read_parquet(PITCHER_GAMES).select(
        pl.col("game_date").cast(pl.Date).alias("game_date_d"),
        pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
        pl.col("K").cast(pl.Float64).alias("actual_k"),
    )
    open_joined = opens.join(games, on=["game_date_d", "pitcher_id_i"], how="inner")

    def _p_mkt(over: float, under: float) -> float:
        return float(devig_two_way(over, under)[0])

    market = (
        open_joined.with_columns(
            pl.struct(["over_odds", "under_odds"])
            .map_elements(
                lambda s: _p_mkt(float(s["over_odds"]), float(s["under_odds"])),
                return_dtype=pl.Float64,
            )
            .alias("p_mkt_over")
        )
        .group_by(["game_date_d", "pitcher_id_i", "line"])
        .agg(
            pl.col("actual_k").first(),
            pl.col("p_mkt_over").median().alias("p_mkt_over"),
            pl.len().alias("n_books"),
        )
    )

    keys = market.select(["game_date_d", "pitcher_id_i"]).unique()
    train = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
        )
        .join(keys, on=["game_date_d", "pitcher_id_i"], how="inner")
        .sort(["game_date_d", "pitcher_id_i"])
    )
    if train.is_empty():
        raise RuntimeError("No training rows matched open pitcher-games")

    scored_pd, report = score_frame(
        train.to_pandas(),
        calibration_path=False,
        krate_ensemble_config=DEFAULT_KRATE_ENSEMBLE_CONFIG,
        lines=LINES_MAIN,
    )
    scored = pl.from_pandas(scored_pd).with_columns(
        pl.col("game_date").cast(pl.Date).alias("game_date_d"),
        pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
    )
    p_cols = [p_over_col(ln, calibrated=False) for ln in LINES_MAIN]
    keep = ["game_date_d", "pitcher_id_i"]
    for c in ("k_rate_pred", "projected_tbf", "k_rate", "projected_tbf"):
        if c in scored.columns and c not in keep:
            keep.append(c)
    keep.extend([c for c in p_cols if c in scored.columns])
    scored = scored.select(keep).unique(subset=["game_date_d", "pitcher_id_i"], keep="last")
    scored_map = {
        (r["game_date_d"], r["pitcher_id_i"]): r for r in scored.iter_rows(named=True)
    }

    rows: list[dict[str, Any]] = []
    for r in market.iter_rows(named=True):
        key = (r["game_date_d"], r["pitcher_id_i"])
        s = scored_map.get(key)
        if s is None:
            continue
        line = float(r["line"])
        col = p_over_col(line, calibrated=False)
        if col not in s or s[col] is None:
            continue
        rows.append(
            {
                "game_date": r["game_date_d"],
                "pitcher_id": r["pitcher_id_i"],
                "line": line,
                "line_bucket": _line_bucket(line),
                "actual_k": float(r["actual_k"]),
                "y_over": _y_over(float(r["actual_k"]), line),
                "p_raw": float(s[col]),
                "p_mkt_over": float(r["p_mkt_over"]),
                "n_books": int(r["n_books"]),
            }
        )
    out = pl.DataFrame(rows).sort(["game_date", "pitcher_id", "line"])
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(CACHE)
    meta = {
        "n_rows": out.height,
        "date_min": str(out["game_date"].min()),
        "date_max": str(out["game_date"].max()),
        "score_report_keys": list(report.keys()) if isinstance(report, dict) else None,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    CACHE.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Cached {out.height} open rows → {CACHE}")
    return out


def _roi_summary(stakes: np.ndarray, pnls: np.ndarray) -> dict[str, Any]:
    stake = float(np.sum(stakes)) if len(stakes) else 0.0
    pnl = float(np.sum(pnls)) if len(pnls) else 0.0
    return {
        "n": int(len(stakes)),
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / stake, 4) if stake else None,
    }


def evaluate_postfreeze_king(cals: dict[str, SegmentCal]) -> dict[str, Any]:
    led = dedupe_ledger_props(settled_bets(pl.read_parquet(LEDGER))).with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("pitcher").cast(pl.Int64),
    )
    king = led.filter(
        (pl.col("game_date") > FREEZE)
        & (pl.col("passes_floor") == True)  # noqa: E712
        & (pl.col("stake") > 0)
    )
    graded = pl.read_parquet(GRADED).with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("pitcher").cast(pl.Int64),
    )
    p_cols = [
        c for c in graded.columns if c.startswith("p_over_") and not c.endswith("_cal")
    ]
    act_col = "actual_K" if "actual_K" in graded.columns else "actual_k"
    g = graded.select(["game_date", "pitcher", act_col] + p_cols)
    joined = king.join(g, on=["game_date", "pitcher"], how="left")

    fixed_rows: list[dict[str, Any]] = []
    for r in joined.iter_rows(named=True):
        line = float(r["line"])
        col = p_over_col(line, calibrated=False)
        if col not in r or r[col] is None:
            continue
        side = str(r["side"]).lower()
        try:
            po, pu = devig_two_way(float(r["over_price"]), float(r["under_price"]))
        except Exception:
            continue
        p_mkt = po if side == "over" else pu
        actual = r.get(act_col)
        if actual is None:
            res = str(r.get("result") or "").lower()
            if res not in {"win", "loss"}:
                continue
            won = res == "win"
            y_over = 1.0 if ((side == "over" and won) or (side == "under" and not won)) else 0.0
        else:
            y_over = _y_over(float(actual), line)
        y_side = y_over if side == "over" else 1.0 - y_over
        stake = float(r["stake"])
        if r.get("pnl") is not None:
            pnl = float(r["pnl"])
        else:
            price = int(r["bet_price"])
            pnl = (american_to_decimal(price) - 1.0) * stake if str(r["result"]).lower() == "win" else -stake
        fixed_rows.append(
            {
                "line": line,
                "side": side,
                "p_raw": float(r[col]),
                "p_model_live": float(r["p_model"]),
                "p_mkt": float(p_mkt),
                "y_over": float(y_over),
                "y_side": float(y_side),
                "stake": stake,
                "pnl": pnl,
            }
        )

    if not fixed_rows:
        return {"error": "no KING rows matched graded raw p_over", "schemes": {}}

    p_raw = np.array([x["p_raw"] for x in fixed_rows])
    lines = np.array([x["line"] for x in fixed_rows])
    sides = [x["side"] for x in fixed_rows]
    y_side = np.array([x["y_side"] for x in fixed_rows])
    p_mkt = np.array([x["p_mkt"] for x in fixed_rows])
    stakes = np.array([x["stake"] for x in fixed_rows])
    pnls = np.array([x["pnl"] for x in fixed_rows])
    p_live = np.array([x["p_model_live"] for x in fixed_rows])
    over_m = np.array([s == "over" for s in sides])
    under_m = ~over_m

    post = led.filter((pl.col("game_date") > FREEZE) & pl.col("edge").is_not_null())
    post = post.join(g, on=["game_date", "pitcher"], how="left")

    out: dict[str, Any] = {
        "n_king_matched": len(fixed_rows),
        "live_ticket_roi": _roi_summary(stakes, pnls),
        "schemes": {},
    }

    for name, cal in cals.items():
        p_cal = apply_segment_cal(cal, p_raw, lines)
        p_side = np.array(
            [pc if s == "over" else 1.0 - pc for pc, s in zip(p_cal, sides, strict=True)]
        )
        cf_stakes: list[float] = []
        cf_pnls: list[float] = []
        cf_over_n = 0
        for r in post.iter_rows(named=True):
            line = float(r["line"])
            col = p_over_col(line, calibrated=False)
            if col not in r or r[col] is None:
                continue
            side = str(r["side"]).lower()
            try:
                po, pu = devig_two_way(float(r["over_price"]), float(r["under_price"]))
            except Exception:
                continue
            p_m = po if side == "over" else pu
            pc = float(apply_segment_cal(cal, np.array([float(r[col])]), np.array([line]))[0])
            ps = pc if side == "over" else 1.0 - pc
            if (ps - float(p_m)) < 0.12:
                continue
            if r.get("result") is None:
                continue
            if r.get("stake") is not None and float(r["stake"]) > 0 and r.get("pnl") is not None:
                stake = float(r["stake"])
                pnl = float(r["pnl"])
            else:
                price = r.get("bet_price")
                if price is None:
                    continue
                stake = 1.0
                won = str(r["result"]).lower() == "win"
                pnl = (american_to_decimal(int(price)) - 1.0) if won else -1.0
            cf_stakes.append(stake)
            cf_pnls.append(pnl)
            if side == "over":
                cf_over_n += 1

        out["schemes"][name] = {
            "fixed_king_skill": _prob_metrics(y_side, p_side, p_mkt),
            "fixed_king_skill_over": _prob_metrics(y_side[over_m], p_side[over_m], p_mkt[over_m]),
            "fixed_king_skill_under": _prob_metrics(
                y_side[under_m], p_side[under_m], p_mkt[under_m]
            ),
            "fixed_king_live_p_model_skill": _prob_metrics(y_side, p_live, p_mkt),
            "counterfactual_floor_0_12": {
                **_roi_summary(np.array(cf_stakes), np.array(cf_pnls)),
                "n_over": cf_over_n,
                "note": "may include unit-stake imputed non-KING candidates; directional only",
            },
        }
    return out


def _md_metrics(m: dict[str, Any]) -> str:
    if not m or m.get("brier") is None:
        return f"n={m.get('n', 0)} (insufficient)"
    return (
        f"n={m['n']} brier={m['brier']} ece={m['ece']} "
        f"skill_brier={m['brier_skill_vs_market']} "
        f"skill_ll={m['logloss_skill_vs_market']} bias_pp={m['bias_pp']}"
    )


def write_report(payload: dict[str, Any]) -> None:
    hold = payload["holdout"]
    pick = payload["selected_scheme"]
    pf = payload["postfreeze"]
    lines_out = [
        "# Granular open calibration challenger",
        "",
        f"**Dated:** {payload['generated_at'][:10]}  ",
        "**Status:** research / shadow only — **no live calibrator or KING edit**.  ",
        f"**Pre-registered pick rule:** maximize late-open holdout "
        f"`brier_skill_vs_market` (start {HOLDOUT_START}).",
        "",
        "## Data",
        f"- Open cache rows: **{payload['open_n']}** "
        f"({payload['open_date_min']} → {payload['open_date_max']})",
        f"- Fit (pre-holdout): n={payload['fit_n']}",
        f"- Holdout: n={payload['holdout_n']}",
        f"- Frozen ensemble: `{DEFAULT_KRATE_ENSEMBLE_CONFIG.name}` (raw p_over)",
        "",
        "## Holdout metrics (selection universe)",
        "",
        "| Scheme | n | Brier skill vs mkt | Logloss skill | ECE | bias_pp |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, m in hold.items():
        lines_out.append(
            f"| {name} | {m.get('n')} | {m.get('brier_skill_vs_market')} | "
            f"{m.get('logloss_skill_vs_market')} | {m.get('ece')} | {m.get('bias_pp')} |"
        )
    lines_out += [
        "",
        f"**Selected by holdout skill:** `{pick}` "
        f"(skill={hold[pick].get('brier_skill_vs_market')}).",
        "",
        "### Holdout by line (selected scheme)",
        "",
        "| Line | metrics |",
        "| --- | --- |",
    ]
    for line, m in sorted(payload["holdout_by_line"].items(), key=lambda x: float(x[0])):
        lines_out.append(f"| {line} | {_md_metrics(m)} |")

    lines_out += [
        "",
        "## Post-freeze OOS (scored after selection — do not re-pick)",
        "",
        f"Fixed KING tickets matched to graded raw p_over: n={pf.get('n_king_matched')}. "
        f"Live ticket ROI: {pf.get('live_ticket_roi')}.",
        "",
        "| Scheme | fixed skill (all) | over skill | under skill | CF floor0.12 ROI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, block in pf.get("schemes", {}).items():
        fa = block["fixed_king_skill"]
        fo = block["fixed_king_skill_over"]
        fu = block["fixed_king_skill_under"]
        cf = block["counterfactual_floor_0_12"]
        lines_out.append(
            f"| {name} | skill={fa.get('brier_skill_vs_market')} ece={fa.get('ece')} | "
            f"{fo.get('brier_skill_vs_market')} | {fu.get('brier_skill_vs_market')} | "
            f"n={cf.get('n')} roi={cf.get('roi')} |"
        )

    live_skill = {}
    if pf.get("schemes"):
        live_skill = next(iter(pf["schemes"].values())).get(
            "fixed_king_live_p_model_skill", {}
        )
    lines_out += [
        "",
        "### Live `p_model` on same fixed KING set",
        _md_metrics(live_skill),
        "",
        "## Overfitting watch",
        "",
    ]
    for bullet in payload["overfit_flags"]:
        lines_out.append(f"- {bullet}")
    lines_out += ["", "## Questions for user (before any promote)", ""]
    for q in payload["questions"]:
        lines_out.append(f"- {q}")
    lines_out += [
        "",
        "## Reproduce",
        "```bash",
        "python production/ops/fit_granular_open_calibration.py",
        "```",
        "",
        f"Artifacts: `{OUT_JSON.relative_to(ROOT).as_posix()}`, "
        f"cache `{CACHE.relative_to(ROOT).as_posix()}`.",
        "",
    ]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines_out), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args()

    open_df = build_open_cache(rebuild=args.rebuild_cache)
    # normalize column names if cache used older schema
    rename = {}
    if "p_raw" not in open_df.columns and "p_over_raw" in open_df.columns:
        rename["p_over_raw"] = "p_raw"
    if "y_over" not in open_df.columns and "y" in open_df.columns:
        rename["y"] = "y_over"
    if "p_mkt_over" not in open_df.columns and "p_mkt" in open_df.columns:
        rename["p_mkt"] = "p_mkt_over"
    if rename:
        open_df = open_df.rename(rename)

    fit_df = open_df.filter(pl.col("game_date") < HOLDOUT_START)
    hold_df = open_df.filter(pl.col("game_date") >= HOLDOUT_START)
    if fit_df.height < 500 or hold_df.height < 200:
        raise RuntimeError(
            f"Insufficient chrono split: fit={fit_df.height} holdout={hold_df.height}"
        )

    p_fit = fit_df["p_raw"].to_numpy()
    y_fit = fit_df["y_over"].to_numpy()
    lines_fit = fit_df["line"].to_numpy()

    schemes = {
        "raw": fit_segment_cal(
            name="raw",
            mode="raw",
            p=p_fit,
            y=y_fit,
            lines=lines_fit,
            key_fn=lambda ln: "all",
            min_n=0,
        ),
        "global_isotonic": fit_segment_cal(
            name="global_isotonic",
            mode="global_iso",
            p=p_fit,
            y=y_fit,
            lines=lines_fit,
            key_fn=lambda ln: "all",
            min_n=0,
        ),
        "global_platt": fit_segment_cal(
            name="global_platt",
            mode="global_platt",
            p=p_fit,
            y=y_fit,
            lines=lines_fit,
            key_fn=lambda ln: "all",
            min_n=0,
        ),
        "line_isotonic": fit_segment_cal(
            name="line_isotonic",
            mode="segmented_iso",
            p=p_fit,
            y=y_fit,
            lines=lines_fit,
            key_fn=lambda ln: f"line_{ln}",
            min_n=MIN_N_LINE,
        ),
        "line_bucket_isotonic": fit_segment_cal(
            name="line_bucket_isotonic",
            mode="segmented_iso",
            p=p_fit,
            y=y_fit,
            lines=lines_fit,
            key_fn=_line_bucket,
            min_n=MIN_N_BUCKET,
        ),
    }

    p_h = hold_df["p_raw"].to_numpy()
    y_h = hold_df["y_over"].to_numpy()
    lines_h = hold_df["line"].to_numpy()
    mkt_h = hold_df["p_mkt_over"].to_numpy()

    hold_metrics: dict[str, dict[str, Any]] = {}
    for name, cal in schemes.items():
        hold_metrics[name] = _prob_metrics(
            y_h, apply_segment_cal(cal, p_h, lines_h), mkt_h
        )

    def skill_key(name: str) -> float:
        v = hold_metrics[name].get("brier_skill_vs_market")
        return float(v) if v is not None else -1e9

    selected = max(hold_metrics.keys(), key=skill_key)
    sel_cal = schemes[selected]
    p_sel = apply_segment_cal(sel_cal, p_h, lines_h)
    hold_by_line: dict[str, dict[str, Any]] = {}
    for line in sorted({float(x) for x in lines_h}):
        m = lines_h == line
        hold_by_line[str(line)] = _prob_metrics(y_h[m], p_sel[m], mkt_h[m])

    dates = fit_df["game_date"].to_list()
    unique_months = sorted({(d.year, d.month) for d in dates})
    cv_rows: list[dict[str, Any]] = []
    if len(unique_months) >= 4:
        for i in range(2, len(unique_months)):
            cut_y, cut_m = unique_months[i]
            cut = date(cut_y, cut_m, 1)
            next_m = cut_m + 1 if cut_m < 12 else 1
            next_y = cut_y if cut_m < 12 else cut_y + 1
            nxt = date(next_y, next_m, 1)
            tr = fit_df.filter(pl.col("game_date") < cut)
            te = fit_df.filter((pl.col("game_date") >= cut) & (pl.col("game_date") < nxt))
            if tr.height < 300 or te.height < 80:
                continue
            for label, mode, key_fn, min_n in (
                ("global_isotonic", "global_iso", lambda ln: "all", 0),
                ("line_isotonic", "segmented_iso", lambda ln: f"line_{ln}", MIN_N_LINE),
            ):
                cal = fit_segment_cal(
                    name=f"cv_{label}",
                    mode=mode,
                    p=tr["p_raw"].to_numpy(),
                    y=tr["y_over"].to_numpy(),
                    lines=tr["line"].to_numpy(),
                    key_fn=key_fn,
                    min_n=min_n,
                )
                pc = apply_segment_cal(cal, te["p_raw"].to_numpy(), te["line"].to_numpy())
                m = _prob_metrics(te["y_over"].to_numpy(), pc, te["p_mkt_over"].to_numpy())
                cv_rows.append({"month": f"{cut_y}-{cut_m:02d}", "scheme": label, **m})

    postfreeze = evaluate_postfreeze_king(schemes)

    flags: list[str] = []
    raw_s = hold_metrics["raw"].get("brier_skill_vs_market")
    line_s = hold_metrics["line_isotonic"].get("brier_skill_vs_market")
    glob_s = hold_metrics["global_isotonic"].get("brier_skill_vs_market")
    if (
        line_s is not None
        and glob_s is not None
        and raw_s is not None
        and (line_s - glob_s) < 0.005
        and (line_s - raw_s) < 0.01
    ):
        flags.append(
            "Line-isotonic holdout skill ≈ global — granular maps may be noise; "
            "prefer global or buckets."
        )
    if selected == "line_isotonic":
        n_seg = sum(1 for v in schemes["line_isotonic"].by_key_iso.values() if v is not None)
        flags.append(
            f"Selected line_isotonic with {n_seg} active line maps (min_n={MIN_N_LINE}); "
            "watch rare lines that fell back to global."
        )
    pf_roi = {
        k: (v.get("counterfactual_floor_0_12") or {}).get("roi")
        for k, v in postfreeze.get("schemes", {}).items()
    }
    pf_roi_valid = {k: v for k, v in pf_roi.items() if v is not None}
    if pf_roi_valid:
        roi_pick = max(pf_roi_valid.keys(), key=lambda k: float(pf_roi_valid[k]))
        if roi_pick != selected:
            flags.append(
                f"OVERFIT WATCH: post-freeze CF ROI would prefer `{roi_pick}` "
                f"(roi={pf_roi_valid[roi_pick]}) vs holdout pick `{selected}` — "
                "do NOT switch; holdout rule stands."
            )
        else:
            flags.append(
                f"Holdout pick `{selected}` agrees with post-freeze CF ROI leader "
                "(not a promote signal by itself)."
            )
    flags.append(
        "Frozen k-rate ensemble may have partially seen open-season games in train; "
        "calibrator chrono-split + post-freeze window remain the honest tests."
    )
    flags.append(
        "Calib challenger does not replace 4.5-over veto / asym floors — "
        "selection toxicity can remain."
    )

    questions = [
        f"Accept holdout-selected `{selected}`, force `line_bucket_isotonic` for stability, "
        "or stay on live global transfer map?",
        f"Is min_n={MIN_N_LINE} per line / {MIN_N_BUCKET} per bucket right, or raise further?",
        "Promote gate: require holdout skill > global by ≥X and post-freeze over skill not worse — what X?",
        "Apply new map under shadow only with current floors, or jointly with veto_4_5_over (separate A/B)?",
        "Rebuild full open→manual transfer stack with granular calib, or calib-only overlay on current p_raw?",
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "open_n": open_df.height,
        "open_date_min": str(open_df["game_date"].min()),
        "open_date_max": str(open_df["game_date"].max()),
        "fit_n": fit_df.height,
        "holdout_n": hold_df.height,
        "holdout_start": str(HOLDOUT_START),
        "min_n_line": MIN_N_LINE,
        "min_n_bucket": MIN_N_BUCKET,
        "holdout": hold_metrics,
        "holdout_by_line": hold_by_line,
        "selected_scheme": selected,
        "chrono_cv_monthly": cv_rows,
        "postfreeze": postfreeze,
        "overfit_flags": flags,
        "questions": questions,
        "line_isotonic_active_keys": [
            k for k, v in schemes["line_isotonic"].by_key_iso.items() if v is not None
        ],
        "bucket_isotonic_active_keys": [
            k for k, v in schemes["line_bucket_isotonic"].by_key_iso.items() if v is not None
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_report(payload)
    print(f"Selected (holdout): {selected}")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
