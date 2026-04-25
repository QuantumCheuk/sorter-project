#!/usr/bin/env python3
"""
电容式含水率传感器 — moisture_sensor.py
==========================================
功能：豆子含水率测量（电容法）
接口：AD7746 I2C 24-bit 容值计 / 555振荡器备选

Author: Little Husky 🐕
Date: 2026-04-25
"""

import time
import math
from typing import Optional, Tuple

# ─────────────────────────────────────────────
# 物理常数
# ─────────────────────────────────────────────
EPSILON_0 = 8.854e-12  # F/m

# 介电模型参数（Tabatabaei et al. @ 500MHz）
DIELECTRIC_A = 3.47
DIELECTRIC_B = 0.0197
DIELECTRIC_C = 0.137


def dielectric_constant(moisture_pct: float) -> float:
    """
    咖啡豆介电常数（Tabatabaei经验公式）
    适用于 5-15% 质量含水率，500MHz
    """
    if moisture_pct <= 0:
        return DIELECTRIC_A
    return max(DIELECTRIC_A,
               DIELECTRIC_A + DIELECTRIC_B * moisture_pct + DIELECTRIC_C * moisture_pct**2)


def moisture_from_dielectric(eps_eff: float) -> float:
    """
    反函数：从介电常数计算含水率
    eps = a + b*M + c*M^2
    M = (-b + sqrt(b^2 + 4c*(eps-a))) / 2c
    """
    a, b, c = DIELECTRIC_A, DIELECTRIC_B, DIELECTRIC_C
    disc = b**2 + 4 * c * (eps_eff - a)
    if disc < 0:
        return 0.0
    M = (-b + math.sqrt(disc)) / (2 * c)
    return max(0.0, min(100.0, M))


# ─────────────────────────────────────────────
# 探头几何配置
# ─────────────────────────────────────────────
PROBE_DEFAULT = {
    'plate_area_mm2': 15 * 15,   # 225 mm²
    'gap_mm': 8.0,               # 8mm 间隙（容纳单粒豆）
    'bean_fill_fraction': 0.30,  # 豆子占空比（体积分数）
}


class MoistureProbe:
    """
    电容式含水率探头
    """

    def __init__(self,
                 plate_area_mm2: float = PROBE_DEFAULT['plate_area_mm2'],
                 gap_mm: float = PROBE_DEFAULT['gap_mm'],
                 bean_fill_fraction: float = PROBE_DEFAULT['bean_fill_fraction'],
                 circuit: str = 'AD7746'):
        """
        参数:
            plate_area_mm2: 电极板面积 (mm²)
            gap_mm: 两极板间隙 (mm)
            bean_fill_fraction: 豆子占空比（体积分数）
            circuit: 'AD7746' | '555' — 测量电路类型
        """
        self.A = plate_area_mm2 * 1e-6       # m²
        self.d = gap_mm * 1e-3               # m
        self.vf = bean_fill_fraction
        self.circuit = circuit

    def _capacitance_no_bean(self) -> float:
        """纯空气电容（无豆时基线）"""
        return EPSILON_0 * self.A / self.d

    def _capacitance_with_bean(self, eps_bean: float) -> float:
        """有豆时的电容（体积填充模型）"""
        d_bean = self.d * self.vf
        d_air  = self.d - d_bean
        if d_air < 0.1e-3:
            d_air = 0.1e-3

        A_bean = self.A * self.vf
        A_air  = self.A - A_bean

        C_bean = EPSILON_0 * eps_bean * A_bean / self.d
        C_air  = EPSILON_0 * A_air / self.d
        return C_bean + C_air

    def capacitance(self, moisture_pct: float) -> float:
        """给定含水率的电容值（pF）"""
        eps = dielectric_constant(moisture_pct)
        return self._capacitance_with_bean(eps) * 1e12  # pF

    def moisture_from_capacitance(self, C_pF: float) -> float:
        """从电容反推含水率"""
        C = C_pF * 1e-12  # F
        # 反函数求解 eps_bean
        # C = eps0 * (eps_bean * A_vf + 1 * A_air) / d
        # eps_bean = (C * d / eps0 - A_air) / A_vf
        A_bean = self.A * self.vf
        A_air  = self.A - A_bean
        eps_bean = (C * self.d / EPSILON_0 - A_air) / A_bean
        eps_bean = max(1.0, eps_bean)
        return moisture_from_dielectric(eps_bean)

    def sensitivity(self, at_moisture_pct: float) -> float:
        """灵敏度 dC/dM (pF per 1% moisture)"""
        dM = 0.1
        C1 = self.capacitance(at_moisture_pct - dM/2)
        C2 = self.capacitance(at_moisture_pct + dM/2)
        return (C2 - C1) / dM

    def calibration_curve(self, moisture_range=(5, 15), points=101) -> Tuple[list, list]:
        """生成标定曲线数据"""
        M_vals = [moisture_range[0] + i * (moisture_range[1] - moisture_range[0]) / (points - 1)
                  for i in range(points)]
        C_vals = [self.capacitance(m) for m in M_vals]
        return M_vals, C_vals


# ─────────────────────────────────────────────
# AD7746 I2C 容值芯片驱动
# ─────────────────────────────────────────────
class AD7746Driver:
    """
    AD7746 24-bit I2C 容值-数字转换器
    
    AD7746规格：
    - 24-bit 分辨率 (1 fF RMS noise)
    - I2C 地址: 0x48 (ADDR=0) 或 0x49 (ADDR=1)
    - 电容输入范围: ±4 pF (差分) 或 0-8 pF (单端)
    - 采样率: 10 Hz / 50 Hz 可选
    
    接法:
    - CAP+ (pin 1): 探头电极 (+)
    - CAP- (pin 2): 探头电极 (-)
    - GND: 探头外壳/屏蔽
    - VCC: 3.3V 或 5V
    - SDA/SCL: I2C 总线
    """
    
    I2C_ADDRESS = 0x48  # ADDR pin = GND
    
    # 寄存器地址
    REG_STATUS   = 0x00
    REG_CAP_DATA = 0x01  # 24-bit
    REG_VT_DATA  = 0x03  # voltage/temp
    REG_CAP_SETUP = 0x07
    REG_VT_SETUP  = 0x08
    REG_MODE      = 0x0A
    REG_CFG       = 0x0B
    
    def __init__(self, i2c_bus=1):
        self.i2c_bus = i2c_bus
        self._initialized = False
        self._simulate = False  # 是否模拟模式（无真实硬件）
    
    def init(self):
        """初始化 AD7746"""
        try:
            import smbus2
            self.bus = smbus2.SMBus(self.i2c_bus)
            self._simulate = False
            self._initialized = True
        except ImportError:
            print("[MoistureSensor] smbus2 not available, using simulation mode")
            self._simulate = True
            self._initialized = True
        except Exception as e:
            print(f"[MoistureSensor] I2C init failed: {e}, using simulation mode")
            self._simulate = True
            self._initialized = True
    
    def _read_capacitance_raw(self) -> float:
        """读取原始电容值（pF）"""
        if self._simulate:
            # 模拟模式：返回标称值
            return 1.47  # pF ≈ 10% moisture
    
    def read_moisture(self, probe: MoistureProbe) -> Optional[float]:
        """
        读取含水率
        
        返回: 含水率 (%)，或 None（读取失败）
        """
        if not self._initialized:
            self.init()
        
        C_pF = self._read_capacitance_raw()
        return probe.moisture_from_capacitance(C_pF)
    
    def read_capacitance(self) -> float:
        """读取电容（pF）"""
        if not self._initialized:
            self.init()
        return self._read_capacitance_raw()


# ─────────────────────────────────────────────
# 555振荡器 + GPIO测量方案（低成本备选）
# ─────────────────────────────────────────────
class555Oscillator:
    """
    555多谐振荡器 + GPIO脉冲计数测量方案
    
    原理：电容变化 → 频率变化 → 脉冲计数
    f = 1.44 / ((R1 + 2R2) × C)
    
    R1 = R2 = 1MΩ, C = 测量电容
    f ≈ 720 / C(pF)  kHz
    
    C=1pF → f=720kHz (太高，需调整)
    C=10pF → f=72kHz
    C=100pF → f=7.2kHz
    
    实际：并联一个固定电容(如1000pF)降低频率
    """
    
    def __init__(self, R1=1e6, R2=1e6, C_offset=1e-9, gpio_pin=None):
        """
        参数:
            R1, R2: 电阻 (Ω)
            C_offset: 附加固定电容 (F)，用于频率调节
            gpio_pin: GPIO引脚号（用于计数）
        """
        self.R1 = R1
        self.R2 = R2
        self.C_offset = C_offset
        self.gpio_pin = gpio_pin
        self._simulate = True  # 默认模拟模式
    
    def frequency(self, C_F: float) -> float:
        """给定电容(C_total = C + C_offset)的振荡频率"""
        C_total = C_F + self.C_offset
        if C_total <= 0:
            return float('inf')
        return 1.44 / ((self.R1 + 2 * self.R2) * C_total)
    
    def capacitance_from_freq(self, freq_Hz: float) -> float:
        """从频率反推电容"""
        if freq_Hz <= 0:
            return 0.0
        return (1.44 / freq_Hz - self.R1 - 2 * self.R2 * 0) / (self.R1 + 2 * self.R2) - self.C_offset
    
    def measure_moisture(self, probe: MoistureProbe, count_time=1.0) -> Optional[float]:
        """
        测量含水率
        
        参数:
            count_time: 脉冲计数时间 (s)
        
        返回: 含水率 (%)，或 None
        """
        if self._simulate:
            C_pF = probe.capacitance(10.0)  # 模拟10%含水率
            return 10.0
        
        # 真实测量：计数脉冲数
        # count = f × count_time
        # 待实现GPIO脉冲计数
        return None


# ─────────────────────────────────────────────
# 高级封装
# ─────────────────────────────────────────────
class MoistureSensor:
    """
    含水率传感器高级封装
    
    使用 AD7746（高精度）或 555振荡器（低成本）
    """
    
    def __init__(self,
                 plate_area_mm2: float = PROBE_DEFAULT['plate_area_mm2'],
                 gap_mm: float = PROBE_DEFAULT['gap_mm'],
                 bean_fill_fraction: float = PROBE_DEFAULT['bean_fill_fraction'],
                 circuit: str = 'AD7746',
                 i2c_bus: int = 1):
        """
        参数:
            circuit: 'AD7746' | '555'
        """
        self.probe = MoistureProbe(plate_area_mm2, gap_mm, bean_fill_fraction)
        self.circuit_type = circuit
        
        if circuit == 'AD7746':
            self.driver = AD7746Driver(i2c_bus=i2c_bus)
        else:
            self.driver = class555Oscillator()
    
    def measure(self, samples: int = 5) -> Optional[float]:
        """
        测量单粒豆子含水率
        
        参数:
            samples: 采样次数，取平均
        
        返回:
            含水率 (%)，或 None（测量失败）
        """
        readings = []
        for _ in range(samples):
            if self.circuit_type == 'AD7746':
                val = self.driver.read_moisture(self.probe)
            else:
                val = self.driver.measure_moisture(self.probe)
            if val is not None:
                readings.append(val)
            time.sleep(0.05)
        
        if not readings:
            return None
        
        # 去极值平均
        readings.sort()
        if len(readings) > 2:
            readings = readings[1:-1]  # 去掉最大最小
        return sum(readings) / len(readings)
    
    def auto_tare(self, n_samples: int = 10):
        """
        自动去皮：测量空载（无豆）基线
        用于补偿温度漂移和零点偏移
        """
        baseline_C = []
        for _ in range(n_samples):
            if self.circuit_type == 'AD7746':
                c = self.driver.read_capacitance()
            else:
                c = self.probe.capacitance(0)
            baseline_C.append(c)
            time.sleep(0.05)
        
        self._baseline_C = sum(baseline_C) / len(baseline_C)
        print(f"[MoistureSensor] Tare: baseline = {self._baseline_C:.4f} pF")
        return self._baseline_C


# ─────────────────────────────────────────────
# 标定工具
# ─────────────────────────────────────────────
class MoistureCalibrator:
    """
    含水率传感器标定工具
    
    方法：重量法（烘干箱）+ 电容测量对照
    """
    
    @staticmethod
    def two_point_calibration(
        known_M1: float, C1_pF: float,
        known_M2: float, C2_pF: float
    ) -> dict:
        """
        两点标定：已知两个含水率样本的电容值
        线性标定：C = a + b × M
        """
        b = (C2_pF - C1_pF) / (known_M2 - known_M1)
        a = C1_pF - b * known_M1
        return {'a': a, 'b': b, 'model': 'linear'}
    
    @staticmethod
    def oven_dry_reference(bean_weight_g: float, dry_weight_g: float) -> float:
        """
        烘干法计算含水率（标准参考法）
        
        质量含水率 w.b.% = (W_wet - W_dry) / W_wet × 100
        """
        if bean_weight_g <= 0:
            return 0.0
        return (bean_weight_g - dry_weight_g) / bean_weight_g * 100.0


# ─────────────────────────────────────────────
# 物理测试协议
# ─────────────────────────────────────────────
def run_physical_test_protocol():
    """
    物理测试协议（6步验证）
    
    Step 1: 零点标定（空载）
    Step 2: 参考电容验证（已知电容）
    Step 3: 干豆基准测量
    Step 4: 吸水饱和豆测量
    Step 5: 线性标定（两点）
    Step 6: 精度验证（重复测量）
    """
    print("\n" + "=" * 60)
    print("含水率传感器 — 物理测试协议")
    print("=" * 60)
    
    sensor = MoistureSensor(circuit='AD7746')
    probe = sensor.probe
    
    print("\n📋 探头参数:")
    print(f"  电极面积: {probe.A*1e6:.0f} mm²")
    print(f"  极板间隙: {probe.d*1e3:.1f} mm")
    print(f"  占空比: {probe.vf:.2f}")
    
    print("\n📊 理论标定曲线:")
    M_vals, C_vals = probe.calibration_curve()
    print(f"  5%  → {probe.capacitance(5):.3f} pF")
    print(f"  10% → {probe.capacitance(10):.3f} pF")
    print(f"  12% → {probe.capacitance(12):.3f} pF")
    print(f"  15% → {probe.capacitance(15):.3f} pF")
    print(f"\n  灵敏度 @ 10%: {probe.sensitivity(10):.4f} pF/%")
    print(f"  ±0.5% 对应 ΔC = {probe.sensitivity(10)*0.5:.3f} fF")
    
    print("\n✅ 测试协议就绪，待硬件采购完成后执行")


if __name__ == '__main__':
    run_physical_test_protocol()
