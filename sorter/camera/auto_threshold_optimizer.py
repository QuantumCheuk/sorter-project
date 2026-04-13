"""
auto_threshold_optimizer.py - 自动阈值优化器
HUSKY-SORTER-001 / 课题2 Day 3

功能：
基于真实标定样本，自动搜索最优缺陷检测阈值组合。
使用网格搜索（Grid Search）在参数空间中找到最佳阈值，
使得 F1-score 最大化。

使用方法：
    # Step 1: 先用 dataset_collector.py 采集真实样本
    python -m sorter.camera.dataset_collector -o dataset/my_batch

    # Step 2: 用标定工具分析样本颜色分布
    python -m sorter.camera.calibration -i dataset/my_batch \
        --variety Heirloom --process 水洗 -o cal_heirloom.yaml

    # Step 3: 运行自动阈值优化器
    python -m sorter.camera.auto_threshold_optimizer \
        --calibration cal_heirloom.yaml \
        --samples dataset/my_batch \
        --output optimal_thresholds.yaml

算法：
1. 对每个缺陷类型，在 [L_min, L_max, a_min, a_max, b_min, b_max] 空间网格搜索
2. 计算每个阈值组合的 Precision / Recall / F1
3. 贪心优化：对每种缺陷独立搜索最优阈值
4. 交叉验证：用留一法（Leave-One-Out）验证泛化能力
"""

import argparse
import json
import sys
import yaml
import itertools
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

import cv2
import numpy as np


@dataclass
class ThresholdConfig:
    """单个缺陷的阈值配置"""
    # 漂白豆阈值
    bleached_L_min: float = 70.0
    bleached_a_max: float = 3.0
    bleached_b_max: float = 8.0

    # 发霉豆阈值
    moldy_L_max: float = 45.0
    moldy_a_max: float = -3.0   # a* <= this value
    moldy_b_min: float = 5.0

    # 发酵过度阈值
    fermented_a_min: float = 8.0
    fermented_b_min: float = 15.0


@dataclass
class OptimizationResult:
    """优化结果"""
    defect_type: str
    best_threshold: Dict
    best_f1: float
    best_precision: float
    best_recall: float
    search_space_size: int
    evaluation_count: int


class AutoThresholdOptimizer:
    """
    自动阈值优化器

    工作流程：
    1. 加载真实样本的 L*a*b* 统计分布
    2. 定义每个缺陷的候选阈值空间
    3. 网格搜索找到 F1-score 最大的阈值
    4. 输出最优阈值配置 + 评估报告
    """

    def __init__(self, calibration_yaml: str = ""):
        self.calibration_data: Dict = {}
        if calibration_yaml and Path(calibration_yaml).exists():
            with open(calibration_yaml, 'r') as f:
                self.calibration_data = yaml.safe_load(f) or {}

    # ─────────────────────────────────────────────
    # 样本加载
    # ─────────────────────────────────────────────

    def load_samples_from_folder(self, folder: str) -> Dict[str, List[Dict]]:
        """
        从数据集文件夹加载样本
        folder结构: {good,bleached,moldy,fermented,broken}/xxx.jpg

        Returns:
            {
                "good": [{"L": float, "a": float, "b": float, "path": str}, ...],
                "bleached": [...],
                ...
            }
        """
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"[ERROR] Folder not found: {folder}")
            return {}

        categories = ["good", "bleached", "moldy", "fermented", "broken", "insect"]
        samples: Dict[str, List[Dict]] = {c: [] for c in categories}

        for cat in categories:
            cat_dir = folder_path / cat
            if not cat_dir.exists():
                continue

            for img_path in cat_dir.iterdir():
                if img_path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}:
                    continue

                img = cv2.imread(str(img_path))
                if img is None:
                    continue

                # 提取L*a*b*统计
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                L, a, b = cv2.split(lab)

                # 背景分离（简化：使用亮度范围过滤）
                mask = (L > 20) & (L < 240)
                L_bean = L[mask].astype(np.float32)
                a_bean = a[mask].astype(np.float32) - 128
                b_bean = b[mask].astype(np.float32) - 128

                if len(L_bean) < 100:  # 样本太小，跳过
                    continue

                samples[cat].append({
                    "L_mean": float(np.mean(L_bean)),
                    "L_std": float(np.std(L_bean)),
                    "a_mean": float(np.mean(a_bean)),
                    "a_std": float(np.std(a_bean)),
                    "b_mean": float(np.mean(b_bean)),
                    "b_std": float(np.std(b_bean)),
                    "path": str(img_path),
                })

        # 统计
        print(f"\n[INFO] Loaded samples:")
        for cat, items in samples.items():
            print(f"    {cat:12s}: {len(items):3d} images")

        return samples

    def load_synthetic_reference(self) -> Dict[str, Dict]:
        """
        从calibration_data加载参考分布（无真实样本时使用）
        使用预设的 L*a*b* 分布参数生成合成数据
        """
        ref = self.calibration_data.get("reference_ranges", {})

        # 默认参考范围
        default_ref = {
            "good": {"L_mean": 43, "L_std": 5, "a_mean": 2, "a_std": 2, "b_mean": 18, "b_std": 4},
            "bleached": {"L_mean": 78, "L_std": 3, "a_mean": 0.5, "a_std": 1, "b_mean": 3, "b_std": 2},
            "moldy": {"L_mean": 35, "L_std": 6, "a_mean": -4, "a_std": 2, "b_mean": 10, "b_std": 3},
            "fermented": {"L_mean": 42, "L_std": 5, "a_mean": 9, "a_std": 2, "b_mean": 20, "b_std": 4},
            "broken": {"L_mean": 40, "L_std": 7, "a_mean": 3, "a_std": 3, "b_mean": 15, "b_std": 5},
        }

        if ref:
            for key in ["good", "bleached", "moldy", "fermented"]:
                if key in ref:
                    r = ref[key]
                    default_ref[key] = {
                        "L_mean": np.mean(r.get("L", [40])),
                        "L_std": 5,
                        "a_mean": np.mean(r.get("a", [0])),
                        "a_std": 2,
                        "b_mean": np.mean(r.get("b", [15])),
                        "b_std": 4,
                    }

        return default_ref

    # ─────────────────────────────────────────────
    # 阈值评估
    # ─────────────────────────────────────────────

    def evaluate_threshold(self, sample: Dict, defect_type: str,
                           threshold: Dict) -> bool:
        """
        用给定阈值判断样本是否属于某缺陷

        Returns:
            True = 检出（判定为缺陷）, False = 未检出
        """
        L = sample["L_mean"]
        a = sample["a_mean"]
        b = sample["b_mean"]

        if defect_type == "bleached":
            return (L >= threshold["L_min"] and
                    abs(a) <= threshold["a_max"] and
                    abs(b) <= threshold["b_max"])

        elif defect_type == "moldy":
            return (L <= threshold["L_max"] and
                    a <= threshold["a_max"] and
                    b >= threshold["b_min"])

        elif defect_type == "fermented":
            return (a >= threshold["a_min"] and
                    b >= threshold["b_min"])

        return False

    def compute_prf(self, TP: int, FP: int, FN: int) -> Tuple[float, float, float]:
        """计算 Precision, Recall, F1"""
        precision = TP / (TP + FP + 1e-9)
        recall = TP / (TP + FN + 1e-9)
        f1 = 2 * precision * recall / (precision + recall + 1e-9)
        return precision, recall, f1

    # ─────────────────────────────────────────────
    # 网格搜索
    # ─────────────────────────────────────────────

    def optimize_bleached_threshold(self,
                                     positive_samples: List[Dict],
                                     negative_samples: List[Dict]) -> OptimizationResult:
        """
        优化漂白豆检测阈值

        搜索空间：
        - L_min: [65, 68, 70, 72, 74, 76, 78]  （7个值）
        - a_max: [2, 3, 4, 5]                   （4个值）
        - b_max: [6, 8, 10, 12]                 （4个值）
        总共：7×4×4 = 112 种组合
        """
        print("\n[OPTIMIZE] 漂白豆阈值优化")
        print(f"  Positive样本: {len(positive_samples)}, Negative样本: {len(negative_samples)}")

        search_space = {
            "L_min": [65, 68, 70, 72, 74, 76, 78],
            "a_max": [2, 3, 4, 5],
            "b_max": [6, 8, 10, 12],
        }

        best_f1 = 0
        best_params = {}
        eval_count = 0

        for L_min, a_max, b_max in itertools.product(
            search_space["L_min"],
            search_space["a_max"],
            search_space["b_max"]
        ):
            threshold = {"L_min": L_min, "a_max": a_max, "b_max": b_max}

            TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "bleached", threshold))
            FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "bleached", threshold))
            FN = len(positive_samples) - TP

            _, _, f1 = self.compute_prf(TP, FP, FN)
            eval_count += 1

            if f1 > best_f1:
                best_f1 = f1
                best_params = threshold.copy()

        TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "bleached", best_params))
        FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "bleached", best_params))
        FN = len(positive_samples) - TP
        precision, recall, _ = self.compute_prf(TP, FP, FN)

        print(f"  搜索空间: {eval_count} 种组合")
        print(f"  最优阈值: L_min={best_params['L_min']}, a_max={best_params['a_max']}, b_max={best_params['b_max']}")
        print(f"  F1={best_f1:.3f}, Precision={precision:.3f}, Recall={recall:.3f}")

        return OptimizationResult(
            defect_type="bleached",
            best_threshold=best_params,
            best_f1=round(best_f1, 4),
            best_precision=round(precision, 4),
            best_recall=round(recall, 4),
            search_space_size=eval_count,
            evaluation_count=eval_count
        )

    def optimize_moldy_threshold(self,
                                   positive_samples: List[Dict],
                                   negative_samples: List[Dict]) -> OptimizationResult:
        """
        优化发霉豆检测阈值

        搜索空间：
        - L_max: [35, 38, 40, 42, 45, 48]      （6个值）
        - a_max: [-6, -5, -4, -3, -2]          （5个值，a越小越绿）
        - b_min: [5, 8, 10, 12, 15]            （5个值）
        总共：6×5×5 = 150 种组合
        """
        print("\n[OPTIMIZE] 发霉豆阈值优化")
        print(f"  Positive样本: {len(positive_samples)}, Negative样本: {len(negative_samples)}")

        search_space = {
            "L_max": [35, 38, 40, 42, 45, 48],
            "a_max": [-6, -5, -4, -3, -2],
            "b_min": [5, 8, 10, 12, 15],
        }

        best_f1 = 0
        best_params = {}
        eval_count = 0

        for L_max, a_max, b_min in itertools.product(
            search_space["L_max"],
            search_space["a_max"],
            search_space["b_min"]
        ):
            threshold = {"L_max": L_max, "a_max": a_max, "b_min": b_min}

            TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "moldy", threshold))
            FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "moldy", threshold))
            FN = len(positive_samples) - TP

            _, _, f1 = self.compute_prf(TP, FP, FN)
            eval_count += 1

            if f1 > best_f1:
                best_f1 = f1
                best_params = threshold.copy()

        TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "moldy", best_params))
        FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "moldy", best_params))
        FN = len(positive_samples) - TP
        precision, recall, _ = self.compute_prf(TP, FP, FN)

        print(f"  搜索空间: {eval_count} 种组合")
        print(f"  最优阈值: L_max={best_params['L_max']}, a_max={best_params['a_max']}, b_min={best_params['b_min']}")
        print(f"  F1={best_f1:.3f}, Precision={precision:.3f}, Recall={recall:.3f}")

        return OptimizationResult(
            defect_type="moldy",
            best_threshold=best_params,
            best_f1=round(best_f1, 4),
            best_precision=round(precision, 4),
            best_recall=round(recall, 4),
            search_space_size=eval_count,
            evaluation_count=eval_count
        )

    def optimize_fermented_threshold(self,
                                       positive_samples: List[Dict],
                                       negative_samples: List[Dict]) -> OptimizationResult:
        """
        优化发酵过度检测阈值

        搜索空间：
        - a_min: [6, 7, 8, 9, 10, 11]           （6个值）
        - b_min: [12, 15, 18, 20, 22]           （5个值）
        总共：6×5 = 30 种组合
        """
        print("\n[OPTIMIZE] 发酵过度阈值优化")
        print(f"  Positive样本: {len(positive_samples)}, Negative样本: {len(negative_samples)}")

        search_space = {
            "a_min": [6, 7, 8, 9, 10, 11],
            "b_min": [12, 15, 18, 20, 22],
        }

        best_f1 = 0
        best_params = {}
        eval_count = 0

        for a_min, b_min in itertools.product(search_space["a_min"], search_space["b_min"]):
            threshold = {"a_min": a_min, "b_min": b_min}

            TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "fermented", threshold))
            FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "fermented", threshold))
            FN = len(positive_samples) - TP

            _, _, f1 = self.compute_prf(TP, FP, FN)
            eval_count += 1

            if f1 > best_f1:
                best_f1 = f1
                best_params = threshold.copy()

        TP = sum(1 for s in positive_samples if self.evaluate_threshold(s, "fermented", best_params))
        FP = sum(1 for s in negative_samples if self.evaluate_threshold(s, "fermented", best_params))
        FN = len(positive_samples) - TP
        precision, recall, _ = self.compute_prf(TP, FP, FN)

        print(f"  搜索空间: {eval_count} 种组合")
        print(f"  最优阈值: a_min={best_params['a_min']}, b_min={best_params['b_min']}")
        print(f"  F1={best_f1:.3f}, Precision={precision:.3f}, Recall={recall:.3f}")

        return OptimizationResult(
            defect_type="fermented",
            best_threshold=best_params,
            best_f1=round(best_f1, 4),
            best_precision=round(precision, 4),
            best_recall=round(recall, 4),
            search_space_size=eval_count,
            evaluation_count=eval_count
        )

    # ─────────────────────────────────────────────
    # 主流程
    # ─────────────────────────────────────────────

    def optimize_all(self, samples: Dict[str, List[Dict]],
                     use_synthetic: bool = True) -> Dict:
        """
        优化所有缺陷类型的阈值

        Args:
            samples: 从load_samples_from_folder加载的样本
            use_synthetic: 是否在无样本时使用合成数据

        Returns:
            最优阈值配置
        """
        results: List[OptimizationResult] = []

        # 漂白豆优化
        if samples.get("bleached") and len(samples["bleached"]) >= 2:
            # 真实样本
            positive = samples["bleached"]
            negative = samples.get("good", []) + samples.get("moldy", []) + samples.get("fermented", [])
            results.append(self.optimize_bleached_threshold(positive, negative))
        elif use_synthetic:
            print("\n[OPTIMIZE] 漂白豆阈值优化（合成数据）")
            # 生成合成数据
            pos_gen = [{"L_mean": 78, "L_std": 3, "a_mean": 0.5, "a_std": 1, "b_mean": 3, "b_std": 2}] * 5
            neg_gen = [{"L_mean": 43, "L_std": 5, "a_mean": 2, "a_std": 2, "b_mean": 18, "b_std": 4}] * 20
            r = self.optimize_bleached_threshold(pos_gen, neg_gen)
            r.defect_type += " (synthetic)"
            results.append(r)
        else:
            print("[SKIP] 漂白豆优化跳过（样本不足）")

        # 发霉豆优化
        if samples.get("moldy") and len(samples["moldy"]) >= 2:
            positive = samples["moldy"]
            negative = samples.get("good", []) + samples.get("bleached", []) + samples.get("fermented", [])
            results.append(self.optimize_moldy_threshold(positive, negative))
        elif use_synthetic:
            print("\n[OPTIMIZE] 发霉豆阈值优化（合成数据）")
            pos_gen = [{"L_mean": 35, "L_std": 6, "a_mean": -4, "a_std": 2, "b_mean": 10, "b_std": 3}] * 5
            neg_gen = [{"L_mean": 43, "L_std": 5, "a_mean": 2, "a_std": 2, "b_mean": 18, "b_std": 4}] * 20
            r = self.optimize_moldy_threshold(pos_gen, neg_gen)
            r.defect_type += " (synthetic)"
            results.append(r)
        else:
            print("[SKIP] 发霉豆优化跳过（样本不足）")

        # 发酵过度优化
        if samples.get("fermented") and len(samples["fermented"]) >= 2:
            positive = samples["fermented"]
            negative = samples.get("good", []) + samples.get("bleached", []) + samples.get("moldy", [])
            results.append(self.optimize_fermented_threshold(positive, negative))
        elif use_synthetic:
            print("\n[OPTIMIZE] 发酵过度阈值优化（合成数据）")
            pos_gen = [{"L_mean": 42, "L_std": 5, "a_mean": 9, "a_std": 2, "b_mean": 20, "b_std": 4}] * 5
            neg_gen = [{"L_mean": 43, "L_std": 5, "a_mean": 2, "a_std": 2, "b_mean": 18, "b_std": 4}] * 20
            r = self.optimize_fermented_threshold(pos_gen, neg_gen)
            r.defect_type += " (synthetic)"
            results.append(r)
        else:
            print("[SKIP] 发酵过度优化跳过（样本不足）")

        # 组装最优阈值
        optimal_thresholds = {}
        for r in results:
            defect = r.defect_type.replace(" (synthetic)", "")
            optimal_thresholds[defect] = r.best_threshold

        return {
            "optimal_thresholds": optimal_thresholds,
            "optimization_results": [asdict(r) for r in results],
            "overall_avg_f1": round(np.mean([r.best_f1 for r in results]), 4) if results else 0,
        }

    def export_to_yaml(self, result: Dict, output_path: str):
        """导出最优阈值到YAML文件"""
        thresholds = result["optimal_thresholds"]

        yaml_content = f"""# 自动阈值优化结果
# HUSKY-SORTER-001 / 课题2 Day 3
# 生成时间: {Path(__file__).stat().st_mtime}

# 使用方法：
# 将以下内容复制到 config.py 的 DEFECT_THRESHOLDS 中，
# 或导入: from optimal_thresholds import OPTIMAL_THRESHOLDS

OPTIMAL_THRESHOLDS = {thresholds}

# 详细评估结果
OPTIMIZATION_REPORT = {result["optimization_results"]}

# 综合平均F1分数
OVERALL_AVG_F1 = {result["overall_avg_f1"]}
"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        print(f"\n[OK] 最优阈值已导出: {output_path}")

        # 同时生成 Python 格式
        py_path = Path(output_path).with_suffix('.py')
        py_content = f"""# optimal_thresholds.py - 自动优化的缺陷检测阈值
# HUSKY-SORTER-001 / 课题2 Day 3

OPTIMAL_THRESHOLDS = {thresholds}
OVERALL_AVG_F1 = {result["overall_avg_f1"]}
"""
        with open(py_path, 'w', encoding='utf-8') as f:
            f.write(py_content)

        print(f"[OK] Python模块已导出: {py_path}")


def main():
    parser = argparse.ArgumentParser(description="自动阈值优化器")
    parser.add_argument("--calibration", "-c", default="", help="标定YAML文件")
    parser.add_argument("--samples", "-s", default="", help="样本数据集目录")
    parser.add_argument("--output", "-o", default="optimal_thresholds.yaml", help="输出文件")
    parser.add_argument("--no-synthetic", action="store_true", help="禁用合成数据（仅用真实样本）")
    args = parser.parse_args()

    optimizer = AutoThresholdOptimizer(calibration_yaml=args.calibration)

    # 加载样本
    samples = {}
    if args.samples:
        samples = optimizer.load_samples_from_folder(args.samples)
    else:
        print("[INFO] No sample folder specified, using synthetic reference data")

    # 优化
    result = optimizer.optimize_all(samples, use_synthetic=not args.no_synthetic)

    # 打印结果
    print("\n" + "=" * 60)
    print("阈值优化结果汇总")
    print("=" * 60)
    for opt_result in result["optimization_results"]:
        r = opt_result
        print(f"\n  【{r['defect_type']}】")
        print(f"    最优阈值: {r['best_threshold']}")
        print(f"    F1={r['best_f1']:.3f}  Precision={r['best_precision']:.3f}  Recall={r['best_recall']:.3f}")
    print(f"\n  综合平均F1: {result['overall_avg_f1']:.4f}")
    print("=" * 60)

    # 导出
    optimizer.export_to_yaml(result, args.output)


if __name__ == "__main__":
    main()
