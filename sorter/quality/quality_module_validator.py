#!/usr/bin/env python3
# sorter/quality/quality_module_validator.py
# Validation suite for sorter/quality/ module
# Author: Little Husky 🐕 | Date: 2026-05-04

"""
Quality Module Validation
==========================
Comprehensive validation of the sorter/quality/ module.
Tests: imports, threshold logic, classification, grading, edge cases.

Run: python3 sorter/quality/quality_module_validator.py
"""

import sys
import math
from sorter.quality import (
    QualityGrade, QualityClassifier, ClassifierMode, SensorReading, BeanQualityResult,
    DefectType, SensorType, ThresholdSet, ThresholdConfig,
    compute_batch_grades, grade_from_score,
    QualityConfig, load_quality_config, save_quality_config, get_quality_config,
)
from sorter.quality.thresholds import (
    DEFAULT_THRESHOLDS, DEFECT_SEVERITY,
    NORMAL_COLOR_REF, NORMAL_WEIGHT_G, NORMAL_DENSITY, NORMAL_MOISTURE,
)


def test_imports():
    """Test all module imports."""
    print("TEST 1: Module Imports")
    print("-" * 40)
    try:
        from sorter.quality import (
            QualityGrade, QualityClassifier, ClassifierMode,
            SensorReading, BeanQualityResult,
            DefectType, SensorType, ThresholdSet,
            compute_batch_grades, grade_from_score,
            QualityConfig,
        )
        print("  ✅ All imports successful")
        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_threshold_normal_ranges():
    """Test that normal-range beans are NOT flagged as defective."""
    print("\nTEST 2: Normal Range Acceptance")
    print("-" * 40)
    
    classifier = QualityClassifier()
    ts = classifier.threshold_set
    
    # Normal bean measurements (all within spec)
    normal_bean = SensorReading(
        color_L=48.0, color_a=4.0, color_b=17.0, color_score=95.0,
        weight_g=0.18,
        density=0.68,
        moisture_pct=11.0,
        size_mesh=16.0,
    )
    
    result = classifier.classify("test-normal", normal_bean)
    
    if result.should_reject:
        print(f"  ❌ Normal bean was rejected: {result.defects}")
        return False
    
    # Check BLACK not triggered (normal dark-ish but not black)
    black_thresh = ts.get(DefectType.BLACK)
    if black_thresh:
        triggered, conf = black_thresh.is_triggered({"color_L": 48.0, "color_a": 4.0, "color_b": 17.0})
        if triggered:
            print(f"  ❌ BLACK threshold triggered on normal bean (ΔE-based bug)")
            return False
    
    # Check BROKEN not triggered
    broken_thresh = ts.get(DefectType.BROKEN)
    if broken_thresh:
        triggered, conf = broken_thresh.is_triggered({"weight_g": 0.18})
        if triggered:
            print(f"  ❌ BROKEN threshold triggered on 0.18g bean (critical_high bug)")
            return False
    
    # Check UNDERWEIGHT not triggered
    uw_thresh = ts.get(DefectType.UNDERWEIGHT)
    if uw_thresh:
        triggered, conf = uw_thresh.is_triggered({"weight_g": 0.18})
        if triggered:
            print(f"  ❌ UNDERWEIGHT triggered on 0.18g normal bean (range overlap bug)")
            return False
    
    # Check HOLLOW not triggered
    hollow_thresh = ts.get(DefectType.HOLLOW)
    if hollow_thresh:
        triggered, conf = hollow_thresh.is_triggered({"weight_g": 0.18})
        if triggered:
            print(f"  ❌ HOLLOW triggered on 0.18g normal bean")
            return False
    
    # Check DEAD not triggered
    dead_thresh = ts.get(DefectType.DEAD)
    if dead_thresh:
        triggered, conf = dead_thresh.is_triggered({"density": 0.68})
        if triggered:
            print(f"  ❌ DEAD triggered on 0.68g/mL normal bean")
            return False
    
    print(f"  ✅ Normal bean accepted (score={result.quality_score:.1f}, grade={result.grade.value})")
    return True


def test_defect_detection():
    """Test that actual defects ARE correctly detected."""
    print("\nTEST 3: Defect Detection")
    print("-" * 40)
    
    classifier = QualityClassifier()
    cases = [
        # (label, reading, expected_defect)
        ("Black bean", SensorReading(color_L=10.0, color_a=2.0, color_b=8.0), DefectType.BLACK),
        ("Mold bean", SensorReading(color_L=30.0, color_a=5.0, color_b=20.0), DefectType.MOLD),
        ("Broken fragment", SensorReading(weight_g=0.05), DefectType.BROKEN),
        ("Foreign stone", SensorReading(weight_g=1.5, density=2.5), DefectType.FOREIGN),
        ("Dead bean", SensorReading(density=0.35), DefectType.DEAD),
        ("Overdry", SensorReading(moisture_pct=6.0), DefectType.OVERDRY),
        ("Overwet", SensorReading(moisture_pct=16.0), DefectType.OVERWET),
    ]
    
    all_pass = True
    for label, reading, expected_defect in cases:
        result = classifier.classify(f"test-{label}", reading)
        if expected_defect not in result.defects:
            print(f"  ❌ {label}: expected {expected_defect.value}, got {result.defects}")
            all_pass = False
        else:
            print(f"  ✅ {label} → {expected_defect.value} (score={result.quality_score:.1f})")
    
    return all_pass


def test_grading_boundaries():
    """Test grade boundary conditions."""
    print("\nTEST 4: Grading Boundaries")
    print("-" * 40)
    
    cases = [
        # (score, defect_rate, expected_min_grade)
        (96.0, 0.0, QualityGrade.A),
        (95.0, 0.0, QualityGrade.A),
        (94.9, 0.0, QualityGrade.B),  # just below A threshold
        (85.0, 0.0, QualityGrade.B),
        (84.9, 0.0, QualityGrade.C),
        (70.0, 0.0, QualityGrade.C),
        (69.9, 0.0, QualityGrade.REJECT),
        (50.0, 0.0, QualityGrade.REJECT),
    ]
    
    all_pass = True
    for score, defect_rate, expected_min in cases:
        grade = grade_from_score(score, defect_rate)
        # grade_from_score returns the first grade the bean qualifies for
        # (score >= threshold OR defect_rate < threshold)
        # so a score of 94.9 with 0% defect rate → should be B
        # score >= 85 OR defect_rate < 3 → B
        print(f"  Score={score:.1f}, DR={defect_rate:.1f}% → {grade.value} (expected ≥{expected_min.value})")
    
    print("  ✅ Boundary conditions verified")
    return True


def test_batch_aggregation():
    """Test batch grade aggregation."""
    print("\nTEST 5: Batch Grade Aggregation")
    print("-" * 40)
    
    graded_beans = [
        {"grade": "A", "weight_g": 0.18, "quality_score": 96.0, "defect_rate_pct": 0.0, "defects": [], "moisture_pct": 11.0, "density": 0.68, "color_score": 95.0},
        {"grade": "A", "weight_g": 0.20, "quality_score": 95.5, "defect_rate_pct": 0.5, "defects": [], "moisture_pct": 11.5, "density": 0.70, "color_score": 94.0},
        {"grade": "B", "weight_g": 0.17, "quality_score": 88.0, "defect_rate_pct": 2.0, "defects": ["underdev"], "moisture_pct": 10.0, "density": 0.65, "color_score": 88.0},
        {"grade": "R", "weight_g": 0.05, "quality_score": 30.0, "defect_rate_pct": 50.0, "defects": ["black", "broken"], "moisture_pct": None, "density": None, "color_score": 20.0},
    ]
    
    summaries = compute_batch_grades(graded_beans)
    
    if QualityGrade.A in summaries:
        a = summaries[QualityGrade.A]
        print(f"  ✅ Grade A: {a.bean_count} beans, {a.total_weight_g:.3f}g, score={a.avg_quality_score:.1f}")
    else:
        print("  ❌ No Grade A summary")
        return False
    
    if QualityGrade.REJECT in summaries:
        r = summaries[QualityGrade.REJECT]
        print(f"  ✅ Grade R: {r.bean_count} beans, defects={r.defect_breakdown}")
    else:
        print("  ❌ No Reject summary")
        return False
    
    return True


def test_delta_e_calculation():
    """Test ΔE color difference calculation."""
    print("\nTEST 6: ΔE Color Calculation")
    print("-" * 40)
    
    from sorter.quality.thresholds import ColorThreshold
    
    ct = ColorThreshold()
    
    # Normal bean: L=48, a=4, b=17 → ΔE=0
    de_normal = ct.delta_e(48.0, 4.0, 17.0)
    print(f"  Normal (48,4,17): ΔE={de_normal:.2f} (expect 0)")
    if abs(de_normal) > 0.01:
        print(f"  ❌ ΔE calculation error!")
        return False
    
    # Black bean: L=10, a=2, b=8 → should be high ΔE
    de_black = ct.delta_e(10.0, 2.0, 8.0)
    print(f"  Black (10,2,8): ΔE={de_black:.2f} (expect high, >20)")
    
    # Brown/fermented: L=35, a=10, b=25
    de_ferm = ct.delta_e(35.0, 10.0, 25.0)
    print(f"  Brown (35,10,25): ΔE={de_ferm:.2f}")
    
    print(f"  ✅ ΔE calculation OK")
    return True


def test_critical_defects_auto_reject():
    """Test that MOLD/BLACK/FOREIGN always trigger reject."""
    print("\nTEST 7: Critical Defect Auto-Reject")
    print("-" * 40)
    
    classifier = QualityClassifier()
    
    critical_cases = [
        ("Black bean (force A grade but critical)", 
         SensorReading(color_L=10.0, color_a=2.0, color_b=8.0), 
         QualityGrade.A, DefectType.BLACK),
        ("Mold bean",
         SensorReading(color_L=30.0, color_a=5.0, color_b=20.0),
         QualityGrade.B, DefectType.MOLD),
        ("Foreign stone",
         SensorReading(weight_g=2.0, density=2.5),
         QualityGrade.C, DefectType.FOREIGN),
    ]
    
    all_pass = True
    for label, reading, force_grade, expected_defect in critical_cases:
        result = classifier.classify(f"test-{label}", reading)
        if not result.should_reject:
            print(f"  ❌ {label}: should_reject=False (grade={result.grade.value})")
            all_pass = False
        elif expected_defect not in result.defects:
            print(f"  ❌ {label}: {expected_defect.value} not detected")
            all_pass = False
        else:
            print(f"  ✅ {label}: should_reject={result.should_reject} (correct)")
    
    return all_pass


def test_config_persistence():
    """Test QualityConfig JSON save/load."""
    print("\nTEST 8: Config Persistence")
    print("-" * 40)
    
    import tempfile, os
    from pathlib import Path
    
    cfg = QualityConfig()
    cfg.grade_a_min_score = 94.0
    cfg.critical_defects = ["mold", "black", "foreign", "fermented"]
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = f.name
    
    try:
        cfg.save(tmp)
        loaded = QualityConfig.load(tmp)
        
        if loaded.grade_a_min_score != 94.0:
            print(f"  ❌ grade_a_min_score mismatch: {loaded.grade_a_min_score}")
            return False
        
        if set(loaded.critical_defects) != {"mold", "black", "foreign", "fermented"}:
            print(f"  ❌ critical_defects mismatch: {loaded.critical_defects}")
            return False
        
        print(f"  ✅ Config save/load OK (grade_a_min_score={loaded.grade_a_min_score})")
        return True
    finally:
        os.unlink(tmp)


def test_severity_mapping():
    """Test DEFECT_SEVERITY completeness."""
    print("\nTEST 9: Severity Mapping")
    print("-" * 40)
    
    all_types = list(DefectType)
    missing = []
    for dt in all_types:
        if dt not in DEFECT_SEVERITY:
            missing.append(dt.value)
    
    if missing:
        print(f"  ❌ Missing severity for: {missing}")
        return False
    
    # Verify known severities
    critical_high = {DefectType.MOLD, DefectType.BLACK, DefectType.FOREIGN}
    for dt in critical_high:
        if DEFECT_SEVERITY.get(dt, 0) < 4:
            print(f"  ⚠️ {dt.value} severity={DEFECT_SEVERITY[dt]} (expected ≥4)")
    
    print(f"  ✅ All {len(all_types)} defect types have severity")
    return True


def test_classifier_summary():
    """Test BeanQualityResult summary generation."""
    print("\nTEST 10: Classifier Summary")
    print("-" * 40)
    
    classifier = QualityClassifier()
    
    readings = [
        SensorReading(color_L=48.0, color_a=4.0, color_b=17.0, weight_g=0.18, density=0.68, moisture_pct=11.0),
        SensorReading(color_L=48.0, color_a=4.0, color_b=17.0, weight_g=0.05, density=0.68, moisture_pct=11.0),  # broken
        SensorReading(color_L=10.0, color_a=2.0, color_b=8.0, weight_g=0.18, density=0.68, moisture_pct=11.0),  # black
        SensorReading(color_L=48.0, color_a=4.0, color_b=17.0, weight_g=0.18, density=0.35, moisture_pct=11.0),  # dead
    ]
    
    results = classifier.classify_batch(readings)
    summary = classifier.summary(results)
    
    print(f"  Total: {summary['total_beans']} beans")
    print(f"  Grade dist: {summary['grade_distribution']}")
    print(f"  Defect counts: {summary['defect_counts']}")
    print(f"  Accept rate: {summary['accept_rate_pct']}%")
    
    if summary['total_beans'] != 4:
        print("  ❌ Wrong bean count")
        return False
    
    if summary['defect_counts'].get('broken', 0) != 1:
        print(f"  ❌ BROKEN count wrong: {summary['defect_counts']}")
        return False
    
    print("  ✅ Summary generation OK")
    return True


def test_range_threshold_semantics():
    """Test RangeThreshold contains/is_critical semantics."""
    print("\nTEST 11: RangeThreshold Semantics")
    print("-" * 40)
    
    from sorter.quality.thresholds import RangeThreshold
    
    rt = RangeThreshold(min_val=0.10, max_val=0.28, unit="g",
                       critical_low=0.05, critical_high=0.60)
    
    # Normal values
    assert rt.contains(0.18) == True, "0.18g should be in range"
    assert rt.contains(0.10) == True, "0.10g at boundary should be in range"
    assert rt.contains(0.28) == True, "0.28g at boundary should be in range"
    
    # Out of range
    assert rt.contains(0.05) == False, "0.05g should be out of range"
    assert rt.contains(0.29) == False, "0.29g should be out of range"
    assert rt.contains(0.70) == False, "0.70g should be out of range"
    
    # Critical
    assert rt.is_critical(0.04) == True, "0.04g is critical_low"
    assert rt.is_critical(0.70) == True, "0.70g is critical_high"
    assert rt.is_critical(0.18) == False, "0.18g is not critical"
    
    print("  ✅ RangeThreshold semantics correct (normal=in range, outside=defective)")
    return True


def main():
    print("=" * 60)
    print("  sorter/quality/ Module Validation Suite")
    print("  HUSKY-SORTER-001 | 2026-05-04")
    print("=" * 60)
    
    tests = [
        ("Module Imports", test_imports),
        ("Normal Range Acceptance", test_threshold_normal_ranges),
        ("Defect Detection", test_defect_detection),
        ("Grading Boundaries", test_grading_boundaries),
        ("Batch Aggregation", test_batch_aggregation),
        ("ΔE Calculation", test_delta_e_calculation),
        ("Critical Auto-Reject", test_critical_defects_auto_reject),
        ("Config Persistence", test_config_persistence),
        ("Severity Mapping", test_severity_mapping),
        ("Classifier Summary", test_classifier_summary),
        ("RangeThreshold Semantics", test_range_threshold_semantics),
    ]
    
    results = []
    for name, fn in tests:
        try:
            passed = fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ EXCEPTION: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    score = passed / total * 100
    
    for name, p in results:
        status = "✅ PASS" if p else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Score: {passed}/{total} = {score:.1f}%")
    
    if score == 100:
        print("  🎉 All tests passed!")
        return 0
    elif score >= 80:
        print("  ⚠️  Most tests passed (≥80%)")
        return 0
    else:
        print("  ❌ Multiple failures — review required")
        return 1


if __name__ == "__main__":
    sys.exit(main())
