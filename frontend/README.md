# Frontend

Next.js 14 (App Router, TypeScript, Tailwind CSS) dashboard for the fraud-detection backend --
see the repo root `CLAUDE.md` for the full project writeup, design-system decisions, and phase
history.

## Local dev

```bash
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your local backend
npm install
npm run dev
```

Requires the FastAPI backend (`backend/`) running separately -- see the root `SETUP.md`.

## Pages

- `/` -- Overview
- `/transactions` -- Transactions
- `/test-transaction` -- Test a Transaction

Skeleton only as of the initial scaffold (see CLAUDE.md's frontend-scaffolding phase) -- real
page content comes next.
