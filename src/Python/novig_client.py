"""Novig NBX exchange framework, Stage 0/1 (owner 2026-09-23).

Docs: https://docs.novig.com (NBX API: OAuth2 client-credentials, REST
``https://api.novig.us/nbx/v2``, QA ``https://api-qa.novig.us``).

What this module does (NO order placement — Stage 3+ only):
- Stage 0: credential plumbing. ``NOVIG_CLIENT_ID`` + ``NOVIG_CLIENT_SECRET``
  from env (Modal Secret ``mlb-props-keys`` in prod, ``.env`` laptop-only).
  Missing creds = loud fail-closed ``NovigAuthError`` (the one place
  fail-closed is correct: no key, no calls). Secrets never logged.
- Stage 1 (read-only): mint/cached OAuth tokens (30-min TTL), list open MLB
  markets (``PITCHER_STRIKEOUTS``/``PITCHER_OUTS``), resolve our ticket
  (player + line + side) to a Novig market/outcome, normalize a paper tick.

Staging: (2) QA/paper loop, (3) $5 shadow, (4) $50 IOC — each needs its own
explicit owner order. ``place_order`` intentionally raises until Stage 3.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PROD_API = "https://api.novig.us/nbx/v2"
QA_API = "https://api-qa.novig.us/nbx/v2"
PROD_AUTH = "https://auth.novig.us/oauth/token"
QA_AUTH = "https://auth-qa.novig.us/oauth/token"
PROD_AUDIENCE = "https://api.novig.us"
QA_AUDIENCE = "https://api-qa.novig.us"
TOKEN_TTL_S = 30 * 60

K_MARKET_TYPES = ("PITCHER_STRIKEOUTS", "PITCHER_OUTS")


class NovigAuthError(RuntimeError):
    """No credentials — wire NOVIG_CLIENT_ID/SECRET, then retry."""


def _redact(mapping: dict) -> dict:
    out = dict(mapping)
    for k in ("client_secret", "clientSecret", "token", "access_token"):
        if k in out:
            out[k] = "***"
    return out


@dataclass
class NovigConfig:
    client_id: str
    client_secret: str
    qa: bool = True

    @property
    def api_base(self) -> str:
        return QA_API if self.qa else PROD_API

    @property
    def auth_url(self) -> str:
        return QA_AUTH if self.qa else PROD_AUTH

    @property
    def audience(self) -> str:
        return QA_AUDIENCE if self.qa else PROD_AUDIENCE


def load_config(*, qa: bool = True) -> NovigConfig:
    """Read credentials from env. Raises NovigAuthError when absent."""
    cid = os.getenv("NOVIG_CLIENT_ID", "").strip()
    sec = os.getenv("NOVIG_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise NovigAuthError(
            "NOVIG_CLIENT_ID / NOVIG_CLIENT_SECRET not set. "
            "Prod: add both to the Modal Secret 'mlb-props-keys'. "
            "Laptop: add both to .env (gitignored, local-only). "
            "Keys never go in chat, code, or the repo.")
    return NovigConfig(client_id=cid, client_secret=sec, qa=qa)


class NovigClient:
    """Thin NBX REST client (read-only until Stage 3)."""

    def __init__(self, config: NovigConfig, timeout_s: float = 5.0):
        self.config = config
        self.timeout_s = timeout_s
        self._token = ""
        self._token_exp = 0.0

    def _post_json(self, url: str, payload: dict,
                   headers: dict | None = None) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"novig POST failed (redacted={_redact(payload)}): {exc!r}")

    def _get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=self._auth_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"novig GET failed: {url.split('?')[0]}: {exc!r}")

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    def token(self) -> str:
        """Mint-once OAuth token, refreshed past TTL (never logged)."""
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        body = self._post_json(self.config.auth_url, {
            "audience": self.config.audience,
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        })
        token = str(body.get("access_token") or body.get("token") or "")
        if not token:
            raise NovigAuthError("token endpoint returned no access_token")
        self._token = token
        self._token_exp = time.time() + TOKEN_TTL_S
        return token

    def open_markets(self, *, league: str = "MLB",
                     market_type: str = "PITCHER_STRIKEOUTS") -> list[dict]:
        """List open markets (read-only, Stage 1)."""
        out = self._get_json(
            f"{self.config.api_base}/emm/markets/open"
            f"?league={league}&marketType={market_type}")
        return out if isinstance(out, list) else []


def norm_name(name: str) -> str:
    return " ".join(str(name or "").lower().split())


def resolve_market(markets: list[dict], *, player_name: str, line: float,
                   side: str) -> dict | None:
    """Match our ticket to one open Novig market/outcome (pure, testable).

    Matches on normalized player + line within 1e-9; returns the market with
    the outcome id for ``side`` when present, else None (no fill there).
    """
    want = norm_name(player_name)
    try:
        want_line = float(line)
    except (TypeError, ValueError):
        return None
    for m in markets:
        try:
            if norm_name(m.get("player") or m.get("playerName") or "") != want:
                continue
            if abs(float(m.get("line")) - want_line) > 1e-9:
                continue
        except (TypeError, ValueError, KeyError):
            continue
        outcomes = m.get("outcomes") or m.get("sides") or []
        for o in outcomes:
            if str(o.get("side") or "").lower() == str(side or "").lower():
                return {"market_id": m.get("marketId") or m.get("id"),
                        "outcome_id": o.get("outcomeId") or o.get("id"),
                        "market": m, "outcome": o}
        return {"market_id": m.get("marketId") or m.get("id"),
                "outcome_id": None, "market": m, "outcome": None}
    return None


def place_order(*args, **kwargs) -> None:
    """Stage 3+ only — intentionally unimplemented (owner 2026-09-23)."""
    raise NotImplementedError(
        "order placement needs the Stage-3 owner order ($5 shadow first).")
