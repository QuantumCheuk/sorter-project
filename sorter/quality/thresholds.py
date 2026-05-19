# sorter/quality/thresholds.py
# Defect threshold configuration for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-04 (v3 — threshold logic v2)

"""
Defect Threshold Configuration
================================
Per-sensor, per-defect-type threshold definitions.
Supports rule-based rejection (without ML inference).

Design Principles (v2/v3):
===========================
- Each sensor threshold defines the NORMAL (acceptable) range for that property
- A measurement OUTSIDE the normal range = defect detected
- Color uses \u0394E (delta-E) from reference normal green: \u0394E > threshold = defect
- Physical properties (weight/density/moisture/size): outside [min,max] = defect

Semantic of is_triggered():
  - is_triggered() returns True when measurement is DEFECTIVE
  - is_critical() returns True for extreme danger values (auto-reject)
  - contains() returns True when value is in NORMAL range (not defective)

Color \u0394E reference: L*=48, a*=+4, b*=+17 (typical green Arabica)
  Normal beans: \u0394E 0-8 from reference
  Defect \u0394E:     >10 from reference

Normal physical ranges:
  Weight:   0.10-0.28 g/bean
  Density:  0.58-0.78 g/mL
  Moisture: 8-14% wet basis
  Size:     14-19 mesh
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math


class DefectType(str, Enum):
    """Known coffee bean defect types."""
    MOLD = "mold"
    FERMENTED = "fermented"
    BLACK = "black"
    BROKEN = "broken"
    FOREIGN = "foreign"
    UNDERWEIGHT = "underweight"
    OVERWEIGHT = "overweight"
    UNDERDEVELOPED = "underdev"
    DEAD = "dead"
    INSECT_DAMAGED = "insect"
    HOLLOW = "hollow"
    OVERDRY = "overdry"
    OVERWET = "overwet"
    MOLD_PRECURSOR = "mold_precursor"
    UNKNOWN = "unknown"


class SensorType(str, Enum):
    COLOR = "color"
    WEIGHT = "weight"
    DENSITY = "density"
    MOISTURE = "moisture"
    SIZE = "size"
    FUSION = "fusion"


# Severity levels (1=minor, 5=critical)
DEFECT_SEVERITY: Dict[DefectType, int] = {
    DefectType.MOLD: 5,
    DefectType.FERMENTED: 4,
    DefectType.BLACK: 5,
    DefectType.FOREIGN: 5,
    DefectType.UNDERWEIGHT: 2,
    DefectType.OVERWEIGHT: 1,
    DefectType.BROKEN: 3,
    DefectType.UNDERDEVELOPED: 2,
    DefectType.DEAD: 3,
    DefectType.INSECT_DAMAGED: 3,
    DefectType.HOLLOW: 2,
    DefectType.OVERDRY: 2,
    DefectType.OVERWET: 2,
    DefectType.MOLD_PRECURSOR: 2,
    DefectType.UNKNOWN: 1,
}


# Normal reference values for green Arabica coffee beans
NORMAL_COLOR_REF = {"L": 48.0, "a": 4.0, "b": 17.0}
NORMAL_WEIGHT_G = (0.10, 0.28)
NORMAL_DENSITY = (0.58, 0.78)
NORMAL_MOISTURE = (8.0, 14.0)
NORMAL_SIZE_MESH = (14.0, 19.0)


@dataclass
class ColorThreshold:
    """
    L*a*b* color threshold using \u0394E (color difference) from reference normal.

    \u0394E = sqrt((L-L_ref)² + (a-a_ref)² + (b-b_ref)²)

    Normal green coffee: \u0394E 0-8 (imperceptible to slight variation)
    Defect:              \u0394E > threshold

    Reference normal: L*=48, a*=+4, b*=+17
    """
    L_ref: float = 48.0
    a_ref: float = 4.0
    b_ref: float = 17.0
    # \u0394E above this → defect detected
    delta_e_threshold: float = 10.0
    # Fast bounding-box pre-filter (must pass or immediate defect)
    L_min: float = 35.0
    L_max: float = 62.0
    a_min: float = -1.0
    a_max: float = 12.0
    b_min: float = 8.0
    b_max: float = 28.0

    def delta_e(self, L: float, a: float, b: float) -> float:
        dL = L - self.L_ref
        da = a - self.a_ref
        db = b - self.b_ref
        return math.sqrt(dL**2 + da**2 + db**2)

    def contains(self, L: float, a: float, b: float) -> bool:
        """
        Returns True if color is NORMAL (acceptable).
        Returns False if color is DEFECTIVE.
        Two-stage: bounding box pre-filter then full \u0394E.
        """
        # Stage 1: bounding box
        if not (self.L_min <= L <= self.L_max
                and self.a_min <= a <= self.a_max
                and self.b_min <= b <= self.b_max):
            return False
        # Stage 2: \u0394E from reference
        return self.delta_e(L, a, b) <= self.delta_e_threshold

    def to_dict(self) -> dict:
        return {
            "L_ref": self.L_ref, "a_ref": self.a_ref, "b_ref": self.b_ref,
            "delta_e_threshold": self.delta_e_threshold,
            "L_range": [self.L_min, self.L_max],
            "a_range": [self.a_min, self.a_max],
            "b_range": [self.b_min, self.b_max],
        }


@dataclass
class RangeThreshold:
    """
    Min-max range for non-color sensors.

    A value OUTSIDE [min_val, max_val] = defective.
    A value OUTSIDE [critical_low, critical_high] = critically defective (auto-reject).
    """
    min_val: float
    max_val: float
    unit: str = ""
    critical_low: Optional[float] = None   # Below this → auto-reject (dangerous)
    critical_high: Optional[float] = None  # Above this → auto-reject (dangerous)

    def contains(self, val: float) -> bool:
        """True = value is in NORMAL range (acceptable, not defective)."""
        return self.min_val <= val <= self.max_val

    def is_critical(self, val: float) -> bool:
        """True = value is in DANGER zone (auto-reject regardless)."""
        if self.critical_low is not None and val < self.critical_low:
            return True
        if self.critical_high is not None and val > self.critical_high:
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "range": [self.min_val, self.max_val],
            "unit": self.unit,
            "critical": [self.critical_low, self.critical_high],
        }


@dataclass
class DefectThreshold:
    """Threshold set for one defect type."""
    defect_type: DefectType
    primary_sensor: SensorType
    severity: int = 1
    enabled: bool = True

    color: Optional[ColorThreshold] = None
    weight: Optional[RangeThreshold] = None
    density: Optional[RangeThreshold] = None
    moisture: Optional[RangeThreshold] = None
    size: Optional[RangeThreshold] = None

    min_confidence: float = 0.7
    # True = ALL sensors must agree; False = ANY sensor = defect
    require_all_sensors: bool = False

    def is_triggered(self, measurements: dict) -> Tuple[bool, float]:
        """
        Returns (is_defective: bool, confidence: float 0-1).

        A defect is triggered when a measurement falls INSIDE
        the defect's defined sensor ranges.

        For color sensors: contains() returns True if NORMAL (not defective).
          → triggered = NOT contains() = color is abnormal
        For physical sensors (weight/density/moisture/size):
          → The defect's range IS the abnormal range (e.g., BROKEN = 0.02-0.08g, below normal).
          → triggered = contains() = value IS in the defect range.

        Only sensors that have a threshold definition for THIS defect
        are checked. A sensor being absent from the defect's definition means
        that sensor is not relevant to detecting this defect type.
        """
        if not self.enabled:
            return False, 0.0

        confidence = measurements.get("confidence", 1.0)
        if confidence < self.min_confidence:
            return False, confidence

        # Only check sensors that are actually defined for this defect threshold
        sensor_checks: List[Tuple[SensorType, bool]] = []

        if self.color and "color_L" in measurements:
            L = measurements["color_L"]
            a = measurements.get("color_a", self.color.a_ref)
            b = measurements.get("color_b", self.color.b_ref)
            # Color: contains() = True if NORMAL → NOT triggered
            #       contains() = False if DEFECTIVE → triggered
            sensor_checks.append((SensorType.COLOR, not self.color.contains(L, a, b)))

        if self.weight and "weight_g" in measurements:
            w = measurements["weight_g"]
            # Physical: the defect's range IS the abnormal range
            # triggered = value IS in the defect range (contains = True)
            sensor_checks.append((SensorType.WEIGHT, self.weight.contains(w)))

        if self.density and "density" in measurements:
            d = measurements["density"]
            sensor_checks.append((SensorType.DENSITY, self.density.contains(d)))

        if self.moisture and "moisture_pct" in measurements:
            m = measurements["moisture_pct"]
            sensor_checks.append((SensorType.MOISTURE, self.moisture.contains(m)))

        if self.size and "size_mesh" in measurements:
            s = measurements["size_mesh"]
            sensor_checks.append((SensorType.SIZE, self.size.contains(s)))

        if not sensor_checks:
            return False, confidence

        total_checks = len(sensor_checks)
        triggered_sensors = [st for st, triggered in sensor_checks if triggered]

        if self.require_all_sensors:
            triggered = len(triggered_sensors) == total_checks
        else:
            triggered = len(triggered_sensors) > 0

        sensor_confidence = len(triggered_sensors) / total_checks
        final_confidence = (confidence + sensor_confidence) / 2
        return triggered, final_confidence


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────
#
# DESIGN RULES:
# 1. Each defect has an EXCLUSIVE normal range — values OUTSIDE = defect
# 2. Normal weight: 0.10-0.28g. Broken <0.08g. Hollow <0.10g. No weight overlap.
# 3. Normal density: 0.58-0.78 g/mL. Underdev <0.58. Dead <0.52. No overlap.
# 4. Normal moisture: 8-14%. Overdry <8%. Overwet >14%. No overlap.
# 5. Color: \u0394E from L*=48/a*=+4/b*=+17 > threshold = defect
# 6. critical_high/low only for truly dangerous extremes, NOT for defect ranges

DEFAULT_THRESHOLDS: Dict[DefectType, DefectThreshold] = {

    # ═══════════════════════════════════════════════════════════════════════
    # COLOR DEFECTS
    # Normal ref: L*=48, a*=+4, b*=+17  →  \u0394E=0
    # Normal beans: \u0394E 0-8 (L* 38-58, a* -1 to +10, b* 10-25)
    # ═══════════════════════════════════════════════════════════════════════

    DefectType.BLACK: DefectThreshold(
        defect_type=DefectType.BLACK,
        primary_sensor=SensorType.COLOR,
        severity=5,
        color=ColorThreshold(
            delta_e_threshold=20.0,   # Obvious black/dark brown
            L_min=0.0, L_max=65.0,   # Very wide — color diff >20 is the real detector, not L box
            a_min=-5.0, a_max=15.0,
            b_min=0.0, b_max=30.0,
        ),
        min_confidence=0.8,
    ),

    DefectType.MOLD: DefectThreshold(
        defect_type=DefectType.MOLD,
        primary_sensor=SensorType.COLOR,
        severity=5,
        color=ColorThreshold(
            delta_e_threshold=15.0,   # Clear discoloration + possible greenish tint
            L_min=0.0, L_max=65.0,   # Very wide — color diff >15 is the real detector, not L box
            a_min=-5.0, a_max=18.0,
            b_min=0.0, b_max=35.0,
        ),
        min_confidence=0.75,
    ),

    DefectType.FERMENTED: DefectThreshold(
        defect_type=DefectType.FERMENTED,
        primary_sensor=SensorType.COLOR,
        severity=4,
        color=ColorThreshold(
            delta_e_threshold=12.0,   # Brownish/reddish discoloration
            L_min=15.0, L_max=70.0,  # Very wide — color diff >12 is the real detector
            a_min=-5.0, a_max=20.0,  # More brown (higher a*)
            b_min=3.0, b_max=38.0,   # More yellow/brown (higher b*)
        ),
        min_confidence=0.7,
    ),

    DefectType.MOLD_PRECURSOR: DefectThreshold(
        defect_type=DefectType.MOLD_PRECURSOR,
        primary_sensor=SensorType.COLOR,
        severity=2,
        color=ColorThreshold(
            # Subtle — just starting to deviate from normal
            # Normal L* 38-58, a* -1 to +8, b* 10-22
            delta_e_threshold=8.0,
            L_min=36.0, L_max=55.0,
            a_min=-1.5, a_max=9.0,
            b_min=7.0, b_max=23.0,
        ),
        # Elevated moisture as supporting sensor (BOTH must agree)
        moisture=RangeThreshold(
            min_val=12.5, max_val=15.0,
            unit="% w.b.",
        ),
        require_all_sensors=True,  # color AND moisture both abnormal
        min_confidence=0.8,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # WEIGHT DEFECTS — P1-17 fix: mutually exclusive ranges
    # Normal: 0.10-0.28g
    # BROKEN:    0.02-0.05g (fragments only)
    # UNDERWEIGHT: 0.05-0.10g (light/immature, normal density)
    # HOLLOW:    density-only defect (no weight trigger — hollow beans
    #            can weigh normally but have low density <0.52 g/mL)
    # OVERWEIGHT: >0.28g
    # ═══════════════════════════════════════════════════════════════════════

    DefectType.BROKEN: DefectThreshold(
        defect_type=DefectType.BROKEN,
        primary_sensor=SensorType.WEIGHT,
        severity=3,
        weight=RangeThreshold(
            min_val=0.02, max_val=0.05,   # Fragment: <0.05g (exclusive with UNDERWEIGHT)
            unit="g",
        ),
        min_confidence=0.7,
    ),

    DefectType.UNDERWEIGHT: DefectThreshold(
        defect_type=DefectType.UNDERWEIGHT,
        primary_sensor=SensorType.WEIGHT,
        severity=2,
        weight=RangeThreshold(
            # Immature/light: 0.05-0.10g (exclusive with BROKEN, exclusive with normal)
            min_val=0.05, max_val=0.10,
            unit="g",
            critical_low=0.05,
        ),
        min_confidence=0.7,
    ),

    DefectType.HOLLOW: DefectThreshold(
        defect_type=DefectType.HOLLOW,
        primary_sensor=SensorType.DENSITY,  # P1-17: density-only, NOT weight
        severity=2,
        density=RangeThreshold(
            # Hollow beans have abnormally low density regardless of weight
            min_val=0.25, max_val=0.52,
            unit="g/mL",
        ),
        min_confidence=0.6,
    ),

    DefectType.OVERWEIGHT: DefectThreshold(
        defect_type=DefectType.OVERWEIGHT,
        primary_sensor=SensorType.WEIGHT,
        severity=1,
        weight=RangeThreshold(
            # Overly large/overripe: > 0.28g normal maximum
            min_val=0.28, max_val=0.60,
            unit="g",
            critical_high=0.60,
        ),
        min_confidence=0.6,
    ),

    DefectType.FOREIGN: DefectThreshold(
        defect_type=DefectType.FOREIGN,
        primary_sensor=SensorType.WEIGHT,
        severity=5,
        # Anything > 0.40g is definitely not a coffee bean
        weight=RangeThreshold(
            min_val=0.40, max_val=200.0,
            unit="g",
        ),
        # Foreign objects (stones) are very dense
        density=RangeThreshold(
            min_val=1.5, max_val=10.0,
            unit="g/mL",
        ),
        require_all_sensors=False,  # Either heavy OR dense = foreign
        min_confidence=0.85,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # DENSITY DEFECTS
    # Normal: 0.58-0.78 g/mL
    # ═══════════════════════════════════════════════════════════════════════

    DefectType.UNDERDEVELOPED: DefectThreshold(
        defect_type=DefectType.UNDERDEVELOPED,
        primary_sensor=SensorType.DENSITY,
        severity=2,
        density=RangeThreshold(
            # Low density: 0.52-0.58 g/mL (just below normal 0.58-0.78)
            # Normal beans: 0.58+ → NOT underdev
            min_val=0.52, max_val=0.58,
            unit="g/mL",
        ),
        min_confidence=0.7,
    ),

    DefectType.DEAD: DefectThreshold(
        defect_type=DefectType.DEAD,
        primary_sensor=SensorType.DENSITY,
        severity=3,
        density=RangeThreshold(
            # Very low density: < 0.52 g/mL (empty/hollow/dead)
            # Normal beans: 0.58+ → NOT dead
            min_val=0.25, max_val=0.52,
            unit="g/mL",
            critical_high=0.52,  # 0.52 marks the boundary — above is underdev or normal
        ),
        min_confidence=0.75,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # MOISTURE DEFECTS
    # Normal: 8-14% wet basis
    # ═══════════════════════════════════════════════════════════════════════

    DefectType.OVERDRY: DefectThreshold(
        defect_type=DefectType.OVERDRY,
        primary_sensor=SensorType.MOISTURE,
        severity=2,
        moisture=RangeThreshold(
            min_val=4.0, max_val=8.0,   # Below normal 8-14% → overdry
            unit="% w.b.",
            critical_high=8.0,
        ),
        min_confidence=0.75,
    ),

    DefectType.OVERWET: DefectThreshold(
        defect_type=DefectType.OVERWET,
        primary_sensor=SensorType.MOISTURE,
        severity=2,
        moisture=RangeThreshold(
            min_val=14.0, max_val=20.0,  # Above normal 8-14% → overwet (mold risk)
            unit="% w.b.",
            critical_low=14.0,
        ),
        min_confidence=0.75,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SIZE DEFECTS
    # Normal: 14-19 mesh
    # ═══════════════════════════════════════════════════════════════════════

    DefectType.INSECT_DAMAGED: DefectThreshold(
        defect_type=DefectType.INSECT_DAMAGED,
        primary_sensor=SensorType.SIZE,
        severity=3,
        size=RangeThreshold(
            min_val=10.0, max_val=14.0,  # Smaller than normal min 14 mesh
            unit="mesh",
            critical_high=14.0,
        ),
        # Supporting color check (discoloration near insect holes)
        color=ColorThreshold(
            delta_e_threshold=14.0,
            L_min=28.0, L_max=55.0,
            a_min=-2.0, a_max=12.0,
            b_min=7.0, b_max=28.0,
        ),
        min_confidence=0.7,
    ),
}


@dataclass
class ThresholdSet:
    """Collection of all defect thresholds."""
    thresholds: Dict[DefectType, DefectThreshold] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    version: str = "3.0"
    notes: str = "v3: Fixed threshold semantics — thresholds define EXCLUSIVE normal ranges, outside = defect. Removed critical_high from BROKEN/HOLLOW that falsely triggered on normal beans."

    def get(self, defect_type: DefectType) -> Optional[DefectThreshold]:
        return self.thresholds.get(defect_type)

    def all_enabled(self) -> List[DefectThreshold]:
        return [t for t in self.thresholds.values() if t.enabled]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "notes": self.notes,
            "thresholds": {
                dt.value: {
                    "enabled": t.enabled,
                    "severity": t.severity,
                    "primary_sensor": t.primary_sensor.value,
                    "min_confidence": t.min_confidence,
                    "require_all_sensors": t.require_all_sensors,
                    "color": t.color.to_dict() if t.color else None,
                    "weight": t.weight.to_dict() if t.weight else None,
                    "density": t.density.to_dict() if t.density else None,
                    "moisture": t.moisture.to_dict() if t.moisture else None,
                    "size": t.size.to_dict() if t.size else None,
                }
                for dt, t in self.thresholds.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThresholdSet":
        ts = cls()
        ts.version = data.get("version", "3.0")
        ts.notes = data.get("notes", "")
        return ts

    @classmethod
    def default(cls) -> "ThresholdSet":
        return cls(thresholds=dict(DEFAULT_THRESHOLDS))


class ThresholdConfig:
    """Manages threshold sets and active profile."""

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path
        self._active_set = ThresholdSet.default()
        self._profiles: Dict[str, ThresholdSet] = {}

    @property
    def active(self) -> ThresholdSet:
        return self._active_set

    def set_active(self, profile_name: str) -> bool:
        if profile_name in self._profiles:
            self._active_set = self._profiles[profile_name]
            return True
        return False

    def register_profile(self, name: str, threshold_set: ThresholdSet):
        self._profiles[name] = threshold_set

    def add_threshold(self, defect_type: DefectType, threshold: DefectThreshold):
        self._active_set.thresholds[defect_type] = threshold

    def disable_threshold(self, defect_type: DefectType):
        if defect_type in self._active_set.thresholds:
            self._active_set.thresholds[defect_type].enabled = False

    def enable_threshold(self, defect_type: DefectType):
        if defect_type in self._active_set.thresholds:
            self._active_set.thresholds[defect_type].enabled = True

    def to_dict(self) -> dict:
        return {
            "active_profile": "default",
            "profiles": {name: ts.to_dict() for name, ts in self._profiles.items()},
            "active": self._active_set.to_dict(),
        }