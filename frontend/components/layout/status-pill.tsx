"use client";

import { useHealth } from "@/lib/hooks";

/** Lives in the sidebar chrome (all pages), not a page's own content --
 * a real, live GET /health check via the same polling TanStack Query setup
 * the rest of the app will use, so the scaffold proves the wiring works end
 * to end rather than just installing the pieces. */
export function StatusPill() {
  const { data, isError, isLoading } = useHealth();

  let label = "checking backend…";
  let dotClassName = "bg-text-faint";

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
  }

  return (
    <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2 font-mono text-[11px] text-text-muted">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClassName}`} />
      {label}
    </div>
  );
}
