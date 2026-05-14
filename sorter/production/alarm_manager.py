#!/usr/bin/env python3
"""
Production Alarm Management System — v1.0
==========================================
Centralized alarm handling for the sorter production line.
Consumes events from: BatchQualityTracker, QCAuditSystem, BatchTrackingSystem.
Dispatches to: MQTT (toast alerts), REST API callbacks, log files.

Run: python sorter/production/alarm_manager.py --demo
"""

import json
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import sys
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))


# ══════════════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

class AlarmSeverity(str, Enum):
    INFO      = "info"
    WARNING   = "warning"
    CRITICAL  = "critical"
    EMERGENCY = "emergency"


class AlarmCategory(str, Enum):
    QUALITY        = "quality"
    MECHANICAL     = "mechanical"
    SENSOR         = "sensor"
    CALIBRATION    = "calibration"
    THROUGHPUT     = "throughput"
    SAFETY         = "safety"
    SUPPLY_CHAIN   = "supply_chain"
    batch_tracking = "batch_tracking"


class AlarmStatus(str, Enum):
    ACTIVE       = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED     = "resolved"
    SUPPRESSED   = "suppressed"


class AlarmSource(str, Enum):
    BATCH_QUALITY_TRACKER = "batch_quality_tracker"
    QC_AUDIT_SYSTEM        = "qc_audit_system"
    BATCH_TRACKING_SYSTEM  = "batch_tracking_system"
    HEALTH_MONITOR         = "health_monitor"
    SPC_MONITOR            = "spc_monitor"
    OPERATOR               = "operator"
    SYSTEM                 = "system"


@dataclass
class TriggerCondition:
    metric: str
    operator: str
    threshold: float
    window_secs: int
    severity_at_fire: AlarmSeverity


@dataclass
class AlarmPolicy:
    alarm_id: str
    name: str
    category: AlarmCategory
    description: str
    trigger: TriggerCondition
    max_occurrences_before_escalation: int = 3
    escalation_delay_secs: int = 300
    notify_mqtt: bool = True
    notify_rest_callback: bool = False
    rest_callback_url: Optional[str] = None
    notify_slack: bool = False
    slack_webhook_url: Optional[str] = None
    auto_acknowledge_on_stable_secs: int = 600
    suppress_on_maintenance_window: bool = False
    enable: bool = True
    hysteresis_pct: float = 10.0


@dataclass
class AlarmRecord:
    alarm_id: str
    alarm_name: str
    category: AlarmCategory
    severity: AlarmSeverity
    source: AlarmSource
    message: str
    context: dict = field(default_factory=dict)
    batch_id: Optional[str] = None
    recipe_name: Optional[str] = None
    fired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    status: AlarmStatus = AlarmStatus.ACTIVE
    occurrence_count: int = 1
    total_occurrences: int = 1
    escalated: bool = False
    last_escalation_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolution_note: Optional[str] = None
    uid: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    @property
    def is_active(self) -> bool:
        return self.status == AlarmStatus.ACTIVE

    @property
    def age_secs(self) -> float:
        return (datetime.now(timezone.utc) - self.fired_at).total_seconds()

    @property
    def duration_secs(self) -> float:
        if self.resolved_at:
            return (self.resolved_at - self.fired_at).total_seconds()
        return self.age_secs

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "alarm_id": self.alarm_id,
            "alarm_name": self.alarm_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "source": self.source.value,
            "message": self.message,
            "context": self.context,
            "batch_id": self.batch_id,
            "recipe_name": self.recipe_name,
            "fired_at": self.fired_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "status": self.status.value,
            "occurrence_count": self.occurrence_count,
            "total_occurrences": self.total_occurrences,
            "escalated": self.escalated,
            "age_secs": round(self.age_secs, 1),
            "acknowledged_by": self.acknowledged_by,
            "resolution_note": self.resolution_note,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  DEFAULT ALARM POLICIES
# ══════════════════════════════════════════════════════════════════════════════

def _tc(metric: str, op: str, threshold: float, window: int, sev: AlarmSeverity) -> TriggerCondition:
    return TriggerCondition(metric=metric, operator=op, threshold=threshold, window_secs=window, severity_at_fire=sev)

DEFAULT_POLICIES: list[AlarmPolicy] = [
    AlarmPolicy(
        alarm_id="QUALITY_001", name="High Defect Rate",
        category=AlarmCategory.QUALITY,
        description="Defect rate exceeded WARNING threshold (>2%)",
        trigger=_tc("defect_rate_pct", "gt", 2.0, 60, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="QUALITY_002", name="Critical Defect Rate",
        category=AlarmCategory.QUALITY,
        description="Defect rate exceeded CRITICAL threshold (>5%)",
        trigger=_tc("defect_rate_pct", "gt", 5.0, 30, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
        max_occurrences_before_escalation=2,
        escalation_delay_secs=120,
    ),
    AlarmPolicy(
        alarm_id="QUALITY_003", name="Grade A Drop",
        category=AlarmCategory.QUALITY,
        description="Grade A ratio fell below target (<85%)",
        trigger=_tc("grade_a_pct", "lt", 85.0, 120, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="QUALITY_004", name="Color Score Low",
        category=AlarmCategory.QUALITY,
        description="Average color score below WARNING threshold",
        trigger=_tc("avg_color_score", "lt", 80.0, 90, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="QUALITY_005", name="Moisture Drift",
        category=AlarmCategory.QUALITY,
        description="Moisture reading deviating from recipe target",
        trigger=_tc("moisture_pct", "gt", 0.8, 120, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="THRU_001", name="Throughput Below Target",
        category=AlarmCategory.THROUGHPUT,
        description="Real-time throughput < 1.8 kg/h (90% of 2.0 target)",
        trigger=_tc("throughput_kg_h", "lt", 1.8, 180, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="THRU_002", name="Critical Throughput Drop",
        category=AlarmCategory.THROUGHPUT,
        description="Throughput < 1.0 kg/h for >5 min",
        trigger=_tc("throughput_kg_h", "lt", 1.0, 300, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
        escalation_delay_secs=180,
    ),
    AlarmPolicy(
        alarm_id="SENSOR_001", name="Sensor Reading Out of Range",
        category=AlarmCategory.SENSOR,
        description="Sensor value outside physical range",
        trigger=_tc("sensor_anomaly_score", "gt", 0.95, 10, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="SENSOR_002", name="Sensor Drift Detected",
        category=AlarmCategory.SENSOR,
        description="SPC control chart detected sustained drift",
        trigger=_tc("spc_drift_score", "gt", 0.85, 300, AlarmSeverity.WARNING),
        notify_mqtt=True,
        notify_rest_callback=True,
    ),
    AlarmPolicy(
        alarm_id="SENSOR_003", name="Multiple Sensors Offline",
        category=AlarmCategory.SENSOR,
        description="More than 2 sensors reporting offline",
        trigger=_tc("offline_sensor_count", "gt", 2.0, 30, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="MECH_001", name="Feeder Jam Detected",
        category=AlarmCategory.MECHANICAL,
        description="Vibrating feeder stalled or rate below 10bpm",
        trigger=_tc("feeder_rate_bpm", "lt", 10.0, 60, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="MECH_002", name="Air Pressure Low",
        category=AlarmCategory.MECHANICAL,
        description="Compressed air pressure below safe operating threshold",
        trigger=_tc("air_pressure_psi", "lt", 45.0, 30, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="MECH_003", name="Motor Temperature High",
        category=AlarmCategory.MECHANICAL,
        description="Stepper motor temperature exceeded 60°C",
        trigger=_tc("motor_temp_c", "gt", 60.0, 60, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="SAFETY_001", name="E-STOP Triggered",
        category=AlarmCategory.SAFETY,
        description="Emergency stop button activated",
        trigger=_tc("estop_active", "eq", 1.0, 0, AlarmSeverity.EMERGENCY),
        notify_mqtt=True,
        max_occurrences_before_escalation=1,
    ),
    AlarmPolicy(
        alarm_id="SAFETY_002", name="Safety Circuit Open",
        category=AlarmCategory.SAFETY,
        description="FAIL-SAFE safety relay chain interrupted",
        trigger=_tc("safety_circuit_ok", "eq", 0.0, 0, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="CAL_001", name="Calibration Expired",
        category=AlarmCategory.CALIBRATION,
        description="Sensor calibration beyond 24h recommended interval",
        trigger=_tc("hours_since_calibration", "gt", 24.0, 0, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="BATCH_001", name="Lot At Risk - Urgent Processing",
        category=AlarmCategory.SUPPLY_CHAIN,
        description="Green coffee lot close to expiry / needs urgent processing",
        trigger=_tc("lot_urgency_score", "gt", 8.0, 0, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
    AlarmPolicy(
        alarm_id="BATCH_002", name="Batch Recall Triggered",
        category=AlarmCategory.batch_tracking,
        description="Quality problem requires batch recall",
        trigger=_tc("recall_triggered", "eq", 1.0, 0, AlarmSeverity.CRITICAL),
        notify_mqtt=True,
        notify_rest_callback=True,
    ),
    AlarmPolicy(
        alarm_id="BATCH_003", name="Custody Chain Break",
        category=AlarmCategory.batch_tracking,
        description="Chain-of-custody record gap detected",
        trigger=_tc("custody_gap_detected", "eq", 1.0, 0, AlarmSeverity.WARNING),
        notify_mqtt=True,
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFIER
# ══════════════════════════════════════════════════════════════════════════════

class AlarmNotifier:
    def __init__(self, mqtt_client=None, rest_callback_url: Optional[str] = None):
        self._mqtt = mqtt_client
        self._rest_url = rest_callback_url

    def notify(self, alarm: AlarmRecord) -> None:
        payload = alarm.to_dict()
        payload["ts"] = datetime.now(timezone.utc).isoformat()
        payload["type"] = "alarm"

        if self._mqtt:
            topic = f"sorter/alarms/{alarm.category.value}/{alarm.severity.value}"
            try:
                self._mqtt.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
            except Exception:
                pass

        if self._rest_url:
            try:
                import urllib.request
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self._rest_url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except Exception:
                pass

        icon = {"emergency": "🆘", "critical": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(alarm.severity.value, "💬")
        print(f"  {icon} [{alarm.severity.value.upper()}/{alarm.category.value.upper()}] {alarm.alarm_name}: {alarm.message}")


# ══════════════════════════════════════════════════════════════════════════════
#  METRIC STORE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MetricSample:
    timestamp: datetime
    value: float
    tags: dict = field(default_factory=dict)


class MetricStore:
    def __init__(self, max_samples: int = 1000):
        self._store: dict[str, list[MetricSample]] = {}
        self._max = max_samples

    def put(self, metric: str, value: float, tags: Optional[dict] = None) -> None:
        if metric not in self._store:
            self._store[metric] = []
        self._store[metric].append(MetricSample(timestamp=datetime.now(timezone.utc), value=value, tags=tags or {}))
        if len(self._store[metric]) > self._max:
            self._store[metric] = self._store[metric][-self._max:]

    def get(self, metric: str, window_secs: Optional[int] = None) -> list[float]:
        if metric not in self._store:
            return []
        cutoff = None
        if window_secs:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_secs)
        samples = self._store[metric]
        if cutoff:
            samples = [s for s in samples if s.timestamp >= cutoff]
        return [s.value for s in samples]

    def latest(self, metric: str) -> Optional[float]:
        vals = self.get(metric)
        return vals[-1] if vals else None

    def avg(self, metric: str, window_secs: int) -> Optional[float]:
        vals = self.get(metric, window_secs)
        return sum(vals) / len(vals) if vals else None


# ══════════════════════════════════════════════════════════════════════════════
#  COMPARE
# ══════════════════════════════════════════════════════════════════════════════

def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator in ("gt", ">"):
        return value > threshold
    if operator in ("lt", "<"):
        return value < threshold
    if operator in ("gte", ">="):
        return value >= threshold
    if operator in ("lte", "<="):
        return value <= threshold
    if operator in ("eq", "==", "="):
        return abs(value - threshold) < 1e-9
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTION ALARM MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class ProductionAlarmManager:
    def __init__(
        self,
        policies: Optional[list[AlarmPolicy]] = None,
        mqtt_client=None,
        rest_callback_url: Optional[str] = None,
        demo_mode: bool = False,
    ):
        self._policies: dict[str, AlarmPolicy] = {
            p.alarm_id: p for p in (policies or DEFAULT_POLICIES)
        }
        self._notifier = AlarmNotifier(mqtt_client=mqtt_client, rest_callback_url=rest_callback_url)
        self._store = MetricStore()
        self._active_alarms: dict[str, AlarmRecord] = {}
        self._alarm_history: list[AlarmRecord] = []
        self._condition_onset: dict[str, float] = {}  # time.time() based
        self._demo_mode = demo_mode

    def _force_alarm_ready(self, alarm_id: str) -> None:
        """Mark alarm condition as already sustained (for demo/testing).
        Simulates that the window_secs duration has already elapsed."""
        import time as _time
        if alarm_id in self._policies:
            self._condition_onset[alarm_id] = _time.time() - 9999  # far in the past

    def feed_metric(self, metric: str, value: float, tags: Optional[dict] = None) -> None:
        self._store.put(metric, value, tags)

    def feed_batch_quality(self, metrics: dict) -> None:
        if "defect_rate_pct" in metrics:
            self.feed_metric("defect_rate_pct", float(metrics["defect_rate_pct"]), {"batch_id": metrics.get("batch_id")})
        if "grade_a_pct" in metrics:
            self.feed_metric("grade_a_pct", float(metrics["grade_a_pct"]), {"batch_id": metrics.get("batch_id")})
        if "avg_color_score" in metrics:
            self.feed_metric("avg_color_score", float(metrics["avg_color_score"]), {"batch_id": metrics.get("batch_id")})
        if "avg_moisture_pct" in metrics:
            self.feed_metric("moisture_pct", float(metrics["avg_moisture_pct"]), {"batch_id": metrics.get("batch_id")})
        if "throughput_kg_h" in metrics:
            self.feed_metric("throughput_kg_h", float(metrics["throughput_kg_h"]), {"batch_id": metrics.get("batch_id")})

    def feed_sensor_health(self, offline_count: int, anomaly_score: float = 0.0) -> None:
        self.feed_metric("offline_sensor_count", float(offline_count))
        if anomaly_score > 0:
            self.feed_metric("sensor_anomaly_score", float(anomaly_score))

    def feed_mechanical(self, feeder_rate: float, air_pressure: float, motor_temp: float) -> None:
        self.feed_metric("feeder_rate_bpm", float(feeder_rate))
        self.feed_metric("air_pressure_psi", float(air_pressure))
        self.feed_metric("motor_temp_c", float(motor_temp))

    def feed_spc(self, drift_score: float) -> None:
        self.feed_metric("spc_drift_score", float(drift_score))

    def evaluate(self) -> list[AlarmRecord]:
        import time as _time
        now_ts = _time.time()
        newly_fired: list[AlarmRecord] = []

        for alarm_id, policy in self._policies.items():
            if not policy.enable:
                continue

            window = policy.trigger.window_secs
            values = self._store.get(policy.trigger.metric, window if window > 0 else None)

            if not values:
                self._condition_onset.pop(alarm_id, None)
                continue

            latest = values[-1]
            triggered = _compare(latest, policy.trigger.operator, policy.trigger.threshold)

            if triggered:
                if alarm_id not in self._condition_onset:
                    self._condition_onset[alarm_id] = now_ts

                duration = now_ts - self._condition_onset[alarm_id]
                # instant-fire: window == 0 (e.g. E-STOP) fires immediately on first detection
                # timed-fire: window > 0 must persist for window_secs
                fire = (window == 0) or (duration >= window)
                if fire:
                    fired = self._fire_alarm(policy, latest, now_ts)
                    if fired:
                        newly_fired.append(fired)
            else:
                self._condition_onset.pop(alarm_id, None)
                if alarm_id in self._active_alarms:
                    hysteresis_factor = 1.0 - (policy.hysteresis_pct / 100.0)
                    cleared = _compare(latest, policy.trigger.operator, policy.trigger.threshold * hysteresis_factor)
                    if cleared:
                        self._resolve_alarm(alarm_id, "Auto-resolved (condition cleared + hysteresis)")

        return newly_fired

    def _fire_alarm(self, policy: AlarmPolicy, metric_value: float, now_ts: float) -> Optional[AlarmRecord]:
        import time as _time
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        existing = self._active_alarms.get(policy.alarm_id)

        if existing:
            existing.occurrence_count += 1
            existing.total_occurrences += 1
            existing.context["metric_value"] = metric_value
            existing.context["last_updated"] = now_dt.isoformat()

            if not existing.escalated:
                if existing.occurrence_count >= policy.max_occurrences_before_escalation:
                    time_since_first = now_ts - existing.fired_at.timestamp()
                    if time_since_first >= policy.escalation_delay_secs:
                        existing.escalated = True
                        existing.last_escalation_at = now_dt
                        existing.message = f"[ESCALATED] {existing.message}"
            return None

        record = AlarmRecord(
            alarm_id=policy.alarm_id,
            alarm_name=policy.name,
            category=policy.category,
            severity=policy.trigger.severity_at_fire,
            source=AlarmSource.SYSTEM,
            message=policy.description,
            context={
                "metric": policy.trigger.metric,
                "operator": policy.trigger.operator,
                "threshold": policy.trigger.threshold,
                "metric_value": metric_value,
                "window_secs": policy.trigger.window_secs,
            },
            status=AlarmStatus.ACTIVE,
            fired_at=now_dt,
        )

        self._active_alarms[policy.alarm_id] = record
        self._alarm_history.append(record)
        if len(self._alarm_history) > 1000:
            self._alarm_history = self._alarm_history[-1000:]

        self._notifier.notify(record)
        return record

    def _resolve_alarm(self, alarm_id: str, note: str) -> None:
        if alarm_id not in self._active_alarms:
            return
        alarm = self._active_alarms[alarm_id]
        alarm.status = AlarmStatus.RESOLVED
        alarm.resolved_at = datetime.now(timezone.utc)
        alarm.resolution_note = note
        self._active_alarms.pop(alarm_id, None)

    def acknowledge(self, alarm_uid: str, acknowledged_by: str = "operator") -> bool:
        for alarm in self._active_alarms.values():
            if alarm.uid == alarm_uid:
                alarm.status = AlarmStatus.ACKNOWLEDGED
                alarm.acknowledged_at = datetime.now(timezone.utc)
                alarm.acknowledged_by = acknowledged_by
                return True
        return False

    def resolve(self, alarm_uid: str, note: str = "") -> bool:
        for alarm in list(self._active_alarms.values()):
            if alarm.uid == alarm_uid:
                alarm.status = AlarmStatus.RESOLVED
                alarm.resolved_at = datetime.now(timezone.utc)
                alarm.resolution_note = note
                self._active_alarms.pop(alarm.alarm_id, None)
                return True
        return False

    def suppress(self, alarm_id: str, reason: str = "maintenance") -> bool:
        if alarm_id in self._policies:
            self._policies[alarm_id].enable = False
            return True
        return False

    def get_active_alarms(self, category: Optional[AlarmCategory] = None) -> list[AlarmRecord]:
        alarms = list(self._active_alarms.values())
        if category:
            alarms = [a for a in alarms if a.category == category]
        return sorted(alarms, key=lambda a: (a.severity.value, -a.age_secs))

    def get_alarm_history(self, limit: int = 50, category: Optional[AlarmCategory] = None,
                          status: Optional[AlarmStatus] = None) -> list[AlarmRecord]:
        alarms = self._alarm_history[-limit:]
        if category:
            alarms = [a for a in alarms if a.category == category]
        if status:
            alarms = [a for a in alarms if a.status == status]
        return alarms

    def get_active_count(self, severity: Optional[AlarmSeverity] = None) -> int:
        if severity:
            return sum(1 for a in self._active_alarms.values() if a.severity == severity)
        return len(self._active_alarms)

    def get_stats(self) -> dict:
        total = len(self._alarm_history)
        by_status = {"active": 0, "acknowledged": 0, "resolved": 0, "suppressed": 0}
        by_severity = {"info": 0, "warning": 0, "critical": 0, "emergency": 0}
        for a in self._alarm_history:
            by_status[a.status.value] = by_status.get(a.status.value, 0) + 1
            by_severity[a.severity.value] = by_severity.get(a.severity.value, 0) + 1

        resolved = [a for a in self._alarm_history if a.status == AlarmStatus.RESOLVED]
        avg_resolution_secs = sum(a.duration_secs for a in resolved) / len(resolved) if resolved else 0

        return {
            "total_alarms": total,
            "active_count": self.get_active_count(),
            "by_status": by_status,
            "by_severity": by_severity,
            "avg_resolution_secs": round(avg_resolution_secs, 1),
            "policies_count": len(self._policies),
            "enabled_policies_count": sum(1 for p in self._policies.values() if p.enable),
        }

    def generate_report(self) -> dict:
        stats = self.get_stats()
        active = self.get_active_alarms()
        recent = self.get_alarm_history(limit=20)
        return {
            "report_id": f"ALARM-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "active_alarms": [a.to_dict() for a in active],
            "recent_alarms": [a.to_dict() for a in recent],
        }

    def print_status(self) -> None:
        stats = self.get_stats()
        active = self.get_active_alarms()
        print("\n" + "=" * 60)
        print(f"  PRODUCTION ALARM SYSTEM  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print(f"  Policies: {stats['policies_count']} total  |  {stats['enabled_policies_count']} enabled")
        print(f"  Active: {stats['active_count']}  |  Total fired: {stats['total_alarms']}")
        print(f"  Avg resolution: {stats['avg_resolution_secs']:.0f}s")
        print(f"  By Severity:  INFO={stats['by_severity']['info']}  WARN={stats['by_severity']['warning']}  CRIT={stats['by_severity']['critical']}  EMERG={stats['by_severity']['emergency']}")
        if active:
            print(f"\n  Active Alarms ({len(active)}):")
            for a in active:
                age = a.age_secs
                age_str = f"{age:.0f}s" if age < 60 else f"{age/60:.1f}m" if age < 3600 else f"{age/3600:.1f}h"
                icon = {"emergency": "🆘", "critical": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(a.severity.value, "💬")
                status_icon = {"active": "⚡", "acknowledged": "👁️", "resolved": "✅"}.get(a.status.value, "•")
                print(f"    {icon}{status_icon} [{age_str}] {a.alarm_name}")
                print(f"         {a.message}")
                print(f"         context: {a.context}")
        else:
            print("\n  ✅ No active alarms")
        print("=" * 60)

    def save_report(self, path: Optional[Path] = None) -> Path:
        if path is None:
            reports_dir = _project_root / "sorter" / "reports"
            reports_dir.mkdir(exist_ok=True)
            path = reports_dir / f"alarm_report_{datetime.now().strftime('%Y%m%d')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.generate_report(), f, ensure_ascii=False, indent=2)
        return path


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Production Alarm Manager")
    parser.add_argument("--demo", action="store_true", help="Run demo simulation")
    parser.add_argument("--status", action="store_true", help="Show alarm status")
    parser.add_argument("--report", action="store_true", help="Generate and save report")
    args = parser.parse_args()

    if args.demo:
        print("=" * 60)
        print("  PRODUCTION ALARM MANAGER — Demo")
        print("=" * 60)
        mgr = ProductionAlarmManager()

        print("\n── Normal operation ──")
        for i in range(3):
            mgr.feed_metric("defect_rate_pct", 1.2, {"batch_id": "BATCH_001"})
            mgr.feed_metric("throughput_kg_h", 2.1)
            mgr.feed_metric("grade_a_pct", 91.5)
            mgr.evaluate()
            time.sleep(0.05)

        print("\n── Defect rate rising → QUALITY_001 WARNING ──")
        for val in [2.1, 2.3, 2.5, 2.7]:
            mgr.feed_metric("defect_rate_pct", val, {"batch_id": "BATCH_001"})
            mgr.evaluate()
            time.sleep(0.05)

        print("\n── Throughput dropping → THRU_001 WARNING ──")
        for val in [2.0, 1.9, 1.8, 1.7]:
            mgr.feed_metric("throughput_kg_h", val)
            mgr.evaluate()
            time.sleep(0.05)

        print("\n── Critical defect rate → QUALITY_002 CRITICAL ──")
        for val in [5.1, 5.3, 5.5]:
            mgr.feed_metric("defect_rate_pct", val, {"batch_id": "BATCH_001"})
            mgr.evaluate()
            time.sleep(0.05)

        print("\n── Alarms stabilize → Auto-resolve ──")
        for val in [1.0, 0.8, 0.5]:
            mgr.feed_metric("defect_rate_pct", val)
            mgr.feed_metric("throughput_kg_h", 2.2)
            mgr.evaluate()
            time.sleep(0.05)

        mgr.print_status()
        path = mgr.save_report()
        print(f"\n  Report saved: {path}")

    elif args.status:
        mgr = ProductionAlarmManager()
        mgr.print_status()

    elif args.report:
        mgr = ProductionAlarmManager()
        path = mgr.save_report()
        print(f"Alarm report saved: {path}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()