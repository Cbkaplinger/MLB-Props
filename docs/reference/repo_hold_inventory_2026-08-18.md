# Hold Inventory (2026-08-18)

This file tracks unresolved candidates from the repo-quality passthrough.
`hold` means the file/family is not deleted or moved until an explicit follow-up decision.

## Hold Candidates

| Path / Family | Why hold | Future-use signal | Risk if moved/deleted now |
|---|---|---|---|
| `analysis/` | Research narrative surface, non-runtime but still referenced by docs | Storytelling and model communication | medium |
| `playground/` | Ad-hoc scripts with uncertain reuse | Future what-if and calibration experiments | medium |
| `data/Odds-Open-Close-2025-2026/` | Source-like historical market snapshots | Backtests and open-line calibration studies | medium |
| `docs/archive/` | Historical provenance and superseded evidence | Auditability / manuscript references | high |
| `artifacts/notebook_exec/` | Generated notebook execution traces may be redundant | Repro/debug trail for notebook automation | medium |

## Decision Rule Reminder

- Promote from `hold` to `delete` only after dependency/reference check and smoke checks pass.
- Promote from `hold` to `keep` when active references or operational value are confirmed.
