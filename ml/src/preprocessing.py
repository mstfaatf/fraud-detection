"""Leakage-safe preprocessing pipeline for the PaySim fraud dataset.

Turns a raw PaySim dataframe into the finalized Phase 1 feature set (see
CLAUDE.md, "Feature Schema" section, for the rationale behind every
inclusion/exclusion here). This module is imported both at training time
(ml/) and, later, at inference time (backend/) — keep it dependency-light
and free of notebook-only code.
"""

from __future__ import annotations

import pandas as pd

TRANSACTION_TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]

TARGET_COLUMN = "isFraud"

# amount / (oldbalanceOrg + BALANCE_EPSILON). oldbalanceOrg is exactly 0 for
# a meaningful share of PaySim rows (e.g. merchant-originated transactions),
# so a bare division would produce inf. 1.0 is used rather than a
# vanishingly small epsilon (e.g. 1e-6): amounts are raw currency units
# (tens to millions), so a tiny epsilon would blow the ratio up to an
# arbitrarily huge, uninformative number for zero-balance rows, whereas +1
# simply caps the ratio at ~`amount` itself for those rows — bounded and
# still meaningful as "this account had nothing to draw from".
BALANCE_EPSILON = 1.0

# Columns intentionally excluded from the trained model's feature set.
# Kept here (rather than just omitted) so the reason is explicit and can't
# silently regress if someone adds a column back without reading CLAUDE.md.
LEAKAGE_COLUMNS = [
    # Post-transaction state — not known at real-time scoring time, when a
    # payment must be scored *before* it executes. Excluded regardless of
    # predictive power (see CLAUDE.md: "Excluded — leakage").
    "newbalanceOrig",
    "newbalanceDest",
    # Row identifiers, not predictive features.
    "nameOrig",
    "nameDest",
    # Empirically unreliable per Phase 1 EDA (16/6.36M rows flagged, and the
    # documented ">200,000 transfer" rule doesn't hold in the data).
    "isFlaggedFraud",
]


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive hour_of_day and day_of_week from `step`.

    `step` is hours since simulation start; step 0 = hour 0 of day 0.
    """
    df = df.copy()
    df["hour_of_day"] = df["step"] % 24
    df["day_of_week"] = (df["step"] // 24) % 7
    return df


def add_amount_to_balance_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """amount / (oldbalanceOrg + epsilon) — pre-transaction balance only."""
    df = df.copy()
    df["amount_to_balance_ratio"] = df["amount"] / (df["oldbalanceOrg"] + BALANCE_EPSILON)
    return df


def add_is_merchant_dest(df: pd.DataFrame) -> pd.DataFrame:
    """PaySim merchant accounts are identifiable by nameDest starting with "M"."""
    df = df.copy()
    df["is_merchant_dest"] = df["nameDest"].str.startswith("M")
    return df


def encode_transaction_type(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode `type` over the fixed 5-category PaySim vocabulary.

    Categories are hard-coded (not inferred from the data) so that a single
    transaction scored at inference time still produces all 5 columns.
    """
    df = df.copy()
    for t in TRANSACTION_TYPES:
        df[f"type_{t}"] = df["type"] == t
    return df


FEATURE_COLUMNS = [
    "oldbalanceOrg",
    "oldbalanceDest",
    "amount",
    "hour_of_day",
    "day_of_week",
    "amount_to_balance_ratio",
    "is_merchant_dest",
] + [f"type_{t}" for t in TRANSACTION_TYPES]


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, "pd.Series | None", list[str]]:
    """Build the Phase 1 feature matrix from a raw PaySim dataframe.

    Parameters
    ----------
    df : raw PaySim rows (must contain step, type, amount, oldbalanceOrg,
        oldbalanceDest, nameDest; isFraud is optional — absent at
        real-time inference time, when a single transaction is scored
        before its label exists).

    Returns
    -------
    (X, y, feature_columns): X is the model-ready feature matrix (only
    FEATURE_COLUMNS, never the leakage columns in LEAKAGE_COLUMNS or raw
    nameOrig/nameDest/type), y is the isFraud series or None if not
    present in the input, and feature_columns is the ordered list of
    X's column names.
    """
    df = add_time_features(df)
    df = add_amount_to_balance_ratio(df)
    df = add_is_merchant_dest(df)
    df = encode_transaction_type(df)

    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].copy() if TARGET_COLUMN in df.columns else None

    return X, y, FEATURE_COLUMNS
