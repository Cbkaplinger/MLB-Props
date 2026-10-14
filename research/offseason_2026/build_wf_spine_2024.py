"""Build the unfiltered WF feature spine (seasons 2023+2024, min PA 0).

Redirects every pipeline output path to the research directory so the
parked repo's data/processed artifacts are never touched. Public API
only (games.run min_batters_faced=0); no production code is edited.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

RESEARCH = Path(r"C:\Users\ckaplinger\MLB-Props-Research")
SPINE = RESEARCH / "wf_spine_2024"

sys.path.insert(0, "src")

from Python import config  # noqa: E402
from Python.pipeline import games, rolling, training  # noqa: E402

SPINE.mkdir(parents=True, exist_ok=True)
_REDIRECT = {
    "PITCHER_GAMES_PATH": "pitcher_games.parquet",
    "PITCH_TYPE_GAMES_PATH": "pitch_type_games.parquet",
    "BATTER_GAMES_PATH": "batter_games.parquet",
    "BULLPEN_TEAM_GAMES_PATH": "bullpen_team_games.parquet",
    "BULLPEN_APPEARANCES_PATH": "bullpen_appearances.parquet",
    "PITCHER_ROLLING_PATH": "pitcher_rolling.parquet",
    "BATTER_ROLLING_PATH": "batter_rolling.parquet",
    "PITCHER_TRAINING_PATH": "pitcher_training.parquet",
    "BATTER_TRAINING_PATH": "batter_training.parquet",
    "PARK_FACTORS_PATH": "park_factors.parquet",
}
for attr, name in _REDIRECT.items():
    setattr(config, attr, SPINE / name)


def main() -> None:
    t0 = time.time()
    print("L1 games (2023+2024, min_batters_faced=0) ...", flush=True)
    paths = games.run((2023, 2024), min_batters_faced=0,
                      refresh_player_map=False)
    for name, path in paths.items():
        print(f"  {name}: {path.name}", flush=True)
    print(f"L1 done {time.time()-t0:.0f}s", flush=True)

    print("L2 rolling ...", flush=True)
    out = rolling.run()
    for name, path in out.items():
        print(f"  {name}: {path.name}", flush=True)
    print(f"L2 done {time.time()-t0:.0f}s", flush=True)

    print("L3 training frames ...", flush=True)
    out = training.run()
    for name, path in out.items():
        print(f"  {name}: {path.name}", flush=True)
    print(f"ALL DONE {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
