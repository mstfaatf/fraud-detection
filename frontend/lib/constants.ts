/**
 * Poll interval for the "live feed" feel on /predictions and /health --
 * plain interval polling via TanStack Query's refetchInterval, no
 * WebSockets (real-time ingestion transport hasn't been decided per
 * CLAUDE.md's Known Limitations; polling is the simple interim choice for
 * this project's demo-scale traffic).
 */
export const POLL_INTERVAL_MS = 7_000;

/** Rows shown in the Overview page's recent-activity table -- a feed, not
 * the full paginated history (that's the Transactions page's job). */
export const RECENT_TRANSACTIONS_LIMIT = 15;

/** Rows per page on the full Transactions table. 25 -- big enough that a
 * page feels substantial, small enough that a single GET /predictions call
 * (offset/limit, per CLAUDE.md's Phase 6.5 pagination contract) stays
 * cheap. Previous/Next controls, not numbered pages -- see the
 * Transactions page for why. */
export const TRANSACTIONS_PAGE_SIZE = 25;
