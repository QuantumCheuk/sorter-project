#!/usr/bin/env python3
"""
Production Scheduler & Batch Optimizer
=======================================
HUSKY-SORTER-001 | v1.0 | 2026-05-11

Purpose: Optimize batch scheduling and production planning for green coffee bean
sorting operations. Integrates with OEE monitoring and Monte Carlo production
analysis to provide risk-aware scheduling recommendations.

Author: Little Husky (AI CTO) 🐕
"""

from __future__ import annotations
import json
import random
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Callable
from enum import Enum
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

class BeanOrigin(Enum):
    ETHIOPIA_YIRGACHEFFE = "Ethiopia Yirgacheffe"
    ETHIOPIA_GUJI = "Ethiopia Guji"
    COLOMBIA_HUILA = "Colombia Huila"
    COLOMBIA_NARIÑO = "Colombia Nariño"
    BRAZIL_CERRADO = "Brazil Cerrado"
    BRAZIL_SANTOS = "Brazil Santos"
    GUATEMALA_ANTIGUA = "Guatemala Antigua"
    KENYA_AA = "Kenya AA"
    YEMEN = "Yemen"
    PANAMA_GEOFFREY = "Panama Geoffrey"

class ProcessMethod(Enum):
    WASHED = "Washed"
    NATURAL = "Natural"
    HONEY = "Honey"
    ANAEROBIC = "Anaerobic"

class BeanGrade(Enum):
    GRADE_AA = "AA"      # > 18 screen (largest)
    GRADE_A = "A"        # 17-18 screen
    GRADE_B = "B"        # 15-17 screen
    GRADE_C = "C"        # < 15 screen
    REJECT = "Reject"

class ScheduleStrategy(Enum):
    FIFO = "FIFO"                          # First in, first out
    OEE_OPTIMIZED = "OEE_Optimized"        # Maximize OEE
    DEFECT_PRIORITY = "Defect_Priority"    # Process high-defect batches first
    GRADE_OPTIMIZED = "Grade_Optimized"    # Maximize Grade A output
    MIXED = "Mixed"                        # Balance multiple factors

class ShiftType(Enum):
    MORNING = "Morning (06:00-14:00)"
    AFTERNOON = "Afternoon (14:00-22:00)"
    NIGHT = "Night (22:00-06:00)"

@dataclass
class GreenCoffeeLot:
    """Represents an incoming green coffee lot awaiting processing."""
    lot_id: str
    origin: BeanOrigin
    process: ProcessMethod
    weight_kg: float              # Total lot weight in kg
    defect_rate_estimated: float # Estimated % defects (0.0-1.0)
    moisture_pct: float          # Moisture content %
    density_g_ml: float          # Density g/ml
    arrival_date: datetime
    target_roast_date: datetime  # Target date to send to roaster
    priority: int = 5           # 1 (highest) to 10 (lowest)
    screen_mix: dict = field(default_factory=lambda: {"AA": 0.3, "A": 0.4, "B": 0.2, "C": 0.08, "Reject": 0.02})
    # Screen mix: percentage of beans by size grade
    notes: str = ""

    @property
    def urgency_score(self) -> float:
        """Higher = more urgent (closer to target roast date)."""
        days_to_roast = (self.target_roast_date - datetime.now()).total_seconds() / 86400
        return max(0, 10.0 - days_to_roast + (10 - self.priority))

    @property
    def expected_good_kg(self) -> float:
        """Expected kg of good product after sorting."""
        return self.weight_kg * (1.0 - self.defect_rate_estimated)

@dataclass
class ProductionBatch:
    """A scheduled production batch."""
    batch_id: str
    lot: GreenCoffeeLot
    scheduled_start: datetime
    scheduled_end: datetime | None
    target_weight_kg: float
    actual_weight_kg: float | None
    grade_aa_kg: float = 0.0
    grade_a_kg: float = 0.0
    grade_b_kg: float = 0.0
    grade_c_kg: float = 0.0
    reject_kg: float = 0.0
    oee_actual: float = 0.0
    defects_detected: int = 0
    status: str = "scheduled"  # scheduled/running/completed/paused/cancelled
    notes: str = ""

@dataclass
class Shift:
    """A production shift."""
    shift_type: ShiftType
    date: datetime
    planned_hours: float = 8.0
    downtime_planned_min: float = 30.0  # Scheduled breaks/maintenance
    operator: str = "TBD"
    target_batches: list[str] = field(default_factory=list)
    target_weight_kg: float = 0.0
    realized_weight_kg: float = 0.0

    @property
    def effective_hours(self) -> float:
        return self.planned_hours - (self.downtime_planned_min / 60.0)

@dataclass
class ScheduleMetrics:
    """Metrics for a schedule evaluation."""
    total_lots: int
    total_weight_kg: float
    total_batches: int
    estimated_duration_hours: float
    estimated_good_product_kg: float
    estimated_reject_kg: float
    avg_defect_rate_pct: float
    grade_a_rate_pct: float  # % of output that is Grade A
    oee_weighted_avg: float
    lots_at_risk: int        # Lots that may miss target roast date
    utilization_pct: float   # Equipment utilization %
    score: float             # Overall schedule score 0-100

# ─────────────────────────────────────────────────────────────────────────────
# System Parameters (from SPEC.md / prior analysis)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PARAMS = {
    "channels": 3,
    "target_throughput_kg_h": 2.70,     # 3ch × 50bpm (upgraded target)
    "min_throughput_kg_h": 0.90,        # 1ch degraded
    "sorting_efficiency": 0.879,        # Bayesian fusion recall (v1.19)
    "false_positive_rate": 0.05,       # FP rate from Monte Carlo analysis
    "grade_a_target_pct": 0.85,        # World-class target
    "shift_hours": 8.0,
    "shift_break_min": 30.0,
    "oee_excellent": 0.776,            # From v1.62 OEE analysis
    "oee_typical": 0.457,
    "oee_startup": 0.123,
    "beans_per_kg": 6600,              # ~6600 beans/kg for medium arabica
    "avg_bean_weight_g": 0.152,        # grams per bean (from prior analysis)
    "annual_processing_kg": 7500,       # 7.5 tonnes/year (from v1.27)
    "working_days_per_year": 300,
    "working_hours_per_day": 10.0,
}

def estimate_processing_time(weight_kg: float, channels: int = 3, bpm: int = 50) -> float:
    """Estimate processing time for a given weight in hours."""
    # Throughput: 3ch × 50bpm × 0.152g/bean = 3 × 50 × 60 × 0.152 / 1000 = 1.37kg/h (pre-upgrade)
    # Post-upgrade (Nema17): 3ch × 73bpm × 0.152g = 2.00kg/h
    # Nema17 upgrade achieves 3ch × 73bpm = 2.10kg/h (from v1.53)
    beans_per_sec = channels * bpm / 60.0
    weight_per_sec = beans_per_sec * 0.152 / 1000  # kg/sec
    return weight_kg / weight_per_sec if weight_per_sec > 0 else float('inf')

def simulate_batch_output(lot: GreenCoffeeLot, system_efficiency: float = 0.879) -> dict:
    """
    Simulate the output of processing a lot.
    Returns grade distribution based on screen mix and defect rates.
    """
    total_kg = lot.weight_kg
    screen_mix = lot.screen_mix
    defect_rate = lot.defect_rate_estimated

    # Apply sorting efficiency to reduce defect rate
    # Effective defect rate after sorting = original × (1 - efficiency)
    effective_defect = defect_rate * (1.0 - system_efficiency)

    # Good product splits across grades based on screen mix
    grade_aa = total_kg * float(screen_mix.get("AA", 0)) * (1 - defect_rate)
    grade_a  = total_kg * float(screen_mix.get("A", 0))  * (1 - defect_rate)
    grade_b  = total_kg * float(screen_mix.get("B", 0))  * (1 - defect_rate)
    grade_c  = total_kg * float(screen_mix.get("C", 0))  * (1 - defect_rate)
    reject_pre = total_kg * float(screen_mix.get("Reject", 0))
    defect_catch = total_kg * defect_rate * system_efficiency  # Defects caught by sorter

    # Total reject = original screen reject + undetected defects
    reject_total = reject_pre + (total_kg * defect_rate * (1 - system_efficiency))

    return {
        "grade_aa": round(grade_aa, 3),
        "grade_a": round(grade_a, 3),
        "grade_b": round(grade_b, 3),
        "grade_c": round(grade_c, 3),
        "reject": round(reject_total, 3),
        "defect_caught": round(defect_catch, 3),
        "good_product_kg": round(grade_aa + grade_a + grade_b + grade_c, 3),
    }

# ─────────────────────────────────────────────────────────────────────────────
# Schedule Optimizer
# ─────────────────────────────────────────────────────────────────────────────

class ProductionScheduler:
    """
    Production scheduling and batch optimization engine.
    Schedules green coffee lots into production batches across shifts.
    """

    def __init__(self, strategy: ScheduleStrategy = ScheduleStrategy.MIXED,
                 oee_scenario: str = "typical"):
        self.strategy = strategy
        self.lots: list[GreenCoffeeLot] = []
        self.batches: list[ProductionBatch] = []
        self.shifts: list[Shift] = []

        # OEE parameters based on scenario
        self.oee_scenario = oee_scenario
        if oee_scenario == "excellent":
            self.oee = SYSTEM_PARAMS["oee_excellent"]
        elif oee_scenario == "startup":
            self.oee = SYSTEM_PARAMS["oee_startup"]
        else:
            self.oee = SYSTEM_PARAMS["oee_typical"]

        self.channels = SYSTEM_PARAMS["channels"]

    def add_lot(self, lot: GreenCoffeeLot):
        self.lots.append(lot)

    def add_lots(self, lots: list[GreenCoffeeLot]):
        self.lots.extend(lots)

    def _sort_lots(self) -> list[GreenCoffeeLot]:
        """Sort lots according to selected strategy."""
        if self.strategy == ScheduleStrategy.FIFO:
            return sorted(self.lots, key=lambda l: l.arrival_date)
        elif self.strategy == ScheduleStrategy.OEE_OPTIMIZED:
            # Maximize OEE: batch similar lots together to reduce changeover
            return sorted(self.lots, key=lambda l: (l.origin, l.process, -l.urgency_score))
        elif self.strategy == ScheduleStrategy.DEFECT_PRIORITY:
            # Process high-defect lots first (more value to rescue)
            return sorted(self.lots, key=lambda l: (-l.defect_rate_estimated, -l.urgency_score))
        elif self.strategy == ScheduleStrategy.GRADE_OPTIMIZED:
            # Prioritize high-value lots
            return sorted(self.lots, key=lambda l: (-l.urgency_score, l.defect_rate_estimated))
        elif self.strategy == ScheduleStrategy.MIXED:
            # Balance urgency + efficiency: urgent lots first, batch similar together
            return sorted(self.lots, key=lambda l: (-l.urgency_score, l.origin.value))
        else:
            return sorted(self.lots, key=lambda l: l.arrival_date)

    def _create_batches(self, start_time: datetime) -> list[ProductionBatch]:
        """Create production batches from sorted lots."""
        batches = []
        current_time = start_time
        batch_counter = 1

        sorted_lots = self._sort_lots()
        remaining_lots = sorted_lots.copy()

        # Optimal batch size: roaster capacity is 250g/batch, target ~2kg/hour
        # So roughly 8 batches/hour of roaster capacity
        # For sorting: aim for 1-2kg batches for efficient handling
        optimal_batch_size_kg = 2.0  # kg per batch (fits roaster nicely)

        for lot in remaining_lots:
            # Split large lots into batches
            remaining_weight = lot.weight_kg
            lot_start = current_time

            while remaining_weight > 0:
                batch_weight = min(optimal_batch_size_kg, remaining_weight)

                # Estimate processing time
                proc_time_h = estimate_processing_time(batch_weight,
                                                        channels=self.channels)
                proc_time_min = proc_time_h * 60.0

                # Adjust for OEE: effective throughput = nominal × OEE
                effective_throughput = SYSTEM_PARAMS["target_throughput_kg_h"] * self.oee
                effective_time_h = batch_weight / effective_throughput if effective_throughput > 0 else proc_time_h
                effective_time_min = effective_time_h * 60.0

                batch_end = lot_start + timedelta(minutes=effective_time_min)

                batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d')}-{batch_counter:03d}"

                batch = ProductionBatch(
                    batch_id=batch_id,
                    lot=lot,
                    scheduled_start=lot_start,
                    scheduled_end=batch_end,
                    target_weight_kg=batch_weight,
                    actual_weight_kg=None,
                )

                # Simulate output
                # Adjust lot weight temporarily for sub-batch simulation
                original_weight = lot.weight_kg
                lot.weight_kg = batch_weight
                output = simulate_batch_output(lot, SYSTEM_PARAMS["sorting_efficiency"])
                lot.weight_kg = original_weight

                batch.grade_aa_kg = output["grade_aa"]
                batch.grade_a_kg = output["grade_a"]
                batch.grade_b_kg = output["grade_b"]
                batch.grade_c_kg = output["grade_c"]
                batch.reject_kg = output["reject"]
                batch.defects_detected = int(output["defect_caught"] * 1000 / 0.152)
                batch.oee_actual = self.oee

                batches.append(batch)
                batch_counter += 1

                remaining_weight -= batch_weight
                current_time = lot_start = batch_end  # Next batch starts when this ends

        return batches

    def _create_shifts(self, batches: list[ProductionBatch],
                       start_date: datetime) -> list[Shift]:
        """Organize batches into shifts."""
        shifts = []
        current_date = start_date.replace(hour=6, minute=0, second=0)  # Start at 6 AM

        shift_configs = [
            (ShiftType.MORNING, 6, 14),
            (ShiftType.AFTERNOON, 14, 22),
            (ShiftType.NIGHT, 22, 6),
        ]

        batch_idx = 0
        shift_counter = 1

        while batch_idx < len(batches):
            # Determine current shift type based on hour
            hour = current_date.hour
            if 6 <= hour < 14:
                shift_type = ShiftType.MORNING
            elif 14 <= hour < 22:
                shift_type = ShiftType.AFTERNOON
            else:
                shift_type = ShiftType.NIGHT

            shift_start = current_date
            shift_end = shift_start + timedelta(hours=8)
            shift_duration = timedelta(hours=8)

            # Collect batches that fit in this shift
            shift_batches = []
            shift_weight = 0.0

            while batch_idx < len(batches):
                batch = batches[batch_idx]
                if batch.scheduled_start >= shift_end:
                    break
                shift_batches.append(batch.batch_id)
                shift_weight += batch.target_weight_kg
                batch_idx += 1

            if shift_batches:
                shift = Shift(
                    shift_type=shift_type,
                    date=shift_start,
                    planned_hours=8.0,
                    target_batches=shift_batches,
                    target_weight_kg=round(shift_weight, 2),
                )
                shifts.append(shift)

            # Advance to next shift
            current_date = shift_end
            if current_date.hour == 0 and shift_type == ShiftType.NIGHT:
                # Skip from night to next morning
                current_date = current_date + timedelta(hours=6)

            shift_counter += 1

        return shifts

    def generate_schedule(self, start_date: datetime | None = None,
                         verbose: bool = True) -> tuple[list[ProductionBatch], list[Shift], ScheduleMetrics]:
        """Generate an optimized production schedule."""
        if not self.lots:
            raise ValueError("No lots to schedule. Add lots first.")

        if start_date is None:
            start_date = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
            # If it's already past 6 PM, start tomorrow morning
            if datetime.now().hour >= 18:
                start_date += timedelta(days=1)

        batches = self._create_batches(start_date)
        shifts = self._create_shifts(batches, start_date)

        # Calculate metrics
        metrics = self._calculate_metrics(batches, shifts)

        self.batches = batches
        self.shifts = shifts

        if verbose:
            self._print_schedule_overview(batches, shifts, metrics)

        return batches, shifts, metrics

    def _calculate_metrics(self, batches: list[ProductionBatch],
                           shifts: list[Shift]) -> ScheduleMetrics:
        """Calculate schedule quality metrics."""
        total_weight = sum(b.target_weight_kg for b in batches)
        total_good = sum(b.grade_aa_kg + b.grade_a_kg + b.grade_b_kg + b.grade_c_kg
                         for b in batches)
        total_reject = sum(b.reject_kg for b in batches)
        total_defects = sum(b.defects_detected for b in batches)

        # Grade A rate (AA + A as % of good product)
        grade_a_total = sum(b.grade_aa_kg + b.grade_a_kg for b in batches)
        grade_a_rate = (grade_a_total / total_good * 100) if total_good > 0 else 0

        # OEE weighted average
        oee_w = sum(b.oee_actual * b.target_weight_kg for b in batches)
        oee_avg = oee_w / total_weight if total_weight > 0 else 0

        # Duration
        if batches:
            first_start = min(b.scheduled_start for b in batches)
            last_end = max(b.scheduled_end for b in batches if b.scheduled_end)
            duration_h = (last_end - first_start).total_seconds() / 3600 if last_end else 0
        else:
            duration_h = 0

        # Lots at risk (target roast date may be missed)
        now = datetime.now()
        lots_at_risk = sum(1 for lot in self.lots
                           if lot.target_roast_date < now + timedelta(days=3))

        # Utilization (actual productive time / total shift time)
        productive_min = sum(
            (b.scheduled_end - b.scheduled_start).total_seconds() / 60
            for b in batches if b.scheduled_end
        )
        total_shift_min = sum(s.planned_hours * 60 for s in shifts)
        utilization = (productive_min / total_shift_min * 100) if total_shift_min > 0 else 0

        theoretical_min = total_weight / SYSTEM_PARAMS["target_throughput_kg_h"]

        # Overall score (0-100) — compute inline before building metrics object
        score = (
            min(oee_avg / 0.776 * 100, 100) * 0.25 +
            min(grade_a_rate / 85.0 * 100, 100) * 0.25 +
            min(utilization / 90.0 * 100, 100) * 0.20 +
            max(0, 100 - lots_at_risk * 5) * 0.15 +
            (theoretical_min / duration_h * 100 if (duration_h > 0 and theoretical_min > 0) else 0) * 0.15
        )

        return ScheduleMetrics(
            total_lots=len(self.lots),
            total_weight_kg=round(total_weight, 2),
            total_batches=len(batches),
            estimated_duration_hours=round(duration_h, 1),
            estimated_good_product_kg=round(total_good, 2),
            estimated_reject_kg=round(total_reject, 2),
            avg_defect_rate_pct=round(sum(l.defect_rate_estimated for l in self.lots) / len(self.lots) * 100, 1),
            grade_a_rate_pct=round(grade_a_rate, 1),
            oee_weighted_avg=round(oee_avg * 100, 1),
            lots_at_risk=lots_at_risk,
            utilization_pct=round(utilization, 1),
            score=round(score, 1),
        )

    def _score_schedule(self, metrics: ScheduleMetrics,
                        batches: list[ProductionBatch],
                        shifts: list[Shift]) -> float:
        """Calculate overall schedule score (0-100)."""
        score = 0.0

        # OEE component (25%)
        oee_score = min(metrics.oee_weighted_avg / 77.6 * 100, 100)  # vs excellent target
        score += oee_score * 0.25

        # Grade A rate (25%)
        grade_score = min(metrics.grade_a_rate_pct / 85.0 * 100, 100)  # vs 85% world-class
        score += grade_score * 0.25

        # Utilization (20%)
        util_score = min(metrics.utilization_pct / 90.0 * 100, 100)
        score += util_score * 0.20

        # Risk penalty (15%)
        risk_penalty = metrics.lots_at_risk * 5  # -5 per at-risk lot
        risk_score = max(0, 100 - risk_penalty)
        score += risk_score * 0.15

        # Efficiency (duration vs theoretical minimum) (15%)
        theoretical_min = metrics.total_weight_kg / SYSTEM_PARAMS["target_throughput_kg_h"]
        if theoretical_min > 0:
            efficiency = theoretical_min / metrics.estimated_duration_hours * 100
            efficiency = min(efficiency, 100)
        else:
            efficiency = 0
        score += efficiency * 0.15

        return score

    def _print_schedule_overview(self, batches: list[ProductionBatch],
                                 shifts: list[Shift],
                                 metrics: ScheduleMetrics):
        """Print ASCII schedule overview."""
        print("\n" + "=" * 70)
        print("  HUSKY-SORTER-001  PRODUCTION SCHEDULE OVERVIEW")
        print("=" * 70)
        print(f"  Strategy: {self.strategy.value}  |  OEE Scenario: {self.oee_scenario}")
        print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 70)

        # Metrics summary
        print(f"\n  SCHEDULE METRICS")
        print(f"  {'─' * 40}")
        print(f"  Total Lots:        {metrics.total_lots:>8}")
        print(f"  Total Weight:      {metrics.total_weight_kg:>8.2f} kg")
        print(f"  Total Batches:     {metrics.total_batches:>8}")
        print(f"  Duration:          {metrics.estimated_duration_hours:>8.1f} hours")
        print(f"  Good Product:      {metrics.estimated_good_product_kg:>8.2f} kg")
        print(f"  Reject:            {metrics.estimated_reject_kg:>8.2f} kg")
        print(f"  Avg Defect Rate:    {metrics.avg_defect_rate_pct:>7.1f} %")
        print(f"  Grade A Rate:      {metrics.grade_a_rate_pct:>7.1f} %")
        print(f"  OEE (weighted):    {metrics.oee_weighted_avg:>7.1f} %")
        print(f"  Lots at Risk:      {metrics.lots_at_risk:>8}")
        print(f"  Utilization:       {metrics.utilization_pct:>7.1f} %")
        print(f"  {'─' * 40}")
        print(f"  OVERALL SCORE:     {metrics.score:>7.1f} / 100")
        rating = "🟢 EXCELLENT" if metrics.score >= 80 else "🟡 GOOD" if metrics.score >= 60 else "🔴 NEEDS IMPROVEMENT"
        print(f"  Rating: {rating}")

        # Shift summary
        print(f"\n  SHIFT BREAKDOWN")
        print(f"  {'─' * 40}")
        shift_weights = defaultdict(float)
        shift_batches = defaultdict(int)
        for shift in shifts:
            shift_weights[shift.shift_type.value] += shift.target_weight_kg
            shift_batches[shift.shift_type.value] += len(shift.target_batches)

        for st in ShiftType:
            w = shift_weights.get(st.value, 0)
            n = shift_batches.get(st.value, 0)
            if n > 0:
                print(f"  {st.value:<28} {n:>3} batches  {w:>8.2f} kg")

        # Batch timeline (first 10)
        print(f"\n  BATCH TIMELINE (first 10 of {len(batches)})")
        print(f"  {'─' * 70}")
        print(f"  {'Batch ID':<28} {'Start':<12} {'End':<12} {'Weight':>6}  Origin")
        print(f"  {'─' * 70}")
        for batch in batches[:10]:
            start_str = batch.scheduled_start.strftime('%m-%d %H:%M')
            end_str = batch.scheduled_end.strftime('%m-%d %H:%M') if batch.scheduled_end else "TBD"
            origin_short = batch.lot.origin.value.split()[-1][:12]
            print(f"  {batch.batch_id:<28} {start_str:<12} {end_str:<12} {batch.target_weight_kg:>5.2f}  {origin_short}")
        if len(batches) > 10:
            print(f"  ... and {len(batches) - 10} more batches")

        print("\n" + "=" * 70)

    def whatif_scenarios(self) -> dict:
        """
        Run what-if scenarios comparing different strategies and OEE levels.
        Returns comparison table.
        """
        strategies = [
            ScheduleStrategy.FIFO,
            ScheduleStrategy.OEE_OPTIMIZED,
            ScheduleStrategy.DEFECT_PRIORITY,
            ScheduleStrategy.MIXED,
        ]
        oee_scenarios = ["excellent", "typical", "startup"]

        results = {}
        for strat in strategies:
            for oee_scenario in oee_scenarios:
                scheduler = ProductionScheduler(strategy=strat, oee_scenario=oee_scenario)
                scheduler.add_lots(self.lots.copy())
                try:
                    batches, shifts, metrics = scheduler.generate_schedule(verbose=False)
                    key = f"{strat.value}_{oee_scenario}"
                    results[key] = {
                        "strategy": strat.value,
                        "oee_scenario": oee_scenario,
                        "score": metrics.score,
                        "grade_a_rate_pct": metrics.grade_a_rate_pct,
                        "lots_at_risk": metrics.lots_at_risk,
                        "duration_h": metrics.estimated_duration_hours,
                        "utilization_pct": metrics.utilization_pct,
                        "total_batches": metrics.total_batches,
                    }
                except Exception as e:
                    results[key] = {"error": str(e)}

        return results

    def print_whatif_comparison(self):
        """Print what-if scenario comparison table."""
        results = self.whatif_scenarios()

        print("\n" + "=" * 90)
        print("  WHAT-IF SCENARIO COMPARISON")
        print("=" * 90)
        print(f"  {'Strategy':<20} {'OEE Scenario':<12} {'Score':>6}  {'GradeA%':>7}  {'Risk':>4}  {'Hours':>6}  {'Util%':>6}")
        print(f"  {'─' * 85}")

        # Sort by score
        sorted_results = sorted(
            [(k, v) for k, v in results.items() if "error" not in v],
            key=lambda x: x[1]["score"],
            reverse=True
        )

        for key, r in sorted_results:
            print(f"  {r['strategy']:<20} {r['oee_scenario']:<12} {r['score']:>6.1f}  "
                  f"{r['grade_a_rate_pct']:>6.1f}%  {r['lots_at_risk']:>4}  "
                  f"{r['duration_h']:>5.1f}h  {r['utilization_pct']:>5.1f}%")

        print(f"  {'─' * 85}")
        best = sorted_results[0][1] if sorted_results else None
        if best:
            print(f"  🏆 Best: {best['strategy']} + {best['oee_scenario']} OEE = {best['score']:.1f}/100")

        print("=" * 90)

        return results

    def generate_schedule_report(self, output_path: str = "sorter/reports/schedule_report.json"):
        """Generate JSON schedule report."""
        metrics_dict = asdict(self._calculate_metrics(self.batches, self.shifts))

        report = {
            "report_id": f"SCHEDULE-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "strategy": self.strategy.value,
            "oee_scenario": self.oee_scenario,
            "metrics": metrics_dict,
            "shifts": [
                {
                    "shift_type": s.shift_type.value,
                    "date": s.date.isoformat(),
                    "planned_hours": s.planned_hours,
                    "target_batches": s.target_batches,
                    "target_weight_kg": s.target_weight_kg,
                }
                for s in self.shifts
            ],
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "lot_id": b.lot.lot_id,
                    "origin": b.lot.origin.value,
                    "process": b.lot.process.value,
                    "scheduled_start": b.scheduled_start.isoformat(),
                    "scheduled_end": b.scheduled_end.isoformat() if b.scheduled_end else None,
                    "target_weight_kg": b.target_weight_kg,
                    "grade_aa_kg": b.grade_aa_kg,
                    "grade_a_kg": b.grade_a_kg,
                    "grade_b_kg": b.grade_b_kg,
                    "grade_c_kg": b.grade_c_kg,
                    "reject_kg": b.reject_kg,
                    "oee_actual": b.oee_actual,
                    "status": b.status,
                }
                for b in self.batches
            ],
        }

        os_path = output_path
        import os
        os.makedirs(os.path.dirname(os_path), exist_ok=True)
        with open(os_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"  📄 Schedule report saved to {os_path}")
        return report

# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo Schedule Risk Analysis
# ─────────────────────────────────────────────────────────────────────────────

class MonteCarloScheduler:
    """
    Monte Carlo simulation for production schedule risk analysis.
    Runs multiple schedule realizations with probabilistic parameters.
    """

    def __init__(self, scheduler: ProductionScheduler, n_simulations: int = 1000):
        self.scheduler = scheduler
        self.n_simulations = n_simulations

    def run(self, verbose: bool = True) -> dict:
        """
        Run Monte Carlo simulation.
        Returns distribution of key metrics.
        """
        all_scores = []
        all_good_product = []
        all_duration = []
        all_grade_a_rate = []
        all_lots_at_risk = []
        all_utilization = []

        for i in range(self.n_simulations):
            sim_scheduler = ProductionScheduler(
                strategy=self.scheduler.strategy,
                oee_scenario=self.scheduler.oee_scenario,
            )
            # Add lots with small random variations in defect rates
            for lot in self.scheduler.lots:
                varied_defect = max(0.001, lot.defect_rate_estimated * random.uniform(0.85, 1.15))
                varied_lot = GreenCoffeeLot(
                    lot_id=lot.lot_id,
                    origin=lot.origin,
                    process=lot.process,
                    weight_kg=lot.weight_kg * random.uniform(0.98, 1.02),
                    defect_rate_estimated=varied_defect,
                    moisture_pct=lot.moisture_pct * random.uniform(0.98, 1.02),
                    density_g_ml=lot.density_g_ml * random.uniform(0.99, 1.01),
                    arrival_date=lot.arrival_date,
                    target_roast_date=lot.target_roast_date,
                    priority=lot.priority,
                    screen_mix=lot.screen_mix.copy(),
                    notes=lot.notes,
                )
                sim_scheduler.add_lot(varied_lot)

            try:
                batches, shifts, metrics = sim_scheduler.generate_schedule(verbose=False)
                all_scores.append(metrics.score)
                all_good_product.append(metrics.estimated_good_product_kg)
                all_duration.append(metrics.estimated_duration_hours)
                all_grade_a_rate.append(metrics.grade_a_rate_pct)
                all_lots_at_risk.append(metrics.lots_at_risk)
                all_utilization.append(metrics.utilization_pct)
            except Exception:
                pass

        if not all_scores:
            return {}

        def percentile(data, p):
            s = sorted(data)
            idx = int(len(s) * p / 100)
            return s[min(idx, len(s) - 1)]

        results = {
            "n_simulations": self.n_simulations,
            "score": {
                "p10": percentile(all_scores, 10),
                "p50": percentile(all_scores, 50),
                "p90": percentile(all_scores, 90),
                "mean": sum(all_scores) / len(all_scores),
            },
            "good_product_kg": {
                "p10": percentile(all_good_product, 10),
                "p50": percentile(all_good_product, 50),
                "p90": percentile(all_good_product, 90),
                "mean": sum(all_good_product) / len(all_good_product),
            },
            "duration_h": {
                "p10": percentile(all_duration, 10),
                "p50": percentile(all_duration, 50),
                "p90": percentile(all_duration, 90),
                "mean": sum(all_duration) / len(all_duration),
            },
            "grade_a_rate_pct": {
                "p10": percentile(all_grade_a_rate, 10),
                "p50": percentile(all_grade_a_rate, 50),
                "p90": percentile(all_grade_a_rate, 90),
                "mean": sum(all_grade_a_rate) / len(all_grade_a_rate),
            },
            "lots_at_risk": {
                "p10": percentile(all_lots_at_risk, 10),
                "p50": percentile(all_lots_at_risk, 50),
                "p90": percentile(all_lots_at_risk, 90),
                "mean": sum(all_lots_at_risk) / len(all_lots_at_risk),
            },
            "utilization_pct": {
                "p10": percentile(all_utilization, 10),
                "p50": percentile(all_utilization, 50),
                "p90": percentile(all_utilization, 90),
                "mean": sum(all_utilization) / len(all_utilization),
            },
        }

        if verbose:
            self._print_monte_carlo_results(results)

        return results

    def _print_monte_carlo_results(self, results: dict):
        """Print Monte Carlo simulation results."""
        print("\n" + "=" * 70)
        print("  MONTE CARLO SCHEDULE RISK ANALYSIS")
        print("=" * 70)
        print(f"  Simulations: {results['n_simulations']}")
        print(f"  {'─' * 60}")
        print(f"  {'Metric':<20} {'P10':>8} {'P50':>8} {'P90':>8} {'Mean':>8}")
        print(f"  {'─' * 60}")

        metrics_display = [
            ("Overall Score", results["score"]),
            ("Good Product (kg)", results["good_product_kg"]),
            ("Duration (h)", results["duration_h"]),
            ("Grade A Rate (%)", results["grade_a_rate_pct"]),
            ("Lots at Risk", results["lots_at_risk"]),
            ("Utilization (%)", results["utilization_pct"]),
        ]

        for name, data in metrics_display:
            print(f"  {name:<20} {data['p10']:>8.1f} {data['p50']:>8.1f} "
                  f"{data['p90']:>8.1f} {data['mean']:>8.1f}")

        print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# Demo / CLI
# ─────────────────────────────────────────────────────────────────────────────

def demo():
    """Demonstrate production scheduler with sample data."""
    print("\n" + "=" * 70)
    print("  HUSKY-SORTER-001  PRODUCTION SCHEDULER DEMO")
    print("  v1.0 | 2026-05-11 | Little Husky 🐕")
    print("=" * 70)

    # Create sample lots spanning 2 weeks
    now = datetime.now()
    lots = [
        GreenCoffeeLot(
            lot_id="LOT-2026-001",
            origin=BeanOrigin.ETHIOPIA_YIRGACHEFFE,
            process=ProcessMethod.WASHED,
            weight_kg=60.0,
            defect_rate_estimated=0.04,
            moisture_pct=11.2,
            density_g_ml=0.72,
            arrival_date=now - timedelta(days=5),
            target_roast_date=now + timedelta(days=2),
            priority=2,
            screen_mix={"AA": 0.25, "A": 0.45, "B": 0.20, "C": 0.07, "Reject": 0.03},
            notes="Premium micro-lot, process immediately",
        ),
        GreenCoffeeLot(
            lot_id="LOT-2026-002",
            origin=BeanOrigin.COLOMBIA_HUILA,
            process=ProcessMethod.HONEY,
            weight_kg=120.0,
            defect_rate_estimated=0.06,
            moisture_pct=10.8,
            density_g_ml=0.71,
            arrival_date=now - timedelta(days=3),
            target_roast_date=now + timedelta(days=5),
            priority=3,
            screen_mix={"AA": 0.20, "A": 0.40, "B": 0.25, "C": 0.10, "Reject": 0.05},
            notes="Standard commercial lot",
        ),
        GreenCoffeeLot(
            lot_id="LOT-2026-003",
            origin=BeanOrigin.KENYA_AA,
            process=ProcessMethod.WASHED,
            weight_kg=30.0,
            defect_rate_estimated=0.03,
            moisture_pct=11.5,
            density_g_ml=0.73,
            arrival_date=now - timedelta(days=1),
            target_roast_date=now + timedelta(days=1),
            priority=1,
            screen_mix={"AA": 0.35, "A": 0.40, "B": 0.15, "C": 0.06, "Reject": 0.04},
            notes="URGENT: Black Friday promotion lot",
        ),
        GreenCoffeeLot(
            lot_id="LOT-2026-004",
            origin=BeanOrigin.BRAZIL_CERRADO,
            process=ProcessMethod.NATURAL,
            weight_kg=200.0,
            defect_rate_estimated=0.08,
            moisture_pct=11.0,
            density_g_ml=0.70,
            arrival_date=now,
            target_roast_date=now + timedelta(days=7),
            priority=5,
            screen_mix={"AA": 0.15, "A": 0.35, "B": 0.30, "C": 0.12, "Reject": 0.08},
            notes="Large volume commodity lot",
        ),
        GreenCoffeeLot(
            lot_id="LOT-2026-005",
            origin=BeanOrigin.GUATEMALA_ANTIGUA,
            process=ProcessMethod.WASHED,
            weight_kg=45.0,
            defect_rate_estimated=0.035,
            moisture_pct=11.3,
            density_g_ml=0.72,
            arrival_date=now - timedelta(days=2),
            target_roast_date=now + timedelta(days=4),
            priority=4,
            screen_mix={"AA": 0.28, "A": 0.42, "B": 0.20, "C": 0.06, "Reject": 0.04},
            notes="Good quality, standard processing",
        ),
        GreenCoffeeLot(
            lot_id="LOT-2026-006",
            origin=BeanOrigin.PANAMA_GEOFFREY,
            process=ProcessMethod.ANAEROBIC,
            weight_kg=15.0,
            defect_rate_estimated=0.025,
            moisture_pct=11.8,
            density_g_ml=0.74,
            arrival_date=now - timedelta(days=6),
            target_roast_date=now + timedelta(days=3),
            priority=2,
            screen_mix={"AA": 0.40, "A": 0.38, "B": 0.14, "C": 0.05, "Reject": 0.03},
            notes="Geisha variety, premium auction lot",
        ),
    ]

    print(f"\n  Added {len(lots)} sample lots:")
    print(f"  {'─' * 60}")
    for lot in lots:
        days_to = (lot.target_roast_date - now).days
        print(f"  {lot.lot_id:<15} {lot.origin.value:<25} {lot.weight_kg:>5.1f}kg "
              f"Δ={lot.defect_rate_estimated*100:>4.1f}%  Roast in {days_to}d  Urgent={lot.urgency_score:.1f}")

    # Run scheduler
    scheduler = ProductionScheduler(strategy=ScheduleStrategy.MIXED, oee_scenario="typical")
    scheduler.add_lots(lots)

    print("\n")
    start = now.replace(hour=6, minute=0, second=0)
    batches, shifts, metrics = scheduler.generate_schedule(start_date=start, verbose=True)

    # What-if analysis
    print()
    scheduler.print_whatif_comparison()

    # Monte Carlo risk analysis
    mc = MonteCarloScheduler(scheduler, n_simulations=500)
    mc.run(verbose=True)

    # Save report
    scheduler.generate_schedule_report()

    return scheduler, batches, metrics


if __name__ == "__main__":
    demo()
