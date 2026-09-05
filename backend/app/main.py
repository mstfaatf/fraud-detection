"""FastAPI app instance, startup wiring, and route registration."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.health import router as health_router
from app.api.predict import router as predict_router
from app.api.predictions import router as predictions_router
from app.core.config import settings
from app.core.limiter import limiter
from app.ml.explainer import build_explainer
from app.ml.isolation_forest_loader import load_isolation_forest
from app.ml.model_loader import load_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    model, metadata = load_model(settings)
    app.state.xgb_model = model
    app.state.model_metadata = metadata
    app.state.shap_explainer = build_explainer(model)
    app.state.isolation_forest = load_isolation_forest(settings)
    yield


app = FastAPI(title="Fraud Detection API", lifespan=lifespan)

# Per-IP rate limiting (slowapi) -- open item since the backend skeleton phase,
# closed here because /predict is now genuinely public. Keyed on remote address
# (no auth/API-key layer exists to key on instead -- see CLAUDE.md's Known
# Limitations). `limiter` itself lives in app/core/limiter.py (shared with
# app/api/predict.py, which applies it as a decorator) to avoid a circular
# import between this module and the routers it registers below. The actual
# rate cap is applied only on the /predict route, not globally, since the
# read-only /predictions endpoints and /health don't need the same protection.
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Same Retry-After-header injection slowapi's own default handler uses
    # (via the limiter's tracked view_rate_limit for this request) -- reused
    # here only to give a clearer JSON body than the library's terse default.
    response = JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded ({exc.detail}). Please slow down and try again shortly.",
        },
    )
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)


# CORS: restricted to the real frontend origin(s), not "*" -- see the TODO
# this replaced, flagged since the backend skeleton phase. Local dev origins
# are always allowed (harmless -- they're not reachable from the public
# internet); settings.frontend_origin adds the real production Vercel URL
# once deployed. allow_origin_regex additionally covers that same Vercel
# project's *preview* deployments (a new URL per PR/branch, e.g.
# "https://fraud-detection-git-some-branch-<team>.vercel.app") so preview
# builds keep working without listing every preview URL by hand -- scoped to
# the "fraud-detection" project-name prefix specifically, not "*.vercel.app"
# generally, so it can't be satisfied by an unrelated Vercel deployment.
_dev_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_allow_origins = _dev_origins + ([settings.frontend_origin] if settings.frontend_origin else [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_origin_regex=r"^https://fraud-detection(-[a-zA-Z0-9-]*)?\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(predict_router)
app.include_router(predictions_router)
