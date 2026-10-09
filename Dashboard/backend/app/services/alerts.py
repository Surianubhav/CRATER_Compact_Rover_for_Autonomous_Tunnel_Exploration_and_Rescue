"""
Alert lifecycle.

Alerts are sorted by (tier severity, newest first). ACKed alerts stay
visible but no longer pinned; RESOLVED alerts are removed from the
active list and appear only in the event log (see event_log.py, which
mission_state.py also writes to when an alert resolves).
"""
from __future__ import annotations

import time
import uuid

from app.models.schemas import Alert, AlertState, AlertTier, RoverPosition


class AlertService:
    def __init__(self):
        self.alerts: dict[str, Alert] = {}
        self._next_num = 1

    def raise_alert(
        self,
        tier: AlertTier,
        title: str,
        detail: str,
        mission_time_s: float,
        ref_type: str | None = None,
        ref_id: str | None = None,
        position: RoverPosition | None = None,
        dedupe_key: str | None = None,
    ) -> Alert | None:
        """
        Creates a new active alert unless an ACTIVE (unacked or acked, but
        not resolved) alert with the same dedupe_key already exists --
        prevents e.g. re-raising "NODE 4 LOST" every simulation tick.
        """
        if dedupe_key:
            for a in self.alerts.values():
                if a.ref_id == dedupe_key and a.state != AlertState.RESOLVED:
                    return None
        alert_id = f"ALT-{self._next_num:04d}"
        self._next_num += 1
        alert = Alert(
            id=alert_id, tier=tier, title=title, detail=detail,
            mission_time_s=mission_time_s, created_at=time.time(),
            ref_type=ref_type, ref_id=ref_id or dedupe_key, position=position,
        )
        self.alerts[alert_id] = alert
        return alert

    def ack(self, alert_id: str) -> Alert | None:
        alert = self.alerts.get(alert_id)
        if alert and alert.state == AlertState.ACTIVE:
            alert.state = AlertState.ACKED
        return alert

    def resolve(self, alert_id: str) -> Alert | None:
        alert = self.alerts.get(alert_id)
        if alert:
            alert.state = AlertState.RESOLVED
        return alert

    def resolve_by_ref(self, ref_id: str) -> list[Alert]:
        resolved = []
        for a in self.alerts.values():
            if a.ref_id == ref_id and a.state != AlertState.RESOLVED:
                a.state = AlertState.RESOLVED
                resolved.append(a)
        return resolved

    def active(self) -> list[Alert]:
        items = [a for a in self.alerts.values() if a.state != AlertState.RESOLVED]
        # severity (lower tier number = more severe) first, then newest first
        return sorted(items, key=lambda a: (a.tier.value, -a.created_at))

    def all(self) -> list[Alert]:
        return sorted(self.alerts.values(), key=lambda a: -a.created_at)
