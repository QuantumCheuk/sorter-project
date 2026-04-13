"""
light_uniformity_test.py - LED 光照均匀度分析工具
HUSKY-SORTER-001 / 课题2 Day 3

功能：
1. 从拍摄的白板图像分析光照均匀度
2. 生成光照热力图（Intensity Map）
3. 给出LED调整建议

原理：
- 在暗箱中放置白色漫反射板（或白色A4纸）
- 拍摄得到亮度分布图
- 计算各区域亮度与平均值的偏差

均匀度指标：U = 1 - (I_max - I_min) / (I_max + I_min)
- U > 0.9 → 优秀
- U > 0.8 → 良好
- U < 0.8 → 需改善

用法：
    python -m sorter.camera.light_uniformity_test --input ./white_board.jpg
    python -m sorter.camera.light_uniformity_test --input ./white_board.jpg --grid 7 --output ./heatmap.png
"""

import argparse
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 无头模式
import json
from pathlib import Path
from typing import Tuple, List, Dict, Optional

matplotlib.rcParams['font.family'] = 'DejaVu Sans'


class LightUniformityAnalyzer:
    """
    LED 光照均匀度分析

    分析方法：
    1. 灰度化 + 归一化
    2. 分网格计算各区域平均亮度
    3. 计算不均匀度系数 U
    4. 生成热力图可视化
    5. 给出LED位置调整建议
    """

    def __init__(self, grid_size: int = 5):
        """
        Args:
            grid_size: 分网格的行列数（grid_size×grid_size）
        """
        self.grid_size = grid_size

    def analyze(self, image_path: str, output_path: Optional[str] = None) -> Dict:
        """
        分析光照均匀度

        Returns:
            {
                "uniformity_coefficient": float,  # 均匀度系数 U (0-1, 越高越好)
                "grid_means": List[List[float]],   # 各网格平均亮度
                "overall_mean": float,
                "overall_std": float,
                "cv_pct": float,                    # 变异系数%
                "max_deviation_pct": float,        # 最大偏差%
                "passed": bool,
                "recommendations": List[str],
            }
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        return self.analyze_image(img, output_path)

    def analyze_image(self, image: np.ndarray, output_path: Optional[str] = None) -> Dict:
        """直接分析 numpy 图像"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)

        h, w = gray.shape
        grid_h, grid_w = h // self.grid_size, w // self.grid_size

        # 计算每个网格的平均亮度
        grid_means = np.zeros((self.grid_size, self.grid_size))
        for gy in range(self.grid_size):
            for gx in range(self.grid_size):
                y1, y2 = gy * grid_h, (gy + 1) * grid_h
                x1, x2 = gx * grid_w, (gx + 1) * grid_w
                patch = gray[y1:y2, x1:x2]
                grid_means[gy, gx] = np.mean(patch)

        # 统计分析
        overall_mean = np.mean(grid_means)
        overall_std = np.std(grid_means)
        cv_pct = overall_std / (overall_mean + 1e-6) * 100

        I_max = np.max(grid_means)
        I_min = np.min(grid_means)
        # 均匀度系数（也称为"波动系数"）
        uniformity_coeff = 1 - (I_max - I_min) / (I_max + I_min + 1e-6)

        max_deviation_pct = max(
            abs(I_max - overall_mean) / (overall_mean + 1e-6),
            abs(overall_mean - I_min) / (overall_mean + 1e-6)
        ) * 100

        # 评分（百分制）
        if uniformity_coeff >= 0.9:
            score = 100
            passed = True
        elif uniformity_coeff >= 0.85:
            score = 90
            passed = True
        elif uniformity_coeff >= 0.8:
            score = 75
            passed = True
        elif uniformity_coeff >= 0.7:
            score = 60
            passed = False
        else:
            score = 40
            passed = False

        # 找出最暗和最亮区域
        min_pos = np.unravel_index(np.argmin(grid_means), grid_means.shape)
        max_pos = np.unravel_index(np.argmax(grid_means), grid_means.shape)
        min_val = grid_means[min_pos]
        max_val = grid_means[max_pos]

        print(f"\n{'='*50}")
        print(f"LED 光照均匀度分析报告")
        print(f"{'='*50}")
        print(f"  网格尺寸: {self.grid_size}×{self.grid_size} ({self.grid_size**2} 区域)")
        print(f"  整体平均亮度: {overall_mean:.1f} (0-255)")
        print(f"  标准差: {overall_std:.2f}")
        print(f"  变异系数: {cv_pct:.2f}%")
        print(f"  均匀度系数 U: {uniformity_coeff:.4f}")
        print(f"  最大偏差: {max_deviation_pct:.2f}%")
        print(f"  最亮区域: {max_pos} = {max_val:.1f}")
        print(f"  最暗区域: {min_pos} = {min_val:.1f}")
        print(f"  评分: {score}/100 {'✅ 通过' if passed else '❌ 未通过'}")
        print(f"{'='*50}")

        # 生成建议
        recommendations = self._generate_recommendations(
            grid_means, min_pos, max_pos, uniformity_coeff
        )

        # 生成热力图
        if output_path:
            self._save_heatmap(grid_means, overall_mean, output_path)

        return {
            "uniformity_coefficient": round(uniformity_coeff, 4),
            "grid_means": grid_means.tolist(),
            "overall_mean": round(float(overall_mean), 2),
            "overall_std": round(float(overall_std), 2),
            "cv_pct": round(cv_pct, 2),
            "max_deviation_pct": round(max_deviation_pct, 2),
            "darkest_cell": {"row": int(min_pos[0]), "col": int(min_pos[1]), "value": round(float(min_val), 2)},
            "brightest_cell": {"row": int(max_pos[0]), "col": int(max_pos[1]), "value": round(float(max_val), 2)},
            "score": score,
            "passed": passed,
            "recommendations": recommendations,
        }

    def _generate_recommendations(self, grid_means: np.ndarray,
                                   min_pos: Tuple, max_pos: Tuple,
                                   U: float) -> List[str]:
        """根据分析结果生成LED调整建议"""
        recs = []

        if U >= 0.9:
            recs.append("✅ 光照非常均匀，无需调整")
            return recs

        if U >= 0.8:
            recs.append("⚠️ 光照轻微不均匀，建议微调")

        # 分析暗角问题（四周比中心暗 → 需要增加角LED或漫反射）
        border_mean = (
            np.mean(grid_means[0, :]) +           # 上边
            np.mean(grid_means[-1, :]) +          # 下边
            np.mean(grid_means[:, 0]) +           # 左边
            np.mean(grid_means[:, -1])            # 右边
        ) / 4
        center_mean = grid_means[1:-1, 1:-1].mean()

        if border_mean < center_mean * 0.9:
            recs.append(
                f"🔍 检测到暗角（边缘亮度{center_mean:.0f}的{border_mean/center_mean*100:.0f}%）"
            )
            recs.append("   → 建议：在四角LED旁各加一片白色PET漫反射片")
            recs.append("   → 或在暗角区域贴一小块白色海绵增加漫反射")

        # 分析中心暗斑（中心比边缘暗 → LED角度问题）
        if center_mean < border_mean * 0.9:
            recs.append("🔍 检测到中心暗斑")
            recs.append("   → 可能是LED环形灯角度过低，调整LED仰角使其向下照射")
            recs.append("   → 或LED距离暗箱顶部太近，降低安装位置")

        # 分析单侧过亮
        row_means = grid_means.mean(axis=1)
        col_means = grid_means.mean(axis=0)
        if row_means[0] > row_means[2] * 1.2:
            recs.append("🔍 检测到上侧过亮（比其他侧亮20%+）")
            recs.append("   → 检查顶部LED是否正对摄像方向，尝试偏移5-10°")
        if col_means[-1] > col_means[0] * 1.2:
            recs.append("🔍 检测到右侧过亮")
            recs.append("   → 检查右侧LED角度")

        # 最暗区域定位
        gy, gx = min_pos
        position_hints = {
            (0, 0): "左上角",
            (0, -1): "右上角",
            (-1, 0): "左下角",
            (-1, -1): "右下角",
        }
        pos_desc = "第{}行第{}列".format(gy+1, gx+1)
        recs.append(f"📍 最暗区域：{pos_desc}（相对暗{int((1-U)*100)}%）")
        recs.append(f"   → 在该区域对应的暗箱内壁贴一小块白色漫反射纸")

        if U < 0.7:
            recs.append("⚠️ 均匀度严重不足，当前条件下颜色检测结果不可靠")
            recs.append("   → 必须解决光照问题后才能进行颜色标定")

        return recs

    def _save_heatmap(self, grid_means: np.ndarray, mean_val: float, output_path: str):
        """保存热力图"""
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # 热力图
        ax1 = axes[0]
        im = ax1.imshow(grid_means, cmap='RdYlGn_r', vmin=grid_means.min(), vmax=grid_means.max())
        ax1.set_title(f'Light Uniformity Heatmap (U={1-(grid_means.max()-grid_means.min())/(grid_means.max()+grid_means.min()):.3f})')
        ax1.set_xlabel('Column')
        ax1.set_ylabel('Row')
        plt.colorbar(im, ax=ax1, label='Brightness (0-255)')

        # 在每个格子标注数值
        for gy in range(self.grid_size):
            for gx in range(self.grid_size):
                val = grid_means[gy, gx]
                color = 'white' if val < (grid_means.max() + grid_means.min()) / 2 else 'black'
                ax1.text(gx, gy, f'{val:.0f}', ha='center', va='center', color=color, fontsize=9)

        # 亮度分布直方图
        ax2 = axes[1]
        ax2.hist(grid_means.flatten(), bins=20, color='steelblue', edgecolor='white', alpha=0.8)
        ax2.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean={mean_val:.1f}')
        ax2.set_title('Brightness Distribution Across Grid Cells')
        ax2.set_xlabel('Brightness')
        ax2.set_ylabel('Count')
        ax2.legend()

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[OK] Heatmap saved: {output_path}")

    def analyze_from_camera_capture(self, camera_index: int = 0,
                                     num_captures: int = 3,
                                     white_surface: str = "white_board") -> Dict:
        """
        直接从摄像头捕获白板图像并分析

        Args:
            camera_index: 摄像头索引
            num_captures: 平均帧数（减少噪点）
            white_surface: "white_board" 或 "gray_card"
        """
        cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            print("[WARN] Cannot open camera")
            return {}

        frames = []
        for _ in range(num_captures):
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                print(f"[WARN] Failed to capture frame {_}")
        cap.release()

        if not frames:
            print("[ERROR] No frames captured")
            return {}

        # 平均多帧降噪
        avg_frame = np.mean(frames, axis=0).astype(np.uint8)
        return self.analyze_image(avg_frame)


def main():
    parser = argparse.ArgumentParser(description="LED 光照均匀度分析工具")
    parser.add_argument("--input", "-i", required=True, help="白板图像路径")
    parser.add_argument("--output", "-o", help="热力图输出路径 (.png)")
    parser.add_argument("--grid", "-g", type=int, default=5, help="网格尺寸 (默认5×5)")
    parser.add_argument("--camera", "-c", action="store_true", help="从摄像头实时捕获")
    parser.add_argument("--camera-index", type=int, default=0, help="摄像头索引")
    args = parser.parse_args()

    analyzer = LightUniformityAnalyzer(grid_size=args.grid)

    if args.camera:
        result = analyzer.analyze_from_camera_capture(camera_index=args.camera_index)
    else:
        result = analyzer.analyze(args.input, output_path=args.output)

    if result:
        print("\n调整建议:")
        for rec in result["recommendations"]:
            print(f"  {rec}")

        # 保存JSON报告
        report_path = Path(args.input).with_suffix('.uniformity_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] JSON报告已保存: {report_path}")


if __name__ == "__main__":
    main()
