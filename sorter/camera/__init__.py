"""
sorter/camera - 颜色检测模块
HUSKY-SORTER-001 / 课题2
"""

from .capture import BeanCamera
from .color_analyzer import ColorAnalyzer, ColorResult, calibrate_reference
from .defect_detector import DefectDetector
from .dark_box import DARK_BOX_PARAMS, generate_openscad, generate_freecad_macro

__all__ = [
    "BeanCamera",
    "ColorAnalyzer",
    "ColorResult",
    "DefectDetector",
    "calibrate_reference",
    "DARK_BOX_PARAMS",
    "generate_openscad",
    "generate_freecad_macro",
]
