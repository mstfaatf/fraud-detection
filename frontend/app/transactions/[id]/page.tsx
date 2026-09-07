"use client";

import Link from "next/link";

import { ShapBarChart } from "@/components/charts/shap-bar-chart";
import { RiskBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { LoadingOrColdStart } from "@/components/ui/cold-start-notice";
import { Legend, Row } from "@/components/ui/detail-row";
import { ApiError } from "@/lib/api";
import { formatAmount, formatProbability, formatTimestamp } from "@/lib/format";
import { usePrediction, useSlowLoading } from "@/lib/hooks";
import { getFraudTier, getFraudTierLabel } from "@/lib/risk";

export default function TransactionDetailPage({ params }: { params: { id: string } }) {
  const { data, isLoading, isError, error } = usePrediction(params.id);
  const isSlow = useSlowLoading(isLoading);

  if (isLoading) {
    return (
      <div>
        <BackLink />
        <div className="mt-6">
          <LoadingOrColdStart slow={isSlow} label="Loading transaction…" />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div>
        <BackLink />
        <div className="mt-6 max-w-md">
          <h1 className="font-display text-2xl text-text">
            {notFound ? "Transaction not found" : "Couldn't load this transaction"}
          </h1>
          <p className="mt-2 text-text-muted">
            {notFound ? (
              <>
                No prediction exists with id <code className="font-mono text-text">{params.id}</code>.
              </>
            ) : (
              <>
                The backend didn&apos;t respond — is it running, and does{" "}
                <code className="font-mono text-text">NEXT_PUBLIC_API_URL</code> point at it?
              </>
            )}
          </p>
        </div>
      </div>
    );
  }

  const tier = getFraudTier(data.fraud_probability, data.threshold_used);

  return (
    <div>
      <BackLink />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-3xl text-text">Transaction</h1>
        <RiskBadge variant={tier}>{getFraudTierLabel(tier)}</RiskBadge>
        {data.anomaly_flag ? <RiskBadge variant="anomaly">anomaly</RiskBadge> : null}
      </div>
      <p className="mt-1 font-mono text-xs text-text-faint">{data.id}</p>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Transaction</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <Row label="Amount" value={formatAmount(data.amount)} />
            <Row label="Type" value={<span className="font-mono">{data.type}</span>} />
            <Row label="Origin balance" value={formatAmount(data.oldbalanceOrg)} />
            <Row label="Destination balance" value={formatAmount(data.oldbalanceDest)} />
            <Row
              label="Destination"
              value={data.is_merchant_dest ? "Merchant account" : "Personal account"}
            />
            <Row label="Scored at" value={formatTimestamp(data.created_at)} />
          </dl>
        </Card>

        <Card>
          <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Prediction</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <Row label="Fraud probability" value={<span className="font-mono">{formatProbability(data.fraud_probability)}</span>} />
            <Row label="Decision" value={<RiskBadge variant={tier}>{data.is_fraud ? "fraud" : "legit"}</RiskBadge>} />
            <Row
              label="Threshold"
              value={<span className="font-mono">{formatProbability(data.threshold_used)}</span>}
            />
            <Row
              label="Anomaly flag"
              value={
                data.anomaly_flag ? (
                  <RiskBadge variant="anomaly">flagged</RiskBadge>
                ) : (
                  <span className="text-text-faint">not flagged</span>
                )
              }
            />
            <Row label="Anomaly score" value={<span className="font-mono">{data.anomaly_score.toFixed(3)}</span>} />
            <Row label="Model version" value={<span className="font-mono">{data.model_version}</span>} />
          </dl>
        </Card>
      </div>

      <Card className="mt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">
            SHAP feature contributions
          </h2>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <Legend color="var(--color-risk-fraud)" label="pushes toward fraud" />
            <Legend color="var(--color-risk-legit)" label="pushes toward legit" />
          </div>
        </div>
        <p className="mt-1 text-xs text-text-faint">
          All {data.shap_explanation.length} features this model was trained on, ranked by
          |SHAP value| — not capped at 5 like <code className="font-mono">POST /predict</code>&apos;s
          response.
        </p>
        <div className="mt-4">
          <ShapBarChart data={data.shap_explanation} />
        </div>
      </Card>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="text-sm text-text-muted hover:text-accent">
      ← Back to Overview
    </Link>
  );
}
