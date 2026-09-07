/**
 * Typed client for the FastAPI backend. Every shape here mirrors a specific
 * backend source of truth -- kept in sync by hand, not generated -- so a
 * schema change on the backend should be cross-checked against this file:
 *
 *   - TransactionInput / TransactionType -> backend/app/schemas/prediction.py
 *   - ShapContribution / PredictionResponse -> backend/app/schemas/prediction.py
 *   - PredictionListItem / PredictionDetail / PredictionListResponse
 *       -> backend/app/schemas/prediction.py + backend/app/api/predictions.py
 *   - HealthResponse -> backend/app/api/health.py
 *   - ScenarioWeights / SimulatorStartRequest / SimulatorStatus
 *       -> backend/app/schemas/simulator.py + backend/app/api/simulator.py
 *   - CreatePaymentIntentResponse
 *       -> backend/app/schemas/stripe_checkout.py + backend/app/api/stripe_checkout.py
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TransactionType = "CASH_IN" | "CASH_OUT" | "DEBIT" | "PAYMENT" | "TRANSFER";

/** Raw pre-transaction fields POST /predict accepts -- see TransactionInput
 * in backend/app/schemas/prediction.py. No newbalanceOrig/newbalanceDest:
 * those are post-transaction state the backend never accepts, on purpose
 * (see CLAUDE.md, "Feature Schema" -- Excluded, leakage). */
export interface TransactionInput {
  step: number;
  type: TransactionType;
  amount: number;
  oldbalanceOrg: number;
  oldbalanceDest: number;
  nameDest: string;
}

export interface ShapContribution {
  feature: string;
  shap_value: number;
}

/** POST /predict response. shap_explanation is capped at 5 entries
 * server-side -- see PredictionDetail below for the uncapped version. */
export interface PredictionResponse {
  fraud_probability: number;
  is_fraud: boolean;
  threshold_used: number;
  anomaly_flag: boolean;
  anomaly_score: number;
  shap_explanation: ShapContribution[];
  model_version: string;
}

/** One row of GET /predictions -- a Prediction joined with its Transaction.
 * No shap_explanation here by design (see backend/app/schemas/prediction.py's
 * PredictionListItem docstring) -- that's detail-only. */
export interface PredictionListItem {
  id: string;
  created_at: string;
  amount: number;
  type: TransactionType;
  oldbalanceOrg: number;
  oldbalanceDest: number;
  is_merchant_dest: boolean;
  /** "paysim_sim" (simulator / POST /predict / Test a Transaction) or
   * "stripe_test" (the checkout demo, via POST /webhooks/stripe). */
  source: string;
  fraud_probability: number;
  is_fraud: boolean;
  anomaly_flag: boolean;
  anomaly_score: number;
  threshold_used: number;
  model_version: string;
}

/** GET /predictions/{id} -- same joined shape, plus the full (uncapped)
 * ranked SHAP list. */
export interface PredictionDetail extends PredictionListItem {
  shap_explanation: ShapContribution[];
}

export interface PredictionListResponse {
  items: PredictionListItem[];
  limit: number;
  offset: number;
  total: number;
}

export interface PredictionListParams {
  limit?: number;
  offset?: number;
  is_fraud?: boolean;
  anomaly_flag?: boolean;
  source?: string;
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  db_connected: boolean;
}

/** Relative weights, not required to already sum to 1 -- the backend
 * normalizes whatever's given (see app/services/simulator.py's scenario
 * picker). `velocity` is a UI/demo illustration of a rapid-succession
 * burst, not a claim the model detects velocity patterns -- see the note
 * next to its control on the Simulator page. */
export interface ScenarioWeights {
  legit: number;
  fraud: number;
  velocity: number;
}

export interface SimulatorStartRequest {
  rate_per_second: number;
  scenario_weights?: ScenarioWeights;
}

export interface SimulatorStatus {
  running: boolean;
  rate_per_second: number | null;
  scenario_weights: ScenarioWeights | null;
  transactions_generated: number;
  started_at: string | null;
  uptime_seconds: number | null;
}

/** POST /create-payment-intent response -- see
 * backend/app/schemas/stripe_checkout.py. `wallet_balance` is the checkout
 * demo's synthetic Stripe Customer wallet balance (stripe_adapter.py's
 * stand-in for oldbalanceOrg), surfaced so the page can explain, with the
 * real number, why a given amount does or doesn't look like PaySim's
 * draining-pattern fraud signature. */
export interface CreatePaymentIntentResponse {
  client_secret: string;
  payment_intent_id: string;
  wallet_balance: number;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }

  return res.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function predictTransaction(input: TransactionInput): Promise<PredictionResponse> {
  return request<PredictionResponse>("/predict", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getPredictions(params: PredictionListParams = {}): Promise<PredictionListResponse> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.is_fraud !== undefined) search.set("is_fraud", String(params.is_fraud));
  if (params.anomaly_flag !== undefined) search.set("anomaly_flag", String(params.anomaly_flag));
  if (params.source !== undefined) search.set("source", params.source);

  const query = search.toString();
  return request<PredictionListResponse>(`/predictions${query ? `?${query}` : ""}`);
}

export function getPrediction(id: string): Promise<PredictionDetail> {
  return request<PredictionDetail>(`/predictions/${id}`);
}

export function startSimulator(input: SimulatorStartRequest): Promise<SimulatorStatus> {
  return request<SimulatorStatus>("/simulator/start", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function stopSimulator(): Promise<SimulatorStatus> {
  return request<SimulatorStatus>("/simulator/stop", { method: "POST" });
}

export function getSimulatorStatus(): Promise<SimulatorStatus> {
  return request<SimulatorStatus>("/simulator/status");
}

export function createPaymentIntent(amount: number): Promise<CreatePaymentIntentResponse> {
  return request<CreatePaymentIntentResponse>("/create-payment-intent", {
    method: "POST",
    body: JSON.stringify({ amount }),
  });
}

interface FastApiValidationError {
  loc: (string | number)[];
  msg: string;
}

function isValidationErrorArray(value: unknown): value is FastApiValidationError[] {
  return (
    Array.isArray(value) &&
    value.every((entry) => entry && typeof entry === "object" && "msg" in entry && "loc" in entry)
  );
}

/** Turns an ApiError's raw response body into a message worth showing a
 * user -- FastAPI's 422s carry a `detail` array of {loc, msg} entries (one
 * per invalid field), its 503s (see api/predict.py) carry a plain `detail`
 * string. Falls back to the raw body/status for anything else rather than
 * swallowing the error. */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Couldn't reach the backend. Is uvicorn running, and does NEXT_PUBLIC_API_URL point at it?";
  }

  try {
    const body = JSON.parse(error.message) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (isValidationErrorArray(body.detail)) {
      return body.detail
        .map((entry) => {
          const field = entry.loc.filter((part) => part !== "body").join(".");
          return field ? `${field}: ${entry.msg}` : entry.msg;
        })
        .join("; ");
    }
  } catch {
    // Not JSON -- fall through to the raw body below.
  }

  return error.message || `Request failed with status ${error.status}`;
}
