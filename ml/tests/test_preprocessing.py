"""Tests for ml/src/preprocessing.py — the leakage-safe Phase 1 feature pipeline."""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ml" / "src"))

from preprocessing import LEAKAGE_COLUMNS, TRANSACTION_TYPES, build_features  # noqa: E402


def make_raw_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
            # nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud
            [1, "CASH_IN", 1000.0, "C1", 5000.0, 6000.0, "M1", 0.0, 0.0, 0, 0],
            [25, "TRANSFER", 5000.0, "C2", 5000.0, 0.0, "C3", 1000.0, 6000.0, 1, 0],
            [48, "CASH_OUT", 200.0, "C4", 0.0, 0.0, "C5", 500.0, 700.0, 0, 0],
            [70, "DEBIT", 50.0, "C6", 300.0, 250.0, "M2", 0.0, 0.0, 0, 0],
            [90, "PAYMENT", 75.0, "C7", 400.0, 325.0, "M3", 0.0, 0.0, 0, 0],
        ],
        columns=[
            "step",
            "type",
            "amount",
            "nameOrig",
            "oldbalanceOrg",
            "newbalanceOrig",
            "nameDest",
            "oldbalanceDest",
            "newbalanceDest",
            "isFraud",
            "isFlaggedFraud",
        ],
    )


def test_no_leakage_columns_in_output():
    X, y, feature_columns = build_features(make_raw_df())
    for col in LEAKAGE_COLUMNS + ["type", "isFraud"]:
        assert col not in X.columns
        assert col not in feature_columns


def test_no_nans_introduced_including_zero_balance_rows():
    X, _, _ = build_features(make_raw_df())
    assert not X.isna().any().any()


def test_one_hot_type_columns_sum_to_one_per_row():
    X, _, _ = build_features(make_raw_df())
    type_cols = [f"type_{t}" for t in TRANSACTION_TYPES]
    assert (X[type_cols].sum(axis=1) == 1).all()


def test_is_merchant_dest_is_boolean():
    X, _, _ = build_features(make_raw_df())
    assert X["is_merchant_dest"].dtype == bool
    # nameDest starting with "M" (rows 0, 3, 4) should be True
    assert X["is_merchant_dest"].tolist() == [True, False, False, True, True]


def test_target_extracted_when_present_and_none_when_absent():
    raw = make_raw_df()
    _, y, _ = build_features(raw)
    assert y.tolist() == raw["isFraud"].tolist()

    _, y_missing, _ = build_features(raw.drop(columns=["isFraud"]))
    assert y_missing is None
