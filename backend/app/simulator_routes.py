"""Demo-only API for submitting deterministic synthetic observations."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from .event_broker import publish_after_commit
from pydantic import BaseModel, ConfigDict, Field

from .model import active_model_metadata, explain, predict_probability, risk_level
from .schemas import RiskPrediction
from .simulator import observation_for_step
from .storage import save_observation

router = APIRouter(prefix="/api/v1/demo", tags=["demo-simulator"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(default="DEMO-LIVE-001", min_length=1, max_length=64)
    scenario: Literal["stable", "worsening", "recovering"] = "stable"
    step: int = Field(default=0, ge=0, le=1000)


@router.post("/observations", response_model=RiskPrediction)
async def submit_demo_observation(payload: SimulationRequest, request: Request):
    """Generate, validate, score, and persist one fictional observation.

    A caller controls the step to make the demo deterministic and easy to
    present. Repeated requests are separate observations, not idempotent writes.
    """
    values = observation_for_step(payload.scenario, payload.step)
    probability = await asyncio.to_thread(predict_probability, values)
    score = round(probability * 100)
    result = RiskPrediction(
        patient_id=payload.patient_id,
        risk_score=score,
        risk_level=risk_level(score),
        model_probability=round(probability, 4),
        factors=explain(values),
        model_version=active_model_metadata()["model_version"],
    )
    saved = await asyncio.to_thread(save_observation, payload.patient_id, values, result.model_dump(), session_id=request.headers.get('X-Session-ID'))
    await publish_after_commit(saved['event'])
    return result.model_copy(
        update={"observation_id": saved["id"], "created_at": saved["created_at"]}
    )
