"""Shared slowapi Limiter instance.

Lives in its own module (not app/main.py) specifically to avoid a circular
import: app/main.py registers the routers from app/api/*.py, and
app/api/predict.py needs to import `limiter` to decorate its route --
importing it from app.main would import app.main from within a module
app.main itself imports.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# headers_enabled=True is what makes _inject_headers (called from main.py's
# RateLimitExceeded handler) actually write a Retry-After header -- it's a
# no-op otherwise (slowapi defaults headers_enabled to False).
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
