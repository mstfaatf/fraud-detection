"""Control endpoints for the background transaction simulator (see
app/services/simulator.py for the engine and the velocity-scenario caveat).

Thin route handlers, same split as predict.py/health.py: the actual engine
logic lives in the service module, these just validate the ML layer is
ready and translate the engine's own signals (SimulatorAlreadyRunningError)
into HTTP status codes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.limiter import limiter
from app.schemas.simulator import SimulatorStartRequest, SimulatorStatus
from app.services.simulator import SimulatorAlreadyRunningError, simulator

router = APIRouter(prefix="/simulator", tags=["simulator"])

_REQUIRED_STATE_ATTRS = ("xgb_model", "model_metadata", "shap_explainer", "isolation_forest")

# start/stop each cause real resource use -- a successful start spins up a
# background task generating and persisting rows at up to 20/sec (see
# app/services/simulator.py), and even a rejected/idempotent call is cheap
# but repeatable. Legitimate usage is "start once, stop once" per demo
# session, not a rapid loop, so this is deliberately tighter than the
# read-only /predictions limit (see SECURITY_AUDIT.md). /status is left
# unlimited: it's an in-memory dict read with no DB/ML cost, and the
# frontend's own Simulator page polls it every 7s (POLL_INTERVAL_MS).
_SIMULATOR_CONTROL_RATE_LIMIT = "10/minute"


@router.post("/start", response_model=SimulatorStatus)
@limiter.limit(_SIMULATOR_CONTROL_RATE_LIMIT)
async def start_simulator(payload: SimulatorStartRequest, request: Request, response: Response) -> SimulatorStatus:
    state = request.app.state
    missing = [attr for attr in _REQUIRED_STATE_ATTRS if getattr(state, attr, None) is None]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"ML layer not ready -- missing: {', '.join(missing)}. Check /health.",
        )

    try:
        return await simulator.start(
            rate_per_second=payload.rate_per_second,
            scenario_weights=payload.scenario_weights.model_dump(),
            ml_state={
                "xgb_model": state.xgb_model,
                "model_metadata": state.model_metadata,
                "shap_explainer": state.shap_explainer,
                "isolation_forest": state.isolation_forest,
            },
        )
    except SimulatorAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop", response_model=SimulatorStatus)
@limiter.limit(_SIMULATOR_CONTROL_RATE_LIMIT)
async def stop_simulator(request: Request, response: Response) -> SimulatorStatus:
    # Idempotent -- see TransactionSimulator.stop()'s docstring. Stopping an
    # already-stopped simulator is a deliberate no-op, not a 409/404.
    return await simulator.stop()


@router.get("/status", response_model=SimulatorStatus)
def simulator_status() -> SimulatorStatus:
    return simulator.status()
