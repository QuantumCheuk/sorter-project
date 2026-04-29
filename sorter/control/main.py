#!/usr/bin/env python3
"""
生豆分选机 - 控制系统核心 / Control System Core
HUSKY-SORTER-001

功能：
  - 主控制循环
  - 状态机管理
  - 传感器集成
  - 事件调度
  - 错误恢复

使用方法：
  python -m sorter.control.main --simulate    # 模拟模式（无硬件）
  python -m sorter.control.main --hardware    # 真实硬件模式
"""

import time
import json
import logging
import threading
import argparse
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timedelta
from collections import deque
import signal
import sys

# =============================================================================
# 日志配置
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("control.main")


# =============================================================================
# 状态机定义
# =============================================================================
class MachineState(Enum):
    """机器主状态"""
    IDLE           = auto()   # 待机
    INITIALIZING   = auto()   # 初始化中
    CALIBRATING    = auto()   # 标定中
    READY          = auto()   # 就绪
    RUNNING        = auto()   # 运行中
    FEEDING        = auto()   # 出豆中
    PAUSED         = auto()   # 暂停
    FAULT          = auto()   # 故障
    ESTOP          = auto()   # 急停


class SubState(Enum):
    """子状态（运行时详细状态）"""
    # IDLE
    IDLE_NO_BEANS      = auto()
    IDLE_BEANS_LOADED  = auto()
    # RUNNING
    RUN_FEEDING        = auto()   # 振动给料
    RUN_SIZING         = auto()   # 尺寸分选
    RUN_COLOR_DETECT   = auto()   # 颜色检测
    RUN_WEIGHING       = auto()   # 称重
    RUN_DENSITY        = auto()   # 密度分选
    RUN_MOISTURE       = auto()   # 含水率检测
    RUN_BUFFERING      = auto()   # 缓冲仓
    # FEEDING
    FEED_SELECTING     = auto()   # 选择仓格
    FEED_DISPENSING    = auto()   # 螺旋给料
    FEED_COMPLETING    = auto()   # 完成出豆


# =============================================================================
# 事件定义
# =============================================================================
class Event(Enum):
    """系统事件"""
    START               = auto()
    STOP                = auto()
    PAUSE               = auto()
    RESUME              = auto()
    ESTOP               = auto()
    RESET               = auto()
    LOAD_BEANS          = auto()
    BATCH_START         = auto()
    BATCH_FEED_COMPLETE = auto()
    UPSTREAM_READY       = auto()
    BEAN_DETECTED       = auto()   # 光电传感器触发
    WEIGHT_MEASURED    = auto()
    QUALITY_CLASSIFIED  = auto()
    FAULT_DETECTED      = auto()
    CALIBRATE_ALL       = auto()


@dataclass
class BeanRecord:
    """单粒豆子数据记录"""
    bean_id:        int
    timestamp:      str = field(default_factory=lambda: datetime.now().isoformat())
    size_grade:    Optional[int] = None
    weight_g:      Optional[float] = None
    density_class: Optional[str] = None
    moisture_pct:  Optional[float] = None
    color_defect:  bool = False
    color_score:   Optional[float] = None
    quality_class: Optional[str] = None
    is_rejected:   bool = False
    reject_reason: Optional[str] = None
    channel_id:    int = 1


@dataclass
class BatchRecord:
    """批次记录"""
    batch_id:        str
    timestamp:       str = field(default_factory=lambda: datetime.now().isoformat())
    metadata:        Dict[str, Any] = field(default_factory=dict)
    beans:            List[BeanRecord] = field(default_factory=list)
    feed_plan:        List[Dict[str, Any]] = field(default_factory=list)
    feed_sequence:    int = 0
    total_weight_kg:  float = 0.0


# =============================================================================
# 传感器接口基类
# =============================================================================
class SensorBase:
    """传感器基类"""
    def __init__(self, name: str, simulate: bool = True):
        self.name = name
        self.simulate = simulate
        self._last_reading: Any = None
        self._error_count: int = 0
        self.logger = logging.getLogger(f"sensor.{name}")

    def read(self) -> Optional[Any]:
        """读取传感器数据"""
        raise NotImplementedError

    def is_ready(self) -> bool:
        """传感器是否就绪"""
        raise NotImplementedError

    def calibrate(self, params: Dict[str, Any]) -> bool:
        """标定传感器"""
        raise NotImplementedError


class T1Sensor(SensorBase):
    """顶部光电传感器 T1 — 触发顶部相机"""
    def __init__(self, pin: int = 4, simulate: bool = True):
        super().__init__("T1", simulate)
        self.pin = pin
        self._triggered = False

    def read(self) -> bool:
        """返回 True = 触发（有豆遮挡）"""
        if self.simulate:
            # 模拟模式：周期性触发
            return (time.time() % 2.0) < 0.05  # ~50ms 触发
        # 真实GPIO读取
        # return GPIO.input(self.pin) == 0  # 遮断式：低=遮断
        return False

    def is_ready(self) -> bool:
        return True


class T2Sensor(SensorBase):
    """底部光电传感器 T2 — 触发底部相机"""
    def __init__(self, pin: int = 17, simulate: bool = True):
        super().__init__("T2", simulate)
        self.pin = pin

    def read(self) -> bool:
        if self.simulate:
            return (time.time() % 2.0) < 0.05
        return False

    def is_ready(self) -> bool:
        return True


class HX711Sensor(SensorBase):
    """称重传感器 HX711 + Load Cell"""
    def __init__(self, dt_pin: int = 5, sck_pin: int = 27,
                 simulate: bool = True, noise_std_mg: float = 1.0):
        super().__init__("HX711", simulate)
        self.dt_pin = dt_pin
        self.sck_pin = sck_pin
        self.noise_std_mg = noise_std_mg
        self._calibration_offset = 0.0
        self._calibration_scale = 1.0

    def read(self) -> Optional[float]:
        """
        读取重量，单位：g
        返回 None 表示无效读数（豆子未落杯或超量程）
        """
        if self.simulate:
            # 模拟：正常豆 0.12-0.20g 高斯噪声
            import random
            noise = random.gauss(0, self.noise_std_mg / 1000.0)  # mg → g
            base = 0.15  # g
            return base + noise
        # 真实 HX711 读取
        # value = hx711.get_weight(5)  # 5次平均
        # return value * self._calibration_scale + self._calibration_offset
        return None

    def is_ready(self) -> bool:
        return True

    def calibrate(self, params: Dict[str, Any]) -> bool:
        """两点标定"""
        known_weight = params.get("known_weight_g", 100.0)
        raw_value = params.get("raw_value", 100000)
        self._calibration_scale = known_weight / raw_value
        self.logger.info(f"HX711 calibrated: scale={self._calibration_scale:.6f}")
        return True


class MoistureSensor(SensorBase):
    """含水率传感器 AD7746"""
    def __init__(self, i2c_bus: int = 1, simulate: bool = True):
        super().__init__("AD7746", simulate)
        self.i2c_bus = i2c_bus
        self._intercept = -0.034  # pF 截距
        self._slope = 0.206       # pF / % 含水率

    def read(self) -> Optional[float]:
        """读取含水率，单位：%"""
        if self.simulate:
            import random
            base = 11.0  # 11% 含水率
            return base + random.gauss(0, 0.3)
        # 真实 I2C 读取
        # cap = ad7746.read_capacitance()
        # moisture = (cap - self._intercept) / self._slope
        # return max(5.0, min(15.0, moisture))
        return None

    def is_ready(self) -> bool:
        return True


class ColorCamera(SensorBase):
    """颜色检测相机（双摄像头系统）"""
    def __init__(self, simulate: bool = True):
        super().__init__("color_camera", simulate)
        self._buffer: Dict[int, Dict] = {}  # bean_id → {top_img, bottom_img, ...}
        self._next_bean_id = 1

    def capture_top(self) -> Optional[Dict]:
        if self.simulate:
            bean_id = self._next_bean_id
            self._next_bean_id += 1
            self._buffer[bean_id] = {"bean_id": bean_id, "top": True, "bottom": None}
            return {"bean_id": bean_id, "image_captured": True}
        # 真实相机
        # ret, frame = top_camera.read()
        # return {"bean_id": bean_id, "image": frame} if ret else None
        return None

    def capture_bottom(self, bean_id: int) -> Optional[Dict]:
        if self.simulate:
            if bean_id in self._buffer:
                self._buffer[bean_id]["bottom"] = True
                return {"bean_id": bean_id, "image_captured": True}
            return None
        return None

    def analyze(self, bean_id: int) -> Dict[str, Any]:
        """分析豆子颜色，返回缺陷结果"""
        if self.simulate:
            import random
            # 95% 概率正常，5% 概率有缺陷
            is_defect = random.random() < 0.05
            return {
                "bean_id": bean_id,
                "is_defect": is_defect,
                "defect_type": "mold" if is_defect else None,
                "color_score": random.uniform(80, 98) if not is_defect else random.uniform(40, 70),
                "l_star": random.uniform(40, 55),
                "a_star": random.uniform(3, 12),
                "b_star": random.uniform(15, 30),
            }
        return {"bean_id": bean_id, "is_defect": False, "color_score": 95.0}

    def is_ready(self) -> bool:
        return True


# =============================================================================
# 执行器接口
# =============================================================================
class ActuatorBase:
    def __init__(self, name: str, simulate: bool = True):
        self.name = name
        self.simulate = simulate
        self._is_active = False
        self.logger = logging.getLogger(f"actuator.{name}")

    def activate(self, duration_ms: Optional[int] = None) -> None:
        """激活执行器"""
        raise NotImplementedError

    def deactivate(self) -> None:
        """关闭执行器"""
        raise NotImplementedError

    def is_active(self) -> bool:
        return self._is_active


class AirJetValve(ActuatorBase):
    """气喷电磁阀 — 缺陷豆剔除"""
    def __init__(self, pin: int = 16, simulate: bool = True):
        super().__init__("air_jet", simulate)
        self.pin = pin
        self._open_duration_ms = 80

    def activate(self, duration_ms: Optional[int] = None) -> None:
        """打开气喷，duration_ms后自动关闭"""
        if self._is_active:
            return
        dur = duration_ms or self._open_duration_ms
        self._is_active = True
        self.logger.debug(f"Air jet ON ({dur}ms)")
        if not self.simulate:
            # GPIO.output(self.pin, GPIO.HIGH)
            pass
        # 模拟：自动关闭
        if dur > 0:
            def close():
                time.sleep(dur / 1000.0)
                self.deactivate()
            threading.Thread(target=close, daemon=True).start()

    def deactivate(self) -> None:
        if not self._is_active:
            return
        self._is_active = False
        if not self.simulate:
            # GPIO.output(self.pin, GPIO.LOW)
            pass

    def eject_bean(self, bean_record: BeanRecord) -> None:
        """执行单粒豆子剔除"""
        bean_record.is_rejected = True
        bean_record.reject_reason = "color_defect"
        self.logger.info(f"Bean {bean_record.bean_id} REJECTED: {bean_record.reject_reason}")
        self.activate(self._open_duration_ms)


class VibratingFeeder(ActuatorBase):
    """振动给料器 — Nema17 or 28BYJ-48"""
    def __init__(self, simulate: bool = True, target_bpm: int = 50):
        super().__init__("vibrating_feeder", simulate)
        self.target_bpm = target_bpm
        self._speed_pwm = 0  # 0-1023

    def set_speed(self, bpm: int) -> None:
        """设置给料速度 BPM"""
        self.target_bpm = bpm
        # 计算 PWM 占空比
        # 50bpm → 120RPM 电机转速 → PWM映射
        pwm = int(bpm * 1024 / 60)
        self._speed_pwm = min(1023, pwm)
        if not self.simulate:
            # GPIO.PWM(gpio_pin, freq).start(duty)
            pass
        self.logger.debug(f"Vibrating feeder speed set to {bpm} bpm")

    def start(self) -> None:
        self._is_active = True
        if not self.simulate:
            pass  # 启动 PWM

    def stop(self) -> None:
        self._is_active = False
        if not self.simulate:
            pass


class WeighingCupRelease(ActuatorBase):
    """称重杯释放电磁阀"""
    def __init__(self, pin: int = 20, simulate: bool = True):
        super().__init__("weighing_release", simulate)
        self.pin = pin

    def activate(self, duration_ms: Optional[int] = None) -> None:
        """打开释放门，30ms后关闭"""
        self._is_active = True
        if not self.simulate:
            # GPIO.output(self.pin, GPIO.HIGH)
            pass
        def close():
            time.sleep(0.030)
            self.deactivate()
        threading.Thread(target=close, daemon=True).start()

    def deactivate(self) -> None:
        self._is_active = False
        if not self.simulate:
            # GPIO.output(self.pin, GPIO.LOW)
            pass


# =============================================================================
# 主控制器
# =============================================================================
class SorterController:
    """
    生豆分选机主控制器

    负责：
    - 状态机管理
    - 传感器轮询
    - 执行器控制
    - 批次管理
    - MQTT/Roaster 接口协调
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.simulate = config.get("simulate", True)
        self._state = MachineState.IDLE
        self._substate = SubState.IDLE_NO_BEANS
        self._prev_state = MachineState.IDLE

        # 事件队列
        self._event_queue: deque[Event] = deque(maxlen=100)

        # 传感器实例化
        self.t1_sensor = T1Sensor(simulate=self.simulate)
        self.t2_sensor = T2Sensor(simulate=self.simulate)
        self.hx711 = HX711Sensor(simulate=self.simulate)
        self.moisture_sensor = MoistureSensor(simulate=self.simulate)
        self.top_camera = ColorCamera(simulate=self.simulate)

        # 执行器实例化
        self.air_jet = AirJetValve(simulate=self.simulate)
        self.vibrating_feeder = VibratingFeeder(simulate=self.simulate)
        self.weighing_release = WeighingCupRelease(simulate=self.simulate)

        # 数据存储
        self._current_batch: Optional[BatchRecord] = None
        self._bean_counter = 0
        self._bean_buffer: Dict[int, BeanRecord] = {}  # bean_id → record
        self._recent_beans: deque[BeanRecord] = deque(maxlen=1000)

        # 统计
        self._stats = {
            "total_beans": 0,
            "rejected_beans": 0,
            "uptime_seconds": 0.0,
            "fault_count": 0,
        }

        # 运行控制
        self._running = False
        self._pause_event = threading.Event()
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None

        logger.info(f"SorterController initialized (simulate={self.simulate})")

    # -------------------------------------------------------------------------
    # 状态机
    # -------------------------------------------------------------------------
    @property
    def state(self) -> MachineState:
        return self._state

    @property
    def substate(self) -> SubState:
        return self._substate

    def transition(self, new_state: MachineState, new_substate: Optional[SubState] = None) -> None:
        """状态转换"""
        with self._lock:
            self._prev_state = self._state
            self._state = new_state
            if new_substate is not None:
                self._substate = new_substate
            logger.info(f"STATE: {self._prev_state.name} → {new_state.name}"
                        + (f" / {new_substate.name}" if new_substate else ""))

    def post_event(self, event: Event, data: Optional[Dict] = None) -> None:
        """发送事件到队列"""
        self._event_queue.append((event, data))
        logger.debug(f"EVENT: {event.name}" + (f" data={data}" if data else ""))

    def process_events(self) -> None:
        """处理事件队列（非阻塞）"""
        while self._event_queue:
            event, data = self._event_queue.popleft()
            self._handle_event(event, data)

    def _handle_event(self, event: Event, data: Optional[Dict]) -> None:
        """处理单个事件"""
        handler_map: Dict[Event, Callable] = {
            Event.START:               self._on_start,
            Event.STOP:                self._on_stop,
            Event.PAUSE:              self._on_pause,
            Event.RESUME:             self._on_resume,
            Event.ESTOP:              self._on_estop,
            Event.RESET:              self._on_reset,
            Event.LOAD_BEANS:         self._on_load_beans,
            Event.BATCH_START:        self._on_batch_start,
            Event.BATCH_FEED_COMPLETE: self._on_batch_feed_complete,
            Event.UPSTREAM_READY:     self._on_upstream_ready,
            Event.FAULT_DETECTED:     self._on_fault,
            Event.CALIBRATE_ALL:      self._on_calibrate_all,
        }
        handler = handler_map.get(event)
        if handler:
            handler(data or {})

    # -------------------------------------------------------------------------
    # 事件处理器
    # -------------------------------------------------------------------------
    def _on_start(self, data: Dict) -> None:
        if self._state in (MachineState.IDLE, MachineState.READY):
            self.transition(MachineState.INITIALIZING)
            # 初始化序列
            self._init_sequence()

    def _init_sequence(self) -> None:
        """初始化序列：传感器自检 → 归位 → 就绪"""
        logger.info("Running init sequence...")
        if not self.simulate:
            # 真实硬件初始化
            # self._homing()  # 步进电机归位
            # self._check_sensors()
            pass
        self.transition(MachineState.READY, SubState.IDLE_NO_BEANS)
        logger.info("Init complete — READY")

    def _on_stop(self, data: Dict) -> None:
        """停止 — 关闭执行器，记录状态"""
        self.vibrating_feeder.stop()
        self.air_jet.deactivate()
        self.transition(MachineState.IDLE)

    def _on_pause(self, data: Dict) -> None:
        if self._state == MachineState.RUNNING:
            self.vibrating_feeder.stop()
            self.transition(MachineState.PAUSED)
            self._pause_event.set()

    def _on_resume(self, data: Dict) -> None:
        if self._state == MachineState.PAUSED:
            self._pause_event.clear()
            self.transition(MachineState.RUNNING)

    def _on_estop(self, data: Dict) -> None:
        """急停 — 立即关闭所有执行器"""
        logger.warning("E-STOP triggered!")
        self.vibrating_feeder.stop()
        self.air_jet.deactivate()
        self.weighing_release.deactivate()
        self.transition(MachineState.ESTOP)

    def _on_reset(self, data: Dict) -> None:
        """复位 — 从故障/急停恢复到待机"""
        self._stats["fault_count"] = 0
        self.transition(MachineState.IDLE)

    def _on_load_beans(self, data: Dict) -> None:
        """有料倒入 — 切换到待机有料状态"""
        if self._state == MachineState.READY:
            self.transition(MachineState.READY, SubState.IDLE_BEANS_LOADED)
        elif self._state in (MachineState.IDLE,):
            self._on_start({})
            self.transition(MachineState.READY, SubState.IDLE_BEANS_LOADED)

    def _on_batch_start(self, data: Dict) -> None:
        """开始新批次"""
        batch_id = data.get("batch_id", f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        self._current_batch = BatchRecord(
            batch_id=batch_id,
            metadata=data.get("metadata", {}),
            feed_plan=data.get("feed_plan", []),
        )
        self._bean_counter = 0
        self.transition(MachineState.RUNNING, SubState.RUN_FEEDING)
        self.vibrating_feeder.start()
        logger.info(f"Batch started: {batch_id}")

    def _on_batch_feed_complete(self, data: Dict) -> None:
        """批次出豆完成"""
        self.transition(MachineState.READY)
        logger.info("Batch feed complete — READY")

    def _on_upstream_ready(self, data: Dict) -> None:
        """烘豆机 UPSTREAM_READY=1 — 准备出豆"""
        if self._state == MachineState.READY and self._current_batch:
            self.transition(MachineState.FEEDING, SubState.FEED_SELECTING)
            self._start_feeding()

    def _on_fault(self, data: Dict) -> None:
        """故障"""
        fault_type = data.get("type", "unknown")
        severity = data.get("severity", "medium")
        logger.error(f"FAULT: {fault_type} (severity={severity})")
        self._stats["fault_count"] += 1
        self.vibrating_feeder.stop()
        self.transition(MachineState.FAULT)

    def _on_calibrate_all(self, data: Dict) -> None:
        """全标定流程"""
        self.transition(MachineState.CALIBRATING)
        logger.info("Calibrating all sensors...")
        # 颜色预热 + 白板
        logger.info("  [Color]  Warming up camera...")
        time.sleep(5)  # 预热
        # 称重去皮
        logger.info("  [Weight] Taring...")
        # 含水率基线
        logger.info("  [Moisture] Reading baseline...")
        self.transition(MachineState.READY)

    # -------------------------------------------------------------------------
    # 运行循环
    # -------------------------------------------------------------------------
    def run(self) -> None:
        """启动主控制循环"""
        self._running = True
        self._start_time = time.time()
        logger.info("Main control loop started")

        try:
            while self._running:
                self._pause_event.wait()  # 暂停时阻塞
                self.process_events()
                self._poll_sensors()
                self._update_stats()
                time.sleep(0.005)  # ~200Hz 轮询
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — stopping")
            self._on_estop({})

    def _poll_sensors(self) -> None:
        """传感器轮询 — 非阻塞采集"""
        if self._state != MachineState.RUNNING:
            return

        # T1 触发 → 顶部相机拍摄
        if self.t1_sensor.read():
            self._handle_t1_trigger()

        # T2 触发 → 底部相机拍摄（配合buffer中的记录）
        if self.t2_sensor.read():
            self._handle_t2_trigger()

        # 称重（模拟：周期性读取）
        if self._substate == SubState.RUN_WEIGHING:
            weight = self.hx711.read()
            if weight is not None:
                self._handle_weight_measured(weight)

        # 含水率
        if self._substate == SubState.RUN_MOISTURE:
            moisture = self.moisture_sensor.read()
            if moisture is not None:
                self._handle_moisture_measured(moisture)

    def _handle_t1_trigger(self) -> None:
        """T1触发：顶部相机拍摄"""
        result = self.top_camera.capture_top()
        if result:
            bean_id = result["bean_id"]
            record = BeanRecord(bean_id=bean_id)
            self._bean_buffer[bean_id] = record
            self._bean_counter += 1
            logger.debug(f"Bean {bean_id}: T1 triggered, top captured")

    def _handle_t2_trigger(self) -> None:
        """T2触发：底部相机拍摄 + 颜色分析 + 决定剔除"""
        # 找到最新未处理的 bean
        if not self._bean_buffer:
            return
        bean_id = max(self._bean_buffer.keys())
        record = self._bean_buffer[bean_id]

        self.top_camera.capture_bottom(bean_id)
        color_result = self.top_camera.analyze(bean_id)

        record.color_defect = color_result["is_defect"]
        record.color_score = color_result["color_score"]
        self._stats["total_beans"] += 1

        if record.color_defect:
            self.air_jet.eject_bean(record)
        else:
            # 正常豆进入称重
            self.transition(MachineState.RUNNING, SubState.RUN_WEIGHING)

        # 清理 buffer（不再需要）
        del self._bean_buffer[bean_id]
        self._recent_beans.append(record)

    def _handle_weight_measured(self, weight: float) -> None:
        """称重完成"""
        if self._recent_beans:
            latest = self._recent_beans[-1]
            if latest.weight_g is None:
                latest.weight_g = weight
                self.transition(MachineState.RUNNING, SubState.RUN_MOISTURE)
                logger.debug(f"Bean {latest.bean_id}: weight={weight*1000:.1f}mg")

    def _handle_moisture_measured(self, moisture: float) -> None:
        """含水率测量完成"""
        if self._recent_beans:
            latest = self._recent_beans[-1]
            latest.moisture_pct = moisture
            self._classify_quality(latest)
            self.transition(MachineState.RUNNING, SubState.RUN_BUFFERING)
            logger.debug(f"Bean {latest.bean_id}: moisture={moisture:.2f}%")

    def _classify_quality(self, record: BeanRecord) -> None:
        """品质分类"""
        score = record.color_score or 50.0
        weight = record.weight_g or 0.15
        # 简化分类逻辑（实际应查表）
        if record.color_defect:
            record.quality_class = "REJECT"
        elif score >= 90 and 0.12 <= weight <= 0.22:
            record.quality_class = "A"
        elif score >= 75:
            record.quality_class = "B"
        else:
            record.quality_class = "C"

    def _start_feeding(self) -> None:
        """开始出豆流程"""
        if not self._current_batch:
            return
        batch = self._current_batch
        batch.feed_sequence += 1
        portion = batch.feed_plan[batch.feed_sequence - 1]["portion_kg"] if \
                  batch.feed_sequence <= len(batch.feed_plan) else 0.25

        self.transition(MachineState.FEEDING, SubState.FEED_DISPENSING)
        logger.info(f"Feeding seq #{batch.feed_sequence}: {portion*1000:.0f}g")
        # 螺旋给料器启动（模拟定时关闭）
        def feed_done():
            time.sleep(0.5)  # 模拟出豆时间
            self.post_event(Event.BATCH_FEED_COMPLETE, {"sequence": batch.feed_sequence})
        threading.Thread(target=feed_done, daemon=True).start()

    def _update_stats(self) -> None:
        """更新统计"""
        if self._start_time:
            self._stats["uptime_seconds"] = time.time() - self._start_time

    # -------------------------------------------------------------------------
    # 外部查询接口
    # -------------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """获取状态快照"""
        return {
            "state": self._state.name,
            "substate": self._substate.name,
            "stats": dict(self._stats),
            "current_batch": self._current_batch.batch_id if self._current_batch else None,
            "buffer_size": len(self._bean_buffer),
            "recent_beans_count": len(self._recent_beans),
        }

    def get_recent_beans(self, n: int = 100) -> List[Dict]:
        """获取最近 n 粒豆子的数据"""
        beans = list(self._recent_beans)[-n:]
        return [asdict(b) for b in beans]

    def stop(self) -> None:
        """停止主循环"""
        self._running = False


# =============================================================================
# 信号处理
# =============================================================================
class SignalHandler:
    def __init__(self, controller: SorterController):
        self.controller = controller
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

    def setup(self) -> None:
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)

    def _handler(self, signum, frame) -> None:
        logger.info(f"Signal {signum} received")
        self.controller.post_event(Event.ESTOP)
        time.sleep(0.1)
        self.controller.stop()
        sys.exit(0)


# =============================================================================
# CLI 入口
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 Control System")
    parser.add_argument("--simulate", action="store_true", default=True,
                        help="Simulation mode (default: True)")
    parser.add_argument("--hardware", dest="simulate", action="store_false",
                        help="Hardware mode (real GPIO/I2C)")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    config = {"simulate": args.simulate}
    controller = SorterController(config)

    # 信号处理
    sh = SignalHandler(controller)
    sh.setup()

    # 启动主循环（子线程）
    loop_thread = threading.Thread(target=controller.run, daemon=True)
    loop_thread.start()

    # CLI 交互
    print("HUSKY-SORTER-001 Control System")
    print("Commands: start | stop | load | batch | status | beans | estop | quit")
    print("-" * 50)

    try:
        while True:
            cmd = input("> ").strip().lower()
            if not cmd:
                continue

            if cmd in ("start", "s"):
                controller.post_event(Event.START)
            elif cmd in ("stop",):
                controller.post_event(Event.STOP)
            elif cmd in ("load", "l"):
                controller.post_event(Event.LOAD_BEANS)
            elif cmd in ("batch", "b"):
                controller.post_event(Event.BATCH_START, {
                    "batch_id": f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                    "metadata": {"origin": "Ethiopia Yirgacheffe"},
                    "feed_plan": [
                        {"portion_kg": 0.250, "feed_sequence": 1},
                        {"portion_kg": 0.250, "feed_sequence": 2},
                    ]
                })
            elif cmd in ("status", "st"):
                print(json.dumps(controller.get_status(), indent=2, default=str))
            elif cmd in ("beans",):
                beans = controller.get_recent_beans(10)
                print(json.dumps(beans, indent=2, default=str))
            elif cmd in ("upstream", "ready"):
                controller.post_event(Event.UPSTREAM_READY)
            elif cmd in ("cal",):
                controller.post_event(Event.CALIBRATE_ALL)
            elif cmd in ("estop", "e"):
                controller.post_event(Event.ESTOP)
            elif cmd in ("quit", "q", "exit"):
                controller.post_event(Event.ESTOP)
                controller.stop()
                break
            else:
                print(f"Unknown command: {cmd}")
    except EOFError:
        controller.stop()


if __name__ == "__main__":
    main()
