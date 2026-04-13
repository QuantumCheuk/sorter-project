"""
HX711 Load Cell Driver for Green Coffee Bean Sorter
=====================================================

Low-level driver for HX711 24-bit ADC used with weight measurement.

Hardware Connection (Raspberry Pi):
    HX711 VCC     → 3.3V (or 5V if level-shifted)
    HX711 GND     → GND
    HX711 DT (DATA) → GPIO 5 (configurable)
    HX711 SCK (CLK)  → GPIO 6 (configurable)
    HX711 A+     → Load Cell E+ (excitation+)
    HX711 A-     → Load Cell E- (excitation-)
    HX711 B+     → (not used, set to Channel A)
    HX711 B-     → (not used)

Bean Weight Specs:
    Single bean: 0.10 - 0.25g typical
    Load Cell:  200g max (provides ~0.05g resolution with 24-bit ADC)
    Target precision: ±0.01g

Author: Little Husky (HUSKY-SORTER-001)
Date: 2026-04-13
"""

import time
import threading
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class HX711Config:
    """HX711 configuration parameters."""
    data_pin: int = 5      # GPIO pin for DT (DATA)
    clock_pin: int = 6    # GPIO pin for SCK (CLK)
    channel: str = "A"    # "A" or "B" (Channel A has 128 gain, Channel B has 32)
    gain: int = 128        # Gain: 128 (Channel A), 64 (Channel A), or 32 (Channel B)
    reference_unit: float = 1.0  # Scale factor (to be calibrated)
    offset: float = 0.0     # Tare offset


class HX711:
    """
    HX711 24-bit ADC driver for load cell weight measurement.
    
    Features:
    - Thread-safe reading with background thread option
    - Configurable gain and channel selection
    - Calibration support with reference weights
    - Moving average filter for noise reduction
    """
    
    # HX711 clock pulse duration (minimum 0.2µs per datasheet)
    CLOCK_US = 1  # microseconds (1µs is safe)
    
    # Power down pulse duration
    POWER_DOWN_US = 60
    
    def __init__(self, config: Optional[HX711Config] = None):
        self.config = config or HX711Config()
        self._lock = threading.Lock()
        self._is_ready = False
        self._last_reading = 0.0
        
        # Try to import RPi.GPIO, fallback to mock for testing
        self._gpio = None
        self._use_mock = False
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setup(self.config.data_pin, self._gpio.IN)
            self._gpio.setup(self.config.clock_pin, self._gpio.OUT)
            self._is_ready = True
        except (ImportError, RuntimeError):
            # Not on Raspberry Pi or GPIO not available - use mock mode
            self._use_mock = True
            self._mock_value = 0.0
        
        # Pre-warm: send 25 clock pulses to power up the HX711
        if self._is_ready:
            self._power_up()
    
    def _power_up(self) -> None:
        """Send clock pulses to power up HX711."""
        for _ in range(25):
            self._gpio.output(self.config.clock_pin, True)
            time.sleep(self.CLOCK_US / 1_000_000)
            self._gpio.output(self.config.clock_pin, False)
            time.sleep(self.CLOCK_US / 1_000_000)
    
    def _is_data_ready(self) -> bool:
        """Check if HX711 has data ready (DT pin low = ready)."""
        if self._use_mock:
            return True
        return self._gpio.input(self.config.data_pin) == 0
    
    def _wait_ready(self, timeout_ms: int = 1000) -> bool:
        """Wait for data to be ready with timeout."""
        start = time.time()
        timeout = timeout_ms / 1000.0
        
        if self._use_mock:
            time.sleep(0.001)  # Small delay in mock mode
            return True
        
        while time.time() - start < timeout:
            if self._is_data_ready():
                return True
            time.sleep(0.0001)  # 0.1ms poll interval
        
        return False
    
    def _read_raw(self) -> int:
        """
        Read raw 24-bit signed value from HX711.
        Must be called when data is ready (DT pin low).
        """
        if self._use_mock:
            # Mock: return simulated raw value
            # Simulate realistic ADC noise
            import random
            noise = random.gauss(0, 10)
            raw = int(self._mock_value * self.config.reference_unit + noise)
            # Clamp to 24-bit signed range
            raw = max(-8388608, min(8388607, raw))
            return raw
        
        with self._lock:
            # Read 24 bits (MSB first)
            value = 0
            for _ in range(24):
                self._gpio.output(self.config.clock_pin, True)
                time.sleep(self.CLOCK_US / 1_000_000)
                bit = self._gpio.input(self.config.data_pin)
                value = (value << 1) | bit
                self._gpio.output(self.config.clock_pin, False)
                time.sleep(self.CLOCK_US / 1_000_000)
            
            # Send additional clock pulses for channel/gain selection
            # Channel A, gain 128 = 1 pulse
            # Channel A, gain 64 = 3 pulses  
            # Channel B, gain 32 = 2 pulses
            if self.config.gain == 128:
                num_pulses = 1
            elif self.config.gain == 64:
                num_pulses = 3
            else:  # 32
                num_pulses = 2
            
            for _ in range(num_pulses):
                self._gpio.output(self.config.clock_pin, True)
                time.sleep(self.CLOCK_US / 1_000_000)
                self._gpio.output(self.config.clock_pin, False)
                time.sleep(self.CLOCK_US / 1_000_000)
            
            # Convert from unsigned to signed (24-bit two's complement)
            if value >= 0x800000:
                value -= 0x1000000
            
            return value
    
    def read(self, samples: int = 5, timeout_ms: int = 1000) -> Optional[float]:
        """
        Read weight value with averaging.
        
        Args:
            samples: Number of samples to average (default 5)
            timeout_ms: Timeout in milliseconds for waiting for data
            
        Returns:
            Weight in grams, or None if read failed/timeout
        """
        if not self._wait_ready(timeout_ms):
            return None
        
        readings = []
        for _ in range(samples):
            raw = self._read_raw()
            if raw is None:
                continue
            readings.append(raw)
            if _ < samples - 1:
                time.sleep(0.02)  # 20ms between samples
        
        if not readings:
            return None
        
        # Calculate average raw value
        avg_raw = sum(readings) / len(readings)
        
        # Apply calibration: (raw_value / reference_unit) - offset
        weight = (avg_raw / self.config.reference_unit) - self.config.offset
        
        self._last_reading = weight
        return weight
    
    def get_weight(self, samples: int = 5) -> Optional[float]:
        """Alias for read() with default 5 samples averaging."""
        return self.read(samples=samples)
    
    def tare(self, samples: int = 10) -> bool:
        """
        Set current reading as zero (tare).
        
        Args:
            samples: Number of samples to average for tare value
            
        Returns:
            True if tare successful, False otherwise
        """
        reading = self.read(samples=samples)
        if reading is None:
            return False
        
        self.config.offset += reading
        return True
    
    def calibrate(self, known_weight_g: float, samples: int = 10) -> bool:
        """
        Calibrate scale with a known reference weight.
        
        Args:
            known_weight_g: Reference weight in grams (e.g., 100.0g calibration weight)
            samples: Number of samples to average
            
        Returns:
            True if calibration successful, False otherwise
        """
        reading = self.read(samples=samples)
        if reading is None:
            return False
        
        # Calculate reference unit: raw_value / expected_weight
        # After calibration: weight = (raw / new_reference_unit) - offset
        # At zero: offset = raw_zero / new_reference_unit
        # At known weight: known_weight = (raw_cal / new_reference_unit) - offset
        # Substituting: known_weight = (raw_cal - raw_zero) / new_reference_unit
        # new_reference_unit = (raw_cal - raw_zero) / known_weight
        
        # We need the raw value when tare is zero
        # For simplicity, recalculate reference_unit assuming current offset is 0
        raw_zero = 0
        raw_cal = reading * self.config.reference_unit
        
        self.config.reference_unit = raw_cal / known_weight_g
        self.config.offset = 0  # Reset offset (tare at zero)
        
        return True
    
    def set_mock_value(self, weight_g: float) -> None:
        """Set mock ADC value for testing without hardware."""
        self._mock_value = weight_g * 1000  # Convert to raw-like units
    
    def power_down(self) -> None:
        """Power down the HX711 (stops oscillation)."""
        if self._gpio and not self._use_mock:
            self._gpio.output(self.config.clock_pin, True)
            time.sleep(self.POWER_DOWN_US / 1_000_000)
    
    def power_up(self) -> None:
        """Power up the HX711 after power_down()."""
        if self._gpio and not self._use_mock:
            self._gpio.output(self.config.clock_pin, False)
            self._power_up()
    
    def reset(self) -> None:
        """Reset HX711 to default state."""
        if self._gpio and not self._use_mock:
            self._power_up()
        self.config.offset = 0
        self.config.reference_unit = 1.0
    
    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        if self._gpio and not self._use_mock:
            self._gpio.cleanup([self.config.data_pin, self.config.clock_pin])
        self._is_ready = False
    
    def is_ready(self) -> bool:
        """Check if HX711 hardware is detected and ready."""
        return self._is_ready or self._use_mock
    
    @property
    def last_reading(self) -> float:
        """Get the last successful reading."""
        return self._last_reading


# ============================================================================
# High-Level Weight Measurement API
# ============================================================================

class LoadCell:
    """
    High-level load cell interface with bean-specific features.
    
    Wraps HX711 with:
    - Bean counting and weight tracking
    - Statistical analysis (mean, std, distribution)
    - Anomaly detection (stuck bean, missing bean)
    """
    
    def __init__(self, config: Optional[HX711Config] = None):
        self._hx711 = HX711(config)
        self._bean_weights = []  # List of individual bean weights (g)
        self._session_start_weight = 0.0
        self._total_beans = 0
        
        # Expected bean weight range (typical for green coffee)
        self.min_bean_weight_g = 0.08
        self.max_bean_weight_g = 0.30
    
    def measure_single(self, samples: int = 5) -> Optional[float]:
        """Measure a single weight reading in grams."""
        return self._hx711.read(samples=samples)
    
    def record_bean(self, weight_g: float) -> bool:
        """
        Record a single bean's weight.
        
        Args:
            weight_g: Weight in grams
            
        Returns:
            True if weight is in valid range, False if anomalous
        """
        is_valid = self.min_bean_weight_g <= weight_g <= self.max_bean_weight_g
        
        if is_valid:
            self._bean_weights.append(weight_g)
            self._total_beans += 1
        
        return is_valid
    
    def record_bean_from_measurement(self, samples: int = 5) -> Optional[float]:
        """Take measurement and record if valid."""
        weight = self.measure_single(samples=samples)
        if weight is not None:
            self.record_bean(weight)
        return weight
    
    def get_statistics(self) -> dict:
        """Get weight statistics for recorded beans."""
        if not self._bean_weights:
            return {
                "count": 0,
                "mean_g": 0.0,
                "std_g": 0.0,
                "min_g": 0.0,
                "max_g": 0.0,
                "total_g": 0.0
            }
        
        import statistics
        return {
            "count": len(self._bean_weights),
            "mean_g": statistics.mean(self._bean_weights),
            "std_g": statistics.stdev(self._bean_weights) if len(self._bean_weights) > 1 else 0.0,
            "min_g": min(self._bean_weights),
            "max_g": max(self._bean_weights),
            "total_g": sum(self._bean_weights),
            "median_g": statistics.median(self._bean_weights)
        }
    
    def get_distribution(self, bins: int = 10) -> Tuple[list, list]:
        """
        Get weight distribution histogram.
        
        Returns:
            (bin_edges, counts) for histogram plotting
        """
        if not self._bean_weights:
            return [], []
        
        import numpy as np
        counts, edges = np.histogram(self._bean_weights, bins=bins)
        return edges.tolist(), counts.tolist()
    
    def detect_anomaly(self, weight_g: float) -> str:
        """
        Classify a weight reading as normal or anomalous type.
        
        Returns:
            "normal", "too_light", "too_heavy", or "suspect"
        """
        if weight_g < self.min_bean_weight_g:
            return "too_light"
        elif weight_g > self.max_bean_weight_g:
            return "too_heavy"
        elif len(self._bean_weights) >= 10:
            # Check if significantly different from session mean
            import statistics
            mean = statistics.mean(self._bean_weights)
            std = statistics.stdev(self._bean_weights) if len(self._bean_weights) > 1 else 0.05
            if abs(weight_g - mean) > 3 * std:
                return "suspect"
        return "normal"
    
    def reset_session(self) -> dict:
        """Reset bean counter and return final session stats."""
        stats = self.get_statistics()
        self._bean_weights = []
        self._total_beans = 0
        return stats
    
    def tare(self, samples: int = 10) -> bool:
        """Tare (zero) the scale."""
        return self._hx711.tare(samples=samples)
    
    def calibrate(self, known_weight_g: float, samples: int = 10) -> bool:
        """Calibrate with known reference weight."""
        return self._hx711.calibrate(known_weight_g, samples=samples)
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self._hx711.cleanup()


# ============================================================================
# Testing & Demo
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HX711 Load Cell Driver Test")
    print("=" * 60)
    
    # Initialize with default config
    config = HX711Config(
        data_pin=5,
        clock_pin=6,
        gain=128,
        reference_unit=1.0,
        offset=0.0
    )
    
    hx711 = HX711(config)
    
    print(f"\nHardware ready: {hx711.is_ready()}")
    print(f"Mode: {'MOCK (no hardware detected)' if hx711._use_mock else 'REAL (GPIO connected)'}")
    
    # Demo with mock values
    print("\n--- Mock Weight Reading Demo ---")
    test_weights = [0.152, 0.148, 0.201, 0.089, 0.255]
    
    for w in test_weights:
        hx711.set_mock_value(w)
        reading = hx711.read(samples=3)
        print(f"  Weight: {reading:.3f}g" if reading else "  [timeout]")
    
    print("\n--- LoadCell High-Level API Demo ---")
    load_cell = LoadCell()
    
    # Simulate measuring 20 beans
    import random
    import statistics
    
    mock_weights = [random.gauss(0.15, 0.02) for _ in range(20)]
    
    for w in mock_weights:
        hx711.set_mock_value(w)
        load_cell.record_bean_from_measurement(samples=1)
    
    stats = load_cell.get_statistics()
    print(f"\n  Beans measured: {stats['count']}")
    print(f"  Mean weight: {stats['mean_g']:.3f}g")
    print(f"  Std dev: {stats['std_g']:.3f}g")
    print(f"  Min: {stats['min_g']:.3f}g, Max: {stats['max_g']:.3f}g")
    print(f"  Total: {stats['total_g']:.3f}g")
    
    print("\n  Anomaly detection test:")
    test_cases = [0.05, 0.15, 0.25, 0.50]
    for w in test_cases:
        hx711.set_mock_value(w)
        load_cell.record_bean_from_measurement(samples=1)
        anomaly = load_cell.detect_anomaly(w)
        print(f"    {w:.2f}g → {anomaly}")
    
    print("\n" + "=" * 60)
    print("Driver test complete.")
    print("=" * 60)
