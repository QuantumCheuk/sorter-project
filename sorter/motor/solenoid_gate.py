"""
Weighing Station Control Module
================================
Integrates:
- Load Cell (HX711) for weight measurement
- Solenoid Gate for bean release
- State machine for weighing cycle control

HUSKY-SORTER-001 | Author: Little Husky | Date: 2026-04-14
"""

import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock

from sorter.sensors.load_cell import LoadCell, HX711Config


class WeighingState(Enum):
    """Weighing station state machine states."""
    IDLE = "idle"
    BEAN_EXPECTED = "bean_expected"
    FILLING = "filling"
    SETTLING = "settling"
    MEASURING = "measuring"
    RELEASING = "releasing"
    RESETTING = "resetting"


@dataclass
class WeighingStationConfig:
    """Weighing station configuration."""
    # Timing (ms)
    settle_time_ms: int = 50       # Wait for bean to settle
    hx711_sample_time_ms: int = 15 # HX711 sampling time
    solenoid_actuate_ms: int = 15  # Solenoid pull-in time
    bean_release_ms: int = 30      # Bean fall time from cup
    total_cycle_ms: int = 80        # Total cycle time
    
    # Solenoid GPIO
    solenoid_gpio: int = 26        # GPIO pin for solenoid (active HIGH)
    
    # Bean weight range
    min_bean_weight_g: float = 0.08
    max_bean_weight_g: float = 0.30
    
    # Auto-tare
    auto_tare_interval_s: float = 30.0  # Re-tare every 30 seconds


@dataclass
class WeighingResult:
    """Result of a weighing cycle."""
    bean_id: int
    weight_g: float
    state: str
    quality_class: str = "UNKNOWN"
    anomaly: str = "none"
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.anomaly != "none":
            self.state = f"{self.state}_ANOMALY"


class WeighingStation:
    """
    High-level weighing station controller.
    
    Manages:
    - Load cell reading and filtering
    - Solenoid gate control
    - State machine for weighing cycle
    - Auto-tare for temperature drift compensation
    - Statistics tracking
    
    Usage:
        station = WeighingStation()
        station.start()
        
        # When bean arrives from color sensor:
        station.expect_bean(bean_id=1)
        
        # In main loop:
        result = station.update()  # Call frequently, non-blocking
        if result:
            print(f"Bean {result.bean_id}: {result.weight_g*1000:.1f}mg")
        
        # Cleanup:
        station.stop()
    """
    
    def __init__(self, config: Optional[WeighingStationConfig] = None):
        self.config = config or WeighingStationConfig()
        self._state = WeighingState.IDLE
        self._lock = Lock()
        self._running = False
        self._hx711_thread: Optional[threading.Thread] = None
        self._auto_tare_thread: Optional[threading.Thread] = None
        
        # Bean tracking
        self._current_bean_id: Optional[int] = None
        self._bean_queue: list = []
        self._last_result: Optional[WeighingResult] = None
        
        # Statistics
        self._total_measured = 0
        self._total_anomalies = 0
        
        # Initialize load cell
        self._init_load_cell()
        
        # Initialize solenoid GPIO
        self._init_solenoid()
        
        # Callbacks
        self._on_result: Optional[Callable[[WeighingResult], None]] = None
    
    def _init_load_cell(self):
        """Initialize the load cell."""
        hx711_config = HX711Config(
            data_pin=5,
            clock_pin=6,
            gain=128,
            reference_unit=1.0,
            offset=0.0
        )
        self.load_cell = LoadCell(hx711_config)
        self.load_cell.min_bean_weight_g = self.config.min_bean_weight_g
        self.load_cell.max_bean_weight_g = self.config.max_bean_weight_g
        
        # Initial tare
        self.load_cell.tare(samples=10)
    
    def _init_solenoid(self):
        """Initialize solenoid GPIO."""
        self._solenoid_gpio = self.config.solenoid_gpio
        
        # Try to set up GPIO
        self._gpio = None
        self._gpio_mode = "mock"
        
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._solenoid_gpio, GPIO.OUT, initial=GPIO.LOW)
            self._gpio_mode = "real"
            print(f"[WeighingStation] Solenoid GPIO{self._solenoid_gpio} initialized (REAL mode)")
        except (ImportError, RuntimeError):
            print(f"[WeighingStation] Solenoid GPIO{self._solenoid_gpio} initialized (MOCK mode)")
    
    def start(self):
        """Start the weighing station."""
        if self._running:
            return
        
        self._running = True
        self._state = WeighingState.IDLE
        
        # Start auto-tare thread
        self._auto_tare_thread = threading.Thread(target=self._auto_tare_loop, daemon=True)
        self._auto_tare_thread.start()
        
        print("[WeighingStation] Started")
    
    def stop(self):
        """Stop the weighing station."""
        self._running = False
        
        # Release solenoid
        self._solenoid_off()
        
        if self._gpio and self._gpio_mode == "real":
            self._gpio.cleanup([self._solenoid_gpio])
        
        print("[WeighingStation] Stopped")
    
    def expect_bean(self, bean_id: int):
        """
        Notify the station that a bean is expected.
        Called when bean is detected at T2 (color sensor bottom).
        
        The bean will fall from the color sensor to the weighing cup
        in approximately 15ms (60mm drop).
        """
        with self._lock:
            self._current_bean_id = bean_id
            self._bean_queue.append(bean_id)
            
            if self._state == WeighingState.IDLE:
                self._state = WeighingState.BEAN_EXPECTED
        
        # Trigger filling state after expected fall time
        threading.Timer(0.015, self._on_bean_arrived).start()
    
    def _on_bean_arrived(self):
        """Called when bean physically arrives at weighing cup."""
        with self._lock:
            if self._state == WeighingState.BEAN_EXPECTED:
                self._state = WeighingState.FILLING
                
                # Transition to settling after short fill time
                threading.Timer(0.005, self._start_settling).start()
    
    def _start_settling(self):
        """Start the settling phase."""
        with self._lock:
            self._state = WeighingState.SETTLING
        
        # After settling time, start measurement
        settling_s = self.config.settle_time_ms / 1000.0
        threading.Timer(settling_s, self._start_measuring).start()
    
    def _start_measuring(self):
        """Start the HX711 measurement."""
        with self._lock:
            self._state = WeighingState.MEASURING
        
        bean_id = self._current_bean_id
        
        # Take HX711 reading (blocking, ~15ms)
        weight = self.load_cell.measure_single(samples=3)
        
        if weight is None:
            weight = 0.0
        
        # Classify
        anomaly = self.load_cell.detect_anomaly(weight)
        self.load_cell.record_bean(weight)
        
        # Determine quality class
        if anomaly == "normal":
            if weight > 0.13:
                quality = "A"
            else:
                quality = "B"
        elif anomaly == "too_light":
            quality = "C"
        elif anomaly == "too_heavy":
            quality = "B"
        else:
            quality = "C"
        
        # Create result
        result = WeighingResult(
            bean_id=bean_id,
            weight_g=weight,
            state=self._state.value,
            quality_class=quality,
            anomaly=anomaly
        )
        
        self._last_result = result
        self._total_measured += 1
        if anomaly != "none":
            self._total_anomalies += 1
        
        # Trigger release
        self._trigger_release()
        
        # Notify callback
        if self._on_result:
            self._on_result(result)
    
    def _trigger_release(self):
        """Trigger the solenoid to release the bean."""
        with self._lock:
            self._state = WeighingState.RELEASING
        
        # Activate solenoid
        self._solenoid_on()
        
        # Keep solenoid on for release duration
        release_s = (self.config.solenoid_actuate_ms + self.config.bean_release_ms) / 1000.0
        threading.Timer(release_s, self._complete_release).start()
    
    def _complete_release(self):
        """Complete the release and reset for next bean."""
        self._solenoid_off()
        
        with self._lock:
            self._state = WeighingState.RESETTING
            self._current_bean_id = None
        
        # Small delay then return to idle
        threading.Timer(0.010, self._return_to_idle).start()
    
    def _return_to_idle(self):
        """Return to idle state."""
        with self._lock:
            self._state = WeighingState.IDLE
            # Check if there's a bean waiting
            if self._bean_queue:
                next_bean_id = self._bean_queue.pop(0)
                self.expect_bean(next_bean_id)
    
    def _solenoid_on(self):
        """Activate the solenoid."""
        if self._gpio and self._gpio_mode == "real":
            self._gpio.output(self._solenoid_gpio, self._gpio.HIGH)
        else:
            pass  # Mock mode: just log
    
    def _solenoid_off(self):
        """Deactivate the solenoid."""
        if self._gpio and self._gpio_mode == "real":
            self._gpio.output(self._solenoid_gpio, self._gpio.LOW)
        else:
            pass  # Mock mode
    
    def _auto_tare_loop(self):
        """Background thread for auto-tare."""
        interval = self.config.auto_tare_interval_s
        while self._running:
            time.sleep(interval)
            if self._state == WeighingState.IDLE:
                success = self.load_cell.tare(samples=5)
                if success:
                    pass  # Could log: print(f"[WeighingStation] Auto-tare successful")
    
    def update(self) -> Optional[WeighingResult]:
        """
        Non-blocking update. Call this in your main loop.
        
        Returns:
            WeighingResult if a bean was just measured, None otherwise.
        """
        # This is used for synchronous (non-callback-based) usage
        # In our threaded implementation, results come via callback
        # But we expose last_result for polling-based code
        result = self._last_result
        self._last_result = None
        return result
    
    def get_result(self) -> Optional[WeighingResult]:
        """Get the last weighing result (non-destructive)."""
        return self._last_result
    
    def get_statistics(self) -> dict:
        """Get current statistics."""
        stats = self.load_cell.get_statistics()
        stats['total_measured'] = self._total_measured
        stats['total_anomalies'] = self._total_anomalies
        stats['anomaly_rate_pct'] = (
            self._total_anomalies / self._total_measured * 100
            if self._total_measured > 0 else 0
        )
        stats['state'] = self._state.value
        return stats
    
    def reset_statistics(self):
        """Reset bean statistics."""
        self.load_cell.reset_session()
        self._total_measured = 0
        self._total_anomalies = 0
    
    @property
    def state(self) -> WeighingState:
        """Current state."""
        return self._state
    
    @property
    def is_idle(self) -> bool:
        """Check if station is idle."""
        return self._state == WeighingState.IDLE
    
    @property
    def is_busy(self) -> bool:
        """Check if station is busy processing a bean."""
        return self._state not in [WeighingState.IDLE, WeighingState.BEAN_EXPECTED]


# ============================================================================
# DEMO / TEST
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Weighing Station Controller Test")
    print("=" * 60)
    
    station = WeighingStation()
    station.start()
    
    # Collect results via callback
    results = []
    def on_result(r: WeighingResult):
        results.append(r)
        print(f"\n  🎉 BEAN MEASURED: id={r.bean_id}, "
              f"weight={r.weight_g*1000:.1f}mg, "
              f"class={r.quality_class}, "
              f"anomaly={r.anomaly}")
    
    station._on_result = on_result
    
    # Simulate 10 beans arriving
    import random
    print("\n  Simulating 10 beans through weighing station...\n")
    
    for i in range(1, 11):
        # In real system, bean arrives ~85ms after T2 trigger
        print(f"  → Bean {i} expected")
        station.expect_bean(bean_id=i)
        time.sleep(0.35)  # 350ms between beans (slightly above 333ms target)
    
    # Wait for all beans to complete
    time.sleep(1.0)
    
    # Print statistics
    stats = station.get_statistics()
    print(f"\n  📊 Statistics:")
    print(f"     Total measured: {stats['total_measured']}")
    print(f"     Mean weight: {stats['mean_g']*1000:.1f}mg")
    print(f"     Std dev: {stats['std_g']*1000:.1f}mg")
    print(f"     Anomaly rate: {stats['anomaly_rate_pct']:.1f}%")
    print(f"     Final state: {stats['state']}")
    
    station.stop()
    print("\n  ✅ Test complete")
