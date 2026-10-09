"""
Event log: the durable record of everything that happened during the
mission (comms, detections, gas crossings, thermal, node changes,
commands, annotations, system messages). Alerts write here when they
resolve; the simulator and command service write here directly too.
"""
from __future__ import annotations

import csv
import io
import time

from app.models.schemas import EventCategory, MissionEvent


def _clock(ts: float) -> str:
    t = time.localtime(ts)
    return time.strftime("%H:%M:%S", t)


class EventLogService:
    def __init__(self):
        self.events: list[MissionEvent] = []
        self._next_num = 1

    def add(
        self,
        category: EventCategory,
        message: str,
        source: str,
        mission_time_s: float,
        operator_action: str | None = None,
    ) -> MissionEvent:
        event = MissionEvent(
            id=f"EVT-{self._next_num:05d}",
            mission_time_s=round(mission_time_s, 1),
            clock=_clock(time.time()),
            category=category,
            message=message,
            source=source,
            operator_action=operator_action,
        )
        self._next_num += 1
        self.events.append(event)
        self.events = self.events[-2000:]
        return event

    def query(
        self,
        search: str | None = None,
        category: EventCategory | None = None,
        limit: int = 500,
    ) -> list[MissionEvent]:
        items = self.events
        if category:
            items = [e for e in items if e.category == category]
        if search:
            s = search.lower()
            items = [
                e for e in items
                if s in e.message.lower() or s in e.source.lower() or s in e.category.value.lower()
            ]
        return list(reversed(items))[:limit]

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["mission_time_s", "clock", "category", "event", "source", "operator_action"])
        for e in self.events:
            writer.writerow([e.mission_time_s, e.clock, e.category.value, e.message, e.source, e.operator_action or ""])
        return buf.getvalue()
