import { Card } from "@/components/ui/card";

export default function TestTransactionPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="font-display text-3xl text-text">Test a Transaction</h1>
      <p className="mt-3 text-text-muted">
        A form for the same six fields <code className="font-mono text-text">POST /predict</code>{" "}
        accepts — step, type, amount, and the two pre-transaction balances — scored against the real
        XGBoost model running on the backend, with the SHAP explanation rendered as a bar chart
        instead of a JSON blob.
      </p>

      <Card className="mt-8">
        <p className="text-sm text-text-muted">
          Form and chart aren&apos;t built yet — Recharts is installed and ready for the SHAP bars.
        </p>
      </Card>
    </div>
  );
}
