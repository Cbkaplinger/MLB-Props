# Validation lanes and lineup-version logging (Phase 7.5 specification — no execution)

## Lane definitions

| Lane | Lineup source | Opportunity | Availability evidence | Permitted claims |
|---|---|---|---|---|
| A. Conditional PA probability | Actual batter faced | Observed PA (label rows) | Historical (Statcast realized PAs), 2023–24 | Matchup probability quality. NOT board-time replay. |
| B. Oracle aggregation | Actual PA sequence | Actual TBF | Historical (same rows), reconciled 4,711 starts | K-model diagnostic; matchup vs opportunity error decomposition. Never actionable. |
| C. Historical-initial-lineup sensitivity | `is_initial_lineup` (realized initial 9) | **Frozen predicted TBF** | Historical (all years), but lineup availability at wager time UNVERIFIED | Pregame-style sensitivity: tests opportunity integration without pretending lineups were known. Labeled "lineup availability unverified". |
| D. Board-time replay | Timestamped projected lineup (`fetched_at` ≤ wager ts) | Frozen predicted TBF | 2026-ONLY: 6 RG snapshots, ~2 true pre-tip; `lineup_status` logged only since 2026-09-15 | Historically actionable replay on the thin snapshot set ONLY; never a full-season deployability claim. |

Unsupported assumptions to avoid: treating lane C as lane D; full-season 2026 deployability from
thin snapshots; actual-TBF results as pregame results.

## 2025 implication

No 2025 projected-lineup snapshots exist and none can be reconstructed (no fetch logging before
2026-09-15). Therefore the clean 2025 frozen-model comparison runs on lane A/B evidence (model
validation) plus lane C (pregame-style opportunity sensitivity, clearly labeled), while lane D
waits for logged snapshots (2026 thin set, 2027 definitive).

## Lineup-version logging (specification only — implementation deferred; propose starting at
spring 2027 reactivation while the app is stopped)

Log on every board pull, append-only:
- `fetched_at` (UTC, first-seen and every refresh)
- `source` / version (RG scrape id, MLB probable ID)
- `lineup_status` (confirmed / projected)
- slots 1–9: player name + resolved MLBAM ID + resolution method
- board-time snapshot reference (file/row hash)
- prediction-time feature/model identity (feature_manifest_hash, model_id)

This makes lane D measurable for 2027 and removes the provenance gap that currently blocks
historical deployability claims.
