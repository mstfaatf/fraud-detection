"""Shared pytest fixtures for backend/tests.

Disables the /predict rate limiter (app/core/limiter.py) for the whole test
session: the suite legitimately calls /predict far more than 20/minute across
its various modules (test_predict.py, test_persistence.py,
test_predictions_read.py all seed rows via real POST /predict calls), and
that's test-suite volume, not the abuse pattern the limiter exists to catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.limiter import limiter  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _disable_rate_limiting():
    limiter.enabled = False
    yield
