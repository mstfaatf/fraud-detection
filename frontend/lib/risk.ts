import type { RiskVariant } from "@/components/ui/badge";

/**
 * Three fraud-probability tiers, derived entirely from each row's own
 * threshold_used -- never a hardcoded 0.6145 or an independently-chosen
 * cutoff. "elevated" sits at threshold/2: meaningfully closer to being
 * flagged than a clearly-clear transaction, without inventing a second
 * unrelated operating point the model was never evaluated at.
 *
 *   >= threshold          -> "fraud"    (this is exactly is_fraud)
 *   >= threshold / 2       -> "elevated" (worth a second look, not flagged)
 *   <  threshold / 2       -> "legit"
 */
export function getFraudTier(fraudProbability: number, thresholdUsed: number): RiskVariant {
  if (fraudProbability >= thresholdUsed) return "fraud";
  if (fraudProbability >= thresholdUsed / 2) return "elevated";
  return "legit";
}

export function getFraudTierLabel(variant: RiskVariant): string {
  switch (variant) {
    case "fraud":
      return "fraud";
    case "elevated":
      return "elevated";
    default:
      return "clear";
  }
}
