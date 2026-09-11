"""Player age table via MLBAM bulk DOB (one-time pull, cached).

Reads data/dimensions/player_id_map.parquet (mlb_id, player_name),
batches personIds x100 against statsapi /people, writes
data/dimensions/player_ages.parquet (mlb_id, birth_date; ignored? no —
small static CSV-style dimension, stays tracked like sibling map).
Age-as-of computed downstream (WS2-age).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "data" / "dimensions" / "player_id_map.parquet"
OUT = ROOT / "data" / "dimensions" / "player_ages.parquet"


def fetch(ids: list[int]) -> list[dict]:
    u = ("https://statsapi.mlb.com/api/v1/people?personIds=" + ",".join(map(str, ids))
         + "&fields=people,id,fullName,birthDate")
    with urllib.request.urlopen(u, timeout=30) as r:
        return json.load(r).get("people", [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    m = pl.read_parquet(MAP).select(["mlb_id"]).unique()
    ids = [int(x) for x in m["mlb_id"].to_list() if x is not None]
    print(f"ids: {len(ids)}")
    rows: list[dict] = []
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            got = fetch(chunk)
        except Exception as e:
            print(f"chunk {i}: {str(e)[:100]}")
            continue
        rows.extend({"mlb_id": p["id"], "birth_date": p.get("birthDate", "")} for p in got)
        print(f"chunk {i}: {len(got)}/{len(chunk)}")
    pl.DataFrame(rows).write_parquet(OUT)
    print(f"wrote {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
