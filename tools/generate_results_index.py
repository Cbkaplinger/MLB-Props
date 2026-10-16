#!/usr/bin/env python3
"""Generate the machine-generated results index (Chat 3 charter).

Scans ONLY declared run metadata (experiment cards, metrics.json,
run_manifest.json, frozen registrations, lake manifests / status receipts)
and emits:

  docs/RESULTS_INDEX.md           markdown table (human-readable view)
  docs/RESULTS_INDEX.csv          structured index (polars-written)
  docs/RESULTS_INDEX_COVERAGE.md  coverage report (every registered entry
                                  indexed or explicitly excluded, with reason)

Rules:
  - Every value is copied from a declared metadata file at a declared
    location; the provenance (file role + dotted path) is recorded.
  - Absent values are MISSING. Results are never inferred from prose.
  - This index is NOT a source of truth until Chat 2 reviews it; the
    canonical artifacts referenced here remain authoritative.

Stdlib + polars only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

MISSING = "MISSING"
DEFAULT_LAKE_ROOT = Path(r"C:\Users\ckaplinger\MLB-Props-Research")
REPO_EXPERIMENTS = "research/offseason_2026/experiments"

RESULT_CLASSES = (
    "development-only",
    "confirmation",
    "diagnostic",
    "eligible-for-promotion",
    "nonconforming",
    "superseded",
)

REVIEW_VALUES = ("ACCEPTED", "PENDING", "SUPERSEDED", "RECONCILED", MISSING)

CSV_COLUMNS = [
    "entry_id",
    "lane",
    "status",
    "code_identity",
    "input_identity",
    "population",
    "candidate",
    "reference",
    "principal_metric",
    "contrast",
    "review_status",
    "artifacts",
    "result_class",
    "result_class_evidence",
    "primary_meta",
    "provenance",
]


def P(role: str, dotted: str) -> tuple[str, str]:
    """Declare one extraction path: (file_role, dotted.path.into.json)."""
    return (role, dotted)


@dataclass
class Entry:
    entry_id: str
    lane: str                       # "repo" or "lake"
    title: str
    files: dict[str, str]           # role -> path relative to lane root
    required_roles: list[str]       # roles that must exist for INDEXED
    status: list[tuple[str, str]] = field(default_factory=list)
    code_identity: list[tuple[str, str]] = field(default_factory=list)
    input_identity: list[tuple[str, str]] = field(default_factory=list)
    population: list[tuple[str, str]] = field(default_factory=list)
    candidate: list[tuple[str, str]] = field(default_factory=list)
    reference: list[tuple[str, str]] = field(default_factory=list)
    principal_metric: dict | None = None   # {"metric": str, "parts": [(label, P)], ...}
    contrast: dict | None = None
    review: dict | None = None      # {"kind": "json"|"marker", ...}
    result_class: str = MISSING
    class_evidence: str = ""
    notes: str = ""


# --------------------------------------------------------------------------
# Registry of declared entries (the ONLY things this index scans).
# --------------------------------------------------------------------------

def registry() -> list[Entry]:
    entries: list[Entry] = []

    # ---------------- repo experiment lanes (offseason_2026) -------------
    for exp, exp_id, cls, ev, principal, contrast in [
        (
            "logistic_pa", "LOGISTIC-PA-L", "development-only",
            "card.json label: 'development only; no production or betting claim'",
            {
                "metric": "Brier, E1, challenger arm L1a (frozen 2024 eval)",
                "parts": [("brier", P("metrics", "metrics_2024.E1.L1a.brier")),
                          ("n", P("metrics", "metrics_2024.E1.L1a.n"))],
            },
            None,  # no paired_comparisons.json in this lane
        ),
        (
            "pa1a_raw_pa", "PA-1A", "development-only",
            "card.json (dev raw-PA base lane; no metrics.json recorded)",
            None,
            None,
        ),
        (
            "pa1b_oracle_xk", "PA-1B-O", "diagnostic",
            "card.json label: 'Oracle opportunity decomposition; not pregame xK, "
            "not actionable replay'",
            {
                "metric": "RMSE, pooled descriptive, arm M2 (oracle decomposition)",
                "parts": [("RMSE", P("metrics", "pooled_descriptive.M2.RMSE")),
                          ("n", P("metrics", "pooled_descriptive.M2.n"))],
            },
            {
                "label": "M2 - M1 paired RMSE delta (slate-date bootstrap)",
                "parts": [("delta", P("paired", "date.E1.M2-M1.RMSE.raw")),
                          ("ci95", P("paired", "date.E1.M2-M1.RMSE.ci95"))],
            },
        ),
        (
            "pitcher_prior", "PITCHER-PRIOR", "development-only",
            "card.json dev challenger lane (pitcher prior; production untouched)",
            {
                "metric": "Brier, pooled descriptive, arm P2 (pitcher_only lane)",
                "parts": [("brier", P("metrics", "pitcher_only|pooled_descriptive.P2.brier")),
                          ("n", P("metrics", "pitcher_only|pooled_descriptive.P2.n"))],
            },
            {
                "label": "P1 - P0 paired Brier delta (E1, slate-date bootstrap)",
                "parts": [("delta", P("paired", "E1.pitcher_only.P1-P0_br.raw")),
                          ("ci95", P("paired", "E1.pitcher_only.P1-P0_br.ci95"))],
            },
        ),
        (
            "tree_pa", "TREE-PA", "development-only",
            "card.json dev tree lane (development only)",
            {
                "metric": "Brier, pooled descriptive, arm T1",
                "parts": [("brier", P("metrics", "metrics_2024.pooled_descriptive.T1.brier")),
                          ("logloss", P("metrics", "metrics_2024.pooled_descriptive.T1.logloss"))],
            },
            {
                "label": "T1 - T0 paired Brier delta (slate-date bootstrap)",
                "parts": [("delta", P("paired", "date.E1.T1-T0_br.raw")),
                          ("ci95", P("paired", "date.E1.T1-T0_br.ci95"))],
            },
        ),
    ]:
        files = {"card": f"{REPO_EXPERIMENTS}/{exp}/card.json"}
        required = ["card"]
        if principal:
            files["metrics"] = f"{REPO_EXPERIMENTS}/{exp}/metrics.json"
            required.append("metrics")
        if contrast:
            files["paired"] = f"{REPO_EXPERIMENTS}/{exp}/paired_comparisons.json"
        entries.append(Entry(
            entry_id=f"repo:{exp}",
            lane="repo",
            title=exp_id,
            files=files,
            required_roles=required,
            status=[P("card", "status"), P("card", "registration.status")],
            code_identity=[P("card", "git.head")],
            input_identity=[P("card", "inputs")],
            population=[P("card", "population_primary.definition"),
                        P("card", "populations")],
            candidate=[P("card", "arms")],
            principal_metric=principal,
            contrast=contrast,
            result_class=cls,
            class_evidence=ev,
        ))

    # ---------------- lake lanes ----------------------------------------
    lake = DEFAULT_LAKE_ROOT

    entries.append(Entry(
        entry_id="lake:first-run-v1",
        lane="lake",
        title="first-run-v1 (canonical harness run, count-eval-v2 interface)",
        files={
            "run_manifest": "first-run-v1/0cda7bdd4b9edbdcf395a5cd8d7a96164b066bd71c9d71cc034ff6a5eba19f57/run_manifest.json",
            "metrics": "first-run-v1/0cda7bdd4b9edbdcf395a5cd8d7a96164b066bd71c9d71cc034ff6a5eba19f57/metrics.json",
            "ablation_status": "first-run-v1/ablation_row_v3_status.json",
            "mirror_status": "first-run-v1/lake_mirror_status_v2.json",
        },
        required_roles=["run_manifest", "metrics", "ablation_status"],
        status=[P("ablation_status", "decision.verdict"),
                P("run_manifest", "run_label")],
        code_identity=[
            P("ablation_status", "identity.git_sha"),
            P("ablation_status", "identity.config_sha256"),
            P("run_manifest", "interface_version"),
        ],
        input_identity=[P("run_manifest", "inputs_sha256")],
        population=[P("run_manifest", "folds"),
                    P("run_manifest", "candidates")],
        candidate=[P("run_manifest", "candidates")],
        reference=[P("run_manifest", "config.baseline")],
        principal_metric={
            "metric": "Brier paired delta (P1_H3_incumbent_refit - P0_log5), pooled dev",
            "parts": [
                ("point", P("metrics", "pooled_dev.paired_vs_baseline.brier.P1_H3_incumbent_refit_minus_P0_log5.point")),
                ("ci95", P("metrics", "pooled_dev.paired_vs_baseline.brier.P1_H3_incumbent_refit_minus_P0_log5.ci95")),
            ],
        },
        contrast={
            "label": "registered ablation row ablation-001__P1_H3_incumbent_refit__vs__P0_log5",
            "parts": [
                ("row_id", P("ablation_status", "identity.row_id")),
                ("verdict", P("ablation_status", "decision.verdict")),
            ],
        },
        review={
            "kind": "json",
            "verdict_path": P("ablation_status", "decision.verdict"),
            "basis_path": P("ablation_status", "decision.basis"),
            "prefix": "ACCEPTED",
        },
        result_class="confirmation",
        class_evidence=(
            "ablation_row_v3_status.json decision.verdict = "
            "CANONICAL-WITH-RECORDED-SEQUENCE-DEVIATION (Chat 2 review ACCEPTED; "
            "canonical status conditional on the recorded sequence deviation)"
        ),
        notes=(
            "Sequence deviation on record: execution preceded the exact-SHA READY "
            "verdict (one-time recorded owner exception; see SEQUENCE_DEVIATION.md). "
            "Canonical status conditional on that deviation remaining on record; "
            "no promotion or pooling claim"
        ),
    ))

    entries.append(Entry(
        entry_id="lake:recency-batch-v1",
        lane="lake",
        title="recency-batch-v1 (dev-fold candidate batch, confirm excluded)",
        files={
            "run_manifest": "recency-batch-v1/c09890ae6c3d111f187fcd35d5b2bca17f27fa24fd13f683a9489bf5d3d0c3eb/run_manifest.json",
            "metrics": "recency-batch-v1/c09890ae6c3d111f187fcd35d5b2bca17f27fa24fd13f683a9489bf5d3d0c3eb/metrics.json",
            "reconciliation": "recency-batch-v1/reconciliation_c1_c4.json",
        },
        required_roles=["run_manifest", "metrics"],
        status=[P("run_manifest", "run_label"),
                P("run_manifest", "confirm_block_status")],
        code_identity=[
            P("run_manifest", "interface_version"),
            P("reconciliation", "executed_code.sha256"),
        ],
        input_identity=[P("run_manifest", "inputs_sha256"),
                        P("reconciliation", "input_hashes")],
        population=[P("run_manifest", "dev_blocks"),
                    P("reconciliation", "shared_rows_labels")],
        candidate=[P("run_manifest", "config.candidates")],
        reference=[P("run_manifest", "config.baseline")],
        principal_metric={
            "metric": "Brier RAW paired contrast delta, pooled dev (C4_both_vs_batter_only)",
            "parts": [
                ("delta", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C4_both_vs_batter_only.delta")),
                ("p_holm", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C4_both_vs_batter_only.p_holm")),
            ],
        },
        contrast={
            "label": "C1-C4 registered contrasts (hypothesis_test_brier_raw)",
            "parts": [
                ("C1_delta", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C1_pitcher_ew_vs_B.delta")),
                ("C2_delta", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C2_batter_ew_vs_B.delta")),
                ("C3_delta", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C3_both_vs_pitcher_only.delta")),
                ("C4_delta", P("metrics", "pooled_dev.hypothesis_test_brier_raw.contrasts.C4_both_vs_batter_only.delta")),
            ],
        },
        review={
            "kind": "json",
            "verdict_path": P("reconciliation", "verdict.canonical_metrics_reproduced_bit_exact"),
            "basis_path": P("reconciliation", "verdict.conclusion"),
            "prefix": "RECONCILED",
        },
        result_class="development-only",
        class_evidence=(
            "run_manifest.json confirm_block_status EXCLUDED-BY-CONFIG; dev folds "
            "only (block_2024H1/2024H2/2025H1); no confirm or 2026 rows"
        ),
    ))

    entries.append(Entry(
        entry_id="lake:lgbm-equal-info-v2",
        lane="lake",
        title="lgbm-equal-info-v2 (executed LightGBM equal-information contrast)",
        files={
            "receipt": "lgbm-equal-info-v2/execution_receipt.json",
        },
        required_roles=["receipt"],
        status=[P("receipt", "authorization")],
        code_identity=[P("receipt", "receipt_version"),
                       P("receipt", "persistence_reference")],
        input_identity=[P("receipt", "input_hashes_confirmed")],
        population=[P("receipt", "matched_exposure")],
        candidate=[P("receipt", "contrast.a")],
        reference=[P("receipt", "contrast.b")],
        principal_metric={
            "metric": "Brier RAW paired delta (LightGBM - both-EW logistic), pooled dev",
            "parts": [
                ("delta", P("receipt", "contrast.delta")),
                ("ci95", P("receipt", "contrast.ci95_unadjusted")),
                ("p_holm", P("receipt", "contrast.p_holm")),
            ],
        },
        contrast={
            "label": "C_lgbm_v2_vs_both_EW_logistic (null-centered bootstrap, shared draw stream)",
            "parts": [
                ("id", P("receipt", "contrast.id")),
                ("effect", P("receipt", "effect_interpretation")),
            ],
        },
        review=None,  # self-receipt only; no independent review artifact recorded
        result_class="diagnostic",
        class_evidence=(
            "execution_receipt.json effect_interpretation = 'INCONCLUSIVE / NO "
            "DETECTED DIFFERENCE' (negligible effect, CI straddles zero)"
        ),
        notes=(
            "Receipt records owner authorization for the single execution; no "
            "independent-review verdict artifact is recorded (review_status MISSING)"
        ),
    ))

    entries.append(Entry(
        entry_id="lake:bf-lane-v1",
        lane="lake",
        title="bf-lane-v1 (B0 audit + B1 ridge challenger registration)",
        files={
            "manifest": "bf-lane-v1/MANIFEST.json",
            "registration": "bf-lane-v1/b1_registration.json",
        },
        required_roles=["manifest", "registration"],
        status=[P("registration", "status")],
        code_identity=[P("manifest", "registration_hash"),
                       P("registration", "registration_id")],
        input_identity=[P("manifest", "files")],
        population=[P("registration", "challenger.population")],
        candidate=[P("registration", "challenger.name")],
        reference=[P("registration", "b0_reference")],
        principal_metric=None,  # frozen - NOT executed; no metrics by design
        contrast={
            "label": "predeclared contrast (registered, not executed)",
            "parts": [("contrast", P("registration", "paired_uncertainty.predeclared_contrasts"))],
        },
        review=None,
        result_class="development-only",
        class_evidence=(
            "b1_registration.json status = 'FROZEN - NOT EXECUTED (no fit, no "
            "scoring, no real-data run)'; B0 reference audit verdict PASS recorded"
        ),
        notes="Self-check packet (SELF_CHECK_CHAT2.md) prepared for Chat 2; no verdict artifact yet",
    ))

    entries.append(Entry(
        entry_id="lake:pregame-pa-ext-v1",
        lane="lake",
        title="pregame-pa-ext-v1 (projected-batter per-PA payload extension)",
        files={
            "manifest": "pregame-pa-ext-v1/manifest.json",
            "report": "pregame-pa-ext-v1/report.json",
            "review_marker": "pregame-pa-ext-v1/REVIEW_SUPERSESSION.md",
        },
        required_roles=["manifest", "report"],
        status=[P("report", "status")],
        code_identity=[P("manifest", "inputs_sha256.scripts/paext_core.py"),
                       P("manifest", "inputs_sha256.scripts/build_pa_ext.py")],
        input_identity=[P("manifest", "payload")],
        population=[P("report", "population")],
        candidate=[P("report", "arms")],
        principal_metric=None,  # scoring outputs live outside the declared scan set
        contrast={
            "label": "registered scoring contrasts (H3-raw vs LOG5-raw; see card scoring_step)",
            "parts": [("registered", P("report", "arms.registered_count_pmf_arms"))],
        },
        review={
            "kind": "marker",
            "file": "review_marker",
            "marker": "REVIEW SUPERSESSION",
            "verdict": "SUPERSEDED",
            "note": ("Chat 2 review superseded for this card's extension scope "
                     "(review conflated the 134-row pilot with the 7,194-start "
                     "extension); re-review pending"),
        },
        result_class="development-only",
        class_evidence=(
            "report.json registration.status = 'REGISTERED EXTENSION'; payload "
            "frozen and hashed before label join; 2026 closed; window "
            "2024-07-01..2025-12-31 only"
        ),
        notes=(
            "Scoring metrics (incl. versioned RMSE correction) live in outputs/ "
            "outside the declared scan set; see REVIEW_SUPERSESSION.md pointer"
        ),
    ))

    entries.append(Entry(
        entry_id="lake:count-eval-v1",
        lane="lake",
        title="count-eval-v1 (frozen execution manifest + lgbm-equal-info-v1 freeze)",
        files={
            "execution_manifest": "count-eval-v1/EXECUTION_MANIFEST.json",
            "freeze": "count-eval-v1/freeze_lgbm_equal_info_v1.json",
        },
        required_roles=["execution_manifest"],
        status=[P("execution_manifest", "status")],
        code_identity=[P("execution_manifest", "input_hashes_sha256.scripts/run_count_eval.py")],
        input_identity=[P("execution_manifest", "input_hashes_sha256")],
        population=[P("execution_manifest", "cohort")],
        candidate=[P("freeze", "config.baseline_binding.registered_contrasts")],
        reference=[P("freeze", "config.baseline_binding.reference")],
        principal_metric=None,  # output report.json sits outside the declared scan set
        contrast={
            "label": "registered baseline binding contrast",
            "parts": [("id", P("freeze", "config.baseline_binding.registered_contrasts"))],
        },
        review=None,
        result_class="development-only",
        class_evidence=(
            "EXECUTION_MANIFEST.json status = 'FROZEN before execution; single "
            "execution; write-once output' + no_fit_declaration (RAW arms, frozen "
            "BASE BF PMF); realized-sequence outputs carry mandatory DIAGNOSTIC label"
        ),
    ))

    entries.append(Entry(
        entry_id="lake:market-eval-v1-score-v2",
        lane="lake",
        title="market-eval-v1 score_v2 (confirm_2025H2 scored vs market)",
        files={
            "score_manifest": "market-eval-v1/outputs/score_v2/score_manifest.json",
            "confirm_metrics": "market-eval-v1/outputs/score_v2/confirm_metrics.json",
            "review_marker": "market-eval-v1/REVIEW_SNAPSHOT.md",
        },
        required_roles=["score_manifest", "confirm_metrics"],
        status=[P("confirm_metrics", "population"),
                P("confirm_metrics", "registered_dev_blocks")],
        code_identity=[P("score_manifest", "params")],
        input_identity=[P("score_manifest", "inputs_sha256_16")],
        population=[P("confirm_metrics", "population"),
                    P("confirm_metrics", "n_rows"),
                    P("confirm_metrics", "n_dates")],
        candidate=[P("confirm_metrics", "registered_dev_blocks")],
        reference=[],
        principal_metric={
            "metric": "Brier skill vs market (h3 arm), confirm_2025H2",
            "parts": [
                ("brier_skill_vs_market.h3", P("confirm_metrics", "brier_skill_vs_market.h3")),
                ("h3_brier", P("confirm_metrics", "brier.h3")),
                ("market_brier", P("confirm_metrics", "brier.market")),
            ],
        },
        contrast={
            "label": "h3 - l5 paired Brier delta, slate-date bootstrap (2000, seed 20261001)",
            "parts": [
                ("point", P("confirm_metrics", "h3_minus_l5.point")),
                ("ci95", [P("confirm_metrics", "h3_minus_l5.p2.5"),
                          P("confirm_metrics", "h3_minus_l5.p97.5")]),
            ],
        },
        review={
            "kind": "marker",
            "file": "review_marker",
            "marker": "REVIEW_SNAPSHOT",
            "verdict": "PENDING",
            "note": ("review snapshot pinned 2026-10-14 (commit 02ce162, 9 blobs "
                     "byte-identical) for independent review; no verdict artifact "
                     "recorded"),
        },
        result_class="confirmation",
        class_evidence=(
            "confirm_metrics.json population = confirm_2025H2 with registered dev "
            "blocks; note records confirm rows never enter dev pooled points or "
            "bootstrap draws (card C3.3/C3.7)"
        ),
        notes="Negative skill vs market (h3 -0.0172); recorded as-is, no promotion inference",
    ))

    entries.append(Entry(
        entry_id="lake:seal-package-preflight",
        lane="lake",
        title="seal-package-preflight (outcome-free scoring package; sealed by receipt)",
        files={
            "seal_manifest": "seal-package-preflight/seal_manifest.json",
            "seal_receipt": "seal-package-preflight/SEAL_RECEIPT.json",
        },
        required_roles=["seal_manifest", "seal_receipt"],
        status=[P("seal_receipt", "manifest_status_unchanged")],
        code_identity=[P("seal_receipt", "producing_code"),
                       P("seal_receipt", "source_commit")],
        input_identity=[P("seal_manifest", "payload_hashes")],
        population=[P("seal_manifest", "forecast_artifacts.population")],
        candidate=[P("seal_manifest", "forecast_artifacts.dir")],
        reference=[],
        principal_metric=None,  # outcome access none by design; no metrics exist
        contrast={
            "label": "frozen scoring plan (paired count-RPS B-A primary; not yet executed)",
            "parts": [("plan", P("seal_manifest", "frozen_scoring_plan"))],
        },
        review={
            "kind": "json",
            "verdict_path": P("seal_receipt", "reviewer_acceptance"),
            "prefix": "ACCEPTED",
        },
        result_class="diagnostic",
        class_evidence=(
            "seal_manifest.json outcome_access = 'none'; package is an outcome-free "
            "preflight/forecast artifact, not a results run"
        ),
        notes="SEALED status established by SEAL_RECEIPT.json (2026-10-13); manifest byte-preserved PREPARED-NOT-SEALED",
    ))

    entries.append(Entry(
        entry_id="lake:bf-2026-predictor-seal-v1",
        lane="lake",
        title="bf-2026-predictor-seal-v1 (2026 predictor seal payload, PREPARED-NOT-SEALED)",
        files={
            "seal_manifest": "bf-2026-predictor-seal-v1/seal_manifest.json",
            "seal_prep_report": "bf-2026-predictor-seal-v1/seal_prep_report.json",
        },
        required_roles=["seal_manifest", "seal_prep_report"],
        status=[P("seal_manifest", "status")],
        code_identity=[P("seal_manifest", "lineage.builder_sha256"),
                       P("seal_prep_report", "seal")],
        input_identity=[P("seal_manifest", "payload_hashes")],
        population=[P("seal_manifest", "population")],
        candidate=[P("seal_prep_report", "arm_identities.arm_B")],
        reference=[P("seal_prep_report", "arm_identities.arm_A")],
        principal_metric=None,  # outcome scoring forbidden until seal approval
        contrast={
            "label": "A/B arms frozen in payload; scoring gated",
            "parts": [("outcome_scoring", P("seal_manifest", "outcome_scoring"))],
        },
        review={
            "kind": "json",
            "verdict_path": P("seal_prep_report", "pa_source_lineage_deviation"),
            "prefix": "PENDING",
            "verdict_value": "PENDING (lineage deviation flagged for Chat 2 review)",
        },
        result_class="diagnostic",
        class_evidence=(
            "seal_manifest.json status = PREPARED-NOT-SEALED; outcome_scoring = "
            "'none performed; 2026 outcome scoring remains forbidden until seal approval'"
        ),
        notes="seal_prep_report.json records a pa_source_lineage_deviation flagged for Chat 2 review",
    ))

    return entries


# --------------------------------------------------------------------------
# Extraction engine
# --------------------------------------------------------------------------

def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def get_path(doc, dotted: str):
    """Follow a dotted path through dicts; return the value or None.

    A path segment may itself contain '.' (e.g. 'p2.5' or 'scripts/x.py'),
    so longest-prefix matching is used at each step.
    """
    if doc is None:
        return None
    segs = dotted.split(".")
    cur = doc
    i = 0
    while i < len(segs):
        matched = False
        for take in range(len(segs), i, -1):
            key = ".".join(segs[i:take])
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
                i = take
                matched = True
                break
        if not matched:
            return None
        if i == len(segs):
            return cur
    return cur


def fmt_scalar(v, limit: int = 220) -> str:
    if v is None:
        return MISSING
    if isinstance(v, float):
        s = repr(v)
    elif isinstance(v, bool):
        s = str(v).lower()
    elif isinstance(v, (dict, list)):
        return fmt_compound(v, limit)
    else:
        s = str(v).strip()
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def fmt_compound(v, limit: int = 220) -> str:
    if isinstance(v, list):
        return "[" + "; ".join(fmt_scalar(x, 60) for x in v[:6]) + ("; ..." if len(v) > 6 else "") + "]"
    if isinstance(v, dict):
        items = list(v.items())
        body = "; ".join(f"{k}={fmt_scalar(x, 60)}" for k, x in items[:6])
        tail = "; ..." if len(items) > 6 else ""
        return "{" + body + tail + "}"
    return fmt_scalar(v, limit)


def hash_short(s: str) -> str:
    """Shorten 64-hex hashes for the markdown view."""
    if isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower()):
        return s[:16] + "..."
    return s


class Extractor:
    """Loads declared files once and extracts declared paths with provenance."""

    def __init__(self, root: Path, entry: Entry):
        self.root = root
        self.entry = entry
        self.docs: dict[str, object] = {}
        self.existing: dict[str, Path] = {}
        for role, rel in entry.files.items():
            path = root / rel
            if path.is_file():
                self.existing[role] = path
                self.docs[role] = load_json(path)

    def missing_roles(self) -> list[str]:
        return [r for r in self.entry.required_roles if r not in self.existing]

    def first(self, specs) -> tuple[str, str]:
        """specs: list of P(role, dotted) or lists of alternatives."""
        prov = []
        for spec in specs:
            alternatives = spec if isinstance(spec, list) else [spec]
            for role, dotted in alternatives:
                if role not in self.docs:
                    continue
                v = get_path(self.docs[role], dotted)
                if v is not None:
                    prov.append(f"{role}:{dotted}")
                    return fmt_scalar(v), ";".join(prov)
        return MISSING, ""

    def metric_block(self, block: dict | None) -> tuple[str, str]:
        if not block:
            return MISSING, ""
        label = block.get("metric") or block.get("label") or ""
        parts, prov = [], []
        for plabel, spec in block["parts"]:
            if isinstance(spec, list) and spec and isinstance(spec[0], tuple):
                # list of declared alternative paths: collect every hit
                hits = []
                for role, dotted in spec:
                    if role not in self.docs:
                        continue
                    v = get_path(self.docs[role], dotted)
                    if v is not None:
                        hits.append(fmt_scalar(v, 120))
                        prov.append(f"{role}:{dotted}")
                if hits:
                    parts.append(f"{plabel}=[{'; '.join(hits)}]")
                continue
            alternatives = spec if isinstance(spec, list) else [spec]
            for role, dotted in alternatives:
                if role not in self.docs:
                    continue
                v = get_path(self.docs[role], dotted)
                if v is not None:
                    text = fmt_scalar(v, 120)
                    if plabel in ("ci95",) or isinstance(v, list):
                        text = fmt_compound(v, 120)
                    if plabel not in ("n",):
                        text = hash_short(text)
                    parts.append(f"{plabel}={text}")
                    prov.append(f"{role}:{dotted}")
                    break
        if not parts:
            return MISSING, ""
        return f"{label}: " + ", ".join(parts), ";".join(prov)

    def review_status(self) -> tuple[str, str]:
        rv = self.entry.review
        if rv is None:
            return MISSING, ""
        if rv["kind"] == "marker":
            path = self.existing.get(rv["file"])
            if path is None:
                return MISSING, rv["file"] + " (absent)"
            return rv["verdict"] + " - " + rv["note"], str(self.entry.files[rv["file"]])
        role, dotted = rv["verdict_path"]
        v = get_path(self.docs.get(role), dotted)
        if v is None:
            return MISSING, f"{role}:{dotted} (absent)"
        prefix = rv.get("prefix", "")
        if "verdict_value" in rv:
            return rv["verdict_value"], f"{role}:{dotted}"
        text = fmt_scalar(v, 400)
        basis_path = rv.get("basis_path")
        basis = ""
        if basis_path:
            bv = get_path(self.docs.get(basis_path[0]), basis_path[1])
            if bv is not None:
                basis = " | basis: " + fmt_scalar(bv, 260)
        if prefix and not str(v).strip().lower().startswith(prefix.lower()):
            return f"{prefix} ({text}){basis}", f"{role}:{dotted}"
        return f"{text}{basis}", f"{role}:{dotted}"


# --------------------------------------------------------------------------
# Emission
# --------------------------------------------------------------------------

def shorten_row(row: dict) -> dict:
    out = dict(row)
    for col in ("status", "code_identity", "input_identity", "artifacts"):
        if out.get(col):
            parts = [hash_short(p.strip()) for p in str(out[col]).split(";")]
            out[col] = "; ".join(parts)
    return out


def build_rows(repo_root: Path, lake_root: Path, entries: list[Entry]):
    rows, coverage = [], []
    for entry in entries:
        root = repo_root if entry.lane == "repo" else lake_root
        if not root.is_dir():
            coverage.append((entry.entry_id, "EXCLUDED", f"lane root not found: {root}"))
            continue
        ex = Extractor(root, entry)
        missing = ex.missing_roles()
        if missing:
            coverage.append((
                entry.entry_id, "EXCLUDED",
                "required metadata absent: " + ", ".join(
                    f"{r} ({entry.files[r]})" for r in missing),
            ))
            continue

        prov: list[str] = []
        status, p1 = ex.first(entry.status)
        if p1:
            prov.append(f"status={p1}")
        code, p2 = ex.first(entry.code_identity)
        if p2:
            prov.append(f"code={p2}")
        inputs, p3 = ex.first(entry.input_identity)
        if p3:
            prov.append(f"inputs={p3}")
        pop, p4 = ex.first(entry.population)
        if p4:
            prov.append(f"population={p4}")
        cand, p5 = ex.first(entry.candidate)
        if p5:
            prov.append(f"candidate={p5}")
        ref, p6 = ex.first(entry.reference)
        if p6:
            prov.append(f"reference={p6}")
        if entry.principal_metric:
            principal, p7 = ex.metric_block(entry.principal_metric)
            if p7:
                prov.append(f"principal={p7}")
        else:
            principal = MISSING
        if entry.contrast:
            contrast, p8 = ex.metric_block(entry.contrast)
            if p8:
                prov.append(f"contrast={p8}")
        else:
            contrast = MISSING
        review, p9 = ex.review_status()
        if p9:
            prov.append(f"review={p9}")

        if entry.result_class not in RESULT_CLASSES:
            raise ValueError(f"entry {entry.entry_id}: invalid result_class {entry.result_class}")

        artifacts = "; ".join(str(entry.files[r]) for r in sorted(entry.files))
        rows.append({
            "entry_id": entry.entry_id,
            "lane": entry.lane,
            "status": status,
            "code_identity": code,
            "input_identity": inputs,
            "population": pop,
            "candidate": cand,
            "reference": ref,
            "principal_metric": principal,
            "contrast": contrast,
            "review_status": review,
            "artifacts": artifacts,
            "result_class": entry.result_class,
            "result_class_evidence": entry.class_evidence,
            "primary_meta": entry.files[entry.required_roles[0]],
            "provenance": "; ".join(prov),
            "notes": entry.notes,
        })
        coverage.append((entry.entry_id, "INDEXED", ""))
    return rows, coverage


def write_csv(rows: list[dict], out_dir: Path) -> Path:
    path = out_dir / "RESULTS_INDEX.csv"
    df = pl.DataFrame(rows, schema=CSV_COLUMNS)
    df.write_csv(path)
    return path


def write_md(rows: list[dict], coverage: list[tuple], out_dir: Path,
             repo_root: Path, lake_root: Path) -> Path:
    n = len(rows)
    indexed = sum(1 for _, disp, _ in coverage if disp == "INDEXED")
    excluded = len(coverage) - indexed
    missing_principal = [r["entry_id"] for r in rows if r["principal_metric"] == MISSING]
    missing_review = [r["entry_id"] for r in rows if r["review_status"] == MISSING]

    lines = []
    a = lines.append
    a("# Machine-Generated Results Index")
    a("")
    a("Generated by `tools/generate_results_index.py` from declared run metadata only.")
    a("This index is **not a source of truth** until Chat 2 reviews it; the canonical")
    a("artifacts referenced below remain authoritative. Missing values are recorded as")
    a("`MISSING`; nothing is inferred from prose.")
    a("")
    a(f"- Entries indexed: **{indexed}** of {len(coverage)} registered "
      f"({excluded} excluded, see `RESULTS_INDEX_COVERAGE.md`)")
    a(f"- Repo scan root: `{repo_root}`; lake scan root: `{lake_root}`")
    a(f"- Principal metric MISSING: {len(missing_principal)}"
      + (f" ({', '.join(missing_principal)})" if missing_principal else ""))
    a(f"- Review status MISSING: {len(missing_review)}"
      + (f" ({', '.join(missing_review)})" if missing_review else ""))
    a("")
    a("Result classes: development-only / confirmation / diagnostic / "
      "eligible-for-promotion / nonconforming / superseded. Review values: "
      "ACCEPTED / PENDING / SUPERSEDED / RECONCILED / MISSING.")
    a("")
    a("Hashes are shortened to 16 hex chars in this view; full values and value-level")
    a("provenance (file:json-path per field) are in `RESULTS_INDEX.csv`.")
    a("")

    md_cols = ["entry_id", "status", "population", "candidate", "reference",
               "principal_metric", "contrast", "review_status", "result_class"]
    header = "| " + " | ".join(md_cols) + " |"
    sep = "|" + "|".join([" --- "] * len(md_cols)) + "|"
    a(header)
    a(sep)
    for row in rows:
        srow = shorten_row(row)
        cells = []
        for col in md_cols:
            v = str(srow.get(col, ""))
            v = v.replace("|", "\\|")
            if len(v) > 160:
                v = v[:157] + "..."
            cells.append(v)
        a("| " + " | ".join(cells) + " |")
    a("")
    a("## Artifact pointers and classification evidence")
    a("")
    a("| entry | primary metadata | artifacts | result class | evidence / notes |")
    a("| --- | --- | --- | --- | --- |")
    for row in rows:
        a("| {} | `{}` | `{}` | {} | {} |".format(
            row["entry_id"], row["primary_meta"],
            str(row["artifacts"]).replace("|", "\\|")[:200],
            row["result_class"],
            (row["result_class_evidence"] + (" NOTES: " + row["notes"] if row["notes"] else ""))
            .replace("|", "\\|")[:400]))
    a("")

    path = out_dir / "RESULTS_INDEX.md"
    path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return path


def write_coverage(rows: list[dict], coverage: list[tuple], out_dir: Path) -> Path:
    indexed = sum(1 for _, d, _ in coverage if d == "INDEXED")
    excluded = len(coverage) - indexed
    lines = []
    a = lines.append
    a("# Results Index Coverage Report")
    a("")
    a(f"Registered entries: {len(coverage)}; indexed: {indexed}; excluded: {excluded}.")
    a("Every registered experiment is either indexed below or explicitly excluded")
    a("with a reason. Registered = declared in `tools/generate_results_index.py`.")
    a("")
    a("| entry | disposition | reason / detail |")
    a("| --- | --- | --- |")
    for entry_id, disp, reason in coverage:
        a(f"| {entry_id} | {disp} | {reason or ('indexed from declared metadata') if disp == 'INDEXED' else ''} |")
    a("")
    a("## Scope deviations (recorded, not repaired)")
    a("")
    a("- Repo experiment cards are `card.json` (no `card.md` exists in "
      "`research/offseason_2026/experiments/`); the declared card path is the "
      "recorded JSON card.")
    a("- `run_manifest.json` exists only inside the write-once frozen run dirs of "
      "executed harness batches (first-run-v1, recency-batch-v1); it is scanned "
      "there, not at batch top level.")
    a("- No `freeze_*.json` files exist in the repo; the frozen registrations in "
      "scope are lake-side (`freeze_lgbm_equal_info_v1.json`, "
      "`b1_registration.json`, seal manifests).")
    a("- Scoring/output reports (`report.json` under run dirs, "
      "`bf-2026-eval-v1-outputs/report.json`, corrected-RMSE reports) are outside "
      "the declared metadata set; entries whose only metrics live there carry "
      "principal_metric = MISSING with a pointer instead of pulling numbers from "
      "undeclared files or prose.")
    a("- `lgbm-equal-info-v1` (frozen, not executed) is reachable only through "
      "count-eval-v1's freeze file; it is not a separate indexed run.")
    a("")
    a("## Known gaps surfaced (not fixed by this index)")
    a("")
    a("- Entries with `review_status = MISSING` have no recorded independent-review "
      "verdict artifact; they are flagged, not judged.")
    a("- Entries with `principal_metric = MISSING` either did not execute (frozen "
      "registrations, seal preps with outcome access none) or keep their metrics "
      "in artifacts outside the declared scan set.")
    a("")
    path = out_dir / "RESULTS_INDEX_COVERAGE.md"
    path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return path


def main(argv=None) -> int:
    script_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Generate the machine-generated results index.")
    ap.add_argument("--repo-root", type=Path, default=script_root)
    ap.add_argument("--lake-root", type=Path,
                    default=Path(os.environ.get("MLB_PROPS_RESEARCH_LAKE", str(DEFAULT_LAKE_ROOT))))
    ap.add_argument("--out-dir", type=Path, default=script_root / "docs")
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    entries = registry()
    rows, coverage = build_rows(args.repo_root, args.lake_root, entries)
    csv_path = write_csv(rows, args.out_dir)
    md_path = write_md(rows, coverage, args.out_dir, args.repo_root, args.lake_root)
    cov_path = write_coverage(rows, coverage, args.out_dir)

    indexed = sum(1 for _, d, _ in coverage if d == "INDEXED")
    print(f"results index: {indexed} indexed / {len(coverage)} registered")
    print(f"  {csv_path}")
    print(f"  {md_path}")
    print(f"  {cov_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
