#!/usr/bin/env python3
"""
Batch Quality Tracker — sorter/production/batch_quality_tracker.py
===================================================================
实时批次质量追踪系统

Purpose:
  在硬件到位后用于生产运营；结合批次配方系统(qc_audit_system)提供
  批次级质量评分、趋势分析、预警管理。

  与 batch_recipe_manager.py → qc_audit_system 形成三级质量链路：
    Recipe (预设阈值) → Tracker (实时监控) → Audit (批次归档)

Author: Little Husky (他他) 🐕
Version: 1.0 — 2026-05-14
"""

import json
import random
import statistics
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────

class QualityTrend(Enum):
    """质量趋势"""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """告警级别"""
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class QualityMetrics:
    """单批次质量指标"""
    defect_rate_pct: float      # 缺陷率%
    color_score_avg: float       # 平均颜色分 0-100
    weight_avg_g: float          # 平均单粒重量 g
    moisture_avg_pct: float      # 平均含水率%
    density_score: float         # 密度评分 0-100
    size_conformance_pct: float # 尺寸合规率%
    throughput_kg_h: float      # 实际产能 kg/h

    def overall_score(self) -> float:
        """
        综合质量评分 0-100
        权重：缺陷率40%/颜色25%/重量15%/含水率10%/密度5%/尺寸5%
        """
        # 缺陷率评分 (缺陷率越低越好)
        if self.defect_rate_pct <= 0.5:
            defect_score = 100
        elif self.defect_rate_pct <= 1.0:
            defect_score = 90
        elif self.defect_rate_pct <= 2.0:
            defect_score = 75
        elif self.defect_rate_pct <= 3.0:
            defect_score = 60
        elif self.defect_rate_pct <= 5.0:
            defect_score = 40
        else:
            defect_score = max(0, 20 - self.defect_rate_pct * 2)

        color_score = self.color_score_avg  # 0-100 直接用
        weight_score = 100 - abs(self.weight_avg_g - 0.152) / 0.152 * 50  # 基准0.152g
        weight_score = max(0, min(100, weight_score))
        moisture_score = 100 - abs(self.moisture_avg_pct - 11.0) / 11.0 * 50  # 基准11%
        moisture_score = max(0, min(100, moisture_score))
        density_score = self.density_score
        size_score = self.size_conformance_pct

        total = (
            defect_score * 0.40 +
            color_score * 0.25 +
            weight_score * 0.15 +
            moisture_score * 0.10 +
            density_score * 0.05 +
            size_score * 0.05
        )
        return round(total, 1)

    def grade(self) -> str:
        """等级判定"""
        s = self.overall_score()
        if s >= 90:
            return "A"
        elif s >= 75:
            return "B"
        elif s >= 60:
            return "C"
        else:
            return "D"


@dataclass
class BatchState:
    """批次状态"""
    batch_id: str
    recipe_name: str
    start_time: datetime
    beans_processed: int = 0
    beans_rejected: int = 0
    total_weight_g: float = 0.0
    target_weight_g: float = 0.0

    # 滚动指标 (最近 N 粒)
    recent_defect_rates: list = field(default_factory=list)
    recent_color_scores: list = field(default_factory=list)
    recent_weights: list = field(default_factory=list)
    recent_moisture: list = field(default_factory=list)
    recent_densities: list = field(default_factory=list)

    end_time: Optional[datetime] = None
    status: str = "running"  # running / paused / completed / aborted

    WINDOW_SIZE: int = 100  # 滚动窗口大小

    def add_bean(self, is_defect: bool, weight_g: float, color_score: float,
                moisture_pct: float, density_score: float):
        self.beans_processed += 1
        if is_defect:
            self.beans_rejected += 1
        self.total_weight_g += weight_g

        # 滚动窗口更新
        self.recent_defect_rates.append(1.0 if is_defect else 0.0)
        self.recent_color_scores.append(color_score)
        self.recent_weights.append(weight_g)
        self.recent_moisture.append(moisture_pct)
        self.recent_densities.append(density_score)

        # 保持窗口大小
        for lst in [self.recent_defect_rates, self.recent_color_scores,
                    self.recent_weights, self.recent_moisture, self.recent_densities]:
            if len(lst) > self.WINDOW_SIZE:
                lst.pop(0)

    def current_metrics(self) -> QualityMetrics:
        """当前滚动质量指标"""
        n = len(self.recent_defect_rates)
        if n == 0:
            return QualityMetrics(
                defect_rate_pct=0, color_score_avg=0, weight_avg_g=0,
                moisture_avg_pct=0, density_score=0, size_conformance_pct=100,
                throughput_kg_h=0
            )

        defect_rate = sum(self.recent_defect_rates) / n * 100
        color_avg = statistics.mean(self.recent_color_scores)
        weight_avg = statistics.mean(self.recent_weights)
        moisture_avg = statistics.mean(self.recent_moisture)
        density_avg = statistics.mean(self.recent_densities)

        # 吞吐量计算
        elapsed_h = (datetime.now() - self.start_time).total_seconds() / 3600
        throughput = self.total_weight_g / 1000 / max(elapsed_h, 0.001)

        return QualityMetrics(
            defect_rate_pct=round(defect_rate, 3),
            color_score_avg=round(color_avg, 2),
            weight_avg_g=round(weight_avg, 4),
            moisture_avg_pct=round(moisture_avg, 2),
            density_score=round(density_avg, 1),
            size_conformance_pct=round(100 - defect_rate, 2),
            throughput_kg_h=round(throughput, 3)
        )

    def progress_pct(self) -> float:
        """批次完成进度%"""
        if self.target_weight_g <= 0:
            return 0.0
        return min(100, self.total_weight_g / self.target_weight_g * 100)


@dataclass
class QualityAlert:
    """质量告警"""
    timestamp: datetime
    level: AlertLevel
    message: str
    batch_id: str
    metric: str
    value: float
    threshold: float


# ─────────────────────────────────────────────
# Batch Quality Tracker
# ─────────────────────────────────────────────

class BatchQualityTracker:
    """
    实时批次质量追踪器

    使用方法:
        tracker = BatchQualityTracker()
        tracker.set_recipe("Ethiopian_Washed")
        tracker.start_batch("BATCH-2026-0514-001", target_g=2000)

        # 每收到一粒豆子:
        tracker.record_bean(is_defect=False, weight_g=0.148, color_score=88,
                           moisture_pct=11.2, density_score=92)

        tracker.get_current_status()  # 实时状态
        tracker.end_batch()          # 完成批次
    """

    def __init__(self, alert_callback=None):
        self.active_batch: Optional[BatchState] = None
        self.completed_batches: list[BatchState] = []
        self.alerts: list[QualityAlert] = []

        # 告警回调 (外部系统如 dashboard 订阅)
        self.alert_callback = alert_callback

        # 阈值配置
        self.THRESHOLDS = {
            "defect_rate_pct": {"warning": 2.0, "critical": 5.0},
            "color_score_avg": {"warning": 80.0, "critical": 70.0},
            "weight_avg_g": {"warning": 0.10, "critical": 0.08},   # 低阈值
            "moisture_avg_pct": {"warning": 0.8, "critical": 1.2}, # 偏离11%
        }

    def set_recipe(self, recipe_name: str):
        """设置当前配方 (用于验证批次是否符合配方要求)"""
        self.current_recipe = recipe_name

    def start_batch(self, batch_id: str, target_g: float, recipe: str = "Default"):
        """开始新批次"""
        if self.active_batch and self.active_batch.status == "running":
            raise RuntimeError(f"Batch {self.active_batch.batch_id} still running")

        self.active_batch = BatchState(
            batch_id=batch_id,
            recipe_name=recipe,
            start_time=datetime.now(),
            target_weight_g=target_g
        )
        self.current_recipe = recipe

    def record_bean(self, is_defect: bool, weight_g: float,
                    color_score: float, moisture_pct: float,
                    density_score: float):
        """记录一粒豆的质量数据"""
        if not self.active_batch or self.active_batch.status != "running":
            return

        self.active_batch.add_bean(is_defect, weight_g, color_score,
                                   moisture_pct, density_score)
        self._check_alerts()

    def _check_alerts(self):
        """检查是否触发告警"""
        if not self.active_batch:
            return

        metrics = self.active_batch.current_metrics()
        n = len(self.active_batch.recent_defect_rates)
        if n < 20:  # 前20粒不告警 (稳定需要数据)
            return

        # 缺陷率告警
        for metric_key, thresholds in self.THRESHOLDS.items():
            val = getattr(metrics, metric_key, None)
            if val is None:
                continue

            if metric_key == "defect_rate_pct":
                if val >= thresholds["critical"]:
                    self._emit_alert(AlertLevel.CRITICAL, "defect_rate_pct", val,
                                     thresholds["critical"])
                elif val >= thresholds["warning"]:
                    self._emit_alert(AlertLevel.WARNING, "defect_rate_pct", val,
                                     thresholds["warning"])
            elif metric_key == "color_score_avg":
                if val <= thresholds["critical"]:
                    self._emit_alert(AlertLevel.CRITICAL, "color_score_avg", val,
                                     thresholds["critical"])
                elif val <= thresholds["warning"]:
                    self._emit_alert(AlertLevel.WARNING, "color_score_avg", val,
                                     thresholds["warning"])

    def _emit_alert(self, level: AlertLevel, metric: str, value: float, threshold: float):
        """发射告警"""
        alert = QualityAlert(
            timestamp=datetime.now(),
            level=level,
            message=f"[{level.value.upper()}] {metric} = {value:.3f} "
                    f"(threshold: {threshold})",
            batch_id=self.active_batch.batch_id,
            metric=metric,
            value=value,
            threshold=threshold
        )
        self.alerts.append(alert)
        if len(self.alerts) > 200:  # 保持告警历史上限
            self.alerts.pop(0)
        if self.alert_callback:
            self.alert_callback(alert)

    def get_current_status(self) -> dict:
        """获取当前状态 (供 dashboard 使用)"""
        if not self.active_batch:
            return {"status": "idle"}

        batch = self.active_batch
        metrics = batch.current_metrics()

        return {
            "status": batch.status,
            "batch_id": batch.batch_id,
            "recipe": batch.recipe_name,
            "progress_pct": batch.progress_pct(),
            "beans_processed": batch.beans_processed,
            "beans_rejected": batch.beans_rejected,
            "defect_rate_pct": metrics.defect_rate_pct,
            "color_score_avg": metrics.color_score_avg,
            "weight_avg_g": metrics.weight_avg_g,
            "moisture_avg_pct": metrics.moisture_avg_pct,
            "density_score": metrics.density_score,
            "quality_score": metrics.overall_score(),
            "quality_grade": metrics.grade(),
            "throughput_kg_h": metrics.throughput_kg_h,
            "elapsed_min": round(
                (datetime.now() - batch.start_time).total_seconds() / 60, 1
            )
        }

    def pause_batch(self):
        if self.active_batch:
            self.active_batch.status = "paused"

    def resume_batch(self):
        if self.active_batch:
            self.active_batch.status = "running"

    def end_batch(self) -> Optional[BatchState]:
        """结束当前批次"""
        if not self.active_batch:
            return None

        self.active_batch.end_time = datetime.now()
        self.active_batch.status = "completed"
        batch = self.active_batch
        self.completed_batches.append(batch)
        self.active_batch = None
        return batch

    def abort_batch(self):
        """中止当前批次"""
        if self.active_batch:
            self.active_batch.end_time = datetime.now()
            self.active_batch.status = "aborted"
            self.completed_batches.append(self.active_batch)
            self.active_batch = None

    def get_batch_summary(self, batch_id: str) -> Optional[dict]:
        """获取指定批次的完整摘要"""
        for batch in self.completed_batches:
            if batch.batch_id == batch_id:
                metrics = batch.current_metrics()
                return {
                    "batch_id": batch.batch_id,
                    "recipe": batch.recipe_name,
                    "status": batch.status,
                    "start_time": batch.start_time.isoformat(),
                    "end_time": batch.end_time.isoformat() if batch.end_time else None,
                    "duration_min": round(
                        (batch.end_time - batch.start_time).total_seconds() / 60
                        if batch.end_time else 0, 1
                    ),
                    "beans_processed": batch.beans_processed,
                    "beans_rejected": batch.beans_rejected,
                    "total_weight_g": batch.total_weight_g,
                    "target_weight_g": batch.target_weight_g,
                    "quality_score": metrics.overall_score(),
                    "quality_grade": metrics.grade(),
                    "metrics": {
                        "defect_rate_pct": metrics.defect_rate_pct,
                        "color_score_avg": metrics.color_score_avg,
                        "weight_avg_g": metrics.weight_avg_g,
                        "moisture_avg_pct": metrics.moisture_avg_pct,
                        "density_score": metrics.density_score,
                        "throughput_kg_h": metrics.throughput_kg_h
                    }
                }
        return None

    def recent_alerts(self, n: int = 10) -> list[dict]:
        """最近 N 条告警"""
        alerts = self.alerts[-n:]
        return [
            {
                "timestamp": a.timestamp.isoformat(),
                "level": a.level.value,
                "message": a.message,
                "metric": a.metric,
                "value": round(a.value, 3)
            }
            for a in alerts
        ]

    def trend_analysis(self, n_batches: int = 5) -> dict:
        """
        对最近 n_batches 做趋势分析
        """
        batches = self.completed_batches[-n_batches:]
        if len(batches) < 2:
            return {"trend": QualityTrend.UNKNOWN.value, "message": "数据不足"}

        scores = []
        defect_rates = []
        for b in batches:
            m = b.current_metrics()
            scores.append(m.overall_score())
            defect_rates.append(m.defect_rate_pct)

        # 趋势判定
        score_diff = scores[-1] - scores[0]
        defect_diff = defect_rates[-1] - defect_rates[0]

        if score_diff > 3 and defect_diff < -0.5:
            trend = QualityTrend.IMPROVING
        elif score_diff < -3 or defect_diff > 1.0:
            trend = QualityTrend.DEGRADING
        else:
            trend = QualityTrend.STABLE

        return {
            "trend": trend.value,
            "n_batches": len(batches),
            "quality_scores": [round(s, 1) for s in scores],
            "defect_rates_pct": [round(d, 3) for d in defect_rates],
            "avg_quality_score": round(statistics.mean(scores), 1),
            "score_std": round(statistics.stdev(scores), 1) if len(scores) > 1 else 0,
            "recommendation": self._trend_recommendation(trend, scores, defect_rates)
        }

    def _trend_recommendation(self, trend: QualityTrend, scores, defect_rates) -> str:
        if trend == QualityTrend.IMPROVING:
            return "✅ 质量趋势向好，保持当前参数配置"
        elif trend == QualityTrend.DEGRADING:
            return "⚠️ 质量趋势下降，建议检查传感器标定或原料质量"
        else:
            return "➡️ 质量趋势稳定，继续监控"


# ─────────────────────────────────────────────
# Demo / CLI
# ─────────────────────────────────────────────

def simulate_batch(tracker: BatchQualityTracker, recipe: str,
                  target_g: float, n_beans: int = 500,
                  defect_rate: float = 0.04) -> BatchState:
    """蒙特卡洛模拟批次 (用于演示/验证)"""

    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tracker.start_batch(batch_id, target_g=target_g, recipe=recipe)

    for i in range(n_beans):
        is_defect = random.random() < defect_rate
        weight_g = random.gauss(0.152, 0.010)
        color_score = random.gauss(85, 8) if not is_defect else random.gauss(65, 15)
        moisture_pct = random.gauss(11.0, 0.5) if not is_defect else random.gauss(9.5, 1.0)
        density_score = random.gauss(88, 6) if not is_defect else random.gauss(72, 12)

        tracker.record_bean(
            is_defect=is_defect,
            weight_g=max(0.05, weight_g),
            color_score=max(0, min(100, color_score)),
            moisture_pct=max(5, min(15, moisture_pct)),
            density_score=max(0, min(100, density_score))
        )

        # 模拟处理时间 (~1粒/100ms)

    return tracker.end_batch()


def main():
    print("=" * 60)
    print("  Batch Quality Tracker — Demo")
    print("=" * 60)

    tracker = BatchQualityTracker()

    # 模拟3个批次
    recipes = ["Ethiopian_Washed", "Kenyan_Washed AA+AB", "Brazilian_Natural"]
    batch_summaries = []

    for recipe in recipes:
        print(f"\n▶ Starting batch: {recipe}")
        batch = simulate_batch(tracker, recipe, target_g=2000, n_beans=500)
        summary = tracker.get_batch_summary(batch.batch_id)
        print(f"  Beans processed: {summary['beans_processed']}")
        print(f"  Defect rate: {summary['metrics']['defect_rate_pct']:.2f}%")
        print(f"  Color score: {summary['metrics']['color_score_avg']:.1f}")
        print(f"  Quality score: {summary['quality_score']:.1f} ({summary['quality_grade']})")
        print(f"  Throughput: {summary['metrics']['throughput_kg_h']:.3f} kg/h")

        batch_summaries.append(tracker.get_batch_summary(batch.batch_id))

    # 趋势分析
    print("\n" + "=" * 60)
    print("  Trend Analysis (last 3 batches)")
    print("=" * 60)
    trend = tracker.trend_analysis(n_batches=3)
    print(f"  Trend: {trend['trend']}")
    print(f"  Quality scores: {trend['quality_scores']}")
    print(f"  Defect rates: {trend['defect_rates_pct']}%")
    print(f"  Avg score: {trend['avg_quality_score']}")
    print(f"  Recommendation: {trend['recommendation']}")

    # 告警摘要
    print("\n  Recent alerts:")
    for a in tracker.recent_alerts(n=5):
        print(f"    [{a['timestamp'][11:19]}] {a['message']}")

    # 保存JSON报告
    report = {
        "generated_at": datetime.now().isoformat(),
        "batches": batch_summaries,
        "trend": trend
    }

    import os
    os.makedirs("sorter/reports", exist_ok=True)
    report_path = f"sorter/reports/batch_quality_report_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Report saved: {report_path}")


if __name__ == "__main__":
    main()