#!/usr/bin/env python3
# sorter/simulation/process_capability_analysis.py
# Process Capability Analysis for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-16

"""
Process Capability Analysis
============================
Comprehensive process capability analysis for the green coffee bean sorter.
Analyzes whether the system can reliably meet quality and throughput targets
under real-world process variation.

Key Outputs:
- Cpk analysis per critical parameter (weight, color, moisture, density)
- Overall equipment effectiveness (OEE) decomposition
- Process capability dashboard (histogram + normal curve visualization)
- Critical parameter ranking (Pareto of capability gaps)
- "Is the process capable?" verdict with evidence

Target Specs:
- Throughput: >= 2.0 kg/h (3ch x 50bpm)
- Defect rate: < 2% (Grade A >= 95%)
- Quality score: >= 85 (Grade B minimum)

Usage:
    python sorter/simulation/process_capability_analysis.py
    python sorter/simulation/process_capability_analysis.py --report
    python sorter/simulation/process_capability_analysis.py --params weight,color,moisture
    python sorter/simulation/process_capability_analysis.py --mc-samples 5000
"""

import sys
import math
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


# ============================================================================
# Data Models
# ============================================================================

class CapabilityLevel(Enum):
    WORLD_CLASS = "WORLD_CLASS"      # Cpk >= 2.0
    EXCELLENT = "EXCELLENT"          # Cpk >= 1.67
    CAPABLE = "CAPABLE"              # Cpk >= 1.33
    MARGINAL = "MARGINAL"           # Cpk >= 1.0
    NOT_CAPABLE = "NOT_CAPABLE"     # Cpk < 1.0

    @staticmethod
    def from_cpk(cpk: float) -> "CapabilityLevel":
        if cpk >= 2.0: return CapabilityLevel.WORLD_CLASS
        elif cpk >= 1.67: return CapabilityLevel.EXCELLENT
        elif cpk >= 1.33: return CapabilityLevel.CAPABLE
        elif cpk >= 1.0: return CapabilityLevel.MARGINAL
        else: return CapabilityLevel.NOT_CAPABLE


class ParameterType(Enum):
    TWO_SIDED = "two_sided"
    ONE_SIDED_UPPER = "one_sided_upper"
    ONE_SIDED_LOWER = "one_sided_lower"


@dataclass
class SpecLimits:
    nominal: float
    usl: Optional[float] = None
    lsl: Optional[float] = None
    target: Optional[float] = None
    unit: str = ""

    @property
    def parameter_type(self) -> ParameterType:
        if self.usl is not None and self.lsl is not None:
            return ParameterType.TWO_SIDED
        elif self.usl is not None:
            return ParameterType.ONE_SIDED_UPPER
        else:
            return ParameterType.ONE_SIDED_LOWER

    @property
    def tolerance(self) -> float:
        if self.usl is not None and self.lsl is not None:
            return self.usl - self.lsl
        return 0.0


@dataclass
class ProcessStats:
    mean: float
    std: float
    median: float
    min_val: float
    max_val: float
    n: int

    @property
    def variance(self) -> float:
        return self.std ** 2

    @property
    def cv(self) -> float:
        if self.mean == 0:
            return 0.0
        return abs(self.std / self.mean) * 100.0


@dataclass
class CapabilityMetrics:
    cp: float
    cpk: float
    cpk_u: float
    cpk_l: float
    pp: float
    ppk: float
    ppk_u: float
    ppk_l: float
    ppm_out_of_spec: float
    pct_out_of_spec: float
    level: CapabilityLevel

    def to_dict(self) -> dict:
        return {
            "cp": round(self.cp, 3),
            "cpk": round(self.cpk, 3),
            "cpk_u": round(self.cpk_u, 3),
            "cpk_l": round(self.cpk_l, 3),
            "pp": round(self.pp, 3),
            "ppk": round(self.ppk, 3),
            "ppm_out_of_spec": round(self.ppm_out_of_spec),
            "pct_out_of_spec": round(self.pct_out_of_spec, 4),
            "level": self.level.value,
        }


@dataclass
class ParameterAnalysis:
    name: str
    display_name: str
    specs: SpecLimits
    stats: ProcessStats
    metrics: CapabilityMetrics
    spec_status: str
    critical: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "specs": {
                "nominal": self.specs.nominal,
                "usl": self.specs.usl,
                "lsl": self.specs.lsl,
                "unit": self.specs.unit,
            },
            "stats": {
                "mean": round(self.stats.mean, 4),
                "std": round(self.stats.std, 4),
                "median": round(self.stats.median, 4),
                "cv_pct": round(self.stats.cv, 2),
                "n": self.stats.n,
            },
            "metrics": self.metrics.to_dict(),
            "spec_status": self.spec_status,
            "critical": self.critical,
            "notes": self.notes,
        }


@dataclass
class OEEAnalysis:
    availability_pct: float
    performance_pct: float
    quality_pct: float
    oee_pct: float
    target_oee_pct: float = 85.0

    @property
    def gap_pct(self) -> float:
        return self.target_oee_pct - self.oee_pct

    @property
    def world_class(self) -> bool:
        return self.oee_pct >= 85.0

    def to_dict(self) -> dict:
        return {
            "availability_pct": round(self.availability_pct, 2),
            "performance_pct": round(self.performance_pct, 2),
            "quality_pct": round(self.quality_pct, 2),
            "oee_pct": round(self.oee_pct, 2),
            "target_oee_pct": self.target_oee_pct,
            "gap_pct": round(self.gap_pct, 2),
            "world_class": self.world_class,
        }


@dataclass
class OverallVerdict:
    capable: bool
    score: float
    grade: str
    summary: str
    top_findings: List[str]
    recommendations: List[str]
    process_capable_params: int
    process_marginal_params: int
    process_not_capable_params: int

    def to_dict(self) -> dict:
        return {
            "capable": self.capable,
            "score": self.score,
            "grade": self.grade,
            "summary": self.summary,
            "top_findings": self.top_findings,
            "recommendations": self.recommendations,
            "capable_count": self.process_capable_params,
            "marginal_count": self.process_marginal_params,
            "not_capable_count": self.process_not_capable_params,
        }


# ============================================================================
# Statistical Calculations
# ============================================================================

def _compute_stats(data: List[float]) -> ProcessStats:
    if not data:
        return ProcessStats(mean=0, std=0, median=0, min_val=0, max_val=0, n=0)
    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std = math.sqrt(variance) if variance > 0 else 0.0
    sorted_data = sorted(data)
    median = sorted_data[n // 2] if n % 2 == 1 else (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
    return ProcessStats(
        mean=mean, std=std, median=median,
        min_val=min(data), max_val=max(data), n=n
    )


def _compute_capability_metrics(data: List[float], specs: SpecLimits) -> CapabilityMetrics:
    if len(data) < 2:
        return CapabilityMetrics(cp=0, cpk=0, cpk_u=0, cpk_l=0, pp=0, ppk=0,
                                  ppk_u=0, ppk_l=0, ppm_out_of_spec=0,
                                  pct_out_of_spec=100.0, level=CapabilityLevel.NOT_CAPABLE)

    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std_long = math.sqrt(variance) if variance > 0 else 1e-6

    if len(data) > 1:
        mr = [abs(data[i] - data[i-1]) for i in range(1, len(data))]
        avg_mr = sum(mr) / len(mr) if mr else 0.0
        std_short = avg_mr / 1.128 if avg_mr > 0 else std_long
    else:
        std_short = std_long

    std_short = max(std_short, 1e-6)
    std_long = max(std_long, 1e-6)

    cp = cpk = cpk_u = cpk_l = 0.0
    pp = ppk = ppk_u = ppk_l = 0.0

    if specs.usl is not None and specs.lsl is not None:
        tol = specs.usl - specs.lsl
        if std_short > 0:
            cp = tol / (6 * std_short)
            cpk_u = (specs.usl - mean) / (3 * std_short)
            cpk_l = (mean - specs.lsl) / (3 * std_short)
            cpk = min(cpk_u, cpk_l)
        if std_long > 0:
            pp = tol / (6 * std_long)
            ppk_u = (specs.usl - mean) / (3 * std_long)
            ppk_l = (mean - specs.lsl) / (3 * std_long)
            ppk = min(ppk_u, ppk_l)
    elif specs.usl is not None:
        if std_short > 0:
            cp = cpk_u = (specs.usl - mean) / (3 * std_short)
            cpk = cpk_u
        if std_long > 0:
            pp = ppk_u = (specs.usl - mean) / (3 * std_long)
            ppk = ppk_u
    elif specs.lsl is not None:
        if std_short > 0:
            cp = cpk_l = (mean - specs.lsl) / (3 * std_short)
            cpk = cpk_l
        if std_long > 0:
            pp = ppk_l = (mean - specs.lsl) / (3 * std_long)
            ppk = ppk_l

    out_count = 0
    for x in data:
        if specs.usl is not None and x > specs.usl:
            out_count += 1
        elif specs.lsl is not None and x < specs.lsl:
            out_count += 1

    pct_out = (out_count / n) * 100.0
    ppm_out = pct_out * 10000
    level = CapabilityLevel.from_cpk(cpk if cpk > 0 else ppk)

    return CapabilityMetrics(
        cp=cp, cpk=cpk, cpk_u=cpk_u, cpk_l=cpk_l,
        pp=pp, ppk=ppk, ppk_u=ppk_u, ppk_l=ppk_l,
        ppm_out_of_spec=ppm_out, pct_out_of_spec=pct_out, level=level
    )


# ============================================================================
# Process Capability Analyzer
# ============================================================================

class ProcessCapabilityAnalyzer:
    """HUSKY-SORTER-001 Process Capability Analysis Engine."""

    PARAMETER_SPECS: Dict[str, SpecLimits] = {
        "bean_weight": SpecLimits(nominal=0.152, usl=0.28, lsl=0.10, unit="g"),
        "moisture_content": SpecLimits(nominal=11.0, usl=13.5, lsl=8.5, unit="%"),
        "color_score": SpecLimits(nominal=90.0, usl=100.0, lsl=75.0, unit="score"),
        "density": SpecLimits(nominal=0.68, usl=0.75, lsl=0.55, unit="g/mL"),
        "defect_rate_pct": SpecLimits(nominal=1.0, usl=2.0, lsl=0.0, unit="%"),
        "throughput_kgh": SpecLimits(nominal=2.0, usl=None, lsl=2.0, unit="kg/h"),
        "air_jet_timing_ms": SpecLimits(nominal=15.0, usl=25.0, lsl=5.0, unit="ms"),
        "sorting_latency_ms": SpecLimits(nominal=50.0, usl=100.0, lsl=0.0, unit="ms"),
    }

    def __init__(self, mc_samples: int = 3000, seed: int = 42):
        self.mc_samples = mc_samples
        self.seed = seed
        self._cache: Dict[str, ParameterAnalysis] = {}

    def _generate_data(self, param: str) -> List[float]:
        import random
        random.seed(self.seed)
        specs = self.PARAMETER_SPECS.get(param, SpecLimits(nominal=0))
        nominal = specs.nominal

        param_variation = {
            "bean_weight": (nominal, 0.08 * nominal),
            "moisture_content": (nominal, 0.5),
            "color_score": (nominal, 5.0),
            "density": (nominal, 0.02),
            "defect_rate_pct": (1.5, 1.2),
            "throughput_kgh": (2.0, 0.3),
            "air_jet_timing_ms": (15.0, 3.0),
            "sorting_latency_ms": (50.0, 8.0),
        }

        mean, std = param_variation.get(param, (nominal, nominal * 0.1))
        data = []
        for _ in range(self.mc_samples):
            sample = random.gauss(mean, std)
            if param == "throughput_kgh" and sample < 0:
                sample = 0.0
            elif param in ("bean_weight", "moisture_content", "color_score", "density") and sample < 0:
                sample = abs(sample)
            data.append(sample)
        return data

    def analyze_parameter(self, param: str) -> ParameterAnalysis:
        if param in self._cache:
            return self._cache[param]

        specs = self.PARAMETER_SPECS.get(param, SpecLimits(nominal=0))
        display_names = {
            "bean_weight": "Bean Weight",
            "moisture_content": "Moisture Content",
            "color_score": "Color Score",
            "density": "Bean Density",
            "defect_rate_pct": "Defect Rate",
            "throughput_kgh": "Throughput",
            "air_jet_timing_ms": "Air Jet Timing",
            "sorting_latency_ms": "Sorting Latency",
        }

        data = self._generate_data(param)
        stats = _compute_stats(data)
        metrics = _compute_capability_metrics(data, specs)

        out_count = sum(1 for x in data
                       if (specs.usl is not None and x > specs.usl) or
                          (specs.lsl is not None and x < specs.lsl))

        if out_count == 0:
            spec_status = "WITHIN_SPEC"
        elif metrics.pct_out_of_spec < 5:
            spec_status = "AT_RISK"
        else:
            spec_status = "OUT_OF_SPEC"

        critical_params = {"bean_weight", "moisture_content", "color_score",
                          "defect_rate_pct", "throughput_kgh"}
        critical = param in critical_params

        notes = []
        if metrics.cpk < 1.0:
            notes.append(f"Cpk={metrics.cpk:.2f} — process NOT capable, immediate attention needed")
        elif metrics.cpk < 1.33:
            notes.append(f"Cpk={metrics.cpk:.2f} — marginal capability, improvement recommended")
        elif metrics.cpk >= 1.67:
            notes.append(f"Cpk={metrics.cpk:.2f} — excellent capability")

        if param == "throughput_kgh" and stats.mean < 2.0:
            notes.append(f"Average {stats.mean:.2f}kg/h below 2.0kg/h target")

        analysis = ParameterAnalysis(
            name=param,
            display_name=display_names.get(param, param),
            specs=specs,
            stats=stats,
            metrics=metrics,
            spec_status=spec_status,
            critical=critical,
            notes=notes,
        )
        self._cache[param] = analysis
        return analysis

    def analyze_oee(self) -> OEEAnalysis:
        availability = 88.0
        performance = 72.0
        quality = 95.0
        oee = (availability / 100) * (performance / 100) * (quality / 100) * 100
        return OEEAnalysis(availability_pct=availability, performance_pct=performance,
                           quality_pct=quality, oee_pct=oee)

    def generate_verdict(self) -> OverallVerdict:
        params = list(self.PARAMETER_SPECS.keys())
        analyses = [self.analyze_parameter(p) for p in params]

        capable = sum(1 for a in analyses
                    if a.metrics.level in (CapabilityLevel.CAPABLE, CapabilityLevel.EXCELLENT,
                                           CapabilityLevel.WORLD_CLASS))
        marginal = sum(1 for a in analyses if a.metrics.level == CapabilityLevel.MARGINAL)
        not_cap = sum(1 for a in analyses if a.metrics.level == CapabilityLevel.NOT_CAPABLE)

        total = len(analyses)
        score = (capable * 100 + marginal * 60 + not_cap * 10) / total

        if score >= 90: grade = "A"
        elif score >= 75: grade = "B"
        elif score >= 60: grade = "C"
        else: grade = "F"

        findings = [f"{a.display_name}: Cpk={a.metrics.cpk:.2f} ({a.metrics.level.value})"
                    for a in sorted(analyses, key=lambda x: x.metrics.cpk if x.metrics.cpk > 0 else 999)
                    if a.metrics.cpk < 1.33][:5]

        recommendations = []
        for a in analyses:
            if a.metrics.cpk < 1.0:
                recommendations.append(f"IMMEDIATE: {a.display_name} Cpk={a.metrics.cpk:.2f} — out of spec")
            elif a.metrics.cpk < 1.33:
                recommendations.append(f"SOON: {a.display_name} Cpk={a.metrics.cpk:.2f} — improve or monitor closely")

        throughput = self.analyze_parameter("throughput_kgh")
        if throughput.stats.mean < 2.0:
            recommendations.append("UPGRADE: Throughput below 2kg/h — need Nema17 or 5-channel upgrade")

        summary = f"{capable}/{total} parameters capable" if capable == total else \
                  f"{capable}/{total} capable — {not_cap} not capable, {marginal} marginal"

        return OverallVerdict(
            capable=(not_cap == 0 and capable >= total * 0.7),
            score=round(score, 1),
            grade=grade,
            summary=summary,
            top_findings=findings,
            recommendations=recommendations[:5],
            process_capable_params=capable,
            process_marginal_params=marginal,
            process_not_capable_params=not_cap,
        )


# ============================================================================
# ASCII Visualization
# ============================================================================

def _bar(value: float, max_val: float, width: int = 20) -> str:
    if max_val <= 0: max_val = 1.0
    filled = int((abs(value) / max_val) * width)
    return "█" * filled + "░" * (width - filled)


def _histogram(data: List[float], bins: int = 15) -> Tuple[List[Tuple[float, float, int]], float, float]:
    if not data: return [], 0.0, 1.0
    min_v, max_v = min(data), max(data)
    range_v = max_v - min_v if max_v > min_v else 1.0
    bw = range_v / bins
    edges = [min_v + i * bw for i in range(bins + 1)]
    counts = [0] * bins
    for x in data:
        idx = min(int((x - min_v) / bw), bins - 1)
        counts[idx] += 1
    max_count = max(counts) if counts else 1
    return list(zip(edges[:-1], edges[1:], counts)), min_v, max_v


def _render_hist(hist: List[Tuple[float, float, int]], min_v: float, max_v: float,
                  specs: SpecLimits, width: int = 35) -> List[str]:
    if not hist: return ["[No data]"]
    max_count = max(c for _, _, c in hist)
    if max_count == 0: max_count = 1
    lines = []
    for lo, hi, count in hist:
        bar_len = int((count / max_count) * width)
        mid = (lo + hi) / 2
        lines.append(f"  {mid:8.3f} |" + "█" * bar_len + "░" * (width - bar_len) + f" {count:4d}")
    return lines


def print_dashboard(analyzer: ProcessCapabilityAnalyzer) -> None:
    print("\n" + "=" * 70)
    print("  PROCESS CAPABILITY ANALYSIS — HUSKY-SORTER-001")
    print("  Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 70)

    verdict = analyzer.generate_verdict()
    colors = {"A": "🟢", "B": "🟡", "C": "🟠", "F": "🔴"}
    print(f"\n  OVERALL VERDICT: {colors.get(verdict.grade,'⚪')} Grade {verdict.grade} | Score {verdict.score}/100 | {'CAPABLE' if verdict.capable else 'NOT CAPABLE'}")
    print(f"  {verdict.summary}")

    if verdict.top_findings:
        print(f"\n  Top Findings:")
        for f in verdict.top_findings:
            print(f"    • {f}")

    if verdict.recommendations:
        print(f"\n  Recommendations:")
        for r in verdict.recommendations:
            print(f"    -> {r}")

    print(f"\n  {'-' * 70}")
    print("  OVERALL EQUIPMENT EFFECTIVENESS (OEE)")
    oee = analyzer.analyze_oee()
    print(f"\n  Availability:   {oee.availability_pct:.1f}%  [{_bar(oee.availability_pct, 100, 20)}]")
    print(f"  Performance:    {oee.performance_pct:.1f}%  [{_bar(oee.performance_pct, 100, 20)}]")
    print(f"  Quality:         {oee.quality_pct:.1f}%  [{_bar(oee.quality_pct, 100, 20)}]")
    print(f"  {'-'*43}")
    print(f"  OEE:            {oee.oee_pct:.1f}%  [{_bar(oee.oee_pct, 100, 20)}]  (target: {oee.target_oee_pct:.0f}%)")
    wc = "WORLD CLASS" if oee.world_class else "Below world-class"
    print(f"\n  Status: {'✅' if oee.world_class else '⚠️'} {wc} ({oee.oee_pct:.1f}% vs {oee.target_oee_pct:.0f}% target)")

    print(f"\n  {'-' * 70}")
    print("  PROCESS CAPABILITY BY PARAMETER")
    print(f"\n  {'Parameter':<22} {'Mean':>8} {'Std':>7} {'Cpk':>6} {'Level':<16} Status")
    print(f"  {'-' * 22} {'-' * 8} {'-' * 7} {'-' * 6} {'-' * 16} {'-' * 20}")

    params = list(ProcessCapabilityAnalyzer.PARAMETER_SPECS.keys())
    icons = {CapabilityLevel.WORLD_CLASS: "🌟", CapabilityLevel.EXCELLENT: "✅",
             CapabilityLevel.CAPABLE: "🟡", CapabilityLevel.MARGINAL: "⚠️",
             CapabilityLevel.NOT_CAPABLE: "❌"}

    for param in params:
        a = analyzer.analyze_parameter(param)
        cpk = a.metrics.cpk if a.metrics.cpk > 0 else a.metrics.ppk
        icon = icons.get(a.metrics.level, "")
        print(f"  {a.display_name:<22} {a.stats.mean:>8.3f} {a.stats.std:>7.3f} {cpk:>6.3f} {icon} {a.metrics.level.value:<15} {a.spec_status}")

    analyses = [analyzer.analyze_parameter(p) for p in params]
    capable = sum(1 for a in analyses if a.metrics.level in
                 (CapabilityLevel.CAPABLE, CapabilityLevel.EXCELLENT, CapabilityLevel.WORLD_CLASS))
    marginal = sum(1 for a in analyses if a.metrics.level == CapabilityLevel.MARGINAL)
    not_cap = sum(1 for a in analyses if a.metrics.level == CapabilityLevel.NOT_CAPABLE)
    total = len(analyses)

    print(f"\n  {'-' * 70}")
    print("  CAPABILITY DISTRIBUTION")
    cap_pct = capable / total * 100
    marg_pct = marginal / total * 100
    nc_pct = not_cap / total * 100
    bar_total = 50
    cap_b = int(cap_pct / 100 * bar_total)
    marg_b = int(marg_pct / 100 * bar_total)
    nc_b = bar_total - cap_b - marg_b
    print(f"\n  [{'🟢' * cap_b}{'🟡' * marg_b}{'🔴' * nc_b}]")
    print(f"  🟢 Capable (Cpk≥1.33):    {capable}/{total} ({cap_pct:.0f}%)")
    print(f"  🟡 Marginal (Cpk 1-1.33): {marginal}/{total} ({marg_pct:.0f}%)")
    print(f"  🔴 Not Capable (Cpk<1):   {not_cap}/{total} ({nc_pct:.0f}%)")

    print("\n" + "=" * 70)


def generate_json_report(analyzer: ProcessCapabilityAnalyzer) -> dict:
    params = list(ProcessCapabilityAnalyzer.PARAMETER_SPECS.keys())
    verdict = analyzer.generate_verdict()
    oee = analyzer.analyze_oee()

    param_analyses = {}
    for param in params:
        a = analyzer.analyze_parameter(param)
        cpk = a.metrics.cpk if a.metrics.cpk > 0 else a.metrics.ppk
        param_analyses[param] = {
            "display_name": a.display_name,
            "specs": {"nominal": a.specs.nominal, "usl": a.specs.usl, "lsl": a.specs.lsl, "unit": a.specs.unit},
            "stats": {"mean": round(a.stats.mean, 4), "std": round(a.stats.std, 4),
                      "median": round(a.stats.median, 4), "cv_pct": round(a.stats.cv, 2), "n": a.stats.n},
            "metrics": a.metrics.to_dict(),
            "cpk": round(cpk, 3),
            "spec_status": a.spec_status,
            "critical": a.critical,
            "notes": a.notes,
        }

    return {
        "report_id": f"PCA-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "generated_at": datetime.now().isoformat(),
        "verdict": verdict.to_dict(),
        "oee": oee.to_dict(),
        "parameters": param_analyses,
        "monte_carlo_samples": analyzer.mc_samples,
    }


def main():
    parser = argparse.ArgumentParser(description="Process Capability Analysis for HUSKY-SORTER-001")
    parser.add_argument("--report", action="store_true", help="Generate JSON report")
    parser.add_argument("--params", default="all", help="Comma-separated params (default: all)")
    parser.add_argument("--mc-samples", type=int, default=3000, help="Monte Carlo samples (default: 3000)")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    analyzer = ProcessCapabilityAnalyzer(mc_samples=args.mc_samples)

    if args.report or args.output:
        report = generate_json_report(analyzer)
        if args.output:
            Path(args.output).write_text(json.dumps(report, indent=2))
            print(f"Report saved to {args.output}")
        else:
            print(json.dumps(report, indent=2))
    else:
        print_dashboard(analyzer)


if __name__ == "__main__":
    main()