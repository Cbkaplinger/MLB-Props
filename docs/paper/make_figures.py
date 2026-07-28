"""Generate manuscript figures from reported metrics (no new findings)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "figure.dpi": 160,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

GREEN = "#1b5e20"
GREEN_FILL = "#e8f5e9"
BLUE = "#1565c0"
PURPLE = "#4a148c"


def _box(ax, x, y, w, h, text, fontsize=9) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=GREEN_FILL,
            edgecolor=GREEN,
            linewidth=1.5,
            mutation_aspect=0.3,
            zorder=2,
        )
    )
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color="#1a1a1a",
        linespacing=1.25,
        zorder=3,
    )


def _arrow(ax, x0, y0, x1, y1) -> None:
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.3,
            color="#333333",
            zorder=1,
        )
    )


def fig1_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    ax.set_xlim(0, 10.2)
    ax.set_ylim(0, 4.2)
    ax.axis("off")

    bw, bh = 2.05, 1.05
    top_y, bot_y = 2.35, 0.45
    xs = [0.35, 2.75, 5.15, 7.55]

    top_labels = [
        "Raw Statcast\nparquet",
        "Level 1\nGame aggregates",
        "Level 2\nLagged rolling form",
        "Level 3\nTraining frame",
    ]
    bot_labels = [
        "k-rate\nLightGBM",
        "Projected TBF\nRidge",
        "Count layer\nE[K], P(K ≥ L)",
    ]
    # Bottom row aligns under Levels 1–3 (skip raw)
    bot_xs = xs[1:]

    for x, text in zip(xs, top_labels):
        _box(ax, x, top_y, bw, bh, text)
    for x, text in zip(bot_xs, bot_labels):
        _box(ax, x, bot_y, bw, bh, text)

    # Top flow
    for i in range(3):
        _arrow(ax, xs[i] + bw + 0.02, top_y + bh / 2, xs[i + 1] - 0.02, top_y + bh / 2)
    # Vertical L1/L2/L3 → models
    for x in bot_xs:
        _arrow(ax, x + bw / 2, top_y - 0.02, x + bw / 2, bot_y + bh + 0.02)
    # Bottom flow k-rate → TBF → count
    for i in range(2):
        _arrow(
            ax,
            bot_xs[i] + bw + 0.02,
            bot_y + bh / 2,
            bot_xs[i + 1] - 0.02,
            bot_y + bh / 2,
        )

    ax.text(
        5.1,
        3.85,
        "Leakage-safe pregame stack: rate × exposure → expected strikeouts",
        ha="center",
        va="center",
        fontsize=11,
        fontweight="bold",
        color="#111111",
    )
    fig.savefig(OUT / "fig1_pipeline.png")
    plt.close(fig)


def fig2_model_comparison() -> None:
    models = ["Mean", "Ridge", "LightGBM"]
    mae = [0.0854, 0.0788, 0.0783]
    rmse = [0.1070, 0.0993, 0.0983]
    x = np.arange(len(models))
    width = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    b1 = ax.bar(
        x - width / 2,
        mae,
        width,
        label="MAE",
        color=GREEN,
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    b2 = ax.bar(
        x + width / 2,
        rmse,
        width,
        label="RMSE",
        color=BLUE,
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(models)
    ax.set_ylabel("Error on k-rate")
    ax.set_title("Chronological test error by model (248-feature screen)", pad=10)
    ax.set_ylim(0, 0.125)
    ax.grid(axis="y", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)

    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 0.0025,
                f"{h:.4f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#222222",
                zorder=4,
            )

    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        fontsize=9,
    )
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(OUT / "fig2_model_comparison.png")
    plt.close(fig)


def fig3_ablation() -> None:
    """Mean ΔMAE bars with whiskers spanning the two outer folds (H1-H2)."""
    # From artifacts/feature_research/leave_family_out/outer_results.csv
    rows = [
        ("Drop usage", 0.000531, -0.000022, -0.000453, -0.000623),
        ("Drop context", 0.000296, 0.000137, 0.000080, 0.000154),
        ("Drop park", 0.000147, 0.000383, 0.000177, 0.000188),
        ("Drop pitch physics", 0.000776, 0.000264, -0.005076, -0.000260),
        ("Drop rolling (keep STD/static)", 0.002982, -0.000482, -0.011709, -0.000252),
        ("Drop opponent lineup", 0.002380, 0.002702, 0.002120, 0.002504),
    ]
    labels = [r[0] for r in rows]
    lgbm_mean = [(a + b) / 2 for _, a, b, _, _ in rows]
    ridge_mean = [(a + b) / 2 for _, _, _, a, b in rows]
    lgbm_lo = [m - min(a, b) for m, (_, a, b, _, _) in zip(lgbm_mean, rows)]
    lgbm_hi = [max(a, b) - m for m, (_, a, b, _, _) in zip(lgbm_mean, rows)]
    ridge_lo = [m - min(a, b) for m, (_, _, _, a, b) in zip(ridge_mean, rows)]
    ridge_hi = [max(a, b) - m for m, (_, _, _, a, b) in zip(ridge_mean, rows)]

    y = np.arange(len(labels))
    height = 0.32
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.barh(
        y + height / 2,
        lgbm_mean,
        height,
        xerr=np.vstack([lgbm_lo, lgbm_hi]),
        label="LightGBM mean ΔMAE (whiskers = H1-H2)",
        color=GREEN,
        edgecolor="white",
        linewidth=0.4,
        capsize=2.5,
        error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
        zorder=3,
    )
    ax.barh(
        y - height / 2,
        ridge_mean,
        height,
        xerr=np.vstack([ridge_lo, ridge_hi]),
        label="Ridge mean ΔMAE (whiskers = H1-H2)",
        color=PURPLE,
        edgecolor="white",
        linewidth=0.4,
        capsize=2.5,
        error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
        zorder=3,
    )
    ax.axvline(0, color="#222", lw=1.1, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel(
        "Held-out ΔMAE vs full model  (positive = dropping the family hurt)"
    )
    ax.set_title(
        "Leave-family-out ablation (248-feature screen; two outer folds)", pad=10
    )
    ax.set_xlim(-0.0135, 0.0045)
    ax.grid(axis="x", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=1,
        fontsize=8.5,
    )
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.22, left=0.32)
    fig.savefig(OUT / "fig3_ablation.png")
    plt.close(fig)


def fig4_calibration() -> None:
    path = Path("artifacts/model_quality/phase11c_calibration/reliability_bins.csv")
    fig, ax = plt.subplots(figsize=(5.8, 5.6))
    ax.plot([0, 1], [0, 1], "--", color="#777777", lw=1.2, label="Perfect calibration", zorder=1)

    if path.exists():
        df = pl.read_csv(path)
        lines = df["line"].unique().to_list()
        prefer = 5.5 if 5.5 in lines else (lines[0] if lines else None)
        sub = df.filter(pl.col("line") == prefer).sort("bin") if prefer is not None else df
        if "n" in sub.columns:
            sub = sub.filter(pl.col("n") >= 20)
        x = sub["mean_prob"].to_numpy()
        y = sub["empirical"].to_numpy()
        n = sub["n"].to_numpy() if "n" in sub.columns else np.full(len(x), 40.0)
        sizes = np.clip(n / n.max() * 200, 35, 200)
        ax.scatter(
            x,
            y,
            s=sizes,
            color=BLUE,
            alpha=0.88,
            edgecolors="white",
            linewidths=0.7,
            label="Reliability bins (K ≥ 5.5)",
            zorder=3,
        )
        note = "Mean ECE ≈ 0.024 (no recalibration)"
    else:
        x = np.array([0.15, 0.30, 0.45, 0.60, 0.75, 0.88])
        y = x + np.array([0.02, -0.015, 0.01, -0.02, 0.015, -0.01])
        ax.scatter(x, y, s=70, color=BLUE, label="Reliability bins", zorder=3)
        note = "Mean ECE ≈ 0.024 (schematic)"

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Empirical frequency")
    ax.set_title("Count-layer reliability diagram", pad=10)
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.grid(True, linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    ax.set_aspect("equal", adjustable="box")

    ax.text(
        0.03,
        0.97,
        note,
        transform=ax.transAxes,
        fontsize=9,
        va="top",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#cccccc", linewidth=0.8),
        zorder=5,
    )
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=1,
        fontsize=9,
    )
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.16)
    fig.savefig(OUT / "fig4_calibration.png")
    plt.close(fig)


def main() -> None:
    fig1_pipeline()
    fig2_model_comparison()
    fig3_ablation()
    fig4_calibration()
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
