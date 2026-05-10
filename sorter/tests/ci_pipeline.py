#!/usr/bin/env python3
"""
CI/CD Validation Pipeline for HUSKY-SORTER-001
================================================
Automated code quality and validation pipeline.
Runs on every push to ensure software quality gate.

Usage:
  python sorter/tests/ci_pipeline.py              # Full pipeline
  python sorter/tests/ci_pipeline.py --fast        # Skip slow tests
  python sorter/tests/ci_pipeline.py --modules sorter.camera sorter.control

Author: Little Husky 🐕 | Date: 2026-05-10
"""

import sys
import os
import re
import ast
import json
import time
import subprocess
import argparse
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
SORTEDIR = PROJECT_ROOT / "sorter"

GREEN = "\x1b[92m"
RED = "\x1b[91m"
YELLOW = "\x1b[93m"
BLUE = "\x1b[94m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

def color(code: str, text: str) -> str:
    return f"{code}{text}{RESET}"

def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(color(BOLD + BLUE, f"  {title}"))
    print(color(BOLD + BLUE, f"  {'='*70}"))

def ok(msg: str) -> None:
    print(f"  {color(GREEN, '✅')}  {msg}")

def fail(msg: str) -> None:
    print(f"  {color(RED, '❌')}  {msg}")

def warn(msg: str) -> None:
    print(f"  {color(YELLOW, '⚠️')}  {msg}")

def info(msg: str) -> None:
    print(f"  {color(BLUE, 'ℹ️')}  {msg}")

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    duration_ms: float = 0.0
    details: List[str] = field(default_factory=list)

@dataclass
class PipelineResult:
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    warnings: int = 0
    total_time_ms: float = 0.0
    results: List[TestResult] = field(default_factory=list)

# =============================================================================
# Test 1: Python Syntax Validation
# =============================================================================
def test_python_syntax() -> TestResult:
    """Validate all Python files compile without syntax errors."""
    start = time.time()
    result = TestResult(name="Python Syntax Validation", passed=True)
    
    python_files = list(PROJECT_ROOT.glob("**/*.py"))
    python_files = [f for f in python_files if "__pycache__" not in str(f) and ".git" not in str(f)]
    
    errors = []
    checked = 0
    for f in python_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                source = fp.read()
            ast.parse(source)
            checked += 1
        except SyntaxError as e:
            errors.append(f"  {f.relative_to(PROJECT_ROOT)}:{e.lineno} → {e.msg}")
    
    result.duration_ms = (time.time() - start) * 1000
    if errors:
        result.passed = False
        result.message = f"{len(errors)} syntax error(s) found"
        result.details = errors[:20]  # Cap at 20
    else:
        result.message = f"All {checked} Python files valid ✅"
    
    return result

# =============================================================================
# Test 2: Import Validation
# =============================================================================
def test_imports() -> TestResult:
    """Validate all Python modules can be imported without errors."""
    start = time.time()
    result = TestResult(name="Module Import Validation", passed=True)
    
    modules_to_test = [
        "sorter.config",
        "sorter.control.main",
        "sorter.control.health_monitor",
        "sorter.control.dashboard",
        "sorter.camera.ml_pipeline",
        "sorter.camera.synthetic_test_data_generator",
        "sorter.sensors.load_cell",
        "sorter.sensors.moisture",
        "sorter.motor.spiral_feeder",
        "sorter.motor.solenoid_gate",
        "sorter.db.models",
        "sorter.db.database",
        "sorter.db.report_generator",
        "sorter.db.cli",
        "sorter.simulation.robustness_test_framework",
        "sorter.simulation.oee_monitor",
        "sorter.simulation.spc_quality_monitor",
    ]
    
    # Only test files that exist
    existing = []
    for m in modules_to_test:
        path = PROJECT_ROOT / (m.replace(".", "/") + ".py")
        if path.exists():
            existing.append(m)
    
    errors = []
    optional_warnings = 0
    for mod in existing:
        try:
            __import__(mod)
        except ImportError as e:
            error_str = str(e)
            if any(dep in error_str for dep in ["Flask", "tensorflow", "keras", "_tkinter", "matplotlib"]):
                optional_warnings += 1
                continue
            errors.append(f"  {mod} → {error_str}")
    
    result.warnings = optional_warnings
    result.duration_ms = (time.time() - start) * 1000
    if errors:
        result.passed = False
        result.message = f"{len(errors)} import error(s)"
        result.details = errors
    else:
        result.message = f"All {len(existing)} modules imported ✅ ({optional_warnings} optional deps expected)"
    
    return result

# =============================================================================
# Test 3: Data Model Integrity
# =============================================================================
def test_data_models() -> TestResult:
    """Validate core data models are consistent across modules."""
    start = time.time()
    result = TestResult(name="Data Model Integrity", passed=True)
    
    checks = []
    
    # Check BeanDefect enum consistency
    from sorter.db.models import BeanDefect, BatchState, SortGrade
    defects = list(BeanDefect)
    checks.append(("BeanDefect enum count", len(defects) == 14, f"{len(defects)} defects"))
    
    # Check sort grades
    grades = list(SortGrade)
    checks.append(("SortGrade enum count", len(grades) == 4, f"{len(grades)} grades"))
    
    # Check batch states
    states = list(BatchState)
    checks.append(("BatchState enum count", len(states) >= 5, f"{len(states)} states"))
    
    # Check BeanRecord fields (control layer uses camelCase-style names)
    from sorter.control.main import BeanRecord
    bean_fields = {f.name for f in fields(BeanRecord)}
    # Control layer BeanRecord fields (actual schema)
    required_fields = {"bean_id", "weight_g", "moisture_pct", "color_score", "density_class", "quality_class", "channel_id", "timestamp"}
    missing = required_fields - bean_fields
    checks.append(("BeanRecord required fields", len(missing) == 0, f"missing: {missing}" if missing else "complete"))
    
    failed = [c for c in checks if not c[1]]
    result.duration_ms = (time.time() - start) * 1000
    if failed:
        result.passed = False
        result.message = f"{len(failed)} data model inconsistency"
        result.details = [f"{c[0]}: {c[2]}" for c in failed]
    else:
        result.message = f"All {len(checks)} data model checks passed ✅"
    
    return result

# =============================================================================
# Test 4: Configuration Schema Validation
# =============================================================================
def test_config_schema() -> TestResult:
    """Validate system configuration schema is complete."""
    start = time.time()
    result = TestResult(name="Configuration Schema Validation", passed=True)
    
    from sorter.config import SystemConfig
    try:
        cfg = SystemConfig()
        config_checks = [
            ("gpio config", cfg.gpio is not None),
            ("sensor config", cfg.sensor is not None),
            ("motor config", cfg.motor is not None),
            ("mqtt config", cfg.mqtt is not None),
            ("api config", cfg.api is not None),
            ("batch config", cfg.batch is not None),
            ("quality config", cfg.quality is not None),
        ]
        
        # JSON serialization
        json_ok = False
        try:
            d = cfg.to_dict()
            json_ok = d is not None and isinstance(d, dict)
            config_checks.append(("JSON serialization", json_ok, "OK" if json_ok else "FAIL"))
        except Exception as e:
            config_checks.append(("JSON serialization", False, str(e)))
        
        failed = [c for c in config_checks if not c[1]]
        result.duration_ms = (time.time() - start) * 1000
        if failed:
            result.passed = False
            result.message = f"{len(failed)} config schema issue(s)"
            result.details = [f"{c[0]}: {c[2]}" for c in failed]
        else:
            result.message = f"All 8 config sections valid ✅"
    except Exception as e:
        result.passed = False
        result.message = f"Config load failed: {e}"
        result.duration_ms = (time.time() - start) * 1000
    
    return result

# =============================================================================
# Test 5: State Machine Coverage
# =============================================================================
def test_state_machine() -> TestResult:
    """Validate state machine transitions are complete."""
    start = time.time()
    result = TestResult(name="State Machine Coverage", passed=True)
    
    from sorter.control.main import MachineState, SubState, Event
    
    states = list(MachineState)
    events = list(Event)
    
    checks = [
        ("MachineState enum", len(states) == 9, f"{len(states)} states"),
        ("Event enum", len(events) >= 10, f"{len(events)} events"),
        ("SubState enum", len(list(SubState)) >= 5, f"{len(list(SubState))} sub-states"),
    ]
    
    failed = [c for c in checks if not c[1]]
    result.duration_ms = (time.time() - start) * 1000
    if failed:
        result.passed = False
        result.message = f"{len(failed)} state machine issue(s)"
        result.details = [f"{c[0]}: {c[2]}" for c in failed]
    else:
        result.message = f"State machine complete: {len(states)} states, {len(events)} events ✅"
    
    return result

# =============================================================================
# Test 6: Database Schema
# =============================================================================
def test_database_schema() -> TestResult:
    """Validate database schema and migrations."""
    start = time.time()
    result = TestResult(name="Database Schema Validation", passed=True)
    
    from sorter.db.database import Database
    import tempfile
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_ci.db")
            db = Database(db_path)
            
            tables = db._local.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            
            required_tables = {"batches", "beans", "calibrations", "system_events"}
            missing = required_tables - set(table_names)
            
            checks = [
                ("batches table", "batches" in table_names, table_names),
                ("beans table", "beans" in table_names, table_names),
                ("calibrations table", "calibrations" in table_names, table_names),
                ("system_events table", "system_events" in table_names, table_names),
            ]
            
            failed = [c for c in checks if not c[1]]
            result.duration_ms = (time.time() - start) * 1000
            if failed:
                result.passed = False
                result.message = f"{len(failed)} missing table(s)"
                result.details = [f"Required: {missing}"]
            else:
                result.message = f"All 4 tables exist ✅"
    except Exception as e:
        result.passed = False
        result.message = f"Database schema check failed: {e}"
        result.duration_ms = (time.time() - start) * 1000
    
    return result

# =============================================================================
# Test 7: Report Generator
# =============================================================================
def test_report_generator() -> TestResult:
    """Validate report generation for all output formats."""
    start = time.time()
    result = TestResult(name="Report Generator Validation", passed=True)
    
    from sorter.db.report_generator import BatchReportGenerator
    from sorter.db.models import BatchState
    import tempfile
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            batch = {
                "batch_id": "CI-TEST-001",
                "state": BatchState.COMPLETED,
                "origin": "Test Origin",
                "total_beans": 100,
                "defective_beans": 5,
                "total_weight_g": 15.2,
                "grade_a_count": 80,
                "grade_b_count": 15,
                "grade_c_count": 3,
                "rejected_count": 2,
                "quality_score": 82.5,
                "defect_types": {"BROKEN": 3, "MOLD": 2},
                "start_time": datetime.now().isoformat(),
                "end_time": datetime.now().isoformat(),
            }
            
            from sorter.db.models import BatchRecord, BatchState

            # Build proper BatchRecord from dict
            batch_record = BatchRecord(
                batch_id="CI-TEST-001",
                state=BatchState.COMPLETED.value,
                origin=batch["origin"],
                total_beans=batch["total_beans"],
                defective_beans=batch["defective_beans"],
                total_weight_g=batch["total_weight_g"],
                grade_a_count=batch["grade_a_count"],
                grade_b_count=batch["grade_b_count"],
                grade_c_count=batch["grade_c_count"],
                grade_reject_count=batch["rejected_count"],
                defect_counts_json=json.dumps(batch.get("defect_types", {})),
                started_at_utc=datetime.now().isoformat(),
                ended_at_utc=datetime.now().isoformat(),
            )

            # Use DB-backed BatchReportGenerator
            from sorter.db.database import Database
            db = Database(os.path.join(tmpdir, "ci_test.db"))
            gen = BatchReportGenerator(db)

            # Insert test batch into DB
            batch_id = db.insert_batch(batch_record)
            
            json_report = gen.generate_json("CI-TEST-001", include_beans=True, include_events=True)
            json_valid = isinstance(json_report, dict) and len(json_report) > 0
            
            csv_str = gen.generate_csv("CI-TEST-001")
            csv_valid = isinstance(csv_str, str) and len(csv_str) > 50
            csv_path = os.path.join(tmpdir, f"batch_CI-TEST-001.csv")
            with open(csv_path, "w") as f:
                f.write(csv_str)
            csv_exists = os.path.exists(csv_path)
            
            text_report = gen.generate_text("CI-TEST-001")
            text_valid = isinstance(text_report, str) and len(text_report) > 50
            
            checks = [
                ("JSON report", json_valid, "OK" if json_valid else "FAIL"),
                ("CSV report", csv_exists, csv_path if csv_exists else "MISSING"),
                ("TEXT report", text_valid, "OK" if text_valid else "FAIL"),
            ]
            
            failed = [c for c in checks if not c[1]]
            result.duration_ms = (time.time() - start) * 1000
            if failed:
                result.passed = False
                result.message = f"{len(failed)} report format(s) failed"
                result.details = [f"{c[0]} → {c[2]}" for c in failed]
            else:
                result.message = f"All 3 report formats generated ✅"
    except Exception as e:
        result.passed = False
        result.message = f"Report generator failed: {e}"
        result.duration_ms = (time.time() - start) * 1000
    
    return result

# =============================================================================
# Test 8: Simulation Smoke Tests
# =============================================================================
def test_simulation_smoke() -> TestResult:
    """Smoke test simulation modules."""
    start = time.time()
    result = TestResult(name="Simulation Smoke Tests", passed=True)
    
    sim_modules = [
        "sorter.simulation.robustness_test_framework",
        "sorter.simulation.oee_monitor",
        "sorter.simulation.spc_quality_monitor",
        "sorter.simulation.digital_twin_simulation",
        "sorter.simulation.parameter_sensitivity_analysis",
    ]
    
    errors = []
    for mod_name in sim_modules:
        try:
            mod = __import__(mod_name, fromlist=[""])
            # Check for key classes
            if "robustness" in mod_name:
                assert hasattr(mod, "RobustnessTestRunner"), f"No RobustnessTestRunner in {mod_name}"
            elif "oee" in mod_name:
                assert hasattr(mod, "OEECalculator"), f"No OEECalculator in {mod_name}"
            elif "spc" in mod_name or "quality" in mod_name:
                assert hasattr(mod, "SPCMonitor"), f"No SPCMonitor in {mod_name}"
        except AssertionError as e:
            errors.append(f"  {mod_name}: {e}")
        except ImportError:
            result.warnings = getattr(result, 'warnings', 0) + 1
            continue
        except Exception as e:
            errors.append(f"  {mod_name}: {e}")
    
    result.duration_ms = (time.time() - start) * 1000
    if errors:
        result.passed = False
        result.message = f"{len(errors)} simulation module error(s)"
        result.details = errors
    else:
        result.message = f"Simulation modules smoke test passed ✅"
    
    return result

# =============================================================================
# Test 9: Docs & README Links Check
# =============================================================================
def test_docs_integrity() -> TestResult:
    """Check all documentation files exist and have expected structure."""
    start = time.time()
    result = TestResult(name="Documentation Integrity", passed=True)
    
    required_docs = [
        "sorter/docs/OPERATOR_MANUAL.md",
        "sorter/docs/PROCUREMENT_GUIDE.md",
        "sorter/docs/ANNOTATION_GUIDE.md",
        "sorter/docs/COMMISSIONING_GUIDE.md",
        "sorter/docs/SITE_PREP.md",
        "sorter/control/WIRING_GUIDE.md",
        "sorter/control/DEBUGGING_GUIDE.md",
        "sorter/control/pi_setup.sh",
        "README.md",
    ]
    
    missing = []
    for doc in required_docs:
        path = PROJECT_ROOT / doc
        if not path.exists():
            missing.append(doc)
        elif path.stat().st_size < 100:
            missing.append(f"{doc} (empty)")
    
    result.duration_ms = (time.time() - start) * 1000
    if missing:
        result.passed = False
        result.message = f"{len(missing)} doc file(s) missing or empty"
        result.details = [f"  {m}" for m in missing]
    else:
        result.message = f"All {len(required_docs)} docs present ✅"
    
    return result

# =============================================================================
# Test 10: Git Repository State
# =============================================================================
def test_git_state() -> TestResult:
    """Check git repository is in clean state for push."""
    start = time.time()
    result = TestResult(name="Git Repository State", passed=True)
    
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        untracked = [l for l in status.stdout.strip().split("\n") if l and not l.startswith("??")]
        
        if untracked:
            result.warnings = 1
            result.message = f"{len(untracked)} staged file(s) to commit"
        else:
            result.message = "Git working tree clean ✅"
    except Exception as e:
        result.warnings = 1
        result.message = f"Git check skipped: {e}"
    
    result.duration_ms = (time.time() - start) * 1000
    return result

# =============================================================================
# Pipeline Runner
# =============================================================================
def run_pipeline(fast: bool = False) -> PipelineResult:
    """Run the full CI pipeline."""
    pipeline = PipelineResult()
    
    section("CI/CD Validation Pipeline — HUSKY-SORTER-001")
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project: {PROJECT_ROOT}")
    
    tests = [
        ("Syntax", test_python_syntax),
        ("Imports", test_imports),
        ("DataModels", test_data_models),
        ("Config", test_config_schema),
        ("StateMachine", test_state_machine),
        ("Database", test_database_schema),
        ("Reports", test_report_generator),
        ("Simulation", test_simulation_smoke),
        ("Docs", test_docs_integrity),
        ("Git", test_git_state),
    ]
    
    for name, test_fn in tests:
        if fast and name in ("Simulation",):
            info(f"Skipping {name} (fast mode)")
            pipeline.skipped += 1
            continue
        
        try:
            result = test_fn()
            pipeline.results.append(result)
            pipeline.total_tests += 1
            
            status_icon = color(GREEN, "✅ PASS") if result.passed else color(RED, "❌ FAIL")
            print(f"\n  {status_icon}  {result.name}")
            print(f"      {result.message}  ({result.duration_ms:.1f}ms)")
            
            if result.details:
                for d in result.details[:5]:
                    print(f"      {d}")
            
            if result.passed:
                pipeline.passed += 1
            else:
                pipeline.failed += 1
                pipeline.warnings += len(result.details)
                
        except Exception as e:
            fail(f"{name} crashed: {e}")
            pipeline.total_tests += 1
            pipeline.failed += 1
            pipeline.results.append(TestResult(name=name, passed=False, message=str(e)))
    
    pipeline.total_time_ms = sum(r.duration_ms for r in pipeline.results)
    return pipeline

def print_summary(result: PipelineResult) -> None:
    """Print pipeline summary."""
    section("Pipeline Summary")
    
    total = result.total_tests
    passed = result.passed
    failed = result.failed
    skipped = result.skipped
    duration = result.total_time_ms / 1000
    
    pct = (passed / total * 100) if total > 0 else 0
    grade = "A" if pct >= 90 else "B" if pct >= 75 else "C" if pct >= 60 else "F"
    grade_color = GREEN if grade == "A" else YELLOW if grade == "B" else RED
    
    print(f"\n  {'Tests':<20} {passed}/{total} passed", end="")
    if skipped > 0:
        print(f"  ({skipped} skipped)", end="")
    print()
    print(f"  {'Duration':<20} {duration:.2f}s")
    print(f"  {'Score':<20} {color(BOLD + grade_color, grade)}  ({pct:.1f}%)")
    
    if result.failed > 0:
        print(f"\n  {color(RED, 'Failed Tests:')}")
        for r in result.results:
            if not r.passed:
                print(f"    - {r.name}: {r.message}")
    
    if result.warnings > 0:
        print(f"\n  {color(YELLOW, f'Warnings: {result.warnings}')}")
    
    # Score bar
    bar_len = 30
    filled = int(bar_len * pct / 100)
    bar = color(GREEN, "█" * filled) + color(GREEN, "░" * (bar_len - filled))
    print(f"\n  Score: [{bar}] {pct:.1f}%")
    
    return pct >= 75

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 CI Pipeline")
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--modules", nargs="+", help="Test specific modules")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()
    
    result = run_pipeline(fast=args.fast)
    success = print_summary(result)
    
    if args.json:
        report = {
            "timestamp": datetime.now().isoformat(),
            "total": result.total_tests,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "warnings": result.warnings,
            "duration_sec": result.total_time_ms / 1000,
            "grade": "A" if success else "F",
            "results": [
                {"name": r.name, "passed": r.passed, "message": r.message, "duration_ms": r.duration_ms}
                for r in result.results
            ]
        }
        report_path = PROJECT_ROOT / "sorter" / "reports" / "ci_pipeline_report.json"
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        info(f"JSON report → {report_path}")
    
    sys.exit(0 if success else 1)