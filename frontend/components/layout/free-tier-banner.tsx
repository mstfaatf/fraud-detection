"use client";

import { useEffect, useState } from "react";

const DISMISS_KEY = "fraud-detection:free-tier-banner-dismissed";

/**
 * Global, dismissible heads-up that this demo runs on free-tier hosting
 * (Render + Supabase), usually kept warm by a scheduled keep-alive ping, but
 * that an occasional first visit can still take up to a couple of minutes to
 * respond while the backend spins back up. The "up to a couple of minutes"
 * figure is a real measurement, not an estimate -- see CLAUDE.md's
 * "Free-tier cold-start mitigation" section: a genuine ~12h20m idle test
 * (keep-alive ping disabled) found the actual cold start took roughly
 * 95-105s. The "usually warm" framing was added once the keep-alive ping
 * was confirmed actually firing on its own schedule (a real "Scheduled" run
 * in the Actions tab, not just a manual workflow_dispatch), not before.
 * Lives in the root layout, not a single page -- a shared link could point
 * straight at /checkout or /simulator, not just Overview, so this needs to
 * be visible regardless of which page a visitor lands on first.
 *
 * This is the calm, always-visible counterpart to the per-request "Waking
 * up the backend..." notices (components/ui/cold-start-notice.tsx) that
 * only appear once a specific request is actually slow -- see CLAUDE.md's
 * "Free-tier cold-start mitigation" section for how the two fit together.
 */
export function FreeTierBanner() {
  // Renders nothing until mounted, matching what the server rendered, so
  // there's no hydration mismatch -- localStorage doesn't exist server-side.
  // A visitor who previously dismissed this never sees it appear at all; a
  // first-time visitor sees it appear a beat after mount, which is fine.
  const [mounted, setMounted] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") setDismissed(true);
    } catch {
      // Private window / storage blocked -- falls back to showing the
      // banner every visit, which is harmless.
    }
  }, []);

  function handleDismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Nothing to persist -- it'll just show again next visit.
    }
  }

  if (!mounted || dismissed) return null;

  return (
    <div className="flex items-center justify-between gap-4 border-b border-border bg-surface-2 px-4 py-2 text-xs text-text-muted">
      <span className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
        This demo runs on free-tier hosting (Render + Supabase) — a scheduled ping usually keeps
        it warm, but an occasional first visit can still take up to a couple of minutes while the
        backend spins back up. A hosting characteristic, not a bug.
      </span>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded px-1.5 py-0.5 text-text-faint transition-colors hover:bg-surface hover:text-text"
      >
        ✕
      </button>
    </div>
  );
}
