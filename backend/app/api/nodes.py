from fastapi import APIRouter

from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["nodes"])


@router.get("/nodes")
def get_nodes():
    mission = get_mission_state()
    if mission._history:
        snap = mission._history[-1][1]
        return {"nodes": snap["nodes"], "link": snap["link"]}
    snap = mission.tick(0.0).model_dump(mode="json")
    return {"nodes": snap["nodes"], "link": snap["link"]}
