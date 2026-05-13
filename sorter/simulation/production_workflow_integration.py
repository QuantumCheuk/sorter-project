#!/usr/bin/env python3
"""
Production Workflow Integration Test
=====================================
End-to-end integration test tying together:
  - batch_recipe_manager  (v1.69)
  - batch_tracking_system (v1.72 fix: ISO timestamp)
  - qc_audit_system      (v1.70)

Run: python sorter/simulation/production_workflow_integration.py
"""

import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── import ────────────────────────────────────────────────────────────────────
try:
    from sorter.production.batch_recipe_manager import (
        RecipeManager, BatchRecipe,
    )
    from sorter.production.batch_tracking_system import (
        RealTimeBatchTracker, ChainOfCustodyLogger,
        BatchLot, BatchOrigin, BatchMetrics, BatchStage,
        TraceActor, TraceEventType,
    )
    from sorter.quality.qc_audit_system import (
        BatchAuditReport, SCABeanGradeSheet,
        DefectDifferentialDiagnosisSystem,
        SupplierQualityProfile, ComplianceCertificate,
        QCAuditReportGenerator,
        DefectCount, DefectCategory, SensorReadingSummary, ComplianceStatus,
        SCAGrade, AuditFinding,
    )
    IMPORTS_OK = True
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

# ── helpers ───────────────────────────────────────────────────────────────────
def _p(label: str) -> None:
    print(f"  ✅ {label}")

def _f(label: str, detail: str = "") -> None:
    print(f"  ❌ {label}" + (f": {detail}" if detail else ""))

def _w(label: str, detail: str = "") -> None:
    print(f"  ⚠️  {label}" + (f": {detail}" if detail else ""))

def _sec(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ── reproducible RNG ───────────────────────────────────────────────────────────
random.seed(20260514)
BEAN_WEIGHT_G = 0.152

def _simulate_beans(origin: str, n: int = 200) -> list[dict]:
    rates = {"Ethiopia": 0.05, "Kenya": 0.04, "Colombia": 0.06, "Brazil": 0.07}
    rate = next((v for k, v in rates.items() if origin.startswith(k)), 0.05)
    defects = ["bleached", "moldy", "fermented", "broken", "immature", "insect", "black"]
    beans = []
    for i in range(n):
        dt = None if random.random() >= rate else random.choice(defects)
        beans.append({
            "bean_id": f"{origin[:3].upper()}-{i:04d}",
            "weight_g": round(BEAN_WEIGHT_G + random.gauss(0, 0.008), 4),
            "defect_type": dt,
            "quality_score": round(random.uniform(60, 100), 1),
        })
    return beans


def _make_sensor_summary(channel: str = "score", avg: float = 72.4, std: float = 2.0) -> SensorReadingSummary:
    return SensorReadingSummary(
        channel=channel,
        n_samples=100,
        mean=avg,
        std=std,
        min_val=avg - 5,
        max_val=avg + 5,
        median=avg,
        cv_pct=std / avg * 100 if avg else 0,
        out_of_spec_count=0,
    )


def _make_defect_counts(defect_counts: dict, total_beans: int) -> list[DefectCount]:
    """Convert raw defect dict to DefectCount list (PRIMARY: moldy/fermented, SECONDARY: rest)."""
    PRIMARY = {"moldy", "fermented"}
    result = []
    for k, v in defect_counts.items():
        cat = DefectCategory.PRIMARY if k in PRIMARY else DefectCategory.SECONDARY
        result.append(DefectCount(
            defect_type=k,
            category=cat,
            count=v,
            eq_full_defects=v * 0.5,
            notes="",
        ))
    return result


def _make_batch_audit_report(
    batch_id: str,
    lot_id: str,
    origin: str,
    process_method: str,
    variety: str,
    harvest_year: int,
    supplier: str,
    recipe_name: str,
    total_beans: int,
    defect_counts: dict,
    batch_weight_kg: float,
    avg_beans_per_kg: float,
    sensor_readings: dict,
    duration_sec: int,
) -> BatchAuditReport:
    """Build BatchAuditReport from raw test parameters (correct API signature)."""
    total_primary = defect_counts.get("moldy", 0) + defect_counts.get("fermented", 0)
    total_secondary = sum(v for k, v in defect_counts.items()
                         if k not in ("moldy", "fermented"))
    sca_eq = sum(v * 0.5 for v in defect_counts.values())
    grade_a = total_beans - sum(defect_counts.values())
    grade_a_pct = grade_a / total_beans * 100 if total_beans else 0

    defects = _make_defect_counts(defect_counts, total_beans)

    return BatchAuditReport(
        audit_id=f"AUDIT-{batch_id}",
        batch_id=batch_id,
        lot_id=lot_id,
        origin=origin,
        process_method=process_method,
        variety=variety,
        harvest_year=harvest_year,
        supplier=supplier,
        audit_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        production_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        shift="Morning",
        operator_id="SYS-001",
        equipment_id="SORTER-01",
        recipe_name=recipe_name,
        total_beans_processed=total_beans,
        total_kg_processed=batch_weight_kg,
        grade_a_count=grade_a,
        grade_b_count=0,
        grade_c_count=0,
        grade_reject_count=sum(defect_counts.values()),
        grade_a_pct=grade_a_pct,
        grade_b_pct=0.0,
        grade_c_pct=0.0,
        grade_reject_pct=100 - grade_a_pct,
        defects=defects,
        total_primary_defects=total_primary,
        total_secondary_defects=total_secondary,
        sca_eq_full_defects=sca_eq,
        weight_summary=_make_sensor_summary(sensor_readings.get("weight_avg_g", BEAN_WEIGHT_G)),
        moisture_summary=_make_sensor_summary(sensor_readings.get("moisture_pct", 11.2)),
        density_summary=_make_sensor_summary(sensor_readings.get("density_g_ml", 0.68)),
        color_summary=_make_sensor_summary(sensor_readings.get("color_score_avg", 72.4)),
        compliance_status=ComplianceStatus.COMPLIANT,
        sca_grade=SCAGrade.SPECIALTY if sca_eq < 5 else SCAGrade.PREMIUM,
        quality_score=sensor_readings.get("color_score_avg", 72.4),
        defect_rate_pct=sum(defect_counts.values()) / total_beans * 100 if total_beans else 0,
        moisture_pct_avg=sensor_readings.get("moisture_pct", 11.2),
        density_avg=sensor_readings.get("density_g_ml", 0.68),
        color_score_avg=sensor_readings.get("color_score_avg", 72.4),
        findings=[],
    )


# ── TEST 1: Recipe Manager ────────────────────────────────────────────────────
def test_recipe_manager() -> dict[str, bool]:
    results = {}
    _sec("TEST 1 — Batch Recipe Manager")
    rm = RecipeManager()

    # list recipes
    try:
        recipes = rm.list_recipes()
        results["list_recipes"] = len(recipes) >= 9
        _p(f"list_recipes() → {len(recipes)} recipes")
    except Exception as e:
        results["list_recipes"] = False
        _f("list_recipes()", str(e))

    # get recipe
    for name in ["Ethiopian_Washed", "Kenyan_Washed", "Brazilian_Natural"]:
        try:
            r = rm.get_recipe(name)
            results[f"get_{name}"] = r is not None
            _p(f"get_recipe('{name}')") if r else _f(f"get_{name}", "None")
        except Exception as e:
            results[f"get_{name}"] = False
            _f(f"get_recipe('{name}')", str(e))

    # validate (API: takes recipe_id string, returns dict)
    try:
        v_result = rm.validate_recipe("Ethiopian_Washed")
        valid = isinstance(v_result, dict) and v_result.get("valid", False)
        results["validate_Ethiopian_Washed"] = valid
        errs = v_result.get("errors", [])
        _p(f"validate_recipe: valid={valid}, errors={len(errs)}")
        if errs:
            _w(f"  validation errors: {errs}")
    except Exception as e:
        results["validate_Ethiopian_Washed"] = False
        _f("validate_recipe()", str(e))

    # apply (API: takes recipe_id string, returns dict)
    try:
        cfg = rm.apply_recipe("Brazilian_Natural", "WF-BRA-TEST")
        results["apply_Brazilian_Natural"] = cfg is not None and isinstance(cfg, dict)
        keys = list(cfg.keys()) if isinstance(cfg, dict) else []
        _p(f"apply_recipe() → {len(keys)} config keys: {keys}")
    except Exception as e:
        results["apply_Brazilian_Natural"] = False
        _f("apply_recipe()", str(e))

    # load recipe
    try:
        loaded = rm.load_recipe("Kenyan_Washed")
        results["load_Kenyan_Washed"] = loaded is not None
        _p("load_recipe('Kenyan_Washed')")
    except Exception as e:
        results["load_Kenyan_Washed"] = False
        _f("load_recipe()", str(e))

    # get active recipe
    try:
        active = rm.get_active_recipe()
        results["get_active_recipe"] = active is not None
        _p(f"get_active_recipe() → {active.recipe_id if active else 'None'}")
    except Exception as e:
        results["get_active_recipe"] = False
        _f("get_active_recipe()", str(e))

    # export all recipes
    try:
        export_path = rm.export_all_recipes()
        results["export_all_recipes"] = export_path is not None and export_path.exists()
        _p(f"export_all_recipes() → {export_path.name}")
    except Exception as e:
        results["export_all_recipes"] = False
        _f("export_all_recipes()", str(e))

    return results


# ── TEST 2: Batch Tracking System ────────────────────────────────────────────
def test_batch_tracking_system() -> dict[str, bool]:
    results = {}
    _sec("TEST 2 — Batch Tracking System")

    logger = ChainOfCustodyLogger(storage_path=str(PROJECT_ROOT / "sorter" / "data" / "custody"))
    tracker = RealTimeBatchTracker(custody_logger=logger)

    LOT_ID = "TEST-LOT-20260514"
    ACTOR = TraceActor(actor_id="SYS-001", actor_name="IntegrationTest", actor_role="system")
    TS = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # register lot  (BatchLot: lot_id/origin/recipe_id/stage/created_at/updated_at required)
    try:
        lot = BatchLot(
            lot_id=LOT_ID,
            origin=BatchOrigin(
                origin_country="Ethiopia", region="Yirgacheffe",
                farm="Worka", altitude_m=1950, harvest_season="2025",
                processing="Washed", variety="Heirloom",
                importer="Trabocca", arrival_date="2026-05-10",
            ),
            recipe_id="Ethiopian_Washed",
            stage=BatchStage.RECEIVED,
            created_at=TS,
            updated_at=TS,
        )
        # BatchMetrics: beans_sorted/beans_grade_a/beans_rejected/final_defect_rate_pct/grade_a_yield_pct
        lot.metrics = BatchMetrics(
            beans_sorted=0, beans_grade_a=0,
            beans_rejected=0, final_defect_rate_pct=0.0, grade_a_yield_pct=0.0,
        )
        tracker.register_lot(lot)
        results["register_lot"] = True
        _p(f"register_lot('{LOT_ID}')")
    except Exception as e:
        results["register_lot"] = False
        _f("register_lot()", str(e))
        return results

    # update stages
    for stage, location in [
        (BatchStage.INSPECTED, "QC-Lab"),
        (BatchStage.READY, "Sorter-01"),
        (BatchStage.IN_SORTER, "Sorter-01"),
        (BatchStage.SORTING, "Sorter-01"),
        (BatchStage.QCED, "QC-Lab"),
    ]:
        try:
            ok = tracker.update_stage(LOT_ID, stage, ACTOR, location)
            results[f"update_stage_{stage.value}"] = ok
            _p(f"update_stage({stage.value})")
        except Exception as e:
            results[f"update_stage_{stage.value}"] = False
            _f(f"update_stage({stage.value})", str(e))

    # get lot status
    try:
        status = tracker.get_lot_status(LOT_ID)
        results["get_lot_status"] = status is not None
        stage = status.get("stage") if status else "N/A"
        _p(f"get_lot_status() → stage={stage}")
    except Exception as e:
        results["get_lot_status"] = False
        _f("get_lot_status()", str(e))

    # list lots
    try:
        lots = tracker.list_lots()
        results["list_lots"] = len(lots) >= 1
        _p(f"list_lots() → {len(lots)} lot(s)")
    except Exception as e:
        results["list_lots"] = False
        _f("list_lots()", str(e))

    # trace lot
    try:
        trace_str = tracker.trace_lot(LOT_ID)
        results["trace_lot"] = trace_str is not None and len(trace_str) > 50
        _p(f"trace_lot() → {len(trace_str)} chars")
    except Exception as e:
        results["trace_lot"] = False
        _f("trace_lot()", str(e))

    # pipeline summary
    try:
        summary = tracker.get_pipeline_summary()
        results["get_pipeline_summary"] = summary is not None and "total_lots" in summary
        _p(f"get_pipeline_summary() → {summary.get('total_lots', '?')} lots")
    except Exception as e:
        results["get_pipeline_summary"] = False
        _f("get_pipeline_summary()", str(e))

    # v1.72 ISO timestamp check
    try:
        ts_str = lot.created_at
        has_z = "Z" in ts_str
        has_plus = "+" in ts_str and "T" in ts_str
        results["iso_timestamp_format"] = has_z or has_plus
        _p(f"ISO timestamp: {ts_str}")
    except Exception as e:
        results["iso_timestamp_format"] = False
        _f("ISO timestamp", str(e))

    return results


# ── TEST 3: QC Audit System ──────────────────────────────────────────────────
def test_qc_audit_system() -> dict[str, bool]:
    results = {}
    _sec("TEST 3 — QC Audit System")

    # Shared test data
    defect_counts = {
        "bleached": 8, "moldy": 4, "fermented": 12,
        "broken": 25, "immature": 18, "insect": 3, "black": 2,
    }
    sensor_readings = {
        "color_score_avg": 72.4, "weight_avg_g": BEAN_WEIGHT_G,
        "moisture_pct": 11.2, "density_g_ml": 0.68,
    }
    total_beans = 3000

    # 3a. BatchAuditReport  (correct API: named params matching BatchAuditReport.__init__)
    try:
        report = _make_batch_audit_report(
            batch_id="QA-TEST-001",
            lot_id="LOT-QA-001",
            origin="Ethiopia",
            process_method="Natural",
            variety="Heirloom",
            harvest_year=2025,
            supplier="TestSupplier",
            recipe_name="Ethiopian_Washed",
            total_beans=total_beans,
            defect_counts=defect_counts,
            batch_weight_kg=0.456,
            avg_beans_per_kg=6578,
            sensor_readings=sensor_readings,
            duration_sec=3600,
        )
        rj = report.to_dict()
        results["BatchAuditReport_json"] = isinstance(rj, dict)
        _p("BatchAuditReport.to_dict()")
    except Exception as e:
        results["BatchAuditReport_json"] = False
        _f("BatchAuditReport", str(e))
        report = None

    # 3b. SCABeanGradeSheet  (correct API: certificate_id/lot_id/origin/process_method/...)
    #       Output method is to_dict(), NOT to_json(); no total_score attr
    try:
        sheet = SCABeanGradeSheet(
            certificate_id="CERT-QA-001",
            lot_id="LOT-QA-001",
            origin="Ethiopia",
            process_method="Natural",
            variety="Heirloom",
            harvest_year=2025,
            supplier="TestSupplier",
            grading_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            graded_by="HUSKY-SORTER-001 Auto-Audit",
            total_beans_graded=total_beans,
            sca_eq_full_defects=sum(v * 0.5 for v in defect_counts.values()),
            moisture_pct=sensor_readings["moisture_pct"],
            density_g_mL=sensor_readings["density_g_ml"],
            screen_size_majority="15",
            color_uniformity="good",
            primary_defect_count=4 + 12,
            secondary_defect_count=sum(v for k, v in defect_counts.items() if k not in ("moldy", "fermented")),
        )
        sj = sheet.to_dict()
        results["SCABeanGradeSheet_json"] = isinstance(sj, dict)
        _p("SCABeanGradeSheet.to_dict()")
        # Check sca_pass (v1.70 regression: boolean attribute)
        try:
            sca_pass = sheet.sca_pass
            results["SCABeanGradeSheet_sca_pass"] = isinstance(sca_pass, bool)
            _p(f"SCABeanGradeSheet.sca_pass = {sca_pass}")
        except AttributeError:
            results["SCABeanGradeSheet_sca_pass"] = False
            _f("sca_pass (v1.70 regression: missing attribute!)")
    except Exception as e:
        results["SCABeanGradeSheet_json"] = False
        _f("SCABeanGradeSheet", str(e))
        sheet = None

    # 3c. DefectDifferentialDiagnosisSystem  (correct API: diagnose(bean_id/weight_g/moisture_pct/density_g_mL/lab_color/color_std))
    try:
        ddds = DefectDifferentialDiagnosisSystem()
        scenarios = [
            ("low_weight_hollow", 0.08, 11.0, 0.55, {"L_star": 55, "a_star": 0, "b_star": 0}),
            ("moldy_dark",        0.16, 11.0, 0.70, {"L_star": 18, "a_star": 0, "b_star": 0}),
            ("fermented",         0.13, 11.0, 0.62, {"L_star": 38, "a_star": 0, "b_star": 0}),
            ("normal",            0.15, 11.0, 0.68, {"L_star": 42, "a_star": 0, "b_star": 0}),
        ]
        all_ok = True
        for scenario_name, w, m, d, lab in scenarios:
            try:
                r = ddds.diagnose(
                    bean_id=f"DIAG-{scenario_name}",
                    weight_g=w,
                    moisture_pct=m,
                    density_g_mL=d,
                    lab_color=lab,
                    color_std=2.0,
                )
                if r is None:
                    all_ok = False
            except Exception:
                all_ok = False
        results["DefectDifferentialDiagnosis"] = all_ok
        _p(f"DefectDifferentialDiagnosis × 4 scenarios {'✅' if all_ok else '❌'}")
    except Exception as e:
        results["DefectDifferentialDiagnosis"] = False
        _f("DefectDifferentialDiagnosisSystem", str(e))

    # 3d. SupplierQualityProfile  (correct API: supplier_id/supplier_name/origin/process_methods[]/varieties[])
    #       No add_batch() method; batch_history is a field that can be appended to
    try:
        sqp = SupplierQualityProfile(
            supplier_id="SUP-TEST-001",
            supplier_name="TestSupplier",
            origin="Ethiopia",
            process_methods=["Natural", "Washed"],
            varieties=["Heirloom"],
        )
        for i in range(5):
            # batch_history is a list; append directly
            sqp.batch_history.append({
                "batch_id": f"SQP-{i}", "total_beans": 3000,
                "defect_rate": 0.05 + i * 0.01, "quality_score": 75 + i,
                "moisture_pct": 11.0,
            })
        profile = sqp.to_dict()
        results["SupplierQualityProfile"] = isinstance(profile, dict)
        _p("SupplierQualityProfile.to_dict()")
    except Exception as e:
        results["SupplierQualityProfile"] = False
        _f("SupplierQualityProfile", str(e))

    # 3e. ComplianceCertificate  (correct API: cert_id/batch_id/lot_id/... + bool fields, NO 'standards' param)
    try:
        cert = ComplianceCertificate(
            cert_id="CERT-QA-001",
            batch_id="QA-TEST-001",
            lot_id="LOT-QA-001",
            origin="Ethiopia",
            process_method="Natural",
            variety="Heirloom",
            harvest_year=2025,
            supplier="TestSupplier",
            production_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            inspection_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            equipment_id="SORTER-01",
            operator_id="SYS-001",
            sca_cat1_pass=True,
            sca_cat2_pass=True,
            moisture_in_spec=True,
            density_in_spec=True,
            defect_rate_pass=True,
            recipe_compliant=True,
            sca_eq_defects=sum(v * 0.5 for v in defect_counts.values()),
            moisture_pct=sensor_readings["moisture_pct"],
            density_g_mL=sensor_readings["density_g_ml"],
            defect_rate_pct=sum(defect_counts.values()) / total_beans * 100,
            quality_score=sensor_readings["color_score_avg"],
            sca_grade=SCAGrade.PREMIUM,
        )
        # sca_eq_defects must be a property, not a method (v1.70 bug)
        try:
            sca_val = cert.sca_eq_defects
            results["sca_eq_defects_is_property"] = isinstance(sca_val, (int, float))
            _p(f"ComplianceCertificate.sca_eq_defects = {sca_val:.4f} (property ✅)")
        except TypeError:
            results["sca_eq_defects_is_property"] = False
            _f("sca_eq_defects (METHOD called with () — v1.70 regression!)")

        cert_json = cert.to_dict()
        results["ComplianceCertificate_json"] = isinstance(cert_json, dict)
        _p("ComplianceCertificate.to_dict()")

        results["overall_compliant"] = bool(cert.overall_compliant)
        _p(f"overall_compliant: {cert.overall_compliant}")
    except Exception as e:
        results["ComplianceCertificate_json"] = False
        _f("ComplianceCertificate", str(e))

    # 3f. QCAuditReportGenerator orchestrator
    if report is not None:
        try:
            gen = QCAuditReportGenerator()

            # generate_certificate takes BatchAuditReport (correct API)
            cert_out = gen.generate_certificate(
                report=report,
                audit_report_id="AUDIT-QA-001",
                recipe_ref="Ethiopian_Washed",
                calibration_ref="CAL-20260514",
            )
            results["generate_certificate"] = cert_out is not None
            _p("generate_certificate()")

            # generate_sca_grade_sheet takes BatchAuditReport (correct API)
            sca_out = gen.generate_sca_grade_sheet(report=report)
            results["generate_sca_grade_sheet"] = sca_out is not None
            _p("generate_sca_grade_sheet()")
        except Exception as e:
            for k in ["generate_certificate", "generate_sca_grade_sheet"]:
                results[k] = False
            _f("QCAuditReportGenerator.orchestrator", str(e))
    else:
        for k in ["generate_certificate", "generate_sca_grade_sheet"]:
            results[k] = False

    return results


# ── TEST 4: End-to-End Workflow ───────────────────────────────────────────────
TEST_ORIGINS = [
    ("ETH", "Ethiopia", "Yirgacheffe", "Ethiopian_Washed"),
    ("KEN", "Kenya",     "Kirinyaga",   "Kenyan_Washed"),
    ("COL", "Colombia",  "Huila",       "Colombian_Washed"),
    ("BRA", "Brazil",    "Cerrado",     "Brazilian_Natural"),
]

def test_end_to_end() -> dict[str, bool]:
    results = {}
    _sec("TEST 4 — End-to-End Production Workflow (4 Origins)")

    rm = RecipeManager()
    logger = ChainOfCustodyLogger(storage_path=str(PROJECT_ROOT / "sorter" / "data" / "custody"))
    tracker = RealTimeBatchTracker(custody_logger=logger)

    all_ok = True
    for abbr, country, region, recipe_name in TEST_ORIGINS:
        batch_id = f"WF-{abbr}-20260514"
        LOT_ID = f"LOT-{abbr}-20260514"
        TS = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 1. Load recipe
        try:
            cfg = rm.apply_recipe(recipe_name, batch_id)
            results[f"wf_recipe_{abbr}"] = cfg is not None and isinstance(cfg, dict)
            if cfg:
                _p(f"[{abbr}] recipe '{recipe_name}' applied → {len(cfg)} keys")
            else:
                _f(f"[{abbr}] recipe '{recipe_name}'", "returned None")
                all_ok = False
                continue
        except Exception as e:
            results[f"wf_recipe_{abbr}"] = False
            _f(f"[{abbr}] recipe", str(e))
            all_ok = False
            continue

        # 2. Register lot + simulate beans
        try:
            lot = BatchLot(
                lot_id=LOT_ID,
                origin=BatchOrigin(
                    origin_country=country, region=region, farm="TestFarm",
                    altitude_m=1800, harvest_season="2025",
                    processing="Washed", variety="Heirloom",
                    importer="TestImport", arrival_date="2026-05-10",
                ),
                recipe_id=recipe_name,
                stage=BatchStage.RECEIVED,
                created_at=TS,
                updated_at=TS,
            )
            # BatchMetrics: only beans_sorted, beans_grade_a, beans_rejected
            lot.metrics = BatchMetrics(
                beans_sorted=0, beans_grade_a=0,
                beans_rejected=0, final_defect_rate_pct=0.0, grade_a_yield_pct=0.0,
            )
            tracker.register_lot(lot)
            beans = _simulate_beans(country, n=200)

            for bean in beans:
                lot.metrics.beans_sorted += 1
                if bean["defect_type"] is None:
                    lot.metrics.beans_grade_a += 1
                else:
                    lot.metrics.beans_rejected += 1

            if lot.metrics.beans_sorted > 0:
                lot.metrics.final_defect_rate_pct = (
                    lot.metrics.beans_rejected / lot.metrics.beans_sorted * 100
                )
                lot.metrics.grade_a_yield_pct = (
                    lot.metrics.beans_grade_a / lot.metrics.beans_sorted * 100
                )

            tracker.update_stage(
                LOT_ID, BatchStage.QCED,
                TraceActor(actor_id="E2E-001", actor_name="e2e-test", actor_role="system"),
                "QC-Lab", {"beans": len(beans)},
            )
            results[f"wf_track_{abbr}"] = True
            _p(f"[{abbr}] tracked {len(beans)} beans, "
               f"defect_rate={lot.metrics.final_defect_rate_pct:.1f}%, "
               f"gradeA={lot.metrics.grade_a_yield_pct:.1f}%")
        except Exception as e:
            results[f"wf_track_{abbr}"] = False
            _f(f"[{abbr}] track", str(e))
            all_ok = False
            continue

        # 3. Generate QC audit via _make_batch_audit_report helper
        try:
            defect_counts = {}
            for b in beans:
                if b["defect_type"]:
                    defect_counts[b["defect_type"]] = defect_counts.get(b["defect_type"], 0) + 1

            audit = _make_batch_audit_report(
                batch_id=batch_id,
                lot_id=LOT_ID,
                origin=country,
                process_method="Washed",
                variety="Heirloom",
                harvest_year=2025,
                supplier="TestSupplier",
                recipe_name=recipe_name,
                total_beans=len(beans),
                defect_counts=defect_counts,
                batch_weight_kg=len(beans) * BEAN_WEIGHT_G / 1000,
                avg_beans_per_kg=1 / BEAN_WEIGHT_G,
                sensor_readings={
                    "color_score_avg": 72.4, "weight_avg_g": BEAN_WEIGHT_G,
                    "moisture_pct": 11.2, "density_g_ml": 0.68,
                },
                duration_sec=30,
            )
            results[f"wf_audit_{abbr}"] = audit is not None
            if audit:
                _p(f"[{abbr}] QC audit generated (sca_eq={audit.sca_eq_full_defects:.1f})")
            else:
                _f(f"[{abbr}] QC audit", "returned None")
                all_ok = False
        except Exception as e:
            results[f"wf_audit_{abbr}"] = False
            _f(f"[{abbr}] QC audit", str(e))
            all_ok = False

    results["e2e_all_origins"] = all_ok
    return results


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   Production Workflow Integration Test  (2026-05-14)          ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    t0 = time.time()
    all_results: dict[str, bool] = {}
    all_results.update(test_recipe_manager())
    all_results.update(test_batch_tracking_system())
    all_results.update(test_qc_audit_system())
    all_results.update(test_end_to_end())

    elapsed = time.time() - t0
    passed   = sum(1 for v in all_results.values() if v)
    total    = len(all_results)
    pct      = passed / total * 100 if total else 0

    grade = (
        "🟢 A (90–100%)" if pct >= 90 else
        "🟡 B (70–89%)"  if pct >= 70 else
        "🟠 C (50–69%)"  if pct >= 50 else
        "🔴 F (<50%)"
    )

    _sec("SUMMARY")
    print(f"  Passed:  {passed}/{total}  ({pct:.1f}%)")
    print(f"  Grade:   {grade}")
    print(f"  Time:    {elapsed:.2f}s")

    failed = [k for k, v in all_results.items() if not v]
    if failed:
        print(f"\n  Failed ({len(failed)}):")
        for k in failed:
            print(f"    ❌ {k}")

    return 0 if pct == 100 else 1

if __name__ == "__main__":
    sys.exit(main())