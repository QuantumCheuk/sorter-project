"""
Production Integration Bridge — v1.0
Connects RecipeManager → QualityClassifier → SorterController → Database.
Enables recipe-driven batch processing with end-to-end quality traceability.
"""

import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from sorter.production.batch_recipe_manager import (
    BatchRecipe,
    ColorThresholds,
    DensityThresholds,
    DefectWeights,
    MoistureThresholds,
    RecipeManager,
    WeightThresholds,
)
from sorter.quality.classifier import (
    BeanQualityResult,
    ClassifierMode,
    DefectResult,
    QualityClassifier,
    SensorReading,
)
from sorter.quality.grades import QualityGrade, grade_from_score
from sorter.quality.thresholds import (
    ColorThreshold,
    DefectThreshold,
    DefectType,
    RangeThreshold,
    SensorType,
    ThresholdSet,
)


class ProcessingStage(str, Enum):
    """Batch processing lifecycle stages."""

    CREATED = "created"
    RUNNING = "running"
    QUALITY_CHECK = "quality_check"
    GRADING = "grading"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Section 1: Recipe → ThresholdSet Bridge
# ---------------------------------------------------------------------------


class RecipeToThresholdSetBridge:
    """
    Converts a BatchRecipe's quality targets and defect thresholds
    into a ThresholdSet consumable by QualityClassifier.

    Responsibilities:
    - Map ColorThresholds (top/bottom L*a*b*) → ColorThreshold
    - Map WeightThresholds → RangeThreshold
    - Map MoistureThresholds → RangeThreshold
    - Map DensityThresholds → RangeThreshold
    - Map DefectWeights → DefectThreshold severity weights
    - Build ThresholdSet for QualityClassifier
    """

    @staticmethod
    def _lab_to_color_threshold(ct: ColorThresholds) -> ColorThreshold:
        # Use average of top+bottom ranges as reference point
        l_ref = (ct.top_L_min + ct.top_L_max + ct.bottom_L_min + ct.bottom_L_max) / 4
        a_ref = (ct.top_a_min + ct.top_a_max + ct.bottom_a_min + ct.bottom_a_max) / 4
        b_ref = (ct.top_b_min + ct.top_b_max + ct.bottom_b_min + ct.bottom_b_max) / 4
        # Bounding box from the tightest overlapping ranges
        l_min = max(ct.top_L_min, ct.bottom_L_min)
        l_max = min(ct.top_L_max, ct.bottom_L_max)
        a_min = max(ct.top_a_min, ct.bottom_a_min)
        a_max = min(ct.top_a_max, ct.bottom_a_max)
        b_min = max(ct.top_b_min, ct.bottom_b_min)
        b_max = min(ct.top_b_max, ct.bottom_b_max)
        return ColorThreshold(
            L_ref=l_ref,
            a_ref=a_ref,
            b_ref=b_ref,
            L_min=l_min,
            L_max=l_max,
            a_min=a_min,
            a_max=a_max,
            b_min=b_min,
            b_max=b_max,
        )

    @staticmethod
    def _weight_to_range(wt: WeightThresholds) -> RangeThreshold:
        # Normal range from recipe thresholds
        return RangeThreshold(
            min_val=wt.normal_min_g,
            max_val=wt.normal_max_g,
        )

    @staticmethod
    def _moisture_to_range(mt: MoistureThresholds) -> RangeThreshold:
        return RangeThreshold(
            min_val=mt.target_min_pct,
            max_val=mt.target_max_pct,
        )

    @staticmethod
    def _density_to_range(dt: DensityThresholds) -> RangeThreshold:
        return RangeThreshold(
            min_val=dt.medium_min,
            max_val=dt.medium_max,
        )

    @classmethod
    def build_threshold_set(cls, recipe: BatchRecipe) -> ThresholdSet:
        """Build a ThresholdSet from a BatchRecipe."""
        ts = ThresholdSet()

        # Color
        color_thresh = cls._lab_to_color_threshold(recipe.color)
        weight_thresh = cls._weight_to_range(recipe.weight)
        moisture_thresh = cls._moisture_to_range(recipe.moisture)
        density_thresh = cls._density_to_range(recipe.density)

        # Defect weights → severity
        critical = recipe.defect_weights.MOLD  # 10.0
        major_broken = recipe.defect_weights.BROKEN  # 9.0
        major_fermented = recipe.defect_weights.FERRY  # 9.0
        major_black = recipe.defect_weights.BLACK  # 10.0
        major_insect = recipe.defect_weights.INSECT  # 10.0
        minor_immature = recipe.defect_weights.IMMATURE  # 8.0
        minor_underdev = recipe.defect_weights.UNDERSIZE  # 4.0

        # MOLD (critical color defect — severity from weight, no physical weight threshold)
        mold_thresh = DefectThreshold(
            defect_type=DefectType.MOLD,
            primary_sensor=SensorType.COLOR,
            severity=5,
            color=color_thresh,
        )
        ts.thresholds[DefectType.MOLD] = mold_thresh

        # FERMENTED (critical color defect — severity from weight, no physical weight threshold)
        ferm_thresh = DefectThreshold(
            defect_type=DefectType.FERMENTED,
            primary_sensor=SensorType.COLOR,
            severity=4,
            color=color_thresh,
        )
        ts.thresholds[DefectType.FERMENTED] = ferm_thresh

        # BLACK (critical color defect — severity from weight, no physical weight threshold)
        black_thresh = DefectThreshold(
            defect_type=DefectType.BLACK,
            primary_sensor=SensorType.COLOR,
            severity=5,
            color=color_thresh,
        )
        ts.thresholds[DefectType.BLACK] = black_thresh

        # BROKEN (fragment — physically small, below any normal bean)
        broken_thresh = DefectThreshold(
            defect_type=DefectType.BROKEN,
            severity=3,
            weight=RangeThreshold(
                min_val=0.02,
                max_val=0.08,  # physical fragment range
            ),
            primary_sensor=SensorType.WEIGHT,
        )
        ts.thresholds[DefectType.BROKEN] = broken_thresh

        # UNDERWEIGHT (below recipe's normal_min but above fragment range)
        underwt_thresh = DefectThreshold(
            defect_type=DefectType.UNDERWEIGHT,
            severity=2,
            weight=RangeThreshold(
                min_val=0.08,
                max_val=recipe.weight.normal_min_g,
            ),
            primary_sensor=SensorType.WEIGHT,
        )
        ts.thresholds[DefectType.UNDERWEIGHT] = underwt_thresh

        # HOLLOW (density too light — primary density, weight as severity only)
        # P-004 fix: lower bound 0.30 (physically meaningful), not 0.0
        hollow_thresh = DefectThreshold(
            defect_type=DefectType.HOLLOW,
            primary_sensor=SensorType.DENSITY,
            severity=2,
            density=RangeThreshold(
                min_val=0.30,  # P-004: physical minimum, 0.0 was meaningless
                max_val=recipe.density.medium_min,
            ),
        )
        ts.thresholds[DefectType.HOLLOW] = hollow_thresh

        # UNDERDEVELOPED = IMMATURE (too dry, primary moisture sensor)
        immature_thresh = DefectThreshold(
            defect_type=DefectType.UNDERDEVELOPED,
            primary_sensor=SensorType.MOISTURE,
            severity=3,
            moisture=RangeThreshold(
                min_val=0.0,
                max_val=recipe.moisture.target_min_pct,
            ),
        )
        ts.thresholds[DefectType.UNDERDEVELOPED] = immature_thresh

        # INSECT_DAMAGED (color-based detection — weight as severity only)
        insect_thresh = DefectThreshold(
            defect_type=DefectType.INSECT_DAMAGED,
            primary_sensor=SensorType.COLOR,
            severity=3,
            color=color_thresh,
        )
        ts.thresholds[DefectType.INSECT_DAMAGED] = insect_thresh

        return ts

    @classmethod
    def apply_recipe_to_classifier(
        cls, classifier: QualityClassifier, recipe: BatchRecipe
    ) -> None:
        ts = cls.build_threshold_set(recipe)
        # Replace the classifier's threshold set
        classifier._threshold_set = ts


# ---------------------------------------------------------------------------
# Section 2: Quality Results → Batch Grade Bridge
# ---------------------------------------------------------------------------


@dataclass
class BatchQualitySummary:
    """Aggregated quality metrics for a single batch."""

    batch_id: str
    origin: str
    recipe_name: str
    stage: str
    total_beans: int = 0
    grade_a_count: int = 0
    grade_b_count: int = 0
    grade_c_count: int = 0
    grade_r_count: int = 0
    defect_counts: dict = field(default_factory=dict)
    avg_score: float = 0.0
    quality_score: float = 0.0
    defect_rate_pct: float = 0.0
    created_at: str = ""

    @property
    def grade_a_pct(self) -> float:
        return (self.grade_a_count / self.total_beans * 100) if self.total_beans else 0.0

    @property
    def accept_rate(self) -> float:
        return (
            (self.grade_a_count + self.grade_b_count) / self.total_beans * 100
            if self.total_beans
            else 0.0
        )


class QualityToBatchBridge:
    """
    Aggregates per-bean BeanQualityResult into batch-level quality
    metrics and derives final batch grades.
    """

    @staticmethod
    def aggregate_batch(
        batch_id: str,
        origin: str,
        recipe_name: str,
        bean_results: list[BeanQualityResult],
    ) -> BatchQualitySummary:
        summary = BatchQualitySummary(
            batch_id=batch_id,
            origin=origin,
            recipe_name=recipe_name,
            stage=ProcessingStage.GRADING.value,
            created_at=datetime.now().isoformat() + "Z",
        )

        defect_counts: dict[str, int] = {}
        score_sum = 0.0

        for result in bean_results:
            summary.total_beans += 1
            grade = result.grade
            score = result.quality_score

            score_sum += score
            if grade == QualityGrade.A:
                summary.grade_a_count += 1
            elif grade == QualityGrade.B:
                summary.grade_b_count += 1
            elif grade == QualityGrade.C:
                summary.grade_c_count += 1
            else:
                summary.grade_r_count += 1

            for defect in result.defects:
                key = defect.value if isinstance(defect, DefectType) else str(defect)
                defect_counts[key] = defect_counts.get(key, 0) + 1

        summary.defect_counts = defect_counts
        summary.defect_rate_pct = (
            summary.grade_r_count / summary.total_beans * 100
            if summary.total_beans
            else 0.0
        )
        summary.avg_score = score_sum / summary.total_beans if summary.total_beans else 0.0
        summary.quality_score = summary.avg_score

        return summary

    @staticmethod
    def derive_batch_grade(summary: BatchQualitySummary) -> QualityGrade:
        return grade_from_score(summary.avg_score, summary.defect_rate_pct)


# ---------------------------------------------------------------------------
# Section 3: Production Orchestrator (all 4 layers unified)
# ---------------------------------------------------------------------------


@dataclass
class ProductionSession:
    """Holds the complete state of one production session."""

    session_id: str
    recipe: BatchRecipe
    classifier: QualityClassifier
    stage: str = ProcessingStage.CREATED.value
    batch_ids: list = field(default_factory=list)
    total_beans_processed: int = 0
    start_time: str = ""
    end_time: str = ""
    summaries: list = field(default_factory=list)


class ProductionOrchestrator:
    """
    Unified API tying together all four layers:

    1. RecipeManager     — loads and validates batch recipes
    2. QualityClassifier — applies recipe thresholds to bean stream
    3. SorterController   — drives physical sorting (placeholder)
    4. Database           — persists batch records and audit logs

    Usage:
        orch = ProductionOrchestrator()
        orch.start_session("Ethiopian_Washed")
        for batch_result in orch.run_batch_stream(beans=3000, batch_size=500):
            print(batch_result)
        report = orch.generate_session_report()
    """

    def __init__(self, db_path: str = ":memory:"):
        self.recipe_manager = RecipeManager()
        self.db = None  # Lazy import to avoid startup errors
        self._sessions: dict[str, ProductionSession] = {}
        self._db_path = db_path

    # ---- Recipe Layer ----

    def load_recipe(self, recipe_name: str) -> BatchRecipe:
        recipe = self.recipe_manager.get_recipe(recipe_name)
        if recipe is None:
            raise ValueError(f"Recipe not found: {recipe_name}")
        return recipe

    def list_recipes(self) -> list[str]:
        return self.recipe_manager.list_recipes()

    # ---- Session Management ----

    def start_session(self, recipe_name: str) -> ProductionSession:
        recipe = self.load_recipe(recipe_name)
        classifier = QualityClassifier(mode=ClassifierMode.THRESHOLD_ONLY)
        RecipeToThresholdSetBridge.apply_recipe_to_classifier(classifier, recipe)
        session_id = f"SESSION-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        session = ProductionSession(
            session_id=session_id,
            recipe=recipe,
            classifier=classifier,
            stage=ProcessingStage.RUNNING.value,
            start_time=datetime.now().isoformat() + "Z",
        )
        self._sessions[session_id] = session
        return session

    def end_session(self, session: ProductionSession) -> None:
        session.end_time = datetime.now().isoformat() + "Z"
        session.stage = ProcessingStage.COMPLETED.value

    # ---- Bean Processing ----

    def process_single_bean(
        self, session: ProductionSession, bean_id: str, sensor_readings: dict
    ) -> BeanQualityResult:
        """
        Process one bean through the quality classifier.

        sensor_readings keys:
            weight_g (float), moisture_pct (float), density_g_mL (float),
            top_color (dict with L, a, b),
            bottom_color (dict with L, a, b)
        """
        reading = SensorReading(
            weight_g=sensor_readings.get("weight_g"),
            moisture_pct=sensor_readings.get("moisture_pct"),
            density=sensor_readings.get("density_g_mL"),
        )

        top_color = sensor_readings.get("top_color", {})
        if top_color:
            reading.color_L = top_color.get("L")
            reading.color_a = top_color.get("a")
            reading.color_b = top_color.get("b")
            reading.color_score = top_color.get("color_score")

        result = session.classifier.classify(bean_id=bean_id, reading=reading)
        session.total_beans_processed += 1
        return result

    # ---- Batch Operations ----

    def run_batch(
        self,
        session: ProductionSession,
        batch_id: str,
        bean_stream: list[dict],
    ) -> BatchQualitySummary:
        """Run a batch of beans through the quality pipeline."""
        results = []
        for bean_data in bean_stream:
            result = self.process_single_bean(
                session=session,
                bean_id=bean_data.get("bean_id", "unknown"),
                sensor_readings=bean_data.get("sensor_readings", {}),
            )
            results.append(result)

        summary = QualityToBatchBridge.aggregate_batch(
            batch_id=batch_id,
            origin=session.recipe.origin_country,
            recipe_name=session.recipe.name,
            bean_results=results,
        )
        session.summaries.append(summary)
        session.batch_ids.append(batch_id)
        return summary

    # ---- Reporting ----

    def generate_session_report(self, session: ProductionSession) -> dict:
        total_beans = sum(s.total_beans for s in session.summaries)
        total_grade_a = sum(s.grade_a_count for s in session.summaries)
        total_grade_b = sum(s.grade_b_count for s in session.summaries)
        total_grade_c = sum(s.grade_c_count for s in session.summaries)
        total_grade_r = sum(s.grade_r_count for s in session.summaries)

        all_scores = [s.avg_score for s in session.summaries if s.avg_score > 0]
        overall_avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        overall_defect_rate = (
            total_grade_r / total_beans * 100 if total_beans else 0.0
        )
        overall_grade = grade_from_score(overall_avg_score, overall_defect_rate)

        return {
            "session_id": session.session_id,
            "recipe": session.recipe.name,
            "origin": session.recipe.origin_country,
            "stage": session.stage,
            "total_beans_processed": total_beans,
            "batch_count": len(session.batch_ids),
            "grade_distribution": {
                "A": total_grade_a,
                "B": total_grade_b,
                "C": total_grade_c,
                "R": total_grade_r,
            },
            "grade_a_pct": (total_grade_a / total_beans * 100) if total_beans else 0.0,
            "accept_rate": (
                (total_grade_a + total_grade_b) / total_beans * 100
                if total_beans
                else 0.0
            ),
            "overall_avg_score": overall_avg_score,
            "overall_defect_rate_pct": overall_defect_rate,
            "overall_batch_grade": overall_grade.value,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "batch_summaries": [
                {
                    "batch_id": s.batch_id,
                    "total_beans": s.total_beans,
                    "grade_a_pct": s.grade_a_pct,
                    "accept_rate": s.accept_rate,
                    "avg_score": s.avg_score,
                    "defect_rate_pct": s.defect_rate_pct,
                    "defect_counts": s.defect_counts,
                }
                for s in session.summaries
            ],
        }


# ---------------------------------------------------------------------------
# Section 4: CLI smoke-test
# ---------------------------------------------------------------------------


def _simulate_bean_stream(n: int, origin: str) -> list[dict]:
    """Generate a simulated bean stream for CLI validation."""
    beans = []
    for i in range(n):
        is_defect = random.random() < 0.05
        beans.append(
            {
                "bean_id": f"{origin[:3].upper()}-{i:05d}",
                "sensor_readings": {
                    "weight_g": random.gauss(0.152, 0.015),
                    "moisture_pct": random.gauss(10.5, 1.0),
                    "density_g_mL": random.gauss(1.05, 0.02),
                    "top_color": {
                        "L": random.gauss(48, 5),
                        "a": random.gauss(3, 2),
                        "b": random.gauss(15, 3),
                    },
                    "bottom_color": {
                        "L": random.gauss(47, 5),
                        "a": random.gauss(3, 2),
                        "b": random.gauss(14, 3),
                    },
                },
            }
        )
    return beans


def main():
    print("=" * 60)
    print("Production Integration Bridge — CLI Validation")
    print("=" * 60)

    orch = ProductionOrchestrator()

    # [1] List recipes
    recipes = orch.list_recipes()
    print(f"\n[1] RecipeManager: {len(recipes)} recipes available")
    for r in recipes[:3]:
        print(f"    - {r}")
    if len(recipes) > 3:
        print(f"    ... and {len(recipes) - 3} more")

    # [2] Start session
    print("\n[2] Starting production session: Ethiopian_Washed")
    session = orch.start_session("Ethiopian_Washed")
    print(f"    session_id: {session.session_id}")
    print(f"    origin: {session.recipe.origin_country}")
    print(f"    target_throughput: {session.recipe.quality.target_throughput_kg_h} kg/h")

    # [3] Simulate first batch
    print("\n[3] Running batch 1 (500 beans)")
    beans = _simulate_bean_stream(500, session.recipe.origin_country)
    batch_summary = orch.run_batch(
        session,
        batch_id=f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        bean_stream=beans,
    )
    print(f"    batch_id: {batch_summary.batch_id}")
    print(f"    total_beans: {batch_summary.total_beans}")
    print(f"    Grade A: {batch_summary.grade_a_count} ({batch_summary.grade_a_pct:.1f}%)")
    print(f"    Grade B: {batch_summary.grade_b_count}")
    print(f"    Grade C: {batch_summary.grade_c_count}")
    print(f"    Reject:  {batch_summary.grade_r_count}")
    print(f"    avg_score: {batch_summary.avg_score:.2f}")
    print(f"    defect_rate: {batch_summary.defect_rate_pct:.2f}%")
    print(f"    accept_rate: {batch_summary.accept_rate:.1f}%")
    if batch_summary.defect_counts:
        top_defects = sorted(
            batch_summary.defect_counts.items(), key=lambda x: x[1], reverse=True
        )[:3]
        print(f"    top defects: {top_defects}")

    # [4] Second batch
    print("\n[4] Running batch 2 (500 beans)")
    beans2 = _simulate_bean_stream(500, session.recipe.origin_country)
    batch_summary2 = orch.run_batch(
        session,
        batch_id=f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        bean_stream=beans2,
    )
    print(f"    batch 2: {batch_summary2.total_beans} beans, "
          f"accept_rate={batch_summary2.accept_rate:.1f}%")

    # [5] End session and generate report
    print("\n[5] Ending session and generating final report")
    orch.end_session(session)
    report = orch.generate_session_report(session)
    print(f"    total_beans_processed: {report['total_beans_processed']}")
    print(f"    batch_count: {report['batch_count']}")
    print(f"    overall_avg_score: {report['overall_avg_score']:.2f}")
    print(f"    overall_batch_grade: {report['overall_batch_grade']}")
    print(f"    accept_rate: {report['accept_rate']:.1f}%")
    print(f"    grade_a_pct: {report['grade_a_pct']:.1f}%")

    # [6] Test with different recipe
    print("\n[6] Testing second recipe: Kenyan_Washed")
    session2 = orch.start_session("Kenyan_Washed")
    print(f"    session_id: {session2.session_id}")
    beans3 = _simulate_bean_stream(500, session2.recipe.origin)
    summary3 = orch.run_batch(
        session2,
        batch_id=f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        bean_stream=beans3,
    )
    print(f"    {summary3.total_beans} beans, accept_rate={summary3.accept_rate:.1f}%")
    orch.end_session(session2)

    print("\n✅ Production Integration Bridge validation complete")


if __name__ == "__main__":
    main()