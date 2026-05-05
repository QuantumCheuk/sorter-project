#!/usr/bin/env python3
"""
生豆分选机 — 预测性维护与磨损分析
Predictive Maintenance & Wear Analysis for HUSKY-SORTER-001

Research Objective:
在硬件到位前的最后准备阶段，建立完整的预测性维护体系。
覆盖：①组件磨损机理分析；②BOM耗材寿命模型；③多层级维护计划；
④故障诊断决策树；⑤年度维护成本建模；⑥备件库存优化。

Author: Little Husky (HUSKY-SORTER-001)
Version: v1.0 — 2026-05-05
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# SECTION 1: Component Wear Database
# =============================================================================

@dataclass
class WearProfile:
    component: str
    category: str  # electrical | mechanical | sensor | consumable | structural
    lifespan_hours: float
    lifespan_units: str  # hours | shots | grams
    wear_mechanism: str
    failure_mode: str
    failure_severity: int  # 1=minor, 5=critical
    replacement_cost_rmb: float
    downtime_minutes: float
    environmental_factors: list = field(default_factory=list)
    notes: str = ""


WEAR_DATABASE = {

    # ─── 电气类 ────────────────────────────────────────────────────────────────
    "pi4": WearProfile(
        component="Raspberry Pi 4 Model B",
        category="electrical",
        lifespan_hours=87600,
        lifespan_units="hours",
        wear_mechanism="电容老化 + SD卡磨损",
        failure_mode="启动失败 / SD卡只读 / USB端口退化",
        failure_severity=4,
        replacement_cost_rmb=290,
        downtime_minutes=30,
        environmental_factors=["高温", "电源波动", "灰尘"],
        notes="SD卡为最薄弱环节；建议使用SSD或高耐久性SD卡"
    ),
    "psu_12v": WearProfile(
        component="12V DC 电源适配器 (执行器)",
        category="electrical",
        lifespan_hours=26280,
        lifespan_units="hours",
        wear_mechanism="电解电容老化 + 热疲劳",
        failure_mode="输出电压下降 / 输出波动 / 完全失效",
        failure_severity=3,
        replacement_cost_rmb=80,
        downtime_minutes=15,
        environmental_factors=["高温", "过载", "潮湿"],
        notes="12V 3A minimum；空压机峰值3A+，当前2A适配器不足⚠️"
    ),
    "psu_5v": WearProfile(
        component="5V USB-C 电源适配器 (Pi)",
        category="electrical",
        lifespan_hours=26280,
        lifespan_units="hours",
        wear_mechanism="USB-C接口磨损 + 电容老化",
        failure_mode="间歇性重启 / USB-C接口松动",
        failure_severity=3,
        replacement_cost_rmb=60,
        downtime_minutes=10,
        environmental_factors=["高温", "机械应力"],
        notes="建议使用官方Pi电源适配器"
    ),
    "hx711": WearProfile(
        component="HX711 24-bit ADC模块",
        category="electrical",
        lifespan_hours=43800,
        lifespan_units="hours",
        wear_mechanism="焊点热疲劳 + 输入保护二极管老化",
        failure_mode="读数漂移 / ADC饱和 / I2C通信失败",
        failure_severity=3,
        replacement_cost_rmb=15,
        downtime_minutes=20,
        environmental_factors=["振动", "温度波动"],
        notes="建议备2个；焊锡接头需定期检查"
    ),
    "ad7746": WearProfile(
        component="AD7746 I2C电容数字转换器",
        category="electrical",
        lifespan_hours=43800,
        lifespan_units="hours",
        wear_mechanism="参考电容老化 + 基准电压漂移",
        failure_mode="含水率读数系统性偏移 / I2C通信失败",
        failure_severity=3,
        replacement_cost_rmb=60,
        downtime_minutes=25,
        environmental_factors=["温度漂移", "湿度变化"],
        notes="采购交付周期约14天，需备1个"
    ),
    "esp32": WearProfile(
        component="ESP32 DevKit MCU",
        category="electrical",
        lifespan_hours=87600,
        lifespan_units="hours",
        wear_mechanism="Flash写入次数限制 + USB接口磨损",
        failure_mode="固件上传失败 / UART通信异常",
        failure_severity=2,
        replacement_cost_rmb=25,
        downtime_minutes=20,
        environmental_factors=["高温", "电源波动"],
        notes="Flash寿命约100,000次擦写；每日重启1次可工作273年"
    ),

    # ─── 机械类 ────────────────────────────────────────────────────────────────
    "nema17": WearProfile(
        component="Nema 17 步进电机 (振动给料)",
        category="mechanical",
        lifespan_hours=8760,
        lifespan_units="hours",
        wear_mechanism="轴承磨损 + 磁铁退磁 + 润滑脂干涸",
        failure_mode="失步 / 发热过高 / 共振噪音",
        failure_severity=3,
        replacement_cost_rmb=65,
        downtime_minutes=30,
        environmental_factors=["振动", "灰尘", "高温"],
        notes="3通道×50bpm@10h/天≈547,500次/年，远低于额定寿命"
    ),
    "28byj48": WearProfile(
        component="28BYJ-48 步进电机 (旋转分配器)",
        category="mechanical",
        lifespan_hours=3000,
        lifespan_units="hours",
        wear_mechanism="塑料齿轮磨损 + 轴承老化",
        failure_mode="丢步 / 异响 / 堵转",
        failure_severity=2,
        replacement_cost_rmb=12,
        downtime_minutes=20,
        environmental_factors=["振动", "过载"],
        notes="分配器转速低，磨损较轻"
    ),
    "turbine_blower": WearProfile(
        component="涡轮鼓风机 (密度分选)",
        category="mechanical",
        lifespan_hours=17520,
        lifespan_units="hours",
        wear_mechanism="轴承磨损 + 涡轮叶片积灰 + 密封圈老化",
        failure_mode="风速下降 / 异响 / 振动增大",
        failure_severity=4,
        replacement_cost_rmb=200,
        downtime_minutes=60,
        environmental_factors=["粉尘", "连续运行", "咖啡油脂沉积"],
        notes="预计交付周期60天⚠️；需备1个；每月清洁进风口过滤棉"
    ),
    "air_compressor": WearProfile(
        component="小型空压机 (气喷气源)",
        category="mechanical",
        lifespan_hours=4380,
        lifespan_units="hours",
        wear_mechanism="活塞环磨损 + 阀片疲劳 + 储气罐腐蚀",
        failure_mode="气压不足 / 噪音增大 / 过热保护",
        failure_severity=4,
        replacement_cost_rmb=200,
        downtime_minutes=45,
        environmental_factors=["连续运行", "湿度", "油品质量"],
        notes="按需运行(非连续)可延长寿命3×；需每日排水"
    ),
    "sol_valve": WearProfile(
        component="微型电磁阀 12V NC (气喷)",
        category="mechanical",
        lifespan_hours=8760000,
        lifespan_units="shots",
        wear_mechanism="线圈老化 + 密封磨损 + 弹簧疲劳",
        failure_mode="响应变慢 / 泄漏 / 无法关闭",
        failure_severity=3,
        replacement_cost_rmb=25,
        downtime_minutes=20,
        environmental_factors=["高频开关", "压缩空气杂质"],
        notes="实际约18,000次/天×300天=5.4M次/年；远低于额定8.76M"
    ),
    "solenoid_release": WearProfile(
        component="电磁阀释放机构 (称重杯)",
        category="mechanical",
        lifespan_hours=5475000,
        lifespan_units="shots",
        wear_mechanism="弹簧疲劳 + 密封磨损",
        failure_mode="释放不完全 / 卡滞",
        failure_severity=2,
        replacement_cost_rmb=20,
        downtime_minutes=25,
        environmental_factors=["高频开关"],
        notes="动作频率与气喷电磁阀相近"
    ),
    "vibration_feeder_bowl": WearProfile(
        component="振动给料 bowl (3D打印PETG)",
        category="mechanical",
        lifespan_hours=3000,
        lifespan_units="hours",
        wear_mechanism="材料疲劳 + 螺纹连接松动",
        failure_mode="裂纹扩展 / 共振频率漂移",
        failure_severity=2,
        replacement_cost_rmb=15,
        downtime_minutes=90,
        environmental_factors=["振动应力", "温度循环"],
        notes="PETG比PLA更适合高振动环境；定期检查紧固螺丝"
    ),
    "buffer_bin_hinge": WearProfile(
        component="缓冲仓转轴/铰链",
        category="mechanical",
        lifespan_hours=8760,
        lifespan_units="hours",
        wear_mechanism="轴承磨损 + 润滑脂流失",
        failure_mode="旋转不顺畅 / 异响",
        failure_severity=2,
        replacement_cost_rmb=10,
        downtime_minutes=30,
        environmental_factors=["负重", "灰尘"],
        notes="8格缓冲仓每天多次旋转；润滑脂需每6个月补充"
    ),

    # ─── 传感器类 ──────────────────────────────────────────────────────────────
    "photocell_t1t2": WearProfile(
        component="红外光电传感器 T1/T2",
        category="sensor",
        lifespan_hours=17520,
        lifespan_units="hours",
        wear_mechanism="LED发光强度衰减 + 灰尘遮挡",
        failure_mode="触发阈值漂移 / 误触发 / 无响应",
        failure_severity=3,
        replacement_cost_rmb=8,
        downtime_minutes=15,
        environmental_factors=["灰尘", "LED老化", "温度"],
        notes="红外LED衰减约1%/1000小时；需定期清洁镜片"
    ),
    "load_cell": WearProfile(
        component="称重传感器 Load Cell (零点漂移)",
        category="sensor",
        lifespan_hours=17520,
        lifespan_units="hours",
        wear_mechanism="应变片蠕变 + 温度漂移累积",
        failure_mode="零点漂移超出标定范围 / 重复性下降",
        failure_severity=3,
        replacement_cost_rmb=50,
        downtime_minutes=40,
        environmental_factors=["温度波动", "冲击载荷", "长期偏心负载"],
        notes="每天自动归零可延缓；长期使用后建议更换"
    ),
    "camera_lens": WearProfile(
        component="相机镜头 M12 6mm",
        category="sensor",
        lifespan_hours=26280,
        lifespan_units="hours",
        wear_mechanism="光学镀膜老化 + 镜片位移",
        failure_mode="对焦漂移 / 眩光增加 / 色彩还原偏差",
        failure_severity=2,
        replacement_cost_rmb=80,
        downtime_minutes=20,
        environmental_factors=["温度冲击", "湿气", "振动"],
        notes="IP65防护罩可延长寿命；暗箱内定期清洁镜头"
    ),
    "hq_camera": WearProfile(
        component="Raspberry Pi HQ Camera IMX477",
        category="sensor",
        lifespan_hours=26280,
        lifespan_units="hours",
        wear_mechanism="CMOS传感器老化 + 接口松动",
        failure_mode="图像噪点增加 / 连接不稳定 / 色彩偏差",
        failure_severity=3,
        replacement_cost_rmb=350,
        downtime_minutes=25,
        environmental_factors=["热噪声累积", "接口磨损"],
        notes="预计交付周期60天⚠️；需备1个"
    ),

    # ─── 耗材类 ───────────────────────────────────────────────────────────────
    "air_filter_cotton": WearProfile(
        component="空气过滤器棉 (空压机进气)",
        category="consumable",
        lifespan_hours=720,
        lifespan_units="hours",
        wear_mechanism="粉尘积聚堵塞",
        failure_mode="气压下降 / 能耗增加",
        failure_severity=2,
        replacement_cost_rmb=5,
        downtime_minutes=10,
        environmental_factors=["环境粉尘浓度"],
        notes="每2周清洁(可复用)或更换；密集使用需更频繁"
    ),
    "o_ring_seal": WearProfile(
        component="O型密封圈 (气路接口)",
        category="consumable",
        lifespan_hours=2160,
        lifespan_units="hours",
        wear_mechanism="压缩永久变形 + 臭氧老化",
        failure_mode="气路泄漏 / 气压不足",
        failure_severity=2,
        replacement_cost_rmb=3,
        downtime_minutes=15,
        environmental_factors=["臭氧", "压缩空气温度"],
        notes="建议备10个；NBR材质适合一般矿物油基压缩空气"
    ),
    "lubricating_grease": WearProfile(
        component="润滑脂 (轴承/导轨)",
        category="consumable",
        lifespan_hours=4320,
        lifespan_units="hours",
        wear_mechanism="润滑脂氧化/干涸",
        failure_mode="噪音/磨损增加",
        failure_severity=1,
        replacement_cost_rmb=10,
        downtime_minutes=30,
        environmental_factors=["高温", "高湿度", "粉尘"],
        notes="食品级润滑脂用于接触食品的部件；每月检查"
    ),
    "cable_connector": WearProfile(
        component="杜邦线/连接器 (GPIO/I2C)",
        category="consumable",
        lifespan_hours=4320,
        lifespan_units="hours",
        wear_mechanism="插针氧化 + 机械磨损",
        failure_mode="接触不良 / 间歇性通信错误",
        failure_severity=2,
        replacement_cost_rmb=5,
        downtime_minutes=20,
        environmental_factors=["湿度", "振动", "插拔次数"],
        notes="使用防潮箱存放备件；接线端子定期检查紧固"
    ),
    "sd_card": WearProfile(
        component="SD卡 (系统存储)",
        category="consumable",
        lifespan_hours=17520,
        lifespan_units="hours",
        wear_mechanism="NAND Flash写入磨损",
        failure_mode="只读模式 / 启动失败 / 文件系统损坏",
        failure_severity=4,
        replacement_cost_rmb=40,
        downtime_minutes=20,
        environmental_factors=["写入频率", "电源中断"],
        notes="使用高耐久性SD卡(A1/A2等级)；启用只读文件系统降低磨损"
    ),

    # ─── 结构类 ───────────────────────────────────────────────────────────────
    "dark_box": WearProfile(
        component="遮光暗箱 (3D打印)",
        category="structural",
        lifespan_hours=26280,
        lifespan_units="hours",
        wear_mechanism="连接件松动 + 遮光材料老化",
        failure_mode="漏光导致颜色检测误差",
        failure_severity=2,
        replacement_cost_rmb=20,
        downtime_minutes=60,
        environmental_factors=["光老化", "温度循环"],
        notes="遮光棉边缘老化后需更换；接缝定期检查密封性"
    ),
    "sizing_plate": WearProfile(
        component="尺寸分选孔板 (激光切割PMMA)",
        category="structural",
        lifespan_hours=8760,
        lifespan_units="hours",
        wear_mechanism="孔口磨损扩张 + 应力裂纹",
        failure_mode="尺寸分选精度下降",
        failure_severity=2,
        replacement_cost_rmb=30,
        downtime_minutes=45,
        environmental_factors=["豆子冲击磨损", "清洗溶剂"],
        notes="PMMA比PLA更耐磨；定期用酒精清洁孔内残留物"
    ),
    "transparent_window": WearProfile(
        component="底部透明磨砂窗口 (PMMA)",
        category="structural",
        lifespan_hours=8760,
        lifespan_units="hours",
        wear_mechanism="表面划痕 + 光散射特性退化",
        failure_mode="底部相机成像质量下降",
        failure_severity=2,
        replacement_cost_rmb=15,
        downtime_minutes=30,
        environmental_factors=["物理摩擦", "清洗刮擦"],
        notes="磨砂面朝上安装；用软布清洁，避免研磨性材料"
    ),
}


# =============================================================================
# SECTION 2: Usage Profile & Lifetime Calculator
# =============================================================================

@dataclass
class UsageProfile:
    channels: int = 3
    beans_per_minute_per_channel: float = 50
    operating_hours_per_day: float = 10
    operating_days_per_year: int = 300
    defect_rejection_rate: float = 0.05
    # beans per day
    def beans_per_hour(self) -> float:
        return self.channels * self.beans_per_minute_per_channel * 60

    def beans_per_day(self) -> float:
        return self.beans_per_hour() * self.operating_hours_per_day

    def shots_per_day_air_jet(self) -> float:
        """气喷电磁阀每日开关次数（仅缺陷豆）"""
        return self.beans_per_day() * self.defect_rejection_rate

    def shots_per_day_solenoid(self) -> float:
        """称重释放电磁阀每日开关次数（所有豆）"""
        return self.beans_per_day()


DEFAULT_USAGE = UsageProfile()


def calc_lifespan_months(wear: WearProfile, usage: UsageProfile) -> float:
    if wear.lifespan_units == "hours":
        return wear.lifespan_hours / (usage.operating_hours_per_day * usage.operating_days_per_year / 12)
    elif wear.lifespan_units == "shots":
        shots_per_day = (usage.shots_per_day_air_jet() if "气喷" in wear.component
                         else usage.shots_per_day_solenoid())
        return wear.lifespan_hours / (shots_per_day * usage.operating_days_per_year / 12)
    else:
        return wear.lifespan_hours / (usage.operating_hours_per_day * usage.operating_days_per_year / 12)


def get_wear_summary(usage: UsageProfile = DEFAULT_USAGE) -> list[dict]:
    results = []
    for comp_id, wear in WEAR_DATABASE.items():
        months = calc_lifespan_months(wear, usage)
        monthly_cost = wear.replacement_cost_rmb / max(months, 0.01)
        annual_cost = monthly_cost * 12
        crit = "🔴" if wear.failure_severity >= 4 else ("🟡" if wear.failure_severity >= 3 else "🟢")
        results.append({
            "id": comp_id,
            "component": wear.component,
            "category": wear.category,
            "lifespan_months": round(months, 1),
            "wear_mechanism": wear.wear_mechanism,
            "failure_mode": wear.failure_mode,
            "failure_severity": wear.failure_severity,
            "criticality": crit,
            "replacement_cost_rmb": wear.replacement_cost_rmb,
            "monthly_cost_rmb": round(monthly_cost, 2),
            "annual_cost_rmb": round(annual_cost, 2),
            "downtime_minutes": wear.downtime_minutes,
            "notes": wear.notes[:60] if wear.notes else ""
        })
    results.sort(key=lambda x: (-x["failure_severity"], -x["annual_cost_rmb"]))
    return results


# =============================================================================
# SECTION 3: Annual Maintenance Cost Model
# =============================================================================

def calc_annual_maintenance_cost(usage: UsageProfile = DEFAULT_USAGE) -> dict:
    """计算年度维护总成本"""
    summary = get_wear_summary(usage)
    total_parts = sum(r["annual_cost_rmb"] for r in summary)
    total_downtime_hours = sum(r["lifespan_months"] for r in summary if r["lifespan_months"] > 0)
    # MTBF: weighted average months
    weighted_mtbf = sum(r["lifespan_months"] * r["failure_severity"] for r in summary) / max(sum(r["failure_severity"] for r in summary), 1)
    # downtime cost: assume 150 RMB/hour opportunity cost
    downtime_cost_per_hour = 150
    estimated_downtime_per_year = sum(
        r["downtime_minutes"] / 60 * (usage.operating_days_per_year * usage.operating_hours_per_day / max(r["lifespan_months"] * 30 * 24, 1))
        for r in summary
    )
    by_category = {}
    for r in summary:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = 0
        by_category[cat] += r["annual_cost_rmb"]
    return {
        "total_annual_parts_cost_rmb": round(total_parts, 2),
        "estimated_downtime_hours_per_year": round(estimated_downtime_per_year, 1),
        "downtime_cost_rmb_per_year": round(estimated_downtime_per_year * downtime_cost_per_hour, 2),
        "total_annual_cost_rmb": round(total_parts + estimated_downtime_per_year * downtime_cost_per_hour, 2),
        "weighted_mtbf_months": round(weighted_mtbf, 1),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
        "usage_summary": {
            "channels": usage.channels,
            "beans_per_hour": round(usage.beans_per_hour(), 1),
            "beans_per_day": round(usage.beans_per_day(), 1),
            "annual_output_kg": round(usage.beans_per_day() * 0.15 / 1000 * usage.operating_days_per_year, 1),
        }
    }


# =============================================================================
# SECTION 4: Spare Parts Inventory Recommendation
# =============================================================================

def get_spare_parts_recommendation() -> list[dict]:
    """推荐备件库存（基于风险等级和交付周期）"""
    spares = []
    for comp_id, wear in WEAR_DATABASE.items():
        if wear.failure_severity >= 3 or wear.category == "consumable":
            # stock quantity: 1 for long-lead, 2 for critical
            if wear.failure_severity >= 4:
                stock = 2
            elif wear.category == "consumable":
                stock = 5  # 耗材多备
            else:
                stock = 1
            spares.append({
                "component": wear.component,
                "category": wear.category,
                "stock_qty": stock,
                "unit_cost_rmb": wear.replacement_cost_rmb,
                "total_value_rmb": round(wear.replacement_cost_rmb * stock, 2),
                "failure_severity": wear.failure_severity,
                "lead_time_days": 60 if wear.component in ["HQ Camera", "涡轮鼓风机"] else 14,
                "priority": "HIGH" if wear.failure_severity >= 4 else ("MEDIUM" if wear.failure_severity >= 3 else "LOW")
            })
    spares.sort(key=lambda x: (-x["failure_severity"], -x["total_value_rmb"]))
    return spares


# =============================================================================
# SECTION 5: Maintenance Schedule
# =============================================================================

@dataclass
class MaintenanceTask:
    task: str
    frequency: str
    components: list
    estimated_minutes: float
    skill: str  # basic | intermediate | advanced
    procedure_summary: str
    pass_criteria: str


MAINTENANCE_TASKS: list[MaintenanceTask] = [
    MaintenanceTask(
        task="空压机每日排水",
        frequency="daily",
        components=["air_compressor"],
        estimated_minutes=5,
        skill="basic",
        procedure_summary="关闭电源→打开底部排水阀→排出积液→关闭阀门→重启",
        pass_criteria="排水口无积水；气压600-800kPa"
    ),
    MaintenanceTask(
        task="外观与声音检查",
        frequency="daily",
        components=["nema17", "turbine_blower", "air_compressor", "sol_valve"],
        estimated_minutes=5,
        skill="basic",
        procedure_summary="目视检查异常振动/噪音/气味；检查线缆连接",
        pass_criteria="无异常；运行电流正常"
    ),
    MaintenanceTask(
        task="气路泄漏检查",
        frequency="daily",
        components=["sol_valve", "o_ring_seal"],
        estimated_minutes=5,
        skill="basic",
        procedure_summary="听气路嘶嘶声；肥皂水涂抹接口观察气泡",
        pass_criteria="无气泡；无明显泄漏"
    ),
    MaintenanceTask(
        task="给料系统清洁",
        frequency="daily",
        components=["vibration_feeder_bowl"],
        estimated_minutes=10,
        skill="basic",
        procedure_summary="关闭电源→软刷清理给料bowl→检查弹簧片→测试出料",
        pass_criteria="出料速度正常；无堵塞"
    ),
    MaintenanceTask(
        task="光电传感器镜片清洁",
        frequency="weekly",
        components=["photocell_t1t2"],
        estimated_minutes=10,
        skill="basic",
        procedure_summary="关闭电源→酒精棉签擦拭T1/T2镜片→测试触发阈值",
        pass_criteria="触发响应正常；阈值在标定范围内"
    ),
    MaintenanceTask(
        task="MQTT Broker健康检查",
        frequency="weekly",
        components=["esp32"],
        estimated_minutes=5,
        skill="intermediate",
        procedure_summary="检查Mosquitto服务状态→查看日志→测试pub/sub→内存检查",
        pass_criteria="服务正常；消息延迟<100ms；内存<200MB"
    ),
    MaintenanceTask(
        task="零点标定验证（称重系统）",
        frequency="weekly",
        components=["hx711", "load_cell"],
        estimated_minutes=10,
        skill="intermediate",
        procedure_summary="空载称重杯→观察零点读数→记录漂移→超过50mg则tare归零",
        pass_criteria="零点漂移<50mg；标定记录已更新"
    ),
    MaintenanceTask(
        task="步进电机温度检查",
        frequency="weekly",
        components=["nema17"],
        estimated_minutes=5,
        skill="basic",
        procedure_summary="运行30分钟后测温枪测量外壳温度",
        pass_criteria="外壳温度<60°C；无异常振动"
    ),
    MaintenanceTask(
        task="空压机进气过滤器清洁/更换",
        frequency="monthly",
        components=["air_filter_cotton"],
        estimated_minutes=15,
        skill="basic",
        procedure_summary="关闭电源→拆卸过滤器→压缩空气反向吹洗或更换→重新安装",
        pass_criteria="气压恢复正常；无明显下降"
    ),
    MaintenanceTask(
        task="轴承润滑脂补充",
        frequency="monthly",
        components=["nema17_bearing", "buffer_bin_hinge"],
        estimated_minutes=30,
        skill="intermediate",
        procedure_summary="关闭电源→补充食品级润滑脂→手动旋转确认→擦除多余→测试",
        pass_criteria="噪音降低或消失；旋转顺畅"
    ),
    MaintenanceTask(
        task="相机暗箱清洁",
        frequency="monthly",
        components=["camera_lens", "dark_box"],
        estimated_minutes=20,
        skill="basic",
        procedure_summary="关闭电源→气吹清洁暗箱→镜头纸擦拭镜头→检查遮光棉→检查LED",
        pass_criteria="无灰尘；成像清晰；LED无闪烁"
    ),
    MaintenanceTask(
        task="电气连接紧固检查",
        frequency="monthly",
        components=["cable_connector", "psu_12v", "psu_5v"],
        estimated_minutes=20,
        skill="intermediate",
        procedure_summary="关闭电源→逐一检查GPIO/12V/5V/接地→紧固松动连接→拍照记录",
        pass_criteria="所有连接牢固；无氧化/腐蚀"
    ),
    MaintenanceTask(
        task="称重系统完整标定",
        frequency="monthly",
        components=["hx711", "load_cell"],
        estimated_minutes=30,
        skill="advanced",
        procedure_summary="准备100g砝码→空载tare→放置砝码→5次平均→误差<0.1g则通过",
        pass_criteria="误差<0.1g；5次标准差<10mg；记录已保存"
    ),
    MaintenanceTask(
        task="O型密封圈全面检查与更换",
        frequency="monthly",
        components=["o_ring_seal"],
        estimated_minutes=20,
        skill="basic",
        procedure_summary="检查所有气路接口O型圈→记录状态→更换可疑件",
        pass_criteria="无硬化/裂纹/永久变形"
    ),
    MaintenanceTask(
        task="涡轮鼓风机清洁与检查",
        frequency="quarterly",
        components=["turbine_blower"],
        estimated_minutes=45,
        skill="intermediate",
        procedure_summary="拆卸进风口→软刷清理叶轮→干燥气枪吹扫→测试风速与基准对比",
        pass_criteria="风速恢复到标定值±10%；无异常噪音"
    ),
    MaintenanceTask(
        task="螺旋给料机构检查",
        frequency="quarterly",
        components=["nema17"],
        estimated_minutes=30,
        skill="intermediate",
        procedure_summary="手动旋转确认无卡阻→检查联轴器→测量给料速率与基准对比",
        pass_criteria="旋转顺畅；给料速率在基准±5%内"
    ),
    MaintenanceTask(
        task="含水率传感器标定验证",
        frequency="quarterly",
        components=["ad7746"],
        estimated_minutes=40,
        skill="advanced",
        procedure_summary="准备5%和12%含水率样本→按标定流程测量→误差>0.5%则重新标定",
        pass_criteria="误差<0.5%；标定曲线R²>0.99"
    ),
    MaintenanceTask(
        task="SD卡健康检查",
        frequency="quarterly",
        components=["sd_card"],
        estimated_minutes=10,
        skill="intermediate",
        procedure_summary="smartctl检查Wear_Leveling_Count→测试读写速度→检查剩余空间",
        pass_criteria="Wear_Leveling>80%剩余；读写>10MB/s；空间>20%"
    ),
    MaintenanceTask(
        task="空压机年度全面维护",
        frequency="annually",
        components=["air_compressor"],
        estimated_minutes=120,
        skill="advanced",
        procedure_summary="更换活塞环/阀片/O型圈→换油→检查储气罐→安全阀测试",
        pass_criteria="排气量恢复出厂规格；无过热；噪音正常"
    ),
    MaintenanceTask(
        task="步进电机轴承更换",
        frequency="annually",
        components=["nema17"],
        estimated_minutes=90,
        skill="advanced",
        procedure_summary="断电标记线序→拆卸电机→换轴承→重新安装→测试运行",
        pass_criteria="运行平稳；无异常噪音；电流正常"
    ),
    MaintenanceTask(
        task="气路系统全面检漏与压力测试",
        frequency="annually",
        components=["o_ring_seal", "sol_valve"],
        estimated_minutes=60,
        skill="intermediate",
        procedure_summary="全系统肥皂水检漏→压力测试(1.5倍工作压)→记录泄漏点",
        pass_criteria="无可见气泡；压力保持稳定"
    ),
]


# =============================================================================
# SECTION 6: Troubleshooting Decision Tree
# =============================================================================

@dataclass
class TroubleshootingNode:
    symptom: str
    possible_causes: list[dict]  # {cause, probability, severity}
    diagnostic_steps: list[str]
    node_id: str = ""


TROUBLESHOOTING_TREE = [
    {
        "node_id": "S1",
        "symptom": "系统无法启动 (Pi不通电)",
        "priority": 1,
        "possible_causes": [
            {"cause": "电源适配器故障", "probability": 0.30, "severity": 3},
            {"cause": "USB-C接口松动/损坏", "probability": 0.25, "severity": 3},
            {"cause": "SD卡损坏", "probability": 0.20, "severity": 4},
            {"cause": "GPIO引脚短路", "probability": 0.10, "severity": 4},
            {"cause": "SD卡只读模式(磨损)", "probability": 0.15, "severity": 4},
        ],
        "diagnostic_steps": [
            "1. 检查电源指示灯(Pi绿灯)是否亮起",
            "2. 用万用表测量USB-C接口输出电压(5.1V±0.2V)",
            "3. 尝试另一个已知良好的电源适配器",
            "4. 检查SD卡金属触点是否氧化；尝试读卡器读取",
            "5. 用显示器+键盘直连Pi检查启动日志",
        ],
        "quick_fix": "更换电源适配器或SD卡",
        "downtime_estimate_min": "10-30"
    },
    {
        "node_id": "S2",
        "symptom": "MQTT消息丢失/延迟>500ms",
        "priority": 2,
        "possible_causes": [
            {"cause": "Mosquitto服务崩溃", "probability": 0.35, "severity": 3},
            {"cause": "SD卡写入阻塞(日志过多)", "probability": 0.25, "severity": 3},
            {"cause": "WiFi信号弱", "probability": 0.20, "severity": 2},
            {"cause": "消息频率超过Pi处理能力", "probability": 0.10, "severity": 2},
            {"cause": "ESP32 UART通信阻塞", "probability": 0.10, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. systemctl status mosquitto — 检查服务状态",
            "2. journalctl -u mosquitto — 查看崩溃日志",
            "3. free -h — 检查可用内存(应>300MB)",
            "4. iwconfig wlan0 — 检查WiFi信号强度",
            "5. mosquitto_sub测试本地pub/sub延迟",
        ],
        "quick_fix": "systemctl restart mosquitto",
        "downtime_estimate_min": "2-5"
    },
    {
        "node_id": "S3",
        "symptom": "称重读数漂移 > 100mg",
        "priority": 2,
        "possible_causes": [
            {"cause": "温度漂移(热源附近安装)", "probability": 0.35, "severity": 3},
            {"cause": "零点未归零(皮重累积)", "probability": 0.30, "severity": 2},
            {"cause": "HX711 ADC故障/老化", "probability": 0.15, "severity": 3},
            {"cause": "称重杯物理变形/污染", "probability": 0.15, "severity": 2},
            {"cause": "Load Cell过载冲击损坏", "probability": 0.05, "severity": 4},
        ],
        "diagnostic_steps": [
            "1. 检查环境温度是否稳定(±2°C内)",
            "2. 执行tare归零，等待60s稳定后重新测量",
            "3. 用100g砝码验证读数误差是否<0.1g",
            "4. 检查HX711模块焊点(放大镜目视)",
            "5. 拆卸称重杯检查是否有残留物或变形",
        ],
        "quick_fix": "执行tare归零；移至远离热源位置",
        "downtime_estimate_min": "10-40"
    },
    {
        "node_id": "S4",
        "symptom": "颜色检测误判率突然上升",
        "priority": 2,
        "possible_causes": [
            {"cause": "LED光源衰减(>1000小时)", "probability": 0.30, "severity": 3},
            {"cause": "镜头脏污/起雾", "probability": 0.25, "severity": 2},
            {"cause": "暗箱漏光(密封老化)", "probability": 0.20, "severity": 2},
            {"cause": "相机对焦漂移", "probability": 0.15, "severity": 2},
            {"cause": "ML模型文件损坏", "probability": 0.10, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. 目视检查暗箱所有接缝是否漏光",
            "2. 用镜头纸清洁top和bottom相机镜头",
            "3. 运行dashboard观察实时图像是否清晰",
            "4. 用白色参考卡验证相机曝光/L*a*b*读数是否正常",
            "5. 检查ML模型文件大小和哈希值",
        ],
        "quick_fix": "清洁镜头+白板标定+重新加载ML模型",
        "downtime_estimate_min": "20-30"
    },
    {
        "node_id": "S5",
        "symptom": "气喷电磁阀响应延迟/无力",
        "priority": 2,
        "possible_causes": [
            {"cause": "气压不足(<500kPa)", "probability": 0.30, "severity": 3},
            {"cause": "O型圈老化导致泄漏", "probability": 0.30, "severity": 2},
            {"cause": "电磁阀线圈老化(内阻↑)", "probability": 0.20, "severity": 3},
            {"cause": "电源适配器供电不足", "probability": 0.15, "severity": 3},
            {"cause": "ESP32 GPIO输出故障", "probability": 0.05, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. 检查空压机气压表(应600-800kPa)",
            "2. 手动测试电磁阀: 直接供12V听是否有嗒嗒声",
            "3. 用万用表测量电磁阀线圈电阻(正常约30-60Ω)",
            "4. 检查12V电源适配器输出电流规格",
            "5. 用示波器测量GPIO输出波形(应有12V驱动)",
        ],
        "quick_fix": "更换电磁阀O型圈；提升气压到600kPa以上",
        "downtime_estimate_min": "15-25"
    },
    {
        "node_id": "S6",
        "symptom": "步进电机失步/丢步",
        "priority": 1,
        "possible_causes": [
            {"cause": "电机轴承磨损/损坏", "probability": 0.30, "severity": 3},
            {"cause": "皮带/联轴器松动", "probability": 0.20, "severity": 2},
            {"cause": "驱动器电流不足", "probability": 0.20, "severity": 3},
            {"cause": "机械卡阻(异物/润滑不足)", "probability": 0.20, "severity": 2},
            {"cause": "供电电压波动", "probability": 0.10, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. 手动旋转轴确认无机械卡阻",
            "2. 检查皮带张紧度(适中，无明显松弛)",
            "3. 测量供电电压是否稳定(万用表监测)",
            "4. 听电机运行声音是否有异常噪音",
            "5. 降低转速测试是否改善(排除共振问题)",
        ],
        "quick_fix": "清理异物+补充润滑脂；紧固皮带；降低转速",
        "downtime_estimate_min": "20-45"
    },
    {
        "node_id": "S7",
        "symptom": "含水率读数异常高/低 (>±2%)",
        "priority": 2,
        "possible_causes": [
            {"cause": "AD7746探头电缆过长(>5cm)", "probability": 0.30, "severity": 4},
            {"cause": "探头极板污染/氧化", "probability": 0.25, "severity": 3},
            {"cause": "AD7746基准电容漂移", "probability": 0.20, "severity": 3},
            {"cause": "标定曲线错误(豆种不匹配)", "probability": 0.15, "severity": 3},
            {"cause": "温度影响(非补偿温度范围)", "probability": 0.10, "severity": 2},
        ],
        "diagnostic_steps": [
            "1. 检查AD7746模块与探头距离(<5cm)",
            "2. 用无水酒精清洁探头极板",
            "3. 用标准电容验证AD7746读数准确性",
            "4. 重新执行两点标定(5%和12%样本)",
            "5. 检查环境温度是否在10-40°C范围内",
        ],
        "quick_fix": "清洁探头+重新标定；缩短电缆至<5cm",
        "downtime_estimate_min": "30-50"
    },
    {
        "node_id": "S8",
        "symptom": "密度分选风速下降",
        "priority": 2,
        "possible_causes": [
            {"cause": "涡轮鼓风机叶轮积灰", "probability": 0.40, "severity": 3},
            {"cause": "进气过滤器堵塞", "probability": 0.30, "severity": 2},
            {"cause": "PWM控制信号异常", "probability": 0.15, "severity": 3},
            {"cause": "鼓风机轴承磨损", "probability": 0.15, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. 检查并清洁进气过滤器",
            "2. 用风速计测量实际风速与基准对比",
            "3. 拆卸进风口目视检查叶轮积灰程度",
            "4. 测量鼓风机供电电压和电流",
            "5. 检查ESP32 PWM输出信号(Duty Cycle)",
        ],
        "quick_fix": "清洁进气过滤器+叶轮；检查PWM信号",
        "downtime_estimate_min": "30-60"
    },
    {
        "node_id": "S9",
        "symptom": "I2C设备无法发现/通信失败",
        "priority": 1,
        "possible_causes": [
            {"cause": "I2C地址冲突(多个设备同地址)", "probability": 0.25, "severity": 3},
            {"cause": "上拉电阻缺失/损坏", "probability": 0.20, "severity": 2},
            {"cause": "杜邦线接触不良", "probability": 0.25, "severity": 2},
            {"cause": "设备I2C引脚损坏(ESD/过压)", "probability": 0.15, "severity": 4},
            {"cause": "I2C总线被GPIO占用", "probability": 0.15, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. i2cdetect -y 1 — 扫描I2C总线设备",
            "2. 逐一拔插设备定位冲突源",
            "3. 测量SDA/SCL上拉电阻(正常4.7kΩ±10%)",
            "4. 重新插拔杜邦线接头",
            "5. 检查GPIO复用配置(conflict with PWM?)",
        ],
        "quick_fix": "重新插拔杜邦线；修复上拉电阻",
        "downtime_estimate_min": "10-25"
    },
    {
        "node_id": "S10",
        "symptom": "E-STOP无法复位",
        "priority": 1,
        "possible_causes": [
            {"cause": "FAIL-SAFE继电器卡滞", "probability": 0.35, "severity": 5},
            {"cause": "E-STOP按钮机械损坏", "probability": 0.20, "severity": 4},
            {"cause": "安全回路接线断开", "probability": 0.25, "severity": 5},
            {"cause": "软件状态机卡在FAULT", "probability": 0.20, "severity": 3},
        ],
        "diagnostic_steps": [
            "1. 检查E-STOP按钮是否已旋钮释放",
            "2. 测量安全回路各节点连续性(应导通)",
            "3. 检查K1/K2/K3/K4继电器状态LED",
            "4. 重启Pi并观察启动日志",
            "5. 短接安全回路测试(仅在排查时)",
        ],
        "quick_fix": "旋转E-STOP释放+重启Pi",
        "downtime_estimate_min": "5-20"
    },
]


# =============================================================================
# SECTION 7: Run Analysis & Generate Report
# =============================================================================

def generate_maintenance_report() -> dict:
    usage = DEFAULT_USAGE
    summary = get_wear_summary(usage)
    cost = calc_annual_maintenance_cost(usage)
    spares = get_spare_parts_recommendation()

    total_spare_value = sum(s["total_value_rmb"] for s in spares)

    report = {
        "report_id": f"MAINT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "generated": datetime.now().isoformat(),
        "version": "v1.0",
        "usage_profile": cost["usage_summary"],
        "component_wear_summary": summary,
        "annual_cost_breakdown": cost,
        "spare_parts_recommendation": spares,
        "total_spare_inventory_value_rmb": round(total_spare_value, 2),
        "maintenance_schedule": [
            {
                "task": t.task,
                "frequency": t.frequency,
                "components": t.components,
                "estimated_minutes": t.estimated_minutes,
                "skill": t.skill,
                "pass_criteria": t.pass_criteria
            }
            for t in MAINTENANCE_TASKS
        ],
        "troubleshooting_tree": TROUBLESHOOTING_TREE,
    }
    return report


def print_report(report: dict):
    print("=" * 70)
    print("  HUSKY-SORTER-001 预测性维护分析报告")
    print(f"  Report ID: {report['report_id']}")
    print(f"  Generated: {report['generated']}")
    print("=" * 70)

    up = report["usage_profile"]
    print(f"\n📊 使用配置:")
    print(f"   通道数: {up['channels']} | 目标处理量: {up['beans_per_hour']:.0f} 豆/小时")
    print(f"   每日处理: {up['beans_per_day']:.0f} 豆 | 年处理量: {up['annual_output_kg']:.1f} kg/年")

    cost = report["annual_cost_breakdown"]
    print(f"\n💰 年度维护成本分析:")
    print(f"   配件成本: ¥{cost['total_annual_parts_cost_rmb']:.2f}/年")
    print(f"   停机损失: ¥{cost['downtime_cost_rmb_per_year']:.2f}/年 (按 ¥150/h)")
    print(f"   年度总成本: ¥{cost['total_annual_cost_rmb']:.2f}")
    print(f"   加权MTBF: {cost['weighted_mtbf_months']:.1f} 个月")
    print(f"\n   按类别拆分:")
    for cat, amt in cost["by_category"].items():
        print(f"     {cat}: ¥{amt:.2f}/年")

    print(f"\n🔧 组件磨损排名 (按严重性+成本):")
    print(f"   {'组件':<30} {'寿命(月)':>8} {'严重':>4} {'年成本':>10} {'备注'}")
    print(f"   {'-'*80}")
    for r in report["component_wear_summary"][:10]:
        print(f"   {r['criticality']} {r['component']:<28} {r['lifespan_months']:>7.1f} "
              f"{r['failure_severity']:>3}   ¥{r['annual_cost_rmb']:>8.2f}  {r['notes'][:40]}")

    print(f"\n📦 推荐备件库存 (总价值 ¥{report['total_spare_inventory_value_rmb']:.2f}):")
    print(f"   {'组件':<30} {'数量':>4} {'单价':>8} {'总价值':>10} {'优先级':>8}")
    print(f"   {'-'*70}")
    for s in report["spare_parts_recommendation"][:12]:
        print(f"   {s['component']:<30} {s['stock_qty']:>3}   ¥{s['unit_cost_rmb']:>6.0f}  "
              f"¥{s['total_value_rmb']:>8.2f}  {s['priority']:>8}")
    print(f"   ... 等共 {len(report['spare_parts_recommendation'])} 项")

    print(f"\n📅 维护计划概览:")
    freq_groups = {}
    for t in MAINTENANCE_TASKS:
        freq_groups.setdefault(t.frequency, []).append(t)
    for freq in ["daily", "weekly", "monthly", "quarterly", "annually"]:
        tasks = freq_groups.get(freq, [])
        if tasks:
            total_mins = sum(t.estimated_minutes for t in tasks)
            print(f"\n   {freq.upper()} ({len(tasks)}项, 约{total_mins:.0f}分钟):")
            for t in tasks[:5]:
                print(f"     • {t.task} ({t.estimated_minutes:.0f}min) — {t.components[0]}")
            if len(tasks) > 5:
                print(f"     ... 还有 {len(tasks)-5} 项")

    print(f"\n🔍 故障诊断快速索引:")
    for node in report["troubleshooting_tree"][:6]:
        print(f"\n   [{node['node_id']}] {node['symptom']}")
        top_cause = max(node["possible_causes"], key=lambda x: x["probability"])
        print(f"       最可能原因: {top_cause['cause']} (P={top_cause['probability']:.0%})")
        print(f"       快速修复: {node['quick_fix']}")
        print(f"       预计停机: {node['downtime_estimate_min']}分钟")

    print("\n" + "=" * 70)
    print("  分析完成")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    from datetime import datetime

    report = generate_maintenance_report()

    # Print to stdout
    print_report(report)

    # Save JSON report
    json_path = "predictive_maintenance_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 JSON报告已保存: {json_path}")

    print("\n✅ 预测性维护分析完成!")
    print(f"   关键发现:")
    print(f"   • 年度配件成本 ¥{report['annual_cost_breakdown']['total_annual_parts_cost_rmb']:.2f}")
    print(f"   • 备件库存建议 ¥{report['total_spare_inventory_value_rmb']:.2f} (一次投入)")
    print(f"   • 预计年停机 {report['annual_cost_breakdown']['estimated_downtime_hours_per_year']:.1f} 小时")
    print(f"   • 最高风险组件: 空压机⚠️ / HQ相机⚠️ / 涡轮鼓风机⚠️ (均为进口件, 交付周期长)")
