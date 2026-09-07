"""Test for /predict's per-IP rate limit (app/core/limiter.py, applied in
app/api/predict.py). The rest of the suite disables the limiter globally
(see conftest.py's autouse `_disable_rate_limiting` fixture) since it
legitimately calls /predict far more than the configured cap -- this is the
one test that re-enables it, deliberately, to exercise the 429 path itself."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402

LEGIT_PAYLOAD = {
    "step": 10,
    "type": "PAYMENT",
    "amount": 150.75,
    "oldbalanceOrg": 25000.0,
    "oldbalanceDest": 0.0,
    "nameDest": "M998877665",
}


def test_predict_returns_429_with_retry_after_once_rate_limit_exceeded():
    limiter.enabled = True
    limiter.reset()
    try:
        with TestClient(app) as client:
            responses = [client.post("/predict", json=LEGIT_PAYLOAD) for _ in range(25)]
    finally:
        limiter.enabled = False

    statuses = [r.status_code for r in responses]
    assert 200 in statuses, "some requests should succeed before the cap is hit"
    assert 429 in statuses, "the cap should eventually be exceeded"

    throttled = next(r for r in responses if r.status_code == 429)
    assert "retry-after" in {h.lower() for h in throttled.headers.keys()}
    assert int(throttled.headers["retry-after"]) > 0
    assert "Rate limit exceeded" in throttled.json()["detail"]
