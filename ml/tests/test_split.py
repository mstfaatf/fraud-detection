"""Tests for ml/src/split.py — the chronological train/test split."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ml" / "src"))

from split import (  # noqa: E402
    check_split_skew,
    compute_cutoff_step,
    find_degenerate_days,
    propose_adjusted_cutoff,
    time_based_split,
    time_based_split_adjusted,
    time_based_train_test_split,
)


def make_raw_df(n_days: int = 10, rows_per_day: int = 20, fraud_every: int = 7) -> pd.DataFrame:
    """A synthetic-but-schema-correct PaySim-shaped dataframe spanning
    `n_days` simulated days with a roughly steady fraud rate -- i.e. a
    "well-behaved" input with none of the real dataset's tail collapse, so
    these tests isolate the split mechanics from PaySim's specific artifact.
    """
    n = n_days * rows_per_day
    rng = np.random.default_rng(0)

    # `rows_per_day` rows per day, step = day*24 + (row index mod 24)
    steps = []
    for day in range(n_days):
        for i in range(rows_per_day):
            steps.append(day * 24 + (i % 24))
    steps = np.array(steps)

    is_fraud = (np.arange(n) % fraud_every == 0).astype(int)
    amount = rng.uniform(10, 1000, size=n)
    old_balance_org = rng.uniform(0, 5000, size=n)

    return pd.DataFrame(
        {
            "step": steps,
            "type": np.random.choice(["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"], size=n),
            "amount": amount,
            "nameOrig": [f"C{i}" for i in range(n)],
            "oldbalanceOrg": old_balance_org,
            "newbalanceOrig": np.maximum(old_balance_org - amount, 0),
            "nameDest": [f"C{i + 1000}" for i in range(n)],
            "oldbalanceDest": rng.uniform(0, 5000, size=n),
            "newbalanceDest": rng.uniform(0, 5000, size=n),
            "isFraud": is_fraud,
            "isFlaggedFraud": np.zeros(n, dtype=int),
        }
    )


def test_split_is_chronological_not_shuffled():
    df = make_raw_df()
    cutoff = compute_cutoff_step(df)
    train_df, test_df = time_based_split(df, cutoff)

    assert train_df["step"].max() <= cutoff
    assert test_df["step"].min() > cutoff
    # every train step precedes every test step
    assert train_df["step"].max() <= test_df["step"].min()


def test_naive_cutoff_targets_last_20_percent_of_step_range():
    df = make_raw_df(n_days=10)  # steps span 0-239
    cutoff = compute_cutoff_step(df, test_fraction=0.2)
    step_min, step_max = df["step"].min(), df["step"].max()
    expected = int(step_min + 0.8 * (step_max - step_min))
    assert cutoff == expected


def test_preprocessing_applied_after_split_not_before():
    df = make_raw_df()
    result = time_based_train_test_split(df)

    # X_train/X_test never contain leakage or raw identifier columns --
    # only true if build_features ran on the already-split frames.
    for col in ["newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest", "isFlaggedFraud"]:
        assert col not in result.X_train.columns
        assert col not in result.X_test.columns

    assert len(result.X_train) == len(result.train_df)
    assert len(result.X_test) == len(result.test_df)


def test_diagnostics_counts_match_manual_computation():
    df = make_raw_df()
    result = time_based_train_test_split(df)

    train_diag = result.diagnostics["train"]
    test_diag = result.diagnostics["test"]

    assert train_diag.n_rows == len(result.train_df)
    assert test_diag.n_rows == len(result.test_df)
    assert train_diag.n_fraud == result.train_df["isFraud"].sum()
    assert test_diag.n_fraud == result.test_df["isFraud"].sum()
    assert train_diag.step_min == result.train_df["step"].min()
    assert test_diag.step_max == result.test_df["step"].max()


def test_find_degenerate_days_detects_all_fraud_day_including_missing_rows():
    df = make_raw_df(n_days=5, rows_per_day=20, fraud_every=7)
    # make the last day (day 4) fully fraud -> zero legitimate rows that day
    last_day_mask = df["step"] // 24 == 4
    df.loc[last_day_mask, "isFraud"] = 1

    degenerate = find_degenerate_days(df)
    assert degenerate == [4]


def test_find_degenerate_days_does_not_false_positive_on_a_subset_missing_early_days():
    # a test-split-shaped subset that simply doesn't contain days 0-2 should
    # not be reported as having degenerate days 0-2 -- they're absent, not
    # zero-legitimate. Regression test for a reindex-from-zero bug.
    df = make_raw_df(n_days=5, rows_per_day=20, fraud_every=7)
    subset = df[df["step"] // 24 >= 3].copy()

    degenerate = find_degenerate_days(subset)
    assert degenerate == []


def test_check_split_skew_flags_fraud_rate_ratio_and_degenerate_days():
    df = make_raw_df(n_days=5, rows_per_day=20, fraud_every=7)
    train_df = df[df["step"] // 24 < 4].copy()
    test_df = df[df["step"] // 24 == 4].copy()
    test_df["isFraud"] = 1  # force the test split fully degenerate

    warnings = check_split_skew(train_df, test_df)
    assert any("Fraud rate differs" in w or "ZERO legitimate" in w for w in warnings)
    assert any("ZERO legitimate" in w for w in warnings)


def test_check_split_skew_silent_when_balanced():
    df = make_raw_df(n_days=10, rows_per_day=50, fraud_every=7)
    cutoff = compute_cutoff_step(df)
    train_df, test_df = time_based_split(df, cutoff)

    warnings = check_split_skew(train_df, test_df)
    assert warnings == []


def test_propose_adjusted_cutoff_excludes_trailing_degenerate_day():
    df = make_raw_df(n_days=10, rows_per_day=20, fraud_every=7)
    last_day_mask = df["step"] // 24 == 9
    df.loc[last_day_mask, "isFraud"] = 1  # last day fully degenerate

    adjusted = propose_adjusted_cutoff(df, test_fraction=0.2)
    assert adjusted < 9 * 24  # excludes day 9 entirely from the usable range


def test_adjusted_cutoff_alone_does_not_remove_degenerate_day_from_naive_split():
    """Regression test: propose_adjusted_cutoff() only shifts the cutoff
    used to *compute* the split point -- feeding that value into plain
    time_based_split still lets the test side run to the true max step, so
    a trailing degenerate day survives in the test set. This was caught
    while building the baseline-model notebook: check_split_skew still
    flagged a degenerate day even after "using the adjusted cutoff."
    time_based_split_adjusted (tested below) is the actual fix.
    """
    df = make_raw_df(n_days=10, rows_per_day=20, fraud_every=7)
    last_day_mask = df["step"] // 24 == 9
    df.loc[last_day_mask, "isFraud"] = 1

    adjusted_cutoff = propose_adjusted_cutoff(df, test_fraction=0.2)
    _, naive_test_df = time_based_split(df, adjusted_cutoff)

    assert find_degenerate_days(naive_test_df) == [9]


def test_time_based_split_adjusted_actually_excludes_degenerate_tail():
    df = make_raw_df(n_days=10, rows_per_day=20, fraud_every=7)
    last_day_mask = df["step"] // 24 == 9
    df.loc[last_day_mask, "isFraud"] = 1  # last day fully degenerate

    train_df, test_df, cutoff = time_based_split_adjusted(df, test_fraction=0.2)

    assert find_degenerate_days(test_df) == []
    assert find_degenerate_days(train_df) == []
    assert test_df["step"].max() < 9 * 24  # day 9 dropped entirely, not just relabeled
    assert train_df["step"].max() <= cutoff
    assert test_df["step"].min() > cutoff
    # the degenerate day's rows are gone from both splits, not silently
    # merged into train
    assert len(train_df) + len(test_df) < len(df)
