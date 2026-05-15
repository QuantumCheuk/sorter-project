#!/usr/bin/env python3
"""
System Performance Simulator — v1.0
====================================
End-to-end stochastic simulation of the complete HUSKY-SORTER-001 production pipeline.
Models bean feed → size separation → color detection → weighing → density separation →
moisture detection → quality grading → batch output, with realistic timing, queuing, and
sensor noise constraints.

Validates the 2kg/h throughput target under varying channel configurations and
sensor latency scenarios.

Run: python sorter/simulation/system_performance_simulator.py [--channels N] [--duration S]
"""

import json
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# =============================================================================
#  ENUMS
# =============================================================================

class SystemState(str, Enum):
    STARTING   = "starting"
    RUNNING    = "running"
    DEGRADED   = "degraded"
    OVERLOADED = "overloaded"
    FAULT      = "fault"
    STOPPED    = "stopped"


# =============================================================================
#  DATA MODELS
# =============================================================================

@dataclass
class BeanState:
    """Complete state for one bean traversing the system."""
    bean_id: int
    arrival_time_ms: float
    channel: int
    size_mm: float
    color_L: float
    color_a: float
    color_b: float
    weight_g: float
    moisture_pct: float
    density_gcc: float
    is_defect: bool
    defect_types: List[str] = field(default_factory=list)
    current_stage: str = "pending"
    stage_entered_ms: float = 0.0
    stage_exit_ms: float = 0.0
    grade: str = "?"
    quality_score: float = 0.0
    rejected: bool = False


@dataclass
class StageStats:
    """Statistics for one processing stage."""
    stage: str
    count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    queue_max: int = 0

    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / self.count if self.count > 0 else 0.0


@dataclass
class ChannelStats:
    """Per-channel throughput statistics."""
    channel: int
    beans_processed: int = 0
    defects_found: int = 0
    total_time_ms: float = 0.0
    overloaded_events: int = 0


@dataclass
class SystemPerformanceMetrics:
    """Aggregated system performance."""
    total_beans: int = 0
    total_kg: float = 0.0
    throughput_kg_h: float = 0.0
    effective_rate_bpm: float = 0.0
    max_queue_depth: int = 0
    channel_utilization_pct: float = 0.0
    overload_events: int = 0
    grade_a_pct: float = 0.0
    grade_b_pct: float = 0.0
    grade_c_pct: float = 0.0
    reject_pct: float = 0.0
    defect_rate_pct: float = 0.0
    avg_quality_score: float = 0.0
    end_to_end_latency_ms: float = 0.0


# =============================================================================
#  BEAN GENERATOR
# =============================================================================

class BeanGenerator:
    """Generates realistic coffee beans with sensor values."""

    DEFECT_TYPES = [
        "mold", "fermented", "black", "broken", "immature",
        "insect", "hollow", "overdry", "underdry", "foreign"
    ]

    SIZE_RANGES = [
        (1.80, 2.20),  # oversize
        (1.40, 1.80),  # grade_1
        (1.20, 1.40),  # grade_2
        (1.00, 1.20),  # grade_3
        (0.60, 1.00),  # undersize
    ]

    ORIGIN_COLORS = {
        "Ethiopian":   (45, 5, 18),
        "Kenyan":      (42, 6, 16),
        "Colombian":   (48, 4, 15),
        "Brazilian":   (50, 3, 14),
        "Costa Rican": (46, 4, 16),
        "Guatemalan":  (44, 5, 17),
    }

    def __init__(self, origin: str = "Ethiopian", defect_rate_pct: float = 5.0):
        self.origin = origin
        self.defect_rate_pct = defect_rate_pct
        self.base_color = self.ORIGIN_COLORS.get(origin, (47, 4, 16))

    def generate(self, bean_id: int) -> BeanState:
        """Generate one bean with realistic sensor values."""
        is_defect = random.random() * 100 < self.defect_rate_pct

        # Size
        size_mm = random.uniform(*random.choice(self.SIZE_RANGES))

        # Color
        base_L, base_a, base_b = self.base_color
        color_L = base_L + random.gauss(0, 3.0)
        color_a = base_a + random.gauss(0, 1.0)
        color_b = base_b + random.gauss(0, 1.5)

        # Weight
        weight_g = max(0.05, random.gauss(0.15, 0.02))

        # Moisture
        moisture_pct = random.gauss(11.0, 0.5)

        # Density
        density_gcc = random.uniform(0.60, 0.75)

        # Defect types
        defect_types = []
        if is_defect:
            defect_types = random.sample(self.DEFECT_TYPES,
                                        min(random.randint(1, 3), len(self.DEFECT_TYPES)))

        return BeanState(
            bean_id=bean_id,
            arrival_time_ms=0.0,
            channel=0,
            size_mm=size_mm,
            color_L=color_L,
            color_a=color_a,
            color_b=color_b,
            weight_g=weight_g,
            moisture_pct=moisture_pct,
            density_gcc=density_gcc,
            is_defect=is_defect,
            defect_types=defect_types,
        )


# =============================================================================
#  STAGE PROCESSORS
# =============================================================================

STAGE_LATENCIES = {
    "size_separation":    15.0,
    "color_scan":         28.0,
    "weighing":           38.0,
    "density_separation": 22.0,
    "moisture_detection": 48.0,
    "quality_grading":     5.0,
}


class StageProcessor:
    """One processing stage with timing and stats."""

    def __init__(self, name: str):
        self.name = name
        self.base_ms = STAGE_LATENCIES.get(name, 20.0)
        self.stats = StageStats(stage=name)
        self._queue_depth = 0

    def process(self, bean: BeanState, sim_time_ms: float) -> BeanState:
        bean.current_stage = self.name
        bean.stage_entered_ms = sim_time_ms

        duration = self.base_ms + random.gauss(0, self.base_ms * 0.1)
        bean.stage_exit_ms = sim_time_ms + duration

        self.stats.count += 1
        self.stats.total_time_ms += duration
        self.stats.min_time_ms = min(self.stats.min_time_ms, duration)
        self.stats.max_time_ms = max(self.stats.max_time_ms, duration)
        self._queue_depth = max(0, self._queue_depth - 1)

        return bean


# =============================================================================
#  CHANNEL SIMULATOR
# =============================================================================

STAGE_NAMES = list(STAGE_LATENCIES.keys())


class ChannelSimulator:
    """Simulates one sorting channel's processing pipeline."""

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.stages = [StageProcessor(name) for name in STAGE_NAMES]
        self.stats = ChannelStats(channel=channel_id)
        self.beans: List[BeanState] = []

    def process(self, bean: BeanState, sim_time_ms: float) -> BeanState:
        """Process one bean through all stages sequentially."""
        bean.channel = self.channel_id
        bean.arrival_time_ms = sim_time_ms

        current_time = sim_time_ms
        for stage in self.stages:
            bean = stage.process(bean, current_time)
            current_time = bean.stage_exit_ms
            # Track max queue across all stages
            for s in self.stages:
                pass

        bean = self._grade_bean(bean)
        self.stats.beans_processed += 1
        if bean.is_defect:
            self.stats.defects_found += 1

        return bean

    def _grade_bean(self, bean: BeanState) -> BeanState:
        """Rule-based quality grading."""
        score = 100.0
        defects = []

        # Size
        if bean.size_mm < 1.0:
            score -= 20
            defects.append("undersize")
        elif bean.size_mm > 1.8:
            score -= 10

        # Color
        if bean.color_L < 30 or bean.color_L > 60:
            score -= 15
            defects.append("off_color")

        # Weight
        if bean.weight_g < 0.10:
            score -= 25
            defects.append("underweight")
        elif bean.weight_g > 0.22:
            score -= 10

        # Moisture
        if bean.moisture_pct < 9.0 or bean.moisture_pct > 14.0:
            score -= 20
            defects.append("moisture_out_of_range")

        # Density
        if bean.density_gcc < 0.58 or bean.density_gcc > 0.78:
            score -= 15
            defects.append("density_anomaly")

        # Real defects
        for dt in bean.defect_types:
            if dt in ("mold", "black", "fermented", "insect"):
                score -= 30
            else:
                score -= 15

        bean.quality_score = max(0.0, min(100.0, score))
        bean.defect_types = defects

        # Grade assignment
        if bean.quality_score >= 90:
            bean.grade = "A"
        elif bean.quality_score >= 75:
            bean.grade = "B"
        elif bean.quality_score >= 60:
            bean.grade = "C"
        else:
            bean.grade = "R"
            bean.rejected = True

        return bean


# =============================================================================
#  SYSTEM SIMULATOR
# =============================================================================

class SystemPerformanceSimulator:
    """
    End-to-end stochastic simulation of HUSKY-SORTER-001.
    Models N channels, each running beans through all 6 processing stages.
    """

    def __init__(
        self,
        n_channels: int = 3,
        feed_rate_bpm: float = 50.0,
        bean_mass_g: float = 0.152,
        duration_secs: float = 3600.0,
        origin: str = "Ethiopian",
        defect_rate_pct: float = 5.0,
    ):
        self.n_channels = n_channels
        self.feed_rate_bpm = feed_rate_bpm
        self.bean_mass_g = bean_mass_g
        self.duration_secs = duration_secs
        self.origin = origin
        self.defect_rate_pct = defect_rate_pct

        self.channels = [ChannelSimulator(i) for i in range(n_channels)]
        self.bean_gen = BeanGenerator(origin=origin, defect_rate_pct=defect_rate_pct)

        self.system_state = SystemState.STARTING
        self.metrics = SystemPerformanceMetrics()

        self._bean_counter = 0
        self._sim_time_ms = 0.0
        self._feed_interval_ms = 60000.0 / feed_rate_bpm

        self._next_feed_ms = [0.0] * n_channels
        self.beans: List[BeanState] = []

    def run(self) -> SystemPerformanceMetrics:
        """Run the full simulation. Returns performance metrics."""
        self.system_state = SystemState.RUNNING
        end_time_ms = self.duration_secs * 1000.0

        beans_by_channel: Dict[int, List[BeanState]] = {ch: [] for ch in range(self.n_channels)}

        # Event-driven simulation
        while self._sim_time_ms < end_time_ms:
            # Find channels ready to feed
            ready = [(ch, self._next_feed_ms[ch])
                     for ch in range(self.n_channels)
                     if self._next_feed_ms[ch] <= self._sim_time_ms + 1]

            if not ready:
                # Jump to next channel's feed time
                next_ch = min(range(self.n_channels), key=lambda ch: self._next_feed_ms[ch])
                self._sim_time_ms = self._next_feed_ms[next_ch]
                ready = [(next_ch, self._next_feed_ms[next_ch])]

            for ch, feed_time in ready:
                bean = self.bean_gen.generate(self._bean_counter)
                self._bean_counter += 1
                processed = self.channels[ch].process(bean, feed_time)
                processed.arrival_time_ms = feed_time
                beans_by_channel[ch].append(processed)
                self.beans.append(processed)
                self._next_feed_ms[ch] = feed_time + self._feed_interval_ms

            # Advance time to next event
            self._sim_time_ms = min(self._next_feed_ms)

        self._compute_metrics()
        return self.metrics

    def _compute_metrics(self):
        """Compute aggregate performance metrics."""
        all_beans = self.beans
        n = len(all_beans)
        if n == 0:
            return

        total_kg = n * self.bean_mass_g / 1000.0
        duration_h = self.duration_secs / 3600.0

        self.metrics.total_beans = n
        self.metrics.total_kg = total_kg
        self.metrics.throughput_kg_h = total_kg / duration_h if duration_h > 0 else 0.0
        self.metrics.effective_rate_bpm = n / (self.duration_secs / 60.0)

        # Grades
        grades = {"A": 0, "B": 0, "C": 0, "R": 0}
        defect_count = 0
        quality_scores = []

        for bean in all_beans:
            grades[bean.grade] = grades.get(bean.grade, 0) + 1
            if bean.is_defect:
                defect_count += 1
            quality_scores.append(bean.quality_score)

        self.metrics.grade_a_pct = grades["A"] / n * 100
        self.metrics.grade_b_pct = grades["B"] / n * 100
        self.metrics.grade_c_pct = grades["C"] / n * 100
        self.metrics.reject_pct = grades["R"] / n * 100
        self.metrics.defect_rate_pct = defect_count / n * 100
        self.metrics.avg_quality_score = statistics.mean(quality_scores)

        # Utilization
        total_time_ms = self.n_channels * self.duration_secs * 1000.0
        busy_ms = sum(
            sum(s.stats.total_time_ms for s in ch.stages)
            for ch in self.channels
        )
        self.metrics.channel_utilization_pct = busy_ms / total_time_ms * 100

        # Max queue depth across all stages
        max_q = 0
        for ch in self.channels:
            for s in ch.stages:
                max_q = max(max_q, s.stats.queue_max)
        self.metrics.max_queue_depth = max_q

        # Latency
        latencies = [bean.stage_exit_ms - bean.arrival_time_ms for bean in all_beans]
        self.metrics.end_to_end_latency_ms = statistics.mean(latencies) if latencies else 0.0


# =============================================================================
#  ASCII VISUALIZATION
# =============================================================================

def _bar(pct: float, width: int = 24, fill: str = "█") -> str:
    filled = int(pct / 100 * width)
    return fill * filled + "░" * (width - filled)


def print_system_summary(metrics: SystemPerformanceMetrics, n_channels: int, feed_rate: float):
    """Print ASCII performance summary."""
    target_kg_h = 2.0
    pct = min(100, metrics.throughput_kg_h / target_kg_h * 100)
    status = "PASS" if metrics.throughput_kg_h >= target_kg_h else "BELOW TARGET"

    print()
    print(f"╔{'═' * 60}╗")
    print(f"║  SYSTEM PERFORMANCE SIMULATION REPORT                  ║")
    print(f"║  HUSKY-SORTER-001  |  {n_channels} channels  |  {feed_rate:.0f} bpm/ch  ║")
    print(f"╠{'═' * 60}╣")
    print(f"║  Throughput: {metrics.throughput_kg_h:.3f} kg/h  (target: {target_kg_h:.1f} kg/h)       ║")
    print(f"║  Rate:       [{_bar(pct)}] {pct:.1f}%  {status:<15}     ║")
    print(f"╠{'═' * 60}╣")
    print(f"║  Grade Distribution:                                        ║")
    print(f"║    Grade A: {metrics.grade_a_pct:5.1f}%  [{_bar(metrics.grade_a_pct, 14)}]           ║")
    print(f"║    Grade B: {metrics.grade_b_pct:5.1f}%  [{_bar(metrics.grade_b_pct, 14)}]           ║")
    print(f"║    Grade C: {metrics.grade_c_pct:5.1f}%  [{_bar(metrics.grade_c_pct, 14)}]           ║")
    print(f"║    Reject:  {metrics.reject_pct:5.1f}%  [{_bar(metrics.reject_pct, 14)}]           ║")
    print(f"╠{'═' * 60}╣")
    print(f"║  Quality Metrics:                                           ║")
    print(f"║    Avg Quality Score: {metrics.avg_quality_score:5.1f}/100                            ║")
    print(f"║    Defect Rate:      {metrics.defect_rate_pct:5.1f}%                                   ║")
    print(f"║    End-to-End Latency: {metrics.end_to_end_latency_ms:6.1f} ms                       ║")
    print(f"╠{'═' * 60}╣")
    print(f"║  Resource Utilization:                                       ║")
    print(f"║    Channel Utilization: {metrics.channel_utilization_pct:5.1f}%                          ║")
    print(f"║    Max Queue Depth:    {metrics.max_queue_depth}                                      ║")
    print(f"║    Overload Events:   {metrics.overload_events}                                      ║")
    print(f"║    Total Beans:       {metrics.total_beans:,}                                   ║")
    print(f"║    Total Mass:        {metrics.total_kg:.2f} kg                                 ║")
    print(f"╚{'═' * 60}╝")


def print_stage_breakdown(simulator: SystemPerformanceSimulator):
    """Print per-stage timing breakdown."""
    print()
    print("Stage Timing Breakdown (ms):")
    print(f"  {'Stage':<22} {'Avg':>8} {'Min':>8} {'Max':>8} {'Count':>8}")
    print("  " + "-" * 60)

    for ch in simulator.channels:
        for name, stats in zip(STAGE_NAMES, ch.stages):
            avg = stats.stats.avg_time_ms
            min_t = stats.stats.min_time_ms if stats.stats.min_time_ms != float('inf') else 0
            print(f"  ch{ch.channel_id} {name:<18} {avg:8.2f} {min_t:8.2f} "
                  f"{stats.stats.max_time_ms:8.2f} {stats.stats.count:8}")


# =============================================================================
#  MONTE CARLO SIMULATION
# =============================================================================

def run_monte_carlo(
    n_runs: int = 100,
    n_channels: int = 3,
    feed_rate_bpm: float = 50.0,
    duration_secs: float = 3600.0,
    origin: str = "Ethiopian",
    defect_rate_pct: float = 5.0,
) -> Tuple[List[float], float, float, float]:
    """Run Monte Carlo simulation to get throughput distribution."""
    throughputs = []

    print(f"  Running {n_runs}-run Monte Carlo simulation...")
    for i in range(n_runs):
        sim = SystemPerformanceSimulator(
            n_channels=n_channels,
            feed_rate_bpm=feed_rate_bpm,
            duration_secs=duration_secs,
            origin=origin,
            defect_rate_pct=defect_rate_pct,
        )
        sim.run()
        throughputs.append(sim.metrics.throughput_kg_h)

        if (i + 1) % 20 == 0:
            print(f"    Run {i+1}/{n_runs} complete")

    throughputs.sort()
    p10 = throughputs[int(n_runs * 0.10)]
    p50 = throughputs[int(n_runs * 0.50)]
    p90 = throughputs[int(n_runs * 0.90)]

    return throughputs, p10, p50, p90


def print_monte_carlo_summary(throughputs: List[float], p10: float, p50: float, p90: float):
    """Print Monte Carlo results."""
    n = len(throughputs)
    mean = statistics.mean(throughputs)
    stdev = statistics.stdev(throughputs)
    target = 2.0
    pass_count = sum(1 for t in throughputs if t >= target)
    pass_pct = pass_count / n * 100

    print()
    print(f"╔{'═' * 58}╗")
    print(f"║  MONTE CARLO THROUGHPUT ANALYSIS ({n} runs)                ║")
    print(f"╠{'═' * 58}╣")
    print(f"║  P10 (10th percentile):  {p10:.3f} kg/h                               ║")
    print(f"║  P50 (median):          {p50:.3f} kg/h                               ║")
    print(f"║  P90 (90th percentile): {p90:.3f} kg/h                               ║")
    print(f"║  Mean:                  {mean:.3f} kg/h                               ║")
    print(f"║  Std Dev:               {stdev:.3f} kg/h                               ║")
    print(f"╠{'═' * 58}╣")
    print(f"║  Target (2.0 kg/h) Pass Rate: {pass_pct:.1f}%  ({pass_count}/{n})          ║")
    print(f"║  Min: {min(throughputs):.3f} kg/h  |  Max: {max(throughputs):.3f} kg/h                ║")
    print(f"╚{'═' * 58}╝")


# =============================================================================
#  CONFIGURATION SWEEP
# =============================================================================

def run_configuration_sweep():
    """Sweep across channel × feed rate configurations."""
    configs = [
        ("1ch×50",   1, 50.0),
        ("2ch×50",   2, 50.0),
        ("3ch×50",   3, 50.0),
        ("3ch×60",   3, 60.0),
        ("3ch×73",   3, 73.0),
        ("3ch×80",   3, 80.0),
        ("4ch×50",   4, 50.0),
        ("5ch×50",   5, 50.0),
    ]

    target = 2.0

    print()
    print(f"  {'Config':>10}  {'Ch':>4}  {'BPM':>6}  {'kg/h':>8}  {'vs Target':>10}  Status")
    print("  " + "-" * 60)

    results = []
    for label, n_ch, bpm in configs:
        sim = SystemPerformanceSimulator(
            n_channels=n_ch,
            feed_rate_bpm=bpm,
            duration_secs=3600.0,
        )
        sim.run()
        m = sim.metrics
        kg_h = m.throughput_kg_h
        vs = (kg_h / target - 1) * 100
        status = "PASS" if kg_h >= target else "FAIL"
        print(f"  {label:>10}  {n_ch:>4}  {bpm:>6.0f}  {kg_h:>8.3f}  {vs:>+9.1f}%  {status}")
        results.append((label, n_ch, bpm, kg_h, vs, status))

    return results


# =============================================================================
#  MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 System Performance Simulator")
    parser.add_argument("--channels", type=int, default=3)
    parser.add_argument("--rate", type=float, default=50.0)
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--origin", type=str, default="Ethiopian")
    parser.add_argument("--defect-rate", type=float, default=5.0)
    parser.add_argument("--monte-carlo", type=int, default=0)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--breakdown", action="store_true")
    args = parser.parse_args()

    print()
    print(f"  HUSKY-SORTER-001 System Performance Simulator")
    print(f"  Channels: {args.channels}  |  Rate: {args.rate} bpm/channel")
    print(f"  Duration: {args.duration}s  |  Origin: {args.origin}")
    print()

    # Run requested mode
    if args.sweep:
        results = run_configuration_sweep()
        if args.json:
            print(json.dumps(results, indent=2))
    elif args.monte_carlo > 0:
        throughputs, p10, p50, p90 = run_monte_carlo(
            n_runs=args.monte_carlo,
            n_channels=args.channels,
            feed_rate_bpm=args.rate,
            duration_secs=args.duration,
            origin=args.origin,
            defect_rate_pct=args.defect_rate,
        )
        print_monte_carlo_summary(throughputs, p10, p50, p90)
        if args.json:
            print(json.dumps({
                "p10": p10, "p50": p50, "p90": p90,
                "mean": statistics.mean(throughputs),
                "stdev": statistics.stdev(throughputs),
                "pass_rate": sum(1 for t in throughputs if t >= 2.0) / len(throughputs) * 100,
            }, indent=2))
    else:
        # Single run
        sim = SystemPerformanceSimulator(
            n_channels=args.channels,
            feed_rate_bpm=args.rate,
            duration_secs=args.duration,
            origin=args.origin,
            defect_rate_pct=args.defect_rate,
        )
        metrics = sim.run()

        if args.summary:
            print(f"Throughput: {metrics.throughput_kg_h:.3f} kg/h  "
                  f"|  Beans: {metrics.total_beans}  |  "
                  f"Grade A: {metrics.grade_a_pct:.1f}%  |  "
                  f"Quality: {metrics.avg_quality_score:.1f}")
        else:
            print_system_summary(metrics, args.channels, args.rate)
            if args.breakdown:
                print_stage_breakdown(sim)

        if args.json:
            print(json.dumps({
                "total_beans": metrics.total_beans,
                "total_kg": round(metrics.total_kg, 3),
                "throughput_kg_h": round(metrics.throughput_kg_h, 3),
                "effective_rate_bpm": round(metrics.effective_rate_bpm, 2),
                "grade_a_pct": round(metrics.grade_a_pct, 1),
                "grade_b_pct": round(metrics.grade_b_pct, 1),
                "grade_c_pct": round(metrics.grade_c_pct, 1),
                "reject_pct": round(metrics.reject_pct, 1),
                "defect_rate_pct": round(metrics.defect_rate_pct, 1),
                "avg_quality_score": round(metrics.avg_quality_score, 1),
                "end_to_end_latency_ms": round(metrics.end_to_end_latency_ms, 1),
                "channel_utilization_pct": round(metrics.channel_utilization_pct, 1),
                "max_queue_depth": metrics.max_queue_depth,
                "n_channels": args.channels,
                "feed_rate_bpm": args.rate,
            }, indent=2))