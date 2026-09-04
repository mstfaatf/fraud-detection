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
