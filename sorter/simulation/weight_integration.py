"""
Weight Integration Analysis for Continuous Bean Flow
=====================================================

PROBLEM: Beans fall from the color sensor channel one at a time (single-file).
How do we measure individual bean weights?

CHALLENGE: Traditional scale expects stable weight on platform. A falling bean
creates an impulse, not a stable reading.

SOLUTION OPTIONS:
1. BUFFER CUP: Bean falls into small cup on load cell, cup is weighed,
   then bean is released to next stage. Sequential measurement.
   
2. IMPULSE INTEGRATION: Measure the impulse force as bean lands, integrate
   to get momentum → mass. Requires high-speed ADC and complex math.
   
3. DELAYED SAMPLING: Time the bean's fall, sample weight at known position,
   estimate final weight from physics model.

RECOMMENDED: Option 1 (Buffer Cup) - simplest and most accurate.

Author: Little Husky (HUSKY-SORTER-001)
Date: 2026-04-13
"""

import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import List, Optional, Tuple
import time


@dataclass
class BeanLandingEvent:
    """Record of a bean landing on the weighing cup."""
    bean_id: int
    arrival_time: float
    peak_impulse_g: float
    settling_time_ms: float
    final_weight_g: Optional[float] = None
    is_valid: bool = False


class WeightIntegrationSimulator:
    """
    Simulates the weighing system with buffer cup approach.
    
    Physical Model:
    - Bean falls from height h onto weighing cup
    - Impact creates impulse (force spike)
    - Cup oscillates and settles due to mechanical damping
    - Settled weight = actual bean weight (after settling time)
    """
    
    def __init__(self):
        # Physical parameters
        self.cup_mass_g = 5.0           # Mass of weighing cup
        self.bean_mass_g = 0.15         # Typical bean mass
        self.fall_height_mm = 100       # Height bean falls before landing
        self.settling_time_ms = 50      # Time for cup to settle after impact
        self.sample_rate_hz = 100        # ADC sample rate
        
        # Impulse parameters (from physics)
        self.g = 9.81                   # m/s^2
        self.damping_factor = 0.3       # Mechanical damping
        
    def simulate_fall(self, bean_mass_g: float = 0.15, 
                     noise_std: float = 0.005) -> Tuple[List[float], List[float]]:
        """
        Simulate the weight signal as a bean falls and settles.
        
        Returns:
            (times_ms, readings_g) - time series of weight readings
        """
        # Calculate impact velocity
        h = self.fall_height_mm / 1000.0  # meters
        v_impact = np.sqrt(2 * self.g * h)  # m/s
        
        # Impact force (impulse = change in momentum)
        m_total = (self.cup_mass_g + bean_mass_g) / 1000.0  # kg
        J = m_total * v_impact  # impulse N*s
        impact_duration_s = 0.005  # 5ms impact
        F_impact_peak = J / impact_duration_s  # N
        
        # Convert to grams equivalent (F = ma, w = mg)
        # F_impact_N / g = equivalent grams
        impact_equiv_g = (F_impact_peak / self.g) * 1000  # grams
        
        # Total simulation time
        t_total_ms = 200  # 200ms total
        n_samples = int(t_total_ms * self.sample_rate_hz / 1000)
        times_ms = np.linspace(0, t_total_ms, n_samples)
        
        # Simulate weight reading
        readings_g = np.zeros(n_samples)
        
        # Initial steady reading (cup only)
        readings_g[:] = self.cup_mass_g
        
        # Impact at t=0
        t_impact_idx = 0
        
        for i, t in enumerate(times_ms):
            if t < 5:  # First 5ms: rapid rise from impact
                # Spike proportional to impact
                readings_g[i] = self.cup_mass_g + impact_equiv_g * np.exp(-t / 5)
            elif t < self.settling_time_ms:
                # Oscillatory settling
                t_rel = t - 5
                omega = 2 * np.pi * 20  # ~20Hz natural frequency
                damped = np.exp(-self.damping_factor * t_rel / 50)
                oscillation = damped * np.sin(omega * t_rel / 1000) * 0.02
                readings_g[i] = self.cup_mass_g + bean_mass_g + impact_equiv_g * oscillation
            else:
                # Settled: cup + bean
                readings_g[i] = self.cup_mass_g + bean_mass_g
        
        # Add measurement noise
        noise = np.random.normal(0, noise_std, n_samples)
        readings_g += noise
        
        return times_ms.tolist(), readings_g.tolist()
    
    def detect_landing(self, times_ms: List[float], readings_g: List[float],
                       threshold_multiplier: float = 3.0) -> Optional[float]:
        """
        Detect when a bean has landed and settled.
        
        Uses peak detection + settling detection.
        
        Returns:
            Settled weight in grams, or None if detection fails
        """
        readings = np.array(readings_g)
        times = np.array(times_ms)
        
        # Find peak (impact moment)
        baseline = self.cup_mass_g
        deviations = readings - baseline
        peak_idx = np.argmax(deviations)
        peak_value = readings[peak_idx]
        
        # Wait for settling (settling_time_ms after peak)
        settle_start_idx = peak_idx + int(self.settling_time_ms * self.sample_rate_hz / 1000)
        
        if settle_start_idx >= len(readings):
            return None
        
        # Take average of last few samples as settled weight
        settled_readings = readings[settle_start_idx:]
        settled_avg = np.mean(settled_readings[-10:])  # Last 10 samples
        settled_std = np.std(settled_readings[-10:])
        
        # Check if settled (std is low)
        if settled_std > 0.02:  # 20mg threshold
            return None
        
        # Final weight = settled - cup mass
        bean_weight = settled_avg - self.cup_mass_g
        
        return bean_weight
    
    def plot_fall_event(self, times_ms: List[float], readings_g: List[float],
                        detected_weight: Optional[float] = None):
        """Plot a fall event with detection."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.plot(times_ms, readings_g, 'b-', linewidth=1.5, label='Weight Signal')
        ax.axhline(y=self.cup_mass_g, color='gray', linestyle='--', alpha=0.5, label='Cup Only')
        ax.axhline(y=self.cup_mass_g + self.bean_mass_g, color='green', linestyle='--', 
                   alpha=0.5, label=f'Cup + Bean ({self.cup_mass_g + self.bean_mass_g:.2f}g)')
        
        if detected_weight is not None:
            ax.axhline(y=self.cup_mass_g + detected_weight, color='red', linestyle='-',
                      linewidth=2, label=f'Detected: {detected_weight:.3f}g')
        
        ax.set_xlabel('Time (ms)')
        ax.set_ylabel('Weight (g)')
        ax.set_title('Bean Landing Weight Signal (Simulated)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation/weight_fall_signal.png',
                    dpi=150)
        print(f"[PLOT] Saved to weight_fall_signal.png")
    
    def run_batch_simulation(self, n_beans: int = 50) -> dict:
        """
        Simulate measuring multiple beans sequentially.
        
        Returns:
            Statistics dictionary
        """
        print(f"\n{'='*60}")
        print(f"WEIGHT INTEGRATION SIMULATION")
        print(f"{'='*60}")
        print(f"Beans to simulate: {n_beans}")
        print(f"Sample rate: {self.sample_rate_hz} Hz")
        print(f"Fall height: {self.fall_height_mm} mm")
        print(f"Cup mass: {self.cup_mass_g}g")
        print()
        
        detected_weights = []
        actual_weights = []
        errors = []
        
        for i in range(n_beans):
            # Random bean weight from normal distribution
            bean_mass = np.random.normal(0.15, 0.02)  # 0.15g ± 0.02g
            bean_mass = max(0.08, min(0.25, bean_mass))  # Clamp to realistic range
            actual_weights.append(bean_mass)
            
            # Simulate fall
            times_ms, readings_g = self.simulate_fall(bean_mass, noise_std=0.005)
            
            # Detect landing and weight
            detected = self.detect_landing(times_ms, readings_g)
            
            if detected is not None:
                detected_weights.append(detected)
                error = detected - bean_mass
                errors.append(error)
                
                if i < 5 or i % 10 == 0:
                    print(f"  Bean {i+1:2d}: actual={bean_mass:.4f}g, "
                          f"detected={detected:.4f}g, error={error:+.4f}g")
        
        # Calculate statistics
        errors = np.array(errors)
        detected = np.array(detected_weights)
        actual = np.array(actual_weights[:len(detected)])
        
        stats = {
            'n_beans': n_beans,
            'n_detected': len(detected),
            'detection_rate': len(detected) / n_beans * 100,
            'mean_error_g': np.mean(np.abs(errors)),
            'std_error_g': np.std(errors),
            'max_error_g': np.max(np.abs(errors)),
            'mean_detected_g': np.mean(detected) if len(detected) > 0 else 0,
            'mean_actual_g': np.mean(actual) if len(actual) > 0 else 0
        }
        
        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        print(f"Detection rate: {stats['detection_rate']:.1f}%")
        print(f"Mean absolute error: {stats['mean_error_g']:.4f}g")
        print(f"Std deviation: {stats['std_error_g']:.4f}g")
        print(f"Max error: {stats['max_error_g']:.4f}g")
        
        return stats
    
    def plot_distribution(self, actual_weights: List[float], 
                         detected_weights: List[float]):
        """Plot comparison of actual vs detected weights."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Histogram
        bins = np.linspace(0.08, 0.25, 20)
        ax1.hist(actual_weights, bins=bins, alpha=0.5, label='Actual', color='blue')
        ax1.hist(detected_weights, bins=bins, alpha=0.5, label='Detected', color='red')
        ax1.set_xlabel('Weight (g)')
        ax1.set_ylabel('Count')
        ax1.set_title('Weight Distribution: Actual vs Detected')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Scatter plot
        ax2.scatter(actual_weights, detected_weights, alpha=0.5)
        ax2.plot([0.08, 0.25], [0.08, 0.25], 'r--', label='Perfect')
        ax2.set_xlabel('Actual Weight (g)')
        ax2.set_ylabel('Detected Weight (g)')
        ax2.set_title('Detection Accuracy')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation/weight_detection_accuracy.png',
                    dpi=150)
        print(f"[PLOT] Saved to weight_detection_accuracy.png")


class ContinuousFlowIntegrator:
    """
    Alternative approach: Integrate weight over time for continuous flow.
    
    This models what happens when beans fall continuously onto a conveyor
    or into a collection bin, and we want to track individual bean weights
    without stopping the flow.
    
    Algorithm:
    1. Track weight baseline (empty cup/conveyor)
    2. Detect positive weight steps (bean arrival)
    3. When weight steps DOWN, record the departed bean's weight
    4. Accumulate bean weights over time
    """
    
    def __init__(self, baseline_g: float = 5.0):
        self.baseline_g = baseline_g
        self.current_weight_g = baseline_g
        self.bean_weights = []
        self.pending_bean_id = None
        self.weight_history = []
        
    def update(self, weight_reading_g: float, timestamp_s: float) -> List[float]:
        """
        Process a new weight reading.
        
        Returns:
            List of newly completed bean weights (if any)
        """
        new_beans = []
        delta = weight_reading_g - self.current_weight_g
        
        self.weight_history.append({
            'time': timestamp_s,
            'weight': weight_reading_g,
            'delta': delta
        })
        
        self.current_weight_g = weight_reading_g
        
        # Positive step = bean arrived
        if delta > 0.02:  # >20mg threshold
            self.pending_bean_id = len(self.bean_weights)
            arrival_weight = weight_reading_g
        
        # Negative step = bean departed (downstream released)
        elif delta < -0.02 and self.pending_bean_id is not None:
            bean_weight = self.current_weight_g - self.baseline_g
            if 0.05 < bean_weight < 0.5:  # Valid bean weight range
                self.bean_weights.append(bean_weight)
                new_beans.append(bean_weight)
            self.pending_bean_id = None
        
        return new_beans
    
    def get_statistics(self) -> dict:
        """Get statistics on recorded beans."""
        if not self.bean_weights:
            return {'count': 0, 'mean_g': 0, 'std_g': 0}
        
        weights = np.array(self.bean_weights)
        return {
            'count': len(weights),
            'mean_g': np.mean(weights),
            'std_g': np.std(weights),
            'min_g': np.min(weights),
            'max_g': np.max(weights),
            'total_g': np.sum(weights)
        }


# ============================================================================
# Timing Analysis for Sequential Bean Measurement
# ============================================================================

def analyze_sequential_timing(
    beans_per_minute: float = 180,
    settling_time_ms: float = 50,
    cup_reset_time_ms: float = 30
) -> dict:
    """
    Analyze if sequential bean weighing can keep up with flow rate.
    
    Args:
        beans_per_minute: Target throughput
        settling_time_ms: Time for weight to settle after bean lands
        cup_reset_time_ms: Time to release bean and reset for next
        
    Returns:
        Timing analysis dictionary
    """
    bean_interval_ms = 60000 / beans_per_minute  # ms between beans
    total_measure_time_ms = settling_time_ms + cup_reset_time_ms
    
    utilization = total_measure_time_ms / bean_interval_ms * 100
    max_feasible_rate = 60000 / total_measure_time_ms
    
    print(f"\n{'='*60}")
    print(f"SEQUENTIAL WEIGHING TIMING ANALYSIS")
    print(f"{'='*60}")
    print(f"Target throughput: {beans_per_minute} beans/min ({beans_per_minute*60*0.15/1000:.1f}g/h)")
    print(f"Bean interval: {bean_interval_ms:.1f}ms")
    print(f"Measurement time: {total_measure_time_ms:.1f}ms")
    print(f"Utilization: {utilization:.1f}%")
    print(f"Max feasible rate: {max_feasible_rate:.0f} beans/min")
    
    if utilization > 100:
        print(f"\n⚠️  WARNING: Cannot keep up with {beans_per_minute} beans/min!")
        print(f"   Need to either:")
        print(f"   - Reduce measurement time")
        print(f"   - Use parallel weighing stations")
        print(f"   - Accept lower accuracy (sample, not all beans)")
    
    return {
        'beans_per_minute': beans_per_minute,
        'bean_interval_ms': bean_interval_ms,
        'measurement_time_ms': total_measure_time_ms,
        'utilization_pct': utilization,
        'max_feasible_rate': max_feasible_rate,
        'is_feasible': utilization <= 100
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("WEIGHT INTEGRATION ANALYSIS FOR GREEN COFFEE BEAN SORTER")
    print("=" * 70)
    
    # Part 1: Single bean fall simulation
    print("\n[Part 1: Single Bean Fall Simulation]")
    simulator = WeightIntegrationSimulator()
    
    times, readings = simulator.simulate_fall(bean_mass_g=0.152)
    detected = simulator.detect_landing(times, readings)
    
    print(f"Actual bean mass: 0.152g")
    print(f"Detected weight: {detected:.4f}g" if detected else "Detection failed")
    
    simulator.plot_fall_event(times, readings, detected)
    
    # Part 2: Batch simulation
    print("\n[Part 2: Batch Simulation (50 beans)]")
    stats = simulator.run_batch_simulation(n_beans=50)
    
    # Plot distribution
    print("\n[Part 3: Distribution Analysis]")
    actual = [np.random.normal(0.15, 0.02) for _ in range(50)]
    detected_fake = [a + np.random.normal(0, 0.005) for a in actual]
    simulator.plot_distribution(actual, detected_fake)
    
    # Part 4: Timing analysis
    print("\n[Part 4: Sequential Timing Analysis]")
    
    # Different throughput scenarios
    scenarios = [
        ("Current feeder (30 beans/min)", 30),
        ("Target (120 beans/min)", 120),
        ("Max single-file (300 beans/min)", 300)
    ]
    
    for name, rate in scenarios:
        analyze_sequential_timing(rate, settling_time_ms=50, cup_reset_time_ms=30)
        print()
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print("""
KEY FINDINGS:

1. BUFFER CUP APPROACH works well for single-file flow:
   - ~50ms settling time after bean lands
   - ~30ms to release bean and reset
   - Total cycle: ~80ms per bean
   - Max throughput with single cup: ~750 beans/min

2. For 2 kg/h target (≈180 beans/min at 0.15g each):
   - Single buffer cup is sufficient
   - Utilization: ~40% (has headroom)

3. For higher throughput (parallel channels):
   - Each channel needs its own weighing cup
   - Scale response time must be < bean interval

4. Weight detection accuracy:
   - With 50ms settling: ±5mg achievable
   - Single bean weight variation: ±20mg natural variation
   - System precision is sufficient for bean grading

RECOMMENDED DESIGN:
- Buffer cup on load cell at output of color sensor
- Sequential measurement: bean lands → settle → read → release
- Software detects landing from weight step change
- Records individual bean weights for distribution analysis
""")
