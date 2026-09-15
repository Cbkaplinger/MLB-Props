# src/Python — shared library (model math + ledger + market)

## Purpose

Importable code both production scripts and research share. Frozen where it
matters (model stems), living where it must (ops helpers).

## Map

| Module | Role |
|---|---|
| `market.py` | Devig, edge, Kelly, CLV, `bet_pnl` — the ONE money function; unit anchor |
| `count_layer.py` | Poisson (live default) / binomial count families, `COUNT_LAYER_FAMILY_DEFAULT` |
| `prob_calibration.py` | WS1c per-line Platt maps + bundle pointer |
| `odds_board.py` | Board scoring (floors/veto/cap/lean/exposure/game-cap) |
| `odds_ledger.py` | Atomic parquet writes, `dedupe_ledger_props` (canonical), replace/append, settle/void |
| `real_bets.py` | Append-only real-money ledger (priced rows only, never zeros) |
| `sharp_odds.py` | SharpAPI client (env key, 6s self-throttle, shared-fetch) |
| `live_assembly.py` | Frozen bundle loader (krate 20260803 + TBF 20260728 stems, sha-pinned) |
| `config.py` | Paths via `MLB_PROPS_*_DIR` env overrides (cloud points these at the volume) |
| `pipeline/` | L2/L3 rolling + training joins (age/kadj/command extends, gated) |
| `statcast.py`, `rolling.py`, `training.py` | Savant fetch, rolling windows, LightGBM/Ridge fits |

## Rules

- Odds never enter the trainer (product/market split is load-bearing).
- `dedupe_ledger_props` is canonical — every money number rides it.
- Atomic writes everywhere (`atomic_write_parquet/text`); sidecars scoped by path.
- Tests: `tests/` pins legacy defaults + live-stack drift (update pin with
  approved change, same commit).
