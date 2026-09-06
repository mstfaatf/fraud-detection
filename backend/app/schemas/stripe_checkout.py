"""Request/response schemas for POST /create-payment-intent -- the one
endpoint the checkout demo (frontend/app/checkout/page.tsx) needs before it
can mount Stripe Elements. Kept separate from schemas/prediction.py: this is
about creating a real Stripe object, not about the fraud model's input/output
shape (see schemas/simulator.py for the same per-feature schema-file
convention).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreatePaymentIntentRequest(BaseModel):
    # Whole currency units (dollars), not cents -- converted to Stripe's
    # integer-cents convention inside the endpoint, matching
    # stripe_adapter.py's own cents<->dollars convention (just inverted).
    amount: float = Field(gt=0, description="Demo payment amount in whole dollars.")


class CreatePaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    # The demo customer's seeded synthetic wallet balance (see
    # stripe_adapter.py's WALLET_BALANCE_METADATA_KEY) -- surfaced so the
    # checkout page can explain, with the real number, why a given amount
    # does or doesn't resemble PaySim's draining-pattern fraud signature
    # (amount ~= oldbalanceOrg), instead of hardcoding that number twice.
    wallet_balance: float
