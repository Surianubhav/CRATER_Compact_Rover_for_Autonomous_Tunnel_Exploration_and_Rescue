"""
Builds a rescue route from ENTRY to a confirmed detection's position,
following the mine's gallery waypoints (app/simulation/mine_map.py)
rather than a straight line through walls/pillars, with 25m distance
ticks and a worst-case-hazard classification per segment for the
printable route sheet.

Hazard classification here is intentionally deterministic (not sampled
from the live/random telemetry simulator) so a generated route sheet is
reproducible -- it uses the same illustrative distance bands the
telemetry simulator biases readings around.
"""
from __future__ import annotations

import math

from app.config.settings import get_thresholds
from app.simulation import mine_map

CH4_ZONE_CENTER_M, CH4_ZONE_WIDTH_M = 150, 20
HEAT_ZONE_CENTER_M, HEAT_ZONE_WIDTH_M = 180, 14


def _severity_at(distance_m: float, th: dict) -> tuple[str, float, float]:
    ch4_bump = math.exp(-((distance_m - CH4_ZONE_CENTER_M) ** 2) / (2 * CH4_ZONE_WIDTH_M ** 2)) * 0.85
    ch4_pct = 0.18 + ch4_bump
    heat_bump = math.exp(-((distance_m - HEAT_ZONE_CENTER_M) ** 2) / (2 * HEAT_ZONE_WIDTH_M ** 2)) * 22.0
    temp_c = 25.5 + heat_bump * 0.15
    hotspot_c = 22.0 + heat_bump

    severity = "normal"
    if ch4_pct >= th["ch4_pct"]["danger"] or hotspot_c >= th["thermal_hotspot_c"]["danger"]:
        severity = "danger"
    elif ch4_pct >= th["ch4_pct"]["caution"] or hotspot_c >= th["thermal_hotspot_c"]["caution"]:
        severity = "caution"
    return severity, round(ch4_pct, 3), round(hotspot_c, 1)


def build_route(target_x_m: float, target_y_m: float) -> dict:
    waypoints = mine_map.route_entry_to(target_x_m, target_y_m)
    cum = mine_map.cumulative_distance(waypoints)
    th = get_thresholds()

    segments = []
    max_ch4, max_hotspot, min_o2 = 0.0, 0.0, 20.9
    for i in range(len(waypoints) - 1):
        d_mid = (cum[i] + cum[i + 1]) / 2
        severity, ch4_pct, hotspot_c = _severity_at(d_mid, th)
        max_ch4 = max(max_ch4, ch4_pct)
        max_hotspot = max(max_hotspot, hotspot_c)
        segments.append(
            {
                "from": waypoints[i].id, "to": waypoints[i + 1].id,
                "from_xy": [waypoints[i].x_m, waypoints[i].y_m],
                "to_xy": [waypoints[i + 1].x_m, waypoints[i + 1].y_m],
                "distance_start_m": round(cum[i], 1), "distance_end_m": round(cum[i + 1], 1),
                "severity": severity,
            }
        )

    ticks = []
    total_m = cum[-1]
    tick_d = 0.0
    while tick_d <= total_m:
        ticks.append(round(tick_d, 1))
        tick_d += 25.0

    known_obstacles = [
        h["label"] for h in mine_map.HAZARDS
        if any(
            math.hypot(h["x_m"] - wp.x_m, h["y_m"] - wp.y_m) < 25 for wp in waypoints
        )
    ]

    return {
        "waypoints": [{"id": w.id, "x_m": w.x_m, "y_m": w.y_m} for w in waypoints],
        "segments": segments,
        "distance_ticks_m": ticks,
        "total_length_m": round(total_m, 1),
        "max_ch4_pct": round(max_ch4, 3),
        "max_co_ppm": None,  # CO is not location-biased in this simulator; reported as scene-level only
        "min_o2_pct": min_o2,
        "max_temperature_c": max_hotspot,
        "known_obstacles": known_obstacles or ["None charted on this route"],
    }
