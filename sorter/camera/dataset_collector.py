"""
dataset_collector.py - 训练数据集采集工具
HUSKY-SORTER-001 / 课题2 Day 2

功能：
1. 连接摄像头，实时预览
2. 人工标注（按键盘分类）
3. 保存标注图像到结构化目录
4. 生成标签文件（labels.json）

用法：
    python -m sorter.camera.dataset_collector --output dataset/heirloom_washed

采集流程：
1. 启动预览
2. 将豆子放入暗箱，对焦
3. 按键盘标注：
   [G] = Good (合格)
   [B] = Bleached (漂白)
   [M] = Moldy (发霉)
   [F] = Fermented (发酵过度)
   [R] = Broken (破碎)
   [I] = Insect damaged (虫蛀)
   [Q] = Quit & export
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

# 尝试导入 BeanCamera
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from sorter.camera.capture import BeanCamera
except ImportError:
    BeanCamera = None


LABEL_MAP = {
    "g": "good",
    "b": "bleached",
    "m": "moldy",
    "f": "fermented",
    "r": "broken",
    "i": "insect_damaged",
    "q": "quit",
}

LABEL_NAMES = {
    "good": "✅ 合格",
    "bleached": "🧹 漂白豆",
    "moldy": "🦠 发霉豆",
    "fermented": "🍷 发酵过度",
    "broken": "💔 破碎豆",
    "insect_damaged": "🐛 虫蛀豆",
}


class DatasetCollector:
    """训练数据集采集器"""

    def __init__(self, output_dir: str, camera_source: str = "hq",
                 resolution: tuple = (4056, 3040)):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        self.label_dirs = {}
        for label in ["good", "bleached", "moldy", "fermented", "broken", "insect_damaged"]:
            d = self.output_dir / label
            d.mkdir(exist_ok=True)
            self.label_dirs[label] = d

        self.dataset_json = self.output_dir / "labels.json"
        self.labels: List[Dict] = []
        self.counts = {k: 0 for k in self.label_dirs.keys()}

        # 加载已有标签
        if self.dataset_json.exists():
            with open(self.dataset_json, "r") as f:
                self.labels = json.load(f)
            for entry in self.labels:
                label = entry["label"]
                if label in self.counts:
                    self.counts[label] += 1

        # 摄像头
        self.camera = None
        self.camera_source = camera_source
        self.resolution = resolution

        # 预览窗口
        self.window_name = "Dataset Collector - Press G/B/M/F/R/I to label | Q to quit"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 800, 600)

        # 采集统计
        self.session_start = datetime.now()

    def connect_camera(self) -> bool:
        """连接摄像头"""
        if BeanCamera is None:
            print("[WARN] BeanCamera not available, using OpenCV directly")
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                print("[ERROR] Cannot open camera")
                return False
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            return True

        self.camera = BeanCamera(source=self.camera_source, resolution=self.resolution)
        if not self.camera.open():
            return False
        return True

    def capture_and_label(self) -> bool:
        """
        主循环：预览 + 采集 + 标注
        返回 False 表示退出
        """
        print(f"\n[INFO] Starting dataset collection: {self.output_dir}")
        print(f"[INFO] Current counts: {self.counts}")
        print(f"[INFO] Controls: G=Good B=Bleached M=Moldy F=Fermented R=Broken I=Insect Q=Quit")
        print(f"[INFO] Press SPACE to capture and wait for label key\n")

        preview_resolution = (800, 600)
        save_resolution = self.resolution  # 保存原分辨率

        while True:
            # 获取帧
            if self.camera is not None:
                # 采集多帧降噪
                frame = self.camera.capture_batch(count=3, interval_s=0.05)
                if len(frame) == 0:
                    frame = self.camera.capture()
            else:
                ret, frame = self.cap.read()
                if not ret:
                    continue

            if frame is None:
                continue

            # 缩放用于预览
            preview = cv2.resize(frame, preview_resolution)

            # 叠加信息
            self._overlay_info(preview)

            cv2.imshow(self.window_name, preview)

            key = cv2.waitKey(100) & 0xFF
            if key == ord(' '):
                # 空格：采集当前帧（等待标注）
                high_res = self.camera.capture_batch(count=5, interval_s=0.05) if self.camera else frame
                if len(high_res) == 0:
                    high_res = frame
                # 等待标注键
                self._wait_for_label(high_res)

            elif key != 255:
                char = chr(key).lower()
                if char == 'q':
                    self._quit()
                    return False
                elif char in LABEL_MAP and char != 'q':
                    frame_to_save = self.camera.capture_batch(count=5, interval_s=0.05) if self.camera else frame
                    if len(frame_to_save) == 0:
                        frame_to_save = frame
                    self._save_with_label(frame_to_save, LABEL_MAP[char])

    def _overlay_info(self, frame: np.ndarray):
        """在预览帧上叠加信息"""
        h, w = frame.shape[:2]

        # 顶部状态栏
        cv2.rectangle(frame, (0, 0), (w, 30), (20, 20, 20), -1)
        cv2.putText(frame, f"Collecting: {self.output_dir.name}", (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 底部标签说明
        bar_h = 50
        cv2.rectangle(frame, (0, h - bar_h), (w, h), (20, 20, 20), -1)

        x_pos = 5
        for key, label in LABEL_NAMES.items():
            color = (0, 200, 100) if self.counts.get(key, 0) > 0 else (150, 150, 150)
            count = self.counts.get(key, 0)
            text = f"[{key.upper()}] {label}: {count}"
            cv2.putText(frame, text, (x_pos, h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            x_pos += 180

        # 当前时间
        elapsed = datetime.now() - self.session_start
        time_str = f"Elapsed: {elapsed.seconds // 60}m {elapsed.seconds % 60}s"
        cv2.putText(frame, time_str, (w - 120, h - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 100), 1)

    def _wait_for_label(self, frame: np.ndarray):
        """等待标注键"""
        print("[CAPTURED] Press label key to save (G/B/M/F/R/I), any other key to discard")

        window_label = "Label: SPACE=Save | G/B/M/F/R/I=Label | Esc=Discard"
        cv2.imshow(window_label, cv2.resize(frame, (600, 450)))

        while True:
            key = cv2.waitKey(0) & 0xFF
            cv2.destroyWindow(window_label)

            if key == 27:  # Esc
                print("[DISCARDED]")
                return
            elif key in [ord(c) for c in LABEL_MAP.keys()]:
                char = chr(key).lower()
                if char == 'q':
                    self._quit()
                    return
                elif char != 'q':
                    self._save_with_label(frame, LABEL_MAP[char])
                    return
            else:
                print("[DISCARDED]")
                return

    def _save_with_label(self, frame: np.ndarray, label: str):
        """保存图像并记录标签"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{label}_{timestamp}.jpg"
        filepath = self.output_dir / self.label_dirs[label].name / filename

        # 保存图像（降低分辨率以节省空间，但保持足够用于ML）
        save_frame = cv2.resize(frame, (2048, 1536))  # 3MP 足够训练
        cv2.imwrite(str(filepath), save_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

        # 记录标签
        entry = {
            "filename": filename,
            "label": label,
            "timestamp": timestamp,
            "shape": list(frame.shape),
        }
        self.labels.append(entry)
        self.counts[label] += 1

        print(f"[SAVED] {filepath} -> {label} (total: {self.counts[label]})")

        # 保存 labels.json
        with open(self.dataset_json, "w") as f:
            json.dump(self.labels, f, ensure_ascii=False, indent=2)

    def _quit(self):
        """退出并导出"""
        print(f"\n[EXPORT] Total samples: {len(self.labels)}")
        print("[COUNTS]")
        for label, count in self.counts.items():
            print(f"  {label}: {count}")

        # 导出元数据
        meta = {
            "variety": "unknown",
            "process": "unknown",
            "created": datetime.now().isoformat(),
            "total": len(self.labels),
            "counts": self.counts,
            "labels": self.labels,
        }
        meta_path = self.output_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[OK] Dataset exported to {self.output_dir}")
        cv2.destroyAllWindows()

    def close(self):
        if self.camera:
            self.camera.close()


def main():
    parser = argparse.ArgumentParser(description="训练数据集采集工具")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--camera", "-c", default="hq", choices=["hq", "usb"], help="摄像头类型")
    parser.add_argument("--width", "-w", type=int, default=4056, help="图像宽度")
    parser.add_argument("--height", "-H", type=int, default=3040, help="图像高度")
    parser.add_argument("--variety", default="unknown", help="品种（记录到元数据）")
    parser.add_argument("--process", default="unknown", help="处理法（记录到元数据）")
    args = parser.parse_args()

    collector = DatasetCollector(
        output_dir=args.output,
        camera_source=args.camera,
        resolution=(args.width, args.height)
    )

    if not collector.connect_camera():
        print("[ERROR] Camera connection failed")
        return

    try:
        collector.capture_and_label()
    finally:
        collector.close()


if __name__ == "__main__":
    main()
