from fastapi import APIRouter

from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api/mission", tags=["mission"])


@router.get("/state")
def get_state():
    """Full current mission snapshot -- same shape /ws/telemetry pushes."""
    mission = get_mission_state()
    if mission._history:
        return mission._history[-1][1]
    return mission.tick(0.0).model_dump(mode="json")


@router.get("/map")
def get_map():
    """Static mine geometry the frontend needs to draw the SVG map."""
    from app.simulation import mine_map
    return {
        "main_path": [{"id": w.id, "x_m": w.x_m, "y_m": w.y_m} for w in mine_map.MAIN_PATH],
        "dead_end_branch": [{"id": w.id, "x_m": w.x_m, "y_m": w.y_m} for w in mine_map.DEAD_END_BRANCH],
        "hazards": mine_map.HAZARDS,
        "gallery_half_width_m": mine_map.GALLERY_HALF_WIDTH_M,
        "dead_end_half_width_m": mine_map.DEAD_END_HALF_WIDTH_M,
        "total_path_length_m": mine_map.MAIN_PATH_TOTAL_M,
    }
