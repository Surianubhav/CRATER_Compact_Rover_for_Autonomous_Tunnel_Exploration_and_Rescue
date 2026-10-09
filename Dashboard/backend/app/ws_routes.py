"""
WebSocket endpoints. Each connection just joins a broadcast channel and
otherwise sits idle -- all the actual state changes are pushed from
app/simulation/loop.py. Kept as a separate module (rather than inline in
main.py) so main.py stays a thin composition root.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.mission_state import get_mission_state
from app.websocket.manager import get_hub

router = APIRouter()


async def _serve(websocket: WebSocket, channel_name: str):
    hub = get_hub()
    channel = getattr(hub, channel_name)
    await channel.connect(websocket)
    try:
        # send an immediate snapshot on connect so the UI isn't blank
        # until the next simulation tick
        mission = get_mission_state()
        if mission._history:
            await websocket.send_json(mission._history[-1][1])
        while True:
            # clients don't need to send anything; just keep the socket
            # open and drop it cleanly on disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await channel.disconnect(websocket)


@router.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await _serve(websocket, "telemetry")


@router.websocket("/ws/thermal")
async def ws_thermal(websocket: WebSocket):
    await _serve(websocket, "thermal")


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await _serve(websocket, "events")
