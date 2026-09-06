# Fraud Detection Platform

A real-time fraud detection platform built on Kaggle's PaySim dataset: every transaction is scored
the instant it arrives by an XGBoost classifier, explained per-decision with SHAP, and
cross-checked against an Isolation Forest anomaly signal — end to end, from a FastAPI/Postgres
backend through a live Next.js dashboard, with a real (test-mode) Stripe payment integration
gated by the model in real time. It's a **portfolio project** demonstrating ML, backend, and
frontend engineering together — not a production fraud system — so decisions throughout optimize
for demonstrating real engineering practice (time-based train/test splits, leakage-aware feature
design, model explainability, an honest accounting of the dataset's limits) over handling
real-world scale.

## Live Demo

**Frontend:** [fraud-detection-six-nu.vercel.app](https://fraud-detection-six-nu.vercel.app)
**Backend API:** [fraud-detection-api-blkr.onrender.com](https://fraud-detection-api-blkr.onrender.com) (interactive docs at `/docs`)

> **Heads up:** this runs on free-tier hosting (Render + Supabase). After a period of inactivity,
> the first request can take 20–50 seconds while the backend spins back up — that's a hosting
> characteristic, not a bug. The site itself explains this if you hit it (a dismissible banner, and
> a "waking up the backend…" status in place of a blank screen on any request that's taking a
> while), and a scheduled keep-alive ping reduces how often it happens — but it can still happen on
> a genuinely fresh visit.

## Feature Walkthrough

### Overview

![Overview page](docs/screenshots/overview.png)

The landing page: all-time stat tiles (transactions scored, fraud rate, anomaly flags) and a
live-polling feed of the most recent predictions, filterable by fraud/anomaly status. Every row
links through to a full SHAP breakdown for that transaction.

### Transactions

![Transactions page](docs/screenshots/transactions.png)

The full history behind Overview's feed, off the same `GET /predictions` endpoint — real
Previous/Next pagination (25 rows/page) instead of a fixed recent slice, with the same fraud/
anomaly filters.

### Test a Transaction

![Test a Transaction page](docs/screenshots/test-transaction.png)

A live form that calls `POST /predict` directly. Enter a transaction by hand (or load a preset
legit/fraud example) and see the real fraud probability, decision, anomaly score, and a SHAP
waterfall chart explaining exactly which features pushed the score toward fraud or legitimate.

### Simulator

![Simulator page](docs/screenshots/simulator.png)

A background transaction generator that continuously calls the same scoring pipeline as Test a
Transaction, so the dashboard has a live feed of activity without submitting transactions by hand.
Rate and the legit/fraud/velocity scenario mix are both adjustable from the page.

### Checkout Demo

![Checkout Demo page](docs/screenshots/checkout.png)

A real (test-mode, sandboxed — no real money moves) Stripe payment flow: creating a PaymentIntent
fires a real Stripe webhook that scores the payment through this project's model in real time and
can cancel it before it's ever confirmed — the model gating a live payment rail, not just an
isolated ML demo running on the side.

## Tech Stack

- **Backend** — FastAPI, SQLAlchemy, Alembic, PostgreSQL (Supabase in production)
- **ML** — scikit-learn, XGBoost, SHAP, imbalanced-learn, trained on Kaggle's PaySim synthetic
  fraud dataset
- **Frontend** — Next.js 14 (App Router), TypeScript, Tailwind CSS, TanStack Query, Recharts
- **Payments** — Stripe (test mode)
- **Deployment** — Render (backend), Vercel (frontend), Supabase (Postgres), GitHub Actions
  (scheduled keep-alive ping)

## Known Limitations

Pulled from this project's own decision log, not reinvented here — see the link below for the
full reasoning behind each:

- **Synthetic data, not real transactions.** The model is trained entirely on PaySim, a simulated
  dataset — chosen specifically because its fields are interpretable (real amounts and balances,
  not PCA-anonymized columns), which is what makes the SHAP explainability story possible, but it
  isn't real-world transaction data.
- **The model has never seen fraud outside two transaction types.** PaySim's fraud only occurs in
  `TRANSFER` and `CASH_OUT` — there are zero fraud examples for `PAYMENT`, `CASH_IN`, or `DEBIT` to
  train on.
- **No account-history or velocity features.** PaySim has too little repeat-customer activity
  (0.15% of origin accounts recur) to train real behavioral features on. The Simulator's
  "velocity" scenario is a UI illustration of a rapid-fire transaction burst, not a claim that the
  model detects velocity-based fraud — every transaction in a burst is scored completely
  independently.
- **The fraud threshold (~0.6145) is a reasoned demo choice, not cost-calibrated.** It maximizes
  precision at ≥99% recall on the evaluation set — a defensible default given there's no real
  fraud/false-positive cost data behind a synthetic dataset, not a number derived from actual
  business economics.
- **Isolation Forest is a secondary, non-blocking signal.** In evaluation it added zero unique
  fraud catches beyond XGBoost on this dataset (PaySim's fraud only has one generation pattern) —
  it's surfaced as a separate "anomaly" flag and never blended into the fraud decision.

For the full decision log — every EDA finding, model comparison, and architecture tradeoff behind
this project, phase by phase — see **[CLAUDE.md](./CLAUDE.md)**.

Local development setup (Python/Node environments, database, Stripe test keys) is covered in
[SETUP.md](./SETUP.md).
