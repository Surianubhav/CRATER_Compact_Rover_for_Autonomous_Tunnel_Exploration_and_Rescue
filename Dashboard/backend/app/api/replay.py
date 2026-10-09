from fastapi import APIRouter

from app.models.schemas import EventCategory
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api/replay", tags=["replay"])

TIMELINE_CATEGORIES = {EventCategory.NODE, EventCategory.DETECTION, EventCategory.GAS, EventCategory.COMMS}


@router.get("/timeline")
def get_timeline():
    """
    Event markers for the scrubber (node drops, detections, gas
    threshold crossings, communication outages) plus the min/max mission
    time currently available to scrub through.
    """
    mission = get_mission_state()
    start_s, end_s = mission.timeline_bounds()
    markers = [
        e.model_dump(mode="json") for e in mission.events.query(limit=500)
        if e.category in TIMELINE_CATEGORIES
    ]
    return {"start_s": start_s, "end_s": end_s, "markers": markers}


@router.get("/snapshot")
def get_snapshot(t: float):
    """Mission state as it was at mission-time `t` seconds (nearest recorded tick)."""
    mission = get_mission_state()
    snap = mission.snapshot_at(t)
    if snap is None:
        return {"error": "no history recorded yet"}
    return snap
