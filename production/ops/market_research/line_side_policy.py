"""Line x side policy: 2025-select cells, 2026-judge once (measurement).

Pre-registered rule (fixed here, no fit): on 2025 juiced taken, TAKE a
(line, side) cell in 2026 iff 2025 cell ROI > 0 AND n >= 30. Champion base
(floor/cap/veto/lean/DKFD) stays underneath; cells only subtract.
Judge once on 2026 vs champion-on-2026. Kill: judge ROI <= champion ROI.
Label: confirmatory (2026 peeked before) -- October re-judge decides.

Reads: juiced_replay_candidates.parquet.
Writes: artifacts/odds_log/line_side_policy_report.json. No live change.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT = REPO / "artifacts" / "odds_log" / "line_side_policy_report.json"

MIN_N = 30


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    st = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pn = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    return {"n": n, "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None}


def main() -> None:
    taken = (pl.read_parquet(CAND)
             .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"])).to_dicts())
    y25 = [r for r in taken if str(r.get("yr")) == "2025"]
    y26 = [r for r in taken if str(r.get("yr")) == "2026"]
    cells25: dict[str, list] = {}
    for r in y25:
        cells25.setdefault(f"{r['side']}@{float(r['line'])}", []).append(r)
    take = {c for c, v in cells25.items()
            if len(v) >= MIN_N and stats(v)["roi"] is not None and stats(v)["roi"] > 0}
    kept26 = [r for r in y26 if f"{r['side']}@{float(r['line'])}" in take]
    champ26 = stats(y26)
    gated26 = stats(kept26)
    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rule": f"take cell iff 2025 ROI>0 and n>={MIN_N} (pre-registered, no fit)",
        "cells_2025": {c: stats(v) for c, v in sorted(cells25.items())},
        "take_cells": sorted(take),
        "drop_cells": sorted(set(cells25) - take),
        "champion_2026": champ26,
        "gated_2026": gated26,
        "roi_delta_gated_minus_champ": round(gated26["roi"] - champ26["roi"], 4)
        if gated26["roi"] is not None and champ26["roi"] is not None else None,
        "label": "confirmatory (2026 peeked); October re-judge decides",
        "kill": "SURVIVE (proposal next)"
        if gated26["roi"] is not None and champ26["roi"] is not None and gated26["roi"] > champ26["roi"]
        else "KILL (cells add nothing over the champion)",
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: v for k, v in rep.items() if k != "cells_2025"}, indent=2))
    for c, s in sorted(rep["cells_2025"].items()):
        print(f"  2025 {c}: n={s['n']} ROI={s['roi']}")


if __name__ == "__main__":
    main()
