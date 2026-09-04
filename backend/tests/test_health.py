"""Tests for GET /health -- starts the real app (via TestClient) so the
lifespan handler actually loads the XGBoost model, SHAP explainer, and
Isolation Forest model, and asserts /health reflects that."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_reports_models_loaded():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True}
