"""Novig probe tests: keyless skip, resolver wiring, tick write (no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "novig_probe",
        ROOT / "production" / "ops" / "market_research" / "novig_probe.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["novig_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


np = _load()


class _FakeClient:
    def __init__(self, markets):
        self._markets = markets

    def open_markets(self, market_type="PITCHER_STRIKEOUTS"):
        return self._markets


def _recs(tmp_path: Path, rows: list[dict]):
    import polars as pl

    d = tmp_path / "odds"
    d.mkdir()
    base = {"game_date": "2026-09-23", "recommendation": "BET"}
    pl.DataFrame([{**base, **r} for r in rows]).write_parquet(d / "recommendations.parquet")
    return d


def test_no_key_skips_clean(monkeypatch) -> None:
    monkeypatch.delenv("NOVIG_CLIENT_ID", raising=False)
    monkeypatch.delenv("NOVIG_CLIENT_SECRET", raising=False)
    try:
        np.probe(slate="2026-09-23", qa=True)
        raise AssertionError("expected NovigAuthError")
    except Exception as exc:
        assert "NOVIG_CLIENT_ID" in str(exc)


def test_probe_resolves_and_writes(monkeypatch, tmp_path) -> None:
    import polars as pl

    d = _recs(tmp_path, [
        {"player_name": "Max Fried", "line": 5.5, "best_side": "under"},
        {"player_name": "Ghost Arm", "line": 9.5, "best_side": "over"},
    ])
    monkeypatch.setattr(np, "ODDS_DIR", d)
    markets = [{"marketId": "m1", "player": "Max Fried", "line": 5.5,
                "outcomes": [{"side": "under", "outcomeId": "o1"}]}]
    ticks, audit = np.probe(slate="2026-09-23", qa=True,
                            client=_FakeClient(markets))
    # Fake returns the same market for both K market types (K + outs scan).
    assert audit == {"n_signals": 2, "n_markets": 2, "n_available": 1}
    by_name = {t["player_name"]: t for t in ticks}
    assert by_name["Max Fried"]["available"] is True
    assert by_name["Max Fried"]["outcome_id"] == "o1"
    assert by_name["Ghost Arm"]["available"] is False
    path = np.write_ticks(ticks, slate="2026-09-23", out_dir=tmp_path)
    assert path.name == "novig_ticks_2026-09-23.parquet"
    assert pl.read_parquet(path).height == 2


def test_kalshi_soft_fail_never_raises(monkeypatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "kalshi_k_reader",
        ROOT / "production" / "ops" / "market_research" / "kalshi_k_reader.py")
    assert spec is not None and spec.loader is not None
    kr = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_k_reader"] = kr
    spec.loader.exec_module(kr)

    def _boom(*a, **k):
        raise RuntimeError("vendor down")

    monkeypatch.setattr(kr, "fetch_open_k_events", _boom)
    monkeypatch.setattr(sys, "argv", ["kalshi_k_reader.py", "--soft-fail"])
    kr.main()  # must not raise
    assert "KALSHI-SOFT" in capsys.readouterr().out
