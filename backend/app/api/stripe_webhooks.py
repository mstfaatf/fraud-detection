"""POST /webhooks/stripe -- scores an incoming Stripe (test-mode) PaymentIntent
in real time and takes a real gating action on it, not just a passive log.

**Listens for `payment_intent.created` specifically**, not `.succeeded` or
`.confirmed` -- scoring has to happen *before* a payment is confirmed for a
"cancel it" action to mean anything, consistent with this project's
real-time, score-before-execution philosophy (see CLAUDE.md's Feature Schema
section: "a payment is scored *before* it executes"). Every other event type
is acknowledged with a 200 and ignored -- Stripe expects a fast 2xx for
anything it sends, even events an endpoint doesn't act on; returning
non-200 for an event type this endpoint deliberately doesn't handle would
just make Stripe retry-storm it.

**Signature verification is mandatory, not optional.** `stripe.Webhook.
construct_event` verifies the `Stripe-Signature` header against
`settings.stripe_webhook_secret` using the *raw* request body (not the
parsed JSON -- signature verification is byte-exact) before this handler
trusts anything about the payload. A bad/missing signature (or a secret
that isn't configured at all) is rejected with 400 and nothing is scored or
persisted.

**The gating action -- this is the actual "so what" of this integration,**
not a passive log line: if the score clears the model's chosen threshold,
this handler calls the real (test-mode) `stripe.PaymentIntent.cancel` API,
which prevents that PaymentIntent from ever being confirmed. A payment
flagged as fraud is stopped before money moves, on a real payment rail
(sandboxed by Stripe, but a genuine API call, not a mock) -- not merely
recorded as "would have been fraud."

**ML-outage behavior deliberately diverges from POST /predict's.**
`/predict` returns 503 when the ML layer isn't loaded (see
app/api/predict.py) because an HTTP caller can reasonably retry a 503 on its
own schedule. Stripe webhooks are different: Stripe interprets any non-2xx
response as "please retry, with backoff, for hours" -- retry-storming a
webhook against an ML layer that's down doesn't make it come back up any
sooner, it just piles up duplicate, doomed delivery attempts against an
already-degraded service. So this handler logs an ML outage loudly (it's
still a real, actionable problem -- see the log line below) but returns 200
anyway, letting Stripe consider the event delivered rather than retrying it
into a queue that will never drain. This is a considered tradeoff for
Stripe's specific retry semantics, not a shortcut to hide failures.
"""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.prediction_service import predict_transaction
from app.services.stripe_adapter import build_transaction_input_for_payment_intent

router = APIRouter()

logger = logging.getLogger(__name__)

# The source value stamped on every Transaction row scored through this path
# (see the "source" column added by alembic/versions/69e4f3ee4a95_*.py) --
# distinguishes real Stripe test-mode traffic from "paysim_sim" (the
# simulator, POST /predict, Test a Transaction).
STRIPE_WEBHOOK_SOURCE = "stripe_test"

_REQUIRED_STATE_ATTRS = ("xgb_model", "model_metadata", "shap_explainer", "isolation_forest")

_HANDLED_EVENT_TYPE = "payment_intent.created"


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    if not settings.stripe_webhook_secret:
        # No configured secret means signature verification is impossible --
        # refuse to process rather than silently trusting an unverifiable
        # payload.
        raise HTTPException(status_code=400, detail="STRIPE_WEBHOOK_SECRET is not configured")

    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(raw_body, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("Rejected Stripe webhook: invalid payload/signature (%s)", exc)
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload or signature") from exc

    if event["type"] != _HANDLED_EVENT_TYPE:
        return {"status": "ignored", "event_type": event["type"]}

    payment_intent = event["data"]["object"]

    state = request.app.state
    missing = [attr for attr in _REQUIRED_STATE_ATTRS if getattr(state, attr, None) is None]
    if missing:
        # See module docstring: 200, not 503, on purpose -- Stripe's retry
        # semantics, not a shortcut. Still logged loudly since an ML outage
        # dropping real webhook events is a real, actionable problem.
        logger.error(
            "Stripe webhook for PaymentIntent %s received but ML layer not ready "
            "(missing: %s) -- dropping event, not retrying, per Stripe's retry semantics.",
            payment_intent.get("id"),
            ", ".join(missing),
        )
        return {"status": "dropped", "reason": "ml_layer_not_ready"}

    # get_or_create_demo_customer() (called inside here if `customer` isn't
    # already expanded on the PaymentIntent) needs a configured API key to
    # talk to Stripe's test-mode API for the wallet-balance lookup/seed.
    stripe.api_key = settings.stripe_secret_key

    transaction_input = build_transaction_input_for_payment_intent(payment_intent)

    response = predict_transaction(
        transaction_input,
        xgb_model=state.xgb_model,
        model_metadata=state.model_metadata,
        explainer=state.shap_explainer,
        isolation_forest=state.isolation_forest,
        db=db,
        source=STRIPE_WEBHOOK_SOURCE,
    )

    # --- The actual gating decision: this is the point where the model's ---
    # --- output changes what Stripe does, not just a passive log record. ---
    action_taken = "allowed"
    if response.is_fraud:
        stripe.PaymentIntent.cancel(payment_intent["id"])
        action_taken = "cancelled"
        logger.warning(
            "Cancelled Stripe PaymentIntent %s -- fraud_probability=%.4f >= threshold %.4f",
            payment_intent["id"],
            response.fraud_probability,
            response.threshold_used,
        )

    return {
        "status": "scored",
        "payment_intent_id": payment_intent["id"],
        "fraud_probability": response.fraud_probability,
        "is_fraud": response.is_fraud,
        "action_taken": action_taken,
    }
