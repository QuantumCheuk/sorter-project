"""
Coffee Bean Defect Detection — ML Training Pipeline
=====================================================
HUSKY-SORTER-001 | Green Coffee Bean Sorter

Purpose:
    Framework for training and deploying the bean defect detection model.
    Supports both synthetic data (pre-hardware) and real data (post-hardware)
    collection pipelines.

Hardware: HQ Camera IMX477 (top) + Logitech C270 (bottom)
Model:    MobileNetV2 + custom classification head
Framework: TensorFlow Lite / PyTorch (dual support)

Classes (14 defect types):
    0: normal         — Good quality bean
    1: mold           — Moldy bean (blue-green patches)
    2: fermented      — Fermented/unwanted fermentation (brown, sour smell)
    3: black          — Black bean (over-fermented or damaged)
    4: broken         — Broken/chipped bean
    5: foreign        — Foreign matter (stones, twigs, wood)
    6: underweight    — Severely underweight/shriveled bean
    7: underdeveloped  — Immature/flat bean (low density)
    8: dead           — Dead bean (no germination potential)
    9: insect         — Insect-damaged/虫蛀豆
    10: hollow        — Hollow bean (empty interior)
    11: over_dry      — Over-dried bean (cracked, light)
    12: over_wet      — Over-wet bean (visible moisture, risk of mold)
    13: pre_mold      — Pre-mold condition (early discoloration)

Quality Action:
    - normal (class 0) → PASS → route to grade bin
    - any defect (class 1-13) → REJECT → waste bin

---
Usage (pre-hardware, synthetic data):
    python -m sorter.camera.ml_pipeline --mode synthetic --generate 5000

Usage (post-hardware, real data collection):
    python -m sorter.camera.ml_pipeline --mode collect --duration 3600

Usage (training):
    python -m sorter.camera.ml_pipeline --mode train --epochs 50 --data ./data/beans/

Usage (evaluation):
    python -m sorter.camera.ml_pipeline --mode evaluate --model ./models/beans_v1.tflite

Usage (export):
    python -m sorter.camera.ml_pipeline --mode export --model ./models/beans_v1.h5
"""

import os
import sys
import json
import argparse
import datetime
import hashlib
import random
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

import numpy as np

# ============================================================
# Constants
# ============================================================

BEAN_CLASSES = [
    "normal", "mold", "fermented", "black", "broken",
    "foreign", "underweight", "underdeveloped", "dead",
    "insect", "hollow", "over_dry", "over_wet", "pre_mold"
]
NUM_CLASSES = len(BEAN_CLASSES)

# Image dimensions (HQ Camera IMX477 at 4056x3040, downscale for training)
TRAIN_INPUT_SIZE = (224, 224)  # MobileNetV2 default
FULL_RES_SIZE = (4056, 3040)

# L*a*b* color ranges for each defect class (approximate real-world values)
# Format: [L_min, L_max, a_min, a_max, b_min, b_max]
LAB_RANGES = {
    "normal":        [50, 85, -5, 15, 10, 40],    # Light green-brown
    "mold":          [25, 60, -5, 20, -10, 30],   # Blue-green patches
    "fermented":    [30, 60, 5, 30, 10, 45],     # Brownish-red
    "black":         [5, 30, 0, 15, -5, 15],       # Near black
    "broken":        [45, 80, -3, 12, 8, 35],     # Exposed interior
    "foreign":       [40, 90, -5, 20, 5, 50],     # Variable by material
    "underweight":   [55, 85, -8, 10, 8, 38],     # Light, pale
    "underdeveloped":[50, 80, -6, 12, 8, 40],    # Smaller, lighter
    "dead":          [45, 75, -5, 15, 5, 35],      # Dull, lifeless
    "insect":        [35, 65, 0, 25, 5, 40],       # Brown damage marks
    "hollow":        [50, 82, -6, 12, 8, 38],     # Slight color difference
    "over_dry":      [55, 88, -7, 8, 10, 42],      # Cracked, light
    "over_wet":      [40, 70, -3, 18, 8, 45],     # Darker, moist appearance
    "pre_mold":      [45, 75, -3, 18, 5, 38],     # Early discoloration
}

# Defect → Rejection mapping
DEFECT_REJECTION = {cls: (cls != "normal") for cls in BEAN_CLASSES}

# Training hyperparameters
DEFAULT_BATCH_SIZE = 32
DEFAULT_EPOCHS = 50
DEFAULT_LEARNING_RATE = 0.001
IMAGE_AUGMENTATION = {
    "rotation_range": 15,
    "width_shift_range": 0.1,
    "height_shift_range": 0.1,
    "zoom_range": 0.1,
    "horizontal_flip": True,
    "brightness_range": [0.8, 1.2],
}


# ============================================================
# Data Classes
# ============================================================

@dataclass
class BeanImageRecord:
    """Single bean image record for training dataset."""
    image_path: str
    bean_id: str
    camera_position: str  # "top" or "bottom"
    defect_class: int     # 0-13
    class_name: str
    is_reject: bool
    metadata: Dict[str, Any]
    captured_at: str
    confidence: float = 1.0  # Human annotator confidence

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "bean_id": self.bean_id,
            "camera_position": self.camera_position,
            "defect_class": self.defect_class,
            "class_name": self.class_name,
            "is_reject": self.is_reject,
            "metadata": self.metadata,
            "captured_at": self.captured_at,
            "confidence": self.confidence,
        }


@dataclass
class TrainingConfig:
    """Training configuration."""
    model_name: str = "mobilenet_v2"
    input_size: Tuple[int, int] = TRAIN_INPUT_SIZE
    num_classes: int = NUM_CLASSES
    batch_size: int = DEFAULT_BATCH_SIZE
    epochs: int = DEFAULT_EPOCHS
    learning_rate: float = DEFAULT_LEARNING_RATE
    train_split: float = 0.7
    val_split: float = 0.15
    test_split: float = 0.15
    augmentation: Dict[str, Any] = field(default_factory=lambda: IMAGE_AUGMENTATION.copy())
    use_synthetic: bool = False
    data_dir: str = "./data/beans"
    output_dir: str = "./models"
    label_smoothing: float = 0.1
    class_weights: Optional[List[float]] = None  # Auto-computed if None

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "input_size": list(self.input_size),
            "num_classes": self.num_classes,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "train_split": self.train_split,
            "val_split": self.val_split,
            "test_split": self.test_split,
            "augmentation": self.augmentation,
            "use_synthetic": self.use_synthetic,
            "data_dir": self.data_dir,
            "output_dir": self.output_dir,
            "label_smoothing": self.label_smoothing,
        }


@dataclass
class ModelEvaluation:
    """Model evaluation metrics."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    per_class_precision: List[float]
    per_class_recall: List[float]
    confusion_matrix: np.ndarray
    total_params: int
    inference_time_ms: float
    model_size_mb: float

    def to_dict(self) -> dict:
        return {
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "per_class_precision": [round(p, 4) for p in self.per_class_precision],
            "per_class_recall": [round(r, 4) for r in self.per_class_recall],
            "confusion_matrix": self.confusion_matrix.tolist(),
            "total_params": self.total_params,
            "inference_time_ms": round(self.inference_time_ms, 3),
            "model_size_mb": round(self.model_size_mb, 2),
        }


# ============================================================
# Synthetic Data Generation (Pre-Hardware)
# ============================================================

class SyntheticBeanGenerator:
    """
    Generates synthetic coffee bean images for pre-hardware model development.

    Uses procedural generation based on real bean color/size distributions.
    Note: Synthetic data supplements but does NOT replace real training data.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.bean_count = 0

    def generate_bean_image(
        self,
        defect_class: int,
        camera_position: str = "top",
        add_noise: bool = True,
        add_artefacts: bool = True,
    ) -> np.ndarray:
        """
        Generate a single synthetic bean image.

        Args:
            defect_class: 0-13 (BEAN_CLASSES index)
            camera_position: "top" (HQ Camera) or "bottom" (C270)
            add_noise: Add sensor noise
            add_artefacts: Add lighting artefacts

        Returns:
            RGB image as np.ndarray (uint8, shape: 224x224x3)
        """
        h, w = TRAIN_INPUT_SIZE
        img = np.zeros((h, w, 3), dtype=np.uint8)

        # Background: dark box interior (dark gray ~#1a1a1a to #2a2a2a)
        bg_l = self.rng.integers(20, 45)
        img[:, :] = [bg_l, bg_l, bg_l]

        # Bean parameters based on defect class
        lab = LAB_RANGES[BEAN_CLASSES[defect_class]]
        L_mean = (lab[0] + lab[1]) / 2
        a_mean = (lab[2] + lab[3]) / 2
        b_mean = (lab[4] + lab[5]) / 2

        # Bean shape: ellipse (flattened slightly for side/top view)
        bean_w = self.rng.integers(60, 90)
        bean_h = self.rng.integers(40, 65)
        cx = self.rng.integers(bean_w // 2 + 10, w - bean_w // 2 - 10)
        cy = self.rng.integers(bean_h // 2 + 10, h - bean_h // 2 - 10)

        # Generate bean pixel coordinates
        y_coords, x_coords = np.ogrid[:h, :w]
        ellipse_mask = (
            ((x_coords - cx) / (bean_w / 2)) ** 2 +
            ((y_coords - cy) / (bean_h / 2)) ** 2
        ) <= 1

        # Color variation within bean (texture)
        L_variation = self.rng.normal(0, 5, (h, w))
        a_variation = self.rng.normal(0, 3, (h, w))
        b_variation = self.rng.normal(0, 4, (h, w))

        L_pixels = np.clip(L_mean + L_variation, 0, 100).astype(np.float32)
        a_pixels = np.clip(a_mean + a_variation, -128, 127).astype(np.float32)
        b_pixels = np.clip(b_mean + b_variation, -128, 127).astype(np.float32)

        # Convert Lab to RGB
        from colorsys import hls_to_rgb
        def lab_to_rgb(L, a, b):
            # Simple approximation: Lab -> XYZ -> RGB
            # Using the formula from ITU-R BT.709
            # First Lab -> XYZ
            L1 = (L + 16) / 116
            X = 0.95047 * (L1 + a / 500)
            Y = 1.00000 * L1
            Z = 1.08883 * (L1 - b / 200)

            X, Y, Z = [max(x, 0.001) for x in [X, Y, Z]]
            # XYZ -> linear RGB (D65 illuminant)
            r_lin = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
            g_lin = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
            b_lin = 0.0557 * X - 0.2040 * Y + 1.0570 * Z

            # Gamma correction
            def gamma(x):
                return (12.92 * x) if x <= 0.0031308 else (1.055 * (x ** (1/2.4)) - 0.055)
            r = gamma(r_lin)
            g = gamma(g_lin)
            b = gamma(b_lin)
            return [int(max(0, min(255, round(x * 255)))) for x in [r, g, b]]

        rgb_img = np.zeros((h, w, 3), dtype=np.uint8)
        for i in range(h):
            for j in range(w):
                if ellipse_mask[i, j]:
                    rgb_img[i, j] = lab_to_rgb(L_pixels[i, j], a_pixels[i, j], b_pixels[i, j])

        # Blend onto background
        img[ellipse_mask] = rgb_img[ellipse_mask]

        # Lighting artefacts (LED ring light reflection)
        if add_artefacts:
            light_x = cx + self.rng.integers(-10, 10)
            light_y = cy + self.rng.integers(-10, 10)
            dist = np.sqrt((x_coords - light_x)**2 + (y_coords - light_y)**2)
            highlight = np.exp(-dist / 80) * 30
            img[:, :, 0] = np.clip(img[:, :, 0] + highlight * 0.95, 0, 255).astype(np.uint8)
            img[:, :, 1] = np.clip(img[:, :, 1] + highlight * 0.95, 0, 255).astype(np.uint8)
            img[:, :, 2] = np.clip(img[:, :, 2] + highlight * 0.95, 0, 255).astype(np.uint8)

        # Sensor noise (Poisson + Gaussian)
        if add_noise:
            noise_std = self.rng.uniform(1.0, 3.0)
            img = np.clip(img + self.rng.normal(0, noise_std, img.shape), 0, 255).astype(np.uint8)
            # Shot noise
            img = np.clip(img + self.rng.poisson(0.5, img.shape), 0, 255).astype(np.uint8)

        # Add specular highlight (moisture sheen, for over_wet class)
        if defect_class == 12:  # over_wet
            spec_x = cx + self.rng.integers(-5, 5)
            spec_y = cy + self.rng.integers(-5, 5)
            dist = np.sqrt((x_coords - spec_x)**2 + (y_coords - spec_y)**2)
            spec = np.exp(-dist / 15) * 40
            img[:, :, 0] = np.clip(img[:, :, 0] - spec * 0.3, 0, 255).astype(np.uint8)
            img[:, :, 1] = np.clip(img[:, :, 1] - spec * 0.3, 0, 255).astype(np.uint8)
            img[:, :, 2] = np.clip(img[:, :, 2] + spec * 0.5, 0, 255).astype(np.uint8)

        # Add crack lines (for over_dry class)
        if defect_class == 11:  # over_dry
            num_cracks = self.rng.integers(1, 4)
            for _ in range(num_cracks):
                angle = self.rng.uniform(0, math.pi)
                length = self.rng.integers(10, 30)
                cx_c = cx + self.rng.integers(-20, 20)
                cy_c = cy + self.rng.integers(-20, 20)
                for d in range(-length // 2, length // 2):
                    px = int(cx_c + d * math.cos(angle))
                    py = int(cy_c + d * math.sin(angle))
                    if 0 <= px < w and 0 <= py < h:
                        for dy in range(-1, 2):
                            for dx in range(-1, 2):
                                if 0 <= px+dx < w and 0 <= py+dy < h:
                                    img[py+dy, px+dx] = [bg_l, bg_l, bg_l]

        self.bean_count += 1
        return img

    def generate_dataset(
        self,
        samples_per_class: int = 500,
        output_dir: str = "./data/synthetic_beans",
        split_ratios: Tuple[float, float, float] = (0.7, 0.15, 0.15),
    ) -> Dict[str, List[BeanImageRecord]]:
        """
        Generate a complete synthetic training dataset.

        Args:
            samples_per_class: Number of images per defect class
            output_dir: Root directory for dataset
            split_ratios: (train, val, test) — must sum to 1.0

        Returns:
            Dictionary with train/val/test record lists
        """
        train_split, val_split, test_split = split_ratios
        assert abs(train_split + val_split + test_split - 1.0) < 1e-6

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_id = f"synthetic_beans_{timestamp}"

        splits = {"train": train_split, "val": val_split, "test": test_split}
        datasets: Dict[str, List[BeanImageRecord]] = {k: [] for k in splits}

        print(f"🎨 Generating synthetic dataset: {NUM_CLASSES} classes × {samples_per_class} samples")
        print(f"   Output: {output_dir}/{dataset_id}")

        total = NUM_CLASSES * samples_per_class
        current = 0

        for class_idx, class_name in enumerate(BEAN_CLASSES):
            for i in range(samples_per_class):
                # Determine split
                r = (i + 1) / samples_per_class
                if r <= train_split:
                    split = "train"
                elif r <= train_split + val_split:
                    split = "val"
                else:
                    split = "test"

                # Generate image
                cam_pos = "top" if self.rng.random() > 0.3 else "bottom"
                img = self.generate_bean_image(class_idx, cam_pos)

                # Save image
                bean_id = f"syn_{dataset_id}_{class_name}_{i:04d}"
                filename = f"{bean_id}.png"
                subdir = os.path.join(output_dir, dataset_id, split, class_name)
                os.makedirs(subdir, exist_ok=True)
                filepath = os.path.join(subdir, filename)

                # Save as PNG
                try:
                    import tensorflow as tf
                    tf.io.write_file(filepath, tf.image.encode_png(img))
                except ImportError:
                    # Fallback: PIL
                    from PIL import Image
                    Image.fromarray(img).save(filepath)

                # Create record
                record = BeanImageRecord(
                    image_path=filepath,
                    bean_id=bean_id,
                    camera_position=cam_pos,
                    defect_class=class_idx,
                    class_name=class_name,
                    is_reject=DEFECT_REJECTION[class_name],
                    metadata={
                        "dataset_id": dataset_id,
                        "synthetic": True,
                        "class_distribution": BEAN_CLASSES,
                    },
                    captured_at=datetime.datetime.now().isoformat(),
                )
                datasets[split].append(record)

                current += 1
                if current % 100 == 0:
                    print(f"   Progress: {current}/{total} ({100*current/total:.1f}%)")

        # Save dataset manifest
        manifest_path = os.path.join(output_dir, dataset_id, "manifest.json")
        manifest = {
            "dataset_id": dataset_id,
            "created_at": datetime.datetime.now().isoformat(),
            "num_classes": NUM_CLASSES,
            "classes": BEAN_CLASSES,
            "samples_per_class": samples_per_class,
            "split": {k: len(v) for k, v in datasets.items()},
            "camera_positions": ["top", "bottom"],
            "image_size": list(TRAIN_INPUT_SIZE),
            "synthetic": True,
            "records": {k: [r.to_dict() for r in v] for k, v in datasets.items()},
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"\n✅ Dataset generated: {dataset_id}")
        print(f"   Train: {len(datasets['train'])} | Val: {len(datasets['val'])} | Test: {len(datasets['test'])}")
        print(f"   Manifest: {manifest_path}")

        return datasets


# ============================================================
# Data Collection (Post-Hardware)
# ============================================================

class BeanDataCollector:
    """
    Real data collection manager for post-hardware deployment.
    Integrates with dark_box_test_protocol.py for systematic data collection.
    """

    def __init__(self, output_dir: str = "./data/beans_real", dark_box_protocol=None):
        self.output_dir = output_dir
        self.dark_box = dark_box_protocol
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(output_dir, f"session_{self.session_id}")
        os.makedirs(self.session_dir, exist_ok=True)

        self.pending_annotation: List[str] = []
        self.annotated: List[BeanImageRecord] = []

    def capture_bean_pair(
        self,
        bean_id: str,
        top_image: np.ndarray,
        bottom_image: np.ndarray,
        sensor_data: Optional[Dict] = None,
    ) -> Tuple[str, str]:
        """
        Capture a top+bottom bean image pair for annotation.

        Args:
            bean_id: Unique bean identifier
            top_image: RGB image from top camera
            bottom_image: RGB image from bottom camera
            sensor_data: Optional metadata (weight, moisture, etc.)

        Returns:
            (top_path, bottom_path) of saved images
        """
        metadata = {
            "bean_id": bean_id,
            "session_id": self.session_id,
            "captured_at": datetime.datetime.now().isoformat(),
            "sensor_data": sensor_data or {},
            "annotated": False,
        }

        top_path = os.path.join(self.session_dir, f"{bean_id}_top.png")
        bottom_path = os.path.join(self.session_dir, f"{bean_id}_bottom.png")

        # Save images
        try:
            from PIL import Image
            Image.fromarray(top_image).save(top_path)
            Image.fromarray(bottom_image).save(bottom_path)
        except ImportError:
            import tensorflow as tf
            tf.io.write_file(top_path, tf.image.encode_png(top_image))
            tf.io.write_file(bottom_path, tf.image.encode_png(bottom_image))

        # Write metadata sidecar
        meta_path = os.path.join(self.session_dir, f"{bean_id}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        self.pending_annotation.append(bean_id)
        return top_path, bottom_path

    def export_for_annotation(self, output_csv: str) -> int:
        """
        Export pending samples as CSV for human annotation tool (LabelImg / CVAT).

        Returns:
            Number of samples exported
        """
        import csv

        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["image_path", "bean_id", "top_image", "bottom_image", "defect_class", "annotator", "notes"])
            for bean_id in self.pending_annotation:
                top_path = os.path.join(self.session_dir, f"{bean_id}_top.png")
                bottom_path = os.path.join(self.session_dir, f"{bean_id}_bottom.png")
                writer.writerow([top_path, bean_id, top_path, bottom_path, "", "", ""])

        print(f"📋 Exported {len(self.pending_annotation)} samples to {output_csv}")
        return len(self.pending_annotation)


# ============================================================
# Model Training (TensorFlow/Keras)
# ============================================================

class BeanDefectTrainer:
    """
    Model training pipeline for coffee bean defect detection.

    Architecture: MobileNetV2 (pretrained on ImageNet) + custom classification head
    Transfer Learning: Fine-tune last 30 layers
    Optimization: Adam + cosine learning rate schedule

    For production edge deployment: export to TensorFlow Lite (INT8 quantized)
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.history = None

    def build_model(self) -> Any:
        """
        Build MobileNetV2 + custom head model.

        Returns:
            Compiled Keras model
        """
        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras import layers, models
            from tensorflow.keras.applications import MobileNetV2
            from tensorflow.keras.optimizers import Adam
            from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
        except ImportError:
            print("❌ TensorFlow not installed. Run: pip install tensorflow")
            print("   For PyTorch fallback, use --framework pytorch")
            return None

        # Load pretrained MobileNetV2 (ImageNet)
        base_model = MobileNetV2(
            input_shape=(self.config.input_size[0], self.config.input_size[1], 3),
            include_top=False,
            weights="imagenet",
            pooling="avg",
        )

        # Freeze base model initially (fine-tune later)
        base_model.trainable = False

        # Build model
        inputs = layers.Input(shape=(self.config.input_size[0], self.config.input_size[1], 3))
        x = base_model(inputs, training=False)
        x = layers.Dropout(0.3)(x)
        x = layers.Dense(256, activation="relu", kernel_regularizer=keras.regularizers.l2(1e-4))(x)
        x = layers.Dropout(0.3)(x)
        outputs = layers.Dense(self.config.num_classes, activation="softmax")(x)

        self.model = models.Model(inputs, outputs)

        # Compile
        self.model.compile(
            optimizer=Adam(learning_rate=self.config.learning_rate),
            loss=keras.losses.CategoricalCrossentropy(label_smoothing=self.config.label_smoothing),
            metrics=["accuracy", keras.metrics.Precision(), keras.metrics.Recall()],
        )

        # Model summary
        total_params = self.model.count_params()
        print(f"📐 Model: MobileNetV2 + custom head ({total_params:,} parameters)")

        return self.model

    def fine_tune(self, unfreeze_layers: int = 30) -> None:
        """
        Fine-tune last N layers of MobileNetV2 base.

        Args:
            unfreeze_layers: Number of last layers to unfreeze
        """
        if self.model is None:
            print("❌ Model not built yet")
            return

        import tensorflow as tf
        from tensorflow import keras

        base_model = self.model.layers[1]  # MobileNetV2
        base_model.trainable = True

        # Unfreeze last N layers
        for layer in base_model.layers[-unfreeze_layers:]:
            layer.trainable = True

        # Recompile with lower learning rate
        self.model.compile(
            optimizer=Adam(learning_rate=self.config.learning_rate * 0.1),
            loss=keras.losses.CategoricalCrossentropy(label_smoothing=self.config.label_smoothing),
            metrics=["accuracy", keras.metrics.Precision(), keras.metrics.Recall()],
        )
        print(f"🔧 Fine-tuned last {unfreeze_layers} layers of MobileNetV2")

    def train(self, data_dir: str) -> Optional[Dict]:
        """
        Train the model on collected data.

        Args:
            data_dir: Path to dataset (must have train/val/test subdirs with class subdirs)

        Returns:
            Training history dict
        """
        if self.model is None:
            self.build_model()

        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras.callbacks import (
                EarlyStopping, ModelCheckpoint, ReduceLROnPlateau,
                CSVLogger, TensorBoard
            )
        except ImportError:
            print("❌ TensorFlow not installed")
            return None

        # Data generators
        train_datagen = keras.preprocessing.image.ImageDataGenerator(
            rotation_range=self.config.augmentation["rotation_range"],
            width_shift_range=self.config.augmentation["width_shift_range"],
            height_shift_range=self.config.augmentation["height_shift_range"],
            zoom_range=self.config.augmentation["zoom_range"],
            horizontal_flip=self.config.augmentation["horizontal_flip"],
            brightness_range=self.config.augmentation["brightness_range"],
            rescale=1.0 / 255.0,
        )

        val_datagen = keras.preprocessing.image.ImageDataGenerator(rescale=1.0 / 255.0)

        train_dir = os.path.join(data_dir, "train")
        val_dir = os.path.join(data_dir, "val")

        train_gen = train_datagen.flow_from_directory(
            train_dir,
            target_size=self.config.input_size,
            batch_size=self.config.batch_size,
            class_mode="categorical",
            shuffle=True,
        )

        val_gen = val_datagen.flow_from_directory(
            val_dir,
            target_size=self.config.input_size,
            batch_size=self.config.batch_size,
            class_mode="categorical",
            shuffle=False,
        )

        # Print class indices
        print(f"📂 Class indices: {train_gen.class_indices}")

        # Callbacks
        os.makedirs(os.path.join(self.config.output_dir, "logs"), exist_ok=True)
        callbacks = [
            EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
            ModelCheckpoint(
                filepath=os.path.join(self.config.output_dir, "beans_best.h5"),
                monitor="val_accuracy", save_best_only=True,
            ),
            ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=2, min_lr=1e-6),
            CSVLogger(os.path.join(self.config.output_dir, "logs", "training_log.csv")),
            TensorBoard(log_dir=os.path.join(self.config.output_dir, "logs", "tb")),
        ]

        # Train
        print(f"\n🚀 Starting training: {self.config.epochs} epochs, batch_size={self.config.batch_size}")
        self.history = self.model.fit(
            train_gen,
            epochs=self.config.epochs,
            validation_data=val_gen,
            callbacks=callbacks,
            class_weight=self._compute_class_weights(train_gen),
        )

        # Save final model
        os.makedirs(self.config.output_dir, exist_ok=True)
        model_path = os.path.join(self.config.output_dir, f"beans_v1.h5")
        self.model.save(model_path)
        print(f"💾 Model saved: {model_path}")

        return self.history.history if self.history else None

    def _compute_class_weights(self, data_generator) -> Dict[int, float]:
        """
        Compute class weights to handle imbalanced dataset.
        Defect classes (1-13) are typically 2-10% each vs 70%+ normal.
        """
        from collections import Counter
        import numpy as np

        labels = data_generator.classes
        counter = Counter(labels)
        total = len(labels)
        n_classes = len(counter)

        weights = {}
        for cls, count in counter.items():
            weights[cls] = total / (n_classes * count)

        # Boost minority defect classes (1-13) slightly
        for cls_idx in range(1, NUM_CLASSES):
            if cls_idx in weights:
                weights[cls_idx] *= 1.5  # Extra boost for rare defects

        return weights

    def evaluate(self, model_path: str, test_dir: str) -> Optional[ModelEvaluation]:
        """
        Evaluate trained model on held-out test set.

        Returns:
            ModelEvaluation with metrics
        """
        try:
            import tensorflow as tf
            from tensorflow import keras
            import time
        except ImportError:
            print("❌ TensorFlow not installed")
            return None

        # Load model
        model = keras.models.load_model(model_path)
        model_size_mb = os.path.getsize(model_path) / (1024 * 1024)

        # Test data generator
        test_datagen = keras.preprocessing.image.ImageDataGenerator(rescale=1.0 / 255.0)
        test_gen = test_datagen.flow_from_directory(
            test_dir,
            target_size=self.config.input_size,
            batch_size=self.config.batch_size,
            class_mode="categorical",
            shuffle=False,
        )

        # Evaluate
        start = time.time()
        results = model.evaluate(test_gen, verbose=1)
        inference_time = (time.time() - start) / len(test_gen) * 1000  # ms per batch

        loss, accuracy, precision, recall = results[:4]

        # Per-class metrics
        from sklearn.metrics import classification_report, confusion_matrix
        y_pred = model.predict(test_gen, verbose=0)
        y_pred_classes = np.argmax(y_pred, axis=1)
        y_true = test_gen.classes

        report = classification_report(
            y_true, y_pred_classes, labels=list(range(NUM_CLASSES)),
            target_names=BEAN_CLASSES, output_dict=True, zero_division=0
        )
        cm = confusion_matrix(y_true, y_pred_classes)

        per_class_prec = [report[cls]["precision"] for cls in BEAN_CLASSES]
        per_class_rec = [report[cls]["recall"] for cls in BEAN_CLASSES]

        # Compute macro F1
        f1_scores = [report[cls]["f1-score"] for cls in BEAN_CLASSES]
        macro_f1 = sum(f1_scores) / len(f1_scores)

        eval_result = ModelEvaluation(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=macro_f1,
            per_class_precision=per_class_prec,
            per_class_recall=per_class_rec,
            confusion_matrix=cm,
            total_params=model.count_params(),
            inference_time_ms=inference_time,
            model_size_mb=model_size_mb,
        )

        # Save evaluation report
        report_path = os.path.join(self.config.output_dir, "evaluation_report.json")
        with open(report_path, "w") as f:
            json.dump(eval_result.to_dict(), f, indent=2)

        print(f"\n📊 Evaluation Results:")
        print(f"   Accuracy:  {accuracy:.4f}")
        print(f"   Precision: {precision:.4f}")
        print(f"   Recall:    {recall:.4f}")
        print(f"   Macro F1:  {macro_f1:.4f}")
        print(f"   Model size: {model_size_mb:.1f} MB")
        print(f"   Inference:  {inference_time:.1f} ms/batch")
        print(f"\n📋 Per-class report:")
        for cls in BEAN_CLASSES:
            p = report[cls]["precision"]
            r = report[cls]["recall"]
            f1 = report[cls]["f1-score"]
            support = int(report[cls]["support"])
            print(f"   {cls:20s}  P={p:.3f}  R={r:.3f}  F1={f1:.3f}  [n={support}]")

        print(f"\n💾 Report saved: {report_path}")
        return eval_result

    def export_to_tflite(self, h5_path: str, quantize: bool = True) -> str:
        """
        Export trained model to TensorFlow Lite for edge deployment on Pi 4.

        Args:
            h5_path: Path to trained .h5 model
            quantize: Apply INT8 post-training quantization (recommended for Pi)

        Returns:
            Path to exported .tflite file
        """
        try:
            import tensorflow as tf
            from tensorflow import keras
        except ImportError:
            print("❌ TensorFlow not installed")
            return ""

        # Load model
        model = keras.models.load_model(h5_path)

        # Convert to TFLite
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]

        if quantize:
            # INT8 quantization with representative dataset
            # For production: provide a representative dataset (100-500 images)
            # converter.representative_dataset = lambda: self._representative_dataset()
            converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
            converter.inference_input_type = tf.uint8
            converter.inference_output_type = tf.uint8

        tflite_path = h5_path.replace(".h5", "_int8.tflite")
        tflite_model = converter.convert()

        with open(tflite_path, "wb") as f:
            f.write(tflite_model)

        size_mb = os.path.getsize(tflite_path) / (1024 * 1024)
        print(f"✅ TFLite model exported: {tflite_path} ({size_mb:.1f} MB)")
        return tflite_path

    def inference_benchmark(self, tflite_path: str, num_runs: int = 100) -> Dict:
        """
        Benchmark TFLite model inference speed on target hardware.

        Returns:
            Dict with mean/std latency and throughput
        """
        try:
            import tensorflow as tf
        except ImportError:
            print("❌ TensorFlow not installed")
            return {}

        # Load TFLite model
        interpreter = tf.lite.Interpreter(model_path=tflite_path)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # Generate random test input
        input_shape = input_details[0]["shape"]
        dummy_input = np.random.randint(0, 255, input_shape, dtype=np.uint8)

        # Warmup
        for _ in range(5):
            interpreter.set_tensor(input_details[0]["index"], dummy_input)
            interpreter.invoke()

        # Benchmark
        import time
        latencies = []
        for _ in range(num_runs):
            start = time.perf_counter()
            interpreter.set_tensor(input_details[0]["index"], dummy_input)
            interpreter.invoke()
            latencies.append((time.perf_counter() - start) * 1000)  # ms

        latencies = np.array(latencies)
        mean_lat = np.mean(latencies)
        std_lat = np.std(latencies)
        throughput = 1000.0 / mean_lat  # inferences per second

        print(f"\n⚡ TFLite Benchmark ({num_runs} runs):")
        print(f"   Mean latency: {mean_lat:.2f} ± {std_lat:.2f} ms")
        print(f"   Throughput:  {throughput:.1f} inferences/sec")
        print(f"   Min/Max:     {np.min(latencies):.2f} / {np.max(latencies):.2f} ms")

        return {
            "mean_latency_ms": round(mean_lat, 3),
            "std_latency_ms": round(std_lat, 3),
            "throughput_per_sec": round(throughput, 1),
            "min_ms": round(np.min(latencies), 3),
            "max_ms": round(np.max(latencies), 3),
        }


# ============================================================
# TFLite Inference Runner (for sorter/camera/defect_detector.py)
# ============================================================

class TFLiteDefectClassifier:
    """
    Lightweight TFLite inference runner for real-time defect classification.
    Integrates with sorter/camera/defect_detector.py

    Usage:
        classifier = TFLiteDefectClassifier("./models/beans_v1_int8.tflite")
        defect_class, confidence = classifier.classify(cv2_image)
    """

    def __init__(self, model_path: str, num_threads: int = 4):
        try:
            import tensorflow as tf
        except ImportError:
            raise RuntimeError("TensorFlow Lite requires: pip install tensorflow")

        self.interpreter = tf.lite.Interpreter(
            model_path=model_path,
            num_threads=num_threads,
        )
        self.interpreter.allocate_tensors()

        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

        self.input_shape = self.input_details[0]["shape"][1:3]  # (H, W)
        self.input_dtype = self.input_details[0]["dtype"]

        # Load class labels
        self.labels = BEAN_CLASSES

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for TFLite inference.

        Args:
            image: RGB image (H×W×3), uint8

        Returns:
            Preprocessed tensor (1×H×W×3), dtype matches model input
        """
        import cv2

        # Resize to model input size
        resized = cv2.resize(image, (self.input_shape[1], self.input_shape[0]))

        # Convert RGB→BGR if needed (TF uses RGB)
        # Already RGB from OpenCV capture, no conversion needed

        # Normalize to [0, 1] if float model
        if self.input_dtype == np.float32:
            resized = resized.astype(np.float32) / 255.0

        # Add batch dimension
        return np.expand_dims(resized, axis=0).astype(self.input_dtype)

    def classify(self, image: np.ndarray) -> Tuple[int, str, float]:
        """
        Classify a single bean image.

        Args:
            image: RGB image (H×W×3), uint8

        Returns:
            (class_id, class_name, confidence)
        """
        import cv2

        # Preprocess
        input_data = self.preprocess(image)

        # Run inference
        self.interpreter.set_tensor(self.input_details[0]["index"], input_data)
        self.interpreter.invoke()

        # Get output
        output_data = self.interpreter.get_tensor(self.output_details[0]["index"])
        probabilities = output_data[0]

        # Get top prediction
        class_id = int(np.argmax(probabilities))
        confidence = float(probabilities[class_id])
        class_name = self.labels[class_id]

        return class_id, class_name, confidence

    def classify_batch(self, images: List[np.ndarray]) -> List[Tuple[int, str, float]]:
        """
        Classify a batch of bean images.

        Args:
            images: List of RGB images

        Returns:
            List of (class_id, class_name, confidence)
        """
        return [self.classify(img) for img in images]


# ============================================================
# Main CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Coffee Bean Defect ML Pipeline")
    parser.add_argument("--mode", choices=["synthetic", "collect", "train", "evaluate", "export", "benchmark"],
                        default="synthetic", help="Pipeline mode")
    parser.add_argument("--generate", type=int, default=5000,
                        help="Number of synthetic images per class")
    parser.add_argument("--data", default="./data/beans", help="Data directory")
    parser.add_argument("--output", default="./models", help="Output directory")
    parser.add_argument("--model", help="Model path (.h5 or .tflite)")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--framework", default="tensorflow",
                        choices=["tensorflow", "pytorch"],
                        help="ML framework (tensorflow recommended for edge)")
    parser.add_argument("--duration", type=int, default=3600,
                        help="Collection duration in seconds (mode=collect)")
    parser.add_argument("--classes", type=int, default=NUM_CLASSES,
                        help="Number of defect classes")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    config = TrainingConfig(
        batch_size=args.batch_size,
        epochs=args.epochs,
        data_dir=args.data,
        output_dir=args.output,
    )

    if args.mode == "synthetic":
        print("=" * 60)
        print("🎨 SYNTHETIC DATA GENERATION (Pre-Hardware Development)")
        print("=" * 60)
        print(f"   Classes: {NUM_CLASSES}")
        print(f"   Images per class: {args.generate}")
        print(f"   Total images: {NUM_CLASSES * args.generate}")
        print(f"   Output: {args.data}/synthetic_beans_*/")
        print()
        print("⚠️  NOTE: Synthetic data is for development/pre-tuning only.")
        print("         Real training data collection required before production.")
        print()

        generator = SyntheticBeanGenerator(seed=args.seed)
        datasets = generator.generate_dataset(
            samples_per_class=args.generate,
            output_dir=args.data,
        )
        print("\n✅ Next steps:")
        print("   1. python -m sorter.camera.ml_pipeline --mode train --data ./data/beans")
        print("   2. python -m sorter.camera.ml_pipeline --mode evaluate --model ./models/beans_best.h5")
        print("   3. python -m sorter.camera.ml_pipeline --mode export --model ./models/beans_v1.h5")
        print("   4. After real data collection:")
        print("      python -m sorter.camera.ml_pipeline --mode collect --duration 3600")

    elif args.mode == "train":
        print(f"🚀 Training: {args.framework} ({args.epochs} epochs, batch={args.batch_size})")
        trainer = BeanDefectTrainer(config)
        trainer.build_model()
        history = trainer.train(data_dir=args.data)
        if history:
            print("✅ Training complete!")

    elif args.mode == "evaluate":
        if not args.model:
            print("❌ --model required for evaluation")
            return
        print(f"📊 Evaluating: {args.model}")
        trainer = BeanDefectTrainer(config)
        result = trainer.evaluate(model_path=args.model, test_dir=os.path.join(args.data, "test"))
        if result:
            print("✅ Evaluation complete!")

    elif args.mode == "export":
        if not args.model:
            print("❌ --model required for export")
            return
        print(f"📦 Exporting to TFLite: {args.model}")
        trainer = BeanDefectTrainer(config)
        tflite_path = trainer.export_to_tflite(args.model, quantize=True)
        if tflite_path:
            benchmark_result = trainer.inference_benchmark(tflite_path)
            print(f"✅ TFLite export complete!")

    elif args.mode == "benchmark":
        if not args.model:
            print("❌ --model (.tflite) required for benchmark")
            return
        print(f"⚡ Benchmarking: {args.model}")
        trainer = BeanDefectTrainer(config)
        trainer.inference_benchmark(args.model)

    elif args.mode == "collect":
        print(f"📸 Real data collection (session: {datetime.datetime.now().strftime('%Y%m%d_%H%M%S')})")
        print(f"   Duration: {args.duration}s | Output: {args.data}")
        print("   ⚠️  Requires hardware (dark_box_test_protocol.py)")
        print("   Run on Pi with: python -m sorter.camera.dark_box_test_protocol --collect")
        collector = BeanDataCollector(output_dir=args.data)
        print(f"   Session dir: {collector.session_dir}")


if __name__ == "__main__":
    main()
