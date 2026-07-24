# Superseded pre-pipeline v6 output

`shap_table_v6_lgb.csv` and `test_predictions_v6_lgb.csv` are historical
exports from the pre-pipeline v6 workflow. The SHAP table contains fields that
are forbidden by the current pregame feature policy, including same-game
outcomes and unlagged measurements. The prediction file begins on the invalid
shared July 6 split boundary. Neither file may be used as current model evidence
or as a feature registry.

They are retained only for research provenance. The replacement feature policy
is implemented by `src/Python/features.py`, and the corrected frozen model
metadata is stored at
`artifacts/models/lightgbm_krate_20260723_202255.*`.
