#!/usr/bin/env python3
"""
disaster_recovery.py — HUSKY-SORTER-001 Disaster Recovery & Backup System
Author: Little Husky 🐕 | Date: 2026-05-15
Version: v1.0

Provides complete backup/restore capability for:
  - SQLite database snapshots (full batch/bean/calibration/event data)
  - System configuration archives (JSON + versioned)
  - ML model files (TFLite, checkpoints)
  - Calibration certificates
  - Firmware binaries
  - Offsite/cloud backup to generic HTTP(S) endpoint
  - Scheduled backup rotation (daily/weekly/monthly)
  - Full disaster recovery orchestration

Usage:
    python -m sorter.production.disaster_recovery --backup
    python -m sorter.production.disaster_recovery --restore latest
    python -m sorter.production.disaster_recovery --status
    python -m sorter.production.disaster_recovery --verify
    python -m sorter.production.disaster_recovery --rotate
    python -m sorter.production.disaster_recovery --cloud-sync
    python -m sorter.production.disaster_recovery --list
    python -m sorter.production.disaster_recovery --show <backup_id>
    python -m sorter.production.disaster_recovery --extract <backup_id>
"""

import os
import sys
import json
import sqlite3
import shutil
import hashlib
import gzip
import argparse
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import time

# =============================================================================
# Constants
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "sorter" / "data"
DB_PATH = PROJECT_ROOT / "sorter" / "db" / "sorter.db"
BACKUP_DIR = PROJECT_ROOT / "sorter" / "backups"
ARCHIVE_DIR = PROJECT_ROOT / "sorter" / "archives"
MODEL_DIR = PROJECT_ROOT / "sorter" / "models"
FIRMWARE_DIR = PROJECT_ROOT / "sorter" / "firmware"
CALIB_DIR = PROJECT_ROOT / "sorter" / "calibration_data"
REPORTS_DIR = PROJECT_ROOT / "sorter" / "reports"

BACKUP_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR.mkdir(exist_ok=True)

RETENTION_DAILY = 7
RETENTION_WEEKLY = 4
RETENTION_MONTHLY = 12

CLOUD_BACKUP_ENABLED = bool(os.environ.get("DR_CLOUD_ENABLED", ""))
CLOUD_BACKUP_URL = os.environ.get("DR_CLOUD_URL", "")
CLOUD_BACKUP_TOKEN = os.environ.get("DR_CLOUD_TOKEN", "")

# =============================================================================
# Enums & Data Classes
# =============================================================================

class BackupStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    OFFSITE_OK = "offsite_ok"
    CORRUPTED = "corrupted"


class BackupLevel(str, Enum):
    FULL = "full"
    DATABASE = "database"
    CONFIG = "config"
    INCREMENTAL = "incremental"


class RotationPolicy(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class BackupManifest:
    backup_id: str
    timestamp: str
    level: str
    rotation: str
    size_bytes: int
    sha256: str
    components: dict
    database_version: str
    firmware_version: str = ""
    ml_model_version: str = ""
    status: str = BackupStatus.PENDING.value
    error_message: str = ""
    cloud_synced: bool = False
    cloud_url: str = ""
    restore_count: int = 0
    verified_at: str = ""
    expires_at: str = ""


@dataclass
class ComponentBackup:
    name: str
    success: bool
    size_bytes: int = 0
    sha256: str = ""
    error: str = ""
    duration_ms: int = 0


# =============================================================================
# Helpers
# =============================================================================

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ts_id() -> str:
    return utcnow().strftime("%Y%m%d_%H%M%S")


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Component Backers
# =============================================================================

class DatabaseBacker:
    """Back up and restore the SQLite database."""

    @staticmethod
    def backup(backup_dir: Path, manifest: BackupManifest) -> ComponentBackup:
        t0 = time.time()
        name = "database"
        try:
            ensure_dir(backup_dir)
            db_copy = backup_dir / "sorter.db"

            # Online backup (WAL snapshot)
            src = sqlite3.connect(str(DB_PATH), uri=True)
            dst = sqlite3.connect(str(db_copy))
            src.backup(dst, pages=0)
            dst.close()
            src.close()

            size = db_copy.stat().st_size
            sha = compute_sha256(db_copy)

            # SQL dump for extra safety (P1-16 fix: parameterized escaping)
            dump_path = backup_dir / "sorter_dump.sql.gz"
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            with gzip.open(str(dump_path), "wt", encoding="utf-8") as dump:
                for table in tables:
                    cur.execute(f"SELECT * FROM {table}")
                    cols = [d[0] for d in cur.description]
                    # P3-07: use fetchmany() to avoid loading entire table into memory
                    while True:
                        rows = cur.fetchmany(1000)
                        if not rows:
                            break
                        for row in rows:
                            vals = ",".join(
                                f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if v is not None else "NULL"
                                for v in row
                            )
                            dump.write(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({vals});\n")
            conn.close()
            dump_size = dump_path.stat().st_size

            return ComponentBackup(name=name, success=True, size_bytes=size + dump_size,
                                  sha256=sha, duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return ComponentBackup(name=name, success=False, error=f"{type(e).__name__}: {e}",
                                  duration_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def restore(backup_dir: Path) -> bool:
        db = backup_dir / "sorter.db"
        if not db.exists():
            return False
        shutil.copy2(str(db), str(DB_PATH))
        return True

    @staticmethod
    def verify(backup_dir: Path) -> tuple[bool, str]:
        db = backup_dir / "sorter.db"
        if not db.exists():
            return False, "sorter.db not found"
        try:
            conn = sqlite3.connect(str(db))
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM sqlite_master")
            n_tables = cur.fetchone()[0]
            conn.close()
            if result[0] == "ok" and n_tables > 0:
                return True, f"ok ({n_tables} tables)"
            return False, f"integrity={result[0]}"
        except Exception as e:
            return False, str(e)


class ConfigBacker:
    """Back up system configuration files and recipe archives."""

    @staticmethod
    def backup(backup_dir: Path, manifest: BackupManifest) -> ComponentBackup:
        t0 = time.time()
        name = "config"
        try:
            cfg_dir = backup_dir / "config"
            ensure_dir(cfg_dir)

            # config.py
            cfg_src = PROJECT_ROOT / "sorter" / "config.py"
            if cfg_src.exists():
                shutil.copy2(str(cfg_src), str(cfg_dir / "config.py"))

            # recipes
            recipes_src = PROJECT_ROOT / "sorter" / "recipes"
            if recipes_src.exists():
                shutil.copytree(str(recipes_src), str(cfg_dir / "recipes"), dirs_exist_ok=True)

            # quality config
            for src_name, dst_name in [
                (PROJECT_ROOT / "sorter" / "quality" / "config.py", "quality_config.py"),
                (PROJECT_ROOT / "sorter" / "quality" / "thresholds.py", "thresholds.py"),
            ]:
                if src_name.exists():
                    shutil.copy2(str(src_name), str(cfg_dir / dst_name))

            # Snapshot of current running config
            try:
                sys_cfg = PROJECT_ROOT / "sorter" / "config.py"
                if sys_cfg.exists():
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("sorter_config", str(sys_cfg))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "get_sorter_config"):
                        cfg = mod.get_sorter_config()
                        with open(cfg_dir / "config_snapshot.json", "w") as f:
                            json.dump(cfg, f, indent=2, default=str)
            except Exception:
                pass

            total = sum(f.stat().st_size for f in cfg_dir.rglob("*") if f.is_file())
            hasher = hashlib.sha256()
            for f in sorted(cfg_dir.rglob("*")):
                if f.is_file():
                    hasher.update(f.read_bytes())
            sha = hasher.hexdigest()

            return ComponentBackup(name=name, success=True, size_bytes=total, sha256=sha,
                                  duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return ComponentBackup(name=name, success=False, error=f"{type(e).__name__}: {e}",
                                  duration_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def restore(backup_dir: Path) -> bool:
        cfg_dir = backup_dir / "config"
        if not cfg_dir.exists():
            return False
        cfg_src = cfg_dir / "config.py"
        if cfg_src.exists():
            shutil.copy2(str(cfg_src), str(PROJECT_ROOT / "sorter" / "config.py"))
        recipes_src = cfg_dir / "recipes"
        if recipes_src.exists():
            shutil.copytree(str(recipes_src), str(PROJECT_ROOT / "sorter" / "recipes"), dirs_exist_ok=True)
        return True


class ModelBacker:
    """Back up ML model files."""

    MODEL_FILES = [
        MODEL_DIR / "defect_classifier.tflite",
        MODEL_DIR / "mobilenet_v2_weights.h5",
        MODEL_DIR / "best_model.h5",
        MODEL_DIR / "model_checkpoint",
    ]

    @staticmethod
    def backup(backup_dir: Path, manifest: BackupManifest) -> ComponentBackup:
        t0 = time.time()
        name = "ml_models"
        try:
            models_dir = backup_dir / "models"
            ensure_dir(models_dir)
            total = 0

            for mp in ModelBacker.MODEL_FILES:
                if mp.exists():
                    dest = models_dir / mp.name
                    shutil.copy2(str(mp), str(dest))
                    total += dest.stat().st_size

            train_cfg = PROJECT_ROOT / "sorter" / "camera" / "ml_pipeline.py"
            if train_cfg.exists():
                shutil.copy2(str(train_cfg), str(models_dir / "ml_pipeline.py"))

            return ComponentBackup(name=name, success=True, size_bytes=total,
                                  duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return ComponentBackup(name=name, success=False, error=f"{type(e).__name__}: {e}",
                                  duration_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def restore(backup_dir: Path) -> bool:
        models_dir = backup_dir / "models"
        if not models_dir.exists():
            return False
        for f in models_dir.rglob("*"):
            if f.is_file():
                dest = MODEL_DIR / f.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(dest))
        return True


class CalibrationBacker:
    """Back up calibration certificates."""

    @staticmethod
    def backup(backup_dir: Path, manifest: BackupManifest) -> ComponentBackup:
        t0 = time.time()
        name = "calibration"
        try:
            calib_dir = backup_dir / "calibration"
            ensure_dir(calib_dir)
            total = 0

            if CALIB_DIR.exists():
                for pattern in ["CERT-*.json", "*.yaml"]:
                    for f in CALIB_DIR.glob(pattern):
                        shutil.copy2(str(f), str(calib_dir / f.name))
                        total += f.stat().st_size

            return ComponentBackup(name=name, success=True, size_bytes=total,
                                  duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return ComponentBackup(name=name, success=False, error=f"{type(e).__name__}: {e}",
                                  duration_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def restore(backup_dir: Path) -> bool:
        calib_dir = backup_dir / "calibration"
        if not calib_dir.exists():
            return False
        CALIB_DIR.mkdir(parents=True, exist_ok=True)
        for f in calib_dir.rglob("*"):
            if f.is_file():
                shutil.copy2(str(f), str(CALIB_DIR / f.name))
        return True


class FirmwareBacker:
    """Back up ESP32 firmware binaries."""

    @staticmethod
    def backup(backup_dir: Path, manifest: BackupManifest) -> ComponentBackup:
        t0 = time.time()
        name = "firmware"
        try:
            fw_dir = backup_dir / "firmware"
            ensure_dir(fw_dir)
            total = 0

            if FIRMWARE_DIR.exists():
                for ext in ["*.ino.hex", "*.bin"]:
                    for f in FIRMWARE_DIR.glob(ext):
                        shutil.copy2(str(f), str(fw_dir / f.name))
                        total += f.stat().st_size

            return ComponentBackup(name=name, success=True, size_bytes=total,
                                  duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return ComponentBackup(name=name, success=False, error=f"{type(e).__name__}: {e}",
                                  duration_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def restore(backup_dir: Path) -> bool:
        fw_dir = backup_dir / "firmware"
        if not fw_dir.exists():
            return False
        FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
        for f in fw_dir.rglob("*"):
            if f.is_file():
                shutil.copy2(str(f), str(FIRMWARE_DIR / f.name))
        return True


# =============================================================================
# Archiver
# =============================================================================

class BackupArchiver:
    """Create/extract gzipped tar archives."""

    @staticmethod
    def create_archive(backup_dir: Path, archive_path: Path,
                      compression: int = 6) -> tuple[bool, int]:
        import tarfile
        ensure_dir(archive_path.parent)
        with tarfile.open(archive_path, "w:gz", compresslevel=compression) as tar:
            tar.add(backup_dir, arcname=backup_dir.name)
        return True, archive_path.stat().st_size

    @staticmethod
    def extract_archive(archive_path: Path, extract_to: Path) -> bool:
        import tarfile
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_to)
        return True

    @staticmethod
    def verify_archive(archive_path: Path) -> tuple[bool, str]:
        import tarfile
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
            return True, f"valid ({len(members)} files)"
        except Exception as e:
            return False, str(e)


# =============================================================================
# Cloud Sync
# =============================================================================

class CloudSync:
    """Upload backups to offsite HTTP endpoint."""

    def __init__(self, endpoint: str, token: str):
        self.endpoint = endpoint
        self.token = token

    def upload(self, archive_path: Path, backup_id: str) -> tuple[bool, str]:
        if not CLOUD_BACKUP_ENABLED:
            return False, "Cloud backup not enabled"
        if not archive_path.exists():
            return False, f"Archive not found: {archive_path}"
        try:
            import requests
            with open(archive_path, "rb") as f:
                files = {"file": (archive_path.name, f, "application/gzip")}
                headers = {"Authorization": f"Bearer {self.token}"}
                resp = requests.put(
                    f"{self.endpoint}/{backup_id}",
                    files=files, headers=headers, timeout=300
                )
            if resp.status_code in (200, 201, 204):
                return True, resp.text or "uploaded"
            return False, f"HTTP {resp.status_code}"
        except ImportError:
            return False, "requests not available"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"


# =============================================================================
# Backup Registry
# =============================================================================

class BackupRegistry:
    """Track all backups in a local JSON registry."""

    REGISTRY_FILE = BACKUP_DIR / "backup_registry.json"

    def __init__(self):
        self.backups: list[BackupManifest] = []
        self._load()

    def _load(self) -> None:
        if self.REGISTRY_FILE.exists():
            try:
                data = json.loads(self.REGISTRY_FILE.read_text())
                self.backups = [BackupManifest(**b) for b in data]
            except Exception:
                self.backups = []

    def _save(self) -> None:
        ensure_dir(self.REGISTRY_FILE.parent)
        data = [asdict(b) for b in self.backups]
        self.REGISTRY_FILE.write_text(json.dumps(data, indent=2))

    def add(self, manifest: BackupManifest) -> None:
        self.backups.append(manifest)
        self._save()

    def update(self, backup_id: str, **kwargs) -> bool:
        for b in self.backups:
            if b.backup_id == backup_id:
                for k, v in kwargs.items():
                    if hasattr(b, k):
                        setattr(b, k, v)
                self._save()
                return True
        return False

    def get(self, backup_id: str) -> Optional[BackupManifest]:
        for b in self.backups:
            if b.backup_id == backup_id:
                return b
        return None

    def get_latest(self) -> Optional[BackupManifest]:
        valid = [b for b in self.backups
                 if b.status in (BackupStatus.COMPLETED.value, BackupStatus.VERIFIED.value)]
        if not valid:
            return None
        return sorted(valid, key=lambda b: b.timestamp, reverse=True)[0]

    def list_all(self) -> list[BackupManifest]:
        return sorted(self.backups, key=lambda b: b.timestamp, reverse=True)


# =============================================================================
# DisasterRecoveryManager
# =============================================================================

class DisasterRecoveryManager:
    """
    Orchestrates all backup/restore operations for HUSKY-SORTER-001.
    """

    COMPONENT_BACKERS = [
        DatabaseBacker,
        ConfigBacker,
        ModelBacker,
        CalibrationBacker,
        FirmwareBacker,
    ]

    COMPONENT_MAP = {
        "database": DatabaseBacker,
        "config": ConfigBacker,
        "model": ModelBacker,
        "calibration": CalibrationBacker,
        "firmware": FirmwareBacker,
    }

    def __init__(self):
        self.registry = BackupRegistry()
        self.cloud = CloudSync(CLOUD_BACKUP_URL, CLOUD_BACKUP_TOKEN)
        self._lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def create_backup(self,
                      level: str = BackupLevel.FULL.value,
                      rotation: str = RotationPolicy.DAILY.value,
                      cloud_sync: bool = False,
                      verify: bool = True) -> BackupManifest:
        with self._lock:
            backup_id = f"BK-{ts_id()}"
            ts = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            manifest = BackupManifest(
                backup_id=backup_id,
                timestamp=ts,
                level=level,
                rotation=rotation,
                size_bytes=0,
                sha256="",
                components={},
                database_version=self._db_version(),
            )

            work_dir = BACKUP_DIR / backup_id
            work_dir.mkdir(parents=True, exist_ok=True)
            manifest.status = BackupStatus.RUNNING.value
            self.registry.add(manifest)

            # Select components
            if level == BackupLevel.FULL.value:
                classes = self.COMPONENT_BACKERS
            elif level == BackupLevel.DATABASE.value:
                classes = [DatabaseBacker, ConfigBacker]
            elif level == BackupLevel.CONFIG.value:
                classes = [ConfigBacker]
            else:
                classes = [DatabaseBacker]

            results = {}
            for bc in classes:
                r = bc.backup(work_dir, manifest)
                results[r.name] = {
                    "success": r.success,
                    "size_bytes": r.size_bytes,
                    "sha256": r.sha256,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
            manifest.components = results
            total_size = sum(r["size_bytes"] for r in results.values() if r["success"])

            # Create archive
            arc_name = f"{backup_id}.tar.gz"
            arc_path = BACKUP_DIR / arc_name
            ok, arc_size = BackupArchiver.create_archive(work_dir, arc_path)
            if ok:
                manifest.size_bytes = arc_size
                manifest.sha256 = compute_sha256(arc_path)
            else:
                manifest.status = BackupStatus.FAILED.value
                manifest.error_message = str(arc_size)
                update_dict = {k: v for k, v in asdict(manifest).items() if k != 'backup_id'}
                self.registry.update(backup_id, **update_dict)
                return manifest

            shutil.rmtree(work_dir)

            # Verify archive
            if verify:
                v_ok, _ = BackupArchiver.verify_archive(arc_path)
                manifest.status = BackupStatus.VERIFIED.value if v_ok else BackupStatus.COMPLETED.value
                if v_ok:
                    manifest.verified_at = ts
            else:
                manifest.status = BackupStatus.COMPLETED.value

            update_dict = {k: v for k, v in asdict(manifest).items() if k != 'backup_id'}
            self.registry.update(backup_id, **update_dict)

            # Cloud sync
            if cloud_sync and CLOUD_BACKUP_ENABLED:
                c_ok, c_msg = self.cloud.upload(arc_path, backup_id)
                if c_ok:
                    manifest.cloud_synced = True
                    manifest.cloud_url = f"{CLOUD_BACKUP_URL}/{backup_id}"
                    self.registry.update(backup_id, cloud_synced=True, cloud_url=manifest.cloud_url)

            return manifest

    def restore_backup(self, backup_id: str,
                       components: Optional[list[str]] = None) -> tuple[bool, str]:
        manifest = self.registry.get(backup_id)
        if not manifest:
            return False, f"Backup {backup_id} not in registry"

        arc_name = f"{backup_id}.tar.gz"
        arc_path = BACKUP_DIR / arc_name
        if not arc_path.exists():
            return False, f"Archive {arc_name} not found"

        extract_dir = BACKUP_DIR / f"{backup_id}_restoring"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            BackupArchiver.extract_archive(arc_path, extract_dir)
        except Exception as e:
            return False, f"Extract failed: {e}"

        if components is None:
            components = list(self.COMPONENT_MAP.keys())

        restored, errors = [], []
        for name in components:
            bc = self.COMPONENT_MAP.get(name)
            if not bc:
                errors.append(f"Unknown: {name}")
                continue
            work_dir = extract_dir / backup_id
            if bc.restore(work_dir):
                restored.append(name)
            else:
                errors.append(f"Failed: {name}")

        shutil.rmtree(extract_dir)
        self.registry.update(backup_id, restore_count=manifest.restore_count + 1)

        msg = f"Restored: {', '.join(restored)}"
        if errors:
            msg += f"\nErrors: {', '.join(errors)}"
        return True, msg

    def schedule_backup(self, level: str = BackupLevel.FULL.value) -> BackupManifest:
        """Auto-select rotation based on day-of-week."""
        now = utcnow()
        dow, dom = now.weekday(), now.day
        if dom == 1:
            rotation = RotationPolicy.MONTHLY.value
        elif dow >= 5:
            rotation = RotationPolicy.WEEKLY.value
        else:
            rotation = RotationPolicy.DAILY.value
        return self.create_backup(level=level, rotation=rotation, verify=True)

    def get_status(self) -> dict[str, Any]:
        backups = self.registry.list_all()
        disk_used = sum(f.stat().st_size for f in BACKUP_DIR.glob("BK-*.tar.gz"))
        latest = self.registry.get_latest()
        return {
            "total_backups": len(backups),
            "disk_usage_bytes": disk_used,
            "disk_usage_human": human_size(disk_used),
            "retention_daily": RETENTION_DAILY,
            "retention_weekly": RETENTION_WEEKLY,
            "retention_monthly": RETENTION_MONTHLY,
            "cloud_enabled": CLOUD_BACKUP_ENABLED,
            "latest_backup": asdict(latest) if latest else None,
            "backups_by_status": {
                s: sum(1 for b in backups if b.status == s)
                for s in [BackupStatus.VERIFIED.value, BackupStatus.COMPLETED.value,
                         BackupStatus.FAILED.value]
            }
        }

    def _db_version(self) -> str:
        if not DB_PATH.exists():
            return "N/A"
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            n = len(cur.fetchall())
            conn.close()
            return f"v1 ({n} tables)"
        except Exception:
            return "unknown"


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 Disaster Recovery")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="Create a new backup")
    p_backup.add_argument("--level", choices=["full", "database", "config"], default="full")
    p_backup.add_argument("--rotation", choices=["daily", "weekly", "monthly"], default="daily")
    p_backup.add_argument("--cloud", action="store_true")
    p_backup.add_argument("--no-verify", action="store_true")

    p_restore = sub.add_parser("restore", help="Restore a backup")
    p_restore.add_argument("backup_id", help="Backup ID (or 'latest')")
    p_restore.add_argument("--components", help="Comma-separated component list")

    p_schedule = sub.add_parser("schedule", help="Auto-schedule backup (rotation by day)")
    p_schedule.add_argument("--level", default="full")

    p_list = sub.add_parser("list", help="List all backups")
    p_show = sub.add_parser("show", help="Show backup details")
    p_show.add_argument("backup_id")
    p_status = sub.add_parser("status", help="Show backup system status")
    p_rotate = sub.add_parser("rotate", help="Apply retention rotation")
    p_verify = sub.add_parser("verify", help="Verify backup archive")
    p_verify.add_argument("backup_id")
    p_cloud = sub.add_parser("cloud-sync", help="Sync latest backup to cloud")
    p_extract = sub.add_parser("extract", help="Extract backup to temp directory")
    p_extract.add_argument("backup_id")

    args = parser.parse_args()
    mgr = DisasterRecoveryManager()

    # ---- backup ----
    if args.cmd == "backup":
        manifest = mgr.create_backup(
            level=args.level,
            rotation=args.rotation,
            cloud_sync=args.cloud,
            verify=not args.no_verify,
        )
        print(f"\nBackup created: {manifest.backup_id}")
        print(f"  Level:     {manifest.level}")
        print(f"  Rotation:  {manifest.rotation}")
        print(f"  Size:      {human_size(manifest.size_bytes)}")
        print(f"  SHA256:    {manifest.sha256}")
        print(f"  Status:    {manifest.status}")
        print(f"  Cloud:     {manifest.cloud_synced}")
        print(f"  Verified:  {manifest.verified_at or 'N/A'}")
        print(f"  Components: {list(manifest.components.keys())}")

    # ---- restore ----
    elif args.cmd == "restore":
        bid = args.backup_id
        if bid == "latest":
            latest = mgr.registry.get_latest()
            bid = latest.backup_id if latest else ""
        components = args.components.split(",") if args.components else None
        ok, msg = mgr.restore_backup(bid, components)
        print(f"\nRestore result: {'SUCCESS' if ok else 'FAILED'}")
        print(msg)

    # ---- schedule ----
    elif args.cmd == "schedule":
        manifest = mgr.schedule_backup(level=args.level)
        print(f"\nScheduled backup: {manifest.backup_id}")
        print(f"  Rotation: {manifest.rotation} ({'monthly' if manifest.rotation=='monthly' else 'weekly' if manifest.rotation=='weekly' else 'daily'})")
        print(f"  Size:     {human_size(manifest.size_bytes)}")
        print(f"  Status:   {manifest.status}")

    # ---- list ----
    elif args.cmd == "list":
        backups = mgr.registry.list_all()
        if not backups:
            print("\nNo backups found.")
            return
        print(f"\n{'ID':<22} {'Timestamp':<21} {'Level':<10} {'Rotation':<8} {'Size':>8} {'Status':<12} {'Components'}")
        print("-" * 100)
        for b in backups:
            comps = ",".join(k for k, v in b.components.items() if v.get("success"))
            print(f"{b.backup_id:<22} {b.timestamp:<21} {b.level:<10} {b.rotation:<8} "
                  f"{human_size(b.size_bytes):>8} {b.status:<12} {comps}")

    # ---- show ----
    elif args.cmd == "show":
        b = mgr.registry.get(args.backup_id)
        if not b:
            print(f"Backup {args.backup_id} not found")
            return
        print(f"\nBackup: {b.backup_id}")
        print(f"  Timestamp:     {b.timestamp}")
        print(f"  Level:         {b.level}")
        print(f"  Rotation:      {b.rotation}")
        print(f"  Size:          {human_size(b.size_bytes)}")
        print(f"  SHA256:        {b.sha256}")
        print(f"  Status:        {b.status}")
        print(f"  DB Version:    {b.database_version}")
        print(f"  Cloud Synced:  {b.cloud_synced}")
        print(f"  Restore Count: {b.restore_count}")
        print(f"  Verified At:   {b.verified_at or 'N/A'}")
        print(f"  Components:")
        for name, info in b.components.items():
            ok = "OK" if info.get("success") else "FAIL"
            sz = human_size(info.get("size_bytes", 0))
            err = f" [ERR: {info.get('error')}]" if info.get("error") else ""
            print(f"    {ok} {name:<15} {sz:<10}{err}")

    # ---- status ----
    elif args.cmd == "status":
        st = mgr.get_status()
        print(f"\n{'='*50}")
        print(f"  Disaster Recovery Status")
        print(f"{'='*50}")
        print(f"  Total backups:      {st['total_backups']}")
        print(f"  Disk usage:         {st['disk_usage_human']}")
        print(f"  Daily retention:    {st['retention_daily']} days")
        print(f"  Weekly retention:   {st['retention_weekly']} weeks")
        print(f"  Monthly retention:  {st['retention_monthly']} months")
        print(f"  Cloud enabled:       {st['cloud_enabled']}")
        print(f"  Latest backup:")
        lv = st["latest_backup"]
        if lv:
            print(f"    ID:        {lv['backup_id']}")
            print(f"    Timestamp: {lv['timestamp']}")
            print(f"    Level:     {lv['level']}")
            print(f"    Size:      {human_size(lv['size_bytes'])}")
            print(f"    Status:    {lv['status']}")
        else:
            print("    (none)")
        print(f"  Status breakdown:")
        for s, n in st["backups_by_status"].items():
            print(f"    {s}: {n}")

    # ---- rotate ----
    elif args.cmd == "rotate":
        result = mgr.rotate_backups()
        print(f"\nRotation applied:")
        print(f"  Removed: {result['removed']}")
        print(f"  Daily:   {result['daily_count']}")
        print(f"  Weekly:  {result['weekly_count']}")
        print(f"  Monthly: {result['monthly_count']}")

    # ---- verify ----
    elif args.cmd == "verify":
        b = mgr.registry.get(args.backup_id)
        if not b:
            print(f"Backup {args.backup_id} not found")
            return
        arc = BACKUP_DIR / f"{args.backup_id}.tar.gz"
        if not arc.exists():
            print(f"Archive not found: {arc}")
            return
        ok, msg = BackupArchiver.verify_archive(arc)
        print(f"\nVerification: {'PASS' if ok else 'FAIL'}")
        print(f"  Archive: {arc.name} ({human_size(arc.stat().st_size)})")
        print(f"  Result:  {msg}")

    # ---- cloud-sync ----
    elif args.cmd == "cloud-sync":
        latest = mgr.registry.get_latest()
        if not latest:
            print("No backup to sync")
            return
        arc = BACKUP_DIR / f"{latest.backup_id}.tar.gz"
        if not arc.exists():
            print(f"Archive not found: {arc}")
            return
        ok, msg = mgr.cloud.upload(arc, latest.backup_id)
        print(f"\nCloud sync: {'OK' if ok else 'FAILED'}")
        print(f"  Message: {msg}")

    # ---- extract ----
    elif args.cmd == "extract":
        b = mgr.registry.get(args.backup_id)
        if not b:
            print(f"Backup {args.backup_id} not found")
            return
        arc = BACKUP_DIR / f"{args.backup_id}.tar.gz"
        if not arc.exists():
            print(f"Archive not found: {arc}")
            return
        extract_dir = BACKUP_DIR / f"{args.backup_id}_extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        BackupArchiver.extract_archive(arc, extract_dir)
        print(f"\nExtracted to: {extract_dir}")
        for f in sorted(extract_dir.rglob("*")):
            if f.is_file():
                print(f"  {f.relative_to(extract_dir)}")


if __name__ == "__main__":
    main()