#!/usr/bin/env python3
# sorter/db/demo_batch_runner.py
# Demo: simulate a full batch run → save to DB → generate all reports
# Validates the database layer + report generator end-to-end
# Author: Little Husky 🐕 | Date: 2026-05-02

import json
import random
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sorter.db.database import Database
from sorter.db.models import (
    BeanDefect, BeanRecord, BatchRecord, BatchState, CalibrationRecord,
    ColorReading, SensorSnapshot, SortGrade, SystemEvent,
)
from sorter.db.report_generator import BatchReportGenerator


# ─── Deterministic simulation helpers ────────────────────────────────────────

BEAN_COUNT = 3000         # Simulate 3000 beans per batch (~1.2kg @ 0.4g/bean)
DEFECT_RATE = 0.07        # 7% defect rate
CHANNEL = 1

DEFECT_WEIGHTS = {
    BeanDefect.NORMAL: 93,
    BeanDefect.MOLDY: 1,
    BeanDefect.FERMENTED: 0.8,
    BeanDefect.BLACK: 0.5,
    BeanDefect.BROKEN: 1.5,
    BeanDefect.FOREIGN: 0.3,
    BeanDefect.UNDERWEIGHT: 0.8,
    BeanDefect.OVERWEIGHT: 0.5,
    BeanDefect.STUNTED: 0.6,
    BeanDefect.DEAD: 0.4,
    BeanDefect.INSECT_DAMAGED: 0.3,
    BeanDefect.HOLLOW: 0.2,
    BeanDefect.OVER_DRY: 0.05,
    BeanDefect.OVER_WET: 0.05,
}


def pick_defect() -> int:
    defect_ids, weights = zip(*DEFECT_WEIGHTS.items())
    return random.choices(defect_ids, weights=weights, k=1)[0].value


def make_bean(batch_id: str, index: int, channel: int = 1) -> BeanRecord:
    defect_id = pick_defect()
    defect = BeanDefect(defect_id)

    # Physical parameters vary by defect type
    if defect == BeanDefect.NORMAL:
        weight = random.gauss(0.42, 0.06)
        moisture = random.gauss(11.0, 1.0)
        density = random.gauss(0.72, 0.04)
        size_mm = random.gauss(15.5, 1.2)
        top_L = random.gauss(48, 5)
    elif defect == BeanDefect.MOLDY:
        weight = random.gauss(0.38, 0.07)
        moisture = random.gauss(14.5, 1.5)
        density = random.gauss(0.65, 0.05)
        size_mm = random.gauss(14.0, 1.5)
        top_L = random.gauss(52, 6)
    elif defect == BeanDefect.FERMENTED:
        weight = random.gauss(0.36, 0.08)
        moisture = random.gauss(13.0, 2.0)
        density = random.gauss(0.68, 0.05)
        size_mm = random.gauss(14.5, 1.5)
        top_L = random.gauss(38, 6)
    elif defect == BeanDefect.BLACK:
        weight = random.gauss(0.30, 0.06)
        moisture = random.gauss(10.0, 2.0)
        density = random.gauss(0.80, 0.06)
        size_mm = random.gauss(13.0, 1.5)
        top_L = random.gauss(18, 4)
    elif defect == BeanDefect.BROKEN:
        weight = random.gauss(0.25, 0.06)
        moisture = random.gauss(10.5, 1.0)
        density = random.gauss(0.72, 0.05)
        size_mm = random.gauss(11.0, 1.5)
        top_L = random.gauss(46, 5)
    else:
        weight = random.gauss(0.38, 0.10)
        moisture = random.gauss(11.0, 2.0)
        density = random.gauss(0.71, 0.06)
        size_mm = random.gauss(14.0, 2.0)
        top_L = random.gauss(45, 8)

    weight = max(0.05, weight)
    moisture = max(4.0, min(20.0, moisture))
    density = max(0.50, min(0.95, density))
    size_mm = max(8.0, min(20.0, size_mm))
    top_L = max(10.0, min(75.0, top_L))

    color = ColorReading(
        top_L=top_L,
        top_a=random.gauss(12, 3),
        top_b=random.gauss(24, 5),
        bottom_L=top_L * random.uniform(0.92, 1.08),
        bottom_a=random.gauss(12, 3),
        bottom_b=random.gauss(24, 5),
    )
    sensors = SensorSnapshot(
        weight_g=round(weight, 3),  # grams (typical arabica: 0.1-0.5g)
        moisture_pct=round(moisture, 2),
        density_gcc=round(density, 4),
        size_mm=round(size_mm, 1),
        color=color,
    )

    # Quality score: 100 base, deductions per defect severity
    quality_score = 100.0 - (defect.severity * 10) - random.uniform(0, 5)
    quality_score = max(0.0, min(100.0, quality_score))

    # Grade
    if quality_score >= 85:
        grade = SortGrade.GRADE_A.value
    elif quality_score >= 70:
        grade = SortGrade.GRADE_B.value
    elif quality_score >= 50:
        grade = SortGrade.GRADE_C.value
    else:
        grade = SortGrade.REJECT.value

    # Bin routing
    ejected = defect_id != BeanDefect.NORMAL.value
    bin_map = {
        SortGrade.GRADE_A.value: "A1",
        SortGrade.GRADE_B.value: "A2",
        SortGrade.GRADE_C.value: "A3",
        SortGrade.REJECT.value: "BF",
    }
    assigned_bin = bin_map.get(grade, "A1")

    timestamp = datetime.now(timezone.utc).isoformat()

    return BeanRecord(
        bean_id=str(uuid.uuid4()),
        batch_id=batch_id,
        timestamp_utc=timestamp,
        channel=channel,
        bean_index=index,
        sensors=sensors,
        primary_defect=defect_id,
        secondary_defect=0,
        ml_confidence=round(random.uniform(0.82, 0.99), 4),
        quality_score=round(quality_score, 1),
        grade=grade,
        assigned_bin=assigned_bin,
        ejected=ejected,
        eject_reason=defect.label if ejected else "",
    )


def compute_batch_summary(beans: list) -> dict:
    """Compute aggregated summary fields from bean list."""
    total = len(beans)
    if total == 0:
        return {}

    defect_counter = Counter(b.primary_defect for b in beans)
    grade_counter = Counter(b.grade for b in beans)

    total_weight = sum(b.sensors.weight_g for b in beans)
    avg_weight = total_weight / total
    avg_moisture = sum(b.sensors.moisture_pct for b in beans) / total
    avg_density = sum(b.sensors.density_gcc for b in beans) / total

    color_Ls = [b.sensors.color.top_L for b in beans if b.sensors.color]
    avg_color_L = sum(color_Ls) / len(color_Ls) if color_Ls else 0

    eject_reasons = Counter(b.eject_reason for b in beans if b.eject_reason)

    return {
        "total_beans": total,
        "defective_beans": sum(1 for b in beans if b.is_defective()),
        "ejected_beans": sum(1 for b in beans if b.ejected),
        "total_weight_g": round(total_weight, 2),
        "grade_a_count": grade_counter.get(SortGrade.GRADE_A.value, 0),
        "grade_b_count": grade_counter.get(SortGrade.GRADE_B.value, 0),
        "grade_c_count": grade_counter.get(SortGrade.GRADE_C.value, 0),
        "grade_reject_count": grade_counter.get(SortGrade.REJECT.value, 0),
        "defect_counts_json": json.dumps({str(k): v for k, v in defect_counter.items()}),
        "avg_quality_score": round(sum(b.quality_score for b in beans) / total, 1),
        "avg_weight_g": round(avg_weight, 2),
        "avg_moisture_pct": round(avg_moisture, 2),
        "avg_density_gcc": round(avg_density, 4),
        "avg_color_L": round(avg_color_L, 2),
        "eject_reasons_json": json.dumps(dict(eject_reasons)),
    }


# ─── Main demo ────────────────────────────────────────────────────────────────

def run_demo(num_batches: int = 3):
    print("🌱 HUSKY-SORTER-001 — Batch Data Simulation Demo")
    print("=" * 60)

    db = Database()
    gen = BatchReportGenerator(db)

    # Seed RNG for reproducibility
    random.seed(42)

    origins = ["Ethiopia Yirgacheffe", "Colombia Huila", "Kenya AA"]
    varieties = ["Heirloom", "Caturra", "SL28/SL34"]
    processes = ["Washed", "Natural", "Honey"]

    batch_ids = []

    for i in range(num_batches):
        batch_id = str(uuid.uuid4())
        batch_ids.append(batch_id)
        started = datetime.now(timezone.utc) - timedelta(minutes=15)
        ended = datetime.now(timezone.utc)

        origin = origins[i % len(origins)]
        variety = varieties[i % len(varieties)]
        process = processes[i % len(processes)]

        print(f"\n📦 Batch {i+1}/{num_batches}: {batch_id[:12]}... ({origin})")
        print(f"   Simulating {BEAN_COUNT} beans...")

        # Create batch record
        batch = BatchRecord(
            batch_id=batch_id,
            started_at_utc=started.isoformat(),
            ended_at_utc=ended.isoformat(),
            state=BatchState.COMPLETED.value,
            target_weight_g=250.0,
            target_throughput_kg_h=2.0,
            channels_used=1,
            origin=origin,
            variety=variety,
            process=process,
            lot_number=f"LOT-2026-{i+1:04d}",
            operator_notes="Demo batch — auto-generated",
        )

        # Simulate beans
        beans = [make_bean(batch_id, idx) for idx in range(BEAN_COUNT)]

        # Save batch first
        db.insert_batch(batch)

        # Save beans in bulk
        db.insert_beans_bulk(beans)
        print(f"   ✅ Saved {len(beans)} bean records")

        # Compute and update summary
        summary = compute_batch_summary(beans)
        summary["ended_at_utc"] = ended.isoformat()
        db.update_batch_summary(batch_id, **summary)

        # Log a system event
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            severity="INFO",
            component="sorter",
            message=f"Batch {batch_id[:8]} completed",
            details_json=json.dumps({"total_beans": len(beans), "defect_rate": summary["defective_beans"] / len(beans) * 100}),
        )
        db.insert_event(event)

        # Show quick summary
        defect_rate = summary["defective_beans"] / len(beans) * 100
        grade_a_pct = summary["grade_a_count"] / len(beans) * 100
        print(f"   📊 {summary['total_beans']} beans | {defect_rate:.1f}% defects | "
              f"Grade A: {grade_a_pct:.1f}% | Weight: {summary['total_weight_g']:.1f}g")

    # ── Generate reports ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📄 Generating reports...")

    report_dir = Path.home() / ".husky_sorter" / "demo_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    for batch_id in batch_ids:
        batch = db.get_batch(batch_id)

        # TEXT report
        text = gen.generate_text(batch_id)
        txt_path = report_dir / f"{batch_id[:8]}_report.txt"
        txt_path.write_text(text, encoding="utf-8")
        print(f"  ✅ TEXT: {txt_path.name}")

        # JSON report
        json_data = gen.generate_json(batch_id)
        json_path = report_dir / f"{batch_id[:8]}_report.json"
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✅ JSON: {json_path.name}")

    # Multi-batch summary
    summary_report = gen.generate_multi_batch_summary(limit=num_batches)
    summary_path = report_dir / "multi_batch_summary.json"
    summary_path.write_text(json.dumps(summary_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ SUMMARY: multi_batch_summary.json")

    # Show system stats
    stats = db.get_system_stats()
    print(f"\n📊 Database stats: {stats['total_batches']} batches, "
          f"{stats['total_beans']:,} beans, {stats['db_size_kb']} KB")

    print(f"\n📁 Reports saved to: {report_dir}")
    print("\n✅ Demo complete!")

    # Print first TEXT report
    print("\n" + "=" * 60)
    print("📋 Sample TEXT Report (first batch):")
    print("=" * 60)
    print(gen.generate_text(batch_ids[0]))

    return batch_ids


if __name__ == "__main__":
    run_demo(num_batches=3)
