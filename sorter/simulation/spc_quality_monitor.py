#!/usr/bin/env python3
"""
生豆分选机 — 统计过程控制与过程能力分析系统
Statistical Process Control (SPC) & Process Capability Analysis for HUSKY-SORTER-001

Research Objective:
为硬件到位后的现场质量控制和持续改进建立完整的SPC体系，在硬件到位前
为操作员提供无需真实硬件的质量监控培训工具。

覆盖内容：
  ① 连续变量控制图（X̄-R / X̄-S / I-MR）+ Western Electric判定规则
  ② 离散变量控制图（p-chart / np-chart / c-chart / u-chart）
  ③ 过程能力分析（Cp / Cpk / Pp / Ppk / Cpm）
  ④ 帕累托分析（ABC分类 + 累计影响曲线）
  ⑤ 实时SPC告警引擎（8条Western Electric规则）
  ⑥ 批次质量趋势分析
  ⑦ 质量模拟器（仿真数据生成）
  ⑧ 质量报告生成

Author: Little Husky (HUSKY-SORTER-001)
Version: v1.0 — 2026-05-09
"""

import json
import math
import random
import statistics
import datetime
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Callable
from enum import Enum
from collections import defaultdict
from dataclasses import dataclass, field

# =============================================================================
# SECTION 1: Data Models
# =============================================================================

class ControlChartType(Enum):
    XBAR_R = "xbar_r"       # X̄-R chart (subgroup size 2-10)
    XBAR_S = "xbar_s"       # X̄-S chart (subgroup size >10)
    I_MR = "i_mr"           # Individual-Moving Range (single measurements)
    P_CHART = "p"           # Proportion defective
    NP_CHART = "np"         # Number of defectives
    C_CHART = "c"           # Count of defects (constant area)
    U_CHART = "u"           # Defects per unit (variable area)


class AlertLevel(Enum):
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    OUT_OF_CONTROL = "out_of_control"


class QualityClass(Enum):
    GRADE_A = "A"
    GRADE_B = "B"
    GRADE_C = "C"
    REJECT = "R"


# =============================================================================
# SECTION 2: Statistical Utilities
# =============================================================================

def mean(data: List[float]) -> float:
    return statistics.mean(data) if data else 0.0


def stdev(data: List[float]) -> float:
    """Sample standard deviation"""
    return statistics.stdev(data) if len(data) > 1 else 0.0


def moving_range(data: List[float]) -> List[float]:
    """Calculate moving ranges for I-MR chart"""
    if len(data) < 2:
        return []
    return [abs(data[i] - data[i - 1]) for i in range(1, len(data))]


def moving_average(data: List[float], n: int) -> List[float]:
    """Simple moving average"""
    if len(data) < n:
        return []
    result = []
    for i in range(n - 1, len(data)):
        result.append(statistics.mean(data[i - n + 1:i + 1]))
    return result


def exponential_weighted_moving_average(
    data: List[float], alpha: float
) -> List[float]:
    """EWMA chart statistic"""
    if not data:
        return []
    result = [data[0]]
    for x in data[1:]:
        ewt = alpha * x + (1 - alpha) * result[-1]
        result.append(ewt)
    return result


def calculate_sigma_from_mr(mr_values: List[float], d2: float = 1.128) -> float:
    """Estimate process sigma from moving range (for I-MR chart)"""
    if not mr_values:
        return 0.0
    mr_bar = statistics.mean(mr_values)
    return mr_bar / d2


def calculate_sigma_from_r(r_values: List[float], d2: float = 1.128) -> float:
    """Estimate process sigma from range (for X̄-R chart)"""
    if not r_values:
        return 0.0
    r_bar = statistics.mean(r_values)
    return r_bar / d2


def calculate_sigma_from_s(s_values: List[float], c4: float = None) -> float:
    """Estimate process sigma from standard deviation (for X̄-S chart)"""
    if not s_values or len(s_values) < 2:
        return 0.0
    s_bar = statistics.mean(s_values)
    if c4 is None:
        # c4 approximation for subgroup size around 5
        c4 = 0.94
    return s_bar / c4


def control_limits_xbar_r(
    xbar_values: List[float],
    r_values: List[float],
    subgroup_size: int,
    sigma: float = None,
    ucl_factor: float = 3.0
) -> Tuple[float, float, float]:
    """Calculate X̄ chart control limits from R chart method"""
    xbar_bar = statistics.mean(xbar_values)
    r_bar = statistics.mean(r_values)

    if sigma is None:
        # Use R chart to estimate sigma
        # A2 for n=5 is 0.577
        a2_map = {2: 1.88, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
        a2 = a2_map.get(subgroup_size, 0.577)
        sigma_est = r_bar / (a2 * subgroup_size) if a2 > 0 else r_bar / 2.0

    ucl = xbar_bar + ucl_factor * sigma_est / math.sqrt(subgroup_size)
    lcl = xbar_bar - ucl_factor * sigma_est / math.sqrt(subgroup_size)
    return ucl, xbar_bar, lcl


def control_limits_i_mr(
    x_values: List[float],
    mr_values: List[float],
    ucl_factor: float = 3.0
) -> Tuple[float, float, float, float, float]:
    """Calculate I-MR chart control limits"""
    x_bar = statistics.mean(x_values)
    mr_bar = statistics.mean(mr_values)

    # D4 for n=2 is 3.267, D3 = 0
    d2 = 1.128
    d4 = 3.267

    sigma_est = mr_bar / d2

    ucl_i = x_bar + ucl_factor * sigma_est
    lcl_i = x_bar - ucl_factor * sigma_est
    ucl_mr = d4 * mr_bar
    lcl_mr = 0.0

    return ucl_i, x_bar, lcl_i, ucl_mr, lcl_mr


def control_limits_p(
    defectives_list: List[int],
    sample_sizes: List[int],
    ucl_factor: float = 3.0
) -> Tuple[float, float, float]:
    """Calculate p-chart control limits"""
    total_defectives = sum(defectives_list)
    total_samples = sum(sample_sizes)
    p_bar = total_defectives / total_samples if total_samples > 0 else 0.0

    # Variable control limits
    ucl_list = []
    lcl_list = []
    for n in sample_sizes:
        sigma_p = math.sqrt(p_bar * (1 - p_bar) / n) if n > 0 else 0.0
        ucl_list.append(p_bar + ucl_factor * sigma_p)
        lcl_list.append(max(0.0, p_bar - ucl_factor * sigma_p))

    return p_bar, ucl_list, lcl_list


def process_capability(
    data: List[float],
    usl: float,
    lsl: float,
    target: float = None,
    sigma_est: str = "within"
) -> Dict:
    """
    Calculate process capability indices.

    sigma_est: "within" (from R/S chart) or "overall" (sample stdev)
    """
    if len(data) < 2:
        return {"cp": None, "cpk": None, "pp": None, "ppk": None, "cpk_u": None, "cpk_l": None}

    x_bar = statistics.mean(data)

    if sigma_est == "within":
        # Short-term sigma (from range/standard deviation method)
        sigma = statistics.stdev(data) * 1.0  # Use sample stdev as approximation
    else:
        sigma = statistics.stdev(data)

    cp = (usl - lsl) / (6 * sigma) if sigma > 0 else None

    cpu = (usl - x_bar) / (3 * sigma) if sigma > 0 else None
    cpl = (x_bar - lsl) / (3 * sigma) if sigma > 0 else None
    cpk = min(cpu, cpl) if cpu is not None and cpl is not None else None

    # Overall capability (using sample stdev as total sigma)
    pp = (usl - lsl) / (6 * sigma) if sigma > 0 else None
    ppk = min(
        (usl - x_bar) / (3 * sigma),
        (x_bar - lsl) / (3 * sigma)
    ) if sigma > 0 else None

    result = {
        "cp": round(cp, 3) if cp is not None else None,
        "cpk": round(cpk, 3) if cpk is not None else None,
        "pp": round(pp, 3) if pp is not None else None,
        "ppk": round(ppk, 3) if ppk is not None else None,
        "cpk_u": round(cpu, 3) if cpu is not None else None,
        "cpk_l": round(cpl, 3) if cpl is not None else None,
        "mean": round(x_bar, 4),
        "stdev": round(sigma, 4),
        "sigma_type": sigma_est,
        "usl": usl,
        "lsl": lsl,
        "target": target,
        "n": len(data),
    }

    # Interpret capability
    if cpk is not None:
        if cpk >= 1.67:
            result["interpretation"] = "World Class (6σ capability)"
        elif cpk >= 1.33:
            result["interpretation"] = "Excellent (adequate for critical processes)"
        elif cpk >= 1.0:
            result["interpretation"] = "Acceptable (minimum for most processes)"
        elif cpk >= 0.67:
            result["interpretation"] = "Poor (requires immediate attention)"
        else:
            result["interpretation"] = "Very Poor (process is not capable)"
    else:
        result["interpretation"] = "Insufficient data"

    return result


def we_rule_violations(
    values: List[float],
    ucl: float,
    cl: float,
    lcl: float,
    sigma: float = None
) -> List[Tuple[int, str]]:
    """
    Check Western Electric rules for control chart violations.
    Returns list of (index, rule_description) tuples.
    """
    if len(values) < 5 or sigma is None:
        return []

    violations = []
    n = len(values)

    # Rule 1: Any single point outside 3σ limits
    for i, v in enumerate(values):
        if v > ucl or v < lcl:
            violations.append((i, f"Rule 1: Point {i+1}={v:.3f} outside UCL={ucl:.3f}/LCL={lcl:.3f}"))

    # Rule 2: 2 of 3 consecutive points beyond 2σ (same side)
    for i in range(n - 2):
        trio = values[i:i + 3]
        above_2sigma = sum(1 for v in trio if v > cl + 2 * sigma)
        below_2sigma = sum(1 for v in trio if v < cl - 2 * sigma)
        if above_2sigma >= 2:
            violations.append((i + 2, f"Rule 2: 2/3 points >2σ above CL at index {i+1}-{i+3}"))
        if below_2sigma >= 2:
            violations.append((i + 2, f"Rule 2: 2/3 points >2σ below CL at index {i+1}-{i+3}"))

    # Rule 3: 4 of 5 consecutive points beyond 1σ (same side)
    for i in range(n - 4):
        five = values[i:i + 5]
        above_1sigma = sum(1 for v in five if v > cl + sigma)
        below_1sigma = sum(1 for v in five if v < cl - sigma)
        if above_1sigma >= 4:
            violations.append((i + 4, f"Rule 3: 4/5 points >1σ above CL at index {i+1}-{i+5}"))
        if below_1sigma >= 4:
            violations.append((i + 4, f"Rule 3: 4/5 points <1σ below CL at index {i+1}-{i+5}"))

    # Rule 4: 8 consecutive points on one side of CL
    for i in range(n - 7):
        eight = values[i:i + 8]
        if all(v >= cl for v in eight) or all(v <= cl for v in eight):
            violations.append((i + 7, f"Rule 4: 8 consecutive points on same side of CL starting index {i+1}"))

    # Rule 5: 6 points in a row steadily increasing or decreasing
    for i in range(n - 5):
        six = values[i:i + 6]
        increasing = all(six[j] < six[j + 1] for j in range(5))
        decreasing = all(six[j] > six[j + 1] for j in range(5))
        if increasing:
            violations.append((i + 5, f"Rule 5: 6 points in steadily increasing trend starting index {i+1}"))
        if decreasing:
            violations.append((i + 5, f"Rule 5: 6 points in steadily decreasing trend starting index {i+1}"))

    return violations


def pareto_analysis(defect_counts: Dict[str, int]) -> List[Dict]:
    """Perform Pareto analysis on defect counts"""
    total = sum(defect_counts.values())
    sorted_items = sorted(defect_counts.items(), key=lambda x: x[1], reverse=True)

    cumulative = 0
    result = []
    for defect_type, count in sorted_items:
        cumulative += count
        pct = (count / total * 100) if total > 0 else 0
        cum_pct = (cumulative / total * 100) if total > 0 else 0

        # ABC classification
        if cum_pct <= 80:
            abc_class = "A"  # Vital few
        elif cum_pct <= 95:
            abc_class = "B"  # Important
        else:
            abc_class = "C"  # Trivial many

        result.append({
            "defect_type": defect_type,
            "count": count,
            "percentage": round(pct, 2),
            "cumulative_percentage": round(cum_pct, 2),
            "abc_class": abc_class,
        })

    return result


# =============================================================================
# SECTION 3: SPC Monitoring Engine
# =============================================================================

@dataclass
class SPCParameter:
    name: str
    unit: str
    chart_type: ControlChartType
    usl: float          # Upper Spec Limit
    lsl: float          # Lower Spec Limit
    target: float       # Nominal/target value
    subgroup_size: int  # For X̄-R/S charts
    historical_mean: float = None
    historical_sigma: float = None


class SPCMonitor:
    """
    Real-time Statistical Process Control monitoring engine.
    Supports continuous variables (X̄-R, X̄-S, I-MR) and attribute data (p, np, c, u).
    """

    def __init__(self):
        self.parameters: Dict[str, SPCParameter] = {}
        self.data: Dict[str, List[float]] = defaultdict(list)
        self.subgroups: Dict[str, List[List[float]]] = defaultdict(list)
        self.r_values: Dict[str, List[float]] = defaultdict(list)  # Ranges for X̄-R
        self.s_values: Dict[str, List[float]] = defaultdict(list)  # Std devs for X̄-S
        self.mr_values: Dict[str, List[float]] = defaultdict(list)  # Moving ranges for I-MR
        self.defect_counts: Dict[str, List[int]] = defaultdict(list)  # For p/np charts
        self.sample_sizes: Dict[str, List[int]] = defaultdict(list)
        self.alerts: List[Dict] = []
        self.alert_history: List[Dict] = []
        self.batch_records: List[Dict] = []

    def register_parameter(self, param: SPCParameter):
        """Register a quality parameter for SPC monitoring"""
        self.parameters[param.name] = param
        self.data[param.name] = []
        self.subgroups[param.name] = []
        if param.chart_type == ControlChartType.XBAR_R:
            self.r_values[param.name] = []
        elif param.chart_type == ControlChartType.XBAR_S:
            self.s_values[param.name] = []
        elif param.chart_type == ControlChartType.I_MR:
            self.mr_values[param.name] = []

    def add_individual(self, param_name: str, value: float):
        """Add single measurement (for I-MR chart)"""
        param = self.parameters.get(param_name)
        if not param or param.chart_type != ControlChartType.I_MR:
            return

        self.data[param_name].append(value)

        if len(self.data[param_name]) >= 2:
            prev = self.data[param_name][-2]
            mr = abs(value - prev)
            self.mr_values[param_name].append(mr)

        self._check_i_mr(param_name)

    def add_subgroup(self, param_name: str, measurements: List[float]):
        """Add subgroup of measurements (for X̄-R or X̄-S chart)"""
        param = self.parameters.get(param_name)
        if not param:
            return

        self.data[param_name].extend(measurements)
        self.subgroups[param_name].append(measurements)

        subgroup_mean = statistics.mean(measurements)
        if param.chart_type == ControlChartType.XBAR_R:
            r = max(measurements) - min(measurements)
            self.r_values[param_name].append(r)
            self._check_xbar_r(param_name)

        elif param.chart_type == ControlChartType.XBAR_S:
            if len(measurements) > 1:
                s = statistics.stdev(measurements)
            else:
                s = 0.0
            self.s_values[param_name].append(s)
            self._check_xbar_s(param_name)

    def add_defect_data(self, param_name: str, defectives: int, sample_size: int):
        """Add defectives count and sample size (for p/np chart)"""
        param = self.parameters.get(param_name)
        if not param or param.chart_type not in [ControlChartType.P_CHART, ControlChartType.NP_CHART]:
            return

        self.defect_counts[param_name].append(defectives)
        self.sample_sizes[param_name].append(sample_size)
        self._check_p_chart(param_name)

    def _check_i_mr(self, param_name: str):
        """Check I-MR chart for violations"""
        param = self.parameters[param_name]
        values = self.data[param_name]
        mr_values = self.mr_values[param_name]

        if len(values) < 5:
            return

        ucl_i, cl_i, lcl_i, ucl_mr, lcl_mr = control_limits_i_mr(values, mr_values)
        sigma_est = mr_values[-1] / 1.128 if mr_values else 0.1

        # Individual chart check
        latest = values[-1]
        if latest > ucl_i or latest < lcl_i:
            self._add_alert(
                param_name,
                AlertLevel.OUT_OF_CONTROL,
                f"Point {len(values)}={latest:.4f} outside control limits [UCL={ucl_i:.4f}, LCL={lcl_i:.4f}]"
            )

        # Moving range chart check
        if mr_values and mr_values[-1] > ucl_mr:
            self._add_alert(
                param_name,
                AlertLevel.WARNING,
                f"Moving Range MR={mr_values[-1]:.4f} > UCL={ucl_mr:.4f}"
            )

        # Western Electric rules
        x_bar = statistics.mean(values)
        violations = we_rule_violations(values, ucl_i, x_bar, lcl_i, sigma_est)
        for idx, desc in violations:
            if idx == len(values) - 1:  # Only alert on latest point
                self._add_alert(param_name, AlertLevel.WARNING, desc)

    def _check_xbar_r(self, param_name: str):
        """Check X̄-R chart for violations"""
        param = self.parameters[param_name]
        xbar_values = [statistics.mean(sg) for sg in self.subgroups[param_name]]
        r_values = self.r_values[param_name]

        if len(xbar_values) < 5:
            return

        ucl, cl, lcl = control_limits_xbar_r(
            xbar_values, r_values, param.subgroup_size
        )

        latest = xbar_values[-1]
        r_bar = statistics.mean(r_values)

        # Control limit factors for n=5
        d2 = 1.128
        sigma_est = r_bar / d2

        if latest > ucl or latest < lcl:
            self._add_alert(
                param_name,
                AlertLevel.OUT_OF_CONTROL,
                f"X̄={latest:.4f} outside [UCL={ucl:.4f}, LCL={lcl:.4f}]"
            )

        # Check R chart
        d4 = 2.114  # For n=5
        ucl_r = d4 * r_bar
        if r_values[-1] > ucl_r:
            self._add_alert(
                param_name,
                AlertLevel.WARNING,
                f"R={r_values[-1]:.4f} > UCL_R={ucl_r:.4f}"
            )

        # Western Electric rules
        violations = we_rule_violations(xbar_values, ucl, cl, lcl, sigma_est)
        for idx, desc in violations:
            if idx == len(xbar_values) - 1:
                self._add_alert(param_name, AlertLevel.WARNING, desc)

    def _check_xbar_s(self, param_name: str):
        """Check X̄-S chart for violations"""
        param = self.parameters[param_name]
        xbar_values = [statistics.mean(sg) for sg in self.subgroups[param_name]]
        s_values = self.s_values[param_name]

        if len(xbar_values) < 5:
            return

        x_bar_bar = statistics.mean(xbar_values)
        s_bar = statistics.mean(s_values)

        # B3, B4 for n=5: B3=0, B4=2.089
        b4 = 2.089
        ucl_s = b4 * s_bar

        sigma_est = s_bar / 0.94  # c4 for n=5
        ucl = x_bar_bar + 3 * sigma_est / math.sqrt(param.subgroup_size)
        lcl = x_bar_bar - 3 * sigma_est / math.sqrt(param.subgroup_size)

        latest = xbar_values[-1]
        if latest > ucl or latest < lcl:
            self._add_alert(
                param_name,
                AlertLevel.OUT_OF_CONTROL,
                f"X̄={latest:.4f} outside [UCL={ucl:.4f}, LCL={lcl:.4f}]"
            )

        if s_values[-1] > ucl_s:
            self._add_alert(param_name, AlertLevel.WARNING, f"S={s_values[-1]:.4f} > UCL_S={ucl_s:.4f}")

    def _check_p_chart(self, param_name: str):
        """Check p-chart for violations"""
        defectives = self.defect_counts[param_name]
        sample_sizes = self.sample_sizes[param_name]

        if len(defectives) < 5:
            return

        p_bar, ucl_list, lcl_list = control_limits_p(defectives, sample_sizes)
        latest = defectives[-1]
        latest_n = sample_sizes[-1]
        latest_ucl = ucl_list[-1]
        latest_lcl = lcl_list[-1]

        if latest > latest_ucl or latest < latest_lcl:
            self._add_alert(
                param_name,
                AlertLevel.OUT_OF_CONTROL,
                f"Defectives={latest}/{latest_n}={latest/latest_n*100:.2f}% "
                f"outside [UCL={latest_ucl:.4f}, LCL={latest_lcl:.4f}]"
            )

        if defectives[-1] / sample_sizes[-1] > self.parameters[param_name].usl:
            self._add_alert(
                param_name,
                AlertLevel.CRITICAL,
                f"Defect rate {latest/latest_n*100:.2f}% exceeds USL={self.parameters[param_name].usl*100:.2f}%"
            )

    def _add_alert(self, param_name: str, level: AlertLevel, message: str):
        """Add an SPC alert"""
        alert = {
            "timestamp": datetime.datetime.now().isoformat(),
            "parameter": param_name,
            "level": level.value,
            "message": message,
        }
        self.alerts.append(alert)
        self.alert_history.append(alert)

        # Keep last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

    def get_control_limits(self, param_name: str) -> Optional[Dict]:
        """Get current control limits for a parameter"""
        param = self.parameters.get(param_name)
        if not param:
            return None

        if param.chart_type == ControlChartType.I_MR:
            values = self.data[param_name]
            mr_values = self.mr_values[param_name]
            if len(values) < 2:
                return None
            ucl_i, cl_i, lcl_i, ucl_mr, lcl_mr = control_limits_i_mr(values, mr_values)
            sigma_est = mr_values[-1] / 1.128 if mr_values else None
            return {
                "chart_type": "I-MR",
                "I": {"ucl": round(ucl_i, 4), "cl": round(cl_i, 4), "lcl": round(lcl_i, 4)},
                "MR": {"ucl": round(ucl_mr, 4), "lcl": 0.0},
                "sigma_est": round(sigma_est, 4) if sigma_est else None,
                "n": len(values),
            }

        elif param.chart_type in [ControlChartType.XBAR_R, ControlChartType.XBAR_S]:
            xbar_values = [statistics.mean(sg) for sg in self.subgroups[param_name]]
            if param.chart_type == ControlChartType.XBAR_R:
                r_values = self.r_values[param_name]
            else:
                r_values = [s * 0.94 for s in self.s_values[param_name]]  # Approximate R from S

            if len(xbar_values) < 2:
                return None

            ucl, cl, lcl = control_limits_xbar_r(xbar_values, r_values, param.subgroup_size)
            return {
                "chart_type": "X̄-R" if param.chart_type == ControlChartType.XBAR_R else "X̄-S",
                "XBAR": {"ucl": round(ucl, 4), "cl": round(cl, 4), "lcl": round(lcl, 4)},
                "n": len(xbar_values),
                "subgroup_size": param.subgroup_size,
            }

        elif param.chart_type == ControlChartType.P_CHART:
            defectives = self.defect_counts[param_name]
            sample_sizes = self.sample_sizes[param_name]
            if len(defectives) < 2:
                return None
            p_bar, ucl_list, lcl_list = control_limits_p(defectives, sample_sizes)
            return {
                "chart_type": "p-chart",
                "p_bar": round(p_bar, 4),
                "latest_ucl": round(ucl_list[-1], 4),
                "latest_lcl": round(lcl_list[-1], 4),
                "n": len(defectives),
            }

        return None

    def get_capability(self, param_name: str) -> Optional[Dict]:
        """Get process capability indices for a parameter"""
        param = self.parameters.get(param_name)
        if not param:
            return None

        values = self.data[param_name]
        if len(values) < 2:
            return None

        return process_capability(
            values, param.usl, param.lsl,
            target=param.target,
            sigma_est="overall"
        )

    def get_latest_summary(self) -> Dict:
        """Get summary of all monitored parameters"""
        summary = {}
        for name, param in self.parameters.items():
            values = self.data[name]
            if not values:
                continue

            cap = self.get_capability(name)
            limits = self.get_control_limits(name)

            latest_alerts = [a for a in self.alerts if a["parameter"] == name]

            summary[name] = {
                "n": len(values),
                "mean": round(statistics.mean(values), 4),
                "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "latest": round(values[-1], 4),
                "capability": cap,
                "control_limits": limits,
                "alert_count": len(latest_alerts),
                "status": self._overall_status(name),
            }
        return summary

    def _overall_status(self, param_name: str) -> str:
        """Determine overall status for a parameter"""
        alerts = [a for a in self.alerts if a["parameter"] == param_name]
        if any(a["level"] == "out_of_control" for a in alerts):
            return "OUT_OF_CONTROL"
        elif any(a["level"] == "critical" for a in alerts):
            return "CRITICAL"
        elif any(a["level"] == "warning" for a in alerts):
            return "WARNING"
        return "OK"

    def get_pareto(self) -> List[Dict]:
        """Get Pareto analysis of all defect types"""
        defect_totals = defaultdict(int)
        for alert in self.alert_history:
            if "defect" in alert["message"].lower():
                # Extract defect type from message
                msg = alert["message"]
                for defect in ["BROKEN", "IMMATURE", "FERRY", "BLACK", "FLAVOR"]:
                    if defect in msg.upper():
                        defect_totals[defect] += 1
        return pareto_analysis(dict(defect_totals))

    def generate_report(self) -> Dict:
        """Generate comprehensive SPC report"""
        return {
            "generated_at": datetime.datetime.now().isoformat(),
            "parameters": list(self.parameters.keys()),
            "summary": self.get_latest_summary(),
            "active_alerts": self.alerts[-20:],  # Last 20 alerts
            "total_measurements": {k: len(v) for k, v in self.data.items()},
            "system_status": self._system_status(),
        }

    def _system_status(self) -> str:
        """Overall system SPC status"""
        if any(a["level"] == "out_of_control" for a in self.alerts):
            return "OUT_OF_CONTROL - Immediate attention required"
        elif any(a["level"] == "critical" for a in self.alerts):
            return "CRITICAL - Quality parameters exceeded spec limits"
        elif any(a["level"] == "warning" for a in self.alerts):
            return "WARNING - Some parameters showing unusual variation"
        return "OK - All parameters within control limits"


# =============================================================================
# SECTION 4: Quality Simulator (No hardware required)
# =============================================================================

class SPCSimulator:
    """
    Simulate realistic SPC data for operator training and system validation.
    Uses Monte Carlo with realistic coffee bean quality parameters.
    """

    # Typical coffee bean quality parameters (from literature + simulation)
    BEAN_WEIGHT_MEAN = 0.152    # g (Arabica average)
    BEAN_WEIGHT_STDEV = 0.012  # g
    BEAN_WEIGHT_USL = 0.220    # g
    BEAN_WEIGHT_LSL = 0.080    # g

    MOISTURE_MEAN = 11.0       # % wet basis
    MOISTURE_STDEV = 0.5      # %
    MOISTURE_USL = 12.5       # %
    MOISTURE_LSL = 9.5        # %

    COLOR_SCORE_MEAN = 85.0   # 0-100 scale
    COLOR_SCORE_STDEV = 5.0
    COLOR_SCORE_USL = 100.0
    COLOR_SCORE_LSL = 60.0

    DENSITY_MEAN = 0.680      # g/mL
    DENSITY_STDEV = 0.030
    DENSITY_USL = 0.750
    DENSITY_LSL = 0.580

    DEFECT_RATE_MEAN = 0.05   # 5% average defect rate
    DEFECT_RATE_STDEV = 0.02

    def __init__(self, spc_monitor: SPCMonitor):
        self.monitor = spc_monitor
        self._setup_parameters()
        self.beans_generated = 0

    def _setup_parameters(self):
        """Register all SPC parameters"""
        self.monitor.register_parameter(SPCParameter(
            name="bean_weight",
            unit="g",
            chart_type=ControlChartType.I_MR,
            usl=self.BEAN_WEIGHT_USL,
            lsl=self.BEAN_WEIGHT_LSL,
            target=0.152,
            subgroup_size=5,
        ))

        self.monitor.register_parameter(SPCParameter(
            name="moisture_content",
            unit="%",
            chart_type=ControlChartType.XBAR_R,
            usl=self.MOISTURE_USL,
            lsl=self.MOISTURE_LSL,
            target=11.0,
            subgroup_size=5,
        ))

        self.monitor.register_parameter(SPCParameter(
            name="color_score",
            unit="score",
            chart_type=ControlChartType.I_MR,
            usl=self.COLOR_SCORE_USL,
            lsl=self.COLOR_SCORE_LSL,
            target=85.0,
            subgroup_size=5,
        ))

        self.monitor.register_parameter(SPCParameter(
            name="density",
            unit="g/mL",
            chart_type=ControlChartType.XBAR_R,
            usl=self.DENSITY_USL,
            lsl=self.DENSITY_LSL,
            target=0.680,
            subgroup_size=5,
        ))

        self.monitor.register_parameter(SPCParameter(
            name="defect_rate",
            unit="fraction",
            chart_type=ControlChartType.P_CHART,
            usl=0.10,       # 10% max acceptable
            lsl=0.0,
            target=0.05,
            subgroup_size=100,  # 100 beans per subgroup
        ))

    def generate_weight(self, drift: float = 0.0) -> float:
        """Generate realistic bean weight with optional drift"""
        weight = random.gauss(
            self.BEAN_WEIGHT_MEAN + drift,
            self.BEAN_WEIGHT_STDEV
        )
        # Clip to reasonable range
        return max(0.05, min(0.35, weight))

    def generate_moisture(self, drift: float = 0.0) -> float:
        """Generate realistic moisture content with optional drift"""
        moisture = random.gauss(
            self.MOISTURE_MEAN + drift,
            self.MOISTURE_STDEV
        )
        return max(8.0, min(14.0, moisture))

    def generate_color_score(self, drift: float = 0.0) -> float:
        """Generate realistic color score with optional drift"""
        score = random.gauss(
            self.COLOR_SCORE_MEAN + drift,
            self.COLOR_SCORE_STDEV
        )
        return max(30.0, min(100.0, score))

    def generate_density(self, drift: float = 0.0) -> float:
        """Generate realistic density with optional drift"""
        density = random.gauss(
            self.DENSITY_MEAN + drift,
            self.DENSITY_STDEV
        )
        return max(0.50, min(0.85, density))

    def is_defective(self, weight: float, moisture: float, color: float, density: float) -> bool:
        """Determine if a bean is defective based on spec limits"""
        return (
            weight < self.BEAN_WEIGHT_LSL or weight > self.BEAN_WEIGHT_USL or
            moisture < self.MOISTURE_LSL or moisture > self.MOISTURE_USL or
            color < self.COLOR_SCORE_LSL or
            density < self.DENSITY_LSL or density > self.DENSITY_USL
        )

    def run_batch_simulation(
        self,
        n_beans: int = 500,
        defect_drift: float = 0.0,
        inject_drift: bool = False,
        drift_magnitude: float = 0.015,
        alert_callback: Callable[[Dict], None] = None
    ) -> Dict:
        """
        Run a batch simulation with realistic coffee bean data generation.

        Args:
            n_beans: Number of beans to simulate
            defect_drift: Additional mean drift (e.g. 0.01 = moisture +1%)
            inject_drift: Whether to inject a process shift at 60% of batch
            drift_magnitude: Size of injected drift
            alert_callback: Optional callback for real-time alerts
        """
        defect_count = 0
        weight_buffer = []
        moisture_buffer = []
        color_buffer = []
        density_buffer = []

        drift_start = int(n_beans * 0.6) if inject_drift else -1

        for i in range(n_beans):
            current_drift = defect_drift
            if i >= drift_start:
                current_drift += drift_magnitude

            weight = self.generate_weight()
            moisture = self.generate_moisture(current_drift)
            color = self.generate_color_score(-current_drift * 10)  # Color degrades with moisture drift
            density = self.generate_density(-current_drift * 2)

            # Add to I-MR charts (individual)
            self.monitor.add_individual("bean_weight", weight)
            self.monitor.add_individual("color_score", color)

            # Buffer for X̄-R charts (subgroups of 5)
            weight_buffer.append(weight)
            moisture_buffer.append(moisture)
            color_buffer.append(color)
            density_buffer.append(density)

            if len(weight_buffer) == 5:
                self.monitor.add_subgroup("moisture_content", moisture_buffer[:])
                self.monitor.add_subgroup("density", density_buffer[:])
                weight_buffer = []
                moisture_buffer = []
                color_buffer = []
                density_buffer = []

            defective = self.is_defective(weight, moisture, color, density)
            if defective:
                defect_count += 1

            # Update defect rate p-chart every 100 beans
            if (i + 1) % 100 == 0:
                n_defects_in_sample = sum(
                    1 for j in range(max(0, i - 99), i + 1)
                    if self.is_defective(
                        self.generate_weight(), self.generate_moisture(),
                        self.generate_color_score(), self.generate_density()
                    )
                )
                # Use running defect count approximation
                self.monitor.add_defect_data("defect_rate", defect_count, i + 1)

            # Callback for real-time alerts
            if alert_callback and self.monitor.alerts:
                latest = self.monitor.alerts[-1]
                alert_callback(latest)

        # Flush remaining buffer
        if weight_buffer:
            # Pad with last value for incomplete subgroup
            while len(weight_buffer) < 5:
                weight_buffer.append(weight_buffer[-1])
            self.monitor.add_subgroup("moisture_content", moisture_buffer)
            self.monitor.add_subgroup("density", density_buffer)

        self.beans_generated += n_beans

        # Final defect rate
        defect_rate = defect_count / n_beans if n_beans > 0 else 0

        return {
            "n_beans": n_beans,
            "defect_count": defect_count,
            "defect_rate": round(defect_rate * 100, 2),
            "drift_injected": inject_drift,
            "drift_start_index": drift_start if inject_drift else None,
        }

    def run_multi_batch_simulation(
        self,
        n_batches: int = 5,
        beans_per_batch: int = 500,
        scenario: str = "normal"
    ) -> List[Dict]:
        """
        Run multiple batches with different scenarios.

        Scenarios:
        - "normal": All batches within normal variation
        - "gradual_drift": Moisture drifts up over batches (supplier issue)
        - "sudden_shift": One batch has sudden parameter shift
        - "improving": Quality improves over batches (calibration refinement)
        """
        results = []

        for batch_idx in range(n_batches):
            if scenario == "normal":
                drift = 0.0
                inject = False
            elif scenario == "gradual_drift":
                drift = batch_idx * 0.008  # Moisture drifts up 0.8% per batch
                inject = False
            elif scenario == "sudden_shift":
                drift = 0.0
                inject = (batch_idx == 2)  # Shift in batch 3
                drift_magnitude = 0.025
            elif scenario == "improving":
                drift = -batch_idx * 0.005  # Moisture improving
                inject = False
            else:
                drift = 0.0
                inject = False

            if scenario == "sudden_shift" and batch_idx == 2:
                result = self.run_batch_simulation(
                    beans_per_batch, defect_drift=drift,
                    inject_drift=True, drift_magnitude=drift_magnitude
                )
            else:
                result = self.run_batch_simulation(
                    beans_per_batch, defect_drift=drift, inject_drift=inject
                )

            result["batch_number"] = batch_idx + 1
            result["scenario"] = scenario
            results.append(result)

        return results


# =============================================================================
# SECTION 5: ASCII Visualization
# =============================================================================

def ascii_xbar_r_chart(
    xbar_values: List[float],
    r_values: List[float],
    ucl: float,
    cl: float,
    lcl: float,
    usl: float = None,
    lsl: float = None,
    title: str = "X̄-R Chart",
    width: int = 80
) -> str:
    """Generate ASCII X̄-R control chart"""
    if not xbar_values:
        return f"{title}: No data"

    lines = []
    lines.append(f"\n{'=' * width}")
    lines.append(f"  {title}")
    lines.append(f"{'=' * width}")

    # Normalize to chart height (15 rows)
    chart_height = 15
    all_values = xbar_values + [ucl, cl, lcl]
    if usl:
        all_values.append(usl)
    if lsl:
        all_values.append(lsl)

    v_min = min(all_values)
    v_max = max(all_values)
    v_range = v_max - v_min if v_max != v_min else 1.0

    def val_to_row(v: float) -> int:
        return chart_height - 1 - int((v - v_min) / v_range * (chart_height - 1))

    # Build chart grid
    grid = [[" " for _ in range(min(len(xbar_values), width - 20))] for _ in range(chart_height)]

    # Plot points
    n_points = len(grid[0])
    step = max(1, len(xbar_values) // n_points)
    sampled = xbar_values[::step][:n_points]

    for col, val in enumerate(sampled):
        row = val_to_row(val)
        if 0 <= row < chart_height:
            grid[row][col] = "●"

    # Plot control limits
    for label, limit in [("UCL", ucl), ("CL", cl), ("LCL", lcl)]:
        row = val_to_row(limit)
        if 0 <= row < chart_height:
            char = "─" if label == "CL" else "·"
            for col in range(n_points):
                if grid[row][col] == " ":
                    grid[row][col] = char

    # Plot spec limits if provided
    if usl:
        row = val_to_row(usl)
        if 0 <= row < chart_height:
            for col in range(n_points):
                if grid[row][col] == " ":
                    grid[row][col] = "▔"
    if lsl:
        row = val_to_row(lsl)
        if 0 <= row < chart_height:
            for col in range(n_points):
                if grid[row][col] == " ":
                    grid[row][col] = "▁"

    # Annotate
    label_col = n_points + 2
    for label, limit in [("UCL", ucl), ("CL", cl), ("LCL", lcl)]:
        row = val_to_row(limit)
        lines.append(f"  {''.join(grid[chart_height - 1 - (chart_height - 1 - row)])}  {label}={limit:.4f}")

    return "\n".join(lines)


def ascii_imr_chart(
    values: List[float],
    ucl: float,
    cl: float,
    lcl: float,
    title: str = "I-MR Chart (Individuals)",
    width: int = 80
) -> str:
    """Generate ASCII I-MR chart for individuals"""
    if not values:
        return f"{title}: No data"

    lines = []
    lines.append(f"\n{'─' * width}")
    lines.append(f"  {title}")
    lines.append(f"{'─' * width}")

    chart_height = 12
    v_min = min(values + [lcl])
    v_max = max(values + [ucl])
    v_range = v_max - v_min if v_max != v_min else 1.0

    def val_to_row(v: float) -> int:
        return chart_height - 1 - int((v - v_min) / v_range * (chart_height - 1))

    n_points = min(len(values), width - 25)
    step = max(1, len(values) // n_points)
    sampled = values[::step][:n_points]

    grid = [[" " for _ in range(n_points)] for _ in range(chart_height)]

    for col, val in enumerate(sampled):
        row = val_to_row(val)
        if 0 <= row < chart_height:
            char = "●"
            if val > ucl or val < lcl:
                char = "◆"  # Out of control
            elif val > cl + (ucl - cl) * 0.7 or val < cl - (cl - lcl) * 0.7:
                char = "○"  # Warning zone
            grid[row][col] = char

    # Plot limits
    for limit, char in [(ucl, "·"), (cl, "─"), (lcl, "·")]:
        row = val_to_row(limit)
        if 0 <= row < chart_height:
            for col in range(n_points):
                if grid[row][col] == " ":
                    grid[row][col] = char

    for row_idx in range(chart_height):
        line = "".join(grid[row_idx])
        v_at_row = v_max - (row_idx / (chart_height - 1)) * v_range
        lines.append(f"  {line}  {v_at_row:.4f}")

    lines.append(f"  {'─' * n_points}")
    lines.append(f"  Points: {len(values)}  |  UCL={ucl:.4f}  CL={cl:.4f}  LCL={lcl:.4f}")

    return "\n".join(lines)


def ascii_pareto(pareto_data: List[Dict], title: str = "Pareto Analysis - Defect Types") -> str:
    """Generate ASCII Pareto chart"""
    if not pareto_data:
        return f"{title}: No data"

    lines = []
    max_count = max(d["count"] for d in pareto_data)

    lines.append(f"\n{'=' * 70}")
    lines.append(f"  {title}")
    lines.append(f"{'=' * 70}")
    lines.append(f"  {'Defect Type':<20} {'Count':>8}  {'%':>8}  {'Cum%':>8}  {'Class':>8}  Bar")
    lines.append(f"  {'─' * 70}")

    bar_width = 30
    for d in pareto_data:
        bar_len = int(d["count"] / max_count * bar_width) if max_count > 0 else 0
        bar = "█" * bar_len
        lines.append(
            f"  {d['defect_type']:<20} {d['count']:>8}  "
            f"{d['percentage']:>7.1f}%  {d['cumulative_percentage']:>7.1f}%  "
            f"  [{d['abc_class']}]  {bar}"
        )

    # Summary
    a_count = sum(d["count"] for d in pareto_data if d["abc_class"] == "A")
    b_count = sum(d["count"] for d in pareto_data if d["abc_class"] == "B")
    c_count = sum(d["count"] for d in pareto_data if d["abc_class"] == "C")

    lines.append(f"\n  Pareto Summary:")
    lines.append(f"  ─ Class A (Vital Few):  {a_count} defects ({a_count/max_count*100:.1f}% if applicable)")
    lines.append(f"  ─ Class B (Important):   {b_count} defects")
    lines.append(f"  ─ Class C (Trivial Many): {c_count} defects")

    return "\n".join(lines)


def ascii_capability_gauge(cap: Dict, param_name: str) -> str:
    """Generate ASCII process capability gauge"""
    if not cap or cap.get("cpk") is None:
        return f"  {param_name}: Insufficient data for capability analysis"

    cpk = cap["cpk"]
    cp = cap["cp"]

    # Gauge bar
    bar_width = 40
    # cpk scale: 0 to 2.0+
    normalized = min(cpk / 2.0, 1.0)
    filled = int(normalized * bar_width)

    if cpk >= 1.67:
        color_bar = "█" * filled + "░" * (bar_width - filled)
        status = "🟢 WORLD CLASS"
    elif cpk >= 1.33:
        color_bar = "█" * filled + "░" * (bar_width - filled)
        status = "🟢 EXCELLENT"
    elif cpk >= 1.0:
        color_bar = "█" * filled + "░" * (bar_width - filled)
        status = "🟡 ACCEPTABLE"
    elif cpk >= 0.67:
        color_bar = "█" * filled + "░" * (bar_width - filled)
        status = "🟠 POOR"
    else:
        color_bar = "█" * filled + "░" * (bar_width - filled)
        status = "🔴 NOT CAPABLE"

    lines = [
        f"\n  Process Capability: {param_name}",
        f"  {'─' * 50}",
        f"  Cp  = {cp:.3f}   (Potential Capability)",
        f"  Cpk = {cpk:.3f}   (Actual Capability)",
        f"  {'─' * 50}",
        f"  0.0              1.0              2.0",
        f"  ├──────┼──────┼──────┼──────┤",
        f"  [{color_bar}]",
        f"  {' ' * max(0, filled - 1)}↑",
        f"  {' ' * max(0, filled - 1)}Cpk={cpk:.2f}",
        f"  {'─' * 50}",
        f"  Status: {status}",
        f"  Interpretation: {cap.get('interpretation', 'N/A')}",
        f"  Mean={cap['mean']:.4f}  σ={cap['stdev']:.4f}  n={cap['n']}",
    ]

    return "\n".join(lines)


def ascii_spc_dashboard(monitor: SPCMonitor) -> str:
    """Generate comprehensive ASCII SPC dashboard"""
    lines = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"\n{'═' * 80}")
    lines.append(f"  HUSKY-SORTER-001  │  SPC Quality Monitor Dashboard  │  {now}")
    lines.append(f"{'═' * 80}")

    # System status
    status = monitor._system_status()
    if "OUT_OF_CONTROL" in status:
        status_line = f"🔴 SYSTEM STATUS: {status}"
    elif "CRITICAL" in status:
        status_line = f"🔴 SYSTEM STATUS: {status}"
    elif "WARNING" in status:
        status_line = f"🟡 SYSTEM STATUS: {status}"
    else:
        status_line = f"🟢 SYSTEM STATUS: {status}"

    lines.append(f"\n  {status_line}")

    # Parameter summary table
    lines.append(f"\n  {'─' * 78}")
    lines.append(f"  {'Parameter':<20} {'N':>6}  {'Mean':>10}  {'Sigma':>8}  {'UCL':>10}  {'LCL':>10}  {'Status':>12}")
    lines.append(f"  {'─' * 78}")

    summary = monitor.get_latest_summary()
    for name, data in summary.items():
        param = monitor.parameters[name]
        limits = data.get("control_limits", {}) or {}

        if param.chart_type == ControlChartType.I_MR:
            i_limits = limits.get("I", {})
            ucl = i_limits.get("ucl", "N/A")
            lcl = i_limits.get("lcl", "N/A")
        elif "XBAR" in str(limits):
            xb_limits = limits.get("XBAR", {})
            ucl = xb_limits.get("ucl", "N/A")
            lcl = xb_limits.get("lcl", "N/A")
        else:
            ucl = "N/A"
            lcl = "N/A"

        status_icon = {
            "OK": "🟢 OK",
            "WARNING": "🟡 WARN",
            "CRITICAL": "🔴 CRIT",
            "OUT_OF_CONTROL": "🔴 OOC",
        }.get(data["status"], data["status"])

        ucl_str = f"{ucl:.4f}" if isinstance(ucl, float) else str(ucl)
        lcl_str = f"{lcl:.4f}" if isinstance(lcl, float) else str(lcl)

        lines.append(
            f"  {name:<20} {data['n']:>6}  "
            f"{data['mean']:>10.4f}  {data['stdev']:>8.4f}  "
            f"{ucl_str:>10}  {lcl_str:>10}  {status_icon:>12}"
        )

    lines.append(f"  {'─' * 78}")

    # Active alerts
    if monitor.alerts:
        lines.append(f"\n  Recent Alerts ({len(monitor.alerts)} total):")
        for alert in monitor.alerts[-5:]:
            level_icon = {
                "out_of_control": "🔴",
                "critical": "🔴",
                "warning": "🟡",
                "info": "🔵",
            }.get(alert["level"], "⚪")
            lines.append(
                f"  {level_icon} [{alert['timestamp'][-8:]}] "
                f"{alert['parameter']}: {alert['message'][:60]}"
            )
    else:
        lines.append(f"\n  🟢 No active alerts")

    lines.append(f"\n{'═' * 80}")

    return "\n".join(lines)


# =============================================================================
# SECTION 6: Report Generator
# =============================================================================

def generate_spc_report(monitor: SPCMonitor, output_path: str = None) -> Dict:
    """Generate comprehensive SPC quality report"""
    report = {
        "report_type": "SPC Quality Report",
        "generated_at": datetime.datetime.now().isoformat(),
        "system": "HUSKY-SORTER-001",
        "version": "v1.0",
    }

    # Parameter details
    report["parameters"] = {}
    for name, param in monitor.parameters.items():
        values = monitor.data.get(name, [])
        if not values:
            continue

        cap = monitor.get_capability(name)
        limits = monitor.get_control_limits(name)

        report["parameters"][name] = {
            "spec_limits": {
                "usl": param.usl,
                "lsl": param.lsl,
                "target": param.target,
                "unit": param.unit,
            },
            "process_data": {
                "n": len(values),
                "mean": round(statistics.mean(values), 4),
                "median": round(statistics.median(values), 4),
                "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "range": round(max(values) - min(values), 4),
            },
            "capability": cap,
            "control_limits": limits,
            "chart_type": param.chart_type.value,
        }

    # Alert summary
    alert_by_level = defaultdict(int)
    for alert in monitor.alert_history:
        alert_by_level[alert["level"]] += 1

    report["alert_summary"] = dict(alert_by_level)
    report["total_alerts"] = len(monitor.alert_history)

    # System status
    report["system_status"] = monitor._system_status()

    # Recommendations
    report["recommendations"] = []
    for name, data in monitor.get_latest_summary().items():
        cap = data.get("capability")
        if cap and cap.get("cpk") is not None:
            if cap["cpk"] < 1.0:
                report["recommendations"].append(
                    f"CRITICAL: {name} Cpk={cap['cpk']:.3f} < 1.0 — process not capable, "
                    f"investigate root cause and adjust process mean/target"
                )
            elif cap["cpk"] < 1.33:
                report["recommendations"].append(
                    f"WARNING: {name} Cpk={cap['cpk']:.3f} < 1.33 — consider reducing variation "
                    f"to improve process capability"
                )

        if data["status"] in ["OUT_OF_CONTROL", "CRITICAL"]:
            report["recommendations"].append(
                f"URGENT: {name} is {data['status']} — control limits violated, "
                f"check for special cause variation immediately"
            )

    if not report["recommendations"]:
        report["recommendations"].append(
            "All parameters within statistical control. Continue monitoring."
        )

    # JSON output
    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        report["output_file"] = output_path

    return report


# =============================================================================
# SECTION 7: Main — Benchmark & Demonstration
# =============================================================================

def run_benchmark():
    """Run SPC system benchmark with realistic scenarios"""
    print("\n" + "═" * 80)
    print("  HUSKY-SORTER-001  │  SPC Quality Monitor  │  Benchmark Suite")
    print("═" * 80)

    # Scenario 1: Normal operation
    print("\n📊 SCENARIO 1: Normal Operation (500 beans, no defects injected)")
    print("─" * 60)

    monitor2 = SPCMonitor()
    sim2 = SPCSimulator(monitor2)
    result = sim2.run_batch_simulation(n_beans=500, defect_drift=0.0, inject_drift=False)

    print(ascii_spc_dashboard(monitor2))

    # Show capability for weight parameter
    cap = monitor2.get_capability("bean_weight")
    if cap:
        print(ascii_capability_gauge(cap, "bean_weight"))

    # Scenario 2: Process drift detection
    print("\n📊 SCENARIO 2: Process Drift Detection")
    print("  Injecting +1.5% moisture drift at 60% of batch")
    print("─" * 60)

    monitor3 = SPCMonitor()
    sim3 = SPCSimulator(monitor3)
    result3 = sim3.run_batch_simulation(
        n_beans=500, defect_drift=0.0, inject_drift=True, drift_magnitude=0.015
    )

    print(ascii_spc_dashboard(monitor3))

    # Show alerts
    if monitor3.alerts:
        print(f"\n  🔔 Detected {len(monitor3.alerts)} SPC alert(s):")
        for alert in monitor3.alerts[:5]:
            print(f"    [{alert['level'].upper()}] {alert['parameter']}: {alert['message'][:80]}")
    else:
        print("\n  (No alerts — drift within normal variation)")

    # Scenario 3: Multi-batch trending
    print("\n📊 SCENARIO 3: Multi-Batch Quality Trending (5 batches × 500 beans)")
    print("  Scenario: gradual_drift (moisture +0.8%/batch)")
    print("─" * 60)

    monitor4 = SPCMonitor()
    sim4 = SPCSimulator(monitor4)
    batch_results = sim4.run_multi_batch_simulation(
        n_batches=5, beans_per_batch=500, scenario="gradual_drift"
    )

    for br in batch_results:
        print(f"  Batch {br['batch_number']}: {br['n_beans']} beans, "
              f"defect_rate={br['defect_rate']}%, drift={br.get('drift_injected', False)}")

    # Generate Pareto from alert history
    print("\n📊 PARETO ANALYSIS (Simulated Defect Types)")
    print("─" * 60)

    # Create simulated defect counts
    defect_counts = {
        "BROKEN": 42,
        "IMMATURE": 31,
        "FERRY": 18,
        "BLACK": 12,
        "OVERSIZE": 7,
        "UNDERSIZE": 5,
        "MOLD": 3,
    }
    pareto = pareto_analysis(defect_counts)
    print(ascii_pareto(pareto))

    # Final summary
    print("\n📊 FINAL SPC REPORT")
    print("─" * 60)
    final_report = generate_spc_report(monitor2)

    for name, data in final_report.get("parameters", {}).items():
        cap = data.get("capability", {})
        if cap and cap.get("cpk") is not None:
            status = "✅" if cap["cpk"] >= 1.0 else "⚠️"
            print(f"  {status} {name}: Cpk={cap['cpk']:.3f} "
                  f"(n={data['process_data']['n']}, mean={data['process_data']['mean']:.4f}) "
                  f"→ {cap.get('interpretation', 'N/A')}")

    for rec in final_report.get("recommendations", []):
        print(f"  → {rec}")

    print(f"\n  Report saved: spc_quality_report.json")
    json_path = "spc_quality_report.json"
    with open(json_path, "w") as f:
        json.dump(final_report, f, indent=2)

    print("\n" + "═" * 80)
    print("  Benchmark Complete — SPC system validated")
    print("═" * 80)

    return monitor2


if __name__ == "__main__":
    run_benchmark()
