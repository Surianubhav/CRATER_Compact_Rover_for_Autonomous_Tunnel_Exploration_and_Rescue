"""
Simulated gas/environment telemetry.

Produces the SAME normalized fields the hardware adapter produces
(ch4_pct, co_ppm, o2_pct, temperature_c, humidity_pct, pressure_pa) so it
can be fed into `telemetry_builder.build_telemetry_frame()` through the
identical code path a live feed would use. Never presented as LIVE data
by the caller -- `MissionState` stamps every frame it produces with
`DataSource.SIMULATED` unless a real hardware payload has been ingested
via /api/telemetry/ingest.

Demo scenario A (nominal operation) calls for "CH4 caution near 150m"
and "47C hotspot near 180m" -- this simulator reproduces that by biasing
readings toward those distance bands, on top of small continuous random
walk drift so the strip never looks perfectly static.
"""
from __future__ import annotations

import math
import random


class TelemetrySimulator:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.ch4_pct = 0.18
        self.co_ppm = 6.0
        self.o2_pct = 20.9
        self.temperature_c = 25.5
        self.humidity_pct = 58.0
        self.pressure_pa = 97600.0

    @staticmethod
    def _bump(distance_m: float, center_m: float, width_m: float, amplitude: float) -> float:
        return amplitude * math.exp(-((distance_m - center_m) ** 2) / (2 * width_m ** 2))

    def step(self, rover_distance_m: float, dt_s: float) -> dict:
        rng = self._rng

        # base random-walk drift
        self.ch4_pct = max(0.02, self.ch4_pct + rng.uniform(-0.01, 0.012) * dt_s)
        self.co_ppm = max(0.5, self.co_ppm + rng.uniform(-0.4, 0.5) * dt_s)
        self.o2_pct = min(20.95, max(18.5, self.o2_pct + rng.uniform(-0.01, 0.01) * dt_s))
        self.temperature_c = max(20.0, self.temperature_c + rng.uniform(-0.03, 0.04) * dt_s)
        self.humidity_pct = min(95.0, max(35.0, self.humidity_pct + rng.uniform(-0.15, 0.15) * dt_s))
        self.pressure_pa = self.pressure_pa + rng.uniform(-6, 6) * dt_s

        # location-based bumps (demo scenario A)
        ch4_bump = self._bump(rover_distance_m, center_m=150, width_m=18, amplitude=0.85)
        heat_bump = self._bump(rover_distance_m, center_m=180, width_m=12, amplitude=22.0)

        return {
            "ch4_pct": round(self.ch4_pct + ch4_bump, 3),
            "co_ppm": round(self.co_ppm, 2),
            "o2_pct": round(self.o2_pct, 2),
            "temperature_c": round(self.temperature_c + heat_bump * 0.15, 2),
            "humidity_pct": round(self.humidity_pct, 2),
            "pressure_pa": round(self.pressure_pa, 1),
            "hotspot_c": round(22.0 + heat_bump, 1),
            "hotspot_active": heat_bump > 4.0,
            "hotspot_x_m": 180,
            "hotspot_y_m": 38,
        }
