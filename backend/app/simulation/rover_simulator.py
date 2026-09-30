"""
Rover motion + battery simulation.

Drives a single "distance travelled along MAIN_PATH" state variable that
both autonomous exploration and issued rover commands (go to node,
return to entry, hold, ...) manipulate, so the map/rover marker/mesh/
telemetry all stay consistent with wherever the rover "is" right now.
"""
from __future__ import annotations

import random

from app.models.schemas import ControlState, RoverPosition, RoverState
from app.simulation import mine_map

ROVER_SPEED_MPS = 0.35
# Calibrated so ~47 minutes of mission time drains battery to ~37%,
# matching the reference console's example readout.
BATTERY_DRAIN_PCT_PER_S = 63.0 / 2832.0
TRAIL_SAMPLE_INTERVAL_M = 4.0


class RoverSimulator:
    def __init__(self):
        self.distance_m = 0.0
        self.path_travelled_m = 0.0
        self.battery_pct = 100.0
        self.control_state = ControlState.AUTONOMOUS
        self.target_distance_m = 214.0  # nominal default per demo scenario A
        self.holding = False
        self.trail: list[RoverPosition] = []
        self._last_trail_dist = -999.0
        self._rng = random.Random(7)
        self._jitter = 0.0

    def set_target(self, distance_m: float, control_state: ControlState = ControlState.COMMAND):
        self.target_distance_m = max(0.0, min(distance_m, mine_map.MAIN_PATH_TOTAL_M))
        if not self.holding:
            self.control_state = control_state

    def hold(self):
        self.holding = True
        self.control_state = ControlState.HOLDING

    def resume(self):
        self.holding = False
        self.control_state = ControlState.AUTONOMOUS

    def explore_unexplored(self):
        self.set_target(min(self.distance_m + 40, mine_map.MAIN_PATH_TOTAL_M))

    def step(self, dt_s: float, link_lost: bool) -> RoverState:
        if not self.holding and not link_lost:
            direction = 1.0 if self.target_distance_m >= self.distance_m else -1.0
            step_m = ROVER_SPEED_MPS * dt_s
            remaining = abs(self.target_distance_m - self.distance_m)
            move = min(step_m, remaining)
            self.distance_m += direction * move
            self.path_travelled_m += move
            self._jitter += self._rng.uniform(0, move * 0.08)
            self.path_travelled_m_display = self.path_travelled_m + self._jitter

            if remaining <= 0.05 and self.control_state == ControlState.COMMAND:
                self.control_state = ControlState.AUTONOMOUS
                # once a commanded goal is reached, resume a gentle default creep
                if self.target_distance_m < mine_map.MAIN_PATH_TOTAL_M - 1:
                    self.target_distance_m = min(
                        self.target_distance_m + 30, mine_map.MAIN_PATH_TOTAL_M
                    )

            self.battery_pct = max(0.0, self.battery_pct - BATTERY_DRAIN_PCT_PER_S * dt_s)

        x, y, heading = mine_map.position_at_distance(self.distance_m)

        if self.distance_m - self._last_trail_dist >= TRAIL_SAMPLE_INTERVAL_M:
            self.trail.append(RoverPosition(x_m=x, y_m=y, heading_deg=heading))
            self.trail = self.trail[-120:]
            self._last_trail_dist = self.distance_m

        return RoverState(
            control_state=self.control_state,
            battery_pct=round(self.battery_pct, 1),
            distance_from_entry_m=round(self.distance_m, 1),
            path_travelled_m=round(getattr(self, "path_travelled_m_display", self.path_travelled_m), 1),
            position=RoverPosition(x_m=x, y_m=y, heading_deg=heading),
            trail=list(self.trail),
            ghosted=link_lost,
        )
