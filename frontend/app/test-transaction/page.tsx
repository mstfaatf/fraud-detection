"use client";

import { useState, type FormEvent, type ReactNode } from "react";

import { ShapBarChart } from "@/components/charts/shap-bar-chart";
import { RiskBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ColdStartNotice } from "@/components/ui/cold-start-notice";
import { Legend, Row } from "@/components/ui/detail-row";
import { ProbabilityGauge } from "@/components/ui/gauge";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { describeApiError, type PredictionResponse, type TransactionInput, type TransactionType } from "@/lib/api";
import { formatProbability } from "@/lib/format";
import { usePredictTransaction, useSlowLoading } from "@/lib/hooks";
import { getFraudTier } from "@/lib/risk";

const TRANSACTION_TYPES: TransactionType[] = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"];

// Synthetic destination account ids, following PaySim's own naming
// convention (M = merchant, C = customer/personal) -- not real accounts.
// The model only ever looks at the "M" prefix (see is_merchant_dest in
// ml/src/preprocessing.py), so asking a demo user to type a realistic-
// looking account number would be pure friction for zero signal -- the
// Personal/Merchant toggle below captures the only bit of nameDest that
// actually reaches the model.
const MERCHANT_NAME_DEST = "M0000000000";
const PERSONAL_NAME_DEST = "C0000000000";

interface FormState {
  step: number;
  type: TransactionType;
  amount: number;
  oldbalanceOrg: number;
  oldbalanceDest: number;
  isMerchantDest: boolean;
}

// Mirrors backend/tests/test_predict.py's LEGIT_PAYLOAD/FRAUD_PAYLOAD
// exactly -- these are the same two scenarios the backend's own test suite
// validates against, not values invented for this page.
const LEGIT_EXAMPLE: FormState = {
  step: 10,
  type: "PAYMENT",
  amount: 150.75,
  oldbalanceOrg: 25000,
  oldbalanceDest: 0,
  isMerchantDest: true,
};

const FRAUD_EXAMPLE: FormState = {
  step: 12,
  type: "CASH_OUT",
  amount: 181000,
  oldbalanceOrg: 181000,
  oldbalanceDest: 0,
  isMerchantDest: false,
};

const INPUT_CLASSES =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text focus:border-accent focus:outline-none";

function validate(form: FormState): string | null {
  if (!Number.isInteger(form.step) || form.step < 0) return "Step must be a whole number, 0 or greater.";
  if (Number.isNaN(form.amount) || form.amount < 0) return "Amount must be 0 or greater.";
  if (Number.isNaN(form.oldbalanceOrg) || form.oldbalanceOrg < 0) return "Origin balance must be 0 or greater.";
  if (Number.isNaN(form.oldbalanceDest) || form.oldbalanceDest < 0) return "Destination balance must be 0 or greater.";
  return null;
}

export default function TestTransactionPage() {
  const [form, setForm] = useState<FormState>(LEGIT_EXAMPLE);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const mutation = usePredictTransaction();
  const isSlow = useSlowLoading(mutation.isPending);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validate(form);
    if (problem) {
      setValidationError(problem);
      return;
    }
    setValidationError(null);
    setErrorMessage(null);

    const input: TransactionInput = {
      step: form.step,
      type: form.type,
      amount: form.amount,
      oldbalanceOrg: form.oldbalanceOrg,
      oldbalanceDest: form.oldbalanceDest,
      nameDest: form.isMerchantDest ? MERCHANT_NAME_DEST : PERSONAL_NAME_DEST,
    };

    const start = performance.now();
    try {
      const response = await mutation.mutateAsync(input);
      setLatencyMs(performance.now() - start);
      setResult(response);
    } catch (err) {
      setLatencyMs(null);
      setResult(null);
      setErrorMessage(describeApiError(err));
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl text-text">Test a Transaction</h1>
      <p className="mt-2 max-w-2xl text-text-muted">
        Calls the real <code className="font-mono text-text">POST /predict</code> endpoint live —
        the same XGBoost model, Isolation Forest, and SHAP explainer scoring every transaction on
        Overview, running against whatever you enter below.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-[380px_1fr]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Transaction</h2>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setForm(LEGIT_EXAMPLE)}
                className="text-xs text-accent hover:underline"
              >
                Legit example
              </button>
              <button
                type="button"
                onClick={() => setForm(FRAUD_EXAMPLE)}
                className="text-xs text-accent hover:underline"
              >
                Fraud example
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <Field label="Step" hint="Hours since simulation start — derives hour_of_day/day_of_week.">
              <input
                type="number"
                min={0}
                step={1}
                value={form.step}
                onChange={(e) => setForm({ ...form, step: e.target.valueAsNumber })}
                className={INPUT_CLASSES}
              />
            </Field>

            <Field label="Type">
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value as TransactionType })}
                className={INPUT_CLASSES}
              >
                {TRANSACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Amount">
              <input
                type="number"
                min={0}
                step="0.01"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.valueAsNumber })}
                className={INPUT_CLASSES}
              />
            </Field>

            <Field label="Origin balance (before)">
              <input
                type="number"
                min={0}
                step="0.01"
                value={form.oldbalanceOrg}
                onChange={(e) => setForm({ ...form, oldbalanceOrg: e.target.valueAsNumber })}
                className={INPUT_CLASSES}
              />
            </Field>

            <Field label="Destination balance (before)">
              <input
                type="number"
                min={0}
                step="0.01"
                value={form.oldbalanceDest}
                onChange={(e) => setForm({ ...form, oldbalanceDest: e.target.valueAsNumber })}
                className={INPUT_CLASSES}
              />
            </Field>

            <div>
              <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-text-faint">
                Destination account
              </span>
              <SegmentedControl
                label=""
                value={form.isMerchantDest ? "merchant" : "personal"}
                onChange={(value) => setForm({ ...form, isMerchantDest: value === "merchant" })}
                options={[
                  { value: "personal", label: "Personal" },
                  { value: "merchant", label: "Merchant" },
                ]}
              />
              <p className="mt-1.5 text-xs text-text-faint">
                We don&apos;t collect a real account id here — only whether it&apos;s a merchant,
                since that&apos;s the only part of <code className="font-mono">nameDest</code> the
                model actually uses (<code className="font-mono">is_merchant_dest</code>).
              </p>
            </div>

            {validationError ? <p className="text-sm text-risk-fraud">{validationError}</p> : null}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {mutation.isPending ? "Scoring…" : "Score transaction"}
            </button>
            {isSlow ? <ColdStartNotice className="mt-2" /> : null}
          </form>
        </Card>

        <div className="space-y-4">
          {errorMessage ? (
            <Card>
              <p className="text-sm text-text-muted">{errorMessage}</p>
            </Card>
          ) : null}

          {!result ? (
            !errorMessage ? (
              <Card>
                <p className="text-sm text-text-muted">
                  Fill out the form and hit <span className="text-text">Score transaction</span> —
                  results (probability, decision, anomaly signal, and the SHAP breakdown) show up
                  here.
                </p>
              </Card>
            ) : null
          ) : (
            <PredictionResult data={result} latencyMs={latencyMs} />
          )}
        </div>
      </div>
    </div>
  );
}

function PredictionResult({ data, latencyMs }: { data: PredictionResponse; latencyMs: number | null }) {
  const tier = getFraudTier(data.fraud_probability, data.threshold_used);

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-6">
          <ProbabilityGauge probability={data.fraud_probability} tier={tier} />
          <dl className="min-w-[200px] flex-1 space-y-2 text-sm">
            <Row
              label="Decision"
              value={<RiskBadge variant={tier}>{data.is_fraud ? "fraud" : "legit"}</RiskBadge>}
            />
            <Row label="Threshold" value={<span className="font-mono">{formatProbability(data.threshold_used)}</span>} />
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
            <Row
              label="Round-trip latency"
              value={<span className="font-mono">{latencyMs === null ? "—" : `${latencyMs.toFixed(0)} ms`}</span>}
            />
          </dl>
        </div>
        <p className="mt-4 text-xs text-text-faint">
          This transaction was scored and persisted — it&apos;ll show up in Overview&apos;s recent
          activity on the next poll. <code className="font-mono">POST /predict</code> doesn&apos;t
          return the saved row&apos;s id, so there&apos;s no direct link to its detail page from
          here.
        </p>
      </Card>

      <Card>
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
          Top {data.shap_explanation.length} features — <code className="font-mono">POST /predict</code>{" "}
          caps here; a persisted transaction&apos;s detail page shows the full, uncapped list.
        </p>
        <div className="mt-4">
          <ShapBarChart data={data.shap_explanation} />
        </div>
      </Card>
    </>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-text-faint">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-text-faint">{hint}</span> : null}
    </label>
  );
}
