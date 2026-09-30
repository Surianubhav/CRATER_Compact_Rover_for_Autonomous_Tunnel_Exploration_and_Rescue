"""
Central backend configuration.

Everything that might differ between machines, environments, or
deployments (model path, ports, simulation on/off, CORS origins) lives
here and is overridable via environment variables / .env. Nothing else
in the backend should hardcode a filesystem path or a "magic number"
that belongs here.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

# backend/app/config/settings.py -> parents[2] == backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


class Settings:
    # ---- Server ----------------------------------------------------
    HOST: str = os.getenv("MINESWEEPER_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("MINESWEEPER_PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("MINESWEEPER_CORS_ORIGINS", "*").split(",")
    ]

    # ---- Thermal model ----------------------------------------------
    # Default resolves to backend/models/yolov8_thermal_best.pt, which is
    # where the existing trained model already lives in this repo. Override
    # with MINESWEEPER_MODEL_PATH if the model is stored elsewhere.
    MODEL_PATH: Path = Path(
        os.getenv(
            "MINESWEEPER_MODEL_PATH",
            str(BACKEND_ROOT / "models" / "yolov8_thermal_best.pt"),
        )
    )
    MODEL_CONF_THRESHOLD: float = _env_float("MINESWEEPER_MODEL_CONF", 0.25)
    # If the real model / ultralytics / torch isn't installed on this
    # machine yet, the thermal adapter degrades to an explicit
    # MODEL_ERROR / DISCONNECTED state rather than crashing the API or
    # silently fabricating detections. This flag lets a developer force
    # that state off (e.g. CI) even if the model *is* present.
    THERMAL_ENABLED: bool = _env_bool("MINESWEEPER_THERMAL_ENABLED", True)

    # ---- Simulation ---------------------------------------------------
    # The rover/gas/mesh/event simulator that stands in for hardware
    # telemetry until the hardware team's live feed is wired into
    # /api/telemetry/ingest. This must be explicit in the UI (LIVE vs
    # SIMULATED) and never presented as real sensor data.
    SIMULATION_ENABLED: bool = _env_bool("MINESWEEPER_SIMULATION_ENABLED", True)
    SIMULATION_TICK_SECONDS: float = _env_float("MINESWEEPER_SIM_TICK", 1.0)

    # ---- Data source labelling -----------------------------------------
    # LIVE = real hardware feed via /api/telemetry/ingest
    # SIMULATED = internal simulator (default until hardware is wired up)
    TELEMETRY_SOURCE_MODE: str = os.getenv("MINESWEEPER_TELEMETRY_MODE", "SIMULATED")

    # ---- Misc -----------------------------------------------------------
    MISSION_CODENAME: str = os.getenv("MINESWEEPER_MISSION_CODE", "MSW-014")
    MISSION_LOCATION: str = os.getenv("MINESWEEPER_MISSION_LOCATION", "Level 2, East Gallery")
    REPLAY_HISTORY_SECONDS: int = int(os.getenv("MINESWEEPER_REPLAY_HISTORY_S", "3600"))

    THRESHOLDS_PATH: Path = BACKEND_ROOT / "app" / "config" / "thresholds.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_thresholds() -> dict:
    """
    Illustrative gas / environmental thresholds, kept in one JSON file
    instead of scattered through the codebase. These are PLACEHOLDER
    values until the mine authority / hardware team supplies calibrated
    limits -- see thresholds.json's own "_note" field.
    """
    with open(get_settings().THRESHOLDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
