"""
capture.py - 双摄像头图像采集模块
HUSKY-SORTER-001 / 课题2: 颜色检测系统

v2 2026-05-17: Dual-camera architecture per SPEC.md 2.2
  - Top: HQ Camera IMX477 (俯视正面)
  - Bottom: USB Camera (仰视背面)
  - T1/T2 光电传感器 GPIO 中断触发拍照
  - bean_buffer 确保 top/bottom 图像一一对应同一粒豆
  - Air jet rejection timing integration

SPEC 2.2.1: 单文件通道 + 光电触发
  T1 (GPIO4) → top_cam.capture()
  T2 (GPIO17) → bottom_cam.capture() + defect detection + rejection decision

SPEC 2.2.5: 气喷剔除时序
  air_blast_delay_ms = 15    # 电磁阀响应延迟
  air_blast_duration_ms = 80 # 气喷持续时间
"""

import cv2
import time
import threading
import logging
import numpy as np
from collections import OrderedDict
from typing import Optional, Tuple, Callable, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("capture")


# ─────────────────────────────────────────────
# 豆粒图像对缓冲区 — 确保 top/bottom 来自同一粒豆
# ─────────────────────────────────────────────
@dataclass
class BeanImagePair:
    """单粒豆的正反面图像对"""
    bean_id: int
    top_image: Optional[np.ndarray] = None
    bottom_image: Optional[np.ndarray] = None
    top_capture_time: float = 0.0
    bottom_capture_time: float = 0.0
    paired: bool = False

    @property
    def is_complete(self) -> bool:
        return self.top_image is not None and self.bottom_image is not None

    @property
    def capture_interval_ms(self) -> float:
        if self.top_capture_time and self.bottom_capture_time:
            return (self.bottom_capture_time - self.top_capture_time) * 1000
        return 0.0


class BeanBuffer:
    """
    豆粒图像缓冲区

    T1 触发 → 创建 BeanImagePair，采集 top 图像
    T2 触发 → 找到对应 BeanImagePair，采集 bottom 图像，标记 paired
    配对完成 → 回调 on_bean_ready(pair)
    """

    def __init__(self, max_pending: int = 10, pairing_timeout_ms: int = 500):
        """
        Args:
            max_pending: 最多同时等待配对的 bean 数量
            pairing_timeout_ms: T1→T2 超时时间（超出视为配对失败）
        """
        self._buffer: OrderedDict[int, BeanImagePair] = OrderedDict()
        self._max_pending = max_pending
        self._pairing_timeout_ms = pairing_timeout_ms
        self._lock = threading.Lock()
        self._bean_counter = 0
        self.on_bean_ready: Optional[Callable[[BeanImagePair], None]] = None

    def on_t1_trigger(self, top_image: np.ndarray) -> int:
        """
        T1 光电传感器触发（顶部）— 创建新 bean 记录

        Returns: bean_id
        """
        with self._lock:
            self._bean_counter += 1
            bean_id = self._bean_counter

            pair = BeanImagePair(
                bean_id=bean_id,
                top_image=top_image,
                top_capture_time=time.monotonic(),
            )
            self._buffer[bean_id] = pair

            # Evict oldest if buffer full
            while len(self._buffer) > self._max_pending:
                oldest_id, oldest = self._buffer.popitem(last=False)
                logger.warning(f"Bean {oldest_id} evicted (no T2 match)")

            return bean_id

    def on_t2_trigger(self, bottom_image: np.ndarray) -> Optional[BeanImagePair]:
        """
        T2 光电传感器触发（底部）— 配对并返回完整 BeanImagePair

        Returns: 配对成功的 BeanImagePair，或 None（无匹配的 T1 记录）
        """
        with self._lock:
            if not self._buffer:
                logger.warning("T2 trigger with empty buffer (no T1 match)")
                return None

            # FIFO: 最老的 bean 应该最先到达 T2
            bean_id, pair = self._buffer.popitem(last=False)
            pair.bottom_image = bottom_image
            pair.bottom_capture_time = time.monotonic()

            interval_ms = pair.capture_interval_ms
            if interval_ms > self._pairing_timeout_ms:
                logger.warning(
                    f"Bean {bean_id} pairing timeout: {interval_ms:.0f}ms "
                    f"> {self._pairing_timeout_ms}ms"
                )
                return None

            pair.paired = True

            if self.on_bean_ready:
                self.on_bean_ready(pair)

            return pair

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()


# ─────────────────────────────────────────────
# 摄像头驱动
# ─────────────────────────────────────────────
class TopCamera:
    """
    顶部摄像头 — HQ Camera IMX477

    特性:
    - 4056×3040 分辨率（12MP）
    - M12 6mm 镜头
    - 俯视正面拍摄
    - libcamera 驱动（Pi OS）

    Pi 上推荐使用 libcamera 而非 V4L2:
    cv2.VideoCapture(0) 在 Pi OS Bullseye+ 自动使用 libcamera
    """

    def __init__(self, resolution: Tuple[int, int] = (2028, 1520),
                 fps: int = 30, simulate: bool = False):
        """
        Args:
            resolution: (width, height) — HQ Camera 默认 2028×1520（半分辨率，更快）
                         全分辨率 4056×3040 用于离线标定
            fps: 帧率
            simulate: True=返回合成图像（无硬件）
        """
        self.resolution = resolution
        self.fps = fps
        self.simulate = simulate
        self.cap: Optional[cv2.VideoCapture] = None
        self._warm = False

    def open(self) -> bool:
        if self.simulate:
            self._warm = True
            logger.info("[TopCam] Simulation mode ready")
            return True

        # Try libcamera first (Pi OS native), fall back to V4L2
        try:
            self.cap = cv2.VideoCapture(0)
        except Exception:
            try:
                self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            except Exception as e:
                logger.error(f"[TopCam] Failed to open: {e}")
                return False

        if not self.cap or not self.cap.isOpened():
            logger.error("[TopCam] Camera not available")
            return False

        # HQ Camera 分辨率设置
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        # Warmup: 丢弃前 10 帧（自动曝光稳定）
        for _ in range(10):
            self.cap.read()
        self._warm = True

        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"[TopCam] Opened HQ Camera @ {actual_w}x{actual_h} {self.fps}fps")
        return True

    def capture(self) -> Optional[np.ndarray]:
        if self.simulate:
            return self._simulate_frame()
        if not self.cap or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        return frame if ret else None

    def _simulate_frame(self) -> np.ndarray:
        """合成测试帧 — 模拟咖啡豆俯视图像"""
        img = np.full((*self.resolution[::-1], 3), (180, 150, 120), dtype=np.uint8)
        # 模拟豆子椭圆
        cx, cy = self.resolution[0] // 2, self.resolution[1] // 2
        cv2.ellipse(img, (cx, cy), (60, 40), 0, 0, 360, (140, 100, 70), -1)
        cv2.line(img, (cx - 50, cy), (cx + 50, cy), (80, 60, 40), 2)  # 中线
        return img

    def close(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None
        self._warm = False


class BottomCamera:
    """
    底部摄像头 — USB Camera (UVC)

    特性:
    - 仰视背面拍摄
    - 分辨率 1920×1080（Logitech C270 或同等）
    - 透过底部磨砂亚克力窗口拍摄
    - 独立 LED 光源
    """

    def __init__(self, resolution: Tuple[int, int] = (1920, 1080),
                 fps: int = 30, simulate: bool = False,
                 device_index: int = 1):
        self.resolution = resolution
        self.fps = fps
        self.simulate = simulate
        self.device_index = device_index
        self.cap: Optional[cv2.VideoCapture] = None
        self._warm = False

    def open(self) -> bool:
        if self.simulate:
            self._warm = True
            logger.info("[BottomCam] Simulation mode ready")
            return True

        try:
            self.cap = cv2.VideoCapture(self.device_index)
        except Exception as e:
            logger.error(f"[BottomCam] Failed to open: {e}")
            return False

        if not self.cap or not self.cap.isOpened():
            logger.error("[BottomCam] Camera not available")
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        for _ in range(5):
            self.cap.read()
        self._warm = True

        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"[BottomCam] Opened USB Camera @ {actual_w}x{actual_h} {self.fps}fps")
        return True

    def capture(self) -> Optional[np.ndarray]:
        if self.simulate:
            return self._simulate_frame()
        if not self.cap or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        return frame if ret else None

    def _simulate_frame(self) -> np.ndarray:
        """合成测试帧 — 模拟咖啡豆仰视背面图像"""
        img = np.full((*self.resolution[::-1], 3), (180, 150, 120), dtype=np.uint8)
        cx, cy = self.resolution[0] // 2, self.resolution[1] // 2
        cv2.ellipse(img, (cx, cy), (55, 38), 0, 0, 360, (130, 90, 60), -1)
        cv2.line(img, (cx - 45, cy + 2), (cx + 45, cy + 2), (90, 70, 50), 2)
        return img

    def close(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None
        self._warm = False


# ─────────────────────────────────────────────
# 光电传感器触发器 — T1/T2 GPIO 中断
# ─────────────────────────────────────────────
class PhotoelectricTrigger:
    """
    T1/T2 红外光电传感器 GPIO 中断触发器

    SPEC 2.2.1: 光电触发而非时间同步
      T1 (GPIO4)  → top camera capture
      T2 (GPIO17) → bottom camera capture + defect detection + rejection

    SPEC 5.2.1: GPIO4=T1, GPIO17=T2 (NPN NO 遮断式)
      豆子遮断光束 → GPIO LOW → 触发中断
    """

    def __init__(self, t1_pin: int = 4, t2_pin: int = 17, simulate: bool = False):
        self.t1_pin = t1_pin
        self.t2_pin = t2_pin
        self.simulate = simulate
        self._active = False

        # Callbacks
        self.on_t1: Optional[Callable[[], None]] = None
        self.on_t2: Optional[Callable[[], None]] = None

    def start(self):
        """注册 GPIO 中断"""
        if self.simulate:
            self._active = True
            logger.info(f"[PhotoSensor] Simulation mode (T1=GPIO{self.t1_pin}, T2=GPIO{self.t2_pin})")
            return

        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.t1_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self.t2_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            # NPN NO: 无豆=HIGH (光束通), 有豆=LOW (光束遮断)
            # 下降沿触发 = 豆子经过
            GPIO.add_event_detect(
                self.t1_pin, GPIO.FALLING,
                callback=self._t1_callback, bouncetime=5
            )
            GPIO.add_event_detect(
                self.t2_pin, GPIO.FALLING,
                callback=self._t2_callback, bouncetime=5
            )
            self._active = True
            logger.info(f"[PhotoSensor] T1=GPIO{self.t1_pin}, T2=GPIO{self.t2_pin} interrupts registered")
        except ImportError:
            logger.error("[PhotoSensor] RPi.GPIO not available, using simulation")
            self.simulate = True
            self._active = True
        except Exception as e:
            logger.error(f"[PhotoSensor] GPIO setup failed: {e}")

    def _t1_callback(self, channel):
        if self.on_t1:
            self.on_t1()

    def _t2_callback(self, channel):
        if self.on_t2:
            self.on_t2()

    def stop(self):
        if not self.simulate:
            try:
                import RPi.GPIO as GPIO
                GPIO.remove_event_detect(self.t1_pin)
                GPIO.remove_event_detect(self.t2_pin)
            except Exception:
                pass
        self._active = False

    @property
    def active(self) -> bool:
        return self._active


# ─────────────────────────────────────────────
# 气喷剔除时序控制器
# ─────────────────────────────────────────────
class AirJetController:
    """
    气喷剔除控制器 — SPEC 2.2.5

    时序:
      air_blast_delay_ms = 15    # 电磁阀响应延迟
      air_blast_duration_ms = 80 # 气喷持续时间
      总延迟 = 95ms
      豆子 T2 后 110ms 离开通道 → 余量 15ms

    触发条件: top 或 bottom 任意一面检测到缺陷 → 气喷剔除
    """

    def __init__(self, valve_pin: int = 16,
                 delay_ms: int = 15, duration_ms: int = 80,
                 simulate: bool = False):
        self.valve_pin = valve_pin
        self.delay_ms = delay_ms
        self.duration_ms = duration_ms
        self.simulate = simulate
        self._reject_count = 0
        self._timer: Optional[threading.Timer] = None

    def trigger_rejection(self, bean_id: int):
        """
        触发气喷剔除（延迟 delay_ms 后开阀，持续 duration_ms 后关阀）

        非阻塞调用。
        """
        def _fire():
            if self.simulate:
                logger.info(f"[AirJet] SIM: bean {bean_id} rejected "
                            f"(delay={self.delay_ms}ms, duration={self.duration_ms}ms)")
                self._reject_count += 1
                return

            try:
                import RPi.GPIO as GPIO
                GPIO.output(self.valve_pin, GPIO.HIGH)  # 开阀
                time.sleep(self.duration_ms / 1000.0)
                GPIO.output(self.valve_pin, GPIO.LOW)   # 关阀
                self._reject_count += 1
            except Exception as e:
                logger.error(f"[AirJet] Valve fire failed: {e}")

        self._timer = threading.Timer(self.delay_ms / 1000.0, _fire)
        self._timer.start()

    def cancel(self):
        """取消待执行的气喷"""
        if self._timer:
            self._timer.cancel()
            self._timer = None

    @property
    def reject_count(self) -> int:
        return self._reject_count


# ─────────────────────────────────────────────
# 双摄像头采集器 — 整合 Top + Bottom + 触发 + 缓冲
# ─────────────────────────────────────────────
class DualCameraCapture:
    """
    双摄像头采集系统 — SPEC 2.2 完整实现

    工作流程:
    1. T1 光电传感器触发 → Top Camera 拍照 → 存入 BeanBuffer
    2. T2 光电传感器触发 → Bottom Camera 拍照 → 从 BeanBuffer 取出配对
    3. 配对完成 → 回调 on_bean_complete(pair) 进行缺陷检测
    4. 任意一面检测到缺陷 → AirJetController 气喷剔除
    """

    def __init__(self, simulate: bool = False,
                 top_resolution: Tuple[int, int] = (2028, 1520),
                 bottom_resolution: Tuple[int, int] = (1920, 1080),
                 t1_pin: int = 4, t2_pin: int = 17,
                 valve_pin: int = 16):
        self.simulate = simulate

        self.top_cam = TopCamera(resolution=top_resolution, simulate=simulate)
        self.bottom_cam = BottomCamera(resolution=bottom_resolution, simulate=simulate)
        self.buffer = BeanBuffer(max_pending=10)
        self.photo_trigger = PhotoelectricTrigger(
            t1_pin=t1_pin, t2_pin=t2_pin, simulate=simulate
        )
        self.air_jet = AirJetController(valve_pin=valve_pin, simulate=simulate)

        # Stats
        self._beans_captured = 0
        self._beans_rejected = 0
        self._pairing_failures = 0

        # User callback for defect detection results
        self.on_defect_result: Optional[Callable[[BeanImagePair, Dict[str, Any]], None]] = None

    def start(self) -> bool:
        """启动双摄像头系统"""
        if not self.top_cam.open():
            return False
        if not self.bottom_cam.open():
            return False

        # Wire T1 → top capture
        self.photo_trigger.on_t1 = self._handle_t1
        # Wire T2 → bottom capture + pair + detect
        self.photo_trigger.on_t2 = self._handle_t2
        # Wire buffer pairing → defect detection callback
        self.buffer.on_bean_ready = self._handle_bean_ready

        self.photo_trigger.start()
        logger.info("[DualCamera] System started")
        return True

    def _handle_t1(self):
        """T1 中断处理: top camera 拍照 → 存入 buffer"""
        top_img = self.top_cam.capture()
        if top_img is not None:
            bean_id = self.buffer.on_t1_trigger(top_img)
            logger.debug(f"T1: bean {bean_id} top captured")
        else:
            logger.warning("T1: top capture failed")

    def _handle_t2(self):
        """T2 中断处理: bottom camera 拍照 → 配对 → 缺陷检测"""
        bottom_img = self.bottom_cam.capture()
        if bottom_img is None:
            logger.warning("T2: bottom capture failed")
            return

        pair = self.buffer.on_t2_trigger(bottom_img)
        if pair is None:
            self._pairing_failures += 1
            logger.warning("T2: no T1 match — bottom image discarded")
        # Pair will trigger buffer.on_bean_ready callback

    def _handle_bean_ready(self, pair: BeanImagePair):
        """Bean 配对完成 — 触发缺陷检测 + 剔除判定"""
        self._beans_captured += 1

        # User-defined defect detection (set by SorterController)
        if self.on_defect_result:
            result = self.on_defect_result(pair)
            if result and result.get("is_defective"):
                self._beans_rejected += 1
                self.air_jet.trigger_rejection(pair.bean_id)
                logger.info(
                    f"Bean {pair.bean_id} REJECTED "
                    f"({result.get('defect_type', '?')})"
                )

    def stop(self):
        """停止系统"""
        self.photo_trigger.stop()
        self.top_cam.close()
        self.bottom_cam.close()
        self.air_jet.cancel()
        logger.info("[DualCamera] System stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "beans_captured": self._beans_captured,
            "beans_rejected": self._beans_rejected,
            "pairing_failures": self._pairing_failures,
            "pending_beans": self.buffer.pending_count,
            "reject_ratio_pct": (
                self._beans_rejected / max(1, self._beans_captured) * 100
            ),
        }


# ─────────────────────────────────────────────
# 快速测试
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    system = DualCameraCapture(simulate=True)
    system.start()

    # Simulate 5 beans passing through
    for i in range(5):
        system._handle_t1()
        time.sleep(0.09)  # ~90ms T1→T2 (per SPEC 40mm gap)
        system._handle_t2()
        time.sleep(0.3)

    print(f"\nStats: {system.stats}")
    system.stop()
