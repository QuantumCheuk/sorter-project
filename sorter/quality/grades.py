# sorter/quality/grades.py
# Quality grade definitions for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-04

"""
Quality Grade Definitions
==========================
Defines grade tiers (A/B/C/Reject), grade boundaries,
and batch-level grade aggregation.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class QualityGrade(str, Enum):
    """Bean quality grade levels."""
    A = "A"      # Premium — defect rate < 1%
    B = "B"      # Standard — defect rate 1-3%
    C = "C"      # Economy — defect rate 3-10%
    REJECT = "R" # Reject — defect rate > 10% or critical defects


GRADE_SYMBOLS = {
    QualityGrade.A: "🅰️",
    QualityGrade.B: "🅱️",
    QualityGrade.C: "🅲",
    QualityGrade.REJECT: "❌",
}


@dataclass
class GradeDefinition:
    """Definition of a single quality grade tier."""
    grade: QualityGrade
    name: str
    min_score: float       # Minimum quality score (0-100) for this grade
    max_defect_rate: float # Maximum defect rate (%) to qualify
    color_hex: str         # UI color for this grade
    price_multiplier: float # Price multiplier vs base price
    description: str       # Human-readable description

    # Defect-type-specific allowances
    allow_mold: bool = False
    allow_fermented: bool = False
    allow_black: bool = False
    allow_broken: bool = False
    allow_underdev: bool = True   # Underdeveloped beans tolerated in lower grades
    allow_empty: bool = True
    allow_dry: bool = True
    allow_wet: bool = True


# Default grade definitions
GRADE_DEFINITIONS: Dict[QualityGrade, GradeDefinition] = {
    QualityGrade.A: GradeDefinition(
        grade=QualityGrade.A,
        name="Premium",
        min_score=95.0,
        max_defect_rate=1.0,   # <1% defect rate
        color_hex="#00C853",
        price_multiplier=1.5,
        description="Premium specialty grade. Near-zero defects, optimal moisture & density.",
        allow_mold=False,
        allow_fermented=False,
        allow_black=False,
        allow_broken=False,
        allow_underdev=False,
        allow_empty=False,
        allow_dry=False,
        allow_wet=False,
    ),
    QualityGrade.B: GradeDefinition(
        grade=QualityGrade.B,
        name="Standard",
        min_score=85.0,
        max_defect_rate=3.0,   # 1-3% defect rate
        color_hex="#64DD17",
        price_multiplier=1.2,
        description="Standard commercial grade. Minor defects acceptable, good cup quality.",
        allow_mold=False,
        allow_fermented=False,
        allow_black=False,
        allow_broken=False,
        allow_underdev=True,
        allow_empty=True,
        allow_dry=True,
        allow_wet=True,
    ),
    QualityGrade.C: GradeDefinition(
        grade=QualityGrade.C,
        name="Economy",
        min_score=70.0,
        max_defect_rate=10.0,  # 3-10% defect rate
        color_hex="#FFC107",
        price_multiplier=1.0,
        description="Economy grade. Visible defects acceptable for blending use.",
        allow_mold=False,
        allow_fermented=True,
        allow_black=False,
        allow_broken=True,
        allow_underdev=True,
        allow_empty=True,
        allow_dry=True,
        allow_wet=True,
    ),
    QualityGrade.REJECT: GradeDefinition(
        grade=QualityGrade.REJECT,
        name="Reject",
        min_score=0.0,
        max_defect_rate=100.0,  # >10% or any critical
        color_hex="#D50000",
        price_multiplier=0.0,
        description="Reject — do not use. Critical defects or excessive defect rate.",
        allow_mold=True,
        allow_fermented=True,
        allow_black=True,
        allow_broken=True,
        allow_underdev=True,
        allow_empty=True,
        allow_dry=True,
        allow_wet=True,
    ),
}


@dataclass
class GradeSummary:
    """Aggregated grade statistics for a batch."""
    grade: QualityGrade
    bean_count: int
    total_weight_g: float
    defect_count: int
    defect_rate_pct: float
    avg_quality_score: float
    avg_moisture_pct: Optional[float] = None
    avg_weight_g: Optional[float] = None
    avg_density: Optional[float] = None
    avg_color_score: Optional[float] = None
    defect_breakdown: Dict[str, int] = field(default_factory=dict)

    @property
    def grade_symbol(self) -> str:
        return GRADE_SYMBOLS.get(self.grade, "❓")

    @property
    def grade_definition(self) -> GradeDefinition:
        return GRADE_DEFINITIONS[self.grade]

    def to_dict(self) -> dict:
        return {
            "grade": self.grade.value,
            "grade_symbol": self.grade_symbol,
            "bean_count": self.bean_count,
            "total_weight_kg": round(self.total_weight_g / 1000, 4),
            "defect_count": self.defect_count,
            "defect_rate_pct": round(self.defect_rate_pct, 3),
            "avg_quality_score": round(self.avg_quality_score, 2),
            "avg_moisture_pct": round(self.avg_moisture_pct, 2) if self.avg_moisture_pct else None,
            "avg_weight_g": round(self.avg_weight_g, 4) if self.avg_weight_g else None,
            "avg_density": round(self.avg_density, 4) if self.avg_density else None,
            "avg_color_score": round(self.avg_color_score, 2) if self.avg_color_score else None,
            "defect_breakdown": self.defect_breakdown,
        }


def compute_batch_grades(graded_beans: List[dict]) -> Dict[QualityGrade, GradeSummary]:
    """
    Aggregate bean records into grade summaries.

    Args:
        graded_beans: List of bean records, each must have:
            - grade: QualityGrade value
            - weight_g: float
            - quality_score: float
            - defect_rate_pct: float
            - defects: list of defect type strings
            - moisture_pct, density, color_score (optional)

    Returns:
        Dict mapping each QualityGrade to its GradeSummary
    """
    buckets: Dict[QualityGrade, List[dict]] = {g: [] for g in QualityGrade}

    for bean in graded_beans:
        try:
            grade_val = bean.get("grade", "R")
            grade = QualityGrade(grade_val) if isinstance(grade_val, str) else QualityGrade.R
        except ValueError:
            grade = QualityGrade.REJECT
        buckets[grade].append(bean)

    summaries = {}
    for grade, beans in buckets.items():
        if not beans:
            continue

        total_weight = sum(b.get("weight_g", 0) for b in beans)
        total_defects = sum(len(b.get("defects", [])) for b in beans)
        total_defect_rate = sum(b.get("defect_rate_pct", 0) for b in beans) / len(beans)
        avg_score = sum(b.get("quality_score", 0) for b in beans) / len(beans)

        moisture_vals = [b["moisture_pct"] for b in beans if "moisture_pct" in b and b["moisture_pct"] is not None]
        weight_vals = [b["weight_g"] for b in beans if "weight_g" in b]
        density_vals = [b["density"] for b in beans if "density" in b and b["density"] is not None]
        color_vals = [b["color_score"] for b in beans if "color_score" in b and b["color_score"] is not None]

        defect_breakdown: Dict[str, int] = {}
        for b in beans:
            for d in b.get("defects", []):
                defect_breakdown[d] = defect_breakdown.get(d, 0) + 1

        summaries[grade] = GradeSummary(
            grade=grade,
            bean_count=len(beans),
            total_weight_g=total_weight,
            defect_count=total_defects,
            defect_rate_pct=total_defect_rate,
            avg_quality_score=avg_score,
            avg_moisture_pct=sum(moisture_vals) / len(moisture_vals) if moisture_vals else None,
            avg_weight_g=sum(weight_vals) / len(weight_vals) if weight_vals else None,
            avg_density=sum(density_vals) / len(density_vals) if density_vals else None,
            avg_color_score=sum(color_vals) / len(color_vals) if color_vals else None,
            defect_breakdown=defect_breakdown,
        )

    return summaries


def grade_from_score(score: float, defect_rate: float = 0.0) -> QualityGrade:
    """
    Map a quality score (and optional defect rate) to a grade.

    Args:
        score: Quality score 0-100
        defect_rate: Defect rate percentage

    Returns:
        QualityGrade enum value
    """
    if score >= 95.0 or defect_rate < 1.0:
        return QualityGrade.A
    elif score >= 85.0 or defect_rate < 3.0:
        return QualityGrade.B
    elif score >= 70.0 or defect_rate < 10.0:
        return QualityGrade.C
    else:
        return QualityGrade.REJECT