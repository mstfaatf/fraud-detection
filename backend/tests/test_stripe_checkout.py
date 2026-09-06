"""Tests for POST /create-payment-intent -- the checkout demo's server-side
half (frontend/app/checkout/page.tsx). Mocks every real Stripe API call
(Customer.create/retrieve, PaymentIntent.create), same convention as
test_stripe_webhooks.py -- no real Stripe API calls in the test suite.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.stripe_adapter import WALLET_BALANCE_METADATA_KEY  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _configure_stripe_key(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy_for_tests")


def _fake_customer():
    return {"id": "cus_fake123", "metadata": {WALLET_BALANCE_METADATA_KEY: "50000.0"}}


def test_create_payment_intent_returns_client_secret_and_wallet_balance(client, monkeypatch):
    monkeypatch.setattr(stripe.Customer, "create", lambda **kw: _fake_customer())

    created_kwargs = {}

    def fake_create(**kwargs):
        created_kwargs.update(kwargs)
        return SimpleNamespace(client_secret="pi_fake_secret_123", id="pi_fake123")

    monkeypatch.setattr(stripe.PaymentIntent, "create", fake_create)

    response = client.post("/create-payment-intent", json={"amount": 250.0})

    assert response.status_code == 200
    data = response.json()
    assert data["client_secret"] == "pi_fake_secret_123"
    assert data["payment_intent_id"] == "pi_fake123"
    assert data["wallet_balance"] == pytest.approx(50000.0)

    # Amount was converted from dollars to integer cents, and the demo
    # customer's id was attached to the created PaymentIntent.
    assert created_kwargs["amount"] == 25000
    assert created_kwargs["currency"] == "usd"
    assert created_kwargs["customer"] == "cus_fake123"


@pytest.mark.parametrize("bad_amount", [0, -10.0])
def test_create_payment_intent_rejects_non_positive_amount(client, bad_amount):
    response = client.post("/create-payment-intent", json={"amount": bad_amount})
    assert response.status_code == 422


def test_create_payment_intent_503_when_stripe_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", None)

    response = client.post("/create-payment-intent", json={"amount": 100.0})

    assert response.status_code == 503
