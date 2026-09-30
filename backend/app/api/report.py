from __future__ import annotations

import io
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.services.mission_state import get_mission_state

router = APIRouter(prefix="/api", tags=["report"])


def _build_report_data() -> dict:
    mission = get_mission_state()
    snap = mission._history[-1][1] if mission._history else mission.tick(0.0).model_dump(mode="json")

    confirmed = [d for d in snap["detections"] if d["status"] == "CONFIRMED"]
    gas_peaks = {g["key"]: {"label": g["label"], "peak": g["peak_value"], "unit": g["unit"]}
                 for g in snap["telemetry"]["gases"]}
    temp_reading = next((e for e in snap["telemetry"]["environment"] if e["key"] == "temperature_c"), None)

    node_log = [
        {"id": n["id"], "state": n["state"], "battery_pct": n["battery_pct"]}
        for n in snap["nodes"]
    ]
    outages = [e.model_dump(mode="json") for e in mission.events.query(category=None) if e.category.value == "COMMS"]

    return {
        "mission_id": snap["mission_id"],
        "date": time.strftime("%Y-%m-%d"),
        "operator": "Operator role",  # no auth/user system yet -- see README assumptions
        "duration_s": snap["mission_time_s"],
        "distance_explored_m": snap["rover"]["distance_from_entry_m"],
        "path_travelled_m": snap["rover"]["path_travelled_m"],
        "area_mapped_note": "Explored-corridor length only; area (m\u00b2) requires the SLAM/occupancy module.",
        "confirmed_detections": confirmed,
        "gas_peaks": gas_peaks,
        "temperature_max_c": temp_reading["peak_value"] if temp_reading else None,
        "node_deployment_log": node_log,
        "communication_outages": outages[:20],
        "commands": snap["commands"],
        "annotations": snap["annotations"],
        "event_log_excerpt": [e.model_dump(mode="json") for e in mission.events.query(limit=40)],
    }


@router.get("/report")
def get_report():
    return _build_report_data()


@router.get("/report/export.json")
def export_report_json():
    return JSONResponse(content=_build_report_data())


@router.get("/report/export.pdf")
def export_report_pdf():
    data = _build_report_data()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        return JSONResponse(
            status_code=501,
            content={
                "error": "reportlab not installed",
                "detail": "pip install reportlab (see backend/requirements.txt) to enable PDF export. "
                          "Use /api/report/export.json or the in-app print-ready report view meanwhile.",
            },
        )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    def line(text: str, size=10, dy=6 * mm, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(20 * mm, y, text)
        y -= dy

    line(f"MINESWEEPER Mission Report \u2014 {data['mission_id']}", 16, 10 * mm, bold=True)
    line(f"Date: {data['date']}    Operator: {data['operator']}")
    line(f"Duration: {int(data['duration_s'] // 60):02d}:{int(data['duration_s'] % 60):02d}")
    line(f"Distance explored: {data['distance_explored_m']} m    Path travelled: {data['path_travelled_m']} m")
    y -= 4 * mm
    line("Confirmed detections", 12, bold=True)
    if data["confirmed_detections"]:
        for d in data["confirmed_detections"]:
            line(f"  {d['id']} \u2014 confidence {d['confidence']:.0%} \u2014 {d['distance_m']} m from entry")
    else:
        line("  None")
    y -= 4 * mm
    line("Gas peaks", 12, bold=True)
    for key, g in data["gas_peaks"].items():
        line(f"  {g['label']}: {g['peak']} {g['unit']}")
    y -= 4 * mm
    line(f"Maximum temperature: {data['temperature_max_c']} \u00b0C", 12, bold=True)
    y -= 4 * mm
    line("Node deployment log", 12, bold=True)
    for n in data["node_deployment_log"]:
        line(f"  {n['id']}: {n['state']} \u2014 battery {n['battery_pct']}%")
    y -= 4 * mm
    line("Communication outages", 12, bold=True)
    if data["communication_outages"]:
        for o in data["communication_outages"][:8]:
            line(f"  {o['clock']} \u2014 {o['message']}")
    else:
        line("  None recorded")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    return Response(content=pdf_bytes, media_type="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename={data['mission_id']}-report.pdf"})
