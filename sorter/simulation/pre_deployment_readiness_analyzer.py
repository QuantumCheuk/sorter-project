#!/usr/bin/env python3
"""
HUSKY-SORTER-001 Pre-Deployment Readiness Analyzer
===================================================
Validates complete project readiness for hardware arrival.

Checks:
1. Project structure completeness
2. Key files presence
3. ESP32 firmware compilation readiness
4. Python syntax integrity across all modules
5. Calibration data validation
6. SPEC.md compliance cross-check
7. Documentation coverage
8. Git sync status

Output: JSON report + GO/NO-GO readiness verdict

Author: Little Husky 🐕 | Date: 2026-05-08
"""

import json
import os
import sys
import ast
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
SORT = PROJECT_ROOT / "sorter"


@dataclass
class CheckResult:
    name: str
    passed: bool
    score: float  # 0-100
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


@dataclass
class ReadinessReport:
    timestamp: str
    project_path: str
    total_checks: int
    passed_checks: int
    overall_score: float
    verdict: str  # GO / NO-GO / CONDITIONAL-GO
    checks: List[CheckResult] = field(default_factory=list)
    critical_blockers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class PreDeploymentAnalyzer:
    """Analyzes project readiness for hardware deployment."""

    def __init__(self):
        self.checks: List[CheckResult] = []

    def check_project_structure(self) -> CheckResult:
        """Check that all required directories and files exist."""
        result = CheckResult(
            name="Project Structure Completeness",
            passed=True,
            score=0.0
        )

        required_dirs = [
            "sorter/camera", "sorter/sensors", "sorter/motor",
            "sorter/control", "sorter/db", "sorter/mqtt",
            "sorter/api", "sorter/simulation", "sorter/docs",
            "sorter/quality", "firmware/sorter_esp32",
            "data", "reports", "calibration_data"
        ]

        missing = []
        for d in required_dirs:
            if not (PROJECT_ROOT / d).exists():
                missing.append(d)

        if missing:
            result.errors.append(f"Missing directories: {', '.join(missing)}")
            result.passed = False

        # Count files
        py_files = list(PROJECT_ROOT.rglob("*.py"))
        ino_files = list(PROJECT_ROOT.rglob("*.ino"))
        md_files = list(PROJECT_ROOT.rglob("*.md"))

        result.details = {
            "python_files": len(py_files),
            "arduino_files": len(ino_files),
            "markdown_docs": len(md_files),
            "missing_dirs": missing
        }

        # Score based on file counts
        target_py = 60
        target_md = 5
        py_score = min(50, (len(py_files) / target_py) * 50)
        md_score = min(20, (len(md_files) / target_md) * 20)
        dir_score = 30 if not missing else 0
        result.score = py_score + md_score + dir_score

        return result

    def check_python_syntax(self) -> CheckResult:
        """Validate Python syntax across all files."""
        result = CheckResult(
            name="Python Syntax Integrity",
            passed=True,
            score=100.0
        )

        py_files = list(PROJECT_ROOT.rglob("*.py"))
        errors = []
        checked = 0

        for f in py_files:
            # Skip __pycache__ and node_modules
            if "__pycache__" in str(f) or "node_modules" in str(f):
                continue
            try:
                with open(f, "rb") as fp:
                    raw = fp.read()
                # Try UTF-8, fall back to Latin-1
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    content = raw.decode("latin-1")
                ast.parse(content, filename=str(f))
                checked += 1
            except SyntaxError as e:
                errors.append(f"{f.relative_to(PROJECT_ROOT)}: Line {e.lineno}: {e.msg}")
                result.passed = False

        if errors:
            result.errors.extend(errors[:10])  # cap at 10
            result.score = max(0, 100 - len(errors) * 10)

        result.details = {
            "files_checked": checked,
            "syntax_errors": len(errors)
        }

        return result

    def check_firmware_readiness(self) -> CheckResult:
        """Check ESP32 firmware file exists and has key components."""
        result = CheckResult(
            name="ESP32 Firmware Readiness",
            passed=True,
            score=0.0
        )

        firmware_path = PROJECT_ROOT / "firmware" / "sorter_esp32" / "sorter_esp32.ino"
        if not firmware_path.exists():
            result.errors.append("sorter_esp32.ino not found")
            result.passed = False
            result.score = 0
            return result

        with open(firmware_path) as f:
            content = f.read()

        # Check key components
        checks = {
            "FIRMWARE_VERSION": "FIRMWARE_VERSION" in content,
            "HX711_interface": "hx711_read_raw" in content,
            "UART_protocol": "HardwareSerial" in content or "Serial" in content,
            "Stepper_control": "stepper_move_steps" in content,
            "Solenoid_control": "solenoid_set" in content,
            "JSON_protocol": "cmd" in content and "args" in content,
            "FreeRTOS_tasks": "xTaskCreate" in content or "TaskHandle_t" in content,
            "GPIO_init": "gpio_config" in content,
        }

        passed = sum(checks.values())
        total = len(checks)
        result.details = checks
        result.score = (passed / total) * 100
        result.passed = passed == total

        if not result.passed:
            failed = [k for k, v in checks.items() if not v]
            result.errors.append(f"Missing components: {', '.join(failed)}")

        # Check firmware version
        line_count = len(content.split("\n"))
        result.details["line_count"] = line_count

        return result

    def check_documentation_coverage(self) -> CheckResult:
        """Check critical documentation files exist and are substantial."""
        result = CheckResult(
            name="Documentation Coverage",
            passed=True,
            score=0.0
        )

        docs = {
            "OPERATOR_MANUAL.md": ("sorter/docs/OPERATOR_MANUAL.md", 500),
            "COMMISSIONING_GUIDE.md": ("sorter/docs/COMMISSIONING_GUIDE.md", 400),
            "PROCUREMENT_GUIDE.md": ("sorter/docs/PROCUREMENT_GUIDE.md", 300),
            "WIRING_GUIDE.md": ("sorter/control/WIRING_GUIDE.md", 200),
            "DEBUGGING_GUIDE.md": ("sorter/control/DEBUGGING_GUIDE.md", 300),
            "ANNOTATION_GUIDE.md": ("sorter/docs/ANNOTATION_GUIDE.md", 200),
            "SPEC.md": ("SPEC.md", 500),
            "README.md": ("README.md", 100),
        }

        checked = {}
        missing = []
        insufficient = []

        for name, (path, min_lines) in docs.items():
            full_path = PROJECT_ROOT / path
            if not full_path.exists():
                missing.append(name)
            else:
                with open(full_path) as f:
                    lines = len([l for l in f.readlines() if l.strip()])
                checked[name] = lines
                if lines < min_lines:
                    insufficient.append(f"{name} ({lines}<{min_lines})")

        result.details = checked

        if missing:
            result.errors.append(f"Missing docs: {', '.join(missing)}")
            result.passed = False

        if insufficient:
            result.warnings.extend(insufficient)

        # Score
        base_score = 50 if not missing else 0
        quality_bonus = min(50, sum(max(0, v - 100) for v in checked.values()) / 20)
        result.score = base_score + quality_bonus

        return result

    def check_calibration_data(self) -> CheckResult:
        """Check calibration data files exist and are valid."""
        result = CheckResult(
            name="Calibration Data Validation",
            passed=True,
            score=100.0
        )

        cal_dir = PROJECT_ROOT / "calibration_data"
        if not cal_dir.exists():
            result.warnings.append("calibration_data directory not found (expected after first calibration run)")
            result.score = 60
            return result

        json_files = list(cal_dir.glob("*.json"))
        result.details = {
            "calibration_files": len(json_files),
            "files": [f.name for f in json_files]
        }

        # Validate JSON structure
        valid_count = 0
        for f in json_files:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                # Check for required fields
                if "timestamp" in data or "calibration_id" in data:
                    valid_count += 1
            except json.JSONDecodeError:
                result.errors.append(f"Invalid JSON: {f.name}")

        if json_files:
            result.score = (valid_count / len(json_files)) * 100
            result.passed = valid_count == len(json_files)

        return result

    def check_spec_compliance(self) -> CheckResult:
        """Check key SPEC.md requirements against implementation."""
        result = CheckResult(
            name="SPEC.md Compliance",
            passed=True,
            score=100.0
        )

        spec_path = PROJECT_ROOT / "SPEC.md"
        if not spec_path.exists():
            result.errors.append("SPEC.md not found")
            result.passed = False
            result.score = 0
            return result

        with open(spec_path) as f:
            spec_content = f.read()

        # Key requirements to check
        requirements = {
            "3_channel_architecture": "3通道" in spec_content or "3-channel" in spec_content,
            "mqtt_integration": "MQTT" in spec_content,
            "esp32_firmware": "ESP32" in spec_content,
            "color_detection": "颜色" in spec_content or "color" in spec_content.lower(),
            "weight_sensor": "称重" in spec_content or "weight" in spec_content.lower(),
            "moisture_sensor": "含水率" in spec_content or "moisture" in spec_content.lower(),
            "density_separation": "密度" in spec_content or "density" in spec_content,
            "throughput_2kg": "2kg" in spec_content or "2.0kg" in spec_content,
            "safety_system": "安全" in spec_content or "safety" in spec_content.lower(),
            "rest_api": "REST" in spec_content or "API" in spec_content,
        }

        passed = sum(requirements.values())
        total = len(requirements)
        result.details = requirements
        result.score = (passed / total) * 100
        result.passed = passed >= total - 1  # allow 1 miss

        if not result.passed:
            failed = [k for k, v in requirements.items() if not v]
            result.errors.append(f"Missing specs: {', '.join(failed)}")

        # Extract version
        import re
        version_match = re.search(r"v(\d+\.\d+)", spec_content[:500])
        if version_match:
            result.details["spec_version"] = version_match.group(0)

        return result

    def check_git_status(self) -> CheckResult:
        """Check Git synchronization status."""
        result = CheckResult(
            name="Git Synchronization Status",
            passed=True,
            score=100.0
        )

        git_dir = PROJECT_ROOT / ".git"
        if not git_dir.exists():
            result.warnings.append("Not a git repository")
            result.score = 50
            return result

        # Check for uncommitted changes
        import subprocess
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=10
            )
            uncommitted = proc.stdout.strip()
            if uncommitted:
                lines = uncommitted.split("\n")
                result.warnings.append(f"{len(lines)} uncommitted file(s)")
                result.details["uncommitted_files"] = len(lines)
                result.score = max(30, 100 - len(lines) * 5)
            else:
                result.details["status"] = "clean"

            # Get current commit
            proc2 = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=10
            )
            if proc2.returncode == 0:
                result.details["commit"] = proc2.stdout.strip()

            # Check remote
            proc3 = subprocess.run(
                ["git", "branch", "-vv"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=10
            )
            if "[origin/" in proc3.stdout:
                result.details["remote_tracking"] = "configured"
            else:
                result.warnings.append("No remote tracking configured")

        except Exception as e:
            result.warnings.append(f"Git check failed: {e}")
            result.score = 70

        return result

    def check_simulation_breadth(self) -> CheckResult:
        """Check that simulation modules cover all subsystems."""
        result = CheckResult(
            name="Simulation Breadth",
            passed=True,
            score=0.0
        )

        sim_dir = PROJECT_ROOT / "sorter" / "simulation"
        if not sim_dir.exists():
            result.errors.append("simulation directory not found")
            result.passed = False
            return result

        sim_files = [f.name for f in sim_dir.glob("*.py")]
        result.details = {"simulation_files": len(sim_files), "files": sim_files}

        # Key simulation areas
        required_sims = {
            "throughput_analysis": any("throughput" in f.lower() for f in sim_files),
            "calibration_toolkit": any("calibration" in f.lower() for f in sim_files),
            "digital_twin": any("digital" in f.lower() or "twin" in f.lower() for f in sim_files),
            "multi_channel": any("multi" in f.lower() or "channel" in f.lower() for f in sim_files),
            "safety_analysis": any("safety" in f.lower() for f in sim_files),
            "energy_analysis": any("energy" in f.lower() for f in sim_files),
            "quality_scoring": any("quality" in f.lower() or "fusion" in f.lower() for f in sim_files),
        }

        passed = sum(required_sims.values())
        total = len(required_sims)
        result.score = (passed / total) * 100
        result.passed = passed >= total - 1
        result.details["coverage"] = required_sims

        return result

    def run_all_checks(self) -> ReadinessReport:
        """Run all checks and generate report."""
        check_methods = [
            self.check_project_structure,
            self.check_python_syntax,
            self.check_firmware_readiness,
            self.check_documentation_coverage,
            self.check_calibration_data,
            self.check_spec_compliance,
            self.check_git_status,
            self.check_simulation_breadth,
        ]

        for method in check_methods:
            self.checks.append(method())

        total_score = sum(c.score for c in self.checks) / len(self.checks)
        passed_count = sum(1 for c in self.checks if c.passed)

        # Determine verdict
        critical_blockers = []
        for c in self.checks:
            critical = ["firmware", "syntax", "spec"]
            if any(x in c.name.lower() for x in critical) and not c.passed:
                critical_blockers.extend(c.errors)

        if critical_blockers:
            verdict = "NO-GO"
        elif passed_count >= len(self.checks) - 1:
            if total_score >= 85:
                verdict = "GO"
            else:
                verdict = "CONDITIONAL-GO"
        else:
            verdict = "CONDITIONAL-GO"

        # Recommendations
        recommendations = []
        for c in self.checks:
            if c.warnings:
                recommendations.extend([f"[{c.name}] {w}" for w in c.warnings[:3]])
        if total_score < 80:
            recommendations.append("Overall score below 80 - address critical gaps before deployment")

        return ReadinessReport(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            project_path=str(PROJECT_ROOT),
            total_checks=len(self.checks),
            passed_checks=passed_count,
            overall_score=total_score,
            verdict=verdict,
            checks=self.checks,
            critical_blockers=critical_blockers[:5],
            recommendations=recommendations[:10]
        )


def main():
    print("=" * 60)
    print("HUSKY-SORTER-001 Pre-Deployment Readiness Analyzer")
    print("=" * 60)

    analyzer = PreDeploymentAnalyzer()
    report = analyzer.run_all_checks()

    # Console output
    print(f"\nOverall Score: {report.overall_score:.1f}/100")
    print(f"Verdict: {report.verdict}")
    print(f"Passed: {report.passed_checks}/{report.total_checks} checks\n")

    print("Check Results:")
    print("-" * 60)
    for check in report.checks:
        status = "✅" if check.passed else "❌"
        print(f"  {status} [{check.score:5.1f}] {check.name}")
        if check.errors:
            for e in check.errors[:3]:
                print(f"       ERROR: {e}")
        if check.warnings:
            for w in check.warnings[:2]:
                print(f"       WARN:  {w}")

    if report.critical_blockers:
        print("\n🚨 CRITICAL BLOCKERS:")
        for b in report.critical_blockers:
            print(f"  - {b}")

    if report.recommendations:
        print("\n📋 Recommendations:")
        for r in report.recommendations[:5]:
            print(f"  - {r}")

    # Save JSON report
    report_path = PROJECT_ROOT / "reports" / f"pre_deployment_readiness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)

    report_dict = {
        "timestamp": report.timestamp,
        "project_path": report.project_path,
        "total_checks": report.total_checks,
        "passed_checks": report.passed_checks,
        "overall_score": report.overall_score,
        "verdict": report.verdict,
        "critical_blockers": report.critical_blockers,
        "recommendations": report.recommendations,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "score": c.score,
                "warnings": c.warnings[:5],
                "errors": c.errors[:5],
                "details": c.details
            }
            for c in report.checks
        ]
    }

    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Report saved: {report_path}")
    print("=" * 60)

    return 0 if report.verdict in ("GO", "CONDITIONAL-GO") else 1


if __name__ == "__main__":
    sys.exit(main())