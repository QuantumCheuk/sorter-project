# sorter/quality/__init__.py
# Quality grading and threshold management for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-04

"""
Quality Grading & Threshold Management
========================================
Manages quality grades, defect thresholds, and classification rules
for bean sorting. Integrates with the multi-sensor fusion system.

Key components:
- QualityGrade: Grade A/B/C/Reject definitions
- DefectThreshold: Per-defect-type threshold config
- QualityClassifier: Applies thresholds to bean records
- GradeSummary: Aggregates batch-level grade stats
"""

from .grades import QualityGrade, GradeDefinition, GradeSummary, compute_batch_grades, grade_from_score
from .thresholds import DefectType, DefectThreshold, ThresholdConfig, ThresholdSet, SensorType
from .classifier import QualityClassifier, ClassifierMode, SensorReading, BeanQualityResult
from .config import QualityConfig, load_quality_config, save_quality_config, get_quality_config

__all__ = [
    "QualityGrade",
    "GradeDefinition",
    "GradeSummary",
    "compute_batch_grades",
    "grade_from_score",
    "DefectType",
    "DefectThreshold",
    "ThresholdConfig",
    "ThresholdSet",
    "SensorType",
    "QualityClassifier",
    "ClassifierMode",
    "SensorReading",
    "BeanQualityResult",
    "QualityConfig",
    "load_quality_config",
    "save_quality_config",
    "get_quality_config",
]