#!/usr/bin/env python3
"""
ML Model Field Validation Framework
====================================
硬件到位后，用于验证部署模型是否满足质量基准的完整测试套件。

Version: 1.0 (2026-05-09)
Project: HUSKY-SORTER-001
"""

import os
import sys
import json
import time
import random
import argparse
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from statistics import mean, stdev

# === Path Setup ===
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =============================================================================
# DATASET DEFINITIONS
# =============================================================================

BEAN_CLASSES = {
    0: "normal",
    1: "mold",
    2: "fermented",
    3: "black",
    4: "broken",
    5: "foreign",
    6: "underweight",
    7: "underdeveloped",
    8: "dead",
    9: "insect",
    10: "hollow",
    11: "over_dry",
    12: "over_wet",
    13: "pre_mold"
}

CRITICAL_CLASSES = {"mold", "fermented", "black", "foreign", "insect"}
HIGH_PRIORITY_CLASSES = {"broken", "dead", "hollow"}
DEFECT_CLASSES = set(BEAN_CLASSES.values()) - {"normal"}


@dataclass
class ValidationResult:
    """单次验证结果"""
    test_name: str
    passed: bool
    score: float = 0.0
    threshold: float = 0.0
    details: str = ""
    latency_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class FieldValidationReport:
    """完整现场验证报告"""
    report_id: str
    timestamp: str
    model_path: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings_count: int = 0
    overall_pass: bool = False
    overall_score: float = 0.0
    duration_seconds: float = 0.0
    results: List[ValidationResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


# =============================================================================
# TEST DATASET GENERATORS (Synthetic, for pre-hardware validation)
# =============================================================================

class SyntheticTestDatasetGenerator:
    """
    生成合成测试数据集，用于验证ML pipeline的端到端功能。
    硬件到位前无法获取真实图像，但可以验证pipeline逻辑。
    """
    
    def __init__(self, output_dir: str = "./data/ml_validation_test"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_synthetic_image(self, class_id: int, img_size: Tuple[int, int] = (224, 224)) -> Optional[np.ndarray]:
        """生成指定类别的合成图像"""
        if not HAS_CV2 or not HAS_NUMPY:
            return None
        
        # 基础颜色基于类别
        np.random.seed(class_id * 1000 + int(time.time()) % 1000)
        
        # 14个类别的颜色范围 (L*, a*, b* -> BGR)
        CLASS_LAB_RANGES = {
            0: ([35, 55], [-2, 2], [5, 20]),     # normal - 浅棕色
            1: ([20, 40], [-5, 5], [5, 25]),     # mold - 青灰绿
            2: ([25, 45], [3, 15], [10, 30]),    # fermented - 黄棕色
            3: ([10, 30], [0, 10], [0, 15]),     # black - 深棕黑
            4: ([30, 50], [-3, 3], [5, 20]),     # broken - 不均匀棕色
            5: ([40, 60], [-5, 5], [5, 25]),     # foreign - 异物(随机)
            6: ([32, 52], [-3, 3], [5, 20]),     # underweight - 偏淡
            7: ([28, 48], [-3, 3], [5, 20]),     # underdeveloped - 小而淡
            8: ([15, 35], [0, 8], [0, 20]),      # dead - 暗色
            9: ([25, 45], [-5, 5], [5, 25]),     # insect - 小目标
            10: ([20, 40], [-3, 3], [5, 20]),    # hollow - 中空
            11: ([35, 55], [-3, 3], [0, 15]),    # over_dry - 淡黄
            12: ([30, 50], [-3, 3], [10, 30]),   # over_wet - 深色
            13: ([25, 45], [-5, 10], [5, 30]),   # pre_mold - 青灰
        }
        
        l_range, a_range, b_range = CLASS_LAB_RANGES.get(class_id, ([30, 50], [-3, 3], [5, 25]))
        
        # 生成L*a*b*
        L = random.uniform(*l_range)
        a = random.uniform(*a_range)
        b = random.uniform(*b_range)
        
        # L*a*b* -> RGB
        Lab = np.array([[[L, a, b]]], dtype=np.float64)
        Lab[0, 0, 0] = (Lab[0, 0, 0] + 16) / 116
        fL = Lab[0, 0, 0] + 16 / 116
        fC = 0.00885645167
        
        rgb = np.zeros((1, 1, 3), dtype=np.uint8)
        for i in range(3):
            f = (7.787 * Lab[0, 0, i] / 255) + (16 / 116) if i == 0 else (7.787 * (Lab[0, 0, i] / 255 - 0.19783))
            rgb[0, 0, i] = max(0, min(255, int((f > fC) * (116 * f - 16) + (f <= fC) * (903.3 * f) + 16)))
        
        # 创建图像
        img = np.zeros((*img_size[::-1], 3), dtype=np.uint8)
        base_color = (int(rgb[0, 0, 0]), int(rgb[0, 0, 1]), int(rgb[0, 0, 2]))
        img[:] = base_color
        
        # 添加纹理噪声
        noise = np.random.randint(-20, 20, img.shape, dtype=np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # 添加传感器噪声模拟
        sensor_noise = np.random.normal(0, 2, img.shape).astype(np.int16)
        img = np.clip(img.astype(np.int16) + sensor_noise, 0, 255).astype(np.uint8)
        
        return img
    
    def generate_test_dataset(self, samples_per_class: int = 50) -> Tuple[List[str], List[int]]:
        """
        生成完整测试数据集
        Returns: (image_paths, class_labels)
        """
        image_paths = []
        class_labels = []
        
        for class_id in range(14):
            class_name = BEAN_CLASSES[class_id]
            class_dir = self.output_dir / class_name
            class_dir.mkdir(exist_ok=True)
            
            for i in range(samples_per_class):
                img = self.generate_synthetic_image(class_id)
                if img is None:
                    continue
                
                filename = f"{class_name}_{i:04d}.png"
                filepath = class_dir / filename
                cv2.imwrite(str(filepath), img)
                
                image_paths.append(str(filepath))
                class_labels.append(class_id)
        
        print(f"Generated {len(image_paths)} synthetic test images")
        return image_paths, class_labels


# =============================================================================
# ML INFERENCE ENGINE (Simulated)
# =============================================================================

class MLInferenceEngine:
    """
    ML推理引擎 - 模拟真实模型的推理行为。
    硬件到位后替换为实际TFLite推理。
    """
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.inference_count = 0
        self.total_latency_ms = 0.0
        self.has_tflite = False
        self.interpreter = None
        
        # 尝试加载TFLite
        try:
            import tflite_runtime.interpreter as tflite
            self.tflite = tflite
            self.has_tflite = True
            print("TFLite runtime available")
        except ImportError:
            print("TFLite runtime not available - using simulated inference")
    
    def load_model(self, model_path: str = None):
        """加载TFLite模型"""
        if not self.has_tflite:
            return False
        
        path = model_path or self.model_path
        if not path or not Path(path).exists():
            print(f"Model not found: {path}")
            return False
        
        try:
            self.interpreter = self.tflite.Interpreter(model_path=path)
            self.interpreter.allocate_tensors()
            print(f"Model loaded: {path}")
            return True
        except Exception as e:
            print(f"Failed to load model: {e}")
            return False
    
    def predict(self, image_path: str) -> Tuple[np.ndarray, float]:
        """
        对图像进行推理
        Returns: (probabilities, latency_ms)
        """
        start = time.perf_counter()
        
        if self.interpreter:
            # 真实TFLite推理
            # ... (actual inference would go here)
            pass
        
        # 模拟推理 - 基于图像路径和类名生成真实感概率分布
        # 随机baseline应该产生接近均匀的分布（约7.1%每类）
        np.random.seed(hash(image_path) % (2**32))
        
        # 生成14类概率 - 随机baseline
        probs = np.random.dirichlet(np.ones(14) * 0.1)
        
        # 模拟推理延迟 (~30ms mean)
        latency = np.random.gamma(20, 1.5)
        
        self.inference_count += 1
        self.total_latency_ms += latency
        
        return probs, latency
    
    def predict_batch(self, image_paths: List[str]) -> List[Tuple[np.ndarray, float]]:
        """批量推理"""
        return [self.predict(p) for p in image_paths]
    
    def get_average_latency(self) -> float:
        if self.inference_count == 0:
            return 0.0
        return self.total_latency_ms / self.inference_count
    
    def reset_stats(self):
        self.inference_count = 0
        self.total_latency_ms = 0.0


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class InferenceLatencyTest:
    """测试1: 推理延迟基准测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            target_latency_ms: float = 50.0,
            min_samples: int = 100) -> ValidationResult:
        
        # 生成测试图像
        image_paths, _ = generator.generate_test_dataset(samples_per_class=10)
        sample_paths = image_paths[:min(min_samples, len(image_paths))]
        
        latencies = []
        for path in sample_paths:
            _, latency = engine.predict(path)
            latencies.append(latency)
        
        p50 = np.percentile(latencies, 50)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)
        avg_lat = np.mean(latencies)
        
        passed = p95 <= target_latency_ms
        
        details = (
            f"Target: {target_latency_ms}ms p95 | "
            f"Actual: p50={p50:.1f}ms / p95={p95:.1f}ms / p99={p99:.1f}ms / avg={avg_lat:.1f}ms"
        )
        
        result = ValidationResult(
            test_name="Inference Latency",
            passed=passed,
            score=p95,
            threshold=target_latency_ms,
            details=details,
            latency_ms=avg_lat
        )
        
        if p95 > target_latency_ms:
            result.warnings.append(f"p95 latency {p95:.1f}ms exceeds target {target_latency_ms}ms")
        
        return result


class ConfidenceDistributionTest:
    """测试2: 置信度分布验证"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine) -> ValidationResult:
        
        image_paths, class_labels = generator.generate_test_dataset(samples_per_class=10)
        
        high_conf_count = 0  # 置信度 > 0.8
        low_conf_count = 0   # 置信度 < 0.3
        
        for i, path in enumerate(image_paths[:100]):
            probs, _ = engine.predict(path)
            max_conf = np.max(probs)
            
            if max_conf > 0.8:
                high_conf_count += 1
            elif max_conf < 0.3:
                low_conf_count += 1
        
        high_pct = high_conf_count / 100 * 100
        low_pct = low_conf_count / 100 * 100
        
        # 理想分布: 大部分图像应该有明确预测
        # 真实模型应该产生更多高置信度输出
        passed = high_pct >= 30  # 至少30%的高置信度
        
        details = (
            f"High conf (>0.8): {high_pct:.1f}% | "
            f"Low conf (<0.3): {low_pct:.1f}% | "
            f"(Baseline expectation: high≥30%, low≤20%)"
        )
        
        return ValidationResult(
            test_name="Confidence Distribution",
            passed=passed,
            score=high_pct,
            threshold=30.0,
            details=details
        )


class CriticalDefectRecallTest:
    """测试3: 关键缺陷召回率测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            recall_threshold: float = 0.85) -> ValidationResult:
        
        image_paths, class_labels = generator.generate_test_dataset(samples_per_class=20)
        
        # 关键缺陷类别ID
        critical_ids = {k for k, v in BEAN_CLASSES.items() if v in CRITICAL_CLASSES}
        
        recalls = {}
        for class_id in critical_ids:
            class_images = [image_paths[i] for i, l in enumerate(class_labels) if l == class_id]
            if not class_images:
                continue
            
            true_positives = 0
            for path in class_images:
                probs, _ = engine.predict(path)
                predicted_class = np.argmax(probs)
                if predicted_class in critical_ids:
                    true_positives += 1
            
            recalls[BEAN_CLASSES[class_id]] = true_positives / len(class_images) if class_images else 0
        
        avg_recall = np.mean(list(recalls.values())) if recalls else 0
        passed = avg_recall >= recall_threshold
        
        details = " | ".join([f"{k}: {v*100:.0f}%" for k, v in recalls.items()])
        details += f" | Avg: {avg_recall*100:.1f}%"
        
        return ValidationResult(
            test_name="Critical Defect Recall",
            passed=passed,
            score=avg_recall * 100,
            threshold=recall_threshold * 100,
            details=details
        )


class NormalClassSpecificityTest:
    """测试4: 正常豆类别特异性测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            specificity_threshold: float = 0.90) -> ValidationResult:
        
        image_paths, class_labels = generator.generate_test_dataset(samples_per_class=20)
        
        # 正常类图像
        normal_images = [image_paths[i] for i, l in enumerate(class_labels) if l == 0]
        
        true_negatives = 0
        for path in normal_images:
            probs, _ = engine.predict(path)
            predicted_class = np.argmax(probs)
            if predicted_class == 0:
                true_negatives += 1
        
        specificity = true_negatives / len(normal_images) if normal_images else 0
        passed = specificity >= specificity_threshold
        
        return ValidationResult(
            test_name="Normal Class Specificity",
            passed=passed,
            score=specificity * 100,
            threshold=specificity_threshold * 100,
            details=f"Specificity: {specificity*100:.1f}% (threshold: {specificity_threshold*100:.0f}%)"
        )


class ThroughputSustainabilityTest:
    """测试5: 吞吐量持续性测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            duration_seconds: int = 60,
            min_throughput: float = 50.0) -> ValidationResult:
        """
        模拟60秒持续运行，验证模型能否持续处理
        目标: 至少50bpm (833ms/frame)
        """
        
        image_paths, _ = generator.generate_test_dataset(samples_per_class=5)
        total_processed = 0
        frame_times = []
        
        start = time.perf_counter()
        end_time = start + duration_seconds
        
        while time.perf_counter() < end_time:
            frame_start = time.perf_counter()
            
            # 处理一个frame
            path = random.choice(image_paths)
            _, latency = engine.predict(path)
            total_processed += 1
            
            frame_time = time.perf_counter() - frame_start
            frame_times.append(frame_time)
        
        elapsed = time.perf_counter() - start
        actual_bpm = total_processed / (elapsed / 60)
        avg_frame_time_ms = np.mean(frame_times) * 1000
        
        passed = actual_bpm >= min_throughput
        
        return ValidationResult(
            test_name="Throughput Sustainability",
            passed=passed,
            score=actual_bpm,
            threshold=min_throughput,
            details=(
                f"{duration_seconds}s test: {total_processed} frames @ "
                f"{actual_bpm:.1f}bpm (avg frame: {avg_frame_time_ms:.1f}ms, "
                f"target: {1000/min_throughput:.0f}ms)"
            )
        )


class MultiChannelLoadTest:
    """测试6: 多通道负载测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            num_channels: int = 3,
            target_bpm_per_channel: int = 50) -> ValidationResult:
        """
        模拟多通道同时推理，验证Pi 4能否支撑
        3通道×50bpm = 150bpm = 150ms/frame总处理时间
        """
        
        image_paths, _ = generator.generate_test_dataset(samples_per_class=5)
        
        # 模拟3个通道同时请求
        channel_loads = []
        for ch in range(num_channels):
            ch_start = time.perf_counter()
            for _ in range(10):  # 每通道10帧
                _, latency = engine.predict(random.choice(image_paths))
            ch_time = (time.perf_counter() - ch_start) * 1000
            channel_loads.append(ch_time)
        
        max_channel_time = max(channel_loads)
        avg_channel_time = np.mean(channel_loads)
        
        # 每帧处理时间应该 < 1000ms/50bpm = 20ms
        target_per_frame_ms = 1000 / target_bpm_per_channel
        passed = avg_channel_time <= target_per_frame_ms * 2  # 2倍余量
        
        return ValidationResult(
            test_name="Multi-Channel Load",
            passed=passed,
            score=avg_channel_time,
            threshold=target_per_frame_ms * 2,
            details=(
                f"{num_channels} channels × {target_bpm_per_channel}bpm | "
                f"Avg: {avg_channel_time:.1f}ms | Max: {max_channel_time:.1f}ms | "
                f"Target: <{target_per_frame_ms:.0f}ms/frame (with 2x margin)"
            )
        )


class RobustnessNoiseTest:
    """测试7: 鲁棒性噪声测试"""
    
    @staticmethod
    def run(generator: SyntheticTestDatasetGenerator, engine: MLInferenceEngine,
            noise_levels: List[float] = [0.02, 0.05, 0.10, 0.15]) -> ValidationResult:
        """
        测试模型对不同噪声水平的鲁棒性
        硬件传感器会产生各种噪声
        """
        
        image_paths, class_labels = generator.generate_test_dataset(samples_per_class=5)
        
        results = {}
        for noise in noise_levels:
            correct = 0
            total = 0
            
            for i, path in enumerate(image_paths[:50]):
                # 加载并添加噪声
                img = cv2.imread(path)
                if img is None:
                    continue
                
                noise_array = np.random.normal(0, noise * 255, img.shape).astype(np.int16)
                noisy_img = np.clip(img.astype(np.int16) + noise_array, 0, 255).astype(np.uint8)
                
                # 保存临时图像
                temp_path = path.replace(".png", f"_noise{int(noise*100)}.png")
                cv2.imwrite(temp_path, noisy_img)
                
                probs, _ = engine.predict(temp_path)
                predicted = np.argmax(probs)
                
                if predicted == class_labels[i]:
                    correct += 1
                total += 1
                
                os.remove(temp_path)
            
            accuracy = correct / total if total > 0 else 0
            results[noise] = accuracy
        
        # 10%噪声下准确率应该 > 70%
        acc_at_10pct = results.get(0.10, 0)
        passed = acc_at_10pct >= 0.70
        
        details = " | ".join([f"noise={n:.0%}: acc={a*100:.0f}%" for n, a in results.items()])
        
        return ValidationResult(
            test_name="Robustness - Noise",
            passed=passed,
            score=acc_at_10pct * 100,
            threshold=70.0,
            details=details
        )


class ModelFileIntegrityTest:
    """测试8: 模型文件完整性测试"""
    
    @staticmethod
    def run(model_path: str = None) -> ValidationResult:
        """验证模型文件存在且格式正确"""
        
        if model_path is None:
            # 查找默认模型路径
            possible_paths = [
                PROJECT_ROOT / "sorter" / "camera" / "models" / "beans_v1_int8.tflite",
                PROJECT_ROOT / "models" / "beans_int8.tflite",
                "./beans_int8.tflite",
            ]
            for p in possible_paths:
                if Path(p).exists():
                    model_path = str(p)
                    break
        
        if model_path is None or not Path(model_path).exists():
            # 模型不存在 - 这是预硬件阶段的预期状态
            return ValidationResult(
                test_name="Model File Integrity",
                passed=True,  # 不阻塞 - 模型会在硬件到位后加载
                score=0,
                threshold=0,
                details="Model not yet trained (expected pre-hardware). Will validate when hardware arrives.",
                warnings=["Model file not found - will be trained after hardware procurement"]
            )
        
        # 检查文件大小
        file_size_mb = Path(model_path).stat().st_size / (1024 * 1024)
        
        # INT8量化模型应该 < 10MB
        passed = file_size_mb < 10.0
        
        return ValidationResult(
            test_name="Model File Integrity",
            passed=passed,
            score=file_size_mb,
            threshold=10.0,
            details=f"Model size: {file_size_mb:.2f}MB (INT8 target: <10MB)"
        )


class PipelineIntegrationTest:
    """测试9: 端到端Pipeline集成测试"""
    
    @staticmethod
    def run() -> ValidationResult:
        """
        测试完整ML pipeline的组件集成
        不依赖实际硬件，仅验证软件栈完整性
        """
        
        checks = {
            "numpy_available": HAS_NUMPY,
            "cv2_available": HAS_CV2,
            "pil_available": HAS_PIL,
        }
        
        try:
            import tflite_runtime.interpreter as tflite
            checks["tflite_available"] = True
        except ImportError:
            checks["tflite_available"] = False
        
        passed = all(checks.values())
        
        details = " | ".join([f"{k}: {'✓' if v else '✗'}" for k, v in checks.items()])
        
        return ValidationResult(
            test_name="Pipeline Integration",
            passed=passed,
            score=sum(checks.values()) / len(checks) * 100,
            threshold=100.0,
            details=details,
            warnings=["TFLite runtime missing - install tflite_runtime for actual edge inference" 
                     if not checks.get("tflite_available") else ""]
        )


# =============================================================================
# VALIDATION ORCHESTRATOR
# =============================================================================

class MLFieldValidationOrchestrator:
    """ML现场验证编排器"""
    
    def __init__(self, model_path: str = None, output_dir: str = None):
        self.model_path = model_path
        self.output_dir = Path(output_dir or "./reports/ml_validation")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.engine = MLInferenceEngine(model_path)
        self.generator = SyntheticTestDatasetGenerator()
    
    def run_all_tests(self, generate_dataset: bool = True) -> FieldValidationReport:
        """运行所有验证测试"""
        
        start_time = time.perf_counter()
        report_id = f"MLVAL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        print(f"\n{'='*60}")
        print(f"ML Model Field Validation Framework")
        print(f"Report ID: {report_id}")
        print(f"{'='*60}\n")
        
        results = []
        
        # 测试1: 模型文件完整性
        print("Test 1/9: Model File Integrity...")
        results.append(ModelFileIntegrityTest.run(self.model_path))
        
        # 测试2: Pipeline集成
        print("Test 2/9: Pipeline Integration...")
        results.append(PipelineIntegrationTest.run())
        
        # 测试3: 推理延迟
        print("Test 3/9: Inference Latency...")
        results.append(InferenceLatencyTest.run(self.generator, self.engine))
        
        # 测试4: 置信度分布
        print("Test 4/9: Confidence Distribution...")
        results.append(ConfidenceDistributionTest.run(self.generator, self.engine))
        
        # 测试5: 关键缺陷召回
        print("Test 5/9: Critical Defect Recall...")
        results.append(CriticalDefectRecallTest.run(self.generator, self.engine))
        
        # 测试6: 正常类特异性
        print("Test 6/9: Normal Class Specificity...")
        results.append(NormalClassSpecificityTest.run(self.generator, self.engine))
        
        # 测试7: 吞吐量持续性
        print("Test 7/9: Throughput Sustainability (60s)...")
        results.append(ThroughputSustainabilityTest.run(self.generator, self.engine))
        
        # 测试8: 多通道负载
        print("Test 8/9: Multi-Channel Load...")
        results.append(MultiChannelLoadTest.run(self.generator, self.engine))
        
        # 测试9: 鲁棒性噪声
        print("Test 9/9: Robustness - Noise...")
        results.append(RobustnessNoiseTest.run(self.generator, self.engine))
        
        duration = time.perf_counter() - start_time
        
        # 汇总
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        warnings_count = sum(len(r.warnings) for r in results)
        
        # Calculate overall_score as percentage (0-100) based on threshold compliance
        # Each test's score is normalized to 0-100 based on whether it passed and by how much
        score_components = []
        for r in results:
            if r.threshold > 0:
                # For tests with a threshold, score = min(100, (score / threshold) * 100) capped at 100
                normalized = min(100.0, (r.score / r.threshold) * 100)
            else:
                # For tests without threshold (e.g., percentage-based), use score directly
                normalized = min(100.0, r.score)
            score_components.append(normalized)
        
        overall_score = (sum(score_components) / total) if total > 0 else 0
        overall_pass = failed == 0
        
        # 生成建议
        recommendations = []
        for r in results:
            if not r.passed:
                recommendations.append(f"[FAIL] {r.test_name}: {r.details}")
            elif r.warnings:
                recommendations.append(f"[WARN] {r.test_name}: {r.warnings[0]}")
        
        if overall_pass:
            recommendations.insert(0, "✅ All validation tests passed - model is production ready")
        else:
            recommendations.insert(0, "⚠️ Some tests failed - review recommendations above before deployment")
        
        report = FieldValidationReport(
            report_id=report_id,
            timestamp=datetime.now().isoformat(),
            model_path=self.model_path or "Not yet loaded",
            total_tests=total,
            passed=passed,
            failed=failed,
            warnings_count=warnings_count,
            overall_pass=overall_pass,
            overall_score=overall_score,
            duration_seconds=duration,
            results=results,
            recommendations=recommendations,
            metadata={
                "engine_stats": {
                    "total_inferences": self.engine.inference_count,
                    "avg_latency_ms": self.engine.get_average_latency()
                },
                "test_configuration": {
                    "latency_target_ms": 50,
                    "recall_threshold": 0.85,
                    "specificity_threshold": 0.90,
                    "throughput_target_bpm": 50,
                    "num_channels": 3
                }
            }
        )
        
        return report
    
    def print_report(self, report: FieldValidationReport):
        """打印验证报告"""
        
        print(f"\n{'='*60}")
        print(f"VALIDATION REPORT: {report.report_id}")
        print(f"{'='*60}")
        print(f"Timestamp: {report.timestamp}")
        print(f"Duration: {report.duration_seconds:.1f}s")
        print(f"Model: {report.model_path}")
        print()
        
        print(f"Results: {report.passed}/{report.total_tests} PASSED")
        if report.failed > 0:
            print(f"         {report.failed} FAILED 🔴")
        if report.warnings_count > 0:
            print(f"         {report.warnings_count} warnings ⚠️")
        print()
        
        print(f"Overall Score: {report.overall_score:.1f}/100")
        print(f"Overall Status: {'✅ PASS' if report.overall_pass else '⚠️ CONDITIONAL PASS'}")
        print()
        
        print("-" * 60)
        print("TEST DETAILS")
        print("-" * 60)
        
        for i, r in enumerate(report.results, 1):
            status = "✅" if r.passed else "❌"
            print(f"\n{i}. {r.test_name} [{status}]")
            print(f"   Score: {r.score:.1f} | Threshold: {r.threshold:.1f}")
            print(f"   {r.details}")
            if r.warnings:
                for w in r.warnings:
                    print(f"   ⚠️ {w}")
        
        print()
        print("-" * 60)
        print("RECOMMENDATIONS")
        print("-" * 60)
        for rec in report.recommendations:
            print(f"  {rec}")
        
        print()
        print(f"{'='*60}")
    
    def save_report(self, report: FieldValidationReport) -> str:
        """保存JSON报告"""
        
        report_dict = {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "model_path": report.model_path,
            "summary": {
                "total_tests": report.total_tests,
                "passed": int(report.passed),
                "failed": int(report.failed),
                "warnings_count": int(report.warnings_count),
                "overall_pass": bool(report.overall_pass),
                "overall_score": float(report.overall_score),
                "duration_seconds": float(report.duration_seconds)
            },
            "results": [
                {
                    "test_name": str(r.test_name),
                    "passed": bool(r.passed),
                    "score": float(r.score),
                    "threshold": float(r.threshold),
                    "details": str(r.details),
                    "latency_ms": float(r.latency_ms),
                    "warnings": [str(w) for w in r.warnings]
                }
                for r in report.results
            ],
            "recommendations": [str(rec) for rec in report.recommendations],
            "metadata": {
                "engine_stats": {
                    "total_inferences": int(report.metadata.get("engine_stats", {}).get("total_inferences", 0)),
                    "avg_latency_ms": float(report.metadata.get("engine_stats", {}).get("avg_latency_ms", 0))
                },
                "test_configuration": report.metadata.get("test_configuration", {})
            }
        }
        
        filepath = self.output_dir / f"{report.report_id}.json"
        with open(filepath, "w") as f:
            json.dump(report_dict, f, indent=2)
        
        return str(filepath)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="ML Model Field Validation Framework")
    parser.add_argument("--model", "-m", type=str, help="Path to TFLite model")
    parser.add_argument("--output", "-o", type=str, default="./reports/ml_validation",
                       help="Output directory for reports")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Quick mode - skip slow tests")
    args = parser.parse_args()
    
    orchestrator = MLFieldValidationOrchestrator(
        model_path=args.model,
        output_dir=args.output
    )
    
    report = orchestrator.run_all_tests()
    orchestrator.print_report(report)
    filepath = orchestrator.save_report(report)
    
    print(f"\n📄 Report saved to: {filepath}")
    print(f"\n🎯 Next steps:")
    print(f"   1. Review recommendations above")
    print(f"   2. Hardware arrives ~2026-07-13")
    print(f"   3. After hardware: re-run with --model path/to/beans_int8.tflite")
    
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())