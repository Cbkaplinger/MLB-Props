"""P1 repair: paired slate-date bootstrap uncertainty for the overnight-p2 ladder.

Repairs the previously reported uncertainty (reports/pooled_comparison.json,
reports/ladder_results.json) for the H3-vs-LOG5 and H3-vs-H0 (B_logreg)
comparisons:

Repair 1 (paired draws). The original code drew a fresh rng per comparison and
per arm, so intervals across arms were not paired at the draw level. Here one
set of slate-date draws per block per replicate is shared by every arm of every
comparison (arms live in the same frame, so each sampled row enters every arm).

Repair 2 (block-stratified pooled resampling). The original pooled bootstrap
pooled all 281 dev slate dates into one unstratified pool, letting a replicate
draw arbitrary date counts per development block. Here each replicate draws
n_dates_of_block dates WITHIN each dev block (2024H1 / 2024H2 / 2025H1) and
then combines the sampled rows row-weighted across blocks.

Estimand (unchanged, preserved): row-weighted log loss = sum of per-row losses
/ count of rows over all sampled-date rows. Per sampled slate date the block
contributes its loss_sum and n_rows (ALL rows of the date, rows never
thinned). Pooled replicate statistic = (sum of loss_sums) / (sum of n_rows)
across blocks. Point estimate = same estimand on the full data.

Seed 20261001, 2000 replicates, percentile 95% interval [2.5, 97.5].
confirm_2025H2 is never loaded (dev blocks only), matching the original
pooled comparison.

Usage:
    python research/offseason_2026/run_paired_uncertainty.py \
        --data-dir <dir-with-preds-block-*.parquet> \
        --out <results.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

EPS = 1e-15
SEED = 20261001
N_BOOT = 2000

ARMS = {
    "H3": "pred_H3_raw",
    "LOG5": "pred_LOG5_raw",
    "H0": "pred_B_logreg_raw",
}

# Dev-block assessment windows (owner-ruled v3 boundaries, run_ladder.py).
BLOCK_WINDOWS = {
    "block_2024H1": ("2024-01-01", "2024-06-30"),
    "block_2024H2": ("2024-07-01", "2024-12-31"),
    "block_2025H1": ("2025-01-01", "2025-06-30"),
}
COMPARISONS = [("H3", "LOG5"), ("H3", "H0")]


def log_loss_terms(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1.0 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def load_preds_block(path: Path) -> pl.DataFrame:
    """Load one dev-block preds parquet with fail-loud validation."""
    if not path.exists():
        raise FileNotFoundError(f"missing preds parquet: {path}")
    df = pl.read_parquet(path)
    required = ["game_pk", "at_bat_number", "batter", "game_date", "y"]
    missing = [c for c in required if c not in df.columns]
    missing += [c for c in ARMS.values() if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing required columns {missing}")
    dup = df.group_by(["game_pk", "at_bat_number", "batter"]).len().filter(pl.col("len") > 1)
    if dup.height > 0:
        raise ValueError(f"{path.name}: {dup.height} duplicate arm keys "
                         "(game_pk, at_bat_number, batter)")
    if df.filter(pl.col("game_date").is_null()).height > 0:
        raise ValueError(f"{path.name}: rows with null game_date (missing slate dates)")
    if df.filter(pl.col("y").is_null()).height > 0:
        raise ValueError(f"{path.name}: rows with null y")
    for col in ARMS.values():
        if df.filter(pl.col(col).is_null()).height > 0:
            raise ValueError(f"{path.name}: rows with null {col}")
    return df


def enforce_window(df: pl.DataFrame, block: str, path: Path) -> pl.DataFrame:
    lo, hi = BLOCK_WINDOWS[block]
    out = df.filter((pl.col("game_date") >= pl.date(*(int(x) for x in lo.split("-")))) &
                    (pl.col("game_date") <= pl.date(*(int(x) for x in hi.split("-")))))
    dropped = df.height - out.height
    if dropped > 0:
        raise ValueError(f"{path.name}: {dropped} rows outside declared assessment "
                         f"window {lo}..{hi} (missing slate dates)")
    if out.height == 0:
        raise ValueError(f"{path.name}: no rows inside assessment window {lo}..{hi}")
    return out


def date_tables(df: pl.DataFrame) -> dict:
    """Per-slate-date loss_sum / n_rows per arm (all rows of a date kept)."""
    y = df["y"].to_numpy().astype(np.int64)
    uniq, inv = np.unique(df["game_date"].to_numpy(), return_inverse=True)
    tables = {}
    for arm, col in ARMS.items():
        loss = log_loss_terms(y, df[col].to_numpy())
        tables[arm] = {
            "loss_sum": np.bincount(inv, weights=loss),
            "n_rows": np.bincount(inv).astype(np.float64),
        }
    return {"dates": uniq, "arm_tables": tables}


def draw_date_indices(rng: np.random.Generator, n_dates_by_block: dict,
                      n_boot: int) -> dict:
    """One draw per block per replicate, shared by all arms (stratified)."""
    draws = {}
    for block, n_dates in n_dates_by_block.items():
        draws[block] = rng.integers(0, n_dates, size=(n_boot, n_dates))
    return draws


def replicate_stats(draws: dict, tables_by_block: dict) -> dict:
    """Row-weighted pooled numerator/denominator per arm per replicate."""
    num = {arm: np.zeros(next(iter(draws.values())).shape[0]) for arm in ARMS}
    den = np.zeros(next(iter(draws.values())).shape[0])
    for block, idx in draws.items():
        tabs = tables_by_block[block]["arm_tables"]
        for arm in ARMS:
            num[arm] += tabs[arm]["loss_sum"][idx].sum(axis=1)
        den += tabs["H3"]["n_rows"][idx].sum(axis=1)
    return {"num": num, "den": den}


def point_estimates(tables_by_block: dict) -> dict:
    tot = {arm: 0.0 for arm in ARMS}
    n = 0
    for block, t in tables_by_block.items():
        for arm in ARMS:
            tot[arm] += float(t["arm_tables"][arm]["loss_sum"].sum())
        n += int(t["arm_tables"]["H3"]["n_rows"].sum())
    ll = {arm: tot[arm] / n for arm in ARMS}
    return {"ll": ll, "rows": n,
            "diff": {(a, b): ll[a] - ll[b] for a, b in COMPARISONS}}


def run_paired_uncertainty(data_dir: Path, seed: int = SEED,
                           n_boot: int = N_BOOT) -> dict:
    tables_by_block = {}
    meta = {}
    for block in BLOCK_WINDOWS:
        path = data_dir / f"preds_{block}.parquet"
        df = enforce_window(load_preds_block(path), block, path)
        tables_by_block[block] = date_tables(df)
        meta[block] = {"rows": df.height, "dates": df["game_date"].n_unique(),
                       "path": str(path)}

    draws = draw_date_indices(
        np.random.default_rng(seed),
        {b: len(t["dates"]) for b, t in tables_by_block.items()},
        n_boot,
    )
    stats = replicate_stats(draws, tables_by_block)
    pts = point_estimates(tables_by_block)

    # per-block replicates (same draws, restricted to that block)
    per_block_ci = {}
    for block, idx in draws.items():
        tabs = tables_by_block[block]["arm_tables"]
        den_b = tabs["H3"]["n_rows"][idx].sum(axis=1)
        per_block_ci[block] = {}
        for arm in ARMS:
            per_block_ci[block][arm] = tabs[arm]["loss_sum"][idx].sum(axis=1) / den_b

    results = {
        "method": "paired slate-date bootstrap, block-stratified, row-weighted",
        "seed": seed, "n_boot": n_boot,
        "estimand": "sum of per-row log losses / count of rows over all "
                    "sampled-date rows (rows never thinned)",
        "interval": "percentile 2.5/97.5",
        "arms": ARMS,
        "blocks": {},
        "pooled": {"rows": pts["rows"], "dates": sum(m["dates"] for m in meta.values()),
                   "ll": pts["ll"]},
        "comparisons": [],
    }
    for block in BLOCK_WINDOWS:
        m = meta[block]
        tabs = tables_by_block[block]["arm_tables"]
        results["blocks"][block] = {
            "rows": m["rows"], "dates": m["dates"],
            "ll": {arm: float(tabs[arm]["loss_sum"].sum()
                              / tabs[arm]["n_rows"].sum())
                   for arm in ARMS},
        }
    for a, b in COMPARISONS:
        row = {"pair": f"{a}_vs_{b}"}
        for block in BLOCK_WINDOWS:
            reps = per_block_ci[block][a] - per_block_ci[block][b]
            d_pt = (results["blocks"][block]["ll"][a]
                    - results["blocks"][block]["ll"][b])
            row[block] = {
                "paired_estimate": float(d_pt),
                "ci95": [float(np.percentile(reps, 2.5)),
                         float(np.percentile(reps, 97.5))],
            }
        reps = (stats["num"][a] - stats["num"][b]) / stats["den"]
        row["pooled"] = {
            "paired_estimate": float(pts["diff"][(a, b)]),
            "ci95": [float(np.percentile(reps, 2.5)),
                     float(np.percentile(reps, 97.5))],
        }
        results["comparisons"].append(row)
    results["_block_meta"] = meta
    return results


def format_table(results: dict) -> str:
    lines = ["| metric | block | rows | dates | pair | paired estimate (dLL) | 95% CI |",
             "|---|---|---|---|---|---|---|"]
    for comp in results["comparisons"]:
        pair = comp["pair"]
        for block in list(BLOCK_WINDOWS) + ["pooled"]:
            m = comp[block]
            where = results["blocks"][block] if block != "pooled" else results["pooled"]
            lines.append(
                f"| log_loss_pa | {block} | {where['rows']} | {where['dates']} "
                f"| {pair} | {m['paired_estimate']:+.7f} "
                f"| [{m['ci95'][0]:+.7f}, {m['ci95'][1]:+.7f}] |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    args = ap.parse_args()
    results = run_paired_uncertainty(args.data_dir, seed=args.seed, n_boot=args.n_boot)
    results.pop("_block_meta", None)
    table = format_table(results)
    print(table)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
