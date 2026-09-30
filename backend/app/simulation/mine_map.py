"""
Static description of the mine layout used by:
  - the rover simulator (path the rover walks along)
  - the route planner (entry -> person path, follows galleries not walls)
  - the map API (so the frontend SVG map and the backend agree on geometry)

Coordinates are METERS relative to ENTRY at (0, 0). There is no GPS in an
underground mine, so this is a purely local/relative coordinate system, as
specified by the product brief. This is a stylised layout (not a survey),
loosely reproducing the long-gallery / rectangular-pillar / crosscut /
dead-end / roof-fall structure described in the reference design.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Waypoint:
    id: str
    x_m: float
    y_m: float


# Main gallery spine the rover follows from ENTRY, plus a side crosscut
# and a dead end. Ordered so consecutive points are walkable (used both to
# animate the rover and to route rescue paths along real mine geometry
# instead of a straight line through pillars).
MAIN_PATH: list[Waypoint] = [
    Waypoint("ENTRY", 0, 0),
    Waypoint("WP1", 35, 6),
    Waypoint("WP2", 78, 10),
    Waypoint("N1", 92, 12),
    Waypoint("WP3", 128, 18),
    Waypoint("N2", 150, 22),
    Waypoint("WP4", 172, 30),
    Waypoint("N3", 188, 34),
    Waypoint("WP5", 205, 40),
    Waypoint("N4", 214, 46),
    Waypoint("WP6", 222, 54),
    Waypoint("PERSON_ZONE", 231, 58),  # nominal person-detection location, ~231m distance
    Waypoint("WP7", 238, 64),
    Waypoint("N5", 248, 70),
    Waypoint("WP8", 255, 78),
    Waypoint("ROVER_FRONTIER", 262, 84),
]

# Side branch off WP3 leading to a collapsed / roof-fall dead end -- used
# for the "blocked area" callout on the map, not currently traversed by
# the rover's default route.
DEAD_END_BRANCH: list[Waypoint] = [
    Waypoint("WP3", 128, 18),
    Waypoint("DE1", 118, 55),
    Waypoint("ROOF_FALL", 112, 78),
]

NODE_IDS = ["N1", "N2", "N3", "N4", "N5"]

HAZARDS = [
    {"id": "HZ-ROOFALL-1", "type": "roof_fall", "x_m": 112, "y_m": 78, "label": "ROOF FALL - BLOCKED"},
    {"id": "HZ-GAS-1", "type": "gas", "x_m": 172, "y_m": 32, "label": "CH4 CAUTION ZONE"},
    {"id": "HZ-HEAT-1", "type": "heat", "x_m": 180, "y_m": 38, "label": "47C HOTSPOT"},
]

# Gallery corridor half-widths (meters) used when rendering the occupancy
# polygon / hatching in the frontend map -- kept here so backend geometry
# and frontend rendering can't silently drift apart.
GALLERY_HALF_WIDTH_M = 9.0
DEAD_END_HALF_WIDTH_M = 7.0


def _by_id(points: list[Waypoint]) -> dict:
    return {p.id: p for p in points}


ALL_WAYPOINTS = _by_id(MAIN_PATH + DEAD_END_BRANCH)


def node_position(node_id: str) -> Waypoint:
    return ALL_WAYPOINTS[node_id]


def path_as_tuples(points: list[Waypoint]) -> list[tuple]:
    return [(p.x_m, p.y_m) for p in points]


def cumulative_distance(points: list[Waypoint]) -> list[float]:
    """Running distance (m) travelled along a sequence of waypoints."""
    out = [0.0]
    for a, b in zip(points, points[1:]):
        dx, dy = b.x_m - a.x_m, b.y_m - a.y_m
        out.append(out[-1] + (dx ** 2 + dy ** 2) ** 0.5)
    return out


MAIN_PATH_CUM_DIST = cumulative_distance(MAIN_PATH)
MAIN_PATH_TOTAL_M = MAIN_PATH_CUM_DIST[-1]


def position_at_distance(distance_m: float) -> tuple[float, float, float]:
    """
    Interpolate (x_m, y_m, heading_deg) at a given travelled distance along
    MAIN_PATH. Clamps to the ends of the path.
    """
    distance_m = max(0.0, min(distance_m, MAIN_PATH_TOTAL_M))
    for i in range(len(MAIN_PATH) - 1):
        d0, d1 = MAIN_PATH_CUM_DIST[i], MAIN_PATH_CUM_DIST[i + 1]
        if d0 <= distance_m <= d1 or i == len(MAIN_PATH) - 2:
            seg_len = max(d1 - d0, 1e-6)
            t = (distance_m - d0) / seg_len
            t = max(0.0, min(1.0, t))
            a, b = MAIN_PATH[i], MAIN_PATH[i + 1]
            x = a.x_m + (b.x_m - a.x_m) * t
            y = a.y_m + (b.y_m - a.y_m) * t
            heading = _heading(a, b)
            return x, y, heading
    last = MAIN_PATH[-1]
    return last.x_m, last.y_m, 0.0


def _heading(a: Waypoint, b: Waypoint) -> float:
    import math
    dx, dy = b.x_m - a.x_m, b.y_m - a.y_m
    return (math.degrees(math.atan2(dx, -dy))) % 360  # 0deg = "up"/into the mine


def route_entry_to(target_x: float, target_y: float) -> list[Waypoint]:
    """
    Build a rescue route from ENTRY to the nearest point on MAIN_PATH to
    (target_x, target_y), following gallery waypoints rather than a
    straight line through pillars/walls.
    """
    # find nearest waypoint on the main spine to the target
    best_i, best_d = 0, float("inf")
    for i, wp in enumerate(MAIN_PATH):
        d = (wp.x_m - target_x) ** 2 + (wp.y_m - target_y) ** 2
        if d < best_d:
            best_d, best_i = d, i
    route = list(MAIN_PATH[: best_i + 1])
    last = route[-1]
    if (last.x_m, last.y_m) != (target_x, target_y):
        route.append(Waypoint("TARGET", target_x, target_y))
    return route
