# API Reference

This is the endpoint reference for the FastAPI backend. I pulled every request/response shape
directly from `backend/app/schemas/` and the route definitions themselves, not from memory, so
this should match the live API exactly. For the interactive version (try requests directly in the
browser), see the live [Swagger UI](https://fraud-detection-api-blkr.onrender.com/docs) or
[ReDoc](https://fraud-detection-api-blkr.onrender.com/redoc). The raw OpenAPI schema is at
[`/openapi.json`](https://fraud-detection-api-blkr.onrender.com/openapi.json).

**Auth:** none, on any endpoint, by design. This is a public portfolio demo with no user accounts
and no real money behind it, so I didn't add an authentication layer. Per-IP rate limiting (noted
per endpoint below) is the only protection layer, and it's explicitly demo-scale, not a
production-grade defense (see `SECURITY_AUDIT.md` for the full reasoning).

**Base URL:** `https://fraud-detection-api-blkr.onrender.com` in production, `http://localhost:8000`
for local dev.

---

## `GET /health`

Reports whether the ML layer has finished loading and whether the database is reachable, as two
independent booleans rather than one combined status.

**Request:** none.

**Response:**

```json
{
  "status": "ok",
  "model_loaded": true,
  "db_connected": true
}
```

`model_loaded` is `true` only when the XGBoost model, the SHAP explainer, and the Isolation Forest
model are all present in application state. `db_connected` is a real `SELECT 1` round trip against
the configured database, not just a check that the engine object exists.

**Notes:** no rate limit. Polled by the frontend's sidebar status pill.

---

## `POST /predict`

Scores a single transaction for fraud in real time and persists the result.

**Request body** (`TransactionInput`):

| field | type | constraints | notes |
|---|---|---|---|
| `step` | int | `>= 0` | Hours since simulation start (PaySim's time unit) |
| `type` | string | one of `CASH_IN`, `CASH_OUT`, `DEBIT`, `PAYMENT`, `TRANSFER` | |
| `amount` | float | `>= 0` | |
| `oldbalanceOrg` | float | `>= 0` | Originating account balance before this transaction |
| `oldbalanceDest` | float | `>= 0` | Destination account balance before this transaction |
| `nameDest` | string | length 1 to 255 | Destination account id. PaySim merchant accounts start with `M`; this is how `is_merchant_dest` gets derived |

I deliberately left `newbalanceOrig`/`newbalanceDest` off this schema. Those are post-transaction
state that doesn't exist yet at real-time decision time, so accepting them would invite the exact
leakage this project's feature schema rules out. Unrecognized extra fields are silently ignored
rather than rejected, so a client forwarding a fuller upstream object won't get a spurious 422.

**Response body** (`PredictionResponse`):

```json
{
  "fraud_probability": 0.9939,
  "is_fraud": true,
  "threshold_used": 0.6144940853118896,
  "anomaly_flag": false,
  "anomaly_score": 0.42,
  "shap_explanation": [
    { "feature": "amount_to_balance_ratio", "shap_value": 5.21 }
  ],
  "model_version": "1.0.0"
}
```

`shap_explanation` is the top 5 features by `|shap_value|`, in the model's log-odds output space
(positive pushes toward fraud, negative toward legitimate), not the full feature vector.
`anomaly_flag`/`anomaly_score` come from Isolation Forest and are a separate, advisory-only signal.
I never blend them into `fraud_probability`/`is_fraud`; in evaluation, Isolation Forest added zero
unique fraud catches beyond XGBoost on this dataset, so treat it as a secondary flag, not a second
vote.

**Notes:**
- Rate limited to 20 requests/minute per IP by default (`PREDICT_RATE_LIMIT`), with a `Retry-After`
  header on a 429.
- Returns **503** if the ML layer hasn't finished loading yet (check `/health`).
- Returns **422** for invalid/missing/out-of-range fields, before any scoring happens.
- Every scored transaction is persisted as one `transactions` row and one linked `predictions` row,
  synchronously, in the request path. If persistence itself fails, the endpoint still returns the
  already-computed prediction rather than turning a working ML result into a 500 over an unrelated
  storage problem.

---

## `GET /predictions`

Returns a paginated, filterable list of past predictions, newest first.

**Query parameters:**

| param | type | default | notes |
|---|---|---|---|
| `limit` | int | 50 | capped at 200 server-side regardless of what's requested |
| `offset` | int | 0 | |
| `is_fraud` | bool | unset | optional filter |
| `anomaly_flag` | bool | unset | optional filter |
| `source` | string (max 64 chars) | unset | e.g. `paysim_sim` or `stripe_test` |

**Response body** (`PredictionListResponse`):

```json
{
  "items": [
    {
      "id": "b3f1...",
      "created_at": "2026-09-06T18:35:43Z",
      "amount": 181000.0,
      "type": "CASH_OUT",
      "oldbalanceOrg": 181000.0,
      "oldbalanceDest": 0.0,
      "is_merchant_dest": false,
      "source": "paysim_sim",
      "fraud_probability": 0.9939,
      "is_fraud": true,
      "anomaly_flag": false,
      "anomaly_score": 0.42,
      "threshold_used": 0.6144940853118896,
      "model_version": "1.0.0"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 3869
}
```

`total` is a real `COUNT(*)` over the filtered query, not the unfiltered table, so it reflects
whatever filters are active. Each item omits `shap_explanation`. A list view renders many rows at
once and doesn't need a per-row explanation, so I left it out to keep the payload small (use the
detail endpoint below for that).

**Notes:** rate limited to 60 requests/minute per IP. No ML state is touched, so there's no 503
case here.

---

## `GET /predictions/{id}`

Returns the full detail for one prediction, including the complete SHAP explanation.

**Path parameter:** `id` (UUID).

**Response body** (`PredictionDetail`): the same shape as one `GET /predictions` list item, plus:

```json
"shap_explanation": [
  { "feature": "amount_to_balance_ratio", "shap_value": 5.21 },
  { "feature": "is_merchant_dest", "shap_value": -1.87 },
  { "feature": "type_TRANSFER", "shap_value": 0.94 }
]
```

Unlike `POST /predict`'s response, this isn't capped at 5. It's the full ranked feature vector (12
entries for the current model), since a single-item detail view can afford to show the whole thing.

**Notes:** rate limited to 60 requests/minute per IP (shared with `GET /predictions`). Returns
**404** if no prediction exists with that id.

---

## `POST /simulator/start`

Starts the background transaction generator, which continuously builds synthetic transactions and
scores them through the same pipeline as `POST /predict`.

**Request body** (`SimulatorStartRequest`):

| field | type | constraints | default |
|---|---|---|---|
| `rate_per_second` | float | `> 0`, `<= 20` | 1.0 |
| `scenario_weights.legit` | float | `>= 0` | 0.85 |
| `scenario_weights.fraud` | float | `>= 0` | 0.10 |
| `scenario_weights.velocity` | float | `>= 0` | 0.05 |

The weights don't need to already sum to 1; they're normalized automatically. At least one has to
be positive. The rate cap of 20/second is a demo-scale safety limit I set myself, not a measured
platform limit.

**Response body** (`SimulatorStatus`, see below).

**Notes:**
- Rate limited to 10 requests/minute per IP.
- Returns **503** if the ML layer hasn't finished loading yet.
- Returns **409** if the simulator is already running. It's rejected, not auto-restarted, so a
  config change always means an explicit stop first.
- Returns **422** for an out-of-range rate or an all-zero weight set.

---

## `POST /simulator/stop`

Stops the simulator if it's running.

**Request:** none.

**Response body:** `SimulatorStatus`.

**Notes:** rate limited to 10 requests/minute per IP. Idempotent: stopping an already-stopped
simulator is a no-op that returns the current status, not an error.

---

## `GET /simulator/status`

Returns the simulator's current state.

**Request:** none.

**Response body** (`SimulatorStatus`):

```json
{
  "running": true,
  "rate_per_second": 5.0,
  "scenario_weights": { "legit": 0.85, "fraud": 0.1, "velocity": 0.05 },
  "transactions_generated": 142,
  "started_at": "2026-09-06T18:30:00Z",
  "uptime_seconds": 71.4
}
```

`transactions_generated` and `uptime_seconds` reset to 0 on each new `start()` call; they count
this run only, not an all-time total.

**Notes:** no rate limit. The frontend's Simulator page polls this endpoint every 7 seconds, so I
left it unbounded rather than risk the app rate-limiting itself.

---

## `POST /webhooks/stripe`

Receives Stripe webhook events and, for a `payment_intent.created` event, scores the underlying
payment in real time and cancels it if the model flags it as fraud. This is the endpoint Stripe
itself calls, not something a browser or a typical API client would call directly.

**Request:** a raw Stripe event payload, with a `Stripe-Signature` header. Signature verification
against `STRIPE_WEBHOOK_SECRET` is mandatory; I never trust the payload before that check passes.

**Response body** varies by branch:

```json
// payment_intent.created, scored normally
{
  "status": "scored",
  "payment_intent_id": "pi_...",
  "fraud_probability": 0.041,
  "is_fraud": false,
  "action_taken": "allowed"
}
```

```json
// any other event type
{ "status": "ignored", "event_type": "payment_intent.succeeded" }
```

**Notes:**
- No rate limit. Stripe has its own retry semantics for webhook delivery, and a rate limit here
  would just make Stripe re-deliver events it thinks failed.
- Returns **400** if the signature is missing or invalid, or if `STRIPE_WEBHOOK_SECRET` isn't
  configured at all. Nothing is scored or persisted in that case.
- Returns **200**, not 503, if the ML layer isn't ready. That's a deliberate divergence from
  `POST /predict`: Stripe interprets any non-2xx response as "retry for hours," and retry-storming
  a webhook against a down ML layer wouldn't help it come back any sooner. The outage is still
  logged loudly on the backend.
- On a fraud decision, this calls the real `stripe.PaymentIntent.cancel` API (test mode, sandboxed,
  no real money moves), which prevents that PaymentIntent from ever being confirmed. Persisted rows
  from this path are tagged `source: "stripe_test"`, distinct from the simulator's/`/predict`'s
  `"paysim_sim"`.

---

## `POST /create-payment-intent`

Creates a real (test-mode) Stripe PaymentIntent for the checkout demo page, so the frontend can
mount Stripe Elements. This endpoint doesn't score anything itself; scoring happens asynchronously
once Stripe fires the resulting `payment_intent.created` event back to `POST /webhooks/stripe`.

**Request body** (`CreatePaymentIntentRequest`):

| field | type | constraints | notes |
|---|---|---|---|
| `amount` | float | `> 0`, `<= 100,000,000` | whole dollars, not cents |

**Response body** (`CreatePaymentIntentResponse`):

```json
{
  "client_secret": "pi_..._secret_...",
  "payment_intent_id": "pi_...",
  "wallet_balance": 1000000.0
}
```

`wallet_balance` is the demo customer's seeded synthetic wallet balance, surfaced so the checkout
page can explain, with the real number, why a given amount does or doesn't resemble PaySim's
draining-pattern fraud signature (`amount` close to `oldbalanceOrg`).

**Notes:**
- Rate limited to 10 requests/minute per IP.
- Returns **503** if Stripe isn't configured (`STRIPE_SECRET_KEY` unset).
- Returns **422** for a non-positive or absurdly large amount.
