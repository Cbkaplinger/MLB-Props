"""Run denominator-aware stabilization studies on the locked dev seasons.

The main curves call ``Python.reliability.stabilization_by_denominator``.
Bootstrap intervals resample complete player histories, preserving the
within-player chronological dependence while retaining duplicate selections.
Outputs are local research artifacts under ``artifacts/stabilization``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl

from Python import config, reliability

matplotlib.use("Agg")


@dataclass(frozen=True)
class StatSpec:
    population: str
    name: str
    numerator: str
    denominator: str
    targets: tuple[int, ...]


PITCHER_SPECS = (
    StatSpec("pitcher", "k_rate", "K", "PA", tuple(range(25, 1001, 25))),
    StatSpec(
        "pitcher", "whiff_rate", "Whiffs", "Swings", tuple(range(50, 2501, 50))
    ),
    StatSpec(
        "pitcher", "swstr_rate", "Whiffs", "Pitches", tuple(range(100, 5001, 100))
    ),
    StatSpec(
        "pitcher", "ball_rate", "Balls", "Pitches", tuple(range(100, 5001, 100))
    ),
    StatSpec(
        "pitcher", "chase_rate", "Chases", "OutZone", tuple(range(50, 2501, 50))
    ),
    StatSpec(
        "pitcher", "csw_rate", "CSW", "Pitches", tuple(range(100, 5001, 100))
    ),
    StatSpec("pitcher", "bb_rate", "BB", "PA", tuple(range(25, 1001, 25))),
    StatSpec("pitcher", "gb_rate", "GB", "BIP", tuple(range(25, 1001, 25))),
    StatSpec("pitcher", "hr_fb", "HR", "FB", tuple(range(10, 401, 10))),
)
BatterSpec = StatSpec
BATTER_SPECS = (
    BatterSpec("batter", "k_rate", "K", "PA", tuple(range(25, 1001, 25))),
    BatterSpec(
        "batter", "whiff_rate", "Whiffs", "Swings", tuple(range(50, 2001, 50))
    ),
    BatterSpec(
        "batter", "swstr_rate", "Whiffs", "Pitches", tuple(range(100, 4001, 100))
    ),
    BatterSpec(
        "batter", "chase_rate", "Chases", "OutZone", tuple(range(50, 2001, 50))
    ),
)


def _dev_frame(path: Path, id_col: str) -> pd.DataFrame:
    frame = (
        pl.read_parquet(path)
        .with_columns(pl.col("game_date").dt.year().alias("season"))
        .filter(pl.col("season").is_in(config.FEATURE_RESEARCH_SEASONS))
        .sort([id_col, "game_date"])
        .to_pandas()
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected dev seasons {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )
    return frame


def _player_pairs(
    frame: pd.DataFrame,
    spec: StatSpec,
    id_col: str,
) -> dict[int, dict[int, tuple[float, float]]]:
    """Return target -> player -> consecutive denominator-bucket values."""
    pairs = {target: {} for target in spec.targets}
    for player, group in frame.groupby(id_col, sort=False):
        ordered = group.sort_values("game_date")
        num = ordered[spec.numerator].to_numpy(dtype=float)
        den = ordered[spec.denominator].to_numpy(dtype=float)
        mask = np.isfinite(num) & np.isfinite(den)
        num, den = num[mask], den[mask]
        cumulative_den = np.cumsum(den)
        for target in spec.targets:
            if cumulative_den.size == 0 or cumulative_den[-1] < 2 * target:
                continue
            first_end = int(np.searchsorted(cumulative_den, target))
            remainder = cumulative_den[first_end + 1 :] - cumulative_den[first_end]
            second_offset = int(np.searchsorted(remainder, target))
            if second_offset >= remainder.size:
                continue
            second_end = first_end + 1 + second_offset
            first_den = den[: first_end + 1].sum()
            second_den = den[first_end + 1 : second_end + 1].sum()
            if first_den <= 0 or second_den <= 0:
                continue
            pairs[target][int(player)] = (
                float(num[: first_end + 1].sum() / first_den),
                float(num[first_end + 1 : second_end + 1].sum() / second_den),
            )
    return pairs


def _bootstrap_ci(
    pairs: dict[int, dict[int, tuple[float, float]]],
    players: np.ndarray,
    *,
    n_boot: int,
    min_players: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    targets = tuple(pairs)
    values = np.full((n_boot, len(targets)), np.nan)
    for bootstrap in range(n_boot):
        sampled = rng.choice(players, size=len(players), replace=True)
        for column, target in enumerate(targets):
            selected = [pairs[target][int(player)] for player in sampled if int(player) in pairs[target]]
            if len(selected) < min_players:
                continue
            first, second = np.asarray(selected, dtype=float).T
            if first.std() < 1e-9 or second.std() < 1e-9:
                continue
            values[bootstrap, column] = np.corrcoef(first, second)[0, 1]
    bootstrap_frame = pd.DataFrame(values, columns=targets)
    return pd.DataFrame(
        {
            "target": targets,
            "median_r": bootstrap_frame.median().to_numpy(),
            "ci_low": bootstrap_frame.quantile(0.025).to_numpy(),
            "ci_high": bootstrap_frame.quantile(0.975).to_numpy(),
            "n_valid_boots": bootstrap_frame.notna().sum().to_numpy(),
        }
    )


def _first_crossing(frame: pd.DataFrame, column: str, threshold: float) -> float:
    reached = frame.loc[frame[column] >= threshold, "target"]
    return float(reached.iloc[0]) if not reached.empty else np.nan


def analyze(
    frame: pd.DataFrame,
    spec: StatSpec,
    *,
    id_col: str,
    output_dir: Path,
    n_boot: int = 300,
) -> list[dict[str, object]]:
    main = reliability.stabilization_by_denominator(
        frame,
        [(spec.numerator, spec.denominator, True)],
        targets=spec.targets,
        id_col=id_col,
        min_players=50,
    )
    pairs = _player_pairs(frame, spec, id_col)
    players = frame[id_col].dropna().astype(int).unique()
    ci = _bootstrap_ci(
        pairs,
        players,
        n_boot=n_boot,
        min_players=20,
        seed=42,
    )
    ci["observed_r"] = main[spec.numerator].reindex(ci["target"]).to_numpy()
    ci["n_qualified_players"] = ci["target"].map(
        lambda target: len(pairs[int(target)])
    )
    median_per_start = float(frame[spec.denominator].median())
    ci["median_denominator_per_start"] = median_per_start
    ci["typical_starts"] = ci["target"] / median_per_start

    stem = f"{spec.population}_{spec.name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    ci.to_csv(output_dir / f"{stem}_curve.csv", index=False)
    ci[
        [
            "target",
            "median_r",
            "ci_low",
            "ci_high",
            "n_valid_boots",
        ]
    ].to_csv(output_dir / f"{stem}_bootstrap_ci.csv", index=False)

    figure, left = plt.subplots(figsize=(9, 5))
    left.plot(ci["target"], ci["observed_r"], label="observed r", color="tab:blue")
    left.fill_between(
        ci["target"],
        ci["ci_low"],
        ci["ci_high"],
        alpha=0.2,
        color="tab:blue",
        label="95% player-bootstrap CI",
    )
    left.axhline(0.50, color="gray", linestyle="--", linewidth=0.8)
    left.axhline(0.70, color="gray", linestyle=":", linewidth=0.8)
    left.set_xlabel(spec.denominator)
    left.set_ylabel("split-half Pearson r")
    right = left.twinx()
    right.plot(
        ci["target"],
        ci["n_qualified_players"],
        color="tab:orange",
        alpha=0.65,
        label="qualified players",
    )
    right.set_ylabel("qualified players")
    left.set_title(f"{spec.population} {spec.name}: {spec.numerator}/{spec.denominator}")
    figure.tight_layout()
    figure.savefig(output_dir / f"{stem}_curve.png", dpi=140)
    plt.close(figure)

    summaries = []
    for threshold in (0.50, 0.70):
        median_cross = _first_crossing(ci, "median_r", threshold)
        low_cross = _first_crossing(ci, "ci_low", threshold)
        high_cross = _first_crossing(ci, "ci_high", threshold)
        qualified = (
            int(ci.loc[ci["target"] == median_cross, "n_qualified_players"].iloc[0])
            if np.isfinite(median_cross)
            else None
        )
        qualified_low = (
            int(ci.loc[ci["target"] == low_cross, "n_qualified_players"].iloc[0])
            if np.isfinite(low_cross)
            else None
        )
        qualified_high = (
            int(ci.loc[ci["target"] == high_cross, "n_qualified_players"].iloc[0])
            if np.isfinite(high_cross)
            else None
        )
        summaries.append(
            {
                "population": spec.population,
                "stat": spec.name,
                "numerator": spec.numerator,
                "denominator": spec.denominator,
                "threshold": threshold,
                "median_crossing": median_cross,
                "ci_low_crossing": low_cross,
                "ci_high_crossing": high_cross,
                "qualified_at_median_crossing": qualified,
                "qualified_at_ci_low_crossing": qualified_low,
                "qualified_at_ci_high_crossing": qualified_high,
                "reliably_estimable": bool(
                    np.isfinite(low_cross)
                    and qualified_low is not None
                    and qualified_low >= 50
                ),
                "median_denominator_per_start": median_per_start,
                "typical_starts_at_median_crossing": (
                    median_cross / median_per_start
                    if np.isfinite(median_cross)
                    else np.nan
                ),
            }
        )
    return summaries


def main() -> None:
    output_dir = config.OUTPUT_DIR / "stabilization"
    pitcher = _dev_frame(config.PITCHER_GAMES_PATH, "pitcher")
    batter = _dev_frame(config.BATTER_GAMES_PATH, "batter")
    if pitcher["PA"].min() < config.MIN_STARTER_BATTERS_FACED:
        raise ValueError("pitcher dev frame violates the locked starter population")

    summaries: list[dict[str, object]] = []
    for spec in PITCHER_SPECS:
        print(f"Analyzing {spec.population} {spec.name}...")
        summaries.extend(
            analyze(pitcher, spec, id_col="pitcher", output_dir=output_dir)
        )
    for spec in BATTER_SPECS:
        print(f"Analyzing {spec.population} {spec.name}...")
        summaries.extend(
            analyze(batter, spec, id_col="batter", output_dir=output_dir)
        )

    summary = pd.DataFrame(summaries)
    summary.to_csv(output_dir / "crossings_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"Wrote stabilization outputs to {output_dir}")


if __name__ == "__main__":
    main()
