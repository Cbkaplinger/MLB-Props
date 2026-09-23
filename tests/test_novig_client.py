"""Novig framework tests: auth plumbing, resolver, token cache (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import Python.novig_client as nv  # noqa: E402


def test_missing_creds_fail_closed_loud(monkeypatch) -> None:
    monkeypatch.delenv("NOVIG_CLIENT_ID", raising=False)
    monkeypatch.delenv("NOVIG_CLIENT_SECRET", raising=False)
    try:
        nv.load_config()
        raise AssertionError("expected NovigAuthError")
    except nv.NovigAuthError as exc:
        assert "Modal Secret" in str(exc) and "chat" in str(exc)


def test_qa_vs_prod_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("NOVIG_CLIENT_ID", "id")
    monkeypatch.setenv("NOVIG_CLIENT_SECRET", "sec")
    qa = nv.load_config(qa=True)
    assert qa.api_base.startswith("https://api-qa.novig.us")
    prod = nv.load_config(qa=False)
    assert prod.api_base == "https://api.novig.us/nbx/v2"


def test_resolve_market_matches_player_line_side() -> None:
    markets = [
        {"marketId": "m1", "player": "Max Fried", "line": 5.5,
         "outcomes": [{"side": "under", "outcomeId": "o1"},
                      {"side": "over", "outcomeId": "o2"}]},
        {"marketId": "m2", "player": "Taj Bradley", "line": 6.5,
         "outcomes": [{"side": "over", "outcomeId": "o3"}]},
    ]
    hit = nv.resolve_market(markets, player_name="max  fried", line=5.5,
                            side="UNDER")
    assert hit is not None and hit["market_id"] == "m1"
    assert hit["outcome_id"] == "o1"
    assert nv.resolve_market(markets, player_name="Max Fried", line=6.5,
                             side="under") is None
    assert nv.resolve_market(markets, player_name="Nobody", line=5.5,
                             side="under") is None


def test_token_cached_until_ttl(monkeypatch) -> None:
    monkeypatch.setenv("NOVIG_CLIENT_ID", "id")
    monkeypatch.setenv("NOVIG_CLIENT_SECRET", "sec")
    client = nv.NovigClient(nv.load_config())
    calls = {"n": 0}

    def fake_post(url, payload, headers=None):
        calls["n"] += 1
        assert "sec" not in str(payload.get("client_id"))
        return {"access_token": "tok123"}

    monkeypatch.setattr(client, "_post_json", fake_post)
    assert client.token() == "tok123"
    assert client.token() == "tok123"  # cached, no second mint
    assert calls["n"] == 1
    client._token_exp = 0.0  # force expiry
    assert client.token() == "tok123"
    assert calls["n"] == 2


def test_place_order_blocked_until_stage3() -> None:
    try:
        nv.place_order()
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass
