# Superseded overlapping-split baseline

This directory preserves the Mean and Ridge results captured on 2026-07-23
before the chronological splitter was corrected. The row-index split divided
boundary dates across partitions: training ended on 2025-04-15 and validation
and test both included 2025-07-06.

These metrics are process history, not valid current model evidence. The
replacement is the date-disjoint 227-feature evaluation recorded in
`PAPER_NOTES.md` and `docs/model-card.md`. The corrected LightGBM model and
feature metadata are frozen at
`artifacts/models/lightgbm_krate_20260723_202255.*`.

`GIT_STATE.txt` is retained only to document the state that generated the
superseded run.
