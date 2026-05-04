# sorter/quality/classifier.py
# Quality classifier using rule-based thresholds for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-04

"""
Quality Classifier
====================
Applies rule-based threshold detection to bean measurements.
Used when ML model is unavailable or as a fallback to ML detection.

Supports two modes:
1. THRESHOLD_ONLY: Pure rule-based, no ML
2. ML_PLUS_RULES: ML detection + rule-based guardrails

The classifier produces a BeanQualityResult for each bean:
- grade: QualityGrade (A/B/C/Reject)
- quality_score: 0-100
- defect_rate_pct: percentage of sensors that flagged defects
- defects: list of detected DefectType values
- should_reject: whether to reject this bean
- sensor_readings: raw sensor values
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from .grades import QualityGrade, GRADE_DEFINITIONS, GradeDefinition
from .thresholds import (
    DefectType, DefectThreshold, ThresholdSet, ThresholdConfig,
    SensorType, DEFAULT_THRESHOLDS
)


class ClassifierMode(str, Enum):
    THRESHOLD_ONLY = "threshold_only"    # Pure rules, no ML
    ML_PLUS_RULES = "ml_plus_rules"     # ML detection + rule guardrails
    RULES_AS_BACKUP = "rules_as_backup" # ML primary, rules if ML unavailable


@dataclass
class SensorReading:
    """Raw sensor readings for one bean."""
    # Color
    color_L: Optional[float] = None
    color_a: Optional[float] = None
    color_b: Optional[float] = None
    color_score: Optional[float] = None
    # Weight
    weight_g: Optional[float] = None
    # Density
    density: Optional[float] = None
    # Moisture
    moisture_pct: Optional[float] = None
    # Size
    size_mesh: Optional[float] = None

    # ML model output (if available)
    ml_defect_probabilities: Optional[Dict[str, float]] = None
    ml_primary_defect: Optional[str] = None
    ml_confidence: float = 1.0  # 0-1

    def to_measurements_dict(self) -> dict:
        d = {"confidence": self.ml_confidence}
        if self.color_L is not None:
            d["color_L"] = self.color_L
            d["color_a"] = self.color_a or 0
            d["color_b"] = self.color_b or 0
            d["color_score"] = self.color_score or 50.0
        if self.weight_g is not None:
            d["weight_g"] = self.weight_g
        if self.density is not None:
            d["density"] = self.density
        if self.moisture_pct is not None:
            d["moisture_pct"] = self.moisture_pct
        if self.size_mesh is not None:
            d["size_mesh"] = self.size_mesh
        return d


@dataclass
class DefectResult:
    """Result of checking one defect threshold."""
    defect_type: DefectType
    triggered: bool
    confidence: float
    primary_sensor: SensorType
    severity: int


@dataclass
class BeanQualityResult:
    """Complete quality classification result for one bean."""
    bean_id: str
    grade: QualityGrade
    quality_score: float          # 0-100
    defect_rate_pct: float        # 0-100
    should_reject: bool
    defects: List[DefectType]    # List of detected defect types
    defect_results: List[DefectResult]  # Per-defect detection details
    sensor_reading: SensorReading
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bean_id": self.bean_id,
            "grade": self.grade.value,
            "quality_score": round(self.quality_score, 2),
            "defect_rate_pct": round(self.defect_rate_pct, 2),
            "should_reject": self.should_reject,
            "defects": [d.value for d in self.defects],
            "defect_count": len(self.defects),
            "notes": self.notes,
        }


def _compute_quality_score(defect_results: List[DefectResult], max_score: float = 100.0) -> float:
    """Compute quality score from defect results.

    Score deduction per defect:
    - Severity 5: -25 points
    - Severity 4: -20 points
    - Severity 3: -15 points
    - Severity 2: -10 points
    - Severity 1: -5 points
    """
    SEVERITY_PENALTIES = {5: 25.0, 4: 20.0, 3: 15.0, 2: 10.0, 1: 5.0}
    total_penalty = sum(
        r.confidence * SEVERITY_PENALTIES.get(r.severity, 10.0)
        for r in defect_results
        if r.triggered
    )
    return max(0.0, max_score - total_penalty)


def _compute_defect_rate(triggered_count: int, total_sensors: int) -> float:
    if total_sensors == 0:
        return 0.0
    return (triggered_count / total_sensors) * 100.0


class QualityClassifier:
    """
    Rule-based quality classifier using threshold definitions.

    Usage:
        classifier = QualityClassifier(mode=ClassifierMode.THRESHOLD_ONLY)
        result = classifier.classify(bean_id="bean-001", reading=sensor_reading)
    """

    def __init__(
        self,
        mode: ClassifierMode = ClassifierMode.THRESHOLD_ONLY,
        threshold_set: Optional[ThresholdSet] = None,
    ):
        self.mode = mode
        self._threshold_set = threshold_set or ThresholdSet.default()
        self._threshold_config = ThresholdConfig()

        # Normal color reference (typical green coffee bean)
        self._normal_color = {"L": 48.0, "a": 4.0, "b": 17.0}

    @property
    def threshold_set(self) -> ThresholdSet:
        return self._threshold_set

    def classify(
        self,
        bean_id: str,
        reading: SensorReading,
        force_reject: bool = False,
    ) -> BeanQualityResult:
        """
        Classify a single bean based on sensor readings and thresholds.

        Args:
            bean_id: Unique identifier for this bean
            reading: Raw sensor readings
            force_reject: If True, always set should_reject=True (for testing)

        Returns:
            BeanQualityResult with grade, score, defect list
        """
        measurements = reading.to_measurements_dict()
        defect_results: List[DefectResult] = []
        detected_defects: List[DefectType] = []

        # Run all enabled thresholds
        for defect_type, threshold in self._threshold_set.thresholds.items():
            if not threshold.enabled:
                continue

            triggered, confidence = threshold.is_triggered(measurements)
            dr = DefectResult(
                defect_type=defect_type,
                triggered=triggered,
                confidence=confidence,
                primary_sensor=threshold.primary_sensor,
                severity=threshold.severity,
            )
            defect_results.append(dr)

            if triggered:
                detected_defects.append(defect_type)

        # ML integration
        if self.mode in (ClassifierMode.ML_PLUS_RULES, ClassifierMode.RULES_AS_BACKUP):
            if reading.ml_primary_defect and reading.ml_confidence > 0.7:
                try:
                    ml_defect = DefectType(reading.ml_primary_defect)
                    if ml_defect not in detected_defects:
                        detected_defects.append(ml_defect)
                        defect_results.append(DefectResult(
                            defect_type=ml_defect,
                            triggered=True,
                            confidence=reading.ml_confidence,
                            primary_sensor=SensorType.COLOR,
                            severity=5,
                        ))
                except ValueError:
                    pass  # Unknown ML defect type

        # Compute scores
        triggered_results = [r for r in defect_results if r.triggered]
        total_checks = len([r for r in defect_results if r.primary_sensor is not None])
        quality_score = _compute_quality_score(triggered_results)
        defect_rate_pct = _compute_defect_rate(len(triggered_results), max(total_checks, 1))

        # Determine grade
        grade = self._grade_from_results(quality_score, defect_rate_pct, detected_defects)

        # Determine rejection
        should_reject = (
            force_reject
            or grade == QualityGrade.REJECT
            or len([d for d in detected_defects if d in (
                DefectType.MOLD, DefectType.BLACK, DefectType.FOREIGN
            )]) > 0
        )

        # Generate notes
        notes = []
        if detected_defects:
            notes.append(f"Detected: {', '.join(d.value for d in detected_defects)}")
        if reading.ml_primary_defect and self.mode != ClassifierMode.THRESHOLD_ONLY:
            notes.append(f"ML: {reading.ml_primary_defect} ({reading.ml_confidence:.0%})")

        return BeanQualityResult(
            bean_id=bean_id,
            grade=grade,
            quality_score=quality_score,
            defect_rate_pct=defect_rate_pct,
            should_reject=should_reject,
            defects=detected_defects,
            defect_results=defect_results,
            sensor_reading=reading,
            notes=notes,
        )

    def _grade_from_results(
        self,
        quality_score: float,
        defect_rate_pct: float,
        defects: List[DefectType],
    ) -> QualityGrade:
        """Determine grade from quality score and defect list."""
        # Critical defects → automatic reject
        critical = {DefectType.MOLD, DefectType.BLACK, DefectType.FOREIGN}
        if any(d in critical for d in defects):
            return QualityGrade.REJECT

        # Score-based grading
        if quality_score >= 95.0 or defect_rate_pct < 1.0:
            return QualityGrade.A
        elif quality_score >= 85.0 or defect_rate_pct < 3.0:
            return QualityGrade.B
        elif quality_score >= 70.0 or defect_rate_pct < 10.0:
            return QualityGrade.C
        else:
            return QualityGrade.REJECT

    def classify_batch(
        self,
        readings: List[SensorReading],
        start_id: int = 0,
    ) -> List[BeanQualityResult]:
        """Classify multiple beans."""
        return [
            self.classify(bean_id=f"bean-{start_id + i}", reading=r)
            for i, r in enumerate(readings)
        ]

    def summary(self, results: List[BeanQualityResult]) -> dict:
        """Generate a summary report from classification results."""
        if not results:
            return {"error": "No results to summarize"}

        total = len(results)
        grade_counts = {g.value: 0 for g in QualityGrade}
        total_defects = sum(len(r.defects) for r in results)
        avg_score = sum(r.quality_score for r in results) / total
        avg_defect_rate = sum(r.defect_rate_pct for r in results) / total
        reject_count = sum(1 for r in results if r.should_reject)

        for r in results:
            grade_counts[r.grade.value] += 1

        defect_counts: Dict[str, int] = {}
        for r in results:
            for d in r.defects:
                defect_counts[d.value] = defect_counts.get(d.value, 0) + 1

        return {
            "total_beans": total,
            "grade_distribution": grade_counts,
            "avg_quality_score": round(avg_score, 2),
            "avg_defect_rate_pct": round(avg_defect_rate, 2),
            "total_defects": total_defects,
            "defect_counts": defect_counts,
            "reject_count": reject_count,
            "accept_count": total - reject_count,
            "accept_rate_pct": round((total - reject_count) / total * 100, 2),
        }