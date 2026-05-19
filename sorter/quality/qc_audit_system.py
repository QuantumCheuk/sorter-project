#!/usr/bin/env python3
# sorter/quality/qc_audit_system.py
# QC Audit & Compliance System for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-12 | Version: 1.0

"""
QC Audit & Compliance System
==============================
Purpose:
    Hardware-ready production quality auditing and SCA (Specialty Coffee
    Association) compliance documentation generator. Provides real-time
    audit trails, defect differential diagnosis, and batch compliance
    certificates for green coffee procurement and specialty certification.

Key Capabilities:
    1. BatchAuditReport — complete audit trail per batch with timestamps,
       sensor readings, defect counts, grade certification
    2. SCABeanGradeSheet — SCA-compliant cupping score sheet (sensory
       pre-assessment from objective metrics + known origin characteristics)
    3. DefectDifferentialDiagnosisSystem — operator decision support for
       ambiguous defect classification (fermented vs. moldy vs. over-dry, etc.)
    4. SupplierQualityProfile — per-origin quality fingerprint from incoming
       inspection data, enabling AI-driven supplier scoring
    5. ComplianceCertificateGenerator — ISO 22000 / SCA-inspired compliance
       doc per batch/lot for export documentation

Design Philosophy:
    - Stateless functions + dataclass models — no side effects, fully
      testable without hardware
    - All output formats (JSON / CSV row / human TEXT) generated from
      a single source of truth
    - Compatible with sorter/quality/thresholds.py and sorter/db/models.py

References:
    - SCA Green Coffee Classification: ≥90 pts = Specialty, 80-89.99 = Premium
    - SCA Cupping Scorecard: 6 sensory categories + overall (0-100)
    - ISO 22000:2018 food safety management
    - CODEX Stan 193-1995 coffee standards
"""

from __future__ import annotations

import json
import math
import statistics
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ─── Enums ────────────────────────────────────────────────────────────────────

class AuditSeverity(str, Enum):
    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"

class ComplianceStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    CONDITIONAL = "CONDITIONAL"
    NON_COMPLIANT = "NON_COMPLIANT"
    SUSPENDED = "SUSPENDED"

class SCAGrade(str, Enum):
    SPECIALTY = "SPECIALTY"          # ≥90 pts
    PREMIUM = "PREMIUM"             # 85-89.99 pts
    COMMERCIAL = "COMMERCIAL"       # 80-84.99 pts
    BELOW_STANDARD = "BELOW_STANDARD" # <80 pts

class DefectCategory(str, Enum):
    PRIMARY = "PRIMARY"    # Category 1: zero tolerance (mold, foreign matter, etc.)
    SECONDARY = "SECONDARY" # Category 2: countable defects per sample

# ─── SCA Defect Equivalence ──────────────────────────────────────────────────

SCA_DEFECT_EQUIVALENTS: Dict[str, Tuple[DefectCategory, float]] = {
    # (category, SCA full-defect equivalent per occurrence)
    # P-009 fix: keys must match DefectType enum values from thresholds.py
    "mold":           (DefectCategory.PRIMARY,    3.0),
    "fermented":      (DefectCategory.PRIMARY,    2.0),
    "black":          (DefectCategory.PRIMARY,    2.0),
    "dead":           (DefectCategory.PRIMARY,    2.0),
    "insect":         (DefectCategory.PRIMARY,    1.5),  # was "insect_damaged"
    "foreign":        (DefectCategory.PRIMARY,    5.0),  # Most severe
    "overweight":     (DefectCategory.SECONDARY,  0.5),
    "underweight":    (DefectCategory.SECONDARY,  0.5),
    "broken":         (DefectCategory.SECONDARY,  0.3),
    "underdev":       (DefectCategory.SECONDARY,  0.3),  # was "stunted"
    "hollow":         (DefectCategory.SECONDARY,  0.3),
    "overdry":        (DefectCategory.SECONDARY,  0.3),  # was "over_dry"
    "overwet":        (DefectCategory.SECONDARY,  0.5),  # was "over_wet"
    "mold_precursor": (DefectCategory.SECONDARY,  0.2),  # new: pre-mold
    "unknown":        (DefectCategory.SECONDARY,  0.1),
    "normal":         (DefectCategory.SECONDARY,  0.0),
}

# ─── Quality Score Weights ────────────────────────────────────────────────────

WEIGHT_CONFIG = {
    "defect_score_weight":   0.35,
    "moisture_score_weight": 0.20,
    "color_score_weight":    0.20,
    "density_score_weight":  0.15,
    "uniformity_weight":    0.10,
}

# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class SensorReadingSummary:
    channel: str
    n_samples: int
    mean: float
    std: float
    min_val: float
    max_val: float
    median: float
    cv_pct: float
    out_of_spec_count: int

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "n_samples": self.n_samples,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "min": round(self.min_val, 4),
            "max": round(self.max_val, 4),
            "median": round(self.median, 4),
            "cv_pct": round(self.cv_pct, 3),
            "out_of_spec_count": self.out_of_spec_count,
        }


@dataclass
class DefectCount:
    defect_type: str
    category: DefectCategory
    count: int
    eq_full_defects: float
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "defect_type": self.defect_type,
            "category": self.category.value,
            "count": self.count,
            "eq_full_defects": round(self.eq_full_defects, 2),
            "notes": self.notes,
        }


@dataclass
class AuditFinding:
    severity: AuditSeverity
    code: str
    title: str
    description: str
    affected_beans: int
    affected_pct: float
    recommendation: str
    corrective_action: str
    regulatory_ref: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "affected_beans": self.affected_beans,
            "affected_pct": round(self.affected_pct, 3),
            "recommendation": self.recommendation,
            "corrective_action": self.corrective_action,
            "regulatory_ref": self.regulatory_ref,
        }


@dataclass
class BatchAuditReport:
    audit_id: str
    batch_id: str
    lot_id: str
    origin: str
    process_method: str
    variety: str
    harvest_year: int
    supplier: str
    audit_timestamp: str
    production_date: str
    shift: str
    operator_id: str
    equipment_id: str
    recipe_name: str
    total_beans_processed: int
    total_kg_processed: float
    grade_a_count: int
    grade_b_count: int
    grade_c_count: int
    grade_reject_count: int
    grade_a_pct: float
    grade_b_pct: float
    grade_c_pct: float
    grade_reject_pct: float
    defects: List[DefectCount]
    total_primary_defects: int
    total_secondary_defects: int
    sca_eq_full_defects: float
    weight_summary: SensorReadingSummary
    moisture_summary: SensorReadingSummary
    density_summary: SensorReadingSummary
    color_summary: SensorReadingSummary
    compliance_status: ComplianceStatus
    sca_grade: SCAGrade
    quality_score: float
    defect_rate_pct: float
    moisture_pct_avg: float
    density_avg: float
    color_score_avg: float
    findings: List[AuditFinding]
    auditor: str = "HUSKY-SORTER-001 Auto-Audit"
    report_version: str = "1.0"

    @property
    def sca_pass_fail(self) -> bool:
        return self.sca_eq_full_defects <= 3.0

    @property
    def specialty_compliant(self) -> bool:
        return self.quality_score >= 90.0 and self.total_primary_defects == 0

    @property
    def compliance_badge(self) -> str:
        badges = {
            ComplianceStatus.COMPLIANT:       "🟢 COMPLIANT",
            ComplianceStatus.CONDITIONAL:     "🟡 CONDITIONAL",
            ComplianceStatus.NON_COMPLIANT:   "🔴 NON_COMPLIANT",
            ComplianceStatus.SUSPENDED:      "⚪ SUSPENDED",
        }
        return badges.get(self.compliance_status, "❓")

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "batch_id": self.batch_id,
            "lot_id": self.lot_id,
            "origin": self.origin,
            "process_method": self.process_method,
            "variety": self.variety,
            "harvest_year": self.harvest_year,
            "supplier": self.supplier,
            "audit_timestamp": self.audit_timestamp,
            "production_date": self.production_date,
            "shift": self.shift,
            "operator_id": self.operator_id,
            "equipment_id": self.equipment_id,
            "recipe_name": self.recipe_name,
            "volume": {
                "total_beans_processed": self.total_beans_processed,
                "total_kg_processed": round(self.total_kg_processed, 4),
                "grade_a_count": self.grade_a_count,
                "grade_b_count": self.grade_b_count,
                "grade_c_count": self.grade_c_count,
                "grade_reject_count": self.grade_reject_count,
                "grade_a_pct": round(self.grade_a_pct, 3),
                "grade_b_pct": round(self.grade_b_pct, 3),
                "grade_c_pct": round(self.grade_c_pct, 3),
                "grade_reject_pct": round(self.grade_reject_pct, 3),
            },
            "sca_defects": {
                "defects": [d.to_dict() for d in self.defects],
                "total_primary_defects": self.total_primary_defects,
                "total_secondary_defects": self.total_secondary_defects,
                "sca_eq_full_defects": round(self.sca_eq_full_defects, 2),
                "sca_pass": self.sca_pass_fail,
                "specialty_compliant": self.specialty_compliant,
            },
            "sensor_summaries": {
                "weight":  self.weight_summary.to_dict(),
                "moisture": self.moisture_summary.to_dict(),
                "density": self.density_summary.to_dict(),
                "color":   self.color_summary.to_dict(),
            },
            "compliance": {
                "status":        self.compliance_status.value,
                "badge":         self.compliance_badge,
                "sca_grade":     self.sca_grade.value,
                "quality_score": round(self.quality_score, 2),
                "defect_rate_pct": round(self.defect_rate_pct, 3),
                "moisture_pct_avg": round(self.moisture_pct_avg, 2),
                "density_avg":   round(self.density_avg, 4),
                "color_score_avg": round(self.color_score_avg, 2),
            },
            "findings": [f.to_dict() for f in self.findings],
            "meta": {
                "auditor": self.auditor,
                "report_version": self.report_version,
            },
        }

    def to_text(self) -> str:
        lines = [
            "=" * 70,
            "  HUSKY-SORTER-001  —  QC AUDIT REPORT",
            "=" * 70,
            f"  Audit ID    : {self.audit_id}",
            f"  Batch ID    : {self.batch_id}",
            f"  Lot ID      : {self.lot_id}",
            f"  Timestamp   : {self.audit_timestamp}",
            f"  Auditor     : {self.auditor}",
            "=" * 70,
            "",
            "┌─ IDENTITY ─────────────────────────────────────────────────────",
            f"│ Origin      : {self.origin}",
            f"│ Process     : {self.process_method}",
            f"│ Variety     : {self.variety}",
            f"│ Harvest     : {self.harvest_year}",
            f"│ Supplier    : {self.supplier}",
            f"│ Recipe      : {self.recipe_name}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ PRODUCTION ────────────────────────────────────────────────────",
            f"│ Date/Shift  : {self.production_date} / {self.shift}",
            f"│ Operator    : {self.operator_id}",
            f"│ Equipment   : {self.equipment_id}",
            f"│ Total Beans : {self.total_beans_processed:,}",
            f"│ Total Weight: {self.total_kg_processed:.4f} kg",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ GRADE DISTRIBUTION ──────────────────────────────────────────",
            f"│ Grade A     : {self.grade_a_count:,} ({self.grade_a_pct:.1f}%)",
            f"│ Grade B     : {self.grade_b_count:,} ({self.grade_b_pct:.1f}%)",
            f"│ Grade C     : {self.grade_c_count:,} ({self.grade_c_pct:.1f}%)",
            f"│ Reject      : {self.grade_reject_count:,} ({self.grade_reject_pct:.1f}%)",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ SCA DEFECT ASSESSMENT (350g sample) ──────────────────────────",
            f"│ Primary Defects (Category 1) : {self.total_primary_defects}",
            f"│ Secondary Defects (Category 2): {self.total_secondary_defects}",
            f"│ SCA Eq. Full Defects         : {self.sca_eq_full_defects:.2f}",
            f"│ SCA Pass (≤3 full def/350g)  : {'✅ PASS' if self.sca_pass_fail else '❌ FAIL'}",
            "│ Defect Detail:",
        ]
        for d in self.defects:
            if d.count > 0:
                lines.append(
                    f"│   - {d.defect_type:<20} {d.count:>4} ({d.category.value}) "
                    f"= {d.eq_full_defects:.1f} full def"
                )
        lines.extend([
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ SENSOR STATISTICS ────────────────────────────────────────────",
            f"│ Weight (g/b)  μ={self.weight_summary.mean:.4f}  σ={self.weight_summary.std:.4f}  "
            f"CV={self.weight_summary.cv_pct:.1f}%  OOS={self.weight_summary.out_of_spec_count}",
            f"│ Moisture (%)  μ={self.moisture_summary.mean:.2f}  σ={self.moisture_summary.std:.4f}  "
            f"CV={self.moisture_summary.cv_pct:.1f}%  OOS={self.moisture_summary.out_of_spec_count}",
            f"│ Density (g/mL) μ={self.density_summary.mean:.4f}  σ={self.density_summary.std:.4f}  "
            f"CV={self.density_summary.cv_pct:.1f}%  OOS={self.density_summary.out_of_spec_count}",
            f"│ Color Score  μ={self.color_summary.mean:.2f}  σ={self.color_summary.std:.4f}  "
            f"CV={self.color_summary.cv_pct:.1f}%  OOS={self.color_summary.out_of_spec_count}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ COMPLIANCE ────────────────────────────────────────────────────",
            f"│ Status       : {self.compliance_badge}",
            f"│ SCA Grade    : {self.sca_grade.value}",
            f"│ Quality Score: {self.quality_score:.1f}/100",
            f"│ Defect Rate  : {self.defect_rate_pct:.2f}%",
            f"│ Specialty    : {'✅ YES (≥90pts, 0 Cat-1)' if self.specialty_compliant else '❌ NO'}",
            "└────────────────────────────────────────────────────────────────",
        ])
        if self.findings:
            lines.extend(["", "┌─ AUDIT FINDINGS ──────────────────────────────────────────────"])
            sev_icon = {"INFO": "ℹ️", "MINOR": "⚠️", "MAJOR": "🔶", "CRITICAL": "🚨"}
            for i, f in enumerate(self.findings, 1):
                icon = sev_icon.get(f.severity.value, "•")
                lines.extend([
                    f"│ [{i}] {icon} {f.code}  {f.title}  ({f.severity.value})",
                    f"│     {f.description}",
                    f"│     Impact: {f.affected_beans} beans ({f.affected_pct:.2f}%)",
                    f"│     Recommendation: {f.recommendation}",
                    f"│     Corrective Action: {f.corrective_action}",
                ])
            lines.append("└────────────────────────────────────────────────────────────────")
        lines.extend([
            "",
            "─" * 70,
            f"  Report Version: {self.report_version} | Generated: {self.audit_timestamp}",
            "─" * 70,
        ])
        return "\n".join(lines)


# ─── Core Computation Functions ───────────────────────────────────────────────

def compute_sca_grade(quality_score: float) -> SCAGrade:
    if quality_score >= 90.0:
        return SCAGrade.SPECIALTY
    elif quality_score >= 85.0:
        return SCAGrade.PREMIUM
    elif quality_score >= 80.0:
        return SCAGrade.COMMERCIAL
    return SCAGrade.BELOW_STANDARD


def compute_sensor_summary(
    channel: str,
    readings: List[float],
    spec_min: float,
    spec_max: float,
) -> SensorReadingSummary:
    if not readings:
        return SensorReadingSummary(
            channel=channel, n_samples=0, mean=0.0, std=0.0,
            min_val=0.0, max_val=0.0, median=0.0, cv_pct=0.0,
            out_of_spec_count=0,
        )
    mean = statistics.mean(readings)
    std = statistics.stdev(readings) if len(readings) > 1 else 0.0
    cv_pct = (std / mean * 100) if mean != 0 else 0.0
    oos = sum(1 for r in readings if r < spec_min or r > spec_max)
    return SensorReadingSummary(
        channel=channel, n_samples=len(readings), mean=mean, std=std,
        min_val=min(readings), max_val=max(readings),
        median=statistics.median(readings), cv_pct=cv_pct,
        out_of_spec_count=oos,
    )


def compute_quality_score(
    defect_rate_pct: float,
    moisture_pct: float,
    moisture_target: float = 11.0,
    moisture_tolerance: float = 2.0,
    color_score: float = 85.0,
    density: float = 0.68,
    density_target: float = 0.68,
    density_tolerance: float = 0.05,
    weight_cv_pct: float = 5.0,
) -> Tuple[float, Dict[str, float]]:
    defect_score    = max(0.0, 100.0 - defect_rate_pct * 10.0)
    moisture_dev    = abs(moisture_pct - moisture_target)
    moisture_score  = max(0.0, 100.0 - (moisture_dev / moisture_tolerance) * 50.0)
    density_dev     = abs(density - density_target)
    density_score   = max(0.0, 100.0 - (density_dev / density_tolerance) * 50.0)
    uniformity_score= max(0.0, 100.0 - weight_cv_pct * 4.0)
    total = (
        defect_score    * WEIGHT_CONFIG["defect_score_weight"]
      + moisture_score  * WEIGHT_CONFIG["moisture_score_weight"]
      + color_score     * WEIGHT_CONFIG["color_score_weight"]
      + density_score   * WEIGHT_CONFIG["density_score_weight"]
      + uniformity_score* WEIGHT_CONFIG["uniformity_weight"]
    )
    components = {
        "defect_score":     round(defect_score, 2),
        "moisture_score":   round(moisture_score, 2),
        "color_score":      round(color_score, 2),
        "density_score":    round(density_score, 2),
        "uniformity_score": round(uniformity_score, 2),
    }
    return round(total, 2), components


def compute_compliance_status(
    defect_rate_pct: float,
    moisture_pct: float,
    sca_pass: bool,
    primary_defects: int,
    moisture_spec: Tuple[float, float] = (8.0, 14.0),
) -> ComplianceStatus:
    if primary_defects > 0:
        return ComplianceStatus.NON_COMPLIANT
    if not sca_pass:
        return ComplianceStatus.NON_COMPLIANT
    if moisture_pct < moisture_spec[0] or moisture_pct > moisture_spec[1]:
        return ComplianceStatus.NON_COMPLIANT
    if defect_rate_pct > 10.0:
        return ComplianceStatus.NON_COMPLIANT
    if defect_rate_pct > 3.0:
        return ComplianceStatus.CONDITIONAL
    return ComplianceStatus.COMPLIANT


def generate_audit_findings(
    report: BatchAuditReport,
    recipe_targets: Dict[str, Any],
) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    target_defect = recipe_targets.get("defect_rate_max_pct", 2.0)

    if report.defect_rate_pct > target_defect:
        excess = report.defect_rate_pct - target_defect
        findings.append(AuditFinding(
            severity=AuditSeverity.MAJOR if excess > 2.0 else AuditSeverity.MINOR,
            code="QC-001",
            title="Defect Rate Exceeds Recipe Target",
            description=f"Batch defect rate {report.defect_rate_pct:.2f}% exceeds "
                        f"recipe target {target_defect:.2f}%",
            affected_beans=int(report.total_beans_processed * excess / 100),
            affected_pct=excess,
            recommendation="Review origin quality; check sorting thresholds",
            corrective_action="Increase sorting aggressiveness for affected defect type",
            regulatory_ref="SCA Green Coffee Classification Protocol",
        ))

    target_moisture = recipe_targets.get("moisture_target_pct", 11.0)
    moisture_tol    = recipe_targets.get("moisture_tolerance_pct", 2.0)
    if abs(report.moisture_pct_avg - target_moisture) > moisture_tol:
        findings.append(AuditFinding(
            severity=AuditSeverity.CRITICAL,
            code="QC-002",
            title="Moisture Content Out of Safe Range",
            description=f"Batch moisture {report.moisture_pct_avg:.2f}% outside "
                        f"safe range ({target_moisture:.1f}±{moisture_tol:.1f}%)",
            affected_beans=report.total_beans_processed,
            affected_pct=100.0,
            recommendation="Do not store — mold risk (>13%) or brittleness (<8%)",
            corrective_action="Quarantine batch immediately; re-dry if >13%",
            regulatory_ref="CODEX Stan 193-1995; SCA Green Coffee Best Practices",
        ))

    if report.total_primary_defects > 0:
        findings.append(AuditFinding(
            severity=AuditSeverity.CRITICAL,
            code="SCA-001",
            title="SCA Category 1 (Primary) Defects Detected",
            description=f"{report.total_primary_defects} Category 1 defects found. "
                        f"Zero required for SCA specialty classification.",
            affected_beans=report.total_primary_defects,
            affected_pct=report.total_primary_defects
                         / max(1, report.total_beans_processed) * 100,
            recommendation="Batch is NOT specialty-grade. Downgrade to Commercial.",
            corrective_action="Re-sort with aggressive thresholds or reject lot",
            regulatory_ref="SCA Green Coffee Classification: ≥0 Category 1 defects",
        ))

    if not report.sca_pass_fail:
        findings.append(AuditFinding(
            severity=AuditSeverity.MAJOR,
            code="SCA-002",
            title="SCA Defect Count Exceeds Limit",
            description=f"SCA eq. full defects {report.sca_eq_full_defects:.2f} > 3.0 threshold",
            affected_beans=report.total_beans_processed,
            affected_pct=100.0,
            recommendation="Batch fails SCA minimum standard",
            corrective_action="Re-inspect lot; consider blending with cleaner lots",
            regulatory_ref="SCA Green Coffee Defect Chart",
        ))

    if report.color_summary.cv_pct > 15.0:
        findings.append(AuditFinding(
            severity=AuditSeverity.MINOR,
            code="QC-003",
            title="High Color Uniformity Variation",
            description=f"Color CV% = {report.color_summary.cv_pct:.1f}% (threshold 15%). "
                        f"Indicates inconsistent fermentation or mixing of origins.",
            affected_beans=int(report.total_beans_processed * 0.3),
            affected_pct=30.0,
            recommendation="Investigate fermentation process consistency",
            corrective_action="Audit fermentation tanks; verify no lot mixing",
            regulatory_ref="SCA Bean Ref 2 — Color as Sorting Criterion",
        ))

    if report.weight_summary.cv_pct > 10.0:
        findings.append(AuditFinding(
            severity=AuditSeverity.MINOR,
            code="QC-004",
            title="High Weight Uniformity Variation",
            description=f"Weight CV% = {report.weight_summary.cv_pct:.1f}% (threshold 10%)",
            affected_beans=int(report.total_beans_processed * 0.25),
            affected_pct=25.0,
            recommendation="Verify screen sizing before mixing",
            corrective_action="Check screen grade separation in upstream handling",
            regulatory_ref="SCA Green Coffee Classification Protocol",
        ))

    if report.grade_a_pct == 0.0 and report.total_beans_processed > 0:
        findings.append(AuditFinding(
            severity=AuditSeverity.MAJOR,
            code="QC-005",
            title="No Grade A Production",
            description="All beans failed Grade A threshold.",
            affected_beans=report.total_beans_processed,
            affected_pct=100.0,
            recommendation="Review sorting thresholds; verify recipe suitability",
            corrective_action="Adjust color/weight thresholds; verify sensor calibration",
            regulatory_ref="HUSKY-SORTER-001 Grade Specification",
        ))

    return findings


# ─── Defect Differential Diagnosis System ────────────────────────────────────

@dataclass
class DifferentialDiagnosis:
    bean_id: str
    differential_findings: List[str]
    primary_hypothesis: str
    alternative_hypotheses: List[str]
    confidence: float
    action: str

    def to_dict(self) -> dict:
        return {
            "bean_id": self.bean_id,
            "differential_findings": self.differential_findings,
            "primary_hypothesis": self.primary_hypothesis,
            "alternative_hypotheses": self.alternative_hypotheses,
            "confidence": round(self.confidence, 1),
            "action": self.action,
        }


class DefectDifferentialDiagnosisSystem:
    """
    Operator decision support for ambiguous defect classification.

    Key ambiguous pairs:
      1. Moldy vs. Fermented: Both dark coloration. Mold → uniform
         + elevated moisture. Fermented → patchy + irregular color.
      2. Over-Dry vs. Broken: Both low weight. Over-dry → correct
         density, lighter color. Broken → normal density, sharp edge.
      3. Hollow vs. Stunted: Both low weight. Hollow → very low density,
         visible air gap. Stunted → normal density, smaller but filled.
      4. Insect Damaged vs. Foreign: Insect → entry hole + internal void.
         Foreign (stone) → high density, irregular shape.
      5. Black vs. Over-Fermented: Both very dark. Black → full penetration.
         Over-fermented → mottled dark/green.

    Decision thresholds:
      DARK_LAB_THRESHOLD  = ΔE > 20 from normal green (L*=48, a*=+4, b*=+17)
      LOW_WEIGHT_THRESHOLD = 0.08 g/bean
      LOW_DENSITY_THRESHOLD = 0.55 g/mL
      HIGH_MOISTURE_THRESHOLD = 14.5%
    """

    def diagnose(
        self,
        bean_id: str,
        weight_g: float,
        moisture_pct: float,
        density_g_mL: float,
        lab_color: Dict[str, float],
        color_std: float,
    ) -> DifferentialDiagnosis:
        L = lab_color.get("L", 48)
        a = lab_color.get("a", 0)
        b = lab_color.get("b", 17)
        delta_E = math.sqrt((L - 48)**2 + (a - 4)**2 + (b - 17)**2)

        findings: List[str] = []
        hypotheses: List[Tuple[str, float]] = []

        # ── Weight-based discrimination ────────────────────────────────────
        if weight_g < 0.08:
            findings.append(f"LOW WEIGHT: {weight_g:.4f}g < 0.08g")
            if density_g_mL < 0.55:
                findings.append("→ LOW DENSITY + LOW WEIGHT → HOLLOW likely (air gap)")
                hypotheses.append(("hollow", 0.85))
            else:
                findings.append("→ NORMAL DENSITY + LOW WEIGHT → UNDERWEIGHT or STUNTED")
                hypotheses.append(("underweight", 0.6))
                hypotheses.append(("underdev", 0.4))
        elif weight_g > 0.28:
            findings.append(f"HIGH WEIGHT: {weight_g:.4f}g > 0.28g")
            hypotheses.append(("overweight", 0.9))

        # ── Color-based discrimination ─────────────────────────────────────
        if delta_E > 20:
            findings.append(f"SEVERE COLOR DEVIATION: ΔE={delta_E:.1f} >> 20 (normal green)")
            if delta_E > 35:
                findings.append("→ ΔE>35 → BLACK (full penetration)")
                hypotheses.append(("black", 0.90))
            elif color_std > 0.15:
                findings.append("→ PATCHY dark coloration → FERMENTED likely")
                hypotheses.append(("fermented", 0.65))
                hypotheses.append(("black", 0.35))
            else:
                findings.append("→ UNIFORM dark → MOLD likely")
                hypotheses.append(("mold", 0.70))
                hypotheses.append(("black", 0.30))
        elif delta_E > 10:
            findings.append(f"MILD COLOR DEVIATION: ΔE={delta_E:.1f} (10<ΔE<20)")
            if moisture_pct > 14.5:
                findings.append("→ DARK + HIGH MOISTURE → MOLD risk")
                hypotheses.append(("mold", 0.60))
                hypotheses.append(("overwet", 0.4))
            else:
                findings.append("→ MILD discoloration → possible early fermentation")
                hypotheses.append(("fermented", 0.50))
                hypotheses.append(("stunted", 0.3))
        else:
            findings.append(f"NORMAL COLOR: ΔE={delta_E:.1f} ≤ 10")
            hypotheses.append(("normal", 0.80))
            hypotheses.append(("stunted", 0.2))

        # ── Density-based discrimination ───────────────────────────────────
        if density_g_mL < 0.55:
            findings.append(f"LOW DENSITY: {density_g_mL:.3f} g/mL < 0.55 → HOLLOW")
            if not any(h[0] == "hollow" for h in hypotheses):
                hypotheses.append(("hollow", 0.80))
        elif density_g_mL > 0.80:
            findings.append(f"HIGH DENSITY: {density_g_mL:.3f} g/mL > 0.80 → FOREIGN (stone)")
            hypotheses.append(("foreign", 0.75))
            hypotheses.append(("overweight", 0.25))

        # ── Moisture-based discrimination ───────────────────────────────────
        if moisture_pct < 8.0:
            findings.append(f"LOW MOISTURE: {moisture_pct:.1f}% < 8% → OVER-DRY")
            hypotheses.append(("overdry", 0.85))
        elif moisture_pct > 14.5:
            findings.append(f"HIGH MOISTURE: {moisture_pct:.1f}% > 14.5% → OVER-WET or MOLD")
            hypotheses.append(("overwet", 0.55))
            hypotheses.append(("mold", 0.45))

        # Sort hypotheses by confidence descending
        hypotheses.sort(key=lambda x: x[1], reverse=True)
        primary = hypotheses[0][0] if hypotheses else "unknown"
        alternatives = [h[0] for h in hypotheses[1:4]] if len(hypotheses) > 1 else []
        confidence = hypotheses[0][1] if hypotheses else 0.0

        action_map = {
            "black":        "REJECT — Category 1 primary defect",
            "mold":        "REJECT — mold risk, food safety hazard",
            "fermented":    "REJECT — fermentation overdrive, sour taint",
            "hollow":      "RECLASSIFY as Grade C or Reject",
            "foreign":     "REJECT — foreign matter, food safety hazard",
            "overweight":  "RECLASSIFY to oversized bin",
            "underweight": "RECLASSIFY to lightweight bin",
            "underdev":     "RECLASSIFY as Grade C or below",
            "overdry":      "RECLASSIFY as Grade C — brittleness risk",
            "overwet":      "REJECT — mold risk, shelf-life compromised",
            "normal":      "ACCEPT — Grade A candidate",
        }

        return DifferentialDiagnosis(
            bean_id=bean_id,
            differential_findings=findings,
            primary_hypothesis=primary,
            alternative_hypotheses=alternatives,
            confidence=confidence * 100,
            action=action_map.get(primary, "INVESTIGATE — ambiguous classification"),
        )


# ─── SCA Bean Grade Sheet ─────────────────────────────────────────────────────

@dataclass
class SCABeanGradeSheet:
    """SCA Green Coffee Certificate — pre-cupping quality assessment."""
    certificate_id: str
    lot_id: str
    origin: str
    process_method: str
    variety: str
    harvest_year: int
    supplier: str
    grading_date: str
    graded_by: str

    # Objective measurements (from sorter)
    total_beans_graded: int
    sample_weight_g: int = 350

    # SCA defect count (extrapolated to 350g sample)
    sca_eq_full_defects: float = 0.0

    # Physical quality scores
    moisture_pct: float = 11.0
    density_g_mL: float = 0.68
    screen_size_majority: str = "15"
    color_uniformity: str = "good"  # good / fair / poor

    # Estimated cupping profile (from objective data + origin known profile)
    estimated_aroma_score: float = 7.5
    estimated_flavor_score: float = 7.5
    estimated_acidity_score: float = 7.5
    estimated_body_score: float = 7.5
    estimated_balance_score: float = 7.5
    estimated_overall_score: float = 7    # Defects found
    defects_found: List[str] = field(default_factory=list)
    primary_defect_count: int = 0
    secondary_defect_count: int = 0

    # Origin-known profile (for estimated cupping)
    origin_aroma_notes: str = ""
    origin_process_characteristics: str = ""

    @property
    def sca_category_1_pass(self) -> bool:
        return self.primary_defect_count == 0

    @property
    def sca_category_2_points(self) -> float:
        return self.sca_eq_full_defects

    @property
    def sca_pass(self) -> bool:
        return self.sca_eq_full_defects <= 3.0

    @property
    def sca_preliminary_grade(self) -> SCAGrade:
        if self.sca_eq_full_defects <= 3.0 and self.primary_defect_count == 0:
            return SCAGrade.SPECIALTY
        elif self.sca_eq_full_defects <= 5.0:
            return SCAGrade.PREMIUM
        elif self.sca_eq_full_defects <= 8.0:
            return SCAGrade.COMMERCIAL
        return SCAGrade.BELOW_STANDARD

    @property
    def preliminary_points(self) -> float:
        base = 60.0  # SCA baseline from physical assessment
        base += min(self.estimated_overall_score, 10.0) * 4.0
        base -= self.sca_eq_full_defects * 2.0
        return max(0.0, min(100.0, base))

    def to_dict(self) -> dict:
        return {
            "certificate_id": self.certificate_id,
            "lot_id": self.lot_id,
            "origin": self.origin,
            "process_method": self.process_method,
            "variety": self.variety,
            "harvest_year": self.harvest_year,
            "supplier": self.supplier,
            "grading_date": self.grading_date,
            "graded_by": self.graded_by,
            "sample_weight_g": self.sample_weight_g,
            "total_beans_graded": self.total_beans_graded,
            "physical_assessment": {
                "moisture_pct": round(self.moisture_pct, 2),
                "density_g_mL": round(self.density_g_mL, 4),
                "screen_size_majority": self.screen_size_majority,
                "color_uniformity": self.color_uniformity,
            },
            "sca_defects": {
                "eq_full_defects": round(self.sca_eq_full_defects, 2),
                "primary_defect_count": self.primary_defect_count,
                "secondary_defect_count": self.secondary_defect_count,
                "defects_found": self.defects_found,
                "cat1_pass": self.sca_category_1_pass,
                "cat2_pass": self.sca_eq_full_defects <= 3.0,
                "sca_pass": self.sca_pass,
            },
            "estimated_cupping_profile": {
                "aroma":       round(self.estimated_aroma_score, 1),
                "flavor":      round(self.estimated_flavor_score, 1),
                "acidity":     round(self.estimated_acidity_score, 1),
                "body":        round(self.estimated_body_score, 1),
                "balance":     round(self.estimated_balance_score, 1),
                "overall":     round(self.estimated_overall_score, 1),
                "notes": {
                    "aroma": self.origin_aroma_notes,
                    "process": self.origin_process_characteristics,
                },
            },
            "preliminary_grade": {
                "sca_grade": self.sca_preliminary_grade.value,
                "preliminary_points": round(self.preliminary_points, 1),
                "note": "Final grade requires actual cupping session",
            },
        }

    def to_text(self) -> str:
        lines = [
            "=" * 70,
            "  SCA GREEN COFFEE CERTIFICATE (Preliminary — Pre-Cupping)",
            "=" * 70,
            f"  Certificate ID : {self.certificate_id}",
            f"  Lot ID         : {self.lot_id}",
            f"  Grading Date   : {self.grading_date}",
            f"  Graded By      : {self.graded_by}",
            "=" * 70,
            "",
            "┌─ ORIGIN INFORMATION ──────────────────────────────────────────",
            f"│ Origin         : {self.origin}",
            f"│ Process Method : {self.process_method}",
            f"│ Variety        : {self.variety}",
            f"│ Harvest Year   : {self.harvest_year}",
            f"│ Supplier       : {self.supplier}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ PHYSICAL ASSESSMENT ─────────────────────────────────────────",
            f"│ Moisture       : {self.moisture_pct:.2f}% (SCA spec: 8-12%)",
            f"│ Density        : {self.density_g_mL:.3f} g/mL (SCA spec: ≥0.65)",
            f"│ Screen Size    : {self.screen_size_majority} (majority)",
            f"│ Color Uniformity: {self.color_uniformity}",
            f"│ Beans Graded   : {self.total_beans_graded:,}",
            f"│ Sample Weight  : {self.sample_weight_g}g",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ SCA DEFECT CLASSIFICATION ───────────────────────────────────",
            f"│ Category 1 (Primary) Defects  : {self.primary_defect_count}"
            f"  {'✅ PASS — 0 found' if self.sca_category_1_pass else '❌ FAIL'}"
            ,
            f"│ Category 2 Defect Points      : {self.sca_eq_full_defects:.2f} / 3.0 max",
            f"│ SCA Pass (≤3 full def/350g)  : {'✅ PASS' if self.sca_pass else '❌ FAIL'}",
        ]
        if self.defects_found:
            lines.append(f"│ Defects Identified: {', '.join(self.defects_found)}")
        lines.extend([
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ ESTIMATED CUPPING PROFILE (Pre-Cupping Estimate) ────────────",
            f"│ Aroma      : {self.estimated_aroma_score:.1f} / 10",
            f"│ Flavor     : {self.estimated_flavor_score:.1f} / 10",
            f"│ Acidity    : {self.estimated_acidity_score:.1f} / 10",
            f"│ Body       : {self.estimated_body_score:.1f} / 10",
            f"│ Balance    : {self.estimated_balance_score:.1f} / 10",
            f"│ Overall    : {self.estimated_overall_score:.1f} / 10",
            f"│ ─────────────────────────────────────────────────────────────",
            f"│ Estimated Score: {self.preliminary_points:.1f} / 100",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ PRELIMINARY SCA GRADE ────────────────────────────────────────",
            f"│ Preliminary Grade : {self.sca_preliminary_grade.value}",
            f"│ Preliminary Points: {self.preliminary_points:.1f}",
            "│",
            "│ ⚠️  NOTE: This is a MACHINE-BASED preliminary assessment.",
            "│    Final specialty grade requires human Q-Grader cupping.",
            "└────────────────────────────────────────────────────────────────",
            "",
            f"  Certificate ID: {self.certificate_id} | Generated: {self.grading_date}",
        ])
        return "\n".join(lines)


# ─── Supplier Quality Profile ────────────────────────────────────────────────

@dataclass
class SupplierQualityProfile:
    """Per-origin quality fingerprint from historical inspection data."""
    supplier_id: str
    supplier_name: str
    origin: str
    process_methods: List[str]
    varieties: List[str]

    # Historical stats
    total_batches: int = 0
    total_kg_processed: float = 0.0
    avg_quality_score: float = 0.0
    avg_defect_rate_pct: float = 0.0
    avg_moisture_pct: float = 0.0
    avg_density_g_mL: float = 0.0
    avg_sca_grade_pts: float = 0.0
    avg_grade_a_pct: float = 0.0

    # Batch history
    batch_history: List[Dict] = field(default_factory=list)
    last_inspection_date: str = ""

    # Computed ratings
    consistency_rating: float = 0.0   # 0-100
    quality_trend: str = "stable"     # improving / stable / declining
    risk_level: str = "LOW"            # LOW / MEDIUM / HIGH
    compliance_rate_pct: float = 0.0

    # SCA history
    specialty_batches: int = 0
    specialty_rate_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "origin": self.origin,
            "process_methods": self.process_methods,
            "varieties": self.varieties,
            "historical_stats": {
                "total_batches": self.total_batches,
                "total_kg_processed": round(self.total_kg_processed, 2),
                "avg_quality_score": round(self.avg_quality_score, 2),
                "avg_defect_rate_pct": round(self.avg_defect_rate_pct, 3),
                "avg_moisture_pct": round(self.avg_moisture_pct, 2),
                "avg_density_g_mL": round(self.avg_density_g_mL, 4),
                "avg_sca_grade_pts": round(self.avg_sca_grade_pts, 1),
                "avg_grade_a_pct": round(self.avg_grade_a_pct, 2),
            },
            "consistency_rating": round(self.consistency_rating, 1),
            "quality_trend": self.quality_trend,
            "risk_level": self.risk_level,
            "compliance_rate_pct": round(self.compliance_rate_pct, 2),
            "specialty_batches": self.specialty_batches,
            "specialty_rate_pct": round(self.specialty_rate_pct, 2),
            "batch_history": self.batch_history[-20:],  # last 20
            "last_inspection_date": self.last_inspection_date,
        }

    def to_text(self) -> str:
        risk_color = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(self.risk_level, "⚪")
        trend_icon = {"improving": "📈", "stable": "➡️", "declining": "📉"}.get(
            self.quality_trend, "➡️"
        )
        lines = [
            "=" * 60,
            "  SUPPLIER QUALITY PROFILE",
            "=" * 60,
            f"  Supplier     : {self.supplier_name} ({self.supplier_id})",
            f"  Origin       : {self.origin}",
            f"  Processes    : {', '.join(self.process_methods)}",
            f"  Varieties    : {', '.join(self.varieties)}",
            "=" * 60,
            "",
            f"  {risk_color} Risk Level  : {self.risk_level}",
            f"  {trend_icon} Quality Trend: {self.quality_trend}",
            "",
            "┌─ HISTORICAL PERFORMANCE ──────────────────────────────────────",
            f"│ Batches Processed  : {self.total_batches}",
            f"│ Total Volume       : {self.total_kg_processed:.2f} kg",
            f"│ Avg Quality Score  : {self.avg_quality_score:.1f}/100",
            f"│ Avg Defect Rate    : {self.avg_defect_rate_pct:.2f}%",
            f"│ Avg Moisture       : {self.avg_moisture_pct:.2f}%",
            f"│ Avg Density        : {self.avg_density_g_mL:.4f} g/mL",
            f"│ Avg SCA Points     : {self.avg_sca_grade_pts:.1f}",
            f"│ Avg Grade A Rate   : {self.avg_grade_a_pct:.1f}%",
            f"│ Specialty Rate     : {self.specialty_rate_pct:.1f}% "
            f"({self.specialty_batches} batches)",
            f"│ Compliance Rate    : {self.compliance_rate_pct:.1f}%",
            "└────────────────────────────────────────────────────────────────",
            "",
            f"  Last Inspection: {self.last_inspection_date}",
            f"  Consistency Rating: {self.consistency_rating:.1f}/100",
        ]
        return "\n".join(lines)


def compute_supplier_profile(
    supplier_id: str,
    supplier_name: str,
    origin: str,
    batch_reports: List[BatchAuditReport],
) -> SupplierQualityProfile:
    """
    Aggregate batch audit reports into a supplier quality profile.
    """
    if not batch_reports:
        return SupplierQualityProfile(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            origin=origin,
            process_methods=[],
            varieties=[],
            risk_level="UNKNOWN",
            consistency_rating=0.0,
        )

    n = len(batch_reports)
    quality_scores   = [r.quality_score for r in batch_reports]
    defect_rates     = [r.defect_rate_pct for r in batch_reports]
    moistures        = [r.moisture_pct_avg for r in batch_reports]
    densities        = [r.density_avg for r in batch_reports]
    grade_a_pcts     = [r.grade_a_pct for r in batch_reports]
    sca_pts_list     = [r.quality_score for r in batch_reports]  # using quality score as proxy

    # Consistency: inverse of CV of quality scores
    qs_mean = statistics.mean(quality_scores)
    qs_std  = statistics.stdev(quality_scores) if n > 1 else 0.0
    cv      = (qs_std / qs_mean * 100) if qs_mean > 0 else 0.0
    consistency_rating = max(0.0, 100.0 - cv * 2.0)

    # Quality trend: compare first third vs last third
    third = max(1, n // 3)
    early_avg = statistics.mean(quality_scores[:third])
    late_avg  = statistics.mean(quality_scores[-third:])
    delta = late_avg - early_avg
    trend = "improving" if delta > 2.0 else ("declining" if delta < -2.0 else "stable")

    # Risk level
    risk = "LOW"
    if defect_rates and max(defect_rates) > 5.0:
        risk = "MEDIUM"
    if defect_rates and max(defect_rates) > 10.0:
        risk = "HIGH"

    # Compliance rate
    compliant_count = sum(
        1 for r in batch_reports
        if r.compliance_status == ComplianceStatus.COMPLIANT
    )
    compliance_rate = compliant_count / n * 100

    # Specialty rate
    specialty_count = sum(1 for r in batch_reports if r.specialty_compliant)
    specialty_rate  = specialty_count / n * 100

    process_methods = list({r.process_method for r in batch_reports})
    varieties       = list({r.variety for r in batch_reports})

    return SupplierQualityProfile(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        origin=origin,
        process_methods=process_methods,
        varieties=varieties,
        total_batches=n,
        total_kg_processed=sum(r.total_kg_processed for r in batch_reports),
        avg_quality_score=round(qs_mean, 2),
        avg_defect_rate_pct=round(statistics.mean(defect_rates), 3),
        avg_moisture_pct=round(statistics.mean(moistures), 2),
        avg_density_g_mL=round(statistics.mean(densities), 4),
        avg_sca_grade_pts=round(statistics.mean(sca_pts_list), 1),
        avg_grade_a_pct=round(statistics.mean(grade_a_pcts), 2),
        consistency_rating=round(consistency_rating, 1),
        quality_trend=trend,
        risk_level=risk,
        compliance_rate_pct=round(compliance_rate, 2),
        specialty_batches=specialty_count,
        specialty_rate_pct=round(specialty_rate, 2),
        batch_history=[{"batch_id": r.batch_id, "quality_score": r.quality_score,
                        "grade_a_pct": r.grade_a_pct, "date": r.production_date}
                       for r in batch_reports[-20:]],
        last_inspection_date=batch_reports[-1].production_date,
    )


# ─── Compliance Certificate Generator ─────────────────────────────────────────

@dataclass
class ComplianceCertificate:
    """ISO 22000 / SCA-inspired compliance certificate per batch/lot."""
    cert_id: str
    batch_id: str
    lot_id: str
    origin: str
    process_method: str
    variety: str
    harvest_year: int
    supplier: str
    production_date: str
    inspection_date: str
    equipment_id: str
    operator_id: str

    # Compliance checks
    sca_cat1_pass: bool
    sca_cat2_pass: bool
    moisture_in_spec: bool
    density_in_spec: bool
    defect_rate_pass: bool
    recipe_compliant: bool

    # Quantitative values
    sca_eq_defects: float
    moisture_pct: float
    density_g_mL: float
    defect_rate_pct: float
    quality_score: float
    sca_grade: SCAGrade

    # Document references
    audit_report_ref: str = ""
    recipe_ref: str = ""
    calibration_ref: str = ""

    @property
    def overall_compliant(self) -> bool:
        return all([
            self.sca_cat1_pass,
            self.sca_cat2_pass,
            self.moisture_in_spec,
            self.density_in_spec,
            self.defect_rate_pass,
            self.recipe_compliant,
        ])

    @property
    def compliance_rate(self) -> float:
        checks = 6
        passed = sum([
            self.sca_cat1_pass,
            self.sca_cat2_pass,
            self.moisture_in_spec,
            self.density_in_spec,
            self.defect_rate_pass,
            self.recipe_compliant,
        ])
        return passed / checks * 100

    def to_dict(self) -> dict:
        return {
            "cert_id": self.cert_id,
            "batch_id": self.batch_id,
            "lot_id": self.lot_id,
            "origin": self.origin,
            "process_method": self.process_method,
            "variety": self.variety,
            "harvest_year": self.harvest_year,
            "supplier": self.supplier,
            "production_date": self.production_date,
            "inspection_date": self.inspection_date,
            "equipment_id": self.equipment_id,
            "operator_id": self.operator_id,
            "compliance_checks": {
                "sca_cat1_pass": self.sca_cat1_pass,
                "sca_cat2_pass": self.sca_cat2_pass,
                "moisture_in_spec": self.moisture_in_spec,
                "density_in_spec": self.density_in_spec,
                "defect_rate_pass": self.defect_rate_pass,
                "recipe_compliant": self.recipe_compliant,
            },
            "quantitative_values": {
                "sca_eq_defects": round(self.sca_eq_defects, 2),
                "moisture_pct": round(self.moisture_pct, 2),
                "density_g_mL": round(self.density_g_mL, 4),
                "defect_rate_pct": round(self.defect_rate_pct, 3),
                "quality_score": round(self.quality_score, 2),
            },
            "sca_grade": self.sca_grade.value,
            "overall_compliant": self.overall_compliant,
            "compliance_rate_pct": round(self.compliance_rate, 1),
            "document_refs": {
                "audit_report": self.audit_report_ref,
                "recipe": self.recipe_ref,
                "calibration": self.calibration_ref,
            },
        }

    def to_text(self) -> str:
        badge = "✅ COMPLIANT" if self.overall_compliant else "⚠️ CONDITIONAL / NON-COMPLIANT"
        lines = [
            "=" * 70,
            "  COMPLIANCE CERTIFICATE — HUSKY-SORTER-001",
            "=" * 70,
            f"  Certificate ID : {self.cert_id}",
            f"  Batch ID        : {self.batch_id}",
            f"  Lot ID          : {self.lot_id}",
            f"  Issue Date      : {self.inspection_date}",
            "=" * 70,
            "",
            f"  Origin      : {self.origin} ({self.process_method})",
            f"  Variety     : {self.variety} | {self.harvest_year}",
            f"  Supplier    : {self.supplier}",
            f"  Production  : {self.production_date}",
            f"  Equipment   : {self.equipment_id}",
            f"  Operator    : {self.operator_id}",
            "=" * 70,
            "",
            f"  🏷️  Overall Status : {badge}",
            f"  📊 Compliance Rate : {self.compliance_rate:.0f}% (6/6 checks)",
            "",
            "┌─ COMPLIANCE CHECKS ─────────────────────────────────────────────",
            f"│ SCA Category 1 (Primary Defects) : "
            f"{'✅ PASS' if self.sca_cat1_pass else '❌ FAIL'}",
            f"│ SCA Category 2 (≤3 full def/350g): "
            f"{'✅ PASS' if self.sca_cat2_pass else '❌ FAIL'}",
            f"│ Moisture 8-14%                   : "
            f"{'✅ PASS' if self.moisture_in_spec else '❌ FAIL'}",
            f"│ Density ≥0.58 g/mL               : "
            f"{'✅ PASS' if self.density_in_spec else '❌ FAIL'}",
            f"│ Defect Rate ≤ Target            : "
            f"{'✅ PASS' if self.defect_rate_pass else '❌ FAIL'}",
            f"│ Recipe Compliance               : "
            f"{'✅ PASS' if self.recipe_compliant else '❌ FAIL'}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ QUANTITATIVE VALUES ──────────────────────────────────────────",
            f"│ SCA Eq. Full Defects : {self.sca_eq_defects:.2f}",
            f"│ Moisture             : {self.moisture_pct:.2f}%",
            f"│ Density              : {self.density_g_mL:.4f} g/mL",
            f"│ Defect Rate          : {self.defect_rate_pct:.3f}%",
            f"│ Quality Score        : {self.quality_score:.1f}/100",
            f"│ SCA Grade            : {self.sca_grade.value}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "┌─ DOCUMENT REFERENCES ──────────────────────────────────────────",
            f"│ Audit Report : {self.audit_report_ref or 'N/A'}",
            f"│ Recipe       : {self.recipe_ref or 'N/A'}",
            f"│ Calibration  : {self.calibration_ref or 'N/A'}",
            "└────────────────────────────────────────────────────────────────",
            "",
            "  Reference Standard: ISO 22000:2018 / SCA Green Coffee Protocol",
            f"  Certificate ID: {self.cert_id} | Valid for 12 months from issue",
            "=" * 70,
        ]
        return "\n".join(lines)


# ─── Report Generator (Main Orchestrator) ─────────────────────────────────────

class QCAuditReportGenerator:
    """
    Main orchestrator: generate all QC audit documents for a batch.
    """

    def __init__(self, equipment_id: str = "HUSKY-SORTER-001"):
        self.equipment_id = equipment_id

    def generate_audit_report(
        self,
        batch_id: str,
        lot_id: str,
        origin: str,
        process_method: str,
        variety: str,
        harvest_year: int,
        supplier: str,
        recipe_name: str,
        operator_id: str,
        production_date: str,
        shift: str,
        bean_records: List[Dict[str, Any]],
        recipe_targets: Optional[Dict[str, Any]] = None,
    ) -> BatchAuditReport:
        """
        Generate a complete BatchAuditReport from bean record data.

        Args:
            bean_records: List of bean record dicts, each containing:
                - weight_g: float
                - moisture_pct: float
                - density: float
                - color_score: float (0-100)
                - grade: str (A/B/C/R)
                - defects: list of defect type strings

        Returns:
            BatchAuditReport with all computed fields
        """
        if recipe_targets is None:
            recipe_targets = {
                "defect_rate_max_pct": 2.0,
                "moisture_target_pct": 11.0,
                "moisture_tolerance_pct": 2.0,
                "color_score_min": 80.0,
            }

        n = len(bean_records)
        if n == 0:
            raise ValueError("bean_records cannot be empty")

        avg_weight   = sum(r.get("weight_g", 0.12) for r in bean_records) / n
        total_kg     = sum(r.get("weight_g", 0.12) for r in bean_records) / 1000

        weights      = [r.get("weight_g", 0.12) for r in bean_records]
        moistures    = [r.get("moisture_pct", 11.0) for r in bean_records]
        densities    = [r.get("density", 0.68) for r in bean_records]
        color_scores = [r.get("color_score", 85.0) for r in bean_records]

        weight_std   = statistics.stdev(weights) if len(weights) > 1 else 0.0
        weight_cv    = (weight_std / statistics.mean(weights) * 100) if weights else 0.0

        all_defects: Dict[str, int] = {}
        for rec in bean_records:
            for d in rec.get("defects", []):
                d_key = d.lower().replace(" ", "_")
                all_defects[d_key] = all_defects.get(d_key, 0) + 1

        defect_list: List[DefectCount] = []
        primary_total = 0
        secondary_total = 0
        for dtype, cnt in all_defects.items():
            cat, eq = SCA_DEFECT_EQUIVALENTS.get(dtype, (DefectCategory.SECONDARY, 0.5))
            defect_list.append(DefectCount(
                defect_type=dtype,
                category=cat,
                count=cnt,
                eq_full_defects=cnt * eq,
            ))
            if cat == DefectCategory.PRIMARY:
                primary_total += cnt
            else:
                secondary_total += cnt

        total_defects = primary_total + secondary_total
        defect_rate   = total_defects / n * 100

        # Extrapolate to SCA 350g sample: assume avg bean = 0.12g → 2917 beans/350g
        beans_per_350g = 350.0 / max(avg_weight, 0.001)
        sca_eq_350g    = (total_defects / n) * beans_per_350g * sum(
            SCA_DEFECT_EQUIVALENTS.get(d, (None, 0.5))[1]
            for d in all_defects
        ) / len(all_defects) if all_defects else 0.0
        # Simplified: SCA full defects = total_defects * avg_eq
        avg_eq = statistics.mean([
            SCA_DEFECT_EQUIVALENTS.get(d, (None, 0.5))[1]
            for d in all_defects
        ]) if all_defects else 0.0
        sca_eq = (total_defects / n) * beans_per_350g * avg_eq / beans_per_350g
        # Even simpler: scale raw defect rate to 350g
        sca_eq = (defect_rate_pct_to_sca_eq(defect_rate))

        grade_counts = {"A": 0, "B": 0, "C": 0, "R": 0}
        for rec in bean_records:
            g = rec.get("grade", "R")
            if g in grade_counts:
                grade_counts[g] += 1
            else:
                grade_counts["R"] += 1

        weight_summary  = compute_sensor_summary("weight",   weights,   0.10, 0.28)
        moisture_summary= compute_sensor_summary("moisture", moistures, 8.0, 14.0)
        density_summary = compute_sensor_summary("density",  densities, 0.58, 0.78)
        color_summary   = compute_sensor_summary("color",   color_scores, 60.0, 100.0)

        moisture_avg = statistics.mean(moistures)
        density_avg  = statistics.mean(densities)
        color_avg    = statistics.mean(color_scores)

        quality_score, _ = compute_quality_score(
            defect_rate_pct=defect_rate,
            moisture_pct=moisture_avg,
            color_score=color_avg,
            density=density_avg,
            weight_cv_pct=weight_cv,
        )
        sca_pass       = sca_eq <= 3.0
        comp_status    = compute_compliance_status(
            defect_rate, moisture_avg, sca_pass, primary_total,
        )
        sca_grade       = compute_sca_grade(quality_score)

        # Generate findings
        report_base = BatchAuditReport(
            audit_id=f"AUD-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            batch_id=batch_id, lot_id=lot_id, origin=origin,
            process_method=process_method, variety=variety,
            harvest_year=harvest_year, supplier=supplier,
            audit_timestamp=datetime.now(timezone.utc).isoformat(),
            production_date=production_date, shift=shift,
            operator_id=operator_id, equipment_id=self.equipment_id,
            recipe_name=recipe_name,
            total_beans_processed=n, total_kg_processed=total_kg,
            grade_a_count=grade_counts["A"], grade_b_count=grade_counts["B"],
            grade_c_count=grade_counts["C"], grade_reject_count=grade_counts["R"],
            grade_a_pct=grade_counts["A"]/n*100, grade_b_pct=grade_counts["B"]/n*100,
            grade_c_pct=grade_counts["C"]/n*100, grade_reject_pct=grade_counts["R"]/n*100,
            defects=defect_list,
            total_primary_defects=primary_total,
            total_secondary_defects=secondary_total,
            sca_eq_full_defects=sca_eq,
            weight_summary=weight_summary,
            moisture_summary=moisture_summary,
            density_summary=density_summary,
            color_summary=color_summary,
            compliance_status=comp_status,
            sca_grade=sca_grade,
            quality_score=quality_score,
            defect_rate_pct=defect_rate,
            moisture_pct_avg=moisture_avg,
            density_avg=density_avg,
            color_score_avg=color_avg,
            findings=[],
        )

        findings = generate_audit_findings(report_base, recipe_targets)
        report_base.findings.extend(findings)

        return report_base

    def generate_certificate(
        self,
        report: BatchAuditReport,
        audit_report_id: str = "",
        recipe_ref: str = "",
        calibration_ref: str = "",
    ) -> ComplianceCertificate:
        """Generate a compliance certificate from an audit report."""
        return ComplianceCertificate(
            cert_id=f"CERT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            batch_id=report.batch_id,
            lot_id=report.lot_id,
            origin=report.origin,
            process_method=report.process_method,
            variety=report.variety,
            harvest_year=report.harvest_year,
            supplier=report.supplier,
            production_date=report.production_date,
            inspection_date=report.audit_timestamp[:10],
            equipment_id=report.equipment_id,
            operator_id=report.operator_id,
            sca_cat1_pass=report.total_primary_defects == 0,
            sca_cat2_pass=report.sca_eq_full_defects <= 3.0,
            moisture_in_spec=8.0 <= report.moisture_pct_avg <= 14.0,
            density_in_spec=0.58 <= report.density_avg <= 0.78,
            defect_rate_pass=report.defect_rate_pct <= 10.0,
            recipe_compliant=(
                report.compliance_status == ComplianceStatus.COMPLIANT
                or report.compliance_status == ComplianceStatus.CONDITIONAL
            ),
            sca_eq_defects=report.sca_eq_full_defects,
            moisture_pct=report.moisture_pct_avg,
            density_g_mL=report.density_avg,
            defect_rate_pct=report.defect_rate_pct,
            quality_score=report.quality_score,
            sca_grade=report.sca_grade,
            audit_report_ref=audit_report_id or report.audit_id,
            recipe_ref=recipe_ref,
            calibration_ref=calibration_ref,
        )

    def generate_sca_grade_sheet(
        self,
        report: BatchAuditReport,
    ) -> SCABeanGradeSheet:
        """Generate an SCA pre-cupping grade sheet from a batch audit report."""
        all_defect_list = [d.defect_type for d in report.defects if d.count > 0]

        primary_count = report.total_primary_defects
        secondary_count = report.total_secondary_defects

        base_cupping = 7.5
        if report.sca_eq_full_defects <= 3.0:
            base_cupping += 1.0
        if report.moisture_pct_avg and 10.0 <= report.moisture_pct_avg <= 12.0:
            base_cupping += 0.3

        return SCABeanGradeSheet(
            certificate_id=f"SCA-{report.batch_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            lot_id=report.lot_id,
            origin=report.origin,
            process_method=report.process_method,
            variety=report.variety,
            harvest_year=report.harvest_year,
            supplier=report.supplier,
            grading_date=report.audit_timestamp[:10],
            graded_by=report.operator_id,
            total_beans_graded=report.total_beans_processed,
            sca_eq_full_defects=report.sca_eq_full_defects,
            moisture_pct=report.moisture_pct_avg or 11.0,
            density_g_mL=report.density_avg or 0.68,
            screen_size_majority="15",
            color_uniformity="good",
            estimated_aroma_score=base_cupping,
            estimated_flavor_score=base_cupping,
            estimated_acidity_score=base_cupping + (0.3 if "Washed" in report.process_method else -0.2),
            estimated_body_score=base_cupping + (0.2 if "Natural" in report.process_method else 0.0),
            estimated_balance_score=base_cupping,
            estimated_overall_score=base_cupping - (report.sca_eq_full_defects * 0.1),
            defects_found=all_defect_list[:10],
            primary_defect_count=primary_count,
            secondary_defect_count=secondary_count,
            origin_aroma_notes=self._origin_aroma_notes(report.origin),
            origin_process_characteristics=self._origin_process_notes(report.origin, report.process_method),
        )

    def _origin_aroma_notes(self, origin: str) -> str:
        notes = {
            "Ethiopian": "Blueberry, jasmine, citrus",
            "Kenyan": "Blackcurrant, tomato, bright acidity",
            "Brazilian": "Chocolate, nuts, low acidity",
            "Colombian": "Caramel, red fruit, balanced",
            "Costa_Rican": "Honey, bright, clean",
            "Guatemalan": "Chocolate, spice, structured",
            "Yemen": "Winey, complex, rare",
        }
        for key, note in notes.items():
            if key in origin:
                return note
        return "Complex, origin-characteristic"

    def _origin_process_notes(self, origin: str, process: str) -> str:
        if "Washed" in process:
            return "Clean, bright, tea-like body"
        elif "Natural" in process:
            return "Heavy body, fruit-forward, complex"
        elif "Honey" in process:
            return "Sweet, balanced, medium body"
        return "Origin-typical processing"


def defect_rate_pct_to_sca_eq(defect_rate_pct: float) -> float:
    """
    Convert batch defect rate % to SCA equivalent full defects per 350g sample.
    Assumes avg bean weight = 0.12g, so 350g ≈ 2917 beans.
    """
    beans_per_sample = 350.0 / 0.12  # ≈ 2917
    # Defect rate % means N defects per 100 beans
    # SCA defect count per sample = defect_rate_pct * (beans_per_sample / 100)
    # But SCA weights by severity (full defect equivalent)
    # Approximate: divide by 100 to get fraction, multiply by beans per sample
    # then divide by ~10 for full-defect weighting (crude approximation)
    return defect_rate_pct * beans_per_sample / 100 * 0.1


# ─── CLI Demo ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random
    import os

    print("\n" + "=" * 60)
    print("  HUSKY-SORTER-001  —  QC AUDIT SYSTEM  DEMO")
    print("=" * 60 + "\n")

    # Simulate 3000 bean records for a Ethiopian Washed batch
    origins = [
        ("Ethiopian_Yirgacheffe", "Washed", "Heirloom", 2025, "Sidama Cooperative"),
        ("Kenyan_Kirinyaga", "Washed", "SL28/SL34", 2025, "Kii Factory Ltd"),
        ("Brazilian_Cerrado", "Natural", "Catuai", 2025, "Fazenda Nossa Senhora"),
        ("Colombian_Huila", "Washed", "Caturra", 2025, "Finca El Paraiso"),
    ]

    gen = QCAuditReportGenerator()

    for origin, process, variety, harvest, supplier in origins:
        # Simulate bean records with ~5% defect rate
        bean_records = []
        defect_types = ["broken", "underdev", "fermented", "underweight", "mold",
                        "black", "hollow", "overdry", "overwet", "insect"]

        for i in range(3000):
            is_defect = random.random() < 0.05
            defects = []
            if is_defect:
                defects = [random.choice(defect_types)]

            weight = random.gauss(0.152, 0.015)
            weight = max(0.05, min(0.35, weight))

            bean_records.append({
                "weight_g": round(weight, 4),
                "moisture_pct": round(random.gauss(11.0, 0.5), 2),
                "density": round(random.gauss(0.68, 0.03), 4),
                "color_score": round(random.gauss(85.0, 5.0), 1),
                "grade": random.choices(["A", "B", "C", "R"], weights=[75, 15, 7, 3])[0],
                "defects": defects,
            })

        # Generate audit report
        report = gen.generate_audit_report(
            batch_id=f"BATCH-{origin[:3].upper()}-{random.randint(1000,9999)}",
            lot_id=f"LOT-{origin[:3].upper()}-2025",
            origin=origin,
            process_method=process,
            variety=variety,
            harvest_year=harvest,
            supplier=supplier,
            recipe_name=f"{origin}_{process}",
            operator_id="OPERATOR-001",
            production_date="2026-05-12",
            shift="Morning",
            bean_records=bean_records,
        )
        print(f"  {origin}: {len(bean_records)} beans, "
              f"Grade A: {report.grade_a_pct:.1f}%, "
              f"Defect rate: {report.defect_rate_pct:.2f}%, "
              f"SCA Grade: {report.sca_grade.value}")
        print(f"    SCA EQ Full Defects: {report.sca_eq_full_defects:.1f}/350g, "
              f"Quality Score: {report.quality_score}/100")

        # Generate compliance certificate
        cert = gen.generate_certificate(report)
        overall = "PASS" if cert.overall_compliant else "FAIL"
        print(f"    Compliance: {overall} ({cert.compliance_rate:.0f}%), "
              f"Cert: {cert.cert_id}")

        # Generate SCA grade sheet
        sca_sheet = gen.generate_sca_grade_sheet(report)
        print(f"    SCA Score: {sca_sheet.preliminary_points:.1f}/100 "
              f"({'Exceeds SCA Specialty Grade' if sca_sheet.sca_pass else 'Below Specialty Threshold'})")

        print()

print("=" * 60)
print("  All 4 origins processed successfully.")
print("=" * 60)
