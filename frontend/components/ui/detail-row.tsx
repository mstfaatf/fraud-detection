import type { ReactNode } from "react";

/** A label/value line inside a <dl> -- shared by the transaction detail page
 * and the Test a Transaction results panel, both of which show the same
 * kind of prediction summary. */
export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-text-muted">{label}</dt>
      <dd className="text-right text-text">{value}</dd>
    </div>
  );
}

/** A small colored-dot + label pair, used as the SHAP chart's sign legend
 * wherever ShapBarChart is shown. */
export function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
