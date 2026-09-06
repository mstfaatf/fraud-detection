"use client";

import { useHealth, useSlowLoading } from "@/lib/hooks";

/** Lives in the sidebar chrome (all pages), not a page's own content --
 * a real, live GET /health check via the same polling TanStack Query setup
 * the rest of the app will use, so the scaffold proves the wiring works end
 * to end rather than just installing the pieces.
 *
 * This is also the very first request the app makes on any page load, so
 * it's the earliest place a Render/Supabase free-tier cold start would show
 * up -- see CLAUDE.md's "Free-tier cold-start mitigation" section. */
export function StatusPill() {
  const { data, isError, isLoading } = useHealth();
  const slow = useSlowLoading(isLoading);

  let label = "checking backend…";
  let dotClassName = "bg-text-faint";
  let title: string | undefined;

  if (!isLoading) {
    if (isError) {
      label = "backend unreachable";
      dotClassName = "bg-risk-fraud";
    } else if (data?.model_loaded && data?.db_connected) {
      label = "model + db online";
      dotClassName = "bg-risk-legit";
    } else {
      label = "degraded";
      dotClassName = "bg-risk-anomaly";
    }
  } else if (slow) {
    label = "waking up the backend…";
    dotClassName = "bg-accent animate-pulse";
    title =
      "This demo runs on a free Render + Supabase tier -- a scheduled ping usually keeps it warm, but an occasional first request can still take up to a couple of minutes (measured directly). Not an error.";
  }

  return (
    <div
      className="flex items-center gap-2 rounded-md border border-border px-3 py-2 font-mono text-[11px] text-text-muted"
      title={title}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClassName}`} />
      {label}
    </div>
  );
}
