#!/usr/bin/env python3
"""
HUSKY-SORTER-001 - Hardware Acceptance Test Simulator
======================================================
Hardware acceptance test protocol simulator for HUSKY-SORTER-001.
Simulates real hardware test execution results based on manufacturing risk models.

Run:
  python3 sorter/simulation/acceptance_test_simulator.py
  python3 sorter/simulation/acceptance_test_simulator.py --verbose
  python3 sorter/simulation/acceptance_test_simulator.py --output reports/
"""

import json
import math
import os
import random
import statistics
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════

@dataclass
class TestResult:
    test_id: str
    name: str
    category: str
    measured_value: float
    unit: str
    threshold_low: Optional[float]
    threshold_high: Optional[float]
    is_pass: bool
    margin_pct: float
    notes: str
    is_marginal: bool
    failure_mode: Optional[str] = None


@dataclass
class CategoryResult:
    category: str
    total_tests: int
    passed_count: int
    failed_count: int
    skipped_count: int
    marginal_count: int
    pass_rate: float
    worst_margin: float
    category_score: float


@dataclass
class AcceptanceReport:
    timestamp: str
    hardware_version: str
    total_tests: int
    passed_count: int
    failed_count: int
    skipped_count: int
    marginal_count: int
    overall_pass: bool
    pass_rate: float
    category_results: List[CategoryResult]
    test_results: List[TestResult]
    recommendations: List[str]
    estimated_real_pass_rate: float
    confidence: str


# ═══════════════════════════════════════════════════════════
# Test Case Definitions
# ═══════════════════════════════════════════════════════════

# (test_id, name, category, unit, threshold_low, threshold_high, noise_sigma, bias)
ACCEPTANCE_TESTS = [
    # Color detection (6)
    ("C-01", "White board L* stability", "color", "%", 98.0, 100.0, 0.15, -0.05),
    ("C-02", "White board a* stability", "color", "%", -1.0, 1.0, 0.10, 0.0),
    ("C-03", "White board b* stability", "color", "%", -1.0, 1.0, 0.10, 0.0),
    ("C-04", "Dual-camera consistency ΔL*", "color", "ΔE", None, 2.0, 0.15, 0.1),
    ("C-05", "Color detection resolution ΔE", "color", "ΔE", 1.5, None, 0.20, 0.05),
    ("C-06", "Dark box light blocking", "color", "lux", None, 50.0, 5.0, 2.0),
    # Weighing system (4)
    ("W-01", "Zero stability - 10 readings std", "weight", "mg", None, 10.0, 0.8, 0.3),
    ("W-02", "100g calibration error", "weight", "mg", None, 50.0, 3.5, 4.0),
    ("W-03", "Weighing linearity error", "weight", "mg", None, 35.0, 2.5, 3.0),
    ("W-04", "Temp drift (20°C vs 25°C)", "weight", "mg", None, 100.0, 8.0, 5.0),
    # Moisture detection (2)
    ("M-01", "AD7746 baseline noise RMS", "moisture", "pF", None, 0.1, 0.015, 0.008),
    ("M-02", "Moisture 10-12% sample error", "moisture", "%", None, 0.8, 0.10, 0.05),
    # Density sorting (2)
    ("D-01", "Density separation accuracy", "density", "%", 90.0, None, 2.5, 1.5),
    ("D-02", "Airflow velocity stability", "density", "m/s", 3.8, 4.2, 0.10, 0.02),
    # Vibrating feeder (2)
    ("F-01", "Feeder speed stability", "feeder", "bpm", 48.0, 52.0, 1.2, 0.4),
    ("F-02", "Max feeder speed", "feeder", "bpm", 50.0, None, 1.5, -0.3),
    # System-level (2)
    ("S-01", "End-to-end single bean latency", "system", "ms", 70.0, 130.0, 5.0, 2.0),
    ("S-02", "MQTT message latency", "system", "ms", None, 100.0, 8.0, 5.0),
]

# Risk mapping: high-risk parts → affected tests
RISK_TEST_MAP = {
    "Hopper (入料斗)": ["F-01", "F-02"],
    "Color detection dark box": ["C-06", "C-04"],
    "Weighing cup": ["W-01", "W-02", "W-03"],
    "Density air channel": ["D-01", "D-02"],
    "AD7746 probe": ["M-01", "M-02"],
}

# Real hardware degradation factors (based on manufacturing risk analysis)
REAL_HW_DEGRADATION = {
    "color": 0.92,
    "weight": 0.85,
    "moisture": 0.80,
    "density": 0.88,
    "feeder": 0.90,
    "system": 0.95,
}


# ═══════════════════════════════════════════════════════════
# Simulator
# ═══════════════════════════════════════════════════════════

class AcceptanceTestSimulator:
    def __init__(self, seed: int = 42, verbose: bool = False):
        self.seed = seed
        self.rng = random.Random(seed)
        self.verbose = verbose
        self.test_results: List[TestResult] = []
        self._run_all_tests()

    def _gauss(self, sigma: float) -> float:
        u1 = self.rng.random()
        u2 = self.rng.random()
        z = math.sqrt(-2 * math.log(u1 + 1e-10)) * math.cos(2 * math.pi * u2)
        return z * sigma

    def _extra_bias(self, test_id: str, noise_sigma: float) -> float:
        """
        Compute per-test extra bias from high-risk part mapping.
        Scale sigma by noise level so high-precision tests (tiny noise_sigma)
        aren't overwhelmed. We use noise_sigma as the unit scale, and apply
        2.5 noise_sigma as the extra spread — same multiplier as before but
        now proportional to each test's actual noise floor.
        """
        bias = 0.0
        for _part, tests in RISK_TEST_MAP.items():
            if test_id in tests:
                # Scale extra bias by the test's own noise_sigma
                # (2.5× noise_sigma keeps proportional impact constant)
                bias += self.rng.gauss(0, 2.5 * noise_sigma)
        return bias

    def _eval_single_test(self, test: Tuple) -> TestResult:
        (test_id, name, cat, unit, thr_low, thr_high, noise, bias) = test

        # Per-test realistic baselines (normal operating point)
        BASELINES = {
            "C-01": (99.0, 0.15),   # white L* near 99
            "C-02": (0.0, 0.10),    # white a* near 0
            "C-03": (0.0, 0.10),    # white b* near 0
            "C-04": (0.5, 0.15),    # ΔL* small difference
            "C-05": (1.0, 0.20),    # ΔE small
            "C-06": (10.0, 5.0),    # lux low in dark box
            "W-01": (2.0, 0.8),     # std in mg
            "W-02": (20.0, 3.5),    # calibration error mg
            "W-03": (15.0, 2.5),    # linearity error mg
            "W-04": (30.0, 8.0),    # temp drift mg
            "M-01": (0.03, 0.015),  # noise pF
            "M-02": (0.3, 0.10),    # moisture error %
            "D-01": (95.0, 2.5),    # separation accuracy %
            "D-02": (4.0, 0.10),    # air velocity m/s
            "F-01": (50.0, 1.2),    # feeder bpm
            "F-02": (51.0, 1.5),    # max feeder bpm
            "S-01": (100.0, 5.0),   # latency ms
            "S-02": (40.0, 8.0),    # MQTT latency ms
        }

        base_val, noise_sigma = BASELINES.get(test_id, (50.0, 1.0))
        measurement = base_val + self._gauss(noise_sigma) + bias + self._extra_bias(test_id, noise_sigma)

        # Special case: absolute value (non-negative quantities)
        if test_id in ("C-04", "C-06", "W-01"):
            measurement = abs(measurement)

        # Pass/fail determination
        is_pass = True
        failure_mode = None
        if thr_low is not None and measurement < thr_low:
            is_pass = False
            failure_mode = "BELOW_MIN"
        if thr_high is not None and measurement > thr_high:
            is_pass = False
            failure_mode = "ABOVE_MAX"

        # Margin calculation
        margin_pct = 0.0
        if thr_low is not None and thr_high is not None:
            width = thr_high - thr_low
            midpoint = (thr_low + thr_high) / 2
            if width > 0:
                if is_pass:
                    dist = abs(measurement - midpoint)
                    margin_pct = 100.0 * (1.0 - 2.0 * dist / width)
                else:
                    if measurement < thr_low:
                        edge_dist = midpoint - width/2
                        margin_pct = -100.0 * (thr_low - measurement) / edge_dist if edge_dist > 0 else -100.0
                    else:
                        edge_dist = midpoint + width/2
                        margin_pct = -100.0 * (measurement - thr_high) / edge_dist if edge_dist > 0 else -100.0
            else:
                margin_pct = -100.0 if not is_pass else 0.0
        elif thr_high is not None:
            if thr_high > 0:
                margin_pct = 100.0 * (1.0 - measurement / thr_high) if is_pass else -100.0 * (measurement - thr_high) / thr_high
            else:
                margin_pct = -100.0 if not is_pass else 0.0
        elif thr_low is not None:
            if thr_low > 0:
                margin_pct = 100.0 * (measurement / thr_low - 1.0) if is_pass else -100.0 * (thr_low - measurement) / thr_low
            else:
                margin_pct = -100.0 if not is_pass else 0.0
        else:
            margin_pct = 50.0

        is_marginal = 0 <= abs(margin_pct) < 15.0

        notes = ""
        if not is_pass:
            notes = f"FAIL: {failure_mode}"
        elif is_marginal:
            notes = "MARGINAL"

        return TestResult(
            test_id=test_id, name=name, category=cat,
            measured_value=round(measurement, 3), unit=unit,
            threshold_low=thr_low, threshold_high=thr_high,
            is_pass=is_pass, margin_pct=round(margin_pct, 1),
            notes=notes, is_marginal=is_marginal,
            failure_mode=failure_mode
        )

    def _run_all_tests(self):
        for test in ACCEPTANCE_TESTS:
            result = self._eval_single_test(test)
            self.test_results.append(result)
            if self.verbose:
                status = "PASS" if result.is_pass else "FAIL"
                m = "MARG" if result.is_marginal else "    "
                print(f"  [{result.test_id}] {m} {status:4s} {result.name}: "
                      f"{result.measured_value}{result.unit} (margin: {result.margin_pct:+.1f}%)")

    def _summarize_cat(self, cat: str) -> CategoryResult:
        cat_res = [r for r in self.test_results if r.category == cat]
        passed_ct = sum(1 for r in cat_res if r.is_pass)
        marginal_ct = sum(1 for r in cat_res if r.is_marginal)
        margins = [r.margin_pct for r in cat_res]
        worst = min(margins) if margins else 0.0
        score = max(0.0, min(100.0, 100.0 + worst))

        return CategoryResult(
            category=cat,
            total_tests=len(cat_res),
            passed_count=passed_ct,
            failed_count=len(cat_res) - passed_ct,
            skipped_count=0,
            marginal_count=marginal_ct,
            pass_rate=round(100.0 * passed_ct / len(cat_res), 1),
            worst_margin=round(worst, 1),
            category_score=round(score, 1)
        )

    def generate_report(self) -> AcceptanceReport:
        passed_ct = sum(1 for r in self.test_results if r.is_pass)
        failed_ct = len(self.test_results) - passed_ct
        marginal_ct = sum(1 for r in self.test_results if r.is_marginal)

        categories = ["color", "weight", "moisture", "density", "feeder", "system"]
        cat_results = [self._summarize_cat(c) for c in categories if any(r.category == c for r in self.test_results)]

        # Real hardware degradation estimate
        weighted_deg = 0.0
        for cr in cat_results:
            deg = REAL_HW_DEGRADATION.get(cr.category, 1.0)
            weighted_deg += cr.pass_rate / 100.0 * (1.0 - deg)
        est_real = round(max(0.0, min(100.0, (1.0 - weighted_deg) * 100.0)), 1)

        if est_real >= 90:
            confidence = "HIGH"
        elif est_real >= 75:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Recommendations
        recommendations = []
        failed_tests = [r for r in self.test_results if not r.is_pass]
        marginal_ok = [r for r in self.test_results if r.is_marginal and r.is_pass]

        if failed_tests:
            recommendations.append(f"{len(failed_tests)} test(s) failed - hardware needs rework or replacement")
            for ft in failed_tests:
                thr_str = f"<{ft.threshold_high}" if ft.threshold_high else f">{ft.threshold_low}"
                recommendations.append(f"   {ft.test_id} {ft.name}: measured={ft.measured_value}{ft.unit}, threshold={thr_str}")

        if marginal_ok:
            recommendations.append(f"{len(marginal_ok)} marginal pass test(s) - monitor closely after deployment")

        low_score = [cr for cr in cat_results if cr.category_score < 80]
        if low_score:
            recommendations.append(f"Categories needing attention: {', '.join(c.category for c in low_score)}")

        return AcceptanceReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            hardware_version="v0.9",
            total_tests=len(self.test_results),
            passed_count=passed_ct,
            failed_count=failed_ct,
            skipped_count=0,
            marginal_count=marginal_ct,
            overall_pass=(failed_ct == 0),
            pass_rate=round(100.0 * passed_ct / len(self.test_results), 1),
            category_results=cat_results,
            test_results=self.test_results,
            recommendations=recommendations,
            estimated_real_pass_rate=est_real,
            confidence=confidence
        )


# ═══════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════

def print_report(report: AcceptanceReport, verbose: bool = False):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  HUSKY-SORTER-001 - Hardware Acceptance Test Report")
    print(f"  Simulated: {report.timestamp}")
    print(f"{sep}")

    overall = "PASS" if report.overall_pass else "FAIL"
    overall_icon = f"✅ {overall}" if report.overall_pass else f"❌ {overall}"
    print(f"\n  Overall:         {overall_icon}")
    print(f"  Pass rate:       {report.pass_rate}% ({report.passed_count}/{report.total_tests})")
    print(f"  Marginal:       {report.marginal_count}")
    print(f"  Est. real HW:    {report.pass_rate}% -> {report.estimated_real_pass_rate}%")
    print(f"  Confidence:     {report.confidence}")

    print(f"\n  Category Results")
    print(f"  {'Category':<12} {'Pass/Total':<12} {'Rate':<8} {'Score':<8} {'Worst%'}")
    print(f"  {'-'*50}")
    for cr in report.category_results:
        icons = {"color": "🎨", "weight": "⚖️", "moisture": "💧",
                 "density": "🌬️", "feeder": "📳", "system": "🔧"}
        icon = icons.get(cr.category, "•")
        bar = "█" * int(cr.category_score / 10) + "░" * (10 - int(cr.category_score / 10))
        print(f"  {icon} {cr.category:<10} {cr.passed_count}/{cr.total_tests:<8} {cr.pass_rate:>5.1f}%  {bar} {cr.category_score:>5.1f}  {cr.worst_margin:>+6.1f}%")

    if verbose or report.failed_count > 0:
        print(f"\n  Detailed Results")
        print(f"  {'ID':<6} {'Test':<35} {'Value':<10} {'Threshold':<15} {'Pass':<6} {'Margin%'}")
        print(f"  {'-'*82}")
        for r in report.test_results:
            icon = "✅" if r.is_pass else "❌"
            if r.threshold_low is not None and r.threshold_high is not None:
                th = f"[{r.threshold_low:.1f}, {r.threshold_high:.1f}]"
            elif r.threshold_high is not None:
                th = f"<{r.threshold_high:.1f}"
            elif r.threshold_low is not None:
                th = f">{r.threshold_low:.1f}"
            else:
                th = "N/A"
            print(f"  {r.test_id:<6} {r.name:<35} {r.measured_value:>8.3f}{r.unit:<2} {th:<15} {icon:<6} {r.margin_pct:>+6.1f}%")

    if report.recommendations:
        print(f"\n  Recommendations")
        for rec in report.recommendations:
            print(f"  {rec}")

    print(f"\n{sep}")
    return


def export_json(report: AcceptanceReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = out_dir / f"acceptance_test_{ts}.json"

    data = {
        "report_version": "v1.0",
        "timestamp": report.timestamp,
        "hardware_version": report.hardware_version,
        "summary": {
            "total_tests": report.total_tests,
            "passed": report.passed_count,
            "failed": report.failed_count,
            "marginal": report.marginal_count,
            "overall_pass": report.overall_pass,
            "pass_rate": report.pass_rate,
            "estimated_real_pass_rate": report.estimated_real_pass_rate,
            "confidence": report.confidence
        },
        "categories": [
            {"name": cr.category, "total": cr.total_tests, "passed": cr.passed_count,
             "failed": cr.failed_count, "marginal": cr.marginal_count,
             "pass_rate": cr.pass_rate, "score": cr.category_score, "worst_margin": cr.worst_margin}
            for cr in report.category_results
        ],
        "tests": [
            {"test_id": r.test_id, "name": r.name, "category": r.category,
             "measured_value": r.measured_value, "unit": r.unit,
             "threshold_low": r.threshold_low, "threshold_high": r.threshold_high,
             "passed": r.is_pass, "margin_pct": r.margin_pct,
             "is_marginal": r.is_marginal, "failure_mode": r.failure_mode}
            for r in report.test_results
        ],
        "recommendations": report.recommendations,
        "note": "Simulated results based on manufacturing risk model"
    }

    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return fp


def export_md(report: AcceptanceReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = out_dir / f"acceptance_test_{ts}.md"

    overall = "✅ PASS" if report.overall_pass else "❌ FAIL"

    lines = [
        "# HUSKY-SORTER-001 Hardware Acceptance Test Report",
        "",
        f"**Report time:** {report.timestamp}",
        f"**Hardware version:** {report.hardware_version}",
        "",
        "## Summary",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Overall | {overall} |",
        f"| Pass rate | {report.pass_rate}% ({report.passed_count}/{report.total_tests}) |",
        f"| Marginal | {report.marginal_count} |",
        f"| Est. real HW | {report.estimated_real_pass_rate}% |",
        f"| Confidence | {report.confidence} |",
        "",
        "## Category Results",
        "",
        f"| Category | Pass/Total | Rate | Score | Worst Margin |",
        f"|----------|-----------|------|-------|---------------|",
    ]

    for cr in report.category_results:
        bar = "█" * int(cr.category_score / 10)
        lines.append(f"| {cr.category} | {cr.passed_count}/{cr.total_tests} | {cr.pass_rate}% | {bar} {cr.category_score:.0f} | {cr.worst_margin:+.1f}% |")

    lines.extend([
        "",
        "## Detailed Results",
        "",
        f"| ID | Test | Value | Threshold | Pass | Margin |",
        f"|----|------|-------|-----------|------|--------|",
    ])

    for r in report.test_results:
        icon = "✅" if r.is_pass else "❌"
        th = ""
        if r.threshold_low is not None and r.threshold_high is not None:
            th = f"{r.threshold_low}–{r.threshold_high}"
        elif r.threshold_high is not None:
            th = f"<{r.threshold_high}"
        elif r.threshold_low is not None:
            th = f">{r.threshold_low}"
        lines.append(f"| {r.test_id} | {r.name} | {r.measured_value:.3f}{r.unit} | {th} | {icon} | {r.margin_pct:+.1f}% |")

    if report.recommendations:
        lines.extend(["", "## Recommendations", ""])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

    lines.extend(["", "---", "*Simulated result. Real hardware pass rate depends on component quality and assembly.*"])

    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="HUSKY-SORTER-001 Hardware Acceptance Test Simulator")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--output", "-o", default="reports")
    ap.add_argument("--seed", "-s", type=int, default=42)
    ap.add_argument("--format", "-f", choices=["json", "md", "all"], default="all")
    args = ap.parse_args()

    print(f"\n{'='*60}")
    print(f"  HUSKY-SORTER-001 Hardware Acceptance Test Simulator")
    print(f"  Random seed: {args.seed}")
    print(f"{'='*60}")

    sim = AcceptanceTestSimulator(seed=args.seed, verbose=args.verbose)
    report = sim.generate_report()
    print_report(report, verbose=args.verbose)

    out_dir = Path(args.output)
    if args.format in ("json", "all"):
        p = export_json(report, out_dir)
        print(f"\n  JSON: {p}")
    if args.format in ("md", "all"):
        p = export_md(report, out_dir)
        print(f"  Markdown: {p}")

    sys.exit(0 if report.overall_pass else 1)


if __name__ == "__main__":
    main()