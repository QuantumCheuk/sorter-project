# sorter/quality/config.py
# Quality module configuration for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-05-04

"""
Quality Configuration
=======================
JSON-based config for quality thresholds, grade boundaries,
and classification rules. Supports runtime reload.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict

from .grades import QualityGrade, GRADE_DEFINITIONS, QualityGrade
from .thresholds import ThresholdSet, ThresholdConfig, DEFAULT_THRESHOLDS, DefectType
from .classifier import ClassifierMode


DEFAULT_CONFIG_PATH = "/etc/sorter/quality_config.json"
ENV_CONFIG_PATH = "SORTER_QUALITY_CONFIG"


@dataclass
class QualityConfig:
    """Top-level quality configuration."""
    config_version: str = "1.0"
    mode: str = "threshold_only"  # threshold_only | ml_plus_rules | rules_as_backup

    # Grade boundaries
    grade_a_max_defect_rate: float = 1.0    # <1% for Grade A
    grade_b_max_defect_rate: float = 3.0    # <3% for Grade B
    grade_c_max_defect_rate: float = 10.0   # <10% for Grade C

    # Score boundaries
    grade_a_min_score: float = 95.0
    grade_b_min_score: float = 85.0
    grade_c_min_score: float = 70.0

    # Critical defects (auto-reject regardless of score)
    critical_defects: list = field(default_factory=lambda: [
        "mold", "black", "foreign"
    ])

    # Per-defect-type overrides (defect_type -> {enabled, threshold_values})
    defect_overrides: Dict[str, dict] = field(default_factory=dict)

    # Normal color reference
    normal_color: dict = field(default_factory=lambda: {
        "L": 48.0, "a": 4.0, "b": 17.0
    })

    @classmethod
    def default(cls) -> "QualityConfig":
        return cls()

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityConfig":
        """Reconstruct from dict, ignoring unknown fields."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "QualityConfig":
        return cls.from_dict(json.loads(text))

    def save(self, path: Optional[str] = None) -> bool:
        """Save config to JSON file."""
        target = path or os.environ.get(ENV_CONFIG_PATH, DEFAULT_CONFIG_PATH)
        try:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w") as f:
                f.write(self.to_json())
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, path: Optional[str] = None) -> "QualityConfig":
        """Load config from JSON file, fall back to defaults."""
        target = path or os.environ.get(ENV_CONFIG_PATH, DEFAULT_CONFIG_PATH)
        if os.path.exists(target):
            try:
                with open(target) as f:
                    return cls.from_json(f.read())
            except Exception:
                pass
        return cls.default()


# Module-level singleton
_instance: Optional[QualityConfig] = None


def load_quality_config(path: Optional[str] = None) -> QualityConfig:
    global _instance
    _instance = QualityConfig.load(path)
    return _instance


def save_quality_config(cfg: Optional[QualityConfig] = None, path: Optional[str] = None) -> bool:
    global _instance
    if cfg is None:
        cfg = _instance or QualityConfig.default()
    return cfg.save(path)


def get_quality_config() -> QualityConfig:
    global _instance
    if _instance is None:
        _instance = load_quality_config()
    return _instance