# 05 — Live prediction flow (production, as of 2026-09-24)

How a slate becomes money (or paper) tracking, end to end. Research-era
training is `03`; this file is the thing that runs every day.

```mermaid
flowchart TB
    classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
    classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
    classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
    classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
    classDef next fill:#01579b,stroke:#81d4fa,color:#fff

    CRON["5 Modal crons (NY-local)<br/>03:00 settle · 05:30 drift · 08:00 morning<br/>09–22 hourly · q5m sweeps 12–22"]:::built

    MORN["Morning chain<br/>heal → refresh L1/L2 → log_projections<br/>→ board → poll(open) → Kalshi → Novig probe<br/>→ edge-watch → alert(always fires)"]:::built
    HOUR["Hourly chain<br/>same, minus refresh<br/>alert flips-only (quiet when green)"]:::built
    SWEEP["Close sweeps<br/>urgency gate T-45 · burst 60s inside T-6<br/>T+5 stop · one slip per signal"]:::built
    SETTLE["Settle 03:00<br/>MLB API finals · void PPD-24h<br/>auto-settle-api"]:::built
    DRIFT["Drift 05:30<br/>8 checks · exit 0/1/2 = GREEN/YELLOW/RED"]:::built

    ENS["K-rate ensemble<br/>LightGBM: 0.60 sparse72_monotone (72-feat)<br/>+ 0.40 final58 (58-feat) · 0.00 sparse72 · frozen"]:::built
    TBF["TBF Ridge<br/>thin bullpen · MAE≈2.49"]:::built
    CNT["Count layer<br/>Poisson(rate×TBF) → P(over) 2.5…9.5"]:::built
    WS1C["WS1c calibration<br/>per-line Platt · live 2026-09-10<br/>prob_calibration_production.json"]:::built
    POL["Policy (kpi_policy)<br/>floors · 4.5-over veto · 2.5/3.5 probation<br/>edge cap · under-lean · DK+FD · game caps"]:::built
    SIZE["Sizing 1/16-Kelly → realized flat $50u<br/>per-line $150 · per-game $200 · day $500"]:::built

    LED["Ledger (one slip/signal)<br/>best price at signal · xbook + Kalshi + paid CLV"]:::built
    GRADE["Grading<br/>settled+staked+family-deduped<br/>ROI · WR · CLV/xbook/cons · THIN/CALIB/EXEC"]:::built
    MAN["Manifests + heartbeat<br/>P4/P6 run records · cloud_heartbeat.jsonl"]:::built

    SIM["Research lane (never live)<br/>ladder v2 posterior · showdown<br/>monte-carlo v1 · Kalshi panels"]:::next

    CRON --> MORN
    CRON --> HOUR
    CRON --> SWEEP
    CRON --> SETTLE
    CRON --> DRIFT

    MORN --> ENS
    MORN --> TBF
    ENS --> CNT
    TBF --> CNT
    CNT --> WS1C
    WS1C --> POL
    POL --> SIZE
    SIZE --> LED
    HOUR --> LED
    SWEEP --> LED
    SETTLE --> LED
    LED --> GRADE
    GRADE --> MAN
    DRIFT --> MAN
    MORN -.->|"alerts"| MAN

    LED -.->|"paper feeds"| SIM
    SIM -.->|"nothing back without orders"| POL
```

## Layers (modeling → money)

| # | Layer | File / artifact | Frozen? |
|---|---|---|---|
| 1 | K-rate ensemble | `src/Python/live_assembly.py` + `live_krate_ensemble.json` | Yes (prod-184) |
| 2 | TBF Ridge | `src/Python/pipeline/` + TBF bundle | Yes |
| 3 | Count layer (Poisson) | `src/Python/market.py` (`p_strikeouts_ge`) | Yes |
| 4 | WS1c per-line Platt | `artifacts/models/prob_calibration_production.json` | Yes (2026-09-10) |
| 5 | Policy + floors + vetoes | `production/ops/kpi_policy.json` | Tunable (orders) |
| 6 | Sizing 1/16-Kelly + caps | `src/Python/market.py` | Frozen |
| 7 | One-slip ledger + 3-source CLV | `artifacts/odds_log/ledger.parquet` | Live |
| 8 | Grading + manifests + drift | `send_daily_grading.py` / `run_manifest.py` / drift | Live |

## Grading: before AND after (owner Q 2026-09-24)

- **Before first pitch (at signal):** edge vs books, model prob vs market prob,
  CLV expectation implicit in edge floor ≥12%. Recorded on every ticket.
- **After final (settle + grading):** ROI/WR on settled+staked+dedeuped,
  same-book CLV, xbook CLV, paid-consensus CLV, trailing-200 beat rule,
  THIN/CALIB/EXEC flags. Plus calibration-vs-actuals research
  (Brier/logloss/ECE notebooks + ladder showdown).
- **Independent recomputation (money-on-the-line discipline):**
  grading math re-derived three ways — daily grading message,
  `paper_quant` track, gate-next-N artifact — plus content-hash pins on
  kpi/krate/ws1c in every manifest and 500+ CI tests. A number that can't
  be recomputed from the ledger doesn't ship in a page.

## Notes

- Research sims (ladder v2, monte-carlo v1, Kalshi panels) read the ledger
  and write reports; no arrow points back into policy without owner orders.
- Season end 2026-09-27: `season.postseason = hold_all_no_bets` in policy.
- Cron cap: 5 Modal schedules — new jobs fold in as steps, never schedules.
