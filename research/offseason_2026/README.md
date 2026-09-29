# research/offseason_2026 — bounded challenger workspace

Question: can a PA-level K-rate challenger beat the frozen champion on identical
observations, prices, lines, timestamps, and policies?
Gates: Gates 1–6 (audit §AF). Status: SCAFFOLD ONLY — specs + funnel manifest;
no model, no CV, no 2026 run. Frozen comparator untouched.

Boundaries (audit §AF, enforced by `boundary.py` + `tests/test_offseason_workspace_boundary.py`):
- Import canonical prod modules where safe (`market`, `count_layer`,
  `prob_calibration`-read, `odds_ledger`-read only).
- Adapters required for board builder, live assembly, slate/modal chains.
- NEVER import writers/pagers/scheduler (see `FORBIDDEN_MODULES`).
- Write only beneath this directory. Never to ledgers, pointers, volumes.
- Refer to frozen artifacts via manifests, never copy binaries or prod files.
- No `.env` keys, no API calls. Repro: decisions entry → hashes → one command.

Boundary-test result: recorded in choice log Phase 4 entry (see final report).
