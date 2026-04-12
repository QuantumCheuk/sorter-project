"""
defect_detector.py - 缺陷检测模块（ML模型）
HUSKY-SORTER-001 / 课题2: 颜色检测系统

支持两种模式：
1. 规则检测（阈值法）- 快速，适合实时
2. ML模型检测（SVM/MLP）- 精度高，需训练

缺陷类型：
- 漂白豆 (Bleached)
- 发霉豆 (Moldy)
- 发酵过度 (Fermented)
- 破碎豆 (Broken)
- 虫蛀豆 (Insect-damaged)
"""

import cv2
import numpy as np
import pickle
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class DefectDetector:
    """缺陷检测器"""

    # 缺陷类型ID
    DEFECT_TYPES = {
        0: "normal",
        1: "bleached",
        2: "moldy",
        3: "fermented",
        4: "broken",
        5: "insect_damaged"
    }

    def __init__(self, model_path: Optional[str] = None, use_ml: bool = False):
        """
        Args:
            model_path: 训练好的模型文件路径
            use_ml: 是否使用ML模型（False=规则检测）
        """
        self.use_ml = use_ml
        self.model = None

        if use_ml and model_path and os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            print(f"[OK] Loaded ML model: {model_path}")
        else:
            print("[INFO] Using rule-based defect detection")

        # 备用：规则阈值
        self.rules = {
            "bleached": {"L_min": 70, "a_max": 3, "b_max": 10},
            "moldy": {"L_max": 40, "a_min": -3, "b_min": 8},
            "fermented": {"a_min": 10, "b_min": 18},
            "broken": {"area_ratio_max": 0.3, "aspect_min": 0.4},
            "insect_damaged": {"hole_area_min": 20, "hole_count_min": 1},
        }

    def extract_features(self, image: np.ndarray, bean_mask: np.ndarray) -> np.ndarray:
        """
        提取豆子特征向量（用于ML模型）

        Returns:
            特征向量: [L_mean, a_mean, b_mean, L_std, a_std, b_std,
                       hue_mean, sat_mean, val_mean, 颜色均匀度, ...]
        """
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        # 颜色特征
        L_bean = L[bean_mask > 0].astype(np.float32)
        a_bean = a[bean_mask > 0].astype(np.float32)
        b_bean = b[bean_mask > 0].astype(np.float32)

        features = []

        # L*a*b* 均值和标准差
        features.extend([
            np.mean(L_bean) * 100 / 255,
            np.mean(a_bean) - 128,
            np.mean(b_bean) - 128,
            np.std(L_bean) * 100 / 255,
            np.std(a_bean),
            np.std(b_bean),
        ])

        # HSV 特征
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        H, S, V = cv2.split(hsv)
        H_bean = H[bean_mask > 0].astype(np.float32)
        S_bean = S[bean_mask > 0].astype(np.float32)
        V_bean = V[bean_mask > 0].astype(np.float32)

        features.extend([
            np.mean(H_bean) * 2,  # 转换到 [0, 360]
            np.mean(S_bean) * 100 / 255,
            np.mean(V_bean) * 100 / 255,
        ])

        # 颜色均匀度（直方图峰值比例）
        hist_L = cv2.calcHist([L], [0], bean_mask, [32], [0, 256])
        hist_L = hist_L.flatten() / max(1, hist_L.sum())
        peaks = np.sum(hist_L > 0.1)  # 超过10%的bin数量
        features.append(peaks / 32)  # 均匀度指标

        # 斑点特征（检测发霉/虫蛀）
        blob_mask = self._detect_dark_spots(bean_mask, L_bean)
        features.append(np.sum(blob_mask) / max(1, len(L_bean)))

        return np.array(features, dtype=np.float32)

    def _detect_dark_spots(self, mask: np.ndarray, L_values: np.ndarray) -> np.ndarray:
        """检测暗斑（可能是发霉或虫蛀）"""
        # 简化：假设暗斑是L值低于40的区域
        # 实际需要更复杂的区域生长算法
        return (L_values * 100 / 255 < 40).astype(np.uint8)

    def detect(self, image: np.ndarray, bean_mask: np.ndarray) -> Dict:
        """
        检测缺陷

        Returns:
            {
                "defect_type": str,  # "normal" 或具体缺陷类型
                "defect_score": float,  # 缺陷置信度 [0, 1]
                "is_defective": bool,
                "recommendation": str  # "accept" / "reject"
            }
        """
        if self.use_ml and self.model is not None:
            return self._detect_ml(image, bean_mask)
        else:
            return self._detect_rule(image, bean_mask)

    def _detect_rule(self, image: np.ndarray, bean_mask: np.ndarray) -> Dict:
        """基于规则的缺陷检测"""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        L_bean = L[bean_mask > 0]
        a_bean = a[bean_mask > 0]
        b_bean = b[bean_mask > 0]

        if len(L_bean) == 0:
            return {"defect_type": "normal", "defect_score": 0, "is_defective": False, "recommendation": "accept"}

        avg_L = np.mean(L_bean) * 100 / 255
        avg_a = np.mean(a_bean) - 128
        avg_b = np.mean(b_bean) - 128

        # 逐规则检测
        defects = []

        # 漂白豆
        if (avg_L >= self.rules["bleached"]["L_min"] and
                abs(avg_a) <= self.rules["bleached"]["a_max"] and
                abs(avg_b) <= self.rules["bleached"]["b_max"]):
            defects.append(("bleached", 0.9))

        # 发霉豆
        if (avg_L <= self.rules["moldy"]["L_max"] and
                avg_a <= self.rules["moldy"]["a_min"] and
                avg_b >= self.rules["moldy"]["b_min"]):
            defects.append(("moldy", 0.85))

        # 发酵过度
        if (avg_a >= self.rules["fermented"]["a_min"] and
                avg_b >= self.rules["fermented"]["b_min"]):
            defects.append(("fermented", 0.8))

        # 破碎豆（需形状分析，这里简化）
        bean_area = np.sum(bean_mask > 0)
        # 假设分辨率已知，估算面积
        expected_area = 10000  # 估算值
        if bean_area < expected_area * self.rules["broken"]["area_ratio_max"]:
            defects.append(("broken", 0.7))

        if defects:
            defect_type, confidence = max(defects, key=lambda x: x[1])
            return {
                "defect_type": defect_type,
                "defect_score": confidence,
                "is_defective": True,
                "recommendation": "reject"
            }
        else:
            return {
                "defect_type": "normal",
                "defect_score": 0.1,
                "is_defective": False,
                "recommendation": "accept"
            }

    def _detect_ml(self, image: np.ndarray, bean_mask: np.ndarray) -> Dict:
        """基于ML模型的缺陷检测"""
        features = self.extract_features(image, bean_mask).reshape(1, -1)

        # 预测
        prediction = self.model.predict(features)[0]
        probabilities = self.model.predict_proba(features)[0]

        defect_id = int(prediction)
        confidence = float(probabilities[defect_id])

        defect_type = self.DEFECT_TYPES.get(defect_id, "unknown")

        return {
            "defect_type": defect_type,
            "defect_score": confidence,
            "is_defective": defect_id != 0,
            "recommendation": "reject" if defect_id != 0 else "accept"
        }

    def train_svm(self, X_train: List[np.ndarray], y_train: List[int],
                  model_path: str = "models/defect_svm.pkl") -> None:
        """
        训练SVM缺陷分类模型

        Args:
            X_train: 特征向量列表
            y_train: 标签列表 (0=normal, 1=bleached, ...)
            model_path: 模型保存路径
        """
        from sklearn.svm import SVC
        from sklearn.preprocessing import StandardScaler

        X = np.array(X_train)
        y = np.array(y_train)

        # 标准化
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # 训练SVM（RBF核）
        svm = SVC(kernel='rbf', probability=True, class_weight='balanced')
        svm.fit(X_scaled, y)

        # 保存模型+scaler
        model_data = {"model": svm, "scaler": scaler}
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)

        print(f"[OK] Model saved to {model_path}")


if __name__ == "__main__":
    # 测试
    detector = DefectDetector()

    # 模拟图像
    test_img = np.random.randint(40, 80, (480, 640, 3), dtype=np.uint8)
    mask = np.zeros((480, 640), dtype=np.uint8)
    mask[100:400, 200:500] = 255

    result = detector.detect(test_img, mask)
    print(f"Result: {result}")
