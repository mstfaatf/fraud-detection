import type { ReactNode } from "react";

type RiskVariant = "fraud" | "legit" | "anomaly";

/**
 * fraud/legit are filled -- the two outcomes that actually gate a decision.
 * anomaly is an outline only, never filled: it's a secondary, non-blocking
 * signal (see ISOLATION_FOREST_FINDINGS.md / CLAUDE.md -- 0% unique-catch
 * precision on the eval set, never meant to override the fraud call), and
 * giving it its own filled color would read as a third decision state that
 * doesn't actually exist.
 */
const VARIANT_STYLES: Record<RiskVariant, string> = {
  fraud: "border-risk-fraud/40 bg-risk-fraud-soft text-risk-fraud",
  legit: "border-risk-legit/40 bg-risk-legit-soft text-risk-legit",
  anomaly: "border-risk-anomaly bg-transparent text-risk-anomaly",
};

export function RiskBadge({ variant, children }: { variant: RiskVariant; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wide ${VARIANT_STYLES[variant]}`}
    >
      {children}
    </span>
  );
}
