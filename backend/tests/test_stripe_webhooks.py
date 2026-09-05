"""Tests for POST /webhooks/stripe -- starts the real app (TestClient, real
ML layer, real local Docker Postgres) but never calls the real Stripe API:
`stripe.Webhook.construct_event` and `stripe.PaymentIntent.cancel` are
monkeypatched for the "valid payload" tests, per this project's own
instruction not to hit real Stripe from the test suite. The one exception is
the invalid-signature test, which deliberately does NOT mock
`construct_event` -- it exercises Stripe's real (offline, no-network)
cryptographic signature check against a header that doesn't match, which is
a stronger test of the 400-on-bad-signature behavior than mocking would be.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Prediction, Transaction  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# A dummy-but-truthy secret -- the real value doesn't matter for the mocked
# tests (construct_event itself is replaced), but the endpoint's own
# "is a secret configured at all" guard requires *some* non-empty value.
_DUMMY_WEBHOOK_SECRET = "whsec_test_dummy_secret_for_tests"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _configure_webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", _DUMMY_WEBHOOK_SECRET)


def _fake_event(event_type: str, payment_intent: dict) -> dict:
    return {
        "id": "evt_test_" + payment_intent.get("id", "unknown"),
        "type": event_type,
        "data": {"object": payment_intent},
    }


def _payment_intent(pi_id: str, amount_dollars: float, wallet_balance: float) -> dict:
    """A fabricated PaymentIntent with an already-expanded `customer`, so
    build_transaction_input_for_payment_intent() (called from the webhook
    handler) never needs to call the real Stripe API to resolve the wallet
    balance -- see stripe_adapter.py.
    """
    return {
        "id": pi_id,
        "amount": int(round(amount_dollars * 100)),
        "currency": "usd",
        "created": 1_735_689_600,
        "customer": {
            "id": f"cus_{pi_id}",
            "metadata": {"wallet_balance": str(wallet_balance)},
        },
    }


# Draining-pattern amount verified (manually, against the real model) to
# clear the fraud threshold even with stripe_adapter.py's fixed
# SYNTHETIC_DEST_BALANCE -- see CLAUDE.md's Phase 9 part 2 notes on how that
# fixed destination balance suppresses probability at smaller amounts.
FRAUD_SHAPED_PI = _payment_intent("pi_test_fraud_shaped", amount_dollars=5_000_000.0, wallet_balance=5_000_000.0)
LEGIT_SHAPED_PI = _payment_intent("pi_test_legit_shaped", amount_dollars=5_000.0, wallet_balance=5_000.0)


def _cleanup_transaction(name_dest_suffix: str) -> None:
    db = SessionLocal()
    try:
        transactions = db.query(Transaction).filter(Transaction.nameDest.like(f"%{name_dest_suffix}%")).all()
        for transaction in transactions:
            db.query(Prediction).filter(Prediction.transaction_id == transaction.id).delete()
            db.delete(transaction)
        db.commit()
    finally:
        db.close()


def test_fraud_shaped_payload_cancels_payment_intent_and_persists_stripe_test_source(client, monkeypatch):
    cancel_calls = []
    monkeypatch.setattr(
        stripe.PaymentIntent, "cancel", lambda pi_id, **kw: cancel_calls.append(pi_id)
    )
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda *a, **kw: _fake_event("payment_intent.created", FRAUD_SHAPED_PI),
    )

    try:
        response = client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "irrelevant-because-mocked"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scored"
        assert data["is_fraud"] is True
        assert data["action_taken"] == "cancelled"
        assert cancel_calls == [FRAUD_SHAPED_PI["id"]]

        db = SessionLocal()
        try:
            transaction = (
                db.query(Transaction)
                .filter(Transaction.nameDest == f"C{FRAUD_SHAPED_PI['id']}")
                .order_by(Transaction.created_at.desc())
                .first()
            )
            assert transaction is not None
            assert transaction.source == "stripe_test"

            prediction = db.query(Prediction).filter(Prediction.transaction_id == transaction.id).one_or_none()
            assert prediction is not None
            assert prediction.is_fraud is True
        finally:
            db.close()
    finally:
        _cleanup_transaction(FRAUD_SHAPED_PI["id"])


def test_legit_shaped_payload_does_not_cancel(client, monkeypatch):
    cancel_calls = []
    monkeypatch.setattr(
        stripe.PaymentIntent, "cancel", lambda pi_id, **kw: cancel_calls.append(pi_id)
    )
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda *a, **kw: _fake_event("payment_intent.created", LEGIT_SHAPED_PI),
    )

    try:
        response = client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "irrelevant-because-mocked"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scored"
        assert data["is_fraud"] is False
        assert data["action_taken"] == "allowed"
        assert cancel_calls == []
    finally:
        _cleanup_transaction(LEGIT_SHAPED_PI["id"])


def test_invalid_signature_returns_400_and_persists_nothing(client):
    """Deliberately does NOT mock stripe.Webhook.construct_event -- this
    exercises Stripe's real signature-verification logic (a local
    cryptographic check, no network call) against a header that cannot
    possibly match the dummy secret, confirming the endpoint actually
    verifies signatures rather than trusting any payload it receives.
    """
    body = json.dumps(_fake_event("payment_intent.created", LEGIT_SHAPED_PI)).encode()

    response = client.post(
        "/webhooks/stripe",
        content=body,
        headers={"stripe-signature": "t=1,v1=0000000000000000000000000000000000000000000000000000000000000000"},
    )

    assert response.status_code == 400

    db = SessionLocal()
    try:
        assert (
            db.query(Transaction).filter(Transaction.nameDest == f"C{LEGIT_SHAPED_PI['id']}").first() is None
        )
    finally:
        db.close()


def test_non_created_event_type_returns_200_and_does_not_score(client, monkeypatch):
    cancel_calls = []
    monkeypatch.setattr(
        stripe.PaymentIntent, "cancel", lambda pi_id, **kw: cancel_calls.append(pi_id)
    )
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda *a, **kw: _fake_event("payment_intent.succeeded", FRAUD_SHAPED_PI),
    )

    response = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "irrelevant-because-mocked"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["event_type"] == "payment_intent.succeeded"
    assert cancel_calls == []

    db = SessionLocal()
    try:
        assert (
            db.query(Transaction).filter(Transaction.nameDest == f"C{FRAUD_SHAPED_PI['id']}").first() is None
        )
    finally:
        db.close()
