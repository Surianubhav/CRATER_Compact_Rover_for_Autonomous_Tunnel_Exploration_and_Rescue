"""
MissionState is the one place that owns "what is currently true" about
the mission: rover position, link/node health, telemetry, alerts,
detections, command queue, annotations, and a rolling replay history.

The simulation loop (app/simulation/loop.py) calls `tick()` roughly once
a second. The REST API and WebSocket broadcasts both just read a
`snapshot()` of this object -- neither owns any state of its own. This
is what section 28/30 of the brief calls for: one application-state
architecture, and the same normalized path for both simulated and real
(hardware / thermal-model) data.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from app.adapters.hardware_adapter import HardwareAdapterError, normalize_hardware_payload
from app.config.settings import get_settings
from app.models.schemas import (
    Alert, AlertTier, Annotation, ControlState, DataSource, DetectionStatus, EventCategory,
    LinkState, LinkStatus, MissionSnapshot, NodeState, RoverPosition, ThermalDetection,
)
from app.services.alerts import AlertService
from app.services.commands import CommandService
from app.services.event_log import EventLogService
from app.services.telemetry_builder import build_telemetry_frame
from app.simulation import mine_map
from app.simulation.node_simulator import CHAIN_ORDER, NodeSimulator
from app.simulation.rover_simulator import RoverSimulator
from app.simulation.telemetry_simulator import TelemetrySimulator

HARDWARE_FRESHNESS_S = 10.0
LOW_BATTERY_PCT = 20.0


class MissionState:
    def __init__(self):
        settings = get_settings()
        self.mission_id = settings.MISSION_CODENAME
        self.mission_location = settings.MISSION_LOCATION
        self.start_time = time.time()

        self.rover = RoverSimulator()
        self.nodes = NodeSimulator()
        self.telemetry_sim = TelemetrySimulator()
        self.alerts = AlertService()
        self.events = EventLogService()
        self.commands = CommandService()
        self.detections: dict[str, ThermalDetection] = {}
        self.annotations: list[Annotation] = []

        self._last_hardware_payload: dict | None = None
        self._last_hardware_ts: float = 0.0

        self.replay_mode = False
        self.replay_time_s: float | None = None
        self._history: list[tuple[float, dict]] = []  # (mission_time_s, snapshot dict)
        self._max_history = int(settings.REPLAY_HISTORY_SECONDS / max(settings.SIMULATION_TICK_SECONDS, 0.5))

        self._detections_ever_active = False

        self.events.add(EventCategory.SYSTEM, "Mission console initialised", "system", 0.0)
        self.alerts.raise_alert(
            AlertTier.INFORMATION, "Mission started",
            f"{self.mission_id} online \u00b7 {self.mission_location}",
            0.0, ref_type="system", ref_id="mission-start",
        )

    # -- time -------------------------------------------------------------
    @property
    def mission_time_s(self) -> float:
        return time.time() - self.start_time

    # -- hardware ingestion (LIVE path) -----------------------------------
    def ingest_hardware_payload(self, payload: dict) -> None:
        normalize_hardware_payload(payload)  # validates; raises HardwareAdapterError if malformed
        self._last_hardware_payload = payload
        self._last_hardware_ts = time.time()
        self.events.add(EventCategory.SYSTEM, "Live hardware telemetry received", "hardware-adapter",
                         self.mission_time_s)

    def _hardware_is_fresh(self) -> bool:
        return (
            self._last_hardware_payload is not None
            and (time.time() - self._last_hardware_ts) <= HARDWARE_FRESHNESS_S
        )

    # -- detections (shared by real thermal model + dev-scenario) --------
    def ingest_detection(self, detection: ThermalDetection, source: DataSource) -> ThermalDetection:
        is_new_person = detection.id not in self.detections
        if not is_new_person:
            existing = self.detections[detection.id]
            detection.status = existing.status  # preserve operator confirm/dismiss state
            detection.position = detection.position or existing.position
            detection.nearest_node = detection.nearest_node or existing.nearest_node
            detection.distance_m = detection.distance_m if detection.distance_m is not None else existing.distance_m

        if detection.position is None:
            # Approximate: place at the rover's current position (thermal
            # camera is rover-mounted). See thermal_adapter.py docstring --
            # a monocular detector doesn't give real-world XY on its own.
            x, y, _ = mine_map.position_at_distance(self.rover.distance_m)
            detection.position = RoverPosition(x_m=x, y_m=y, heading_deg=0)
            detection.distance_m = round(self.rover.distance_m, 1)

        if detection.nearest_node is None:
            detection.nearest_node = self._nearest_node_id(detection.position.x_m, detection.position.y_m)

        self.detections[detection.id] = detection

        any_active_before = self._detections_ever_active
        has_active_person = any(
            d.status != DetectionStatus.DISMISSED for d in self.detections.values()
        )
        if is_new_person:
            self.events.add(
                EventCategory.DETECTION,
                f"Thermal detection {detection.id}: person, confidence {detection.confidence:.0%}",
                "thermal-model" if source == DataSource.LIVE else "dev-scenario",
                self.mission_time_s,
            )
            self.alerts.raise_alert(
                AlertTier.HUMAN_DETECTION, "Human detection",
                f"{detection.id} \u00b7 confidence {detection.confidence:.0%} \u00b7 "
                f"{detection.distance_m:.0f} m from entry",
                self.mission_time_s, ref_type="detection", ref_id=detection.id,
                position=detection.position, dedupe_key=detection.id,
            )
            if not any_active_before and has_active_person:
                new_relay = self.nodes.deploy_relay()
                self.events.add(EventCategory.NODE, f"Emergency relay {new_relay} deployed", "auto-deploy",
                                 self.mission_time_s)
                self._detections_ever_active = True
        return detection

    def confirm_detection(self, detection_id: str) -> ThermalDetection | None:
        d = self.detections.get(detection_id)
        if not d:
            return None
        d.status = DetectionStatus.CONFIRMED
        self.events.add(EventCategory.DETECTION, f"{detection_id} CONFIRMED by operator", "operator",
                         self.mission_time_s, operator_action="CONFIRM")
        return d

    def dismiss_detection(self, detection_id: str) -> ThermalDetection | None:
        d = self.detections.get(detection_id)
        if not d:
            return None
        d.status = DetectionStatus.DISMISSED
        self.events.add(EventCategory.DETECTION, f"{detection_id} DISMISSED by operator", "operator",
                         self.mission_time_s, operator_action="DISMISS")
        self.alerts.resolve_by_ref(detection_id)
        return d

    def _nearest_node_id(self, x_m: float, y_m: float) -> str | None:
        best_id, best_d = None, float("inf")
        for node_id in self.nodes.deployed:
            wp_x, wp_y = self.nodes.position_for(node_id)
            d = (wp_x - x_m) ** 2 + (wp_y - y_m) ** 2
            if d < best_d:
                best_d, best_id = d, node_id
        return best_id

    # -- dev scenarios ------------------------------------------------------
    def trigger_scenario(self, name: str) -> str:
        if name == "nominal":
            self.nodes.clear_comms_lost()
            for d in list(self.detections.values()):
                if d.status == DetectionStatus.PENDING:
                    d.status = DetectionStatus.DISMISSED
                    self.alerts.resolve_by_ref(d.id)
            self.events.add(EventCategory.SYSTEM, "Dev scenario: NOMINAL restored", "dev-panel", self.mission_time_s)
            return "nominal"

        if name == "person_detected":
            x, y = mine_map.node_position("PERSON_ZONE").x_m, mine_map.node_position("PERSON_ZONE").y_m
            from app.models.schemas import BBox
            det = ThermalDetection(
                id="H-01", type="person", confidence=0.87, timestamp=time.time(),
                bbox=BBox(x_pct=38, y_pct=20, width_pct=24, height_pct=55),
                temperature_delta_c=9.1, max_temperature_c=31.4, estimated_thermal=True,
                position=RoverPosition(x_m=x, y_m=y, heading_deg=0),
                distance_m=mine_map.cumulative_distance(mine_map.MAIN_PATH)[
                    [w.id for w in mine_map.MAIN_PATH].index("PERSON_ZONE")
                ],
                classification_tags=["HUMAN SIGNATURE"],
            )
            self.ingest_detection(det, source=DataSource.SIMULATED)
            self.events.add(EventCategory.SYSTEM, "Dev scenario: PERSON DETECTED injected", "dev-panel",
                             self.mission_time_s)
            return "person_detected"

        if name == "communication_lost":
            self.nodes.set_comms_lost("N4")
            self.events.add(EventCategory.SYSTEM, "Dev scenario: COMMUNICATION LOST (N4) triggered", "dev-panel",
                             self.mission_time_s)
            return "communication_lost"

        raise ValueError(f"Unknown scenario: {name}")

    # -- main tick ------------------------------------------------------
    def tick(self, dt_s: float) -> MissionSnapshot:
        mt = self.mission_time_s

        lost_index = CHAIN_ORDER.index(self.nodes.lost_node_id) if self.nodes.lost_node_id in CHAIN_ORDER else None
        link_lost = lost_index is not None
        nodes = self.nodes.step(dt_s)
        weak_present = any(n.state == NodeState.WEAK for n in nodes)

        if link_lost:
            link_status = LinkStatus.LOST
        elif weak_present:
            link_status = LinkStatus.DEGRADED
        else:
            link_status = LinkStatus.NOMINAL

        rover_state = self.rover.step(dt_s, link_lost=link_lost)

        hops = lost_index if link_lost else len(self.nodes.deployed)
        latency = 0.0 if link_lost else round(84 + (14 if link_status == LinkStatus.DEGRADED else 0), 0)

        unreachable_beyond = None
        if link_lost:
            unreachable_beyond = CHAIN_ORDER[lost_index]

        link = LinkState(
            status=link_status, hops=hops, latency_ms=latency,
            relays_deployed=self.nodes.relays_deployed_count(),
            unreachable_beyond=unreachable_beyond,
            last_contact_age_s=round(time.time() - self.start_time, 0) if not link_lost else
            round((time.time() - getattr(self, "_link_lost_since", time.time())), 0),
        )
        if link_lost and not hasattr(self, "_link_lost_since"):
            self._link_lost_since = time.time()
        if not link_lost and hasattr(self, "_link_lost_since"):
            del self._link_lost_since

        # -- telemetry: LIVE if fresh hardware payload, else SIMULATED ----
        if self._hardware_is_fresh():
            norm = normalize_hardware_payload(self._last_hardware_payload)
            # O2 has no physical sensor on the current hardware BOM (see
            # hardware_adapter.py); keep the simulator ticking just for
            # this one field so it drifts smoothly instead of freezing,
            # and it stays flagged `simulated_field=True` downstream.
            o2_pct = self.telemetry_sim.step(rover_state.distance_from_entry_m, dt_s)["o2_pct"]
            telemetry = build_telemetry_frame(
                ch4_pct=norm.ch4_pct, co_ppm=norm.co_ppm, o2_pct=o2_pct,
                temperature_c=norm.temperature_c or 0.0, humidity_pct=norm.humidity_pct or 0.0,
                pressure_pa=norm.pressure_pa or 0.0, sensor_ok=norm.sensor_ok,
                raw_hardware_present=True, source=DataSource.LIVE, mission_time_s=mt,
                age_seconds=round(time.time() - self._last_hardware_ts, 1),
            )
        else:
            sim = self.telemetry_sim.step(rover_state.distance_from_entry_m, dt_s)
            telemetry = build_telemetry_frame(
                ch4_pct=sim["ch4_pct"], co_ppm=sim["co_ppm"], o2_pct=sim["o2_pct"],
                temperature_c=sim["temperature_c"], humidity_pct=sim["humidity_pct"],
                pressure_pa=sim["pressure_pa"], sensor_ok=True, raw_hardware_present=False,
                source=DataSource.SIMULATED, mission_time_s=mt, age_seconds=0.0,
            )

        self._evaluate_alerts(link, nodes, telemetry, rover_state, mt)
        self.commands.tick(self.rover, link_lost)

        snapshot = MissionSnapshot(
            mission_id=self.mission_id,
            mission_time_s=round(mt, 1),
            wall_clock_iso=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            source=DataSource.SIMULATED if not self._hardware_is_fresh() else DataSource.LIVE,
            link=link, rover=rover_state, nodes=nodes, telemetry=telemetry,
            alerts=self.alerts.active(), detections=list(self.detections.values()),
            commands=self.commands.recent(), annotations=self.annotations,
            replay_mode=self.replay_mode, replay_time_s=self.replay_time_s,
        )

        self._history.append((mt, snapshot.model_dump(mode="json")))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return snapshot

    # -- alert evaluation --------------------------------------------------
    def _evaluate_alerts(self, link, nodes, telemetry, rover_state, mt: float) -> None:
        # comms
        for n in nodes:
            if n.state == NodeState.LOST:
                self.alerts.raise_alert(
                    AlertTier.COMMUNICATIONS, f"{n.id} LOST",
                    f"No heartbeat for {n.last_heartbeat_age_s:.0f}s \u00b7 last RSSI {n.rssi_dbm:.0f} dBm",
                    mt, ref_type="node", ref_id=n.id,
                    position=RoverPosition(x_m=n.x_m, y_m=n.y_m, heading_deg=0),
                    dedupe_key=n.id,
                )
            else:
                self.alerts.resolve_by_ref(n.id)

        # atmosphere
        for g in telemetry.gases:
            key = f"gas:{g.key}"
            if g.status.value != "NORMAL":
                self.alerts.raise_alert(
                    AlertTier.ATMOSPHERE, f"{g.label} {g.status.value}",
                    f"{g.label} at {g.value}{g.unit} \u00b7 mission time {int(mt // 60):02d}:{int(mt % 60):02d}",
                    mt, ref_type="gas", ref_id=key, dedupe_key=key,
                )
            else:
                self.alerts.resolve_by_ref(key)

        # thermal hotspot (environment-level, distinct from a human detection)
        temp_reading = next((e for e in telemetry.environment if e.key == "temperature_c"), None)
        if temp_reading and temp_reading.value >= 34:
            self.alerts.raise_alert(
                AlertTier.THERMAL, "Elevated ambient temperature",
                f"{temp_reading.value}\u00b0C near rover position", mt,
                ref_type="thermal", ref_id="ambient-heat", dedupe_key="ambient-heat",
            )
        else:
            self.alerts.resolve_by_ref("ambient-heat")

        # rover system
        if rover_state.battery_pct <= LOW_BATTERY_PCT:
            self.alerts.raise_alert(
                AlertTier.ROVER_SYSTEM, "Rover battery low",
                f"Battery at {rover_state.battery_pct:.0f}% \u00b7 consider Return to Entry", mt,
                ref_type="rover", ref_id="battery-low", dedupe_key="battery-low",
            )
        else:
            self.alerts.resolve_by_ref("battery-low")

    # -- replay -------------------------------------------------------------
    def snapshot_at(self, mission_time_s: float) -> dict | None:
        if not self._history:
            return None
        best = min(self._history, key=lambda h: abs(h[0] - mission_time_s))
        return best[1]

    def timeline_bounds(self) -> tuple[float, float]:
        if not self._history:
            return 0.0, 0.0
        return self._history[0][0], self._history[-1][0]


_mission_state_singleton: MissionState | None = None


def get_mission_state() -> MissionState:
    global _mission_state_singleton
    if _mission_state_singleton is None:
        _mission_state_singleton = MissionState()
    return _mission_state_singleton
