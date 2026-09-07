"""Serializes the Isolation Forest anomaly-detection model to ml/models/isolation_forest.pkl.

ml/notebooks/07_isolation_forest.ipynb was exploratory/evaluative only, per its documented scope,
and never pickled its trained model. This script retrains it with the exact same hyperparameters,
split, and feature pipeline documented there and in ISOLATION_FOREST_FINDINGS.md, so the backend
has an artifact to load. `contamination=0.01` is set at fit time here (rather than left at "auto"
as in the notebook) so the serialized model's own `.predict()` / `.offset_` matches the chosen
operating threshold from that notebook -- this does not change the fitted trees or anomaly scores,
since `contamination` only affects the post-fit `offset_` computation, not tree structure
(confirmed in the notebook by reading `IsolationForest.fit()`'s source).
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

from sklearn.ensemble import IsolationForest

RANDOM_STATE = 42
CONTAMINATION = 0.01


def find_repo_root(start: Path) -> Path:
    """Walks up for a .git directory or the .repo-root marker file (see the
    matching function/docstring in backend/app/core/config.py for why this
    used to look for CLAUDE.md specifically and why that was fragile).
    """
    for parent in [start, *start.parents]:
        if (parent / ".git").exists() or (parent / ".repo-root").exists():
            return parent
    raise FileNotFoundError("Could not locate repo root (looked for .git or .repo-root)")


def main() -> None:
    repo_root = find_repo_root(Path(__file__).resolve())
    sys.path.insert(0, str(repo_root / "ml" / "src"))

    import pandas as pd

    from preprocessing import build_features
    from split import time_based_split_adjusted

    raw_csv = next((repo_root / "ml" / "data" / "raw").glob("*.csv"))
    df = pd.read_csv(raw_csv)
    print(f"Loaded {raw_csv.name}: {df.shape[0]:,} rows")

    train_df, _test_df, cutoff_used = time_based_split_adjusted(df)
    print(f"Adjusted cutoff: step <= {cutoff_used}")

    X_train, _y_train, _feature_columns = build_features(train_df)
    X_train = X_train.astype(float)
    print(f"X_train: {X_train.shape}")

    iso_forest = IsolationForest(
        n_estimators=200,
        max_samples="auto",
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    iso_forest.fit(X_train)
    print("Isolation Forest fit complete (unsupervised, isFraud label never used).")

    models_dir = repo_root / "ml" / "models"
    out_path = models_dir / "isolation_forest.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(iso_forest, f)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
