"""
Hardware adapter.

This is the single seam between the physical sensor payload produced by
the existing Nano + ESP32 firmware (see /nano/nanoJson2.ino and
/esp_receiver/esp32RecPinChange.ino) and the rest of the backend.

Raw payload shape, exactly as sent by the Nano today:
    {"hb": 123, "mq4": 88, "mq7": 228, "temp": 25.70,
     "hum": 57.60, "pressure": 97627.0, "alt": 312.88, "bmp_ok": true}

No other module should ever read `mq4` / `mq7` / etc directly -- if the
hardware team renames a field or adds a sensor, this file is the only
place that needs to change.

CALIBRATION NOTE (read me): MQ-4 / MQ-7 are analog resistive gas sensors.
Converting their raw ADC counts into calibrated %LEL / ppm normally
requires a burn-in period and a per-sensor calibration curve from the
hardware team, which does not exist yet. The linear scale factors below
are ILLUSTRATIVE PLACEHOLDERS ONLY (documented in README /
thresholds.json) so the console has plausible-looking, internally
consistent numbers to demonstrate the UI and alerting logic against.
Replace `MQ4_FULL_SCALE_PCT` / `MQ7_FULL_SCALE_PPM` with a real
calibration curve when one is available -- nothing else in the app needs
to change.
"""
from __future__ import annotations

from dataclasses import dataclass

MQ4_ADC_MAX = 1023.0
MQ7_ADC_MAX = 1023.0
MQ4_FULL_SCALE_PCT = 5.0     # raw 1023 -> 5.0% CH4 (placeholder)
MQ7_FULL_SCALE_PPM = 200.0   # raw 1023 -> 200 ppm CO (placeholder)


@dataclass
class NormalizedReading:
    ch4_pct: float
    co_ppm: float
    temperature_c: float | None
    humidity_pct: float | None
    pressure_pa: float | None
    altitude_m: float | None
    sensor_ok: bool
    raw_hardware_present: bool


class HardwareAdapterError(ValueError):
    pass


def normalize_hardware_payload(payload: dict) -> NormalizedReading:
    """
    Map a raw Nano/ESP32 JSON payload onto normalized engineering units.
    Raises HardwareAdapterError on a structurally invalid payload so the
    caller can surface a clear ingest error instead of silently accepting
    garbage data.
    """
    required = ("mq4", "mq7")
    missing = [k for k in required if k not in payload]
    if missing:
        raise HardwareAdapterError(f"hardware payload missing field(s): {missing}")

    try:
        mq4_raw = float(payload["mq4"])
        mq7_raw = float(payload["mq7"])
    except (TypeError, ValueError) as exc:
        raise HardwareAdapterError(f"mq4/mq7 must be numeric: {exc}") from exc

    ch4_pct = round((mq4_raw / MQ4_ADC_MAX) * MQ4_FULL_SCALE_PCT, 3)
    co_ppm = round((mq7_raw / MQ7_ADC_MAX) * MQ7_FULL_SCALE_PPM, 2)

    temp = payload.get("temp")
    hum = payload.get("hum")
    pressure = payload.get("pressure")
    alt = payload.get("alt")
    bmp_ok = bool(payload.get("bmp_ok", False))

    return NormalizedReading(
        ch4_pct=ch4_pct,
        co_ppm=co_ppm,
        temperature_c=float(temp) if temp is not None else None,
        humidity_pct=float(hum) if hum is not None else None,
        pressure_pa=float(pressure) if pressure is not None else None,
        altitude_m=float(alt) if alt is not None else None,
        sensor_ok=bmp_ok,
        raw_hardware_present=True,
    )
