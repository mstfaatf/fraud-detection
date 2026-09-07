/**
 * Shown in place of (or alongside) a bare "Loading…"/spinner once
 * useSlowLoading (lib/hooks.ts) decides a request has been pending long
 * enough to probably be a Render/Supabase free-tier cold start rather than
 * ordinary network latency -- see CLAUDE.md's "Free-tier cold-start
 * mitigation" section. Deliberately worded as a status, not an error: this
 * is expected free-tier behavior, not something broken.
 *
 * "Up to a couple of minutes" is a real measured figure, not a guess: a
 * genuine ~12h20m idle test (keep-alive ping disabled on purpose) found the
 * actual cold start took roughly 95-105s. The "usually" framing was added
 * once the scheduled keep-alive ping (.github/workflows/keep-alive.yml) was
 * confirmed actually firing on its own schedule -- a real "Scheduled" run in
 * the Actions tab, not just a manual workflow_dispatch -- so a cold start is
 * now the occasional exception rather than the expected first-visit case.
 */
export function ColdStartNotice({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-start gap-2 ${className}`}>
      <span className="mt-1 h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />
      <p className="text-sm text-text-muted">
        <span className="text-text">Waking up the backend…</span> This demo runs on a free Render
        + Supabase tier. A scheduled ping usually keeps it warm, but an occasional first visit can
        still take up to a couple of minutes to respond. Expected behavior, not an error — hang
        tight.
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
