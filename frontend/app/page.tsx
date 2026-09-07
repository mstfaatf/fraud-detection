"use client";

import Link from "next/link";
import { useState } from "react";

import { PredictionsTable } from "@/components/predictions/predictions-table";
import { Card } from "@/components/ui/card";
import { LoadingOrColdStart } from "@/components/ui/cold-start-notice";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { StatTile } from "@/components/ui/stat-tile";
import { POLL_INTERVAL_MS, RECENT_TRANSACTIONS_LIMIT } from "@/lib/constants";
import { usePredictions, useSlowLoading } from "@/lib/hooks";

type TriState = "all" | "true" | "false";

function triStateToBool(value: TriState): boolean | undefined {
  return value === "all" ? undefined : value === "true";
}

function formatRate(numerator: number | undefined, denominator: number | undefined): string {
  if (numerator === undefined || denominator === undefined || denominator === 0) return "—";
  return `${((numerator / denominator) * 100).toFixed(2)}%`;
}

export default function OverviewPage() {
  const [isFraudFilter, setIsFraudFilter] = useState<TriState>("all");
  const [anomalyFilter, setAnomalyFilter] = useState<TriState>("all");

  // Unfiltered -- the real all-time picture, independent of whatever filter
  // the table below is currently set to. limit: 1 keeps these cheap: the
  // response's `total` is a real COUNT(*), the single row is thrown away.
  const totalQuery = usePredictions({ limit: 1 });
  const fraudCountQuery = usePredictions({ limit: 1, is_fraud: true });
  const anomalyCountQuery = usePredictions({ limit: 1, anomaly_flag: true });

  const recentQuery = usePredictions({
    limit: RECENT_TRANSACTIONS_LIMIT,
    is_fraud: triStateToBool(isFraudFilter),
    anomaly_flag: triStateToBool(anomalyFilter),
  });

  const total = totalQuery.data?.total;
  const fraudCount = fraudCountQuery.data?.total;
  const anomalyCount = anomalyCountQuery.data?.total;

  const hasAnyPredictions = total !== undefined && total > 0;
  const items = recentQuery.data?.items ?? [];

  // Overview is the most likely first page a visitor lands on, so this is
  // usually the first place a Render/Supabase free-tier cold start (see
  // CLAUDE.md's "Free-tier cold-start mitigation" section) would show up.
  // Any of these four requests still pending counts -- they all hit the
  // same backend in parallel on mount.
  const isSlow = useSlowLoading(
    totalQuery.isLoading || fraudCountQuery.isLoading || anomalyCountQuery.isLoading || recentQuery.isLoading
  );

  return (
    <div>
      <h1 className="font-display text-3xl text-text">Overview</h1>
      <p className="mt-2 max-w-2xl text-text-muted">
        A live read of what the XGBoost model has scored so far, straight off{" "}
        <code className="font-mono text-text">GET /predictions</code>.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-[2fr_1fr_1fr]">
        <StatTile
          size="lg"
          label="Transactions scored"
          value={total === undefined ? "—" : total.toLocaleString()}
          caption="all-time"
        />
        <StatTile
          label="Fraud rate"
          value={formatRate(fraudCount, total)}
          caption={fraudCount === undefined ? undefined : `${fraudCount.toLocaleString()} flagged`}
        />
        <StatTile
          label="Anomaly flags"
          value={anomalyCount === undefined ? "—" : anomalyCount.toLocaleString()}
          caption="Isolation Forest, secondary signal"
        />
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-xl text-text">Recent activity</h2>
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-text-faint">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-risk-legit opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-risk-legit" />
            </span>
            polling every {POLL_INTERVAL_MS / 1000}s
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl
            label="Fraud"
            value={isFraudFilter}
            onChange={setIsFraudFilter}
            options={[
              { value: "all", label: "All" },
              { value: "true", label: "Fraud" },
              { value: "false", label: "Legit" },
            ]}
          />
          <SegmentedControl
            label="Anomaly"
            value={anomalyFilter}
            onChange={setAnomalyFilter}
            options={[
              { value: "all", label: "All" },
              { value: "true", label: "Flagged" },
              { value: "false", label: "Clear" },
            ]}
          />
        </div>
      </div>

      <Card className="mt-4 !p-0">
        {recentQuery.isError ? (
          <div className="p-6 text-sm text-text-muted">
            Couldn&apos;t reach the backend. Is <code className="font-mono text-text">uvicorn</code>{" "}
            running, and does <code className="font-mono text-text">NEXT_PUBLIC_API_URL</code> point
            at it?
          </div>
        ) : recentQuery.isLoading ? (
          <div className="p-6">
            <LoadingOrColdStart slow={isSlow} />
          </div>
        ) : !hasAnyPredictions ? (
          <div className="p-10 text-center">
            <p className="text-text">No transactions scored yet.</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-text-muted">
              This Postgres instance is empty. Score one via{" "}
              <Link href="/test-transaction" className="text-accent hover:underline">
                Test a Transaction
              </Link>{" "}
              or a direct <code className="font-mono text-text">POST /predict</code> call, and it
              shows up here on the next poll.
            </p>
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-text">No transactions match this filter.</p>
            <button
              type="button"
              onClick={() => {
                setIsFraudFilter("all");
                setAnomalyFilter("all");
              }}
              className="mt-2 text-sm text-accent hover:underline"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <PredictionsTable items={items} />
        )}
      </Card>
    </div>
  );
}
