import type { RiskVariant } from "./badge";

/** A plain SVG ring, not a charting-library gauge -- there's nothing here
 * Recharts would make easier, and it keeps this component's colors tied
 * directly to the same design tokens (--color-risk-fraud/legit) everything
 * else in the app uses. */
export function ProbabilityGauge({
  probability,
  tier,
  size = 168,
}: {
  probability: number;
  tier: RiskVariant;
  size?: number;
}) {
  const strokeWidth = size * 0.09;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(Math.max(probability, 0), 1);
  const filled = pct * circumference;
  const color = tier === "legit" ? "var(--color-risk-legit)" : "var(--color-risk-fraud)";

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-3xl text-text">{(pct * 100).toFixed(1)}%</span>
        <span className="mt-1 font-mono text-[10px] uppercase tracking-wide text-text-faint">
          fraud probability
        </span>
      </div>
    </div>
  );
}
