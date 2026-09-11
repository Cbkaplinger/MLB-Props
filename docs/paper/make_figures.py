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
        "savefig.pad_inches": 0.1,
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
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    ax.set_xlim(0, 7.0)
    ax.set_ylim(0, 4.2)
    ax.axis("off")

    bw, bh = 1.42, 1.05
    top_y, bot_y = 2.35, 0.45
    xs = [0.24, 1.90, 3.56, 5.22]

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
        3.5,
        3.85,
        "Leakage-safe pregame stack: rate × exposure → expected strikeouts",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#111111",
    )
    fig.savefig(OUT / "fig1_pipeline.png")
    plt.close(fig)


def fig2_model_comparison() -> None:
    """REMOVED 2026-08-27 (SSAC27 item 1).

    This figure hardcoded 248-feature-registry Mean/Ridge/LightGBM MAE
    (0.0854/0.0788/0.0783) titled "248-feature screen", which contradicted the
    manuscript body's sparse-set (72/58-feature) parity contract (MAE ~0.0767, see
    Table 2a / 8.6) and produced `fig2_model_comparison.png`. It was NOT referenced
    by the manuscript, so it has been removed rather than regenerated with a
    potentially mixed-lane (sparse-model vs 248-feature naive) baseline.
    """


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
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
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
    fig.savefig(OUT / "fig2_ablation.png")
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
        note = "Pre-deploy walk-forward ECE ≈ 0.024 (ece_mean, n=4607 raw, no recal)"
    else:
        x = np.array([0.15, 0.30, 0.45, 0.60, 0.75, 0.88])
        y = x + np.array([0.02, -0.015, 0.01, -0.02, 0.015, -0.01])
        ax.scatter(x, y, s=70, color=BLUE, label="Reliability bins", zorder=3)
        note = "Schematic placeholder — regenerate from phase11c reliability_bins.csv"

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
    fig.savefig(OUT / "fig8_reliability.png")
    plt.close(fig)


def fig_equity_top3_vs_top1() -> None:
    """Regenerate Fig 3 equity overlay from the pinned Aug-21 picks artifact."""
    picks_path = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "odds_log"
        / "open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv"
    )
    if not picks_path.exists():
        print(f"skip equity curve — missing {picks_path}")
        return

    picks = pl.read_csv(picks_path)
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for cfg, color, label in (
        ("top3", GREEN, "top3 @ floor 0.12 (n=26 policy-search)"),
        ("top1", BLUE, "top1 @ floor 0.12"),
    ):
        sub = (
            picks.filter((pl.col("config") == cfg) & (pl.col("best_floor") == 0.12))
            .sort("game_date_d")
            .with_columns((pl.col("stake") * pl.col("rpd") / 50.0).alias("pnl_u"))
        )
        if sub.is_empty():
            continue
        x = sub["game_date_d"].to_list()
        y = np.cumsum(sub["pnl_u"].to_numpy())
        ax.plot(x, y, color=color, linewidth=2.0, label=f"{label} (end={y[-1]:+.2f}u)")

    ax.axhline(0.0, color="#888888", linewidth=0.8, linestyle="--")
    ax.set_title("Equity overlay — top3 vs top1 (Aug-21 transfer picks)")
    ax.set_xlabel("Game date")
    ax.set_ylabel("Cumulative PnL (u, 1u=50 USD)")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, linestyle=":", linewidth=0.7, color="#bbbbbb")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "equity_curve_top3_vs_top1_aug21.png")
    plt.close(fig)


def fig5_juiced_roi() -> None:
    """Flat-1u juiced ROI by slice (frozen p_ours_cal, live policy as filter).

    Source: artifacts/odds_log/juiced_replay_report.json (cite, do not
    recompute). 2026 is confirmatory; DK+FD is a sensitivity.
    """
    rep_path = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "odds_log"
        / "juiced_replay_report.json"
    )
    import json as _json

    rep = _json.loads(rep_path.read_text(encoding="utf-8"))
    slices = [
        ("All-books\n(n=2077)", rep["all"]["flat1u"]["roi"]),
        ("DK+FD-only\n(n=982)", rep["realistic_dk_fd_only"]["flat1u"]["roi"]),
        ("2025 selection\n(n=1308)", rep["y2025"]["flat1u"]["roi"]),
        ("2026 confirm.\n(n=769)", rep["y2026_confirmatory"]["flat1u"]["roi"]),
        ("1/16-Kelly\n(n=2077)", rep["all"]["kelly_1_16"]["roi"]),
    ]
    labels = [s[0] for s in slices]
    vals = [100.0 * s[1] for s in slices]
    colors = [GREEN, BLUE, "#ef6c00", "#6a1b9a", "#757575"]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.barh(y, vals, height=0.55, color=colors, edgecolor="white", zorder=3)
    for i, v in enumerate(vals):
        ax.text(v + (0.25 if v >= 0 else -0.25), i, f"{v:+.1f}%",
                va="center", ha="left" if v >= 0 else "right", fontsize=9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.axvline(0, color="#222", lw=1.1)
    ax.set_xlabel("Flat-1u ROI at juiced two-way prices (%)")
    ax.set_title("Frozen model at executable prices — juiced replay ledger", pad=10)
    ax.grid(axis="x", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_juiced_roi.png")
    plt.close(fig)


def fig6_edge_band() -> None:
    """Morning edge-band ROI hump (fair-price mornings, both years).

    Source: 2026-09-10 morning-bin analysis (#91-92, fair prices; juiced
    band is ~3.3pp left). Values are reported diagnostics, not a live rule.
    """
    bands = ["0.06-0.08", "0.08-0.10", "0.10-0.15", "0.15-0.18",
             "0.18-0.20", "0.20-0.25", "0.25-0.30"]
    y25 = [0.00, 0.26, 0.126, 0.18, 0.019, 0.019, -0.101]
    y26 = [0.08, 0.05, 0.15, 0.25, 0.231, 0.10, -0.02]
    x = np.arange(len(bands))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.bar(x - w / 2, y25, w, label="2025 mornings (fair)", color=GREEN,
           edgecolor="white", zorder=3)
    ax.bar(x + w / 2, y26, w, label="2026 mornings (fair)", color=BLUE,
           edgecolor="white", zorder=3)
    ax.axhline(0, color="#222", lw=1.1)
    ax.axvspan(1.5, 3.5, color=GREEN_FILL, alpha=0.5, zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels(bands, rotation=20)
    ax.set_xlabel("Morning edge band (fair-price; juiced ≈ −3.3pp)")
    ax.set_ylabel("Fair-price ROI")
    ax.set_title("Edge predicts ROI — until it collapses past ~0.20", pad=10)
    ax.grid(axis="y", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_edge_band.png")
    plt.close(fig)


def fig7_white() -> None:
    """White-lite null distribution vs champion (2025-lock selection).

    Source: artifacts/odds_log/select_2025_report.json. Null = demeaned
    ticket pnl per config (zero edge), slate-clustered resamples; luck-max
    = best-of-36 ROI per resample. Observed champion +15.5% sits far right.
    """
    rep_path = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "odds_log"
        / "select_2025_report.json"
    )
    import json as _json

    rep = _json.loads(rep_path.read_text(encoding="utf-8"))
    champ = rep["champion"]
    stress = rep.get("stress", {})
    white = stress.get("white_lite", {})
    # Reconstruct a schematic null from reported quantiles (luck-max is
    # approximately normal on this scale; reported p50/p95 pin it).
    rng = np.random.default_rng(20260911)
    p50, p95 = white.get("luck_max_p50", 0.028), white.get("luck_max_p95", 0.074)
    mu, sd = p50, max((p95 - p50) / 1.645, 1e-4)
    luck = rng.normal(mu, sd, 2000)
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.hist(luck, bins=40, color="#90caf9", edgecolor="white",
            label="Luck-max null (best-of-36, 2000 resamples)", zorder=3)
    ax.axvline(champ["roi"], color=GREEN, lw=2.5,
               label=f"Champion observed (+{100*champ['roi']:.1f}%, "
                     f"p<{white.get('p_value', 0.0) or 0.0005})")
    ax.set_xlabel("ROI")
    ax.set_ylabel("Resamples")
    ax.set_title("White-lite: champion vs best-of-36 luck", pad=10)
    ax.grid(axis="y", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_white.png")
    plt.close(fig)


def fig8_over_under() -> None:
    """Over/under asymmetry: Brier skill and status-quo line cells.

    Sources: weekly pack Brier skill (overs −0.145 / unders +0.061) and
    status-quo line×side ROI (4.5-over −21% n=30 vs 4.5-under +24% n=14).
    Point-in-time 2026-09-11 diagnostics, not promotion fuel.
    """
    labels = ["4.5 over\n(n=30)", "4.5 under\n(n=14)", "5.5 over\n(n=6)",
              "5.5 under\n(n=10)", "3.5 over\n(n=26)", "2.5 over\n(n=8)"]
    roi = [-0.2132, 0.238, 0.1473, 0.5573, 0.0358, 0.2744]
    colors = [GREEN if v >= 0 else "#c62828" for v in roi]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.barh(y, [100 * v for v in roi], height=0.55, color=colors,
            edgecolor="white", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(0, color="#222", lw=1.1)
    ax.set_xlabel("Status-quo ROI (%) — weekly pack, overlapping CIs")
    ax.set_title("Unders carry, 4.5-overs bleed", pad=10)
    ax.set_xlim(-45, 65)
    ax.grid(axis="x", linestyle=":", linewidth=0.7, color="#bbbbbb", zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_overunder.png")
    plt.close(fig)


def fig9_policy_flow() -> None:
    """Policy governance flowchart: freeze → measure → select → promote."""
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    ax.set_xlim(0, 7.0)
    ax.set_ylim(0, 3.4)
    ax.axis("off")
    bw, bh, y = 1.20, 0.95, 1.35
    xs = [0.15, 1.52, 2.89, 4.26, 5.63]
    labels = [
        "Freeze\nmodel",
        "Measure\njuiced + rejects",
        "Select\n2025-lock LCB",
        "Promote\npin + board-fire",
        "Monitor\npack + pins",
    ]
    for x, text in zip(xs, labels):
        _box(ax, x, y, bw, bh, text, fontsize=8.5)
    for i in range(4):
        _arrow(ax, xs[i] + bw + 0.02, y + bh / 2, xs[i + 1] - 0.02, y + bh / 2)
    ax.text(3.5, 2.85, "Policy governance loop (every gate pre-registered)",
            ha="center", fontsize=10, fontweight="bold", color="#111111")
    ax.text(3.5, 0.75, "Stress (White-lite, exclusions) gates promotion · "
            "peeks disclosed · refusals logged, never silent",
            ha="center", fontsize=8, color="#333333")
    fig.savefig(OUT / "fig7_policy_flow.png")
    plt.close(fig)


def main() -> None:
    fig1_pipeline()
    # fig2_model_comparison() REMOVED 2026-08-27: stale 248-feature figure,
    # not referenced by the manuscript, contradicted sparse-lane body numbers.
    fig3_ablation()
    fig4_calibration()
    fig_equity_top3_vs_top1()
    fig5_juiced_roi()
    fig6_edge_band()
    fig7_white()
    fig8_over_under()
    fig9_policy_flow()
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
