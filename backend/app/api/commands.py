from fastapi import APIRouter

from app.models.schemas import CommandRequest, EventCategory
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["commands"])

VALID_TYPES = {
    "return_to_entry", "return_to_node", "go_to_node",
    "explore_unexplored", "go_to_marker", "hold_position", "resume",
}


@router.get("/commands")
def list_commands():
    mission = get_mission_state()
    return {"commands": [c.model_dump(mode="json") for c in mission.commands.recent(30)]}


@router.post("/commands")
def issue_command(req: CommandRequest):
    mission = get_mission_state()
    if req.type not in VALID_TYPES:
        return {"error": f"unknown command type {req.type}"}, 422

    link_lost = mission._history[-1][1]["link"]["status"] == "LOST" if mission._history else False

    selected_marker_pos = None
    if req.type == "go_to_marker":
        det = next(iter(mission.detections.values()), None)
        if det and det.position:
            selected_marker_pos = (det.position.x_m, det.position.y_m)

    cmd = mission.commands.issue(req.type, req.target, link_lost, selected_marker_pos)
    mission.events.add(
        EventCategory.COMMAND,
        f"{cmd.id} {cmd.label} \u2014 {cmd.status.value}",
        "operator", mission.mission_time_s, operator_action=cmd.label,
    )
    return cmd.model_dump(mode="json")
