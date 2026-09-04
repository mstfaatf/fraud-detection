# Setup

How to get a local Python environment running for `ml/` and `backend/` work.

## Prerequisites

- Python 3.11+
- Postgres (local install or a hosted free-tier instance) — only needed once you start running
  the backend against a real database.

## Python environment

This project uses **one shared virtual environment** at the repo root for both `ml/` and
`backend/` — not separate environments per package. It's small enough as a portfolio project that
splitting environments would add friction without real benefit.

### 1. Create the virtual environment

```bash
python -m venv .venv
```

(Or run `bash scripts/setup_venv.sh` from the repo root, which does the same thing.)

### 2. Activate it

```bash
# Windows, Git Bash
source .venv/Scripts/activate

# Windows, PowerShell or cmd
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt -r ml/requirements.txt
```

(Or run `bash scripts/install_deps.sh` with the venv active.)

## Convenience scripts

`scripts/` holds thin wrappers around the commands above — a convenience layer, not a build
system:

| Script | What it does |
|---|---|
| `scripts/setup_venv.sh` | Creates `.venv` at the repo root |
| `scripts/install_deps.sh` | Installs backend + ml requirements into the active venv |
| `scripts/run_eda.sh` | Launches Jupyter in `ml/notebooks` |
| `scripts/run_tests.sh` | Runs the backend test suite (`pytest backend/tests`) |

Run them from the repo root with `bash scripts/<name>.sh` (Git Bash on Windows, or any POSIX
shell on macOS/Linux).

## Dataset acquisition

The project uses **PaySim** — Synthetic Financial Datasets For Fraud Detection —
from Kaggle: https://www.kaggle.com/datasets/ealaxi/paysim1

### Option A: automated download (kagglehub)

```bash
python ml/src/download_data.py
```

This uses `kagglehub` to pull the dataset and copies the CSV into `ml/data/raw/`. It requires a
Kaggle API token:

1. Log in to Kaggle, go to https://www.kaggle.com/settings (Account tab).
2. Under "API", click "Create New Token" — this downloads `kaggle.json`.
3. Place it at:
   - Windows: `C:\Users\<you>\.kaggle\kaggle.json`
   - macOS/Linux: `~/.kaggle/kaggle.json`

   Or, instead of the file, set two environment variables: `KAGGLE_USERNAME` and `KAGGLE_KEY`
   (the values come from `kaggle.json`).
4. Re-run `python ml/src/download_data.py`.

If the download fails, the script prints these same setup steps.

### Option B: manual download

If the API route doesn't work for you (auth issues, corporate network, etc.), download the file
by hand:

1. Go to https://www.kaggle.com/datasets/ealaxi/paysim1 (log in if needed).
2. Click "Download" to get the dataset as a zip file.
3. Unzip it and place the resulting CSV (`PS_20174392719_1491204439457_log.csv`) directly in
   `ml/data/raw/`.

Either way, the end state is the same: a PaySim CSV sitting in `ml/data/raw/`, which is
gitignored (see `.gitignore`) so it never gets committed. Once it's there, run
`python ml/src/data_prep.py` to sanity-check it loaded correctly.

## Environment variables

Backend configuration (database URL, Stripe keys, etc.) will be read from a `.env` file at the
repo root via `python-dotenv` / `pydantic-settings`. `.env` is gitignored — no `.env.example`
exists yet; this will be added once `backend/app/core` config is built out.

## Running things day-to-day

```bash
# Backend (from backend/, with venv active — once app/main.py exists)
uvicorn app.main:app --reload

# Frontend (from frontend/, once the Next.js app is scaffolded)
npm run dev

# EDA
bash scripts/run_eda.sh

# Backend tests
bash scripts/run_tests.sh
```

See `CLAUDE.md` → "Important Commands" for the full reference.
