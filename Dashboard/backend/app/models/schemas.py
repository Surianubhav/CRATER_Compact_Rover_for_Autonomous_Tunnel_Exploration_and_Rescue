"""
Normalized data schemas shared by the simulator, the hardware adapter,
the thermal adapter, the REST API and the WebSocket broadcasts.

Nothing downstream (frontend included) should ever depend on raw
hardware field names (mq4, mq7, ...) or raw model output shapes --
everything is translated into these schemas first. When the hardware
team's real payloads are wired in, only the adapters in
`app/adapters/` need to change.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class DataSource(str, Enum):
    LIVE = "LIVE"
    SIMULATED = "SIMULATED"
    REPLAY = "REPLAY"


class LinkStatus(str, Enum):
    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    LOST = "LOST"


class ControlState(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    COMMAND = "COMMAND"
    HOLDING = "HOLDING"


class NodeState(str, Enum):
    ONLINE = "ONLINE"
    WEAK = "WEAK"
    LOST = "LOST"
    UNREACHABLE = "UNREACHABLE"


class SeverityLevel(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DANGER = "DANGER"


class AlertTier(int, Enum):
    COMMUNICATIONS = 1
    HUMAN_DETECTION = 2
    ATMOSPHERE = 3
    THERMAL = 4
    ROVER_SYSTEM = 5
    INFORMATION = 6


ALERT_TIER_LABEL = {
    AlertTier.COMMUNICATIONS: "COMMUNICATIONS",
    AlertTier.HUMAN_DETECTION: "HUMAN DETECTION",
    AlertTier.ATMOSPHERE: "ATMOSPHERE",
    AlertTier.THERMAL: "THERMAL",
    AlertTier.ROVER_SYSTEM: "ROVER SYSTEM",
    AlertTier.INFORMATION: "INFORMATION",
}


class AlertState(str, Enum):
    ACTIVE = "ACTIVE"
    ACKED = "ACKED"
    RESOLVED = "RESOLVED"


class DetectionStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class ThermalConnectionState(str, Enum):
    CONNECTING = "CONNECTING"
    LIVE = "LIVE"
    MODEL_ERROR = "MODEL_ERROR"
    DISCONNECTED = "DISCONNECTED"


class CommandStatus(str, Enum):
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    QUEUED_OFFLINE = "QUEUED_OFFLINE"  # WILL SEND ON RECONNECT


class EventCategory(str, Enum):
    COMMS = "COMMS"
    DETECTION = "DETECTION"
    GAS = "GAS"
    THERMAL = "THERMAL"
    NODE = "NODE"
    COMMAND = "COMMAND"
    ANNOTATION = "ANNOTATION"
    SYSTEM = "SYSTEM"


# ---------------------------------------------------------------------------
# Telemetry (normalized -- this is what hardware_adapter.py and
# telemetry_simulator.py both produce, regardless of upstream shape)
# ---------------------------------------------------------------------------
class GasReading(BaseModel):
    key: str  # "ch4_pct" | "co_ppm" | "o2_pct"
    label: str
    value: float
    unit: str
    status: SeverityLevel
    trend_per_min: float = 0.0
    peak_value: float = 0.0
    peak_time_s: float = 0.0
    history: list[float] = Field(default_factory=list)
    simulated_field: bool = False  # true for readings with no physical sensor yet (e.g. O2)


class EnvironmentReading(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    status: SeverityLevel
    trend_per_min: float = 0.0
    peak_value: float = 0.0
    history: list[float] = Field(default_factory=list)


class TelemetryFrame(BaseModel):
    timestamp: float
    source: DataSource
    age_seconds: float = 0.0
    gases: list[GasReading]
    environment: list[EnvironmentReading]
    sensor_ok: bool = True
    raw_hardware_present: bool = False


# ---------------------------------------------------------------------------
# Rover
# ---------------------------------------------------------------------------
class RoverPosition(BaseModel):
    x_m: float
    y_m: float
    heading_deg: float


class RoverState(BaseModel):
    control_state: ControlState
    battery_pct: float
    distance_from_entry_m: float
    path_travelled_m: float
    position: RoverPosition
    fov_deg: float = 70.0
    trail: list[RoverPosition] = Field(default_factory=list)
    ghosted: bool = False  # true when beyond last-known-good comms


# ---------------------------------------------------------------------------
# Mesh nodes
# ---------------------------------------------------------------------------
class MeshNode(BaseModel):
    id: str
    x_m: float
    y_m: float
    state: NodeState
    battery_pct: float
    rssi_dbm: float
    latency_ms: float
    throughput_kbps: float
    last_heartbeat_age_s: float
    range_m: float = 60.0


class MeshLinkQuality(BaseModel):
    from_id: str
    to_id: str
    rssi_dbm: float
    latency_ms: float
    throughput_kbps: float
    reachable: bool


class LinkState(BaseModel):
    status: LinkStatus
    hops: int
    latency_ms: float
    relays_deployed: int
    relays_total: int = 8
    auto_deploy_armed: bool = True
    rover_buffer_s: float = 0.0
    unreachable_beyond: Optional[str] = None
    last_contact_age_s: float = 0.0


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------
class BBox(BaseModel):
    x_pct: float
    y_pct: float
    width_pct: float
    height_pct: float


class ThermalDetection(BaseModel):
    id: str
    type: str = "person"
    status: DetectionStatus = DetectionStatus.PENDING
    confidence: float
    timestamp: float
    bbox: BBox
    temperature_delta_c: float
    max_temperature_c: float
    estimated_thermal: bool = True  # values derived from image intensity, not a radiometric sensor
    position: Optional[RoverPosition] = None
    distance_m: Optional[float] = None
    nearest_node: Optional[str] = None
    classification_tags: list[str] = Field(default_factory=list)
    thumbnail_data_uri: Optional[str] = None


class ThermalFrameResult(BaseModel):
    connection_state: ThermalConnectionState
    frame_data_uri: Optional[str] = None
    detections: list[ThermalDetection] = Field(default_factory=list)
    scene_avg_c: Optional[float] = None
    scene_max_c: Optional[float] = None
    model_name: Optional[str] = None
    error_message: Optional[str] = None
    inference_ms: Optional[float] = None
    source: DataSource = DataSource.SIMULATED


# ---------------------------------------------------------------------------
# Alerts / Events
# ---------------------------------------------------------------------------
class Alert(BaseModel):
    id: str
    tier: AlertTier
    title: str
    detail: str
    mission_time_s: float
    created_at: float
    state: AlertState = AlertState.ACTIVE
    ref_type: Optional[str] = None  # "node" | "detection" | "gas" | "rover"
    ref_id: Optional[str] = None
    position: Optional[RoverPosition] = None


class MissionEvent(BaseModel):
    id: str
    mission_time_s: float
    clock: str
    category: EventCategory
    message: str
    source: str
    operator_action: Optional[str] = None


class Annotation(BaseModel):
    id: str
    x_m: float
    y_m: float
    label: str
    note: Optional[str] = None
    created_at: float


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
class CommandRequest(BaseModel):
    type: str  # return_to_entry | return_to_node | go_to_node | explore_unexplored | go_to_marker | hold_position | resume
    target: Optional[str] = None


class QueuedCommand(BaseModel):
    id: str
    type: str
    label: str
    target: Optional[str] = None
    status: CommandStatus
    issued_at: float
    eta_s: Optional[float] = None


# ---------------------------------------------------------------------------
# Mission-level snapshot (what /api/mission/state and /ws/telemetry send)
# ---------------------------------------------------------------------------
class MissionSnapshot(BaseModel):
    mission_id: str
    mission_time_s: float
    wall_clock_iso: str
    source: DataSource
    link: LinkState
    rover: RoverState
    nodes: list[MeshNode]
    telemetry: TelemetryFrame
    alerts: list[Alert]
    detections: list[ThermalDetection]
    commands: list[QueuedCommand]
    annotations: list[Annotation]
    replay_mode: bool = False
    replay_time_s: Optional[float] = None
