from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.adapters.thermal_adapter import get_thermal_adapter
from app.api import (
    alerts, annotations, commands, detections, events, mission, nodes,
    replay, report, route, scenario, telemetry, thermal,
)
from app.config.settings import BACKEND_ROOT, get_settings
from app.simulation.loop import run_simulation_loop
from app.ws_routes import router as ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("minesweeper")

settings = get_settings()

app = FastAPI(title="MINESWEEPER Mine Reconnaissance Console API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (mission, telemetry, nodes, alerts, commands, events, annotations,
          detections, thermal, route, report, scenario, replay):
    app.include_router(r.router)

app.include_router(ws_router)


@app.get("/health")
def health():
    adapter = get_thermal_adapter()
    return {
        "status": "ok",
        "simulation_enabled": settings.SIMULATION_ENABLED,
        "thermal_state": adapter.state.value,
    }


@app.on_event("startup")
async def on_startup():
    logger.info("MINESWEEPER backend starting up")
    loop = asyncio.get_event_loop()
    # model loading can be slow (torch import + weights) -- keep it off
    # the event loop so /health etc. respond immediately either way
    loop.run_in_executor(None, get_thermal_adapter().load)

    if settings.SIMULATION_ENABLED:
        asyncio.create_task(run_simulation_loop())
    else:
        logger.warning("Simulation disabled (MINESWEEPER_SIMULATION_ENABLED=0) -- "
                        "mission state will not advance without a live hardware feed.")


# Serve the operator console frontend directly from the backend so a
# single `uvicorn app.main:app` is enough to run the whole system in
# development. This does not affect the REST/WebSocket API above --
# mounted last, and only for paths that aren't already API routes.
_frontend_dir = BACKEND_ROOT.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
