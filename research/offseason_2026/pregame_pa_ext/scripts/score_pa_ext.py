"""pregame-pa-ext-v1 SCORING STEP (separate from the build; NOT executed in
this card - the command is recorded in report.json / manifest.json).

Runs ONLY after the frozen payload exists:
  0. verify the payload sha256 against manifest.json (STOP on mismatch);
  1. label join: realized K per start from the overnight-p2 preds files
     (grouped by game_pk/pitcher, realized-BF-count checked against
     bf_forecasts.realized_bf); expected 0 exclusions on this cohort;
  2. per-start count-RPS / log score / mean-K RMSE / milestone Briers
     (PMF-tail exceedance via kcount_combiner.exceedance) for the two
     REGISTERED RAW arms (h3_raw, l5_raw);
  3. paired count-RPS / log score / milestone comparisons h3_raw - l5_raw
     with slate-date bootstrap (2000 resamples, seed 20261001);
  4. secondary descriptive: the payload's stored CALIBRATED arms
     recomputed through the same aggregation must reproduce the accepted
     pregame-state-v1 v3 uniq_* per-start metrics BIT-IDENTICALLY
     (<=1e-12) - a machinery-equivalence gate; and raw-vs-accepted uniq
     paired diffs per arm.

Usage:  python scripts/score_pa_ext.py
Outputs: data/start_metrics_paext.parquet, report_scored.json,
         reports/scoring_summary.txt
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

import paext_core as core

WORK = core.WORK
V3_METRICS = core.PREGAME_STATE / "data" / "start_metrics_v3.parquet"


def main() -> None:
    manifest = json.loads(core.MANIFEST.read_text(encoding="ascii"))
    payload_sha = core.sha256_file(core.PAYLOAD)
    assert payload_sha == manifest["payload"]["sha256"], (
        f"STOP: frozen payload hash mismatch: {payload_sha} != "
        f"{manifest['payload']['sha256']}")
    payload = pl.read_parquet(core.PAYLOAD)
    assert payload.height == manifest["payload"]["rows"]
    print("payload hash verified:", payload_sha[:16], "...")

    fc = (
        pl.read_parquet(core.BFW / "bf_forecasts.parquet")
        .filter(
            (pl.col("game_date") >= core.WINDOW[0])
            & (pl.col("game_date") <= core.WINDOW[1])
        )
        .select("game_pk", "side", "pitcher", "game_date", "realized_bf")
    )
    preds = pl.concat(
        [pl.read_parquet(core.P2_DATA / f) for f in core.PREDS.values()],
        how="vertical",
    ).filter(
        (pl.col("game_date") >= core.WINDOW[0])
        & (pl.col("game_date") <= core.WINDOW[1])
    )
    grouped = {
        k: g for k, g in preds.partition_by(
            ["game_pk", "pitcher"], as_dict=True, maintain_order=False
        ).items()
    }
    rows = []
    n_no_pas = n_bf_mismatch = 0
    for s in fc.to_dicts():
        g = grouped.get((s["game_pk"], s["pitcher"]))
        if g is None:
            n_no_pas += 1
            continue
        n_real = g.height
        if n_real != s["realized_bf"]:
            n_bf_mismatch += 1
            continue
        k_real = int(g["y"].sum())
        rows.append({"game_pk": s["game_pk"], "side": s["side"],
                     "pitcher": s["pitcher"], "game_date": s["game_date"],
                     "realized_k": k_real})
    realized = pl.DataFrame(rows).sort(
        ["game_date", "game_pk", "side"])
    assert realized.height == core.EXPECTED_N_STARTS, (
        f"label join lost rows: no-PAs={n_no_pas} bf-mismatch={n_bf_mismatch}")

    lab = payload.join(
        realized, on=["game_pk", "side", "pitcher", "game_date"],
        how="inner",
    )
    assert lab.height == core.EXPECTED_N_STARTS

    # ------------- per-start metrics, registered RAW arms
    new_cols = {}
    for tag in ("h3_raw", "l5_raw"):
        pk_all = lab.select(core.PMF_COLS[tag]).to_numpy()
        k_all = lab["realized_k"].to_numpy()
        mean_all = lab[f"mean_k_{tag}"].to_numpy()
        new_cols[f"{tag}_rps"] = [
            core.count_rps(pk, int(k)) for pk, k in zip(pk_all, k_all)]
        new_cols[f"{tag}_logscore"] = [
            core.count_logscore(pk, int(k)) for pk, k in zip(pk_all, k_all)]
        new_cols[f"{tag}_rmse_mean_k"] = list((mean_all - k_all) ** 2)
        for m in core.MILESTONES:
            pge = np.array([core.exceedance(pk, m) for pk in pk_all])
            y = (k_all >= m).astype(np.float64)
            new_cols[f"{tag}_brier_ge{m}"] = list((pge - y) ** 2)
    lab = lab.with_columns(
        *[pl.Series(name, vals) for name, vals in new_cols.items()])

    # lab and cmp must carry the same starts in the same row order: the
    # machinery gate and the secondary bootstrap both pair raw-arm rows
    # (lab) with the v3 uniq_* columns (cmp). Sort both on the full start
    # key so the pairing is deterministic (join order alone is not
    # guaranteed); the explicit alignment assert runs once cmp exists.
    key_cols = ["game_date", "game_pk", "side", "pitcher"]
    lab = lab.sort(key_cols)

    # ------------- machinery-equivalence gate: calibrated arms must
    # reproduce the accepted v3 uniq metrics bit-identically (<=1e-12)
    v3_full = pl.read_parquet(V3_METRICS)
    v3 = v3_full.select(
        "game_pk", "side", "pitcher", "game_date",
        *[c for c in v3_full.columns if c.startswith("uniq_")],
    )
    bf37 = lab.select(core.PMF37_COLS).to_numpy()
    recomp = {}
    for tag in ("h3_cal", "l5_cal"):
        p9 = lab.select([f"p_{tag}_{i}" for i in range(1, 10)]).to_numpy()
        pms = np.zeros((lab.height, core.K_MAX))
        means = np.zeros(lab.height)
        for r in range(lab.height):
            pk, mean_k, _, _ = core.start_count_pmf(p9[r], bf37[r])
            pms[r] = pk
            means[r] = mean_k
        recomp[tag] = (pms, means)
    cmp = lab.join(v3, on=["game_pk", "side", "pitcher", "game_date"],
                   how="inner", suffix="_v3")
    assert cmp.height == core.EXPECTED_N_STARTS, "v3 comparison join lost rows"
    cmp = cmp.sort(key_cols)
    assert cmp.select(key_cols).equals(lab.select(key_cols)), (
        "cmp/lab key misalignment: the uniq_* comparison columns would "
        "not pair with the raw-arm rows")
    bit_id = {}
    for tag, v3name in (("h3_cal", "h3"), ("l5_cal", "l5")):
        pms, means = recomp[tag]
        k_all = cmp["realized_k"].to_numpy()
        rps = np.array([core.count_rps(pk, int(k))
                        for pk, k in zip(pms, k_all)])
        logs = np.array([core.count_logscore(pk, int(k))
                         for pk, k in zip(pms, k_all)])
        d_rps = float(np.abs(rps - cmp[f"uniq_{v3name}_rps"].to_numpy()).max())
        d_log = float(np.abs(
            logs - cmp[f"uniq_{v3name}_logscore"].to_numpy()).max())
        d_mean = float(np.abs(
            means - cmp[f"uniq_{v3name}_err_mean_k"
                        ].to_numpy() - k_all).max())
        bit_id[tag] = {"rps_max_abs_diff": d_rps,
                       "logscore_max_abs_diff": d_log,
                       "mean_k_max_abs_diff": d_mean}
        assert d_rps <= 1e-12 and d_log <= 1e-12 and d_mean <= 1e-12, (
            f"machinery bit-identity FAILED vs v3 uniq_{v3name}: {bit_id[tag]}")
    print("machinery bit-identity vs accepted v3 uniq arms: PASS")

    # ------------- paired comparisons, slate-date bootstrap
    dates = lab["game_date"].to_numpy()

    def paired(a: str, b: str) -> dict:
        return core.v1.slate_bootstrap(
            lab[a].to_numpy() - lab[b].to_numpy(), dates)

    def paired_uniq(a: str, b: str) -> dict:
        # the uniq_* metrics live on cmp (the v3 join), never on lab
        # (full_run-1 crash: ColumnNotFoundError "uniq_h3_rps" not found);
        # cmp is key-aligned to lab (assert above), so dates pair with
        # the cmp rows
        return core.v1.slate_bootstrap(
            lab[a].to_numpy() - cmp[b].to_numpy(), dates)

    boot = {}
    for metric in ("rps", "logscore"):
        boot[f"h3_raw_minus_l5_raw_{metric}"] = paired(
            "h3_raw_" + metric, "l5_raw_" + metric)
    for ms in core.MILESTONES:
        boot[f"h3_raw_minus_l5_raw_brier_ge{ms}"] = paired(
            f"h3_raw_brier_ge{ms}", f"l5_raw_brier_ge{ms}")
    for tag in ("h3_raw", "l5_raw"):
        base = "h3" if tag.startswith("h3") else "l5"
        for metric in ("rps", "logscore"):
            boot[f"{tag}_minus_v3uniq_{base}_{metric}"] = paired_uniq(
                f"{tag}_{metric}", f"uniq_{base}_{metric}")

    agg = {}
    for tag in ("h3_raw", "l5_raw"):
        agg[tag] = {
            "rps": float(lab[f"{tag}_rps"].mean()),
            "logscore": float(lab[f"{tag}_logscore"].mean()),
            "rmse_mean_k": float(np.sqrt(
                (lab[f"{tag}_rmse_mean_k"] ** 2).mean())),
            **{f"brier_ge{m}": float(lab[f"{tag}_brier_ge{m}"].mean())
               for m in core.MILESTONES},
        }

    out_metrics = lab.sort(["game_date", "game_pk", "side"])
    out_metrics.write_parquet(WORK / "data" / "start_metrics_paext.parquet")
    report = {
        "card": "pregame-pa-ext-v1",
        "step": "scoring (label join + paired metrics)",
        "payload_sha256_verified": payload_sha,
        "n_starts": int(lab.height),
        "label_join_exclusions": {"n_no_pas": n_no_pas,
                                  "n_bf_mismatch": n_bf_mismatch},
        "aggregate": agg,
        "bootstrap": {"n": core.BOOT_N, "seed": core.BOOT_SEED,
                      "unit": "slate-date (game_date)"},
        "bootstrap_results": boot,
        "machinery_bit_identity_vs_v3_uniq": bit_id,
    }
    (WORK / "report_scored.json").write_text(
        json.dumps(report, indent=1), encoding="ascii")
    lines = [
        "pregame-pa-ext-v1 SCORING summary",
        "=" * 50,
        f"starts: {lab.height}; payload hash verified",
        json.dumps(agg, indent=1),
        json.dumps(boot, indent=1),
    ]
    (WORK / "reports" / "scoring_summary.txt").write_text(
        "\n".join(lines) + "\n", encoding="ascii")
    print(json.dumps(agg, indent=1))
    print(json.dumps(boot, indent=1))


if __name__ == "__main__":
    main()
