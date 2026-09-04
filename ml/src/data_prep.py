"""Load the raw PaySim CSV from ml/data/raw/ and sanity-check its schema.

Usage:
    python ml/src/data_prep.py
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPO_ROOT / "ml" / "data" / "raw"

EXPECTED_COLUMNS = [
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
]


def find_raw_csv() -> Path:
    csv_files = list(RAW_DATA_DIR.glob("*.csv"))
    if not csv_files:
        print(f"ERROR: no CSV files found in {RAW_DATA_DIR}")
        print("Run ml/src/download_data.py first, or see SETUP.md for the manual download steps.")
        sys.exit(1)
    if len(csv_files) > 1:
        print(f"Found multiple CSVs in {RAW_DATA_DIR}, using the first: {csv_files[0].name}")
    return csv_files[0]


def main() -> None:
    csv_path = find_raw_csv()
    df = pd.read_csv(csv_path)

    print(f"Loaded {csv_path.name}")
    print(f"\nShape: {df.shape}")
    print(f"\nDtypes:\n{df.dtypes}")
    print(f"\nFirst 5 rows:\n{df.head()}")

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]

    if missing or extra:
        print("\nSCHEMA MISMATCH")
        if missing:
            print(f"  Missing expected columns: {missing}")
        if extra:
            print(f"  Unexpected extra columns: {extra}")
        sys.exit(1)

    print("\nSchema matches expected PaySim columns.")


if __name__ == "__main__":
    main()
