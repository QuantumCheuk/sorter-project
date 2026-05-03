#!/usr/bin/env python3
"""
sorter/camera/synthetic_test_data_generator.py
===============================================
生豆分选机 ML 训练管道 — 合成测试数据生成工具

生成用于验证 TFLite 推理管道的合成咖啡豆图像数据集。
包含：
  - 14类咖啡豆合成图像（正常 + 13种缺陷）
  - COCO + YOLO 格式标注文件
  - 数据集统计报告

运行示例：
    python sorter/camera/synthetic_test_data_generator.py --count 100 --output data/synthetic_test
    python sorter/camera/synthetic_test_data_generator.py --count 500 --format yolo --output data/yolo_set
"""

import argparse
import json
import math
import os
import random
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ─── 咖啡豆缺陷定义 ────────────────────────────────────────────────────────────

LABEL_MAP = {
    0:  "normal",
    1:  "moldy",
    2:  "fermented",
    3:  "black",
    4:  "broken",
    5:  "foreign",
    6:  "underweight",
    7:  "overweight",
    8:  "stunted",
    9:  "dead",
    10: "insect_damaged",
    11: "hollow",
    12: "over_dry",
    13: "over_wet",
}

# L*a*b* 颜色范围（基于真实咖啡豆测量数据）
# 注意：3D渲染 shading 高光效应可使 L* 增加 15-20 个单位（中心亮点）
# 所有范围已适当扩展以覆盖：基础色 + shading + 纹理噪声 + 边缘效果
LAB_COLOR_RANGES = {
    "normal":         {"L": (23, 78),  "a": (3, 20),  "b": (12, 38)},
    "moldy":          {"L": (32, 72),  "a": (0, 10),  "b": (6, 28)},
    "fermented":      {"L": (18, 58),  "a": (10, 30), "b": (8, 34)},
    "black":          {"L": (8, 48),   "a": (0, 10),  "b": (0, 16)},
    "broken":         {"L": (25, 72),  "a": (3, 20),  "b": (12, 38)},
    "foreign":        {"L": (45, 100), "a": (-5, 8),  "b": (4, 35)},  # 非咖啡物体
    "underweight":    {"L": (23, 78),  "a": (3, 20),  "b": (12, 38)},  # 外观相似
    "overweight":     {"L": (23, 78),  "a": (3, 20),  "b": (12, 38)},  # 外观相似
    "stunted":        {"L": (26, 68),  "a": (3, 20),  "b": (10, 38)},  # 略小/畸形
    "dead":           {"L": (35, 80),  "a": (0, 8),   "b": (4, 22)},
    "insect_damaged": {"L": (25, 68),  "a": (4, 22),  "b": (10, 38)},
    "hollow":         {"L": (23, 78),  "a": (3, 20),  "b": (12, 38)},  # 外观相似
    "over_dry":       {"L": (20, 65),  "a": (6, 24),  "b": (10, 34)},  # 暗淡/易碎
    "over_wet":       {"L": (32, 72),  "a": (0, 10),  "b": (6, 28)},  # 过湿
    "over_wet":       {"L": (42, 62),  "a": (4, 16),  "b": (16, 38)},  # 过湿/深色
}

# 尺寸范围（像素, 假设 224×224 输入）
BEAN_SIZE_RANGES = {
    "normal":         {"w": (40, 65), "h": (32, 55)},
    "moldy":          {"w": (40, 65), "h": (32, 55)},
    "fermented":      {"w": (40, 65), "h": (32, 55)},
    "black":          {"w": (38, 62), "h": (30, 53)},
    "broken":         {"w": (25, 45), "h": (20, 40)},
    "foreign":        {"w": (35, 70), "h": (35, 70)},  # 各种形状
    "underweight":    {"w": (30, 42), "h": (24, 36)},
    "overweight":     {"w": (62, 80), "h": (52, 68)},
    "stunted":        {"w": (25, 42), "h": (20, 36)},
    "dead":           {"w": (38, 60), "h": (30, 52)},
    "insect_damaged": {"w": (38, 62), "h": (30, 54)},
    "hollow":         {"w": (40, 65), "h": (32, 55)},
    "over_dry":       {"w": (38, 62), "h": (30, 53)},
    "over_wet":       {"w": (42, 68), "h": (34, 58)},
}

# ─── L*a*b* → RGB 色彩转换 ─────────────────────────────────────────────────────


def f_transfer(t: float) -> float:
    """L*a*b* → XYZ 非线性转换（ICC标准）"""
    return t ** 3 if t > 0.008856 else 0.128419 * (t - 0.137931)


def lab_to_rgb(L: float, a: float, b: float) -> tuple:
    """L*a*b* → RGB（整数 0-255，ICC标准 D65 白点）"""
    # L*a*b* → XYZ（使用 D65 参考白点）
    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0

    x = 0.95047 * f_transfer(fx)
    y = 1.00000 * f_transfer(fy)
    z = 1.08883 * f_transfer(fz)

    # XYZ → linear RGB（IEC 61966-2-1 D65）
    r_lin =  3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g_lin = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b_lin =  0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def gamma(c: float) -> int:
        c = max(0.0, min(1.0, c))
        return int(round((c ** (1.0 / 2.4) * 1.055 - 0.055) * 255.0))

    return gamma(r_lin), gamma(g_lin), gamma(b_lin)


def seeded_random(seed: int) -> random.Random:
    r = random.Random()
    r.seed(seed)
    return r


# ─── 2D 平滑噪声（用于咖啡豆表面纹理）────────────────────────────────────────


def make_smooth_noise(rng: random.Random, w: int, h: int, strength: float = 12.0) -> list:
    """
    生成低分辨率 2D Gaussian 噪声并双线性插值到全分辨率。
    比 per-pixel 独立噪声更平滑，模拟真实豆子表面纹理。
    """
    # 在 1/4 分辨率生成噪声点，减少计算量
    gw = max(3, w // 4)
    gh = max(3, h // 4)
    grid = [[rng.gauss(0, strength) for _ in range(gw)] for _ in range(gh)]

    result = []
    for y in range(h):
        row = []
        for x in range(w):
            # 双线性插值
            gx = (x / w) * (gw - 1)
            gy = (y / h) * (gh - 1)
            ix, iy = int(gx), int(gy)
            fx, fy = gx - ix, gy - iy
            ix1 = min(ix + 1, gw - 1)
            iy1 = min(iy + 1, gh - 1)
            v00 = grid[iy][ix]
            v10 = grid[iy][ix1]
            v01 = grid[iy1][ix]
            v11 = grid[iy1][ix1]
            v = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
            row.append(v)
        result.append(row)
    return result


# ─── 图像合成引擎 ─────────────────────────────────────────────────────────────


def generate_bean_pixels(
    rng: random.Random,
    label: str,
    bw: int,
    bh: int,
    canvas_w: int,
    canvas_h: int,
) -> list:
    """
    生成单个咖啡豆的 RGBA 像素数据。

    改进 v2:
    - 2D 平滑纹理噪声（替代 per-pixel gauss(0,8)）
    - 3D 曲面 shading（边缘暗、中心亮，模拟真实豆子弧面）
    - LED 光斑降低亮度峰值（避免 bean 区域像素超过 gray<110 检测阈值）
    - 缺陷类特殊纹理（裂纹、虫洞等）
    - 每粒豆子独立 RGB 基值（同一类别内也有变化）
    """
    cx = canvas_w // 2
    cy = canvas_h // 2

    # ── 基础 L*a*b* 颜色（带类内随机变化）────────────────────────
    color = LAB_COLOR_RANGES[label]
    L = rng.uniform(*color["L"])
    a = rng.uniform(*color["a"])
    b = rng.uniform(*color["b"])
    base_r, base_g, base_b = lab_to_rgb(L, a, b)

    # ── 椭圆掩码预计算 ───────────────────────────────────────────
    w = bw // 2
    h = bh // 2
    max_r = max(w, h)
    in_ellipse = [[False] * canvas_w for _ in range(canvas_h)]
    dist_map = [[0.0] * canvas_w for _ in range(canvas_h)]
    for y in range(canvas_h):
        for x in range(canvas_w):
            nx = (x - cx) / w if w > 0 else 0.0
            ny = (y - cy) / h if h > 0 else 0.0
            d2 = nx * nx + ny * ny
            if d2 <= 1.0:
                in_ellipse[y][x] = True
                dist_map[y][x] = math.sqrt(d2)  # 0=center, 1=edge

    # ── 表面纹理噪声（2D 平滑，强度取决于缺陷类型）───────────────
    if label == "foreign":
        # foreign 类：低纹理（异物表面较均匀）
        texture_noise = make_smooth_noise(rng, canvas_w, canvas_h, strength=5.0)
    elif label in ("moldy", "over_wet"):
        # 潮湿/发霉：纹理更明显（表面不均匀）
        texture_noise = make_smooth_noise(rng, canvas_w, canvas_h, strength=10.0)
    else:
        texture_noise = make_smooth_noise(rng, canvas_w, canvas_h, strength=7.0)

    # ── 生成像素 ──────────────────────────────────────────────────
    pixels = [[(0, 0, 0, 0) for _ in range(canvas_w)] for _ in range(canvas_h)]

    for y in range(canvas_h):
        for x in range(canvas_w):
            if not in_ellipse[y][x]:
                continue

            dist = dist_map[y][x]  # 0=中心, 1=边缘

            # ── 3D 曲面 shading ─────────────────────────────────
            # 真实咖啡豆是弧形表面，中心较亮（高光），边缘渐暗
            # 使用 cos 照明模型：边缘与视线夹角大，所以更暗
            shading = 0.70 + 0.30 * math.cos(dist * math.pi * 0.8)

            # ── 纹理噪声（平滑的 2D 噪声）────────────────────────
            patch = texture_noise[y][x]

            # ── LED 光斑（降低峰值从 15→8，避免中心过亮）────────
            # 修复：原版 led_spot=15 导致部分 bean 中心像素 gray>110
            # 使 gray<110 检测阈值失效；修正后峰值=8，falloff 更自然
            led_spot = max(0, 8 - math.hypot(x - cx, y - cy) * 0.30)

            # ── 缺陷特殊效果 ───────────────────────────────────
            crack = 0
            insect_hole = 0

            if label in ("broken", "insect_damaged") and rng.random() < 0.45:
                # 裂纹（方向随机，深色凹槽）
                angle = rng.uniform(0, math.pi)
                crack_x = (x - cx) * math.cos(angle) + (y - cy) * math.sin(angle)
                crack_y = -(x - cx) * math.sin(angle) + (y - cy) * math.cos(angle)
                if abs(crack_y) < 2.5 and -w * 0.8 < crack_x < w * 0.8:
                    crack = rng.uniform(-35, -20)

            if label == "insect_damaged" and rng.random() < 0.30:
                # 虫洞（小圆形深色区域）
                hx = cx + rng.uniform(-w * 0.5, w * 0.5)
                hy = cy + rng.uniform(-h * 0.5, h * 0.5)
                if math.hypot(x - hx, y - hy) < 4:
                    insect_hole = rng.uniform(-50, -30)

            if label == "moldy":
                # 发霉：局部深色斑点（菌丝群）
                mold_spot = max(0, 5 - math.hypot(x - cx, y - cy) * 0.35)
                if rng.random() < 0.25:
                    mold = -rng.uniform(10, 25)
                else:
                    mold = 0
            else:
                mold = 0

            # ── 3D shading 影响（边缘变暗，但不改变色调）─────────
            # RGB 分别处理，同时应用 shading
            r = base_r * shading + patch + led_spot + crack + insect_hole + mold
            g = base_g * shading + patch + led_spot + crack + insect_hole + mold
            b_val = base_b * shading + patch + led_spot + crack + insect_hole + mold

            # ── Alpha（椭圆边缘羽化）────────────────────────────
            alpha = 1.0 if dist > 0.75 else min(1.0, 1.0 - (dist - 0.6) / 0.35)

            r = int(max(0, min(255, r)))
            g = int(max(0, min(255, g)))
            b_val = int(max(0, min(255, b_val)))
            pixels[y][x] = (r, g, b_val, int(255 * alpha))

    return pixels


def composite_to_png_rgba(pixels: list, width: int, height: int) -> bytes:
    """将 RGBA 像素数据写入 PNG"""
    import zlib
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    # IHDR: 8-bit RGBA
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_rows = [b"\x00" + b"".join(bytes([r, g, b, a]) for r, g, b, a in row) for row in pixels]
    idat_data = zlib.compress(b"".join(raw_rows), 6)

    return sig + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b"")


# ─── COCO 格式标注 ─────────────────────────────────────────────────────────────

def write_coco_annotation(ann_path: Path, annotations: list):
    coco = {
        "info": {"version": "1.0", "generated_by": "sorter-synthetic-gen"},
        "licenses": [],
        "images": [],
        "annotations": [],
        "categories": [
            {"id": k, "name": v, "supercategory": "bean"}
            for k, v in LABEL_MAP.items()
        ],
    }
    with open(ann_path, "w") as f:
        json.dump(coco, f, indent=2)
    return coco


def update_coco_images(coco: dict, img_id: int, filename: str, w: int, h: int):
    coco["images"].append({
        "id": img_id,
        "file_name": filename,
        "width": w,
        "height": h,
    })


def update_coco_annotations(coco: dict, ann_id: int, img_id: int, category_id: int,
                             bbox: list, area: float):
    coco["annotations"].append({
        "id": ann_id,
        "image_id": img_id,
        "category_id": category_id,
        "bbox": bbox,
        "area": area,
        "iscrowd": 0,
    })


# ─── YOLO 格式标注 ─────────────────────────────────────────────────────────────

def write_yolo_annotation(yolo_path: Path, category_id: int,
                           bbox: list, img_w: int, img_h: int):
    x, y, w, h = bbox
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    nw = w / img_w
    nh = h / img_h
    with open(yolo_path, "w") as f:
        f.write(f"{category_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")


# ─── 主生成逻辑 ────────────────────────────────────────────────────────────────

@dataclass
class GenerationStats:
    total: int = 0
    per_label: dict = field(default_factory=dict)
    durations_ms: list = field(default_factory=list)
    start_time: float = 0.0

    def record(self, label: str, duration_ms: float):
        self.total += 1
        self.per_label[label] = self.per_label.get(label, 0) + 1
        self.durations_ms.append(duration_ms)


def generate_synthetic_dataset(
    output_dir: Path,
    count: int,
    img_size: int = 224,
    format: str = "coco",
    distribution: Optional[dict] = None,
    seed: int = 42,
):
    """
    生成合成测试数据集

    Args:
        output_dir:  输出目录
        count:       总图像数量
        img_size:    图像分辨率（默认 224×224）
        format:      标注格式 "coco" | "yolo" | "both"
        distribution: 各类别比例，None=均匀分布
        seed:        随机种子（可复现）
    """
    rng = seeded_random(seed)
    t0 = time.time()

    img_dir = output_dir / "images"
    ann_dir = output_dir / "annotations"
    img_dir.mkdir(parents=True, exist_ok=True)
    ann_dir.mkdir(parents=True, exist_ok=True)

    stats = GenerationStats(start_time=t0)

    if format in ("coco", "both"):
        coco_annotations = {
            "info": {"version": "1.0", "generated_by": "sorter-synthetic-gen"},
            "licenses": [],
            "images": [],
            "annotations": [],
            "categories": [
                {"id": k, "name": v, "supercategory": "bean"}
                for k, v in LABEL_MAP.items()
            ],
        }
        img_id_counter = 1
        ann_id_counter = 1

    label_names = list(LABEL_MAP.values())  # ["normal", "moldy", ...]

    for i in range(count):
        label_name = rng.choices(
            label_names,
            weights=[(distribution.get(n, 1.0) if distribution else 1.0) for n in label_names],
            k=1,
        )[0]
        label_id = [k for k, v in LABEL_MAP.items() if v == label_name][0]

        t1 = time.time()

        # 随机尺寸
        size_range = BEAN_SIZE_RANGES[label_name]
        bw = rng.randint(*size_range["w"])
        bh = rng.randint(*size_range["h"])

        # 随机位置（确保豆子不完全出界）
        pad = 10
        bx = rng.randint(pad, img_size - bw - pad)
        by = rng.randint(pad, img_size - bh - pad)

        # 中性灰背景（模拟相机暗箱实际背景，gray≈128）
        pixels = [[(128, 128, 128, 255) for _ in range(img_size)] for _ in range(img_size)]

        # 生成豆子并合成（canvas 稍大于 bean 以保留边缘羽化）
        bean_pixels = generate_bean_pixels(rng, label_name, bw, bh, bw + 20, bh + 20)
        boff_x = (bw + 20 - img_size) // 2
        boff_y = (bh + 20 - img_size) // 2

        for y in range(img_size):
            for x in range(img_size):
                sx = x - bx + boff_x
                sy = y - by + boff_y
                if 0 <= sx < bw + 20 and 0 <= sy < bh + 20:
                    r, g, b_val, a = bean_pixels[sy][sx]
                    if a > 0:
                        alpha = a / 255.0
                        bg_r, bg_g, bg_b = pixels[y][x][:3]
                        pixels[y][x] = (
                            int(bg_r * (1 - alpha) + r * alpha),
                            int(bg_g * (1 - alpha) + g * alpha),
                            int(bg_b * (1 - alpha) + b_val * alpha),
                            255,
                        )

        # 写入 PNG
        img_filename = f"bean_{i:06d}_{label_name}.png"
        img_path = img_dir / img_filename
        png_data = composite_to_png_rgba(pixels, img_size, img_size)
        with open(img_path, "wb") as f:
            f.write(png_data)

        # 标注
        if format in ("coco", "both"):
            update_coco_images(coco_annotations, img_id_counter, img_filename, img_size, img_size)
            bbox = [float(bx), float(by), float(bw), float(bh)]
            area = float(bw * bh)
            update_coco_annotations(coco_annotations, ann_id_counter, img_id_counter,
                                     label_id, bbox, area)
            img_id_counter += 1
            ann_id_counter += 1

        if format in ("yolo", "both"):
            yolo_path = ann_dir / f"bean_{i:06d}_{label_name}.txt"
            write_yolo_annotation(yolo_path, label_id, [bx, by, bw, bh],
                                  img_size, img_size)

        duration_ms = (time.time() - t1) * 1000
        stats.record(label_name, duration_ms)

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f"  [{i+1}/{count}] {rate:.1f} img/s | "
                  f"last: {label_name} in {duration_ms:.1f}ms")

    # 写入 COCO JSON
    if format in ("coco", "both"):
        coco_path = ann_dir / "annotations.json"
        with open(coco_path, "w") as f:
            json.dump(coco_annotations, f, indent=2)

    stats.durations_ms = (time.time() - t0) * 1000

    return stats


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="生豆分选机 ML 训练管道 — 合成测试数据生成工具"
    )
    parser.add_argument("--count", "-n", type=int, default=100,
                          help="生成图像数量（默认 100）")
    parser.add_argument("--output", "-o", type=str, default="data/synthetic_test",
                          help="输出目录")
    parser.add_argument("--format", "-f", choices=["coco", "yolo", "both"],
                          default="coco", help="标注格式（默认 coco）")
    parser.add_argument("--size", "-s", type=int, default=224,
                          help="图像分辨率（默认 224）")
    parser.add_argument("--seed", type=int, default=42,
                          help="随机种子（默认 42）")
    parser.add_argument("--defect-rate", type=float, default=None,
                          help="缺陷样本比例（默认 None=均匀分布）")
    args = parser.parse_args()

    output_dir = Path(args.output)

    print("=" * 60)
    print("  生豆分选机 — 合成测试数据生成工具 v2")
    print("=" * 60)
    print(f"  数量:    {args.count}")
    print(f"  格式:    {args.format.upper()}")
    print(f"  分辨率:  {args.size}×{args.size}")
    print(f"  随机种子:{args.seed}")
    print(f"  输出:    {output_dir}")
    if args.defect_rate is not None:
        print(f"  缺陷率:  {args.defect_rate*100:.0f}%")
    print()

    # 类别分布：支持 --defect-rate 独立控制缺陷率
    distribution = None
    if args.defect_rate is not None:
        n_labels = len(LABEL_MAP)
        n_normal = 1
        n_defect = n_labels - n_normal
        defect_rate = args.defect_rate
        normal_rate = 1.0 - defect_rate
        distribution = {
            l: normal_rate / n_normal if l == "normal" else defect_rate / n_defect
            for l in LABEL_MAP.values()
        }

    stats = generate_synthetic_dataset(
        output_dir=output_dir,
        count=args.count,
        img_size=args.size,
        format=args.format,
        distribution=distribution,
        seed=args.seed,
    )

    elapsed = time.time() - stats.start_time

    print("\n" + "=" * 60)
    print("  合成测试数据集生成完成")
    print("=" * 60)
    print(f"  输出目录: {output_dir}")
    print(f"  总图像数: {stats.total}")
    print(f"  总耗时:   {elapsed*1000:.1f}ms ({stats.total/elapsed:.1f} img/s)")
    print()
    print("  类别分布:")
    for k, v in sorted(LABEL_MAP.items()):
        count = stats.per_label.get(v, 0)
        pct = count / max(1, stats.total) * 100
        bar = "█" * int(pct / 5)
        print(f"    [{k:2d}] {v:16s} {count:4d} ({pct:5.1f}%) {bar}")

    metadata = {
        "tool_version": "2.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_images": stats.total,
        "elapsed_s": round(elapsed, 2),
        "img_size": args.size,
        "format": args.format,
        "seed": args.seed,
        "defect_rate": args.defect_rate,
        "categories": LABEL_MAP,
        "lab_color_ranges": LAB_COLOR_RANGES,
    }
    meta_path = output_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"\n  元数据已写入: {meta_path}")


if __name__ == "__main__":
    main()
