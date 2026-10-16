# bf-lane-v1 — SELF-CHECK PACKET FOR CHAT 2 (2026-10-16)

**Status: B0 AUDIT PASS + B1 FROZEN — NO FIT, NO SCORING, NO REAL-DATA RUN
has occurred anywhere in this packet.** Execution of B1 requires owner
authorization after this packet + the exact-head CI pass.

## What Chat 2 should check (in order)

1. **Mirror integrity**: `research/offseason_2026/specs/bf-lane-v1/` in the
   repo must be byte-identical to the lake authoritative dir
   `C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\` — verify every file
   against MANIFEST.json sha256s.
2. **B0 verdict**: `b0_audit.json` → verdict PASS; spot-check
   `checks.strictly_prior_construction` (7,194 / 7,194 prior_n rebuilt with 0
   mismatches, prior_mean/lg_mean dev 0.0) and
   `checks.pmf_validity` (sum-to-1 max dev 4.44e-16).
3. **B1 registration hash**: sha256(b1_registration.json) =
   `e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d`.
4. **Hard-rule review** (B1_REGISTRATION.md section 8 / b1_registration.json
   `hard_rules`): no current/eventual BF, no realized lineup, no
   outcome-dependent feature availability in pregame construction; short
   prior outings preserved (966 rows with 1<=prior_n<=9 scored, never
   excluded); explicit availability states (career debut 169 / insufficient
   history 966 / own distribution 6,059 / failed joins 0 / lineup inputs
   N-A-lineup-free 0).
5. **No-run evidence**: no run dir exists under the lake bf-lane-v1 other
   than the packet files; the only script is the read-only
   `scripts/b0_audit.py`; no MLflow run was created for bf-lane-v1.
6. **Exact-head CI**: CI status of the pushed repo HEAD containing this
   packet (recorded below once known).

## Exact-head CI record

| Item | Value |
| --- | --- |
| Branch | research/market-eval-v2 |
| Exact head SHA containing this packet | recorded in the session return after push |
| CI run | recorded in the session return after push (gh run view) |

## Registered next step (NOT executed)

ONE authorized real-data B1 run under `b1_registration.json` exactly as
frozen (Ridge alpha 1.0, folds verbatim, recentered-PMF uncertainty,
registered p_bar, paired 2000/20261001). Any deviation = new registration,
never an amendment of this one.
