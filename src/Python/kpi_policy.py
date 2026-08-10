"""Load dynamic KPI and quality-gate policy from JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Python import config

DEFAULT_POLICY_PATH = config.PROJECT_ROOT / "production" / "ops" / "kpi_policy.json"

DEFAULT_POLICY: dict[str, Any] = {
    "kpi": {
        "min_joined": 100,
        "mae_k_rate_warn": 0.075,
        "abs_under_tbf_bias_warn": 1.5,
        "worst_tier_mae_warn": 0.078,
        "abs_long_rest_bias_warn": 3.0,
        "long_rest_min_n": 8,
        "chrono_min_dates": 24,
        "warn_persist_snapshots": 3,
    },
    "quality_gate": {
        "dynamic_min_edge": {
            "base": 0.12,
            "elevated": 0.14,
            "elevated_when_n_warn_gte": 2,
        },
        "rules": {
            "block_matchup_tier": True,
            "matchup_tiers_blocked": ["avg_matchup", "favorable_matchup"],
            "block_under_long_rest": True,
            "under_long_rest_min_days": 10,
            "block_edge_below_min": True,
        },
    },
    "state_actions": {
        "healthy_max_warn": 1,
        "caution_max_warn": 3,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in override.items():
        cur = out.get(key)
        if isinstance(cur, dict) and isinstance(value, dict):
            out[key] = _deep_merge(cur, value)
        else:
            out[key] = value
    return out


def load_kpi_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Return merged KPI policy (defaults with optional JSON overrides)."""
    policy_path = Path(path) if path else DEFAULT_POLICY_PATH
    if not policy_path.exists():
        return DEFAULT_POLICY
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_POLICY
    if not isinstance(payload, dict):
        return DEFAULT_POLICY
    return _deep_merge(DEFAULT_POLICY, payload)

