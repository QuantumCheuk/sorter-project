#!/usr/bin/env python3
"""
Installation & Commissioning Project Tracker
============================================
HUSKY-SORTER-001 Deployment Phase Management Tool

Purpose: Plan, track, and manage the hardware installation and commissioning
process from equipment arrival to full production readiness.

Author: Little Husky (HUSKY-SORTER-001)
Version: 1.0 | 2026-05-12
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────────────────

class PhaseStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class MilestoneType(Enum):
    HARDWARE = "hardware"
    ASSEMBLY = "assembly"
    CALIBRATION = "calibration"
    INTEGRATION = "integration"
    QUALIFICATION = "qualification"
    PRODUCTION = "production"


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class ChecklistItem:
    item: str
    done: bool = False
    notes: str = ""

@dataclass
class Task:
    id: str
    name: str
    description: str
    phase: str
    duration_hours: float
    dependencies: list[str] = field(default_factory=list)
    owner: str = "Team"
    risk_level: RiskLevel = RiskLevel.LOW
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    checklist: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def completion_pct(self) -> float:
        if self.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED):
            return 100.0
        if not self.checklist:
            return 50.0 if self.status == PhaseStatus.IN_PROGRESS else 0.0
        done = sum(1 for c in self.checklist if c.get("done", False))
        return round(done / len(self.checklist) * 100, 1)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["risk_level"] = self.risk_level.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        d["status"] = PhaseStatus(d.get("status", "pending"))
        d["risk_level"] = RiskLevel(d.get("risk_level", "low"))
        return cls(**d)


@dataclass
class Milestone:
    id: str
    name: str
    description: str
    milestone_type: MilestoneType
    target_date: str
    actual_date: Optional[str] = None
    status: PhaseStatus = PhaseStatus.PENDING
    task_ids: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)
    signoff_by: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["milestone_type"] = self.milestone_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Milestone":
        d["milestone_type"] = MilestoneType(d.get("milestone_type", "hardware"))
        d["status"] = PhaseStatus(d.get("status", "pending"))
        return cls(**d)


@dataclass
class RiskItem:
    id: str
    description: str
    category: str
    likelihood: RiskLevel
    impact: RiskLevel
    mitigation: str
    contingency: str
    owner: str = ""
    status: str = "open"

    def rpn(self) -> int:
        mapping = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 3, RiskLevel.HIGH: 5, RiskLevel.CRITICAL: 7}
        return mapping[self.likelihood] * mapping[self.impact]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["likelihood"] = self.likelihood.value
        d["impact"] = self.impact.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RiskItem":
        d["likelihood"] = RiskLevel(d.get("likelihood", "medium"))
        d["impact"] = RiskLevel(d.get("impact", "medium"))
        return cls(**d)


class CommissioningTracker:
    PROJECT_NAME = "HUSKY-SORTER-001"
    PROJECT_CODE = "HUSKY-INSTALL-001"
    # Hardware delivery estimate: HQ Camera + Turbo Blower ≈ 60 days from order
    HARDWARE_DELIVERY_ESTIMATE = "2026-07-13"

    def __init__(self, state_file: str = "commissioning_state.json"):
        self.state_file = state_file
        self.start_date = datetime.now().strftime("%Y-%m-%d")
        self.tasks: list[Task] = []
        self.milestones: list[Milestone] = []
        self.risks: list[RiskItem] = []
        self._build_tasks()
        self._build_milestones()
        self._build_risks()
        self._load()

    def _add_days(self, date_str: str, days: int) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
        return d.strftime("%Y-%m-%d")

    # ─── Builders ─────────────────────────────────────────────────────────────

    def _build_tasks(self):
        self.tasks = []

        # Phase 1: Hardware Acceptance (Day 1 after delivery)
        self.tasks.append(Task(
            id="H-01", name="Receive Hardware Shipment",
            description="Receive and inspect all components from suppliers against BOM.",
            phase="Phase 1: Hardware Acceptance", duration_hours=3.0,
            owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Verify box count against packing slip", "done": False},
                {"item": "Check for shipping damage on 3D prints", "done": False},
                {"item": "Verify Pi 4 model (4GB recommended)", "done": False},
                {"item": "Verify HQ Camera (Raspberry Pi HQ Camera IMX477)", "done": False},
                {"item": "Verify Nema17 stepper motors × 3", "done": False},
                {"item": "Verify Turbo blower (5015)", "done": False},
                {"item": "Verify HX711 load cell modules × 3", "done": False},
                {"item": "Verify AD7746 capacitance modules × 3", "done": False},
                {"item": "Verify ESP32 DevKitC × 2", "done": False},
                {"item": "Verify power supplies (12V 3A, 5V 3A)", "done": False},
                {"item": "Photograph all damaged items", "done": False},
                {"item": "Scan QR codes / serial numbers into inventory", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="H-02", name="Inventory & Serial Number Registry",
            description="Create complete inventory with serial numbers and purchase records.",
            phase="Phase 1: Hardware Acceptance", duration_hours=2.0,
            dependencies=["H-01"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Create inventory spreadsheet", "done": False},
                {"item": "Record Pi MAC addresses", "done": False},
                {"item": "Record ESP32 MAC addresses", "done": False},
                {"item": "Label all stepper motors (CH1/CH2/CH3)", "done": False},
                {"item": "Photograph all modules and components", "done": False},
                {"item": "Store receipts and warranty info", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="H-03", name="Incoming Electrical Safety Test",
            description="Insulation resistance and ground continuity tests on all electrical components.",
            phase="Phase 1: Hardware Acceptance", duration_hours=1.5,
            dependencies=["H-01"], owner="Team", risk_level=RiskLevel.HIGH,
            checklist=[
                {"item": "Multimeter insulation test: Pi chassis", "done": False},
                {"item": "Ground continuity test: all metal enclosures", "done": False},
                {"item": "Verify 12V/5V supply voltages under load", "done": False},
                {"item": "Check GPIO pin continuity to header", "done": False},
                {"item": "Document all measurements in test record", "done": False},
            ],
        ))

        # Phase 2: Mechanical Assembly (Day 2-4)
        self.tasks.append(Task(
            id="M-01", name="Frame Assembly",
            description="Assemble extruded aluminum frame (2020 profile) according to CAD drawings.",
            phase="Phase 2: Mechanical Assembly", duration_hours=4.0,
            owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Lay out all 2020 aluminum profiles", "done": False},
                {"item": "Assemble base frame (400×300mm)", "done": False},
                {"item": "Attach vertical posts", "done": False},
                {"item": "Install top frame cross-members", "done": False},
                {"item": "Torque all T-slot nuts to 0.5 N·m", "done": False},
                {"item": "Verify frame squareness (diagonal measurement)", "done": False},
                {"item": "Mount frame to workbench", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="M-02", name="3D Printed Parts Installation",
            description="Install all 3D printed components (buffer hopper, size sorting chutes, bean channels).",
            phase="Phase 2: Mechanical Assembly", duration_hours=3.0,
            dependencies=["M-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Print remaining PLA/PETG parts (check warping)", "done": False},
                {"item": "Install buffer hopper (PETG, check seal)", "done": False},
                {"item": "Install size sorting plate (5 tiers)", "done": False},
                {"item": "Install bean drop channels × 3", "done": False},
                {"item": "Install weighing cup holders × 3", "done": False},
                {"item": "Install dark box enclosure for camera", "done": False},
                {"item": "Install LED ring light mount", "done": False},
                {"item": "Install reject collection trays × 3", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="M-03", name="Dense Phase Air Ducting",
            description="Install dense phase air ducting from turbo blower to separation chamber.",
            phase="Phase 2: Mechanical Assembly", duration_hours=2.0,
            dependencies=["M-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Cut ducting to length (φ40mm)", "done": False},
                {"item": "Install flexible coupling at blower", "done": False},
                {"item": "Install ball valve for flow control", "done": False},
                {"item": "Install separation chamber", "done": False},
                {"item": "Check for air leaks (soap bubble test)", "done": False},
                {"item": "Secure all ducting with hose clamps", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="M-04", name="Stepper Motor Mounting",
            description="Mount Nema17 stepper motors to vibrating feeders and rotating distributor.",
            phase="Phase 2: Mechanical Assembly", duration_hours=2.0,
            dependencies=["M-02"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Mount vibrating feeder motors (check alignment)", "done": False},
                {"item": "Mount rotating distributor motor", "done": False},
                {"item": "Check motor shaft runout (< 0.05mm)", "done": False},
                {"item": "Connect motor couplings", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="M-05", name="Pneumatic System Installation",
            description="Install air tubing, solenoid valves, and E-STOP safety circuit.",
            phase="Phase 2: Mechanical Assembly", duration_hours=3.0,
            dependencies=["M-03"], owner="Team", risk_level=RiskLevel.HIGH,
            checklist=[
                {"item": "Install solenoid valves (GPIO16/17/20/21)", "done": False},
                {"item": "Run polyurethane tubing to jet nozzles", "done": False},
                {"item": "Install E-STOP button (test NC contact)", "done": False},
                {"item": "Wire FAIL-SAFE relay circuit", "done": False},
                {"item": "Pressure test at 6 bar (no leaks for 5 min)", "done": False},
                {"item": "Install mufflers on valve exhaust ports", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="M-06", name="Mechanical Assembly Checkpoint",
            description="Verify all mechanical components are properly secured before electrical phase.",
            phase="Phase 2: Mechanical Assembly", duration_hours=1.0,
            dependencies=["M-04", "M-05"], owner="Team", risk_level=RiskLevel.MEDIUM,
        ))

        # Phase 3: Electrical & Wiring (Day 4-5)
        self.tasks.append(Task(
            id="E-01", name="Power Distribution Wiring",
            description="Wire 12V and 5V power rails with proper fusing and protection.",
            phase="Phase 3: Electrical & Wiring", duration_hours=2.0,
            dependencies=["M-06"], owner="Team", risk_level=RiskLevel.HIGH,
            checklist=[
                {"item": "Install DIN rail terminal blocks", "done": False},
                {"item": "Wire 12V rail (blower, solenoids)", "done": False},
                {"item": "Wire 5V rail (Pi, sensors)", "done": False},
                {"item": "Install blade fuses (3A for 5V, 5A for 12V)", "done": False},
                {"item": "Wire E-STOP safety relay (K1/K2)", "done": False},
                {"item": "Verify no polarity reversals with multimeter", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="E-02", name="Pi GPIO Wiring",
            description="Wire all GPIO connections according to WIRING_GUIDE.md (GPIO27 for HX711 SCK).",
            phase="Phase 3: Electrical & Wiring", duration_hours=3.0,
            dependencies=["E-01"], owner="Team", risk_level=RiskLevel.HIGH,
            checklist=[
                {"item": "GPIO27 ← HX711-1 SCK (solder header)", "done": False},
                {"item": "GPIO4 ← T1 sensor CH1 (photogate)", "done": False},
                {"item": "GPIO5 ← T2 sensor CH1 (photogate)", "done": False},
                {"item": "GPIO16/17/20/21 ← Solenoid valves", "done": False},
                {"item": "I2C bus: GPIO2 (SDA) / GPIO3 (SCL) ← AD7746", "done": False},
                {"item": "Install 4.7kΩ I2C pull-up resistors", "done": False},
                {"item": "Photograph completed wiring", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="E-03", name="ESP32 Wiring & Connection",
            description="Wire ESP32 DevKitC to motor drivers and solenoid valves.",
            phase="Phase 3: Electrical & Wiring", duration_hours=2.0,
            dependencies=["E-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Wire ESP32 GPIO18/19 ← Nema17-1 driver PUL", "done": False},
                {"item": "Wire ESP32 GPIO22/26/27 ← Nema17-2/3 drivers", "done": False},
                {"item": "Wire ESP32 GPIO16/17/20/21 ← Solenoid valve drivers", "done": False},
                {"item": "Connect ESP32 UART TX/RX to Pi", "done": False},
                {"item": "Install ESP32 with standoffs", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="E-04", name="Electrical Inspection & Safety Verification",
            description="Electrical safety verification before first power-on.",
            phase="Phase 3: Electrical & Wiring", duration_hours=1.5,
            dependencies=["E-02", "E-03"], owner="Team", risk_level=RiskLevel.CRITICAL,
            checklist=[
                {"item": "Visual inspection: no exposed conductors", "done": False},
                {"item": "Verify ground continuity < 0.1Ω", "done": False},
                {"item": "Verify no shorts between adjacent GPIO pins", "done": False},
                {"item": "Verify E-STOP opens all power relays", "done": False},
                {"item": "Verify no voltage on GPIO headers before Pi boot", "done": False},
            ],
        ))

        # Phase 4: Software Stack Deployment (Day 5-6)
        self.tasks.append(Task(
            id="S-01", name="Pi OS & Dependencies Installation",
            description="Flash Raspberry Pi OS, configure hostname, install all software dependencies.",
            phase="Phase 4: Software Stack Deployment", duration_hours=2.0,
            dependencies=["E-04"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Flash Raspberry Pi OS 64-bit (2026-03 release)", "done": False},
                {"item": "Expand filesystem to full SD card", "done": False},
                {"item": "Configure hostname: sorter-pi-[01]", "done": False},
                {"item": "Enable I2C, SPI, Camera interface", "done": False},
                {"item": "Run pi_setup.sh (automated setup)", "done": False},
                {"item": "Clone sorter-project from GitHub", "done": False},
                {"item": "pip install: tensorflow, tflite-runtime, opencv-python", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="S-02", name="ESP32 Firmware Flash",
            description="Compile and flash ESP32 firmware with esptool.py.",
            phase="Phase 4: Software Stack Deployment", duration_hours=1.5,
            dependencies=["S-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Connect ESP32 via USB", "done": False},
                {"item": "Build firmware: arduino-cli compile", "done": False},
                {"item": "Flash firmware: esptool.py write_flash", "done": False},
                {"item": "Verify firmware version via UART STATUS command", "done": False},
                {"item": "Backup firmware .bin file to SD card", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="S-03", name="TFLite Model Deployment",
            description="Deploy trained defect detection model to Pi filesystem.",
            phase="Phase 4: Software Stack Deployment", duration_hours=1.0,
            dependencies=["S-01"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Copy INT8 quantized model to /opt/sorter/models/", "done": False},
                {"item": "Verify model file SHA256 checksum", "done": False},
                {"item": "Run model load test (Python import)", "done": False},
                {"item": "Run inference latency benchmark (< 50ms)", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="S-04", name="MQTT Broker & Topic Verification",
            description="Configure and test MQTT broker with sorter topics.",
            phase="Phase 4: Software Stack Deployment", duration_hours=1.0,
            dependencies=["S-01"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Start mosquitto broker", "done": False},
                {"item": "Verify broker listening on port 1883", "done": False},
                {"item": "Test publish/subscribe to sorter/status", "done": False},
                {"item": "Enable mosquitto as systemd service", "done": False},
            ],
        ))

        # Phase 5: Calibration (Day 6-8)
        self.tasks.append(Task(
            id="C-01", name="Load Cell (HX711) Calibration",
            description="Calibrate all 3 load cells using 100g reference weight.",
            phase="Phase 5: Calibration", duration_hours=2.0,
            dependencies=["S-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Preheat HX711 for 30 minutes", "done": False},
                {"item": "Tare zero with empty weighing cup", "done": False},
                {"item": "Calibrate CH1 with 100g reference (record reference_unit)", "done": False},
                {"item": "Verify CH1 linearity: 5 known weights (10-500g)", "done": False},
                {"item": "Calibrate CH2 and CH3 with 100g reference", "done": False},
                {"item": "Verify temperature drift < 0.1g/°C (heat gun test)", "done": False},
                {"item": "Save calibration to calibration_data/CERT-YYYYMMDD.json", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="C-02", name="Color Camera Calibration",
            description="Perform dark noise, white balance, and color reference calibration.",
            phase="Phase 5: Calibration", duration_hours=2.5,
            dependencies=["S-03"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Capture dark frame (close shutter, 1s exposure)", "done": False},
                {"item": "Verify dark noise < 5 DN (per pixel)", "done": False},
                {"item": "Acquire white reference (calibration card)", "done": False},
                {"item": "Verify white balance: ΔR < 5%, ΔB < 5%", "done": False},
                {"item": "Capture color references (brown/green/black bean samples)", "done": False},
                {"item": "Verify L*a*b* values within expected range", "done": False},
                {"item": "Synchronize top + bottom camera trigger < 0.2ms", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="C-03", name="Moisture Sensor (AD7746) Calibration",
            description="Calibrate capacitance-to-moisture conversion for all 3 probes.",
            phase="Phase 5: Calibration", duration_hours=2.0,
            dependencies=["S-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Connect AD7746 with < 5cm direct wiring (no cable extension)", "done": False},
                {"item": "Configure AD7746 to 50Hz update rate", "done": False},
                {"item": "Zero calibration: dry air reference (record C_zero)", "done": False},
                {"item": "Two-point calibration: 5% and 15% moisture reference samples", "done": False},
                {"item": "Verify 12% moisture reading error < 0.5% abs", "done": False},
                {"item": "Repeat for CH2 and CH3 probes", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="C-04", name="Density Fan PID Tuning",
            description="Tune PID controller for density separation air velocity.",
            phase="Phase 5: Calibration", duration_hours=2.0,
            dependencies=["M-03"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Connect anemometer to separation chamber", "done": False},
                {"item": "Set PID parameters: Kp=2.5, Ki=0.8, Kd=0.3", "done": False},
                {"item": "Step test: 2 m/s → 4 m/s → 2 m/s (measure settling time)", "done": False},
                {"item": "Verify steady-state error < 0.05 m/s at 4 m/s", "done": False},
                {"item": "Save PID parameters to config.json", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="C-05", name="Vibrating Feeder Frequency Calibration",
            description="Calibrate vibrating feeder amplitude vs PWM for each channel.",
            phase="Phase 5: Calibration", duration_hours=1.5,
            dependencies=["M-04"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Sweep PWM 50-200, record BPM for each channel", "done": False},
                {"item": "Verify CH1 @ 50 bpm: PWM ≈ 167", "done": False},
                {"item": "Verify CH2 @ 50 bpm: PWM ≈ 167 ± 5", "done": False},
                {"item": "Verify CH3 @ 50 bpm: PWM ≈ 167 ± 5", "done": False},
                {"item": "Verify CV between channels < 5%", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="C-06", name="Full System POST Test",
            description="Run power-on self-test for complete system verification.",
            phase="Phase 5: Calibration", duration_hours=1.5,
            dependencies=["C-01", "C-02", "C-03", "C-04", "C-05"], owner="Team",
            risk_level=RiskLevel.MEDIUM,
        ))

        # Phase 6: Integration & Qualification (Day 8-10)
        self.tasks.append(Task(
            id="I-01", name="End-to-End Bean Test (No Defects)",
            description="Run 100% normal beans through system, verify throughput ≥ 1.5kg/h.",
            phase="Phase 6: Integration & Qualification", duration_hours=2.0,
            dependencies=["C-06"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Load 500g normal (defect-free) green beans", "done": False},
                {"item": "Verify throughput ≥ 1.5 kg/h (short-term)", "done": False},
                {"item": "Verify all 3 channels operational", "done": False},
                {"item": "Verify database records written for each bean", "done": False},
                {"item": "Verify no false rejects (all → Grade A)", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="I-02", name="Defect Detection Rate Test",
            description="Test system with known defective beans, verify detection rates.",
            phase="Phase 6: Integration & Qualification", duration_hours=3.0,
            dependencies=["I-01"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Prepare 100 defective beans (20 each type)", "done": False},
                {"item": "Mix with 400 normal beans (20% defect rate)", "done": False},
                {"item": "Run batch, collect reject stream", "done": False},
                {"item": "Manual inspection of reject stream", "done": False},
                {"item": "Verify overall defect recall ≥ 80%", "done": False},
                {"item": "Verify false positive rate < 10%", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="I-03", name="Long-Duration Reliability Run (8 hours)",
            description="Continuous 8-hour run to verify mechanical and thermal stability.",
            phase="Phase 6: Integration & Qualification", duration_hours=9.0,
            dependencies=["I-02"], owner="Team", risk_level=RiskLevel.HIGH,
            checklist=[
                {"item": "Load 5kg of mixed beans", "done": False},
                {"item": "Hour 4: Thermal check (all components < 60°C)", "done": False},
                {"item": "Hour 5-6: Verify OEE remains stable", "done": False},
                {"item": "Hour 8: Final mass balance (input vs output vs reject)", "done": False},
                {"item": "Calculate actual 8h throughput and OEE", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="I-04", name="Safety Systems Qualification",
            description="Verify all safety systems function correctly under test conditions.",
            phase="Phase 6: Integration & Qualification", duration_hours=1.5,
            dependencies=["I-01"], owner="Team", risk_level=RiskLevel.CRITICAL,
            checklist=[
                {"item": "Test E-STOP: all actuators de-energize < 50ms", "done": False},
                {"item": "Test E-STOP reset procedure", "done": False},
                {"item": "Verify air pressure fail-safe (compressor off → valves close)", "done": False},
                {"item": "Verify ESP32 watchdog reset on communication loss", "done": False},
                {"item": "Verify HX711 overload detection (500g sudden load)", "done": False},
            ],
        ))

        # Phase 7: Production Handoff (Day 10-11)
        self.tasks.append(Task(
            id="P-01", name="Production Recipe Setup",
            description="Configure production parameters: bean type, target grade, batch size.",
            phase="Phase 7: Production Handoff", duration_hours=1.0,
            dependencies=["I-03"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Configure green coffee origin and variety", "done": False},
                {"item": "Set target grade A threshold (defect rate < 2%)", "done": False},
                {"item": "Set batch size (2.0 kg per烘豆机 batch)", "done": False},
                {"item": "Configure MQTT topic for烘豆er integration", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="P-02", name="Documentation Handoff",
            description="Deliver all documentation packages to operations team.",
            phase="Phase 7: Production Handoff", duration_hours=2.0,
            dependencies=["I-03"], owner="Team", risk_level=RiskLevel.LOW,
            checklist=[
                {"item": "Deliver OPERATOR_MANUAL.md to ops team", "done": False},
                {"item": "Deliver WIRING_GUIDE.md to maintenance team", "done": False},
                {"item": "Deliver DEBUGGING_GUIDE.md to maintenance team", "done": False},
                {"item": "Deliver all calibration certificates", "done": False},
                {"item": "Ops team sign-off on documentation", "done": False},
            ],
        ))
        self.tasks.append(Task(
            id="P-03", name="Final Production Acceptance Test",
            description="Official production acceptance test witnessed by operations team.",
            phase="Phase 7: Production Handoff", duration_hours=3.0,
            dependencies=["P-01", "P-02"], owner="Team", risk_level=RiskLevel.MEDIUM,
            checklist=[
                {"item": "Load real production beans (10kg)", "done": False},
                {"item": "Run 1-hour continuous production test", "done": False},
                {"item": "Compare manual readings vs system readings", "done": False},
                {"item": "Calculate OEE, throughput, defect rate", "done": False},
                {"item": "All parties sign acceptance certificate", "done": False},
            ],
        ))

    def _build_milestones(self):
        hw = self.HARDWARE_DELIVERY_ESTIMATE
        self.milestones = [
            Milestone(
                id="MS-01", name="Hardware Accepted",
                description="All hardware received and passed incoming inspection.",
                milestone_type=MilestoneType.HARDWARE,
                target_date=self._add_days(hw, 1),
                task_ids=["H-01", "H-02", "H-03"],
                criteria=["All components verified against BOM", "Serial numbers registered", "No electrical safety failures"],
            ),
            Milestone(
                id="MS-02", name="Mechanical Assembly Complete",
                description="All mechanical components installed and verified.",
                milestone_type=MilestoneType.ASSEMBLY,
                target_date=self._add_days(hw, 4),
                task_ids=["M-01", "M-02", "M-03", "M-04", "M-05", "M-06"],
                criteria=["Frame squared and mounted", "All 3D prints installed", "Air system leak-free at 6 bar"],
            ),
            Milestone(
                id="MS-03", name="Electrical Wiring Complete",
                description="All electrical wiring finished and safety verified.",
                milestone_type=MilestoneType.ASSEMBLY,
                target_date=self._add_days(hw, 5),
                task_ids=["E-01", "E-02", "E-03", "E-04"],
                criteria=["Hi-pot test passed", "E-STOP verified", "GPIO continuity confirmed"],
            ),
            Milestone(
                id="MS-04", name="Software Stack Deployed",
                description="Pi OS, ESP32 firmware, ML models, and MQTT broker all operational.",
                milestone_type=MilestoneType.CALIBRATION,
                target_date=self._add_days(hw, 6),
                task_ids=["S-01", "S-02", "S-03", "S-04"],
                criteria=["ESP32 responds to STATUS command", "MQTT broker running", "TFLite model loads < 2s"],
            ),
            Milestone(
                id="MS-05", name="All Sensors Calibrated",
                description="All 6 sensors (3×HX711, 3×AD7746, 2×camera) calibrated and certified.",
                milestone_type=MilestoneType.CALIBRATION,
                target_date=self._add_days(hw, 8),
                task_ids=["C-01", "C-02", "C-03", "C-04", "C-05", "C-06"],
                criteria=["HX711 error < 0.05g at 100g", "AD7746 error < 0.5% abs moisture", "PID steady-state error < 0.05 m/s"],
            ),
            Milestone(
                id="MS-06", name="System Qualification Passed",
                description="Defect detection, throughput, and safety qualification tests passed.",
                milestone_type=MilestoneType.QUALIFICATION,
                target_date=self._add_days(hw, 10),
                task_ids=["I-01", "I-02", "I-03", "I-04"],
                criteria=["Defect recall ≥ 80%", "Throughput ≥ 2.0 kg/h", "E-STOP response < 50ms", "8h thermal stable"],
            ),
            Milestone(
                id="MS-07", name="Production Ready",
                description="System handed over to production team, acceptance signed.",
                milestone_type=MilestoneType.PRODUCTION,
                target_date=self._add_days(hw, 11),
                task_ids=["P-01", "P-02", "P-03"],
                criteria=["1h production run successful", "All docs delivered", "Acceptance certificate signed"],
            ),
        ]

    def _build_risks(self):
        self.risks = [
            RiskItem(
                id="R-01", description="HQ Camera delivery delay beyond 60 days",
                category="Supply Chain", likelihood=RiskLevel.HIGH, impact=RiskLevel.HIGH,
                mitigation="Order immediately; use USB camera as temporary fallback",
                contingency="Use Logitech C270 USB camera for initial calibration (color resolution will be lower)",
                owner="采购",
            ),
            RiskItem(
                id="R-02", description="AD7746 cable effect causes calibration failure",
                category="Technical", likelihood=RiskLevel.MEDIUM, impact=RiskLevel.MEDIUM,
                mitigation="Use PIM direct-connect probe wiring (< 5cm), no cable extensions",
                contingency="Design custom PCB with AD7746 mounted directly at probe",
                owner="硬件",
            ),
            RiskItem(
                id="R-03", description="Nema17 motor resonance causes missed steps at 50+ bpm",
                category="Mechanical", likelihood=RiskLevel.MEDIUM, impact=RiskLevel.MEDIUM,
                mitigation="Perform resonance tuning per vibrating_feeder_resonance_analysis.py; add rubber mounts",
                contingency="Reduce to 40 bpm per channel (still gives 1.8 kg/h with 3 channels)",
                owner="机械",
            ),
            RiskItem(
                id="R-04", description="GPIO wiring error causes Pi 4 damage on first power-on",
                category="Electrical", likelihood=RiskLevel.MEDIUM, impact=RiskLevel.CRITICAL,
                mitigation="Perform E-04 electrical inspection before Pi power; use isolation resistors on GPIO",
                contingency="Keep spare Pi 4 in inventory (ordered in Phase 1)",
                owner="电气",
            ),
            RiskItem(
                id="R-05", description="TFLite model not trained before commissioning (no real data)",
                category="ML", likelihood=RiskLevel.HIGH, impact=RiskLevel.MEDIUM,
                mitigation="Collect training data during first 2 weeks of operation; use synthetic baseline for initial tests",
                contingency="Use rule-based threshold fallback (L*a*b* color + weight ranges) for initial production",
                owner="ML",
            ),
            RiskItem(
                id="R-06", description="Pi 4 thermal throttling during 8h run (summer ambient > 35°C)",
                category="Thermal", likelihood=RiskLevel.LOW, impact=RiskLevel.MEDIUM,
                mitigation="Install 6020 turbo fan per thermal_management_analysis.py; monitor CPU temp during I-03",
                contingency="Add small 40mm fan to Pi chassis; reduce ambient via enclosure placement",
                owner="硬件",
            ),
            RiskItem(
                id="R-07", description="MQTT broker security misconfiguration exposes system to LAN",
                category="Security", likelihood=RiskLevel.LOW, impact=RiskLevel.MEDIUM,
                mitigation="ACL restrict to sorter/* topics; disable anonymous; firewall on Pi LAN interface",
                contingency="Disconnect from LAN, operate in standalone mode with local dashboard only",
                owner="软件",
            ),
            RiskItem(
                id="R-08", description="ESP32 watchdog causes unexpected resets during production run",
                category="Firmware", likelihood=RiskLevel.MEDIUM, impact=RiskLevel.MEDIUM,
                mitigation="Verify watchdog timeout settings; log all reset events during I-03",
                contingency="Extend watchdog timeout to 10s if spurious resets occur; update firmware v1.1",
                owner="固件",
            ),
        ]

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _state_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, self.state_file)

    def save(self):
        path = self._state_path()
        data = {
            "version": "1.0",
            "saved_at": datetime.now().isoformat(),
            "tasks": [t.to_dict() for t in self.tasks],
            "milestones": [m.to_dict() for m in self.milestones],
            "risks": [r.to_dict() for r in self.risks],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[Tracker] State saved: {path}")

    def _load(self):
        path = self._state_path()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            task_map = {t["id"]: Task.from_dict(t) for t in data.get("tasks", [])}
            # Restore tasks from saved state (preserve in-memory task list if newer)
            if task_map:
                for t in self.tasks:
                    if t.id in task_map:
                        saved = task_map[t.id]
                        t.status = saved.status
                        t.started_at = saved.started_at
                        t.completed_at = saved.completed_at
                        t.notes = saved.notes
                        t.checklist = saved.checklist
                        t.blockers = saved.blockers
            print(f"[Tracker] State loaded from {path}")
        except Exception as e:
            print(f"[Tracker] Warning: Could not load state: {e}")

    # ─── Operations ──────────────────────────────────────────────────────────

    def start_task(self, task_id: str) -> bool:
        for t in self.tasks:
            if t.id == task_id:
                # Check dependencies
                blocked = [d for d in t.dependencies if self._task_status(d) != PhaseStatus.COMPLETED]
                if blocked:
                    t.status = PhaseStatus.BLOCKED
                    t.blockers = blocked
                    print(f"[Tracker] Task {task_id} blocked by: {blocked}")
                    return False
                t.status = PhaseStatus.IN_PROGRESS
                t.started_at = datetime.now().isoformat()
                print(f"[Tracker] Started: {task_id} - {t.name}")
                return True
        print(f"[Tracker] Task not found: {task_id}")
        return False

    def complete_task(self, task_id: str, notes: str = ""):
        for t in self.tasks:
            if t.id == task_id:
                t.status = PhaseStatus.COMPLETED
                t.completed_at = datetime.now().isoformat()
                if notes:
                    t.notes.append(notes)
                # Unblock dependent tasks
                for dep_t in self.tasks:
                    if task_id in dep_t.dependencies and dep_t.status == PhaseStatus.BLOCKED:
                        dep_t.blockers = [d for d in dep_t.dependencies if self._task_status(d) != PhaseStatus.COMPLETED]
                        if not dep_t.blockers:
                            dep_t.status = PhaseStatus.PENDING
                            print(f"[Tracker] Task {dep_t.id} unblocked")
                print(f"[Tracker] Completed: {task_id}")
                return
        print(f"[Tracker] Task not found: {task_id}")

    def update_checklist(self, task_id: str, item_index: int, done: bool, notes: str = ""):
        for t in self.tasks:
            if t.id == task_id:
                if 0 <= item_index < len(t.checklist):
                    t.checklist[item_index]["done"] = done
                    if notes:
                        t.checklist[item_index]["notes"] = notes
                return

    def _task_status(self, task_id: str) -> PhaseStatus:
        for t in self.tasks:
            if t.id == task_id:
                return t.status
        return PhaseStatus.PENDING

    def complete_milestone(self, milestone_id: str, signoff_by: str = ""):
        for m in self.milestones:
            if m.id == milestone_id:
                m.status = PhaseStatus.COMPLETED
                m.actual_date = datetime.now().strftime("%Y-%m-%d")
                m.signoff_by = signoff_by
                print(f"[Tracker] Milestone completed: {m.id} - {m.name}")
                return

    # ─── ASCII Report ─────────────────────────────────────────────────────────

    def generate_report(self) -> str:
        lines = []
        W = 120

        def hr(width=W):
            return "─" * width

        def section(title: str) -> str:
            return f"\n{'='*W}\n  {title}\n{'='*W}"

        def phase_header(phase: str) -> str:
            return f"\n{'─'*W}\n  ▶ {phase}\n{'─'*W}"

        # Header
        lines.append(f"""
╔{'═'*W}╗
║  HUSKY-SORTER-001  —  Commissioning Project Tracker  ║
║  Hardware Delivery: {self.HARDWARE_DELIVERY_ESTIMATE}   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}        ║
╚{'═'*W}╝""")

        # ── Executive Summary ──
        total_tasks = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status == PhaseStatus.COMPLETED)
        in_progress = sum(1 for t in self.tasks if t.status == PhaseStatus.IN_PROGRESS)
        blocked = sum(1 for t in self.tasks if t.status == PhaseStatus.BLOCKED)
        pending = sum(1 for t in self.tasks if t.status == PhaseStatus.PENDING)

        overall_pct = completed / total_tasks * 100 if total_tasks else 0

        status_icon = {
            "COMPLETED": "✅",
            "IN_PROGRESS": "🔵",
            "BLOCKED": "🚫",
            "PENDING": "⚪",
            "SKIPPED": "⏭️ ",
        }

        lines.append(section("EXECUTIVE SUMMARY"))
        lines.append(f"  Total Tasks : {total_tasks}")
        lines.append(f"  Completed   : {completed} ✅")
        lines.append(f"  In Progress : {in_progress} 🔵")
        lines.append(f"  Blocked     : {blocked} 🚫")
        lines.append(f"  Pending     : {pending} ⚪")
        lines.append(f"  Overall     : {overall_pct:.1f}%")
        lines.append("")

        # ── Phase Progress ──
        phases = sorted(set(t.phase for t in self.tasks))
        for phase in phases:
            phase_tasks = [t for t in self.tasks if t.phase == phase]
            p_done = sum(1 for t in phase_tasks if t.status == PhaseStatus.COMPLETED)
            p_total = len(phase_tasks)
            p_pct = p_done / p_total * 100 if p_total else 0
            bar_len = 30
            filled = int(bar_len * p_pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            lines.append(f"  [{bar}] {p_pct:5.1f}%  {phase}")

        # ── Critical Path / Blocked Tasks ──
        if blocked > 0:
            lines.append(section("⚠️  BLOCKED TASKS"))
            for t in self.tasks:
                if t.status == PhaseStatus.BLOCKED:
                    lines.append(f"  🚫 {t.id} {t.name}")
                    lines.append(f"     Blocked by: {', '.join(t.blockers)}")

        # ── Milestone Status ──
        lines.append(section("📍 MILESTONES"))
        for m in self.milestones:
            icon = status_icon.get(m.status.value.upper(), "⚪")
            lines.append(f"  {icon} [{m.id}] {m.name}")
            lines.append(f"      Target: {m.target_date} | Actual: {m.actual_date or '—'}")
            lines.append(f"      Type: {m.milestone_type.value} | Signoff: {m.signoff_by or '—'}")
            if m.criteria:
                lines.append(f"      Criteria:")
                for c in m.criteria:
                    lines.append(f"        • {c}")

        # ── Risk Register ──
        lines.append(section("⚠️  RISK REGISTER"))
        # Sort by RPN descending
        sorted_risks = sorted(self.risks, key=lambda r: -r.rpn())
        for r in sorted_risks:
            lik_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(r.likelihood.value, "⚪")
            lines.append(f"  [{r.id}] {lik_icon} L={r.likelihood.value.upper()[0]} I={r.impact.value.upper()[0]} RPN={r.rpn()}  {r.description}")
            lines.append(f"      Mitigation: {r.mitigation}")
            lines.append(f"      Contingency: {r.contingency}")
            lines.append(f"      Owner: {r.owner} | Status: {r.status}")

        # ── Task Detail by Phase ──
        lines.append(section("📋 TASK DETAIL"))
        for phase in phases:
            phase_tasks = [t for t in self.tasks if t.phase == phase]
            lines.append(phase_header(phase))

            # Phase stats
            pt_done = sum(1 for t in phase_tasks if t.status == PhaseStatus.COMPLETED)
            pt_total = len(phase_tasks)
            pt_hrs = sum(t.duration_hours for t in phase_tasks)
            pt_done_hrs = sum(t.duration_hours for t in phase_tasks if t.status == PhaseStatus.COMPLETED)
            lines.append(f"  {pt_done}/{pt_total} tasks | {pt_done_hrs:.1f}/{pt_hrs:.1f} hours")

            for t in phase_tasks:
                icon = status_icon.get(t.status.value.upper(), "⚪")
                risk_indicator = {"low": "", "medium": "⚠️", "high": "🔶", "critical": "🔴"}.get(t.risk_level.value, "")
                pct = t.completion_pct()
                pct_str = f"[{pct:5.1f}%]"
                lines.append(f"\n  {icon} {pct_str} {t.id} {t.name} {risk_indicator}")
                if t.dependencies:
                    lines.append(f"      Depends: {', '.join(t.dependencies)}")
                if t.checklist:
                    for i, c in enumerate(t.checklist):
                        chk = "☑" if c.get("done") else "☐"
                        lines.append(f"      {chk} {c['item']}")
                if t.status == PhaseStatus.IN_PROGRESS and t.notes:
                    for n in t.notes[-2:]:
                        lines.append(f"      📝 {n}")

        # ── Timeline ──
        lines.append(section("📅 COMMISSIONING TIMELINE"))
        hw = datetime.strptime(self.HARDWARE_DELIVERY_ESTIMATE, "%Y-%m-%d")
        lines.append(f"  {'Date':<12} {'Phase':<40} {'Key Tasks'}")
        lines.append(hr())
        for i in range(13):
            day = hw + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            day_label = f"Day {i}" if i > 0 else "HW Arrives"
            phase_map = {
                0: ("Phase 1", "H-01 H-02 H-03"),
                2: ("Phase 2", "M-01 M-02 M-03"),
                4: ("Phase 3", "E-01 E-02 E-03 E-04"),
                5: ("Phase 4", "S-01 S-02 S-03 S-04"),
                6: ("Phase 5", "C-01 C-02 C-03"),
                8: ("Phase 6", "I-01 I-02 I-03 I-04"),
                10: ("Phase 7", "P-01 P-02 P-03"),
            }
            if i in phase_map:
                phase_name, tasks_str = phase_map[i]
                milestone_map = {1: "MS-01", 4: "MS-02", 5: "MS-03", 6: "MS-04", 8: "MS-05", 10: "MS-06", 11: "MS-07"}
                ms = f" → {milestone_map.get(i, '')}" if i in milestone_map else ""
                lines.append(f"  {day_str:<12} [{phase_name:<12}] {tasks_str}{ms}")
            elif i == 11:
                lines.append(f"  {day_str:<12} [PRODUCTION ] 🎉 PRODUCTION READY (MS-07)")
            elif i == 12:
                lines.append(f"  {day_str:<12} [POST-INSTALL] Documentation归档 + 备件入库")

        return "\n".join(lines)

    def generate_json_report(self) -> dict:
        completed = sum(1 for t in self.tasks if t.status == PhaseStatus.COMPLETED)
        in_progress = sum(1 for t in self.tasks if t.status == PhaseStatus.IN_PROGRESS)
        blocked = sum(1 for t in self.tasks if t.status == PhaseStatus.BLOCKED)

        phase_summary = {}
        for phase in sorted(set(t.phase for t in self.tasks)):
            phase_tasks = [t for t in self.tasks if t.phase == phase]
            phase_summary[phase] = {
                "total": len(phase_tasks),
                "completed": sum(1 for t in phase_tasks if t.status == PhaseStatus.COMPLETED),
                "in_progress": sum(1 for t in phase_tasks if t.status == PhaseStatus.IN_PROGRESS),
                "blocked": sum(1 for t in phase_tasks if t.status == PhaseStatus.BLOCKED),
                "pending": sum(1 for t in phase_tasks if t.status == PhaseStatus.PENDING),
                "hours_total": sum(t.duration_hours for t in phase_tasks),
                "hours_completed": sum(t.duration_hours for t in phase_tasks if t.status == PhaseStatus.COMPLETED),
            }

        return {
            "project": self.PROJECT_NAME,
            "tracker_version": "1.0",
            "report_generated": datetime.now().isoformat(),
            "hardware_delivery_estimate": self.HARDWARE_DELIVERY_ESTIMATE,
            "overall_progress": {
                "total_tasks": len(self.tasks),
                "completed": completed,
                "in_progress": in_progress,
                "blocked": blocked,
                "pending": len(self.tasks) - completed - in_progress - blocked,
                "completion_pct": round(completed / len(self.tasks) * 100, 1) if self.tasks else 0,
            },
            "phase_summary": phase_summary,
            "milestones": [m.to_dict() for m in self.milestones],
            "risks": [r.to_dict() for r in self.risks],
            "tasks": [t.to_dict() for t in self.tasks],
        }


# ─── CLI Interface ───────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 Commissioning Tracker")
    parser.add_argument("--report", action="store_true", help="Generate full ASCII report")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--start", metavar="TASK_ID", help="Start a task")
    parser.add_argument("--complete", metavar="TASK_ID", help="Mark task complete")
    parser.add_argument("--check", metavar="TASK_ID", help="Show task checklist")
    parser.add_argument("--save", action="store_true", help="Save current state")
    parser.add_argument("--milestone", metavar="MS_ID", help="Complete a milestone")
    parser.add_argument("--state-file", default="commissioning_state.json", help="State file path")
    args = parser.parse_args()

    tracker = CommissioningTracker(state_file=args.state_file)

    if args.start:
        tracker.start_task(args.start)
        tracker.save()

    elif args.complete:
        tracker.complete_task(args.complete)
        tracker.save()

    elif args.check:
        for t in tracker.tasks:
            if t.id == args.check:
                print(f"\n=== {t.id}: {t.name} ===")
                print(f"Status: {t.status.value} | Completion: {t.completion_pct()}%")
                print(f"Phase: {t.phase} | Duration: {t.duration_hours}h")
                if t.dependencies:
                    print(f"Depends: {', '.join(t.dependencies)}")
                print("\nChecklist:")
                for i, c in enumerate(t.checklist):
                    chk = "☑" if c.get("done") else "☐"
                    print(f"  [{i:02d}] {chk} {c['item']}")
                if t.notes:
                    print("\nNotes:")
                    for n in t.notes:
                        print(f"  • {n}")
                return
        print(f"Task not found: {args.check}")

    elif args.milestone:
        tracker.complete_milestone(args.milestone)
        tracker.save()

    elif args.json:
        import json
        print(json.dumps(tracker.generate_json_report(), indent=2))

    elif args.report:
        print(tracker.generate_report())

    else:
        # Default: show summary
        print(tracker.generate_report())


if __name__ == "__main__":
    main()
