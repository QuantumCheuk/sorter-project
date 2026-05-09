#!/usr/bin/env python3
"""
OEE (Overall Equipment Effectiveness) Monitor
===============================================
HUSKY-SORTER-001 Real-time OEE Calculation & Tracking

Purpose:
  - Calculate real-time OEE = Availability × Performance × Quality
  - Track Six Big Losses ( unplanned stops / setup adjustments / small stops / reduced speed / defect rework / startup rejects )
  - Compute OEE, OAE (Overall Availability Effectiveness), OPE (Overall Performance Effectiveness), OQE (Overall Quality Effectiveness)
  - Daily/batch/shift OEE trending, ASCII visualizations, JSON reports

Author: Little Husky (他他) 🐕
Version: 1.0 | 2026-05-10
"""

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from enum import Enum
from collections import defaultdict


# ============================================================================
# Data Models
# ============================================================================

class LossCategory(str, Enum):
    """Six Big Losses classification."""
    # Availability Losses
    UNPLANNED_STOPS = "unplanned_stops"       # Equipment failures, breakdowns
    SETUP_ADJUSTMENTS = "setup_adjustments"   # Changeovers, adjustments
    # Performance Losses
    SMALL_STOPS = "small_stops"               # Transient stoppages, jams
    REDUCED_SPEED = "reduced_speed"           # Operating below ideal speed
    # Quality Losses
    DEFECT_REWORK = "defect_rework"           # Defects that need rework
    STARTUP_REJECTS = "startup_rejects"       # Rejects during warm-up/stabilization


class DowntimeReason(str, Enum):
    """Detailed downtime root causes."""
    # Unplanned
    MOTOR_FAILURE = "motor_failure"
    SENSOR_FAULT = "sensor_fault"
    I2C_COMM_ERROR = "i2c_comm_error"
    JAM_BLOCKAGE = "jam_blockage"
    AIR_COMPRESSOR_FAILURE = "air_compressor_failure"
    E_STOP_TRIGGERED = "e_stop_triggered"
    POWER_OUTAGE = "power_outage"
    PI_HANG = "pi_hang"
    # Planned
    CHANGE_OVER = "change_over"
    CALIBRATION = "calibration"
    CLEANING = "cleaning"
    MAINTENANCE_SCHEDULED = "maintenance_scheduled"
    MATERIAL_REFILL = "material_refill"
    PARAMETER_TUNING = "parameter_tuning"


@dataclass
class OEEVariables:
    """Core OEE calculation variables."""
    # Time dimensions
    planned_production_time_min: float     # Total scheduled time
    downtime_min: float                    # All stops (planned + unplanned)
    net_operating_time_min: float          # planned_production_time - downtime
    # Count dimensions
    total_beans_processed: int             # All beans fed into system
    good_beans_output: int                 # Successfully sorted to output
    defect_rejected: int                   # Defective beans rejected
    startup_rejects: int                   # Rejects during startup phase
    # Speed dimensions
    ideal_cycle_time_sec_per_bean: float  # Theoretical fastest cycle (sec/bean)
    actual_cycle_time_sec_per_bean: float  # Actual measured cycle time
    # Quality
    total_defects_found: int              # All defects detected


@dataclass
class SixBigLosses:
    """Six Big Losses breakdown."""
    unplanned_stops_min: float = 0.0      # Equipment failures
    setup_adjustments_min: float = 0.0    # Changeovers, settings
    small_stops_min: float = 0.0          # Transient jams, sensor flickers
    reduced_speed_min: float = 0.0        # Operating below rated speed
    defect_rework_count: int = 0          # Defects requiring rework
    startup_rejects_count: int = 0        # Startup waste


@dataclass
class OEEResult:
    """Complete OEE analysis result."""
    timestamp: str
    production_rate_kg_h: float
    uptime_pct: float                     # Availability component
    performance_pct: float                # Performance component
    quality_pct: float                     # Quality component
    oee_pct: float                         # OEE = A × P × Q
    oae_pct: float                         # Overall Availability Effectiveness
    ope_pct: float                         # Overall Performance Effectiveness
    oqe_pct: float                          # Overall Quality Effectiveness
    six_losses: SixBigLosses
    variables: OEEVariables
    losses_summary_pct: Dict[str, float]   # Each loss as % of planned time
    grade_a_rate_pct: float
    total_output_kg: float
    losses_detail_min: Dict[str, float]


# ============================================================================
# OEE Calculator
# ============================================================================

class OEECalculator:
    """
    Compute OEE from operational data.

    OEE Formula:
      Availability = Net Operating Time / Planned Production Time
      Performance = (Total Count × Ideal Cycle Time) / Net Operating Time
      Quality     = Good Count / Total Count
      OEE         = Availability × Performance × Quality

    Six Big Losses mapping:
      Unplanned Stops     → Availability ↓
      Setup Adjustments    → Availability ↓ (changeovers)
      Small Stops          → Performance ↓
      Reduced Speed        → Performance ↓
      Defect Rework        → Quality ↓
      Startup Rejects     → Quality ↓
    """

    # Target: 2kg/h with 0.152g/bean
    # 2kg/h = 2000g/h / 0.152g = 13,158 beans/hour
    # = 219.3 beans/min = 3.66 beans/sec → 0.273 sec/bean (WORLD-CLASS IDEAL)
    # This is the theoretical best at rated 2kg/h target.
    IDEAL_CYCLE_TIME_SEC = 0.273

    def __init__(self):
        self.reset()

    def reset(self):
        self.planned_min = 0.0
        self.downtime_min = 0.0
        self.total_beans = 0
        self.good_beans = 0
        self.startup_rejects = 0
        self.actual_cycle_sec = self.IDEAL_CYCLE_TIME_SEC
        self.unplanned_min = 0.0
        self.setup_min = 0.0
        self.small_stops_min = 0.0
        self.reduced_speed_min = 0.0
        self.defect_rework_count = 0

    def configure(self, planned_min: float):
        """Set planned production time in minutes."""
        self.planned_min = planned_min

    def record_beans(self, total: int, good: int, defects: int):
        """Record bean processing counts."""
        self.total_beans = total
        self.good_beans = good
        self.defect_rework_count = defects

    def record_downtime(self, unplanned: float = 0, setup: float = 0,
                        small_stops: float = 0, reduced_speed: float = 0):
        """Record downtime by category (minutes)."""
        self.unplanned_min = unplanned
        self.setup_min = setup
        self.small_stops_min = small_stops
        self.reduced_speed_min = reduced_speed
        self.downtime_min = unplanned + setup + small_stops + reduced_speed

    def record_startup_rejects(self, count: int):
        """Record beans rejected during startup."""
        self.startup_rejects = count

    def set_actual_cycle_time(self, sec_per_bean: float):
        """Set actual measured cycle time."""
        self.actual_cycle_sec = sec_per_bean

    def compute(self) -> OEEResult:
        """Calculate all OEE metrics."""
        net_operating_min = max(0, self.planned_min - self.downtime_min)

        # Availability
        availability = (net_operating_min / self.planned_min) if self.planned_min > 0 else 0

        # Performance
        ideal_operating_sec = self.total_beans * self.IDEAL_CYCLE_TIME_SEC
        ideal_operating_min = ideal_operating_sec / 60.0
        performance = (ideal_operating_min / net_operating_min) if net_operating_min > 0 else 0
        performance = min(1.0, performance)  # Cap at 100%

        # Quality
        total_output = self.good_beans + self.defect_rework_count + self.startup_rejects
        quality = (self.good_beans / total_output) if total_output > 0 else 0

        # OEE composite
        oee = availability * performance * quality

        # OAE (Availability × Performance only — excludes quality)
        oae = availability * performance

        # OPE (Performance × Quality — rate × quality)
        ope = performance * quality

        # OQE (Quality alone)
        oqe = quality

        # Throughput
        total_output_beans = self.good_beans + self.defect_rework_count + self.startup_rejects
        avg_weight_g = 0.152  # g/bean from digital_twin
        total_kg = total_output_beans * avg_weight_g / 1000.0
        net_hours = net_operating_min / 60.0
        rate_kg_h = (total_kg / net_hours) if net_hours > 0 else 0

        # Grade A rate (good beans / total input)
        grade_a_rate = (self.good_beans / total_output_beans * 100) if total_output_beans > 0 else 0

        # Losses as % of planned time
        losses_detail = {
            "unplanned_stops_pct": (self.unplanned_min / self.planned_min * 100) if self.planned_min > 0 else 0,
            "setup_adjustments_pct": (self.setup_min / self.planned_min * 100) if self.planned_min > 0 else 0,
            "small_stops_pct": (self.small_stops_min / self.planned_min * 100) if self.planned_min > 0 else 0,
            "reduced_speed_pct": (self.reduced_speed_min / self.planned_min * 100) if self.planned_min > 0 else 0,
        }

        losses_summary = {
            "availability_losses_pct": ((self.unplanned_min + self.setup_min) / self.planned_min * 100) if self.planned_min > 0 else 0,
            "performance_losses_pct": ((self.small_stops_min + self.reduced_speed_min) / self.planned_min * 100) if self.planned_min > 0 else 0,
            "quality_losses_pct": 0.0,
            "total_losses_pct": (self.downtime_min / self.planned_min * 100) if self.planned_min > 0 else 0,
        }

        six_losses = SixBigLosses(
            unplanned_stops_min=self.unplanned_min,
            setup_adjustments_min=self.setup_min,
            small_stops_min=self.small_stops_min,
            reduced_speed_min=self.reduced_speed_min,
            defect_rework_count=self.defect_rework_count,
            startup_rejects_count=self.startup_rejects,
        )

        variables = OEEVariables(
            planned_production_time_min=self.planned_min,
            downtime_min=self.downtime_min,
            net_operating_time_min=net_operating_min,
            total_beans_processed=total_output_beans,
            good_beans_output=self.good_beans,
            defect_rejected=self.defect_rework_count,
            startup_rejects=self.startup_rejects,
            ideal_cycle_time_sec_per_bean=self.IDEAL_CYCLE_TIME_SEC,
            actual_cycle_time_sec_per_bean=self.actual_cycle_sec,
            total_defects_found=self.defect_rework_count,
        )

        return OEEResult(
            timestamp=datetime.now().isoformat(),
            production_rate_kg_h=round(rate_kg_h, 3),
            uptime_pct=round(availability * 100, 2),
            performance_pct=round(performance * 100, 2),
            quality_pct=round(quality * 100, 2),
            oee_pct=round(oee * 100, 2),
            oae_pct=round(oae * 100, 2),
            ope_pct=round(ope * 100, 2),
            oqe_pct=round(oqe * 100, 2),
            six_losses=six_losses,
            variables=variables,
            losses_summary_pct=losses_summary,
            grade_a_rate_pct=round(grade_a_rate, 2),
            total_output_kg=round(total_kg, 4),
            losses_detail_min={
                "unplanned_stops": round(self.unplanned_min, 2),
                "setup_adjustments": round(self.setup_min, 2),
                "small_stops": round(self.small_stops_min, 2),
                "reduced_speed": round(self.reduced_speed_min, 2),
            },
        )


# ============================================================================
# OEE Simulator (Monte Carlo with realistic scenarios)
# ============================================================================

SCENARIOS = {
    # Target upgraded system: 3ch × 50bpm = 2.70 kg/h = 17,763 beans/h = 142,105 beans/8h shift
    # IDEAL_CYCLE_TIME_SEC = 0.273 (target for 2kg/h)
    # Performance = (total_beans × ideal_cycle) / net_operating_time
    # Rate = (good_beans × 0.152g) / net_hours  [NOT OEE-derived — independent output metric]
    "excellent": {
        "planned_hours": 8.0,
        "unplanned_min": 5, "setup_min": 10, "small_stops_min": 3,
        "reduced_speed_min": 5, "rework_count": 450, "startup_rejects": 180,
        "actual_cycle_sec": 0.286, "total_beans": 82500, "good_beans": 81520,
        # P = 82500×0.273/28500 = 0.791 → 79.1%, Rate = 81520×0.152/7.917h = 1.565 kg/h
        # But with quality=(81520+450+180)/82500=99.4%, GradeA=81520/82350=98.99%
    },
    "good": {
        "planned_hours": 8.0,
        "unplanned_min": 15, "setup_min": 20, "small_stops_min": 8,
        "reduced_speed_min": 15, "rework_count": 1150, "startup_rejects": 450,
        "actual_cycle_sec": 0.350, "total_beans": 62000, "good_beans": 60180,
        # P = 62000×0.273/27000 = 0.627 → 62.7%, Rate = 60180×0.152/7.5h = 1.221 kg/h
        # Quality = (60180+1150+450)/62000 = 99.97%≈99.9%, GradeA=60180/61780=97.41%
    },
    "typical": {
        "planned_hours": 8.0,
        "unplanned_min": 30, "setup_min": 35, "small_stops_min": 15,
        "reduced_speed_min": 25, "rework_count": 2700, "startup_rejects": 1100,
        "actual_cycle_sec": 0.410, "total_beans": 52000, "good_beans": 48640,
        # P = 52000×0.273/25500 = 0.557 → 55.7%, Rate = 48640×0.152/7.083h = 1.043 kg/h
        # Quality = (48640+2700+1100)/52000 = 96.6%, GradeA=48640/52440=92.78%
    },
    "poor": {
        "planned_hours": 8.0,
        "unplanned_min": 60, "setup_min": 45, "small_stops_min": 30,
        "reduced_speed_min": 40, "rework_count": 5500, "startup_rejects": 2200,
        "actual_cycle_sec": 0.550, "total_beans": 35000, "good_beans": 30340,
        # P = 35000×0.273/21750 = 0.439 → 43.9%, Rate = 30340×0.152/6.042h = 0.764 kg/h
        # Quality = (30340+5500+2200)/35000 = 96.97%≈95.0%, GradeA=30340/38040=79.76%
    },
    "startup_learning": {
        "planned_hours": 8.0,
        "unplanned_min": 90, "setup_min": 60, "small_stops_min": 45,
        "reduced_speed_min": 50, "rework_count": 8500, "startup_rejects": 3500,
        "actual_cycle_sec": 0.700, "total_beans": 22000, "good_beans": 17280,
        # P = 22000×0.273/16950 = 0.354 → 35.4%, Rate = 17280×0.152/4.708h = 0.558 kg/h
        # Quality = (17280+8500+3500)/22000 = 88.5%, GradeA=17280/29280=59.03%
    },
}


def simulate_scenario(name: str, seed: int = 42) -> OEEResult:
    """Run OEE calculation for a named scenario with optional Monte Carlo variation."""
    random.seed(seed)
    s = SCENARIOS[name].copy()

    # Add ±15% random variation to downtime for realism
    for key in ["unplanned_min", "setup_min", "small_stops_min", "reduced_speed_min"]:
        variation = random.uniform(0.85, 1.15)
        s[key] = max(0, s[key] * variation)

    calc = OEECalculator()
    calc.configure(planned_min=s["planned_hours"] * 60)
    calc.record_beans(s["total_beans"], s["good_beans"], s["rework_count"])
    calc.record_downtime(
        unplanned=s["unplanned_min"],
        setup=s["setup_min"],
        small_stops=s["small_stops_min"],
        reduced_speed=s["reduced_speed_min"],
    )
    calc.record_startup_rejects(s["startup_rejects"])
    calc.set_actual_cycle_time(s["actual_cycle_sec"])

    return calc.compute()


def run_monte_carlo_oee(n_runs: int = 1000) -> Dict:
    """Run Monte Carlo simulation of OEE across all scenarios."""
    results = defaultdict(list)

    for scenario_name in SCENARIOS:
        oee_values = []
        for i in range(n_runs):
            r = simulate_scenario(scenario_name, seed=i)
            oee_values.append(r.oee_pct)

        results[scenario_name] = {
            "mean": round(sum(oee_values) / len(oee_values), 2),
            "min": round(min(oee_values), 2),
            "max": round(max(oee_values), 2),
            "std": round(math.sqrt(sum((x - sum(oee_values)/len(oee_values))**2 for x in oee_values) / len(oee_values)), 2),
            "p10": round(sorted(oee_values)[int(len(oee_values)*0.10)], 2),
            "p50": round(sorted(oee_values)[int(len(oee_values)*0.50)], 2),
            "p90": round(sorted(oee_values)[int(len(oee_values)*0.90)], 2),
        }

    return dict(results)


# ============================================================================
# ASCII Visualizations
# ============================================================================

def draw_oee_gauge(oee_pct: float, width: int = 50) -> str:
    """Draw ASCII OEE gauge with grade coloring."""
    filled = int(width * oee_pct / 100)
    empty = width - filled

    if oee_pct >= 85:
        color = "\033[92m"  # Green
        grade = "WORLD CLASS"
    elif oee_pct >= 70:
        color = "\033[93m"  # Yellow
        grade = "GOOD"
    elif oee_pct >= 60:
        color = "\033[33m"  # Orange
        grade = "FAIR"
    else:
        color = "\033[91m"  # Red
        grade = "POOR"

    reset = "\033[0m"
    bar = "█" * filled + "░" * empty
    return f"{color}[{bar}]{reset} {oee_pct:.1f}%  {grade}"


def draw_oee_components(a: float, p: float, q: float, oee: float) -> str:
    """Draw OEE component breakdown bar chart."""
    width = 40

    components = [
        ("Availability", a),
        ("Performance", p),
        ("Quality", q),
        ("OEE", oee),
    ]

    lines = []
    lines.append("\n  ╔════════════════════════════════════════╗")
    lines.append("  ║       OEE Component Breakdown          ║")
    lines.append("  ╠════════════════════════════════════════╣")

    for name, pct in components:
        filled = int(width * pct / 100)
        bar = "▓" * filled + "░" * (width - filled)
        is_oee = name == "OEE"
        prefix = "►" if is_oee else " "
        marker = "◄" if is_oee else " "
        lines.append(f"  ║ {prefix} {name:<12} [{bar}] {pct:5.1f}%{marker:>3} ║")

    lines.append("  ╚════════════════════════════════════════╝")
    return "\n".join(lines)


def draw_six_losses_chart(losses: SixBigLosses, planned_min: float) -> str:
    """Draw Six Big Losses horizontal bar chart."""
    losses_data = [
        ("Unplanned Stops", losses.unplanned_stops_min),
        ("Setup Adjustments", losses.setup_adjustments_min),
        ("Small Stops", losses.small_stops_min),
        ("Reduced Speed", losses.reduced_speed_min),
        ("Defect Rework", losses.defect_rework_count * 0.05),  # Convert to min-equivalent
        ("Startup Rejects", losses.startup_rejects_count * 0.05),
    ]

    max_val = max(v for _, v in losses_data) if losses_data else 1
    max_bar_width = 40

    lines = []
    lines.append("\n  ┌─────────────────────────────────────────┐")
    lines.append("  │         Six Big Losses (minutes)         │")
    lines.append("  ├─────────────────────────────────────────┤")

    for name, val in losses_data:
        bar_len = int(max_bar_width * val / max_val)
        bar = "█" * bar_len + "░" * (max_bar_width - bar_len)
        pct = (val / planned_min * 100) if planned_min > 0 else 0
        lines.append(f"  │ {name:<18} [{bar}] {val:5.1f}min ({pct:4.1f}%) │")

    lines.append("  └─────────────────────────────────────────┘")
    return "\n".join(lines)


def draw_oee_dashboard(results: List[OEEResult]) -> str:
    """Draw full OEE dashboard with trend over multiple runs."""
    if not results:
        return "No results to display."

    latest = results[-1]
    prev = results[-2] if len(results) >= 2 else latest

    lines = []
    lines.append("")
    lines.append("  ╔══════════════════════════════════════════════════════════╗")
    lines.append("  ║        HUSKY-SORTER-001  OEE Dashboard                  ║")
    lines.append("  ╠══════════════════════════════════════════════════════════╣")

    # OEE Big Number
    delta = latest.oee_pct - prev.oee_pct
    arrow = "▲" if delta >= 0 else "▼"
    delta_str = f"{arrow}{abs(delta):.1f}%"

    oee_color = "\033[92m" if latest.oee_pct >= 85 else "\033[93m" if latest.oee_pct >= 70 else "\033[91m"
    reset = "\033[0m"
    lines.append(f"  ║  OEE: {oee_color}{latest.oee_pct:.1f}%\033[0m  |  Rate: {latest.production_rate_kg_h:.2f} kg/h  |  Δ: {delta_str}      ║")

    # Components
    comp_str = f"A={latest.uptime_pct:.1f}%  P={latest.performance_pct:.1f}%  Q={latest.quality_pct:.1f}%"
    lines.append(f"  ║  Components: {comp_str:<43} ║")

    # Grade A rate
    lines.append(f"  ║  Grade A Rate: {latest.grade_a_rate_pct:.1f}%  |  Total Output: {latest.total_output_kg:.3f} kg        ║")

    lines.append("  ╠══════════════════════════════════════════════════════════╣")

    # OEE Gauge
    gauge = draw_oee_gauge(latest.oee_pct, 38)
    lines.append(f"  ║  {gauge:<46} ║")

    # Component bars
    for name, val in [("Availability", latest.uptime_pct), ("Performance", latest.performance_pct), ("Quality", latest.quality_pct)]:
        filled = int(38 * val / 100)
        bar = "▓" * filled + "░" * (38 - filled)
        lines.append(f"  ║  {name:<12} [{bar}] {val:5.1f}%    ║")

    lines.append("  ╠══════════════════════════════════════════════════════════╣")

    # Six Big Losses summary
    sl = latest.six_losses
    total_loss_min = sl.unplanned_stops_min + sl.setup_adjustments_min + sl.small_stops_min + sl.reduced_speed_min
    lines.append(f"  ║  Total Downtime: {total_loss_min:.1f} min  |  Rework: {sl.defect_rework_count} beans  |  Startup Loss: {sl.startup_rejects_count}   ║")

    lines.append("  ╚══════════════════════════════════════════════════════════╝")

    # Historical trend (last 5 runs)
    if len(results) >= 2:
        lines.append("\n  OEE Trend (last 5 runs):")
        recent = results[-5:]
        max_oee = max(r.oee_pct for r in recent)
        for i, r in enumerate(recent):
            filled = int(30 * r.oee_pct / 100)
            bar = "█" * filled + "░" * (30 - filled)
            marker = " ◄current" if r is latest else ""
            lines.append(f"    [{bar}] {r.oee_pct:.1f}%{marker}")

    return "\n".join(lines)


# ============================================================================
# Report Generator
# ============================================================================

def generate_oee_report(results: List[OEEResult], scenario_name: str = "simulation") -> Dict:
    """Generate comprehensive OEE report as dictionary."""
    if not results:
        return {}

    latest = results[-1]

    # Summarize across all runs
    oee_vals = [r.oee_pct for r in results]
    avail_vals = [r.uptime_pct for r in results]
    perf_vals = [r.performance_pct for r in results]
    qual_vals = [r.quality_pct for r in results]

    report = {
        "report_id": f"OEE-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "scenario": scenario_name,
        "timestamp": latest.timestamp,
        "current": {
            "oee_pct": latest.oee_pct,
            "oae_pct": latest.oae_pct,
            "ope_pct": latest.ope_pct,
            "oqe_pct": latest.oqe_pct,
            "availability_pct": latest.uptime_pct,
            "performance_pct": latest.performance_pct,
            "quality_pct": latest.quality_pct,
            "production_rate_kg_h": latest.production_rate_kg_h,
            "grade_a_rate_pct": latest.grade_a_rate_pct,
            "total_output_kg": latest.total_output_kg,
            "net_operating_time_min": latest.variables.net_operating_time_min,
            "planned_time_min": latest.variables.planned_production_time_min,
            "total_downtime_min": latest.variables.downtime_min,
        },
        "six_losses_current": {
            "unplanned_stops_min": latest.six_losses.unplanned_stops_min,
            "setup_adjustments_min": latest.six_losses.setup_adjustments_min,
            "small_stops_min": latest.six_losses.small_stops_min,
            "reduced_speed_min": latest.six_losses.reduced_speed_min,
            "defect_rework_count": latest.six_losses.defect_rework_count,
            "startup_rejects_count": latest.six_losses.startup_rejects_count,
        },
        "statistics": {
            "runs": len(results),
            "oee_mean": round(sum(oee_vals) / len(oee_vals), 2),
            "oee_min": round(min(oee_vals), 2),
            "oee_max": round(max(oee_vals), 2),
            "oee_std": round(math.sqrt(sum((x - sum(oee_vals)/len(oee_vals))**2 for x in oee_vals) / len(oee_vals)), 2),
            "availability_mean": round(sum(avail_vals) / len(avail_vals), 2),
            "performance_mean": round(sum(perf_vals) / len(perf_vals), 2),
            "quality_mean": round(sum(qual_vals) / len(qual_vals), 2),
        },
        "world_class_benchmark": {
            "oee_85_plus": "World Class",
            "oee_70_85": "Typical",
            "oee_60_70": "Fair",
            "oee_below_60": "Poor",
        },
    }

    return report


# ============================================================================
# Main Benchmark Runner
# ============================================================================

def run_oee_benchmark():
    """Run OEE benchmark across all scenarios and generate comprehensive report."""
    print("\n" + "=" * 64)
    print("  HUSKY-SORTER-001  OEE Monitoring System  v1.0")
    print("=" * 64)

    all_results = {}
    scenario_results = {}

    for scenario_name in SCENARIOS:
        print(f"\n  ▶ Running scenario: {scenario_name.upper()}...")

        calc = OEECalculator()
        s = SCENARIOS[scenario_name]
        calc.configure(planned_min=s["planned_hours"] * 60)
        calc.record_beans(s["total_beans"], s["good_beans"], s["rework_count"])
        calc.record_downtime(
            unplanned=s["unplanned_min"], setup=s["setup_min"],
            small_stops=s["small_stops_min"], reduced_speed=s["reduced_speed_min"],
        )
        calc.record_startup_rejects(s["startup_rejects"])
        calc.set_actual_cycle_time(s["actual_cycle_sec"])

        result = calc.compute()
        all_results[scenario_name] = result
        scenario_results[scenario_name] = [result]

        print(f"    OEE={result.oee_pct:.1f}%  A={result.uptime_pct:.1f}%  P={result.performance_pct:.1f}%  Q={result.quality_pct:.1f}%")
        print(f"    Rate: {result.production_rate_kg_h:.2f} kg/h  |  Grade A: {result.grade_a_rate_pct:.1f}%")

    # Monte Carlo
    print("\n  ▶ Running Monte Carlo simulation (n=1000)...")
    mc_results = run_monte_carlo_oee(n_runs=1000)

    # Print comparison table
    print("\n  ┌────────────┬────────┬────────┬────────┬────────┬────────────┐")
    print("  │ Scenario   │   OEE  │   A    │   P    │   Q    │ Rate kg/h  │")
    print("  ├────────────┼────────┼────────┼────────┼────────┼────────────┤")
    for name, r in all_results.items():
        grade = "🟢" if r.oee_pct >= 85 else "🟡" if r.oee_pct >= 70 else "🔴"
        print(f"  │ {grade} {name:<10} │ {r.oee_pct:6.1f}% │ {r.uptime_pct:6.1f}% │ {r.performance_pct:6.1f}% │ {r.quality_pct:6.1f}% │   {r.production_rate_kg_h:6.2f}    │")
    print("  └────────────┴────────┴────────┴────────┴────────┴────────────┘")

    # Monte Carlo summary
    print("\n  Monte Carlo (n=1000) OEE Distribution:")
    print("  ┌────────────┬────────┬────────┬────────┬────────┬────────┬────────┐")
    print("  │ Scenario   │  Mean  │  Min   │  Max   │  P10   │  P50   │  P90   │")
    print("  ├────────────┼────────┼────────┼────────┼────────┼────────┼────────┤")
    for name, stats in mc_results.items():
        print(f"  │ {name:<10} │ {stats['mean']:6.1f}% │ {stats['min']:6.1f}% │ {stats['max']:6.1f}% │ {stats['p10']:6.1f}% │ {stats['p50']:6.1f}% │ {stats['p90']:6.1f}% │")
    print("  └────────────┴────────┴────────┴────────┴────────┴────────┴────────┘")

    # Dashboard for "typical" scenario
    typical_result = all_results.get("typical")
    if typical_result:
        print(draw_oee_dashboard([typical_result]))
        print(draw_six_losses_chart(typical_result.six_losses, typical_result.variables.planned_production_time_min))

    # World-class gap analysis
    print("\n  World-Class OEE Analysis (85% target):")
    print("  ┌────────────┬────────┬────────────┬────────────────────────┐")
    print("  │ Scenario   │  OEE   │   Gap %    │   Required Improvement │")
    print("  ├────────────┼────────┼────────────┼────────────────────────┤")
    for name, r in all_results.items():
        gap = 85.0 - r.oee_pct
        if gap <= 0:
            improvement = "✓ ACHIEVED"
        else:
            improvement = f"+{gap:.1f}% pts OEE"
        print(f"  │ {name:<10} │ {r.oee_pct:6.1f}% │ {gap:9.1f}%  │ {improvement:<22} │")
    print("  └────────────┴────────┴────────────┴────────────────────────┘")

    # Generate report JSON
    report = generate_oee_report(
        [all_results["typical"]],
        scenario_name="typical",
    )

    report_path = "sorter/reports/oee_report.json"
    import os
    os.makedirs("sorter/reports", exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  ✅ OEE report saved: {report_path}")
    print(f"  Report ID: {report['report_id']}")

    return all_results, mc_results


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    results, mc = run_oee_benchmark()