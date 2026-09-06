/**
 * Shown in place of (or alongside) a bare "Loading…"/spinner once
 * useSlowLoading (lib/hooks.ts) decides a request has been pending long
 * enough to probably be a Render/Supabase free-tier cold start rather than
 * ordinary network latency -- see CLAUDE.md's "Free-tier cold-start
 * mitigation" section. Deliberately worded as a status, not an error: this
 * is expected free-tier behavior, not something broken.
 */
export function ColdStartNotice({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-start gap-2 ${className}`}>
      <span className="mt-1 h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />
      <p className="text-sm text-text-muted">
        <span className="text-text">Waking up the backend…</span> This demo runs on a free Render
        + Supabase tier that spins down after a period of inactivity, so the first request can
        take up to a minute to respond. Expected behavior, not an error — hang tight.
      </p>
    </div>
  );
}

/** Drop-in replacement for a plain "Loading…" line: shows that until `slow`
 * flips true, then swaps to the fuller cold-start explanation. */
export function LoadingOrColdStart({ slow, label = "Loading…" }: { slow: boolean; label?: string }) {
  if (!slow) return <p className="text-sm text-text-muted">{label}</p>;
  return <ColdStartNotice />;
}
