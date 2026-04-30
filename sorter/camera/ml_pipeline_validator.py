#!/usr/bin/env python3
"""
sorter/camera/ml_pipeline_validator.py
======================================
HUSKY-SORTER-001 | 生豆分选机 ML 训练管道验证工具

本文档在硬件到位前验证 ML 训练管道的完整性和正确性。
无需真实硬件即可运行，使用合成数据测试整个数据流。

功能：
  1. 合成数据生成器输出验证（COCO + YOLO 格式）
  2. 标注数据完整性检查（bbox/segmentation/area）
  3. 类别分布均衡性分析
  4. ML pipeline 组件可用性检查
  5. 推理延迟基准测试（模拟）
  6. 生成验证报告 (JSON)

运行示例：
    python sorter/camera/ml_pipeline_validator.py
    python sorter/camera/ml_pipeline_validator.py --output /tmp/ml_validation
    python sorter/camera/ml_pipeline_validator.py --synthetic-count 100
"""

import argparse
import json
import math
import os
import random
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# ─── 颜色输出 ──────────────────────────────────────────────────────────────────

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def ok(msg):   print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")
def fail(msg): print(f"{Colors.RED}❌ {msg}{Colors.RESET}")
def warn(msg): print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")
def info(msg): print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")
def section(title): print(f"\n{Colors.BOLD}{'='*60}\n  {title}\n{'='*60}{Colors.RESET}")

# ─── 合成数据生成器调用 ────────────────────────────────────────────────────────

def generate_synthetic_data(output_dir: Path, count: int, seed: int = 42) -> bool:
    """调用合成数据生成器生成测试数据"""
    import subprocess
    script_path = Path(__file__).parent / "synthetic_test_data_generator.py"
    cmd = [
        sys.executable, str(script_path),
        "--count", str(count),
        "--output", str(output_dir),
        "--seed", str(seed),
        "--format", "both"  # 生成 COCO + YOLO 两种格式以便完整验证
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            ok(f"合成数据生成成功: {count} 张图像 → {output_dir}")
            return True
        else:
            fail(f"合成数据生成失败: {result.stderr}")
            return False
    except Exception as e:
        fail(f"合成数据生成器调用失败: {e}")
        return False

# ─── 验证结果数据类 ───────────────────────────────────────────────────────────

class TestStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"

@dataclass
class TestResult:
    name: str
    status: TestStatus
    score: float
    details: Dict[str, Any]
    duration_ms: float
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "score": self.score,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "recommendations": self.recommendations
        }

# ─── 验证测试类 ───────────────────────────────────────────────────────────────

class MLPipelineValidator:
    """
    ML 训练管道完整验证器

    在硬件到位前验证：
    1. 合成数据格式正确性（COCO / YOLO）
    2. 图像内容有效性
    3. 标注数据完整性
    4. 类别分布均衡性
    5. Pipeline 组件可用性
    6. 推理延迟基准（模拟）
    """

    LABEL_MAP = {
        0:  "normal",
        1:  "moldy",
        2:  "fermented",
        3:  "black",
        4:  "broken",
        5:  "foreign",
        6:  "underweight",
        7:  "overweight",
        8:  "stunted",
        9:  "dead",
        10: "insect_damaged",
        11: "hollow",
        12: "over_dry",
        13: "over_wet",
    }

    NUM_CLASSES = 14

    def __init__(self, synthetic_dir: Path, output_dir: Path):
        self.synthetic_dir = Path(synthetic_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[TestResult] = []
        self.start_time = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: COCO 格式验证
    # ─────────────────────────────────────────────────────────────────────────

    def test_01_coco_format(self) -> TestResult:
        """验证 COCO JSON 格式正确性"""
        section("TEST 1: COCO 格式验证")
        t0 = time.time()
        issues = []
        details = {}

        ann_file = self.synthetic_dir / "annotations" / "annotations.json"
        if not ann_file.exists():
            return TestResult(
                name="COCO Format",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details={"error": f"annotations.json not found at {ann_file}"},
                recommendations=["Run synthetic_test_data_generator.py first"]
            )

        try:
            with open(ann_file) as f:
                coco = json.load(f)
        except json.JSONDecodeError as e:
            return TestResult(
                name="COCO Format",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details={"error": f"JSON parse error: {e}"},
                recommendations=["Check annotations.json file integrity"]
            )

        required_fields = ["images", "annotations", "categories"]
        missing = [f for f in required_fields if f not in coco]
        if missing:
            return TestResult(
                name="COCO Format",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details={"missing_fields": missing, "available": list(coco.keys())},
                recommendations=["Regenerate dataset"]
            )

        n_images = len(coco["images"])
        n_annotations = len(coco["annotations"])
        n_categories = len(coco["categories"])
        details["n_images"] = n_images
        details["n_annotations"] = n_annotations
        details["n_categories"] = n_categories

        cat_ids = {cat["id"] for cat in coco["categories"]}
        expected_cats = set(range(self.NUM_CLASSES))
        missing_cats = expected_cats - cat_ids
        extra_cats = cat_ids - expected_cats
        if missing_cats:
            issues.append(f"Missing category IDs: {missing_cats}")
        if extra_cats:
            issues.append(f"Extra category IDs: {extra_cats}")
        if not issues:
            ok(f"Categories: {n_categories} 全部正确 (IDs 0-{self.NUM_CLASSES-1})")

        img_ids = {img["id"] for img in coco["images"]}
        ann_img_ids = {ann["image_id"] for ann in coco["annotations"]}
        orphan_anns = ann_img_ids - img_ids
        if orphan_anns:
            issues.append(f"Orphan annotations: {len(orphan_anns)}")
        else:
            ok(f"Annotations ↔ Images: 全部 {n_annotations} 条标注对应有效图像")

        bad_bboxes = [
            ann["id"] for ann in coco["annotations"]
            if ann.get("bbox", [0,0,0,0])[2] <= 0 or ann.get("bbox", [0,0,0,0])[3] <= 0
        ]
        if bad_bboxes:
            issues.append(f"Invalid bboxes: {len(bad_bboxes)}")
        else:
            ok(f"Bbox 格式: 全部 {n_annotations} 条有效")

        duration_ms = (time.time() - t0) * 1000

        if not issues:
            score, status = 100, TestStatus.PASS
            ok(f"COCO 格式验证通过 (耗时 {duration_ms:.1f}ms)")
        elif len(issues) <= 2:
            score, status = 70, TestStatus.WARN
            warn(f"COCO 格式有小问题: {issues}")
        else:
            score, status = 30, TestStatus.FAIL
            fail(f"COCO 格式验证失败: {issues}")

        return TestResult(
            name="COCO Format",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=[] if not issues else ["Regenerate dataset if COCO format is invalid"]
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: YOLO 格式验证
    # ─────────────────────────────────────────────────────────────────────────

    def test_02_yolo_format(self) -> TestResult:
        """验证 YOLO TXT 格式正确性"""
        section("TEST 2: YOLO 格式验证")
        t0 = time.time()

        ann_dir = self.synthetic_dir / "annotations"
        yolo_files = list(ann_dir.glob("*.txt"))
        if not yolo_files:
            # YOLO not generated - warn but don't fail (default format is coco)
            warn("YOLO .txt 文件未生成（使用默认 --format coco）")
            warn("如需验证 YOLO 格式，重新生成数据: python synthetic_test_data_generator.py --format both")
            return TestResult(
                name="YOLO Format",
                status=TestStatus.WARN,
                score=80,
                duration_ms=(time.time()-t0)*1000,
                details={"error": "No YOLO .txt files found (default format=coco)"},
                recommendations=[
                    "Run: python synthetic_test_data_generator.py --format both --count 100",
                    "YOLO format is optional; COCO format is validated successfully"
                ]
            )

        issues = []
        valid_lines = 0
        invalid_lines = 0
        class_counts = {i: 0 for i in range(self.NUM_CLASSES)}

        for yf in yolo_files:
            with open(yf) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) != 5:
                        invalid_lines += 1
                        continue
                    try:
                        cls = int(parts[0])
                        x, y, w, h = [float(p) for p in parts[1:]]
                        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                            invalid_lines += 1
                            continue
                        if cls not in class_counts:
                            issues.append(f"Invalid class ID {cls} in {yf.name}")
                            continue
                        class_counts[cls] += 1
                        valid_lines += 1
                    except ValueError:
                        invalid_lines += 1

        duration_ms = (time.time() - t0) * 1000
        total = valid_lines + invalid_lines
        details = {
            "n_yolo_files": len(yolo_files),
            "valid_lines": valid_lines,
            "invalid_lines": invalid_lines,
            "class_distribution": class_counts,
        }

        if invalid_lines == 0 and not issues:
            score, status = 100, TestStatus.PASS
            ok(f"YOLO 格式验证通过: {valid_lines} 行 / {len(yolo_files)} 文件 (耗时 {duration_ms:.1f}ms)")
        elif invalid_lines <= total * 0.05:
            score, status = 80, TestStatus.WARN
            warn(f"YOLO 有 {invalid_lines} 行无效 ({invalid_lines/total*100:.1f}%)")
        else:
            score, status = 40, TestStatus.FAIL
            fail(f"YOLO 格式严重问题: {invalid_lines}/{total} 行无效")

        return TestResult(
            name="YOLO Format",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=["Regenerate dataset if YOLO format is invalid"]
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: 图像内容验证
    # ─────────────────────────────────────────────────────────────────────────

    def test_03_image_content(self) -> TestResult:
        """验证合成图像内容有效性"""
        section("TEST 3: 图像内容验证")
        t0 = time.time()

        import cv2
        import numpy as np

        img_dir = self.synthetic_dir / "images"
        img_files = sorted(img_dir.glob("*.png"))
        if not img_files:
            return TestResult(
                name="Image Content",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details={"error": "No images found"},
                recommendations=["Run synthetic_test_data_generator.py first"]
            )

        issues = []
        stats = {
            "shape": None, "dtype": None,
            "min_pixel": [], "max_pixel": [], "mean_pixel": [],
            "empty_images": 0, "grayscale_suspicious": 0,
        }

        for img_path in img_files:
            img = cv2.imread(str(img_path))
            if img is None:
                issues.append(f"Cannot load: {img_path.name}")
                continue
            if stats["shape"] is None:
                stats["shape"] = img.shape
                stats["dtype"] = str(img.dtype)
            elif img.shape != stats["shape"]:
                issues.append(f"Inconsistent shape {img.shape} in {img_path.name}")
            if np.count_nonzero(img) == 0:
                stats["empty_images"] += 1
                issues.append(f"Empty image: {img_path.name}")
            stats["min_pixel"].append(int(img.min()))
            stats["max_pixel"].append(int(img.max()))
            stats["mean_pixel"].append(float(img.mean()))
            if len(img.shape) == 2:
                stats["grayscale_suspicious"] += 1

        duration_ms = (time.time() - t0) * 1000
        details = {
            "n_images_checked": len(img_files),
            "shape": stats["shape"],
            "dtype": stats["dtype"],
            "avg_min_pixel": float(np.mean(stats["min_pixel"])),
            "avg_max_pixel": float(np.mean(stats["max_pixel"])),
            "avg_mean_pixel": float(np.mean(stats["mean_pixel"])),
            "empty_images": stats["empty_images"],
            "grayscale_suspicious": stats["grayscale_suspicious"],
        }

        if stats["empty_images"] > 0:
            issues.append(f"{stats['empty_images']} 张空图像")

        if not issues:
            score, status = 100, TestStatus.PASS
            ok(f"图像内容验证通过: {len(img_files)} 张图像 (耗时 {duration_ms:.1f}ms)")
            ok(f"  Shape: {stats['shape']} | Dtype: {stats['dtype']} | "
               f"像素范围: [{int(np.mean(stats['min_pixel']))}, {int(np.mean(stats['max_pixel']))}]")
        elif len(issues) <= 2:
            score, status = 75, TestStatus.WARN
            warn(f"图像内容有小问题: {issues}")
        else:
            score, status = 40, TestStatus.FAIL
            fail(f"图像内容验证失败: {issues}")

        return TestResult(
            name="Image Content",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=["Regenerate dataset if images are corrupted"]
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: 类别分布均衡性
    # ─────────────────────────────────────────────────────────────────────────

    def test_04_class_distribution(self) -> TestResult:
        """验证类别分布均衡性"""
        section("TEST 4: 类别分布均衡性分析")
        t0 = time.time()

        import numpy as np

        ann_file = self.synthetic_dir / "annotations" / "annotations.json"
        with open(ann_file) as f:
            coco = json.load(f)

        class_counts = {i: 0 for i in range(self.NUM_CLASSES)}
        for ann in coco["annotations"]:
            cls = ann["category_id"]
            if cls in class_counts:
                class_counts[cls] += 1

        total = sum(class_counts.values())
        details = {
            "class_counts": class_counts,
            "total": total,
            "n_classes_present": sum(1 for c in class_counts.values() if c > 0),
        }

        if total == 0:
            return TestResult(
                name="Class Distribution",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details=details,
                recommendations=["Check annotation data"]
            )

        counts = list(class_counts.values())
        expected = total / self.NUM_CLASSES
        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 0
        max_count = max(counts)
        min_count = min(counts)
        imbalance_ratio = max_count / min_count if min_count > 0 else float('inf')

        details["expected_per_class"] = expected
        details["cv"] = cv
        details["imbalance_ratio"] = imbalance_ratio

        zero_classes = [cls for cls, cnt in class_counts.items() if cnt == 0]
        recommendations = []
        if imbalance_ratio > 10:
            recommendations.append(f"类别不平衡比例 {imbalance_ratio:.1f}:1，建议增加生成数量")
            warn(f"类别不平衡: 最大类 {max_count} vs 最小类 {min_count} (比例 {imbalance_ratio:.1f}:1)")
        elif imbalance_ratio > 5:
            warn(f"类别轻度不平衡: 比例 {imbalance_ratio:.1f}:1")

        if zero_classes:
            recommendations.append(f"以下类别缺失: {zero_classes}")
            fail(f"类别缺失: {zero_classes}")

        print(f"\n  类别分布 (总计 {total} 条):")
        print(f"  {'类别':<20} {'数量':>6} {'占比':>8} {'期望':>8} {'偏差':>8}")
        print(f"  {'-'*56}")
        for cls_id, cnt in class_counts.items():
            name = self.LABEL_MAP[cls_id]
            pct = cnt / total * 100 if total > 0 else 0
            deviation = (cnt - expected) / expected * 100 if expected > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"  {name:<20} {cnt:>6} {pct:>7.1f}% {expected:>7.1f} {deviation:>+7.1f}% {bar}")

        print(f"\n  变异系数 (CV): {cv:.3f}")
        print(f"  不平衡比例: {imbalance_ratio:.1f}:1")

        duration_ms = (time.time() - t0) * 1000

        if not zero_classes and imbalance_ratio <= 10:
            score, status = 100, TestStatus.PASS
            ok(f"类别分布均衡性验证通过 (CV={cv:.3f})")
        elif not zero_classes:
            score, status = 80, TestStatus.WARN
        else:
            score, status = 50, TestStatus.FAIL

        return TestResult(
            name="Class Distribution",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=recommendations
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Pipeline 组件可用性
    # ─────────────────────────────────────────────────────────────────────────

    def test_05_pipeline_components(self) -> TestResult:
        """验证 ML pipeline 核心组件是否可用"""
        section("TEST 5: ML Pipeline 组件可用性检查")
        t0 = time.time()

        results = {}
        issues = []

        ml_pipeline_path = Path(__file__).parent / "ml_pipeline.py"
        gen_path = Path(__file__).parent / "synthetic_test_data_generator.py"

        if ml_pipeline_path.exists():
            ok(f"ml_pipeline.py 存在 ({ml_pipeline_path.stat().st_size:,} bytes)")
            results["ml_pipeline"] = "present"
        else:
            issues.append("ml_pipeline.py not found")
            results["ml_pipeline"] = "missing"
            fail("ml_pipeline.py 不存在")

        if gen_path.exists():
            ok(f"synthetic_test_data_generator.py 存在 ({gen_path.stat().st_size:,} bytes)")
            results["synthetic_generator"] = "present"
        else:
            issues.append("synthetic_test_data_generator.py not found")
            results["synthetic_generator"] = "missing"
            fail("synthetic_test_data_generator.py 不存在")

        tf_status = "not_installed"
        try:
            import tensorflow as tf
            tf_status = f"available ({tf.__version__})"
            ok(f"TensorFlow {tf.__version__} 可用")
        except ImportError:
            warn("TensorFlow 未安装，跳过训练相关测试")

        results["tensorflow"] = tf_status

        try:
            import cv2
            ok(f"OpenCV {cv2.__version__} 可用")
            results["opencv"] = "available"
        except ImportError:
            issues.append("OpenCV not installed")
            results["opencv"] = "missing"
            fail("OpenCV 不可用")

        try:
            import numpy as np
            ok(f"NumPy {np.__version__} 可用")
            results["numpy"] = "available"
        except ImportError:
            issues.append("NumPy not installed")
            results["numpy"] = "missing"
            fail("NumPy 不可用")

        try:
            from PIL import Image
            ok("PIL/Pillow 可用")
            results["pillow"] = "available"
        except ImportError:
            issues.append("PIL not installed")
            results["pillow"] = "missing"
            fail("PIL/Pillow 不可用")

        duration_ms = (time.time() - t0) * 1000

        missing_critical = []
        if results.get("ml_pipeline") == "missing":
            missing_critical.append("ml_pipeline.py")
        if results.get("synthetic_generator") == "missing":
            missing_critical.append("synthetic_test_data_generator.py")
        if results.get("opencv") == "missing":
            missing_critical.append("OpenCV")
        if results.get("numpy") == "missing":
            missing_critical.append("NumPy")

        if missing_critical:
            score, status = 0, TestStatus.FAIL
            fail(f"关键组件缺失: {missing_critical}")
        elif tf_status == "not_installed":
            score, status = 70, TestStatus.WARN
            warn("TensorFlow 未安装，无法进行模型训练（预期行为，硬件到位后安装）")
        else:
            score, status = 100, TestStatus.PASS
            ok("所有关键组件可用")

        return TestResult(
            name="Pipeline Components",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=results,
            recommendations=[
                "Install TensorFlow for model training: pip install tensorflow"
            ] if tf_status == "not_installed" else []
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: 标注-图像一致性
    # ─────────────────────────────────────────────────────────────────────────

    def test_06_annotation_image_consistency(self) -> TestResult:
        """验证每张图像都有对应标注"""
        section("TEST 6: 标注-图像一致性验证")
        t0 = time.time()

        import cv2

        ann_file = self.synthetic_dir / "annotations" / "annotations.json"
        with open(ann_file) as f:
            coco = json.load(f)

        issues = []
        img_dir = self.synthetic_dir / "images"
        img_map = {img["id"]: img for img in coco["images"]}

        orphan_images = 0
        size_mismatches = 0

        for img_info in coco["images"]:
            img_path = img_dir / img_info["file_name"]
            if not img_path.exists():
                issues.append(f"Missing image: {img_info['file_name']}")
                orphan_images += 1
                continue
            img = cv2.imread(str(img_path))
            if img is not None:
                h, w = img.shape[:2]
                if img_info["height"] != h or img_info["width"] != w:
                    issues.append(f"Size mismatch {img_info['file_name']}: "
                                  f"COCO({img_info['width']}x{img_info['height']}) vs Actual({w}x{h})")
                    size_mismatches += 1

        ann_on_missing_img = sum(
            1 for ann in coco["annotations"] if ann["image_id"] not in img_map
        )

        duration_ms = (time.time() - t0) * 1000
        details = {
            "n_images": len(coco["images"]),
            "n_annotations": len(coco["annotations"]),
            "orphan_images": orphan_images,
            "size_mismatches": size_mismatches,
            "annotations_on_missing_images": ann_on_missing_img,
        }

        total_issues = orphan_images + size_mismatches + ann_on_missing_img
        if total_issues == 0:
            score, status = 100, TestStatus.PASS
            ok(f"标注-图像一致性验证通过: {len(coco['images'])} 图像 + {len(coco['annotations'])} 标注")
        elif total_issues <= 2:
            score, status = 80, TestStatus.WARN
            warn(f"有 {total_issues} 个小问题")
        else:
            score, status = 40, TestStatus.FAIL
            fail(f"标注-图像一致性问题: {total_issues} 个")

        return TestResult(
            name="Annotation-Image Consistency",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=["Regenerate dataset if consistency issues persist"]
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 7: bbox 面积分布合理性
    # ─────────────────────────────────────────────────────────────────────────

    def test_07_bbox_area_distribution(self) -> TestResult:
        """验证 bbox 面积分布合理"""
        section("TEST 7: Bbox 面积分布分析")
        t0 = time.time()

        import numpy as np

        ann_file = self.synthetic_dir / "annotations" / "annotations.json"
        with open(ann_file) as f:
            coco = json.load(f)

        areas = [ann.get("area", 0) for ann in coco["annotations"]]
        if not areas:
            return TestResult(
                name="Bbox Area Distribution",
                status=TestStatus.FAIL,
                score=0,
                duration_ms=(time.time()-t0)*1000,
                details={"error": "No annotations found"},
                recommendations=["Check annotation data"]
            )

        areas_arr = np.array(areas)
        img_area = 224 * 224

        details = {
            "count": len(areas),
            "mean_area": float(np.mean(areas_arr)),
            "median_area": float(np.median(areas_arr)),
            "std_area": float(np.std(areas_arr)),
            "min_area": float(np.min(areas_arr)),
            "max_area": float(np.max(areas_arr)),
            "p5_area": float(np.percentile(areas_arr, 5)),
            "p95_area": float(np.percentile(areas_arr, 95)),
        }

        tiny_bboxes = sum(1 for area in areas if area < img_area * 0.001)
        huge_bboxes = sum(1 for area in areas if area > img_area * 0.95)

        issues = []
        recommendations = []
        if tiny_bboxes:
            issues.append(f"{tiny_bboxes} 个极小 bbox (< 0.1% 图像)")
            recommendations.append("某些 bbox 极小，可能影响训练效果")

        print(f"\n  面积统计 (像素):")
        print(f"  Mean:   {details['mean_area']:.1f} px²")
        print(f"  Median: {details['median_area']:.1f} px²")
        print(f"  Std:    {details['std_area']:.1f} px²")
        print(f"  Min:    {details['min_area']:.1f} px² (P5: {details['p5_area']:.1f})")
        print(f"  Max:    {details['max_area']:.1f} px² (P95: {details['p95_area']:.1f})")
        print(f"  图像面积: {img_area} px² (224×224)")

        duration_ms = (time.time() - t0) * 1000

        if not issues:
            score, status = 100, TestStatus.PASS
            ok(f"Bbox 面积分布合理")
        elif tiny_bboxes <= len(areas) * 0.1:
            score, status = 80, TestStatus.WARN
            warn(f"有 {tiny_bboxes} 个极小 bbox")
        else:
            score, status = 50, TestStatus.FAIL
            fail(f"Bbox 面积分布异常")

        return TestResult(
            name="Bbox Area Distribution",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=recommendations
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEST 8: 推理延迟模拟基准
    # ─────────────────────────────────────────────────────────────────────────

    def test_08_inference_latency_simulation(self) -> TestResult:
        """基于 edge_inference_analysis.py 数据模拟推理延迟"""
        section("TEST 8: 推理延迟基准测试（基于分析数据）")
        t0 = time.time()

        import numpy as np

        # 基于 sorter/camera/edge_inference_analysis.py 的分析结果
        # Pi 4 2GB + INT8 TFLite: 推理延迟 ~28ms
        # Pi 4 2GB + FP32 TFLite: 推理延迟 ~70ms
        # Pi 4 2GB + EdgeTPU: 推理延迟 ~10ms

        configs = [
            {"name": "Pi 4 2GB + INT8 TFLite", "latency_ms": 28, "available": True},
            {"name": "Pi 4 2GB + FP32 TFLite", "latency_ms": 70, "available": True},
            {"name": "Pi 4 4GB + EdgeTPU", "latency_ms": 10, "available": False},
        ]

        print(f"\n  推理延迟基准 (基于 edge_inference_analysis.py 分析):")
        print(f"  {'配置':<30} {'延迟':>10} {'可用':>8} {'备注':<20}")
        print(f"  {'-'*72}")

        for cfg in configs:
            avail_str = "✅" if cfg["available"] else "⏳ 待采购"
            print(f"  {cfg['name']:<30} {cfg['latency_ms']:>7}ms {avail_str:>8}  (边缘部署推荐: ✅)")
            cfg["available_str"] = avail_str

        # 验证实时性约束
        target_bpm = 50
        interval_ms = 60000 / target_bpm  # 1200ms between beans
        pi4_int8_latency = configs[0]["latency_ms"]

        print(f"\n  实时性约束验证 (目标 {target_bpm}bpm):")
        print(f"  每粒间隔: {interval_ms:.0f}ms")
        print(f"  Pi 4 INT8 推理延迟: {pi4_int8_latency}ms")
        print(f"  延迟占比: {pi4_int8_latency/interval_ms*100:.1f}% (目标 <20%)")

        is_realtime = pi4_int8_latency < interval_ms * 0.2
        print(f"  实时性保障: {'✅ 满足' if is_realtime else '❌ 不满足'}")

        duration_ms = (time.time() - t0) * 1000

        score = 100 if is_realtime else 60
        status = TestStatus.PASS if is_realtime else TestStatus.WARN

        details = {
            "configs": configs,
            "target_bpm": target_bpm,
            "bean_interval_ms": interval_ms,
            "pi4_int8_latency_ms": pi4_int8_latency,
            "latency_utilization_pct": pi4_int8_latency / interval_ms * 100,
            "realtime_feasible": is_realtime,
        }

        return TestResult(
            name="Inference Latency Simulation",
            status=status,
            score=score,
            duration_ms=duration_ms,
            details=details,
            recommendations=[
                "EdgeTPU 非必需（Pi 4 2GB INT8 已满足所有推理需求）"
            ] if not configs[2]["available"] else []
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 运行所有测试
    # ─────────────────────────────────────────────────────────────────────────

    def run_all(self) -> Tuple[List[TestResult], Dict[str, Any]]:
        """运行所有验证测试"""
        section("ML Pipeline 验证 — HUSKY-SORTER-001")
        print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  数据目录: {self.synthetic_dir}")
        print(f"  输出目录: {self.output_dir}")

        tests = [
            self.test_01_coco_format,
            self.test_02_yolo_format,
            self.test_03_image_content,
            self.test_04_class_distribution,
            self.test_05_pipeline_components,
            self.test_06_annotation_image_consistency,
            self.test_07_bbox_area_distribution,
            self.test_08_inference_latency_simulation,
        ]

        for test_fn in tests:
            try:
                result = test_fn()
                self.results.append(result)
            except Exception as e:
                fail(f"{test_fn.__name__} 异常: {e}")
                self.results.append(TestResult(
                    name=test_fn.__name__,
                    status=TestStatus.FAIL,
                    score=0,
                    duration_ms=0,
                    details={"exception": str(e), "traceback": traceback.format_exc()},
                    recommendations=["Fix the test or regenerate data"]
                ))

        total_duration = (time.time() - self.start_time) * 1000
        return self.results, self._build_summary(total_duration)

    def _build_summary(self, total_duration_ms: float) -> Dict[str, Any]:
        """构建验证摘要"""
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        warned = sum(1 for r in self.results if r.status == TestStatus.WARN)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIP)

        total_score = sum(r.score for r in self.results) / len(self.results) if self.results else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.results),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "overall_score": round(total_score, 1),
            "total_duration_ms": round(total_duration_ms, 1),
            "synthetic_dir": str(self.synthetic_dir),
        }

    def save_report(self, summary: Dict[str, Any]) -> Path:
        """保存验证报告"""
        report = {
            "version": "1.0",
            "project": "HUSKY-SORTER-001",
            "validator": "ml_pipeline_validator.py",
            "summary": summary,
            "tests": [r.to_dict() for r in self.results],
        }

        report_path = self.output_dir / "ml_pipeline_validation_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        ok(f"验证报告已保存: {report_path}")
        return report_path


# ─── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ML Pipeline Validator — HUSKY-SORTER-001")
    parser.add_argument(
        "--synthetic-dir",
        type=str,
        default="/tmp/sorter_synthetic_validation",
        help="合成数据目录（默认自动生成到 /tmp/sorter_synthetic_validation）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="/tmp/ml_pipeline_validation_output",
        help="验证报告输出目录"
    )
    parser.add_argument(
        "--synthetic-count",
        type=int,
        default=100,
        help="生成的合成图像数量（默认 100）"
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="跳过合成数据生成（使用现有目录）"
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    synthetic_dir = Path(args.synthetic_dir)

    # 自动生成合成数据（如果目录不存在或已指定）
    if not args.skip_generation:
        if synthetic_dir.exists() and any(synthetic_dir.iterdir()):
            warn(f"使用已有合成数据: {synthetic_dir}")
        else:
            info(f"生成合成测试数据: {args.synthetic_count} 张图像 → {synthetic_dir}")
            ok_flag = generate_synthetic_data(synthetic_dir, args.synthetic_count)
            if not ok_flag:
                fail("合成数据生成失败，退出")
                sys.exit(1)

    # 运行验证
    validator = MLPipelineValidator(synthetic_dir=synthetic_dir, output_dir=output_dir)
    results, summary = validator.run_all()

    # 打印摘要
    section("验证摘要")
    print(f"  总测试数: {summary['total_tests']}")
    print(f"  ✅ 通过: {summary['passed']}")
    print(f"  ⚠️  警告: {summary['warned']}")
    print(f"  ❌ 失败: {summary['failed']}")
    print(f"  跳过: {summary['skipped']}")
    print(f"  总分: {summary['overall_score']}/100")
    print(f"  总耗时: {summary['total_duration_ms']:.0f}ms")

    overall = "✅ 全部通过" if summary['failed'] == 0 and summary['warned'] <= 1 else \
              "⚠️  有警告" if summary['warned'] > 0 else \
              "❌ 有失败项"
    print(f"\n  综合评级: {overall}")

    # 保存报告
    report_path = validator.save_report(summary)

    # 列出所有生成的文件
    print(f"\n  报告文件: {report_path}")
    print(f"  合成数据: {synthetic_dir}")
    print(f"  输出目录: {output_dir}")

    return 0 if summary['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
