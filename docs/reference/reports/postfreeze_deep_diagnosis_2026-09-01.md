# Post-freeze deep diagnosis (2026-09-01)

Analysis-only. **No live KING / floor change.**

Producer: `production/ops/run_postfreeze_deep_diagnosis.py`

## Executive memo

- KING post-freeze: n=74, ROI=-0.0155, PnL=-80.18.
- Edge↔ROI Spearman overs: {'n': 45, 'pearson_r': -0.0906, 'pearson_p': 0.5539, 'spearman_r': -0.081, 'spearman_p': 0.5969}.
- Edge↔ROI Spearman unders: {'n': 29, 'pearson_r': 0.2609, 'pearson_p': 0.1717, 'spearman_r': 0.1693, 'spearman_p': 0.3801}.
- Brier skill vs market: over={'n': 45, 'brier_model': 0.32246, 'brier_market': 0.25221, 'skill_vs_market': -0.27854}, under={'n': 29, 'brier_model': 0.21223, 'brier_market': 0.2491, 'skill_vs_market': 0.14804}.
- If over edge↔ROI is flat/negative, raising a universal floor will not heal overs.
- Prefer side/line gates; keep CLV as a skill check alongside ROI/PnL.
- Do not promote on this single ~10-day window alone.

## Edge% vs per-bet ROI

| Slice | n | Pearson | Spearman |
| --- | ---: | --- | --- |
| king_all | 74 | 0.0881 (p=0.4553) | 0.1093 (p=0.354) |
| king_over | 45 | -0.0906 (p=0.5539) | -0.081 (p=0.5969) |
| king_under | 29 | 0.2609 (p=0.1717) | 0.1693 (p=0.3801) |

## Abs-edge buckets (KING)

| Side | Edge bucket | n | ROI | WR | CLV>0 |
| --- | --- | ---: | ---: | ---: | ---: |
| all | 0.12–0.14 | 11 | 0.03 | 0.5455 | 0.3333 |
| all | 0.14–0.16 | 12 | -0.2353 | 0.4167 | 0.25 |
| all | 0.16–0.18 | 6 | -0.4386 | 0.3333 | 1.0 |
| all | 0.18–0.22 | 11 | 0.2981 | 0.6364 | 1.0 |
| all | 0.22–1.0 | 16 | 0.0971 | 0.5625 | 0.5 |
| over | 0.12–0.14 | 8 | -0.2684 | 0.375 | 0.5 |
| over | 0.14–0.16 | 9 | -0.5234 | 0.2222 | 0.25 |
| over | 0.16–0.18 | 2 | -0.0313 | 0.5 | None |
| over | 0.18–0.22 | 6 | 0.0592 | 0.5 | 1.0 |
| over | 0.22–1.0 | 7 | -0.3408 | 0.2857 | 1.0 |
| under | 0.12–0.14 | 3 | 0.8568 | 1.0 | 0.0 |
| under | 0.14–0.16 | 3 | 1.1742 | 1.0 | None |
| under | 0.16–0.18 | 4 | -0.5987 | 0.25 | 1.0 |
| under | 0.18–0.22 | 5 | 0.6107 | 0.8 | None |
| under | 0.22–1.0 | 9 | 0.3801 | 0.7778 | 0.3333 |

## Universal floor sweep (stake>0 post-freeze)

| Floor | n | ROI | PnL | n_over/under | CLV>0 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.08 | 74 | -0.0155 | -80.18 | 45/29 | 0.5862 |
| 0.1 | 66 | -0.0097 | -47.5 | 39/27 | 0.5417 |
| 0.12 | 56 | 0.0344 | 151.25 | 32/24 | 0.5 |
| 0.14 | 45 | 0.0353 | 129.53 | 24/21 | 0.5833 |
| 0.16 | 33 | 0.0969 | 289.46 | 15/18 | 0.75 |
| 0.18 | 27 | 0.1652 | 437.82 | 13/14 | 0.7143 |
| 0.2 | 22 | 0.137 | 300.51 | 10/12 | 0.6 |

## Asymmetric floor grid (best ROI, n≥25)

| Over floor | Under floor | n | ROI | PnL | CLV>0 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.18 | 0.12 | 37 | 0.1851 | 592.2 | 0.6 |
| 0.16 | 0.12 | 39 | 0.1788 | 589.21 | 0.6 |
| 0.18 | 0.14 | 34 | 0.1422 | 427.86 | 0.75 |
| 0.16 | 0.14 | 36 | 0.1369 | 424.87 | 0.75 |
| 0.18 | 0.1 | 40 | 0.1347 | 450.18 | 0.5833 |
| 0.16 | 0.1 | 42 | 0.1301 | 447.19 | 0.5833 |
| 0.14 | 0.12 | 48 | 0.0761 | 293.87 | 0.5 |
| 0.14 | 0.1 | 51 | 0.038 | 151.85 | 0.5 |

## Line × side (KING)

| Line | Side | n | ROI | WR | CLV>0 | PnL |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2.5 | over | 4 | -1.0 | 0.0 | None | -245.43 |
| 3.5 | over | 17 | -0.0594 | 0.4706 | 0.5714 | -77.67 |
| 3.5 | under | 3 | 0.656 | 0.6667 | 1.0 | 117.18 |
| 4.5 | over | 18 | -0.4086 | 0.3333 | 0.7778 | -422.25 |
| 4.5 | under | 10 | 0.4001 | 0.7 | 0.0 | 258.63 |
| 5.5 | over | 4 | -0.07 | 0.5 | 0.5 | -17.3 |
| 5.5 | under | 7 | 0.476 | 0.7143 | 0.5 | 267.62 |
| 6.5 | over | 2 | 0.2466 | 0.5 | 0.0 | 32.17 |
| 6.5 | under | 4 | -0.1222 | 0.5 | 0.3333 | -49.16 |
| 7.5 | under | 2 | 0.0177 | 0.5 | 1.0 | 4.1 |
| 8.5 | under | 3 | 0.2639 | 0.6667 | None | 51.92 |

## Over-line veto sensitivity

| Veto over lines | n | ROI | PnL | CLV>0 |
| --- | ---: | ---: | ---: | ---: |
| [4.5] | 56 | 0.0825 | 342.07 | 0.5 |
| [3.5, 4.5] | 39 | 0.1478 | 419.73 | 0.4615 |
| [2.5, 3.5, 4.5] | 35 | 0.2563 | 665.16 | 0.4615 |
| [4.5, 5.5] | 52 | 0.0921 | 359.37 | 0.5 |

## High-|edge| overs

```json
[
  {
    "abs_edge_min": 0.12,
    "n": 32,
    "roi": -0.2702,
    "win_rate": 0.3438
  },
  {
    "abs_edge_min": 0.14,
    "n": 24,
    "roi": -0.2707,
    "win_rate": 0.3333
  },
  {
    "abs_edge_min": 0.16,
    "n": 15,
    "roi": -0.1603,
    "win_rate": 0.4
  },
  {
    "abs_edge_min": 0.18,
    "n": 13,
    "roi": -0.1706,
    "win_rate": 0.3846
  },
  {
    "abs_edge_min": 0.2,
    "n": 10,
    "roi": -0.1579,
    "win_rate": 0.4
  }
]
```

## CLV ↔ outcome

```json
{
  "clv_vs_win_spearman": {
    "r": -0.0587,
    "p": 0.7622,
    "n": 29
  },
  "clv_vs_bet_roi_spearman": {
    "r": -0.0287,
    "p": 0.8824,
    "n": 29
  },
  "over_when_clv_gt0": {
    "n": 12,
    "roi": 0.1951
  },
  "over_when_clv_le0": {
    "n": 7,
    "roi": -0.6796
  },
  "under_when_clv_gt0": {
    "n": 5,
    "roi": -0.7841
  },
  "under_when_clv_le0": {
    "n": 5,
    "roi": 0.1061
  }
}
```

## Reliability bins

```json
{
  "all": [
    {
      "bin": 1,
      "n": 18,
      "mean_p_model": 0.5591,
      "hit_rate": 0.4444,
      "gap_hit_minus_p": -0.1146,
      "roi": -0.0368
    },
    {
      "bin": 2,
      "n": 21,
      "mean_p_model": 0.6324,
      "hit_rate": 0.4762,
      "gap_hit_minus_p": -0.1562,
      "roi": -0.0722
    },
    {
      "bin": 3,
      "n": 16,
      "mean_p_model": 0.6733,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.1733,
      "roi": 0.0014
    },
    {
      "bin": 4,
      "n": 19,
      "mean_p_model": 0.7725,
      "hit_rate": 0.5263,
      "gap_hit_minus_p": -0.2461,
      "roi": 0.0249
    }
  ],
  "over": [
    {
      "bin": 1,
      "n": 11,
      "mean_p_model": 0.5548,
      "hit_rate": 0.3636,
      "gap_hit_minus_p": -0.1912,
      "roi": -0.246
    },
    {
      "bin": 2,
      "n": 14,
      "mean_p_model": 0.6357,
      "hit_rate": 0.4286,
      "gap_hit_minus_p": -0.2071,
      "roi": -0.1073
    },
    {
      "bin": 3,
      "n": 8,
      "mean_p_model": 0.6556,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.1556,
      "roi": 0.0578
    },
    {
      "bin": 4,
      "n": 12,
      "mean_p_model": 0.7521,
      "hit_rate": 0.25,
      "gap_hit_minus_p": -0.5021,
      "roi": -0.5161
    }
  ],
  "under": [
    {
      "bin": 1,
      "n": 6,
      "mean_p_model": 0.5646,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.0646,
      "roi": 0.0486
    },
    {
      "bin": 2,
      "n": 8,
      "mean_p_model": 0.6192,
      "hit_rate": 0.625,
      "gap_hit_minus_p": 0.0058,
      "roi": 0.1571
    },
    {
      "bin": 3,
      "n": 7,
      "mean_p_model": 0.7024,
      "hit_rate": 0.7143,
      "gap_hit_minus_p": 0.0119,
      "roi": 0.5182
    },
    {
      "bin": 4,
      "n": 8,
      "mean_p_model": 0.7828,
      "hit_rate": 0.75,
      "gap_hit_minus_p": -0.0328,
      "roi": 0.3057
    }
  ]
}
```

## Brier skill vs market

```json
{
  "all": {
    "n": 74,
    "brier_model": 0.27926,
    "brier_market": 0.25099,
    "skill_vs_market": -0.11262
  },
  "over": {
    "n": 45,
    "brier_model": 0.32246,
    "brier_market": 0.25221,
    "skill_vs_market": -0.27854
  },
  "under": {
    "n": 29,
    "brier_model": 0.21223,
    "brier_market": 0.2491,
    "skill_vs_market": 0.14804
  }
}
```

## Adjustment principles (still not live edits)

1. No universal floor raise to fix overs if edge↔ROI on overs is flat/negative.
2. Side-aware + line-aware gates beat one knobs-for-all floor.
3. Optimize ROI/PnL and CLV jointly; do not buy a one-week ROI spike with CLV collapse.
4. Recalibrate only under a pre-registered split that excludes this eval window.
5. Re-run weekly; promote only under interim stance gates.

JSON: `artifacts/odds_log/postfreeze_deep_diagnosis_20260901.json`
