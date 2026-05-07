#!/usr/bin/env python3
"""
Operator Training Simulator — HUSKY-SORTER-001
================================================
Interactive training environment using the Digital Twin physics engine.
Trains operators on: normal operation / defect recognition / fault handling.

Run:
    python sorter/simulation/operator_training_simulator.py
    python sorter/simulation/operator_training_simulator.py --scenario quick --benchmark

Scenarios:
    quick        — 5-minute intro (50 beans, 3 defects)
    standard     — 20-minute full certification (200 beans, 8 defects)
    advanced     — 45-minute expert (500 beans, all 14 defects)
    stress_test  — Fault injection training (ESTOP, FAULT states)

Author: Little Husky (他他) 🐕
Project: HUSKY-SORTER-001
Date: 2026-05-07
"""

import time
import random
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum, auto

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

BEAN_MASS_G = 0.15  # grams per bean


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class MachineState(Enum):
    IDLE = auto(); INITIALIZING = auto(); CALIBRATING = auto()
    READY = auto(); RUNNING = auto(); PAUSED = auto(); FAULT = auto(); ESTOP = auto()


class BeanDefect(Enum):
    NONE = "none"
    MOLDY = "moldy"; FERMENTED = "fermented"; BLACK = "black"; BROKEN = "broken"
    IMMATURE = "immature"; INSECT_DAMAGED = "insect_damaged"; EMPTY = "empty"
    OVERDRIED = "overdried"; UNDERDRIED = "underdried"


# ──────────────────────────────────────────────────────────────────────────────
# Sensor Simulation
# ──────────────────────────────────────────────────────────────────────────────

DEFECT_COLOR_RANGES = {
    BeanDefect.NONE:          {"L": (38, 58),  "a": (-2, 6),   "b": (6, 24)},
    BeanDefect.MOLDY:         {"L": (22, 36),  "a": (4, 14),   "b": (10, 28)},
    BeanDefect.FERMENTED:     {"L": (24, 40),  "a": (8, 20),   "b": (12, 30)},
    BeanDefect.BLACK:         {"L": (8,  20),  "a": (0, 8),    "b": (0, 10)},
    BeanDefect.BROKEN:        {"L": (32, 52),  "a": (-1, 7),   "b": (5, 22)},
    BeanDefect.IMMATURE:      {"L": (44, 62),  "a": (-4, 4),   "b": (8, 20)},
    BeanDefect.INSECT_DAMAGED:{"L": (28, 46),  "a": (2, 12),   "b": (8, 24)},
    BeanDefect.EMPTY:         {"L": (56, 72),  "a": (-2, 4),   "b": (4, 16)},
    BeanDefect.OVERDRIED:     {"L": (32, 48),  "a": (0, 8),    "b": (8, 20)},
    BeanDefect.UNDERDRIED:    {"L": (50, 64),  "a": (-2, 6),   "b": (10, 26)},
}


def lab_reading(defect: BeanDefect, camera: str = "top") -> Tuple[float, float, float]:
    """Simulate realistic L*a*b* sensor reading with IMX477 noise."""
    sig = DEFECT_COLOR_RANGES.get(defect, DEFECT_COLOR_RANGES[BeanDefect.NONE])
    sigma_L = 2.0 if camera == "top" else 3.0
    sigma_ab = 1.5 if camera == "top" else 2.0
    L = random.uniform(*sig["L"]) + random.gauss(0, sigma_L)
    a = random.uniform(*sig["a"]) + random.gauss(0, sigma_ab)
    b = random.uniform(*sig["b"]) + random.gauss(0, sigma_ab)
    return L, a, b


# ──────────────────────────────────────────────────────────────────────────────
# Production Sort Decision Algorithm
# ──────────────────────────────────────────────────────────────────────────────

COLOR_T = {"L_min": 22, "L_max": 62, "a_max": 18, "b_max": 30,
           "moldy_L_max": 36, "black_L_max": 20, "fermented_a_min": 8}
WEIGHT_T = {"min_normal": 140, "max_normal": 220, "empty_max": 30}
MOISTURE_T = {"target": 4.5, "min": 3.0, "max": 7.0}


def sort_decision(L: float, a: float, b: float, weight_mg: float,
                  moisture_pf: Optional[float] = None) -> Tuple[str, List[str]]:
    reasons, reject = [], False
    if L < COLOR_T["L_min"]: reject = True; reasons.append(f"L*={L:.1f}<min")
    if L > COLOR_T["L_max"]: reject = True; reasons.append(f"L*={L:.1f}>max")
    if a > COLOR_T["a_max"]: reject = True; reasons.append(f"a*={a:.1f}>max")
    if b > COLOR_T["b_max"]: reject = True; reasons.append(f"b*={b:.1f}>max")
    if L < COLOR_T["moldy_L_max"] and a > 4: reject = True; reasons.append("moldy")
    if L < COLOR_T["black_L_max"]: reject = True; reasons.append("black")
    if a > COLOR_T["fermented_a_min"] and b > 12: reject = True; reasons.append("fermented")
    if weight_mg < WEIGHT_T["empty_max"]: reject = True; reasons.append("empty")
    elif weight_mg < WEIGHT_T["min_normal"]: reject = True; reasons.append("underweight")
    if moisture_pf is not None:
        if moisture_pf < MOISTURE_T["min"]: reject = True; reasons.append(f"dry")
        elif moisture_pf > MOISTURE_T["max"]: reject = True; reasons.append(f"wet")
    if reject: return "REJECT", reasons
    if weight_mg > WEIGHT_T["max_normal"]: return "C", reasons
    if L > 50 and 0 <= a <= 4 and 8 <= b <= 20: return "A", reasons
    return "B", reasons


# ──────────────────────────────────────────────────────────────────────────────
# Bean Simulator
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SimBean:
    bean_id: int; defect: BeanDefect; mass_mg: float
    L_top: float; a_top: float; b_top: float
    L_bot: float; a_bot: float; b_bot: float; moisture_pf: float
    expected_grade: str = "REJECT"; actual_grade: str = "REJECT"
    reasons: List[str] = field(default_factory=list)
    correct_decision: bool = False; channel: int = 1


class BeanSimulator:
    DEFECT_WEIGHTS = {
        BeanDefect.NONE: (170, 15), BeanDefect.MOLDY: (160, 12),
        BeanDefect.FERMENTED: (155, 14), BeanDefect.BLACK: (130, 20),
        BeanDefect.BROKEN: (90, 10), BeanDefect.IMMATURE: (120, 12),
        BeanDefect.INSECT_DAMAGED: (145, 15), BeanDefect.EMPTY: (18, 5),
        BeanDefect.OVERDRIED: (140, 10), BeanDefect.UNDERDRIED: (185, 15),
    }

    def __init__(self, defect_probability: float = 0.08, seed: int = None):
        self.defect_probability = defect_probability
        if seed is not None: random.seed(seed)

    def generate(self, bean_id: int, channel: int = 1) -> SimBean:
        defect = BeanDefect.NONE if random.random() >= self.defect_probability \
                 else random.choice(list(BeanDefect)[1:])
        base_mass, mass_std = self.DEFECT_WEIGHTS[defect]
        mass_mg = max(5, random.gauss(base_mass, mass_std))
        L_top, a_top, b_top = lab_reading(defect, "top")
        L_bot, a_bot, b_bot = lab_reading(defect, "bottom")
        if defect == BeanDefect.EMPTY: moisture_pf = random.uniform(0.5, 1.5)
        elif defect == BeanDefect.UNDERDRIED: moisture_pf = random.uniform(6.0, 8.0)
        elif defect == BeanDefect.OVERDRIED: moisture_pf = random.uniform(1.5, 3.0)
        else: moisture_pf = random.gauss(MOISTURE_T["target"], 0.4)

        bean = SimBean(bean_id=bean_id, defect=defect, mass_mg=mass_mg,
                       L_top=L_top, a_top=a_top, b_top=b_top,
                       L_bot=L_bot, a_bot=a_bot, b_bot=b_bot, moisture_pf=moisture_pf, channel=channel)
        bean.actual_grade, bean.reasons = sort_decision(L_top, a_top, b_top, mass_mg, moisture_pf)
        bean.expected_grade = ("A" if defect == BeanDefect.NONE and 50 < L_top < 58
                                and 0 <= a_top <= 4 and 8 <= b_top <= 20
                                else "B" if defect == BeanDefect.NONE else "REJECT")
        # Simulate algorithm error (~5% misclassification)
        bean.correct_decision = (random.random() >= 0.05)
        return bean


# ──────────────────────────────────────────────────────────────────────────────
# Scenario Definitions
# ──────────────────────────────────────────────────────────────────────────────

SCENARIOS = {
    "quick": {
        "name": "Quick Introduction",
        "description": "5-minute intro — learn the dashboard basics",
        "total_beans": 50, "channels": 1, "bpm": 30,
        "defect_probability": 0.05, "max_time_minutes": 5,
        "pass_threshold": 0.75,
        "focus_skills": ["dashboard_reading", "basic_monitoring"],
        "incident_probability": 0.0,
    },
    "standard": {
        "name": "Standard Operator Certification",
        "description": "20-minute full certification — monitor + respond to defects",
        "total_beans": 200, "channels": 1, "bpm": 50,
        "defect_probability": 0.10, "max_time_minutes": 20,
        "pass_threshold": 0.85,
        "focus_skills": ["defect_recognition", "sorting_accuracy", "throughput_monitoring"],
        "incident_probability": 0.05,
    },
    "advanced": {
        "name": "Advanced Operations",
        "description": "45-minute expert — all defects + fault handling",
        "total_beans": 500, "channels": 3, "bpm": 50,
        "defect_probability": 0.15, "max_time_minutes": 45,
        "pass_threshold": 0.90,
        "focus_skills": ["all_defects", "fault_handling", "multi_channel", "efficiency"],
        "incident_probability": 0.10,
    },
    "stress_test": {
        "name": "Emergency Response Training",
        "description": "Fault injection — ESTOP, FAULT states, recovery procedures",
        "total_beans": 100, "channels": 1, "bpm": 50,
        "defect_probability": 0.20, "max_time_minutes": 30,
        "pass_threshold": 0.80,
        "focus_skills": ["emergency_response", "fault_diagnosis", "recovery_procedure"],
        "incident_probability": 0.50,
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Incident Definitions
# ──────────────────────────────────────────────────────────────────────────────

INCIDENTS = [
    ("sensor_offset",  "Color sensor drift — L* values trending high. Recalibration required."),
    ("weight_drift",   "Weight sensor zero drift — readings consistently +8mg high."),
    ("feed_jam",       "Feed jam at channel 1 — beans not advancing. Check hopper level."),
    ("e_stop_test",    "E-STOP test — press ESTOP button NOW to acknowledge."),
    ("pressure_low",   "Air pressure below 4.5 bar — check compressor connections."),
    ("camera_blur",    "Bottom camera image quality degraded — lens cleaning needed."),
    ("motor_overheat", "Feeder motor temperature 78C — above 75C safety threshold."),
    ("i2c_error",      "I2C error: AD7746 moisture sensor not responding. Retrying..."),
]


# ──────────────────────────────────────────────────────────────────────────────
# Training Session
# ──────────────────────────────────────────────────────────────────────────────

class TrainingSession:
    COMMANDS = ["start", "stop", "pause", "resume", "status", "batch",
                "beans", "estop", "reset", "score", "help", "quit"]

    def __init__(self, scenario: str = "standard"):
        if scenario not in SCENARIOS:
            print(f"[ERROR] Unknown scenario: {scenario}")
            print(f"Available: {list(SCENARIOS.keys())}")
            sys.exit(1)
        self.scenario = scenario
        self.config = SCENARIOS[scenario]
        self.simulator = BeanSimulator(self.config["defect_probability"], seed=None)
        self.state = MachineState.IDLE
        self.beans: List[SimBean] = []
        self.beans_processed = 0
        self.start_time: Optional[float] = None
        self.elapsed_seconds = 0.0
        self.pause_duration = 0.0
        self.paused_at: Optional[float] = None
        self.stats = {"total": 0, "grade_A": 0, "grade_B": 0, "grade_C": 0, "rejected": 0,
                      "correct": 0, "incorrect": 0, "defects_in_sample": 0,
                      "false_positives": 0, "false_negatives": 0,
                      "commands_issued": 0, "estop_count": 0,
                      "incidents_injected": 0, "incidents_acknowledged": 0}
        self.incident_history: List[dict] = []
        self._bean_counter = 0
        self._next_incident_at = float('inf')
        self._benchmark_done = False
        self._real_elapsed_s = 0.0  # for accurate throughput calc in benchmark mode

    def _fmt_time(self) -> str:
        m, s = divmod(int(self.elapsed_seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _record_elapsed(self):
        if self.start_time and self.paused_at is None:
            self.elapsed_seconds = time.time() - self.start_time - self.pause_duration

    def _calc_throughput(self) -> float:
        h = max(self.elapsed_seconds, 1) / 3600.0
        return (self.stats["total"] * BEAN_MASS_G / 1000) / max(h, 0.001)

    def _generate_beans_up_to(self, count: int):
        while self._bean_counter < count:
            self._bean_counter += 1
            channel = (self._bean_counter % self.config["channels"]) + 1
            self.beans.append(self.simulator.generate(self._bean_counter, channel))

    def _process_beans(self, delta_s: float):
        if self.state != MachineState.RUNNING:
            return
        beans_per_s = self.config["bpm"] * self.config["channels"] / 60.0
        new_beans = int(beans_per_s * delta_s)
        self._generate_beans_up_to(self.beans_processed + new_beans)
        for _ in range(new_beans):
            if self.beans_processed >= len(self.beans): break
            bean = self.beans[self.beans_processed]
            self.beans_processed += 1
            self.stats["total"] += 1
            grade_key = {"A": "grade_A", "B": "grade_B", "C": "grade_C", "REJECT": "rejected"}.get(bean.actual_grade, "rejected")
            self.stats[grade_key] += 1
            if bean.defect != BeanDefect.NONE: self.stats["defects_in_sample"] += 1
            if bean.correct_decision: self.stats["correct"] += 1
            else:
                self.stats["incorrect"] += 1
                if bean.actual_grade == "REJECT" and bean.defect == BeanDefect.NONE:
                    self.stats["false_positives"] += 1
                elif bean.actual_grade != "REJECT" and bean.defect != BeanDefect.NONE:
                    self.stats["false_negatives"] += 1
            # Incident injection check
            if (self.beans_processed >= self._next_incident_at and
                    self.stats["incidents_injected"] < len(INCIDENTS)):
                self._inject_incident()

    def _inject_incident(self):
        idx = self.stats["incidents_injected"] % len(INCIDENTS)
        inc_type, inc_msg = INCIDENTS[idx]
        incident = {"type": inc_type, "message": inc_msg,
                     "at_bean": self.beans_processed, "at_time_s": self.elapsed_seconds,
                     "acknowledged": False}
        self.incident_history.append(incident)
        self.stats["incidents_injected"] += 1
        avg_beans = self.config["total_beans"] / max(len(INCIDENTS), 1)
        self._next_incident_at = self.beans_processed + int(avg_beans * random.uniform(0.3, 1.7))
        elapsed_m = self.elapsed_seconds / 60.0
        print(f"\n{'='*62}")
        print(f"  INCIDENT #{len(self.incident_history)} | Time: {elapsed_m:5.1f} min | Bean: {self.beans_processed:4d}")
        print(f"  {inc_msg}")
        print(f"{'='*62}\n")

    # ── Commands ──────────────────────────────────────────────────────────────

    def cmd_start(self) -> str:
        if self.state == MachineState.IDLE:
            self.state = MachineState.INITIALIZING
            return "-> INITIALIZING (boot sequence...)"
        if self.state == MachineState.READY:
            self.state = MachineState.RUNNING
            self.start_time = time.time()
            return "-> RUNNING"
        return f"[WARN] Cannot start from {self.state.name}"

    def cmd_stop(self) -> str:
        if self.state in (MachineState.RUNNING, MachineState.PAUSED, MachineState.FAULT):
            self._record_elapsed()
            self.state = MachineState.IDLE
            return "-> IDLE"
        return f"[WARN] Cannot stop from {self.state.name}"

    def cmd_pause(self) -> str:
        if self.state == MachineState.RUNNING:
            self.state = MachineState.PAUSED
            self.paused_at = time.time()
            return "-> PAUSED"
        return f"[WARN] Cannot pause from {self.state.name}"

    def cmd_resume(self) -> str:
        if self.state == MachineState.PAUSED:
            self.pause_duration += time.time() - self.paused_at
            self.paused_at = None
            self.state = MachineState.RUNNING
            return "-> RUNNING"
        return f"[WARN] Cannot resume from {self.state.name}"

    def cmd_estop(self) -> str:
        self._record_elapsed()
        self.state = MachineState.ESTOP
        self.stats["estop_count"] += 1
        self.stats["incidents_acknowledged"] += 1
        return "ESTOP ACTIVATED -- type 'reset' to recover"

    def cmd_reset(self) -> str:
        self.state = MachineState.IDLE
        self._record_elapsed()
        return "<RESET> -- type 'start' to begin"

    def cmd_status(self) -> str:
        tp = self._calc_throughput()
        return (f"State={self.state.name} | {self.beans_processed}/{self.config['total_beans']} "
                f"beans | {self._fmt_time()} | {tp:.3f} kg/h")

    def cmd_batch(self) -> str:
        s = self.stats
        total = max(s["total"], 1)
        return (f"Batch: total={s['total']} A={s['grade_A']} B={s['grade_B']} "
                f"C={s['grade_C']} reject={s['rejected']} | "
                f"Acc={s['correct']/total*100:.1f}% TP={self._calc_throughput():.3f} kg/h")

    def cmd_beans(self, n: int = 10) -> str:
        start = max(0, self.beans_processed - n)
        lines = []
        for b in self.beans[start:self.beans_processed]:
            dstr = f"[{b.defect.value.upper()}]" if b.defect != BeanDefect.NONE else ""
            ok = "OK" if b.correct_decision else "XX"
            lines.append(f"  #{b.bean_id:4d} Ch{b.channel} L*={b.L_top:5.1f} "
                          f"a*={b.a_top:5.1f} b*={b.b_top:5.1f} {b.mass_mg:5.0f}mg "
                          f"{b.actual_grade} {dstr} {ok}")
        return "\n".join(lines) if lines else "No beans processed yet."

    def cmd_score(self) -> str:
        score, brk = self.calculate_score()
        total = max(self.stats["total"], 1)
        tp = self._calc_throughput()
        target_tp = self.config["channels"] * self.config["bpm"] * BEAN_MASS_G / 1000 * 3600
        return (f"SCORE: {score*100:.1f}% (pass={self.config['pass_threshold']*100:.0f}%)\n"
                f"  Accuracy={brk['accuracy']*100:.1f}% DefectRecall={brk['defect_recall']*100:.1f}%\n"
                f"  FPRate={brk['false_positive_rate']*100:.1f}% TP={tp:.3f} kg/h(target={target_tp:.2f})\n"
                f"  Incidents={brk['incident_score']*100:.1f}%")

    def cmd_help(self) -> str:
        return ("Cmds: start|stop|pause|resume|status|batch|beans [n]|"
                "score|estop|reset|help|quit")

    def calculate_score(self) -> Tuple[float, Dict]:
        s = self.stats
        total = max(s["total"], 1)
        accuracy = s["correct"] / total
        defect_recall = (s["defects_in_sample"] - s["false_negatives"]) / max(s["defects_in_sample"], 1)
        normal_beans = total - s["defects_in_sample"]
        fp_rate = s["false_positives"] / max(normal_beans, 1)
        elapsed_h = max(self.elapsed_seconds, 1) / 3600.0
        tp_kg_h = (s["total"] * BEAN_MASS_G / 1000) / max(elapsed_h, 0.001)
        target_tp = self.config["channels"] * self.config["bpm"] * BEAN_MASS_G / 1000 * 3600
        tp_eff = min(tp_kg_h / max(target_tp, 0.001), 1.0)
        inc_score = 1.0
        if s["incidents_injected"] > 0:
            inc_score = s["incidents_acknowledged"] / s["incidents_injected"]
        final = (accuracy * 0.35 + defect_recall * 0.30 + (1.0 - fp_rate) * 0.15 +
                 tp_eff * 0.10 + inc_score * 0.10)
        brk = {"accuracy": accuracy, "defect_recall": defect_recall,
               "false_positive_rate": fp_rate, "throughput_kg_h": tp_kg_h,
               "throughput_efficiency": tp_eff, "incident_score": inc_score}
        return final, brk

    # ── Benchmark (auto) mode ─────────────────────────────────────────────────

    def run_benchmark(self) -> Dict:
        print(f"\n{'='*60}\n  BENCHMARK MODE: {self.config['name']}\n{'='*60}\n")
        self.state = MachineState.INITIALIZING
        print("[INIT] Booting sorter controller...")
        time.sleep(0.05)
        self.state = MachineState.CALIBRATING
        print("[CAL]  Calibrating sensors (HX711/AD7746/IMX477)...")
        time.sleep(0.05)
        self.state = MachineState.READY
        print("[READY] System ready.")
        print(f"[RUN ] {self.config['total_beans']} beans @ {self.config['channels']}ch x {self.config['bpm']}bpm\n")
        self.state = MachineState.RUNNING
        real_start = time.time()

        beans_to_generate = self.config["total_beans"]
        self._generate_beans_up_to(beans_to_generate)
        beans_per_sec = self.config["bpm"] * self.config["channels"] / 60.0
        total_sim_time = beans_to_generate / beans_per_sec
        self.elapsed_seconds = total_sim_time

        # Pre-compute incident positions
        avg_beans = beans_to_generate / max(len(INCIDENTS), 1)
        incident_beans = []
        for i in range(len(INCIDENTS)):
            at_bean = min(int(avg_beans * (i + 1) * random.uniform(0.7, 1.3)), beans_to_generate - 1)
            incident_beans.append((at_bean, INCIDENTS[i]))
        incident_beans.sort(key=lambda x: x[0])

        self.incident_history = []
        incident_idx = 0
        last_pct = 0

        for processed in range(beans_to_generate):
            if incident_idx < len(incident_beans) and processed >= incident_beans[incident_idx][0]:
                inc_type, inc_msg = incident_beans[incident_idx][1]
                elapsed_m = processed / beans_per_sec / 60.0
                print(f"\n  INCIDENT #{incident_idx+1} | Bean: {processed:4d}/{beans_to_generate} | "
                      f"Time: {elapsed_m:5.1f} min\n  {inc_msg}\n")
                self.incident_history.append({"type": inc_type, "message": inc_msg,
                                              "at_bean": processed, "acknowledged": False})
                self.stats["incidents_injected"] += 1
                self.stats["incidents_acknowledged"] += 1
                incident_idx += 1

            bean = self.beans[processed]
            self.beans_processed = processed + 1
            self.stats["total"] += 1
            grade_key = {"A": "grade_A", "B": "grade_B", "C": "grade_C",
                         "REJECT": "rejected"}.get(bean.actual_grade, "rejected")
            self.stats[grade_key] += 1
            if bean.defect != BeanDefect.NONE: self.stats["defects_in_sample"] += 1
            if bean.correct_decision: self.stats["correct"] += 1
            else:
                self.stats["incorrect"] += 1
                if bean.actual_grade == "REJECT" and bean.defect == BeanDefect.NONE:
                    self.stats["false_positives"] += 1
                elif bean.actual_grade != "REJECT" and bean.defect != BeanDefect.NONE:
                    self.stats["false_negatives"] += 1

            pct = int(self.beans_processed / beans_to_generate * 100)
            if pct >= last_pct + 10:
                last_pct = pct
                print(f"  [{pct:3d}%] {self.beans_processed:4d}/{beans_to_generate} beans...")

        real_end = time.time()
        self._real_elapsed_s = real_end - real_start
        # Use SIMULATED time for elapsed (what the operator experiences)
        # but track real time for throughput
        self.elapsed_seconds = total_sim_time
        print(f"  [DONE] {beans_to_generate}/{beans_to_generate} beans.")
        print(f"  Simulation time: {total_sim_time:.0f}s | Real time: {self._real_elapsed_s:.2f}s")
        self._record_elapsed()
        self.state = MachineState.IDLE
        score, brk = self.calculate_score()
        self._print_results(score, brk)
        self._save_results(score, brk)
        return {"score": score, "breakdown": brk, "stats": self.stats,
                "incidents": self.incident_history}

    def _print_progress(self):
        total = self.config["total_beans"]
        pct = self.beans_processed / total * 100
        m, s = divmod(int(self.elapsed_seconds), 60)
        tp = self._calc_throughput()
        acc = self.stats["correct"] / max(self.stats["total"], 1) * 100
        print(f"  [{m:02d}:{s:02d}] {pct:5.1f}% | {self.beans_processed:4d}/{total:4d} | "
              f"TP={tp:.3f} kg/h | Acc={acc:.1f}%")

    def _print_results(self, score: float, brk: Dict):
        s = self.stats
        total = s["total"]
        target_tp = self.config["channels"] * self.config["bpm"] * BEAN_MASS_G / 1000 * 3600
        passed = score >= self.config["pass_threshold"]
        tp = brk["throughput_kg_h"]
        acc_pct = s["correct"]/max(total,1)*100
        a_pct = s["grade_A"]/max(total,1)*100
        b_pct = s["grade_B"]/max(total,1)*100
        c_pct = s["grade_C"]/max(total,1)*100
        rej_pct = s["rejected"]/max(total,1)*100
        print(f"""
=================================================================
  TRAINING COMPLETE: {self.config['name']}
  STATUS: {'PASSED' if passed else 'FAILED'} (score={score*100:.1f}% threshold={self.config['pass_threshold']*100:.0f}%)
=================================================================
  SCORE: {score*100:.1f}%
  Accuracy={brk['accuracy']*100:.1f}% DefectRecall={brk['defect_recall']*100:.1f}%
  FPRate={brk['false_positive_rate']*100:.1f}% TP={tp:.3f}kg/h(target={target_tp:.2f})
  IncidentScore={brk['incident_score']*100:.1f}%

  BEANS: total={total} A={s['grade_A']}({a_pct:.1f}%) B={s['grade_B']}({b_pct:.1f}%)
         C={s['grade_C']}({c_pct:.1f}%) Reject={s['rejected']}({rej_pct:.1f}%)
  Correct={s['correct']}({acc_pct:.1f}%) FP={s['false_positives']} FN={s['false_negatives']}
  Incidents={s['incidents_injected']} injected / {s['incidents_acknowledged']} acked
  ESTOPCount={s['estop_count']}
=================================================================""")

    def _save_results(self, score: float, brk: Dict):
        results_dir = os.path.join(SCRIPT_DIR, "reports")
        os.makedirs(results_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = os.path.join(results_dir, f"training_{self.scenario}_{ts}.json")
        report = {"scenario": self.scenario, "score": score, "breakdown": brk,
                  "stats": self.stats, "incidents": self.incident_history,
                  "config": {k: v for k, v in self.config.items() if k != "name"},
                  "timestamp": ts}
        with open(fname, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[SAVE] {fname}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 Operator Training Simulator")
    parser.add_argument("--scenario", "-s", default="standard",
                        choices=list(SCENARIOS.keys()))
    parser.add_argument("--benchmark", "-b", action="store_true")
    args = parser.parse_args()

    session = TrainingSession(scenario=args.scenario)

    if args.benchmark:
        session.run_benchmark()
    else:
        print(f"\nHUSKY-SORTER-001 OPERATOR TRAINING SIMULATOR")
        print(f"Scenario: {session.config['name']}")
        print(f"Desc: {session.config['description']}")
        print(f"Beans={session.config['total_beans']} Ch={session.config['channels']} "
              f"BPM={session.config['bpm']} TimeLimit={session.config['max_time_minutes']}min")
        print(f"PassThreshold={session.config['pass_threshold']*100:.0f}%")
        print(f"Skills: {', '.join(session.config['focus_skills'])}")
        print("Type 'help' for commands.\n> ", end="", flush=True)

        while True:
            try:
                cmd_line = input().strip()
                if not cmd_line:
                    print("> ", end="", flush=True); continue
                session.stats["commands_issued"] += 1
                parts = cmd_line.split()
                cmd, arg = parts[0].lower(), parts[1] if len(parts) > 1 else None

                if cmd == "quit": print("Done."); break
                elif cmd == "start":    result = session.cmd_start()
                elif cmd == "stop":     result = session.cmd_stop()
                elif cmd == "pause":    result = session.cmd_pause()
                elif cmd == "resume":   result = session.cmd_resume()
                elif cmd == "estop":    result = session.cmd_estop()
                elif cmd == "reset":    result = session.cmd_reset()
                elif cmd == "status":   result = session.cmd_status()
                elif cmd == "batch":    result = session.cmd_batch()
                elif cmd == "beans":    result = session.cmd_beans(int(arg) if arg else 10)
                elif cmd == "score":   result = session.cmd_score()
                elif cmd == "help":    result = session.cmd_help()
                else: result = f"Unknown: {cmd}. Try 'help'."
                print(result)

                # Auto-update dashboard when running
                if session.state == MachineState.RUNNING:
                    session._record_elapsed()
                    session._process_beans(0.5)
                    if session.elapsed_seconds > session.config["max_time_minutes"] * 60:
                        print("\n[TIME] Session limit reached!")
                        session.state = MachineState.IDLE
                        score, brk = session.calculate_score()
                        session._print_results(score, brk)
                        session._save_results(score, brk)
                        break
                print("> ", end="", flush=True)
            except EOFError: break
