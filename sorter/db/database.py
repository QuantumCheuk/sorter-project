# sorter/db/database.py
# SQLite database layer for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-02

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from .models import (
    BatchRecord, BeanRecord, CalibrationRecord, SystemEvent,
    BeanDefect, BatchState, SortGrade,
)

# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id          TEXT PRIMARY KEY,
    started_at_utc    TEXT NOT NULL,
    ended_at_utc     TEXT DEFAULT '',
    state             INTEGER DEFAULT 0,
    target_weight_g   REAL DEFAULT 250.0,
    target_throughput_kg_h REAL DEFAULT 2.0,
    channels_used     INTEGER DEFAULT 1,
    origin            TEXT DEFAULT '',
    variety           TEXT DEFAULT '',
    process           TEXT DEFAULT '',
    lot_number        TEXT DEFAULT '',
    total_beans       INTEGER DEFAULT 0,
    defective_beans   INTEGER DEFAULT 0,
    ejected_beans     INTEGER DEFAULT 0,
    total_weight_g    REAL DEFAULT 0.0,
    grade_a_count     INTEGER DEFAULT 0,
    grade_b_count     INTEGER DEFAULT 0,
    grade_c_count     INTEGER DEFAULT 0,
    grade_reject_count INTEGER DEFAULT 0,
    defect_counts_json TEXT DEFAULT '{}',
    avg_quality_score REAL DEFAULT 0.0,
    avg_weight_g      REAL DEFAULT 0.0,
    avg_moisture_pct   REAL DEFAULT 0.0,
    avg_density_gcc    REAL DEFAULT 0.0,
    avg_color_L        REAL DEFAULT 0.0,
    eject_reasons_json TEXT DEFAULT '{}',
    operator_notes     TEXT DEFAULT '',
    calibration_id     TEXT DEFAULT '',
    created_at_utc     TEXT DEFAULT (datetime('now', 'utc'))
);

CREATE TABLE IF NOT EXISTS beans (
    bean_id           TEXT PRIMARY KEY,
    batch_id          TEXT NOT NULL,
    timestamp_utc     TEXT NOT NULL,
    channel           INTEGER DEFAULT 1,
    bean_index        INTEGER DEFAULT 0,
    sensors_json       TEXT DEFAULT '{}',
    color_json         TEXT DEFAULT '{}',
    primary_defect    INTEGER DEFAULT 0,
    secondary_defect  INTEGER DEFAULT 0,
    ml_confidence     REAL DEFAULT 1.0,
    quality_score     REAL DEFAULT 100.0,
    grade             INTEGER DEFAULT 0,
    assigned_bin      TEXT DEFAULT '',
    ejected           INTEGER DEFAULT 0,
    eject_reason      TEXT DEFAULT '',
    top_image_path    TEXT DEFAULT '',
    bottom_image_path TEXT DEFAULT '',
    created_at_utc     TEXT DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS calibrations (
    cal_id                  TEXT PRIMARY KEY,
    sensor                  TEXT NOT NULL,
    calibration_method      TEXT NOT NULL,
    calibration_date_utc    TEXT NOT NULL,
    operator_id             TEXT DEFAULT '',
    reference_values_json   TEXT DEFAULT '{}',
    coefficients_json       TEXT DEFAULT '{}',
    std_error               REAL DEFAULT 0.0,
    r_squared              REAL DEFAULT 0.0,
    notes                   TEXT DEFAULT '',
    created_at_utc           TEXT DEFAULT (datetime('now', 'utc'))
);

CREATE TABLE IF NOT EXISTS system_events (
    event_id       TEXT PRIMARY KEY,
    timestamp_utc  TEXT NOT NULL,
    severity       TEXT NOT NULL,
    component      TEXT NOT NULL,
    message        TEXT NOT NULL,
    details_json   TEXT DEFAULT '{}',
    created_at_utc  TEXT DEFAULT (datetime('now', 'utc'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_beans_batch_id  ON beans(batch_id);
CREATE INDEX IF NOT EXISTS idx_beans_defect   ON beans(primary_defect);
CREATE INDEX IF NOT EXISTS idx_beans_grade    ON beans(grade);
CREATE INDEX IF NOT EXISTS idx_beans_timestamp ON beans(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_batches_state  ON batches(state);
CREATE INDEX IF NOT EXISTS idx_batches_started ON batches(started_at_utc);
CREATE INDEX IF NOT EXISTS idx_events_severity ON system_events(severity);
CREATE INDEX IF NOT EXISTS idx_events_component ON system_events(component);
"""

# ─── Database Manager ─────────────────────────────────────────────────────────

class Database:
    """
    Thread-safe SQLite database manager.
    Uses connection-per-thread pattern for safety.

    v2 2026-05-17: Added WAL auto-checkpoint (P0-23 fix).
    WAL mode without checkpoint causes unbounded disk growth and
    degraded read performance. Checkpoint runs every N writes or on demand.
    """

    def __init__(self, db_path: Optional[str] = None,
                 wal_checkpoint_interval: int = 1000):
        if db_path is None:
            base = Path.home() / ".husky_sorter"
            base.mkdir(exist_ok=True)
            db_path = str(base / "sorter_data.db")
        self.db_path = db_path
        self._local = threading.local()
        self._write_counter = 0
        self._wal_checkpoint_interval = wal_checkpoint_interval  # 0 = disabled
        self._checkpoint_lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        """Get thread-local DB connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            # Performance
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for explicit transactions."""
        conn = self._conn()
        try:
            yield conn
            conn.commit()
            self._write_counter += 1
            self._maybe_checkpoint(conn)
        except Exception:
            conn.rollback()
            raise

    def _maybe_checkpoint(self, conn: sqlite3.Connection) -> None:
        """Run WAL checkpoint if write threshold reached (P0-23 fix)."""
        if self._wal_checkpoint_interval <= 0:
            return
        if self._write_counter < self._wal_checkpoint_interval:
            return

        with self._checkpoint_lock:
            # Double-check under lock
            if self._write_counter < self._wal_checkpoint_interval:
                return
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                self._write_counter = 0
            except sqlite3.OperationalError:
                pass  # Checkpoint failed (DB locked) — retry next interval

    def wal_checkpoint(self, mode: str = "PASSIVE") -> None:
        """Manually trigger a WAL checkpoint.

        Args:
            mode: "PASSIVE" (non-blocking), "FULL" (wait for readers),
                  "RESTART" (full + truncate WAL)
        """
        conn = self._conn()
        try:
            conn.execute(f"PRAGMA wal_checkpoint({mode})")
            self._write_counter = 0
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"WAL checkpoint failed: {e}") from e

    def _init_db(self) -> None:
        """Create schema if not exists."""
        with self.transaction() as conn:
            conn.executescript(SCHEMA)

    def close(self) -> None:
        """Close thread-local connection and run final checkpoint."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self.wal_checkpoint("RESTART")
            except RuntimeError:
                pass
            self._local.conn.close()
            self._local.conn = None

    # ─── Batch operations ─────────────────────────────────────────────────────

    def insert_batch(self, batch: BatchRecord) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO batches (
                    batch_id, started_at_utc, ended_at_utc, state,
                    target_weight_g, target_throughput_kg_h, channels_used,
                    origin, variety, process, lot_number,
                    total_beans, defective_beans, ejected_beans, total_weight_g,
                    grade_a_count, grade_b_count, grade_c_count, grade_reject_count,
                    defect_counts_json, avg_quality_score, avg_weight_g,
                    avg_moisture_pct, avg_density_gcc, avg_color_L,
                    eject_reasons_json, operator_notes, calibration_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch.to_sql_values(),
            )

    def get_batch(self, batch_id: str) -> Optional[BatchRecord]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_batch(row)

    def list_batches(
        self,
        limit: int = 50,
        offset: int = 0,
        state: Optional[int] = None,
        origin: Optional[str] = None,
    ) -> List[BatchRecord]:
        conn = self._conn()
        query = "SELECT * FROM batches WHERE 1=1"
        params: List[Any] = []
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        if origin:
            query += " AND origin LIKE ?"
            params.append(f"%{origin}%")
        query += " ORDER BY started_at_utc DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_batch(r) for r in rows]

    def update_batch_state(self, batch_id: str, state: int, ended_at_utc: str = "") -> None:
        conn = self._conn()
        if ended_at_utc:
            conn.execute(
                "UPDATE batches SET state=?, ended_at_utc=? WHERE batch_id=?",
                (state, ended_at_utc, batch_id),
            )
        else:
            conn.execute(
                "UPDATE batches SET state=? WHERE batch_id=?",
                (state, batch_id),
            )

    def update_batch_summary(self, batch_id: str, **fields) -> None:
        """Update computed summary fields after batch ends."""
        allowed = {
            "total_beans", "defective_beans", "ejected_beans", "total_weight_g",
            "grade_a_count", "grade_b_count", "grade_c_count", "grade_reject_count",
            "defect_counts_json", "avg_quality_score", "avg_weight_g",
            "avg_moisture_pct", "avg_density_gcc", "avg_color_L",
            "eject_reasons_json", "ended_at_utc",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn = self._conn()
        conn.execute(
            f"UPDATE batches SET {set_clause} WHERE batch_id=?",
            (*updates.values(), batch_id),
        )

    # ─── Bean operations ─────────────────────────────────────────────────────

    def insert_bean(self, bean: BeanRecord) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO beans (
                    bean_id, batch_id, timestamp_utc, channel, bean_index,
                    sensors_json, color_json,
                    primary_defect, secondary_defect, ml_confidence,
                    quality_score, grade, assigned_bin,
                    ejected, eject_reason, top_image_path, bottom_image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                bean.to_sql_values(),
            )

    def insert_beans_bulk(self, beans: List[BeanRecord]) -> None:
        """Bulk insert for performance."""
        if not beans:
            return
        with self.transaction() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO beans (
                    bean_id, batch_id, timestamp_utc, channel, bean_index,
                    sensors_json, color_json,
                    primary_defect, secondary_defect, ml_confidence,
                    quality_score, grade, assigned_bin,
                    ejected, eject_reason, top_image_path, bottom_image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [b.to_sql_values() for b in beans],
            )

    def get_beans_for_batch(
        self,
        batch_id: str,
        defect_filter: Optional[int] = None,
        grade_filter: Optional[int] = None,
        limit: int = 10000,
    ) -> List[BeanRecord]:
        conn = self._conn()
        query = "SELECT * FROM beans WHERE batch_id = ?"
        params: List[Any] = [batch_id]
        if defect_filter is not None:
            query += " AND primary_defect = ?"
            params.append(defect_filter)
        if grade_filter is not None:
            query += " AND grade = ?"
            params.append(grade_filter)
        query += " ORDER BY bean_index LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_bean(r) for r in rows]

    def count_beans(self, batch_id: str) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM beans WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    # ─── Calibration operations ──────────────────────────────────────────────

    def insert_calibration(self, cal: CalibrationRecord) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO calibrations (
                    cal_id, sensor, calibration_method, calibration_date_utc,
                    operator_id, reference_values_json, coefficients_json,
                    std_error, r_squared, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cal.cal_id, cal.sensor, cal.calibration_method,
                    cal.calibration_date_utc, cal.operator_id,
                    cal.reference_values_json, cal.coefficients_json,
                    cal.std_error, cal.r_squared, cal.notes,
                ),
            )

    def get_calibrations(self, sensor: Optional[str] = None, limit: int = 50) -> List[CalibrationRecord]:
        conn = self._conn()
        if sensor:
            rows = conn.execute(
                "SELECT * FROM calibrations WHERE sensor=? ORDER BY calibration_date_utc DESC LIMIT ?",
                (sensor, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM calibrations ORDER BY calibration_date_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_calibration(r) for r in rows]

    def get_latest_calibration(self, sensor: str) -> Optional[CalibrationRecord]:
        rows = self.get_calibrations(sensor=sensor, limit=1)
        return rows[0] if rows else None

    # ─── System events ───────────────────────────────────────────────────────

    def insert_event(self, event: SystemEvent) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO system_events (
                    event_id, timestamp_utc, severity, component, message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event.event_id, event.timestamp_utc, event.severity,
                 event.component, event.message, event.details_json),
            )

    def get_events(
        self,
        severity: Optional[str] = None,
        component: Optional[str] = None,
        since_utc: Optional[str] = None,
        limit: int = 200,
    ) -> List[SystemEvent]:
        conn = self._conn()
        query = "SELECT * FROM system_events WHERE 1=1"
        params: List[Any] = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if component:
            query += " AND component = ?"
            params.append(component)
        if since_utc:
            query += " AND timestamp_utc >= ?"
            params.append(since_utc)
        query += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ─── Statistics ───────────────────────────────────────────────────────────

    def get_batch_stats(self, batch_id: str) -> Dict[str, Any]:
        conn = self._conn()
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN primary_defect != 0 THEN 1 ELSE 0 END) as defective,
                SUM(CASE WHEN ejected = 1 THEN 1 ELSE 0 END) as ejected,
                AVG(quality_score) as avg_score,
                AVG(CAST(sensors_json AS REAL)) as avg_weight
            FROM beans WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        return dict(row) if row else {}

    def get_system_stats(self) -> Dict[str, Any]:
        conn = self._conn()
        c = conn.execute("SELECT COUNT(*) as cnt FROM batches").fetchone()
        b = conn.execute("SELECT COUNT(*) as cnt FROM beans").fetchone()
        e = conn.execute("SELECT COUNT(*) as cnt FROM system_events WHERE severity IN ('ERROR','CRITICAL')").fetchone()
        cal = conn.execute("SELECT COUNT(*) as cnt FROM calibrations").fetchone()
        db_size_kb = os.path.getsize(self.db_path) / 1024 if os.path.exists(self.db_path) else 0
        return {
            "total_batches": c["cnt"] if c else 0,
            "total_beans": b["cnt"] if b else 0,
            "critical_events": e["cnt"] if e else 0,
            "calibrations": cal["cnt"] if cal else 0,
            "db_size_kb": round(db_size_kb, 1),
            "db_path": self.db_path,
        }

    # ─── Row converters ───────────────────────────────────────────────────────

    def _row_to_batch(self, row: sqlite3.Row) -> BatchRecord:
        return BatchRecord(
            batch_id=str(row["batch_id"]),
            started_at_utc=str(row["started_at_utc"]),
            ended_at_utc=str(row["ended_at_utc"] or ""),
            state=int(row["state"]),
            target_weight_g=float(row["target_weight_g"]),
            target_throughput_kg_h=float(row["target_throughput_kg_h"]),
            channels_used=int(row["channels_used"]),
            origin=str(row["origin"] or ""),
            variety=str(row["variety"] or ""),
            process=str(row["process"] or ""),
            lot_number=str(row["lot_number"] or ""),
            total_beans=int(row["total_beans"]),
            defective_beans=int(row["defective_beans"]),
            ejected_beans=int(row["ejected_beans"]),
            total_weight_g=float(row["total_weight_g"]),
            grade_a_count=int(row["grade_a_count"]),
            grade_b_count=int(row["grade_b_count"]),
            grade_c_count=int(row["grade_c_count"]),
            grade_reject_count=int(row["grade_reject_count"]),
            defect_counts_json=str(row["defect_counts_json"] or "{}"),
            avg_quality_score=float(row["avg_quality_score"]),
            avg_weight_g=float(row["avg_weight_g"]),
            avg_moisture_pct=float(row["avg_moisture_pct"]),
            avg_density_gcc=float(row["avg_density_gcc"]),
            avg_color_L=float(row["avg_color_L"]),
            eject_reasons_json=str(row["eject_reasons_json"] or "{}"),
            operator_notes=str(row["operator_notes"] or ""),
            calibration_id=str(row["calibration_id"] or ""),
        )

    def _row_to_bean(self, row: sqlite3.Row) -> BeanRecord:
        sensors = json.loads(row["sensors_json"] or "{}")
        color_data = json.loads(row["color_json"] or "{}")
        color = None
        if color_data:
            from .models import ColorReading
            color = ColorReading(**color_data)
        from .models import SensorSnapshot
        sensor_snapshot = SensorSnapshot(
            weight_g=sensors.get("weight_g", 0.0),
            moisture_pct=sensors.get("moisture_pct", 0.0),
            density_gcc=sensors.get("density_gcc", 0.0),
            size_mm=sensors.get("size_mm", 0.0),
            color=color,
        )
        return BeanRecord(
            bean_id=str(row["bean_id"]),
            batch_id=str(row["batch_id"]),
            timestamp_utc=str(row["timestamp_utc"]),
            channel=int(row["channel"]),
            bean_index=int(row["bean_index"]),
            sensors=sensor_snapshot,
            primary_defect=int(row["primary_defect"]),
            secondary_defect=int(row["secondary_defect"]),
            ml_confidence=float(row["ml_confidence"]),
            quality_score=float(row["quality_score"]),
            grade=int(row["grade"]),
            assigned_bin=str(row["assigned_bin"] or ""),
            ejected=bool(row["ejected"]),
            eject_reason=str(row["eject_reason"] or ""),
            top_image_path=str(row["top_image_path"] or ""),
            bottom_image_path=str(row["bottom_image_path"] or ""),
        )

    def _row_to_calibration(self, row: sqlite3.Row) -> CalibrationRecord:
        return CalibrationRecord(
            cal_id=str(row["cal_id"]),
            sensor=str(row["sensor"]),
            calibration_method=str(row["calibration_method"]),
            calibration_date_utc=str(row["calibration_date_utc"]),
            operator_id=str(row["operator_id"] or ""),
            reference_values_json=str(row["reference_values_json"] or "{}"),
            coefficients_json=str(row["coefficients_json"] or "{}"),
            std_error=float(row["std_error"]),
            r_squared=float(row["r_squared"]),
            notes=str(row["notes"] or ""),
        )

    def _row_to_event(self, row: sqlite3.Row) -> SystemEvent:
        return SystemEvent(
            event_id=str(row["event_id"]),
            timestamp_utc=str(row["timestamp_utc"]),
            severity=str(row["severity"]),
            component=str(row["component"]),
            message=str(row["message"]),
            details_json=str(row["details_json"] or "{}"),
        )
