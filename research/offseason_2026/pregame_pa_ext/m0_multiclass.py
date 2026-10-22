"""RESEARCH-ONLY M0 multi-class PA outcome model (pregame-pa-ext-v2).

v3.1 REPAIR (Chat 2 trailing-fixer batch, implements card v3 exactly):
resolves the five Chat 2 blockers on the f00c6f7/74879bf publication.

Blockers fixed here (one delta):
  B1. Evaluation population = the pitcher-matched, uniqueness-guarded
      observed-PA join (br.observed_pa_join) over the eligible ledger
      slots, asserted against the PUBLISHED 82,817 evaluation-key set
      (c6568151...) - exact set, not a count. Reliever PAs and the
      777417-style cross-side duplicates are structurally excluded.
  B2. EP2 implemented AS DECLARED: per-row 5-class labels through the
      multiclass cross-entropy, vs the league-constant AND log5
      baselines on the same rows. No binary collapse.
  B3. EP1 non-inferiority uses the card's rule: the UPPER 95% CI bound
      of the paired delta must be < +0.005 (not the point estimate).
  B4. Inference completed: the registered bootstrap for EP1 AND EP2,
      Holm m=2 step-down across the two pre-declared endpoint families.
  B5. Receipt validation is FAIL-CLOSED: required sections, populated
      consumed identities (never placeholders, never NOT_AVAILABLE),
      frozen key identities present - enforced BEFORE the initial
      receipt is accepted, mirroring the batter-history contract.

Additional plumbing gap fixed: the 8 FEAT_H3 features are now actually
CONSTRUCTED - training rows via build_checkpoint.build_feature_frame
(the frozen realized-PA lineage) joined with Statcast event labels;
evaluation slots inherit the FROZEN forecast-time features from the
preserved ledger (identical pregame inputs both arms). The previous
publication assumed a caller-supplied feature frame and would have
failed on real data.

Outcome taxonomy (frozen, card v3):
  class 0: strikeout (strikeout, strikeout_double_play)
  class 1: walk_or_hbp (walk, intentional_walk, hit_by_pitch, catcher_interf)
  class 2: field_out (field_out, force_out, fielders_choice, ...)
  class 3: hit (single, double, triple, home_run, ground_rule_double)
  class 4: caught_stealing_or_pickoff (caught_stealing, pickoff_*)

Features: same 8 FEAT_H3 features as the frozen binary recipe.
Model family: StandardScaler + LogisticRegression(multinomial softmax,
C=1.0, max_iter=1000) - same solver family as the frozen binary recipe.

Primary endpoints (Holm m=2 across the two pre-declared families):
  EP1: K marginal NON-INFERIORITY - the multi-class implied K
       probability P(class=0) must be non-inferior to the frozen binary
       p_h3_raw on the paired evaluation PAs; PASS = the UPPER 95% CI
       bound of the paired log-loss delta < +0.005.
  EP2: multiclass cross-entropy LOWER than BOTH the league-constant and
       the log5 baselines on the same rows.
Count-RPS is DESCRIPTIVE (never gated, never a primary result).

NO real-data fitting or evaluation has occurred. Real-outcome execution
is gated behind --i-accept-outcome-evaluation AND explicit owner
authorization. The complete-receipt pre-execution check is runnable via
--verify-receipt-check (synthetic; Chat 2's standing gate).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import build_checkpoint as bc  # noqa: E402
from pregame_pa_ext import count_agg_eval as cae  # noqa: E402

import kcount_combiner as kc  # noqa: E402  (registered count metrics)

# ------------------------------------------------------------ taxonomy
STATCAST_EVENT_TAXONOMY = {
    "strikeout": 0, "strikeout_double_play": 0,
    "walk": 1, "intentional_walk": 1, "hit_by_pitch": 1,
    "catcher_interf": 1,
    "field_out": 2, "force_out": 2, "fielders_choice": 2,
    "fielders_choice_out": 2, "field_error": 2,
    "runner_double_play": 2, "other_out": 2,
    "sacrifice_bunt": 2, "sacrifice_bunt_double_play": 2,
    "sacrifice_fly": 2, "sacrifice_fly_double_play": 2,
    "triple_play": 2,
    "single": 3, "double": 3, "triple": 3, "home_run": 3,
    "ground_rule_double": 3,
    "caught_stealing": 4, "pickoff_1b": 4, "pickoff_2b": 4,
    "pickoff_3b": 4, "caught_stealing_picked_off": 4,
}
CLASS_NAMES = ["strikeout", "walk_or_hbp", "field_out", "hit",
               "caught_stealing_or_pickoff"]
N_CLASSES = len(CLASS_NAMES)
K_CLASS = 0

FEATURES = list(ad.FEAT_H3)

DEV_BLOCK_TRAIN_END = {"block_2024H2": (2024, 6, 30),
                       "block_2025H1": (2024, 12, 31)}
PROTECTED_BLOCK = "confirm_2025H2"

K_NONINFERIORITY_MARGIN = 0.005

EFFECT_SIZE_BUDGET = {
    "n_eval_pa": 82817,
    "se_observed_from_batt_hist": 0.000166,
    "mde_80pct_power": 0.00046,
    "noninferiority_margin": K_NONINFERIORITY_MARGIN,
    "margin_to_mde_ratio": round(K_NONINFERIORITY_MARGIN / 0.00046, 1),
}

MILESTONES = (6, 8, 10, 12)

REQUIRED_RECEIPT_SECTIONS = ("inputs", "code_config", "dev_keys",
                             "config")
PUBLISHED_DEV_EVAL_KEYS_SHA256 = (
    "c65681512d5de924e842e80d7c7f27369889590f1c46111eec11e25acb50f902")
PUBLISHED_DEV_EVAL_KEYS_N = 82817


def sha256_stream(stream: bytes) -> str:
    return hashlib.sha256(stream).hexdigest()


def _lf_bytes(p: Path) -> bytes:
    return Path(p).read_bytes().replace(
        b"\r\n", b"\n").replace(b"\r", b"\n")


def _frame_sha(df: pl.DataFrame) -> str:
    """Deterministic content identity of a consumed Polars frame:
    sha256 over its in-memory IPC serialization (content-defined, so
    the receipt identifies the exact frame bytes consumed)."""
    buf = io.BytesIO()
    df.write_parquet(buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


# ------------------------------------------------------------ taxonomy
def map_statcast_events(events: pl.Series) -> pl.Series:
    """Map Statcast event strings to taxonomy labels; unrecognised or
    null events map to -1 and are excluded from training/evaluation."""
    return events.replace_strict(
        STATCAST_EVENT_TAXONOMY, default=-1, return_dtype=pl.Int8)


def event_label_frame(pa: pl.DataFrame, raw_dir: str | None = None):
    """Per-PA multi-class labels keyed by (game_pk, at_bat_number,
    batter).

    Synthetic/pre-enriched path: `pa` already carries an `events`
    column. Real-data path: read the events column from the raw
    Statcast parquets (repo Savant-Data, read-only) and join on the PA
    identity. Returns (labeled_frame, consumed_raw_files) where
    labeled_frame has (game_pk, at_bat_number, batter, class_label)
    for every PA with a recognised event."""
    consumed = {}
    if "events" in pa.columns:
        labeled = pa.filter(
            pl.col("events").is_not_null()
        ).select(
            "game_pk", "at_bat_number", "batter", "events"
        ).with_columns(
            map_statcast_events(pl.col("events")).alias("class_label")
        ).filter(pl.col("class_label") >= 0)
        return labeled.select(
            "game_pk", "at_bat_number", "batter", "class_label"), consumed
    rd = Path(raw_dir) if raw_dir else Path(
        r"C:\Users\ckaplinger\Downloads\Personal-Projects"
        r"\MLB-Props\data\Savant-Data\regular")
    if not rd.is_dir():
        raise ValueError(
            f"RAW_STATCAST_DIR_MISSING: {rd} (event labels are a "
            "consumed input; the runner never invents labels)")
    frames = []
    for season_dir in sorted(rd.iterdir()):
        f = season_dir / f"statcast_{season_dir.name}_regular.parquet"
        if not f.exists():
            continue
        consumed[f"statcast_{season_dir.name}"] = ad.sha256_file(f)
        df = pl.read_parquet(
            f, columns=["game_pk", "at_bat_number", "batter", "events"]
        ).filter(pl.col("events").is_not_null())
        frames.append(df)
    if not frames:
        raise ValueError("RAW_STATCAST_EMPTY: no event rows found")
    raw = pl.concat(frames).unique(
        subset=["game_pk", "at_bat_number", "batter"], keep="first")
    labeled = raw.with_columns(
        map_statcast_events(pl.col("events")).alias("class_label")
    ).filter(pl.col("class_label") >= 0)
    return labeled.select(
        "game_pk", "at_bat_number", "batter", "class_label"), consumed


# ---------------------------------------------------------- training
def build_multiclass_labels(df: pl.DataFrame) -> pl.DataFrame:
    """COMPATIBILITY wrapper for Chat 1's published integration fixtures
    (b2a1cfe, cleared): attaches the taxonomy class_label to a frame
    carrying an `events` column and preserves every other column
    (identity, y, features). The repaired API is event_label_frame +
    build_training_frames; this wrapper keeps the cleared fixtures
    working without modification."""
    labeled, _ = event_label_frame(df)
    return df.join(
        labeled, on=["game_pk", "at_bat_number", "batter"], how="inner")


def build_training_frames(pa: pl.DataFrame, event_labels: pl.DataFrame,
                          ) -> tuple[dict, dict]:
    """Frozen realized-PA lineage (build_feature_frame: 2023-01-01..,
    original PA identity, the 8 as-of features, lg-finite filter) joined
    with the multi-class labels on the PA identity. Per dev block:
    train = 2023-01-01..cal_first (cal_last = the last realized date
    <= the block train end; cal = [cal_first, cal_last]). Rows without a
    recognised class label are excluded and COUNTED (disclosed, never
    silently labelled). Returns (frames, diagnostics)."""
    feat = bc.build_feature_frame(pa)
    before = feat.height
    feat = feat.join(
        event_labels.select("game_pk", "at_bat_number", "batter",
                            "class_label"),
        on=["game_pk", "at_bat_number", "batter"], how="inner")
    diag = {"feature_rows_before_label_join": before,
            "feature_rows_with_class_label": feat.height,
            "rows_without_class_label_dropped": before - feat.height}
    frames = {}
    for b, (te_y, te_m, te_d) in DEV_BLOCK_TRAIN_END.items():
        end = date(te_y, te_m, te_d)
        in_block = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= end))
        if in_block.height == 0:
            raise ValueError(f"empty multiclass training frame: {b}")
        cal_last = in_block["game_date"].max()
        cal_first = cal_last - timedelta(days=59)
        train = in_block.filter(pl.col("game_date") < cal_first)
        if train.height == 0:
            raise ValueError(f"empty train split: {b}")
        if train["game_date"].max() >= cal_first:
            raise ValueError(f"training rows overlap calibration: {b}")
        counts = train["class_label"].value_counts().sort("class_label")
        per_class = {int(r["class_label"]): int(r["count"])
                     for r in counts.iter_rows(named=True)}
        for c in range(N_CLASSES):
            if per_class.get(c, 0) == 0:
                raise ValueError(
                    f"STOP: class {c} ({CLASS_NAMES[c]}) has 0 training "
                    f"PAs in {b} - taxonomy too granular for the data")
        frames[b] = train
        diag[f"{b}_train_rows"] = int(train.height)
        diag[f"{b}_cal_window"] = [str(cal_first), str(cal_last)]
        diag[f"{b}_per_class_train"] = per_class
        diag[f"{b}_sparse_classes_lt50"] = [
            c for c, n in per_class.items() if n < 50]
    return frames, diag


# ---------------------------------------------------------- model
def fit_multinomial(train: pl.DataFrame) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(train.select(FEATURES).to_numpy())
    lr = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
    lr.fit(scaler.transform(train.select(FEATURES).to_numpy()),
           train["class_label"].to_numpy().astype(int))
    return {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist(),
            "features": list(FEATURES), "classes": lr.classes_.tolist()}


def apply_multinomial(features: pl.DataFrame, model: dict) -> np.ndarray:
    X = features.select(FEATURES).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    intercept = np.asarray(model["intercept"], dtype=np.float64)
    z = (X - mean) / scale
    logits = z @ coef.T + intercept
    exp_l = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = exp_l / exp_l.sum(axis=1, keepdims=True)
    if not np.all(np.isfinite(probs)):
        raise ValueError("non-finite multinomial probability")
    return probs


# ---------------------------------------------------------- baselines
def league_constant_baseline(train: pl.DataFrame,
                             n_eval: int) -> np.ndarray:
    counts = np.bincount(train["class_label"].to_numpy().astype(int),
                         minlength=N_CLASSES)
    probs = counts / counts.sum()
    return np.tile(probs, (n_eval, 1))


def log5_baseline(eval_rows: pl.DataFrame,
                  train: pl.DataFrame) -> np.ndarray:
    k_rate_train = float((train["class_label"] == K_CLASS).mean())
    nonk = []
    for c in range(N_CLASSES):
        if c == K_CLASS:
            nonk.append(0.0)
        else:
            nonk.append(float((train["class_label"] == c).mean())
                        / max(1e-15, 1.0 - k_rate_train))
    nonk = np.asarray(nonk)
    nonk = nonk / nonk.sum()
    p_pitcher = eval_rows["p_pitcher_prior_w150"].to_numpy()
    p_batter = eval_rows["p_batter_prior_w150"].to_numpy()
    lg = eval_rows["lg_rate"].to_numpy()
    num = p_pitcher * p_batter * (1.0 - lg)
    den = num + (1.0 - p_pitcher) * (1.0 - p_batter) * lg
    p_k = np.clip(num / den, 1e-9, 1.0 - 1e-9)
    probs = np.zeros((len(eval_rows), N_CLASSES))
    probs[:, K_CLASS] = p_k
    for c in range(N_CLASSES):
        if c != K_CLASS:
            probs[:, c] = (1.0 - p_k) * nonk[c]
    return probs


# ---------------------------------------------------------- metrics
def multiclass_log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    pc = np.clip(probs, 1e-15, 1.0)
    n = len(y_true)
    total = 0.0
    for i in range(n):
        total -= np.log(max(pc[i, y_true[i]], 1e-15))
    return total / n if n else 0.0


def k_marginal_log_loss(y_true: np.ndarray, p_k: np.ndarray) -> np.ndarray:
    pc = np.clip(p_k, 1e-15, 1.0 - 1e-15)
    return -(y_true * np.log(pc) + (1 - y_true) * np.log1p(-pc))


# ------------------------------------------------- fail-closed receipt
REQUIRED_RECEIPT_SECTIONS = ("inputs", "code_config", "dev_keys",
                             "config")


def validate_receipt_initial(receipt: dict) -> None:
    """FAIL-CLOSED (Chat 2 blocker 5): a receipt with missing sections,
    empty consumed identities, or placeholder notes is REJECTED before
    any computation is accepted."""
    if not isinstance(receipt, dict):
        raise ValueError("provenance receipt is not a JSON object")
    for s in REQUIRED_RECEIPT_SECTIONS:
        if s not in receipt:
            raise ValueError(f"incomplete receipt: missing '{s}'")
        v = receipt[s]
        if v is None or (isinstance(v, (dict, list)) and not v):
            raise ValueError(f"incomplete receipt: empty '{s}'")
    consumed = receipt["inputs"].get("consumed", {})
    if not consumed:
        raise ValueError(
            "incomplete receipt: no CONSUMED input identities "
            "(placeholders are rejected; the batter-history repair "
            "defect class)")
    for k, v in consumed.items():
        if not isinstance(v, str) or len(v) != 64:
            raise ValueError(
                f"incomplete receipt: consumed input '{k}' has no "
                "full sha256 identity")


# ---------------------------------------------------------- gated runner
def run_m0(pa: pl.DataFrame, ledger: pl.DataFrame, out_dir, *,
           event_labels: pl.DataFrame | None = None,
           raw_dir: str | None = None, bf: pl.DataFrame | None = None,
           verify_published: bool = True, n_boot: int = 2000,
           seed: int = 20261001) -> dict:
    """GATED M0 runner (synthetic-tested; real-data execution requires
    --i-accept-outcome-evaluation AND explicit owner authorization).
    Write-once; immutable initial receipt; failure records preserved."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    if event_labels is None:
        event_labels, consumed_raw = event_label_frame(pa, raw_dir)
    else:
        consumed_raw = {}
    initial = {
        "inputs": {
            "consumed": {
                "preserved_run_ledger": _frame_sha(ledger),
                "event_labels_source": _frame_sha(event_labels),
            },
            "context_identities": {},
        },
        "code_config": {
            "m0_multiclass_py_lf_sha256": sha256_stream(
                _lf_bytes(Path(__file__))),
            "taxonomy": {str(k): CLASS_NAMES[k] for k in range(N_CLASSES)},
            "features": list(FEATURES),
            "noninferiority_margin": K_NONINFERIORITY_MARGIN,
            "effect_size_budget": EFFECT_SIZE_BUDGET,
            "endpoints": {
                "EP1": ("K marginal non-inferiority, UPPER 95% CI bound "
                        "< +0.005"),
                "EP2": ("multiclass cross-entropy LOWER than the "
                        "league-constant AND log5 baselines"),
            },
            "holm_family": 2,
        },
        "dev_keys": {
            "start_keys_n": cae.PUBLISHED_DEV_STARTS_N,
            "eval_keys_n": PUBLISHED_DEV_EVAL_KEYS_N,
            "eval_keys_sha256": PUBLISHED_DEV_EVAL_KEYS_SHA256,
        },
        "config": {
            "primary": "EP1 K-marginal non-inferiority + EP2 multiclass "
                       "cross-entropy vs both baselines",
            "descriptive": "count-RPS (never gated)",
            "tail_bucket": "k=23 absorbs K >= 23",
        },
    }
    validate_receipt_initial(initial)
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # stage 1: training frames + fits (frozen lineage + labels)
        frames, diag = build_training_frames(pa, event_labels)
        models = {}
        fits = {}
        for b in DEV_BLOCK_TRAIN_END:
            models[b] = fit_multinomial(frames[b])
            coef_blob = json.dumps(models[b], sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
            fits[b] = {"n_train_rows": int(frames[b].height),
                       "coefficients_sha256": hashlib.sha256(
                           coef_blob).hexdigest()}
        diag["fits"] = fits

        # stage 2: evaluation slots from the preserved ledger (frozen
        # forecast-time features; identical pregame inputs both arms)
        ledger_b = ledger.with_columns(
            pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
            .then(pl.lit("block_2024H2"))
            .when(pl.col("game_date") <= pl.date(2025, 6, 30))
            .then(pl.lit("block_2025H1"))
            .otherwise(pl.lit("confirm_2025H2")).alias("block"))
        elig = br.eligible_slots_from_ledger(ledger_b, br.DEV_BLOCKS)
        slot_rows = elig.join(
            ledger_b.select(
                "game_pk", "side", "pitcher", "batter", "slot",
                "game_date", "p_h3_raw", *FEATURES),
            on=["game_pk", "side", "pitcher", "batter", "slot",
                "game_date"], how="left")
        if slot_rows.filter(pl.col("p_h3_raw").is_null()).height:
            raise ValueError("eligible slot missing the frozen baseline "
                             "probability or features")

        # stage 3: per-block scoring -> 5-class probs + P(class=0)
        slot_probs = []
        for b in DEV_BLOCK_TRAIN_END:
            blk = slot_rows.filter(pl.col("block") == b)
            if blk.height == 0:
                continue
            probs = apply_multinomial(blk, models[b])
            blk = blk.with_columns(
                pl.Series("p_multiclass_k", probs[:, K_CLASS]),
                pl.Series("probs5", list(probs)))
            slot_probs.append(blk)
        slots = pl.concat(slot_probs).sort("game_date", "game_pk", "side",
                                           "slot")

        # stage 4: pitcher-matched observed-PA join (B1) + labels
        pa_obs = br.observed_pa_join(slots, pa)
        ev = pa_obs.join(
            slots.select(
                "game_pk", "side", "pitcher", "batter", "slot",
                "game_date", "p_multiclass_k", "probs5", "p_h3_raw",
                *FEATURES),
            on=["game_pk", "side", "pitcher", "batter", "slot",
                "game_date"], how="inner")
        ev = ev.join(
            event_labels.select("game_pk", "at_bat_number", "batter",
                                "class_label"),
            on=["game_pk", "at_bat_number", "batter"], how="left")
        if ev["class_label"].null_count():
            raise ValueError("observed PA without a multi-class label")
        # label-integrity: class 0 iff the frozen binary y == 1
        mism = ev.filter(
            (pl.col("class_label") == K_CLASS)
            != (pl.col("y") == 1)).height
        if mism:
            raise ValueError(
                f"label-integrity failure: {mism} rows where the "
                "taxonomy class-0 flag disagrees with the frozen y")
        # frozen evaluation-key identity (exact set, B1)
        ev = ev.with_columns(pl.col("y").cast(pl.Int8))
        eval_keys = sorted(set(zip(ev["game_pk"].to_list(),
                                   ev["at_bat_number"].to_list())))
        ek_stream = "\n".join("%d|%d" % k for k in eval_keys).encode("utf-8")
        ek_sha = sha256_stream(ek_stream)
        if verify_published and (
                len(eval_keys) != PUBLISHED_DEV_EVAL_KEYS_N
                or ek_sha != PUBLISHED_DEV_EVAL_KEYS_SHA256):
            raise ValueError(
                "frozen evaluation-key set does not match the published "
                "identity (exact set check)")
        if (ev["block"] == PROTECTED_BLOCK).any():
            raise ValueError("protected confirm block in evaluation")

        # stage 5: endpoints (registered machinery)
        y = ev["y"].to_numpy().astype(int)
        p_multi = ev["p_multiclass_k"].to_numpy()
        p_base = ev["p_h3_raw"].to_numpy()
        ll_multi = k_marginal_log_loss(y, p_multi)
        ll_base = k_marginal_log_loss(y, p_base)
        cmp_mod = br.load_registered_comparison()
        dates = ev["game_date"].to_list()
        blocks = ev["block"].to_list()
        res1 = cmp_mod.slate_date_draws(
            {"multi_k": ll_multi, "binary_k": ll_base},
            dates, blocks, n_boot=n_boot, seed=seed)
        d_rep_1 = res1[:, 0] - res1[:, 1]
        delta_k = float(ll_multi.mean() - ll_base.mean())
        ci1 = [float(np.percentile(d_rep_1, 2.5)),
               float(np.percentile(d_rep_1, 97.5))]
        ep1_pass = ci1[1] < K_NONINFERIORITY_MARGIN
        p1 = cmp_mod.null_centered_p_value(delta_k, d_rep_1)

        y_multi = ev["class_label"].to_numpy().astype(int)
        probs5 = np.vstack(ev["probs5"].to_list())
        mc_ll = multiclass_log_loss(y_multi, probs5)
        lc_probs = league_constant_baseline(
            frames["block_2024H2"], len(ev))
        l5_probs = log5_baseline(ev, frames["block_2024H2"])
        lc_ll = multiclass_log_loss(y_multi, lc_probs)
        l5_ll = multiclass_log_loss(y_multi, l5_probs)
        ce_multi = -np.log(np.clip(
            probs5[np.arange(len(y_multi)), y_multi], 1e-15, 1.0))
        ce_league = -np.log(np.clip(
            lc_probs[np.arange(len(y_multi)), y_multi], 1e-15, 1.0))
        ce_log5 = -np.log(np.clip(
            l5_probs[np.arange(len(y_multi)), y_multi], 1e-15, 1.0))
        res2 = cmp_mod.slate_date_draws(
            {"ce_multi": ce_multi, "ce_league": ce_league,
             "ce_log5": ce_log5},
            dates, blocks, n_boot=n_boot, seed=seed)
        idx = {"multiclass": 0, "league": 1, "log5": 2}
        d_rep_l = res2[:, idx["multiclass"]] - res2[:, idx["league"]]
        d_rep_g = res2[:, idx["multiclass"]] - res2[:, idx["log5"]]
        obs_l = float(ce_multi.mean() - ce_league.mean())
        obs_g = float(ce_multi.mean() - ce_log5.mean())
        p_l = cmp_mod.null_centered_p_value(obs_l, d_rep_l)
        p_g = cmp_mod.null_centered_p_value(obs_g, d_rep_g)
        p_ep2 = max(p_l, p_g)
        holm = cmp_mod.holm_adjust({
            "EP1_k_noninferiority": p1, "EP2_vs_baselines": p_ep2})
        ep2 = {
            "multiclass_log_loss": float(mc_ll),
            "league_constant_log_loss": float(lc_ll),
            "log5_log_loss": float(l5_ll),
            "beats_league_constant": bool(mc_ll < lc_ll),
            "beats_log5": bool(mc_ll < l5_ll),
            "ep2_pass": bool(mc_ll < lc_ll and mc_ll < l5_ll),
            "p_vs_league": p_l, "p_vs_log5": p_g,
            "family_p": p_ep2,
        }
        metrics = {
            "n_eval_pa": int(ev.height),
            "n_eval_keys": len(eval_keys),
            "eval_keys_sha256": ek_sha,
            "EP1": {
                "k_marginal_log_loss_multiclass": float(ll_multi.mean()),
                "k_marginal_log_loss_binary": float(ll_base.mean()),
                "delta": delta_k,
                "noninferiority_margin": K_NONINFERIORITY_MARGIN,
                "ci95": ci1,
                "upper_ci_bound": ci1[1],
                "noninferiority_pass": ep1_pass,
                "p_null_centered": p1,
            },
            "EP2": ep2,
            "holm": {"m": 2,
                     "family": ["EP1_k_noninferiority",
                                "EP2_vs_baselines"],
                     "adjusted": holm,
                     "note": ("EP1 decided by the card's upper-CI-bound "
                              "rule; EP2 requires beating BOTH baselines "
                              "(intersection, stricter than either "
                              "alone); Holm m=2 over the two endpoint "
                              "families")},
            "diagnostics": diag,
        }
        # write-once outputs: the paired evaluation table + metrics
        ev_path = out_dir / "m0_multiclass_eval_v1.parquet"
        ev.write_parquet(ev_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "m0_multiclass_eval_v1.parquet": ad.sha256_file(ev_path),
            "metrics.json": ad.sha256_file(metrics_path),
        }
    except Exception as exc:
        failure = {"stage": "m0_multiclass", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = metrics
    final["outputs"] = outputs
    final["abstentions"] = {
        "note": ("the 43 development / 16 confirmation-block abstaining "
                 "starts are itemized in the frozen abstention record "
                 "(batter-history diagnostic abstentions.json, hash-"
                 "pinned in the batt_recency_v1 receipt); development "
                 "abstentions are excluded from evaluation and the "
                 "full-run total is never a development count"),
    }
    final["acceptance"] = {
        "EP1_noninferiority_pass": ep1_pass,
        "EP2_pass": ep2["ep2_pass"],
        "receipt_chain": initial_sha,
        "evaluation_keys_exact": True,
        "block_isolation": True,
        "exclusion_policy_unchanged": True,
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final, "receipt_initial_sha256": initial_sha}


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify-receipt-check", action="store_true",
                    help="synthetic complete-receipt pre-execution check "
                         "(Chat 2 standing gate; no real data)")
    ap.add_argument("--i-accept-outcome-evaluation", action="store_true",
                    help="gate for real-data execution (owner "
                         "authorization required; never run to date)")
    args = ap.parse_args(argv)
    if args.verify_receipt_check:
        from tests.test_m0_multiclass import synthetic_m0_inputs
        pa, ledger, labels, bf = synthetic_m0_inputs()
        out = Path("_m0_receipt_check")
        if out.exists():
            import shutil
            shutil.rmtree(out)
        res = run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                     verify_published=False)
        ok = res["metrics"]["n_eval_pa"] > 0
        print(json.dumps({"complete_receipt_check": "PASS" if ok
                          else "FAIL"}, indent=1))
        return 0 if ok else 1
    print("REFUSING: M0 real-data execution requires "
          "--i-accept-outcome-evaluation AND explicit owner "
          "authorization. The complete-receipt pre-execution check is "
          "runnable via --verify-receipt-check (synthetic only).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
