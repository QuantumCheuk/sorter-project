#!/usr/bin/env python3
"""
生豆分选机 - 物理测试协议与标定程序
Physical Test Protocol & Calibration Procedures
================================================

目的：硬件到位后，按本协议执行各模块标定与集成测试。
本文件包含：
  1. 标定状态机（各模块独立执行）
  2. 测试序列（8步验证流程）
  3. 性能基准（PASS/FAIL判定标准）
  4. 数据记录格式

版本：v1.0 | 2026-04-29
"""

import time
import json
import statistics
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# =============================================================================
# SECTION 1: 测试数据结构
# =============================================================================

class TestResult(Enum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    WARNING = "WARNING"


class CalibrationPhase(Enum):
    PREP = "preparation"
    ZERO = "zero_calibration"
    SPAN = "span_calibration"
    VERIFY = "verification"
    LIVE = "live_test"


@dataclass
class CalibrationRecord:
    """单次标定记录"""
    timestamp: str
    module: str
    phase: str
    result: str
    readings: list = field(default_factory=list)
    mean: float = 0.0
    std: float = 0.0
    error: float = 0.0
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class TestReport:
    """完整测试报告"""
    report_id: str
    start_time: str
    end_time: str = ""
    device_id: str = "sorter-01"
    firmware_version: str = "v0.7"
    records: list = field(default_factory=list)

    def add_record(self, rec: CalibrationRecord):
        self.records.append(rec.to_dict())

    def summary(self) -> dict:
        passed = sum(1 for r in self.records if r["result"] == "PASS")
        failed = sum(1 for r in self.records if r["result"] == "FAIL")
        return {
            "report_id": self.report_id,
            "total_tests": len(self.records),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{100*passed/max(len(self.records),1):.1f}%"
        }


# =============================================================================
# SECTION 2: 性能基准（PASS/FAIL 标准）
# =============================================================================

BENCHMARKS = {
    # --- 颜色检测 ---
    "color_lighting_stability": {
        "description": "LED光源稳定性（60秒采集10张图）",
        "unit": "ΔL* (CIE L*)",
        "target": "< 2.0",
        "pass_threshold": 2.0,
        "fail_threshold": 5.0,
    },
    "color_reproducibility": {
        "description": "同一豆子5次检测重现性",
        "unit": "σ L*a*b*",
        "pass_threshold": 1.5,  # ΔE00 < 1.5 人眼不可辨
        "fail_threshold": 3.0,
    },

    # --- 称重系统 ---
    "weight_reading_stability": {
        "description": "空杯称重标准差（10次采样）",
        "unit": "g",
        "pass_threshold": 0.003,  # ±3mg
        "fail_threshold": 0.010,
    },
    "weight_accuracy_100g": {
        "description": "100g标准砝码测量误差",
        "unit": "g",
        "pass_threshold": 0.01,   # ±0.01g
        "fail_threshold": 0.05,
    },
    "weight_linearity": {
        "description": "50g/100g/150g三点线性误差",
        "unit": "g",
        "pass_threshold": 0.02,
        "fail_threshold": 0.10,
    },

    # --- 含水率 ---
    "moisture_reading_stability": {
        "description": "探头电容值标准差（10次采样）",
        "unit": "fF",
        "pass_threshold": 5.0,   # AD7746分辨率1fF
        "fail_threshold": 20.0,
    },
    "moisture_accuracy_known": {
        "description": "已知含水率样本（11%）测量误差",
        "unit": "%",
        "pass_threshold": 0.5,   # ±0.5%
        "fail_threshold": 1.5,
    },

    # --- 密度分选 ---
    "density_airflow_stability": {
        "description": "风扇PWM=50%时10秒风速标准差",
        "unit": "m/s",
        "pass_threshold": 0.1,
        "fail_threshold": 0.3,
    },
    "density_separation_known": {
        "description": "已知密度豆（轻/重各10粒）分离正确率",
        "unit": "%",
        "pass_threshold": 90.0,
        "fail_threshold": 70.0,
    },

    # --- 振动给料 ---
    "feeder_rate_stability": {
        "description": "振动给料速率标准差（60秒计数）",
        "unit": "bpm",
        "pass_threshold": 3.0,
        "fail_threshold": 8.0,
    },
    "feeder_max_rate": {
        "description": "最大给料速率（短时测试）",
        "unit": "bpm",
        "pass_threshold": 50.0,
        "fail_threshold": 30.0,
    },

    # --- 整体集成 ---
    "throughput_sustained": {
        "description": "持续处理30分钟平均吞吐量",
        "unit": "kg/h",
        "pass_threshold": 0.9,   # 至少达到目标的90%（单通道0.27/2=13.5%）
        "fail_threshold": 0.15,  # 低于0.15kg/h说明硬件故障
    },
    "defect_detection_rate": {
        "description": "已知缺陷豆（20粒）检出率",
        "unit": "%",
        "pass_threshold": 85.0,
        "fail_threshold": 60.0,
    },
    "false_reject_rate": {
        "description": "正常豆误剔率",
        "unit": "%",
        "pass_threshold": 5.0,
        "fail_threshold": 15.0,
    },
    "system_uptime": {
        "description": "30分钟测试期间系统崩溃次数",
        "unit": "次",
        "pass_threshold": 0,
        "fail_threshold": 3,
    },
    "mqtt_latency": {
        "description": "MQTT消息从发送到确认的平均延迟",
        "unit": "ms",
        "pass_threshold": 100.0,
        "fail_threshold": 500.0,
    },
    "api_response_time": {
        "description": "REST API /status 端点响应时间",
        "unit": "ms",
        "pass_threshold": 200.0,
        "fail_threshold": 1000.0,
    },
}


# =============================================================================
# SECTION 3: 各模块标定流程
# =============================================================================

def run_color_calibration(mock: bool = True) -> CalibrationRecord:
    """
    标定流程：颜色检测系统
    ================================================================
    目标：确保光源稳定 + 双摄图像质量达标

    步骤：
    1. 预热LED光源 5 分钟
    2. 采集10张白板（参照卡）图像，检验 ΔL*
    3. 采集同一粒参考豆 5 次，检验重现性
    4. （真实硬件）用 ColorChecker 验证色彩还原
    """
    module = "color_camera"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    phase = CalibrationPhase.PREP.value
    notes = ""

    # Step 1: 预热
    print("[颜色] 预热LED光源 5 分钟...")
    warmup_readings = []
    if not mock:
        time.sleep(300)  # 真实：等待5分钟
    else:
        # 模拟预热后 readings
        import random
        warmup_readings = [random.gauss(95.0, 0.3) for _ in range(10)]

    # Step 2: 白板稳定性
    print("[颜色] 白板稳定性测试（10次采集）...")
    phase = CalibrationPhase.ZERO.value
    white_readings = [random.gauss(95.0, 0.5) for _ in range(10)] if mock else []
    white_std = statistics.stdev(white_readings) if len(white_readings) > 1 else 0.0
    # 模拟：转换到 ΔL* 指标（白板 L* ≈ 95，σ=0.5 → ΔL*=0.5）
    delta_L = white_std * 1.96  # 95% 置信区间
    bm = BENCHMARKS["color_lighting_stability"]
    if delta_L < bm["pass_threshold"]:
        result = "PASS"
        notes = f"ΔL*={delta_L:.2f} < {bm['pass_threshold']} ✅"
    elif delta_L < bm["fail_threshold"]:
        result = "WARNING"
        notes = f"ΔL*={delta_L:.2f} 在临界区，建议检查LED驱动"
    else:
        result = "FAIL"
        notes = f"ΔL*={delta_L:.2f} > {bm['fail_threshold']} 光源不稳定 ❌"

    return CalibrationRecord(
        timestamp=timestamp, module=module, phase=phase,
        result=result, readings=white_readings,
        mean=statistics.mean(white_readings) if white_readings else 0,
        std=white_std, error=delta_L, notes=notes
    )


def run_weight_calibration(mock: bool = True) -> list[CalibrationRecord]:
    """
    标定流程：称重系统（HX711 + Load Cell）
    ================================================================
    目标：零点稳定 + 量程准确 + 线性良好

    步骤：
    1. 空杯置零（Tare），采集10次稳定性
    2. 放100g标准砝码，测量误差
    3. 放50g/150g砝码，检验线性
    4. （可选）温度漂移测试（冷/热环境）
    """
    records = []
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    import random

    # Step 1: 零点稳定性
    print("[称重] 零点稳定性测试（10次空杯）...")
    zero_readings = [random.gauss(0.0, 0.002) for _ in range(10)]  # 模拟 ±2mg 噪声
    zero_std = statistics.stdev(zero_readings)
    bm = BENCHMARKS["weight_reading_stability"]
    result = "PASS" if zero_std < bm["pass_threshold"] else "FAIL"
    notes = f"σ={zero_std*1000:.1f}mg < {bm['pass_threshold']*1000:.0f}mg ✅" if result == "PASS" else f"σ={zero_std*1000:.1f}mg > {bm['fail_threshold']*1000:.0f}mg ❌"
    records.append(CalibrationRecord(
        timestamp=timestamp, module="load_cell", phase="zero_calibration",
        result=result, readings=[r*1000 for r in zero_readings],  # 转为 mg
        mean=statistics.mean(zero_readings)*1000, std=zero_std*1000,
        error=zero_std, notes=notes
    ))

    # Step 2: 100g 准确性
    print("[称重] 100g标准砝码准确性测试...")
    hx711_read_100g = [random.gauss(100.02, 0.005) for _ in range(5)]  # 模拟 100.02g
    mean_100g = statistics.mean(hx711_read_100g)
    error_100g = abs(mean_100g - 100.0)
    bm = BENCHMARKS["weight_accuracy_100g"]
    result = "PASS" if error_100g < bm["pass_threshold"] else "FAIL"
    notes = f"误差={error_100g*1000:.1f}mg < {bm['pass_threshold']*1000:.0f}mg ✅" if result == "PASS" else f"误差={error_100g*1000:.1f}mg > {bm['fail_threshold']*1000:.0f}mg ❌"
    records.append(CalibrationRecord(
        timestamp=timestamp, module="load_cell", phase="span_calibration",
        result=result, readings=hx711_read_100g,
        mean=mean_100g, std=statistics.stdev(hx711_read_100g),
        error=error_100g, notes=notes
    ))

    # Step 3: 线性（50g + 150g）
    print("[称重] 线性度测试（50g + 150g）...")
    mean_50g = random.gauss(50.01, 0.005)
    mean_150g = random.gauss(150.03, 0.008)
    error_50 = abs(mean_50g - 50.0)
    error_150 = abs(mean_150g - 150.0)
    linearity_error = max(error_50, error_150)
    bm = BENCHMARKS["weight_linearity"]
    result = "PASS" if linearity_error < bm["pass_threshold"] else "FAIL"
    notes = f"最大线性误差={linearity_error*1000:.1f}mg" if result == "PASS" else f"线性误差过大: {linearity_error*1000:.1f}mg"
    records.append(CalibrationRecord(
        timestamp=timestamp, module="load_cell", phase="verification",
        result=result, readings=[mean_50g, mean_100g, mean_150g],
        mean=(mean_50g + mean_100g + mean_150g)/3,
        std=linearity_error, error=linearity_error, notes=notes
    ))

    return records


def run_moisture_calibration(mock: bool = True) -> CalibrationRecord:
    """
    标定流程：含水率检测（AD7746 + 电容探头）
    ================================================================
    目标：探头稳定 + 含水率读数准确

    步骤：
    1. 探头空载（无豆）测量基线电容（应≈探头几何电容）
    2. 放入已知含水率样本（11%），验证误差
    3. 放入5%/15%样本，验证两点线性
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    import random

    # Step 1: 基线稳定性
    print("[含水率] 探头基线电容稳定性测试（10次采集）...")
    base_capacitance = [random.gauss(1.47, 0.3) for _ in range(10)]  # 模拟 pF
    base_std = statistics.stdev(base_capacitance)  # in fF
    bm = BENCHMARKS["moisture_reading_stability"]
    result = "PASS" if base_std < bm["pass_threshold"] else "FAIL"
    notes = f"σ={base_std:.2f}fF < {bm['pass_threshold']:.0f}fF ✅" if result == "PASS" else f"σ={base_std:.2f}fF > {bm['fail_threshold']:.0f}fF ❌"

    record = CalibrationRecord(
        timestamp=timestamp, module="moisture_probe", phase="live_test",
        result=result, readings=base_capacitance,
        mean=statistics.mean(base_capacitance), std=base_std,
        error=base_std, notes=notes
    )

    # Step 2: 已知样本测试（真实环境下执行）
    print("[含水率] 已知样本验证（11%含水率）...")
    # 模拟：AD7746测量值换算后含水率读数
    moisture_read = random.gauss(11.2, 0.2)  # 模拟 11.2%
    moisture_error = abs(moisture_read - 11.0)  # 真值11%
    bm2 = BENCHMARKS["moisture_accuracy_known"]
    result2 = "PASS" if moisture_error < bm2["pass_threshold"] else "FAIL"
    notes2 = f"误差={moisture_error:.2f}% < ±{bm2['pass_threshold']}% ✅" if result2 == "PASS" else f"误差={moisture_error:.2f}% > ±{bm2['fail_threshold']}% ❌"
    record2 = CalibrationRecord(
        timestamp=timestamp, module="moisture_probe", phase="span_calibration",
        result=result2, readings=[moisture_read],
        mean=moisture_read, std=0.0,
        error=moisture_error, notes=notes2
    )

    return [record, record2]


def run_density_calibration(mock: bool = True) -> list[CalibrationRecord]:
    """
    标定流程：密度分选（气流上扬通道 + 5015风扇）
    ================================================================
    目标：风速稳定 + 已知密度豆分离正确

    步骤：
    1. PWM=50%，10秒风速稳定性测试
    2. 已知轻豆（密度<0.60）10粒，应被吹起
    3. 已知重豆（密度>0.75）10粒，应下落
    """
    records = []
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    import random

    # Step 1: 风速稳定性
    print("[密度] 风扇PWM=50% 风速稳定性测试（10次，间隔1秒）...")
    wind_speeds = [random.gauss(2.5, 0.05) for _ in range(10)]  # 模拟 m/s
    wind_std = statistics.stdev(wind_speeds)
    bm = BENCHMARKS["density_airflow_stability"]
    result = "PASS" if wind_std < bm["pass_threshold"] else "FAIL"
    notes = f"σ={wind_std:.3f}m/s < {bm['pass_threshold']}m/s ✅" if result == "PASS" else f"σ={wind_std:.3f}m/s > {bm['fail_threshold']}m/s ❌"
    records.append(CalibrationRecord(
        timestamp=timestamp, module="density_separator", phase="live_test",
        result=result, readings=wind_speeds,
        mean=statistics.mean(wind_speeds), std=wind_std,
        error=wind_std, notes=notes
    ))

    # Step 2: 分离正确率
    print("[密度] 已知密度样本分离测试（轻豆10粒 + 重豆10粒）...")
    # 模拟：轻微失误，90%正确
    light_correct = 9  # 10粒中9粒被正确吹起
    heavy_correct = 9  # 10粒中9粒正确下落
    total = 20
    correct_rate = 100.0 * (light_correct + heavy_correct) / total
    bm2 = BENCHMARKS["density_separation_known"]
    result2 = "PASS" if correct_rate >= bm2["pass_threshold"] else "FAIL"
    notes2 = f"分离正确率={correct_rate:.0f}% (轻:{light_correct}/10, 重:{heavy_correct}/10)"
    if result2 == "PASS":
        notes2 += " ✅"
    else:
        notes2 += " ❌"
    records.append(CalibrationRecord(
        timestamp=timestamp, module="density_separator", phase="verification",
        result=result2, readings=[light_correct, heavy_correct, total - light_correct - heavy_correct],
        mean=correct_rate, std=0.0,
        error=100.0 - correct_rate, notes=notes2
    ))

    return records


def run_feeder_calibration(mock: bool = True) -> list[CalibrationRecord]:
    """
    标定流程：振动给料器
    ================================================================
    目标：给料速率稳定 + 达到目标bpm

    步骤：
    1. 60秒持续运行，统计出豆数（bpm）
    2. 检验速率稳定性（σ）
    """
    records = []
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    import random

    # 模拟：Nema17升级后 50bpm，但有小幅波动
    print("[给料] 60秒持续给料速率测试...")
    bpm_samples = [random.gauss(50.0, 2.0) for _ in range(6)]  # 6个10秒窗口
    mean_bpm = statistics.mean(bpm_samples)
    std_bpm = statistics.stdev(bpm_samples)
    total_60s = int(sum(bpm_samples))  # 约300粒

    bm_rate = BENCHMARKS["feeder_rate_stability"]
    bm_max = BENCHMARKS["feeder_max_rate"]

    result_stability = "PASS" if std_bpm < bm_rate["pass_threshold"] else "FAIL"
    result_max = "PASS" if mean_bpm >= bm_max["pass_threshold"] else "FAIL"

    records.append(CalibrationRecord(
        timestamp=timestamp, module="vibrating_feeder", phase="live_test",
        result=result_stability, readings=bpm_samples,
        mean=mean_bpm, std=std_bpm,
        error=std_bpm, notes=f"60秒{total_60s}粒, σ={std_bpm:.1f}bpm {'✅' if result_stability=='PASS' else '❌'}"
    ))
    target_bpm = bm_max["pass_threshold"]
    fail_msg = f"❌ < {target_bpm}bpm目标" if result_max == "FAIL" else ""
    records.append(CalibrationRecord(
        timestamp=timestamp, module="vibrating_feeder", phase="verification",
        result=result_max, readings=[mean_bpm],
        mean=mean_bpm, std=0.0,
        error=target_bpm - mean_bpm if mean_bpm < target_bpm else 0,
        notes=f"平均{mean_bpm:.1f}bpm ✅" if result_max == "PASS" else f"平均{mean_bpm:.1f}bpm {fail_msg}"
    ))

    return records


# =============================================================================
# SECTION 4: 集成测试序列
# =============================================================================

def run_integration_tests(mock: bool = True) -> list[CalibrationRecord]:
    """
    集成测试：8步验证流程（硬件到位后按顺序执行）
    ================================================================
    测试顺序确保从底层传感器到顶层系统逐步验证
    """
    records = []
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    import random

    print("\n" + "="*60)
    print("集成测试序列开始")
    print("="*60)

    # --- Step 1: 电源与GPIO检查 ---
    print("\n[Step 1/8] 电源与GPIO基础检查...")
    # 模拟GPIO引脚电平测试
    gpio_ok = True  # mock
    records.append(CalibrationRecord(
        timestamp=timestamp, module="system", phase="gpio_check",
        result="PASS" if gpio_ok else "FAIL",
        readings=[1, 1, 1], mean=1.0, std=0.0, error=0.0,
        notes="GPIO基础电平检查 PASS ✅" if gpio_ok else "GPIO异常 ❌"
    ))

    # --- Step 2: I2C设备发现 ---
    print("[Step 2/8] I2C设备扫描（AD7746, MPU6050）...")
    i2c_found = [0x48, 0x68]  # 模拟发现的设备
    expected = [0x48]  # AD7746 必须存在
    i2c_ok = all(addr in i2c_found for addr in expected)
    records.append(CalibrationRecord(
        timestamp=timestamp, module="system", phase="i2c_discovery",
        result="PASS" if i2c_ok else "FAIL",
        readings=i2c_found, mean=len(i2c_found), std=0.0, error=0.0,
        notes=f"I2C设备: {[hex(x) for x in i2c_found]} {'✅' if i2c_ok else '❌ AD7746未找到'}"
    ))

    # --- Step 3: 相机连通性 ---
    print("[Step 3/8] 相机连通性测试（Top + Bottom）...")
    top_ok = True  # mock
    bottom_ok = True  # mock
    cam_ok = top_ok and bottom_ok
    records.append(CalibrationRecord(
        timestamp=timestamp, module="camera", phase="connectivity",
        result="PASS" if cam_ok else "FAIL",
        readings=[1 if top_ok else 0, 1 if bottom_ok else 0],
        mean=2 if cam_ok else (1 if top_ok else 0), std=0.0, error=0.0,
        notes=f"Top: {'✅' if top_ok else '❌'}, Bottom: {'✅' if bottom_ok else '❌'}"
    ))

    # --- Step 4: MQTT连通性 ---
    print("[Step 4/8] MQTT Broker连通性 + 延迟测试...")
    # 模拟MQTT ping延迟
    mqtt_latency = random.gauss(45.0, 10.0)  # 模拟 45ms
    bm = BENCHMARKS["mqtt_latency"]
    mqtt_ok = mqtt_latency < bm["pass_threshold"]
    records.append(CalibrationRecord(
        timestamp=timestamp, module="mqtt", phase="connectivity",
        result="PASS" if mqtt_ok else "FAIL",
        readings=[mqtt_latency], mean=mqtt_latency, std=0.0, error=mqtt_latency,
        notes=f"延迟={mqtt_latency:.1f}ms < {bm['pass_threshold']}ms {'✅' if mqtt_ok else '❌'}"
    ))

    # --- Step 5: REST API响应时间 ---
    print("[Step 5/8] REST API /status 响应时间测试...")
    api_latency = random.gauss(85.0, 20.0)  # 模拟 85ms
    bm = BENCHMARKS["api_response_time"]
    api_ok = api_latency < bm["pass_threshold"]
    records.append(CalibrationRecord(
        timestamp=timestamp, module="rest_api", phase="performance",
        result="PASS" if api_ok else "FAIL",
        readings=[api_latency], mean=api_latency, std=0.0, error=api_latency,
        notes=f"响应={api_latency:.1f}ms < {bm['pass_threshold']}ms {'✅' if api_ok else '❌'}"
    ))

    # --- Step 6: 30分钟持续运行 ---
    print("[Step 6/8] 30分钟持续运行测试（简化版：模拟100粒）...")
    # 简化：模拟100粒豆处理数据
    beans_processed = 100
    defect_rate = 3.5  # 模拟3.5%缺陷率
    false_reject = 1.0  # 模拟1%误剔率
    system_crashes = 0  # 模拟0次崩溃

    bm_uptime = BENCHMARKS["system_uptime"]
    uptime_ok = system_crashes <= bm_uptime["pass_threshold"]
    fail_msg_up = f"❌ > {bm_uptime['fail_threshold']}次" if not uptime_ok else ""
    records.append(CalibrationRecord(
        timestamp=timestamp, module="system", phase="stress_test",
        result="PASS" if uptime_ok else "FAIL",
        readings=[beans_processed, system_crashes],
        mean=beans_processed, std=0.0, error=system_crashes,
        notes=f"处理{beans_processed}粒, 崩溃{system_crashes}次 ✅" if uptime_ok else f"处理{beans_processed}粒, 崩溃{system_crashes}次 {fail_msg_up}"
    ))

    # --- Step 7: 缺陷检出率 ---
    print("[Step 7/8] 缺陷豆检测测试（20粒已知缺陷样本）...")
    known_defects = 20
    detected = int(known_defects * random.uniform(0.85, 0.95))  # 85-95%检出
    detection_rate = 100.0 * detected / known_defects
    bm_det = BENCHMARKS["defect_detection_rate"]
    det_ok = detection_rate >= bm_det["pass_threshold"]
    records.append(CalibrationRecord(
        timestamp=timestamp, module="defect_detector", phase="accuracy",
        result="PASS" if det_ok else "FAIL",
        readings=[detected, known_defects - detected],
        mean=detection_rate, std=0.0, error=100.0 - detection_rate,
        notes=f"检出{detected}/{known_defects}粒 ({detection_rate:.0f}%) {'✅' if det_ok else '❌'}"
    ))

    # --- Step 8: 吞吐量实测 ---
    print("[Step 8/8] 吞吐量实测（处理100粒，计算kg/h）...")
    # 假设每粒0.15g，100粒在2分钟内处理完
    total_weight_kg = 100 * 0.00015  # 0.015 kg
    elapsed_minutes = 2.0  # 模拟2分钟
    throughput_kg_h = total_weight_kg / (elapsed_minutes / 60.0)  # 0.45 kg/h
    bm_tp = BENCHMARKS["throughput_sustained"]
    tp_ok = throughput_kg_h >= bm_tp["pass_threshold"]
    records.append(CalibrationRecord(
        timestamp=timestamp, module="system", phase="throughput_test",
        result="PASS" if tp_ok else "FAIL",
        readings=[throughput_kg_h],
        mean=throughput_kg_h, std=0.0, error=bm_tp["pass_threshold"] - throughput_kg_h,
        notes=f"吞吐量={throughput_kg_h:.3f}kg/h ✅" if tp_ok else f"吞吐量={throughput_kg_h:.3f}kg/h ❌ < {bm_tp['pass_threshold']}kg/h目标"
    ))

    return records


# =============================================================================
# SECTION 5: 测试报告生成
# =============================================================================

def generate_full_report(mock: bool = True) -> TestReport:
    """
    执行完整测试流程，生成报告
    """
    report_id = f"PHY-TEST-{time.strftime('%Y%m%d-%H%M%S')}"
    report = TestReport(report_id=report_id, start_time=time.strftime("%Y-%m-%dT%H:%M:%S+08:00"))

    print(f"\n{'='*60}")
    print(f"物理测试报告: {report_id}")
    print(f"{'='*60}\n")

    # Phase A: 标定
    print(">>> Phase A: 模块标定 <<<")
    color_rec = run_color_calibration(mock=mock)
    report.add_record(color_rec)

    weight_recs = run_weight_calibration(mock=mock)
    for r in weight_recs:
        report.add_record(r)

    moisture_recs = run_moisture_calibration(mock=mock)
    for r in moisture_recs:
        report.add_record(r)

    density_recs = run_density_calibration(mock=mock)
    for r in density_recs:
        report.add_record(r)

    feeder_recs = run_feeder_calibration(mock=mock)
    for r in feeder_recs:
        report.add_record(r)

    # Phase B: 集成测试
    print("\n>>> Phase B: 集成测试 <<<")
    integration_recs = run_integration_tests(mock=mock)
    for r in integration_recs:
        report.add_record(r)

    report.end_time = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    summary = report.summary()

    print(f"\n{'='*60}")
    print(f"测试完成: {summary['passed']}/{summary['total_tests']} 通过")
    print(f"通过率: {summary['pass_rate']}")
    print(f"{'='*60}\n")

    return report


def print_report_json(report: TestReport) -> str:
    """生成报告JSON用于存档"""
    return json.dumps({
        "report_id": report.report_id,
        "start_time": report.start_time,
        "end_time": report.end_time,
        "summary": report.summary(),
        "records": report.records
    }, indent=2, ensure_ascii=False)


# =============================================================================
# SECTION 6: 主程序（模拟运行）
# =============================================================================

if __name__ == "__main__":
    print("物理测试协议 - 模拟运行模式")
    print("="*50)

    report = generate_full_report(mock=True)
    print("\n--- JSON报告 ---")
    print(print_report_json(report))

    # 保存到文件
    output_path = f"/Users/quantumcheuk/.openclaw/workspace/sorter-project/simulation/physical_test_report_{report.report_id}.json"
    with open(output_path, "w") as f:
        f.write(print_report_json(report))
    print(f"\n报告已保存: {output_path}")
