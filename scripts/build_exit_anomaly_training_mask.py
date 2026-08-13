"""Build a reusable training-mask artifact from exit anomaly overrides.

Output columns:
- game_pk
- pitcher
- game_date
- exit_anomaly_flag
- exit_anomaly_type
- exit_anomaly_confidence
- exit_anomaly_source
- include_for_training
"""

from __future__ import annotations

from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.exit_anomalies import (
    KEY_COLS,
    add_training_mask,
    apply_exit_anomaly_overrides,
    load_exit_anomaly_overrides,
    normalize_anomaly_keys,
)


def main() -> None:
    root = ROOT
    graded_path = root / "artifacts" / "projection_log" / "graded.parquet"
    out_path = root / "artifacts" / "projection_log" / "exit_anomaly_training_mask.parquet"

    if not graded_path.exists():
        raise FileNotFoundError(f"Missing {graded_path}. Run grading flow first.")

    graded = pl.read_parquet(graded_path).select(
        [c for c in ["game_pk", "pitcher", "game_date", "player_name"] if c in pl.read_parquet(graded_path, n_rows=1).columns]
    )
    graded_keys = normalize_anomaly_keys(graded).select([c for c in KEY_COLS if c in graded.columns]).unique()
    overrides = load_exit_anomaly_overrides()
    tagged = apply_exit_anomaly_overrides(graded)
    mask = add_training_mask(tagged).select(
        [c for c in [
            "game_pk",
            "pitcher",
            "game_date",
            "player_name",
            "exit_anomaly_flag",
            "exit_anomaly_type",
            "exit_anomaly_confidence",
            "exit_anomaly_source",
            "note",
            "include_for_training",
        ] if c in tagged.columns or c == "include_for_training"]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mask.write_parquet(out_path)

    summary = (
        mask.group_by("include_for_training")
        .agg(pl.len().alias("n_rows"))
        .sort("include_for_training")
    )
    print(f"wrote {out_path}")
    print(summary)
    if overrides.is_empty():
        print("No exit_anomaly_overrides rows found.")
    else:
        join_keys = [c for c in KEY_COLS if c in overrides.columns and c in graded_keys.columns]
        unmatched = overrides.join(graded_keys, on=join_keys, how="anti") if join_keys else overrides
        print(f"overrides_rows={overrides.height} matched_rows={overrides.height - unmatched.height} unmatched_rows={unmatched.height}")
        if unmatched.height:
            print("Unmatched overrides (check game_pk/pitcher/game_date keys):")
            print(unmatched)


if __name__ == "__main__":
    main()
