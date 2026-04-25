"""
Buffer Bin + Spiral Feeder Control Module
==========================================
Controls:
- 8-bin buffer storage (graded by quality)
- Rotary distributor (selects which bin to discharge)
- Spiral feeder (dispenses beans to roaster at controlled rate)

HUSKY-SORTER-001 | Author: Little Husky 🐕 | Date: 2026-04-26
"""

import time
import threading
import numpy as np
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class BufferBinState(Enum):
    """Buffer bin state machine states."""
    IDLE = "idle"
    FILLING = "filling"
    BATCH_READY = "batch_ready"
    DISPENSING = "dispensing"
    DISPENSE_DONE = "dispense_done"
    COOLDOWN = "cooldown"
    WAITING_ROASTER = "waiting_roaster"


@dataclass
class SpiralFeederConfig:
    """Spiral feeder configuration."""
    # Motor (28BYJ-48 + DRV8833)
    dir_pin: int = 20       # GPIO20 = DRV8833 DIR
    step_pin: int = 21      # GPIO21 = DRV8833 STEP
    enable_pin: int = 16    # GPIO16 = DRV8833 ENABLE (active LOW)

    # Geometry (φ20mm tube, 15mm pitch)
    tube_id_mm: float = 20.0
    helix_pitch_mm: float = 15.0
    effective_fill: float = 0.40
    bean_density_g_cm3: float = 0.95

    # Motor settings
    rpm: float = 120.0            # Target RPM (fast for dispensing)
    microstep: int = 8            # DRV8833 microstep setting

    # Stepper specs (28BYJ-48)
    step_angle_deg: float = 5.625
    steps_per_rev: int = 64        # 360/5.625

    # GPIO (rotary distributor motor)
    distributor_dir_pin: int = 12
    distributor_step_pin: int = 19
    distributor_enable_pin: int = 13

    # Dispensing
    target_batch_weight_g: float = 250.0  # 250g per batch to roaster
    rpm_dispense: float = 120.0           # Fast dispensing RPM

    @property
    def mass_per_rev_g(self) -> float:
        """Grams per revolution (computed from geometry)."""
        r_mm = self.tube_id_mm / 2.0
        vol_per_rev_cm3 = (np.pi * r_mm**2 * self.helix_pitch_mm / 1000.0) * self.effective_fill
        return vol_per_rev_cm3 * self.bean_density_g_cm3

    @property
    def steps_per_mm(self) -> float:
        """Steps per mm of linear travel (at microstep=8)."""
        return (self.steps_per_rev * self.microstep) / self.helix_pitch_mm

    @property
    def mass_per_step_g(self) -> float:
        """Grams per step."""
        return self.mass_per_rev_g / (self.steps_per_rev * self.microstep)

    @property
    def grams_per_second(self) -> float:
        """Grams per second at target RPM."""
        rev_per_sec = self.rpm / 60.0
        return self.mass_per_rev_g * rev_per_sec

    @property
    def target_dispense_time_s(self) -> float:
        """Seconds to dispense 250g at target RPM."""
        return self.target_batch_weight_g / self.grams_per_second


@dataclass
class BinLevel:
    """Single bin fill level state."""
    bin_id: str
    grade: str
    current_g: float = 0.0
    capacity_g: float = 100.0
    is_full: bool = False
    is_empty: bool = True

    @property
    def fill_pct(self) -> float:
        return self.current_g / self.capacity_g * 100


class SpiralFeeder:
    """
    Spiral feeder with closed-loop weight control.
    Uses step counting + periodic load cell feedback for accuracy.
    """

    def __init__(self, config: SpiralFeederConfig = None):
        self.config = config or SpiralFeederConfig()
        self._lock = Lock()
        self._enabled = False
        self._running = False
        self._current_pos_steps = 0  # steps from reference
        self._dispensed_g = 0.0

        # GPIO simulation mode (no actual GPIO in analysis)
        self._gpio_available = False
        try:
            import RPi.GPIO as GPIO
            self._gpio_available = True
            self._setup_gpio()
        except (ImportError, RuntimeError):
            pass

    def _setup_gpio(self):
        """Initialize GPIO pins."""
        import RPi.GPIO as GPIO
        c = self.config
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(c.dir_pin, GPIO.OUT)
        GPIO.setup(c.step_pin, GPIO.OUT)
        GPIO.setup(c.enable_pin, GPIO.OUT)
        GPIO.setup(c.distributor_dir_pin, GPIO.OUT)
        GPIO.setup(c.distributor_step_pin, GPIO.OUT)
        GPIO.setup(c.distributor_enable_pin, GPIO.OUT)
        # Disable motors by default
        GPIO.output(c.enable_pin, GPIO.HIGH)
        GPIO.output(c.distributor_enable_pin, GPIO.HIGH)

    def enable(self):
        """Enable motor drivers."""
        with self._lock:
            self._enabled = True
            if self._gpio_available:
                import RPi.GPIO as GPIO
                GPIO.output(self.config.enable_pin, GPIO.LOW)
                GPIO.output(self.config.distributor_enable_pin, GPIO.LOW)

    def disable(self):
        """Disable motor drivers (power saving)."""
        with self._lock:
            self._enabled = False
            if self._gpio_available:
                import RPi.GPIO as GPIO
                GPIO.output(self.config.enable_pin, GPIO.HIGH)
                GPIO.output(self.config.distributor_enable_pin, GPIO.HIGH)

    def set_rpm(self, rpm: float):
        """Set motor RPM by adjusting step pulse delay."""
        self.config.rpm = rpm

    def rotate(self, revolutions: float) -> float:
        """
        Rotate spiral by given revolutions.
        Returns actual mass dispensed (g).
        """
        with self._lock:
            if not self._enabled:
                return 0.0

            steps = int(revolutions * self.config.steps_per_rev * self.config.microstep)
            c = self.config

            if self._gpio_available:
                import RPi.GPIO as GPIO
                # Calculate delay per step for target RPM
                # period_per_rev_s = 60 / rpm
                # period_per_step_s = period_per_rev_s / (steps_per_rev * microstep)
                period_per_step_s = 60.0 / rpm / (c.steps_per_rev * c.microstep)
                delay_s = period_per_step_s / 2  # half period for toggle

                GPIO.output(c.dir_pin, GPIO.HIGH)  # Forward
                for _ in range(steps):
                    GPIO.output(c.step_pin, GPIO.HIGH)
                    time.sleep(delay_s)
                    GPIO.output(c.step_pin, GPIO.LOW)
                    time.sleep(delay_s)
            else:
                # Simulation: just sleep proportionally
                time.sleep(steps * 60.0 / rpm / (c.steps_per_rev * c.microstep))

            self._current_pos_steps += steps
            mass_dispensed = revolutions * c.mass_per_rev_g
            self._dispensed_g += mass_dispensed
            return mass_dispensed

    def dispense_batch(self, target_g: float = None, rpm: float = None,
                       load_cell=None) -> float:
        """
        Dispense a batch of beans to roaster.
        Uses open-loop step counting with optional load cell feedback.
        """
        target = target_g or self.config.target_batch_weight_g
        rpm = rpm or self.config.rpm_dispense
        self.set_rpm(rpm)

        self.enable()
        dispensed = 0.0
        start_time = time.time()
        target_revs = target / self.config.mass_per_rev_g
        step_interval_s = 60.0 / rpm / (self.config.steps_per_rev * self.config.microstep)

        with self._lock:
            if self._gpio_available:
                import RPi.GPIO as GPIO
                steps_needed = int(target_revs * self.config.steps_per_rev * self.config.microstep)
                GPIO.output(self.config.dir_pin, GPIO.HIGH)

                for step in range(steps_needed):
                    # Optional: check load cell periodically for feedback
                    if load_cell and step % 500 == 0 and step > 0:
                        current_weight = load_cell.read(samples=3)
                        if current_weight and current_weight >= target * 0.95:
                            break  # Enough dispensed

                    GPIO.output(self.config.step_pin, GPIO.HIGH)
                    time.sleep(step_interval_s / 2)
                    GPIO.output(self.config.step_pin, GPIO.LOW)
                    time.sleep(step_interval_s / 2)
                    dispensed += self.config.mass_per_step_g

                    if dispensed >= target:
                        break
            else:
                # Simulation
                time.sleep(target_revs * 60.0 / rpm)
                dispensed = target

        duration = time.time() - start_time
        self._dispensed_g += dispensed
        self.disable()
        return dispensed

    def reset(self):
        """Reset position counter."""
        with self._lock:
            self._current_pos_steps = 0
            self._dispensed_g = 0.0


class RotaryDistributor:
    """
    8-position rotary distributor valve.
    Selects which bin to connect to spiral feeder outlet.
    """

    def __init__(self, config: SpiralFeederConfig = None):
        self.config = config or SpiralFeederConfig()
        self._lock = Lock()
        self._current_bin = 0  # 0-7
        self._enabled = False

        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio_available = True
            self._setup_gpio()
        except (ImportError, RuntimeError):
            self._gpio_available = False

    def _setup_gpio(self):
        GPIO = self._gpio
        c = self.config
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(c.distributor_dir_pin, GPIO.OUT)
        GPIO.setup(c.distributor_step_pin, GPIO.OUT)
        GPIO.setup(c.distributor_enable_pin, GPIO.OUT)
        GPIO.output(c.distributor_enable_pin, GPIO.HIGH)

    def enable(self):
        with self._lock:
            self._enabled = True
            if self._gpio_available:
                self._gpio.output(self.config.distributor_enable_pin, self._gpio.LOW)

    def disable(self):
        with self._lock:
            self._enabled = False
            if self._gpio_available:
                self._gpio.output(self.config.distributor_enable_pin, self._gpio.HIGH)

    def select_bin(self, bin_index: int) -> bool:
        """
        Move distributor to bin_index (0-7).
        Returns True on success.
        """
        if not (0 <= bin_index <= 7):
            return False

        with self._lock:
            if not self._enabled:
                self.enable()

            # Calculate shortest rotation direction
            diff = (bin_index - self._current_bin) % 8
            reverse = diff > 4
            steps = min(diff, 8 - diff)

            direction = self._gpio.HIGH if not reverse else self._gpio.LOW

            if self._gpio_available:
                GPIO = self._gpio
                c = self.config
                GPIO.output(c.distributor_dir_pin, direction)

                # Full-step for speed (vs microstep)
                for _ in range(steps * 8):  # 8 steps per bin position
                    GPIO.output(c.distributor_step_pin, GPIO.HIGH)
                    time.sleep(0.003)  # 3ms step
                    GPIO.output(c.distributor_step_pin, GPIO.LOW)
                    time.sleep(0.003)
            else:
                time.sleep(steps * 0.05)  # simulation

            self._current_bin = bin_index
        return True

    @property
    def current_bin(self) -> int:
        return self._current_bin


class BufferBinController:
    """
    High-level buffer bin controller.
    Manages 8 bins, rotary distributor, spiral feeder, and batch dispensing.
    """

    # Bin configuration
    BIN_CONFIG: Dict[str, Dict] = {
        'A1': {'grade': 'A', 'capacity_g': 100},
        'A2': {'grade': 'A', 'capacity_g': 100},
        'A3': {'grade': 'A', 'capacity_g': 100},
        'B1': {'grade': 'B', 'capacity_g': 80},
        'B2': {'grade': 'B', 'capacity_g': 80},
        'C1': {'grade': 'C', 'capacity_g': 60},
        'C2': {'grade': 'C', 'capacity_g': 60},
        'BF': {'grade': 'buffer', 'capacity_g': 100},
    }

    def __init__(self, feeder_config: SpiralFeederConfig = None):
        self.feeder = SpiralFeeder(feeder_config)
        self.distributor = RotaryDistributor(feeder_config)
        self._bins: Dict[str, BinLevel] = {}
        self._state = BufferBinState.IDLE
        self._lock = Lock()

        # Initialize bins
        for bin_id, cfg in self.BIN_CONFIG.items():
            self._bins[bin_id] = BinLevel(
                bin_id=bin_id,
                grade=cfg['grade'],
                capacity_g=cfg['capacity_g']
            )

    @property
    def state(self) -> BufferBinState:
        return self._state

    def add_beans(self, bin_id: str, weight_g: float) -> bool:
        """Add beans to a bin (called from upstream sorter)."""
        with self._lock:
            if bin_id not in self._bins:
                return False
            bin_level = self._bins[bin_id]
            bin_level.current_g = min(bin_level.current_g + weight_g, bin_level.capacity_g)
            bin_level.is_full = bin_level.current_g >= bin_level.capacity_g
            bin_level.is_empty = bin_level.current_g <= 0.1
            return True

    def get_bin_levels(self) -> Dict[str, Dict]:
        """Get all bin fill levels."""
        with self._lock:
            return {
                bid: {
                    'grade': bl.grade,
                    'current_g': round(bl.current_g, 2),
                    'capacity_g': bl.capacity_g,
                    'fill_pct': round(bl.fill_pct, 1),
                    'is_full': bl.is_full,
                    'is_empty': bl.is_empty,
                }
                for bid, bl in self._bins.items()
            }

    def get_ready_bins(self) -> List[str]:
        """Get bins that have enough beans for a batch (≥250g)."""
        with self._lock:
            return [
                bid for bid, bl in self._bins.items()
                if not bl.is_empty and bl.grade != 'buffer'
                and bl.current_g >= 250.0
            ]

    def dispense_to_roaster(self, bin_id: str, batch_weight_g: float = 250.0) -> bool:
        """
        Dispense beans from specified bin to roaster via spiral feeder.
        """
        with self._lock:
            if bin_id not in self._bins:
                return False
            if self._bins[bin_id].current_g < batch_weight_g:
                return False

            self._state = BufferBinState.DISPENSING

        # Select bin
        bin_index = list(self.BIN_CONFIG.keys()).index(bin_id)
        if not self.distributor.select_bin(bin_index):
            self._state = BufferBinState.IDLE
            return False

        # Dispense
        dispensed = self.feeder.dispense_batch(target_g=batch_weight_g)

        # Update bin level
        with self._lock:
            self._bins[bin_id].current_g -= dispensed
            self._bins[bin_id].is_empty = self._bins[bin_id].current_g <= 0.1
            self._state = BufferBinState.DISPENSE_DONE

        return True

    def auto_dispatch(self, batch_weight_g: float = 250.0) -> Optional[str]:
        """
        Automatically find a ready bin and dispense.
        Returns bin_id if successful, None otherwise.
        """
        ready = self.get_ready_bins()
        if not ready:
            return None
        bin_id = ready[0]  # FIFO
        success = self.dispense_to_roaster(bin_id, batch_weight_g)
        return bin_id if success else None

    def get_status(self) -> Dict:
        """Get full system status."""
        with self._lock:
            return {
                'state': self._state.value,
                'bins': self.get_bin_levels(),
                'ready_bins': self.get_ready_bins(),
                'feeder_dispensed_total_g': round(self.feeder._dispensed_g, 2),
                'grams_per_second': round(self.feeder.config.grams_per_second, 2),
                'target_dispense_time_s': round(self.feeder.config.target_dispense_time_s, 1),
            }


# ============================================================
# Physical Test Protocol
# ============================================================

BUFFER_BIN_PHYSICAL_TEST_PROTOCOL = """
缓冲料仓 + 螺旋给料 — 物理测试协议（6步）
============================================

【目的】验证缓冲仓分配、液位检测、螺旋给料精度

【设备准备】
- 缓冲仓3D打印件（PETG）
- 28BYJ-48步进电机 × 2（分配器 + 螺旋给料）
- DRV8833电机驱动模块 × 2
- Raspberry Pi 4
- 电容液位传感器 × 8（或红外光电传感器）
- 250g校准砝码（或已知重量的咖啡豆样本）
- 量杯 + 秒表

【Step 1】旋转分配器精度测试
操作：依次选择 bin 0-7，测量实际位置
通过标准：每个 bin 位置误差 < 1格（< 45°）

【Step 2】液位传感器标定
操作：向各格分别加入 0/25/50/75/100g 豆，记录传感器输出
通过标准：输出线性，重复性 σ < 5g

【Step 3】螺旋给料速率标定
操作：以120RPM运行螺旋给料10秒，收集并称重排出的豆
通过标准：测量值与理论值( mass_per_rev_g×RPM/60×10s )偏差 < ±10%

【Step 4】250g批次精度测试
操作：连续进行5次250g批次称重
通过标准：每次误差 < ±5g（2%）

【Step 5】分批循环测试
操作：连续8次批次（模拟接收到ROASTER_READY信号后自动出豆）
通过标准：每次250g，误差 < ±5g，间隔均匀

【Step 6】满仓压力测试
操作：将任一格填满至溢出临界，记录液位传感器报警时间
通过标准：液位传感器准确在95%容量时报警

【预计总时间】3小时（含准备）
"""


if __name__ == '__main__':
    # Quick sanity test
    cfg = SpiralFeederConfig()
    print(f"mass_per_rev_g: {cfg.mass_per_rev_g:.3f}")
    print(f"grams_per_second @ {cfg.rpm} RPM: {cfg.grams_per_second:.2f} g/s")
    print(f"250g dispense time: {cfg.target_dispense_time_s:.1f}s")
    print(f"steps_per_mm: {cfg.steps_per_mm:.1f}")
    print(f"mass_per_step_g: {cfg.mass_per_step_g:.6f}")

    print("\n--- Buffer Bin Controller Test ---")
    ctrl = BufferBinController()
    print(f"Initial state: {ctrl.state.value}")
    print(f"Ready bins: {ctrl.get_ready_bins()}")

    # Simulate adding beans
    ctrl.add_beans('A1', 300.0)  # Overfills to 100g
    ctrl.add_beans('A1', 50.0)   # Can't add past capacity
    print(f"\nA1 level: {ctrl._bins['A1'].current_g}g / {ctrl._bins['A1'].capacity_g}g")
    print(f"A1 fill%: {ctrl._bins['A1'].fill_pct:.1f}%")

    # Add enough for a batch
    ctrl.add_beans('A1', 150.0)  # Fill up to 100g
    print(f"\nA1 after more: {ctrl._bins['A1'].current_g}g")
    print(f"Ready bins: {ctrl.get_ready_bins()}")

    status = ctrl.get_status()
    print(f"\nBuffer Status:")
    print(f"  State: {status['state']}")
    print(f"  Feeder output: {status['grams_per_second']} g/s")
    print(f"  250g dispense: {status['target_dispense_time_s']}s")

    print("\n--- Physical Test Protocol ---")
    print(BUFFER_BIN_PHYSICAL_TEST_PROTOCOL)
