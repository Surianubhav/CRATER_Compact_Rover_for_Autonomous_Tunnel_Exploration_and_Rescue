from fastapi import APIRouter, HTTPException

from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["detections"])


@router.get("/detections")
def list_detections():
    mission = get_mission_state()
    return {"detections": [d.model_dump(mode="json") for d in mission.detections.values()]}


@router.post("/detections/{detection_id}/confirm")
def confirm_detection(detection_id: str):
    mission = get_mission_state()
    d = mission.confirm_detection(detection_id)
    if not d:
        raise HTTPException(status_code=404, detail="detection not found")
    return d.model_dump(mode="json")


@router.post("/detections/{detection_id}/dismiss")
def dismiss_detection(detection_id: str):
    mission = get_mission_state()
    d = mission.dismiss_detection(detection_id)
    if not d:
        raise HTTPException(status_code=404, detail="detection not found")
    return d.model_dump(mode="json")
