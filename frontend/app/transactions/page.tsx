"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PredictionsTable } from "@/components/predictions/predictions-table";
import { Card } from "@/components/ui/card";
import { LoadingOrColdStart } from "@/components/ui/cold-start-notice";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { TRANSACTIONS_PAGE_SIZE } from "@/lib/constants";
import { usePredictions, useSlowLoading } from "@/lib/hooks";

type TriState = "all" | "true" | "false";

function triStateToBool(value: TriState): boolean | undefined {
  return value === "all" ? undefined : value === "true";
}

export default function TransactionsPage() {
  const [isFraudFilter, setIsFraudFilter] = useState<TriState>("all");
  const [anomalyFilter, setAnomalyFilter] = useState<TriState>("all");
  const [page, setPage] = useState(0);

  const query = usePredictions({
    limit: TRANSACTIONS_PAGE_SIZE,
    offset: page * TRANSACTIONS_PAGE_SIZE,
    is_fraud: triStateToBool(isFraudFilter),
    anomaly_flag: triStateToBool(anomalyFilter),
  });

  const total = query.data?.total;
  const items = query.data?.items ?? [];
  const totalPages = total !== undefined ? Math.max(1, Math.ceil(total / TRANSACTIONS_PAGE_SIZE)) : undefined;
  const hasAnyPredictions = total !== undefined && total > 0;
  const isSlow = useSlowLoading(query.isLoading);

  // A filter change (or the live poll finding fewer rows than before under
  // the current filter) can leave `page` pointing past the last real page --
  // clamp back instead of showing an empty page that isn't really "no
  // results for this filter".
  useEffect(() => {
    if (totalPages !== undefined && page > totalPages - 1) {
      setPage(totalPages - 1);
    }
  }, [totalPages, page]);

  function setFilterAndResetPage(setter: (value: TriState) => void, value: TriState) {
    setter(value);
    setPage(0);
  }

  function clearFilters() {
    setIsFraudFilter("all");
    setAnomalyFilter("all");
    setPage(0);
  }

  return (
    <div>
      <h1 className="font-display text-3xl text-text">Transactions</h1>
      <p className="mt-2 max-w-2xl text-text-muted">
        Every transaction scored through <code className="font-mono text-text">POST /predict</code> --
        directly, via the Simulator, or via the Stripe checkout demo -- straight off{" "}
        <code className="font-mono text-text">GET /predictions</code>, newest first,{" "}
        {TRANSACTIONS_PAGE_SIZE} rows per page.
      </p>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl
            label="Fraud"
            value={isFraudFilter}
            onChange={(value) => setFilterAndResetPage(setIsFraudFilter, value)}
            options={[
              { value: "all", label: "All" },
              { value: "true", label: "Fraud" },
              { value: "false", label: "Legit" },
            ]}
          />
          <SegmentedControl
            label="Anomaly"
            value={anomalyFilter}
            onChange={(value) => setFilterAndResetPage(setAnomalyFilter, value)}
            options={[
              { value: "all", label: "All" },
              { value: "true", label: "Flagged" },
              { value: "false", label: "Clear" },
            ]}
          />
        </div>

        {total !== undefined && (
          <span className="font-mono text-xs text-text-faint">{total.toLocaleString()} total</span>
        )}
      </div>

      <Card className="mt-4 !p-0">
        {query.isError ? (
          <div className="p-6 text-sm text-text-muted">
            Couldn&apos;t reach the backend. Is <code className="font-mono text-text">uvicorn</code>{" "}
            running, and does <code className="font-mono text-text">NEXT_PUBLIC_API_URL</code> point at
            it?
          </div>
        ) : query.isLoading ? (
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
              and it shows up here on the next poll.
            </p>
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-text">No transactions match this filter.</p>
            <button type="button" onClick={clearFilters} className="mt-2 text-sm text-accent hover:underline">
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <PredictionsTable items={items} />
            <div className="flex items-center justify-between border-t border-border px-4 py-3">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(0, current - 1))}
                disabled={page === 0}
                className="rounded-md border border-border px-3 py-1.5 text-xs text-text-muted transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="font-mono text-xs text-text-faint">
                Page {page + 1} of {totalPages ?? 1}
              </span>
              <button
                type="button"
                onClick={() =>
                  setPage((current) => (totalPages !== undefined ? Math.min(totalPages - 1, current + 1) : current + 1))
                }
                disabled={totalPages !== undefined && page >= totalPages - 1}
                className="rounded-md border border-border px-3 py-1.5 text-xs text-text-muted transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
