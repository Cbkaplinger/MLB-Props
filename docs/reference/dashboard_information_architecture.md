# Dashboard Information Architecture (Deterministic, Professional)

Status: **Finalized architecture spec (pre-implementation baseline)**

Purpose: define a stable, implementation-ready architecture for the operator dashboard so it is concise, decision-driven, and auditable.

This document is intentionally architecture-first: **what to show, why it exists, how to compute it, and what decisions it informs**.

---

## 1) Design Principles

- **Decision-first, not data-first:** every widget must map to a real operator decision.
- **One metric, one definition:** no duplicate formulas across tabs/notebooks.
- **Regime-aware by default:** show full-history and recent-window context side-by-side.
- **Layered detail:** top-level summary -> drill-down diagnostic -> raw context.
- **Operational trust:** every displayed metric has a source artifact and update cadence.
- **Matplotlib-first rendering:** keep all visualizations in `matplotlib`/`seaborn`; do not introduce Plotly.

---

## 2) Audience and Decisions

Primary user: you (operator + model owner).

Decisions this dashboard must support:

1. Should we keep current policy mode (`balanced`, `profit_lock`, etc.)?
2. Is signal quality improving or degrading?
3. Is PnL driven by robust edge realization or fragile variance?
4. Are execution mechanics (entry timing/slippage/data quality) helping or hurting?
5. Is a freeze/promotion checkpoint justified?

---

## 3) Canonical Data Sources

Use artifacts as the only dashboard source layer (never re-derive ad hoc in UI):

- `artifacts/odds_log/daily_operator_summary.json`
- `artifacts/odds_log/policy_replay_daily.json`
- `artifacts/odds_log/validation_ops_daily.json`
- `artifacts/odds_log/feature_set_governance_ranked.csv`
- `artifacts/odds_log/feature_set_governance_edge_deciles.csv`
- `artifacts/odds_log/decision_scoreboard_daily.parquet`
- `artifacts/odds_log/ledger.parquet` (context/drill-down only)

Metric definitions are governed by:

- `docs/reference/governance_metric_stack.md`

Freeze governance log:

- `docs/research/floor_freeze_log.md`

---

## 4) Top-Level Layout (5 Panels)

## Panel A — Executive Health (top row)

Goal: answer “is the system healthy enough to continue current operating mode?”

Required metrics (compact cards):

- `recent_30_roi`, `recent_60_roi`, `full_roi`
- `recent_30_mean_clv_pp`, `recent_60_mean_clv_pp`
- `brier_skill_vs_market`
- `ece`, `mce`
- `geo_growth_log_mean`
- `mc_prob_drawdown_breach`
- `go_no_go_status`

Design constraints:

- Max 10 cards.
- Include arrows/trend vs prior snapshot for each card.
- Include “as-of” timestamp and sample size (`n`) in footer.

---

## Panel B — Policy and Path Risk

Goal: answer “is current policy survivable and appropriately sized?”

Views:

- Scenario table from `policy_replay_daily.json`:
  - `scenario`, `n`, `roi`, `clv_mean_pp`
  - `geo_growth_log_mean`
  - `mc_prob_bankroll_floor_breach`
  - `mc_prob_drawdown_breach`
  - `mc_median_terminal_bankroll`, `mc_p10_terminal_bankroll`
- Drawdown diagnostics:
  - `max_drawdown_abs`, `max_drawdown_pct`, `max_recovery_bets`, `cvar_95`

Decision rule examples:

- If `geo_growth_log_mean < 0` and `mc_prob_drawdown_breach` elevated, do not scale risk.
- If ROI positive but risk metrics deteriorate, treat as variance-driven and hold sizing.

---

## Panel C — Signal Quality and Calibration

Goal: answer “are model probabilities meaningfully better than market baseline?”

Views:

- Calibration quality:
  - `brier`, `logloss`, `ece`, `mce`
  - `brier_skill_vs_market`, `logloss_skill_vs_market`
- Reliability chart:
  - observed hit rate vs predicted probability bins
- Candidate governance table (top ranked rows):
  - `feature_set`, `calibration_mode`, `gate_pass_count`, core quality/risk metrics

Decision rule examples:

- Promote only when skill-vs-market is positive and stable and risk guardrails pass.
- Reject “good ROI” candidates with weak calibration or unstable error.

---

## Panel D — Edge Realization and Regime Robustness

Goal: answer “does higher modeled edge actually convert to realized quality?”

Views:

- Edge-decile lift:
  - by decile: `mean_edge`, `roi`, `mean_clv_pp`, `n`
- Segment robustness:
  - side / market / line-band / odds-band dispersion

Decision rule examples:

- If decile monotonicity is weak/inverted, model edge is not trustworthy for sizing.
- If performance concentrates in a narrow segment, reduce confidence in global policy.

---

## Panel E — Execution and Data Quality

Goal: answer “is process quality masking true model quality?”

Views:

- Slippage decomposition from `validation_ops_daily.json`:
  - `open_to_bet_pp`
  - `bet_to_close_pp`
  - `open_to_close_pp`
  - overall + by side
- Data quality:
  - `missing_closes`, `stale_quotes`, `unmatched_rate`

Decision rule examples:

- Persistently negative `open_to_bet_pp` implies entry timing/process drag.
- Missing close data blocks high-confidence CLV governance.

---

## 5) Regime-Aware Framing (Mandatory)

Because production features/calibration/floors changed recently, every key panel must show:

- Full-history
- Last 60 settled
- Last 30 settled

For each of: ROI, mean CLV, and at least one risk metric.

UI requirement:

- Add a visible “Regime-mix caution” note when full/recent metrics diverge materially.

---

## 6) Metric Contract (Implementation Rule)

Every dashboard metric must include:

- **Name** (stable identifier)
- **Definition** (formula and units)
- **Source artifact path**
- **Update job/script**
- **Sample filter**
- **Window** (full/60/30)
- **Directionality** (higher/lower better)

No metric may appear in the dashboard without this contract.

---

## 7) Refresh Cadence and Data Freshness

Recommended cadence:

- Morning workflow refresh
- Post-settlement refresh
- Optional midday manual refresh when significant updates occur

Freshness checks on load:

- “As-of” timestamp per panel
- Row count guardrail (`n` thresholds)
- Data quality flags surfaced before interpretation

---

## 8) Freeze Checkpoint Integration

When a freeze checkpoint is reached:

- record in `docs/research/floor_freeze_log.md`
- include dashboard snapshot references:
  - policy replay risk
  - calibration skill-vs-market
  - edge-decile lift
  - slippage decomposition
  - full vs recent window comparison

This ensures freeze decisions are tied to observable artifacts, not narrative drift.

---

## 9) Anti-Patterns to Avoid

- Showing both raw and transformed variants of the same metric without purpose.
- Mixing feature-candidate governance and live-policy operations in the same table.
- Adding one-off charts that are not tied to a decision.
- Interpreting full-history metrics alone during active regime shifts.
- Threshold churn without documented freeze-log entries.

---

## 10) Suggested Build Sequence (No UI code in this doc)

1. Lock metric dictionary from `governance_metric_stack.md`.
2. Build Panel A cards from summary/replay artifacts.
3. Build Panel B scenario + path-risk view.
4. Build Panel C calibration/skill panel.
5. Build Panel D edge-decile + segment robustness view.
6. Build Panel E execution/data-quality panel.
7. Add freeze-checkpoint export view (read-only evidence pack).

This sequence yields a professional, coherent dashboard without bloat.

---

## 11) Current-State Gap Analysis (vs existing Streamlit app)

Current app strengths:

- Strong artifact coverage and internal remediation hooks.
- Good operational context (`go_no_go`, `policy_replay`, scorecard, artifacts freshness).
- Existing KPI card system and deterministic status chips.
- Matplotlib/seaborn chart stack already in place (aligned with user preference).

Current app friction points:

- Too many top-level sections and repeated summaries across tabs.
- Mixed scope in single views (feature-candidate governance and live policy context can blend).
- Some panels emphasize broad historical views without mandatory recent-window framing.
- Executive strip currently carries many cards/blocks that can dilute decision focus.

Architecture implication:

- Refactor should be **re-composition**, not a full rewrite.
- Preserve existing data loaders, card primitives, and chart stack.
- Reduce duplication through strict panel ownership (each metric appears in one primary panel).

---

## 12) Matplotlib/Seaborn Visualization Standard

Do not use Plotly.

Chart standards:

- Use `matplotlib` + `seaborn` only.
- Standardize titles, axis labels, and interpretation captions.
- Prefer:
  - line charts for trend/rolling windows,
  - bar charts for cross-sectional comparisons,
  - scatter only for profile scans and concentration diagnostics,
  - heatmaps only for compact confusion/coverage matrices.
- Every chart must include:
  - as-of timestamp context,
  - sample size (`n`) context,
  - horizontal reference line where relevant (e.g., ROI=0, beat-close=0.5).

---

## 13) Deterministic Tab Ownership (to prevent jumble)

Use this canonical mapping:

- **Overview tab** -> Panel A only (executive health cards + regime warning + short action text)
- **Policy tab** -> Panel B + policy subset of Panel D
- **Calibration tab** -> Panel C only
- **Edge/Realization tab** -> Panel D only
- **Execution/Data Quality tab** -> Panel E only
- **Ops Health tab (internal mode)** -> automation/task/artifact remediation only

Hard rule:

- If a metric has a primary tab, other tabs may reference it with a single-line pointer but not duplicate full tables/charts.

---

## 14) Migration Strategy (low-risk, iterative)

Phase A: classify existing widgets/charts into panel ownership categories (no UI change yet).

Phase B: remove duplicate metric displays while preserving all current computations.

Phase C: add missing regime-window framing where absent (`full`, `last_60`, `last_30`).

Phase D: finalize concise executive panel (max 10 cards) and move all detail into drill-down tabs.

Phase E: freeze architecture and log the checkpoint in `floor_freeze_log.md`.

This preserves production continuity while cleaning structure.

---

## 15) Metric Dictionary Contract (authoritative fields)

Before implementation, create or maintain one metric dictionary table (file or module)
with one row per dashboard metric, using this schema:

- `metric_id` (stable snake_case key)
- `display_name`
- `panel` (A/B/C/D/E)
- `primary_tab`
- `definition` (plain-English + formula)
- `units`
- `directionality` (`higher_better`, `lower_better`, `contextual`)
- `artifact_source`
- `refresh_job`
- `sample_filter`
- `window` (`full`, `last_60`, `last_30`, or `n/a`)
- `min_sample_for_display`
- `warn_threshold`
- `risk_threshold`
- `owner` (script/notebook origin)

Hard rule: no metric may be shown in dashboard UI without a valid dictionary entry.

---

## 16) Canonical Panel Payloads (minimum required data)

Each panel must render from a minimal payload contract:

- **Panel A payload**
  - action/go-no-go state
  - ROI/CLV windows (`full`, `60`, `30`)
  - calibration skill snapshot
  - path-risk headline
- **Panel B payload**
  - replay scenarios table
  - drawdown/recovery metrics
  - Monte Carlo risk metrics
- **Panel C payload**
  - calibration metrics and skill-vs-market
  - reliability bins
  - top governance candidates
- **Panel D payload**
  - edge-decile realization table/series
  - segment dispersion summary
- **Panel E payload**
  - slippage decomposition
  - data quality alerts and counts

If payload is incomplete, panel must show a deterministic “insufficient data” state
with missing artifact(s), not partial ad hoc replacements.

---

## 17) Display Policy (consistency rules)

- Sentence case for labels and headers.
- All percentages shown with explicit `%` or `pp` units.
- Always display `as-of` timestamp and `n`.
- Always include horizontal reference lines where decision boundaries exist:
  - ROI = 0
  - beat-close rate = 0.5
  - CLV = 0
- Every chart requires a one-line interpretation caption.
- Max 10 cards in executive panel.
- No more than one primary table + one primary chart per sub-panel view.

---

## 18) Regime-Aware Decision Policy

During active model/policy evolution, use this decision weighting:

- 60% weight: `last_30`
- 30% weight: `last_60`
- 10% weight: `full_history`

Use full history as context only when recent windows disagree.

Freeze/promotion decisions must explicitly log:

- whether recent windows confirm or contradict full-history signal,
- which window drove the final decision.

---

## 19) Non-Goals (explicitly out of scope)

- No Plotly migration.
- No dashboard implementation details in this document.
- No threshold changes or freeze decisions embedded in UI architecture.
- No addition of non-governance exploratory visuals to operator dashboard.

---

## 20) Definition of Done (architecture phase)

Architecture is considered complete when:

1. Panel ownership map is accepted and stable.
2. Metric dictionary contract is populated for all displayed metrics.
3. Every displayed metric maps to a canonical artifact and refresh job.
4. Regime-aware windows are specified for all decision-critical metrics.
5. Duplicate metric displays across tabs are identified for removal in implementation.
6. Freeze-checkpoint evidence fields are aligned with dashboard panels.

At this point, implementation may begin with no further architecture expansion.

---

## 21) Final Gap Closures (pre-implementation)

These are the final architecture-level additions to ensure no blind spots remain.

### 21.1 Regime event overlays (required)

Add regime markers to timeline charts:

- model feature-set changes
- calibration pointer changes
- edge-floor/policy changes

Required behavior:

- vertical event lines on ROI/CLV/risk trend charts
- hover/label text with event date + short description
- event source should reference freeze/governance logs

Purpose:

- prevent misattribution of performance moves to the wrong model/policy era.

### 21.2 Metric lineage block (required)

Every panel must show a compact lineage row:

- artifact path key
- artifact `as_of` timestamp
- refresh job/script name
- sample size (`n`)
- checkpoint/hash reference when available

Purpose:

- make every displayed metric auditable in one glance.

### 21.3 Uncertainty display policy (required)

For decision-critical metrics, display confidence context by default:

- `roi`, `clv` -> CI or CI bounds
- skill metrics when sample allows -> CI/uncertainty note
- if CI unavailable due to low `n`, show explicit “insufficient sample” tag

Purpose:

- avoid point-estimate overconfidence.

### 21.4 Policy profile drift trend (required)

Add a compact trend view for policy profile stability over time:

- selected profile
- rank/eligibility drift across snapshots
- recent changes in recommendation volume and ROI/CLV contribution

Purpose:

- detect policy instability before major drawdown episodes.

### 21.5 Concentration risk metric (required)

Add concentration diagnostics as top-level risk context:

- top segment stake share
- top two segment PnL share
- optional: Herfindahl-style concentration index

Purpose:

- detect hidden fragility masked by aggregate ROI.

### 21.6 Data-quality decomposition (required)

Beyond binary alerts, include decomposition:

- missing closes by cause bucket
- unmatched mapping by source/book
- stale quote incidence trend

Purpose:

- direct remediation effort to highest-impact failure mode.

### 21.7 Execution timing linkage (required)

Tie slippage to process timing:

- distribution of time-to-bet / time-from-open-to-bet
- relationship to `open_to_bet_pp`
- side/book split where sample is sufficient

Purpose:

- separate signal weakness from execution latency cost.

### 21.8 Scope control (guardrail)

These additions are architecture requirements; implement only when:

- canonical artifacts are available,
- metric dictionary entries are complete,
- panel ownership remains non-overlapping.

Do not introduce exploratory visuals outside panel ownership rules.
