"""Fetch MLB birthdates for training pitchers and cache them.

Uses the official people endpoint already used for names. Age is not in
``player_id_map``; this builds a separate dimension for research screens.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import polars as pl

from Python import config

MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
OUT_PATH = config.DATA_DIR / "dimensions" / "player_birthdates.parquet"


def fetch_birthdates(player_ids: tuple[int, ...], *, timeout: float = 30.0) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for start in range(0, len(player_ids), 100):
        chunk = player_ids[start : start + 100]
        query = urlencode({"personIds": ",".join(map(str, chunk))})
        with urlopen(f"{MLB_PEOPLE_URL}?{query}", timeout=timeout) as response:
            payload = json.load(response)
        for person in payload.get("people", []):
            mlb_id = person.get("id")
            birth = person.get("birthDate")
            if mlb_id is None or not birth:
                continue
            rows.append({"mlb_id": int(mlb_id), "birth_date": birth})
    if not rows:
        return pl.DataFrame(schema={"mlb_id": pl.Int64, "birth_date": pl.Date})
    return (
        pl.DataFrame(rows)
        .with_columns(pl.col("birth_date").str.to_date())
        .unique(subset=["mlb_id"], keep="first")
        .sort("mlb_id")
    )


def main() -> None:
    training = pl.read_parquet(config.PITCHER_TRAINING_PATH)
    ids = tuple(sorted(int(x) for x in training["pitcher"].unique().to_list()))
    print(f"Fetching birthdates for {len(ids)} pitchers...")
    births = fetch_birthdates(ids)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    births.write_parquet(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({births.height} rows, null-free)")
    coverage = births.height / max(len(ids), 1)
    print(f"Coverage: {coverage:.1%}")


if __name__ == "__main__":
    main()
