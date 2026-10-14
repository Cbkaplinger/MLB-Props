"""Repo-layout import-path fix for the committed pregame-pa-ext-v1 copies.

The frozen predictor payload stays at its stable external lake path (see
manifest.json payload.sha256); only the code is committed to the repo. This
conftest resolves paext_core from the committed scripts dir and points
core.PAYLOAD at the external payload before the test module imports it.
No test or scoring logic is changed.
"""
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORK / "scripts"))

import paext_core as core  # noqa: E402

core.PAYLOAD = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1"
    r"\data\predictor_payload.parquet"
)
