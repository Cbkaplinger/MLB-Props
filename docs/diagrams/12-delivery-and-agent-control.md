# 12 - Delivery and agent control (TARGET-STATE, PROPOSED 2026-10-21)

> Depicts the PROPOSED operating architecture, not a claim that all
> connections are implemented or validated. Existing diagrams remain until
> their consumers are checked.

```mermaid
flowchart TB
    O["Owner<br/>Goals, restricted authorizations"]
    A["Architect<br/>Critical path, ADR/PRD, bounded tasks"]
    Q["Canonical task record<br/>Owner, paths, acceptance, dependencies"]

    B["Chat 1: Builder<br/>Separate worktree"]
    C["Published checkpoint N<br/>Immutable SHA and test receipt"]
    R["Chat 2: Trailing reviewer/fixer<br/>Separate worktree"]
    F["Integrated repair checkpoint<br/>Reconciled head and affected tests"]
    V["Non-author acceptance<br/>Exact SHA; no self-approval"]

    N["Chat 1: Next independent chunk<br/>No overlapping repair paths"]
    G["Restricted execution / acceptance gate<br/>Authorization remains separate"]

    D["Chat 3: Temporary cleaner<br/>Approved independent scope"]
    P["Cleanup milestone<br/>Docs checks and bounded review"]

    O --> A --> Q
    Q --> B --> C
    C --> R --> F --> V --> G
    C --> N
    Q --> D --> P
    O -. "Required authorization" .-> G
    V -. "Evidence / unresolved issues" .-> A
```
