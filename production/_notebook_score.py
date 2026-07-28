"""One-shot daily board scorer for the notebook (fresh process).

Jupyter on Windows can AV inside LightGBM after module reloads; running this
script in a subprocess matches the working terminal path. Writes a single
temporary pickle path provided on the CLI (caller deletes it).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import pickle
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.count_layer import PROJECTION_K_LINES  # noqa: E402
from Python.daily_lineups import build_daily_slate  # noqa: E402
from Python.live_assembly import (  # noqa: E402
    build_live_feature_frame,
    daily_projection_board,
    score_frame,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_pickle", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    sink = io.StringIO()
    cm = contextlib.redirect_stdout(sink) if args.quiet else contextlib.nullcontext()

    with cm:
        slate = build_daily_slate(
            game_date=args.date,
            require_probable_match=False,
        )
        features, build_meta = build_live_feature_frame(
            slate,
            allow_stale=args.allow_stale,
            dual_starters=True,
        )
        scored, report = score_frame(features, lines=PROJECTION_K_LINES)
        board = daily_projection_board(
            scored,
            lines=PROJECTION_K_LINES,
            preferred_only=False,
        )
        preferred = daily_projection_board(
            scored,
            lines=PROJECTION_K_LINES,
            preferred_only=True,
        )

    # Surface a short disagreement summary even when quiet.
    n_dis = int(build_meta.get("n_disagreement_rows") or 0)
    warnings = sink.getvalue() if args.quiet else ""
    payload = {
        "board": board,
        "preferred": preferred,
        "build_meta": build_meta,
        "report": report,
        "lines": list(PROJECTION_K_LINES),
        "n_disagreement_rows": n_dis,
        "warning_excerpt": warnings[:500] if warnings else "",
    }
    args.out_pickle.parent.mkdir(parents=True, exist_ok=True)
    args.out_pickle.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == "__main__":
    main()
