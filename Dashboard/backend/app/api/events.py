from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.models.schemas import EventCategory
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
def list_events(search: str | None = None, category: str | None = None, limit: int = 500):
    mission = get_mission_state()
    cat = None
    if category:
        try:
            cat = EventCategory(category.upper())
        except ValueError:
            cat = None
    return {"events": [e.model_dump(mode="json") for e in mission.events.query(search, cat, limit)]}


@router.get("/events/export.csv", response_class=PlainTextResponse)
def export_events_csv():
    mission = get_mission_state()
    return mission.events.to_csv()
