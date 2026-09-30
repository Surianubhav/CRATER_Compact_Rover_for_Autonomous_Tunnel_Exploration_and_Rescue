from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api/dev", tags=["dev"])


class ScenarioRequest(BaseModel):
    scenario: str  # "nominal" | "person_detected" | "communication_lost"


@router.post("/scenario")
def trigger_scenario(req: ScenarioRequest):
    """
    Development-only control (see product brief section 27): forces the
    simulation into one of a handful of demonstrable states. This does
    NOT fabricate thermal detections when a real camera feed is active --
    it's for exercising the UI before hardware / a live camera is
    plugged in. Intentionally NOT exposed as a prominent production
    control -- the frontend keeps this tucked into a small dev panel.
    """
    mission = get_mission_state()
    try:
        applied = mission.trigger_scenario(req.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"scenario": applied}
