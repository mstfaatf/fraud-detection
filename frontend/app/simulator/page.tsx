"use client";

import Link from "next/link";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import { ColdStartNotice } from "@/components/ui/cold-start-notice";
import { StatTile } from "@/components/ui/stat-tile";
import { describeApiError, type ScenarioWeights, type SimulatorStartRequest } from "@/lib/api";
import { POLL_INTERVAL_MS } from "@/lib/constants";
import { useSimulatorStatus, useSlowLoading, useStartSimulator, useStopSimulator } from "@/lib/hooks";

// Matches backend/app/schemas/simulator.py's SimulatorStartRequest bound
// (rate_per_second: Field(gt=0, le=20)) -- a demo-scale safety cap, not a
// measured platform limit, so this slider can't ask for something the
// backend would reject anyway.
const MIN_RATE = 0.1;
const MAX_RATE = 20;
const RATE_STEP = 0.1;

// Initial slider position only, not a backend default -- the backend has
// no fixed rate of its own (per the original design decision: rate is
// meant to be user-adjustable via a slider, never hardcoded). Whatever the
// slider shows is always what gets sent to POST /simulator/start.
const INITIAL_RATE = 2;

// Matches backend/app/schemas/simulator.py's ScenarioWeights defaults
// (legit=0.85, fraud=0.10, velocity=0.05) as the sliders' starting
// position -- deliberately not PaySim's real ~0.13% fraud prevalence,
// which would almost never produce a visible fraud row in a short demo.
const INITIAL_WEIGHTS: ScenarioWeights = { legit: 85, fraud: 10, velocity: 5 };

function formatUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export default function SimulatorPage() {
  const [rate, setRate] = useState(INITIAL_RATE);
  const [weights, setWeights] = useState<ScenarioWeights>(INITIAL_WEIGHTS);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const statusQuery = useSimulatorStatus();
  const startMutation = useStartSimulator();
  const stopMutation = useStopSimulator();
  const isSlow = useSlowLoading(statusQuery.isLoading);

  const status = statusQuery.data;
  const running = status?.running ?? false;
  const isMutating = startMutation.isPending || stopMutation.isPending;
  const weightSum = weights.legit + weights.fraud + weights.velocity;

  // While running, the sliders are disabled (config can't change mid-run --
  // see the single-run-at-a-time note below) and must show the config that
  // run actually started with, not whatever the local slider state happens
  // to hold -- e.g. after a page reload, local state resets to its initial
  // position, which would otherwise display a rate/mix that isn't the one
  // actually generating transactions right now.
  const displayRate = running && status?.rate_per_second != null ? status.rate_per_second : rate;
  const displayWeights = running && status?.scenario_weights ? status.scenario_weights : weights;
  const displayWeightSum = displayWeights.legit + displayWeights.fraud + displayWeights.velocity;

  async function handleToggle() {
    setErrorMessage(null);
    try {
      if (running) {
        await stopMutation.mutateAsync();
        return;
      }
      if (weightSum <= 0) {
        setErrorMessage("At least one scenario weight must be greater than 0.");
        return;
      }
      const body: SimulatorStartRequest = { rate_per_second: rate, scenario_weights: weights };
      await startMutation.mutateAsync(body);
    } catch (err) {
      setErrorMessage(describeApiError(err));
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl text-text">Simulator</h1>
      <p className="mt-2 max-w-2xl text-text-muted">
        A background generator that keeps calling the real{" "}
        <code className="font-mono text-text">POST /predict</code> pipeline on an interval, so{" "}
        <Link href="/" className="text-accent hover:underline">
          Overview
        </Link>
        &apos;s live feed has continuous activity without submitting transactions by hand. Runs
        in-process on the backend (<code className="font-mono text-text">app/services/simulator.py</code>)
        via the same polling approach as the rest of this dashboard — no WebSockets.
      </p>

      {statusQuery.isError ? (
        <Card className="mt-8">
          <p className="text-sm text-text-muted">
            Couldn&apos;t reach the backend. Is <code className="font-mono text-text">uvicorn</code>{" "}
            running, and does <code className="font-mono text-text">NEXT_PUBLIC_API_URL</code> point
            at it?
          </p>
        </Card>
      ) : (
        <>
          {statusQuery.isLoading && isSlow ? (
            <Card className="mt-8">
              <ColdStartNotice />
            </Card>
          ) : null}

          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatTile
              label="Status"
              value={statusQuery.isLoading ? "—" : running ? "Running" : "Stopped"}
              caption={running ? "generating transactions" : "idle"}
            />
            <StatTile
              label="Transactions this run"
              value={(status?.transactions_generated ?? 0).toLocaleString()}
              caption="resets to 0 on the next start"
            />
            <StatTile label="Uptime" value={formatUptime(status?.uptime_seconds)} />
          </div>

          <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-[380px_1fr]">
            <Card>
              <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Controls</h2>

              <div className="mt-4">
                <SliderField
                  label="Rate"
                  valueLabel={`${displayRate.toFixed(1)} tx/sec`}
                  min={MIN_RATE}
                  max={MAX_RATE}
                  step={RATE_STEP}
                  value={displayRate}
                  onChange={setRate}
                  disabled={running}
                />
                <p className="mt-1.5 text-xs text-text-faint">
                  Transactions generated and scored per second, up to the backend&apos;s safety cap
                  of {MAX_RATE}/sec.
                </p>
              </div>

              <div className="mt-6 space-y-4">
                <p className="font-mono text-[11px] uppercase tracking-wide text-text-faint">
                  Scenario mix
                </p>

                <SliderField
                  label="Legit"
                  valueLabel={String(displayWeights.legit)}
                  min={0}
                  max={100}
                  step={1}
                  value={displayWeights.legit}
                  onChange={(v) => setWeights((w) => ({ ...w, legit: v }))}
                  disabled={running}
                />
                <SliderField
                  label="Fraud"
                  valueLabel={String(displayWeights.fraud)}
                  min={0}
                  max={100}
                  step={1}
                  value={displayWeights.fraud}
                  onChange={(v) => setWeights((w) => ({ ...w, fraud: v }))}
                  disabled={running}
                />
                <SliderField
                  label="Velocity"
                  valueLabel={String(displayWeights.velocity)}
                  min={0}
                  max={100}
                  step={1}
                  value={displayWeights.velocity}
                  onChange={(v) => setWeights((w) => ({ ...w, velocity: v }))}
                  disabled={running}
                />

                <p className="text-xs text-text-faint">
                  Relative weights — not required to sum to 100, the backend normalizes them.
                  {displayWeightSum > 0 ? (
                    <>
                      {" "}
                      Currently{" "}
                      <span className="text-text-muted">
                        {Math.round((displayWeights.legit / displayWeightSum) * 100)}% legit /{" "}
                        {Math.round((displayWeights.fraud / displayWeightSum) * 100)}% fraud /{" "}
                        {Math.round((displayWeights.velocity / displayWeightSum) * 100)}% velocity
                      </span>
                      .
                    </>
                  ) : (
                    " At least one weight must be above 0."
                  )}
                </p>

                <div className="rounded-md border border-risk-anomaly/40 bg-surface-2 p-3 text-xs text-text-muted">
                  <span className="font-mono uppercase tracking-wide text-risk-anomaly">
                    Velocity —{" "}
                  </span>
                  fires a burst of several rapid transactions to demonstrate how the live feed
                  behaves under bursty conditions. The trained model has no account-history or
                  velocity features (PaySim has far too little repeat-customer data to train that
                  on) and scores every transaction in the burst completely
                  independently. This is a dashboard/UI illustration only, not a fraud pattern the
                  model detects.
                </div>
              </div>

              {running ? (
                <p className="mt-4 text-xs text-text-faint">
                  Stop the simulator to change the rate or scenario mix — only one run at a time.
                </p>
              ) : null}

              {errorMessage ? <p className="mt-4 text-sm text-risk-fraud">{errorMessage}</p> : null}

              <button
                type="button"
                onClick={handleToggle}
                disabled={isMutating || statusQuery.isLoading}
                className={`mt-6 w-full rounded-md px-4 py-2 text-sm font-medium transition-opacity disabled:opacity-50 ${
                  running
                    ? "border border-risk-fraud/40 bg-risk-fraud-soft text-risk-fraud hover:opacity-90"
                    : "bg-accent text-bg hover:opacity-90"
                }`}
              >
                {isMutating ? "Working…" : running ? "Stop simulator" : "Start simulator"}
              </button>
            </Card>

            <Card>
              <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">
                What to expect
              </h2>
              <p className="mt-3 text-sm text-text-muted">
                While running, every generated transaction is validated, scored, and persisted
                through the exact same pipeline <code className="font-mono text-text">POST /predict</code>{" "}
                uses (preprocessing → XGBoost → Isolation Forest → SHAP → the{" "}
                <code className="font-mono text-text">transactions</code>/
                <code className="font-mono text-text">predictions</code> tables) — it&apos;s called
                directly in-process, not looped back over HTTP, so it isn&apos;t subject to{" "}
                <code className="font-mono text-text">/predict</code>&apos;s own per-IP rate limit.
              </p>
              <p className="mt-3 text-sm text-text-muted">
                New rows show up on{" "}
                <Link href="/" className="text-accent hover:underline">
                  Overview
                </Link>
                &apos;s recent-activity table on its next poll (every {POLL_INTERVAL_MS / 1000}s) —
                the same generic <code className="font-mono text-text">GET /predictions</code> feed
                that already shows anything submitted via{" "}
                <Link href="/test-transaction" className="text-accent hover:underline">
                  Test a Transaction
                </Link>
                , with no special-casing needed for simulator-generated rows.
              </p>
              <p className="mt-3 text-sm text-text-muted">
                Only one simulator run is allowed at a time — starting a second one while this is
                running is rejected rather than silently restarting it, so a config change always
                means an explicit stop first.
              </p>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function SliderField({
  label,
  valueLabel,
  min,
  max,
  step,
  value,
  onChange,
  disabled,
}: {
  label: string;
  valueLabel: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between font-mono text-[11px] uppercase tracking-wide text-text-faint">
        <span>{label}</span>
        <span className="normal-case tracking-normal text-text-muted">{valueLabel}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent disabled:opacity-50"
      />
    </label>
  );
}
