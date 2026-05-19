# sorter/db/report_generator.py
# Batch report generator for HUSKY-SORTER-001
# Generates JSON / CSV / Text reports for batch analysis and traceability
# Author: Little Husky 🐕 | Date: 2026-05-02

import csv
import io
import json
import logging
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .database import Database
from .models import BeanDefect, BatchRecord, BatchState, SortGrade

logger = logging.getLogger(__name__)


# ─── P2-07: clean defect key → label resolution ──────────────────────────────

def _defect_key_to_label(key: str) -> str:
    """Resolve a defect key from JSON storage to a human-readable label.

    Handles integer keys ("1" → "Moldy") and enum-name keys ("MOLDY" → "Moldy").
    Returns the raw key as fallback and logs a warning for unknown keys.
    """
    # Integer key (JSON stores all dict keys as strings)
    if key.isdigit():
        try:
            return BeanDefect(int(key)).label
        except ValueError:
            pass

    # Exact enum name match
    name = key.upper()
    if hasattr(BeanDefect, name):
        return BeanDefect[name].label

    # Unknown key — log and return as-is
    logger.warning("Unknown defect key in report: %r", key)
    return key


# ─── Report Types ────────────────────────────────────────────────────────────

class ReportFormat:
    JSON = "json"
    CSV = "csv"
    TEXT = "text"


# ─── Main Report Generator ───────────────────────────────────────────────────

class BatchReportGenerator:
    """
    Generate comprehensive batch reports in multiple formats.
    Supports: JSON (machine-readable), CSV (spreadsheet), TEXT (human-readable).
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # ─── JSON Report ──────────────────────────────────────────────────────────

    def generate_json(
        self,
        batch_id: str,
        include_beans: bool = False,
        include_events: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a full JSON report for a batch.

        Args:
            batch_id: The batch to report on
            include_beans: Whether to include per-bean records (can be large)
            include_events: Whether to include system events for this batch's time window
        """
        batch = self.db.get_batch(batch_id)
        if not batch:
            return {"error": f"Batch {batch_id} not found"}

        report = {
            "report_type": "batch_report",
            "report_version": "1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "batch": batch.to_dict(),
        }

        # Compute grade yield
        total = batch.grade_a_count + batch.grade_b_count + batch.grade_c_count + batch.grade_reject_count
        report["grade_yield"] = {
            "A": round(batch.grade_a_count / total * 100, 1) if total else 0,
            "B": round(batch.grade_b_count / total * 100, 1) if total else 0,
            "C": round(batch.grade_c_count / total * 100, 1) if total else 0,
            "reject": round(batch.grade_reject_count / total * 100, 1) if total else 0,
        }

        # Defect breakdown (P2-07: simplified key resolution)
        defect_counts = json.loads(batch.defect_counts_json or "{}")
        report["defect_distribution"] = {}
        for k, v in defect_counts.items():
            label = _defect_key_to_label(k)
            report["defect_distribution"][label] = v

        if include_beans:
            beans = self.db.get_beans_for_batch(batch_id)
            report["beans"] = [b.to_dict() for b in beans]

        if include_events and batch.started_at_utc:
            events = self.db.get_events(since_utc=batch.started_at_utc, limit=500)
            report["system_events"] = [e.to_dict() for e in events]

        # Quality assessment
        report["quality_assessment"] = self._quality_assessment(batch)

        return report

    def _quality_assessment(self, batch: BatchRecord) -> Dict[str, Any]:
        """Assess overall quality grade for the batch."""
        assessment = {"pass": True, "warnings": [], "critical": []}

        # Defect rate check
        defect_rate = batch.defect_rate_pct()
        if defect_rate > 10:
            assessment["pass"] = False
            assessment["critical"].append(
                f"Defect rate {defect_rate:.1f}% exceeds 10% threshold"
            )
        elif defect_rate > 5:
            assessment["warnings"].append(
                f"Defect rate {defect_rate:.1f}% above typical (<5%)"
            )

        # Grade A yield
        grade_a_yield = batch.grade_yield_pct(SortGrade.GRADE_A)
        if grade_a_yield < 60:
            assessment["pass"] = False
            assessment["critical"].append(
                f"Grade A yield {grade_a_yield:.1f}% below 60% minimum"
            )
        elif grade_a_yield < 75:
            assessment["warnings"].append(
                f"Grade A yield {grade_a_yield:.1f}% below optimal (>75%)"
            )

        # Throughput
        throughput = batch.throughput_kg_h()
        if throughput < batch.target_throughput_kg_h * 0.8:
            assessment["warnings"].append(
                f"Throughput {throughput:.2f}kg/h below 80% of target "
                f"({batch.target_throughput_kg_h}kg/h)"
            )

        # Moisture
        if batch.avg_moisture_pct > 12.5:
            assessment["warnings"].append(
                f"Avg moisture {batch.avg_moisture_pct:.1f}% above optimal (10-12%)"
            )
        elif batch.avg_moisture_pct < 9:
            assessment["warnings"].append(
                f"Avg moisture {batch.avg_moisture_pct:.1f}% below optimal (10-12%)"
            )

        return assessment

    # ─── CSV Export ────────────────────────────────────────────────────────────

    def generate_csv(
        self,
        batch_id: str,
        include_sensor_data: bool = True,
    ) -> str:
        """
        Export all beans in a batch as CSV.
        Returns CSV as a string.
        """
        batch = self.db.get_batch(batch_id)
        if not batch:
            return f"ERROR: Batch {batch_id} not found"

        beans = self.db.get_beans_for_batch(batch_id, limit=50000)

        output = io.StringIO()
        headers = [
            "bean_id", "batch_id", "timestamp_utc", "channel", "bean_index",
            "primary_defect", "defect_label", "secondary_defect",
            "ml_confidence", "quality_score", "grade", "grade_label",
            "assigned_bin", "ejected", "eject_reason",
        ]
        if include_sensor_data:
            headers += [
                "weight_g", "moisture_pct", "density_gcc", "size_mm",
                "color_top_L", "color_top_a", "color_top_b",
                "color_bottom_L", "color_bottom_a", "color_bottom_b",
            ]

        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()

        for bean in beans:
            row = bean.to_dict()
            row["defect_label"] = BeanDefect(bean.primary_defect).label
            row["grade_label"] = SortGrade(bean.grade).name
            row["ejected"] = "YES" if bean.ejected else "NO"
            if include_sensor_data:
                sensors = bean.sensors
                row["weight_g"] = sensors.weight_g
                row["moisture_pct"] = sensors.moisture_pct
                row["density_gcc"] = sensors.density_gcc
                row["size_mm"] = sensors.size_mm
                color = sensors.color
                if color:
                    row["color_top_L"] = color.top_L
                    row["color_top_a"] = color.top_a
                    row["color_top_b"] = color.top_b
                    row["color_bottom_L"] = color.bottom_L
                    row["color_bottom_a"] = color.bottom_a
                    row["color_bottom_b"] = color.bottom_b
                else:
                    row["color_top_L"] = ""
                    row["color_top_a"] = ""
                    row["color_top_b"] = ""
                    row["color_bottom_L"] = ""
                    row["color_bottom_a"] = ""
                    row["color_bottom_b"] = ""
            writer.writerow(row)

        return output.getvalue()

    # ─── Text Report ───────────────────────────────────────────────────────────

    def generate_text(self, batch_id: str, safe_ascii: bool = False) -> str:
        """
        Generate a human-readable text report for printing or display.

        Args:
            batch_id: The batch to report on
            safe_ascii: P3-06: if True, strip emojis for safe export (CSV, legacy encodings)
        """
        batch = self.db.get_batch(batch_id)
        if not batch:
            return f"ERROR: Batch {batch_id} not found"

        beans = self.db.get_beans_for_batch(batch_id, limit=100000)
        defect_counts = Counter(b.primary_defect for b in beans)
        grade_counts = Counter(b.grade for b in beans)
        total = len(beans) or 1

        quality = self._quality_assessment(batch)

        # ── Header ────────────────────────────────────────────────────────────
        lines = [
            "=" * 70,
            "        HUSKY-SORTER-001  BATCH QUALITY REPORT",
            "=" * 70,
            "",
            f"  Batch ID        : {batch.batch_id}",
            f"  Origin          : {batch.origin or 'N/A'}",
            f"  Variety         : {batch.variety or 'N/A'}",
            f"  Process         : {batch.process or 'N/A'}",
            f"  Lot Number      : {batch.lot_number or 'N/A'}",
            f"  State           : {BatchState(batch.state).name}",
            f"  Started         : {batch.started_at_utc}",
            f"  Ended           : {batch.ended_at_utc or 'In Progress'}",
            f"  Duration        : {batch.duration_s():.1f}s ({batch.duration_s()/60:.1f} min)",
            f"  Channels Used   : {batch.channels_used}",
            "",
            "-" * 70,
            "  PRODUCTION SUMMARY",
            "-" * 70,
            f"  Total Beans     : {batch.total_beans:,}",
            f"  Total Weight    : {batch.total_weight_g:.1f}g ({batch.total_weight_g/1000:.3f}kg)",
            f"  Defective Beans : {batch.defective_beans:,} ({batch.defect_rate_pct():.1f}%)",
            f"  Ejected Beans   : {batch.ejected_beans:,}",
            f"  Throughput      : {batch.throughput_kg_h():.3f} kg/h (target: {batch.target_throughput_kg_h} kg/h)",
            "",
            "-" * 70,
            "  GRADE DISTRIBUTION",
            "-" * 70,
            f"  Grade A (Premium) : {batch.grade_a_count:>6,}  ({batch.grade_yield_pct(SortGrade.GRADE_A):>5.1f}%)",
            f"  Grade B (Standard): {batch.grade_b_count:>6,}  ({batch.grade_yield_pct(SortGrade.GRADE_B):>5.1f}%)",
            f"  Grade C (Below Std):{batch.grade_c_count:>6,}  ({batch.grade_yield_pct(SortGrade.GRADE_C):>5.1f}%)",
            f"  Reject (Defective):{batch.grade_reject_count:>6,}  ({batch.grade_yield_pct(SortGrade.REJECT):>5.1f}%)",
            "",
            "-" * 70,
            "  DEFECT BREAKDOWN",
            "-" * 70,
        ]

        # Sort defects by count descending
        # P3-06: use ASCII-safe icons when safe_ascii=True
        if safe_ascii:
            sev_map = {4: "[CRIT]", 3: "[MAJ]", 2: "[MIN]", 1: "[INF]"}
            bar_char = "#"
        else:
            sev_map = {4: "🔴", 3: "🟠", 2: "🟡", 1: "⚪"}
            bar_char = "█"

        for defect_id, count in sorted(defect_counts.items(), key=lambda x: -x[1]):
            defect = BeanDefect(defect_id)
            pct = count / total * 100
            bar = bar_char * int(pct / 2)
            sev = sev_map.get(defect.severity, sev_map.get(1, "?"))
            lines.append(f"  {sev} {defect.label:<18}: {count:>6,}  ({pct:>5.1f}%)  {bar}")

        lines += [
            "",
            "-" * 70,
            "  QUALITY METRICS (AVERAGES)",
            "-" * 70,
            f"  Quality Score   : {batch.avg_quality_score:.1f} / 100",
            f"  Bean Weight     : {batch.avg_weight_g:.2f}g",
            f"  Moisture        : {batch.avg_moisture_pct:.2f}%",
            f"  Density         : {batch.avg_density_gcc:.3f} g/cc",
            f"  Color L*        : {batch.avg_color_L:.1f}",
        ]

        if quality["critical"] or quality["warnings"]:
            lines += [
                "",
                "-" * 70,
                "  QUALITY ASSESSMENT",
                "-" * 70,
            ]
            status = ("PASS" if quality["pass"] else "FAIL") if safe_ascii else ("✅ PASS" if quality["pass"] else "❌ FAIL")
            lines.append(f"  Overall Status  : {status}")
            warn_prefix = "!! " if safe_ascii else "⚠ "
            crit_prefix = ">> " if safe_ascii else "🔴 "
            for w in quality["warnings"]:
                lines.append(f"  {warn_prefix}{w}")
            for c in quality["critical"]:
                lines.append(f"  {crit_prefix}{c}")

        lines += [
            "",
            "-" * 70,
            "  OPERATOR NOTES",
            "-" * 70,
            f"  {batch.operator_notes or '(no notes)'}",
            "",
            "=" * 70,
            f"  Report generated: {datetime.now(timezone.utc).isoformat()}",
            f"  HUSKY-SORTER-001 | {batch.batch_id}",
            "=" * 70,
        ]

        return "\n".join(lines)

    # ─── Multi-Batch Summary Report ───────────────────────────────────────────

    def generate_multi_batch_summary(
        self,
        origin: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """
        Generate a summary report across multiple recent batches.
        Useful for daily/weekly quality reviews.
        """
        batches = self.db.list_batches(
            state=BatchState.COMPLETED.value,
            origin=origin,
            limit=limit,
        )

        if not batches:
            return {"error": "No completed batches found", "batches": []}

        total_beans = sum(b.total_beans for b in batches)
        total_defective = sum(b.defective_beans for b in batches)
        total_weight = sum(b.total_weight_g for b in batches)
        total_duration = sum(b.duration_s() for b in batches)

        # Weighted average quality
        weighted_score = sum(b.avg_quality_score * b.total_beans for b in batches)
        avg_score = weighted_score / total_beans if total_beans else 0

        # Aggregate defect distribution
        all_defects: Counter = Counter()
        for batch in batches:
            counts = json.loads(batch.defect_counts_json or "{}")
            all_defects.update({int(k): v for k, v in counts.items()})

        # Grade totals
        grade_a = sum(b.grade_a_count for b in batches)
        grade_b = sum(b.grade_b_count for b in batches)
        grade_c = sum(b.grade_c_count for b in batches)
        grade_r = sum(b.grade_reject_count for b in batches)
        grade_total = grade_a + grade_b + grade_c + grade_r or 1

        report = {
            "report_type": "multi_batch_summary",
            "report_version": "1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "filter": {"origin": origin, "limit": limit},
            "batches_included": len(batches),
            "total_beans": total_beans,
            "total_defective": total_defective,
            "overall_defect_rate_pct": round(total_defective / total_beans * 100, 2) if total_beans else 0,
            "total_weight_kg": round(total_weight / 1000, 3),
            "total_duration_h": round(total_duration / 3600, 2),
            "avg_throughput_kg_h": round(
                (total_weight / 1000) / (total_duration / 3600), 3
            ) if total_duration > 0 else 0,
            "weighted_avg_quality_score": round(avg_score, 1),
            "grade_yield": {
                "A": round(grade_a / grade_total * 100, 1),
                "B": round(grade_b / grade_total * 100, 1),
                "C": round(grade_c / grade_total * 100, 1),
                "reject": round(grade_r / grade_total * 100, 1),
            },
            "defect_distribution": {
                BeanDefect(k).label: v for k, v in all_defects.most_common(10)
            },
            "batch_summaries": [
                {
                    "batch_id": b.batch_id,
                    "origin": b.origin,
                    "total_beans": b.total_beans,
                    "defect_rate_pct": round(b.defect_rate_pct(), 2),
                    "grade_a_yield_pct": round(b.grade_yield_pct(SortGrade.GRADE_A), 1),
                    "throughput_kg_h": round(b.throughput_kg_h(), 3),
                    "avg_quality_score": round(b.avg_quality_score, 1),
                    "started_at_utc": b.started_at_utc,
                }
                for b in batches
            ],
        }

        return report

    # ─── Save to file ─────────────────────────────────────────────────────────

    def save_report(
        self,
        batch_id: str,
        output_dir: str,
        fmt: str = ReportFormat.JSON,
        include_beans: bool = False,
    ) -> Tuple[str, str]:
        """
        Generate and save a report to a file.
        Returns (filepath, summary_line).
        """
        batch = self.db.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        base_name = f"batch_report_{batch_id[:8]}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        if fmt == ReportFormat.JSON:
            data = self.generate_json(batch_id, include_beans=include_beans)
            filepath = Path(output_dir) / f"{base_name}.json"
            content = json.dumps(data, indent=2, ensure_ascii=False)
        elif fmt == ReportFormat.CSV:
            content = self.generate_csv(batch_id)
            filepath = Path(output_dir) / f"{base_name}.csv"
        else:  # TEXT
            content = self.generate_text(batch_id)
            filepath = Path(output_dir) / f"{base_name}.txt"

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

        summary = (
            f"[{fmt.upper()}] {filepath.name} — "
            f"{batch.total_beans} beans, "
            f"{batch.defect_rate_pct():.1f}% defects, "
            f"Grade A: {batch.grade_yield_pct(SortGrade.GRADE_A):.1f}%"
        )
        return str(filepath), summary
