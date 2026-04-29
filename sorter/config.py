#!/usr/bin/env python3
"""
系统配置参数 / System Configuration
HUSKY-SORTER-001

所有可配置参数集中管理，支持：
  - 文件加载（JSON/YAML）
  - 环境变量覆盖
  - 运行时修改
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger("config")


# =============================================================================
# 配置类定义
# =============================================================================
@dataclass
class GPIOConfig:
    """GPIO 引脚分配"""
    # 传感器输入
    T1_SENSOR:       int = 4    # 顶部光电传感器
    T2_SENSOR:       int = 17   # 底部光电传感器
    HX711_DT:        int = 5    # HX711 Data
    LEVEL_SENSOR:    int = 24   # 液位传感器 DATA

    # 执行器输出
    AIR_JET_VALVE:   int = 16   # 气喷电磁阀
    WEIGHING_RELEASE:int = 20   # 称重杯释放电磁阀
    BUFFER_SELECT:   int = 21   # 缓冲仓分配器选择阀

    # 步进电机
    FEEDER_PUL:      int = 26   # 振动给料 PUL
    FEEDER_DIR:      int = 19   # 振动给料 DIR
    DISTRIBUTOR_PUL: int = 13   # 旋转分配器 PUL
    DISTRIBUTOR_DIR: int = 12   # 旋转分配器 DIR
    SPIRAL_PUL:      int = 18   # 螺旋给料 PUL
    SPIRAL_DIR:      int = 23   # 螺旋给料 DIR

    # 专用功能
    HX711_SCK:       int = 27   # HX711 Clock (已从GPIO6迁移 ✅)
    LEVEL_SENSOR_CLK:int = 25   # 液位传感器 CLK
    FAN_PWM:         int = 12   # 5015风扇 PWM

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> "GPIOConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SensorConfig:
    """传感器配置"""
    # 颜色检测
    color_top_enabled:    bool = True
    color_bottom_enabled: bool = True
    color_preheat_sec:    int = 10

    # 称重
    weight_samples:       int = 5      # HX711 采样次数
    weight_tare_interval: float = 30.0  # 自动去皮间隔 (s)
    weight_noise_std_mg:  float = 1.0  # 模拟噪声 (mg)

    # 含水率
    moisture_samples:     int = 5
    moisture_probe_gap_mm:float = 8.0  # 探头极板间隙

    # 密度
    density_fan_type:     str = "5015"  # "5015" | "turbo"
    density_pwm_default: int = 512    # 默认 PWM (0-1023)


@dataclass
class MotorConfig:
    """电机配置"""
    feeder_type:          str = "Nema17"   # "28BYJ-48" | "Nema17"
    feeder_microstep:     int = 8
    feeder_target_bpm:    int = 50        # 目标给料速率
    distributor_type:     str = "Nema17"
    distributor_microstep:int = 8
    spiral_type:          str = "28BYJ-48"
    spiral_microstep:     int = 8


@dataclass
class MQTTConfig:
    """MQTT 配置"""
    broker_host:    str = "localhost"
    broker_port:    int = 1883
    client_id:      str = "sorter-01"
    username:       Optional[str] = None
    password:      Optional[str] = None
    qos:            int = 1
    keepalive:      int = 60

    topics_sorter:  List[str] = field(default_factory=lambda: [
        "sorter/01/batch/output",
        "sorter/01/batch/feed",
        "sorter/01/status",
    ])
    topics_roaster: List[str] = field(default_factory=lambda: [
        "roaster/01/batch/input",
        "roaster/01/status",
    ])


@dataclass
class APIConfig:
    """REST API 配置"""
    host:           str = "0.0.0.0"
    port:           int = 5000
    debug:          bool = False
    auth_required:  bool = False


@dataclass
class BatchConfig:
    """批次处理配置"""
    default_portion_g:   float = 250.0  # 默认每份重量 (g)
    max_portions:        int = 10        # 最大份数
    min_single_bean_g:   float = 0.05   # 单粒豆最小重量 (g)
    max_single_bean_g:   float = 0.5    # 单粒豆最大重量 (g)


@dataclass
class QualityThresholds:
    """品质分类阈值"""
    # 颜色评分 (0-100)
    color_a_min:     float = 90.0
    color_b_min:     float = 75.0

    # 单粒重量 (g)
    weight_a_min_g:  float = 0.12
    weight_a_max_g:  float = 0.22
    weight_b_min_g:  float = 0.08
    weight_b_max_g:  float = 0.30

    # 含水率 (%)
    moisture_min:    float = 9.0
    moisture_max:    float = 13.0

    # 密度 (g/mL)
    density_light:   float = 0.60
    density_heavy:   float = 0.72

    # 尺寸 (目数)
    size_min:        int = 12
    size_max:        int = 20


# =============================================================================
# 主配置类
# =============================================================================
@dataclass
class SystemConfig:
    """系统总配置"""
    device_id:          str = "sorter-01"
    simulate:           bool = True
    log_level:          str = "INFO"

    gpio:               GPIOConfig = field(default_factory=GPIOConfig)
    sensor:             SensorConfig = field(default_factory=SensorConfig)
    motor:              MotorConfig = field(default_factory=MotorConfig)
    mqtt:               MQTTConfig = field(default_factory=MQTTConfig)
    api:                APIConfig = field(default_factory=APIConfig)
    batch:              BatchConfig = field(default_factory=BatchConfig)
    quality:            QualityThresholds = field(default_factory=QualityThresholds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "simulate": self.simulate,
            "log_level": self.log_level,
            "gpio": asdict(self.gpio),
            "sensor": asdict(self.sensor),
            "motor": asdict(self.motor),
            "mqtt": asdict(self.mqtt),
            "api": asdict(self.api),
            "batch": asdict(self.batch),
            "quality": asdict(self.quality),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SystemConfig":
        gpio = GPIOConfig.from_dict(d.get("gpio", {}))
        sensor_cfg = d.get("sensor", {})
        motor_cfg = d.get("motor", {})
        mqtt_cfg = d.get("mqtt", {})
        api_cfg = d.get("api", {})
        batch_cfg = d.get("batch", {})
        quality_cfg = d.get("quality", {})

        return cls(
            device_id=d.get("device_id", "sorter-01"),
            simulate=d.get("simulate", True),
            log_level=d.get("log_level", "INFO"),
            gpio=gpio,
            sensor=SensorConfig(**sensor_cfg) if sensor_cfg else SensorConfig(),
            motor=MotorConfig(**motor_cfg) if motor_cfg else MotorConfig(),
            mqtt=MQTTConfig(**mqtt_cfg) if mqtt_cfg else MQTTConfig(),
            api=APIConfig(**api_cfg) if api_cfg else APIConfig(),
            batch=BatchConfig(**batch_cfg) if batch_cfg else BatchConfig(),
            quality=QualityThresholds(**quality_cfg) if quality_cfg else QualityThresholds(),
        )

    def save(self, path: str) -> None:
        """保存配置到 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Config saved to {path}")

    @classmethod
    def load(cls, path: str) -> "SystemConfig":
        """从 JSON 文件加载配置"""
        if not os.path.exists(path):
            logger.warning(f"Config file not found: {path} — using defaults")
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        logger.info(f"Config loaded from {path}")
        return cls.from_dict(d)

    def apply_env_overrides(self) -> None:
        """从环境变量覆盖配置"""
        # SIMULATE=0/1
        if "SORTER_SIMULATE" in os.environ:
            self.simulate = os.environ["SORTER_SIMULATE"] != "0"
            logger.info(f"simulate overridden by env: {self.simulate}")

        # LOG_LEVEL
        if "SORTER_LOG_LEVEL" in os.environ:
            self.log_level = os.environ["SORTER_LOG_LEVEL"]
            logger.info(f"log_level overridden by env: {self.log_level}")

        # MQTT overrides
        if "SORTER_MQTT_HOST" in os.environ:
            self.mqtt.broker_host = os.environ["SORTER_MQTT_HOST"]
        if "SORTER_MQTT_PORT" in os.environ:
            self.mqtt.broker_port = int(os.environ["SORTER_MQTT_PORT"])

        # DEVICE_ID
        if "SORTER_DEVICE_ID" in os.environ:
            self.device_id = os.environ["SORTER_DEVICE_ID"]


# =============================================================================
# 全局配置实例（支持运行时修改）
# =============================================================================
DEFAULT_CONFIG_PATH = os.environ.get(
    "SORTER_CONFIG",
    "/etc/sorter/config.json"
)

_config_instance: Optional[SystemConfig] = None


def get_config() -> SystemConfig:
    """获取全局配置单例"""
    global _config_instance
    if _config_instance is None:
        if os.path.exists(DEFAULT_CONFIG_PATH):
            _config_instance = SystemConfig.load(DEFAULT_CONFIG_PATH)
        else:
            _config_instance = SystemConfig()
        _config_instance.apply_env_overrides()
    return _config_instance


def reload_config(path: Optional[str] = None) -> SystemConfig:
    """重新加载配置"""
    global _config_instance
    if path:
        _config_instance = SystemConfig.load(path)
    else:
        _config_instance = SystemConfig()
    _config_instance.apply_env_overrides()
    return _config_instance
