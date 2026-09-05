/**
 * Poll interval for the "live feed" feel on /predictions and /health --
 * plain interval polling via TanStack Query's refetchInterval, no
 * WebSockets (real-time ingestion transport hasn't been decided per
 * CLAUDE.md's Known Limitations; polling is the simple interim choice for
 * this project's demo-scale traffic).
 */
export const POLL_INTERVAL_MS = 7_000;
