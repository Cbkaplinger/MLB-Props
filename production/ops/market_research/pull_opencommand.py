"""Pull open-command per-pitch layer from HF (research stage, NC compliant).

Files per season (2024/2025/2026): pbp_info.csv.gz + targets.csv.gz
(~170MB/season) into ignored data/Open-Command/<year>/. Skips present files
(resume). Camera poses + glove tracks NOT pulled (unneeded for start
aggregates). CC BY-NC-SA 4.0: research/exploration only.

Usage: python production/ops/market_research/pull_opencommand.py [--years 2024,2025,2026]
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "https://huggingface.co/datasets/tomdoyo/open-command/resolve/main"
OUT = ROOT / "data" / "Open-Command"
FILES = ["pbp_info.csv.gz", "targets.csv.gz"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2024,2025,2026")
    args = ap.parse_args()
    for year in [y.strip() for y in args.years.split(",") if y.strip()]:
        d = OUT / year
        d.mkdir(parents=True, exist_ok=True)
        for f in FILES:
            dst = d / f
            if dst.exists() and dst.stat().st_size > 0:
                print(f"{year}/{f}: present ({dst.stat().st_size // 1024 // 1024}MB), skip")
                continue
            url = f"{BASE}/{year}/{f}"
            print(f"{year}/{f}: downloading...")
            urllib.request.urlretrieve(url, dst)
            print(f"{year}/{f}: ok ({dst.stat().st_size // 1024 // 1024}MB)")


if __name__ == "__main__":
    main()
