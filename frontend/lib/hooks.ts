"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  getHealth,
  getPrediction,
  getPredictions,
  predictTransaction,
  type PredictionListParams,
  type TransactionInput,
} from "./api";
import { POLL_INTERVAL_MS } from "./constants";

/** TanStack Query's default retries every failure (including a 404) up to 3
 * times with backoff -- fine for a flaky network blip, but it means a
 * genuinely-nonexistent id would sit in a loading state for several seconds
 * before ever reaching the not-found UI. A 4xx is never going to succeed on
 * retry, so only 5xx/network errors get the default retry behavior. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 3;
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
