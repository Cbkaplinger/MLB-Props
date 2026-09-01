# Shadow asymmetric / line-veto policy (2026-09-01)

Post-freeze counterfactuals vs locked KING floor. **No live config change.**

Producer: `production/ops/run_shadow_asymmetric_policy.py`
Stance: `docs/reference/reports/interim_postfreeze_ops_stance_2026-09-01.md`

## Policy lanes

| Lane | n | ROI | WR | CLV mean | CLV>0 | n_over/under |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `status_quo_king_floor` | 74 | -0.0155 | 0.4865 | 0.0159 | 0.5862 | 45/29 |
| `veto_4_5_over` | 56 | 0.0825 | 0.5357 | 0.0191 | 0.5 | 27/29 |
| `veto_low_line_overs` | 35 | 0.2563 | 0.6286 | 0.0272 | 0.4615 | 6/29 |
| `asym_over16_under12` | 58 | 0.1056 | 0.569 | 0.0238 | 0.6154 | 20/38 |
| `asym16_plus_veto_4_5` | 53 | 0.1399 | 0.5849 | 0.0246 | 0.5455 | 15/38 |

## Status-quo side × line (KING floor)

| Line | Side | n | ROI | WR | CLV mean | CLV n |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2.5 | over | 4 | -1.0 | 0.0 | None | 0 |
| 3.5 | over | 17 | -0.0594 | 0.4706 | 0.0043 | 7 |
| 3.5 | under | 3 | 0.656 | 0.6667 | 0.0895 | 1 |
| 4.5 | over | 18 | -0.4086 | 0.3333 | 0.0087 | 9 |
| 4.5 | under | 10 | 0.4001 | 0.7 | -0.0105 | 1 |
| 5.5 | over | 4 | -0.07 | 0.5 | 0.0012 | 2 |
| 5.5 | under | 7 | 0.476 | 0.7143 | 0.0351 | 4 |
| 6.5 | over | 2 | 0.2466 | 0.5 | 0.0 | 1 |
| 6.5 | under | 4 | -0.1222 | 0.5 | -0.0094 | 3 |
| 7.5 | under | 2 | 0.0177 | 0.5 | 0.1594 | 1 |
| 8.5 | under | 3 | 0.2639 | 0.6667 | None | 0 |

## Brier skill vs market (status quo)

```json
{
  "status_quo": {
    "available": true,
    "n": 74,
    "brier_model": 0.27926,
    "brier_market": 0.25099,
    "brier_skill_vs_market": -0.11262
  },
  "status_quo_over": {
    "available": true,
    "n": 45,
    "brier_model": 0.32246,
    "brier_market": 0.25221,
    "brier_skill_vs_market": -0.27854
  },
  "status_quo_under": {
    "available": true,
    "n": 29,
    "brier_model": 0.21223,
    "brier_market": 0.2491,
    "brier_skill_vs_market": 0.14804
  }
}
```

## Read carefully

- `status_quo` / `veto_*` use real KING `passes_floor` stakes.
- `asym_*` may impute stake on non-bet candidates that clear the asymmetric edge gate — treat as directional shadow, not bankroll truth.
- Promote only under gates in the interim stance doc.

JSON: `artifacts/odds_log/shadow_asymmetric_policy_20260901.json`
