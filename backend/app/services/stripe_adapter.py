"""Maps a Stripe (test-mode) PaymentIntent onto this project's real-time
fraud-model input schema (`app.schemas.prediction.TransactionInput`).

**Read this before touching anything below.** Stripe has no concept of
`oldbalanceOrg`, `oldbalanceDest`, or a PaySim-style `type` enum -- those are
PaySim simulator fields, and a Stripe PaymentIntent simply doesn't carry
equivalent data. This module is a **documented simplification layer**, not a
real field mapping: every value below that isn't taken directly off the
PaymentIntent (amount, created timestamp, id) is a synthetic stand-in,
invented here specifically so a real Stripe payment can be run through a
model that was trained on PaySim's schema. None of these stand-ins should
ever be read later as "Stripe actually provides this" -- it does not.

Concretely, per field:

- **`oldbalanceOrg` (the originating balance)** -- Stripe has no per-customer
  running balance concept for a card payment (the money moves from the
  customer's card issuer to the platform's Stripe balance directly). This
  adapter simulates one: a synthetic "wallet balance" stored in a Stripe
  **test-mode Customer's `metadata`** (see `get_or_create_demo_customer`
  below), seeded once at customer creation. It is a demo fiction that lives
  entirely in this project's own metadata usage of a real Stripe API object,
  not anything Stripe tracks natively.
- **`oldbalanceDest` (the destination balance)** -- there's no real
  destination *account* in a simple Stripe checkout flow; the money simply
  becomes platform revenue. Fixed at `SYNTHETIC_DEST_BALANCE` (see constant
  below) rather than 0.0, specifically because PaySim's own fraud signature
  is an *empty* destination balance (a fresh drop account) -- defaulting to
  0.0 here would make every real Stripe payment resemble that fraud pattern
  for a reason that has nothing to do with actual risk. A large, already-
  funded balance is the honest stand-in for "money is flowing to an
  established platform account," which is what's actually happening.
- **`type`** -- fixed at `FIXED_TRANSACTION_TYPE = TransactionType.TRANSFER`.
  A card payment isn't a literal PaySim transaction type; TRANSFER is chosen
  deliberately over PAYMENT for a specific, checkable reason: PaySim's
  `type_PAYMENT` and `is_merchant_dest` are *perfectly* collinear in the
  training data (every PAYMENT goes to a merchant account and vice versa --
  see CLAUDE.md's Known Limitations). Since this adapter also sets
  `is_merchant_dest`-equivalent to False (see below), pairing that with
  PAYMENT would hand the model a (type=PAYMENT, is_merchant_dest=False)
  combination that never occurs anywhere in training -- an even further
  off-distribution input than necessary. TRANSFER-to-a-personal-account does
  occur in PaySim's real data, so this pairing is at least a combination the
  model has actually seen.
- **`is_merchant_dest`** -- not a raw field on `TransactionInput`; it's
  derived downstream (`ml/src/preprocessing.py`) from whether `nameDest`
  starts with `"M"`. This adapter always emits a `"C"`-prefixed synthetic
  `nameDest`, i.e. `is_merchant_dest` resolves to **False** -- chosen (not
  defaulted) for the same collinearity reason as `type` above: PaySim's
  merchant-destined rows are exclusively PAYMENT-type, so a merchant
  destination on a TRANSFER would be a combination this model never trained
  on. "Money leaving a customer's wallet toward the platform" is modeled as
  a personal-account-style transfer, not a merchant payment.
- **`amount`** -- Stripe amounts are integers in the currency's smallest unit
  (cents, for USD), so `amount / 100.0` converts to the same dollar-unit
  convention every other input to this model uses (PaySim's `amount` column
  is already in whole currency units). This adapter assumes USD and does not
  handle multi-currency PaymentIntents.
- **`step`** -- PaySim's `step` is an hours-since-simulation-start counter
  with no real-world calendar meaning (0-743 across a synthetic 31-day
  simulation). A live Stripe payment has no simulation clock to measure
  against, so this adapter derives an hours-since-a-fixed-epoch value from
  the PaymentIntent's real `created` (Unix timestamp) instead -- this keeps
  `hour_of_day`/`day_of_week` (derived from `step` in
  `ml/src/preprocessing.py`) meaningful against real wall-clock time, rather
  than emitting a meaningless constant.

**Wallet-balance persistence is intentionally partial.** This adapter seeds a
wallet balance at customer creation and reads it back before scoring, but
does not debit it after a transaction is scored -- updating the stored
balance to reflect a scored payment (so a customer's synthetic balance
actually drains over repeated payments) is out of scope for this pass and
would belong to a future webhook-endpoint phase, not this adapter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe

from app.core.config import settings
from app.schemas.prediction import TransactionInput, TransactionType

# Metadata key used on the (test-mode) Stripe Customer object to stash the
# synthetic wallet balance this adapter treats as oldbalanceOrg. Stripe
# metadata values are always strings, so this is stored/parsed as one.
WALLET_BALANCE_METADATA_KEY = "wallet_balance"

# Arbitrary but reasonable round starting balance for a freshly-created demo
# customer -- not derived from any real Stripe or PaySim statistic, just a
# plausible order-of-magnitude wallet balance for a demo account.
DEFAULT_WALLET_SEED_BALANCE = 50_000.0

# Fixed synthetic oldbalanceDest -- see module docstring for why this is a
# large established-balance stand-in rather than 0.0.
SYNTHETIC_DEST_BALANCE = 500_000.0

# Fixed synthetic type -- see module docstring for the collinearity reasoning.
FIXED_TRANSACTION_TYPE = TransactionType.TRANSFER

# Reference epoch for deriving a synthetic `step` from a PaymentIntent's real
# `created` timestamp (see module docstring). Arbitrary fixed point in time --
# only the resulting hour_of_day/day_of_week derived from it need to be
# realistic, not the absolute step count itself.
_STEP_EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _derive_step(created_unix: int) -> int:
    """Hours since _STEP_EPOCH, floored at 0. Stands in for PaySim's `step`
    using real wall-clock time instead of a simulation counter -- see module
    docstring."""
    created = datetime.fromtimestamp(created_unix, tz=timezone.utc)
    hours_elapsed = int((created - _STEP_EPOCH).total_seconds() // 3600)
    return max(hours_elapsed, 0)


def get_or_create_demo_customer(
    customer_id: str | None = None,
    *,
    seed_balance: float = DEFAULT_WALLET_SEED_BALANCE,
) -> stripe.Customer:
    """Real (test-mode) Stripe API call -- not a mock. Fetches the given
    customer, seeding `WALLET_BALANCE_METADATA_KEY` into its metadata if it's
    missing one, or creates a brand-new demo customer with a seeded balance
    if no id is given.

    This is the one function in this module that talks to Stripe over the
    network; `map_payment_intent_to_transaction_input` below is a pure
    function precisely so it can be tested (and reasoned about) without a
    live API call.
    """
    stripe.api_key = settings.stripe_secret_key

    if customer_id:
        customer = stripe.Customer.retrieve(customer_id)
        if WALLET_BALANCE_METADATA_KEY not in customer.metadata:
            customer = stripe.Customer.modify(
                customer_id,
                metadata={WALLET_BALANCE_METADATA_KEY: str(seed_balance)},
            )
        return customer

    return stripe.Customer.create(
        description="fraud-detection demo customer (synthetic wallet balance in metadata)",
        metadata={WALLET_BALANCE_METADATA_KEY: str(seed_balance)},
    )


def extract_wallet_balance(customer: Any) -> float:
    """Reads the synthetic wallet balance off a Stripe Customer's metadata
    (or an equivalent plain dict, e.g. from a fabricated test payload).
    Raises loudly rather than silently defaulting -- a customer with no
    seeded balance is a setup bug (`get_or_create_demo_customer` should have
    been called first), not a case to paper over with a made-up number.

    Deliberately uses only `in`/`[]` (never `.get()`) throughout, and takes
    `customer: Any` rather than `Mapping` -- a real `stripe.Customer` (and
    its nested `.metadata`) is emphatically **not** a `dict`/`Mapping` in
    this SDK version (confirmed directly: it raises `AttributeError` on
    `.get()` with "use .to_dict() to convert it"), even though it supports
    `[]`/`in` via its own `__getitem__`/`__contains__`. A plain fabricated
    dict (this module's test suite) supports both styles, so restricting
    this function to the subset both types actually share is what makes it
    work against a real Stripe object and a test fixture alike.
    """
    metadata = customer["metadata"]
    if WALLET_BALANCE_METADATA_KEY not in metadata:
        customer_id = customer["id"] if "id" in customer else "<unknown>"
        raise ValueError(
            f"Stripe customer {customer_id} has no '{WALLET_BALANCE_METADATA_KEY}' "
            "metadata -- call get_or_create_demo_customer() to seed one first."
        )
    return float(metadata[WALLET_BALANCE_METADATA_KEY])


def map_payment_intent_to_transaction_input(
    payment_intent: Any,
    wallet_balance_before: float,
) -> TransactionInput:
    """The actual Stripe -> model-input mapping. Pure and network-free: takes
    the synthetic wallet balance as an explicit argument rather than fetching
    it itself, so this function (and therefore the adapter's core logic) is
    fully testable against a fabricated PaymentIntent-shaped dict with no
    Stripe API access required.

    `payment_intent` only needs to support `["amount"]`, `["created"]`, and
    `["id"]` (a real `stripe.PaymentIntent` supports this via its dict-like
    interface, and so does a plain dict) -- see the module docstring for what
    every output field actually means and why.
    """
    amount_dollars = payment_intent["amount"] / 100.0  # Stripe amounts are integer cents
    step = _derive_step(payment_intent["created"])

    # "C"-prefixed synthetic destination id -- see module docstring
    # (is_merchant_dest) for why this is deliberately personal-account-shaped,
    # not merchant-shaped. Derived from the PaymentIntent id so it's stable
    # and traceable back to the originating payment, not random.
    name_dest = f"C{payment_intent['id']}"

    return TransactionInput(
        step=step,
        type=FIXED_TRANSACTION_TYPE,
        amount=amount_dollars,
        oldbalanceOrg=wallet_balance_before,
        oldbalanceDest=SYNTHETIC_DEST_BALANCE,
        nameDest=name_dest,
    )


def build_transaction_input_for_payment_intent(payment_intent: Any) -> TransactionInput:
    """Convenience entrypoint for real usage: resolves the wallet balance
    (from an already-expanded `customer` field on the PaymentIntent, or by
    calling the real Stripe API if `customer` is just an id string, or by
    creating a brand-new demo customer if there's no customer at all -- the
    common case for a real trigger/test PaymentIntent, confirmed live: see
    CLAUDE.md's Phase 9 part 2 verification) and then delegates to the pure
    mapping function above.

    Branches on `isinstance(customer_field, str)` / `is None` only -- never
    on `isinstance(customer_field, Mapping)` -- because a real, already-
    expanded `stripe.Customer` object does not satisfy `Mapping` in this SDK
    version (confirmed directly against the installed stripe package: it
    isn't a dict subclass and isn't registered as a Mapping), even though it
    supports `[]`/`in`. Anything that's neither `None` nor a plain id string
    is treated as an already-expanded customer object as-is (dict or real
    StripeObject both work, since extract_wallet_balance only ever uses
    `[]`/`in` on it).
    """
    customer_field = payment_intent["customer"] if "customer" in payment_intent else None

    if customer_field is None:
        customer: Any = get_or_create_demo_customer(None)
    elif isinstance(customer_field, str):
        customer = get_or_create_demo_customer(customer_field)
    else:
        customer = customer_field

    wallet_balance_before = extract_wallet_balance(customer)
    return map_payment_intent_to_transaction_input(payment_intent, wallet_balance_before)
