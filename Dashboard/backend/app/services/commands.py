"""
Rover command queue.

Every issued command goes through a real, timed state machine instead of
completing instantly:

    SENT -> ACKNOWLEDGED -> EXECUTING -> COMPLETE | FAILED

or, if the link is down when the operator issues it:

    QUEUED_OFFLINE ("WILL SEND ON RECONNECT") -> SENT -> ... as above,
    once the link comes back.

The command only actually moves the rover once it reaches EXECUTING, so
the queue state and the rover's motion stay honestly in sync.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.models.schemas import CommandStatus, ControlState, QueuedCommand
from app.simulation import mine_map
from app.simulation.node_simulator import CHAIN_ORDER
from app.simulation.rover_simulator import RoverSimulator

ACK_DELAY_S = 1.4
EXEC_START_DELAY_S = 1.2

LABELS = {
    "return_to_entry": "Return to Entry",
    "return_to_node": "Return to Node {target}",
    "go_to_node": "Go to Node {target}",
    "explore_unexplored": "Explore Unexplored",
    "go_to_marker": "Go to Selected Marker",
    "hold_position": "Hold Position",
    "resume": "Resume",
}


@dataclass
class _Internal:
    stage_started_at: float
    kind: str
    target: str | None
    target_distance_m: float | None = None


class CommandService:
    def __init__(self):
        self.queue: list[QueuedCommand] = []
        self._internal: dict[str, _Internal] = {}
        self._next_num = 14  # cosmetic: reference image example starts around CMD-014

    def _new_id(self) -> str:
        self._next_num += 1
        return f"CMD-{self._next_num:03d}"

    def issue(self, cmd_type: str, target: str | None, link_lost: bool, selected_marker_pos=None) -> QueuedCommand:
        cmd_id = self._new_id()
        label = LABELS.get(cmd_type, cmd_type).format(target=target or "")
        now = time.time()

        target_distance_m = None
        if cmd_type == "return_to_entry":
            target_distance_m = 0.0
        elif cmd_type in ("return_to_node", "go_to_node") and target in mine_map.ALL_WAYPOINTS:
            wp = mine_map.node_position(target)
            target_distance_m = self._nearest_path_distance(wp.x_m, wp.y_m)
        elif cmd_type == "explore_unexplored":
            target_distance_m = None  # resolved at execution time
        elif cmd_type == "go_to_marker" and selected_marker_pos is not None:
            target_distance_m = self._nearest_path_distance(*selected_marker_pos)

        status = CommandStatus.QUEUED_OFFLINE if link_lost else CommandStatus.SENT
        cmd = QueuedCommand(
            id=cmd_id, type=cmd_type, label=label, target=target,
            status=status, issued_at=now,
            eta_s=self._estimate_eta(target_distance_m),
        )
        self.queue.insert(0, cmd)
        self._internal[cmd_id] = _Internal(stage_started_at=now, kind=cmd_type, target=target,
                                            target_distance_m=target_distance_m)
        return cmd

    @staticmethod
    def _nearest_path_distance(x_m: float, y_m: float) -> float:
        best_d, best_dist = float("inf"), 0.0
        for i, wp in enumerate(mine_map.MAIN_PATH):
            d = (wp.x_m - x_m) ** 2 + (wp.y_m - y_m) ** 2
            if d < best_d:
                best_d, best_dist = d, mine_map.MAIN_PATH_CUM_DIST[i]
        return best_dist

    @staticmethod
    def _estimate_eta(target_distance_m: float | None) -> float | None:
        if target_distance_m is None:
            return None
        return round(abs(target_distance_m) / 0.35, 0)  # ROVER_SPEED_MPS

    def tick(self, rover: RoverSimulator, link_lost: bool):
        now = time.time()
        for cmd in self.queue:
            internal = self._internal.get(cmd.id)
            if internal is None:
                continue

            if cmd.status == CommandStatus.QUEUED_OFFLINE:
                if not link_lost:
                    cmd.status = CommandStatus.SENT
                    internal.stage_started_at = now
                continue

            if link_lost and cmd.status in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED, CommandStatus.EXECUTING):
                # link dropped mid-flight: freeze progress, don't fail outright
                continue

            if cmd.status == CommandStatus.SENT and now - internal.stage_started_at >= ACK_DELAY_S:
                cmd.status = CommandStatus.ACKNOWLEDGED
                internal.stage_started_at = now

            elif cmd.status == CommandStatus.ACKNOWLEDGED and now - internal.stage_started_at >= EXEC_START_DELAY_S:
                cmd.status = CommandStatus.EXECUTING
                internal.stage_started_at = now
                self._begin_execution(cmd, internal, rover)

            elif cmd.status == CommandStatus.EXECUTING:
                self._check_execution_complete(cmd, internal, rover)

    def _begin_execution(self, cmd: QueuedCommand, internal: _Internal, rover: RoverSimulator):
        if internal.kind == "hold_position":
            rover.hold()
        elif internal.kind == "resume":
            rover.resume()
        elif internal.kind == "explore_unexplored":
            rover.explore_unexplored()
            internal.target_distance_m = rover.target_distance_m
        elif internal.target_distance_m is not None:
            rover.set_target(internal.target_distance_m)

    def _check_execution_complete(self, cmd: QueuedCommand, internal: _Internal, rover: RoverSimulator):
        if internal.kind in ("hold_position", "resume"):
            cmd.status = CommandStatus.COMPLETE
            return
        if internal.target_distance_m is None:
            cmd.status = CommandStatus.COMPLETE
            return
        if abs(rover.distance_m - internal.target_distance_m) <= 0.3:
            cmd.status = CommandStatus.COMPLETE

    def recent(self, limit: int = 12) -> list[QueuedCommand]:
        return self.queue[:limit]
