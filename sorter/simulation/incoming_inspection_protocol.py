#!/usr/bin/env python3
"""
Incoming Goods Inspection & Hardware Integration Test Protocol
生豆分选机 — 来料检验 + 硬件集成测试
============================================================
版本: v1.0 | 2026-05-05
目标: 硬件到位后，按本协议执行验收与集成测试

Usage:
    python3 incoming_inspection_protocol.py --test all
    python3 incoming_inspection_protocol.py --test electrical
    python3 incoming_inspection_protocol.py --test sensors
    python3 incoming_inspection_protocol.py --test actuators
    python3 incoming_inspection_protocol.py --test integration
    python3 incoming_inspection_protocol.py --report

Output:
    inspection_report_YYYYMMDD_HHMM.json
    inspection_report_YYYYMMDD_HHMM.html
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class InspectionItem:
    """单个检验项目"""
    id: str
    category: str          # electrical/mechanical/sensor/actuator/integration
    name: str
    description: str
    test_method: str
    pass_threshold: str
    result: Optional[str] = None   # PASS/FAIL/NA/WARN
    measured_value: Optional[str] = None
    notes: Optional[str] = None
    tested_at: Optional[str] = None

@dataclass
class ComponentInspection:
    """单个组件来料检验记录"""
    component_id: str
    component_name: str
    supplier: str
    order_date: str
    expected_delivery: str
    actual_delivery: Optional[str] = None
    items: list = field(default_factory=list)
    overall_result: Optional[str] = None
    notes: str = ""

# ============================================================================
# Test Items Definition
# ============================================================================

def get_electrical_tests() -> list[InspectionItem]:
    """电气安全与供电测试"""
    return [
        InspectionItem(
            id="E-01", category="electrical",
            name="电源适配器规格验证",
            description="12V适配器输出规格检查",
            test_method="万用表测量输出电压",
            pass_threshold="12V ±5% (11.4-12.6V)"
        ),
        InspectionItem(
            id="E-02", category="electrical",
            name="电源线极性检查",
            description="12V DCJack正负极正确性",
            test_method="万用表二极管档测试",
            pass_threshold="中心正极，外壳负极"
        ),
        InspectionItem(
            id="E-03", category="electrical",
            name="Pi USB-C 5V输出验证",
            description="Pi 4 USB-C接口输出能力",
            test_method="USB电压电流表测量",
            pass_threshold="5V ±5% (4.75-5.25V)"
        ),
        InspectionItem(
            id="E-04", category="electrical",
            name="GPIO引脚对地电阻",
            description="所有GPIO引脚对地短路检查",
            test_method="万用表二极管档，对每pin对GND测试",
            pass_threshold=">1kΩ（无短路）"
        ),
        InspectionItem(
            id="E-05", category="electrical",
            name="GPIO引脚间电阻",
            description="相邻GPIO引脚间无短路",
            test_method="万用表连续性测试相邻引脚对",
            pass_threshold=">10kΩ（无短路）"
        ),
        InspectionItem(
            id="E-06", category="electrical",
            name="I2C总线SDA/SCL上拉电阻",
            description="I2C总线有上拉电阻（4.7kΩ或10kΩ）",
            test_method="万用表测量SDA/SCL对3.3V",
            pass_threshold="4.7kΩ - 10kΩ"
        ),
        InspectionItem(
            id="E-07", category="electrical",
            name="12V供电隔离检查",
            description="12V供电与GPIO控制信号光电隔离",
            test_method="目视光耦确认 + 万用表隔离测试（>1MΩ）",
            pass_threshold="控制侧与功率侧隔离电阻 >1MΩ"
        ),
        InspectionItem(
            id="E-08", category="electrical",
            name="E-STOP安全回路连续性",
            description="E-STOP安全链接线正确性",
            test_method="万用表连续性档测试安全链两端电阻",
            pass_threshold="<5Ω（正常），触发后无限大"
        ),
        InspectionItem(
            id="E-09", category="electrical",
            name="FAIL-SAFE继电器接线验证",
            description="K1/K2/K3/K4 FAIL-SAFE继电器接线正确",
            test_method="继电器断电验证常闭触点导通",
            pass_threshold="NC触点<1Ω（未通电状态）"
        ),
        InspectionItem(
            id="E-10", category="electrical",
            name="接地连续性",
            description="机壳接地端子接地连续性",
            test_method="万用表连续性档对接地端子与接地插头",
            pass_threshold="<0.5Ω"
        ),
    ]

def get_mechanical_tests() -> list[InspectionItem]:
    """机械结构检验"""
    return [
        InspectionItem(
            id="M-01", category="mechanical",
            name="3D打印件外观检查",
            description="检查所有3D打印件无明显层纹/拉丝/粘附",
            test_method="目视检查所有打印件外表面",
            pass_threshold="无明显缺陷，影响功能的缺陷=FAIL"
        ),
        InspectionItem(
            id="M-02", category="mechanical",
            name="尺寸分选孔板孔径精度",
            description="5级孔板孔径是否在±0.2mm以内",
            test_method="游标卡尺测量各级孔径",
            pass_threshold="标称±0.2mm内"
        ),
        InspectionItem(
            id="M-03", category="mechanical",
            name="缓冲仓8格分隔板密封性",
            description="缓冲仓各格间无漏豆",
            test_method="注入100g豆子，静置2分钟，检查渗漏",
            pass_threshold="无豆子从相邻格渗出"
        ),
        InspectionItem(
            id="M-04", category="mechanical",
            name="螺旋给料器螺纹同轴度",
            description="螺旋轴与电机轴同轴连接",
            test_method="手动旋转无卡滞，轴向间隙<0.5mm",
            pass_threshold="旋转顺畅，无明显偏心"
        ),
        InspectionItem(
            id="M-05", category="mechanical",
            name="振动给料碗平衡性",
            description="振动给料碗安装水平，无偏重",
            test_method="注豆前后观察振动模式是否稳定",
            pass_threshold="振动模式稳定，无特定方向偏移"
        ),
        InspectionItem(
            id="M-06", category="mechanical",
            name="气喷嘴对心检查",
            description="电磁阀→气喷嘴气路对中",
            test_method="手动触发气喷，肉眼观察气流方向",
            pass_threshold="气流方向指向单文件通道中心"
        ),
        InspectionItem(
            id="M-07", category="mechanical",
            name="透明底部窗口安装密封",
            description="磨砂亚克力窗口安装无气泡，密封胶完整",
            test_method="目视检查边缘密封，纸巾测试气流",
            pass_threshold="无气泡，纸巾靠近不被气流吹动（不漏气）"
        ),
        InspectionItem(
            id="M-08", category="mechanical",
            name="暗箱遮光检查",
            description="相机暗箱遮光棉安装完整",
            test_method="关灯后进入暗箱，手电外照检查漏光点",
            pass_threshold="无明显漏光点（相机区全黑）"
        ),
        InspectionItem(
            id="M-09", category="mechanical",
            name="LED光源安装角度",
            description="环形LED光源角度一致，漫反射效果均匀",
            test_method="给标准白板拍照，检查亮度均匀性",
            pass_threshold="四角亮度差异<20%（目视对比）"
        ),
        InspectionItem(
            id="M-10", category="mechanical",
            name="步进电机固定螺栓扭矩",
            description="Nema17/28BYJ-48电机安装螺栓扭矩检查",
            test_method="螺丝刀手感检查，无松动",
            pass_threshold="无松动，手拧不动"
        ),
    ]

def get_sensor_tests() -> list[InspectionItem]:
    """传感器模块测试"""
    return [
        InspectionItem(
            id="S-01", category="sensor",
            name="HX711称重传感器零点稳定性",
            description="无负载时HX711读数稳定性",
            test_method="连续读取100次，计算标准差",
            pass_threshold="标准差<5个LSB（无振动环境）"
        ),
        InspectionItem(
            id="S-02", category="sensor",
            name="HX711称重线性度",
            description="标准砝码100g/200g/500g测量线性误差",
            test_method="依次加载100g/200g/500g砝码，记录读数",
            pass_threshold="线性误差<50mg"
        ),
        InspectionItem(
            id="S-03", category="sensor",
            name="AD7746含水率探头基线电容",
            description="空载时AD7746电容读数稳定性",
            test_method="连续读取50次，计算均值和标准差",
            pass_threshold="均值<5pF，标准差<0.1pF"
        ),
        InspectionItem(
            id="S-04", category="sensor",
            name="AD7746含水率分辨率验证",
            description="注入已知含水率样本验证分辨率",
            test_method="用酒精+水配比验证（精度目标0.1%）",
            pass_threshold="分辨率<0.3%"
        ),
        InspectionItem(
            id="S-05", category="sensor",
            name="光电传感器T1/T2遮挡响应",
            description="T1/T2红外光电传感器遮挡响应时间",
            test_method="示波器测量遮挡到GPIO信号变化延迟",
            pass_threshold="<1ms响应时间"
        ),
        InspectionItem(
            id="S-06", category="sensor",
            name="光电传感器T1/T2距离特性",
            description="验证T1/T2在标定距离（~20mm）触发",
            test_method="用豆子通过，验证可靠触发",
            pass_threshold="豆子通过时稳定触发，无漏检"
        ),
        InspectionItem(
            id="S-07", category="sensor",
            name="Top Camera分辨率测试",
            description="HQ Camera IMX477拍摄分辨率标定板",
            test_method="拍摄ISO 12233标定板，测量分辨率",
            pass_threshold="中心分辨率>800 LW/PH"
        ),
        InspectionItem(
            id="S-08", category="sensor",
            name="Top Camera色彩准确性",
            description="白平衡和色彩准确性",
            test_method="拍摄X-Rite ColorChecker，测量Delta E",
            pass_threshold="平均Delta E<5.0"
        ),
        InspectionItem(
            id="S-09", category="sensor",
            name="Bottom Camera分辨率测试",
            description="USB Camera拍摄分辨率测试",
            test_method="拍摄分辨率标定板，测量分辨率",
            pass_threshold=">600 LW/PH"
        ),
        InspectionItem(
            id="S-10", category="sensor",
            name="Top/Bottom Camera同步触发",
            description="同一豆子通过时top+bottom均触发拍摄",
            test_method="注入20颗豆子，检查top+bottom图像对数量",
            pass_threshold="20对图像（无缺失，无多余）"
        ),
        InspectionItem(
            id="S-11", category="sensor",
            name="密度风速传感器校准",
            description="风速传感器在目标风速（4m/s）的读数准确性",
            test_method="标准风速计对比读数",
            pass_threshold="读数误差<±0.2m/s"
        ),
        InspectionItem(
            id="S-12", category="sensor",
            name="气压传感器读数",
            description="气压传感器PSI读数准确性",
            test_method="与空压机表头读数对比",
            pass_threshold="误差<±2 PSI"
        ),
        InspectionItem(
            id="S-13", category="sensor",
            name="I2C设备发现检查",
            description="Pi上电后能发现所有I2C设备",
            test_method="i2cdetect -y 1",
            pass_threshold="0x68(HX711)/0x5A(AD7746)/0x76(BMP280)全部可见"
        ),
    ]

def get_actuator_tests() -> list[InspectionItem]:
    """执行器测试"""
    return [
        InspectionItem(
            id="A-01", category="actuator",
            name="电磁阀响应时间",
            description="AirJet电磁阀通断响应时间",
            test_method="示波器测量GPIO触发到气压变化延迟",
            pass_threshold="<50ms（通电到气压建立）"
        ),
        InspectionItem(
            id="A-02", category="actuator",
            name="电磁阀保压能力",
            description="电磁阀关闭后保压10秒压降",
            test_method="关闭后记录气压表，10秒后再次记录",
            pass_threshold="压降<5 PSI（保压良好）"
        ),
        InspectionItem(
            id="A-03", category="actuator",
            name="Nema17步进电机单步响应",
            description="单脉冲测试步进电机转动",
            test_method="发送1个脉冲，测量转动角度",
            pass_threshold="1脉冲=1.8°±5%（无丢步）"
        ),
        InspectionItem(
            id="A-04", category="actuator",
            name="28BYJ-48步进电机原点复位",
            description="电机复位到原点传感器位置",
            test_method="发送20个脉冲，观察是否能触发原点传感器",
            pass_threshold="20脉冲内触发原点传感器"
        ),
        InspectionItem(
            id="A-05", category="actuator",
            name="振动给料器频率范围",
            description="振动给料器频率可调范围验证",
            test_method="调节频率10-60Hz，验证振动强度变化",
            pass_threshold="10Hz无振动，60Hz强振动，可控"
        ),
        InspectionItem(
            id="A-06", category="actuator",
            name="称重杯释放机构响应",
            description="称重杯释放电磁阀动作",
            test_method="触发释放，验证称重杯打开",
            pass_threshold="<200ms响应"
        ),
        InspectionItem(
            id="A-07", category="actuator",
            name="缓冲仓旋转阀位置",
            description="缓冲仓旋转阀能准确定位8个格子",
            test_method="连续旋转8次，每次验证位置传感器触发",
            pass_threshold="8次旋转均准确定位"
        ),
        InspectionItem(
            id="A-08", category="actuator",
            name="FAIL-SAFE继电器安全测试",
            description="模拟故障时继电器能正确失电",
            test_method="断开安全回路，验证所有执行器断电",
            pass_threshold="所有执行器在安全回路断开时立即断电"
        ),
        InspectionItem(
            id="A-09", category="actuator",
            name="E-STOP急停测试",
            description="触发E-STOP，系统立即停止所有执行器",
            test_method="运行中按下E-STOP按钮",
            pass_threshold="<100ms内所有执行器停止"
        ),
    ]

def get_integration_tests() -> list[InspectionItem]:
    """系统集成测试"""
    return [
        InspectionItem(
            id="I-01", category="integration",
            name="GPIO状态上电自检",
            description="所有GPIO引脚上电初始化状态正确",
            test_method="运行POST自检，查看GPIO状态",
            pass_threshold="POST: GPIO 8项全部PASS"
        ),
        InspectionItem(
            id="I-02", category="integration",
            name="MQTT连接测试",
            test_method="启动MQTT broker，验证Pi能连接并订阅主题",
            description="MQTT broker启动后Pi客户端能连接",
            pass_threshold="连接延迟<2s，订阅成功"
        ),
        InspectionItem(
            id="I-03", category="integration",
            name="REST API响应测试",
            description="Flask API各端点响应",
            test_method="curl测试12个REST端点",
            pass_threshold="所有端点返回200/JSON有效响应"
        ),
        InspectionItem(
            id="I-04", category="integration",
            name="Dashboard启动测试",
            description="Tkinter Dashboard正常启动",
            test_method="运行dashboard.py，观察窗口",
            pass_threshold="1280×800窗口启动，状态显示正常"
        ),
        InspectionItem(
            id="I-05", category="integration",
            name="单粒完整流程测试（模拟模式）",
            description="BeanSimulator注入模拟豆，验证全流程",
            test_method="运行dashboard + BeanSimulator，50bpm×2分钟",
            pass_threshold="数据流完整：传感器→推理→分类→DB记录"
        ),
        InspectionItem(
            id="I-06", category="integration",
            name="缺陷检出率验证（模拟模式）",
            description="模拟缺陷豆验证融合检出率",
            test_method="注入50颗模拟豆（20%缺陷），统计检出",
            pass_threshold="缺陷召回率>80%（融合算法）"
        ),
        InspectionItem(
            id="I-07", category="integration",
            name="数据库写入验证",
            description="批次数据正确写入SQLite",
            test_method="运行测试批次后查询数据库",
            pass_threshold="batches/beans表记录数量与实际一致"
        ),
        InspectionItem(
            id="I-08", category="integration",
            name="健康监控告警触发",
            description="健康监控系统能正确检测异常",
            test_method="模拟传感器异常（断开I2C），观察告警",
            pass_threshold="CRITICAL/OFFLINE告警正确触发"
        ),
        InspectionItem(
            id="I-09", category="integration",
            name="报表生成功能",
            description="report_generator正确生成JSON/CSV/TEXT报告",
            test_method="运行报表生成命令",
            pass_threshold="3种格式均生成，内容完整"
        ),
        InspectionItem(
            id="I-10", category="integration",
            name="空压机噪声测试",
            description="空压机运行时噪声水平",
            test_method="分贝计在1m处测量",
            pass_threshold="<70dB（工作区噪声标准）"
        ),
        InspectionItem(
            id="I-11", category="integration",
            name="连续运行稳定性（1小时）",
            description="系统连续运行1小时无故障",
            test_method="空载运行1小时，监控系统状态",
            pass_threshold="0次FAULT，无内存泄漏"
        ),
        InspectionItem(
            id="I-12", category="integration",
            name="吞吐量实测",
            description="实际处理量达到目标",
            test_method="注入1kg豆子，计时测量处理量",
            pass_threshold="≥2.0kg/h（单通道@50bpm）"
        ),
    ]

# ============================================================================
# Test Runner (Simulated — for hardware not yet arrived)
# ============================================================================

def run_simulated_tests(component: str, items: list[InspectionItem]) -> list[InspectionItem]:
    """模拟运行测试（硬件未到位时使用）"""
    import random

    # 真实硬件未到位，模拟测试结果用于文档验证
    # 实际使用时删除此函数，改用真实测量
    simulated_results = {
        "PASS": 0.85,   # 85% items pass in simulation
        "WARN": 0.10,
        "FAIL": 0.05,
        "NA":   0.00,
    }

    for item in items:
        item.tested_at = datetime.now().isoformat()
        roll = random.random()

        if roll < simulated_results["PASS"]:
            item.result = "PASS"
        elif roll < simulated_results["PASS"] + simulated_results["WARN"]:
            item.result = "WARN"
            item.notes = "仿真环境：真实硬件未到位，模拟值"
        elif roll < simulated_results["PASS"] + simulated_results["WARN"] + simulated_results["FAIL"]:
            item.result = "FAIL"
            item.notes = "⚠️ 需硬件到位后重新测试"
            item.measured_value = "N/A (hardware not arrived)"
        else:
            item.result = "NA"
            item.notes = "不适用"

    return items

# ============================================================================
# Report Generation
# ============================================================================

def generate_report(
    electrical: list,
    mechanical: list,
    sensors: list,
    actuators: list,
    integration: list,
    output_format: str = "json"
) -> dict:
    """生成检验报告"""

    all_items = electrical + mechanical + sensors + actuators + integration

    def count_results(items):
        passed = sum(1 for i in items if i.result == "PASS")
        warned = sum(1 for i in items if i.result == "WARN")
        failed = sum(1 for i in items if i.result == "FAIL")
        na = sum(1 for i in items if i.result == "NA")
        return passed, warned, failed, na, len(items)

    categories = {
        "electrical": electrical,
        "mechanical": mechanical,
        "sensors": sensors,
        "actuators": actuators,
        "integration": integration,
    }

    report = {
        "report_id": f"INSP-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "generated_at": datetime.now().isoformat(),
        "equipment": "HUSKY-SORTER-001 生豆分选机",
        "protocol_version": "v1.0",
        "hardware_arrival_date": "PENDING",  # To be filled when hardware arrives
        "tester": "TBD",
        "categories": {},
        "overall_summary": {},
    }

    total_pass, total_warn, total_fail, total_na, total_items = 0, 0, 0, 0, 0
    category_summaries = []

    for cat_name, cat_items in categories.items():
        p, w, f, na, n = count_results(cat_items)
        total_pass += p; total_warn += w; total_fail += f; total_na += na; total_items += n

        cat_result = "PASS" if f == 0 else ("WARN" if w > 0 else "FAIL")
        category_summaries.append(cat_result)

        report["categories"][cat_name] = {
            "result": cat_result,
            "items_total": n,
            "passed": p,
            "warned": w,
            "failed": f,
            "na": na,
            "pass_rate": f"{p/n*100:.1f}%",
            "test_items": [asdict(item) for item in cat_items]
        }

    overall_result = "PASS" if total_fail == 0 else ("WARN" if total_fail <= 2 else "FAIL")

    report["overall_summary"] = {
        "result": overall_result,
        "total_items": total_items,
        "passed": total_pass,
        "warned": total_warn,
        "failed": total_fail,
        "na": total_na,
        "overall_pass_rate": f"{total_pass/(total_items-total_na)*100:.1f}%",
        "test_duration_minutes": 0,  # Will be filled by real run
        "categories_summary": dict(zip(categories.keys(), category_summaries)),
    }

    return report

def print_summary(report: dict):
    """打印报告摘要"""
    print("\n" + "="*70)
    print(f"  HUSKY-SORTER-001 来料检验报告")
    print(f"  Report ID: {report['report_id']}")
    print(f"  生成时间: {report['generated_at'][:19]}")
    print("="*70)

    summary = report["overall_summary"]
    print(f"\n  总体结果: 【{summary['result']}】")
    print(f"  总计 {summary['total_items']} 项 | "
          f"✅ {summary['passed']} | "
          f"⚠️ {summary['warned']} | "
          f"❌ {summary['failed']} | "
          f"— {summary['na']}")
    print(f"  通过率: {summary['overall_pass_rate']}")

    print("\n  分类结果:")
    for cat, data in report["categories"].items():
        emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(data["result"], "?")
        print(f"    {emoji} [{cat:12s}] {data['result']:4s}  "
              f"{data['passed']:2d}/{data['items_total']:2d}项 "
              f"({data['pass_rate']})")

    # Show failed items
    failed = []
    for cat, data in report["categories"].items():
        for item in data["test_items"]:
            if item["result"] == "FAIL":
                failed.append(f"  ❌ {item['id']}: {item['name']} — {item['notes']}")

    if failed:
        print("\n  失败项 (FAIL):")
        for f in failed:
            print(f)

    warn_items = []
    for cat, data in report["categories"].items():
        for item in data["test_items"]:
            if item["result"] == "WARN":
                warn_items.append(f"  ⚠️ {item['id']}: {item['name']}")

    if warn_items:
        print("\n  警告项 (WARN):")
        for w in warn_items:
            print(w)

    print("\n" + "="*70)

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="HUSKY-SORTER-001 来料检验协议"
    )
    parser.add_argument("--test", default="all",
                        choices=["all", "electrical", "mechanical", "sensors", "actuators", "integration"],
                        help="选择测试类别")
    parser.add_argument("--report", action="store_true", help="生成检验报告")
    parser.add_argument("--output", default="inspection_report",
                        help="报告输出文件名前缀")
    args = parser.parse_args()

    print("HUSKY-SORTER-001 来料检验协议 v1.0")
    print("="*50)
    print("⚠️  注意：当前为模拟模式（硬件未到位）")
    print("    硬件到位后，运行真实测量并更新结果")
    print("="*50)

    electrical = get_electrical_tests()
    mechanical = get_mechanical_tests()
    sensors = get_sensor_tests()
    actuators = get_actuator_tests()
    integration = get_integration_tests()

    if args.test in ("all", "electrical"):
        print(f"\n[电气测试] 共{len(electrical)}项...")
        run_simulated_tests("electrical", electrical)

    if args.test in ("all", "mechanical"):
        print(f"\n[机械测试] 共{len(mechanical)}项...")
        run_simulated_tests("mechanical", mechanical)

    if args.test in ("all", "sensors"):
        print(f"\n[传感器测试] 共{len(sensors)}项...")
        run_simulated_tests("sensors", sensors)

    if args.test in ("all", "actuators"):
        print(f"\n[执行器测试] 共{len(actuators)}项...")
        run_simulated_tests("actuators", actuators)

    if args.test in ("all", "integration"):
        print(f"\n[集成测试] 共{len(integration)}项...")
        run_simulated_tests("integration", integration)

    report = generate_report(electrical, mechanical, sensors, actuators, integration)

    if args.report or args.test == "all":
        output_file = f"{args.output}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 报告已保存: {output_file}")

    print_summary(report)

    # Return exit code based on result
    if report["overall_summary"]["failed"] > 2:
        return 2  # Critical failure
    elif report["overall_summary"]["failed"] > 0:
        return 1  # Some failures
    return 0

if __name__ == "__main__":
    sys.exit(main())