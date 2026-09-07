"""Request/response schemas for /simulator/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ScenarioWeights(BaseModel):
    """Relative mix of generated scenario types.

    Values don't need to already sum to 1 -- app/services/simulator.py's
    scenario picker normalizes whatever's given via random.Random.choices'
    own weights= handling. Defaults deliberately do NOT match PaySim's real
    fraud prevalence (~0.13% of all transactions, per EDA_FINDINGS.md) --
    a rate that rare would almost never produce a visible fraud row in a
    short live-demo session. These defaults exist to keep the dashboard's
    fraud/anomaly UI visibly exercised, not to model real-world prevalence.
    """

    legit: float = Field(default=0.85, ge=0)
    fraud: float = Field(default=0.10, ge=0)
    # See app/services/simulator.py's module docstring and
    # VELOCITY_SCENARIO_NOTE: this is a UI/demo illustration of a
    # rapid-succession burst, not a claim that the trained model detects
    # velocity/account-history patterns -- it was never fit on any such
    # feature (CLAUDE.md, Feature Schema -- "Excluded, insufficient data").
    velocity: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def _at_least_one_positive(self) -> "ScenarioWeights":
        if self.legit + self.fraud + self.velocity <= 0:
            raise ValueError("At least one scenario weight must be positive.")
        return self


class SimulatorStartRequest(BaseModel):
    # Bounded rather than unbounded -- a demo-scale safety cap (not a
    # measured platform limit) so a UI slider, or a typo, can't accidentally
    # hammer the database or the Render free-tier instance.
    rate_per_second: float = Field(default=1.0, gt=0, le=20)
    scenario_weights: ScenarioWeights = Field(default_factory=ScenarioWeights)


class SimulatorStatus(BaseModel):
    running: bool
    rate_per_second: float | None = None
    scenario_weights: dict[str, float] | None = None
    transactions_generated: int = 0
    started_at: datetime | None = None
    uptime_seconds: float | None = None
