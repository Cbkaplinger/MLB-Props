# SSAC27 Item 8 — Null / placebo decision lanes (2026-09-01)

Post-freeze matched nulls vs locked KING floor gate.

| Lane | n | ROI | Win rate | CLV mean | CLV>0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| king_passes_floor_postfreeze | 74 | -0.0155 | 0.4865 | 0.0159 | 0.5862 |
| random_prob_matched_n_floor | 74 | -0.0917 | 0.4595 | 0.0108 | 0.4643 |
| naive_prior_matched_n_floor | 74 | -0.0562 | 0.473 | 0.0112 | 0.4737 |
| shuffle_edge_on_king_set | 56 | -0.0256 | 0.4821 | 0.0203 | 0.6 |

Source JSON: `artifacts/odds_log/null_decision_lane_20260901.json`.

## Read carefully

- KING lane uses real stakes (`passes_floor`).
- Random/naive may impute stake for logged non-bet candidates; they are **null references**, not production policies.
- If KING does not beat these nulls on ROI *and* CLV with margin, do not claim decision-layer edge.
