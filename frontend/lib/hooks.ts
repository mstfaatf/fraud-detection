"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getHealth,
  getPrediction,
  getPredictions,
  predictTransaction,
  type PredictionListParams,
  type TransactionInput,
} from "./api";
import { POLL_INTERVAL_MS } from "./constants";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function usePredictions(params: PredictionListParams = {}) {
  return useQuery({
    queryKey: ["predictions", params],
    queryFn: () => getPredictions(params),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function usePrediction(id: string | undefined) {
  return useQuery({
    queryKey: ["prediction", id],
    queryFn: () => getPrediction(id as string),
    enabled: Boolean(id),
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
