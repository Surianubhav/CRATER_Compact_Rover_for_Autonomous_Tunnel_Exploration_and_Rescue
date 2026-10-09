import time
import uuid

from fastapi import APIRouter

from app.models.schemas import Annotation, EventCategory
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["annotations"])


@router.get("/annotations")
def list_annotations():
    mission = get_mission_state()
    return {"annotations": [a.model_dump(mode="json") for a in mission.annotations]}


@router.post("/annotations")
def add_annotation(payload: dict):
    mission = get_mission_state()
    ann = Annotation(
        id=f"ANN-{len(mission.annotations) + 1:03d}",
        x_m=float(payload.get("x_m", 0)),
        y_m=float(payload.get("y_m", 0)),
        label=str(payload.get("label", "Annotation")),
        note=payload.get("note"),
        created_at=time.time(),
    )
    mission.annotations.append(ann)
    mission.events.add(
        EventCategory.ANNOTATION, f"Annotation added: {ann.label}", "operator", mission.mission_time_s,
        operator_action="ADD NOTE",
    )
    return ann.model_dump(mode="json")
