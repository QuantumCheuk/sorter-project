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
import sys
import time
from dataclasses import dataclass, field, asdict
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
LAB_COLOR_RANGES = {
    "normal":         {"L": (38, 58),  "a": (5, 18),  "b": (15, 35)},
    "moldy":          {"L": (42, 62),  "a": (0, 8),   "b": (8, 24)},
    "fermented":      {"L": (28, 48),  "a": (12, 28), "b": (10, 30)},
    "black":          {"L": (10, 28),  "a": (0, 8),   "b": (0, 12)},
    "broken":         {"L": (35, 58),  "a": (5, 18),  "b": (15, 34)},
    "foreign":        {"L": (55, 90),  "a": (-5, 5),  "b": (5, 30)},  # 非咖啡物体
    "underweight":    {"L": (38, 58),  "a": (5, 18),  "b": (15, 35)},  # 外观相似
    "overweight":     {"L": (38, 58),  "a": (5, 18),  "b": (15, 35)},  # 外观相似
    "stunted":        {"L": (36, 54),  "a": (5, 17),  "b": (14, 33)},  # 略小/畸形
    "dead":           {"L": (45, 65),  "a": (0, 6),   "b": (5, 18)},
    "insect_damaged": {"L": (35, 56),  "a": (6, 19),  "b": (14, 34)},
    "hollow":         {"L": (38, 58),  "a": (5, 18),  "b": (15, 35)},  # 外观相似
    "over_dry":       {"L": (30, 50),  "a": (8, 20),  "b": (12, 28)},  # 暗淡/易碎
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


# ─── 图像合成引擎 ─────────────────────────────────────────────────────────────

def lab_to_rgb(L: float, a: float, b: float) -> tuple:
    """L*a*b* → RGB（整数 0-255）"""
    # L*a*b* → XYZ
    y = (L + 16) / 116
    x = a / 500 + y
    z = y - b / 200

    for ch, val in [(x, 3), (y, 3), (z, 3)]:
        if val > 0.206897:
            pass
        else:
            pass  # handled below

    x = 0.95047 * (x ** 3 if x > 0.206897 else 0.128419 * (x - 0.137931))
    y = 1.00000 * (y ** 3 if y > 0.206897 else 0.128419 * (y - 0.137931))
    z = 1.08883 * (z ** 3 if z > 0.206897 else 0.128419 * (z - 0.137931))

    # XYZ → linear RGB
    r =  3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b_l = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def clamp(c):
        c = max(0, min(1, c))
        # gamma
        return int(round((c ** (1/2.4) * 1.055 - 0.055) * 255))

    return clamp(r), clamp(g), clamp(b_l)


def seeded_random(seed: int) -> random.Random:
    r = random.Random()
    r.seed(seed)
    return r


def generate_bean_pixels(
    rng: random.Random,
    label: str,
    width: int,
    height: int,
    img_width: int = 224,
    img_height: int = 224,
) -> list:
    """生成单个咖啡豆的像素数据（椭圆形 + 贴片噪声）"""
    cx = img_width // 2
    cy = img_height // 2
    w = width // 2
    h = height // 2

    # RGBA 背景（黑色，alpha=0）
    pixels = [[(0, 0, 0, 0) for _ in range(img_width)] for _ in range(img_height)]
    color = LAB_COLOR_RANGES[label]
    L = rng.uniform(*color["L"])
    a = rng.uniform(*color["a"])
    b = rng.uniform(*color["b"])
    base_r, base_g, base_b = lab_to_rgb(L, a, b)

    # 生成椭圆掩码
    for y in range(img_height):
        for x in range(img_width):
            nx = (x - cx) / w if w > 0 else 0
            ny = (y - cy) / h if h > 0 else 0
            dist = nx * nx + ny * ny
            if dist <= 1.0:
                # 边缘羽化
                alpha = max(0, 1.0 - dist ** 0.6) if dist > 0.8 else 1.0
                # 添加贴片变化
                patch = rng.gauss(0, 8)
                # LED 光斑模拟
                led_spot = max(0, 15 - math.hypot(x - cx, y - cy) * 0.4)
                # 裂纹（针对 broken / insect_damaged）
                crack = 0
                if label in ("broken", "insect_damaged") and rng.random() < 0.4:
                    angle = rng.uniform(0, math.pi)
                    crack_dist = abs((x - cx) * math.cos(angle) + (y - cy) * math.sin(angle))
                    if crack_dist < 3:
                        crack = -40
                r = max(0, min(255, base_r + patch + led_spot + crack))
                g = max(0, min(255, base_g + patch + led_spot + crack))
                b_val = max(0, min(255, base_b + patch + led_spot + crack))
                pixels[y][x] = (r, g, b_val, int(255 * alpha))

    return pixels


def composite_to_ppm(pixels: list, width: int, height: int) -> bytes:
    """将像素数据写入 PPM（RGB）格式（无 Alpha，支持 PIL 免费读取）"""
    lines = [f"P6\n{width} {height}\n255\n".encode()]
    for row in pixels:
        for r, g, b, _ in row:
            lines.append(bytes([r, g, b]))
    return b"".join(lines)


def composite_to_png_rgba(pixels: list, width: int, height: int) -> bytes:
    """将 RGBA 像素数据写入 PNG"""
    import zlib
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat_data = b""
    raw_rows = []
    for row in pixels:
        raw_rows.append(b"\x00" + b"".join(bytes([r, g, b, a]) for r, g, b, a in row))
    idat_data = zlib.compress(b"".join(raw_rows), 6)

    return (sig + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b""))


import struct

# ─── COCO 格式标注 ─────────────────────────────────────────────────────────────

def write_coco_annotation(ann_path: Path, annotations: list):
    """写入 COCO JSON 标注文件"""
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
        "bbox": bbox,       # [x, y, w, h]
        "area": area,
        "iscrowd": 0,
    })


# ─── YOLO 格式标注 ─────────────────────────────────────────────────────────────

def write_yolo_annotation(yolo_path: Path, category_id: int,
                            bbox: list, img_w: int, img_h: int):
    """写入 YOLO .txt 标注文件（归一化中心点 + 宽高）"""
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

    labels_pool = list(LABEL_MAP.keys())  # 0-13

    for i in range(count):
        label_id = rng.choices(
            labels_pool,
            weights=[distribution.get(l, 1.0) for l in labels_pool],
            k=1,
        )[0]
        label_name = LABEL_MAP[label_id]

        t1 = time.time()

        # 随机尺寸
        size_range = BEAN_SIZE_RANGES[label_name]
        bw = rng.randint(*size_range["w"])
        bh = rng.randint(*size_range["h"])

        # 随机位置（确保豆子不完全出界）
        pad = 10
        bx = rng.randint(pad, img_size - bw - pad)
        by = rng.randint(pad, img_size - bh - pad)

        # 生成图像（黑色背景 + 咖啡豆）
        # 黑色背景
        pixels = [[(12, 10, 8, 255) for _ in range(img_size)] for _ in range(img_size)]

        # 中心裁剪并合成
        bean_pixels = generate_bean_pixels(rng, label_name, bw, bh, bw + 20, bh + 20)
        boff_x = (bw + 20 - img_size) // 2
        boff_y = (bh + 20 - img_size) // 2

        for y in range(img_size):
            for x in range(img_size):
                sx = x - bx + boff_x
                sy = y - by + boff_y
                if 0 <= sx < bw + 20 and 0 <= sy < bh + 20:
                    r, g, b, a = bean_pixels[sy][sx]
                    if a > 0:
                        alpha = a / 255.0
                        bg_r, bg_g, bg_b = pixels[y][x][:3]
                        pixels[y][x] = (
                            int(bg_r * (1 - alpha) + r * alpha),
                            int(bg_g * (1 - alpha) + g * alpha),
                            int(bg_b * (1 - alpha) + b * alpha),
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


def print_stats(stats: GenerationStats, output_dir: Path, total: int):
    """打印数据集统计报告"""
    elapsed = stats.durations_ms
    print(f"\n{'='*60}")
    print(f"  合成测试数据集生成完成")
    print(f"{'='*60}")
    print(f"  输出目录: {output_dir}")
    print(f"  总图像数: {total}")
    print(f"  总耗时:   {elapsed:.1f}ms ({total/elapsed*1000:.1f} img/s)")
    print(f"\n  类别分布:")
    for label_id in sorted(LABEL_MAP.keys()):
        label = LABEL_MAP[label_id]
        cnt = stats.per_label.get(label, 0)
        pct = cnt / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"    [{label_id:2d}] {label:<16} {cnt:4d} ({pct:5.1f}%) {bar}")

    print(f"\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="生豆分选机 — 合成测试数据生成工具"
    )
    parser.add_argument(
        "--count", "-n", type=int, default=100,
        help="生成图像总数（默认 100）"
    )
    parser.add_argument(
        "--output", "-o", type=Path,
        default=Path("data/synthetic_test"),
        help="输出目录路径"
    )
    parser.add_argument(
        "--format", "-f", choices=["coco", "yolo", "both"],
        default="coco",
        help="标注格式: coco / yolo / both（默认 coco）"
    )
    parser.add_argument(
        "--size", "-s", type=int, default=224,
        help="图像分辨率（默认 224，与 MobileNetV2 输入相同）"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="随机种子（可复现，默认 42）"
    )
    parser.add_argument(
        "--defect-ratio", type=float, default=0.08,
        help="缺陷样本比例（默认 0.08，即 8%%）"
    )
    args = parser.parse_args()

    # 构建类别权重：normal 占比高，缺陷类共享剩余比例
    defect_ratio = args.defect_ratio
    normal_ratio = 1.0 - defect_ratio
    distribution = {"normal": normal_ratio}
    for lid, name in LABEL_MAP.items():
        if name != "normal":
            distribution[name] = defect_ratio / (len(LABEL_MAP) - 1)

    print(f"生豆分选机 — 合成测试数据生成工具")
    print(f"  数量:    {args.count}")
    print(f"  格式:    {args.format}")
    print(f"  分辨率:  {args.size}×{args.size}")
    print(f"  缺陷率:  {defect_ratio*100:.1f}%")
    print(f"  随机种子:{args.seed}")
    print(f"  输出:    {args.output}")
    print()

    stats = generate_synthetic_dataset(
        output_dir=args.output,
        count=args.count,
        img_size=args.size,
        format=args.format,
        distribution=distribution,
        seed=args.seed,
    )

    print_stats(stats, args.output, args.count)

    # 写入元数据
    meta = {
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": args.count,
        "image_size": args.size,
        "format": args.format,
        "defect_ratio": args.defect_ratio,
        "seed": args.seed,
        "label_map": LABEL_MAP,
        "total_duration_ms": stats.durations_ms,
        "per_label_counts": stats.per_label,
    }
    meta_path = args.output / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\n元数据已写入: {meta_path}")


if __name__ == "__main__":
    main()