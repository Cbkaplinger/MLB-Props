"""Tests for ntfy send retries (a lost page = a lost recommendation)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "production" / "ops"))

import send_morning_alert as sma


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("NTFY_URL", raising=False)
    calls: list = []

    def flaky(req, timeout=15):
        calls.append(1)
        if len(calls) < 2:
            raise OSError("blip")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    monkeypatch.setattr(sma.time, "sleep", lambda s: None)
    ok, info = sma._send_ntfy("hi")
    assert ok is True and info == "ntfy_status=200" and len(calls) == 2


def test_send_gives_up_after_retries(monkeypatch) -> None:
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("NTFY_URL", raising=False)
    calls: list = []

    def dead(req, timeout=15):
        calls.append(1)
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", dead)
    monkeypatch.setattr(sma.time, "sleep", lambda s: None)
    ok, info = sma._send_ntfy("hi", retries=3)
    assert ok is False and info.startswith("ntfy_error=") and len(calls) == 3


def test_send_missing_env_no_calls(monkeypatch) -> None:
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("NTFY_URL", raising=False)
    called: list = []
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: called.append(1) or _Resp())
    assert sma._send_ntfy("hi") == (False, "ntfy_env_missing")
    assert called == []
