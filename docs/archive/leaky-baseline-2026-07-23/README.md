# Superseded overlapping-split baseline

This directory preserves the Mean and Ridge results captured on 2026-07-23
before the chronological splitter was corrected. The row-index split divided
boundary dates across partitions: training ended on 2025-04-15 and validation
and test both included 2025-07-06.

These metrics are process history, not valid current model evidence. The first
splitter-corrected replacement was the 227-feature, 2025-consulting evaluation
at `artifacts/models/lightgbm_krate_20260723_202255.*`; it is now also
historical. The active 248-feature 2023-2024 development baseline is documented
in `docs/PAPER_NOTES.md` and `docs/model-card.md`, with model metadata at
`artifacts/models/lightgbm_krate_20260724_165215.*`.

`GIT_STATE.txt` is retained only to document the state that generated the
superseded run.
