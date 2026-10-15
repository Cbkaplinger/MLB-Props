"""review_verify.py -- reviewer-owned, READ-ONLY run-directory verification.

Review support tool (Chat 2 evidence area; not a readiness requirement).
Accepts a run directory and a registered packet/freeze JSON; verifies the
saved outputs against the registered config WITHOUT fitting, scoring, or
modifying anything:

  1. Output inventory + full SHA-256 hashes.
  2. Manifest identity: run label, candidates, confirmation status,
     registered input hashes where the packet declares them.
  3. Confirmation absence: no confirm prediction files when excluded.
  4. Candidate/fold identities: per-file eval-identity hashes vs the
     packet preflight (when present); shared rows/labels across candidates.
  5. Scores: per-fold and pooled RAW (and CAL where present) Brier/log loss
     recomputed from the saved predictions vs metrics.json.
  6. Registered contrasts: deltas, unadjusted percentile intervals,
     null-centered p-values, and Holm recomputed from the same per-row
     arrays + shared draw matrix vs the metrics.json hypothesis-test block
     (covers non-baseline endpoints that paired-vs-baseline omits).
  7. MLflow agreement (optional --skip-mlflow): children tagged with the
     run label; logged metrics vs recomputed values; missing runs reported
     as facts, not failures.

Exit code 0 = all checks pass; 1 = discrepancies (listed). JSON to stdout
or --json-out. Reuses the harness primitives (slate_date_draws) via
--harness-path when available; never modifies harness files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import polars as pl

EPS = 1e-15


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_harness(harness_path):
    if harness_path:
        sys.path.insert(0, str(harness_path))
    try:
        import comparison as cmp  # noqa: N813
        return cmp
    except Exception:
        return None


def llv(y, p):
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    y = np.asarray(y, dtype=np.float64)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brv(y, p):
    return (np.asarray(p, dtype=np.float64) - np.asarray(y, dtype=np.float64)) ** 2


def slate_date_draws(values, dates, blocks, n_boot, seed):
    """Whole-cluster slate-date draws (unit = game_date), block-stratified,
    row-weighted num/den; one rng stream in sorted-block order. Fallback
    mirror of the harness primitive (same semantics)."""
    rng = np.random.default_rng(seed)
    names = list(values)
    mat = np.vstack([np.asarray(values[n], dtype=np.float64) for n in names])
    num = np.zeros((n_boot, mat.shape[0])); den = np.zeros(n_boot)
    for b in sorted(set(blocks)):
        mask = np.array([x == b for x in blocks], dtype=bool)
        idx = np.nonzero(mask)[0]
        b_dates = sorted(set(dates[i] for i in idx))
        idx_of = {d: i for i, d in enumerate(b_dates)}
        d_idx = np.array([idx_of[dates[i]] for i in idx], dtype=np.int64)
        s = np.vstack([np.bincount(d_idx, weights=mat[mk][mask], minlength=len(b_dates))
                       for mk in range(mat.shape[0])])
        cnt = np.bincount(d_idx, minlength=len(b_dates)).astype(np.float64)
        draws = rng.multinomial(len(b_dates), np.full(len(b_dates), 1.0 / len(b_dates)), size=n_boot)
        num += draws @ s.T; den += draws @ cnt
    return num / den[:, None]


def nc_p(delta_obs, delta_rep):
    errs = np.asarray(delta_rep, dtype=np.float64) - float(delta_obs)
    assert errs.ndim == 1, f"replicate array not 1-D: {errs.shape}"
    return (1.0 + int(np.sum(np.abs(errs) >= abs(float(delta_obs))))) / (errs.size + 1.0)


def holm(pv):
    m = len(pv); adj = {}; run = 0.0
    for i, k in enumerate(sorted(pv, key=lambda k: pv[k])):
        run = max(run, (m - i) * pv[k]); adj[k] = min(1.0, run)
    return adj


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="reviewer run-directory verification (read-only)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--harness-path", default=None)
    ap.add_argument("--skip-mlflow", action="store_true")
    ap.add_argument("--mlflow-db",
                    default=r"C:\Users\ckaplinger\MLB-Props-Research\mlflow.db",
                    help="MLflow sqlite store to query (default: canonical)")
    ap.add_argument("--require-mlflow", action="store_true",
                    help="treat missing MLflow runs as a discrepancy (required "
                         "when the registered batch mandates automatic logging); "
                         "otherwise missing runs are informational")
    ap.add_argument("--require-live-resampling", action="store_true",
                    help="fail if the live harness primitive is unavailable and "
                         "the fallback mirror would be used (authoritative "
                         "reconciliations must not silently substitute)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    cfg = packet["config"]
    cmp_mod = load_harness(args.harness_path)
    n_boot = cfg.get("evaluation", {}).get("n_boot", 2000)
    seed = cfg.get("evaluation", {}).get("seed", 20261001)
    mlflow_required = bool(args.require_mlflow
                           or cfg.get("tracking", {}).get("require_automatic_mlflow"))

    rep: dict = {"run_dir": str(run_dir),
                 "packet": packet.get("batch", packet.get("packet", "?")),
                 "checks": {}, "discrepancies": [], "informational": []}

    def fail(msg):
        rep["discrepancies"].append(msg)

    # ---- 1. inventory ------------------------------------------------------
    files = sorted(f.name for f in run_dir.glob("*") if f.is_file())
    rep["checks"]["inventory"] = {
        "n_files": len(files), "files": files,
        "sha256": {f: sha256_file(run_dir / f) for f in files},
    }

    # ---- 2. manifest identity ----------------------------------------------
    if not (run_dir / "run_manifest.json").exists():
        fail("run_manifest.json missing")
        print(json.dumps(rep, indent=2, default=str))
        return 1
    M = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    met = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    cfg_cands = cfg.get("candidate_order") or list((cfg.get("candidates") or {}).keys())
    cands = M["config"]["candidates"]
    rep["checks"]["manifest"] = {
        "run_label": M.get("run_label"),
        "label_matches_registration": M.get("run_label") in (packet.get("run_id"), packet.get("batch_id")),
        "candidates": cands,
        "candidates_match_registration": cands == cfg_cands,
        "include_confirm": M["config"].get("include_confirm"),
        "confirm_block_status": M.get("confirm_block_status"),
        "registered_input_hashes": cfg.get("inputs", {}),
        "manifest_input_hashes": M.get("inputs_sha256", {}),
    }
    if not rep["checks"]["manifest"]["label_matches_registration"]:
        fail("run_label does not match the registered run_id/batch_id")
    if not rep["checks"]["manifest"]["candidates_match_registration"]:
        fail("manifest candidate list differs from registration")
    for k, want in (cfg.get("inputs") or {}).items():
        if k.endswith("_sha256"):
            got = M.get("inputs_sha256", {}).get(k[:-7])
            if got is not None and got != want:
                fail(f"registered input hash mismatch: {k}")

    # ---- 3. confirmation absence -------------------------------------------
    icf = M["config"].get("include_confirm")
    confirm_preds = sorted(p.name for p in run_dir.glob("preds_confirm_2025H2__*.parquet"))
    rep["checks"]["confirmation"] = {"include_confirm": icf, "confirm_pred_files": confirm_preds}
    if icf is False and confirm_preds:
        fail(f"confirmation excluded by config but {len(confirm_preds)} confirm prediction files present")

    # ---- 4. identities + shared rows/labels --------------------------------
    fold_names = sorted({f.name.split("__")[0][len("preds_"):] for f in run_dir.glob("preds_*__*.parquet")})
    reg = (cfg.get("preflight") or {}).get("fold_partitions") or {}
    frames, id_ok, shared_ok, counts = {}, True, True, {}
    for fold in fold_names:
        fs = {}
        for c in cands:
            fp = run_dir / f"preds_{fold}__{c}.parquet"
            if not fp.exists():
                fail(f"missing prediction file: {fp.name}")
                id_ok = False
                continue
            meta = json.loads(pl.read_parquet_metadata(fp).get("run_metadata") or "{}")
            if fold in reg and meta.get("eval_identity_sha256") != reg[fold]["eval_identity_sha256"]:
                id_ok = False
            fs[c] = p = pl.read_parquet(fp)
        frames[fold] = fs
        if len(fs) < len(cands):
            continue  # missing files already failed above; nothing to compare
        key = ["game_pk", "at_bat_number", "batter"]
        base = fs[cands[0]].select(key + ["y"]).sort(key)
        for c in cands[1:]:
            if c not in fs:
                continue
            o = fs[c].select(key + ["y"]).sort(key)
            if not base.equals(o):
                shared_ok = False
        counts[fold] = fs[cands[0]].height
    rep["checks"]["identities_and_shared_rows"] = {
        "eval_identity_hashes_match_registered": id_ok,
        "shared_rows_labels_across_candidates": shared_ok,
        "row_counts": counts,
    }
    if not id_ok:
        fail("per-candidate eval identity hashes differ from registered values")
    if not shared_ok:
        fail("candidates do not share identical rows/labels")

    # ---- 5. scores recomputation --------------------------------------------
    rec, pool = {}, {}
    for fold in fold_names:
        if len(frames[fold]) < len(cands):
            continue  # incomplete fold: already failed in the identity check
        rec[fold] = {}
        for c in cands:
            p = frames[fold][c]
            y = p["y"].to_numpy().astype(int)
            r = {"raw_ll": float(llv(y, p["pred_raw"].to_numpy()).mean()),
                 "raw_brier": float(brv(y, p["pred_raw"].to_numpy()).mean())}
            if "pred_cal" in p.columns:
                cal = p["pred_cal"].to_numpy()
                if not np.all(np.isnan(cal)):
                    r["cal_ll"] = float(llv(y, cal).mean())
                    r["cal_brier"] = float(brv(y, cal).mean())
            rec[fold][c] = r
            pool.setdefault(c, {"raw": [], "ll": [], "y": [], "dates": [], "blocks": []})
            pool[c]["raw"].append(brv(y, p["pred_raw"].to_numpy()))
            pool[c]["ll"].append(llv(y, p["pred_raw"].to_numpy()))
            pool[c]["y"].append(y)
            pool[c]["dates"].append(p["game_date"].to_list())
            pool[c]["blocks"].append([fold] * p.height)
    m_ok = True
    for fold in rec:
        for c in cands:
            if fold not in met["per_fold"] or c not in met["per_fold"][fold]:
                continue  # incomplete/stray fold: the identity check reported it
            e = met["per_fold"][fold][c]
            if (abs(e["log_loss"] - rec[fold][c]["raw_ll"]) > 1e-12
                    or abs(e["brier"] - rec[fold][c]["raw_brier"]) > 1e-12):
                m_ok = False
                fail(f"per-fold raw metric mismatch: {fold}/{c}")
    rep["checks"]["per_fold_raw_recompute_match"] = m_ok
    rep["checks"]["per_fold_scores"] = rec

    pooled_scores, p_rows = {}, {}
    dev_blocks = M["config"].get("dev_blocks") or cfg.get("dev_blocks") or fold_names
    other_folds = [f for f in fold_names if f not in dev_blocks]
    for c in cands:
        sel_folds = [i for i, f in enumerate(fold_names) if f in dev_blocks]
        raw_all = np.concatenate([pool[c]["raw"][i] for i in sel_folds])
        ll_all = np.concatenate([pool[c]["ll"][i] for i in sel_folds])
        pooled_scores[c] = {"log_loss": float(ll_all.mean()), "brier": float(raw_all.mean())}
        p_rows[c] = raw_all
    sel_folds = [i for i, f in enumerate(fold_names) if f in dev_blocks]
    p_dates = sum((pool[cands[0]]["dates"][i] for i in sel_folds), [])
    p_blocks = sum(([fold_names[i]] * frames[fold_names[i]][cands[0]].height
                    for i in sel_folds), [])
    p_ok = all(abs(pooled_scores[c]["log_loss"] - met["pooled_dev"]["candidates"][c]["log_loss"]) < 1e-12
               and abs(pooled_scores[c]["brier"] - met["pooled_dev"]["candidates"][c]["brier"]) < 1e-12
               for c in cands)
    rep["checks"]["pooled_row_weighted_recompute_match"] = p_ok
    rep["checks"]["pooled_scores"] = pooled_scores
    rep["checks"]["other_fold_scores_as_facts"] = {
        f: {c: {"raw_brier": float(brv(frames[f][c]["y"].to_numpy().astype(int),
                                        frames[f][c]["pred_raw"].to_numpy()).mean()),
                "raw_ll": float(llv(frames[f][c]["y"].to_numpy().astype(int),
                                    frames[f][c]["pred_raw"].to_numpy()).mean())}
            for c in cands if c in frames[f]}
        for f in other_folds}
    if not p_ok:
        fail("pooled dev scores do not reproduce row-weighted from saved predictions")

    # ---- 6. registered contrasts --------------------------------------------
    if cmp_mod is not None:
        res = cmp_mod.slate_date_draws(p_rows, p_dates, p_blocks, n_boot, seed)
        resampling_implementation = "live-harness"
    else:
        if args.require_live_resampling:
            fail("live harness resampling primitive unavailable and "
                 "--require-live-resampling was set; the fallback mirror must "
                 "not silently substitute during authoritative reconciliation")
        res = slate_date_draws(p_rows, p_dates, p_blocks, n_boot, seed)
        resampling_implementation = "fallback-mirror"
    rep["checks"]["resampling_implementation"] = resampling_implementation
    col_idx = {n: i for i, n in enumerate(p_rows)}
    reg_contrasts = (cfg.get("evaluation", {}).get("contrasts_predeclared")
                     or cfg.get("baseline_binding", {}).get("registered_contrasts") or [])
    ht = met["pooled_dev"].get("hypothesis_test_brier_raw", {}).get("contrasts", {})
    p_holm_input, rows_out = {}, {}
    for rc in reg_contrasts:
        cid = rc.get("id")
        if " minus " not in rc.get("contrast", ""):
            fail(f"registered contrast {cid}: unparseable contrast expression")
            continue
        a, b = [s.strip() for s in rc["contrast"].split(" minus ")]
        if a not in col_idx or b not in col_idx:
            fail(f"registered contrast {cid}: endpoint(s) absent from the run: {a}, {b}")
            continue
        ia, ib = col_idx[a], col_idx[b]
        d_rep = res[:, ia] - res[:, ib]
        assert d_rep.ndim == 1 and d_rep.shape[0] == res.shape[0]
        d_obs = float(p_rows[a].mean() - p_rows[b].mean())
        row = {"a": a, "b": b, "lane": "RAW (pred_raw)", "folds": FOLDS_snapshot(fold_names),
               "n_rows": int(p_rows[a].size),
               "aggregation": "row-weighted pooled dev mean",
               "delta_direct_per_row": d_obs,
               "ci95_unadjusted": [float(np.percentile(d_rep, 2.5)),
                                   float(np.percentile(d_rep, 97.5))],
               "p_value": float(nc_p(d_obs, d_rep))}
        if cid in ht:
            row["matches_canonical_delta"] = abs(ht[cid]["delta"] - d_obs) < 1e-12
            row["matches_canonical_p"] = abs(ht[cid]["p_value"] - row["p_value"]) < 1e-12
            row["canonical_reports_interval"] = "ci95_unadjusted" in ht[cid] or "ci95" in ht[cid]
            if not row["matches_canonical_delta"]:
                fail(f"contrast {cid}: recomputed delta differs from canonical")
            if not row["matches_canonical_p"]:
                fail(f"contrast {cid}: recomputed p-value differs from canonical")
        p_holm_input[cid] = row["p_value"]
        rows_out[cid] = row
    hmap = holm(p_holm_input)
    for cid, row in rows_out.items():
        row["p_holm"] = hmap[cid]
        if cid in ht and abs(ht[cid]["p_holm"] - hmap[cid]) > 1e-9:
            fail(f"contrast {cid}: Holm adjusted p differs from canonical")
    rep["checks"]["contrasts"] = rows_out

    # ---- 7. MLflow agreement (optional) -------------------------------------
    if not args.skip_mlflow:
        try:
            con = sqlite3.connect(args.mlflow_db)
            cur = con.cursor()
            label = M.get("run_label")
            # Importer tag convention: run_id tag = "<label>" (first-run) or
            # "<label>-<harness-run-id 12..64 hex>" (recency). Match the label
            # exactly or as a prefix so both conventions are found; children
            # are also discovered via mlflow.parentRunId.
            runs = cur.execute(
                "SELECT DISTINCT r.run_uuid, r.name FROM runs r "
                "JOIN tags t ON r.run_uuid=t.run_uuid "
                "WHERE t.key='run_id' AND (t.value=? OR t.value LIKE ? || '-%')",
                (label, label)).fetchall()
            child_ids = [r[0] for r in cur.execute(
                "SELECT t.run_uuid FROM tags t WHERE t.key='mlflow.parentRunId' "
                "AND t.value IN (SELECT run_uuid FROM runs WHERE name LIKE ? || '%')",
                (label,)).fetchall()]
            known = {r[0] for r in runs} | set(child_ids)
            agree, checked = True, 0
            for rid, name in runs:
                parts = name.split("__")
                if len(parts) != 3:
                    continue
                cand, fold, lane = parts
                if cand not in cands or fold not in frames or lane not in ("raw", "cal"):
                    continue
                col = "pred_raw" if lane == "raw" else "pred_cal"
                if col not in frames[fold][cand].columns:
                    continue
                y = frames[fold][cand]["y"].to_numpy().astype(int)
                pv = frames[fold][cand][col].to_numpy()
                mm = dict(cur.execute("SELECT key, value FROM metrics WHERE run_uuid=?",
                                      (rid,)).fetchall())
                if "brier" in mm and abs(float(mm["brier"]) - float(brv(y, pv).mean())) > 1e-9:
                    agree = False
                    fail(f"MLflow brier mismatch: {name}")
                if "log_loss" in mm and abs(float(mm["log_loss"]) - float(llv(y, pv).mean())) > 1e-9:
                    agree = False
                    fail(f"MLflow log_loss mismatch: {name}")
                checked += 1
            rep["checks"]["mlflow"] = {"parent_and_children_tagged": len(runs),
                                       "children_via_parent_tag": len(child_ids),
                                       "children_metric_checked": checked,
                                       "agreement": agree,
                                       "required": mlflow_required,
                                       "classification": ("REQUIRED-MISSING"
                                                          if mlflow_required and not known
                                                          else ("OK" if known else "INFORMATIONAL-MISSING")),
                                       "note": ("no tagged runs found: run was not logged "
                                                "(fact, not failure)" if not known else "")}
            if not known and mlflow_required:
                fail("MLflow runs missing but the registered batch requires "
                     "automatic logging (required check)")
        except Exception as e:
            rep["checks"]["mlflow"] = {"status": "unavailable", "error": str(e)[:120]}
            if mlflow_required:
                fail("MLflow store unavailable but required for a batch that "
                     "mandates automatic logging")

    rep["verdict"] = "ALL-CHECKS-PASS" if not rep["discrepancies"] else "DISCREPANCIES"
    payload = json.dumps(rep, indent=2, default=str)
    if args.json_out:
        Path(args.json_out).write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if not rep["discrepancies"] else 1


def FOLDS_snapshot(fold_names):
    return list(fold_names)


if __name__ == "__main__":
    sys.exit(main())


