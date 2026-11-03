"""Diagnostic scorecard from the saved multiclass baseline artifacts.

Generates five plots from existing authorized evidence + class-outcome
bars. All plots use ONLY the saved per-start parquet and report — no
rerun, no refit, no new inference. Plots requiring per-PA probabilities
or per-start PMF vectors are explicitly labelled unavailable.
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
FIG_DIR = OUT / "diagnostic_figures"
FIG_DIR.mkdir(exist_ok=True)

ps = pl.read_parquet(OUT / "multiclass_baseline_per_start_v1.parquet")
report = json.loads((OUT / "multiclass_baseline_report.json").read_text())

r0 = ps["rps_ref0_population"].to_numpy()
r1 = ps["rps_ref1_multinomial"].to_numpy()
k_real = ps["realized_k"].to_numpy()
diff = r1 - r0
n = len(diff)

BLUE, ORANGE, GREY = "#4C72B0", "#DD8452", "#555555"

# ============================================= 1. realized K histogram
fig, ax = plt.subplots(figsize=(8, 4))
k_vals = np.arange(0, k_real.max() + 1)
counts = np.array([(k_real == k).sum() for k in k_vals])
ax.bar(k_vals, counts, width=0.8, color=BLUE, edgecolor="white")
ax.set_xlabel("Realized strikeouts per start")
ax.set_ylabel("Number of starts")
ax.set_title(f"Realized K distribution — {n} registered starts (2025H1)")
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
fig.tight_layout()
fig.savefig(FIG_DIR / "realized_k_histogram.png", dpi=150)
plt.close(fig)

# ======================================== 2. per-start RPS difference
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
ax1.hist(diff, bins=50, color=BLUE, edgecolor="white", alpha=0.85)
ax1.axvline(0, color=GREY, linewidth=0.8)
ax1.axvline(np.mean(diff), color=ORANGE, linewidth=1.5,
            label=f"mean = {np.mean(diff):.4f}")
ax1.set_xlabel("RPS(Ref 1) − RPS(Ref 0) per start")
ax1.set_ylabel("Number of starts")
ax1.set_title("Per-start count-RPS difference")
ax1.legend()
sorted_diff = np.sort(diff)
ecdf = np.arange(1, n + 1) / n
ax2.plot(sorted_diff, ecdf, color=BLUE, linewidth=1.2)
ax2.axvline(0, color=GREY, linewidth=0.8)
ax2.set_xlabel("RPS(Ref 1) − RPS(Ref 0) per start")
ax2.set_ylabel("ECDF")
ax2.set_title("Empirical CDF of per-start difference")
fig.tight_layout()
fig.savefig(FIG_DIR / "rps_difference_histogram_ecdf.png", dpi=150)
plt.close(fig)

# ============================== 3. paired score summary with CI ======
paired = report["results"]["paired_count_rps_delta"]
delta = paired["delta_a_minus_b"]
ci_lo, ci_hi = paired["ci95"]
fig, ax = plt.subplots(figsize=(6, 3))
ax.errorbar([delta], [0], xerr=[[delta - ci_lo], [ci_hi - delta]],
            fmt="o", color=BLUE, capsize=5, markersize=8, linewidth=2)
ax.axvline(0, color=GREY, linewidth=1, linestyle="--")
ax.set_xlabel("Δ = RPS(Ref 1) − RPS(Ref 0) per start")
ax.set_title(f"Paired count-RPS difference with 95% CI\n"
             f"Δ = {delta:.4f}, CI95 [{ci_lo:.4f}, {ci_hi:.4f}], "
             f"n = {n} starts, bootstrap {paired['n_boot']}/seed {paired['seed']}")
ax.set_yticks([])
fig.tight_layout()
fig.savefig(FIG_DIR / "paired_rps_delta_ci.png", dpi=150)
plt.close(fig)

# ============================================= 4. coverage / accounting
counts = report["counts"]
labels = ["PA source rows", "Training rows", "Request slots",
          "Assessment PAs", "Matched to projections", "Assessment starts",
          "Count-scored starts"]
vals = [counts["pa_source_rows"], counts["train_rows"],
        counts["request_slots"], counts["assessment_pas"],
        counts["assessment_pas_matched_to_projections"],
        counts["assessment_starts"], counts["count_scored_starts"]]
fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.barh(labels, vals, color=BLUE, edgecolor="white")
ax.set_xlabel("Count")
ax.set_title("Pipeline coverage — from PA source to scored starts")
for bar, val in zip(bars, vals):
    ax.text(bar.get_width() + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
            f"{val:,}", va="center", fontsize=9)
ax.invert_yaxis()
fig.tight_layout()
fig.savefig(FIG_DIR / "coverage_accounting.png", dpi=150)
plt.close(fig)

# ==================== 5. RPS difference vs realized K (binned) =======
fig, ax = plt.subplots(figsize=(8, 4))
k_unique = np.unique(k_real)
mean_diff_by_k = [np.mean(diff[k_real == k]) for k in k_unique]
count_by_k = [int((k_real == k).sum()) for k in k_unique]
ax.bar(k_unique, mean_diff_by_k, width=0.8, color=BLUE, edgecolor="white")
ax.axhline(0, color=GREY, linewidth=0.8)
ax.axhline(np.mean(diff), color=ORANGE, linewidth=1.2, linestyle="--",
           label=f"overall mean = {np.mean(diff):.4f}")
ax.set_xlabel("Realized strikeouts per start")
ax.set_ylabel("Mean RPS(Ref 1) − RPS(Ref 0)")
ax.set_title("Per-start count-RPS difference by realized K (descriptive)")
ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
ax.legend()
fig.tight_layout()
fig.savefig(FIG_DIR / "rps_diff_by_realized_k.png", dpi=150)
plt.close(fig)

# ================================= 6. class outcome proportions ======
fig, ax = plt.subplots(figsize=(8, 4))
class_names = ["strikeout", "walk/HBP/interf", "in_play_out", "hit"]
pop_props = report["results"]["population_class_proportions"]
# assessment class proportions from the assessment parquet
ain = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\pregame_multiclass_baseline_v1_inputs_v2")
assess = pl.read_parquet(ain / "assessment_2025H1_v1.parquet")
n_assess = assess.height
assess_props = [float((assess["class_label"] == c).mean()) for c in range(4)]
x = np.arange(4)
width = 0.35
bars1 = ax.bar(x - width / 2, pop_props, width, label="Training population",
               color=BLUE, edgecolor="white")
bars2 = ax.bar(x + width / 2, assess_props, width,
               label="Assessment (2025H1)", color=ORANGE, edgecolor="white")
ax.set_xticks(x)
ax.set_xticklabels(class_names, fontsize=9)
ax.set_ylabel("Proportion")
ax.set_title("PA class proportions: training vs assessment")
for bar in list(bars1) + list(bars2):
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width() / 2, h + 0.005,
            f"{h:.3f}", ha="center", va="bottom", fontsize=8)
ax.legend()
fig.tight_layout()
fig.savefig(FIG_DIR / "class_proportions.png", dpi=150)
plt.close(fig)

# ================================================ summary output =====
print(json.dumps({
    "figures_generated": sorted(p.name for p in FIG_DIR.glob("*.png")),
    "n_starts": n,
    "mean_rps_ref0": float(np.mean(r0)),
    "mean_rps_ref1": float(np.mean(r1)),
    "delta": float(np.mean(diff)),
    "ci95": paired["ci95"],
    "pct_diff_lt_zero": float((diff < 0).mean() * 100),
    "pct_diff_gt_zero": float((diff > 0).mean() * 100),
    "realized_k_range": [int(k_real.min()), int(k_real.max())],
    "plots_unavailable": [
        "average predicted PMF vs observed K frequencies",
        "reliability diagrams at declared K lines",
        "PA K reliability + probability histogram",
        "per-start PMF shapes",
        "training-loss curves",
    ],
    "reason": "per-start PMF vectors and per-PA probabilities were not "
              "saved in the per-start parquet; the bridge output was not "
              "serialized with probability columns",
}, indent=1, default=str))
