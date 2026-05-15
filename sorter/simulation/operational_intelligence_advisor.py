#!/usr/bin/env python3
"""
HUSKY-SORTER-001 运营智能顾问系统 v1.0
Unified Operational Intelligence Advisory System

目标：在硬件到位前建立完整的运营智能分析能力，整合健康监控/SPC/预测性维护数据，
为操作员提供基于多数据源的统一行动建议（而非分散的单独告警）。

文件：sorter/simulation/operational_intelligence_advisor.py
版本：v1.0 | 2026-05-15
依赖：health_monitor.py / spc_quality_monitor.py / predictive_maintenance_analysis.py
"""

import sys
import os
import json
import math
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum, auto

# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

class AdvisorySeverity(Enum):
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    INFO = auto()

class AdvisoryCategory(Enum):
    HEALTH = auto()
    SPC = auto()
    MAINTENANCE = auto()
    QUALITY = auto()
    THROUGHPUT = auto()
    CALIBRATION = auto()
    SAFETY = auto()
    SYSTEM = auto()

class RecommendationUrgency(Enum):
    IMMEDIATE = auto()
    TODAY = auto()
    THIS_WEEK = auto()
    NEXT_CYCLE = auto()
    SCHEDULED = auto()
    MONITOR = auto()

@dataclass
class AdvisoryEntry:
    id: str
    severity: AdvisorySeverity
    category: AdvisoryCategory
    title: str
    description: str
    root_cause: str
    recommendation: str
    urgency: RecommendationUrgency
    affected_component: str
    estimated_downtime_min: int = 0
    risk_score: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    linked_advisories: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['severity'] = self.severity.name
        d['category'] = self.category.name
        d['urgency'] = self.urgency.name
        return d

@dataclass
class ComponentHealthSummary:
    component: str
    health_score: float
    trend: str
    days_since_calibration: int
    mtbf_hours: float
    failure_probability_7d: float
    avg_error_rate: float
    last_maintenance: Optional[str] = None

@dataclass
class SPCSummary:
    parameter: str
    cpk: float
    cpk_status: str
    trend: str
    rule_violations: int
    out_of_spec_count: int

@dataclass
class SystemScore:
    overall: float
    health: float
    spc: float
    quality: float
    throughput: float
    maintenance: float

# ─────────────────────────────────────────────────────────────────────────────
# Simulated Data Generators
# ─────────────────────────────────────────────────────────────────────────────

def generate_mock_health_data() -> Dict[str, ComponentHealthSummary]:
    components = [
        ("HX711_LoadCell", 87.3, "stable", 12, 8760, 0.02, 0.008),
        ("AD7746_Moisture", 91.2, "degrading", 8, 7200, 0.03, 0.005),
        ("IMX477_TopCamera", 95.8, "stable", 15, 10800, 0.01, 0.003),
        ("USB_BottomCamera", 82.4, "degrading", 21, 8640, 0.05, 0.012),
        ("Nema17_Feeder", 89.1, "stable", 10, 12000, 0.02, 0.007),
        ("HX711_Weighing", 76.5, "degrading", 30, 8760, 0.08, 0.015),
        ("AirJetValve", 93.7, "stable", 5, 4320, 0.04, 0.006),
        ("DensityFan", 84.2, "stable", 14, 7200, 0.06, 0.009),
        ("BufferDistributor", 96.3, "improving", 3, 14400, 0.01, 0.002),
        ("MQTT_Broker", 99.1, "stable", 0, 87600, 0.001, 0.0001),
    ]
    return {
        name: ComponentHealthSummary(
            component=name, health_score=score, trend=trend,
            days_since_calibration=days, mtbf_hours=mtbf,
            failure_probability_7d=fprob, avg_error_rate=err_rate,
            last_maintenance=f"2026-05-{random.randint(1,14):02d}"
        )
        for name, score, trend, days, mtbf, fprob, err_rate in components
    }

def generate_mock_spc_data() -> Dict[str, SPCSummary]:
    spc_params = [
        ("bean_weight", 1.914, "world_class", "stable", 0, 0),
        ("moisture_content", 0.723, "acceptable", "degrading", 2, 1),
        ("color_score", 1.456, "excellent", "stable", 1, 0),
        ("density", 0.689, "poor", "degrading", 3, 2),
        ("defect_rate", 1.203, "excellent", "stable", 0, 0),
    ]
    return {
        param: SPCSummary(
            parameter=param, cpk=cpk, cpk_status=status,
            trend=trend, rule_violations=violations, out_of_spec_count=oos
        )
        for param, cpk, status, trend, violations, oos in spc_params
    }

# ─────────────────────────────────────────────────────────────────────────────
# Advisory Rule Engine
# ─────────────────────────────────────────────────────────────────────────────

class AdvisoryRuleEngine:
    def __init__(self, health_data, spc_data, quality_metrics):
        self.health_data = health_data
        self.spc_data = spc_data
        self.quality_metrics = quality_metrics
        self.advisories: List[AdvisoryEntry] = []
        self._run_rules()

    def _run_rules(self):
        self._check_health_rules()
        self._check_spc_rules()
        self._check_quality_rules()
        self._check_calibration_rules()
        self._check_throughput_rules()
        self._check_safety_rules()
        self._prioritize_advisories()

    def _check_health_rules(self):
        for name, h in self.health_data.items():
            if h.health_score < 70:
                self.advisories.append(AdvisoryEntry(
                    id=f"H1_{name}", severity=AdvisorySeverity.HIGH,
                    category=AdvisoryCategory.HEALTH,
                    title=f"{name} 健康评分过低",
                    description=f"组件健康评分 {h.health_score:.1f}/100，趋势{h.trend}。"
                                f"7天内故障概率 {h.failure_probability_7d*100:.1f}%",
                    root_cause=f"组件{name}可能出现降级或需要维护",
                    recommendation=f"建议立即检查{name}，或安排今天内更换/维修。"
                                   f"平均错误率{h.avg_error_rate:.3f}，上次维护{h.last_maintenance}",
                    urgency=RecommendationUrgency.TODAY, affected_component=name,
                    risk_score=h.health_score,
                    evidence={"health_score": h.health_score, "trend": h.trend,
                              "failure_prob_7d": h.failure_probability_7d}
                ))

            if h.trend == "degrading" and h.days_since_calibration > 20:
                self.advisories.append(AdvisoryEntry(
                    id=f"H2_{name}", severity=AdvisorySeverity.MEDIUM,
                    category=AdvisoryCategory.HEALTH,
                    title=f"{name} 性能下降趋势",
                    description=f"组件性能持续下降（{h.trend}），距离上次标定已{h.days_since_calibration}天",
                    root_cause="组件漂移超出可接受范围，可能需要重新标定",
                    recommendation=f"建议本周内对{name}进行重新标定",
                    urgency=RecommendationUrgency.THIS_WEEK, affected_component=name,
                    risk_score=50 + (100 - h.health_score) * 0.5,
                    evidence={"days_since_cal": h.days_since_calibration, "trend": h.trend}
                ))

            if h.failure_probability_7d > 0.05:
                self.advisories.append(AdvisoryEntry(
                    id=f"H3_{name}", severity=AdvisorySeverity.HIGH,
                    category=AdvisoryCategory.MAINTENANCE,
                    title=f"{name} 高故障风险预警",
                    description=f"7天内故障概率 {h.failure_probability_7d*100:.1f}% (MTBF {h.mtbf_hours}h)",
                    root_cause=f"基于MTBF和历史错误率分析，{name}接近使用寿命",
                    recommendation=f"建议备件准备{name}，下周维护时更换",
                    urgency=RecommendationUrgency.THIS_WEEK, affected_component=name,
                    estimated_downtime_min=30,
                    risk_score=h.failure_probability_7d * 1000,
                    evidence={"mtbf_hours": h.mtbf_hours, "failure_prob": h.failure_probability_7d}
                ))

    def _check_spc_rules(self):
        for param, spc in self.spc_data.items():
            if spc.cpk < 1.0:
                self.advisories.append(AdvisoryEntry(
                    id=f"S1_{param}", severity=AdvisorySeverity.HIGH,
                    category=AdvisoryCategory.SPC,
                    title=f"{param} 过程能力不足",
                    description=f"Cpk={spc.cpk:.3f}（{spc.cpk_status}），趋势{spc.trend}。"
                                f"规则违规{spc.rule_violations}次，超规格{spc.out_of_spec_count}次",
                    root_cause="过程漂移超出控制限，需要调整工艺参数或检查设备",
                    recommendation=f"检查{param}传感器标定，考虑调整控制限或工艺设置。"
                                   f"SPC规则{spc.rule_violations}次违规需立即调查",
                    urgency=RecommendationUrgency.TODAY, affected_component=param,
                    risk_score=max(0, (1.0 - spc.cpk) * 100),
                    evidence={"cpk": spc.cpk, "cpk_status": spc.cpk_status,
                              "rule_violations": spc.rule_violations}
                ))

            if spc.trend == "degrading" and spc.rule_violations > 0:
                self.advisories.append(AdvisoryEntry(
                    id=f"S2_{param}", severity=AdvisorySeverity.MEDIUM,
                    category=AdvisoryCategory.SPC,
                    title=f"{param} SPC趋势恶化",
                    description=f"{param}的Cpk趋势{spc.trend}，已有{spc.rule_violations}条规则违规",
                    root_cause="过程参数正在向不利方向漂移",
                    recommendation=f"建议本周内调查{param}漂移原因（传感器/工艺/环境）",
                    urgency=RecommendationUrgency.THIS_WEEK, affected_component=param,
                    risk_score=60 + spc.rule_violations * 5,
                    evidence={"trend": spc.trend, "rule_violations": spc.rule_violations}
                ))

    def _check_quality_rules(self):
        defect_rate = self.quality_metrics.get("defect_rate_pct", 0)
        grade_a_pct = self.quality_metrics.get("grade_a_pct", 0)

        if defect_rate > 5.0:
            self.advisories.append(AdvisoryEntry(
                id="Q1_defect_rate", severity=AdvisorySeverity.CRITICAL,
                category=AdvisoryCategory.QUALITY,
                title="缺陷率严重超标",
                description=f"当前缺陷率 {defect_rate:.2f}%（目标 <2%），超出阈值 150%",
                root_cause="缺陷豆比例过高，可能是颜色检测阈值设置不当或传感器漂移",
                recommendation="立即停止生产检查颜色检测系统，重新标定双摄阈值",
                urgency=RecommendationUrgency.IMMEDIATE, affected_component="ColorCamera",
                risk_score=defect_rate * 20,
                evidence={"defect_rate": defect_rate}
            ))
        elif defect_rate > 2.0:
            self.advisories.append(AdvisoryEntry(
                id="Q2_defect_rate", severity=AdvisorySeverity.HIGH,
                category=AdvisoryCategory.QUALITY,
                title="缺陷率轻度超标",
                description=f"缺陷率 {defect_rate:.2f}%（目标 <2%）",
                root_cause="缺陷率轻微超标，需关注",
                recommendation="今天内检查颜色检测阈值，适当收紧",
                urgency=RecommendationUrgency.TODAY, affected_component="ColorCamera",
                risk_score=defect_rate * 10,
                evidence={"defect_rate": defect_rate}
            ))

        if grade_a_pct < 80 and defect_rate < 2.0:
            self.advisories.append(AdvisoryEntry(
                id="Q3_grade_a", severity=AdvisorySeverity.MEDIUM,
                category=AdvisoryCategory.QUALITY,
                title="A级率偏低",
                description=f"A级率 {grade_a_pct:.1f}%（目标 >=85%）",
                root_cause="可能是密度分选或含水率阈值设置过严",
                recommendation="检查密度分选参数和含水率阈值，适当放宽",
                urgency=RecommendationUrgency.THIS_WEEK, affected_component="DensitySorter",
                risk_score=(85 - grade_a_pct) * 2,
                evidence={"grade_a_pct": grade_a_pct}
            ))

    def _check_calibration_rules(self):
        for name, h in self.health_data.items():
            if h.days_since_calibration > 30:
                self.advisories.append(AdvisoryEntry(
                    id=f"C1_{name}", severity=AdvisorySeverity.MEDIUM,
                    category=AdvisoryCategory.CALIBRATION,
                    title=f"{name} 标定过期",
                    description=f"{name}距离上次标定已{h.days_since_calibration}天（建议30天内）",
                    root_cause="标定证书过期，继续使用可能影响测量精度",
                    recommendation=f"下周维护时对{name}进行重新标定",
                    urgency=RecommendationUrgency.SCHEDULED, affected_component=name,
                    risk_score=h.days_since_calibration,
                    evidence={"days_since_cal": h.days_since_calibration}
                ))

            if h.days_since_calibration > 60:
                self.advisories.append(AdvisoryEntry(
                    id=f"C2_{name}", severity=AdvisorySeverity.HIGH,
                    category=AdvisoryCategory.CALIBRATION,
                    title=f"{name} 标定严重过期",
                    description=f"{name}标定已超过60天！",
                    root_cause="标定严重过期，测量数据可能不可靠",
                    recommendation="立即安排标定，暂停使用该传感器数据进行质量判断",
                    urgency=RecommendationUrgency.TODAY, affected_component=name,
                    risk_score=h.days_since_calibration * 2,
                    evidence={"days_since_cal": h.days_since_calibration}
                ))

    def _check_throughput_rules(self):
        current_throughput = self.quality_metrics.get("throughput_kg_h", 0)
        target = 2.0

        if current_throughput < target * 0.8:
            gap = target - current_throughput
            self.advisories.append(AdvisoryEntry(
                id="T1_throughput", severity=AdvisorySeverity.HIGH,
                category=AdvisoryCategory.THROUGHPUT,
                title="吞吐量严重不足",
                description=f"当前吞吐量 {current_throughput:.2f} kg/h（目标 {target} kg/h），差距 {gap:.2f} kg/h",
                root_cause="振动给料器速率不足（单通道~30bpm瓶颈）或分选机构堵塞",
                recommendation="检查振动给料器频率设置，检查机械通道是否有堵塞，考虑3通道并行升级",
                urgency=RecommendationUrgency.TODAY, affected_component="VibratingFeeder",
                risk_score=gap / target * 100,
                evidence={"current": current_throughput, "target": target}
            ))
        elif current_throughput < target:
            self.advisories.append(AdvisoryEntry(
                id="T2_throughput", severity=AdvisorySeverity.MEDIUM,
                category=AdvisoryCategory.THROUGHPUT,
                title="吞吐量略低于目标",
                description=f"当前 {current_throughput:.2f} kg/h vs 目标 {target} kg/h",
                root_cause="部分通道未达到50bpm设计目标",
                recommendation="调整振动给料器PWM，检查皮带张力，考虑Nema17升级",
                urgency=RecommendationUrgency.NEXT_CYCLE, affected_component="VibratingFeeder",
                risk_score=(target - current_throughput) / target * 50,
                evidence={"current": current_throughput, "target": target}
            ))

    def _check_safety_rules(self):
        for name, h in self.health_data.items():
            if "AirJetValve" in name and h.health_score < 85:
                self.advisories.append(AdvisoryEntry(
                    id="SF1_air_valve", severity=AdvisorySeverity.HIGH,
                    category=AdvisoryCategory.SAFETY,
                    title="气喷阀性能下降",
                    description=f"气喷阀健康评分 {h.health_score}/100，响应时间可能超时",
                    root_cause="电磁阀可能存在响应延迟，影响缺陷豆剔除的时效性",
                    recommendation="检查气喷时序和气压传感器，今天内完成功能测试",
                    urgency=RecommendationUrgency.TODAY, affected_component="AirJetValve",
                    estimated_downtime_min=15,
                    risk_score=80 + (100 - h.health_score),
                    evidence={"health_score": h.health_score}
                ))

    def _prioritize_advisories(self):
        def sort_key(a: AdvisoryEntry):
            severity_weight = {
                AdvisorySeverity.CRITICAL: 1000,
                AdvisorySeverity.HIGH: 100,
                AdvisorySeverity.MEDIUM: 10,
                AdvisorySeverity.LOW: 1,
                AdvisorySeverity.INFO: 0
            }.get(a.severity, 0)
            return severity_weight * 1000 + a.risk_score

        self.advisories.sort(key=sort_key, reverse=True)

    def get_advisories(self) -> List[AdvisoryEntry]:
        return self.advisories

    def get_summary(self) -> dict:
        return {
            "total": len(self.advisories),
            "critical": len([a for a in self.advisories if a.severity == AdvisorySeverity.CRITICAL]),
            "high": len([a for a in self.advisories if a.severity == AdvisorySeverity.HIGH]),
            "medium": len([a for a in self.advisories if a.severity == AdvisorySeverity.MEDIUM]),
            "low": len([a for a in self.advisories if a.severity == AdvisorySeverity.LOW]),
            "info": len([a for a in self.advisories if a.severity == AdvisorySeverity.INFO]),
        }

# ─────────────────────────────────────────────────────────────────────────────
# System Score Calculator
# ─────────────────────────────────────────────────────────────────────────────

def calculate_system_score(health_data, spc_data, quality_metrics) -> SystemScore:
    health_scores = [h.health_score for h in health_data.values()]
    health_avg = sum(health_scores) / len(health_scores) if health_scores else 0

    cpk_scores = []
    for spc in spc_data.values():
        if spc.cpk_status == "world_class":
            cpk_scores.append(100)
        elif spc.cpk_status == "excellent":
            cpk_scores.append(85)
        elif spc.cpk_status == "acceptable":
            cpk_scores.append(65)
        elif spc.cpk_status == "poor":
            cpk_scores.append(40)
        else:
            cpk_scores.append(10)
    spc_avg = sum(cpk_scores) / len(cpk_scores) if cpk_scores else 0

    defect_rate = quality_metrics.get("defect_rate_pct", 0)
    grade_a_pct = quality_metrics.get("grade_a_pct", 0)
    if defect_rate > 5:
        quality = 20
    elif defect_rate > 2:
        quality = 60
    else:
        quality = 100 - (defect_rate * 5) - max(0, (85 - grade_a_pct))
    quality = max(0, min(100, quality))

    throughput = quality_metrics.get("throughput_kg_h", 0)
    throughput_score = min(100, (throughput / 2.0) * 100)

    maintenance_scores = []
    for h in health_data.values():
        score = 100 - (h.days_since_calibration / 60 * 50) - (h.failure_probability_7d * 500)
        maintenance_scores.append(max(0, min(100, score)))
    maintenance_avg = sum(maintenance_scores) / len(maintenance_scores) if maintenance_scores else 0

    weighted = (
        health_avg * 0.25 + spc_avg * 0.20 + quality * 0.25 +
        throughput_score * 0.15 + maintenance_avg * 0.15
    )

    return SystemScore(
        overall=weighted, health=health_avg, spc=spc_avg,
        quality=quality, throughput=throughput_score, maintenance=maintenance_avg
    )

# ─────────────────────────────────────────────────────────────────────────────
# ASCII Visualization
# ─────────────────────────────────────────────────────────────────────────────

def score_bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    if score >= 90:
        color = "\033[92m"
    elif score >= 70:
        color = "\033[93m"
    else:
        color = "\033[91m"
    reset = "\033[0m"
    return f"{color}{'█' * filled}{'░' * empty}{reset}"

def severity_icon(severity: AdvisorySeverity) -> str:
    return {
        AdvisorySeverity.CRITICAL: "🔴",
        AdvisorySeverity.HIGH: "🟠",
        AdvisorySeverity.MEDIUM: "🟡",
        AdvisorySeverity.LOW: "🟢",
        AdvisorySeverity.INFO: "⚪"
    }.get(severity, "⚪")

def format_advisory_report(advisories, system_score, health_data, spc_data) -> str:
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"{'═' * 76}")
    lines.append(f"{'HUSKY-SORTER-001 运营智能顾问报告':^76}")
    lines.append(f"{'生成时间: ' + now:^76}")
    lines.append(f"{'═' * 76}")

    lines.append(f"\n{'系统综合评分':─^76}")
    lines.append(f"  Overall Score    {score_bar(system_score.overall)} {system_score.overall:.1f}/100")
    lines.append(f"  ├─ Health        {score_bar(system_score.health)} {system_score.health:.1f}/100")
    lines.append(f"  ├─ SPC           {score_bar(system_score.spc)} {system_score.spc:.1f}/100")
    lines.append(f"  ├─ Quality       {score_bar(system_score.quality)} {system_score.quality:.1f}/100")
    lines.append(f"  ├─ Throughput    {score_bar(system_score.throughput)} {system_score.throughput:.1f}/100")
    lines.append(f"  └─ Maintenance   {score_bar(system_score.maintenance)} {system_score.maintenance:.1f}/100")

    summary = {
        "CRITICAL": sum(1 for a in advisories if a.severity == AdvisorySeverity.CRITICAL),
        "HIGH": sum(1 for a in advisories if a.severity == AdvisorySeverity.HIGH),
        "MEDIUM": sum(1 for a in advisories if a.severity == AdvisorySeverity.MEDIUM),
        "LOW": sum(1 for a in advisories if a.severity == AdvisorySeverity.LOW),
        "INFO": sum(1 for a in advisories if a.severity == AdvisorySeverity.INFO),
    }
    lines.append(f"\n{'建议汇总':─^76}")
    lines.append(f"  🔴 CRITICAL: {summary['CRITICAL']:>3}  🟠 HIGH: {summary['HIGH']:>3}  "
                 f"🟡 MEDIUM: {summary['MEDIUM']:>3}  🟢 LOW: {summary['LOW']:>3}  ⚪ INFO: {summary['INFO']:>3}")

    priority = [a for a in advisories if a.severity in [AdvisorySeverity.CRITICAL, AdvisorySeverity.HIGH]]
    if priority:
        lines.append(f"\n{'🔴🟠 高优先级建议 (立即处理)':─^76}")
        for a in priority[:10]:
            lines.append(f"\n  {severity_icon(a.severity)} [{a.id}] {a.title}")
            lines.append(f"     📋 {a.description}")
            lines.append(f"     🔎 根因: {a.root_cause}")
            lines.append(f"     ✅ 建议: {a.recommendation}")
            lines.append(f"     ⏱️ 预计停机: {a.estimated_downtime_min}min | 风险评分: {a.risk_score:.1f}")

    medium = [a for a in advisories if a.severity == AdvisorySeverity.MEDIUM]
    if medium:
        lines.append(f"\n{'🟡 中优先级建议 (本周处理)':─^76}")
        for a in medium[:5]:
            lines.append(f"\n  🟡 [{a.id}] {a.title}")
            lines.append(f"     📋 {a.description}")
            lines.append(f"     ✅ {a.recommendation}")

    lines.append(f"\n{'组件健康状态 (Top 5 低分)':─^76}")
    lines.append(f"  {'Component':<25} {'Score':>8} {'Trend':>10} {'Cal Days':>10} {'Fail 7d':>10}")
    lines.append(f"  {'─' * 25} {'─' * 8} {'─' * 10} {'─' * 10} {'─' * 10}")
    sorted_health = sorted(health_data.values(), key=lambda x: x.health_score)[:5]
    for h in sorted_health:
        trend_emoji = "📈" if h.trend == "improving" else ("📉" if h.trend == "degrading" else "➡️")
        fail_pct = h.failure_probability_7d * 100
        sc = "\033[92m" if h.health_score >= 80 else ("\033[93m" if h.health_score >= 60 else "\033[91m")
        lines.append(f"  {sc}{h.component:<25} {h.health_score:>7.1f} {trend_emoji} {h.days_since_calibration:>9}d {fail_pct:>8.1f}%")

    lines.append(f"\n{'SPC 参数状态':─^76}")
    lines.append(f"  {'Parameter':<20} {'Cpk':>8} {'Status':>12} {'Trend':>10} {'Violations':>10}")
    lines.append(f"  {'─' * 20} {'─' * 8} {'─' * 12} {'─' * 10} {'─' * 10}")
    for spc in spc_data.values():
        sc = {"world_class": "\033[92m", "excellent": "\033[92m", "acceptable": "\033[93m",
              "poor": "\033[91m", "critical": "\033[91m"}.get(spc.cpk_status, "\033[0m")
        trend_icon = "📈" if spc.trend == "improving" else ("📉" if spc.trend == "degrading" else "➡️")
        lines.append(f"  {spc.parameter:<20} {spc.cpk:>8.3f} {sc}{spc.cpk_status:>12}\033[0m {trend_icon} {spc.rule_violations:>10}")

    lines.append(f"\n{'═' * 76}")
    lines.append(f"{'报告生成时间: ' + now + ' | 硬件预到位: ~2026-07-13':^76}")
    lines.append(f"{'═' * 76}")

    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class OperationalIntelligenceOrchestrator:
    def __init__(self):
        self.health_data: Dict[str, ComponentHealthSummary] = {}
        self.spc_data: Dict[str, SPCSummary] = {}
        self.quality_metrics: dict = {}
        self.advisories: List[AdvisoryEntry] = []
        self.system_score: Optional[SystemScore] = None
        self.timestamp = datetime.now()

    def collect_data(self):
        self.health_data = generate_mock_health_data()
        self.spc_data = generate_mock_spc_data()
        self.quality_metrics = {"defect_rate_pct": 1.8, "grade_a_pct": 88.7, "throughput_kg_h": 1.94}
        self.timestamp = datetime.now()

    def run_analysis(self) -> List[AdvisoryEntry]:
        self.collect_data()
        engine = AdvisoryRuleEngine(self.health_data, self.spc_data, self.quality_metrics)
        self.advisories = engine.get_advisories()
        self.system_score = calculate_system_score(self.health_data, self.spc_data, self.quality_metrics)
        return self.advisories

    def get_report(self) -> str:
        return format_advisory_report(self.advisories, self.system_score, self.health_data, self.spc_data)

    def generate_json_report(self, output_dir: str = "sorter/reports") -> dict:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_id = f"OIA-{timestamp}"

        report = {
            "report_id": report_id,
            "timestamp": self.timestamp.isoformat(),
            "system_score": asdict(self.system_score) if self.system_score else None,
            "advisory_summary": AdvisoryRuleEngine(self.health_data, self.spc_data, self.quality_metrics).get_summary(),
            "advisories": [a.to_dict() for a in self.advisories],
            "component_health": [asdict(h) for h in self.health_data.values()],
            "spc_summary": [asdict(s) for s in self.spc_data.values()],
            "quality_metrics": self.quality_metrics,
        }

        filepath = os.path.join(output_dir, f"operational_intelligence_report_{timestamp}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report

    def print_report(self):
        self.run_analysis()
        print(self.get_report())

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 运营智能顾问系统")
    parser.add_argument("--report", action="store_true", help="生成JSON报告")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    parser.add_argument("--summary", action="store_true", help="仅显示汇总")
    args = parser.parse_args()

    orchestrator = OperationalIntelligenceOrchestrator()

    if args.json:
        orchestrator.run_analysis()
        print(json.dumps(orchestrator.generate_json_report(), indent=2, ensure_ascii=False))
    elif args.summary:
        orchestrator.run_analysis()
        eng = AdvisoryRuleEngine(orchestrator.health_data, orchestrator.spc_data, orchestrator.quality_metrics)
        s = eng.get_summary()
        print(f"总建议数: {s['total']}  🔴{s['critical']} 🟠{s['high']} 🟡{s['medium']} 🟢{s['low']} ⚪{s['info']}")
    else:
        orchestrator.print_report()
        if args.report:
            result = orchestrator.generate_json_report()
            print(f"\nJSON报告已保存: operational_intelligence_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

if __name__ == "__main__":
    main()
