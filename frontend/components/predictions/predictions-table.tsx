import Link from "next/link";

import { RiskBadge } from "@/components/ui/badge";
import type { PredictionListItem } from "@/lib/api";
import { formatAmount, formatProbability, formatTimestamp } from "@/lib/format";
import { getFraudTier, getFraudTierLabel } from "@/lib/risk";

/**
 * Shared row/column layout behind both Overview's recent-activity feed and
 * the full Transactions page -- same GET /predictions row shape, same risk
 * badges, same per-row link to /transactions/{id}. Pagination, filtering,
 * and loading/empty states are each page's own concern (they genuinely
 * differ: Overview is a fixed recent slice, Transactions is fully
 * paginated) -- only the table itself was worth extracting.
 */
export function PredictionsTable({ items }: { items: PredictionListItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-text-faint">
            <th className="px-4 py-3 font-mono text-[11px] font-normal uppercase tracking-wide">
              Time
            </th>
            <th className="px-4 py-3 font-mono text-[11px] font-normal uppercase tracking-wide">
              Type
            </th>
            <th className="px-4 py-3 text-right font-mono text-[11px] font-normal uppercase tracking-wide">
              Amount
            </th>
            <th className="px-4 py-3 font-mono text-[11px] font-normal uppercase tracking-wide">
              Fraud probability
            </th>
            <th className="px-4 py-3 font-mono text-[11px] font-normal uppercase tracking-wide">
              Anomaly
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const tier = getFraudTier(item.fraud_probability, item.threshold_used);
            return (
              <tr key={item.id} className="border-b border-border last:border-0">
                <td className="p-0">
                  <Link
                    href={`/transactions/${item.id}`}
                    className="block whitespace-nowrap px-4 py-3 font-mono text-text-muted hover:bg-surface-2"
                  >
                    {formatTimestamp(item.created_at)}
                  </Link>
                </td>
                <td className="p-0">
                  <Link
                    href={`/transactions/${item.id}`}
                    className="block px-4 py-3 font-mono text-text hover:bg-surface-2"
                  >
                    {item.type}
                  </Link>
                </td>
                <td className="p-0">
                  <Link
                    href={`/transactions/${item.id}`}
                    className="block whitespace-nowrap px-4 py-3 text-right font-mono text-text hover:bg-surface-2"
                  >
                    {formatAmount(item.amount)}
                  </Link>
                </td>
                <td className="p-0">
                  <Link
                    href={`/transactions/${item.id}`}
                    className="flex items-center gap-2 whitespace-nowrap px-4 py-3 hover:bg-surface-2"
                  >
                    <RiskBadge variant={tier}>{getFraudTierLabel(tier)}</RiskBadge>
                    <span className="font-mono text-xs text-text-muted">
                      {formatProbability(item.fraud_probability)}
                    </span>
                  </Link>
                </td>
                <td className="p-0">
                  <Link
                    href={`/transactions/${item.id}`}
                    className="block px-4 py-3 hover:bg-surface-2"
                  >
                    {item.anomaly_flag ? (
                      <RiskBadge variant="anomaly">flagged</RiskBadge>
                    ) : (
                      <span className="text-text-faint">—</span>
                    )}
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
