# bf-2026-predictor-seal-v1 - seal-dir doc mirror

The seal package itself lives in the external research lake
(`<external-lake>\bf-2026-predictor-seal-v1\`,
status PREPARED-NOT-SEALED) and its payload files are write-once
hash-pinned there. This directory mirrors ONLY the additive metadata
documents so they are durably committed in the repo:

- `CLASSIFICATION.md` - labels the current 134-row payload
  PILOT-REPRODUCTION; hashes preserved; pilot usable-B membership
  (11/123) comes from the PILOT package, never from the seal
  re-stamped arm flags.
- `READY_BRIEF.md` - registered-fit feasibility brief for the single
  fit through 2025-12-31 (calibration ending 2025-09-28): frozen
  procedure, leakage-free window implementation, verdict
  (deterministic execution) and the decisions to pin before execution.

These mirrors are byte-identical copies of the seal-dir files
(sha256-verified at copy time, 2026-10-14). The seal directory remains
the source of record; if the copies ever diverge, the seal-dir files
win and the divergence must be reported, not silently re-synced.
