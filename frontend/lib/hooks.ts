"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  ApiError,
  createPaymentIntent,
  getHealth,
  getPrediction,
  getPredictions,
  getSimulatorStatus,
  predictTransaction,
  startSimulator,
  stopSimulator,
  type PredictionListParams,
  type SimulatorStartRequest,
  type TransactionInput,
} from "./api";
import { POLL_INTERVAL_MS, SLOW_REQUEST_THRESHOLD_MS } from "./constants";

/** TanStack Query's default retries every failure (including a 404) up to 3
 * times with backoff -- fine for a flaky network blip, but it means a
 * genuinely-nonexistent id would sit in a loading state for several seconds
 * before ever reaching the not-found UI. A 4xx is never going to succeed on
 * retry, so only 5xx/network errors get the default retry behavior. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 3;
}

/** True once `active` (an isLoading/isPending flag) has stayed true for at
 * least SLOW_REQUEST_THRESHOLD_MS. Distinguishes ordinary brief loading from
 * a request that's probably hitting Render/Supabase's free-tier cold start
 * (backend spun down from idle, or Supabase's own pooler waking up) -- see
 * CLAUDE.md's "Free-tier cold-start mitigation" section and
 * components/ui/cold-start-notice.tsx, which this is meant to gate. */
export function useSlowLoading(active: boolean, delayMs: number = SLOW_REQUEST_THRESHOLD_MS): boolean {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), delayMs);
    return () => clearTimeout(timer);
  }, [active, delayMs]);

  return slow;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function usePredictions(params: PredictionListParams = {}) {
  return useQuery({
    queryKey: ["predictions", params],
    queryFn: () => getPredictions(params),
    refetchInterval: POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function usePrediction(id: string | undefined) {
  return useQuery({
    queryKey: ["prediction", id],
    queryFn: () => getPrediction(id as string),
    enabled: Boolean(id),
    retry: shouldRetry,
  });
}

/** Scores a transaction via POST /predict, then invalidates the
 * /predictions list/detail caches so the new row shows up on next poll
 * instead of waiting out a full POLL_INTERVAL_MS cycle. */
export function usePredictTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TransactionInput) => predictTransaction(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["predictions"] });
    },
  });
}

/** Same plain-polling approach as everywhere else in this app (no
 * WebSockets) -- see the Simulator page for why POLL_INTERVAL_MS is fine
 * here even for a "live" running/stopped indicator. */
export function useSimulatorStatus() {
  return useQuery({
    queryKey: ["simulator-status"],
    queryFn: getSimulatorStatus,
    refetchInterval: POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

/** Seeds the query cache with the response immediately (not just
 * invalidating) so the Simulator page's running/stopped state flips the
 * instant the request succeeds, rather than waiting up to POLL_INTERVAL_MS
 * for the next status poll. */
export function useStartSimulator() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SimulatorStartRequest) => startSimulator(input),
    onSuccess: (status) => {
      queryClient.setQueryData(["simulator-status"], status);
    },
  });
}

export function useStopSimulator() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => stopSimulator(),
    onSuccess: (status) => {
      queryClient.setQueryData(["simulator-status"], status);
    },
  });
}

/** Creates a real Stripe PaymentIntent server-side (POST
 * /create-payment-intent) for the checkout demo. Scoring/gating happens
 * later, asynchronously, once Stripe delivers the resulting
 * payment_intent.created webhook back to POST /webhooks/stripe -- this
 * mutation only gets the checkout page as far as having a client_secret to
 * mount Stripe Elements with. */
export function useCreatePaymentIntent() {
  return useMutation({
    mutationFn: (amount: number) => createPaymentIntent(amount),
  });
}
