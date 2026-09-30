from fastapi import APIRouter, HTTPException

from app.adapters.hardware_adapter import HardwareAdapterError
from app.config.settings import get_thresholds
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry")
def get_telemetry():
    mission = get_mission_state()
    if mission._history:
        return mission._history[-1][1]["telemetry"]
    return mission.tick(0.0).model_dump(mode="json")["telemetry"]


@router.get("/telemetry/thresholds")
def get_telemetry_thresholds():
    return get_thresholds()


@router.post("/telemetry/ingest")
def ingest_telemetry(payload: dict):
    """
    Hardware integration point. POST the exact JSON the Nano/ESP32 already
    emit, e.g.:
        {"hb": 123, "mq4": 88, "mq7": 228, "temp": 25.70,
         "hum": 57.60, "pressure": 97627.0, "alt": 312.88, "bmp_ok": true}
    While payloads keep arriving (within a ~10s freshness window) the
    mission source flips from SIMULATED to LIVE automatically.
    """
    mission = get_mission_state()
    try:
        mission.ingest_hardware_payload(payload)
    except HardwareAdapterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}
