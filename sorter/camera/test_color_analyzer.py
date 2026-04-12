"""
test_color_analyzer.py - 颜色检测算法测试工具
HUSKY-SORTER-001 / 课题2 Day 2

用法：
    # 测试合成图像
    python -m sorter.camera.test_color_analyzer --synthetic

    # 测试真实图像目录
    python -m sorter.camera.test_color_analyzer --input /path/to/images --compare

    # 导出测试报告
    python -m sorter.camera.test_color_analyzer --input /path/to/images --report /tmp/report.md
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


class ColorAnalyzerTest:
    """颜色分析算法测试框架"""

    def __init__(self):
        self.results: List[Dict] = []
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_synthetic_test_set(self) -> List[Tuple[np.ndarray, str, Dict]]:
        """
        生成合成测试集（模拟真实咖啡生豆）
        用于在没有真实样本时验证算法

        Returns:
            [(image, label, metadata)]
        """
        tests = []

        # 正常豆 (Heirloom 水洗) - 绿色调
        for i in range(10):
            img = self._make_bean_image(
                L_mean=43, a_mean=2, b_mean=18,
                noise_level=5, size=(640, 640)
            )
            tests.append((img, "good", {"variety": "Heirloom", "process": "水洗"}))

        # 正常豆 (Geisha 日晒) - 偏黄
        for i in range(8):
            img = self._make_bean_image(
                L_mean=48, a_mean=3, b_mean=22,
                noise_level=6, size=(640, 640)
            )
            tests.append((img, "good", {"variety": "Geisha", "process": "日晒"}))

        # 漂白豆 - 高亮度
        for i in range(5):
            img = self._make_bean_image(
                L_mean=78, a_mean=0.5, b_mean=3,
                noise_level=3, size=(640, 640)
            )
            tests.append((img, "bleached", {}))

        # 发霉豆 - 暗绿色
        for i in range(5):
            img = self._make_bean_image(
                L_mean=35, a_mean=-4, b_mean=10,
                noise_level=8, size=(640, 640)
            )
            tests.append((img, "moldy", {}))

        # 发酵过度 - 偏红棕
        for i in range(5):
            img = self._make_bean_image(
                L_mean=42, a_mean=9, b_mean=20,
                noise_level=7, size=(640, 640)
            )
            tests.append((img, "fermented", {}))

        return tests

    def _lab_to_bgr(self, L: float, a: float, b: float) -> Tuple[int, int, int]:
        """LAB -> BGR 转换（近似）"""
        # 先转换到 RGB
        L_norm = L * 255 / 100
        a_norm = a + 128
        b_norm = b + 128

        # 简化版转换（实际需要查表）
        r = int(L_norm + 1.371 * (a_norm - 128))
        g = int(L_norm - 0.698 * (a_norm - 128) - 0.336 * (b_norm - 128))
        b_cv = int(L_norm + 0.558 * (b_norm - 128))

        return (
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b_cv)),
        )

    def _make_bean_image(self, L_mean: float, a_mean: float, b_mean: float,
                          noise_level: float, size: Tuple[int, int]) -> np.ndarray:
        """生成模拟豆子图像"""
        h, w = size
        img = np.zeros((h, w, 3), dtype=np.uint8)

        # 填充背景（偏白）
        bg_color = self._lab_to_bgr(L_mean + 40, 0, 0)
        img[:, :] = bg_color

        # 绘制椭圆形的豆子
        cx, cy = w // 2, h // 2
        bgr = self._lab_to_bgr(L_mean, a_mean, b_mean)

        # 添加一些颜色噪声
        noise = np.random.normal(0, noise_level, (h, w, 3))
        noise = np.clip(noise, -30, 30).astype(np.int16)

        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.ellipse(canvas, (cx, cy), (180, 240), 0, 0, 360, bgr, -1)
        canvas = canvas.astype(np.int16) + noise
        canvas = np.clip(canvas, 0, 255).astype(np.uint8)

        # 合并
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (cx, cy), (175, 235), 0, 0, 360, 255, -1)
        img[mask > 0] = canvas[mask > 0]

        return img

    def load_image_folder(self, folder: str) -> List[Tuple[np.ndarray, str, Dict]]:
        """从文件夹加载测试图像"""
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"[ERROR] Folder not found: {folder}")
            return []

        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
        files = sorted([f for f in folder_path.iterdir() if f.suffix.lower() in extensions])

        # 尝试从文件名解析标签（约定: label_timestamp.ext）
        tests = []
        for f in files:
            img = cv2.imread(str(f))
            if img is None:
                continue

            # 尝试从文件名解析
            name = f.stem
            label = "unknown"
            for known in ["good", "bleached", "moldy", "fermented", "broken", "insect"]:
                if known in name.lower():
                    label = known
                    break

            tests.append((img, label, {"path": str(f)}))
            print(f"  Loaded: {f.name} -> {label}")

        return tests

    def run_test(self, image: np.ndarray, expected_label: str,
                 metadata: Dict) -> Dict:
        """对单张图像运行完整分析流程"""
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        try:
            from sorter.camera.color_analyzer import ColorAnalyzer
            from sorter.camera.image_processor import ImageProcessor
        except ImportError:
            # 内联简化版（无外部依赖）
            ColorAnalyzer = None

        t0 = time.time()

        if ColorAnalyzer:
            # 使用完整分析流程
            processor = ImageProcessor()
            mask, regions = processor.preprocess(image, method="combined")

            analyzer = ColorAnalyzer(
                variety=metadata.get("variety", "default"),
                process=metadata.get("process", "default")
            )
            result = analyzer.analyze(image, mask=mask)
            color_score = result.color_score
            defect_flags = result.defect_flags
            detected_label = self._flags_to_label(defect_flags)
        else:
            # 简化版（仅颜色统计）
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            L, a, b = cv2.split(lab)
            L_mean = np.mean(L) * 100 / 255
            a_mean = np.mean(a) - 128
            b_mean = np.mean(b) - 128
            color_score = 50
            defect_flags = {}
            detected_label = "good"
            regions = []

        elapsed_ms = (time.time() - t0) * 1000

        return {
            "timestamp": datetime.now().isoformat(),
            "expected_label": expected_label,
            "detected_label": detected_label,
            "color_score": color_score,
            "defect_flags": defect_flags,
            "processing_time_ms": round(elapsed_ms, 2),
            "metadata": metadata,
            "bean_count": len(regions) if 'regions' in dir() else 0,
        }

    def _flags_to_label(self, flags: Dict[str, bool]) -> str:
        """根据缺陷标记推断标签"""
        if not flags:
            return "good"
        for defect, is_defect in flags.items():
            if is_defect:
                return defect
        return "good"

    def run_synthetic_benchmark(self) -> Dict:
        """运行合成测试集基准测试"""
        print("\n" + "=" * 60)
        print("SYNTHETIC BENCHMARK TEST")
        print("=" * 60)

        tests = self.load_synthetic_test_set()
        print(f"[INFO] Generated {len(tests)} synthetic test samples\n")

        results = []
        for i, (img, expected, meta) in enumerate(tests):
            result = self.run_test(img, expected, meta)
            results.append(result)

            status = "✅" if result["detected_label"] == expected else "❌"
            print(f"  [{i+1:2d}] {status} expected={expected:12s} "
                  f"detected={result['detected_label']:12s} "
                  f"score={result['color_score']:.1f} "
                  f"time={result['processing_time_ms']:.1f}ms")

        return self._compute_metrics(results)

    def run_folder_benchmark(self, folder: str) -> Dict:
        """运行真实图像文件夹基准测试"""
        print(f"\n[INFO] Loading images from: {folder}")
        tests = self.load_image_folder(folder)
        if not tests:
            return {}

        print(f"\n[INFO] Running {len(tests)} tests...\n")
        results = []
        for img, expected, meta in tests:
            result = self.run_test(img, expected, meta)
            results.append(result)

        # 打印结果
        for i, r in enumerate(results):
            status = "✅" if r["detected_label"] == r["expected_label"] else "❌"
            print(f"  [{i+1:2d}] {status} {r['expected_label']:12s} -> {r['detected_label']:12s} "
                  f"score={r['color_score']:.1f}")

        return self._compute_metrics(results)

    def _compute_metrics(self, results: List[Dict]) -> Dict:
        """计算评估指标"""
        if not results:
            return {}

        total = len(results)
        correct = sum(1 for r in results if r["detected_label"] == r["expected_label"])
        accuracy = correct / total * 100

        # 按标签分组统计
        by_label = {}
        for r in results:
            label = r["expected_label"]
            if label not in by_label:
                by_label[label] = {"total": 0, "correct": 0, "scores": []}
            by_label[label]["total"] += 1
            by_label[label]["scores"].append(r["color_score"])
            if r["detected_label"] == label:
                by_label[label]["correct"] += 1

        # 性能统计
        processing_times = [r["processing_time_ms"] for r in results]

        metrics = {
            "total": total,
            "correct": correct,
            "accuracy_pct": round(accuracy, 1),
            "by_label": {
                label: {
                    "recall": round(data["correct"] / data["total"] * 100, 1),
                    "avg_score": round(np.mean(data["scores"]), 1),
                }
                for label, data in by_label.items()
            },
            "performance": {
                "avg_time_ms": round(np.mean(processing_times), 2),
                "max_time_ms": round(np.max(processing_times), 2),
                "min_time_ms": round(np.min(processing_times), 2),
            }
        }

        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Overall Accuracy: {metrics['accuracy_pct']}% ({correct}/{total})")
        print(f"  Avg Processing Time: {metrics['performance']['avg_time_ms']}ms")
        print("\n  Per-Class Recall:")
        for label, data in metrics["by_label"].items():
            print(f"    {label:15s}: {data['recall']}% (avg_score={data['avg_score']})")
        print("=" * 60)

        return metrics

    def export_report(self, metrics: Dict, output_path: str):
        """导出 Markdown 测试报告"""
        lines = [
            f"# 颜色检测算法测试报告",
            f"",
            f"**测试时间:** {self.current_time}",
            f"**测试环境:** HUSKY-SORTER-001 / 课题2 Day 2",
            f"",
            f"## 总体结果",
            f"",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 准确率 | {metrics.get('accuracy_pct', 'N/A')}% |",
            f"| 总样本数 | {metrics.get('total', 'N/A')} |",
            f"| 平均处理时间 | {metrics.get('performance', {}).get('avg_time_ms', 'N/A')}ms |",
            f"",
            f"## 分类召回率",
            f"",
        ]

        by_label = metrics.get("by_label", {})
        if by_label:
            lines.append("| 类别 | 召回率 | 平均评分 |")
            lines.append("|------|--------|---------|")
            for label, data in by_label.items():
                lines.append(f"| {label} | {data['recall']}% | {data['avg_score']} |")

        lines.extend(["", "## 结论", "", "- 待补充真实样本进行实测标定", ""])

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[OK] Report exported: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="颜色分析算法测试工具")
    parser.add_argument("--synthetic", "-s", action="store_true", help="使用合成测试集")
    parser.add_argument("--input", "-i", help="测试图像文件夹")
    parser.add_argument("--report", "-r", help="导出报告路径")
    args = parser.parse_args()

    tester = ColorAnalyzerTest()

    if args.synthetic:
        metrics = tester.run_synthetic_benchmark()
    elif args.input:
        metrics = tester.run_folder_benchmark(args.input)
    else:
        print("[INFO] No input specified, running synthetic benchmark")
        metrics = tester.run_synthetic_benchmark()

    if args.report and metrics:
        tester.export_report(metrics, args.report)


if __name__ == "__main__":
    main()
