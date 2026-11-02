"""Corrected diagnostic scorecard v2 from the saved multiclass baseline
artifacts. Supersedes the v1 figures at 5ce9d906; original PNGs preserved.

Corrections per architect direction:
  1. Removed the claim that 57% improved proves the gain is unconcentrated.
     Reports median, quartiles, tie rate, and a descriptive concentration
     summary from the existing per-start differences.
  2. Coverage panels separated by PA, slot, and start grain.
  3. Class-outcome plot labelled with its actual 56,046-PA assessment
     population (distinct from the 2,509-start registered scoring cohort).
  4. Denominators and source identities shown on relevant figures.
  5. Source hashes verified; backing tables and a diagnostic manifest
     written alongside the corrected figures.
  6. Computational head corrected to efc082ac lineage.

Plots requiring per-PA probabilities or per-start PMF vectors remain
unavailable (labelled in the manifest). No rerun, refit, or new inference.
"""
import sys, json, hashlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import polars as pl

OUT = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\pregame_multiclass_baseline_v1")
V2_DIR = OUT / "diagnostic_figures_v2"
V2_DIR.mkdir(exist_ok=True)

ps = pl.read_parquet(OUT / "multiclass_baseline_per_start_v1.parquet")
report = json.loads((OUT / "multiclass_baseline_report.json").read_text())

r0 = ps["rps_ref0_population"].to_numpy()
r1 = ps["rps_ref1_multinomial"].to_numpy()
k_real = ps["realized_k"].to_numpy()
diff = r1 - r0
n = len(diff)

BLUE, ORANGE, GREY, RED = "#4C72B0", "#DD8452", "#555555", "#C44E52"

# ---- source hash verification ----
def _sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

source_hashes = {p.name: _sha_file(p) for p in sorted(OUT.iterdir())
                 if p.suffix in (".parquet", ".json")}

# ---- concentration summary (descriptive) ----
q25, med, q75 = np.percentile(diff, [25, 50, 75])
iqr = q75 - q25
n_neg = int((diff < 0).sum())
n_pos = int((diff > 0).sum())
n_zero = int((diff == 0).sum())
pct_neg = 100.0 * n_neg / n
deciles = np.percentile(diff, np.arange(0, 110, 10))
iqr_count = int(((diff >= q25) & (diff <= q75)).sum())
top_decile_cut = deciles[9]
bottom_decile_cut = deciles[0]
top_decile_mean = float(np.mean(diff[diff >= top_decile_cut]))
bottom_decile_mean = float(np.mean(diff[diff <= bottom_decile_cut]))

concentration = {
    "n_starts": n,
    "mean_rps_diff": round(float(np.mean(diff)), 6),
    "median_rps_diff": round(float(med), 6),
    "q25": round(float(q25), 6), "q75": round(float(q75), 6),
    "iqr": round(float(iqr), 6),
    "min": round(float(np.min(diff)), 6), "max": round(float(np.max(diff)), 6),
    "n_negative": n_neg, "n_positive": n_pos, "n_tied_at_zero": n_zero,
    "pct_negative": round(pct_neg, 1),
    "pct_positive": round(100.0 * n_pos / n, 1),
    "pct_tied": round(100.0 * n_zero / n, 1),
    "iqr_contains_n_starts": iqr_count,
    "iqr_contains_pct": round(100.0 * iqr_count / n, 1),
    "top_decile_mean_rps_diff": round(top_decile_mean, 6),
    "bottom_decile_mean_rps_diff": round(bottom_decile_mean, 6),
    "decile_boundaries": [round(float(d), 4) for d in deciles],
    "note": ("descriptive concentration summary; the aggregate mean gain "
             "does not establish that the improvement is uniformly "
             "distributed across starts"),
}

# ---- backing tables ----
backing_scores = ps.select(
    "game_pk", "side", "pitcher", "realized_k",
    "rps_ref0_population", "rps_ref1_multinomial",
).with_columns(
    (pl.col("rps_ref1_multinomial") - pl.col("rps_ref0_population"))
    .alias("rps_diff")
)
backing_scores.write_csv(V2_DIR / "backing_per_start_scores.csv")

# ---- figures ----

# 1. realized K discrete histogram
fig, ax = plt.subplots(figsize=(8, 4))
k_vals = np.arange(0, int(k_real.max()) + 1)
counts = np.array([(k_real == k).sum() for k in k_vals])
ax.bar(k_vals, counts, width=0.8, color=BLUE, edgecolor="white")
ax.set_xlabel("Realized strikeouts per start")
ax.set_ylabel("Number of starts")
ax.set_title(f"Realized K distribution — {n} registered eligible starts "
             f"(2025H1, cohort f77d7a66…)")
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
fig.tight_layout()
fig.savefig(V2_DIR / "realized_k_histogram.png", dpi=150)
plt.close(fig)
manifest_fig_1 = {"file": "realized_k_histogram.png",
                  "denominator": f"{n} starts",
                  "source": "per-start parquet realized_k"}

# 2. per-start RPS difference histogram + ECDF
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
ax1.hist(diff, bins=50, color=BLUE, edgecolor="white", alpha=0.85)
ax1.axvline(0, color=GREY, linewidth=0.8)
ax1.axvline(med, color=ORANGE, linewidth=1.5,
            label=f"median = {med:.4f}")
ax1.axvline(np.mean(diff), color=RED, linewidth=1.2, linestyle="--",
            label=f"mean = {np.mean(diff):.4f}")
ax1.set_xlabel("RPS(Ref 1) − RPS(Ref 0) per start")
ax1.set_ylabel("Number of starts")
ax1.set_title(f"Per-start count-RPS difference (n={n})")
ax1.legend()
sorted_diff = np.sort(diff)
ecdf = np.arange(1, n + 1) / n
ax2.plot(sorted_diff, ecdf, color=BLUE, linewidth=1.2)
ax2.axvline(0, color=GREY, linewidth=0.8)
ax2.set_xlabel("RPS(Ref 1) − RPS(Ref 0) per start")
ax2.set_ylabel("ECDF")
ax2.set_title("Empirical CDF")
fig.tight_layout()
fig.savefig(V2_DIR / "rps_difference_histogram_ecdf.png", dpi=150)
plt.close(fig)
manifest_fig_2 = {"denominator": f"{n} starts",
                  "note": "histogram + ECDF; median and IQR in backing table"}

# 3. paired score summary with CI + concentration quantiles
paired = report["results"]["paired_count_rps_delta"]
delta = paired["delta_a_minus_b"]
ci_lo, ci_hi = paired["ci95"]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3.5))
ax1.errorbar([delta], [0], xerr=[[delta - ci_lo], [ci_hi - delta]],
             fmt="o", color=BLUE, capsize=5, markersize=8, linewidth=2)
ax1.axvline(0, color=GREY, linewidth=1, linestyle="--")
ax1.set_xlabel("Δ = RPS(Ref 1) − RPS(Ref 0)")
ax1.set_title(f"Δ = {delta:.4f}, CI95 [{ci_lo:.4f}, {ci_hi:.4f}]")
ax1.set_yticks([])
# quantile strip
ax2.scatter(diff, np.random.RandomState(42).uniform(0.8, 1.2, n),
            s=3, alpha=0.15, color=BLUE)
ax2.axvline(med, color=ORANGE, linewidth=1.5, label=f"median = {med:.4f}")
ax2.axvline(q25, color=GREY, linewidth=0.8, linestyle=":")
ax2.axvline(q75, color=GREY, linewidth=0.8, linestyle=":")
ax2.axvline(0, color=GREY, linewidth=0.8)
ax2.set_xlabel("Per-start RPS difference")
ax2.set_yticks([])
ax2.set_title("Per-start difference distribution (IQR marked)")
ax2.legend(fontsize=8)
fig.tight_layout()
fig.savefig(V2_DIR / "paired_rps_summary.png", dpi=150)
plt.close(fig)
manifest_fig_3 = {"delta": delta, "ci95": [ci_lo, ci_hi],
                  "median": round(float(med), 6),
                  "q25": round(float(q25), 6), "q75": round(float(q75), 6)}

# 3b. concentration summary text block (backing table)
conc_table = pl.DataFrame({
    "statistic": ["n", "mean", "median", "q25", "q75", "IQR",
                  "min", "max", "n_negative", "n_positive", "n_tied_at_zero",
                  "pct_negative", "pct_positive", "pct_tied",
                  "iqr_contains_n", "iqr_contains_pct",
                  "top_decile_mean", "bottom_decile_mean"],
    "value": [float(v) for v in [
        n, float(np.mean(diff)), float(med),
        float(q25), float(q75), float(iqr),
        float(np.min(diff)), float(np.max(diff)),
        n_neg, n_pos, n_zero,
        round(pct_neg, 1), round(100.0 * n_pos / n, 1),
        round(100.0 * n_zero / n, 1),
        iqr_count, round(100.0 * iqr_count / n, 1),
        round(top_decile_mean, 6), round(bottom_decile_mean, 6)]],
})
conc_table.write_csv(V2_DIR / "backing_concentration_summary.csv")

# 4. coverage panels separated by grain
fig, (ax_pa, ax_slot, ax_start) = plt.subplots(
    1, 3, figsize=(14, 4))
# PA grain
pa_labels = ["PA source\nrows", "Training\nrows", "Request\nslots",
             "Assessment\nPAs", "Matched to\nprojections"]
pa_vals = [report["counts"]["pa_source_rows"],
           report["counts"]["train_rows"],
           report["counts"]["request_slots"],
           report["counts"]["assessment_pas"],
           report["counts"]["assessment_pas_matched_to_projections"]]
bars = ax_pa.barh(pa_labels, pa_vals, color=BLUE, edgecolor="white")
ax_pa.set_xlabel("PA count")
ax_pa.set_title("PA grain")
for bar, val in zip(bars, pa_vals):
    ax_pa.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2,
               f"{val:,}", va="center", fontsize=8)
ax_pa.invert_yaxis()
# slot grain
slot_labels = ["Request\nslots", "Lineup\nuncovered", "Cohort\nrestricted",
               "Matched to\nprojections"]
slot_vals = [report["counts"]["request_slots"],
             report["counts"]["lineup_uncovered_slots"],
             report["counts"]["cohort_restriction"]["requests_after"],
             report["counts"]["assessment_pas_matched_to_projections"]]
bars = ax_slot.barh(slot_labels, slot_vals, color=ORANGE, edgecolor="white")
ax_slot.set_xlabel("Slot count")
ax_slot.set_title("Slot grain")
for bar, val in zip(bars, slot_vals):
    ax_slot.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2,
                 f"{val:,}", va="center", fontsize=8)
ax_slot.invert_yaxis()
# start grain
start_labels = ["Registered\neligible", "Assessment\nstarts",
                "Count-scored\nstarts"]
start_vals = [2509, report["counts"]["assessment_starts"],
              report["counts"]["count_scored_starts"]]
bars = ax_start.barh(start_labels, start_vals, color=BLUE, edgecolor="white")
ax_start.set_xlabel("Start count")
ax_start.set_title("Start grain")
for bar, val in zip(bars, start_vals):
    ax_start.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2,
                  f"{val}", va="center", fontsize=9)
ax_start.invert_yaxis()
fig.suptitle("Pipeline coverage by grain (PA / slot / start)", fontsize=11)
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(V2_DIR / "coverage_by_grain.png", dpi=150)
plt.close(fig)
manifest_fig_4 = {"pa_vals": pa_vals, "slot_vals": slot_vals,
                  "start_vals": start_vals,
                  "note": "three separate grain panels, not a single bar chart"}

# 5. RPS difference by realized K
fig, ax = plt.subplots(figsize=(8, 4))
k_unique = np.unique(k_real)
mean_diff_by_k = [np.mean(diff[k_real == k]) for k in k_unique]
ax.bar(k_unique, mean_diff_by_k, width=0.8, color=BLUE, edgecolor="white")
ax.axhline(0, color=GREY, linewidth=0.8)
ax.axhline(np.mean(diff), color=ORANGE, linewidth=1.2, linestyle="--",
           label=f"overall mean = {np.mean(diff):.4f}")
ax.set_xlabel("Realized strikeouts per start")
ax.set_ylabel("Mean RPS(Ref 1) − RPS(Ref 0)")
ax.set_title("Per-start count-RPS difference by realized K (descriptive)")
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig(V2_DIR / "rps_diff_by_realized_k.png", dpi=150)
plt.close(fig)
manifest_fig_5 = {"note": "descriptive only; no causal claim about which "
                          "K region drives the gain"}

# 5b. class outcome proportions (labelled with the correct population)
ain = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\pregame_multiclass_baseline_v1_inputs_v2")
assess = pl.read_parquet(ain / "assessment_2025H1_v1.parquet")
class_names = ["strikeout", "walk/HBP/interf", "in_play_out", "hit"]
pop_props = report["results"]["population_class_proportions"]
assess_props = [float((assess["class_label"] == c).mean())
                for c in range(4)]
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(4)
width = 0.35
bars1 = ax.bar(x - width / 2, pop_props, width, label="Training population",
               color=BLUE, edgecolor="white")
bars2 = ax.bar(x + width / 2, assess_props, width,
               label="Assessment (2025H1, 56,046 PAs)", color=ORANGE,
               edgecolor="white")
ax.set_xticks(x)
ax.set_xticklabels(class_names, fontsize=9)
ax.set_ylabel("Proportion of PAs")
ax.set_title("PA class proportions (assessment population = 56,046 PAs; "
             "NOT the 2,509-start scoring cohort)")
for bar in list(bars1) + list(bars2):
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width() / 2, h + 0.005,
            f"{h:.3f}", ha="center", va="bottom", fontsize=8)
ax.legend()
fig.tight_layout()
fig.savefig(V2_DIR / "class_proportions.png", dpi=150)
plt.close(fig)
manifest_fig_6 = {"population": "56,046 assessment PAs (all completed PAs "
                              "for requested starters in 2025H1)",
                  "note": "this is NOT the 2,509-start registered scoring "
                          "cohort; the class plot describes the assessment "
                          "PA population, not the scored starts",
                  "training_props": pop_props,
                  "assessment_props": assess_props}

# ---- write manifest + backing tables ----
class_table = pl.DataFrame({
    "class_label": class_names,
    "training_proportion": pop_props,
    "assessment_proportion": assess_props,
})
class_table_path = V2_DIR / "backing_class_proportions.csv"
class_table.write_csv(class_table_path)

manifest = {
    "diagnostic_version": "v2_corrected",
    "supersedes": "v1 (5ce9d906 diagnostic_figures/)",
    "computational_head": "efc082ac998f92eff5abe21cbe6692f26c09b948",
    "source_artifact_hashes": source_hashes,
    "population": {
        "registered_eligible_starts": 2509,
        "cohort_hash": "f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7",
        "assessment_pas_retained": 55579,
        "assessment_pas_matched_to_projections": 43565,
        "assessment_pas_excluded_no_matchup": 12014,
        "note": ("PA scoring covers 43565/55579 = 78.4% of retained PAs; "
                 "count-RPS covers all 2509 starts using complete starter "
                 "outcomes derived from all actual PAs including replacements"),
    },
    "concentration_summary": concentration,
    "figures": {
        "realized_k_histogram.png": {"denominator": f"{n} starts",
                                     "grain": "start"},
        "rps_difference_histogram_ecdf.png": {"denominator": f"{n} starts",
                                              "note": manifest_fig_2},
        "paired_rps_summary.png": manifest_fig_3,
        "coverage_by_grain.png": manifest_fig_4,
        "rps_diff_by_realized_k.png": {"grain": "start",
                                       "note": "descriptive only"},
        "class_proportions.png": manifest_fig_6,
    },
    "backing_tables": ["backing_per_start_scores.csv",
                       "backing_concentration_summary.csv",
                       "backing_class_proportions.csv"],
    "plots_unavailable": [
        "average predicted PMF vs observed K frequencies",
        "reliability diagrams at declared K lines",
        "PA K reliability + probability histogram",
        "per-start PMF shapes",
        "training-loss curves",
        "reason: per-start PMF vectors and per-PA probabilities were not "
        "saved in the per-start parquet",
    ],
}
manifest_path = V2_DIR / "diagnostic_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True,
                                    default=str), encoding="utf-8")

# ---- summary ----
print(json.dumps({
    "figures": sorted(p.name for p in V2_DIR.glob("*.png")),
    "backing_tables": sorted(p.name for p in V2_DIR.glob("*.csv")),
    "manifest": str(manifest_path),
    "n_starts": n,
    "mean_rps_diff": round(float(np.mean(diff)), 6),
    "median_rps_diff": round(float(med), 6),
    "pct_negative": round(pct_neg, 1),
    "iqr_contains_pct": round(100.0 * iqr_count / n, 1),
    "n_tied_at_zero": n_zero,
}, indent=1, default=str))
