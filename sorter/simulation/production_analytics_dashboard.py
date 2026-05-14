#!/usr/bin/env python3
"""
Production Analytics Dashboard — v1.0
======================================
Unified multi-metric analytics dashboard for sorter production operations.
Consolidates: OEE monitoring, SPC quality control, batch analytics, throughput trends.

Run: python sorter/simulation/production_analytics_dashboard.py --demo
Output: sorter/reports/production_analytics_report.json
"""

import json
import math
import random
import time
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

class TimeRange(str, Enum):
    SHIFT     = "shift"      # 8h
    DAY       = "day"        # 24h
    WEEK      = "week"       # 7 days
    MONTH     = "month"      # 30 days


@dataclass
class OEEData:
    availability: float  # 0-1
    performance: float   # 0-1
    quality: float      # 0-1
    oee: float          # 0-1
    production_rate_kg_h: float


@dataclass
class SPCData:
    cp: float
    cpk: float
    status: str  # "excellent" / "good" / "warning" / "critical"
    rule_violations: int
    trend: str  # "improving" / "stable" / "degrading"


@dataclass
class QualityData:
    grade_a_pct: float
    defect_rate_pct: float
    avg_quality_score: float
    batch_count: int


@dataclass
class ThroughputData:
    current_kg_h: float
    target_kg_h: float = 2.0
    efficiency_pct: float = 0.0
    total_kg_today: float = 0.0


@dataclass
class ProductionMetrics:
    oee: OEEData
    spc: SPCData
    quality: QualityData
    throughput: ThroughputData
    alarms_active: int
    alerts_suppressed: int


@dataclass
class DashboardMetrics:
    timestamp: str
    metrics: ProductionMetrics
    overall_score: float  # 0-100 composite
    status: str  # "optimal" / "good" / "warning" / "critical"
    recommendations: list[str]


# ══════════════════════════════════════════════════════════════════════════════
#  METRIC COLLECTORS
# ══════════════════════════════════════════════════════════════════════════════

class OEECollector:
    """Simulated OEE data collector — in production, reads from OEE monitor."""

    SCENARIOS = {
        "excellent": {"avail": 0.95, "perf": 0.85, "qual": 0.98, "rate": 1.64},
        "typical":   {"avail": 0.85, "perf": 0.65, "qual": 0.92, "rate": 1.27},
        "startup":   {"avail": 0.50, "perf": 0.40, "qual": 0.80, "rate": 0.56},
        "degraded":  {"avail": 0.70, "perf": 0.50, "qual": 0.85, "rate": 0.93},
    }

    @classmethod
    def get_current(cls) -> OEEData:
        hour = datetime.now().hour
        if 6 <= hour < 14:
            scenario = "excellent"
        elif 14 <= hour < 22:
            scenario = "typical"
        else:
            scenario = "startup"

        s = cls.SCENARIOS[scenario]
        jitter = random.uniform(0.98, 1.02)
        oee = s["avail"] * s["perf"] * s["qual"]
        return OEEData(
            availability=round(s["avail"] * jitter, 4),
            performance=round(s["perf"] * jitter, 4),
            quality=round(s["qual"] * jitter, 4),
            oee=round(oee * jitter, 4),
            production_rate_kg_h=round(s["rate"] * jitter, 3),
        )


class SPCCollector:
    """Simulated SPC data — in production, reads from SPC quality monitor."""

    PARAMETERS = ["bean_weight", "moisture_content", "color_score", "density", "defect_rate"]

    STATUS_THRESHOLDS = {
        "excellent": (1.67, 999),
        "good":      (1.33, 1.67),
        "warning":   (1.0, 1.33),
        "critical":  (0.0, 1.0),
    }

    @classmethod
    def get_current(cls) -> SPCData:
        hour = datetime.now().hour
        if 6 <= hour < 14:
            base_cpk = 1.85
            violations = 0
            trend = "stable"
        elif 14 <= hour < 22:
            base_cpk = 1.40
            violations = random.randint(0, 2)
            trend = "degrading"
        else:
            base_cpk = 0.95
            violations = random.randint(1, 4)
            trend = "improving"

        cp = base_cpk * random.uniform(0.97, 1.03)
        cpk = base_cpk * random.uniform(0.94, 1.00)

        status = "critical"
        for s, (lo, hi) in cls.STATUS_THRESHOLDS.items():
            if lo <= cpk < hi:
                status = s
                break

        return SPCData(
            cp=round(cp, 3),
            cpk=round(cpk, 3),
            status=status,
            rule_violations=violations,
            trend=trend,
        )


class QualityCollector:
    """Simulated quality data — in production, reads from batch quality tracker."""

    @classmethod
    def get_current(cls) -> QualityData:
        hour = datetime.now().hour
        if 6 <= hour < 14:
            grade_a_pct = random.uniform(85, 95)
            defect_rate = random.uniform(0.8, 1.5)
            score = random.uniform(88, 96)
            batches = random.randint(8, 12)
        elif 14 <= hour < 22:
            grade_a_pct = random.uniform(75, 88)
            defect_rate = random.uniform(1.5, 3.0)
            score = random.uniform(78, 90)
            batches = random.randint(6, 10)
        else:
            grade_a_pct = random.uniform(65, 80)
            defect_rate = random.uniform(2.5, 4.5)
            score = random.uniform(70, 82)
            batches = random.randint(4, 7)

        return QualityData(
            grade_a_pct=round(grade_a_pct, 2),
            defect_rate_pct=round(defect_rate, 2),
            avg_quality_score=round(score, 1),
            batch_count=batches,
        )


class ThroughputCollector:
    """Simulated throughput data — in production, reads from sorter controller."""

    @classmethod
    def get_current(cls) -> ThroughputData:
        target = 2.0
        hour = datetime.now().hour
        if 6 <= hour < 14:
            rate = random.uniform(1.55, 1.72)
        elif 14 <= hour < 22:
            rate = random.uniform(1.20, 1.40)
        else:
            rate = random.uniform(0.50, 0.70)

        efficiency = (rate / target) * 100
        # Today's cumulative: assume started at 6am
        now = datetime.now()
        hours_running = max(0, (now.hour + now.minute / 60) - 6)
        total_today = rate * hours_running

        return ThroughputData(
            current_kg_h=round(rate, 3),
            target_kg_h=target,
            efficiency_pct=round(efficiency, 1),
            total_kg_today=round(total_today, 2),
        )


class AlarmCollector:
    """Simulated alarm counts — in production, reads from alarm manager."""

    @classmethod
    def get_current(cls) -> tuple[int, int]:
        hour = datetime.now().hour
        if 6 <= hour < 14:
            active = random.randint(0, 1)
            suppressed = random.randint(0, 2)
        elif 14 <= hour < 22:
            active = random.randint(1, 3)
            suppressed = random.randint(0, 4)
        else:
            active = random.randint(0, 2)
            suppressed = random.randint(1, 5)

        return active, suppressed


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING & RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

class ScoringEngine:
    """Composite scoring + recommendation engine."""

    @staticmethod
    def compute_overall_score(m: ProductionMetrics) -> float:
        # Weighted composite: OEE 30%, SPC 20%, Quality 25%, Throughput 15%, Alarms 10%
        oee_score = m.oee.oee * 100
        spc_score = min(m.spc.cpk / 2.0, 1.0) * 100  # Cpk 2.0 = 100
        quality_score = m.quality.grade_a_pct  # already 0-100
        throughput_score = (m.throughput.current_kg_h / m.throughput.target_kg_h) * 100
        throughput_score = min(throughput_score, 100)
        alarm_score = max(0, 100 - m.alarms_active * 20)

        total = (
            oee_score * 0.30 +
            spc_score * 0.20 +
            quality_score * 0.25 +
            throughput_score * 0.15 +
            alarm_score * 0.10
        )
        return round(total, 1)

    @staticmethod
    def determine_status(score: float) -> str:
        if score >= 85:
            return "optimal"
        elif score >= 70:
            return "good"
        elif score >= 50:
            return "warning"
        else:
            return "critical"

    @staticmethod
    def generate_recommendations(m: ProductionMetrics, score: float) -> list[str]:
        recs = []

        if m.oee.oee < 0.60:
            recs.append("OEE below 60% — investigate unplanned downtime (check feeder, air supply)")
        if m.oee.performance < 0.70:
            recs.append("Performance efficiency low — verify vibration feeder speed and bean flow rate")
        if m.oee.availability < 0.80:
            recs.append("Availability below 80% — schedule preventive maintenance on mechanical components")

        if m.spc.cpk < 1.0:
            recs.append(f"SPC Cpk={m.spc.cpk:.2f} below target — review {random.choice(['bean_weight','moisture_content','color_score'])} process limits")
        if m.spc.rule_violations >= 3:
            recs.append(f"SPC rule violations detected ({m.spc.rule_violations}) — run Western Electric diagnostic")

        if m.quality.defect_rate_pct > 3.0:
            recs.append(f"Defect rate {m.quality.defect_rate_pct}% exceeds 3% — inspect sorting thresholds and camera calibration")
        if m.quality.grade_a_pct < 75:
            recs.append(f"Grade A yield {m.quality.grade_a_pct}% below 75% — review batch recipe thresholds")

        if m.throughput.efficiency_pct < 75:
            recs.append(f"Throughput at {m.throughput.efficiency_pct}% of target — consider upgrading to Nema17 motors or adding channel")

        if m.alarms_active >= 3:
            recs.append(f"Active alarms ({m.alarms_active}) — review alarm manager for unresolved issues")

        if not recs:
            recs.append("All metrics within acceptable ranges — continue monitoring")

        return recs


# ══════════════════════════════════════════════════════════════════════════════
#  VISUALIZATION (ASCII)
# ══════════════════════════════════════════════════════════════════════════════

class ASCIIDashboard:
    """ASCII visualization renderer."""

    @staticmethod
    def bar(value: float, width: int = 20, filled: str = "█", empty: str = "░") -> str:
        filled_count = int(round(value / 100 * width))
        return filled * filled_count + empty * (width - filled_count)

    @staticmethod
    def gauge(value: float, label: str, suffix: str = "%") -> str:
        bar_str = ASCIIDashboard.bar(value, 16)
        return f"{label:20s} [{bar_str}] {value:.1f}{suffix}"

    @staticmethod
    def render(m: ProductionMetrics, overall: float, status: str) -> str:
        status_color = {
            "optimal": "🟢", "good": "🟡",
            "warning": "🟠", "critical": "🔴"
        }.get(status, "⚪")

        lines = []
        lines.append("╔══════════════════════════════════════════════════════════════════╗")
        lines.append(f"║     PRODUCTION ANALYTICS DASHBOARD    {datetime.now().strftime('%Y-%m-%d %H:%M'):>20}    ║")
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append(f"║  Overall Score: {overall:.1f}/100  Status: {status_color} {status.upper():8s}  Alarms: {m.alarms_active} active║")
        lines.append("╠══════════════════════════════════════════════════════════════════╣")

        # OEE Section
        oee_pct = m.oee.oee * 100
        oee_bar = ASCIIDashboard.bar(oee_pct, 18)
        lines.append(f"║  OEE                  [{oee_bar}] {oee_pct:.1f}%                        ║")
        lines.append(f"║    Availability   {m.oee.availability*100:5.1f}%   Performance {m.oee.performance*100:5.1f}%   Quality {m.oee.quality*100:5.1f}%  ║")
        lines.append(f"║    Prod. Rate    {m.oee.production_rate_kg_h:.3f} kg/h                             ║")

        # SPC Section
        spc_color = {"excellent": "✅", "good": "🟡", "warning": "🟠", "critical": "❌"}.get(m.spc.status, "⚪")
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append(f"║  SPC Cpk={m.spc.cpk:.3f} [{spc_color} {m.spc.status.upper():8s}]  CP={m.spc.cp:.3f}  Violations={m.spc.rule_violations}  Trend: {m.spc.trend.upper():8s}  ║")

        # Quality Section
        grade_bar = ASCIIDashboard.bar(m.quality.grade_a_pct, 18)
        defect_str = f"{m.quality.defect_rate_pct:.2f}%"
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append(f"║  Quality  Grade A {grade_bar} {m.quality.grade_a_pct:.1f}%              ║")
        lines.append(f"║           Defect Rate: {defect_str:6s}   Score: {m.quality.avg_quality_score:5.1f}   Batches: {m.quality.batch_count:2d}       ║")

        # Throughput Section
        eff_bar = ASCIIDashboard.bar(m.throughput.efficiency_pct, 18)
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append(f"║  Throughput  [{eff_bar}] {m.throughput.efficiency_pct:.1f}% of target      ║")
        lines.append(f"║  Current: {m.throughput.current_kg_h:.3f} kg/h   Target: {m.throughput.target_kg_h:.1f} kg/h   Today: {m.throughput.total_kg_today:.2f} kg║")

        # Alarms
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        lines.append(f"║  Alarms: {m.alarms_active} active  |  {m.alerts_suppressed} suppressed                          ║")
        lines.append("╚══════════════════════════════════════════════════════════════════╝")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYTICS ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class ProductionAnalyticsOrchestrator:
    """
    Main orchestrator for the production analytics dashboard.
    Aggregates metrics from all subsystems, computes composite scores,
    generates recommendations, and produces ASCII + JSON output.
    """

    def __init__(self):
        self.oee_collector = OEECollector()
        self.spc_collector = SPCCollector()
        self.quality_collector = QualityCollector()
        self.throughput_collector = ThroughputCollector()
        self.alarm_collector = AlarmCollector()
        self.scoring_engine = ScoringEngine()
        self.ascii_renderer = ASCIIDashboard()

    def collect_current_metrics(self) -> ProductionMetrics:
        oee = self.oee_collector.get_current()
        spc = self.spc_collector.get_current()
        quality = self.quality_collector.get_current()
        throughput = self.throughput_collector.get_current()
        active, suppressed = self.alarm_collector.get_current()

        return ProductionMetrics(
            oee=oee,
            spc=spc,
            quality=quality,
            throughput=throughput,
            alarms_active=active,
            alerts_suppressed=suppressed,
        )

    def generate_dashboard(self, metrics: Optional[ProductionMetrics] = None) -> DashboardMetrics:
        if metrics is None:
            metrics = self.collect_current_metrics()

        score = self.scoring_engine.compute_overall_score(metrics)
        status = self.scoring_engine.determine_status(score)
        recommendations = self.scoring_engine.generate_recommendations(metrics, score)

        return DashboardMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            metrics=metrics,
            overall_score=score,
            status=status,
            recommendations=recommendations,
        )

    def print_dashboard(self, d: DashboardMetrics) -> str:
        ascii_output = self.ascii_renderer.render(d.metrics, d.overall_score, d.status)
        return ascii_output

    def generate_report(self, d: DashboardMetrics) -> dict[str, Any]:
        m = d.metrics
        return {
            "report_id": f"ANALYTICS-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "generated_at": d.timestamp,
            "overall_score": d.overall_score,
            "status": d.status,
            "oee": {
                "oee_pct": round(m.oee.oee * 100, 2),
                "availability_pct": round(m.oee.availability * 100, 2),
                "performance_pct": round(m.oee.performance * 100, 2),
                "quality_pct": round(m.oee.quality * 100, 2),
                "production_rate_kg_h": m.oee.production_rate_kg_h,
            },
            "spc": {
                "cp": m.spc.cp,
                "cpk": m.spc.cpk,
                "status": m.spc.status,
                "rule_violations": m.spc.rule_violations,
                "trend": m.spc.trend,
            },
            "quality": {
                "grade_a_pct": m.quality.grade_a_pct,
                "defect_rate_pct": m.quality.defect_rate_pct,
                "avg_quality_score": m.quality.avg_quality_score,
                "batch_count": m.quality.batch_count,
            },
            "throughput": {
                "current_kg_h": m.throughput.current_kg_h,
                "target_kg_h": m.throughput.target_kg_h,
                "efficiency_pct": m.throughput.efficiency_pct,
                "total_kg_today": m.throughput.total_kg_today,
            },
            "alarms": {
                "active": m.alarms_active,
                "suppressed": m.alerts_suppressed,
            },
            "recommendations": d.recommendations,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  TREND ANALYSIS (Historical)
# ══════════════════════════════════════════════════════════════════════════════

class TrendAnalyzer:
    """Analyzes historical metrics for pattern detection."""

    @staticmethod
    def generate_historical_oee(n: int = 24) -> list[dict]:
        """Generate n hours of simulated OEE history."""
        results = []
        now = datetime.now()
        for i in range(n, 0, -1):
            h = (now.hour - i) % 24
            if 6 <= h < 14:
                base_oee = random.uniform(0.70, 0.85)
            elif 14 <= h < 22:
                base_oee = random.uniform(0.55, 0.70)
            else:
                base_oee = random.uniform(0.30, 0.50)

            results.append({
                "hour": h,
                "oee": round(base_oee * random.uniform(0.97, 1.03), 4),
                "production_rate_kg_h": round(base_oee * 2.0 * random.uniform(0.97, 1.03), 3),
            })
        return results

    @staticmethod
    def compute_trend(scores: list[float]) -> str:
        if len(scores) < 3:
            return "stable"
        first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
        second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
        diff_pct = (second_half - first_half) / first_half * 100
        if diff_pct > 5:
            return "improving"
        elif diff_pct < -5:
            return "degrading"
        else:
            return "stable"


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Production Analytics Dashboard")
    parser.add_argument("--demo", action="store_true", help="Run with simulated data")
    parser.add_argument("--json", action="store_true", help="Output JSON report to file")
    parser.add_argument("--hours", type=int, default=24, help="Hours of historical trend")
    args = parser.parse_args()

    orchestrator = ProductionAnalyticsOrchestrator()

    # Collect and generate
    metrics = orchestrator.collect_current_metrics()
    dashboard = orchestrator.generate_dashboard(metrics)

    # Print ASCII
    print(orchestrator.print_dashboard(dashboard))

    # Trend analysis
    print("\n─── OEE Historical Trend (24h) ───")
    history = TrendAnalyzer.generate_historical_oee(args.hours)
    avg_oee = sum(h["oee"] for h in history) / len(history)
    trend = TrendAnalyzer.compute_trend([h["oee"] for h in history])
    print(f"  Average OEE: {avg_oee*100:.1f}%  |  Trend: {trend.upper()}")
    print(f"  Best hour:  {max(history, key=lambda x: x['oee'])['oee']*100:.1f}%  |  Worst: {min(history, key=lambda x: x['oee'])['oee']*100:.1f}%")

    # Recommendations
    print("\n─── Recommendations ───")
    for i, rec in enumerate(dashboard.recommendations, 1):
        print(f"  {i}. {rec}")

    # JSON report
    report = orchestrator.generate_report(dashboard)

    if args.json:
        out_path = Path("sorter/reports/production_analytics_report.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✅ Report saved: {out_path}")

    return report


if __name__ == "__main__":
    report = main()