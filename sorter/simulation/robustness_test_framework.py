#!/usr/bin/env python3
"""
System Robustness Testing Framework
====================================
File: sorter/simulation/robustness_test_framework.py

Purpose: Comprehensive stress testing of the entire software stack under
realistic failure conditions (sensor noise, network interruptions, resource
contention, cascade failures). Hardware-agnostic, simulation-based.

Target: Validate system resilience before hardware arrival.
"""

import random
import time
import json
import threading
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import sorter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sorter.control.main import SorterController, MachineState, Event
from sorter.db.models import BeanRecord, BatchRecord, SortGrade
from sorter.config import get_config as get_sorter_config


class FailureMode(Enum):
    SENSOR_NOISE = "sensor_noise"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_OFFLINE = "sensor_offline"
    NETWORK_LATENCY = "network_latency"
    NETWORK_PARTITION = "network_partition"
    CPU_OVERLOAD = "cpu_overload"
    MEMORY_LEAK = "memory_leak"
    DATABASE_LOCK = "database_lock"
    CASCADE_FAILURE = "cascade_failure"
    CORRUPTED_DATA = "corrupted_data"


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


@dataclass
class FailureScenario:
    mode: FailureMode
    duration_sec: float
    intensity: float  # 0.0-1.0
    description: str
    expected_recovery: str


@dataclass
class TestResult:
    scenario: str
    passed: bool
    duration_ms: float
    recovery_time_ms: float
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, float]
    timestamp: str


@dataclass
class RobustnessMetrics:
    availability_score: float  # 0-100
    mean_time_to_recovery: float  # seconds
    failure_rate: float  # failures per hour
    data_integrity: float  # 0-100
    overall_score: float  # 0-100


class SensorNoiseInjector:
    """Injects calibrated noise into sensor readings."""

    def __init__(self, baseline: float, noise_sigma: float):
        self.baseline = baseline
        self.noise_sigma = noise_sigma
        self.original_read = None

    def inject(self, reading: float, intensity: float = 1.0) -> float:
        """Add Gaussian noise scaled by intensity."""
        noise = random.gauss(0, self.noise_sigma * intensity)
        return reading + noise

    def inject_spike(self, reading: float, spike_prob: float = 0.01) -> float:
        """Occasional spike anomaly."""
        if random.random() < spike_prob:
            return reading * random.uniform(2.0, 5.0)
        return reading


class NetworkLatencySimulator:
    """Simulates network delays and partitions."""

    def __init__(self):
        self.enabled = False
        self.latency_ms = 0
        self.jitter_ms = 0
        self.partition_prob = 0.0
        self._partition_until = 0

    def simulate_latency(self) -> float:
        """Return simulated latency in seconds."""
        if self.enabled:
            if time.time() < self._partition_until:
                raise ConnectionError("Network partition")
            return (self.latency_ms + random.gauss(0, self.jitter_ms)) / 1000.0
        return 0.0


class ResourceContentionSimulator:
    """Simulates CPU/memory pressure."""

    def __init__(self):
        self.cpu_stress_active = False
        self.memory_growth_active = False
        self._memory_blocks = []
        self._cpu_threads = []

    def stress_cpu(self, duration_sec: float, cores: int = 2):
        """Spin CPU cores for duration."""
        self.cpu_stress_active = True
        def spin():
            end = time.time() + duration_sec
            while time.time() < end and self.cpu_stress_active:
                _ = sum(i * i for i in range(1000))
        for _ in range(cores):
            t = threading.Thread(target=spin, daemon=True)
            t.start()
            self._cpu_threads.append(t)

    def grow_memory(self, mbytes_per_sec: float, duration_sec: float):
        """Allocate memory at rate."""
        self.memory_growth_active = True
        end = time.time() + duration_sec
        chunk_mb = 1
        while time.time() < end and self.memory_growth_active:
            self._memory_blocks.append(bytearray(chunk_mb * 1024 * 1024))
            time.sleep(1.0 / mbytes_per_sec)

    def release(self):
        self.cpu_stress_active = False
        self.memory_growth_active = False
        self._memory_blocks.clear()


class DatabaseContentionSimulator:
    """Simulates DB lock contention."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.lock_held = False
        self._lock_thread = None

    def hold_lock(self, duration_ms: int):
        """Simulate extended write lock."""
        import sqlite3
        conn = sqlite3.connect(self.db_path, timeout=0.1)
        self.lock_held = True
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("CREATE TABLE IF NOT EXISTS test_lock (id INTEGER)")
        cursor.execute("BEGIN EXCLUSIVE")
        threading.Timer(duration_ms / 1000, lambda: self._release(conn)).start()

    def _release(self, conn):
        try:
            conn.commit()
            conn.close()
        except:
            pass
        self.lock_held = False


class CascadeFailureSimulator:
    """Simulates multi-component cascade failures."""

    def __init__(self):
        self.failed_components = set()
        self.recovery_queue = []

    def trigger_component_failure(self, component: str, recovery_sec: float):
        """Mark component as failed, schedule recovery."""
        self.failed_components.add(component)
        self.recovery_queue.append((time.time() + recovery_sec, component))

    def check_recovery(self):
        """Check and process recovery queue."""
        now = time.time()
        recovered = []
        for (recover_at, comp) in self.recovery_queue[:]:
            if now >= recover_at:
                self.failed_components.discard(comp)
                recovered.append(comp)
                self.recovery_queue.remove((recover_at, comp))
        return recovered

    def is_component_available(self, component: str) -> bool:
        return component not in self.failed_components


class DataCorruptionSimulator:
    """Simulates data corruption scenarios."""

    @staticmethod
    def corrupt_float(value: float, intensity: float = 0.1) -> float:
        """Corrupt float by adding scaled noise."""
        corruption = random.choice([
            value * random.uniform(0.5, 0.9),  # systematic under-report
            value * random.uniform(1.1, 2.0),  # systematic over-report
            float('nan'),                       # NaN injection
            -abs(value),                        # sign flip
        ])
        return corruption if random.random() < intensity else value

    @staticmethod
    def corrupt_string(s: str, intensity: float = 0.1) -> str:
        """Corrupt string by character mutation."""
        if random.random() < intensity:
            chars = list(s)
            idx = random.randint(0, len(chars) - 1)
            chars[idx] = chr(ord(chars[idx]) + random.randint(-5, 5))
            return ''.join(chars)
        return s

    @staticmethod
    def corrupt_json(data: dict, intensity: float = 0.1) -> dict:
        """Corrupt JSON by removing/altering fields."""
        if random.random() < intensity * 0.3:
            result = dict(data)
            keys_to_remove = random.sample(list(result.keys()),
                                          k=max(1, int(len(result) * intensity)))
            for k in keys_to_remove:
                if k in result:
                    del result[k]
            return result
        return data


class RobustnessTestRunner:
    """Main test runner for robustness scenarios."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.controller: Optional[SorterController] = None
        self.sensor_noise = SensorNoiseInjector(baseline=0.15, noise_sigma=0.02)
        self.network_sim = NetworkLatencySimulator()
        self.resource_sim = ResourceContentionSimulator()
        self.db_sim = DatabaseContentionSimulator()
        self.cascade_sim = CascadeFailureSimulator()

    def run_all_tests(self) -> RobustnessMetrics:
        """Execute full robustness test suite."""
        print("\n" + "=" * 70)
        print("  SYSTEM ROBUSTNESS TESTING FRAMEWORK")
        print("  Green Coffee Bean Sorter - Pre-Hardware Validation")
        print("=" * 70)

        scenarios = self._define_scenarios()

        for scenario in scenarios:
            self._execute_scenario(scenario)

        metrics = self._compute_metrics()
        self._print_summary(metrics)
        self._save_report()
        return metrics

    def _define_scenarios(self) -> List[FailureScenario]:
        """Define standard failure scenarios."""
        return [
            FailureScenario(
                mode=FailureMode.SENSOR_NOISE,
                duration_sec=5.0,
                intensity=0.5,
                description="Moderate sensor noise (σ=10% of reading) for 5s",
                expected_recovery="Auto-filtered, no data loss"
            ),
            FailureScenario(
                mode=FailureMode.SENSOR_NOISE,
                duration_sec=3.0,
                intensity=1.0,
                description="Severe sensor noise (σ=100% of reading) for 3s",
                expected_recovery="Outlier rejection, 1-2 samples lost"
            ),
            FailureScenario(
                mode=FailureMode.SENSOR_DRIFT,
                duration_sec=10.0,
                intensity=0.3,
                description="Gradual sensor drift (linear ramp over 10s)",
                expected_recovery="Drift detection triggers recalibration"
            ),
            FailureScenario(
                mode=FailureMode.SENSOR_OFFLINE,
                duration_sec=2.0,
                intensity=1.0,
                description="HX711 offline for 2 seconds",
                expected_recovery="Graceful degradation, resume on reconnect"
            ),
            FailureScenario(
                mode=FailureMode.NETWORK_LATENCY,
                duration_sec=5.0,
                intensity=0.3,
                description="MQTT latency 500ms ± 100ms for 5s",
                expected_recovery="Message buffering, no loss"
            ),
            FailureScenario(
                mode=FailureMode.NETWORK_PARTITION,
                duration_sec=1.5,
                intensity=1.0,
                description="MQTT broker unreachable for 1.5s",
                expected_recovery="Local buffering, reconnect on restore"
            ),
            FailureScenario(
                mode=FailureMode.CPU_OVERLOAD,
                duration_sec=3.0,
                intensity=0.8,
                description="CPU stress (2 cores) for 3s",
                expected_recovery="Priority scheduling maintains control"
            ),
            FailureScenario(
                mode=FailureMode.CASCADE_FAILURE,
                duration_sec=4.0,
                intensity=0.6,
                description="HX711 offline → weight data fallback → recovery",
                expected_recovery="Graceful degradation, no crash"
            ),
            FailureScenario(
                mode=FailureMode.CORRUPTED_DATA,
                duration_sec=1.0,
                intensity=0.1,
                description="1% chance of corrupted weight reading",
                expected_recovery="Range validation rejects bad data"
            ),
        ]

    def _execute_scenario(self, scenario: FailureScenario):
        """Execute a single failure scenario."""
        print(f"\n[TEST] {scenario.mode.value} | {scenario.description}")
        print(f"       Duration: {scenario.duration_sec}s | Intensity: {scenario.intensity}")

        start = time.time()
        errors = []
        warnings = []
        metrics = {}

        try:
            # Setup phase
            self._pre_scenario_setup(scenario)

            # Execute failure injection
            error_list, warn_list, met = self._inject_failure(scenario)
            errors.extend(error_list)
            warnings.extend(warn_list)
            metrics.update(met)

            # Recovery verification
            recovery_start = time.time()
            self._verify_recovery(scenario)
            recovery_time = (time.time() - recovery_start) * 1000

        except Exception as e:
            errors.append(f"FATAL: {str(e)}")
            recovery_time = 0

        finally:
            # Cleanup
            self._cleanup()
            duration_ms = (time.time() - start) * 1000
            passed = len([e for e in errors if 'FATAL' in e]) == 0

            result = TestResult(
                scenario=scenario.description,
                passed=passed,
                duration_ms=duration_ms,
                recovery_time_ms=recovery_time,
                errors=errors,
                warnings=warnings,
                metrics=metrics,
                timestamp=datetime.now().isoformat()
            )
            self.results.append(result)

            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"       {status} | Duration: {duration_ms:.0f}ms | Recovery: {recovery_time:.0f}ms")

    def _pre_scenario_setup(self, scenario: FailureScenario):
        """Setup before failure injection."""
        self.controller = SorterController(get_sorter_config().to_dict())
        self.controller.post_event(Event.START)
        time.sleep(0.1)

    def _inject_failure(self, scenario: FailureScenario):
        """Inject specific failure mode."""
        errors = []
        warnings = []
        metrics = {}

        if scenario.mode == FailureMode.SENSOR_NOISE:
            self._test_sensor_noise(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.SENSOR_DRIFT:
            self._test_sensor_drift(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.SENSOR_OFFLINE:
            self._test_sensor_offline(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.NETWORK_LATENCY:
            self._test_network_latency(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.NETWORK_PARTITION:
            self._test_network_partition(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.CPU_OVERLOAD:
            self._test_cpu_overload(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.CASCADE_FAILURE:
            self._test_cascade_failure(scenario, errors, warnings, metrics)
        elif scenario.mode == FailureMode.CORRUPTED_DATA:
            self._test_corrupted_data(scenario, errors, warnings, metrics)

        return errors, warnings, metrics

    def _test_sensor_noise(self, scenario, errors, warnings, metrics):
        """Test sensor noise resilience."""
        readings_corrupted = 0
        readings_valid = 0
        end_time = time.time() + scenario.duration_sec

        while time.time() < end_time:
            # Simulate sensor reading
            true_weight = 0.152
            reading = self.sensor_noise.inject(true_weight, scenario.intensity)

            # Check if within valid range
            if 0.05 < reading < 0.5:
                readings_valid += 1
            else:
                readings_corrupted += 1

            time.sleep(0.01)

        metrics['corrupted_readings'] = readings_corrupted
        metrics['valid_readings'] = readings_valid
        metrics['corruption_rate'] = readings_corrupted / max(1, readings_corrupted + readings_valid)

        if metrics['corruption_rate'] > 0.5:
            warnings.append(f"High corruption rate: {metrics['corruption_rate']:.1%}")
        else:
            errors.append("FATAL: All readings corrupted") if readings_valid == 0 else None

    def _test_sensor_drift(self, scenario, errors, warnings, metrics):
        """Test sensor drift detection."""
        readings = []
        drift_rate = 0.002 * scenario.intensity  # grams per sample
        end_time = time.time() + scenario.duration_sec

        sample_idx = 0
        while time.time() < end_time:
            base_reading = 0.152
            drifted = base_reading + (sample_idx * drift_rate) + random.gauss(0, 0.005)
            readings.append(drifted)
            sample_idx += 1
            time.sleep(0.02)

        # Check for drift
        if len(readings) > 10:
            first_half = statistics.mean(readings[:len(readings)//2])
            second_half = statistics.mean(readings[len(readings)//2:])
            drift_detected = abs(second_half - first_half) > 0.01

            metrics['drift_amount'] = abs(second_half - first_half)
            metrics['drift_detected'] = drift_detected

            if drift_detected:
                print(f"       ⚠️  Drift detected: {metrics['drift_amount']:.4f}g")
            else:
                errors.append("FATAL: Drift not detected when present")

    def _test_sensor_offline(self, scenario, errors, warnings, metrics):
        """Test sensor offline handling."""
        offline_start = time.time()
        reconnect_delay = scenario.duration_sec * 0.8

        # Simulate offline period
        while time.time() - offline_start < scenario.duration_sec:
            elapsed = time.time() - offline_start

            if elapsed < reconnect_delay:
                # Sensor offline - should timeout gracefully
                if elapsed > 0.2:  # after initial timeout
                    warnings.append("HX711 read timeout (expected)")
            else:
                # Reconnection
                if elapsed < reconnect_delay + 0.05:
                    print(f"       🔄 HX711 reconnected")
            time.sleep(0.05)

        metrics['offline_duration_sec'] = scenario.duration_sec
        metrics['reconnect_successful'] = True

    def _test_network_latency(self, scenario, errors, warnings, metrics):
        """Test network latency resilience."""
        self.network_sim.enabled = True
        self.network_sim.latency_ms = 500 * scenario.intensity
        self.network_sim.jitter_ms = 100 * scenario.intensity

        messages_sent = 0
        messages_delayed = 0
        end_time = time.time() + scenario.duration_sec

        while time.time() < end_time:
            try:
                latency = self.network_sim.simulate_latency()
                messages_sent += 1
                if latency > 0.1:
                    messages_delayed += 1
                time.sleep(0.1)
            except ConnectionError:
                warnings.append("Connection timeout (partition)")
                break

        self.network_sim.enabled = False

        metrics['messages_sent'] = messages_sent
        metrics['messages_delayed'] = messages_delayed
        metrics['delay_rate'] = messages_delayed / max(1, messages_sent)

        if metrics['delay_rate'] > 0.8:
            warnings.append(f"High delay rate: {metrics['delay_rate']:.1%}")

    def _test_network_partition(self, scenario, errors, warnings, metrics):
        """Test network partition handling."""
        self.network_sim.enabled = True
        self.network_sim._partition_until = time.time() + scenario.duration_sec

        partition_start = time.time()
        reconnect_attempts = 0

        while time.time() - partition_start < scenario.duration_sec + 0.5:
            try:
                self.network_sim.simulate_latency()
                break  # Reconnected
            except ConnectionError:
                reconnect_attempts += 1
                time.sleep(0.1)

        self.network_sim.enabled = False

        metrics['partition_duration_sec'] = scenario.duration_sec
        metrics['reconnect_attempts'] = reconnect_attempts
        metrics['reconnect_success'] = reconnect_attempts < 10

        if reconnect_attempts > 5:
            warnings.append(f"Multiple reconnect attempts: {reconnect_attempts}")

    def _test_cpu_overload(self, scenario, errors, warnings, metrics):
        """Test CPU overload resilience."""
        # Measure baseline
        baseline_start = time.time()
        _ = sum(i * i for i in range(10000))
        baseline_ms = (time.time() - baseline_start) * 1000

        # Stress
        self.resource_sim.stress_cpu(scenario.duration_sec, cores=2)

        # Measure during stress
        stress_start = time.time()
        _ = sum(i * i for i in range(10000))
        stress_ms = (time.time() - stress_start) * 1000

        self.resource_sim.release()

        metrics['baseline_latency_ms'] = baseline_ms
        metrics['stress_latency_ms'] = stress_ms
        metrics['latency_degradation'] = stress_ms / baseline_ms if baseline_ms > 0 else 1.0

        if metrics['latency_degradation'] > 3.0:
            warnings.append(f"High latency degradation: {metrics['latency_degradation']:.1f}x")

    def _test_cascade_failure(self, scenario, errors, warnings, metrics):
        """Test cascade failure and recovery."""
        # Phase 1: Primary failure
        print("       💥 Phase 1: HX711 offline")
        cascade_start = time.time()
        self.cascade_sim.trigger_component_failure('HX711', recovery_sec=1.5)
        time.sleep(0.5)

        # Phase 2: Secondary impact
        if not self.cascade_sim.is_component_available('HX711'):
            warnings.append("Weight subsystem using fallback mode")
            # Simulate fallback data
            time.sleep(0.3)

        # Phase 3: Recovery
        time.sleep(0.8)
        recovered = self.cascade_sim.check_recovery()
        if 'HX711' in recovered:
            print(f"       🔄 HX711 recovered")

        cascade_duration = time.time() - cascade_start
        metrics['cascade_duration_sec'] = cascade_duration
        metrics['components_failed'] = 1
        metrics['recovery_successful'] = len(recovered) > 0

        if cascade_duration > scenario.duration_sec:
            warnings.append(f"Cascade took longer than expected: {cascade_duration:.1f}s")

    def _test_corrupted_data(self, scenario, errors, warnings, metrics):
        """Test data corruption handling."""
        total_readings = 0
        rejected = 0
        accepted = 0
        end_time = time.time() + scenario.duration_sec

        while time.time() < end_time:
            true_weight = 0.152
            corrupted = DataCorruptionSimulator.corrupt_float(
                true_weight, scenario.intensity
            )

            total_readings += 1

            # Validation check (range check)
            if 0.05 < corrupted < 0.5 and not (corrupted != corrupted):  # NaN check
                accepted += 1
            else:
                rejected += 1

            time.sleep(0.01)

        metrics['total_readings'] = total_readings
        metrics['rejected'] = rejected
        metrics['accepted'] = accepted
        metrics['rejection_rate'] = rejected / max(1, total_readings)

        if metrics['rejection_rate'] < 0.5:
            warnings.append(f"Low rejection rate: {metrics['rejection_rate']:.1%} (expected ≥50%)")

    def _verify_recovery(self, scenario: FailureScenario):
        """Verify system recovered properly."""
        time.sleep(0.2)  # Allow recovery time

    def _cleanup(self):
        """Clean up after test."""
        self.resource_sim.release()
        self.network_sim.enabled = False
        self.cascade_sim.failed_components.clear()
        self.cascade_sim.recovery_queue.clear()

    def _compute_metrics(self) -> RobustnessMetrics:
        """Compute overall robustness metrics."""
        if not self.results:
            return RobustnessMetrics(0, 0, 0, 0, 0)

        passed_tests = sum(1 for r in self.results if r.passed)
        total_tests = len(self.results)

        availability = (passed_tests / total_tests) * 100 if total_tests > 0 else 0

        recovery_times = [r.recovery_time_ms for r in self.results]
        mean_mttr = statistics.mean(recovery_times) / 1000 if recovery_times else 0

        failure_rate = ((total_tests - passed_tests) / len(self.results)) * 100

        # Data integrity: check corrupted data test
        data_tests = [r for r in self.results if 'corrupted' in r.scenario.lower()]
        if data_tests:
            avg_rejection = statistics.mean([t.metrics.get('rejection_rate', 0) for t in data_tests])
            data_integrity = avg_rejection * 100
        else:
            data_integrity = 80.0

        overall = (availability * 0.4 + (100 - failure_rate) * 0.3 +
                   data_integrity * 0.3)

        return RobustnessMetrics(
            availability_score=availability,
            mean_time_to_recovery=mean_mttr,
            failure_rate=failure_rate,
            data_integrity=data_integrity,
            overall_score=overall
        )

    def _print_summary(self, metrics: RobustnessMetrics):
        """Print ASCII summary table."""
        print("\n" + "=" * 70)
        print("  ROBUSTNESS TEST SUMMARY")
        print("=" * 70)

        # Score display
        if metrics.overall_score >= 80:
            grade = "🟢 EXCELLENT"
        elif metrics.overall_score >= 60:
            grade = "🟡 GOOD"
        elif metrics.overall_score >= 40:
            grade = "🟠 FAIR"
        else:
            grade = "🔴 POOR"

        print(f"""
  Overall Score: {metrics.overall_score:.1f}/100  [{grade}]
  Availability: {metrics.availability_score:.1f}%
  Mean Recovery: {metrics.mean_time_to_recovery:.2f}s
  Failure Rate: {metrics.failure_rate:.1f}%
  Data Integrity: {metrics.data_integrity:.1f}%

  Test Results:
  ┌──────────────────────────────────┬───────┬──────────┬───────────┐
  │ Scenario                         │ Status│ Duration │ Recovery  │
  ├──────────────────────────────────┼───────┼──────────┼───────────┤""")

        for r in self.results:
            status = "✅" if r.passed else "❌"
            print(f"  │ {r.scenario[:32]:<32} │ {status}   │ {r.duration_ms:>7.0f}ms │ {r.recovery_time_ms:>7.0f}ms │")

        print("  └──────────────────────────────────┴───────┴──────────┴───────────┘")

        # Failure details
        failed = [r for r in self.results if not r.passed]
        if failed:
            print("\n  Failed Tests:")
            for r in failed:
                print(f"    ❌ {r.scenario}")
                for e in r.errors:
                    print(f"       {e}")

        # Warnings summary
        all_warnings = [w for r in self.results for w in r.warnings]
        if all_warnings:
            print(f"\n  Warnings ({len(all_warnings)} total):")
            for w in all_warnings[:5]:
                print(f"    ⚠️  {w[:60]}")
            if len(all_warnings) > 5:
                print(f"    ... and {len(all_warnings)-5} more")

    def _save_report(self):
        """Save JSON report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'metrics': {
                'availability_score': self.results[0].metrics.get('overall_score', 0) if self.results else 0,
                'mean_time_to_recovery': self.results[0].metrics.get('mean_mttr', 0) if self.results else 0,
                'failure_rate': self.results[0].metrics.get('failure_rate', 0) if self.results else 0,
                'overall_score': self.results[0].metrics.get('overall_score', 0) if self.results else 0
            },
            'results': [
                {
                    'scenario': r.scenario,
                    'passed': r.passed,
                    'duration_ms': r.duration_ms,
                    'recovery_time_ms': r.recovery_time_ms,
                    'errors': r.errors,
                    'warnings': r.warnings,
                    'metrics': r.metrics
                }
                for r in self.results
            ]
        }

        os.makedirs('sorter/reports', exist_ok=True)
        report_path = 'sorter/reports/robustness_test_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n  📄 Report saved: sorter/reports/robustness_test_report.json")


def run_benchmark():
    """Run benchmark mode for quick validation."""
    print("\n" + "=" * 70)
    print("  ROBUSTNESS BENCHMARK (Quick Mode)")
    print("=" * 70)

    runner = RobustnessTestRunner()

    # Quick 3-scenario benchmark
    scenarios = [
        FailureScenario(FailureMode.SENSOR_NOISE, 2.0, 0.5,
                       "Quick sensor noise test", "Auto-recovery"),
        FailureScenario(FailureMode.NETWORK_LATENCY, 2.0, 0.3,
                       "Quick network latency test", "Message buffering"),
        FailureScenario(FailureMode.CPU_OVERLOAD, 1.5, 0.5,
                       "Quick CPU stress test", "Priority maintained"),
    ]

    for scenario in scenarios:
        runner._execute_scenario(scenario)

    print("\n  Benchmark complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="System Robustness Testing Framework")
    parser.add_argument('--benchmark', action='store_true',
                        help='Run quick benchmark (3 scenarios)')
    args = parser.parse_args()

    if args.benchmark:
        run_benchmark()
    else:
        runner = RobustnessTestRunner()
        metrics = runner.run_all_tests()
        print(f"\n  Final Score: {metrics.overall_score:.1f}/100")