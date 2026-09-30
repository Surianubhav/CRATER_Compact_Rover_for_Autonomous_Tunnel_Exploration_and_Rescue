"""
Minimal per-channel WebSocket broadcast manager. Three logical channels
are exposed (telemetry, thermal, events) as the brief asks for, even
though today they're all fed by the same MissionState tick -- keeping
them separate endpoints means a future dedicated high-rate thermal
stream (for example) can be pointed at /ws/thermal without touching
/ws/telemetry clients.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket


class Channel:
    def __init__(self, name: str):
        self.name = name
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, payload: dict):
        message = json.dumps(payload, default=str)
        dead = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


class WebSocketHub:
    def __init__(self):
        self.telemetry = Channel("telemetry")
        self.thermal = Channel("thermal")
        self.events = Channel("events")


_hub: WebSocketHub | None = None


def get_hub() -> WebSocketHub:
    global _hub
    if _hub is None:
        _hub = WebSocketHub()
    return _hub
