"""Background transaction-simulator engine.

Generates synthetic pre-transaction payloads and scores each one through the
real prediction pipeline (predict_transaction() -- the exact function POST
/predict calls), on an asyncio background task, so the dashboard's live feed
(GET /predictions polling) has continuous activity without a human submitting
one transaction at a time via Test a Transaction. This is the "later-phase
transaction simulator" flagged since Phase 1's Feature Schema notes.

VELOCITY_SCENARIO_NOTE -- read before touching the "velocity" scenario:
PaySim has only 0.15% repeat `nameOrig` values (see CLAUDE.md, Feature
Schema -- "Excluded, insufficient data"), nowhere near enough to train real
account-history/velocity features on, and `TransactionInput` doesn't even
accept an origin-account identifier (there's no `nameOrig` field on the API
or the `transactions` table at all -- see app/schemas/prediction.py /
app/db/models.py). So the "velocity" scenario below is a *UI/demo
illustration only*: it fires a rapid burst of independently-scored
transactions in quick succession (sharing a narrative -- same type, same
destination, a balance that visibly decreases across the burst -- purely so
it *reads* as "one account, several rapid transfers" to a human watching the
dashboard) to demonstrate the live feed's behavior under bursty submission.
The trained XGBoost model has no cross-transaction memory: it scores every
transaction in a velocity burst exactly as it would score any unrelated
single transaction, with zero special handling. Do not present this
scenario as a model capability -- it demonstrates dashboard/UI behavior
under load, not fraud-velocity detection.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.db.session import SessionLocal
from app.schemas.prediction import TransactionInput
from app.schemas.simulator import SimulatorStatus
from app.services.prediction_service import predict_transaction

logger = logging.getLogger(__name__)


class Scenario(str, Enum):
    LEGIT = "legit"
    FRAUD = "fraud"
    VELOCITY = "velocity"


class SimulatorAlreadyRunningError(Exception):
    """Raised by TransactionSimulator.start() when a run is already active."""


# --- Amount distributions, derived from ml/notebooks/EDA_FINDINGS.md's
# documented statistics, not fit to raw data (this module never loads the
# 6.36M-row PaySim CSV) and not arbitrary either. EDA_FINDINGS.md reports
# amount's median/mean for legit and fraud transactions separately; for a
# lognormal(mu, sigma), median = exp(mu) and mean = exp(mu + sigma^2/2), so
# both parameters are solved directly from those two documented numbers:
#   mu = ln(median), sigma = sqrt(2 * ln(mean / median))
_LEGIT_AMOUNT_MEDIAN = 74_872.0
_LEGIT_AMOUNT_MEAN = 179_862.0
_LEGIT_AMOUNT_MU = math.log(_LEGIT_AMOUNT_MEDIAN)
_LEGIT_AMOUNT_SIGMA = math.sqrt(2 * math.log(_LEGIT_AMOUNT_MEAN / _LEGIT_AMOUNT_MEDIAN))

_FRAUD_AMOUNT_MEDIAN = 441_423.0
_FRAUD_AMOUNT_MEAN = 1_467_967.0
_FRAUD_AMOUNT_MU = math.log(_FRAUD_AMOUNT_MEDIAN)
_FRAUD_AMOUNT_SIGMA = math.sqrt(2 * math.log(_FRAUD_AMOUNT_MEAN / _FRAUD_AMOUNT_MEDIAN))

# Demo-legibility clip, not a data fact -- PaySim's real max (92.4M) is an
# extreme outlier that would dwarf every other row on a dashboard chart.
_AMOUNT_CLIP_MAX = 5_000_000.0

# EDA_FINDINGS.md: overall type volumes are PAYMENT 2,151,495, CASH_IN
# 1,400,000, DEBIT ~41,000 (out of 6,362,620 total), with the CASH_OUT/
# TRANSFER remainder split "~4x" in CASH_OUT's favor -- these weights are
# that documented split, not independently measured.
LEGIT_TYPE_WEIGHTS: dict[str, float] = {
    "PAYMENT": 0.3382,
    "CASH_OUT": 0.3483,
    "CASH_IN": 0.2201,
    "TRANSFER": 0.0871,
    "DEBIT": 0.0064,
}

# EDA_FINDINGS.md: fraud occurs only in TRANSFER/CASH_OUT, and despite very
# different per-transaction fraud rates (TRANSFER 0.77% vs CASH_OUT 0.18%),
# "the two types end up contributing almost the same raw fraud count" --
# hence an even split here, not proportional to overall volume.
FRAUD_TYPE_WEIGHTS: dict[str, float] = {"TRANSFER": 0.5, "CASH_OUT": 0.5}

_SCENARIO_ORDER = [Scenario.LEGIT, Scenario.FRAUD, Scenario.VELOCITY]

# Real wall-clock delay between transactions *within* one velocity burst --
# deliberately much shorter than the loop's normal per-scenario pacing, so a
# burst visibly reads as "several rows landing almost at once" in a
# 7-second-polling dashboard feed (see CLAUDE.md's POLL_INTERVAL_MS).
_VELOCITY_INTRA_BURST_DELAY_SECONDS = 0.15


class TransactionGenerator:
    """Draws synthetic pre-transaction payloads matching TransactionInput's
    schema, from ranges informed by ml/notebooks/EDA_FINDINGS.md and
    ml/notebooks/SHAP_FINDINGS.md rather than arbitrary random numbers.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def _random_account_id(self, prefix: str) -> str:
        return f"{prefix}{self._rng.randrange(10**9, 10**10)}"

    def _clipped_lognormal(self, mu: float, sigma: float, lo: float = 1.0, hi: float = _AMOUNT_CLIP_MAX) -> float:
        return min(max(self._rng.lognormvariate(mu, sigma), lo), hi)

    def _weighted_choice(self, weights: dict[str, float]) -> str:
        keys = list(weights.keys())
        vals = list(weights.values())
        return self._rng.choices(keys, weights=vals, k=1)[0]

    def pick_scenario(self, scenario_weights: dict[str, float]) -> Scenario:
        weights = [scenario_weights.get(s.value, 0.0) for s in _SCENARIO_ORDER]
        return self._rng.choices(_SCENARIO_ORDER, weights=weights, k=1)[0]

    def legit_payload(self) -> dict[str, Any]:
        """A normal-looking transaction: type drawn from PaySim's overall
        type mix, amount from the legit amount distribution, and an origin
        balance sized so amount_to_balance_ratio -- the model's single
        strongest feature (see CLAUDE.md's Phase 3 driver finding) --
        lands comfortably below the near-1.0 fraud-signature band.
        """
        type_ = self._weighted_choice(LEGIT_TYPE_WEIGHTS)
        amount = round(self._clipped_lognormal(_LEGIT_AMOUNT_MU, _LEGIT_AMOUNT_SIGMA), 2)

        ratio = self._rng.uniform(0.0005, 0.35)
        old_balance_org = round(amount / ratio, 2)

        is_merchant = type_ == "PAYMENT"
        name_dest = self._random_account_id("M") if is_merchant else self._random_account_id("C")

        if is_merchant:
            # EDA_FINDINGS.md: every merchant-destination row has
            # oldbalanceDest == 0, with zero exceptions in the real dataset.
            old_balance_dest = 0.0
        elif self._rng.random() < 0.2:
            # A meaningful share of personal destinations are fresh/near-empty
            # accounts too, not just points on the lognormal curve.
            old_balance_dest = 0.0
        else:
            old_balance_dest = round(self._clipped_lognormal(_LEGIT_AMOUNT_MU, _LEGIT_AMOUNT_SIGMA), 2)

        return {
            "step": self._rng.randint(0, 743),
            "type": type_,
            "amount": amount,
            "oldbalanceOrg": old_balance_org,
            "oldbalanceDest": old_balance_dest,
            "nameDest": name_dest,
        }

    def fraud_payload(self) -> dict[str, Any]:
        """A draining-pattern transaction matching PaySim's core fraud
        signature: oldbalanceOrg == amount (EDA_FINDINGS.md: ~97.7% of real
        fraud rows drain the origin account exactly), type restricted to
        TRANSFER/CASH_OUT (fraud never occurs in the other three types), and
        a destination that's usually an empty drop account but sometimes
        already holds a large balance -- the same false-negative-adjacent
        pattern documented in SHAP_FINDINGS.md's step-611 example, where a
        pre-funded destination pulls the score down toward the threshold.
        """
        type_ = self._weighted_choice(FRAUD_TYPE_WEIGHTS)
        amount = round(self._clipped_lognormal(_FRAUD_AMOUNT_MU, _FRAUD_AMOUNT_SIGMA), 2)
        old_balance_org = amount  # the draining signature, exactly

        if self._rng.random() < 0.15:
            old_balance_dest = round(self._clipped_lognormal(_LEGIT_AMOUNT_MU, _LEGIT_AMOUNT_SIGMA), 2)
        else:
            old_balance_dest = 0.0

        # Fraud never targets a merchant in PaySim (only TRANSFER/CASH_OUT
        # carry fraud, and both always go to a C-prefixed customer account).
        name_dest = self._random_account_id("C")

        return {
            "step": self._rng.randint(0, 743),
            "type": type_,
            "amount": amount,
            "oldbalanceOrg": old_balance_org,
            "oldbalanceDest": old_balance_dest,
            "nameDest": name_dest,
        }

    def velocity_burst(self) -> list[dict[str, Any]]:
        """See VELOCITY_SCENARIO_NOTE above -- a UI/demo illustration of a
        rapid-succession burst, not a model-detectable pattern. Produces
        several independently-scored payloads that share a narrative (same
        type, same destination, a balance that decreases across the burst)
        purely so a human watching the dashboard reads it as "one account,
        several fast transfers" -- there is no nameOrig field anywhere in
        this API or schema, so no actual account identity is persisted or
        available to the model; each payload is scored on its own merits
        exactly like any unrelated single transaction.
        """
        burst_size = self._rng.randint(3, 8)
        type_ = self._rng.choice(["CASH_OUT", "TRANSFER"])
        shared_dest = self._random_account_id("C")
        step = self._rng.randint(0, 743)
        balance = self._clipped_lognormal(_LEGIT_AMOUNT_MU, _LEGIT_AMOUNT_SIGMA, lo=10_000.0, hi=2_000_000.0)

        payloads = []
        for _ in range(burst_size):
            # Each hop drains a modest fraction of what's left -- deliberately
            # NOT the fraud scenario's full-drain-in-one-shot signature, so
            # this reads as a distinct "many small rapid transfers" pattern
            # rather than duplicating fraud_payload()'s shape.
            fraction = self._rng.uniform(0.05, 0.2)
            amount = round(balance * fraction, 2)
            payloads.append(
                {
                    "step": step,
                    "type": type_,
                    "amount": amount,
                    "oldbalanceOrg": round(balance, 2),
                    "oldbalanceDest": 0.0,
                    "nameDest": shared_dest,
                }
            )
            balance = max(balance - amount, 0.0)

        return payloads


class TransactionSimulator:
    """Owns the single allowed simulator run (see start()) and its asyncio
    background task. `predict_transaction` is called directly -- never over
    HTTP back to this same app -- so each generated transaction goes through
    the identical pipeline POST /predict uses (preprocessing, XGBoost, SHAP,
    Isolation Forest, persistence) without an extra network hop or being
    subject to /predict's own slowapi rate limit, which exists to protect
    against external callers, not this in-process generator.
    """

    def __init__(self, generator: TransactionGenerator | None = None) -> None:
        self._generator = generator or TransactionGenerator()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._running = False
        self._rate_per_second: float | None = None
        self._scenario_weights: dict[str, float] | None = None
        self._started_at: datetime | None = None
        self._count = 0
        self._ml_state: dict[str, Any] | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> SimulatorStatus:
        uptime = None
        if self._running and self._started_at is not None:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        return SimulatorStatus(
            running=self._running,
            rate_per_second=self._rate_per_second,
            scenario_weights=self._scenario_weights,
            transactions_generated=self._count,
            started_at=self._started_at,
            uptime_seconds=uptime,
        )

    async def start(
        self,
        *,
        rate_per_second: float,
        scenario_weights: dict[str, float],
        ml_state: dict[str, Any],
    ) -> SimulatorStatus:
        """Only one run at a time: starting while already running is
        rejected (409, via SimulatorAlreadyRunningError) rather than
        silently restarting -- an explicit POST /simulator/stop first is
        simpler to reason about than a start-time reset, and avoids a race
        between tearing down the old task and standing up a new one.
        """
        async with self._lock:
            if self._running:
                raise SimulatorAlreadyRunningError(
                    "Simulator is already running -- call POST /simulator/stop first."
                )
            self._rate_per_second = rate_per_second
            self._scenario_weights = dict(scenario_weights)
            self._ml_state = ml_state
            self._count = 0
            self._started_at = datetime.now(timezone.utc)
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            return self.status()

    async def stop(self) -> SimulatorStatus:
        """Idempotent: stopping an already-stopped simulator is a no-op
        that just returns the current (stopped) status, rather than
        erroring -- "make sure it's off" trivially succeeds if it's already
        off.

        Cancels the loop's *next* iteration; a transaction already in
        flight (inside asyncio.to_thread, mid predict_transaction call) is
        not interrupted -- asyncio cannot forcibly stop a running OS thread,
        and letting it finish is the safer choice anyway: predict_transaction
        + its DB commit either fully completes or (per its own try/except)
        rolls back, so there is never a half-written row, only possibly one
        extra completed one racing the "stopped" status.
        """
        async with self._lock:
            self._running = False
            task = self._task
            self._task = None

        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        return self.status()

    async def _run_loop(self) -> None:
        assert self._rate_per_second is not None
        assert self._scenario_weights is not None
        try:
            while True:
                scenario = self._pick_scenario()
                try:
                    if scenario is Scenario.VELOCITY:
                        for raw_payload in self._generator.velocity_burst():
                            await self._score_one(raw_payload)
                            await asyncio.sleep(_VELOCITY_INTRA_BURST_DELAY_SECONDS)
                    elif scenario is Scenario.FRAUD:
                        await self._score_one(self._generator.fraud_payload())
                    else:
                        await self._score_one(self._generator.legit_payload())
                except Exception:
                    # One bad generated transaction (or a transient DB hiccup)
                    # must not silently kill the whole background run --
                    # log it and keep going, same fail-loud-but-keep-serving
                    # philosophy as predict_transaction's own DB-failure path.
                    logger.exception("Simulator: failed to score a generated transaction; continuing")

                await asyncio.sleep(1.0 / self._rate_per_second)
        except asyncio.CancelledError:
            raise

    def _pick_scenario(self) -> Scenario:
        assert self._scenario_weights is not None
        return self._generator.pick_scenario(self._scenario_weights)

    async def _score_one(self, raw_payload: dict[str, Any]) -> None:
        assert self._ml_state is not None
        payload = TransactionInput(**raw_payload)  # same validation POST /predict enforces

        db = SessionLocal()
        try:
            await asyncio.to_thread(
                predict_transaction,
                payload,
                xgb_model=self._ml_state["xgb_model"],
                model_metadata=self._ml_state["model_metadata"],
                explainer=self._ml_state["shap_explainer"],
                isolation_forest=self._ml_state["isolation_forest"],
                db=db,
            )
            self._count += 1
        finally:
            db.close()


# Module-level singleton -- mirrors app/core/limiter.py's shared-instance
# pattern. app/api/simulator.py imports this directly rather than
# constructing its own TransactionSimulator, since there must only ever be
# one simulator run for the whole app process.
simulator = TransactionSimulator()
