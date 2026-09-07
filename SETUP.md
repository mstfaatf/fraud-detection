# Setup

How to get a local Python environment running for `ml/` and `backend/` work.

## Prerequisites

- Python 3.11+
- Postgres (local install or a hosted free-tier instance). Only needed once you start running the
  backend against a real database.

## Python environment

This project uses **one shared virtual environment** at the repo root for both `ml/` and
`backend/`, not separate environments per package. It's small enough as a portfolio project that
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

`scripts/` holds thin wrappers around the commands above: a convenience layer, not a build system.

| Script | What it does |
|---|---|
| `scripts/setup_venv.sh` | Creates `.venv` at the repo root |
| `scripts/install_deps.sh` | Installs backend + ml requirements into the active venv |
| `scripts/run_eda.sh` | Launches Jupyter in `ml/notebooks` |
| `scripts/run_tests.sh` | Runs the backend test suite (`pytest backend/tests`) |

Run them from the repo root with `bash scripts/<name>.sh` (Git Bash on Windows, or any POSIX
shell on macOS/Linux).

## Dataset acquisition

This project uses **PaySim** (Synthetic Financial Datasets For Fraud Detection) from Kaggle:
https://www.kaggle.com/datasets/ealaxi/paysim1

### Option A: automated download (kagglehub)

```bash
python ml/src/download_data.py
```

This uses `kagglehub` to pull the dataset and copies the CSV into `ml/data/raw/`. It requires a
Kaggle API token:

1. Log in to Kaggle, go to https://www.kaggle.com/settings (Account tab).
2. Under "API", click "Create New Token" to download `kaggle.json`.
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
(see "Database (Postgres + Alembic)" below for why). Copy `.env.example` to `.env` and fill in
real values. `.env` itself is gitignored.

## Database (Postgres + Alembic)

Local dev targets a **Docker Postgres container** (`docker-compose.yml`, `postgres` service).
Docker is used here for the database only, not for running the backend/frontend themselves. The
public/live demo instead targets a hosted **Supabase** Postgres project, reusing this exact same
schema and migrations.

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
| `runtime_database_url` | (computed) | `supabase_database_url` if set, else `database_url` | `app/db/session.py`: the app's normal queries |
| `migration_database_url` | (computed) | `supabase_direct_url` if set, else `database_url` | `alembic/env.py`: migrations only |
| `supabase_database_url` | `SUPABASE_DATABASE_URL` | unset | Supabase **Transaction pooler**, port 6543 |
| `supabase_direct_url` | `SUPABASE_DIRECT_URL` | unset | Supabase **direct** connection, port 5432 |

`SUPABASE_DATABASE_URL`/`SUPABASE_DIRECT_URL` are deliberately read as raw env var names, not
`FRAUD_`-prefixed (see the comment in `config.py`), so they read the same whether set in this
project's `.env` or as a literal platform env var on Render/Railway.

**Local dev never depends on Supabase being reachable**: with both Supabase variables unset (the
default, see `.env.example`), `runtime_database_url` and `migration_database_url` both fall back
to the local Docker connection string with zero configuration. Setting either variable (say, to
point this machine at the public demo project for testing) only overrides that one purpose (app
runtime queries or migrations), independently of the other.

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
only when `SUPABASE_DATABASE_URL` is set: the local/direct engines are unaffected):
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
connection. An IPv6-capable host (many cloud platforms, incl. likely Render/Railway) can use the
real direct connection instead.

### 3. Run migrations

```bash
cd backend
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"   # generate a new migration after model changes
```

Run `alembic` commands from `backend/` (its working directory) so `alembic/env.py`'s `from app...`
imports resolve the same way the app's own imports do. Against Supabase, this uses
`SUPABASE_DIRECT_URL` (falling back to `FRAUD_DATABASE_URL`/local Docker if unset). See the IPv6
caveat above if it fails to resolve.

### 4. Verify

```bash
# local
docker exec fraud-detection-postgres psql -U fraud -d fraud_detection -c "\dt"

# Supabase (via the local Postgres container's psql client, or any psql install)
docker exec fraud-detection-postgres psql "<SUPABASE_DIRECT_URL or Session pooler URL>" -c "\dt"
```

should list `transactions`, `predictions`, and `alembic_version` in both.

## Running Locally: Two Paths

There are two genuinely different ways to run this project locally, for two different purposes.
Don't confuse them, and don't assume Docker Compose was ever used to build this project day to
day. It wasn't. Path 1 below is, and always has been, the actual dev loop.

- **Path 1, daily dev (recommended)**: `uvicorn --reload` + `npm run dev` + a local (or hosted)
  Postgres, run directly on the host. Fastest iteration, live reload on both sides, no rebuild step
  between a code change and seeing it run. This is what the whole project was actually built and
  tested against. See "Running things day-to-day" below for the exact commands.
- **Path 2, full-stack Docker Compose**: `docker compose up`, below. Runs the whole stack
  (Postgres + FastAPI + Next.js) as three built containers with one command. This exists as a
  self-contained local setup and as practice containerizing a multi-service app for a portfolio,
  **not** as a faster or better dev loop than path 1, and with **no connection** to the live
  deployment (Render/Vercel/Supabase build and run independently of Docker entirely; see
  `backend/Dockerfile`'s and `frontend/Dockerfile`'s own header comments).

### Path 2: Docker Compose (full stack)

Self-contained against its own local Postgres, never Supabase, regardless of what's in the
repo-root `.env` (see `docker-compose.yml`'s comments on the `backend` service for how that's
enforced).

```bash
docker compose up -d --build

# First time only (and again whenever a new Alembic migration file is added --
# see docker-compose.yml's comment above the `backend` service for why this
# is a manual step, not automatic):
docker compose exec backend alembic upgrade head
```

- Backend: http://localhost:8000 (`/health`, `/predict`, etc.)
- Frontend: http://localhost:3000
- Postgres: `localhost:5432` (same `fraud`/`fraud`/`fraud_detection` credentials as local dev)

Stripe is optional here: if the repo-root `.env` has real `STRIPE_*` test-mode keys set (see
"Stripe (test mode)" below), the backend and frontend containers both pick them up automatically.
If not, Stripe-dependent endpoints return a clean 503 instead of erroring, same as local dev
without Stripe configured. No other env vars need to be set for this stack to run. See
`.env.example`'s "Docker Compose" section for exactly what is and isn't read from `.env` here.

```bash
docker compose down          # stop, keep the postgres_data volume (data persists)
docker compose down -v       # stop and delete the volume (fresh database next time)
```

**Verified working end to end from a genuinely clean state** (a fresh `docker compose down -v`,
then `up --build`): all three containers built, started, and passed their healthchecks
(`postgres` → `pg_isready`; `backend`/`frontend` → their own Dockerfiles' `HEALTHCHECK`s hitting
`/health` and `/`). `alembic upgrade head` created both tables against the container's own,
genuinely empty Postgres (confirmed directly via `psql \dt`, not just Alembic's exit code), and a
transaction submitted through the containerized frontend at `localhost:3000` was scored by the
containerized backend and persisted to the containerized database (confirmed via `GET /predictions`
and a direct `psql` query). One real bug this verification caught and fixed: `alembic.ini`/
`alembic/` weren't in the backend image at all, so the migration command above failed until both
were added to the Dockerfile's `COPY` steps.

## Stripe (test mode)

The Stripe adapter (`backend/app/services/stripe_adapter.py`) maps a Stripe PaymentIntent onto the
model's `TransactionInput` schema, and `POST /webhooks/stripe` (`backend/app/api/
stripe_webhooks.py`) uses it to score a real (test-mode, sandboxed) Stripe payment in real time and
cancel it if the model flags it as fraud. See `stripe_adapter.py`'s own docstring for the full
adapter simplifications and webhook contract. **Test-mode keys only**: sandboxed by Stripe, no real
money ever moves, and this project has no reason to hold a live-mode key at all.

Add these to `.env` (repo root, gitignored, key names only, get the real values from your own
Stripe Dashboard, do not hardcode them anywhere in source):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...   # per-session value from `stripe listen` -- see below
```

### Getting test-mode keys

1. Log in to the [Stripe Dashboard](https://dashboard.stripe.com).
2. Make sure the **Test mode** toggle (top-right) is on. Test-mode and live-mode keys are entirely
   separate credentials.
3. Go to **Developers → API keys**. Copy the **Publishable key** (`pk_test_...`) and reveal +
   copy the **Secret key** (`sk_test_...`).

`backend/app/core/config.py`'s `Settings` reads all three as raw env var names (not the usual
`FRAUD_` prefix), the same convention already used for `SUPABASE_DATABASE_URL`/`FRONTEND_ORIGIN`,
so they read identically whether set in this project's `.env` or as a platform env var on a host
like Render.

### Testing the webhook locally

`STRIPE_WEBHOOK_SECRET` isn't a stable dashboard value the way the other two keys are. It's
printed fresh by the [Stripe CLI](https://docs.stripe.com/stripe-cli) each time you start
`stripe listen`, and only that value verifies signatures for the forwarded events in that
session.

1. Install the Stripe CLI, then either `stripe login` (interactive, browser-based) or skip login
   entirely and pass `--api-key sk_test_...` on every command below (what this project's own
   verification used, since a non-interactive environment can't complete the browser flow).
2. Start the backend (`uvicorn app.main:app --reload`, from `backend/`).
3. In another terminal, start the forwarder. This both forwards events **and** prints the
   `whsec_...` secret for this session:
   ```bash
   stripe listen --forward-to localhost:8000/webhooks/stripe --api-key sk_test_...
   ```
   Copy the printed `whsec_...` into `.env` as `STRIPE_WEBHOOK_SECRET`, then restart the backend
   so it picks up the new value (`Settings` is read once per process at startup).
4. In a third terminal, fire a real (test-mode) event:
   ```bash
   stripe trigger payment_intent.created --api-key sk_test_...
   ```
   This creates a real test-mode PaymentIntent via the Stripe API (no real money, test mode) and
   Stripe delivers the resulting webhook event through your `stripe listen` tunnel to your local
   `/webhooks/stripe`. `stripe listen`'s own terminal shows the forwarded event and the response
   status code your endpoint returned (200/400/etc.); your backend's own logs show the scoring
   result. `stripe trigger`'s fixture always creates a small ($20), non-customer-attached
   PaymentIntent, so it will essentially always score as legitimate. To see a real cancellation,
   create a PaymentIntent directly via the API instead, attached to a customer whose seeded
   `wallet_balance` metadata equals the PaymentIntent's own `amount` (the model's core
   draining-pattern fraud signature).
5. Check the result three ways: the HTTP status `stripe listen` printed for the event, the
   `transactions`/`predictions` rows written with `source = 'stripe_test'` (`docker exec
   fraud-detection-postgres psql -U fraud -d fraud_detection -c "SELECT ... WHERE source =
   'stripe_test'"`), and the real PaymentIntent's `status` via the Stripe API/Dashboard (`canceled`
   if the model flagged it, unchanged otherwise).

## Path 1: Running Things Day-to-Day

```bash
# Backend (from backend/, with venv active -- once app/main.py exists)
uvicorn app.main:app --reload

# Frontend (from frontend/, once the Next.js app is scaffolded)
npm run dev

# EDA
bash scripts/run_eda.sh

# Backend tests
bash scripts/run_tests.sh
```

For the alternative full-stack Docker Compose path, see "Running Locally: Two Paths" above.
