from fastapi import APIRouter, HTTPException

from app.services.mission_state import get_mission_state
from app.services.route_planner import build_route

router = APIRouter(prefix="/api", tags=["route"])


@router.get("/route")
def get_route(detection_id: str | None = None, x_m: float | None = None, y_m: float | None = None):
    """
    Build a rescue route to either a confirmed detection (by id) or an
    explicit x_m/y_m point. Per the brief, only CONFIRMED detections
    should normally be routed to from the UI -- enforced client-side by
    only showing "EXPORT ROUTE" once confirmed, and here by allowing any
    detection but flagging its status in the response.
    """
    target_x, target_y, detection = x_m, y_m, None
    if detection_id:
        mission = get_mission_state()
        detection = mission.detections.get(detection_id)
        if not detection or not detection.position:
            raise HTTPException(status_code=404, detail="detection not found or has no position yet")
        target_x, target_y = detection.position.x_m, detection.position.y_m

    if target_x is None or target_y is None:
        raise HTTPException(status_code=422, detail="provide detection_id or x_m & y_m")

    route = build_route(target_x, target_y)
    if detection:
        route["target_detection_id"] = detection.id
        route["target_detection_status"] = detection.status.value
    return route
