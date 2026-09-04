"""FastAPI app instance, startup wiring, and route registration."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings
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

# TODO: allow_origins=["*"] is wide open for local dev only -- restrict to the
# actual frontend origin(s) before any public deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
