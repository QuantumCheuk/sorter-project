"""
capture.py - 图像采集模块
HUSKY-SORTER-001 / 课题2: 颜色检测系统

支持:
- Raspberry Pi HQ Camera (IMX477)
- USB Camera (UVC)
"""

import cv2
import time
import numpy as np
from typing import Optional, Tuple


class BeanCamera:
    """生豆图像采集器"""

    def __init__(self, source: str = "hq", resolution: Tuple[int, int] = (4056, 3040)):
        """
        Args:
            source: 'hq' = HQ Camera (IMX477), 'usb' = USB Camera
            resolution: (width, height)
        """
        self.source = source
        self.resolution = resolution
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        """打开摄像头"""
        if self.source == "hq":
            # HQ Camera - 使用 libcamera 驱动
            # Raspberry Pi 上通过 cv2.VideoCapture(0) 自动调用 libcamera
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        else:
            # USB Camera
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

        if not self.cap.isOpened():
            print(f"[ERROR] Cannot open camera source: {self.source}")
            return False

        # 设置分辨率
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        # 预热（消除第一帧噪声）
        for _ in range(5):
            self.cap.read()

        print(f"[OK] Camera opened: {self.source} @ {self.resolution}")
        return True

    def capture(self) -> Optional[np.ndarray]:
        """采集单帧图像"""
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        return frame

    def capture_batch(self, count: int = 10, interval_s: float = 0.1) -> list:
        """采集多帧取平均（降噪）"""
        frames = []
        for _ in range(count):
            frame = self.capture()
            if frame is not None:
                frames.append(frame)
            time.sleep(interval_s)

        if not frames:
            return []

        # 曝光融合（平均）
        return np.mean(frames, axis=0).astype(np.uint8)

    def close(self):
        """关闭摄像头"""
        if self.cap:
            self.cap.release()
            self.cap = None


if __name__ == "__main__":
    # 测试 HQ Camera
    cam = BeanCamera(source="hq")
    if cam.open():
        frame = cam.capture()
        if frame is not None:
            print(f"Captured frame shape: {frame.shape}")
            cv2.imwrite("/tmp/test_bean.jpg", frame)
            print("Saved to /tmp/test_bean.jpg")
        cam.close()
