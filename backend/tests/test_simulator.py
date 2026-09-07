"""Tests for the transaction simulator engine (app/services/simulator.py)
and its control endpoints (app/api/simulator.py -- POST /simulator/start,
POST /simulator/stop, GET /simulator/status).

Runs against the real app (TestClient, real ML layer, real local Postgres)
like the rest of this suite. A short simulator run at a fast rate adds a
handful of real rows to the shared dev database -- consistent with how
test_predict.py / test_persistence.py / test_predictions_read.py already
add rows to it (see CLAUDE.md's Known Limitations note on this convention).
Kept brief (sub-two-second runs) specifically to keep that addition small.
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.prediction import TransactionInput  # noqa: E402
from app.services.simulator import TransactionGenerator  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _stop_simulator_after_each_test(client):
    """The engine is a module-level singleton (app/services/simulator.py),
    shared across every test in this module via the module-scoped `client`
    fixture above -- without this, a simulator left running by one test
    would keep generating (and persisting) transactions during the next
    one, making both flaky and hard to reason about."""
    yield
    client.post("/simulator/stop")


def test_generated_payloads_pass_transaction_input_validation():
    """Catches generator bugs early: every payload TransactionGenerator can
    produce, across all three scenarios, must satisfy the exact same
    Pydantic schema POST /predict enforces on real client input."""
    generator = TransactionGenerator()

    for _ in range(200):
        TransactionInput(**generator.legit_payload())
        TransactionInput(**generator.fraud_payload())

    for _ in range(50):
        for raw in generator.velocity_burst():
            TransactionInput(**raw)


def test_status_when_stopped_reports_not_running(client):
    client.post("/simulator/stop")  # idempotent -- ensures a known baseline
    status = client.get("/simulator/status").json()
    assert status["running"] is False
    assert status["transactions_generated"] == 0
    assert status["started_at"] is None
    assert status["uptime_seconds"] is None


def test_start_then_status_then_stop_lifecycle(client):
    start_status = client.post("/simulator/start", json={"rate_per_second": 10}).json()
    assert start_status["running"] is True
    assert start_status["rate_per_second"] == 10
    assert start_status["transactions_generated"] == 0
    assert start_status["started_at"] is not None

    time.sleep(1.0)

    running_status = client.get("/simulator/status").json()
    assert running_status["running"] is True
    assert running_status["transactions_generated"] >= 1
    assert running_status["uptime_seconds"] is not None
    assert running_status["uptime_seconds"] > 0

    stopped_status = client.post("/simulator/stop").json()
    assert stopped_status["running"] is False
    # The count from the finished run is still reported, not reset to 0,
    # until the next start() call.
    assert stopped_status["transactions_generated"] >= 1

    # Idempotent: stopping an already-stopped simulator is a no-op, not an
    # error -- calling it again must not raise or change the reported count.
    stopped_again = client.post("/simulator/stop").json()
    assert stopped_again["running"] is False
    assert stopped_again["transactions_generated"] == stopped_status["transactions_generated"]


def test_starting_twice_returns_409_and_leaves_original_run_untouched(client):
    first = client.post("/simulator/start", json={"rate_per_second": 5})
    assert first.status_code == 200

    second = client.post("/simulator/start", json={"rate_per_second": 17})
    assert second.status_code == 409
    assert "already running" in second.json()["detail"].lower()

    # The rejected second call must not have touched the original run's config.
    status = client.get("/simulator/status").json()
    assert status["running"] is True
    assert status["rate_per_second"] == 5


def test_scenario_weights_are_echoed_in_status(client):
    weights = {"legit": 1.0, "fraud": 0.0, "velocity": 0.0}
    start_status = client.post(
        "/simulator/start",
        json={"rate_per_second": 10, "scenario_weights": weights},
    ).json()
    assert start_status["scenario_weights"] == weights


@pytest.mark.parametrize(
    "body",
    [
        {"rate_per_second": 0},  # must be > 0
        {"rate_per_second": -1},
        {"rate_per_second": 21},  # above the documented safety cap of 20
        {"rate_per_second": 5, "scenario_weights": {"legit": -1.0}},  # weights must be >= 0
    ],
)
def test_start_rejects_invalid_bodies_with_422(client, body):
    response = client.post("/simulator/start", json=body)
    assert response.status_code == 422


def test_start_rejects_all_zero_scenario_weights_with_422(client):
    response = client.post(
        "/simulator/start",
        json={"rate_per_second": 5, "scenario_weights": {"legit": 0, "fraud": 0, "velocity": 0}},
    )
    assert response.status_code == 422
