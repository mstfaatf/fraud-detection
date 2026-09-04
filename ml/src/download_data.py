"""Download the PaySim fraud detection dataset from Kaggle into ml/data/raw/.

Dataset: https://www.kaggle.com/datasets/ealaxi/paysim1

Usage:
    python ml/src/download_data.py
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPO_ROOT / "ml" / "data" / "raw"
DATASET_SLUG = "ealaxi/paysim1"

KAGGLE_SETUP_INSTRUCTIONS = """
Kaggle download failed — this is almost always missing or invalid API credentials.

To fix:
  1. Log in to Kaggle, then go to https://www.kaggle.com/settings (Account tab).
  2. Under the "API" section, click "Create New Token". This downloads a kaggle.json file.
  3. Place that file here:
       Windows:      C:\\Users\\<you>\\.kaggle\\kaggle.json
       macOS/Linux:  ~/.kaggle/kaggle.json
     (Alternatively, skip the file and set two environment variables instead:
       KAGGLE_USERNAME=<your username>
       KAGGLE_KEY=<the key from kaggle.json>)
  4. Re-run this script:
       python ml/src/download_data.py

If the API route doesn't work for you, download the CSV by hand instead — see the
"Dataset acquisition" section in SETUP.md for those steps.
""".strip()


def main() -> None:
    try:
        import kagglehub
    except ImportError:
        print("ERROR: kagglehub is not installed. Run: pip install -r ml/requirements.txt")
        sys.exit(1)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cache_path = Path(kagglehub.dataset_download(DATASET_SLUG))
    except Exception as exc:
        print(f"ERROR: Kaggle download failed ({exc.__class__.__name__}: {exc})\n")
        print(KAGGLE_SETUP_INSTRUCTIONS)
        sys.exit(1)

    csv_files = list(cache_path.glob("*.csv"))
    if not csv_files:
        print(f"ERROR: no CSV files found in downloaded dataset at {cache_path}")
        sys.exit(1)

    for csv_file in csv_files:
        dest = RAW_DATA_DIR / csv_file.name
        shutil.copy2(csv_file, dest)
        print(f"Copied {csv_file.name} -> {dest}")

    print(f"\nDone. Dataset available in {RAW_DATA_DIR}")


if __name__ == "__main__":
    main()
