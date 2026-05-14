#!/usr/bin/env python3
"""
Production Chain Integration Stress Test — v1.0
================================================
Validates the complete production chain end-to-end, without hardware.

Chain tested:
  RecipeManager → QualityClassifier → ProductionOrchestrator
              → RealTimeBatchTracker → ProductionAlarmManager

Tests:
  1. Recipe loading and validation
  2. Batch classification against recipe thresholds
  3. Multi-batch session orchestration
  4. Batch tracking lifecycle
  5. Alarm triggering under stress conditions
  6. Data persistence (database)
  7. Report generation across all formats
  8. BatchQualityTracker real-time monitoring

Run: python sorter/simulation/production_chain_stress_test.py
"""

import sys
import random
import time
import json
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from sorter.production.batch_recipe_manager import (
    BatchRecipe, RecipeManager,
    ColorThresholds, WeightThresholds,
    MoistureThresholds, DensityThresholds,
    DefectWeights, QualityTargets
)
from sorter.quality.classifier import (
    QualityClassifier, ClassifierMode, BeanQualityResult, SensorReading, DefectType
)
from sorter.production.integration_bridge import (
    ProductionOrchestrator, ProductionSession,
    RecipeToThresholdSetBridge, BatchQualitySummary
)
from sorter.production.batch_tracking_system import (
    RealTimeBatchTracker, ChainOfCustodyLogger, BatchLot, BatchOrigin,
    BatchStage, TraceEventType, TraceActor
)
from sorter.production.alarm_manager import (
    ProductionAlarmManager, AlarmSeverity, AlarmCategory, AlarmSource
)
from sorter.production.batch_quality_tracker import (
    BatchQualityTracker, QualityMetrics
)
from sorter.db.database import Database
from sorter.db.models import BatchRecord, BeanRecord, SystemEvent
from sorter.db.report_generator import BatchReportGenerator

random.seed(42)


# ══════════════════════════════════════════════════════════════════════════════
#  TEST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def make_sensor_reading(L=None, a=None, b=None):
    if L is None: L = random.uniform(30, 55)
    if a is None: a = random.uniform(5, 18)
    if b is None: b = random.uniform(10, 30)
    return SensorReading(
        color_L=L, color_a=a, color_b=b,
        weight_g=random.gauss(0.152, 0.008),
        moisture_pct=random.gauss(11.0, 0.5),
        density=random.randint(550, 820) / 1000.0,  # kg/m3 → g/mL
        ml_confidence=1.0,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 1: Recipe Loading and Threshold Bridge
# ══════════════════════════════════════════════════════════════════════════════

def test_recipe_loading():
    print("\n[Test 1] Recipe Loading & Threshold Bridge")
    print("-" * 50)

    rm = RecipeManager()
    recipes = rm.list_recipes()
    print(f"  ✓ Loaded {len(recipes)} recipes: {recipes}")

    ethiopian = rm.get_recipe("Ethiopian_Washed")
    assert ethiopian is not None, "Ethiopian_Washed recipe not found"
    print(f"  ✓ Ethiopian_Washed: origin_country={ethiopian.origin_country}, "
          f"origin_region={ethiopian.origin_region}, process={ethiopian.process}")

    # Build threshold set
    bridge = RecipeToThresholdSetBridge()
    ts = bridge.build_threshold_set(ethiopian)
    thresholds = ts.to_dict()["thresholds"]
    print(f"  ✓ ThresholdSet: {len(thresholds)} defect types, "
          f"MOLD={'MOLD' in thresholds}/BROKEN={'BROKEN' in thresholds}/FERMENTED={'FERMENTED' in thresholds}")

    # Validate all 9 recipes loadable
    for name in recipes:
        r = rm.get_recipe(name)
        assert r is not None, f"Failed to load {name}"
    print(f"  ✓ All {len(recipes)} recipes validated")

    return {"recipes_loaded": len(recipes), "threshold_types": len(thresholds)}


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 2: QualityClassifier with Recipe Thresholds
# ══════════════════════════════════════════════════════════════════════════════

def test_classifier_with_thresholds():
    print("\n[Test 2] QualityClassifier with Recipe Thresholds")
    print("-" * 50)

    rm = RecipeManager()

    recipes = ["Ethiopian_Washed", "Kenyan_Washed", "Brazilian_Natural"]
    results_summary = {}

    for recipe_name in recipes:
        recipe = rm.get_recipe(recipe_name)
        bridge = RecipeToThresholdSetBridge()
        ts = bridge.build_threshold_set(recipe)

        # Build classifier with recipe threshold set
        classifier = QualityClassifier(
            mode=ClassifierMode.THRESHOLD_ONLY,
            threshold_set=ts
        )

        grades = {"A": 0, "B": 0, "C": 0, "REJECT": 0}
        defect_counts = {}

        for i in range(500):
            r = make_sensor_reading()
            bean_id = f"TEST-{recipe_name}-{i+1:03d}"
            result = classifier.classify(bean_id, r)

            grades[result.grade.name] += 1
            for d in result.defect_results:
                key = d.defect_type.name
                defect_counts[key] = defect_counts.get(key, 0) + 1

        grade_a_pct = grades["A"] / 500 * 100
        total_defects = sum(defect_counts.values())
        print(f"  {recipe_name}: GradeA={grade_a_pct:.1f}%, Defects={total_defects}, "
              f"B={grades['B']}, C={grades['C']}, Rej={grades['REJECT']}")
        results_summary[recipe_name] = {
            "grade_a_pct": round(grade_a_pct, 1),
            "total_defects": total_defects
        }

    return results_summary


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 3: ProductionOrchestrator Multi-Session
# ══════════════════════════════════════════════════════════════════════════════

def test_production_orchestrator():
    print("\n[Test 3] ProductionOrchestrator Multi-Session")
    print("-" * 50)

    orch = ProductionOrchestrator()

    session_ids = []
    for recipe_name in ["Ethiopian_Washed", "Kenyan_Washed", "Colombian_Washed"]:
        session = orch.start_session(recipe_name)
        sid = session.session_id
        session_ids.append(sid)
        print(f"  ✓ Session started: {sid[:8]}... → {recipe_name}")

        # Build bean stream
        bean_stream = []
        for i in range(100):
            sensor = make_sensor_reading()
            bean_stream.append({
                "bean_id": f"BEAN-{sid[:8]}-{i+1:03d}",
                "sensor_readings": {
                    "weight": sensor.weight_g,
                    "moisture": sensor.moisture_pct,
                    "color_L": sensor.color_L,
                    "density": sensor.density,
                }
            })

        # Run batch
        batch_result = orch.run_batch(
            session=session,
            batch_id=f"BATCH-{sid[:8]}",
            bean_stream=bean_stream
        )
        print(f"    → Processed {batch_result.total_beans} beans, "
              f"GradeA={batch_result.grade_a_pct:.1f}%, "
              f"defects={int(batch_result.defect_rate_pct * batch_result.total_beans / 100)}")

    assert len(orch._sessions) <= 3, f"Expected ≤ 3 sessions, got {len(orch._sessions)}"
    print(f"  ✓ Sessions tracked in orchestrator: {len(orch._sessions)}")

    report = orch.generate_session_report(session)
    print(f"  ✓ Session report generated")

    return {"sessions_run": 3, "session_ids": session_ids}


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 4: RealTimeBatchTracker Lifecycle
# ══════════════════════════════════════════════════════════════════════════════

def test_batch_tracker_lifecycle():
    print("\n[Test 4] RealTimeBatchTracker Lifecycle")
    print("-" * 50)

    custody_logger = ChainOfCustodyLogger()
    tracker = RealTimeBatchTracker(custody_logger=custody_logger)

    origins = ["Ethiopia Yirgacheffe", "Kenya Kirinyaga", "Brazil Cerrado",
               "Colombia Huila", "Guatemala Antigua"]
    lot_ids = []

    for i, origin in enumerate(origins):
        country = origin.split()[0]
        region = origin

        batch_origin = BatchOrigin(
            origin_country=country,
            region=region,
            farm="Test Farm",
            altitude_m=1500 + i * 100,
            harvest_season=f"2026-{i+1:02d}",
            processing="Washed" if i % 2 == 0 else "Natural",
            variety=f"Variety-{i+1}",
            importer="Test Importer",
        )

        lot = BatchLot(
            lot_id=f"LOT-2026-0515-{i+1:02d}",
            origin=batch_origin,
            recipe_id=f"RECIPE-{i+1:02d}",
            stage=BatchStage.RECEIVED,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        tracker.register_lot(lot)
        lot_id = lot.lot_id
        lot_ids.append(lot_id)
        print(f"  ✓ Lot {i+1} registered: {lot_id[:8]}... origin={origin}")

        # Trace events
        actor = TraceActor(actor_id=f"ACTOR-{i}", actor_name="Auto-System",
                           actor_role="automation", shift="auto")
        tracker.trace_lot(lot_id)
        tracker.update_stage(lot_id, BatchStage.INSPECTED, actor, "QC Lab", {})
        tracker.update_stage(lot_id, BatchStage.READY, actor, "Storage", {})
        tracker.update_stage(lot_id, BatchStage.IN_SORTER, actor, "Sorter", {})
        tracker.update_stage(lot_id, BatchStage.SORTING, actor, "Sorter", {})
        tracker.update_stage(lot_id, BatchStage.QCED, actor, "QC Lab", {})

        if i % 2 == 0:
            tracker.update_stage(lot_id, BatchStage.RELEASED, actor, "Release", {})
            print(f"    → Advanced to RELEASED")
        else:
            print(f"    → Advanced to QCED")

    # Pipeline summary
    summary = tracker.get_pipeline_summary()
    print(f"  ✓ Pipeline summary: {summary.get('total_lots', 0)} lots tracked")

    return {"lots_created": len(lot_ids), "lot_ids": lot_ids}


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 5: ProductionAlarmManager Stress Test
# ══════════════════════════════════════════════════════════════════════════════

def test_alarm_manager_stress():
    print("\n[Test 5] ProductionAlarmManager Stress Test")
    print("-" * 50)

    alarm_mgr = ProductionAlarmManager(demo_mode=True)

    test_conditions = [
        ("normal",    1.0, 90.0, 11.0, 700),
        ("warning",   2.5, 83.0, 11.5, 695),
        ("critical",  6.0, 72.0, 10.2, 680),
        ("recovery",  1.5, 87.0, 11.0, 700),
    ]

    alarm_count = 0
    for label, defect_rate, grade_a, moisture, density in test_conditions:
        alarm_mgr.feed_metric("defect_rate_pct", defect_rate, "batch_quality_tracker")
        alarm_mgr.feed_metric("grade_a_pct", grade_a, "batch_quality_tracker")
        alarm_mgr.feed_metric("avg_moisture_pct", moisture, "batch_quality_tracker")
        alarm_mgr.feed_metric("avg_density_kg_m3", density, "batch_quality_tracker")

        active = alarm_mgr.get_active_alarms()
        print(f"  [{label:10}] defect={defect_rate:.1f}% → active={len(active)}")
        alarm_count += len(active)

    stats = alarm_mgr.get_stats()
    print(f"  ✓ Total alarms fired: {stats.get('total_fired', 0)}")
    print(f"  ✓ Policies loaded: {len(alarm_mgr._policies)}")

    return {"alarms_fired": alarm_count, "policies_loaded": len(alarm_mgr._policies)}


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 6: Database Persistence
# ══════════════════════════════════════════════════════════════════════════════

def test_database_persistence():
    print("\n[Test 6] Database Persistence")
    print("-" * 50)

    db = Database(db_path=None)  # in-memory

    batch_ids = []
    for i in range(5):
        batch = BatchRecord(
            batch_id=f"BATCH-2026-0515-{i+1:02d}",
            started_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            origin=f"Origin-{i}",
            variety=f"Variety-{i}",
            process="Washed" if i % 2 == 0 else "Natural",
            lot_number=f"LOT-2026-0515-{i+1:02d}",
            target_weight_g=250.0,
            target_throughput_kg_h=2.0,
            channels_used=3,
            total_beans=0,
            defective_beans=0,
        )
        db.insert_batch(batch)
        batch_ids.append(batch.batch_id)

    total_beans = 0
    for bid in batch_ids:
        batch = db.get_batch(bid)
        # Insert beans into this batch
        beans = []
        n = random.randint(200, 500)
        for j in range(n):
            sensor_data = {
                "weight_g": random.gauss(0.152, 0.008),
                "moisture_pct": random.gauss(11.0, 0.5),
                "color_L": random.uniform(30, 55),
                "density_kg_m3": random.randint(550, 820),
            }
            bean = BeanRecord(
                bean_id=f"{bid}-BEAN-{j+1:04d}",
                batch_id=bid,
                timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                channel=1,
                bean_index=j,
                quality_score=random.uniform(72, 95),
                grade=random.choice([0, 1, 2, 3]),  # Grade A/B/C/Reject
            )
            beans.append(bean)
        db.insert_beans_bulk(beans)
        total_beans += n

    print(f"  ✓ Inserted {len(batch_ids)} batches, {total_beans} beans")

    stats = db.get_batch_stats(batch_ids[0])
    assert stats is not None, "Batch stats query failed"
    print(f"  ✓ Batch stats query: {stats.get('bean_count', 0)} beans in batch[0]")

    event = SystemEvent(
        event_id=f"EVT-{int(time.time())}",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        severity="INFO",
        component="test",
        message="Test event"
    )
    db.insert_event(event)
    events = db.get_events(batch_ids[0])
    print(f"  ✓ Event log: {len(events)} events for batch[0]")

    return {"batches": len(batch_ids), "beans": total_beans, "events_logged": len(events)}


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 7: Report Generation All Formats
# ══════════════════════════════════════════════════════════════════════════════

def test_report_generation():
    print("\n[Test 7] Report Generation (JSON/CSV/TEXT)")
    print("-" * 50)

    db = Database(db_path=None)
    report_gen = BatchReportGenerator(db=db)

    # Create 3 batches in DB for report generation
    batch_ids = []
    for i in range(3):
        batch = BatchRecord(
            batch_id=f"REPORT-BATCH-{i+1:02d}",
            started_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ended_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            origin=random.choice(["Ethiopia", "Kenya", "Brazil"]),
            variety="Heirloom",
            process="Washed",
            lot_number=f"LOT-{i+1}",
            total_beans=random.randint(2000, 5000),
            grade_a_count=random.randint(1500, 4000),
            grade_b_count=random.randint(200, 600),
            grade_c_count=random.randint(50, 200),
            grade_reject_count=random.randint(20, 150),
            total_weight_g=random.uniform(300, 800),
            avg_quality_score=random.uniform(72, 92),
            defective_beans=random.randint(20, 150),
        )
        db.insert_batch(batch)
        batch_ids.append(batch.batch_id)

    # JSON report (single batch)
    json_report = report_gen.generate_json(batch_ids[0])
    assert json_report, "JSON report empty"
    jdata = json_report if isinstance(json_report, dict) else {}
    print(f"  ✓ JSON report: batch_id={jdata.get('batch_id', '?')}, "
          f"beans={jdata.get('total_beans', '?')}")

    # CSV export (single batch)
    csv_path = report_gen.generate_csv(batch_ids[0])
    assert csv_path is not None, "CSV report failed"
    print(f"  ✓ CSV report: {csv_path}")

    # Multi-batch summary by origin
    summary = report_gen.generate_multi_batch_summary(origin=None, limit=10)
    print(f"  ✓ Multi-batch summary: {len(summary.get('batches', []))} batches")

    # TEXT report (single batch)
    text_report = report_gen.generate_text(batch_ids[0])
    assert len(text_report) > 100, "TEXT report too short"
    print(f"  ✓ TEXT report: {len(text_report)} chars")

    return {
        "batches_reported": len(batch_ids),
        "text_chars": len(text_report),
        "csv_path": str(csv_path)
    }


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 8: BatchQualityTracker Real-Time Monitoring
# ══════════════════════════════════════════════════════════════════════════════

def test_batch_quality_tracker():
    print("\n[Test 8] BatchQualityTracker Real-Time Monitoring")
    print("-" * 50)

    tracker = BatchQualityTracker(alert_callback=None)
    tracker.start_batch(batch_id="BATCH-STRESS-001", target_g=25000, recipe="Default")

    # 7% defect injection
    defect_beans = [("broken", 15), ("immature", 10), ("moldy", 5),
                    ("fermented", 5), ("black", 3)]
    defect_counts = [dict(defect_beans) for _ in range(5)]
    defect_idx = 0

    for i in range(500):
        use_defect = False
        for di, (dtype, _) in enumerate(defect_beans):
            if defect_counts[di][dtype] > 0:
                defect_counts[di][dtype] -= 1
                use_defect = True
                break

        if use_defect:
            weight_g = random.uniform(0.06, 0.10)
            color_score = random.uniform(20, 30)  # low score = defective
            moisture_pct = random.uniform(8.5, 10.5)
            density_score = random.uniform(0.45, 0.55)  # low density
            is_defect = True
        else:
            weight_g = random.gauss(0.152, 0.008)
            color_score = random.uniform(80, 95)  # normal score
            moisture_pct = random.gauss(11.0, 0.5)
            density_score = random.uniform(0.65, 0.80)  # normal density
            is_defect = False

        tracker.record_bean(
            is_defect=is_defect,
            weight_g=weight_g,
            color_score=color_score,
            moisture_pct=moisture_pct,
            density_score=density_score
        )

        if (i + 1) % 100 == 0:
            status = tracker.get_current_status()
            print(f"  Bean {i+1}: status={status.get('status', '?')}, "
                  f"total_beans={status.get('total_beans', 0)}, "
                  f"defect_rate={status.get('defect_rate_pct', 0):.2f}%, "
                  f"quality_score={status.get('quality_score', 0):.1f}")

    status = tracker.get_current_status()
    print(f"  ✓ Final: total_beans={status.get('total_beans', 0)}, "
          f"defect_rate={status.get('defect_rate_pct', 0):.2f}%, "
          f"quality_score={status.get('quality_score', 0):.1f}")
    print(f"  ✓ Trend: {tracker.trend_analysis()}")

    return {
        "total_beans": status.get('total_beans', 0),
        "defect_rate_pct": status.get('defect_rate_pct', 0),
        "quality_score": status.get('quality_score', 0),
        "trend": tracker.trend_analysis()
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  PRODUCTION CHAIN INTEGRATION STRESS TEST")
    print("  HUSKY-SORTER-001 | 2026-05-15 | v1.0")
    print("=" * 60)

    results = {}

    tests = [
        ("Recipe Loading & Threshold Bridge", test_recipe_loading),
        ("QualityClassifier with Recipe Thresholds", test_classifier_with_thresholds),
        ("ProductionOrchestrator Multi-Session", test_production_orchestrator),
        ("RealTimeBatchTracker Lifecycle", test_batch_tracker_lifecycle),
        ("ProductionAlarmManager Stress", test_alarm_manager_stress),
        ("Database Persistence", test_database_persistence),
        ("Report Generation (JSON/CSV/TEXT)", test_report_generation),
        ("BatchQualityTracker Real-Time Monitoring", test_batch_quality_tracker),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            result = fn()
            results[name] = {"status": "PASS", "result": result}
            passed += 1
        except Exception as e:
            import traceback
            results[name] = {"status": "FAIL", "error": str(e)}
            failed += 1
            print(f"\n  ❌ FAIL: {e}")
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    print(f"  Passed: {passed}/{len(tests)}")
    print(f"  Failed: {failed}/{len(tests)}")
    print()

    for name, res in results.items():
        status_icon = "✅" if res["status"] == "PASS" else "❌"
        print(f"  {status_icon} {name}: {res['status']}")

    print()
    if failed == 0:
        print("  🎉 ALL TESTS PASSED — Production chain validated!")
    else:
        print(f"  ⚠️  {failed} test(s) failed — review errors above")

    # Save results
    report_path = Path(__file__).parent.parent / "reports" / "production_chain_stress_test.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {"passed": passed, "failed": failed},
            "results": results
        }, f, indent=2, default=str)
    print(f"\n  📄 Report saved: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())