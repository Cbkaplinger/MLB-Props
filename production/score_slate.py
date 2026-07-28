"""Score today's slate with the frozen k-rate × TBF stack.

Thin ops wrapper around ``Models/Strikeout-Model/predict_slate.py`` so cron
jobs live under ``production/`` without duplicating scoring logic.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREDICT = ROOT / "Models" / "Strikeout-Model" / "predict_slate.py"


def main() -> None:
    if not PREDICT.is_file():
        raise SystemExit(f"Missing predictor script: {PREDICT}")
    # Forward CLI args after this script name.
    sys.argv = [str(PREDICT), *sys.argv[1:]]
    runpy.run_path(str(PREDICT), run_name="__main__")


if __name__ == "__main__":
    main()
