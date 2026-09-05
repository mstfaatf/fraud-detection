"""Tests for app/services/stripe_adapter.py -- purely offline (no real Stripe
API calls). The central assertion: a fabricated PaymentIntent-shaped dict,
run through the adapter, must produce a payload that validates against the
real /predict input schema (TransactionInput) exactly -- this is what would
catch drift if TransactionInput's fields ever change without the adapter
being updated to match.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402

from app.schemas.prediction import TransactionInput, TransactionType  # noqa: E402
from app.services.stripe_adapter import (  # noqa: E402
    SYNTHETIC_DEST_BALANCE,
    WALLET_BALANCE_METADATA_KEY,
    build_transaction_input_for_payment_intent,
    extract_wallet_balance,
    map_payment_intent_to_transaction_input,
)

# A fabricated PaymentIntent-shaped dict -- only the fields the adapter
# actually reads (amount, created, id, customer) need to be present, same as
# a real stripe.PaymentIntent would provide via its dict-like interface.
FAKE_PAYMENT_INTENT = {
    "id": "pi_3FAKE0000000000000000000",
    "amount": 425_00,  # $425.00, in cents
    "currency": "usd",
    "created": 1_735_689_600,  # 2025-01-01T00:00:00Z
    "customer": {
        "id": "cus_FAKE00000000",
        "metadata": {WALLET_BALANCE_METADATA_KEY: "12345.67"},
    },
}


def test_map_payment_intent_returns_valid_transaction_input():
    result = map_payment_intent_to_transaction_input(
        FAKE_PAYMENT_INTENT, wallet_balance_before=12345.67
    )

    assert isinstance(result, TransactionInput)
    # Re-validate through the exact schema /predict uses, from the result's
    # own serialized form -- the real regression check: this must round-trip
    # cleanly through TransactionInput with no drift.
    revalidated = TransactionInput.model_validate(result.model_dump())
    assert revalidated == result


def test_amount_converted_from_cents_to_dollars():
    result = map_payment_intent_to_transaction_input(FAKE_PAYMENT_INTENT, wallet_balance_before=0.0)
    assert result.amount == pytest.approx(425.00)


def test_wallet_balance_maps_to_old_balance_org():
    result = map_payment_intent_to_transaction_input(
        FAKE_PAYMENT_INTENT, wallet_balance_before=12345.67
    )
    assert result.oldbalanceOrg == pytest.approx(12345.67)


def test_fixed_dest_balance_and_type_and_merchant_flag():
    result = map_payment_intent_to_transaction_input(FAKE_PAYMENT_INTENT, wallet_balance_before=0.0)

    assert result.type == TransactionType.TRANSFER
    assert result.oldbalanceDest == pytest.approx(SYNTHETIC_DEST_BALANCE)
    # is_merchant_dest isn't a TransactionInput field -- it's derived
    # downstream from nameDest's prefix. Confirm the adapter emits a
    # "C"-prefixed (personal, not merchant) destination id.
    assert result.nameDest.startswith("C")
    assert not result.nameDest.startswith("M")


def test_step_derived_deterministically_from_created_timestamp():
    result_a = map_payment_intent_to_transaction_input(FAKE_PAYMENT_INTENT, wallet_balance_before=0.0)
    result_b = map_payment_intent_to_transaction_input(FAKE_PAYMENT_INTENT, wallet_balance_before=0.0)

    assert result_a.step == result_b.step
    assert result_a.step >= 0


def test_extract_wallet_balance_reads_metadata():
    balance = extract_wallet_balance(FAKE_PAYMENT_INTENT["customer"])
    assert balance == pytest.approx(12345.67)


def test_extract_wallet_balance_raises_when_metadata_missing():
    customer_without_balance = {"id": "cus_NOBALANCE", "metadata": {}}
    with pytest.raises(ValueError, match=WALLET_BALANCE_METADATA_KEY):
        extract_wallet_balance(customer_without_balance)


def test_build_transaction_input_with_expanded_customer_needs_no_network():
    """The full convenience entrypoint, exercised with an already-expanded
    `customer` dict (as a real Stripe PaymentIntent would carry when
    retrieved with expand=["customer"]) -- this branch never calls the real
    Stripe API, so it's safe to run offline."""
    result = build_transaction_input_for_payment_intent(FAKE_PAYMENT_INTENT)

    assert isinstance(result, TransactionInput)
    TransactionInput.model_validate(result.model_dump())
    assert result.oldbalanceOrg == pytest.approx(12345.67)
