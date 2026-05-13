"""
Production Batch Tracking & Real-Time Traceability System
==========================================================
Complete traceability from green coffee origin to finished batch.
Supports chain-of-custody logging, recall management, and QR code generation.

Usage:
    python -m sorter.production.batch_tracking_system --list
    python -m sorter.production.batch_tracking_system --track LOT-2026-0513-01
    python -m sorter.production.batch_tracking_system --trace LOT-2026-0513-01
    python -m sorter.production.batch_tracking_system --recall --defect MOLD --origin Ethiopian
"""

import json
import os
import uuid
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path


# =============================================================================
# Enums
# =============================================================================

class BatchStage(Enum):
    """Batch lifecycle stages."""
    RECEIVED = "received"
    INSPECTED = "inspected"
    CONDITIONED = "conditioned"
    READY = "ready"
    IN_SORTER = "in_sorter"
    SORTING = "sorting"
    PACKAGED = "packaged"
    QCED = "qced"
    RELEASED = "released"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RECALLED = "recalled"


class TraceEventType(Enum):
    """Types of traceability events."""
    RECEIVED = "received"
    SAMPLED = "sampled"
    CALIBRATED = "calibrated"
    CONDITIONING_START = "conditioning_start"
    CONDITIONING_END = "conditioning_end"
    LOADED_TO_SORTER = "loaded_to_sorter"
    SORTING_START = "sorting_start"
    SORTING_END = "sorting_end"
    GRADED = "graded"
    PACKAGED = "packaged"
    QC_INSPECTION = "qc_inspection"
    RELEASED = "released"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    HOLD = "hold"
    RECALL = "recall"
    DISPOSED = "disposed"


class RecallSeverity(Enum):
    """Recall severity levels."""
    INFORMATIONAL = "informational"
    CLASS_III = "class_iii"
    CLASS_II = "class_ii"
    CLASS_I = "class_i"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class TraceActor:
    """Person or system that performed an action."""
    actor_id: str
    actor_name: str
    actor_role: str
    shift: str = ""


@dataclass
class TraceEvent:
    """Single event in the batch traceability chain."""
    event_id: str
    batch_id: str
    event_type: TraceEventType
    timestamp: str
    actor: TraceActor
    location: str
    details: Dict[str, Any]
    event_hash: str = ""
    previous_event_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['event_type'] = self.event_type.value
        d['actor'] = asdict(self.actor)
        return d


@dataclass
class BatchOrigin:
    """Origin information for a coffee batch."""
    origin_country: str
    region: str
    farm: str
    altitude_m: int
    harvest_season: str
    processing: str
    variety: str
    importer: str = ""
    arrival_date: str = ""


@dataclass
class BatchMetrics:
    """Recorded metrics for a batch at various stages."""
    total_beans_received: int = 0
    defect_rate_at_receipt_pct: float = 0.0
    avg_moisture_pct: float = 0.0
    avg_density_g_ml: float = 0.0
    color_L_avg: float = 0.0
    color_a_avg: float = 0.0
    color_b_avg: float = 0.0
    weight_cv_pct: float = 0.0
    beans_sorted: int = 0
    beans_grade_a: int = 0
    beans_rejected: int = 0
    final_defect_rate_pct: float = 0.0
    grade_a_yield_pct: float = 0.0
    processing_yield_pct: float = 0.0


@dataclass
class QCResult:
    """Quality control inspection result."""
    inspection_id: str
    timestamp: str
    inspector: str
    sample_size: int
    defect_count: int
    defect_types: Dict[str, int]
    moisture_pct: float
    color_L: float
    color_a: float
    color_b: float
    passed: bool
    notes: str = ""


@dataclass
class RecallRecord:
    """Recall event record."""
    recall_id: str
    timestamp: str
    defect_type: str
    severity: RecallSeverity
    reason: str
    affected_batch_ids: List[str]
    affected_quantity_kg: float
    status: str
    corrective_action: str = ""
    closed_date: str = ""


@dataclass
class BatchLot:
    """Complete batch lot with full traceability."""
    lot_id: str
    origin: BatchOrigin
    recipe_id: str
    stage: BatchStage
    created_at: str
    updated_at: str
    events: List[TraceEvent] = field(default_factory=list)
    metrics: BatchMetrics = field(default_factory=BatchMetrics)
    qc_results: List[QCResult] = field(default_factory=list)
    recall_records: List[RecallRecord] = field(default_factory=list)
    linked_lots: List[str] = field(default_factory=list)
    qr_code_data: str = ""
    status_notes: List[str] = field(default_factory=list)
    shelf_life_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'lot_id': self.lot_id,
            'origin': asdict(self.origin),
            'recipe_id': self.recipe_id,
            'stage': self.stage.value,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'events': [e.to_dict() for e in self.events],
            'metrics': asdict(self.metrics),
            'qc_results': [asdict(q) for q in self.qc_results],
            'recall_records': [asdict(r) for r in self.recall_records],
            'linked_lots': self.linked_lots,
            'qr_code_data': self.qr_code_data,
            'status_notes': self.status_notes,
            'shelf_life_date': self.shelf_life_date,
        }

    def add_event(self, event: TraceEvent) -> None:
        if self.events:
            event.previous_event_hash = self.events[-1].event_hash
        event.event_hash = self._hash_event(event)
        self.events.append(event)
        self.updated_at = datetime.now(timezone.utc).isoformat() + "Z"

    def _hash_event(self, event: TraceEvent) -> str:
        content = f"{event.event_id}{event.batch_id}{event.event_type.value}{event.timestamp}{event.previous_event_hash}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def age_hours(self) -> float:
        created = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - created).total_seconds() / 3600

    @property
    def is_active(self) -> bool:
        return self.stage.value not in ['delivered', 'recalled', 'disposed']

    @property
    def is_hold(self) -> bool:
        return any(e.event_type == TraceEventType.HOLD for e in self.events)


# =============================================================================
# Chain of Custody Logger
# =============================================================================

class ChainOfCustodyLogger:
    """Immutable audit trail for batch custody."""

    def __init__(self, storage_path: str = "sorter/data/custody"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[TraceEvent]] = {}

    def log(self, batch_id: str, event: TraceEvent) -> None:
        if batch_id not in self._cache:
            self._cache[batch_id] = []
        event.batch_id = batch_id
        self._cache[batch_id].append(event)
        self._persist(batch_id)

    def get_events(self, batch_id: str) -> List[TraceEvent]:
        if batch_id not in self._cache:
            self._load(batch_id)
        return self._cache.get(batch_id, [])

    def verify_integrity(self, batch_id: str) -> bool:
        events = self.get_events(batch_id)
        if len(events) < 2:
            return True
        for i in range(1, len(events)):
            if events[i].previous_event_hash != events[i-1].event_hash:
                return False
        return True

    def _persist(self, batch_id: str) -> None:
        path = self.storage_path / f"{batch_id}.json"
        events_data = [e.to_dict() for e in self._cache[batch_id]]
        with open(path, 'w') as f:
            json.dump({'batch_id': batch_id, 'events': events_data, 'last_updated': datetime.now(timezone.utc).isoformat() + 'Z'}, f, indent=2)

    def _load(self, batch_id: str) -> None:
        path = self.storage_path / f"{batch_id}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                self._cache[batch_id] = [self._dict_to_event(e) for e in data['events']]

    def _dict_to_event(self, d: Dict) -> TraceEvent:
        actor = TraceActor(**d['actor'])
        return TraceEvent(
            event_id=d['event_id'], batch_id=d['batch_id'],
            event_type=TraceEventType(d['event_type']),
            timestamp=d['timestamp'], actor=actor,
            location=d['location'], details=d['details'],
            event_hash=d.get('event_hash', ''),
            previous_event_hash=d.get('previous_event_hash', '')
        )


# =============================================================================
# Recall Manager
# =============================================================================

class RecallManager:
    """Handle batch recall operations."""

    def __init__(self, custody_logger: ChainOfCustodyLogger):
        self.custody_logger = custody_logger
        self.recalls: List[RecallRecord] = []
        self._load_recalls()

    def initiate_recall(
        self, defect_type: str, severity: RecallSeverity, reason: str,
        affected_batch_ids: List[str], corrective_action: str = ""
    ) -> RecallRecord:
        recall_id = f"RECALL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        recall = RecallRecord(
            recall_id=recall_id,
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            defect_type=defect_type, severity=severity, reason=reason,
            affected_batch_ids=affected_batch_ids,
            affected_quantity_kg=0.0, status="initiated",
            corrective_action=corrective_action
        )
        total_qty = 0.0
        for bid in affected_batch_ids:
            events = self.custody_logger.get_events(bid)
            for e in events:
                if e.event_type == TraceEventType.PACKAGED:
                    total_qty += e.details.get('quantity_kg', 0)
        recall.affected_quantity_kg = total_qty

        for bid in affected_batch_ids:
            recall_event = TraceEvent(
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                batch_id=bid, event_type=TraceEventType.RECALL,
                timestamp=datetime.now(timezone.utc).isoformat() + "Z",
                actor=TraceActor(actor_id="SYSTEM", actor_name="RecallManager", actor_role="system", shift=""),
                location="system",
                details={'recall_id': recall_id, 'defect_type': defect_type, 'severity': severity.value, 'reason': reason}
            )
            self.custody_logger.log(bid, recall_event)
        self.recalls.append(recall)
        self._persist_recalls()
        return recall

    def get_active_recalls(self) -> List[RecallRecord]:
        return [r for r in self.recalls if r.status != "completed"]

    def close_recall(self, recall_id: str) -> bool:
        for r in self.recalls:
            if r.recall_id == recall_id:
                r.status = "completed"
                r.closed_date = datetime.now(timezone.utc).isoformat() + "Z"
                self._persist_recalls()
                return True
        return False

    def _load_recalls(self) -> None:
        path = Path("sorter/data/recalls.json")
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                self.recalls = [RecallRecord(**r) for r in data.get('recalls', [])]

    def _persist_recalls(self) -> None:
        Path("sorter/data").mkdir(parents=True, exist_ok=True)
        with open(Path("sorter/data/recalls.json"), 'w') as f:
            json.dump({'recalls': [asdict(r) for r in self.recalls], 'last_updated': datetime.now(timezone.utc).isoformat() + 'Z'}, f, indent=2)


# =============================================================================
# Real-Time Batch Tracker
# =============================================================================

class RealTimeBatchTracker:
    """Live monitoring of batch status across the pipeline."""

    def __init__(self, custody_logger: ChainOfCustodyLogger):
        self.custody_logger = custody_logger
        self.lots: Dict[str, BatchLot] = {}

    def register_lot(self, lot: BatchLot) -> None:
        self.lots[lot.lot_id] = lot

    def update_stage(self, lot_id: str, new_stage: BatchStage, actor: TraceActor, location: str, details: Dict = None) -> bool:
        if lot_id not in self.lots:
            return False
        lot = self.lots[lot_id]
        event_type_map = {
            BatchStage.RECEIVED: TraceEventType.RECEIVED,
            BatchStage.INSPECTED: TraceEventType.SAMPLED,
            BatchStage.CONDITIONED: TraceEventType.CONDITIONING_END,
            BatchStage.READY: TraceEventType.CALIBRATED,
            BatchStage.IN_SORTER: TraceEventType.LOADED_TO_SORTER,
            BatchStage.SORTING: TraceEventType.SORTING_START,
            BatchStage.PACKAGED: TraceEventType.PACKAGED,
            BatchStage.QCED: TraceEventType.QC_INSPECTION,
            BatchStage.RELEASED: TraceEventType.RELEASED,
            BatchStage.SHIPPED: TraceEventType.SHIPPED,
            BatchStage.DELIVERED: TraceEventType.DELIVERED,
            BatchStage.RECALLED: TraceEventType.RECALL,
        }
        event_type = event_type_map.get(new_stage, TraceEventType.GRADED)
        event = TraceEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            batch_id=lot_id, event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            actor=actor, location=location, details=details or {}
        )
        lot.add_event(event)
        lot.stage = new_stage
        return True

    def get_lot_status(self, lot_id: str) -> Optional[Dict]:
        if lot_id not in self.lots:
            return None
        lot = self.lots[lot_id]
        return {
            'lot_id': lot_id,
            'stage': lot.stage.value,
            'origin': f"{lot.origin.origin_country}/{lot.origin.region}",
            'processing': lot.origin.processing,
            'recipe': lot.recipe_id,
            'age_hours': round(lot.age_hours, 1),
            'is_hold': lot.is_hold,
            'is_active': lot.is_active,
            'events_count': len(lot.events),
            'last_event': lot.events[-1].event_type.value if lot.events else None,
            'final_defect_rate_pct': lot.metrics.final_defect_rate_pct,
            'grade_a_yield_pct': lot.metrics.grade_a_yield_pct,
        }

    def get_pipeline_summary(self) -> Dict:
        stages_count: Dict[str, int] = {}
        total_beans = 0
        total_grade_a = 0
        active_count = 0
        hold_count = 0
        for lot in self.lots.values():
            stages_count[lot.stage.value] = stages_count.get(lot.stage.value, 0) + 1
            total_beans += lot.metrics.beans_sorted
            total_grade_a += lot.metrics.beans_grade_a
            if lot.is_active:
                active_count += 1
            if lot.is_hold:
                hold_count += 1
        return {
            'total_lots': len(self.lots),
            'active_lots': active_count,
            'on_hold': hold_count,
            'stages': stages_count,
            'total_beans_processed': total_beans,
            'total_grade_a_beans': total_grade_a,
            'overall_grade_a_yield_pct': round(total_grade_a / total_beans * 100, 1) if total_beans > 0 else 0,
        }

    def list_lots(self, stage: Optional[str] = None, origin: Optional[str] = None) -> List[Dict]:
        result = []
        for lot in self.lots.values():
            if stage and lot.stage.value != stage:
                continue
            if origin and origin.lower() not in f"{lot.origin.origin_country} {lot.origin.region}".lower():
                continue
            result.append(self.get_lot_status(lot.lot_id))
        return sorted(result, key=lambda x: x['lot_id'], reverse=True)

    def trace_lot(self, lot_id: str) -> Optional[str]:
        """Generate full chain-of-custody trace for a lot."""
        if lot_id not in self.lots:
            return None
        lot = self.lots[lot_id]
        lines = []
        lines.append(f"\n{'='*90}")
        lines.append(f"  CHAIN OF CUSTODY TRACE — {lot_id}")
        lines.append(f"{'='*90}")
        lines.append(f"  Origin: {lot.origin.farm}, {lot.origin.region}, {lot.origin.origin_country}")
        lines.append(f"  Processing: {lot.origin.processing} | Variety: {lot.origin.variety}")
        lines.append(f"  Recipe: {lot.recipe_id} | Stage: {lot.stage.value}")
        lines.append(f"  Created: {lot.created_at[:19].replace('T', ' ')} UTC")
        lines.append(f"{'='*90}")
        lines.append(f"  {'#':<4} {'TIMESTAMP':<22} {'EVENT':<22} {'ACTOR':<20} {'LOCATION':<16} {'DETAILS'}")
        lines.append(f"{'='*90}")
        for i, evt in enumerate(lot.events, 1):
            ts = evt.timestamp[:19].replace('T', ' ')
            evt_name = evt.event_type.value.replace('_', ' ').title()
            actor_name = f"{evt.actor.actor_name} ({evt.actor.actor_role})"
            loc = evt.location[:15]
            details = ", ".join(f"{k}={v}" for k, v in list(evt.details.items())[:3])
            hash_mark = "✓" if evt.event_hash else "?"
            lines.append(f"  {i:<4} {ts:<22} {hash_mark}{evt_name:<21} {actor_name:<20} {loc:<16} {details[:30]}")
        lines.append(f"{'='*90}")
        integrity = self.custody_logger.verify_integrity(lot_id)
        lines.append(f"  Integrity: {'✓ CHAIN INTACT' if integrity else '✗ CHAIN BROKEN'}")
        lines.append(f"  Total events: {len(lot.events)} | Age: {lot.age_hours:.1f}h | Hold: {'YES ⚠️' if lot.is_hold else 'No'}")
        return "\n".join(lines)


# =============================================================================
# Demo Data Generator
# =============================================================================

def create_demo_lots() -> List[BatchLot]:
    """Create demo batch lots for demonstration."""
    demo_origins = [
        BatchOrigin(origin_country="Ethiopia", region="Yirgacheffe", farm="Worka Cooperative",
                    altitude_m=1950, harvest_season="2025", processing="Washed", variety="Heirloom",
                    importer="Trabocca", arrival_date="2026-05-10"),
        BatchOrigin(origin_country="Kenya", region="Kirinyaga", farm="Baragwi Farmers Co-op",
                    altitude_m=1700, harvest_season="2025", processing="Washed", variety="SL28/SL34",
                    importer="Cafe Imports", arrival_date="2026-05-08"),
        BatchOrigin(origin_country="Brazil", region="Cerrado Mineiro", farm="Fazenda Santa Ines",
                    altitude_m=1100, harvest_season="2025", processing="Natural", variety="Yellow Bourbon",
                    importer="Mercon", arrival_date="2026-05-05"),
        BatchOrigin(origin_country="Colombia", region="Huila", farm="Finca El Paraiso",
                    altitude_m=1650, harvest_season="2025", processing="Honey", variety="Castillo",
                    importer="Sucafina", arrival_date="2026-05-03"),
        BatchOrigin(origin_country="Guatemala", region="Antigua", farm="Finca San Sebastian",
                    altitude_m=1500, harvest_season="2025", processing="Washed", variety="Bourbon/Catuai",
                    importer="Organic Products", arrival_date="2026-05-01"),
    ]
    demo_recipes = ["Ethiopian_Washed", "Kenyan_Washed_AA", "Brazilian_Natural", "Colombian_Honey", "Guatemalan_Washed"]
    demo_stages = [BatchStage.DELIVERED, BatchStage.SHIPPED, BatchStage.QCED, BatchStage.SORTING, BatchStage.IN_SORTER]
    shifts = ["Morning", "Afternoon", "Night"]

    lots = []
    now = datetime.now(timezone.utc)
    for i, (origin, recipe, stage) in enumerate(zip(demo_origins, demo_recipes, demo_stages)):
        lot_id = f"LOT-2026-05{(13-i):02d}-0{i+1}"
        created = now - timedelta(hours=i*18 + 5)
        lot = BatchLot(
            lot_id=lot_id, origin=origin, recipe_id=recipe, stage=stage,
            created_at=created.isoformat().replace("+00:00", "Z"),
            updated_at=(now - timedelta(hours=i*2)).isoformat().replace("+00:00", "Z"),
            metrics=BatchMetrics(
                total_beans_received=3000 + i*500,
                defect_rate_at_receipt_pct=4.5 + i*0.5,
                avg_moisture_pct=11.2 + i*0.1, avg_density_g_ml=0.68 + i*0.01,
                color_L_avg=45.0 + i, color_a_avg=12.0, color_b_avg=18.0,
                weight_cv_pct=12.0,
                beans_sorted=(3000 + i*500) - int((3000 + i*500) * (0.045 + i*0.005)),
                beans_grade_a=int((3000 + i*500) * (0.85 - i*0.02)),
                beans_rejected=int((3000 + i*500) * (0.045 + i*0.005)),
                final_defect_rate_pct=1.8 + i*0.2, grade_a_yield_pct=85 - i*2,
                processing_yield_pct=94 - i
            ),
            shelf_life_date=(created + timedelta(days=365)).strftime('%Y-%m-%d')
        )

        events_data = [
            (TraceEventType.RECEIVED, 0, "warehouse_A", "Received at warehouse", {"quantity_kg": 60}),
            (TraceEventType.SAMPLED, 2, "qc_lab", "Sampled for QC", {"sample_size": 300}),
            (TraceEventType.CONDITIONING_START, 4, "conditioning_room", "Started acclimatization", {"temp_c": 20, "humidity_pct": 60}),
            (TraceEventType.CONDITIONING_END, 24, "conditioning_room", "Conditioning complete", {"duration_h": 20}),
            (TraceEventType.CALIBRATED, 26, "sorter_line_1", "Calibrated on sorter", {"recipe": recipe}),
            (TraceEventType.LOADED_TO_SORTER, 28, "sorter_line_1", "Loaded to sorter", {"batch_size_kg": 5}),
            (TraceEventType.SORTING_START, 30, "sorter_line_1", "Sorting started", {"target_bpm": 50}),
        ]
        shift_idx = 0
        for evt_type, age_h, location, desc, details in events_data:
            evt_time = created + timedelta(hours=age_h)
            actor = TraceActor(actor_id=f"OP-{100+i:03d}", actor_name=f"Operator {i+1}", actor_role="operator", shift=shifts[shift_idx % 3])
            event = TraceEvent(
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                batch_id=lot_id, event_type=evt_type,
                timestamp=evt_time.isoformat() + "Z",
                actor=actor, location=location, details=details
            )
            lot.add_event(event)
            shift_idx += 1

        if stage.value in ['qced', 'released', 'shipped', 'delivered']:
            for evt_type, age_h, location, desc, details in [
                (TraceEventType.SORTING_END, 72 + i*5, "sorter_line_1", "Sorting ended", {"retained": 2850 + i*50, "rejected": 150 + i*10}),
                (TraceEventType.PACKAGED, 74 + i*5, "packaging", "Packaged in GrainPro", {"pack_count": 12, "bag_kg": 0.25}),
                (TraceEventType.QC_INSPECTION, 76 + i*5, "qc_lab", "Final QC passed", {"sample_size": 100, "defects_found": 1}),
            ]:
                evt_time = created + timedelta(hours=age_h)
                actor = TraceActor(actor_id=f"QA-{200+i:03d}", actor_name=f"QA Inspector {i+1}", actor_role="qa_inspector", shift="Morning")
                event = TraceEvent(
                    event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                    batch_id=lot_id, event_type=evt_type,
                    timestamp=evt_time.isoformat() + "Z",
                    actor=actor, location=location, details=details
                )
                lot.add_event(event)

        if stage.value in ['released', 'shipped', 'delivered']:
            evt_time = created + timedelta(hours=80 + i*5)
            actor = TraceActor(actor_id="QA-201", actor_name="QA Manager", actor_role="manager", shift="Morning")
            event = TraceEvent(
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                batch_id=lot_id, event_type=TraceEventType.RELEASED,
                timestamp=evt_time.isoformat() + "Z",
                actor=actor, location="qa_office", details={"release_code": f"REL-{2026}{13-i:02d}"}
            )
            lot.add_event(event)

        if stage.value in ['shipped', 'delivered']:
            evt_time = created + timedelta(hours=96 + i*5)
            actor = TraceActor(actor_id="SHIP-301", actor_name="Logistics", actor_role="logistics", shift="Morning")
            event = TraceEvent(
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                batch_id=lot_id, event_type=TraceEventType.SHIPPED,
                timestamp=evt_time.isoformat() + "Z",
                actor=actor, location="shipping_bay", details={"carrier": "DHL Express", "tracking": f"DHL-{2026}{130000+i:06d}"}
            )
            lot.add_event(event)

        if stage.value == 'delivered':
            evt_time = created + timedelta(hours=144 + i*5)
            actor = TraceActor(actor_id="SHIP-301", actor_name="Logistics", actor_role="logistics", shift="Morning")
            event = TraceEvent(
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                batch_id=lot_id, event_type=TraceEventType.DELIVERED,
                timestamp=evt_time.isoformat() + "Z",
                actor=actor, location="customer_location", details={"delivery_confirmed": True}
            )
            lot.add_event(event)

        lots.append(lot)
    return lots


# =============================================================================
# CLI Interface
# =============================================================================

def cmd_list(args) -> None:
    tracker = RealTimeBatchTracker(ChainOfCustodyLogger())
    for lot in create_demo_lots():
        tracker.register_lot(lot)
    lots = tracker.list_lots(stage=args.stage, origin=args.origin)
    if not lots:
        print("No lots found.")
        return
    print(f"\n{'='*90}")
    print(f"  {'LOT ID':<22} {'STAGE':<12} {'ORIGIN':<28} {'PROCESS':<10} {'AGE(h)':<7} {'HOLD':<5}")
    print(f"{'='*90}")
    for lot in lots:
        hold_icon = "YES ⚠️" if lot['is_hold'] else "No"
        print(f"  {lot['lot_id']:<22} {lot['stage']:<12} {lot['origin']:<28} {lot['processing']:<10} {lot['age_hours']:<7} {hold_icon}")
    print(f"{'='*90}")
    summary = tracker.get_pipeline_summary()
    print(f"\nPipeline Summary: {summary['total_lots']} lots | {summary['active_lots']} active | {summary['on_hold']} on hold")
    print(f"Overall Grade A Yield: {summary['overall_grade_a_yield_pct']}% | Total beans: {summary['total_beans_processed']:,}")


def cmd_track(args) -> None:
    tracker = RealTimeBatchTracker(ChainOfCustodyLogger())
    for lot in create_demo_lots():
        tracker.register_lot(lot)
    status = tracker.get_lot_status(args.lot_id)
    if not status:
        print(f"Lot {args.lot_id} not found.")
        return
    print(f"\n{'='*60}")
    print(f"  BATCH STATUS — {args.lot_id}")
    print(f"{'='*60}")
    for k, v in status.items():
        print(f"  {k:<25} {v}")
    print(f"{'='*60}")


def cmd_trace(args) -> None:
    tracker = RealTimeBatchTracker(ChainOfCustodyLogger())
    for lot in create_demo_lots():
        tracker.register_lot(lot)
    trace = tracker.trace_lot(args.lot_id)
    if not trace:
        print(f"Lot {args.lot_id} not found.")
        return
    print(trace)


def cmd_summary(args) -> None:
    tracker = RealTimeBatchTracker(ChainOfCustodyLogger())
    for lot in create_demo_lots():
        tracker.register_lot(lot)
    summary = tracker.get_pipeline_summary()
    print(f"\n{'='*60}")
    print(f"  PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total Lots:        {summary['total_lots']}")
    print(f"  Active Lots:      {summary['active_lots']}")
    print(f"  On Hold:          {summary['on_hold']}")
    print(f"  Total Beans:      {summary['total_beans_processed']:,}")
    print(f"  Grade A Beans:    {summary['total_grade_a_beans']:,}")
    print(f"  Overall Yield:    {summary['overall_grade_a_yield_pct']}%")
    print(f"\n  Stages:")
    for stage, count in sorted(summary['stages'].items()):
        print(f"    {stage:<20} {count}")
    print(f"{'='*60}")


def cmd_recall(args) -> None:
    logger = ChainOfCustodyLogger()
    manager = RecallManager(logger)
    severity_map = {"info": RecallSeverity.INFORMATIONAL, "iii": RecallSeverity.CLASS_III,
                    "ii": RecallSeverity.CLASS_II, "i": RecallSeverity.CLASS_I}
    severity = severity_map.get(args.severity.lower() if args.severity else "iii", RecallSeverity.CLASS_III)
    recall = manager.initiate_recall(
        defect_type=args.defect,
        severity=severity,
        reason=args.reason or "Manual recall initiated",
        affected_batch_ids=args.lot_ids or [],
        corrective_action=args.action or ""
    )
    print(f"\nRecall Initiated: {recall.recall_id}")
    print(f"  Defect: {recall.defect_type} | Severity: {recall.severity.value}")
    print(f"  Affected batches: {len(recall.affected_batch_ids)}")
    print(f"  Status: {recall.status}")


def cmd_export(args) -> None:
    tracker = RealTimeBatchTracker(ChainOfCustodyLogger())
    for lot in create_demo_lots():
        tracker.register_lot(lot)
    lots = tracker.list_lots(stage=args.stage)
    path = Path(args.output or "sorter/reports/batch_lots_export.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump({'lots': lots, 'exported_at': datetime.now(timezone.utc).isoformat() + 'Z', 'total': len(lots)}, f, indent=2)
    print(f"Exported {len(lots)} lots to {path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch Tracking & Traceability System")
    subparsers = parser.add_subparsers(dest='command')

    p_list = subparsers.add_parser('list', help="List all batches")
    p_list.add_argument('--stage', help="Filter by stage")
    p_list.add_argument('--origin', help="Filter by origin country/region")
    p_list.set_defaults(func=cmd_list)

    p_track = subparsers.add_parser('track', help="Track a specific batch")
    p_track.add_argument('lot_id', help="Lot ID")
    p_track.set_defaults(func=cmd_track)

    p_trace = subparsers.add_parser('trace', help="Full chain-of-custody trace")
    p_trace.add_argument('lot_id', help="Lot ID")
    p_trace.set_defaults(func=cmd_trace)

    p_summary = subparsers.add_parser('summary', help="Pipeline summary")
    p_summary.set_defaults(func=cmd_summary)

    p_recall = subparsers.add_parser('recall', help="Initiate recall")
    p_recall.add_argument('--defect', required=True, help="Defect type")
    p_recall.add_argument('--severity', default='iii', help="Severity: info/iii/ii/i")
    p_recall.add_argument('--reason', help="Reason for recall")
    p_recall.add_argument('--lot-ids', nargs='+', help="Affected lot IDs")
    p_recall.add_argument('--action', help="Corrective action")
    p_recall.set_defaults(func=cmd_recall)

    p_export = subparsers.add_parser('export', help="Export batch data")
    p_export.add_argument('--stage', help="Filter by stage")
    p_export.add_argument('--output', help="Output file path")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
    else:
        args.func(args)


if __name__ == "__main__":
    main()