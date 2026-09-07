"""POST /create-payment-intent -- server-side half of the checkout demo
(frontend/app/checkout/page.tsx). Stripe Elements (PaymentElement) needs a
`client_secret` to mount, and only the Stripe API can mint one for a real
PaymentIntent -- the frontend cannot create a PaymentIntent on its own (that
would require the secret key, which never belongs in a browser). This
endpoint is the only thing standing between the checkout page and that
requirement; it does not score anything itself -- scoring happens
asynchronously afterward, in app/api/stripe_webhooks.py, once Stripe fires
the resulting `payment_intent.created` event back to this app.

Kept in its own module rather than stripe_webhooks.py: that module is
specifically the webhook *receiver*; this is an ordinary REST endpoint the
frontend calls directly, a different enough concern to warrant its own file.

Reuses a fresh demo customer (app.services.stripe_adapter.
get_or_create_demo_customer) per checkout attempt, exactly the same helper
Phase 9 part 1/2 already built and tested -- not a new customer-management
scheme. Attaching that customer to the created PaymentIntent means the
webhook's real usage path (build_transaction_input_for_payment_intent) reads
back the *same* seeded wallet_balance this endpoint already fetched, rather
than falling through to its own `customer is None` branch and creating a
second, different demo customer for the same checkout attempt.
"""

from __future__ import annotations

import stripe
from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.stripe_checkout import CreatePaymentIntentRequest, CreatePaymentIntentResponse
from app.services.stripe_adapter import extract_wallet_balance, get_or_create_demo_customer

router = APIRouter()

# Each call makes a real Stripe API call (creating a real Customer/
# PaymentIntent object, even in test mode) and, once the resulting
# `payment_intent.created` webhook lands, a real DB write -- unauthenticated
# and public, so a security review flagged this as needing the same kind of
# bound /predict already has (see SECURITY_AUDIT.md). 10/minute is generous
# for a human clicking through the checkout demo, tight enough to bound an
# automated spam loop against this project's own Stripe test-mode account.
_CREATE_PAYMENT_INTENT_RATE_LIMIT = "10/minute"

# Overrides stripe_adapter.DEFAULT_WALLET_SEED_BALANCE ($50,000) for this one
# call site only. Measured live (see CLAUDE.md's Phase 9 part 3): the
# model's amount_to_balance_ratio signal is an extremely narrow band right
# at ratio == 1.0 (a 5-10% miss collapses fraud_probability back to near
# zero -- confirmed by sweeping ratios 0.9-1.5), and at the $50,000 scale,
# even a perfect ratio==1.0 match never once cleared the ~0.6145 threshold
# across a full simulated week of hour-of-day/day-of-week combinations
# (0/28 samples). At $1,000,000, the same exact-match case clears threshold
# in ~38% of sampled hours -- genuinely demoable (a reviewer entering the
# exact balance amount has a real, if not guaranteed, chance of seeing the
# model block it), without being an implausibly large round number.
CHECKOUT_DEMO_WALLET_SEED_BALANCE = 1_000_000.0


@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
@limiter.limit(_CREATE_PAYMENT_INTENT_RATE_LIMIT)
def create_payment_intent(
    payload: CreatePaymentIntentRequest, request: Request, response: Response
) -> CreatePaymentIntentResponse:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured (STRIPE_SECRET_KEY unset)")

    stripe.api_key = settings.stripe_secret_key

    customer = get_or_create_demo_customer(None, seed_balance=CHECKOUT_DEMO_WALLET_SEED_BALANCE)
    wallet_balance = extract_wallet_balance(customer)

    intent = stripe.PaymentIntent.create(
        amount=int(round(payload.amount * 100)),  # Stripe wants integer cents
        currency="usd",
        customer=customer["id"],
        automatic_payment_methods={"enabled": True},
        description="fraud-detection checkout demo",
    )

    return CreatePaymentIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
        wallet_balance=wallet_balance,
    )
