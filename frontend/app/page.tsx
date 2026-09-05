import { RiskBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

export default function OverviewPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="font-display text-3xl text-text">Overview</h1>
      <p className="mt-3 text-text-muted">
        This is where the numbers behind the model will live: how much volume XGBoost has scored,
        the flag rate at the live threshold, and where Isolation Forest&apos;s anomaly flag disagrees
        with it — all pulled from <code className="font-mono text-text">GET /predictions</code>.
        That page isn&apos;t wired up yet; this is the shell it&apos;ll sit in.
      </p>

      <Card className="mt-8">
        <p className="font-mono text-xs uppercase tracking-wide text-text-faint">Coming next</p>
        <ul className="mt-3 space-y-2 text-sm text-text-muted">
          <li>Stat tiles for volume scored, flag rate, and the chosen threshold (≈0.6145)</li>
          <li>A feed of the most recently scored transactions</li>
          <li>
            Risk badges like <RiskBadge variant="fraud">fraud</RiskBadge>{" "}
            <RiskBadge variant="legit">legit</RiskBadge> <RiskBadge variant="anomaly">anomaly</RiskBadge>{" "}
            standing in for raw booleans
          </li>
        </ul>
      </Card>
    </div>
  );
}
