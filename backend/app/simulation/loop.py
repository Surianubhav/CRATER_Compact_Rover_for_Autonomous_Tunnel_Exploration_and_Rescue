"""
Background asyncio task that ticks MissionState roughly once a second
and broadcasts the resulting snapshot to connected WebSocket clients.
This is the ONLY place MissionState.tick() is called from -- REST
endpoints read state, they never advance the simulation themselves, so
behaviour stays identical whether or not any client is currently
watching.
"""
from __future__ import annotations

import asyncio
import time

from app.config.settings import get_settings
from app.services.mission_state import get_mission_state
from app.websocket.manager import get_hub


async def run_simulation_loop():
    settings = get_settings()
    mission = get_mission_state()
    hub = get_hub()
    last = time.time()

    while True:
        await asyncio.sleep(settings.SIMULATION_TICK_SECONDS)
        now = time.time()
        dt = now - last
        last = now

        snapshot = mission.tick(dt)
        payload = snapshot.model_dump(mode="json")

        await hub.telemetry.broadcast(payload)
        await hub.thermal.broadcast({"detections": payload["detections"], "mission_time_s": payload["mission_time_s"]})
        await hub.events.broadcast({
            "events": [e.model_dump(mode="json") for e in mission.events.query(limit=20)],
            "alerts": payload["alerts"],
        })
