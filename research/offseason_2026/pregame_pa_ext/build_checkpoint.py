"""One-time frozen-checkpoint reconstruction for pregame-pa-ext-v2.

Separates RECONSTRUCTION from ADAPTER EXECUTION (owner instruction):
this script runs ONCE against the private lake, deterministically refits
the frozen H3-raw recipe per block, verifies the refit against the stored
overnight-p2 preds checkpoints at <=1e-8, and serializes the VERIFIED
coefficients to a sha256-pinned JSON artifact. The adapter
(pregame_pa_ext.adapter) loads ONLY that serialized artifact afterwards --
it never refits, never reconstructs, and fails loud with
MISSING_CHECKPOINT_ARTIFACT when the artifact is absent.

Run (private lake required; never runs in CI):

    python research/offseason_2026/pregame_pa_ext/build_checkpoint.py

Override the lake paths with PREGAME_STATE_V1_DIR / OVERNIGHT_P2_DIR /
PAEXT_V2_OUT_DIR / PAEXT_V2_CHECKPOINT_PATH (same env names the adapter
uses). Re-running overwrites only via an explicit --force (the artifact is
otherwise write-once).
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pregame_pa_ext import adapter as ad  # noqa: E402

BLOCK_TRAIN_END = {
    "block_2024H2": (2024, 6, 30),
    "block_2025H1": (2024, 12, 31),
    "confirm_2025H2": (2025, 6, 30),
}


def build_feature_frame(pa: pl.DataFrame) -> pl.DataFrame:
    """Frozen strictly-prior feature frame over realized PAs (the exact
    fit-side lineage formerly inlined in the adapter's run_real)."""
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    realized = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).sort("game_date")
    feat = ad.attach_prior_features(realized, p_daily, b_daily, lg)
    feat = feat.join(pa.select("game_pk", "at_bat_number", "batter", "y"),
                     on=["game_pk", "at_bat_number", "batter"], how="inner")
    # day-1 league state is 0/0 (NaN) in any PA table; the frozen fits
    # start 2023-01-01, long after league history exists, so drop the
    # non-finite league rows from fit frames only (never silently in the
    # projected path, where the cutoff gate already guarantees a finite
    # asof league rate).
    return feat.filter(pl.col("lg_rate").is_finite())


def reconstruct(
    pa: pl.DataFrame,
    out_path: Path,
    preds_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Deterministic refit + <=1e-8 verification + sha256-pinned
    serialization of the frozen H3-raw checkpoint. Raises (STOP) when the
    verification gate fails; refuses to overwrite an existing artifact
    unless --force."""
    out_path = Path(out_path)
    if out_path.exists() and not force:
        raise ad.AdapterError(
            f"write-once violation: checkpoint artifact exists: {out_path} "
            "(pass --force to replace it deliberately)")
    feat = build_feature_frame(pa)
    models = {}
    for block, (te_y, te_m, te_d) in BLOCK_TRAIN_END.items():
        cal_last = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        )["game_date"].max()
        cal_first = cal_last - timedelta(days=59)
        train = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") < cal_first))
        cal = feat.filter(
            (pl.col("game_date") >= cal_first)
            & (pl.col("game_date") <= cal_last))
        models[block] = ad.fit_models_from_frames(train, cal)
    verification = ad.verify_checkpoint(
        models, feat, preds_dir or (ad.OVERNIGHT_P2_DIR / "data"))
    written = ad.serialize_checkpoint(models, verification, out_path)
    models_loaded, meta = ad.load_serialized_checkpoint(written)
    if {b: sorted(m.items()) for b, m in models.items()} != \
            {b: sorted(m.items()) for b, m in models_loaded.items()}:
        raise ad.AdapterError(
            "round-trip mismatch: serialized artifact does not reproduce "
            "the verified coefficients")
    return {
        "artifact": str(written),
        "sha256": meta["sha256"],
        "verification": verification,
        "n_fit_rows": feat.height,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ad.CHECKPOINT_PATH),
                    help="output JSON artifact path (default: "
                         "PAEXT_V2_CHECKPOINT_PATH)")
    ap.add_argument("--force", action="store_true",
                    help="allow replacing an existing artifact")
    args = ap.parse_args(argv)
    pa = ad.load_pa_table()
    report = reconstruct(pa, Path(args.out), force=args.force)
    print("frozen checkpoint reconstructed, verified, and serialized")
    for block, v in report["verification"].items():
        print(f"  {block}: n_rows={v['n_rows']} "
              f"max_abs_diff={v['max_abs_diff']:.3e}")
    print(f"  artifact: {report['artifact']}")
    print(f"  sha256: {report['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
