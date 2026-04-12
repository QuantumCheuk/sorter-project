"""
calibration.py - 颜色阈值标定工具
HUSKY-SORTER-001 / 课题2 Day 2

功能：
1. 导入真实样本图像（已知品质标签）
2. 分析样本的 L*a*b* 分布
3. 自动建议/更新缺陷阈值
4. 导出标定结果到 config.py 或独立 YAML

用法：
    python -m sorter.camera.calibration --input /path/to/samples/ --variety Heirloom --process 水洗
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
import yaml


class ColorCalibrator:
    """颜色标定器 — 从真实样本学习阈值"""

    def __init__(self, variety: str, process: str):
        self.variety = variety
        self.process = process
        self.samples: List[Dict] = []  # {"image": np.ndarray, "label": str, "path": str}

    def add_sample(self, image: np.ndarray, label: str, path: str = ""):
        """添加样本图像

        Args:
            image: BGR 图像
            label: "good" | "bleached" | "moldy" | "fermented" | "broken" | "insect"
            path: 文件路径（用于调试）
        """
        self.samples.append({"image": image, "label": label, "path": path})

    def add_sample_from_file(self, file_path: str, label: str):
        """从文件添加样本"""
        img = cv2.imread(file_path)
        if img is None:
            print(f"[WARN] Cannot read: {file_path}")
            return
        self.add_sample(img, label, file_path)

    def add_samples_from_folder(self, folder: str, label: str):
        """从文件夹添加所有图像样本"""
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"[WARN] Folder not found: {folder}")
            return

        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
        files = [f for f in folder_path.iterdir() if f.suffix.lower() in extensions]
        print(f"[INFO] Loading {len(files)} images from {folder}")
        for f in files:
            self.add_sample_from_file(str(f), label)

    def analyze(self) -> Dict:
        """
        分析所有样本，计算阈值建议

        Returns:
            标定结果字典
        """
        if not self.samples:
            return {"error": "No samples added"}

        # 按标签分组
        groups = {}
        for s in self.samples:
            label = s["label"]
            if label not in groups:
                groups[label] = []
            groups[label].append(s)

        print(f"\n[CALIBRATION] Analyzing {len(self.samples)} samples across {len(groups)} groups")
        for label, samples in groups.items():
            print(f"  {label}: {len(samples)} samples")

        results = {
            "variety": self.variety,
            "process": self.process,
            "total_samples": len(self.samples),
            "groups": {},
            "thresholds": {},
            "reference_ranges": {},
        }

        # 分析每组
        for label, samples in groups.items():
            stats = self._analyze_group(samples, label)
            results["groups"][label] = stats

        # 计算缺陷阈值（基于分位点）
        results["thresholds"] = self._compute_defect_thresholds(groups)

        # 计算参考范围（合格样本）
        if "good" in groups:
            results["reference_ranges"] = self._compute_reference_ranges(groups["good"])

        return results

    def _analyze_group(self, samples: List[Dict], label: str) -> Dict:
        """分析一组样本的颜色分布"""
        L_vals, a_vals, b_vals = [], [], []
        uniformity_scores = []

        for s in samples:
            img = s["image"]
            mask = self._extract_bean_mask(img)

            if mask is None or np.sum(mask) == 0:
                continue

            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            L, a, b = cv2.split(lab)

            L_bean = L[mask > 0].astype(np.float32)
            a_bean = a[mask > 0].astype(np.float32)
            b_bean = b[mask > 0].astype(np.float32)

            L_norm = L_bean * 100 / 255
            a_norm = a_bean - 128
            b_norm = b_bean - 128

            L_vals.extend(L_norm.tolist())
            a_vals.extend(a_norm.tolist())
            b_vals.extend(b_norm.tolist())

            # 颜色均匀度（直方图峰值比例）
            hist_L = cv2.calcHist([L], [0], mask, [32], [0, 256]).flatten()
            hist_L = hist_L / max(1, hist_L.sum())
            peak_ratio = hist_L.max()
            uniformity_scores.append(peak_ratio)

        if not L_vals:
            return {"count": 0}

        L_vals = np.array(L_vals)
        a_vals = np.array(a_vals)
        b_vals = np.array(b_vals)

        stats = {
            "count": len(samples),
            "L": {
                "mean": float(np.mean(L_vals)),
                "std": float(np.std(L_vals)),
                "min": float(np.min(L_vals)),
                "max": float(np.max(L_vals)),
                "p5": float(np.percentile(L_vals, 5)),
                "p95": float(np.percentile(L_vals, 95)),
            },
            "a": {
                "mean": float(np.mean(a_vals)),
                "std": float(np.std(a_vals)),
                "min": float(np.min(a_vals)),
                "max": float(np.max(a_vals)),
                "p5": float(np.percentile(a_vals, 5)),
                "p95": float(np.percentile(a_vals, 95)),
            },
            "b": {
                "mean": float(np.mean(b_vals)),
                "std": float(np.std(b_vals)),
                "min": float(np.min(b_vals)),
                "max": float(np.max(b_vals)),
                "p5": float(np.percentile(b_vals, 5)),
                "p95": float(np.percentile(b_vals, 95)),
            },
            "uniformity": {
                "mean": float(np.mean(uniformity_scores)),
                "std": float(np.std(uniformity_scores)),
            }
        }

        print(f"\n[{label.upper()}] n={stats['count']}")
        print(f"  L*: {stats['L']['mean']:.1f} ± {stats['L']['std']:.1f}  (range [{stats['L']['min']:.1f}, {stats['L']['max']:.1f}])")
        print(f"  a*: {stats['a']['mean']:.1f} ± {stats['a']['std']:.1f}  (range [{stats['a']['min']:.1f}, {stats['a']['max']:.1f}])")
        print(f"  b*: {stats['b']['mean']:.1f} ± {stats['b']['std']:.1f}  (range [{stats['b']['min']:.1f}, {stats['b']['max']:.1f}])")

        return stats

    def _extract_bean_mask(self, image: np.ndarray) -> Optional[np.ndarray]:
        """提取豆子区域掩码（改进的背景分离）"""
        # 使用多色彩空间融合的背景分离
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)

        H, S, V = cv2.split(hsv)
        L, a_col, b_col = cv2.split(lab)

        # 策略1：V通道二值化（对暗背景效果好）
        _, thresh_V = cv2.threshold(V, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 策略2：饱和度 S 高 → 可能是彩色背景，分离
        _, thresh_S = cv2.threshold(S, 30, 255, cv2.THRESH_BINARY)

        # 策略3：L通道高（白色背景）
        _, thresh_L = cv2.threshold(L, 200, 255, cv2.THRESH_BINARY)

        # 合并：豆子 = 非白色背景 且 非高饱和背景
        bg_mask = cv2.bitwise_or(thresh_V, thresh_L)
        bean_candidate = cv2.bitwise_and(cv2.bitwise_not(bg_mask), cv2.bitwise_not(thresh_S))

        # 形态学清理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(bean_candidate, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 过滤太小/太大的区域（豆子面积范围）
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return mask

        # 取最大轮廓
        largest = max(contours, key=cv2.contourArea)
        bean_mask = np.zeros_like(mask)
        cv2.drawContours(bean_mask, [largest], -1, 255, -1)

        return bean_mask

    def _compute_defect_thresholds(self, groups: Dict) -> Dict:
        """基于样本分布计算缺陷检测阈值"""
        thresholds = {}

        # 漂白豆：L值明显偏高，正常豆L上限附近
        # 发霉豆：L偏低，a偏绿(负)，b偏高
        # 发酵过度：a偏红(正)，b偏高

        if "bleached" in groups and "good" in groups:
            bleached_stats = groups["bleached"][0] if groups["bleached"] else {}
            # 漂白豆：L ≥ good_L_max 且 a,b 接近中性
            # 用漂白样本的最小L 作为阈值参考
            bleached_L_p5 = groups["bleached"][0].get("L", {}).get("p5", 75) if groups["bleached"] else 75
            good_L_p95 = groups["good"][0].get("L", {}).get("p95", 55) if groups["good"] else 55
            thresholds["bleached"] = {
                "L_min": max(bleached_L_p5 * 0.9, good_L_p95 * 1.05),
                "a_max": 3.0,  # 保持保守
                "b_max": 10.0,
            }

        if "moldy" in groups and "good" in groups:
            good_moldy = groups.get("moldy", [{}])[0]
            thresholds["moldy"] = {
                "L_max": good_moldy.get("L", {}).get("p95", 45),
                "a_min": good_moldy.get("a", {}).get("p5", -5),
                "b_min": good_moldy.get("b", {}).get("p5", 8),
            }

        if "fermented" in groups and "good" in groups:
            fermented = groups.get("fermented", [{}])[0]
            thresholds["fermented"] = {
                "a_min": fermented.get("a", {}).get("p5", 8),
                "b_min": fermented.get("b", {}).get("p5", 15),
            }

        return thresholds

    def _compute_reference_ranges(self, good_samples: List[Dict]) -> Dict:
        """计算合格样本的参考颜色范围 (5th-95th percentile)"""
        L_vals, a_vals, b_vals = [], [], []

        for s in good_samples:
            img = s["image"]
            mask = self._extract_bean_mask(img)
            if mask is None or np.sum(mask) == 0:
                continue

            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            L, a, b = cv2.split(lab)
            L_norm = L[mask > 0].astype(np.float32) * 100 / 255
            a_norm = a[mask > 0].astype(np.float32) - 128
            b_norm = b[mask > 0].astype(np.float32) - 128
            L_vals.extend(L_norm.tolist())
            a_vals.extend(a_norm.tolist())
            b_vals.extend(b_norm.tolist())

        if not L_vals:
            return {"L": (35, 50), "a": (-2, 6), "b": (12, 25)}

        L_vals, a_vals, b_vals = np.array(L_vals), np.array(a_vals), np.array(b_vals)
        return {
            "L": (float(np.percentile(L_vals, 5)), float(np.percentile(L_vals, 95))),
            "a": (float(np.percentile(a_vals, 5)), float(np.percentile(a_vals, 95))),
            "b": (float(np.percentile(b_vals, 5)), float(np.percentile(b_vals, 95))),
        }

    def save_results(self, results: Dict, output_path: str):
        """保存标定结果到 YAML"""
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(results, f, allow_unicode=True, default_flow_style=False)
        print(f"\n[OK] Calibration saved to {output_path}")

    def print_recommendations(self, results: Dict):
        """打印阈值更新建议"""
        print("\n" + "=" * 60)
        print("THRESHOLD UPDATE RECOMMENDATIONS")
        print("=" * 60)

        if "thresholds" in results and results["thresholds"]:
            print("\n[Defect Thresholds]")
            for defect, th in results["thresholds"].items():
                print(f"  {defect}: {th}")

        if "reference_ranges" in results and results["reference_ranges"]:
            print(f"\n[Reference Ranges for {self.variety}/{self.process}]")
            ref = results["reference_ranges"]
            print(f"  L*: ({ref['L'][0]:.1f}, {ref['L'][1]:.1f})")
            print(f"  a*: ({ref['a'][0]:.1f}, {ref['a'][1]:.1f})")
            print(f"  b*: ({ref['b'][0]:.1f}, {ref['b'][1]:.1f})")

        print("\n[Config Update]")
        print(f"# Update sorter/config.py VARIETY_REFERENCES:")
        print(f'"{self.variety}": {{')
        print(f'    "{self.process}": {results["reference_ranges"]},')
        print(f'}},')
        print("=" * 60)


def generate_synthetic_samples(n_good: int = 20, n_bleached: int = 5,
                                n_moldy: int = 5, n_fermented: int = 5) -> List[Dict]:
    """
    生成合成测试样本（用于在没有真实样本时测试算法）
    模拟不同缺陷类型的颜色特征
    """
    samples = []
    size = (480, 640, 3)

    # 正常豆：L∈[35,50], a∈[-1,5], b∈[12,25]
    for i in range(n_good):
        L_mean = np.random.uniform(38, 48)
        img = np.zeros(size, dtype=np.uint8)
        # 模拟 LAB -> BGR
        img[:, :] = [int(L_mean * 2.5), int(np.random.uniform(-1, 5) + 128), int(np.random.uniform(12, 25) + 128)]
        img = cv2.convertScaleAbs(img)
        samples.append({"image": img, "label": "good", "path": f"synthetic_good_{i}"})

    # 漂白豆：L≥75, a≈0, b≈0
    for i in range(n_bleached):
        img = np.zeros(size, dtype=np.uint8)
        img[:, :] = [200, 128, 130]  # 高L, 中性a,b
        img = cv2.convertScaleAbs(img)
        samples.append({"image": img, "label": "bleached", "path": f"synthetic_bleached_{i}"})

    # 发霉豆：L≤45, a≤-5, b≥8
    for i in range(n_moldy):
        img = np.zeros(size, dtype=np.uint8)
        img[:, :] = [100, 120, 140]  # 暗绿
        img = cv2.convertScaleAbs(img)
        samples.append({"image": img, "label": "moldy", "path": f"synthetic_moldy_{i}"})

    # 发酵过度：a≥8, b≥18
    for i in range(n_fermented):
        img = np.zeros(size, dtype=np.uint8)
        img[:, :] = [110, 138, 148]  # 偏红棕
        img = cv2.convertScaleAbs(img)
        samples.append({"image": img, "label": "fermented", "path": f"synthetic_fermented_{i}"})

    return samples


def main():
    parser = argparse.ArgumentParser(description="颜色阈值标定工具")
    parser.add_argument("--input", "-i", help="输入样本文件夹")
    parser.add_argument("--variety", "-v", default="Heirloom", help="品种")
    parser.add_argument("--process", "-p", default="水洗", help="处理法")
    parser.add_argument("--output", "-o", default="calibration_result.yaml", help="输出文件")
    parser.add_argument("--synthetic", "-s", action="store_true", help="使用合成样本测试")
    args = parser.parse_args()

    calibrator = ColorCalibrator(args.variety, args.process)

    if args.synthetic:
        print("[INFO] Using synthetic test samples")
        samples = generate_synthetic_samples()
        for s in samples:
            calibrator.samples.append(s)
    elif args.input:
        # 假设文件夹结构: input/good/, input/bleached/, input/moldy/, ...
        base = Path(args.input)
        for label in ["good", "bleached", "moldy", "fermented", "broken", "insect"]:
            folder = base / label
            if folder.exists():
                calibrator.add_samples_from_folder(str(folder), label)
    else:
        print("[INFO] No input specified, using synthetic samples for demo")
        samples = generate_synthetic_samples()
        for s in samples:
            calibrator.samples.append(s)

    results = calibrator.analyze()
    calibrator.print_recommendations(calibrator._compute_reference_ranges(
        {"good": [s for s in calibrator.samples if s["label"] == "good"]}
        if "good" in [s["label"] for s in calibrator.samples] else []
    ))
    calibrator.save_results(results, args.output)


if __name__ == "__main__":
    main()
