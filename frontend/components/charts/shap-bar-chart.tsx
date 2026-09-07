"use client";

import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ShapContribution } from "@/lib/api";

const BAR_ROW_HEIGHT = 32;

/**
 * Horizontal bar chart of a prediction's real SHAP feature contributions --
 * whatever backend/app/services/prediction_service.py's ranked list actually
 * contains (amount_to_balance_ratio, type_TRANSFER, is_merchant_dest, etc.),
 * never a hardcoded feature list. Bars are colored by sign, not magnitude:
 * a positive SHAP value pushes the model's log-odds output toward fraud, a
 * negative one pushes toward legitimate (see SHAP_FINDINGS.md) -- reusing
 * this project's existing risk-fraud/risk-legit colors for that, rather than
 * introducing a new gradient, since it's the same underlying red/green
 * "fraud-associated vs. not" concept used everywhere else in the UI.
 */
export function ShapBarChart({ data }: { data: ShapContribution[] }) {
  // The API already sorts by |shap_value| descending; Recharts' category
  // axis draws bottom-to-top, so reverse to keep the largest contribution at
  // the top of the chart, matching the API's own order.
  const chartData = [...data].reverse();

  return (
    <div style={{ height: chartData.length * BAR_ROW_HEIGHT + 40 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
          <XAxis
            type="number"
            stroke="var(--color-border)"
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickFormatter={(value: number) => value.toFixed(2)}
            label={{
              value: "SHAP value (log-odds)",
              position: "insideBottom",
              offset: -4,
              fill: "var(--color-text-faint)",
              fontSize: 11,
            }}
          />
          <YAxis
            type="category"
            dataKey="feature"
            width={190}
            stroke="var(--color-border)"
            tick={{ fill: "var(--color-text)", fontSize: 12 }}
          />
          <ReferenceLine x={0} stroke="var(--color-border)" />
          <Tooltip
            cursor={{ fill: "var(--color-surface-2)" }}
            contentStyle={{
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--color-text)",
            }}
            labelStyle={{ color: "var(--color-text-muted)" }}
            formatter={(value) => [typeof value === "number" ? value.toFixed(4) : value, "SHAP value"]}
          />
          <Bar dataKey="shap_value" radius={2}>
            {chartData.map((entry) => (
              <Cell
                key={entry.feature}
                fill={entry.shap_value >= 0 ? "var(--color-risk-fraud)" : "var(--color-risk-legit)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
