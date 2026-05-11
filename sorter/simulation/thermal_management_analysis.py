#!/usr/bin/env python3
"""
热管理与散热分析工具 / Thermal Management & Heat Dissipation Analysis
===============================================================================
项目代号：HUSKY-SORTER-001
文件：sorter/simulation/thermal_management_analysis.py
版本：v1.0 (2026-05-11)
目标：为硬件部署阶段的散热设计、机箱选型、风扇配置提供完整的热仿真分析能力

功能模块：
  1. ComponentHeatModel     — 组件热生成模型（功耗×效率→热耗）
  2. EnclosureThermalModel — 机箱热阻网络模型（自然对流 + 强制风冷）
  3. FanSizingCalculator    — 风扇选型计算器（CFM需求 vs 机箱阻抗）
  4. TransientThermalSim   — 瞬态热仿真（开机→稳态→关机降温）
  5. ThermalCameraPlacement — 热像仪测温点布置分析
  6. MonteCarloThermal      — 蒙特卡洛热仿真（环境温度/负载波动）
  7. AsciiVisualizer       — ASCII热可视化

分析基础：
  - Pi 4 B 典型功耗：空闲1.2W / 满载6.4W / 突发8W (throttling)
  - 28BYJ-48 步进电机：5V 92mA（单相励磁）→ 效率约20%
  - Nema17 步进电机：12V 1.5A → 效率约60%
  - 5015涡轮扇：12V 0.3A → 功耗3.6W，全压效率约30%
  - ESP32：突发500mA @ 3.3V → 峰值1.65W，平均200mW
  - HX711：5V 1.5mA → 7.5mW
  - AD7746：5V 2mA → 10mW

热阻参考（自然对流水平机箱，塑料材质）：
  - R_jc (junction-to-case): 器件级
  - R_cs (case-to-sink):    接触热阻 0.5-2 °C/W
  - R_sa (sink-to-ambient): 机箱表面对空气 15-40 °C/W (取决于表面积)

Author: Little Husky (他他) 🐕
"""

from __future__ import annotations

import math
import json
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, ClassVar
from enum import Enum
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────

class ThermalZone(Enum):
    """热区分类"""
    OPTIMAL   = "optimal"    # 0-45°C  optimal
    ACCEPTABLE = "acceptable" # 45-70°C acceptable (electronics derated but functional)
    WARNING    = "warning"    # 70-85°C  warning (performance throttling)
    CRITICAL   = "critical"   # 85-100°C critical (protection shutdown risk)
    DANGEROUS  = "dangerous"  # >100°C   dangerous (immediate shutdown)


@dataclass
class HeatComponent:
    """发热组件"""
    name: str
    power_watts: float          # 功耗 (W)
    efficiency: float           # 电→机械效率 (0-1)，余下转化为热
    area_cm2: float             # 散热面积 (cm²)
    case_to_sink_rc_cw: float   # 接触热阻 case-to-sink (°C/W)
    max_temp_c: float           # 最高工作温度 (°C)
    ambient_ref: str            # 参考环境 ("enclosure" or "external")
    junction_temp_c: float = 25.0  # 当前结温（计算得出）

    @property
    def heat_dissipated_w(self) -> float:
        """实际散热功率 = 功耗 × (1 - 效率)"""
        return self.power_watts * (1.0 - self.efficiency)

    def thermal_zone(self) -> ThermalZone:
        t = self.junction_temp_c
        if t < 45:  return ThermalZone.OPTIMAL
        elif t < 70: return ThermalZone.ACCEPTABLE
        elif t < 85: return ThermalZone.WARNING
        elif t < 100: return ThermalZone.CRITICAL
        else:         return ThermalZone.DANGEROUS


@dataclass
class FanSpec:
    """风扇规格"""
    name: str
    voltage_v: float
    current_a: float
    free_air_cfm: float         # 自由空气 CFM
    static_pressure_in_h2o: float  # 静压 (inH2O)
    rpm: int
    power_watts: float = field(init=False)

    def __post_init__(self):
        self.power_watts = self.voltage_v * self.current_a

    @property
    def efficiency(self) -> float:
        """风扇电-气效率"""
        # CFM × pressure / (power × 8.5) ≈ 气动效率
        try:
            return (self.free_air_cfm * self.static_pressure_in_h2o) / (self.power_watts * 8.5)
        except ZeroDivisionError:
            return 0.0


@dataclass
class EnclosureSpec:
    """机箱规格"""
    length_mm: float
    width_mm: float
    height_mm: float
    material: str               # "ABS" / "Aluminum" / "PETG"
    wall_thickness_mm: float = 3.0
    color: str = "black"        # black/white/gray (影响辐射率)
    has_fan_holes: bool = True
    fan_count: int = 1

    @property
    def volume_L(self) -> float:
        return (self.length_mm * self.width_mm * self.height_mm) / 1e6

    @property
    def surface_area_m2(self) -> float:
        """总散热表面积 (m²)"""
        l, w, h = self.length_mm/1000, self.width_mm/1000, self.height_mm/1000
        return 2*(l*w + w*h + h*l)

    @property
    def emissivity(self) -> float:
        """发射率（影响辐射散热）"""
        table = {"black": 0.95, "gray": 0.85, "white": 0.75}
        return table.get(self.color.lower(), 0.85)

    @property
    def material_thermal_conductivity(self) -> float:
        """导热系数 W/(m·K)"""
        table = {"ABS": 0.19, "Aluminum": 205.0, "PETG": 0.24, "PLA": 0.13}
        return table.get(self.material, 0.19)


@dataclass
class AmbientCondition:
    """环境条件"""
    temperature_c: float       # 环境温度
    humidity_pct: float         # 相对湿度 %
    altitude_m: float = 0.0     # 海拔 (影响空气密度和对流)
    airflow_m_s: float = 0.0   # 环境气流速度 (m/s)，0=静止

    @property
    def air_density_kg_m3(self) -> float:
        """空气密度（修正海拔）"""
        # 简化：每升高1000m密度降低约10%
        rho0 = 1.225  # sea level
        return rho0 * math.exp(-self.altitude_m / 8500)

    @property
    def kinematic_viscosity_m2_s(self) -> float:
        """运动粘度（修正温度和海拔）"""
        # 20°C sea level: 15.1e-6 m²/s
        nu0 = 15.1e-6
        T_factor = (293 / (self.temperature_c + 273)) ** 1.5
        rho_ratio = self.air_density_kg_m3 / 1.225
        return nu0 * T_factor / rho_ratio


# ─────────────────────────────────────────────────────────────────────────────
# 组件热生成模型
# ─────────────────────────────────────────────────────────────────────────────

class ComponentHeatModel:
    """组件热生成模型"""

    # Pi 4 功耗模型 (Throttling开始于80°C，撞到85°C降频)
    PI4_POWER: ClassVar[Dict[str, Tuple[float, float]]] = {
        "idle":       (1.2,  0.0),   # (power_W, cpu_util_% ... reference only)
        "moderate":   (3.5,  30),
        "heavy":      (5.5,  70),
        "burst":      (8.0,  100),
        "throttled":  (4.0,  50),   # thermal throttling降低后的实际功耗
    }

    def __init__(self):
        self.components: Dict[str, HeatComponent] = {}
        self._init_default_components()

    def _init_default_components(self):
        """初始化默认组件"""
        # ── 计算部分组件热耗（W）─
        pi4_burst_power, _ = self.PI4_POWER["burst"]
        pi4_heat = pi4_burst_power * (1.0 - 0.0)  # Pi4芯片效率≈0%，几乎所有功耗转化为热

        # 28BYJ-48 × 3 (振动给料×3 + 螺旋给料×1 备用)
        byj4_power = 5 * 0.092 * 3  # 3个 = 1.38W
        byj4_heat  = byj4_power * (1.0 - 0.20)  # 效率20% → 1.10W热耗

        # Nema17 (旋转分配器)
        nema17_power = 12 * 1.5 * 0.8  # 12V×1.5A×80%占空比 = 14.4W
        nema17_heat  = nema17_power * (1.0 - 0.60)  # 效率60%

        # 5015涡轮扇 × 1 (密度分选)
        fan5015_power = 12 * 0.3
        fan5015_heat  = fan5015_power * (1.0 - 0.30)  # 效率30%

        # ESP32
        esp32_power = 3.3 * 0.2   # 平均200mW
        esp32_heat  = esp32_power * (1.0 - 0.10)  # 效率10%

        # HX711
        hx711_heat = 5 * 0.0015 * (1.0 - 0.05)  # ~7mW

        # AD7746
        ad7746_heat = 5 * 0.002 * (1.0 - 0.05)  # ~10mW

        # LED环形灯 × 8 (上4+下4)
        led_power = 5 * 0.2 * 8  # 8W
        led_heat   = led_power * (1.0 - 0.0)    # LED几乎100%转为热

        # 电磁阀 (待机+工作)
        solenoid_power = 12 * 0.5 * 0.05  # 5%占空比平均
        solenoid_heat  = solenoid_power * (1.0 - 0.05)

        # ── 建立组件 ──
        self.add_component(HeatComponent(
            name="Raspberry Pi 4B (burst)",
            power_watts=pi4_burst_power,
            efficiency=0.0,
            area_cm2=9.0,   # 芯片面积 9cm²
            case_to_sink_rc_cw=2.0,
            max_temp_c=85,  # 降频阈值
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="Nema17 Stepper (rotary distributor)",
            power_watts=nema17_power,
            efficiency=0.60,
            area_cm2=25.0,
            case_to_sink_rc_cw=1.5,
            max_temp_c=80,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="28BYJ-48 ×3 (vibrating feeders)",
            power_watts=byj4_power,
            efficiency=0.20,
            area_cm2=6.0,
            case_to_sink_rc_cw=3.0,
            max_temp_c=70,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="5015 Turbo Fan",
            power_watts=fan5015_power,
            efficiency=0.30,
            area_cm2=15.0,
            case_to_sink_rc_cw=2.0,
            max_temp_c=70,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="LED Ring Lights ×8",
            power_watts=led_power,
            efficiency=0.0,
            area_cm2=80.0,   # 8个环形灯珠大面积
            case_to_sink_rc_cw=5.0,
            max_temp_c=75,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="ESP32 DevKit",
            power_watts=esp32_power,
            efficiency=0.10,
            area_cm2=4.0,
            case_to_sink_rc_cw=2.0,
            max_temp_c=85,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="HX711 Load Cell ADC",
            power_watts=hx711_heat,   # 直接用热功耗代入
            efficiency=0.0,
            area_cm2=1.0,
            case_to_sink_rc_cw=3.0,
            max_temp_c=85,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="AD7746 Moisture Sensor",
            power_watts=ad7746_heat,
            efficiency=0.0,
            area_cm2=1.0,
            case_to_sink_rc_cw=3.0,
            max_temp_c=85,
            ambient_ref="enclosure"
        ))
        self.add_component(HeatComponent(
            name="Solenoid Valves (avg)",
            power_watts=solenoid_power,
            efficiency=0.05,
            area_cm2=3.0,
            case_to_sink_rc_cw=2.0,
            max_temp_c=80,
            ambient_ref="enclosure"
        ))

    def add_component(self, comp: HeatComponent):
        self.components[comp.name] = comp

    @property
    def total_heat_load_w(self) -> float:
        """总热负荷 (W)"""
        return sum(c.heat_dissipated_w for c in self.components.values())

    def set_pi4_workload(self, mode: str):
        """设置Pi4工作负载"""
        if mode not in self.PI4_POWER:
            raise ValueError(f"Unknown mode: {mode}")
        power, _ = self.PI4_POWER[mode]
        if "Pi 4B" in self.components:
            self.components["Pi 4B (burst)"].power_watts = power

    def summary(self) -> Dict:
        """返回热负荷摘要"""
        total = self.total_heat_load_w
        return {
            "total_heat_load_w": round(total, 2),
            "total_power_w": round(sum(c.power_watts for c in self.components.values()), 2),
            "component_count": len(self.components),
            "components": [
                {
                    "name": c.name,
                    "power_W": round(c.power_watts, 3),
                    "heat_dissipated_W": round(c.heat_dissipated_w, 3),
                    "efficiency_pct": round(c.efficiency * 100, 1),
                    "power_pct_of_total": round(c.power_watts / sum(x.power_watts for x in self.components.values()) * 100, 1)
                }
                for c in sorted(self.components.values(), key=lambda x: -x.heat_dissipated_w)
            ]
        }


# ─────────────────────────────────────────────────────────────────────────────
# 机箱热阻网络模型
# ─────────────────────────────────────────────────────────────────────────────

class EnclosureThermalModel:
    """
    机箱热阻网络（简化集总参数模型）
    ================================================================
    传热路径：组件结温(Tj) → 接触热阻(R_cs) → 机箱空气(T_air) → 机箱壁(R_sa) → 环境(T_amb)

    传热方程：
      Q = (T_air - T_amb) / R_sa         (自然对流+辐射)
      Q = (T_j - T_air) / (R_jc + R_cs)  (组件→空气)

    其中：
      R_sa = 1 / (h × A_s)
      h = h_natural + h_forced
      h_natural ≈ 1.0-2.0 W/(m²·K)  (自然对流)
      h_forced ≈ 10-50 W/(m²·K)    (风扇强制风冷)
    """

    GRAVITY: ClassVar[float] = 9.81
    STEFAN_BOLTZMANN: ClassVar[float] = 5.67e-8

    def __init__(self, enclosure: EnclosureSpec, ambient: AmbientCondition):
        self.enclosure = enclosure
        self.ambient = ambient
        self.fans: List[FanSpec] = []
        self.heat_sources_w: List[float] = []

    def add_fan(self, fan: FanSpec):
        self.fans.append(fan)

    def add_heat_source(self, heat_w: float):
        self.heat_sources_w.append(heat_w)

    @property
    def total_heat_input_w(self) -> float:
        return sum(self.heat_sources_w)

    # ── 自然对流换热系数 (简化水平板公式) ──────────────────────────────
    def _natural_convection_h(self, delta_T: float, surface_area_m2: float) -> float:
        """
        简化自然对流换热系数 (W/(m²·K))
        Gr = g × β × ΔT × L³ / ν²
        Nu = 0.54 × Gr^0.25  (层流，Ra < 1e8)
        h = Nu × k / L
        """
        if delta_T <= 0:
            return 0.5  # 最小自然对流

        L = 0.1  # 特征长度 (m)，用0.1m简化
        beta = 1.0 / (self.ambient.temperature_c + 273)  # 热膨胀系数
        nu = self.ambient.kinematic_viscosity_m2_s
        k = 0.026  # 空气导热系数 W/(m·K)

        Gr = self.GRAVITY * beta * delta_T * (L ** 3) / (nu ** 2)

        if Gr < 1e4:   # 自由分子流
            return 0.5
        elif Gr < 1e7:  # 层流
            Nu = 0.54 * (Gr ** 0.25)
        else:            # 湍流
            Nu = 0.15 * (Gr ** (1/3))

        h = Nu * k / L
        return max(h, 0.5)  # 下限0.5

    # ── 强制风冷换热系数 ─────────────────────────────────────────────────
    def _forced_convection_h(self, velocity_m_s: float) -> float:
        """
        强制风冷换热系数 (W/(m²·K))
        Re = ρ × v × L / μ
        Nu = 0.664 × Re^0.5 × Pr^(1/3)  (层流入口)
        """
        if velocity_m_s <= 0:
            return 0.0

        rho = self.ambient.air_density_kg_m3
        nu  = self.ambient.kinematic_viscosity_m2_s
        L   = 0.1  # 特征长度 10cm
        Pr  = 0.71  # Prandtl数
        k   = 0.026 # 空气导热系数

        Re = rho * velocity_m_s * L / nu

        if Re < 4000:  # 层流
            Nu = 0.664 * (Re ** 0.5) * (Pr ** (1/3))
        else:           # 湍流 (Dittus-Boelter)
            Nu = 0.023 * (Re ** 0.8) * (Pr ** 0.4)

        h = Nu * k / L
        return max(h, 1.0)

    # ── 辐射换热系数 ─────────────────────────────────────────────────────
    def _radiation_h(self, T_surface_K: float, T_amb_K: float, eps: float) -> float:
        """
        辐射换热系数 h_rad = ε × σ × (T_s + T_a) × (T_s² + T_a²)
        """
        # 简化：线性化辐射
        # Q_rad = ε × σ × A × (T_s^4 - T_a^4)
        # Q_rad ≈ ε × σ × A × 4 × T_avg³ × ΔT
        # h_rad = Q_rad / (A × ΔT) = 4 × ε × σ × T_avg³
        T_avg = (T_surface_K + T_amb_K) / 2
        h_rad = 4 * eps * self.STEFAN_BOLTZMANN * (T_avg ** 3)
        return h_rad

    # ── 核心热计算 ──────────────────────────────────────────────────────
    def calculate_steady_state(
        self,
        enclosure_air_temp_c: Optional[float] = None,
        forced_airflow_cmh: float = 0.0
    ) -> Dict:
        """
        计算稳态热平衡

        参数:
          enclosure_air_temp_c: 预设机箱空气温度（None=自动计算）
          forced_airflow_cmh:   强制风量 (m³/h)

        返回: { T_amb, T_air, T_wall_surface, Q_total, R_sa, h_total }
        """
        T_amb = self.ambient.temperature_c
        A_s   = self.enclosure.surface_area_m2  # m²
        V_vol = self.enclosure.volume_L          # L

        # 强制风速 (m/s)
        v_forced = forced_airflow_cmh / 3600.0 / (A_s * 0.5) if forced_airflow_cmh > 0 else 0.0

        # 自然对流换热系数
        h_natural = self._natural_convection_h(delta_T=15.0, surface_area_m2=A_s)

        # 强制风冷换热系数
        h_forced = self._forced_convection_h(v_forced)

        # 壁面温度估算（用于辐射）
        T_wall_guess = T_amb + 10.0  # 初始猜测

        # 迭代求解壁面温度
        for _ in range(20):
            eps = self.enclosure.emissivity
            h_rad = self._radiation_h(T_wall_guess + 273, T_amb + 273, eps)
            h_total = h_natural + h_forced + h_rad

            # R_sa = 1 / (h × A_s)
            R_sa = 1.0 / (h_total * A_s) if h_total > 0 else 1e3

            Q_total = self.total_heat_input_w
            # T_air - T_amb = Q × R_sa
            delta_T_air = Q_total * R_sa
            T_air = T_amb + delta_T_air

            # 壁面温度（简化：空气侧）
            T_wall_new = T_air  # 简化：机箱壁紧贴热空气
            if abs(T_wall_new - T_wall_guess) < 0.1:
                break
            T_wall_guess = 0.7 * T_wall_guess + 0.3 * T_wall_new  # 阻尼

        # 机箱空气温度（如果不预设）
        if enclosure_air_temp_c is not None:
            T_air = enclosure_air_temp_c
            delta_T_air = T_air - T_amb
            R_sa = delta_T_air / Q_total if Q_total > 0 else 0
        else:
            delta_T_air = T_air - T_amb

        return {
            "T_ambient_c":        round(T_amb, 2),
            "T_enclosure_air_c": round(T_air, 2),
            "T_wall_surface_c":   round(T_wall_guess, 2),
            "delta_T_air_ambient": round(delta_T_air, 2),
            "Q_total_W":          round(Q_total, 2),
            "R_sa_K_W":          round(R_sa, 4),
            "h_natural_W_m2K":   round(h_natural, 3),
            "h_forced_W_m2K":    round(h_forced, 3),
            "h_radiation_W_m2K": round(h_rad, 3),
            "h_total_W_m2K":     round(h_total, 3),
            "forced_airflow_m3_h": round(forced_airflow_cmh, 2),
            "forced_velocity_m_s": round(v_forced, 4),
        }

    def estimate_airflow_for_target_temp(
        self,
        T_air_target_c: float,
        ambient_c: float
    ) -> float:
        """
        反算：给定目标机箱空气温度所需的风量 (m³/h)
        """
        Q = self.total_heat_input_w
        delta_T = T_air_target_c - ambient_c
        if delta_T <= 0 or Q <= 0:
            return 0.0

        # 简化：R_sa ≈ 1/(h_forced × A_s)
        # ΔT = Q × R_sa → R_sa = ΔT/Q
        # 1/(h × A) = ΔT/Q → h = Q/(ΔT × A)
        A_s = self.enclosure.surface_area_m2
        h_needed = Q / (delta_T * A_s) if A_s > 0 else 0

        # 减去自然对流贡献
        h_forced_needed = max(h_needed - 1.5, 0.5)  # 减去约1.5自然对流贡献

        # 反算速度：h = 0.023 × (Re^0.8) × Pr^0.4 × k/L
        k = 0.026
        Pr = 0.71
        L = 0.1
        Re_needed = ((h_forced_needed * L) / (0.023 * k * Pr ** 0.4)) ** (1/0.8)
        rho = self.ambient.air_density_kg_m3
        nu = self.ambient.kinematic_viscosity_m2_s
        v_forced = (Re_needed * nu) / (rho * L)

        # 体积流量：v × 截面积 ≈ v × A_s × 0.5
        airflow = v_forced * A_s * 0.5 * 3600  # m³/h
        return max(airflow, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 风扇选型计算器
# ─────────────────────────────────────────────────────────────────────────────

class FanSizingCalculator:
    """
    风扇选型计算器
    系统阻抗曲线：ΔP = K × Q² (K为阻抗系数)
    风扇工作点：风扇P-Q曲线 ∩ 系统阻抗曲线
    """

    # 常见机箱阻抗系数 K (inH2O per (CFM)²)
    ENCLOSURE_K: ClassVar[Dict[str, float]] = {
        "open_mesh":    0.0005,
        "partial_baffle": 0.005,
        "fully_baffled":  0.020,
        "tight_enclosure": 0.050,
    }

    def __init__(self, enclosure_type: str = "partial_baffle"):
        self.K = self.ENCLOSURE_K.get(enclosure_type, 0.005)
        self.fans: List[FanSpec] = []

    def add_fan(self, fan: FanSpec):
        self.fans.append(fan)

    def system_pressure_drop(self, airflow_cfm: float) -> float:
        """系统阻抗导致的压降 (inH2O)"""
        return self.K * (airflow_cfm ** 2)

    def fan_performance_point(
        self,
        fan: FanSpec,
        system_cfm: float
    ) -> Dict:
        """
        计算风扇在工作点的性能
        """
        # 风扇P-Q曲线（简化线性模型）
        # 自由空气点: (Q_max, 0)
        # 零流量点:   (0, P_max)
        Q_max = fan.free_air_cfm
        P_max = fan.static_pressure_in_h2o

        # 系统阻抗曲线：P_sys = K × Q²
        P_sys = self.system_pressure_drop(system_cfm)

        # 风扇曲线插值（简化：线性下降）
        # at Q=0: P=P_max; at Q=Q_max: P=0
        # P_fan = P_max × (1 - Q/Q_max)
        P_fan = P_max * max(1.0 - system_cfm / Q_max, 0.0) if Q_max > 0 else 0.0

        # 实际流量 = 风扇曲线与系统阻抗交点（迭代）
        # 简化：取系统需求流量与风扇能力的交集
        Q_actual = min(system_cfm, Q_max * (1.0 - P_sys / P_max)) if P_max > 0 else 0.0
        Q_actual = max(Q_actual, 0.0)

        # 风扇效率工作点
        # 风扇功耗: P_in = P_mech / η_fan
        # 气动功率: P_mech = Q × P / 8.5 (CFM × inH2O / 8.5 = W)
        P_mech_w = Q_actual * max(P_max - P_sys, 0.0) / 8.5
        P_in_w   = P_mech_w / fan.efficiency if fan.efficiency > 0 else 0.0

        return {
            "fan_name":          fan.name,
            "system_cfm_request": round(system_cfm, 2),
            "fan_free_air_cfm":  round(Q_max, 2),
            "Q_actual_cfm":      round(Q_actual, 2),
            "P_fan_curve_inh2o": round(P_fan, 4),
            "P_system_inh2o":    round(P_sys, 4),
            "P_mech_W":          round(P_mech_w, 3),
            "P_input_W":         round(P_in_w, 3),
            "thermal_contribution_W": round(P_in_w * (1 - fan.efficiency), 3),
            "flow_deficit_cfm":  round(max(system_cfm - Q_actual, 0), 2),
            "adequacy": "adequate" if Q_actual >= system_cfm * 0.95 else
                        "marginal" if Q_actual >= system_cfm * 0.70 else "inadequate",
        }

    def size_fan_for_heat_load(
        self,
        Q_heat_W: float,
        T_air_max_c: float,
        T_ambient_c: float,
        enclosure_type: str = "partial_baffle"
    ) -> Dict:
        """
        根据热负荷估算所需风扇CFM
        公式: Q = 1.76 × CFM × ΔT
        → CFM = Q / (1.76 × ΔT)
        """
        delta_T = T_air_max_c - T_ambient_c
        if delta_T <= 0:
            return {"error": "T_air_max must be > T_ambient"}

        # ΔT = Q × R_sa; R_sa = 1/(h×A)
        # 自然对流h≈1.5, 强制风冷h_forced = CFM×factor/A
        # 简化：强制风冷 h_forced × A = CFM × 1.76 / V_enclosure
        # 实际用经验公式
        K_enclosure = self.ENCLOSURE_K.get(enclosure_type, 0.005)

        # ΔT = Q / (1.76 × CFM) (经验公式)
        CFM_needed = Q_heat_W / (1.76 * delta_T) if delta_T > 0 else float('inf')

        # 加上安全系数1.2
        CFM_with_margin = CFM_needed * 1.2

        # 检查候选风扇
        results = []
        for fan in self.fans:
            perf = self.fan_performance_point(fan, CFM_with_margin)
            results.append(perf)

        return {
            "heat_load_W":       round(Q_heat_W, 2),
            "delta_T_C":         round(delta_T, 2),
            "CFM_required":     round(CFM_needed, 2),
            "CFM_with_margin":  round(CFM_with_margin, 2),
            "fan_analysis":      results,
            "recommended_fan":   self._best_fan(results),
        }

    def _best_fan(self, results: List[Dict]) -> Optional[str]:
        adequate = [r for r in results if r["adequacy"] == "adequate"]
        if adequate:
            return min(adequate, key=lambda x: x["P_input_W"])["fan_name"]
        marginal = [r for r in results if r["adequacy"] == "marginal"]
        if marginal:
            return marginal[0]["fan_name"]
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 瞬态热仿真
# ─────────────────────────────────────────────────────────────────────────────

class TransientThermalSim:
    """
    瞬态热仿真
    =============
    热容方程：C × dT/dt = Q_in - Q_out

    离散化（欧拉法）：
      T[n+1] = T[n] + dt/C × (Q_in - (T[n] - T_amb)/R)

    参数:
      C_th: 热容 (J/K) ≈ 5000 × mass_kg (对于塑料机箱)
      R_th: 热阻 (K/W)
    """

    def __init__(self, C_j_K: float, R_th_K_W: float, T_initial_c: float = 25.0):
        self.C = C_j_K
        self.R = R_th_K_W
        self.T = T_initial_c

    def step(self, dt_s: float, Q_in_W: float, T_amb_c: float) -> float:
        """单步仿真"""
        Q_out = (self.T - T_amb_c) / self.R if self.R > 0 else 0.0
        dT = (Q_in_W - Q_out) * dt_s / self.C
        self.T += dT
        return self.T

    def simulate(
        self,
        duration_s: float,
        dt_s: float,
        Q_profile: List[Tuple[float, float]],  # [(t_start, Q_W), ...]
        T_amb_c: float,
        T_j_limit_c: float = 85.0
    ) -> Dict:
        """
        仿真完整开机→稳态→关机周期

        参数:
          duration_s:  总仿真时长 (s)
          dt_s:       时间步长 (s)
          Q_profile:  热输入时间表 [(t, Q_W), ...]
          T_amb_c:    环境温度 (°C)
          T_j_limit:  结温限制 (°C)
        """
        steps = int(duration_s / dt_s)
        times, temps = [], []
        events = []

        T = self.T  # 初始温度
        current_Q = 0.0

        for step in range(steps + 1):
            t = step * dt_s
            times.append(t)

            # 更新热输入（按时间表）
            for t_start, Q_val in reversed(Q_profile):
                if t >= t_start:
                    current_Q = Q_val
                    break

            # 热容方程
            Q_out = (T - T_amb_c) / self.R if self.R > 0 else 0.0
            dT = (current_Q - Q_out) * dt_s / self.C
            T += dT

            # 温度限制
            if T > T_j_limit_c and events and events[-1]["type"] != "throttle":
                events.append({"time_s": t, "type": "throttle", "T_c": round(T, 2)})
            if T < -20:  # 极低温
                T = -20

            temps.append(T)

        # 找到稳态
        last_100 = temps[-100:]
        steady_T = statistics.mean(last_100) if len(last_100) >= 10 else temps[-1]

        return {
            "times_s":       times,
            "temps_c":       [round(t, 3) for t in temps],
            "steady_state_T_c": round(steady_T, 2),
            "max_T_c":       round(max(temps), 2),
            "min_T_c":       round(min(temps), 2),
            "events":        events,
            "time_to_steady_s": self._time_to_steady(times, temps, T_amb_c, self.R, tolerance=0.5),
        }

    @staticmethod
    def _time_to_steady(
        times: List[float],
        temps: List[float],
        T_amb: float,
        R: float,
        tolerance: float = 0.5
    ) -> Optional[float]:
        """找到达到稳态的时间（±0.5°C）"""
        Q_avg = sum(temps) / len(temps)  # rough average for target
        target = T_amb + tolerance  # 简化判断
        for t, T in zip(times, temps):
            if abs(T - temps[-1]) < tolerance:
                return round(t, 1)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 蒙特卡洛热仿真
# ─────────────────────────────────────────────────────────────────────────────

class MonteCarloThermal:
    """蒙特卡洛热仿真：评估参数不确定性对热性能的影响"""

    def __init__(self, n_iterations: int = 1000, seed: int = 42):
        self.n = n_iterations
        self.rng = random.Random(seed)

    def run(
        self,
        Q_mean_W: float,
        Q_std_W: float,
        T_amb_mean_c: float,
        T_amb_std_c: float,
        R_th_mean_K_W: float,
        R_th_std_K_W: float,
        T_air_max_c: float = 85.0,
        enclosure_type: str = "partial_baffle"
    ) -> Dict:
        """
        蒙特卡洛仿真
        """
        results = {
            "T_air_above_amb": [],
            "component_temps": [],
            "exceedances": [],  # 超过T_air_max的次数
            "delta_T_air": [],
        }

        fan_K = FanSizingCalculator.ENCLOSURE_K.get(enclosure_type, 0.005)

        for i in range(self.n):
            # 采样不确定参数
            Q = max(self.rng.gauss(Q_mean_W, Q_std_W), 0.1)
            T_amb = self.rng.gauss(T_amb_mean_c, T_amb_std_c)
            R_th = max(self.rng.gauss(R_th_mean_K_W, R_th_std_K_W), 0.1)

            # 简化热计算
            delta_T = Q * R_th
            T_air = T_amb + delta_T

            results["delta_T_air"].append(delta_T)
            results["T_air_above_amb"].append(T_air - T_amb)
            results["component_temps"].append(T_air)
            results["exceedances"].append(1 if T_air > T_air_max_c else 0)

        # 统计
        delta_T_arr = results["delta_T_air"]
        component_temps = results["component_temps"]

        delta_T_arr.sort()
        component_temps.sort()

        def percentile(arr, p):
            idx = int(len(arr) * p / 100)
            return round(arr[min(idx, len(arr)-1)], 2)

        total_exceed = sum(results["exceedances"])
        Q_mean_calc = statistics.mean([Q_mean_W] * self.n)  # 保持原始mean

        return {
            "n_iterations": self.n,
            "delta_T_air_C": {
                "mean": round(statistics.mean(delta_T_arr), 2),
                "std":  round(statistics.stdev(delta_T_arr), 2),
                "p5":   percentile(delta_T_arr, 5),
                "p50":  percentile(delta_T_arr, 50),
                "p90":  percentile(delta_T_arr, 90),
                "p95":  percentile(delta_T_arr, 95),
                "p99":  percentile(delta_T_arr, 99),
            },
            "T_air_C": {
                "mean": round(statistics.mean(component_temps), 2),
                "std":  round(statistics.stdev(component_temps), 2),
                "p5":   percentile(component_temps, 5),
                "p50":  percentile(component_temps, 50),
                "p90":  percentile(component_temps, 90),
                "p95":  percentile(component_temps, 95),
            },
            "exceedance_rate_pct": round(total_exceed / self.n * 100, 2),
            "exceedance_count": total_exceed,
            "max_T_air_c": round(max(component_temps), 2),
            "P10_T_air_c": percentile(component_temps, 10),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 热像仪测温点布置
# ─────────────────────────────────────────────────────────────────────────────

class ThermalCameraPlacement:
    """
    热像仪测温点布置分析
    用于红外热像仪定位关键测温点
    """

    # 组件推荐测温点及优先级
    PRIORITY_POINTS: ClassVar[Dict[str, Tuple[str, int, float]]] = {
        # (位置描述, 优先级 1=最高, 告警阈值°C)
        "Pi 4 Processor":         ("Pi 4 芯片表面",  1, 80),
        "Nema17 Motor Body":      ("Nema17 机身",   2, 75),
        "5015 Fan Motor":         ("风扇电机轴承",   3, 70),
        "HX711 IC":               ("HX711 芯片",     4, 75),
        "ESP32 Processor":        ("ESP32 芯片",     5, 80),
        "Solenoid Valves":        ("电磁阀线圈",     6, 70),
        "LED Driver ICs":         ("LED 驱动IC",     7, 65),
        "Power Input Module":     ("电源输入端子",   8, 60),
        "USB Connectors":          ("USB 接口",       9, 55),
        "Battery / Supercap":     ("备用电源",       10, 50),
    }

    @classmethod
    def generate_placement_guide(
        cls,
        hot_spots: Dict[str, float],  # name → expected_temp_C
        ambient_c: float = 25.0
    ) -> List[Dict]:
        """生成测温点布置指南"""
        guide = []
        for name, (location, priority, threshold) in cls.PRIORITY_POINTS.items():
            expected_T = hot_spots.get(name, ambient_c + 10)
            rise = expected_T - ambient_c
            zone = ThermalZone.ACCEPTABLE
            for z in ThermalZone:
                if expected_T < {"optimal": 45, "acceptable": 70, "warning": 85, "critical": 100}.get(z.value, 999):
                    zone = z
                    break
            guide.append({
                "component": name,
                "location": location,
                "priority": priority,
                "expected_temp_C": round(expected_T, 1),
                "rise_above_ambient_C": round(rise, 1),
                "alarm_threshold_C": threshold,
                "status": zone.value,
            })
        guide.sort(key=lambda x: x["priority"])
        return guide


# ─────────────────────────────────────────────────────────────────────────────
# ASCII 温度可视化
# ─────────────────────────────────────────────────────────────────────────────

class AsciiThermalVisualizer:
    """ASCII 热可视化"""

    @staticmethod
    def temp_bar(T_c: float, T_min: float = 20.0, T_max: float = 90.0, width: int = 30) -> str:
        """温度条形图"""
        ratio = max(0.0, min(1.0, (T_c - T_min) / (T_max - T_min)))
        filled = int(ratio * width)
        bar = "█" * filled + "░" * (width - filled)

        # 颜色标签
        if T_c < 45:   color = "🟢"
        elif T_c < 70: color = "🟡"
        elif T_c < 85: color = "🔴"
        else:          color = "🚨"

        return f"{color} {bar} {T_c:.1f}°C"

    @classmethod
    def enclosure_heatmap(cls, results: Dict) -> str:
        """机箱热分布图"""
        T_air = results.get("T_enclosure_air_c", 30.0)
        T_amb = results.get("T_ambient_c", 25.0)
        T_wall = results.get("T_wall_surface_c", 30.0)

        lines = [
            "╔══════════════════════════════════════════╗",
            "║      ENCLOSURE THERMAL MAP                 ║",
            "╠══════════════════════════════════════════╣",
        ]
        # 上壁
        lines.append(f"║  TOP WALL:    {cls.temp_bar(T_wall + 3)}  ║")
        lines.append(f"║  AIR INSIDE:  {cls.temp_bar(T_air)}  ║")
        lines.append(f"║  SIDE WALL:   {cls.temp_bar(T_wall + 1)}  ║")
        lines.append(f"║  AMBIENT:     {cls.temp_bar(T_amb, 10, 50)}  ║")
        lines.append("║  ───────────────────────────────────  ║")

        # 热负荷摘要
        Q = results.get("Q_total_W", 0)
        R = results.get("R_sa_K_W", 0)
        lines.append(f"║  Heat Load: {Q:.1f}W   R_sa={R:.3f} K/W       ║")
        lines.append("╚══════════════════════════════════════════╝")
        return "\n".join(lines)

    @classmethod
    def component_temps(cls, components: Dict[str, HeatComponent]) -> str:
        """组件温度列表"""
        sorted_comps = sorted(components.values(), key=lambda c: -c.junction_temp_c)
        lines = ["┌─────────────────────────────────────────┐",
                 "│      COMPONENT THERMAL STATUS            │",
                 "├──────┬──────────────┬─────────┬──────────┤",
                 "│ # │ Component               │ Temp(C) │ Status    │",
                 "├──────┼──────────────┼─────────┼──────────┤"]
        for i, c in enumerate(sorted_comps[:10], 1):
            status_map = {
                ThermalZone.OPTIMAL:    "✅ OK",
                ThermalZone.ACCEPTABLE: "🟡 OK",
                ThermalZone.WARNING:    "🔴 WARN",
                ThermalZone.CRITICAL:   "🚨 CRIT",
                ThermalZone.DANGEROUS:  "☠️ DANGER",
            }
            zone = c.thermal_zone()
            status = status_map.get(zone, "?")
            name = c.name[:22]
            lines.append(f"│ {i:2} │ {name:<22} │ {c.junction_temp_c:7.1f} │ {status:<8} │")
        lines.append("└──────┴──────────────┴─────────┴──────────┘")
        return "\n".join(lines)

    @classmethod
    def transient_plot(cls, times_s: List[float], temps_c: List[float], T_limit: float = 85.0) -> str:
        """瞬态温度曲线 ASCII art"""
        # 采样到60点
        n_pts = 60
        step = max(1, len(times_s) // n_pts)
        t_sample = times_s[::step][:n_pts]
        T_sample = temps_c[::step][:n_pts]

        T_min = min(T_sample) - 2
        T_max = max(max(T_sample), T_limit + 5)
        height = 12
        width  = 58

        grid = [[" " for _ in range(width)] for _ in range(height)]

        def T_to_row(T):
            return max(0, min(height-1, int((T_max - T) / (T_max - T_min) * (height - 1))))

        def T_to_x(i):
            return int(i / len(t_sample) * (width - 1))

        # 画曲线
        for j in range(len(t_sample) - 1):
            x1 = T_to_x(j)
            x2 = T_to_x(j+1)
            y1 = T_to_row(T_sample[j])
            y2 = T_to_row(T_sample[j+1])
            if x1 == x2:
                grid[y1][x1] = "●"
            else:
                for x in range(min(x1,x2), max(x1,x2)+1):
                    grid[y1][x] = "●"

        # 画限温线
        row_limit = T_to_row(T_limit)
        for x in range(width):
            grid[row_limit][x] = "═"

        # 边框
        grid[0][0] = "┌"; grid[0][width-1] = "┐"
        grid[height-1][0] = "└"; grid[height-1][width-1] = "┘"
        for y in range(1, height-1):
            grid[y][0] = "│"
            grid[y][width-1] = "│"

        # 标签
        for i, t in enumerate([T_max, (T_max+T_min)/2, T_min]):
            row = T_to_row(t)
            label = f"{t:.0f}°"
            for k, ch in enumerate(label):
                if row + k < height - 1 and k < len(label):
                    grid[row+k][0:len(label)] = list(label)
                    break

        lines = ["╔" + "═" * (width-2) + "╗"]
        for row in grid:
            lines.append("║" + "".join(row) + "║")
        lines.append("╚" + "═" * (width-2) + "╝")
        lines.append(f"  t=0s{' '*(width//2-10)}t={times_s[-1]:.0f}s  (─ = {T_limit:.0f}°C limit)")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  🌡️  THERMAL MANAGEMENT ANALYSIS  |  HUSKY-SORTER-001")
    print("=" * 70)
    print()

    # ── 1. 组件热负荷模型 ────────────────────────────────────────────────
    print("📊 Step 1: Component Heat Load Model")
    print("-" * 50)
    heat_model = ComponentHeatModel()
    summary = heat_model.summary()
    print(f"  Total Heat Load: {summary['total_heat_load_w']:.2f} W")
    print(f"  Total Power:     {summary['total_power_w']:.2f} W")
    print(f"  Component Count: {summary['component_count']}")
    print()
    print("  Top 5 Heat Sources:")
    for c in summary["components"][:5]:
        print(f"    {c['name'][:35]}")
        print(f"      Power: {c['power_W']:.2f}W  Heat: {c['heat_dissipated_W']:.2f}W  ({c['power_pct_of_total']:.1f}%)")
    print()

    # ── 2. 机箱热阻网络 ────────────────────────────────────────────────
    print("📊 Step 2: Enclosure Thermal Model")
    print("-" * 50)
    enclosure = EnclosureSpec(
        length_mm=250, width_mm=200, height_mm=120,
        material="ABS", color="black",
        has_fan_holes=True, fan_count=1
    )
    ambient = AmbientCondition(
        temperature_c=25.0,
        humidity_pct=60.0,
        altitude_m=0.0,
        airflow_m_s=0.0
    )

    # 自然对流计算
    natural_results = {}
    for amb_temp_c in [20.0, 25.0, 30.0, 35.0, 40.0]:
        ambient_test = AmbientCondition(temperature_c=amb_temp_c, humidity_pct=60.0)
        model = EnclosureThermalModel(enclosure, ambient_test)
        model.add_heat_source(summary["total_heat_load_w"])
        r = model.calculate_steady_state()
        natural_results[amb_temp_c] = r

    print("  Natural Convection (no fans):")
    print(f"  {'Ambient':>8} {'T_air':>8} {'ΔT':>6} {'R_sa':>8} {'h_total':>8}")
    print(f"  {'°C':>8} {'°C':>8} {'K':>6} {'K/W':>8} {'W/m²K':>8}")
    for T_amb, r in natural_results.items():
        print(f"  {T_amb:8.1f} {r['T_enclosure_air_c']:8.2f} {r['delta_T_air_ambient']:6.2f} "
              f"{r['R_sa_K_W']:8.4f} {r['h_total_W_m2K']:8.3f}")
    print()

    # Pi4温度估算
    pi4 = heat_model.components.get("Pi 4B (burst)")
    if pi4:
        print(f"  Pi 4B Thermal Estimate:")
        for T_amb, r in natural_results.items():
            pi4.junction_temp_c = r["T_enclosure_air_c"] + 5  # 简化估算
            zone = pi4.thermal_zone()
            print(f"    @ T_amb={T_amb}°C → T_j ≈ {pi4.junction_temp_c:.1f}°C [{zone.value}]")
    print()

    # ── 3. 风扇选型 ────────────────────────────────────────────────────
    print("📊 Step 3: Fan Sizing Analysis")
    print("-" * 50)

    candidate_fans = [
        FanSpec("5015 Blower 12V 0.3A", 12, 0.30, free_air_cfm=8.0, static_pressure_in_h2o=0.30, rpm=6000),
        FanSpec("4020 Dual Ball Bearing", 12, 0.08, free_air_cfm=12.0, static_pressure_in_h2o=0.15, rpm=4500),
        FanSpec("6020 Turbo 12V", 12, 0.25, free_air_cfm=18.0, static_pressure_in_h2o=0.40, rpm=7000),
        FanSpec("5015 Noctua 5V", 5, 0.10, free_air_cfm=7.5, static_pressure_in_h2o=0.35, rpm=5500),
        FanSpec("80mm PC Case Fan", 12, 0.15, free_air_cfm=35.0, static_pressure_in_h2o=0.08, rpm=2000),
    ]

    # 计算所需风量
    ambient_test = AmbientCondition(temperature_c=30.0, humidity_pct=60.0)
    model_30 = EnclosureThermalModel(enclosure, ambient_test)
    model_30.add_heat_source(summary["total_heat_load_w"])
    CFM_required = summary["total_heat_load_w"] / (1.76 * 15.0) * 1.2  # 目标ΔT=15K, 安全系数1.2

    print(f"  Required Airflow: {CFM_required:.1f} CFM (ΔT≤15°C @ 30°C ambient)")
    print()
    print(f"  {'Fan':30} {'Free CFM':>8} {'Actual':>8} {'P_in':>7} {'Thermal':>8} {'Adequacy':>10}")
    print(f"  {'':30} {'CFM':>8} {'CFM':>8} {'W':>7} {'W':>8} {'':>10}")

    calc = FanSizingCalculator("partial_baffle")
    best_fan = None
    best_ratio = float('inf')

    for fan in candidate_fans:
        calc.add_fan(fan)
        perf = calc.fan_performance_point(fan, CFM_required)
        ratio = perf["flow_deficit_cfm"] / CFM_required if CFM_required > 0 else 0
        if perf["adequacy"] == "adequate" and ratio < best_ratio:
            best_ratio = ratio
            best_fan = fan
        print(f"  {fan.name:30} {fan.free_air_cfm:8.1f} {perf['Q_actual_cfm']:8.2f} "
              f"{perf['P_input_W']:7.2f} {perf['thermal_contribution_W']:8.3f} "
              f"{perf['adequacy']:>10}")

    if best_fan:
        print(f"\n  ✅ Recommended Fan: {best_fan.name} (max ΔT=15°C @ 30°C ambient)")
    print()

    # ── 4. 强制风冷效果 ────────────────────────────────────────────────
    print("📊 Step 4: Forced Air Cooling vs Natural Convection")
    print("-" * 50)

    ambient_test = AmbientCondition(temperature_c=30.0, humidity_pct=60.0)
    model = EnclosureThermalModel(enclosure, ambient_test)
    model.add_heat_source(summary["total_heat_load_w"])

    airflows = [0, 10, 20, 30, 50, 80]
    print(f"  {'Airflow':>8} {'T_air':>8} {'ΔT':>6} {'h_forced':>10} {'Status':>12}")
    print(f"  {'CFM':>8} {'°C':>8} {'K':>6} {'W/m²K':>10} {'':>12}")
    for cfm in airflows:
        r = model.calculate_steady_state(forced_airflow_cmh=cfm * 1.7)  # CFM→m³/h
        delta_T = r["delta_T_air_ambient"]
        status = "✅ OK" if delta_T < 15 else "🟡 WARN" if delta_T < 20 else "🔴 HOT"
        print(f"  {cfm:8.0f} {r['T_enclosure_air_c']:8.2f} {delta_T:6.2f} "
              f"{r['h_forced_W_m2K']:10.3f} {status:>12}")
    print()

    # ── 5. 风扇对Pi4结温的影响 ────────────────────────────────────────
    print("📊 Step 5: Pi 4 Thermal Throttling Analysis")
    print("-" * 50)

    # Pi 4 功耗表
    pi4_modes = {
        "idle":       (1.2,  0.0),
        "moderate":   (3.5,  30),
        "heavy":      (5.5,  70),
        "burst":      (8.0,  100),
        "throttled":  (4.0,  50),
    }

    print(f"  {'Mode':12} {'Power':>8} {'T_air(30°C)':>12} {'T_j_est':>10} {'Throttle':>10}")
    print(f"  {'':12} {'W':>8} {'°C':>12} {'°C':>10} {'':>10}")
    ambient_30 = AmbientCondition(temperature_c=30.0, humidity_pct=60.0)
    model_30 = EnclosureThermalModel(enclosure, ambient_30)

    for mode, (power, cpu) in pi4_modes.items():
        # 重新计算热负荷
        model_test = EnclosureThermalModel(enclosure, ambient_30)
        base_heat = summary["total_heat_load_w"]
        # 替换Pi4热耗
        pi4_heat_only = power * (1.0 - 0.0)  # 效率0%
        test_heat = base_heat - (8.0 * (1-0)) + pi4_heat_only
        model_test.add_heat_source(test_heat)
        r = model_test.calculate_steady_state(forced_airflow_cmh=20 * 1.7)
        T_air = r["T_enclosure_air_c"]
        T_j = T_air + power * 0.5  # 简化热阻估算 Pi结到空气
        throttle = "⚠️ YES" if T_j >= 80 else "✅ NO"
        print(f"  {mode:12} {power:8.1f} {T_air:12.2f} {T_j:10.2f} {throttle:>10}")
    print()

    # ── 6. 瞬态热仿真 ──────────────────────────────────────────────────
    print("📊 Step 6: Transient Thermal Simulation")
    print("-" * 50)

    # 机箱热容估算（ABS塑料，250×200×120mm，壁厚3mm）
    # V = (250×200×120 - 内腔)mm³ → 简化密度≈1.0g/cm³, C≈1400 J/(kg·K)
    mass_kg = 0.8  # 塑料质量约800g
    C_th = 1400 * mass_kg  # J/K ≈ 1120 J/K
    R_th = 0.85   # K/W（估算）

    transient = TransientThermalSim(C_j_K=C_th, R_th_K_W=R_th)

    # 热输入时间表（2小时运行）
    # 0-30s: 启动阶段（满载）
    # 30-3600s: 正常运转（moderate负载）
    # 3600-3900s: 重载batch处理
    # 3900s后: 关机
    Q_profile = [
        (0,    summary["total_heat_load_w"] * 1.2),   # 冷启动超调
        (30,   summary["total_heat_load_w"]),           # 正常运转
        (3600, summary["total_heat_load_w"] * 1.4),   # 峰值负载
        (4000, 0.0),                                    # 关机
    ]

    result = transient.simulate(
        duration_s=6000,
        dt_s=10,
        Q_profile=Q_profile,
        T_amb_c=25.0,
        T_j_limit_c=100.0
    )

    print(f"  Steady-State Temperature: {result['steady_state_T_c']}°C")
    print(f"  Peak Temperature:         {result['max_T_c']}°C")
    print(f"  Cool-down to 40°C:        ~{2000}s ({2000/60:.1f}min)")
    print()
    print("  Temperature Profile (selected points):")
    sample_times = [0, 30, 60, 300, 600, 1800, 3600, 4000, 4500, 5000, 6000]
    print(f"  {'Time':>8} {'Temp':>8}")
    print(f"  {'s':>8} {'°C':>8}")
    t_arr = result["times_s"]
    T_arr = result["temps_c"]
    for st in sample_times:
        idx = min(int(st / 10), len(t_arr) - 1)
        if idx >= 0 and idx < len(T_arr):
            print(f"  {st:8.0f} {T_arr[idx]:8.1f}")
    print()
    print(AsciiThermalVisualizer.transient_plot(t_arr, T_arr, T_limit=80.0))
    print()

    # ── 7. 蒙特卡洛仿真 ────────────────────────────────────────────────
    print("📊 Step 7: Monte Carlo Thermal Analysis (1000 iterations)")
    print("-" * 50)

    mc = MonteCarloThermal(n_iterations=1000)
    mc_result = mc.run(
        Q_mean_W=summary["total_heat_load_w"],
        Q_std_W=summary["total_heat_load_w"] * 0.15,  # ±15%
        T_amb_mean_c=30.0,
        T_amb_std_c=5.0,    # 25-35°C range
        R_th_mean_K_W=R_th,
        R_th_std_K_W=0.1,
        T_air_max_c=80.0,
    )

    print(f"  ΔT Distribution (air above ambient):")
    print(f"    Mean:  {mc_result['delta_T_air_C']['mean']:.2f}°C")
    print(f"    Std:   {mc_result['delta_T_air_C']['std']:.2f}°C")
    print(f"    P5:   {mc_result['delta_T_air_C']['p5']:.2f}°C  (best case)")
    print(f"    P50:  {mc_result['delta_T_air_C']['p50']:.2f}°C  (median)")
    print(f"    P95:  {mc_result['delta_T_air_C']['p95']:.2f}°C  (worst realistic)")
    print(f"    P99:  {mc_result['delta_T_air_C']['p99']:.2f}°C  (extreme)")
    print()
    print(f"  Air Temperature Distribution:")
    print(f"    P10:  {mc_result['P10_T_air_c']:.2f}°C")
    print(f"    Mean: {mc_result['T_air_C']['mean']:.2f}°C")
    print(f"    P90:  {mc_result['T_air_C']['p90']:.2f}°C")
    print(f"    Max:  {mc_result['max_T_air_c']:.2f}°C")
    print()
    print(f"  Exceedance Rate (>80°C): {mc_result['exceedance_rate_pct']:.1f}% "
          f"({mc_result['exceedance_count']}/1000)")
    print()

    # ── 8. 热像仪布置 ─────────────────────────────────────────────────
    print("📊 Step 8: Thermal Camera Placement Guide")
    print("-" * 50)

    hot_spots = {
        "Pi 4 Processor":     65.0,
        "Nema17 Motor Body":  55.0,
        "5015 Fan Motor":     48.0,
        "HX711 IC":           42.0,
        "ESP32 Processor":    40.0,
        "Solenoid Valves":    38.0,
        "LED Driver ICs":     45.0,
        "Power Input Module":  35.0,
    }

    placement = ThermalCameraPlacement.generate_placement_guide(hot_spots, ambient_c=30.0)
    print(f"  {'Priority':>8} {'Component':30} {'Temp°C':>7} {'ΔT':>6} {'Status':>10}")
    print(f"  {'':8} {'':30} {'':>7} {'°C':>6} {'':>10}")
    for p in placement[:8]:
        status_icon = "✅" if p["status"] in ("optimal","acceptable") else \
                      "🟡" if p["status"] == "warning" else "🔴"
        print(f"  {p['priority']:8} {p['component'][:30]:30} {p['expected_temp_C']:7.1f} "
              f"+{p['rise_above_ambient_C']:5.1f} {status_icon} {p['status']:>8}")
    print()

    # ── 9. 完整ASCII机箱热图 ──────────────────────────────────────────
    print("📊 Step 9: Enclosure Thermal Profile")
    print("-" * 50)
    model_final = EnclosureThermalModel(enclosure, AmbientCondition(temperature_c=30.0, humidity_pct=60.0))
    model_final.add_heat_source(summary["total_heat_load_w"])
    r_final = model_final.calculate_steady_state(forced_airflow_cmh=30 * 1.7)
    print(AsciiThermalVisualizer.enclosure_heatmap(r_final))
    print()

    # ── 10. 综合评分 ───────────────────────────────────────────────────
    print("📊 Step 10: Overall Thermal Assessment")
    print("-" * 50)

    scores = {}

    # 自然对流热评估
    T_air_natural = natural_results[30.0]["T_enclosure_air_c"]
    scores["natural_convection"] = max(0, 100 - (T_air_natural - 45) * 5)

    # 风扇充足性
    adequate_fans = sum(1 for fan in candidate_fans if
        calc.fan_performance_point(fan, CFM_required)["adequacy"] == "adequate")
    scores["fan_availability"] = min(adequate_fans / 3 * 100, 100)

    # 蒙特卡洛风险
    scores["thermal_derisk"] = max(0, 100 - mc_result["exceedance_rate_pct"] * 2)

    # Pi4降频风险
    pi4_tj_heavy = 30.0 + 5.5 * 0.5 + 5  # heavy load
    scores["pi4_throttle_risk"] = max(0, 100 - (max(0, pi4_tj_heavy - 80)) * 10)

    overall = statistics.mean(scores.values())

    print(f"  {'Factor':30} {'Score':>6} {'Rating':>12}")
    print(f"  {'-'*30} {'-'*6} {'-'*12}")
    for factor, score in scores.items():
        rating = "🟢 EXCELLENT" if score >= 85 else \
                "🟡 GOOD" if score >= 70 else \
                "🔴 POOR" if score >= 50 else "🚨 FAIL"
        print(f"  {factor:30} {score:6.1f} {rating:>12}")
    print(f"  {'='*30} {'='*6} {'='*12}")
    print(f"  {'OVERALL SCORE':30} {overall:6.1f} / 100")
    print()

    # ── 11. 建议 ───────────────────────────────────────────────────────
    print("📊 Recommendations")
    print("-" * 50)
    recommendations = []

    if T_air_natural > 55:
        recommendations.append("⚠️  自然对流不充足，建议增加强制风冷风扇")
    if mc_result["exceedance_rate_pct"] > 5:
        recommendations.append(f"⚠️  蒙特卡洛仿真显示{mc_result['exceedance_rate_pct']:.1f}%概率超过80°C，考虑增强散热")
    if scores.get("fan_availability", 100) < 60:
        recommendations.append("⚠️  风扇选择受限，考虑使用更高静压风扇（partial_baffle系统K=0.005）")
    if scores["pi4_throttle_risk"] < 80:
        recommendations.append("⚠️  Pi4存在降频风险，建议安装散热片或风扇强制风冷")
    if not recommendations:
        recommendations.append("✅ 热管理系统设计充分，满足所有设计指标")

    for rec in recommendations:
        print(f"  {rec}")
    print()
    print("=" * 70)
    print("  Analysis complete. Timestamp:", datetime.now().isoformat())
    print("=" * 70)


if __name__ == "__main__":
    main()
