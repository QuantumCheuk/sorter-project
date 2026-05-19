"""
defect_detector.py - 缺陷检测模块（ML模型 + 规则法）
HUSKY-SORTER-001 / 课题2: 颜色检测系统

v2 2026-05-17: Expanded to full 14-class per SPEC.md 2.2.4
  class 0: normal (合格通过)
  class 1-13: 缺陷类别（需剔除）

支持两种模式:
1. 规则检测（阈值法 + 按品种/处理法加载独立阈值）
2. ML模型检测（MobileNetV2 → TFLite 边缘部署）
"""

import cv2
import numpy as np
import pickle
import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

logger = logging.getLogger("defect_detector")


# ─────────────────────────────────────────────
# 14 类缺陷定义（SPEC.md 2.2.4）
# ─────────────────────────────────────────────
DEFECT_CLASS_14 = {
    0: "normal",           # 合格通过
    1: "mold",             # 发霉豆
    2: "fermented",        # 发酵过度
    3: "black",            # 黑豆
    4: "broken",           # 破碎豆
    5: "foreign",          # 异物（石头/树枝等）
    6: "underweight",      # 过轻
    7: "underdeveloped",   # 发育不全（quaker）
    8: "dead",             # 死豆
    9: "insect",           # 虫蛀
    10: "hollow",          # 空心
    11: "over_dry",        # 过干（含水率<8%）
    12: "over_wet",         # 过湿（含水率>14%）
    13: "pre_mold",        # 早期发霉（轻微霉斑）
}

# 严重等级: CRITICAL=任意面检出→立即剔除, HIGH=严重扣分, MEDIUM=阈值触发
DEFECT_SEVERITY = {
    "normal":           "OK",
    "mold":             "CRITICAL",
    "fermented":        "CRITICAL",
    "black":            "CRITICAL",
    "broken":           "HIGH",
    "foreign":          "CRITICAL",
    "underweight":      "MEDIUM",
    "underdeveloped":   "MEDIUM",
    "dead":             "HIGH",
    "insect":           "CRITICAL",
    "hollow":           "MEDIUM",
    "over_dry":         "MEDIUM",
    "over_wet":         "MEDIUM",
    "pre_mold":         "HIGH",
}

# 14 类默认规则阈值（按品种/处理法可覆盖）
DEFAULT_RULES = {
    "mold":             {"L_max": 40, "a_range": (-8, 2),  "b_min": 8},
    "fermented":        {"a_min": 10, "b_min": 18},
    "black":            {"L_max": 25},
    "broken":           {"area_ratio_max": 0.4, "solidity_max": 0.6},
    "foreign":          {"density_min": 1.5, "L_range": (0, 30)},
    "underweight":      {"weight_max_g": 0.08},
    "underdeveloped":   {"L_min": 75, "a_max": 2, "area_ratio_min": 0.6},
    "dead":             {"L_max": 30, "b_min": 15},
    "insect":           {"hole_area_min": 15, "hole_count_min": 1},
    "hollow":           {"density_max": 0.55, "weight_max_g": 0.06},
    "over_dry":         {"moisture_max_pct": 8.0},
    "over_wet":         {"moisture_min_pct": 14.0},
    "pre_mold":         {"L_max": 55, "spot_pct_min": 3},
}


class DefectDetector:
    """14 类缺陷检测器 — SPEC.md 2.2.4"""

    DEFECT_TYPES = DEFECT_CLASS_14
    NUM_CLASSES = 14

    def __init__(self, model_path: Optional[str] = None,
                 use_ml: bool = False,
                 rules: Optional[Dict] = None,
                 variety_config_path: Optional[str] = None):
        """
        Args:
            model_path: TFLite 或 pickle 模型路径
            use_ml: 使用 ML 模型（False=规则法）
            rules: 自定义规则阈值（覆盖默认值）
            variety_config_path: 品种/处理法独立标定 JSON
        """
        self.use_ml = use_ml
        self.model = None
        self.tflite_interpreter = None

        # Load ML model
        if use_ml and model_path:
            self._load_model(model_path)

        # Rule-based thresholds: start with defaults, override if provided
        self.rules = dict(DEFAULT_RULES)
        if rules:
            self.rules.update(rules)

        # Per-variety calibration
        self.variety_thresholds: Dict[str, Dict] = {}
        if variety_config_path and os.path.exists(variety_config_path):
            with open(variety_config_path) as f:
                self.variety_thresholds = json.load(f)
            logger.info(f"Loaded {len(self.variety_thresholds)} variety configs")

        # Current active variety (set by SorterController)
        self.current_variety: Optional[str] = None

    def set_variety(self, variety_key: str):
        """
        切换品种/处理法标定阈值

        variety_key: e.g. "ethiopian_washed", "geisha_natural"
        """
        self.current_variety = variety_key
        if variety_key in self.variety_thresholds:
            cfg = self.variety_thresholds[variety_key]
            self.rules.update(cfg.get("rules", {}))
            logger.info(f"Thresholds updated for variety: {variety_key}")
        else:
            logger.warning(f"No variety config for '{variety_key}', using defaults")

    def _load_model(self, model_path: str):
        """加载 TFLite 或 pickle 模型"""
        if model_path.endswith(".tflite"):
            try:
                import tflite_runtime.interpreter as tflite
                self.tflite_interpreter = tflite.Interpreter(model_path=model_path)
                self.tflite_interpreter.allocate_tensors()
                logger.info(f"Loaded TFLite model: {model_path}")
            except ImportError:
                try:
                    import tensorflow as tf
                    self.tflite_interpreter = tf.lite.Interpreter(model_path=model_path)
                    self.tflite_interpreter.allocate_tensors()
                    logger.info(f"Loaded TFLite model (tensorflow): {model_path}")
                except ImportError:
                    logger.error("Neither tflite_runtime nor tensorflow available")
        elif os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"Loaded pickle model: {model_path}")

    def detect(self, top_image: np.ndarray, top_mask: np.ndarray,
               bottom_image: Optional[np.ndarray] = None,
               bottom_mask: Optional[np.ndarray] = None,
               sensor_data: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        双摄像头缺陷检测 — SPEC 2.2.3

        任意一面检测到缺陷 → is_defective = True（OR 逻辑）

        Args:
            top_image: 正面 BGR 图像
            top_mask: 正面豆子掩膜
            bottom_image: 背面 BGR 图像（可选）
            bottom_mask: 背面豆子掩膜（可选）
            sensor_data: 其他传感器数据（weight_g, density, moisture_pct 等）

        Returns:
            {
                "is_defective": bool,
                "defect_type": str,           # 最高置信度的缺陷名
                "top_defect": str,            # 正面检测结果
                "bottom_defect": str,         # 背面检测结果
                "defect_score": float,
                "confidence": float,
                "recommendation": "reject" | "accept",
            }
        """
        # Detect top side
        top_result = self._detect_single_side(top_image, top_mask, sensor_data)

        # Detect bottom side
        bottom_result = {"defect_type": "normal", "defect_score": 0.0}
        if bottom_image is not None and bottom_mask is not None:
            bottom_result = self._detect_single_side(
                bottom_image, bottom_mask, sensor_data
            )

        # OR logic: either side defective → reject
        top_defective = top_result["defect_type"] != "normal"
        bottom_defective = bottom_result["defect_type"] != "normal"
        is_defective = top_defective or bottom_defective

        # Pick the highest-severity defect
        if is_defective:
            all_defects = []
            if top_defective:
                all_defects.append((
                    top_result["defect_type"],
                    top_result["defect_score"],
                    DEFECT_SEVERITY.get(top_result["defect_type"], "MEDIUM"),
                ))
            if bottom_defective:
                all_defects.append((
                    bottom_result["defect_type"],
                    bottom_result["defect_score"],
                    DEFECT_SEVERITY.get(bottom_result["defect_type"], "MEDIUM"),
                ))
            # Sort by severity (CRITICAL > HIGH > MEDIUM) then score
            severity_order = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "OK": 0}
            all_defects.sort(
                key=lambda x: (severity_order.get(x[2], 0), x[1]), reverse=True
            )
            primary_defect = all_defects[0]
        else:
            primary_defect = ("normal", 0.0, "OK")

        return {
            "is_defective": is_defective,
            "defect_type": primary_defect[0],
            "top_defect": top_result["defect_type"],
            "bottom_defect": bottom_result["defect_type"],
            "defect_score": primary_defect[1],
            "severity": primary_defect[2],
            "confidence": primary_defect[1],
            "recommendation": "reject" if is_defective else "accept",
        }

    def _detect_single_side(self, image: np.ndarray, mask: np.ndarray,
                            sensor_data: Optional[Dict] = None) -> Dict:
        """单面检测（规则法 或 ML）"""
        if self.use_ml and (self.model or self.tflite_interpreter):
            return self._detect_ml(image, mask)
        return self._detect_rule(image, mask, sensor_data)

    def _detect_rule(self, image: np.ndarray, mask: np.ndarray,
                     sensor_data: Optional[Dict] = None) -> Dict:
        """14 类规则检测"""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        L_bean = L[mask > 0]
        a_bean = a[mask > 0]
        b_bean = b[mask > 0]

        if len(L_bean) == 0:
            return {"defect_type": "normal", "defect_score": 0.0}

        avg_L = np.mean(L_bean) * 100 / 255
        avg_a = np.mean(a_bean) - 128
        avg_b = np.mean(b_bean) - 128

        defects: List[Tuple[str, float]] = []
        rules = self.rules

        # Color-based defects
        r = rules.get("mold", {})
        if avg_L <= r.get("L_max", 40) and avg_b >= r.get("b_min", 8):
            defects.append(("mold", 0.85))

        r = rules.get("fermented", {})
        if avg_a >= r.get("a_min", 10) and avg_b >= r.get("b_min", 18):
            defects.append(("fermented", 0.8))

        r = rules.get("black", {})
        if avg_L <= r.get("L_max", 25):
            defects.append(("black", 0.95))

        r = rules.get("underdeveloped", {})
        if avg_L >= r.get("L_min", 75) and avg_a <= r.get("a_max", 2):
            defects.append(("underdeveloped", 0.7))

        r = rules.get("dead", {})
        if avg_L <= r.get("L_max", 30) and avg_b >= r.get("b_min", 15):
            defects.append(("dead", 0.8))

        r = rules.get("pre_mold", {})
        spot_pct = np.sum(L_bean < 55 * 255 / 100) / max(1, len(L_bean)) * 100
        if avg_L <= r.get("L_max", 55) and spot_pct >= r.get("spot_pct_min", 3):
            defects.append(("pre_mold", 0.6))

        # Shape-based
        r = rules.get("broken", {})
        bean_area = np.sum(mask > 0)
        expected_area = image.shape[0] * image.shape[1] * 0.05  # ~5% of frame
        if bean_area < expected_area * r.get("area_ratio_max", 0.4):
            defects.append(("broken", 0.7))

        # Sensor-based (weight / density / moisture)
        if sensor_data:
            r = rules.get("underweight", {})
            if sensor_data.get("weight_g", 1.0) <= r.get("weight_max_g", 0.08):
                defects.append(("underweight", 0.65))

            r = rules.get("hollow", {})
            if (sensor_data.get("density", 1.0) <= r.get("density_max", 0.55)
                    and sensor_data.get("weight_g", 1.0) <= r.get("weight_max_g", 0.06)):
                defects.append(("hollow", 0.6))

            r = rules.get("over_dry", {})
            if sensor_data.get("moisture_pct", 11.0) <= r.get("moisture_max_pct", 8.0):
                defects.append(("over_dry", 0.5))

            r = rules.get("over_wet", {})
            if sensor_data.get("moisture_pct", 11.0) >= r.get("moisture_min_pct", 14.0):
                defects.append(("over_wet", 0.5))

            r = rules.get("foreign", {})
            if sensor_data.get("density", 0.6) >= r.get("density_min", 1.5):
                defects.append(("foreign", 0.9))

        # Insect: hole detection
        r = rules.get("insect", {})
        dark_mask = (L[mask > 0] * 100 / 255 < 20).astype(np.uint8)
        hole_count = cv2.connectedComponents(dark_mask.reshape(L.shape)[mask > 0].astype(np.uint8))[0] if len(dark_mask) > 0 else 0
        if hole_count >= r.get("hole_count_min", 1):
            defects.append(("insect", 0.75))

        if defects:
            defect_type, score = max(defects, key=lambda x: x[1])
            return {"defect_type": defect_type, "defect_score": score}
        return {"defect_type": "normal", "defect_score": 0.0}

    def _detect_ml(self, image: np.ndarray, mask: np.ndarray) -> Dict:
        """ML 模型检测 (TFLite 或 sklearn)"""
        features = self.extract_features(image, mask)

        if self.tflite_interpreter:
            # TFLite inference
            input_details = self.tflite_interpreter.get_input_details()
            output_details = self.tflite_interpreter.get_output_details()
            input_shape = input_details[0]["shape"]

            if len(features.shape) == 1:
                features = features.reshape(1, -1)
            # Resize to match input if needed
            input_data = features[:1, :input_shape[1]].astype(np.float32)
            self.tflite_interpreter.set_tensor(input_details[0]["index"], input_data)
            self.tflite_interpreter.invoke()
            output = self.tflite_interpreter.get_tensor(output_details[0]["index"])
            defect_id = int(np.argmax(output))
            confidence = float(output[0][defect_id])
        elif self.model:
            prediction = self.model.predict(features.reshape(1, -1))[0]
            probs = self.model.predict_proba(features.reshape(1, -1))[0]
            defect_id = int(prediction)
            confidence = float(probs[defect_id])
        else:
            return {"defect_type": "normal", "defect_score": 0.0}

        defect_type = DEFECT_CLASS_14.get(defect_id, "unknown")
        return {"defect_type": defect_type, "defect_score": confidence}

    def extract_features(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """提取特征向量（同原实现，兼容 ML 模型）"""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        L_bean = L[mask > 0].astype(np.float32)
        a_bean = a[mask > 0].astype(np.float32)
        b_bean = b[mask > 0].astype(np.float32)

        features = [
            np.mean(L_bean) * 100 / 255,
            np.mean(a_bean) - 128,
            np.mean(b_bean) - 128,
            np.std(L_bean) * 100 / 255,
            np.std(a_bean),
            np.std(b_bean),
        ]

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        H, S, V = cv2.split(hsv)
        features.extend([
            np.mean(H[mask > 0]) * 2,
            np.mean(S[mask > 0]) * 100 / 255,
            np.mean(V[mask > 0]) * 100 / 255,
        ])

        hist_L = cv2.calcHist([L], [0], mask, [32], [0, 256])
        hist_L = hist_L.flatten() / max(1, hist_L.sum())
        features.append(np.sum(hist_L > 0.1) / 32)

        dark_pct = np.sum(L_bean < 40 * 255 / 100) / max(1, len(L_bean))
        features.append(dark_pct)

        return np.array(features, dtype=np.float32)

    def train_svm(self, X_train, y_train, model_path="models/defect_svm.pkl"):
        """训练 SVM 模型（兼容 14 类）"""
        from sklearn.svm import SVC
        from sklearn.preprocessing import StandardScaler

        X = np.array(X_train)
        y = np.array(y_train)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        svm = SVC(kernel='rbf', probability=True, class_weight='balanced')
        svm.fit(X_scaled, y)

        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        with open(model_path, 'wb') as f:
            pickle.dump({"model": svm, "scaler": scaler}, f)
        logger.info(f"14-class SVM saved to {model_path}")


if __name__ == "__main__":
    detector = DefectDetector()
    print(f"Defect classes: {len(DEFECT_CLASS_14)}")
    for k, v in DEFECT_CLASS_14.items():
        print(f"  {k}: {v} ({DEFECT_SEVERITY[v]})")

    test_img = np.random.randint(40, 80, (480, 640, 3), dtype=np.uint8)
    mask = np.zeros((480, 640), dtype=np.uint8)
    mask[100:400, 200:500] = 255
    result = detector._detect_rule(test_img, mask)
    print(f"\nRule detection: {result}")

