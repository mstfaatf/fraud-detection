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

Backend configuration (database URL, Stripe keys, etc.) is read from a `.env` file at the repo
root via `python-dotenv` / `pydantic-settings`. Most settings use a `FRAUD_` prefix (e.g.
`FRAUD_DATABASE_URL`, `FRAUD_LOG_LEVEL`); the two Supabase variables are the deliberate exception
— see "Database (Postgres + Alembic)" below for why. Copy `.env.example` to `.env` and fill in
real values; `.env` itself is gitignored.

## Database (Postgres + Alembic)

Local dev targets a **Docker Postgres container** (`docker-compose.yml`, `postgres` service) —
Docker is used here for the database only, not for running the backend/frontend themselves (see
`CLAUDE.md` → "Development Workflow"). The public/live demo instead targets a hosted **Supabase**
Postgres project, reusing this exact same schema and migrations.

### 1. Start local Postgres

```bash
docker compose up -d postgres
```

This starts a `postgres:16` container named `fraud-detection-postgres`, with a named volume
(`postgres_data`) so data survives container restarts, on the standard port `5432`.

### 2. Connection strings and env-based switching

`backend/app/core/config.py`'s `Settings` exposes three URL-shaped values:

| setting | env var | default | used by |
|---|---|---|---|
| `database_url` | `FRAUD_DATABASE_URL` | local Docker connection string | fallback for both of the below |
| `runtime_database_url` | (computed) | `supabase_database_url` if set, else `database_url` | `app/db/session.py` — the app's normal queries |
| `migration_database_url` | (computed) | `supabase_direct_url` if set, else `database_url` | `alembic/env.py` — migrations only |
| `supabase_database_url` | `SUPABASE_DATABASE_URL` | unset | Supabase **Transaction pooler**, port 6543 |
| `supabase_direct_url` | `SUPABASE_DIRECT_URL` | unset | Supabase **direct** connection, port 5432 |

`SUPABASE_DATABASE_URL`/`SUPABASE_DIRECT_URL` are deliberately read as raw env var names (not
`FRAUD_`-prefixed) — see the comment in `config.py` — so they read the same whether set in this
project's `.env` or as a literal platform env var on Render/Railway.

**Local dev never depends on Supabase being reachable**: with both Supabase variables unset (the
default — see `.env.example`), `runtime_database_url` and `migration_database_url` both fall back
to the local Docker connection string with zero configuration. Setting either variable (e.g. to
point this machine at the public demo project for testing) overrides only that one purpose — app
runtime queries vs. migrations — independently.

```
# local Docker default
postgresql://fraud:fraud@localhost:5432/fraud_detection

# Supabase Transaction pooler (SUPABASE_DATABASE_URL -- app runtime)
postgresql://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres

# Supabase direct connection (SUPABASE_DIRECT_URL -- migrations)
postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

**Why the app and migrations use different Supabase connections**: the Transaction pooler
(pgbouncer, transaction mode) hands out a possibly-different backend Postgres connection per
transaction, which is fine for the app's short, independent per-request queries but not safe for
DDL (a migration can span more session state than a pooled transaction guarantees survives). The
direct connection is a plain, un-pooled Postgres connection, which migrations need.

Two connection-arg tweaks are applied to the pooled engine specifically (`app/db/session.py`,
only when `SUPABASE_DATABASE_URL` is set — the local/direct engines are unaffected):
`query_cache_size=0` (disables SQLAlchemy's own compiled-statement cache, whose assumptions about
a stable server-side session don't hold when pgbouncer may switch backend connections between
statements) and `poolclass=NullPool` (pgbouncer already pools connections; adding SQLAlchemy's own
pool on top would just hold pgbouncer slots open and idle, per Supabase's own SQLAlchemy guidance).

**IPv6 caveat, discovered while setting this up**: Supabase's direct-connection hostname
(`db.<project-ref>.supabase.co`) resolves to an **IPv6-only** address. Networks without working
IPv6 (this project's dev machine included) get a DNS/`getaddrinfo` failure trying to reach it
directly, not a timeout. If you hit this, Supabase's **Session pooler** connection string (same
host as the Transaction pooler, but **port 5432, not 6543**) is a working IPv4-reachable
substitute for migrations specifically: it's session-mode, not transaction-mode, so it doesn't
have the pooled-connection DDL risk described above, and it resolves over IPv4 via the pooler's
load balancer. Use it as `SUPABASE_DIRECT_URL` if your network can't reach the true direct
connection; an IPv6-capable host (many cloud platforms, incl. likely Render/Railway) can use the
real direct connection instead.

### 3. Run migrations

```bash
cd backend
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"   # generate a new migration after model changes
```

Run `alembic` commands from `backend/` (its working directory) so `alembic/env.py`'s `from app...`
imports resolve the same way the app's own imports do. Against Supabase, this uses
`SUPABASE_DIRECT_URL` (falling back to `FRAUD_DATABASE_URL`/local Docker if unset) — see the IPv6
caveat above if it fails to resolve.

### 4. Verify

```bash
# local
docker exec fraud-detection-postgres psql -U fraud -d fraud_detection -c "\dt"

# Supabase (via the local Postgres container's psql client, or any psql install)
docker exec fraud-detection-postgres psql "<SUPABASE_DIRECT_URL or Session pooler URL>" -c "\dt"
```

should list `transactions`, `predictions`, and `alembic_version` in both.

## Stripe (test mode)

The Stripe adapter (`backend/app/services/stripe_adapter.py`) maps a Stripe PaymentIntent onto the
model's `TransactionInput` schema, so `/predict` can score a real (test-mode, sandboxed) Stripe
payment the same way it scores a simulator-generated or hand-submitted one. **Test-mode keys
only** — sandboxed by Stripe, no real money ever moves, and this project has no reason to hold a
live-mode key at all.

Add these to `.env` (repo root, gitignored — key names only, get the real values from your own
Stripe Dashboard, do not hardcode them anywhere in source):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...   # unused for now -- no webhook endpoint exists yet
```

### Getting test-mode keys

1. Log in to the [Stripe Dashboard](https://dashboard.stripe.com).
2. Make sure the **Test mode** toggle (top-right) is on — test-mode and live-mode keys are
   entirely separate credentials.
3. Go to **Developers → API keys**. Copy the **Publishable key** (`pk_test_...`) and reveal +
   copy the **Secret key** (`sk_test_...`).
4. `STRIPE_WEBHOOK_SECRET` (`whsec_...`) comes from **Developers → Webhooks** once a webhook
   endpoint is registered — not needed yet, since no webhook endpoint exists in this project (see
   CLAUDE.md).

`backend/app/core/config.py`'s `Settings` reads all three as raw env var names (not the usual
`FRAUD_` prefix), the same convention already used for `SUPABASE_DATABASE_URL`/`FRONTEND_ORIGIN` —
so they read identically whether set in this project's `.env` or as a platform env var on a host
like Render.

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
