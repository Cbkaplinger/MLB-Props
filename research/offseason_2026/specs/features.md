# Feature manifest (frozen spec — audit §§V, W, K)

## Frozen production sets (never edited)

`production_sparse72` (72) / `production_sparse72_monotone` (72-mono) /
`production_final58_consensus` (58); gates in `features.py`
(`FORBIDDEN = {PA,K,Outs,k_rate,actual_*}`); ensemble 0.00/0.60/0.40.

## PA challenger family order (evaluate in order, one family at a time)

1. Pitcher trailing K/whiff/chase + batter trailing K/whiff/chase + league
   baseline (log5 inputs).
2. Handedness splits (batter populated; pitcher usage-only; min-n + shrink rule
   Q-M1: std-only, no short windows until populated).
3. Zone/chase/contact splits. 4. Rest/workload/role stability.
5. Park + slot + lineup-status. 6. Pitch-mix + velo/movement (ablation only).
7. Recent-form deviations. 8. Repertoire×tendencies, location, TTO.
Rolling forms: season-to-date → prior-N PA → prior-N games → shrunk/hierarchical
→ hand/repertoire-specific → career+deviation. Windows chosen inside 23–24 folds
only. Label per family: helps-PA vs helps-opportunity (workload/bullpen/hook =
opportunity, never K features). Market/implied features excluded from the model
(evaluation side only).

## Parity rule

Train and serve share construction (shift(1) + same-date first-collapse, forbidden
gates, park fallback yr-1). Known skews stay declared (realized-vs-announced
lineups; debut null-vs-zero after fix; L3-zero = not-rebuilt). New-feature parity
test: disable→bit-identical frozen outputs.
