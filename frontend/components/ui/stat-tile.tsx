import type { ReactNode } from "react";

import { Card } from "./card";

/**
 * "lg" is the headline metric (bigger number, more visual weight) -- "md" is
 * a supporting stat. Deliberately not a uniform grid of identical tiles: the
 * three stats on Overview don't carry equal importance, so they shouldn't
 * look like they do.
 */
export function StatTile({
  label,
  value,
  caption,
  size = "md",
}: {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  size?: "lg" | "md";
}) {
  return (
    <Card>
      <p className="font-mono text-xs uppercase tracking-wide text-text-faint">{label}</p>
      <p className={`mt-2 font-display text-text ${size === "lg" ? "text-4xl" : "text-2xl"}`}>{value}</p>
      {caption ? <p className="mt-1 text-xs text-text-muted">{caption}</p> : null}
    </Card>
  );
}
