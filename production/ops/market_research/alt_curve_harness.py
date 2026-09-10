"""Alt-curve harness — curve-shape scorer, 39-day panel (post hoc, shadow).

Per graded start with actual_K: OUR p_over_2.5-9.5 (raw + cal) vs BOOK
alt-close fair-over (devig-median per book pair) at every alt line offered.
Per-line: n, our Brier, book Brier, skill, bias, ECE + shape summary
(mean |our-book| gap per start; tail behavior).

Writes artifacts/odds_log/alt_curve_report.json. No live change.
Kill (backlog #16): no shape insight beyond single-line Brier.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text, norm_player_name  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from analyze_book_skill import _devig_pair  # noqa: E402

HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def col(line: float, cal: bool = False) -> str:
    stem = str(line).replace(".", "_")
    return f"p_over_{stem}_cal" if cal else f"p_over_{stem}"


def book_curve(snapshot: str = "close") -> pl.DataFrame:
    """Per (gd, player, line) book over-prob from alt closes.

    NOTE: alt markets are over-ONLY (no under leg), so fair devig is
    impossible — probs are vig-loaded single-price implicits (median across
    books). Absolute Brier comparisons flatter the model; the verdict-grade
    metrics are shape/gap ones (mean |our-book| gap, rank correlation).
    """
    from Python.market import american_to_implied_prob  # noqa: E402
    alt = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts_alternate")
        & (pl.col("snapshot") == snapshot)
        & (pl.col("side") == "over")).collect()
    rows = []
    for r in alt.to_dicts():
        try:
            ip = american_to_implied_prob(float(r["price"]))
        except (TypeError, ValueError):
            continue
        rows.append({"event_id": r["event_id"], "player_norm": r["player_norm"],
                     "line": float(r["line"]), "fair_over": ip})
    pf = pl.DataFrame(rows)
    agg = pf.group_by(["event_id", "player_norm", "line"]).agg(
        pl.col("fair_over").median().alias("book_over"),
        pl.len().alias("n_books")).sort(["event_id", "player_norm", "line"])
    evdate: dict[str, str] = {}
    for fp in sorted((HIST / "raw" / "event_index").glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ev in d.get("data", d.get("events", [])):
            if isinstance(ev, dict) and ev.get("id"):
                ct = str(ev.get("commence_time", ""))[:10]
                if ct:
                    evdate[ev["id"]] = ct
    return agg.with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""), return_dtype=pl.Utf8).alias("gd"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", default="close")
    args = ap.parse_args()

    bc = book_curve(args.snapshot)
    g = pl.read_parquet(ODDS_DIR.parent / "projection_log" / "graded.parquet").filter(
        pl.col("has_actual") & pl.col("actual_K").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: " ".join(sorted(norm_player_name(str(s)).split())),
            return_dtype=pl.Utf8).alias("key"))
    bc = bc.with_columns(
        pl.col("player_norm").map_elements(
            lambda s: " ".join(sorted(str(s).split())), return_dtype=pl.Utf8).alias("key"))
    print(f"graded starts w/ actuals: {g.height} (set-based joins; sorted keys both sides)")

    per_line: dict[float, dict] = {}
    gaps: list[float] = []
    for ln in LINES:
        c, cc = col(ln), col(ln, True)
        if c not in g.columns:
            continue
        ours = g.select(["gd", "key", "actual_K", c, cc]).filter(
            pl.col(c).is_not_null()).with_columns(
            (pl.col("actual_K").cast(pl.Float64) > ln).cast(pl.Float64).alias("y"),
            pl.lit(ln).alias("line")).rename({c: "p", cc: "pcal"})
        pts = ours.join(bc.select(["gd", "key", "line", "book_over"]).filter(
            pl.col("line") == ln), on=["gd", "key", "line"], how="inner")
        if pts.height == 0:
            continue
        ys = pts["y"].to_numpy()
        ps = pts["p"].to_numpy()
        bs = pts["book_over"].to_numpy()
        e_raw, _ = expected_calibration_error(ys, ps)
        e_book, _ = expected_calibration_error(ys, bs)
        entry: dict = {"line": ln, "n": pts.height,
                       "brier_ours": float(np.mean((ps - ys) ** 2)),
                       "brier_book": float(np.mean((bs - ys) ** 2)),
                       "ece_ours": float(e_raw), "ece_book": float(e_book),
                       "bias_ours_pp": float(100 * (ps.mean() - ys.mean())),
                       "bias_book_pp": float(100 * (bs.mean() - ys.mean())),
                       "mean_abs_gap": float(np.mean(np.abs(ps - bs)))}
        entry["skill"] = entry["brier_book"] - entry["brier_ours"]
        ok = pts.filter(pl.col("pcal").is_not_null())
        if ok.height:
            entry["brier_ours_cal"] = float(np.mean((ok["pcal"].to_numpy() - ok["y"].to_numpy()) ** 2))
        per_line[ln] = entry
        gaps.extend(np.abs(ps - bs).tolist())

    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "snapshot": args.snapshot, "n_starts": g.height,
           "per_line": [per_line[ln] for ln in sorted(per_line)],
           "mean_abs_gap_all": float(np.mean(gaps)) if gaps else None,
           "kill": "SURVIVE-shape"}
    out = ODDS_DIR / "alt_curve_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    for v in rep["per_line"]:
        print("line=%.1f n=%d ours=%.4f book=%.4f skill=%+.4f bias_o=%+.1fpp bias_b=%+.1fpp gap=%.3f" % (
            v["line"], v["n"], v["brier_ours"], v["brier_book"], v["skill"],
            v["bias_ours_pp"], v["bias_book_pp"], v["mean_abs_gap"]))
    print(f"mean_abs_gap_all={rep['mean_abs_gap_all']:.4f} kill={rep['kill']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
