"""
color_analyzer.py - 颜色分析模块
HUSKY-SORTER-001 / 课题2: 颜色检测系统

核心算法：
1. L*a*b* 色彩空间分析（更符合人眼感知）
2. 颜色直方图特征提取
3. 缺陷检测（漂白/发霉/发酵过度/破碎）
4. 按品种+处理法独立评分
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ColorResult:
    """颜色分析结果"""
    color_score: float          # 综合颜色评分 0-100
    avg_L: float               # 亮度
    avg_a: float               # 红绿轴
    avg_b: float               # 黄蓝轴
    hist_L: np.ndarray         # L* 直方图
    hist_a: np.ndarray          # a* 直方图
    hist_b: np.ndarray          # b* 直方图
    defect_flags: Dict[str, bool]  # 缺陷标记
    defect_count: int           # 缺陷数量
    defect_rate_pct: float      # 缺陷率%


class ColorAnalyzer:
    """生豆颜色分析器"""

    # 缺陷颜色阈值（基于 L*a*b* 色彩空间）
    # 数值基于咖啡生豆常见缺陷特征
    DEFECT_THRESHOLDS = {
        # 漂白豆：L值极高，a*b接近0
        "bleached": {"L_min": 75, "a_max": 3.0, "b_max": 8.0},

        # 发霉豆：绿色偏暗，有灰绿色调
        "moldy": {"L_max": 45, "a_min": -5.0, "b_min": 5.0},

        # 发酵过度：偏红棕色，a值高
        "fermented": {"a_min": 8.0, "b_min": 15.0},

        # 破碎豆：形状不规则，面积小
        "broken": {"area_min": 50, "aspect_ratio_max": 0.4},
    }

    def __init__(self, variety: str = "default", process: str = "default"):
        """
        Args:
            variety: 品种 (e.g., "Heirloom", "Bourbon")
            process: 处理法 (e.g., "水洗", "日晒", "蜜处理")
        """
        self.variety = variety
        self.process = process

        # 品种/处理法对应的参考颜色范围
        # 这些值需要用真实样本标定
        self.reference_ranges = self._load_reference(variety, process)

    def _load_reference(self, variety: str, process: str) -> Dict:
        """
        加载品种+处理法对应的参考颜色范围
        真实场景：从数据库或文件加载已标定的参考值
        """
        # 默认参考范围（需要根据真实样本更新）
        # L* ∈ [0, 100], a* ∈ [-128, 127], b* ∈ [-128, 127]
        references = {
            "default": {"L": (30, 55), "a": (-2, 8), "b": (10, 30)},
            # 埃塞俄比亚 耶加雪菲 水洗
            "Heirloom_水洗": {"L": (35, 50), "a": (-1, 5), "b": (12, 25)},
            # 埃塞俄比亚 瑰夏 日晒
            "Geisha_日晒": {"L": (38, 55), "a": (-2, 6), "b": (15, 30)},
            # 哥伦比亚 水洗
            "Bourbon_水洗": {"L": (32, 48), "a": (0, 6), "b": (10, 22)},
            # 巴西 日晒
            "Bourbon_日晒": {"L": (40, 58), "a": (1, 8), "b": (15, 32)},
        }

        key = f"{variety}_{process}"
        return references.get(key, references["default"])

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        预处理：提取豆子区域，去除背景
        使用颜色分割 + 形态学操作
        """
        # 转换到 LAB 色彩空间
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        # 简单背景分离：假设背景偏白或偏黑
        # 使用Otsu's二值化
        _, thresh = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 形态学去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 找最大轮廓（豆子区域）
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return mask

        # 取最大轮廓作为豆子掩码
        largest = max(contours, key=cv2.contourArea)
        bean_mask = np.zeros_like(mask)
        cv2.drawContours(bean_mask, [largest], -1, 255, -1)

        return bean_mask

    def analyze(self, image: np.ndarray, mask: Optional[np.ndarray] = None) -> ColorResult:
        """
        分析单帧图像中的豆子颜色

        Args:
            image: BGR 图像
            mask: 豆子区域掩码（None时自动计算）

        Returns:
            ColorResult: 颜色分析结果
        """
        # 预处理
        if mask is None:
            mask = self.preprocess(image)

        # 转换到 L*a*b* 色彩空间
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        # 只分析豆子区域
        L_bean = L[mask > 0].astype(np.float32)
        a_bean = a[mask > 0].astype(np.float32)
        b_bean = b[mask > 0].astype(np.float32)

        if len(L_bean) == 0:
            return ColorResult(
                color_score=0, avg_L=0, avg_a=0, avg_b=0,
                hist_L=np.zeros(256), hist_a=np.zeros(256), hist_b=np.zeros(256),
                defect_flags={}, defect_count=0, defect_rate_pct=0
            )

        # 计算平均值
        avg_L = np.mean(L_bean) * 100 / 255  # 转换到 L* ∈ [0,100]
        avg_a = np.mean(a_bean) - 128         # 转换到 a* ∈ [-128, 127]
        avg_b = np.mean(b_bean) - 128         # 转换到 b* ∈ [-128, 127]

        # 计算直方图
        hist_L = cv2.calcHist([L], [0], mask, [256], [0, 256]).flatten()
        hist_a = cv2.calcHist([a], [0], mask, [256], [0, 256]).flatten()
        hist_b = cv2.calcHist([b], [0], mask, [256], [0, 256]).flatten()

        # 缺陷检测
        defect_flags = self._detect_defects(L_bean, a_bean, b_bean, mask)

        # 计算颜色评分（相对于参考范围）
        color_score = self._calculate_score(avg_L, avg_a, avg_b)

        # 估算缺陷数量（按面积比例）
        defect_count = self._estimate_defect_count(image, mask, defect_flags)
        defect_rate_pct = defect_count / max(1, len(L_bean)) * 100

        return ColorResult(
            color_score=color_score,
            avg_L=avg_L, avg_a=avg_a, avg_b=avg_b,
            hist_L=hist_L, hist_a=hist_a, hist_b=hist_b,
            defect_flags=defect_flags,
            defect_count=defect_count,
            defect_rate_pct=defect_rate_pct
        )

    def _detect_defects(self, L: np.ndarray, a: np.ndarray, b: np.ndarray,
                        mask: np.ndarray) -> Dict[str, bool]:
        """检测各类缺陷"""
        flags = {}

        # 漂白豆检测
        avg_L_norm = np.mean(L) * 100 / 255
        avg_a_norm = np.mean(a) - 128
        avg_b_norm = np.mean(b) - 128
        th = self.DEFECT_THRESHOLDS["bleached"]
        flags["bleached"] = (avg_L_norm >= th["L_min"] and
                             abs(avg_a_norm) <= th["a_max"] and
                             abs(avg_b_norm) <= th["b_max"])

        # 发霉豆检测
        th = self.DEFECT_THRESHOLDS["moldy"]
        flags["moldy"] = (avg_L_norm <= th["L_max"] and
                          avg_a_norm <= th["a_min"] and
                          avg_b_norm >= th["b_min"])

        # 发酵过度检测
        th = self.DEFECT_THRESHOLDS["fermented"]
        flags["fermented"] = (avg_a_norm >= th["a_min"] and
                              avg_b_norm >= th["b_min"])

        # 破碎豆检测（形状分析）
        # 需要在 analyze() 中传入轮廓信息，这里简化为占位
        flags["broken"] = False

        return flags

    def _estimate_defect_count(self, image: np.ndarray, mask: np.ndarray,
                               defect_flags: Dict[str, bool]) -> int:
        """估算缺陷豆数量（基于颜色异常区域面积）"""
        if not any(defect_flags.values()):
            return 0

        # 简单估算：异常颜色区域占总面积的比例
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)

        # 检测漂白区域
        bleached_mask = ((L.astype(np.float32) * 100 / 255 >= 75) &
                         (np.abs(a.astype(np.float32) - 128) <= 10))
        bleached_count = np.sum(bleached_mask & (mask > 0))

        # 检测发霉区域（暗绿色）
        moldy_mask = ((L.astype(np.float32) * 100 / 255 <= 45) &
                      ((a.astype(np.float32) - 128) <= -5))
        moldy_count = np.sum(moldy_mask & (mask > 0))

        total_bean_pixels = np.sum(mask > 0)
        if total_bean_pixels == 0:
            return 0

        # 假设平均一颗豆子约 10000 像素（根据分辨率估算）
        avg_bean_pixels = 10000
        estimated_defects = int((bleached_count + moldy_count) / avg_bean_pixels)

        return max(estimated_defects, 1 if any(defect_flags.values()) else 0)

    def _calculate_score(self, L: float, a: float, b: float) -> float:
        """
        计算颜色评分（0-100）
        基于豆子颜色与参考范围的匹配程度
        """
        ref = self.reference_ranges

        # 计算各维度偏离度
        L_score = self._range_score(L, ref["L"])
        a_score = self._range_score(a, ref["a"])
        b_score = self._range_score(b, ref["b"])

        # 加权平均（L值最重要）
        total_score = L_score * 0.5 + a_score * 0.25 + b_score * 0.25

        return round(min(100, max(0, total_score)), 1)

    def _range_score(self, value: float, valid_range: Tuple[float, float]) -> float:
        """计算值在有效范围内的得分"""
        v_min, v_max = valid_range
        if v_min <= value <= v_max:
            return 100

        # 线性衰减
        if value < v_min:
            dist = v_min - value
        else:
            dist = value - v_max

        # 假设超出范围 20 个单位得分为 0
        score = max(0, 100 - dist * 5)
        return score


def calibrate_reference(variety: str, process: str,
                         sample_images: List[np.ndarray],
                         manual_labels: List[Dict]) -> Dict:
    """
    标定品种+处理法的参考颜色范围

    Args:
        variety: 品种
        process: 处理法
        sample_images: 样本图像列表
        manual_labels: 每张图的标签，包含合格/不合格及原因

    Returns:
        参考范围字典
    """
    # 收集所有合格样本的颜色统计
    qualified_L, qualified_a, qualified_b = [], [], []

    for img, label in zip(sample_images, manual_labels):
        analyzer = ColorAnalyzer(variety, process)
        result = analyzer.analyze(img)

        if label.get("qualified", False):
            qualified_L.append(result.avg_L)
            qualified_a.append(result.avg_a)
            qualified_b.append(result.avg_b)

    if not qualified_L:
        return {"L": (35, 50), "a": (-2, 6), "b": (12, 25)}

    return {
        "L": (np.percentile(qualified_L, 5), np.percentile(qualified_L, 95)),
        "a": (np.percentile(qualified_a, 5), np.percentile(qualified_a, 95)),
        "b": (np.percentile(qualified_b, 5), np.percentile(qualified_b, 95)),
    }


if __name__ == "__main__":
    # 简单测试
    import sys

    # 模拟生成测试图像
    test_img = np.random.randint(50, 100, (480, 640, 3), dtype=np.uint8)

    analyzer = ColorAnalyzer("Heirloom", "水洗")
    result = analyzer.analyze(test_img)

    print(f"Color Score: {result.color_score}")
    print(f"L*a*b*: ({result.avg_L:.1f}, {result.avg_a:.1f}, {result.avg_b:.1f})")
    print(f"Defects: {result.defect_flags}")
