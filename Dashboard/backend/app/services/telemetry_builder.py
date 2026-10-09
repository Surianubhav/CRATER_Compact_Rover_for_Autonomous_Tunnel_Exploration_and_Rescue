"""
Builds a TelemetryFrame (the schema the frontend actually consumes) from
plain normalized values, whichever adapter produced them (hardware or
simulator). Threshold evaluation lives here, in ONE place, driven by the
config file -- not duplicated in the simulator, the API, or the frontend.
"""
from __future__ import annotations

import time

from app.config.settings import get_settings, get_thresholds
from app.models.schemas import DataSource, EnvironmentReading, GasReading, SeverityLevel, TelemetryFrame
from app.services.telemetry_history import TelemetryHistoryTracker

_history = TelemetryHistoryTracker()

_GAS_META = {
    "ch4_pct": {"label": "CH4", "unit": "%"},
    "co_ppm": {"label": "CO", "unit": "ppm"},
    "o2_pct": {"label": "O2", "unit": "%"},
}
_ENV_META = {
    "temperature_c": {"label": "Temp", "unit": "\u00b0C"},
    "humidity_pct": {"label": "Humidity", "unit": "%"},
    "pressure_pa": {"label": "Pressure", "unit": "Pa"},
}


def _status_upper_bound(value: float, thresholds: dict) -> SeverityLevel:
    if value >= thresholds.get("danger", float("inf")):
        return SeverityLevel.DANGER
    if value >= thresholds.get("caution", float("inf")):
        return SeverityLevel.CAUTION
    return SeverityLevel.NORMAL


def _status_lower_bound(value: float, thresholds: dict) -> SeverityLevel:
    if value <= thresholds.get("danger_low", float("-inf")):
        return SeverityLevel.DANGER
    if value <= thresholds.get("caution_low", float("-inf")):
        return SeverityLevel.CAUTION
    return SeverityLevel.NORMAL


def build_telemetry_frame(
    *,
    ch4_pct: float,
    co_ppm: float,
    o2_pct: float,
    temperature_c: float,
    humidity_pct: float,
    pressure_pa: float,
    sensor_ok: bool,
    raw_hardware_present: bool,
    source: DataSource,
    mission_time_s: float,
    age_seconds: float = 0.0,
) -> TelemetryFrame:
    th = get_thresholds()

    gases = []
    for key, value, bound in (
        ("ch4_pct", ch4_pct, "upper"),
        ("co_ppm", co_ppm, "upper"),
    ):
        sample = _history.push(key, value, mission_time_s)
        status = _status_upper_bound(value, th[key])
        gases.append(
            GasReading(
                key=key,
                label=_GAS_META[key]["label"],
                value=value,
                unit=_GAS_META[key]["unit"],
                status=status,
                trend_per_min=sample.trend_per_min,
                peak_value=sample.peak_value,
                peak_time_s=sample.peak_time_s,
                history=sample.history,
                simulated_field=False,
            )
        )

    # O2: no physical sensor exists on the current hardware BOM yet.
    # Always flagged simulated_field=True regardless of overall source
    # mode, so the UI can mark it distinctly instead of implying a real
    # oxygen sensor reading.
    o2_sample = _history.push("o2_pct", o2_pct, mission_time_s)
    gases.append(
        GasReading(
            key="o2_pct",
            label=_GAS_META["o2_pct"]["label"],
            value=o2_pct,
            unit=_GAS_META["o2_pct"]["unit"],
            status=_status_lower_bound(o2_pct, th["o2_pct"]),
            trend_per_min=o2_sample.trend_per_min,
            peak_value=o2_sample.peak_value,
            peak_time_s=o2_sample.peak_time_s,
            history=o2_sample.history,
            simulated_field=True,
        )
    )

    env = []
    for key, value in (
        ("temperature_c", temperature_c),
        ("humidity_pct", humidity_pct),
        ("pressure_pa", pressure_pa),
    ):
        sample = _history.push(key, value, mission_time_s)
        if key == "pressure_pa":
            status = SeverityLevel.NORMAL  # relative-delta metric, informational only
        else:
            status = _status_upper_bound(value, th[key])
        env.append(
            EnvironmentReading(
                key=key,
                label=_ENV_META[key]["label"],
                value=value,
                unit=_ENV_META[key]["unit"],
                status=status,
                trend_per_min=sample.trend_per_min,
                peak_value=sample.peak_value,
                history=sample.history,
            )
        )

    return TelemetryFrame(
        timestamp=time.time(),
        source=source,
        age_seconds=age_seconds,
        gases=gases,
        environment=env,
        sensor_ok=sensor_ok,
        raw_hardware_present=raw_hardware_present,
    )
