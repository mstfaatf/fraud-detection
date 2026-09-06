"use client";

import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { useRef, useState, type FormEvent } from "react";

import { RiskBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ColdStartNotice } from "@/components/ui/cold-start-notice";
import { describeApiError, type PredictionListItem } from "@/lib/api";
import { POLL_INTERVAL_MS } from "@/lib/constants";
import { formatAmount, formatProbability } from "@/lib/format";
import { useCreatePaymentIntent, usePredictions, useSlowLoading } from "@/lib/hooks";
import { getFraudTier } from "@/lib/risk";

// loadStripe() is called once at module scope, not inside the component --
// Stripe's own recommendation, so the underlying Stripe object isn't
// recreated on every render. `null` when the publishable key isn't
// configured, handled explicitly below rather than crashing on
// loadStripe(undefined).
const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
const stripePromise = STRIPE_PUBLISHABLE_KEY ? loadStripe(STRIPE_PUBLISHABLE_KEY) : null;

const DEFAULT_AMOUNT = 100;

// Stripe Elements renders inside a cross-origin iframe, so this project's
// CSS custom properties (app/globals.css) can't be inherited into it --
// var(--color-*) references would resolve to nothing in there. These are
// the same palette values as hardcoded hex, specifically so the card form
// doesn't render as Stripe's default stark-white widget against this
// project's dark-graphite theme (see CLAUDE.md's design-system notes on why
// that default look is deliberately avoided everywhere else in this app).
const STRIPE_ELEMENTS_APPEARANCE = {
  theme: "night" as const,
  variables: {
    colorPrimary: "#c9a04a", // --color-accent
    colorBackground: "#1b1b20", // --color-surface
    colorText: "#e9e6df", // --color-text
    colorTextSecondary: "#9c968c", // --color-text-muted
    colorTextPlaceholder: "#66605a", // --color-text-faint
    colorDanger: "#d1574a", // --color-risk-fraud
    borderRadius: "6px",
  },
  // `theme: "night"` + `variables.colorBackground` alone left the card
  // tab/input/accordion surfaces rendering white in practice (confirmed
  // live, screenshotted) -- these explicit per-selector overrides are what
  // actually forces it, rather than relying on the theme preset to cascade.
  rules: {
    ".Tab": { backgroundColor: "#1b1b20", border: "1px solid #2c2c33" },
    ".Tab:hover": { backgroundColor: "#222229" },
    ".Tab--selected": { backgroundColor: "#222229", border: "1px solid #c9a04a" },
    ".Block": { backgroundColor: "#1b1b20", border: "1px solid #2c2c33" },
    ".Input": { backgroundColor: "#1b1b20", border: "1px solid #2c2c33", color: "#e9e6df" },
    ".Input:focus": { border: "1px solid #c9a04a" },
    ".Label": { color: "#9c968c" },
  },
};

interface CheckoutSession {
  clientSecret: string;
  paymentIntentId: string;
  walletBalance: number;
  amount: number;
}

type ConfirmOutcome = { kind: "declined"; message: string } | { kind: "blocked" } | { kind: "succeeded" } | null;

export default function CheckoutPage() {
  const [session, setSession] = useState<CheckoutSession | null>(null);

  return (
    <div>
      <h1 className="font-display text-3xl text-text">Checkout Demo</h1>
      <p className="mt-2 max-w-2xl text-text-muted">
        A real, test-mode (sandboxed — no real money moves) Stripe payment, scored by the same
        XGBoost model as the rest of this app. Unlike{" "}
        <code className="font-mono text-text">Test a Transaction</code>, this doesn&apos;t call{" "}
        <code className="font-mono text-text">POST /predict</code> directly — it goes through a
        real <code className="font-mono text-text">payment_intent.created</code> webhook (
        <code className="font-mono text-text">POST /webhooks/stripe</code>), so the fraud check
        happens asynchronously, not the instant you click Pay.
      </p>

      <div className="mt-8 max-w-xl">
        {!STRIPE_PUBLISHABLE_KEY ? (
          <Card>
            <p className="text-sm text-text-muted">
              <code className="font-mono text-text">NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY</code> isn&apos;t
              set. Add it to <code className="font-mono text-text">frontend/.env.local</code> (see
              SETUP.md&apos;s &quot;Stripe (test mode)&quot; section) to use this demo.
            </p>
          </Card>
        ) : !session ? (
          <AmountForm onCreated={setSession} />
        ) : (
          <Elements
            key={session.clientSecret}
            stripe={stripePromise}
            options={{ clientSecret: session.clientSecret, appearance: STRIPE_ELEMENTS_APPEARANCE }}
          >
            <PaymentPanel session={session} onStartOver={() => setSession(null)} />
          </Elements>
        )}
      </div>
    </div>
  );
}

function AmountForm({ onCreated }: { onCreated: (session: CheckoutSession) => void }) {
  const [amount, setAmount] = useState(DEFAULT_AMOUNT);
  const [error, setError] = useState<string | null>(null);
  const mutation = useCreatePaymentIntent();
  const isSlow = useSlowLoading(mutation.isPending);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Amount must be greater than 0.");
      return;
    }

    try {
      const result = await mutation.mutateAsync(amount);
      onCreated({
        clientSecret: result.client_secret,
        paymentIntentId: result.payment_intent_id,
        walletBalance: result.wallet_balance,
        amount,
      });
    } catch (err) {
      setError(describeApiError(err));
    }
  }

  return (
    <Card>
      <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Amount</h2>
      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wide text-text-faint">
            Payment amount (USD)
          </span>
          <input
            type="number"
            min={0.5}
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.valueAsNumber)}
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
          />
        </label>

        {error ? <p className="text-sm text-risk-fraud">{error}</p> : null}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? "Creating PaymentIntent…" : "Continue to payment"}
        </button>
        {isSlow ? <ColdStartNotice /> : null}
      </form>
    </Card>
  );
}

function PaymentPanel({ session, onStartOver }: { session: CheckoutSession; onStartOver: () => void }) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState<ConfirmOutcome>(null);
  // Guards against setting state after this panel unmounts (e.g. "Start
  // over" clicked mid-confirm) -- confirmPayment is async and its promise
  // can resolve after the component's gone.
  const mountedRef = useRef(true);

  // Polls GET /predictions?source=stripe_test, the same POLL_INTERVAL_MS
  // cadence used everywhere else in this dashboard (no special faster
  // interval for this page -- the visible wait is honest, not hidden or
  // sped up). Started as soon as this panel mounts (i.e. as soon as
  // POST /create-payment-intent returns), not only after the user clicks
  // Pay -- Stripe fires payment_intent.created (and this project's webhook
  // scores/gates it) at PaymentIntent *creation* time, which can be well
  // before the user finishes entering card details.
  const predictionsQuery = usePredictions({ source: "stripe_test", limit: 10 });
  const matched = predictionsQuery.data?.items.find((item) => Math.abs(item.amount - session.amount) < 0.01);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    setSubmitting(true);
    setOutcome(null);

    const { error, paymentIntent } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
      confirmParams: {
        return_url: typeof window !== "undefined" ? window.location.href : undefined,
      },
    });

    if (!mountedRef.current) return;
    setSubmitting(false);

    if (error) {
      // A PaymentIntent Stripe already canceled (because this project's own
      // webhook flagged it as fraud and called stripe.PaymentIntent.cancel)
      // cannot be confirmed -- confirmPayment surfaces that as an error, not
      // a silent no-op. Distinguishing this from a genuine card decline
      // matters: one is Stripe rejecting a bad card, the other is this
      // project's fraud model actually gating the payment. This assumes
      // nothing else in this system ever cancels one of these checkout
      // PaymentIntents -- true today (only the webhook's fraud-gating logic
      // calls .cancel() on them), so a canceled status reliably means "the
      // model blocked it," not a coincidence this heuristic has to guess at.
      if (error.payment_intent?.status === "canceled") {
        setOutcome({ kind: "blocked" });
      } else {
        setOutcome({ kind: "declined", message: error.message ?? "The card was declined." });
      }
      return;
    }

    if (paymentIntent) {
      setOutcome({ kind: "succeeded" });
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-wide text-text-faint">Payment</h2>
          <button
            type="button"
            onClick={() => {
              mountedRef.current = false;
              onStartOver();
            }}
            className="text-xs text-accent hover:underline"
          >
            Start over
          </button>
        </div>

        <p className="mt-3 text-sm text-text-muted">
          Demo wallet balance:{" "}
          <span className="font-mono text-text">{formatAmount(session.walletBalance)}</span>. This
          project&apos;s dominant fraud signal is a <em>narrow</em> band right at{" "}
          <code className="font-mono">amount == balance</code> (the same PaySim account-draining
          pattern documented on Overview) — a few percent off in either direction and the
          signal collapses. Enter the exact balance above to give the model a real (not
          guaranteed — it also depends on the current time of day, a genuine model
          characteristic, not a demo bug) chance of blocking it; any other amount is treated as
          ordinary.
        </p>

        <p className="mt-2 font-mono text-sm text-text">Paying {formatAmount(session.amount)}</p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <PaymentElement />
          <button
            type="submit"
            disabled={!stripe || submitting}
            className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Confirming…" : `Pay ${formatAmount(session.amount)}`}
          </button>
        </form>

        <div className="mt-4 rounded-md border border-border bg-surface-2 p-3 text-xs text-text-faint">
          <p className="font-mono uppercase tracking-wide text-text-muted">Stripe test cards</p>
          <p className="mt-1">
            <span className="font-mono text-text">4242 4242 4242 4242</span> — guaranteed success.{" "}
            <span className="font-mono text-text">4000 0000 0000 0002</span> — guaranteed decline
            (Stripe&apos;s own generic decline — not this project&apos;s fraud model). Any future
            expiry date, any 3-digit CVC, any postal code.
          </p>
        </div>
      </Card>

      <OutcomeCard
        outcome={outcome}
        matched={matched}
        predictionsError={predictionsQuery.isError ? describeApiError(predictionsQuery.error) : null}
      />
    </div>
  );
}

function OutcomeCard({
  outcome,
  matched,
  predictionsError,
}: {
  outcome: ConfirmOutcome;
  matched: PredictionListItem | undefined;
  predictionsError: string | null;
}) {
  if (outcome?.kind === "declined") {
    return (
      <Card>
        <p className="text-sm text-text">Card declined by Stripe</p>
        <p className="mt-2 text-sm text-text-muted">
          {outcome.message} This is Stripe&apos;s own test-mode card decline — not a decision made
          by this project&apos;s fraud model.
        </p>
      </Card>
    );
  }

  if (outcome?.kind === "blocked") {
    return (
      <Card>
        <div className="flex items-center gap-3">
          <RiskBadge variant="fraud">blocked</RiskBadge>
          <p className="text-sm text-text">Stripe refused to confirm this payment</p>
        </div>
        <p className="mt-2 text-sm text-text-muted">
          The fraud model flagged this PaymentIntent and called{" "}
          <code className="font-mono">stripe.PaymentIntent.cancel</code> (via{" "}
          <code className="font-mono">POST /webhooks/stripe</code>) before you finished checking
          out — confirmation failed because the PaymentIntent was already canceled, not because
          Stripe rejected the card itself.
        </p>
        {matched ? <ScoreDetails item={matched} /> : <WaitingNote />}
      </Card>
    );
  }

  if (outcome?.kind === "succeeded") {
    if (!matched) {
      return (
        <Card>
          <p className="text-sm text-text">Payment succeeded on Stripe</p>
          <p className="mt-2 text-sm text-text-muted">
            Stripe confirmed the payment. This project&apos;s fraud check runs asynchronously
            (via the webhook) and may not have landed yet.
          </p>
          <WaitingNote />
          {predictionsError ? <p className="mt-2 text-xs text-risk-fraud">{predictionsError}</p> : null}
        </Card>
      );
    }

    return (
      <Card>
        <div className="flex items-center gap-3">
          <RiskBadge variant={matched.is_fraud ? "fraud" : "legit"}>
            {matched.is_fraud ? "flagged after the fact" : "approved"}
          </RiskBadge>
          <p className="text-sm text-text">
            {matched.is_fraud
              ? "The model flagged this payment, but the block didn't land in time"
              : "The model let this payment through"}
          </p>
        </div>
        <ScoreDetails item={matched} />
        {matched.is_fraud ? (
          <p className="mt-3 text-xs text-text-faint">
            This is an honest characteristic of gating via an asynchronous webhook, not a bug: the{" "}
            <code className="font-mono">payment_intent.created</code> webhook hadn&apos;t landed
            (and canceled the PaymentIntent) by the time the client-side confirm call reached
            Stripe, so the payment finished before this system&apos;s cancel call could ever be
            sent. A production system this async would typically hold funds uncaptured until the
            check completes, rather than confirming immediately — out of scope for this demo.
          </p>
        ) : null}
      </Card>
    );
  }

  // No confirm attempt yet -- the webhook can still have already scored
  // this PaymentIntent (it fires at *creation* time, not at confirm time),
  // so show that result the moment it's known instead of waiting for Pay.
  return (
    <Card>
      {matched ? (
        <>
          <div className="flex items-center gap-3">
            <RiskBadge variant={matched.is_fraud ? "fraud" : "legit"}>
              {matched.is_fraud ? "already flagged" : "looks legitimate so far"}
            </RiskBadge>
            <p className="text-sm text-text">The fraud check has already landed for this payment</p>
          </div>
          <ScoreDetails item={matched} />
          {matched.is_fraud ? (
            <p className="mt-2 text-xs text-text-faint">
              Confirming now will fail — Stripe has likely already been told to cancel this
              PaymentIntent.
            </p>
          ) : null}
        </>
      ) : (
        <>
          <p className="text-sm text-text-muted">Enter a test card above and click Pay when ready.</p>
          <WaitingNote />
        </>
      )}
      {predictionsError ? <p className="mt-2 text-xs text-risk-fraud">{predictionsError}</p> : null}
    </Card>
  );
}

function WaitingNote() {
  return (
    <p className="mt-2 flex items-center gap-2 text-xs text-text-faint">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      Waiting for the fraud check to land — <code className="font-mono">POST /webhooks/stripe</code>{" "}
      runs asynchronously; this page polls <code className="font-mono">GET /predictions</code> every{" "}
      {POLL_INTERVAL_MS / 1000}s, same as the rest of this dashboard.
    </p>
  );
}

function ScoreDetails({ item }: { item: PredictionListItem }) {
  const tier = getFraudTier(item.fraud_probability, item.threshold_used);
  return (
    <dl className="mt-3 space-y-1.5 text-xs">
      <div className="flex items-center justify-between">
        <dt className="text-text-muted">Fraud probability</dt>
        <dd className="font-mono text-text">{formatProbability(item.fraud_probability)}</dd>
      </div>
      <div className="flex items-center justify-between">
        <dt className="text-text-muted">Risk tier</dt>
        <dd>
          <RiskBadge variant={tier}>{tier}</RiskBadge>
        </dd>
      </div>
      <div className="flex items-center justify-between">
        <dt className="text-text-muted">Anomaly flag</dt>
        <dd className="font-mono text-text">{item.anomaly_flag ? "flagged" : "not flagged"}</dd>
      </div>
    </dl>
  );
}
