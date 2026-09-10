# Agentic Coding Stack — Personal MLB-Props

**Owner:** Cameron  
**Scope:** Personal repository only  
**Goal:** Fast, cost-controlled agentic coding with reliable fallbacks.

## Current finding: Muse Spark 1.3

Muse Spark 1.3 Contributor Free has been the strongest subjective fit so far for fast, practical agentic work on this repository. It is a **temporary free tier**, not a permanent unlimited service. Treat it as an opportunistic primary lane while available, with a paid fallback ready.

### Privacy rule

Muse Spark 1.3 Contributor Free permits prompts and completions to be used to train future Meta models. Never send secrets, API keys, credentials, private financial-account data, private datasets, or anything that should not be retained into that tier. Do not use it for employer code or internal work.

## Observed usage pattern

The exported OpenCode logs show cumulative, cache-heavy agent sessions. One later Muse session reached approximately 144,687 total tokens, including approximately 143,857 cache-read tokens. These logs show `cost: 0`, but they do not reveal the exact free-tier quota size or exact free allocation consumed.

**Interpretation:** Repeated context is the main scale risk. Long-lived agent sessions, broad repository scans, large logs, and repeated task restarts will exhaust a free quota sooner than focused work.

## Stack

| Role | Provider/model | Policy |
|---|---|---|
| Personal primary, while available | OpenCode Zen: `opencode/muse-spark-1.3-contributor-free` | Use only for non-sensitive personal work; expect availability or quota to change. |
| Personal paid fallback | OpenCode Zen: `opencode/deepseek-v4-flash` | Low-cost fallback; set a firm monthly spend cap. |
| Second opinion / difficult task | Paid model chosen deliberately | Invoke only after the primary model fails twice or the task is demonstrably high leverage. |
| Employer work | Lenovo-approved Model Factory / company tooling | Never route employer code, GitHub/Linear content, or CI logs through personal accounts. |

## Cost controls

1. Create a Zen account only if you want paid fallback access.
2. Set a workspace monthly limit of $20–30 before using paid models.
3. Disable Zen auto-reload if you want a true hard cap; otherwise a $20 reload can occur when the balance falls below $5.
4. Keep a per-task record: model, task type, tests passed, elapsed time, and spend.
5. Review the usage console weekly rather than relying on chat-history impressions.

## Context discipline

- Start each task with a narrow goal and a small list of relevant files.
- Run one failed test, one bug, or one review comment at a time.
- Keep `AGENTS.md` concise; it is persistent context.
- Exclude generated data, artifacts, logs, caches, notebooks with outputs, and large exports from agent discovery unless explicitly needed.
- Do not paste raw multi-megabyte logs into an agent prompt; first extract the exact failure or relevant records.
- Prefer continuing a successful focused session over repeatedly restarting broad repository discovery.

## How to evaluate models

Use three representative personal tasks: one bug fix, one pipeline change, and one documentation/refactor task. For each model, use a fresh session and the same prompt. Score:

- Tests passing and behavioral correctness
- Diff scope and code quality
- Wall-clock time
- Tokens and paid spend
- Number of manual corrections required

A model that feels faster is worth keeping if it produces correct, narrow diffs consistently. Your repository results override generic leaderboards.

## Free-tier contingency

The message “Free usage exceeded, subscribe to Go” means the complimentary OpenCode-hosted allocation is exhausted. It does not identify whether that allocation resets on a known schedule. Check the OpenCode console for a reset timestamp or usage breakdown. If none is shown, assume the free hosted allocation is unavailable until OpenCode restores it or you change access paths.

Zen lists `muse-spark-1.3-contributor-free` separately at a $0 token price while available. This is a different path from the generic hosted free allocation and may remain usable after login/configuration, but it can also be removed or throttled without notice.

## Decision rule

- Use free Muse Contributor only for personal, non-sensitive code while it works.
- If it stops, use Zen DeepSeek V4 Flash within the preset cap.
- Buy OpenCode Go only if its curated access and rolling usage limits are preferable to prepaid Zen billing for a full month of your actual workload.
- Do not treat any “free” model as a sole dependency.
