"""
Load Cell Calibration Tools
============================

Calibration procedures for weight measurement system.

Two calibration methods:
1. Single-point calibration: Use one known weight (e.g., 100g)
2. Two-point calibration: Use zero (tare) + known weight for better linearity

Typical Coffee Bean Weights:
- Arabica green beans: 0.10 - 0.18g average
- Robusta green beans: 0.20 - 0.30g average
- Peaberry: 0.08 - 0.12g (single oval bean)

Author: Little Husky (HUSKY-SORTER-001)
Date: 2026-04-13
"""

import json
import time
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass, asdict


@dataclass
class CalibrationResult:
    """Result of a calibration session."""
    timestamp: str
    reference_weight_g: float
    raw_at_zero: float
    raw_at_reference: float
    calculated_reference_unit: float
    samples_used: int
    std_deviation: float
    notes: str = ""


class LoadCellCalibrator:
    """
    Calibration manager for load cell + HX711.
    
    Usage:
        calibrator = LoadCellCalibrator("/path/to/calibration.json")
        calibrator.tare()
        calibrator.calibrate_with_weight(known_weight_g=100.0)
        calibrator.save()
    """
    
    CALIBRATION_FILE = "load_cell_calibration.json"
    
    def __init__(self, calibration_path: Optional[str] = None):
        self.calibration_path = Path(calibration_path or self.CALIBRATION_FILE)
        self.calibration_data: Optional[CalibrationResult] = None
        self._load_existing()
    
    def _load_existing(self) -> bool:
        """Load existing calibration from file."""
        if self.calibration_path.exists():
            try:
                with open(self.calibration_path, 'r') as f:
                    data = json.load(f)
                    self.calibration_data = CalibrationResult(**data)
                return True
            except (json.JSONDecodeError, TypeError):
                return False
        return False
    
    def save(self) -> bool:
        """Save calibration data to file."""
        if self.calibration_data is None:
            return False
        try:
            with open(self.calibration_path, 'w') as f:
                json.dump(asdict(self.calibration_data), f, indent=2)
            return True
        except IOError:
            return False
    
    def load(self) -> Optional[CalibrationResult]:
        """Load and return calibration data."""
        return self.calibration_data
    
    def get_calibration_params(self) -> Tuple[float, float]:
        """
        Get calibration parameters for HX711.
        
        Returns:
            (reference_unit, offset) tuple
        """
        if self.calibration_data is None:
            return (1.0, 0.0)
        return (
            self.calibration_data.calculated_reference_unit,
            self.calibration_data.raw_at_zero / self.calibration_data.calculated_reference_unit
        )
    
    def run_tare(self, load_cell, samples: int = 20) -> bool:
        """
        Perform tare (zero point) calibration.
        
        Args:
            load_cell: LoadCell or HX711 instance
            samples: Number of samples to average
            
        Returns:
            True if successful
        """
        readings = []
        for i in range(samples):
            reading = load_cell.measure_single(samples=1) if hasattr(load_cell, 'measure_single') else load_cell.read(samples=1)
            if reading is not None:
                readings.append(reading)
            time.sleep(0.05)
        
        if len(readings) < samples // 2:
            print(f"[ERROR] Too few valid readings: {len(readings)}/{samples}")
            return False
        
        avg = sum(readings) / len(readings)
        std = (sum((r - avg) ** 2 for r in readings) / len(readings)) ** 0.5
        
        print(f"[TARE] Average: {avg:.4f}g, StdDev: {std:.4f}g, Samples: {len(readings)}")
        return load_cell.tare(samples=samples)
    
    def run_calibration(
        self,
        load_cell,
        reference_weight_g: float,
        samples: int = 30,
        notes: str = ""
    ) -> Optional[CalibrationResult]:
        """
        Run full two-point calibration (zero + reference).
        
        Args:
            load_cell: LoadCell or HX711 instance
            reference_weight_g: Known reference weight in grams
            samples: Number of samples at each point
            notes: Optional notes about calibration environment
            
        Returns:
            CalibrationResult if successful, None otherwise
        """
        print("=" * 60)
        print("LOAD CELL CALIBRATION")
        print("=" * 60)
        print(f"\nStep 1: Tare (empty scale)")
        print("-" * 40)
        
        # Tare first
        if not self.run_tare(load_cell, samples=samples):
            print("[ERROR] Tare failed")
            return None
        
        # Record raw value at zero (after tare)
        readings_zero = []
        for _ in range(samples):
            r = load_cell.measure_single(samples=1) if hasattr(load_cell, 'measure_single') else load_cell.read(samples=1)
            if r is not None:
                readings_zero.append(r)
            time.sleep(0.05)
        
        if len(readings_zero) < samples // 2:
            print("[ERROR] Could not get stable zero reading")
            return None
        
        raw_at_zero = sum(readings_zero) / len(readings_zero)
        std_zero = (sum((r - raw_at_zero) ** 2 for r in readings_zero) / len(readings_zero)) ** 0.5
        
        print(f"\nStep 2: Place reference weight ({reference_weight_g}g)")
        input("  Press ENTER when ready...")
        print("-" * 40)
        
        # Measure with reference weight
        time.sleep(0.5)  # Let weight settle
        readings_cal = []
        for _ in range(samples):
            r = load_cell.measure_single(samples=1) if hasattr(load_cell, 'measure_single') else load_cell.read(samples=1)
            if r is not None:
                readings_cal.append(r)
            time.sleep(0.05)
        
        if len(readings_cal) < samples // 2:
            print("[ERROR] Could not get stable calibration reading")
            return None
        
        raw_at_reference = sum(readings_cal) / len(readings_cal)
        std_cal = (sum((r - raw_at_reference) ** 2 for r in readings_cal) / len(readings_cal)) ** 0.5
        
        print(f"\n[READINGS]")
        print(f"  Zero:     {raw_at_zero:.4f}g (std: {std_zero:.4f})")
        print(f"  Reference: {raw_at_reference:.4f}g (std: {std_cal:.4f})")
        print(f"  Difference: {raw_at_reference - raw_at_zero:.4f}g")
        
        # Calculate reference unit
        # weight = (raw - offset) / reference_unit
        # At zero: 0 = (raw_zero - offset) / ref → offset = raw_zero
        # At ref_weight: ref_weight = (raw_cal - raw_zero) / ref
        # ref = (raw_cal - raw_zero) / ref_weight
        
        if reference_weight_g <= 0:
            print("[ERROR] Invalid reference weight")
            return None
        
        delta_raw = raw_at_reference - raw_at_zero
        if abs(delta_raw) < 0.001:
            print("[ERROR] No change detected - check load cell connection")
            return None
        
        calculated_ref_unit = delta_raw / reference_weight_g
        
        print(f"\n[CALCULATED PARAMETERS]")
        print(f"  Reference Unit: {calculated_ref_unit:.6f}")
        print(f"  Offset: {raw_at_zero:.4f}")
        
        # Store calibration result
        self.calibration_data = CalibrationResult(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            reference_weight_g=reference_weight_g,
            raw_at_zero=raw_at_zero,
            raw_at_reference=raw_at_reference,
            calculated_reference_unit=calculated_ref_unit,
            samples_used=samples,
            std_deviation=max(std_zero, std_cal),
            notes=notes
        )
        
        # Apply to load cell
        load_cell._hx711.config.reference_unit = calculated_ref_unit
        load_cell._hx711.config.offset = raw_at_zero / calculated_ref_unit
        
        print(f"\n[CALIBRATION SAVED]")
        self.save()
        
        print("=" * 60)
        return self.calibration_data
    
    def verify(self, load_cell, test_weights: Optional[List[float]] = None) -> dict:
        """
        Verify calibration accuracy with test weights.
        
        Args:
            load_cell: Calibrated LoadCell instance
            test_weights: List of test weights to check (optional)
            
        Returns:
            Dictionary of verification results
        """
        if test_weights is None:
            # Default test weights spanning expected range
            test_weights = [0.10, 0.15, 0.20, 0.25, 0.50, 1.0, 5.0, 10.0, 50.0, 100.0]
        
        results = []
        print("\n" + "=" * 60)
        print("CALIBRATION VERIFICATION")
        print("=" * 60)
        
        for expected_g in test_weights:
            print(f"\nPlace {expected_g}g weight... ", end="", flush=True)
            input()
            
            readings = []
            for _ in range(5):
                r = load_cell.measure_single(samples=3)
                if r is not None:
                    readings.append(r)
                time.sleep(0.05)
            
            if readings:
                measured = sum(readings) / len(readings)
                error = measured - expected_g
                error_pct = (error / expected_g) * 100 if expected_g > 0 else 0
                results.append({
                    "expected_g": expected_g,
                    "measured_g": measured,
                    "error_g": error,
                    "error_pct": error_pct,
                    "samples": len(readings)
                })
                print(f"{measured:.4f}g (error: {error:+.4f}g, {error_pct:+.2f}%)")
            else:
                print("[no reading]")
        
        # Summary
        if results:
            errors = [r['error_g'] for r in results]
            print("\n[SUMMARY]")
            print(f"  Max error: {max(errors):+.4f}g")
            print(f"  Min error: {min(errors):.4f}g")
            print(f"  Mean error: {sum(errors)/len(errors):+.4f}g")
        
        return {"verification_results": results}
    
    @staticmethod
    def expected_bean_weight(variety: str = "arabica") -> Tuple[float, float]:
        """
        Get expected bean weight range for variety.
        
        Args:
            variety: "arabica", "robusta", or "peaberry"
            
        Returns:
            (min_g, max_g) tuple
        """
        ranges = {
            "arabica": (0.10, 0.18),
            "robusta": (0.20, 0.30),
            "peaberry": (0.08, 0.12),
            "liberia": (0.30, 0.50),
            "excelsa": (0.15, 0.25)
        }
        return ranges.get(variety.lower(), (0.10, 0.25))


# ============================================================================
# Calibration for Different Bean Types
# ============================================================================

BEAN_VARIETY_CALIBRATION = {
    "Ethiopian Heirloom": {
        "typical_weight_g": 0.14,
        "weight_range_g": (0.10, 0.18),
        "density_g/ml": 0.65,
        "notes": "Small to medium, oval shape"
    },
    "Guatemala Bourbon": {
        "typical_weight_g": 0.17,
        "weight_range_g": (0.14, 0.22),
        "density_g/ml": 0.68,
        "notes": "Medium size, full Bourbon character"
    },
    "Colombia Castillo": {
        "typical_weight_g": 0.16,
        "weight_range_g": (0.13, 0.20),
        "density_g/ml": 0.67,
        "notes": "Disease resistant variety"
    },
    "Kenya SL28/SL34": {
        "typical_weight_g": 0.17,
        "weight_range_g": (0.14, 0.22),
        "density_g/ml": 0.70,
        "notes": "Bright acidity, berry notes"
    },
    "Brazil Santos": {
        "typical_weight_g": 0.18,
        "weight_range_g": (0.15, 0.24),
        "density_g/ml": 0.66,
        "notes": "Large bean, low acidity"
    },
    "Yemen Mokha": {
        "typical_weight_g": 0.12,
        "weight_range_g": (0.08, 0.16),
        "density_g/ml": 0.62,
        "notes": "Small irregular beans, complex flavor"
    }
}


def print_calibration_guide():
    """Print quick reference guide for calibration."""
    guide = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║              LOAD CELL CALIBRATION QUICK GUIDE                   ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║                                                                  ║
    ║  WHAT YOU NEED:                                                  ║
    ║    • Calibrated reference weight (100g recommended)              ║
    ║    • Stable flat surface                                         ║
    ║    • No vibration or air movement during calibration             ║
    ║                                                                  ║
    ║  CALIBRATION STEPS:                                              ║
    ║    1. Power on and wait 5 min for warm-up                        ║
    ║    2. Remove all weight from scale                               ║
    ║    3. Run tare (zero)                                            ║
    ║    4. Place reference weight on scale                           ║
    ║    5. Run calibration with known weight value                   ║
    ║    6. Verify with additional test weights                       ║
    ║                                                                  ║
    ║  EXPECTED ACCURACY:                                              ║
    ║    • Resolution: ±0.01g (24-bit ADC)                           ║
    ║    • Accuracy: ±0.05g with proper calibration                   ║
    ║    • Coffee bean: 0.10-0.20g typical                             ║
    ║                                                                  ║
    ║  BEAN VARIETY REFERENCE WEIGHTS:                                 ║
    ║    • Ethiopian Heirloom: 0.14g avg                              ║
    ║    • Guatemala Bourbon: 0.17g avg                               ║
    ║    • Kenya SL28: 0.17g avg                                      ║
    ║    • Brazil Santos: 0.18g avg                                   ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """
    print(guide)


if __name__ == "__main__":
    print_calibration_guide()
    
    # Demo with mock load cell
    print("\n[Running demo calibration sequence...]\n")
    
    from load_cell import LoadCell, HX711, HX711Config
    
    # Create mock load cell
    config = HX711Config(reference_unit=1.0, offset=0.0)
    hx711 = HX711(config)
    load_cell = LoadCell(config)
    
    # Simulate calibration with mock values
    print("Simulating calibration with 100g reference weight...")
    
    # Mock: scale reads 0 at tare, reads ~100 at reference
    # But with our mock, we need to set raw values directly
    hx711.set_mock_value(0.0)
    time.sleep(0.1)
    
    calibrator = LoadCellCalibrator("/tmp/test_calibration.json")
    
    # Simulate what calibration would do
    print("\n[MOCK CALIBRATION RESULT]")
    print(f"  Reference weight: 100.0g")
    print(f"  Raw at zero: 0.0")
    print(f"  Raw at reference: 100000.0")
    print(f"  Calculated reference_unit: 1000.0")
    
    # Save mock calibration
    calibrator.calibration_data = CalibrationResult(
        timestamp="2026-04-13T15:00:00+08:00",
        reference_weight_g=100.0,
        raw_at_zero=0.0,
        raw_at_reference=100000.0,
        calculated_reference_unit=1000.0,
        samples_used=30,
        std_deviation=0.5,
        notes="Mock calibration for testing"
    )
    calibrator.save()
    
    print(f"\nCalibration saved to: {calibrator.calibration_path}")
    
    # Test applying calibration
    hx711.set_mock_value(0.15)  # 0.15g = 150 raw
    hx711.config.reference_unit = 1000.0
    reading = hx711.read(samples=1)
    print(f"\nTest reading (0.15g mock bean): {reading:.4f}g" if reading else "No reading")
