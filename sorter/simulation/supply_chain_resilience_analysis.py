#!/usr/bin/env python3
"""
Supply Chain Resilience Analysis — v1.0
=========================================
Monte Carlo simulation of hardware supply chain risks for HUSKY-SORTER-001.
Models delivery delays, quality issues, cost impacts, and buffer stock strategies.

Run: python sorter/simulation/supply_chain_resilience_analysis.py
Output: sorter/reports/supply_chain_resilience_report.json
"""

import json
import math
import random
import statistics
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

class ComponentCategory(Enum):
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    COMPUTING = "computing"


class SupplierType(Enum):
    DOMESTIC_CN = "domestic_cn"       # 淘宝/天猫/京东/1688
    INTERNATIONAL = "international"     # 进口件
    SPECIALTY = "specialty"            # 专用件（如 HQ Camera）


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Component:
    name: str
    part_number: str
    category: ComponentCategory
    supplier_type: SupplierType
    unit_cost: float          # CNY
    lead_days_base: int       # base lead time in days
    lead_days_sigma: float    # std dev of lead time
    quantity: int            # qty needed
    critical_path: bool       # blocks entire project if delayed
    quality_fail_rate_base: float  # base defect rate (0-1)
    domestic_supplier: str    # 供应商名称
    alternate_supplier: str  # 备选供应商
    alternate_lead_days: int # 备选交货天数


@dataclass
class SupplyRiskEvent:
    name: str
    component: str
    probability: float        # 0-1
    delay_days_mean: int
    delay_days_sigma: float
    cost_penalty: float      # CNY per unit
    quality_fail_rate: float # additional defect rate


@dataclass
class BufferStockStrategy:
    name: str
    safety_days: int
    buffer_qty: int
    holding_cost_pct: float  # % of unit cost per year


@dataclass
class SimulationResult:
    iteration: int
    arrival_dates: dict[str, datetime]
    total_delay_days: int
    total_extra_cost: float
    quality_fail_count: int
    all_components_received: bool
    critical_path_delay: int
    buffer_stock_used: dict[str, int]


# ══════════════════════════════════════════════════════════════════════════════
#  SUPPLY CHAIN MODEL
# ══════════════════════════════════════════════════════════════════════════════

COMPONENTS = [
    # Computing
    Component("Raspberry Pi 4B 4GB", "RPI4-4GB", ComponentCategory.COMPUTING,
              SupplierType.DOMESTIC_CN, 390, 3, 1.0, 2, False, 0.02,
              "树莓派旗舰店", "树莓派直营店", 2),
    Component("SD Card 64GB", "SD-64GB", ComponentCategory.COMPUTING,
              SupplierType.DOMESTIC_CN, 45, 2, 0.5, 2, False, 0.05,
              "三星存储旗舰店", "闪迪自营店", 1),

    # Sensors
    Component("HQ Camera IMX477", "HQ-CAM", ComponentCategory.SENSOR,
              SupplierType.SPECIALTY, 350, 45, 15.0, 1, True, 0.03,
              "Raspberry Pi 官方", "树莓派爱好者店", 60),
    Component("HX711 Load Cell ADC", "HX711", ComponentCategory.SENSOR,
              SupplierType.DOMESTIC_CN, 18, 5, 2.0, 3, True, 0.08,
              "HX711模块专营", "淘宝壹号店", 7),
    Component("AD7746 Capacitive ADC", "AD7746", ComponentCategory.SENSOR,
              SupplierType.SPECIALTY, 60, 30, 10.0, 1, True, 0.05,
              "ADI官方旗舰店", "Mouser贸泽", 45),
    Component("USB Camera C270", "USB-CAM", ComponentCategory.SENSOR,
              SupplierType.DOMESTIC_CN, 80, 7, 3.0, 1, False, 0.04,
              "罗技官方旗舰店", "罗技专卖店", 5),

    # Actuators
    Component("Turbo Blower 5015", "TURBO", ComponentCategory.ACTUATOR,
              SupplierType.DOMESTIC_CN, 120, 30, 15.0, 1, True, 0.06,
              "盘古风机工厂店", "广发机电", 45),
    Component("Nema17 Stepper Motor", "NEMA17", ComponentCategory.ACTUATOR,
              SupplierType.DOMESTIC_CN, 85, 7, 3.0, 3, True, 0.04,
              "步进电机直销店", "阿里巴巴厂家", 5),
    Component("28BYJ-48 Stepper", "28BYJ48", ComponentCategory.ACTUATOR,
              SupplierType.DOMESTIC_CN, 12, 5, 2.0, 3, False, 0.05,
              "28BYJ专营", "阿里巴巴", 3),
    Component("Air Jet Valve", "SOL-VALVE", ComponentCategory.ACTUATOR,
              SupplierType.DOMESTIC_CN, 22, 7, 3.0, 6, False, 0.07,
              "电磁阀工厂店", "淘宝气动元件", 5),
    Component("Air Compressor", "COMPRESSOR", ComponentCategory.ACTUATOR,
              SupplierType.DOMESTIC_CN, 200, 10, 5.0, 1, True, 0.03,
              "静音空压机专营", "京东京东自营", 7),

    # Mechanical
    Component("3D Printed Parts (PETG)", "3D-PETG", ComponentCategory.MECHANICAL,
              SupplierType.DOMESTIC_CN, 25, 3, 1.0, 1, False, 0.10,
              "魔猴3D打印", "未来工厂", 2),
    Component("，孔板 (Acrylic)", "ACRYLIC", ComponentCategory.MECHANICAL,
              SupplierType.DOMESTIC_CN, 80, 5, 2.0, 1, False, 0.05,
              "激光切割加工", "阿里巴巴", 3),
    Component("Buffer Bin 8-Grid", "BUFFER", ComponentCategory.MECHANICAL,
              SupplierType.DOMESTIC_CN, 45, 4, 1.5, 1, False, 0.08,
              "收纳盒工厂店", "天猫收纳博士", 3),

    # Electrical
    Component("Power Supply 12V 3A", "PSU-12V", ComponentCategory.ELECTRICAL,
              SupplierType.DOMESTIC_CN, 35, 3, 1.0, 1, True, 0.02,
              "明纬电源旗舰", "京东自营", 2),
    Component("GPIO Cables", "GPIO-CABLE", ComponentCategory.ELECTRICAL,
              SupplierType.DOMESTIC_CN, 8, 2, 0.5, 10, False, 0.05,
              "杜邦线专营", "阿里巴巴", 1),
    Component("I2C OLED Display", "OLED", ComponentCategory.ELECTRICAL,
              SupplierType.DOMESTIC_CN, 25, 3, 1.0, 1, False, 0.04,
              "OLED显示专家", "阿里巴巴", 2),
]

# Supply risk events (black swan scenarios)
SUPPLY_RISK_EVENTS = [
    SupplyRiskEvent("HQ Camera 港口清关延误", "HQ-CAM",
                     0.15, 14, 7.0, 0, 0.01),
    SupplyRiskEvent("AD7746 代理商缺货", "AD7746",
                     0.20, 21, 8.0, 15, 0.02),
    SupplyRiskEvent("涡轮鼓风机 工厂产能不足", "TURBO",
                     0.15, 18, 6.0, 20, 0.01),
    SupplyRiskEvent("Nema17 进口磁钢涨价", "NEMA17",
                     0.10, 5, 2.0, 40, 0.02),
    SupplyRiskEvent("物流爆仓延误", "GLOBAL",
                     0.25, 4, 2.0, 0, 0.00),
    SupplyRiskEvent("618/双11 物流高峰延误", "GLOBAL",
                     0.30, 7, 3.0, 0, 0.00),
    SupplyRiskEvent("梅雨季 海运延误", "GLOBAL",
                     0.20, 10, 5.0, 0, 0.00),
    SupplyRiskEvent("贸易关税上调", "IMPORTED",
                     0.10, 3, 1.0, 50, 0.00),
]

BUFFER_STRATEGIES = [
    BufferStockStrategy("零库存", 0, 0, 0.0),
    BufferStockStrategy("1周安全库存", 7, 1, 0.15),
    BufferStockStrategy("2周安全库存", 14, 2, 0.20),
    BufferStockStrategy("4周安全库存", 28, 4, 0.25),
]

PROJECT_START_DATE = datetime(2026, 5, 1, tzinfo=timezone.utc)
TARGET_HARDWARE_DATE = datetime(2026, 7, 13, tzinfo=timezone.utc)  # Day 74


# ══════════════════════════════════════════════════════════════════════════════
#  MONTE CARLO SIMULATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def simulate_arrival(comp: Component, strategy: BufferStockStrategy,
                    risk_multiplier: float = 1.0) -> tuple[datetime, float, int]:
    """Simulate component arrival date and return (arrival, extra_cost, quality_failures)."""
    # Base lead time with gaussian noise
    lead_days = max(1, comp.lead_days_base + random.gauss(0, comp.lead_days_sigma))
    
    # Apply risk events
    extra_cost = 0.0
    quality_fails = 0
    delay_from_risks = 0
    
    for event in SUPPLY_RISK_EVENTS:
        if event.component == "GLOBAL" or event.component == comp.part_number:
            if random.random() < event.probability * risk_multiplier:
                delay_days = max(0, int(random.gauss(event.delay_days_mean, event.delay_days_sigma)))
                extra_cost += event.cost_penalty * comp.quantity
                delay_from_risks += delay_days
                quality_fails += int(event.quality_fail_rate * comp.quantity)
    
    # Apply alternate supplier scenario (10% chance of switch)
    if random.random() < 0.10:
        lead_days = comp.alternate_lead_days
    
    total_lead = lead_days + delay_from_risks
    arrival = PROJECT_START_DATE + timedelta(days=total_lead)
    
    return arrival, extra_cost, quality_fails


def run_simulation(n_iterations: int = 5000,
                   strategy: BufferStockStrategy = BUFFER_STRATEGIES[0],
                   risk_multiplier: float = 1.0) -> dict[str, Any]:
    """Run Monte Carlo supply chain simulation."""
    results: list[SimulationResult] = []
    
    for i in range(n_iterations):
        arrival_dates: dict[str, datetime] = {}
        total_delay = 0
        total_extra_cost = 0.0
        total_quality_fails = 0
        critical_path_delay = 0
        buffer_used: dict[str, int] = {}
        
        for comp in COMPONENTS:
            arrival, extra_cost, q_fails = simulate_arrival(comp, strategy, risk_multiplier)
            arrival_dates[comp.part_number] = arrival
            total_extra_cost += extra_cost
            total_quality_fails += q_fails
            
            # Calculate delay vs target
            delay = (arrival - TARGET_HARDWARE_DATE).days
            if delay > 0:
                total_delay += delay
            else:
                total_delay += 0
            
            if comp.critical_path and delay > 0:
                critical_path_delay = max(critical_path_delay, delay)
        
        results.append(SimulationResult(
            iteration=i,
            arrival_dates=arrival_dates,
            total_delay_days=total_delay,
            total_extra_cost=total_extra_cost,
            quality_fail_count=total_quality_fails,
            all_components_received=True,
            critical_path_delay=critical_path_delay,
            buffer_stock_used=buffer_used,
        ))
    
    return results


def compute_stats(results: list[SimulationResult]) -> dict[str, Any]:
    """Compute statistics from simulation results."""
    delays = [r.total_delay_days for r in results]
    costs = [r.total_extra_cost for r in results]
    fails = [r.quality_fail_count for r in results]
    crit_delays = [r.critical_path_delay for r in results]
    
    def percentile(data: list[float], p: float) -> float:
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100.0)
        return sorted_data[min(idx, len(sorted_data) - 1)]
    
    on_time_count = sum(1 for d in delays if d <= 0)
    critical_delayed_count = sum(1 for d in crit_delays if d > 0)
    
    return {
        "n_iterations": len(results),
        "delay": {
            "p10": percentile(delays, 10),
            "p50": percentile(delays, 50),
            "p90": percentile(delays, 90),
            "p95": percentile(delays, 95),
            "mean": statistics.mean(delays),
            "stdev": statistics.stdev(delays) if len(delays) > 1 else 0,
            "max": max(delays),
            "on_time_pct": on_time_count / len(results) * 100,
        },
        "extra_cost": {
            "p10": percentile(costs, 10),
            "p50": percentile(costs, 50),
            "p90": percentile(costs, 90),
            "p95": percentile(costs, 95),
            "mean": statistics.mean(costs),
            "stdev": statistics.stdev(costs) if len(costs) > 1 else 0,
            "max": max(costs),
        },
        "quality_fails": {
            "p50": percentile(fails, 50),
            "p90": percentile(fails, 90),
            "p95": percentile(fails, 95),
            "mean": statistics.mean(fails),
            "max": max(fails),
        },
        "critical_path_delay": {
            "p50": percentile(crit_delays, 50),
            "p90": percentile(crit_delays, 90),
            "p95": percentile(crit_delays, 95),
            "mean": statistics.mean(crit_delays),
            "delayed_pct": critical_delayed_count / len(results) * 100,
        },
        "on_time_pct": on_time_count / len(results) * 100,
        "total_delayed_pct": sum(1 for d in delays if d > 0) / len(results) * 100,
    }


def print_dashboard(stats: dict[str, Any], strategy: BufferStockStrategy,
                    risk_scenario: str):
    """Print ASCII dashboard."""
    print()
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║      SUPPLY CHAIN RESILIENCE ANALYSIS — {risk_scenario:<28s}  ║")
    print(f"║      Buffer Strategy: {strategy.name:<41s}       ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print()
    
    # Delay section
    d = stats["delay"]
    print(f"  📦 DELIVERY DELAY (days past target)")
    print(f"  ├─ P50 (median)   : {d['p50']:>+8.1f} days")
    print(f"  ├─ P90           : {d['p90']:>+8.1f} days")
    print(f"  ├─ P95           : {d['p95']:>+8.1f} days")
    print(f"  ├─ Mean ± σ      : {d['mean']:>+8.1f} ± {d['stdev']:>5.1f} days")
    print(f"  └─ On-time rate  : {stats['on_time_pct']:>7.1f}%  {'✅' if stats['on_time_pct'] > 80 else '⚠️' if stats['on_time_pct'] > 50 else '❌'}")
    print()
    
    # Cost section
    c = stats["extra_cost"]
    print(f"  💰 EXTRA SUPPLY COST (CNY)")
    print(f"  ├─ P50 (median)  : ¥{c['p50']:>8.1f}")
    print(f"  ├─ P90           : ¥{c['p90']:>8.1f}")
    print(f"  ├─ P95           : ¥{c['p95']:>8.1f}")
    print(f"  ├─ Mean ± σ      : ¥{c['mean']:>7.1f} ± ¥{c['stdev']:>6.1f}")
    print(f"  └─ Max worst-case: ¥{c['max']:>8.1f}")
    print()
    
    # Quality section
    q = stats["quality_fails"]
    print(f"  🔍 QUALITY FAILURES (component-level)")
    print(f"  ├─ P50 (median)  : {q['p50']:>8.0f} units")
    print(f"  ├─ P90           : {q['p90']:>8.0f} units")
    print(f"  ├─ Mean          : {q['mean']:>8.1f} units")
    print(f"  └─ Max worst-case: {q['max']:>8.0f} units")
    print()
    
    # Critical path
    cp = stats["critical_path_delay"]
    print(f"  ⚠️  CRITICAL PATH (highest-risk components)")
    print(f"  ├─ P50 delay     : {cp['p50']:>+8.1f} days")
    print(f"  ├─ P90 delay     : {cp['p90']:>+8.1f} days")
    print(f"  └─ Delayed %     : {cp['delayed_pct']:>7.1f}%  {'⚠️ HIGH RISK' if cp['delayed_pct'] > 30 else '✅ manageable'}")
    print()
    
    # Risk matrix
    print(f"  🎲 RISK MATRIX")
    total_components = len(COMPONENTS)
    critical_count = sum(1 for c in COMPONENTS if c.critical_path)
    import_count = sum(1 for c in COMPONENTS if c.supplier_type == SupplierType.SPECIALTY)
    print(f"  ├─ Total components  : {total_components:>4d}")
    print(f"  ├─ Critical-path     : {critical_count:>4d}  ({critical_count/total_components*100:.0f}%)")
    print(f"  ├─ Import/specialty  : {import_count:>4d}  ({import_count/total_components*100:.0f}%)")
    print(f"  └─ Domestics         : {total_components - import_count:>4d}  ({(total_components-import_count)/total_components*100:.0f}%)")


def print_component_risk_table():
    """Print component-level risk assessment."""
    print()
    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║              COMPONENT RISK ASSESSMENT                        ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║ {'Component':<25} {'Type':<12} {'Lead':>5} {'Risk':<9} {'Critical':<9} ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    
    for comp in sorted(COMPONENTS, key=lambda c: c.lead_days_base * (1 + c.quality_fail_rate_base * 10), reverse=True):
        # Compute risk score
        risk_score = (comp.lead_days_base * 0.3 + 
                     comp.quality_fail_rate_base * 100 +
                     (15 if comp.supplier_type == SupplierType.SPECIALTY else 0))
        
        if risk_score > 40:
            risk_label = "🔴 HIGH"
        elif risk_score > 20:
            risk_label = "🟠 MED"
        else:
            risk_label = "🟢 LOW"
        
        critical_label = "⚠️ YES" if comp.critical_path else "  no"
        type_label = comp.supplier_type.value[:8]
        
        print(f"  ║ {comp.name:<25} {type_label:<12} {comp.lead_days_base:>5}d "
              f"{risk_label:<9} {critical_label:<9} ║")
    
    print(f"  ╚══════════════════════════════════════════════════════════════╝")


def print_buffer_strategy_comparison():
    """Compare buffer stock strategies."""
    print()
    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║            BUFFER STOCK STRATEGY COMPARISON                   ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║ {'Strategy':<22} {'Safety':>7} {'Buffer':>7} {'Holding%':>9} {'Score':>6} ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    
    strategy_scores = []
    for strat in BUFFER_STRATEGIES:
        # Quick simulation for this strategy
        results = run_simulation(n_iterations=1000, strategy=strat, risk_multiplier=1.0)
        stats = compute_stats(stats_model_to_list(results))
        
        # Score: higher on-time rate, lower delay, lower cost
        score = (stats["on_time_pct"] * 1.0 - 
                 max(0, stats["delay"]["p90"]) * 2.0 -
                 stats["extra_cost"]["p90"] * 0.01)
        strategy_scores.append((strat, score, stats))
    
    strategy_scores.sort(key=lambda x: x[1], reverse=True)
    
    for strat, score, st in strategy_scores:
        on_time = st["on_time_pct"]
        p90 = st["delay"]["p90"]
        label = "✅ BEST" if strat == strategy_scores[0][0] else ""
        print(f"  ║ {strat.name:<22} {strat.safety_days:>7}d {strat.buffer_qty:>7} "
              f"{strat.holding_cost_pct*100:>8.0f}% {on_time:>5.1f}% {label}  ║")
    
    print(f"  ╚══════════════════════════════════════════════════════════════╝")


def stats_model_to_list(results: list) -> list:
    """Compatibility helper — convert SimulationResult objects to list of dicts."""
    return results


def print_scenario_analysis():
    """Print multi-scenario risk comparison."""
    print()
    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║              WHAT-IF SCENARIO ANALYSIS                        ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║ {'Scenario':<30} {'On-time%':>9} {'P90 Delay':>10} {'Extra Cost':>12} ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    
    scenarios = [
        ("Baseline (normal)", 1.0),
        ("Logistics surge (618)", 1.5),
        ("Port congestion", 2.0),
        ("Best case (smooth)", 0.5),
        ("Worst case (perfect storm)", 3.0),
    ]
    
    for name, multiplier in scenarios:
        # Run quick sim
        n = 2000
        results = run_simulation(n_iterations=n, strategy=BUFFER_STRATEGIES[0], 
                                  risk_multiplier=multiplier)
        stats = compute_stats(results)
        d = stats["delay"]
        c = stats["extra_cost"]
        ot = stats["on_time_pct"]
        
        flag = " ⚠️" if ot < 70 or d["p90"] > 30 else ""
        print(f"  ║ {name:<30} {ot:>8.1f}% {d['p90']:>+10.1f}d ¥{c['p90']:>10.1f}{flag}  ║")
    
    print(f"  ╚══════════════════════════════════════════════════════════════╝")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Supply Chain Resilience Analysis")
    parser.add_argument("--iterations", "-n", type=int, default=5000,
                        help="Number of Monte Carlo iterations (default: 5000)")
    parser.add_argument("--scenario", choices=["baseline", "logistics", "port", "best", "worst", "all"],
                        default="baseline", help="Risk scenario to simulate")
    parser.add_argument("--report", action="store_true", help="Generate JSON report")
    parser.add_argument("--buffer-compare", action="store_true",
                        help="Compare buffer stock strategies")
    args = parser.parse_args()
    
    print("=" * 65)
    print("  SUPPLY CHAIN RESILIENCE ANALYSIS — HUSKY-SORTER-001")
    print("  Monte Carlo Simulation | v1.0 | 2026-05-16")
    print("=" * 65)
    
    print_component_risk_table()
    
    if args.buffer_compare:
        print_buffer_strategy_comparison()
    
    print_scenario_analysis()
    
    # Run main simulation
    risk_map = {
        "baseline": 1.0,
        "logistics": 1.5,
        "port": 2.0,
        "best": 0.5,
        "worst": 3.0,
    }
    multiplier = risk_map.get(args.scenario, 1.0)
    scenario_name = {
        "baseline": "BASELINE",
        "logistics": "LOGISTICS SURGE (618)",
        "port": "PORT CONGESTION",
        "best": "BEST CASE",
        "worst": "PERFECT STORM",
        "all": "BASELINE",
    }.get(args.scenario, "BASELINE")
    
    print()
    print(f"  Running Monte Carlo simulation ({args.iterations} iterations)...")
    results = run_simulation(n_iterations=args.iterations,
                             strategy=BUFFER_STRATEGIES[0],
                             risk_multiplier=multiplier)
    stats = compute_stats(results)
    print_dashboard(stats, BUFFER_STRATEGIES[0], scenario_name)
    
    # Component-level analysis
    print()
    print(f"  🏭  CRITICAL PATH COMPONENT DETAIL")
    critical = [c for c in COMPONENTS if c.critical_path]
    for comp in critical:
        print(f"  ├─ {comp.name}: base lead {comp.lead_days_base}d, "
              f"supplier: {comp.domestic_supplier}, "
              f"alternate: {comp.alternate_supplier} ({comp.alternate_lead_days}d)")
    
    # Recommendations
    print()
    print(f"  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║                    RECOMMENDATIONS                            ║")
    print(f"  ╚══════════════════════════════════════════════════════════════╝")
    print(f"  1. ⚡ IMMEDIATE: Order HQ Camera NOW (45-60d lead time)")
    print(f"     → Target delivery: 2026-06-15 to have buffer before 07-13")
    print(f"  2. ⚡ IMMEDIATE: Order Turbo Blower NOW (30-45d lead time)")
    print(f"     → Both critical-path components need parallel procurement")
    print(f"  3. 📋 SUPPLIER DIVERSIFICATION: AD7746 has no good domestic alt")
    print(f"     → Consider stock-piling 2x minimum order")
    print(f"  4. 📋 LOGISTICS INSURANCE: Peak season (618/Nov11) adds +7d median delay")
    print(f"     → Plan hardware assembly start AFTER peak logistics settles")
    print(f"  5. 📋 QUALITY BUFFER: Budget ¥150 contingency per imported component")
    print(f"     → Total imported exposure: ¥{sum(c.unit_cost * c.quantity for c in COMPONENTS if c.supplier_type == SupplierType.SPECIALTY):.0f}")
    
    # Generate report
    if args.report:
        report_path = Path(__file__).parent.parent.parent / "reports" / f"supply_chain_resilience_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        report = {
            "report_id": f"SUPPLY-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": "HUSKY-SORTER-001",
            "simulation_parameters": {
                "n_iterations": args.iterations,
                "scenario": args.scenario,
                "buffer_strategy": BUFFER_STRATEGIES[0].name,
                "risk_multiplier": multiplier,
            },
            "component_count": len(COMPONENTS),
            "critical_path_count": sum(1 for c in COMPONENTS if c.critical_path),
            "statistics": stats,
            "components": [
                {
                    "name": c.name,
                    "part_number": c.part_number,
                    "category": c.category.value,
                    "unit_cost": c.unit_cost,
                    "quantity": c.quantity,
                    "lead_days_base": c.lead_days_base,
                    "supplier_type": c.supplier_type.value,
                    "critical_path": c.critical_path,
                    "domestic_supplier": c.domestic_supplier,
                    "alternate_supplier": c.alternate_supplier,
                }
                for c in COMPONENTS
            ],
        }
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print()
        print(f"  📄 Report saved: {report_path}")


if __name__ == "__main__":
    from datetime import timedelta
    main()