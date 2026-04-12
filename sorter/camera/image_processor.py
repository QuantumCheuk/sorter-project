"""
image_processor.py - 改进的图像预处理模块
HUSKY-SORTER-001 / 课题2 Day 2

改进点：
1. 多策略背景分离（融合多种色彩空间）
2. 自适应阈值（不使用固定Otsu）
3. 豆子轮廓精确定位
4. 尺寸/形状特征提取
5. 批次图像统计分析
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class BeanRegion:
    """单个豆子区域"""
    contour: np.ndarray           # 轮廓点
    mask: np.ndarray              # 掩码
    bounding_box: Tuple[int, int, int, int]  # x, y, w, h
    centroid: Tuple[float, float]  # 重心
    area_pixels: int              # 面积（像素）
    aspect_ratio: float           # 长宽比
    solidity: float               # 紧凑度 (area / convex_area)
    equidiameter: float           # 等效直径（像素）


class ImageProcessor:
    """
    改进的图像预处理器
    专为咖啡生豆的视觉特征设计（近似椭圆形，绿色/蓝绿色调）
    """

    # 豆子的目标颜色范围（HSV空间，经验值）
    BEAN_HSV_RANGE = {
        "lower": np.array([25, 20, 30]),    # 低饱和度暗色
        "upper": np.array([95, 130, 200]),  # 偏高亮度
    }

    def __init__(self, min_bean_area: int = 2000, max_bean_area: int = 80000):
        """
        Args:
            min_bean_area: 最小豆子面积（像素）
            max_bean_area: 最大豆子面积（像素）
        """
        self.min_bean_area = min_bean_area
        self.max_bean_area = max_bean_area

    def preprocess(self, image: np.ndarray, method: str = "adaptive") -> Tuple[np.ndarray, List[BeanRegion]]:
        """
        预处理主函数：背景分离 + 豆子检测

        Args:
            image: BGR 原始图像
            method: "otsu" | "adaptive" | "hsv" | "combined"

        Returns:
            (background_mask, bean_regions)
            background_mask: 背景掩码（255=背景，0=豆子）
            bean_regions: 检测到的豆子区域列表
        """
        if method == "otsu":
            mask = self._bg_separate_otsu(image)
        elif method == "adaptive":
            mask = self._bg_separate_adaptive(image)
        elif method == "hsv":
            mask = self._bg_separate_hsv(image)
        elif method == "combined":
            mask = self._bg_separate_combined(image)
        else:
            mask = self._bg_separate_combined(image)

        # 形态学清理
        mask = self._morphology_cleanup(mask)

        # 提取豆子区域
        bean_regions = self._extract_bean_regions(mask)

        # 过滤面积范围
        bean_regions = [b for b in bean_regions
                        if self.min_bean_area <= b.area_pixels <= self.max_bean_area]

        return mask, bean_regions

    def _bg_separate_otsu(self, image: np.ndarray) -> np.ndarray:
        """Otsu二值化（基础方法）"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return mask

    def _bg_separate_adaptive(self, image: np.ndarray) -> np.ndarray:
        """自适应阈值（对光照不均匀效果好）"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (9, 9), 2)
        mask = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, 21, 5)
        return mask

    def _bg_separate_hsv(self, image: np.ndarray) -> np.ndarray:
        """HSV色彩空间分割（利用豆子的颜色特征）"""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # 绿色豆子在HSV中的范围
        lower_green = np.array([25, 20, 30])
        upper_green = np.array([95, 140, 210])

        mask = cv2.inRange(hsv, lower_green, upper_green)

        # 反转：豆子=255
        mask = cv2.bitwise_not(mask)

        return mask

    def _bg_separate_combined(self, image: np.ndarray) -> np.ndarray:
        """
        组合策略：融合多色彩空间信息
        这是最鲁棒的方法
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 策略1：HSV 绿色范围
        lower_hsv = np.array([20, 20, 25])
        upper_hsv = np.array([100, 145, 220])
        mask_hsv = cv2.inRange(hsv, lower_hsv, upper_hsv)

        # 策略2：LAB L通道（豆子通常不是最亮也不是最暗）
        L, a_col, b_col = cv2.split(lab)
        # 豆子亮度通常在 30-75% 范围
        _, mask_L = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY)
        mask_L_mid = cv2.inRange(L, 70, 190)  # 中等亮度区域

        # 策略3：灰度 + 自适应
        blur = cv2.GaussianBlur(gray, (7, 7), 0)
        mask_adaptive = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 8
        )

        # 策略4：边缘检测辅助（豆子有明确边界）
        edges = cv2.Canny(blur, 30, 100)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        edges_dilated = cv2.dilate(edges, kernel, iterations=2)

        # 融合：HSV OR (边缘 AND L中间调)
        combined = cv2.bitwise_or(mask_hsv, cv2.bitwise_and(mask_L_mid, edges_dilated))
        combined = cv2.bitwise_or(combined, mask_adaptive)

        return combined

    def _morphology_cleanup(self, mask: np.ndarray) -> np.ndarray:
        """形态学清理：去噪 + 填充空洞"""
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

        # 开运算：去除小噪点
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small)

        # 闭运算：填充豆子内部空洞
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_large)

        return mask

    def _extract_bean_regions(self, mask: np.ndarray) -> List[BeanRegion]:
        """提取所有豆子区域"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions = []
        for cnt in contours:
            area = cv2.contourArea(cnt)

            # 跳过太小/太大的轮廓
            if area < self.min_bean_area * 0.5 or area > self.max_bean_area * 1.5:
                continue

            # 近似轮廓
            epsilon = 0.02 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)

            # 边界框
            x, y, w, h = cv2.boundingRect(cnt)

            # 重心
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
            else:
                cx, cy = x + w/2, y + h/2

            # 长宽比
            aspect = float(min(w, h)) / max(w, h) if max(w, h) > 0 else 0

            # 紧凑度
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            solidity = float(area) / hull_area if hull_area > 0 else 0

            # 等效直径
            equi_d = 2 * np.sqrt(area / np.pi)

            # 生成掩码
            bean_mask = np.zeros_like(mask)
            cv2.drawContours(bean_mask, [cnt], -1, 255, -1)

            regions.append(BeanRegion(
                contour=cnt,
                mask=bean_mask,
                bounding_box=(x, y, w, h),
                centroid=(cx, cy),
                area_pixels=int(area),
                aspect_ratio=aspect,
                solidity=solidity,
                equidiameter=equi_d,
            ))

        return regions

    def extract_bean_image(self, image: np.ndarray, region: BeanRegion,
                           margin: int = 10) -> np.ndarray:
        """
        从原图裁剪出单个豆子区域（带margin）

        Returns:
            裁剪后的 BGR 图像
        """
        x, y, w, h = region.bounding_box
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(image.shape[1], x + w + margin)
        y2 = min(image.shape[0], y + h + margin)
        return image[y1:y2, x1:x2]

    def batch_statistics(self, image: np.ndarray,
                         regions: List[BeanRegion]) -> Dict:
        """
        对检测到的所有豆子进行批量统计分析

        Returns:
            统计字典
        """
        if not regions:
            return {"count": 0}

        areas = [r.area_pixels for r in regions]
        aspect_ratios = [r.aspect_ratio for r in regions]
        solidities = [r.solidity for r in regions]
        diameters = [r.equidiameter for r in regions]

        return {
            "count": len(regions),
            "areas": {
                "mean": float(np.mean(areas)),
                "std": float(np.std(areas)),
                "min": float(np.min(areas)),
                "max": float(np.max(areas)),
            },
            "diameters_px": {
                "mean": float(np.mean(diameters)),
                "std": float(np.std(diameters)),
                "min": float(np.min(diameters)),
                "max": float(np.max(diameters)),
            },
            "aspect_ratios": {
                "mean": float(np.mean(aspect_ratios)),
                "min": float(np.min(aspect_ratios)),
            },
            "solidity": {
                "mean": float(np.mean(solidities)),
                "std": float(np.std(solidities)),
            },
            # 估算物理尺寸（假设已知像素分辨率）
            "estimated_size_mm": float(np.mean(diameters) / 30),  # 粗估：30px≈1mm at 4MP
        }

    def visualize(self, image: np.ndarray, regions: List[BeanRegion],
                  mask: np.ndarray = None) -> np.ndarray:
        """
        可视化检测结果

        Returns:
            带标注的 BGR 图像
        """
        vis = image.copy()

        # 叠加掩码
        if mask is not None:
            mask_color = cv2.applyColorMap(mask, cv2.COLORMAP_JET)
            vis = cv2.addWeighted(vis, 0.7, mask_color, 0.3, 0)

        # 绘制轮廓和标签
        for i, region in enumerate(regions):
            color = (0, 255, 0)  # 绿色
            cv2.drawContours(vis, [region.contour], -1, color, 2)

            # 标注序号和尺寸
            x, y, w, h = region.bounding_box
            label = f"#{i+1} d={region.equidiameter:.0f}px"
            cv2.putText(vis, label, (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # 绘制重心
            cx, cy = region.centroid
            cv2.circle(vis, (int(cx), int(cy)), 3, (0, 0, 255), -1)

        # 统计信息
        h, w = vis.shape[:2]
        stats_text = f"Beans detected: {len(regions)}"
        cv2.putText(vis, stats_text, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return vis


if __name__ == "__main__":
    import sys

    # 测试（使用模拟图像）
    print("[TEST] ImageProcessor with synthetic image")
    processor = ImageProcessor()

    # 生成测试图像：模拟多个豆子
    test_img = np.zeros((800, 800, 3), dtype=np.uint8)
    test_img[:, :] = (180, 180, 160)  # 浅灰色背景

    # 画几个椭圆形"豆子"
    for i in range(5):
        cx, cy = 150 + i * 120, 400
        cv2.ellipse(test_img, (cx, cy), (50, 70), 0, 0, 360, (40, 80, 50), -1)

    mask, regions = processor.preprocess(test_img, method="combined")
    stats = processor.batch_statistics(test_img, regions)
    vis = processor.visualize(test_img, regions, mask)

    cv2.imwrite("/tmp/processor_test.jpg", vis)
    print(f"[OK] Test passed: {stats}")
