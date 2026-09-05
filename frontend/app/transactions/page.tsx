import { Card } from "@/components/ui/card";

export default function TransactionsPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="font-display text-3xl text-text">Transactions</h1>
      <p className="mt-3 text-text-muted">
        Every transaction scored through <code className="font-mono text-text">POST /predict</code>{" "}
        gets persisted as a linked transaction + prediction pair (see CLAUDE.md, Phase 6). This page
        will list them straight off <code className="font-mono text-text">GET /predictions</code> —
        paginated, newest first, filterable by fraud and anomaly flag — with a colored risk badge per
        row instead of a raw <code className="font-mono text-text">is_fraud</code> boolean.
      </p>

      <Card className="mt-8">
        <p className="text-sm text-text-muted">Table not wired up yet — just the route and the API client so far.</p>
      </Card>
    </div>
  );
}
