# Frontend

Next.js 14 (App Router, TypeScript, Tailwind CSS) dashboard for the fraud-detection backend.

## Local dev

```bash
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your local backend
npm install
npm run dev
```

Requires the FastAPI backend (`backend/`) running separately. See the root `SETUP.md`.

## Pages

- `/`: Overview
- `/transactions`: Transactions
- `/test-transaction`: Test a Transaction

Skeleton only as of the initial scaffold. Real page content comes next.
