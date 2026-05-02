# sorter/db/models.py
# Data models for HUSKY-SORTER-001 batch & bean records
# Author: Little Husky 🐕 | Date: 2026-05-02

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple
import json


# ─── Enums ────────────────────────────────────────────────────────────────────

class BeanDefect(IntEnum):
    """14 defect types matching ML pipeline classes."""
    NORMAL = 0
    MOLDY = 1
    FERMENTED = 2
    BLACK = 3
    BROKEN = 4
    FOREIGN = 5
    UNDERWEIGHT = 6
    OVERWEIGHT = 7
    STUNTED = 8
    DEAD = 9
    INSECT_DAMAGED = 10
    HOLLOW = 11
    OVER_DRY = 12
    OVER_WET = 13

    @property
    def label(self) -> str:
        labels = [
            "Normal", "Moldy", "Fermented", "Black", "Broken",
            "Foreign", "Underweight", "Overweight", "Stunted", "Dead",
            "Insect Damaged", "Hollow", "Over Dry", "Over Wet",
        ]
        return labels[self.value] if self.value < len(labels) else "Unknown"

    @property
    def severity(self) -> int:
        """1=info, 2=minor, 3=major, 4=critical (affects food safety)."""
        critical = {BeanDefect.MOLDY, BeanDefect.FERMENTED, BeanDefect.BLACK,
                    BeanDefect.FOREIGN, BeanDefect.INSECT_DAMAGED}
        major = {BeanDefect.BROKEN, BeanDefect.DEAD}
        minor = {BeanDefect.UNDERWEIGHT, BeanDefect.OVERWEIGHT,
                 BeanDefect.STUNTED, BeanDefect.HOLLOW, BeanDefect.OVER_DRY, BeanDefect.OVER_WET}
        if self in critical:
            return 4
        if self in major:
            return 3
        if self in minor:
            return 2
        return 1


class BatchState(IntEnum):
    """Batch lifecycle states."""
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    ABORTED = 3
    ARCHIVED = 4


class SortGrade(IntEnum):
    """Coffee bean quality grade (roaster-facing)."""
    GRADE_A = 0  # Premium (>85 score)
    GRADE_B = 1  # Standard (70-85 score)
    GRADE_C = 2  # Below standard (50-70 score)
    REJECT = 3   # Defective — sent to reject bin


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ColorReading:
    """L*a*b* color data from top + bottom cameras."""
    top_L: float
    top_a: float
    top_b: float
    bottom_L: float = 0.0
    bottom_a: float = 0.0
    bottom_b: float = 0.0

    def avg_L(self) -> float:
        return (self.top_L + self.bottom_L) / 2

    def to_dict(self) -> Dict[str, float]:
        return {
            "top_L": self.top_L, "top_a": self.top_a, "top_b": self.top_b,
            "bottom_L": self.bottom_L, "bottom_a": self.bottom_a, "bottom_b": self.bottom_b,
        }


@dataclass
class SensorSnapshot:
    """Multi-sensor readings for a single bean."""
    weight_g: float = 0.0
    moisture_pct: float = 0.0
    density_gcc: float = 0.0
    size_mm: float = 0.0
    color: Optional[ColorReading] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "weight_g": self.weight_g,
            "moisture_pct": self.moisture_pct,
            "density_gcc": self.density_gcc,
            "size_mm": self.size_mm,
        }
        if self.color:
            d["color"] = self.color.to_dict()
        return d


@dataclass
class BeanRecord:
    """
    Per-bean measurement record.
    Corresponds to one coffee bean passing through the sorter.
    """
    bean_id: str                    # UUID
    batch_id: str                   # FK to batch
    timestamp_utc: str               # ISO-8601 UTC
    channel: int = 1                # 1-N channel number
    bean_index: int = 0              # 0-based index within batch

    # Physical measurements
    sensors: SensorSnapshot = field(default_factory=SensorSnapshot)

    # Classification results
    primary_defect: int = 0          # BeanDefect enum value
    secondary_defect: int = 0
    ml_confidence: float = 1.0       # 0.0–1.0

    # Grading
    quality_score: float = 100.0     # 0–100
    grade: int = 0                   # SortGrade enum value

    # Routing
    assigned_bin: str = ""           # e.g. "A1", "BF"
    ejected: bool = False
    eject_reason: str = ""

    # Image paths (if stored)
    top_image_path: str = ""
    bottom_image_path: str = ""

    def is_defective(self) -> bool:
        return self.primary_defect != BeanDefect.NORMAL.value

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "bean_id": self.bean_id,
            "batch_id": self.batch_id,
            "timestamp_utc": self.timestamp_utc,
            "channel": self.channel,
            "bean_index": self.bean_index,
            "sensors": self.sensors.to_dict(),
            "primary_defect": self.primary_defect,
            "primary_defect_label": BeanDefect(self.primary_defect).label,
            "secondary_defect": self.secondary_defect,
            "ml_confidence": round(self.ml_confidence, 4),
            "quality_score": round(self.quality_score, 1),
            "grade": self.grade,
            "grade_label": SortGrade(self.grade).name,
            "assigned_bin": self.assigned_bin,
            "ejected": self.ejected,
            "eject_reason": self.eject_reason,
            "top_image_path": self.top_image_path,
            "bottom_image_path": self.bottom_image_path,
        }
        return d

    def to_sql_values(self) -> Tuple:
        color_json = json.dumps(self.sensors.color.to_dict() if self.sensors.color else {})
        sensors_json = json.dumps({
            "weight_g": self.sensors.weight_g,
            "moisture_pct": self.sensors.moisture_pct,
            "density_gcc": self.sensors.density_gcc,
            "size_mm": self.sensors.size_mm,
        })
        return (
            self.bean_id, self.batch_id, self.timestamp_utc,
            self.channel, self.bean_index,
            sensors_json, color_json,
            self.primary_defect, self.secondary_defect,
            self.ml_confidence, self.quality_score, self.grade,
            self.assigned_bin, self.ejected, self.eject_reason,
            self.top_image_path, self.bottom_image_path,
        )


@dataclass
class BatchRecord:
    """
    Batch-level summary record.
    One batch = one continuous run of beans, typically 250g–2kg.
    """
    batch_id: str                    # UUID
    started_at_utc: str               # ISO-8601 UTC
    ended_at_utc: str = ""
    state: int = BatchState.PENDING.value

    # Configuration
    target_weight_g: float = 250.0
    target_throughput_kg_h: float = 2.0
    channels_used: int = 1

    # Origins (operator input)
    origin: str = ""
    variety: str = ""
    process: str = ""                # washed/natural/honey/etc.
    lot_number: str = ""

    # Summary (computed after batch ends)
    total_beans: int = 0
    defective_beans: int = 0
    ejected_beans: int = 0
    total_weight_g: float = 0.0

    # Grade distribution
    grade_a_count: int = 0
    grade_b_count: int = 0
    grade_c_count: int = 0
    grade_reject_count: int = 0

    # Defect distribution (defect_id -> count)
    defect_counts_json: str = "{}"

    # Quality metrics
    avg_quality_score: float = 0.0
    avg_weight_g: float = 0.0
    avg_moisture_pct: float = 0.0
    avg_density_gcc: float = 0.0
    avg_color_L: float = 0.0

    # Reject reasons
    eject_reasons_json: str = "{}"

    # Notes
    operator_notes: str = ""
    calibration_id: str = ""

    def duration_s(self) -> float:
        try:
            start = datetime.fromisoformat(self.started_at_utc.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.ended_at_utc.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except (ValueError, AttributeError):
            return 0.0

    def throughput_kg_h(self) -> float:
        dur = self.duration_s()
        if dur <= 0:
            return 0.0
        return (self.total_weight_g / 1000) / (dur / 3600)

    def defect_rate_pct(self) -> float:
        if self.total_beans == 0:
            return 0.0
        return (self.defective_beans / self.total_beans) * 100

    def grade_yield_pct(self, grade: SortGrade) -> float:
        denom = self.grade_a_count + self.grade_b_count + self.grade_c_count + self.grade_reject_count
        if denom == 0:
            return 0.0
        counts = {SortGrade.GRADE_A: self.grade_a_count,
                  SortGrade.GRADE_B: self.grade_b_count,
                  SortGrade.GRADE_C: self.grade_c_count,
                  SortGrade.REJECT: self.grade_reject_count}
        return (counts.get(grade, 0) / denom) * 100

    def to_dict(self) -> Dict[str, Any]:
        defect_counts = json.loads(self.defect_counts_json or "{}")
        eject_reasons = json.loads(self.eject_reasons_json or "{}")
        return {
            "batch_id": self.batch_id,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "state": BatchState(self.state).name,
            "target_weight_g": self.target_weight_g,
            "target_throughput_kg_h": self.target_throughput_kg_h,
            "channels_used": self.channels_used,
            "origin": self.origin,
            "variety": self.variety,
            "process": self.process,
            "lot_number": self.lot_number,
            "total_beans": self.total_beans,
            "defective_beans": self.defective_beans,
            "ejected_beans": self.ejected_beans,
            "total_weight_g": round(self.total_weight_g, 2),
            "grade_a_count": self.grade_a_count,
            "grade_b_count": self.grade_b_count,
            "grade_c_count": self.grade_c_count,
            "grade_reject_count": self.grade_reject_count,
            "defect_counts": defect_counts,
            "avg_quality_score": round(self.avg_quality_score, 1),
            "avg_weight_g": round(self.avg_weight_g, 2),
            "avg_moisture_pct": round(self.avg_moisture_pct, 2),
            "avg_density_gcc": round(self.avg_density_gcc, 2),
            "avg_color_L": round(self.avg_color_L, 2),
            "eject_reasons": eject_reasons,
            "operator_notes": self.operator_notes,
            "calibration_id": self.calibration_id,
            # Computed
            "duration_s": round(self.duration_s(), 1),
            "throughput_kg_h": round(self.throughput_kg_h(), 3),
            "defect_rate_pct": round(self.defect_rate_pct(), 2),
            "grade_a_yield_pct": round(self.grade_yield_pct(SortGrade.GRADE_A), 1),
        }

    def to_sql_values(self) -> Tuple:
        return (
            self.batch_id, self.started_at_utc, self.ended_at_utc,
            self.state, self.target_weight_g, self.target_throughput_kg_h,
            self.channels_used, self.origin, self.variety, self.process,
            self.lot_number, self.total_beans, self.defective_beans,
            self.ejected_beans, self.total_weight_g,
            self.grade_a_count, self.grade_b_count, self.grade_c_count,
            self.grade_reject_count, self.defect_counts_json,
            self.avg_quality_score, self.avg_weight_g, self.avg_moisture_pct,
            self.avg_density_gcc, self.avg_color_L,
            self.eject_reasons_json, self.operator_notes, self.calibration_id,
        )


@dataclass
class CalibrationRecord:
    """Record of a sensor calibration event."""
    cal_id: str
    sensor: str                      # load_cell | color_top | color_bottom | moisture | density
    calibration_method: str         # one-point | two-point | five-point | reference
    calibration_date_utc: str
    operator_id: str = ""
    reference_values_json: str = "{}"
    coefficients_json: str = "{}"
    std_error: float = 0.0
    r_squared: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cal_id": self.cal_id,
            "sensor": self.sensor,
            "calibration_method": self.calibration_method,
            "calibration_date_utc": self.calibration_date_utc,
            "operator_id": self.operator_id,
            "reference_values": json.loads(self.reference_values_json or "{}"),
            "coefficients": json.loads(self.coefficients_json or "{}"),
            "std_error": round(self.std_error, 6),
            "r_squared": round(self.r_squared, 4),
            "notes": self.notes,
        }


@dataclass
class SystemEvent:
    """System-level event log entry."""
    event_id: str
    timestamp_utc: str
    severity: str                   # INFO | WARNING | ERROR | CRITICAL
    component: str                   # sorter | mqtt | api | motor | sensor | calibrator
    message: str
    details_json: str = "{}"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "timestamp_utc": self.timestamp_utc,
            "severity": self.severity,
            "component": self.component,
            "message": self.message,
        }
        d.update(json.loads(self.details_json or "{}"))
        return d
