"""Time-based (chronological) train/test split for the PaySim fraud dataset.

Splits by `step`, never randomly — a random split would leak future
transactions into training and give an optimistic, unrealistic estimate of
how the model would perform on transactions it hasn't seen yet. Chronological
ordering is preserved end to end: sort -> split -> *then* preprocess, so that
if a future feature ever needs a stateful, fitted transform (a scaler, a
target encoder, etc.) it can be fit on the train split only without
restructuring this module. The current Phase 1 feature schema
(`preprocessing.build_features`) is fully stateless/deterministic, so
fit-on-train-only doesn't change today's output — this is future-proofing,
not a current requirement.

Run directly (`python ml/src/split.py`) to print the split diagnostics for
the full PaySim CSV.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from preprocessing import TARGET_COLUMN, build_features

DEFAULT_TEST_FRACTION = 0.2

# A day-sized (24-step) window with zero legitimate transactions is
# unambiguously degenerate: there is nothing to evaluate a false-positive
# rate against for that period, and its 100%-fraud rate is a data artifact,
# not a signal. PaySim's last simulated day (step 720-743) is exactly this
# case: 282/282 rows are fraud.
DEGENERATE_DAY_LEGIT_COUNT = 0

# A fraud-rate ratio between splits beyond this multiple is flagged as
# "badly skewed" rather than silently accepted. PaySim's overall fraud rate
# is ~0.13%; a chronological split landing within the same order of
# magnitude on both sides is expected, a >3x gap is not.
FRAUD_RATE_SKEW_THRESHOLD = 3.0


@dataclass
class SplitDiagnostics:
    name: str
    n_rows: int
    n_fraud: int
    fraud_rate: float
    step_min: int
    step_max: int

    def print_summary(self) -> None:
        print(
            f"  {self.name:<6} rows={self.n_rows:>9,}  fraud={self.n_fraud:>6,}  "
            f"fraud_rate={self.fraud_rate:.4%}  steps=[{self.step_min}, {self.step_max}]"
        )


@dataclass
class TimeSplitResult:
    cutoff_step: int
    train_df: pd.DataFrame
    test_df: pd.DataFrame
    X_train: pd.DataFrame
    y_train: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    feature_columns: list
    diagnostics: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def summarize_split(df: pd.DataFrame, name: str) -> SplitDiagnostics:
    return SplitDiagnostics(
        name=name,
        n_rows=len(df),
        n_fraud=int(df[TARGET_COLUMN].sum()),
        fraud_rate=float(df[TARGET_COLUMN].mean()) if len(df) else 0.0,
        step_min=int(df["step"].min()) if len(df) else -1,
        step_max=int(df["step"].max()) if len(df) else -1,
    )


def find_degenerate_days(df: pd.DataFrame) -> list:
    """Day-sized (24-step) windows with zero legitimate transactions.

    Reindexes over the full day range so a day with *no rows at all* left
    over after filtering out fraud (like PaySim's all-fraud day 30) is still
    caught, rather than silently disappearing from a groupby.
    """
    day = df["step"] // 24
    legit_counts = df.loc[df[TARGET_COLUMN] == 0].groupby(day).size()
    full_range = pd.RangeIndex(int(day.min()), int(day.max()) + 1)
    legit_counts = legit_counts.reindex(full_range, fill_value=0)
    return legit_counts[legit_counts == DEGENERATE_DAY_LEGIT_COUNT].index.tolist()


def compute_cutoff_step(
    df: pd.DataFrame, test_fraction: float = DEFAULT_TEST_FRACTION, max_step: int | None = None
) -> int:
    """Naive chronological cutoff: the last `test_fraction` of the *step
    range* becomes the test set (not a row-count quantile — a row-count
    quantile would implicitly weight the cutoff toward whichever steps
    happen to have more logged transactions, which isn't what "last 20% of
    time" means).

    `max_step` restricts the usable range (used by
    `propose_adjusted_cutoff` to exclude a degenerate tail) without
    dropping rows beyond it from the naive cutoff's own calculation.
    """
    step_min = df["step"].min()
    step_max = max_step if max_step is not None else df["step"].max()
    return int(step_min + (1 - test_fraction) * (step_max - step_min))


def time_based_split(df: pd.DataFrame, cutoff_step: int) -> tuple:
    """Sort by step, then split into (train_df, test_df) at cutoff_step
    (inclusive on the train side)."""
    df = df.sort_values("step").reset_index(drop=True)
    train_df = df[df["step"] <= cutoff_step]
    test_df = df[df["step"] > cutoff_step]
    return train_df, test_df


def check_split_skew(train_df: pd.DataFrame, test_df: pd.DataFrame) -> list:
    """Flag (rather than silently accept) a badly skewed chronological split.

    Two independent, unambiguous checks:
    1. fraud-rate ratio between splits beyond FRAUD_RATE_SKEW_THRESHOLD
    2. either split containing a fully degenerate (zero-legitimate-rows) day
    """
    warnings = []

    train_rate = train_df[TARGET_COLUMN].mean() if len(train_df) else 0.0
    test_rate = test_df[TARGET_COLUMN].mean() if len(test_df) else 0.0
    if min(train_rate, test_rate) > 0:
        ratio = max(train_rate, test_rate) / min(train_rate, test_rate)
        if ratio > FRAUD_RATE_SKEW_THRESHOLD:
            higher = "test" if test_rate > train_rate else "train"
            warnings.append(
                f"Fraud rate differs {ratio:.1f}x between splits (train "
                f"{train_rate:.4%} vs test {test_rate:.4%}, higher in {higher}). "
                f"In PaySim this is driven by legitimate-transaction volume "
                f"collapsing later in the simulation (fraud count per day "
                f"stays roughly flat while legitimate volume drops by 1-2 "
                f"orders of magnitude), not a real shift in fraud behavior."
            )

    for name, part in [("train", train_df), ("test", test_df)]:
        degenerate = find_degenerate_days(part)
        if degenerate:
            warnings.append(
                f"{name} split contains {len(degenerate)} day(s) with ZERO "
                f"legitimate transactions (step//24 in {degenerate}) -- fully "
                f"degenerate, not meaningfully evaluable for that period."
            )

    return warnings


def find_usable_max_step(df: pd.DataFrame) -> int:
    """The last step before a *trailing* run of fully degenerate (zero
    legitimate transaction) days. Only a run ending at the dataset's last
    day counts — an isolated degenerate day in the middle of the timeline
    wouldn't be fixable by moving a single cutoff anyway, and PaySim's only
    such day (30) does sit at the very end.

    Returns the true max step when there is no trailing degenerate run.
    """
    day_max = int(df["step"].max()) // 24
    degenerate_days = set(find_degenerate_days(df))

    trailing_degenerate = 0
    for d in range(day_max, -1, -1):
        if d in degenerate_days:
            trailing_degenerate += 1
        else:
            break

    if trailing_degenerate == 0:
        return int(df["step"].max())

    return (day_max - trailing_degenerate + 1) * 24 - 1


def propose_adjusted_cutoff(df: pd.DataFrame, test_fraction: float = DEFAULT_TEST_FRACTION) -> int:
    """If the trailing days of the dataset are fully degenerate (zero
    legitimate transactions), exclude them from the usable step range and
    recompute the naive 80/20 cutoff over what's left, instead of handing
    the test set a period that's structurally impossible to evaluate a
    false-positive rate on.

    This targets the specific, unambiguous failure (a 100%-fraud day) — it
    does not attempt to fully flatten the softer, gradual volume decline in
    the days before it, which is a real (if messy) characteristic of the
    simulated data and is surfaced as a warning rather than engineered away.

    Note: this cutoff value alone is only half the fix. Feeding it into
    plain `time_based_split` still lets the test side run to the dataset's
    true max step, so the degenerate tail stays in the test set — it just
    becomes a smaller fraction of a now-larger test set. Use
    `time_based_split_adjusted` (which also bounds the test side at
    `find_usable_max_step`) to actually drop the degenerate tail from both
    splits.
    """
    usable_max_step = find_usable_max_step(df)
    return compute_cutoff_step(df, test_fraction, max_step=usable_max_step)


def time_based_split_adjusted(
    df: pd.DataFrame, test_fraction: float = DEFAULT_TEST_FRACTION
) -> tuple:
    """Chronological split that actually excludes a trailing degenerate run
    (see `find_usable_max_step`) from both sides, not just from the cutoff
    arithmetic. Rows beyond the usable range are dropped entirely — they're
    a simulator artifact, not a period either split should be trained or
    evaluated on. Returns (train_df, test_df, cutoff_step).
    """
    usable_max_step = find_usable_max_step(df)
    cutoff_step = compute_cutoff_step(df, test_fraction, max_step=usable_max_step)
    df = df.sort_values("step").reset_index(drop=True)
    train_df = df[df["step"] <= cutoff_step]
    test_df = df[(df["step"] > cutoff_step) & (df["step"] <= usable_max_step)]
    return train_df, test_df, cutoff_step


def time_based_train_test_split(
    df: pd.DataFrame, test_fraction: float = DEFAULT_TEST_FRACTION
) -> TimeSplitResult:
    """End-to-end chronological split + preprocessing for the PaySim schema.

    Order of operations matters: split first, transform second. Prints and
    returns row counts, fraud counts/rate, and min/max step per split, and
    flags (rather than silently proceeding past) a badly skewed split —
    see `check_split_skew`.
    """
    cutoff_step = compute_cutoff_step(df, test_fraction)
    train_df, test_df = time_based_split(df, cutoff_step)

    warnings = check_split_skew(train_df, test_df)
    if warnings:
        adjusted_cutoff = propose_adjusted_cutoff(df, test_fraction)
        print(f"WARNING: naive cutoff (step <= {cutoff_step}) produces a skewed split:")
        for w in warnings:
            print(f"  - {w}")
        if adjusted_cutoff != cutoff_step:
            print(
                f"  Proposed adjusted cutoff: step <= {adjusted_cutoff} "
                f"(excludes the fully degenerate tail from the usable range "
                f"before re-applying the {test_fraction:.0%} split; the "
                f"remaining fraud-rate gap from the gradual volume decline "
                f"is a documented dataset limitation, not something this "
                f"adjustment fully removes)."
            )
        print()

    X_train, y_train, feature_columns = build_features(train_df)
    X_test, y_test, _ = build_features(test_df)

    train_diag = summarize_split(train_df, "train")
    test_diag = summarize_split(test_df, "test")
    print(f"Chronological split at step <= {cutoff_step} ({test_fraction:.0%} test target):")
    train_diag.print_summary()
    test_diag.print_summary()

    return TimeSplitResult(
        cutoff_step=cutoff_step,
        train_df=train_df,
        test_df=test_df,
        X_train=X_train,
        y_train=y_train,
        X_test=X_test,
        y_test=y_test,
        feature_columns=feature_columns,
        diagnostics={"train": train_diag, "test": test_diag},
        warnings=warnings,
    )


def _load_raw_df() -> pd.DataFrame:
    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = repo_root / "ml" / "data" / "raw"
    csv_files = list(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"ERROR: no CSV files found in {raw_dir}")
        sys.exit(1)
    return pd.read_csv(csv_files[0])


def main() -> None:
    df = _load_raw_df()
    time_based_train_test_split(df)


if __name__ == "__main__":
    main()
