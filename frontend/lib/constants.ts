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

/** How long a request has to stay pending before useSlowLoading (lib/hooks.ts)
 * flags it as "probably a Render/Supabase free-tier cold start, not just
 * normal network latency" -- see CLAUDE.md's cold-start section. Long enough
 * that a normal warm request (well under 1s locally, well under this even
 * against the deployed Supabase-backed instance -- see Phase 8's measured
 * latencies) never trips it; short enough that a genuine cold start doesn't
 * sit there looking blank/broken for very long before an explanation shows. */
export const SLOW_REQUEST_THRESHOLD_MS = 3_000;
