"""
Mesh relay node simulator.

Chain topology is fixed: BASE - N1 - N2 - N3 - N4 - N5 - ROVER, matching
the product brief's mesh example. When a node in the chain is marked
LOST, every node (and the rover) downstream of it becomes UNREACHABLE --
this is what powers the communication-loss demo scenario.
"""
from __future__ import annotations

import random

from app.models.schemas import MeshNode, NodeState
from app.simulation import mine_map

CHAIN_ORDER = ["N1", "N2", "N3", "N4", "N5"]


class NodeSimulator:
    def __init__(self):
        self._rng = random.Random(11)
        self.deployed: list[str] = list(CHAIN_ORDER)  # all 5 deployed at mission start
        self.lost_node_id: str | None = None  # set by the comms-lost dev scenario
        self._extra_relays = 0  # e.g. the "sixth node" deployed on person detection

    def deploy_relay(self) -> str:
        self._extra_relays += 1
        new_id = f"N{5 + self._extra_relays}"
        self.deployed.append(new_id)
        return new_id

    def relays_deployed_count(self) -> int:
        return len(self.deployed)

    def set_comms_lost(self, node_id: str | None):
        self.lost_node_id = node_id

    def clear_comms_lost(self):
        self.lost_node_id = None

    def position_for(self, node_id: str) -> tuple[float, float]:
        if node_id in mine_map.ALL_WAYPOINTS:
            wp = mine_map.node_position(node_id)
            return wp.x_m, wp.y_m
        # extra relays: place a bit further out than the last chain node
        idx = int(node_id[1:])
        base = mine_map.node_position(CHAIN_ORDER[-1])
        return base.x_m + (idx - 5) * 8, base.y_m + (idx - 5) * 6

    def step(self, dt_s: float) -> list[MeshNode]:
        nodes: list[MeshNode] = []
        broken = False
        lost_index = CHAIN_ORDER.index(self.lost_node_id) if self.lost_node_id in CHAIN_ORDER else None

        for i, node_id in enumerate(self.deployed):
            x, y = self.position_for(node_id)
            chain_i = CHAIN_ORDER.index(node_id) if node_id in CHAIN_ORDER else 99

            if self.lost_node_id and chain_i == lost_index:
                state = NodeState.LOST
                rssi = -95.0
                battery = max(0.0, 8.0 - dt_s * 0.01)
                latency = 0.0
                throughput = 0.0
                heartbeat_age = 999.0
                broken = True
            elif self.lost_node_id and lost_index is not None and chain_i > lost_index:
                state = NodeState.UNREACHABLE
                rssi = -99.0
                battery = self._rng.uniform(20, 90)
                latency = 0.0
                throughput = 0.0
                heartbeat_age = 999.0
            else:
                jitter = self._rng.uniform(-2, 2)
                state = NodeState.ONLINE if self._rng.random() > 0.015 else NodeState.WEAK
                rssi = round(-58 - i * 4 + jitter, 1)
                battery = round(max(5.0, 92 - i * 3 + self._rng.uniform(-1, 1)), 1)
                latency = round(28 + i * 9 + self._rng.uniform(-3, 3), 1)
                throughput = round(max(4.0, 220 - i * 18 + self._rng.uniform(-5, 5)), 1)
                heartbeat_age = round(self._rng.uniform(0.2, 2.4), 1)

            nodes.append(
                MeshNode(
                    id=node_id,
                    x_m=x,
                    y_m=y,
                    state=state,
                    battery_pct=round(battery, 1),
                    rssi_dbm=rssi,
                    latency_ms=latency,
                    throughput_kbps=throughput,
                    last_heartbeat_age_s=heartbeat_age,
                )
            )
        return nodes
