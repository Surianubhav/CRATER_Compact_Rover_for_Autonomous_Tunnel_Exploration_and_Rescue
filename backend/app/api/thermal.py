"""
Thermal camera endpoints.

/api/thermal/frame is the live path: the frontend ThermalPanel captures
a frame (webcam or an uploaded/looped sample clip) and posts it here.
The adapter runs the EXISTING trained model on it; any person
detections are pushed into MissionState so they show up as a map
marker + Tier 2 alert automatically (see mission_state.ingest_detection).

/api/detect-thermal is kept for backward compatibility with the
single-image-upload contract the previous prototype backend exposed.
"""
from __future__ import annotations

import base64
import time

import numpy as np
from fastapi import APIRouter, File, UploadFile

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from app.adapters.thermal_adapter import get_thermal_adapter
from app.models.schemas import DataSource, ThermalConnectionState, ThermalFrameResult
from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["thermal"])


def _decode_upload(contents: bytes):
    if cv2 is None:
        return None
    nparr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


@router.get("/thermal/status")
def thermal_status():
    adapter = get_thermal_adapter()
    return {
        "connection_state": adapter.state.value,
        "model_name": adapter.model_name,
        "error_message": adapter.error_message,
    }


@router.post("/thermal/frame", response_model=ThermalFrameResult)
async def thermal_frame(file: UploadFile = File(...)):
    adapter = get_thermal_adapter()
    if adapter.state == ThermalConnectionState.DISCONNECTED and adapter.error_message is None:
        adapter.load()

    if adapter.state != ThermalConnectionState.LIVE:
        return ThermalFrameResult(
            connection_state=adapter.state,
            detections=[],
            error_message=adapter.error_message or "Model not ready",
            source=DataSource.LIVE,
        )

    contents = await file.read()
    frame = _decode_upload(contents)
    if frame is None:
        return ThermalFrameResult(
            connection_state=ThermalConnectionState.MODEL_ERROR,
            detections=[], error_message="Could not decode uploaded frame (opencv unavailable or bad image).",
            source=DataSource.LIVE,
        )

    try:
        detections, scene_avg_c, scene_max_c, annotated, inference_ms = adapter.run_inference(frame)
    except Exception as exc:  # noqa: BLE001
        return ThermalFrameResult(
            connection_state=ThermalConnectionState.MODEL_ERROR,
            detections=[], error_message=f"Inference failed: {exc}", source=DataSource.LIVE,
        )

    mission = get_mission_state()
    for det in detections:
        mission.ingest_detection(det, source=DataSource.LIVE)

    frame_uri = None
    if cv2 is not None:
        ok, buf = cv2.imencode(".jpg", annotated)
        if ok:
            frame_uri = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

    return ThermalFrameResult(
        connection_state=ThermalConnectionState.LIVE,
        frame_data_uri=frame_uri,
        detections=detections,
        scene_avg_c=scene_avg_c,
        scene_max_c=scene_max_c,
        model_name=adapter.model_name,
        inference_ms=round(inference_ms, 1),
        source=DataSource.LIVE,
    )


@router.post("/detect-thermal")
async def detect_thermal_legacy(file: UploadFile = File(...)):
    """Back-compat shape for the original prototype's single-image endpoint."""
    result = await thermal_frame(file)  # type: ignore[arg-type]
    detections_out = [
        {"label": d.type, "confidence": d.confidence} for d in result.detections
    ]
    return {
        "detected": len(result.detections) > 0,
        "count": len(result.detections),
        "confidence": max([d.confidence for d in result.detections], default=0.0),
        "detections": detections_out,
        "image_data": result.frame_data_uri,
    }
