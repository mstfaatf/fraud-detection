# syntax=docker/dockerfile:1
#
# Production-style multi-stage Dockerfile for the FastAPI backend, built for
# LOCAL full-stack Docker Compose use and containerization practice -- this is
# NOT how the live public backend is deployed. Render builds directly from
# backend/requirements.txt per render.yaml (`pip install -r
# backend/requirements.txt`, then `uvicorn app.main:app --app-dir backend`)
# and is completely unaffected by anything in this file.
#
# IMPORTANT -- build context must be the REPO ROOT, not backend/:
#   docker build -t fraud-backend -f backend/Dockerfile .
# `docker build -t fraud-backend ./backend` (context = backend/ alone) will
# fail: app/core/config.py resolves REPO_ROOT by walking up from its own file
# looking for a .git directory or the .repo-root marker file (see that
# module's docstring), then puts ml/src/ on sys.path (`import preprocessing`)
# and loads ml/models/{xgboost_model.pkl,model_metadata.json,
# isolation_forest.pkl} at startup -- none of which live under backend/, so a
# backend/-only build context has no way to COPY them in. This was confirmed
# by actually trying the backend/-only build first, not assumed.
# docker-compose.yml should set `build: {context: ., dockerfile:
# backend/Dockerfile}` for the same reason.

# ---- Build stage: compile/install Python dependencies into a venv ----
# `3.12-slim-bookworm` (floating patch within Debian 12/bookworm), not the
# originally-pinned `3.12.7-slim` -- a security audit (SECURITY_AUDIT.md)
# found the pinned tag's underlying Debian package set had accumulated a
# meaningful number of OS-level CVEs since it was first pulled (trivy: 9
# critical/94 high on the base image alone), and a same-OS-major, same-
# Python-minor bump to a newer bookworm point release cut that to 5/55
# with no compatibility risk (still Debian 12, still Python 3.12.x) -- a
# full-major-version float (`python:3.12-slim`, now Debian 13/trixie) was
# considered and deliberately rejected as too large a jump for this fix.
# This floats forward on every rebuild rather than re-pinning a new exact
# patch, since re-stalening is exactly the problem being fixed here.
FROM python:3.12-slim-bookworm AS builder

# build-essential + python3-dev cover any dependency that doesn't ship a
# prebuilt wheel for this platform. Confirmed empirically that every package
# in backend/requirements.txt -- including psycopg2-binary,
# pandas, scikit-learn, xgboost, and shap -- actually installs from prebuilt
# manylinux wheels for cpython 3.12/linux-amd64, so nothing here truly needs
# compiling today. Kept anyway as a safety net: without it, a future
# dependency bump that drops a wheel for this platform would fail with a
# confusing "missing gcc"/"Python.h not found" error instead of just working.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage: slim image, no compilers, non-root user ----
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Repo-root marker (see the note at the top of this file) -- app/core/config.py
# walks up from backend/app/core/config.py looking for a .git directory or
# this exact file. .git is excluded from this build context entirely (see
# backend/Dockerfile.dockerignore's `.git/` entry), so .repo-root -- an empty
# file, always git-tracked, never gitignored -- is the marker this image
# actually relies on.
COPY .repo-root ./.repo-root

# ml/src (imported via the sys.path insert in app/core/config.py) and exactly
# the three trained-model artifacts the app actually loads at startup -- the
# same three files render.yaml's git-based deploy ships (see .gitignore's
# ml/models/* exceptions). shap_explainer.pkl is deliberately NOT copied: the
# SHAP explainer is reconstructed fresh from the loaded model at startup
# (app/ml/explainer.py), never unpickled, so shipping it would be dead weight.
COPY ml/src ./ml/src
COPY ml/models/xgboost_model.pkl ml/models/model_metadata.json ml/models/isolation_forest.pkl ./ml/models/

COPY backend/app ./backend/app

# Alembic config + migration scripts -- a real gap found and fixed during
# Phase 11 part 4's live verification: this Dockerfile originally copied only
# backend/app, so `docker compose exec backend alembic upgrade head` (the
# documented migration step, see docker-compose.yml) failed with "No
# 'script_location' key found in configuration" -- alembic.ini and alembic/
# genuinely weren't in the image at all. `alembic.ini`'s `script_location =
# %(here)s/alembic` resolves relative to alembic.ini's own directory (the
# `%(here)s` token, Alembic 1.9+), so both must land at the same relative
# path to WORKDIR /app/backend below as they have in the real repo.
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/alembic ./backend/alembic

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app /opt/venv
USER appuser

# cwd = /app/backend so `app.main:app` resolves exactly like local dev
# (`uvicorn app.main:app --reload` run from backend/, per SETUP.md) and
# Render's own `--app-dir backend` -- same module path, three different hosts.
WORKDIR /app/backend

# Configurable port, defaulting to the local-dev convention (8000). Compose
# can override via `-e PORT=...` or an env_file without touching this image.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=3)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
