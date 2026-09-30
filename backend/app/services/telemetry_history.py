"""
Rolling per-channel history so gas/environment tiles can show a trend
arrow, a peak value + time, and a sparkline -- computed the SAME way
regardless of whether the sample came from the hardware adapter (LIVE)
or the simulator (SIMULATED). This is the "normalized interface" the
product brief asks for in section 30: only the source of the raw sample
differs, everything downstream is identical.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class ChannelSample:
    value: float
    status: str
    trend_per_min: float
    peak_value: float
    peak_time_s: float
    history: list[float]


class _Channel:
    def __init__(self, maxlen: int = 120):
        self.samples: deque[tuple[float, float]] = deque(maxlen=maxlen)  # (t, value)
        self.peak_value = float("-inf")
        self.peak_time_s = 0.0

    def push(self, value: float, mission_time_s: float) -> ChannelSample:
        now = time.time()
        self.samples.append((now, value))
        if value > self.peak_value:
            self.peak_value = value
            self.peak_time_s = mission_time_s

        trend = 0.0
        if len(self.samples) >= 2:
            t0, v0 = self.samples[0]
            t1, v1 = self.samples[-1]
            dt_min = max((t1 - t0) / 60.0, 1e-6)
            trend = round((v1 - v0) / dt_min, 3)

        history = [round(v, 4) for _, v in self.samples]
        return ChannelSample(
            value=value,
            status="",  # status is computed by the caller against thresholds
            trend_per_min=trend,
            peak_value=round(self.peak_value, 4),
            peak_time_s=self.peak_time_s,
            history=history[-40:],
        )


class TelemetryHistoryTracker:
    """Keeps one rolling `_Channel` per telemetry key (ch4_pct, co_ppm, ...)."""

    def __init__(self) -> None:
        self._channels: dict[str, _Channel] = {}

    def push(self, key: str, value: float, mission_time_s: float) -> ChannelSample:
        if key not in self._channels:
            self._channels[key] = _Channel()
        return self._channels[key].push(value, mission_time_s)
