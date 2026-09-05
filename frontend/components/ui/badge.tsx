import type { ReactNode } from "react";

export type RiskVariant = "fraud" | "elevated" | "legit" | "anomaly";

/**
 * fraud/legit are filled -- the two outcomes that actually gate a decision
 * (is_fraud, i.e. fraud_probability >= threshold_used). elevated is an
 * *outline* in the same red hue as fraud, not a new color -- it marks a
 * probability that's meaningfully close to the threshold without crossing
 * it (see lib/risk.ts -- the boundary is threshold_used / 2, derived from
 * the model's real per-row threshold, not an arbitrary independent cutoff).
 * anomaly is an outline in a third, unrelated hue: it's a genuinely
 * different signal (Isolation Forest, not XGBoost's probability) and must
 * never be confused with a fraud-probability tier (see
 * ISOLATION_FOREST_FINDINGS.md / CLAUDE.md -- 0% unique-catch precision on
 * the eval set, never meant to override the fraud call). Nothing here is
 * filled except the two real decision outcomes -- deliberately not a
 * status-color rainbow.
 */
const VARIANT_STYLES: Record<RiskVariant, string> = {
  fraud: "border-risk-fraud/40 bg-risk-fraud-soft text-risk-fraud",
  elevated: "border-risk-fraud bg-transparent text-risk-fraud",
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
