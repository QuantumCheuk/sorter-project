#!/usr/bin/env python3
"""
Digital Twin Simulation — HUSKY-SORTER-001
==========================================
Real-time physics-based digital twin of the green coffee bean sorter.
Unifies: bean physics, sensor models, state machine, MQTT, and visualization.

Run standalone:
    python sorter/simulation/digital_twin_simulation.py
    python sorter/simulation/digital_twin_simulation.py --channels 3 --bpm 50 --duration 60

Author: Little Husky (他他) 🐕
Project: HUSKY-SORTER-001
Date: 2026-05-07
"""

import time
import math
import random
import json
import sys
import argparse
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum, auto
from collections import deque


# ──────────────────────────────────────────────────────────────────────────────
# Physics Constants
# ──────────────────────────────────────────────────────────────────────────────

RHO_BEAN = 0.62e3          # kg/m³  (green coffee bean bulk density)
BEAN_MASS_G = 0.15         # grams (typical arabica bean)
BEAN_DIAMETER_MM = 8.0     # mm (spherical equivalent)
GRAVITY = 9.81             # m/s²
AIR_RHO = 1.225            # kg/m³ air density
MU_AIR = 1.81e-5           # Pa·s air viscosity


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class MachineState(Enum):
    IDLE = auto()
    INITIALIZING = auto()
    CALIBRATING = auto()
    READY = auto()
    RUNNING = auto()
    PAUSED = auto()
    FAULT = auto()
    ESTOP = auto()


class BeanDefect(Enum):
    NONE = "none"
    MOLDY = "moldy"
    FERMENTED = "fermented"
    BLACK = "black"
    BROKEN = "broken"
    IMMATURE = "immature"
    INSECT_DAMAGED = "insect_damaged"
    EMPTY = "empty"
    OVERDRIED = "overdried"
    UNDERDRIED = "underdried"


class SortGrade(Enum):
    A = "A"
    B = "B"
    C = "C"
    REJECT = "reject"


# ──────────────────────────────────────────────────────────────────────────────
# Bean Physics Engine
# ──────────────────────────────────────────────────────────────────────────────

class BeanPhysics:
    """Lumped-element bean physics: free-fall + drag + terminal velocity."""

    def __init__(self, mass_g: float = BEAN_MASS_G, diameter_mm: float = BEAN_DIAMETER_MM):
        self.mass = mass_g / 1000        # kg
        self.diameter = diameter_mm / 1000  # m
        self.area = math.pi * (self.diameter / 2)**2  # m²
        self.cd = 0.47                    # drag coefficient (sphere)

    def drag_force(self, v: float) -> float:
        """Newton drag: F_d = 0.5 * rho * v² * Cd * A"""
        return 0.5 * AIR_RHO * (v**2) * self.cd * self.area

    def weight_force(self) -> float:
        return self.mass * GRAVITY

    def terminal_velocity(self) -> Tuple[float, float]:
        """Analytical terminal velocity. Returns: (v_t m/s, Re)"""
        m, g, rho, cd = self.mass, GRAVITY, AIR_RHO, self.cd
        A = self.area
        v_t = math.sqrt(2 * m * g / (rho * cd * A))
        re = AIR_RHO * v_t * self.diameter / MU_AIR
        return v_t, re

    def fall_time(self, distance_mm: float, v0: float = 0.0) -> Tuple[float, float]:
        """Compute fall time and final velocity over a distance."""
        d = distance_mm / 1000
        v_t, _ = self.terminal_velocity()
        g = GRAVITY

        v = v0
        t = 0.0
        dt = 0.0001
        pos = 0.0

        while pos < d:
            f_drag = self.drag_force(v)
            f_net = self.weight_force() - f_drag
            accel = f_net / self.mass
            v += accel * dt
            pos += v * dt
            t += dt
            if t > 5.0:
                break

        return t, v

    def reynolds(self, v: float) -> float:
        return AIR_RHO * v * self.diameter / MU_AIR


# ──────────────────────────────────────────────────────────────────────────────
# Sensor Models
# ──────────────────────────────────────────────────────────────────────────────

class SensorModel:
    def __init__(self, name: str, noise_sigma: float = 0.0):
        self.name = name
        self.noise_sigma = noise_sigma
        self.baseline_drift = 0.0

    def read(self, true_value: float) -> float:
        noise = random.gauss(0, self.noise_sigma)
        return max(0, true_value + self.baseline_drift + noise)

    def update_drift(self, temperature_C: float, hours_elapsed: float):
        self.baseline_drift = 0.001 * temperature_C * hours_elapsed


class ColorSensor(SensorModel):
    """Lab color sensor based on HQ camera IMX477 specs (SNR ~44dB)."""

    def __init__(self, position: str = "top"):
        super().__init__(f"ColorSensor({position})", noise_sigma=0.5)

    def measure(self, lab_true: Tuple[float, float, float]) -> Dict:
        L, a, b = lab_true
        L_meas = self.read(L)
        a_meas = self.read(a)
        b_meas = self.read(b)

        is_defective = (L_meas < 20 or L_meas > 75 or
                        abs(a_meas) > 25 or abs(b_meas) > 35)

        ideal = (45, 8, 18)
        delta_e = math.sqrt(sum((x - y)**2 for x, y in zip((L_meas, a_meas, b_meas), ideal)))
        color_score = max(0, 100 - delta_e * 2)

        return {
            "L": round(L_meas, 2),
            "a": round(a_meas, 2),
            "b": round(b_meas, 2),
            "delta_E": round(delta_e, 2),
            "color_score": round(color_score, 1),
            "is_defective": is_defective,
        }


class WeightSensor(SensorModel):
    """HX711 24-bit load cell sensor model."""

    def __init__(self):
        super().__init__("WeightSensor(HX711)", noise_sigma=0.0001)  # 0.1mg
        self.tare_offset = 0.0

    def measure(self, true_weight_g: float, temperature_C: float = 25.0) -> Dict:
        temp_drift = 0.040 * (temperature_C - 25.0) / 1000  # mg→g
        gain_error = 0.0001 * (temperature_C - 25.0)

        reading = true_weight_g + self.read(self.noise_sigma) + temp_drift
        reading *= (1 + gain_error)
        reading -= self.tare_offset

        return {
            "weight_g": round(reading, 4),
            "temperature_C": temperature_C,
            "is_valid": 0.05 < reading < 0.5,
        }

    def tare(self, current_reading: float):
        self.tare_offset = current_reading


class MoistureSensor(SensorModel):
    """Capacitive moisture sensor (AD7746 equivalent)."""

    def __init__(self):
        super().__init__("MoistureSensor(AD7746)", noise_sigma=0.05)
        self.baseline_pf = 0.70  # pF at 5% moisture

    def measure(self, moisture_pct: float, temperature_C: float = 25.0) -> Dict:
        cap_pf = self.baseline_pf + 0.206 * moisture_pct
        cap_meas = cap_pf + self.read(self.noise_sigma)
        temp_comp = 0.001 * (temperature_C - 25.0)
        moisture_meas = (cap_meas - self.baseline_pf) / 0.206 + temp_comp

        return {
            "moisture_pct": round(moisture_meas, 2),
            "capacitance_pf": round(cap_meas, 4),
            "is_defective": moisture_meas < 5.0 or moisture_meas > 15.0,
        }


class DensitySensor:
    """Air-lift density separator sensor model."""

    def __init__(self):
        self.air_velocity = 0.0
        self.fan_pwm = 0.0

    def set_fan_pwm(self, pwm: float):
        self.fan_pwm = max(0, min(1, pwm))
        v_max = 8.0   # m/s turbo blower
        k = 3.0
        self.air_velocity = v_max * (1 - math.exp(-k * self.fan_pwm))

    def measure(self, bean_density_gcc: float, air_velocity: float = None) -> Dict:
        if air_velocity is None:
            air_velocity = self.air_velocity

        bean_mass = BEAN_MASS_G / 1000
        bean_diam = BEAN_DIAMETER_MM / 1000
        A = math.pi * (bean_diam / 2)**2
        cd, rho_air = 0.47, AIR_RHO

        v_equilibrium = math.sqrt(2 * bean_mass * GRAVITY / (rho_air * cd * A))
        v_eq_scaled = v_equilibrium * (bean_density_gcc / 0.65)
        is_light = air_velocity > v_eq_scaled

        return {
            "air_velocity_mps": round(air_velocity, 3),
            "v_equilibrium_mps": round(v_eq_scaled, 3),
            "bean_float": is_light,
            "pwm": round(self.fan_pwm, 3),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Bean Model
# ──────────────────────────────────────────────────────────────────────────────

BEAN_ID_COUNTER = 0

class Bean:
    """Individual coffee bean with all measured properties."""

    def __init__(self,
                 origin: str = "Ethiopia Yirgacheffe",
                 variety: str = "Heirloom",
                 process: str = "washed",
                 defect: BeanDefect = BeanDefect.NONE,
                 weight_g: float = 0.15,
                 density_gcc: float = 0.65,
                 moisture_pct: float = 11.0,
                 size_mesh: int = 15,
                 lab_color: Tuple[float, float, float] = (45, 8, 18)):
        global BEAN_ID_COUNTER
        BEAN_ID_COUNTER += 1
        self.bean_id = BEAN_ID_COUNTER
        self.origin = origin
        self.variety = variety
        self.process = process
        self.defect = defect
        self.weight_g = weight_g
        self.density_gcc = density_gcc
        self.moisture_pct = moisture_pct
        self.size_mesh = size_mesh
        self.lab_color = lab_color
        self.state = "inlet"
        self.grade: Optional[SortGrade] = None
        self.rejected = False
        self._apply_defect()

    def _apply_defect(self):
        if self.defect == BeanDefect.NONE:
            return
        if self.defect == BeanDefect.BLACK:
            self.lab_color = (12, 2, 4)
            self.weight_g *= 0.85
        elif self.defect == BeanDefect.MOLDY:
            self.lab_color = (30, 5, 12)
        elif self.defect == BeanDefect.FERMENTED:
            self.lab_color = (35, 10, 20)
        elif self.defect == BeanDefect.BROKEN:
            self.weight_g *= 0.5
        elif self.defect == BeanDefect.IMMATURE:
            self.weight_g *= 0.7
            self.density_gcc *= 0.9
        elif self.defect == BeanDefect.OVERDRIED:
            self.moisture_pct = 4.5
            self.weight_g *= 0.9
        elif self.defect == BeanDefect.UNDERDRIED:
            self.moisture_pct = 14.5
            self.weight_g *= 1.05
        elif self.defect == BeanDefect.EMPTY:
            self.weight_g *= 0.1

    def to_dict(self) -> Dict:
        return {
            "bean_id": self.bean_id,
            "defect": self.defect.value,
            "weight_g": round(self.weight_g, 4),
            "density_gcc": round(self.density_gcc, 4),
            "moisture_pct": round(self.moisture_pct, 2),
            "size_mesh": self.size_mesh,
            "lab_color": self.lab_color,
            "state": self.state,
            "grade": self.grade.value if self.grade else None,
            "rejected": self.rejected,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Bean Generator
# ──────────────────────────────────────────────────────────────────────────────

BEAN_VARIETIES = [
    ("Ethiopia Yirgacheffe", "Heirloom", "washed"),
    ("Ethiopia Sidama", "Heirloom", "natural"),
    ("Colombia Huila", "Caturra", "washed"),
    ("Kenya AA", "SL28", "washed"),
    ("Guatemala Antigua", "Bourbon", "hone"),
    ("Brazil Cerrado", "Catuaí", "natural"),
]


def generate_bean(defect_rate_pct: float = 5.0) -> Bean:
    """Generate a single bean with realistic properties and optional defect."""
    origin, variety, process = random.choice(BEAN_VARIETIES)

    defect = BeanDefect.NONE
    if random.random() * 100 < defect_rate_pct:
        defects_list = [
            BeanDefect.MOLDY, BeanDefect.FERMENTED, BeanDefect.BLACK,
            BeanDefect.BROKEN, BeanDefect.IMMATURE,
            BeanDefect.OVERDRIED, BeanDefect.UNDERDRIED,
        ]
        weights = [0.20, 0.20, 0.15, 0.15, 0.10, 0.10, 0.10]
        defect = random.choices(defects_list, weights=weights)[0]

    weight_g = max(0.08, min(0.25, random.gauss(0.152, 0.018)))
    density_gcc = max(0.55, min(0.75, random.gauss(0.65, 0.04)))
    moisture_pct = max(5.0, min(14.5, random.gauss(11.0, 1.0)))
    size_mesh = random.choices([13, 14, 15, 16, 17], weights=[0.1, 0.25, 0.40, 0.20, 0.05])[0]

    L = max(30, min(60, random.gauss(45, 5)))
    a = max(3, min(15, random.gauss(8, 2)))
    b = max(10, min(28, random.gauss(18, 3)))
    lab_color = (L, a, b)

    return Bean(origin=origin, variety=variety, process=process,
                 defect=defect, weight_g=weight_g, density_gcc=density_gcc,
                 moisture_pct=moisture_pct, size_mesh=size_mesh, lab_color=lab_color)


# ──────────────────────────────────────────────────────────────────────────────
# Digital Twin Core
# ──────────────────────────────────────────────────────────────────────────────

class DigitalTwin:
    """
    Real-time digital twin of HUSKY-SORTER-001.
    Simulates: bean inlet → sizing → color → weighing → density → moisture → grade.
    """

    def __init__(self,
                 n_channels: int = 1,
                 defect_rate_pct: float = 5.0,
                 target_bpm: float = 30.0,
                 simulate_temperature: float = 25.0,
                 speed_multiplier: float = 10.0,
                 seed: int = 42):
        if seed is not None:
            random.seed(seed)

        self.n_channels = n_channels
        self.defect_rate_pct = defect_rate_pct
        self.target_bpm = target_bpm
        self.simulate_temperature = simulate_temperature
        self.speed_multiplier = speed_multiplier

        # Physics
        self.physics = BeanPhysics()
        v_t, re = self.physics.terminal_velocity()
        self.physics_v_terminal = v_t
        self.physics_reynolds = re

        # Sensors
        self.color_top = ColorSensor("top")
        self.color_bottom = ColorSensor("bottom")
        self.weight_sensor = WeightSensor()
        self.moisture_sensor = MoistureSensor()
        self.density_sensor = DensitySensor()
        self.density_sensor.set_fan_pwm(0.50)

        # State
        self.state = MachineState.IDLE
        self.channel_states = [MachineState.READY] * n_channels
        self.beans_processed = 0
        self.beans_rejected = 0
        self.beans_graded = {g: 0 for g in SortGrade}
        self.defects_detected = {d: 0 for d in BeanDefect if d != BeanDefect.NONE}

        # Timing
        self.beat_interval_s = 60.0 / target_bpm
        self.last_beat_s = 0.0
        self.sim_time_s = 0.0
        self.real_start_time = time.time()
        self._running = False

        # Logs
        self.event_log: deque = deque(maxlen=500)
        self.stats_history: deque = deque(maxlen=600)
        self.total_weight_kg = 0.0
        self.cumulative_grade_weight = {g: 0.0 for g in SortGrade}
        self.channel_throughput = [0.0] * n_channels

        self._log("INFO", "Digital Twin initialized",
                  f"channels={n_channels}, bpm={target_bpm}, "
                  f"defect_rate={defect_rate_pct}%, speed={speed_multiplier}x, "
                  f"v_terminal={v_t:.2f}m/s, Re={re:.0f}")

    def _log(self, level: str, msg: str, detail: str = ""):
        self.event_log.append({
            "sim_time_s": round(self.sim_time_s, 3),
            "level": level,
            "msg": msg,
            "detail": detail,
        })

    def _get_sim_time(self) -> float:
        return (time.time() - self.real_start_time) * self.speed_multiplier

    def start(self):
        self.state = MachineState.RUNNING
        self.channel_states = [MachineState.RUNNING] * self.n_channels
        self.real_start_time = time.time()
        self.last_beat_s = 0.0
        self._running = True
        self._log("INFO", "Digital Twin STARTED", f"channels={self.n_channels}")

    def stop(self):
        self._running = False
        self.state = MachineState.IDLE
        self._log("INFO", "Digital Twin STOPPED",
                  f"beans={self.beans_processed}, kg={self.total_weight_kg:.4f}")

    def _should_generate_bean(self) -> bool:
        if not self._running:
            return False
        t = self._get_sim_time()
        return (t - self.last_beat_s) >= self.beat_interval_s

    def _process_bean(self, bean: Bean):
        """Process a bean through the full sorting pipeline."""
        bean.state = "sized"

        # Color detection (top + bottom)
        bean.state = "color_checked"
        top_result = self.color_top.measure(bean.lab_color)
        bot_result = self.color_bottom.measure(bean.lab_color)

        if top_result["is_defective"] or bot_result["is_defective"]:
            if bean.defect != BeanDefect.NONE:
                self.beans_rejected += 1
                self.defects_detected[bean.defect] += 1
                bean.rejected = True
                bean.state = "rejected"
                self._log("WARN", f"Bean #{bean.bean_id} REJECTED",
                          f"defect={bean.defect.value}, "
                          f"top_L={top_result['L']}, bot_L={bot_result['L']}")
                return

        # Weight
        bean.state = "weighing"
        weight_result = self.weight_sensor.measure(bean.weight_g, self.simulate_temperature)

        # Density
        bean.state = "density_sep"
        density_result = self.density_sensor.measure(bean.density_gcc)

        # Moisture
        bean.state = "moisture"
        moisture_result = self.moisture_sensor.measure(bean.moisture_pct, self.simulate_temperature)

        if moisture_result["is_defective"]:
            self.beans_rejected += 1
            bean.rejected = True
            bean.state = "rejected"
            self._log("WARN", f"Bean #{bean.bean_id} moisture REJECTED",
                      f"moisture={moisture_result['moisture_pct']:.2f}%")
            return

        # Grade assignment
        bean.state = "graded"
        grade = self._assign_grade(bean, top_result, weight_result, density_result)
        bean.grade = grade
        self.beans_graded[grade] += 1
        self.total_weight_kg += bean.weight_g / 1000
        self.cumulative_grade_weight[grade] += bean.weight_g / 1000
        self.beans_processed += 1

        elapsed_h = max(self.sim_time_s / 3600.0, 0.001)
        if elapsed_h > 0 and self.n_channels > 0:
            self.channel_throughput[0] = self.total_weight_kg / elapsed_h

        self._log("DEBUG", f"Bean #{bean.bean_id} COMPLETE",
                  f"grade={grade.value}, weight={bean.weight_g:.3f}g")

    def _assign_grade(self, bean: Bean,
                       color_result: Dict,
                       weight_result: Dict,
                       density_result: Dict) -> SortGrade:
        score = 100.0
        if weight_result["weight_g"] < 0.10:
            score -= 20
        elif weight_result["weight_g"] > 0.22:
            score -= 5
        score -= (100 - color_result["color_score"]) * 0.4
        if bean.density_gcc < 0.58:
            score -= 15
        elif bean.density_gcc > 0.72:
            score -= 5

        if score >= 85:
            return SortGrade.A
        elif score >= 70:
            return SortGrade.B
        elif score >= 55:
            return SortGrade.C
        else:
            return SortGrade.REJECT

    def step(self) -> Dict:
        """Advance one simulation step."""
        self.sim_time_s = self._get_sim_time()

        if self._should_generate_bean():
            bean = generate_bean(self.defect_rate_pct)
            bean.state = "inlet"
            self._process_bean(bean)
            self.last_beat_s = self.sim_time_s

        if (len(self.stats_history) == 0 or
                self.sim_time_s - self.stats_history[-1]["sim_time_s"] >= 1.0):
            self._record_stats()

        return self.get_snapshot()

    def _record_stats(self):
        elapsed_h = max(self.sim_time_s / 3600.0, 0.001)
        self.stats_history.append({
            "sim_time_s": round(self.sim_time_s, 3),
            "beans_processed": self.beans_processed,
            "beans_rejected": self.beans_rejected,
            "total_weight_kg": round(self.total_weight_kg, 4),
            "throughput_kg_h": round(self.total_weight_kg / elapsed_h, 3),
            "defect_rate_actual": round(
                self.beans_rejected / max(self.beans_processed, 1) * 100, 2),
            "grade_A": self.beans_graded[SortGrade.A],
            "grade_B": self.beans_graded[SortGrade.B],
            "grade_C": self.beans_graded[SortGrade.C],
            "grade_reject": self.beans_graded[SortGrade.REJECT],
        })

    def get_snapshot(self) -> Dict:
        elapsed_h = max(self.sim_time_s / 3600.0, 0.001)
        return {
            "state": self.state.name,
            "sim_time_s": round(self.sim_time_s, 2),
            "real_elapsed_s": round(time.time() - self.real_start_time, 1),
            "n_channels": self.n_channels,
            "target_bpm": self.target_bpm,
            "speed_multiplier": self.speed_multiplier,
            "beans_processed": self.beans_processed,
            "beans_rejected": self.beans_rejected,
            "defect_rate_pct": round(
                self.beans_rejected / max(self.beans_processed, 1) * 100, 2),
            "total_weight_kg": round(self.total_weight_kg, 4),
            "throughput_kg_h": round(self.total_weight_kg / elapsed_h, 3),
            "grade_distribution": {g.value: self.beans_graded[g] for g in SortGrade},
            "cumulative_grade_weight_kg": {
                g.value: round(self.cumulative_grade_weight[g], 4) for g in SortGrade
            },
            "channel_throughput_kg_h": [round(v, 3) for v in self.channel_throughput],
            "physics": {
                "v_terminal_mps": round(self.physics_v_terminal, 3),
                "reynolds": round(self.physics_reynolds, 0),
                "bean_mass_g": BEAN_MASS_G,
                "bean_diameter_mm": BEAN_DIAMETER_MM,
            },
        }

    def print_summary(self):
        s = self.get_snapshot()
        print("\n" + "="*60)
        print("  HUSKY-SORTER-001 — Digital Twin Summary")
        print("="*60)
        print(f"  Simulation time:     {s['sim_time_s']:.1f}s")
        print(f"  Real elapsed:       {s['real_elapsed_s']:.1f}s")
        print(f"  Channels:           {s['n_channels']}")
        print(f"  Target BPM:         {s['target_bpm']}")
        print(f"  Speed:              {s['speed_multiplier']}x")
        print()
        print(f"  Beans processed:    {s['beans_processed']}")
        print(f"  Beans rejected:     {s['beans_rejected']}")
        print(f"  Actual defect rate: {s['defect_rate_pct']}%")
        print(f"  Total weight:       {s['total_weight_kg']:.4f} kg")
        print(f"  Throughput:          {s['throughput_kg_h']:.3f} kg/h")
        print()
        print("  Grade distribution:")
        for g in SortGrade:
            print(f"    Grade {g.value}: {s['grade_distribution'][g.value]}"
                  f"  ({s['cumulative_grade_weight_kg'][g.value]*1000:.1f}g)")
        print()
        print("  Physics:")
        print(f"    Terminal velocity: {s['physics']['v_terminal_mps']:.3f} m/s")
        print(f"    Reynolds number:   {s['physics']['reynolds']:.0f}")
        print()
        print("="*60)


# ──────────────────────────────────────────────────────────────────────────────
# ASCII Visualization
# ──────────────────────────────────────────────────────────────────────────────

GRADE_BAR = {"A": "🟢", "B": "🟡", "C": "🟠", "reject": "🔴"}

def visualize(snap: Dict):
    """Print live ASCII visualization of digital twin state."""
    sim_t = snap['sim_time_s']
    beans = snap['beans_processed']
    rejected = snap['beans_rejected']
    kg = snap['total_weight_kg']
    tph = snap['throughput_kg_h']
    grade_dist = snap['grade_distribution']
    physics = snap['physics']

    # Progress bar for throughput vs 2kg/h target
    bar_len = 30
    target_kg_h = 2.0
    fill = min(1.0, tph / target_kg_h)
    bar = "█" * int(fill * bar_len) + "░" * (bar_len - int(fill * bar_len))

    # Throughput bar: target 2kg/h
    print(f"\r[{time.strftime('%H:%M:%S')}] t={sim_t:7.1f}s | "
          f"Beans: {beans:4d} ({rejected:3d} rej) | "
          f"Weight: {kg:.3f}kg | "
          f"TPH: {tph:.2f}kg/h | "
          f"[{bar}] ",
          end="", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Multi-Config Benchmark
# ──────────────────────────────────────────────────────────────────────────────

def run_benchmark():
    """Compare multiple configurations."""
    configs = [
        {"n_channels": 1, "bpm": 30, "defect_rate": 5.0, "label": "1ch × 30bpm (baseline)"},
        {"n_channels": 1, "bpm": 50, "defect_rate": 5.0, "label": "1ch × 50bpm (28BYJ max)"},
        {"n_channels": 3, "bpm": 50, "defect_rate": 5.0, "label": "3ch × 50bpm (TARGET ✅)"},
        {"n_channels": 3, "bpm": 50, "defect_rate": 2.0, "label": "3ch × 50bpm (low defect)"},
        {"n_channels": 3, "bpm": 50, "defect_rate": 10.0, "label": "3ch × 50bpm (high defect)"},
    ]

    duration_sim_s = 3600.0  # 1 hour simulation
    results = []

    for cfg in configs:
        print(f"\n{'='*60}")
        print(f"  Running: {cfg['label']}")
        print(f"{'='*60}")

        dt = DigitalTwin(
            n_channels=cfg["n_channels"],
            target_bpm=cfg["bpm"],
            defect_rate_pct=cfg["defect_rate"],
            speed_multiplier=100.0,  # fast
            seed=42,
        )
        dt.start()

        # Simulate 1 hour
        while dt.sim_time_s < duration_sim_s:
            dt.step()

        dt.stop()
        s = dt.get_snapshot()

        results.append({
            "label": cfg["label"],
            "beans": s["beans_processed"],
            "rejected": s["beans_rejected"],
            "defect_rate": s["defect_rate_pct"],
            "total_kg": s["total_weight_kg"],
            "throughput_kg_h": s["throughput_kg_h"],
            "grade_A": s["grade_distribution"]["A"],
            "grade_B": s["grade_distribution"]["B"],
            "grade_C": s["grade_distribution"]["C"],
            "grade_reject": s["grade_distribution"]["reject"],
        })

        dt.print_summary()

    # Summary table
    print("\n" + "="*80)
    print("  DIGITAL TWIN BENCHMARK — 1 Hour Simulation")
    print("="*80)
    print(f"  {'Config':<35} {'Beans':>7} {'Reject%':>7} "
          f"{'Weight':>8} {'TPH':>8} {'GradeA':>7} {'Status':>8}")
    print("-"*80)
    for r in results:
        status = "✅ TARGET" if r["throughput_kg_h"] >= 2.0 else "⚠️ LOW"
        print(f"  {r['label']:<35} {r['beans']:>7} {r['defect_rate']:>6.1f}% "
              f"{r['total_kg']:>7.2f}kg {r['throughput_kg_h']:>7.2f} "
              f"{r['grade_A']:>7} {status}")

    print("="*80)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 Digital Twin")
    parser.add_argument("--channels", type=int, default=1, help="Number of channels")
    parser.add_argument("--bpm", type=float, default=30.0, help="Beans per minute per channel")
    parser.add_argument("--defect-rate", type=float, default=5.0, help="Defect rate %%")
    parser.add_argument("--duration", type=int, default=30, help="Run duration in seconds (real time)")
    parser.add_argument("--speed", type=float, default=10.0, help="Simulation speed multiplier")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark mode")
    parser.add_argument("--temp", type=float, default=25.0, help="Ambient temperature °C")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    if args.benchmark:
        run_benchmark()
        return

    print("\n" + "="*60)
    print("  HUSKY-SORTER-001 — Digital Twin Simulation")
    print("="*60)
    print(f"  Channels:  {args.channels}")
    print(f"  Target:    {args.bpm} beans/min/channel")
    print(f"  Defect:    {args.defect_rate}%")
    print(f"  Duration:  {args.duration}s real-time")
    print(f"  Speed:     {args.speed}x simulation speed")
    print(f"  Temp:      {args.temp}°C")
    print("="*60)

    dt = DigitalTwin(
        n_channels=args.channels,
        target_bpm=args.bpm,
        defect_rate_pct=args.defect_rate,
        simulate_temperature=args.temp,
        speed_multiplier=args.speed,
        seed=args.seed,
    )
    dt.start()

    try:
        start_real = time.time()
        while time.time() - start_real < args.duration:
            snap = dt.step()
            visualize(snap)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        dt.stop()
        dt.print_summary()

    # Save run stats
    stats_file = "digital_twin_stats.json"
    with open(stats_file, "w") as f:
        snap = dt.get_snapshot()
        snap["stats_history"] = list(dt.stats_history)
        snap["events"] = list(dt.event_log)
        json.dump(snap, f, indent=2)
    print(f"\n  Stats saved: {stats_file}")


if __name__ == "__main__":
    main()
