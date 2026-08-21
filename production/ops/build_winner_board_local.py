from __future__ import annotations

from pathlib import Path
import pandas as pd


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ab = pd.read_csv(root / "artifacts" / "model_quality" / "sparse72_model_family_ablation" / "xgb_full_aug21" / "ablation_summary_ranked.csv")
    hold = pd.read_csv(root / "artifacts" / "odds_log" / "feature_set_market_skill_compare_local_holdout2025_aug21.csv")
    ens = pd.read_csv(root / "artifacts" / "odds_log" / "ensemble_sweep_tuned_lgbm_local20_aug21_ranked.csv")

    mae = ab.iloc[0]
    hs = hold.sort_values(["brier_skill_vs_market", "logloss_skill_vs_market"], ascending=[False, False]).iloc[0]
    ew = ens.iloc[0]

    rows = [
        {
            "lane": "MAE Single",
            "candidate": f"{mae['model_family']} @ {mae['feature_set']}",
            "primary_metric": "mean_expected_k_mae",
            "value": float(mae["mean_expected_k_mae"]),
            "brier_skill": None,
            "logloss_skill": None,
            "roi": None,
            "sortino": None,
            "n_bets": None,
            "decision": "HOLD",
        },
        {
            "lane": "Holdout Skill",
            "candidate": f"{hs['feature_set']} ({hs['calibration_mode']})",
            "primary_metric": "brier/logloss skill",
            "value": float(hs["brier_skill_vs_market"]),
            "brier_skill": float(hs["brier_skill_vs_market"]),
            "logloss_skill": float(hs["logloss_skill_vs_market"]),
            "roi": None,
            "sortino": None,
            "n_bets": int(hs["n_eval_rows"]),
            "decision": "PROMOTE" if hs["brier_skill_vs_market"] > 0 and hs["logloss_skill_vs_market"] > 0 else "HOLD",
        },
        {
            "lane": "Profit Ensemble (tuned-local)",
            "candidate": ew["weights_json"],
            "primary_metric": "profit_score",
            "value": float(ew["profit_score"]),
            "brier_skill": float(ew["brier_skill_vs_market"]),
            "logloss_skill": float(ew["logloss_skill_vs_market"]),
            "roi": float(ew["roi"]),
            "sortino": float(ew["sortino"]),
            "n_bets": int(ew["n_bets"]),
            "decision": (
                "LOCK"
                if (
                    ew["brier_skill_vs_market"] > 0
                    and ew["logloss_skill_vs_market"] > 0
                    and ew["n_bets"] >= 100
                    and ew["sortino"] >= 0.8
                    and ew["max_drawdown_pct"] <= 0.6
                )
                else "HOLD"
            ),
        },
    ]
    out = pd.DataFrame(rows)
    out_path = root / "artifacts" / "odds_log" / "winner_board_local_aug21.csv"
    out.to_csv(out_path, index=False)
    print(out.to_string(index=False))
    print(f"Wrote {out_path}")
    print(f"Ensemble edge floor: {ew['edge_floor']}")


if __name__ == "__main__":
    main()

