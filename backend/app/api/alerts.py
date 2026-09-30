from fastapi import APIRouter, HTTPException

from app.models.schemas import EventCategory
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
def list_alerts(include_resolved: bool = False):
    mission = get_mission_state()
    return {"alerts": [a.model_dump(mode="json") for a in (mission.alerts.all() if include_resolved else mission.alerts.active())]}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str):
    mission = get_mission_state()
    alert = mission.alerts.ack(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    mission.events.add(
        EventCategory.SYSTEM, f"{alert_id} acknowledged by operator", "operator",
        mission.mission_time_s, operator_action="ACK",
    )
    return alert.model_dump(mode="json")
