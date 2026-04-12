"""
config.py - 系统配置
HUSKY-SORTER-001
"""

import os

# ===== 硬件配置 =====
HW_CONFIG = {
    # 树莓派
    "pi_model": "4B",
    "pi_revision": "2GB",

    # 摄像头
    "camera_type": "HQ",          # "HQ" or "USB"
    "camera_resolution": (4056, 3040),
    "camera_fps": 30,
    "lens_focal_length": 6,       # mm, M12镜头

    # LED光源
    "led_count": 4,
    "led_type": "ring",           # "ring" or "strip"
    "led_color": "warm_white",     # 暖白光 ~3200K
    "led_voltage": 5,              # V
    "led_current": 0.5,            # A per LED

    # 称重
    "load_cell_capacity": 200,    # g
    "load_cell_precision": 0.01,   # g
    "hx711_gain": 128,

    # 电机
    "stepper_type": "28BYJ-48",
    "stepper_count": 3,            # 振动给料/尺寸分选/螺旋给料
    "stepper_steps_per_rev": 4096, # 28BYJ-48 完整步数

    # 气流密度分选
    "fan_type": "5015",
    "fan_voltage": 5,
    "fan_max_rpm": 15000,

    # 含水率
    "moisture_range": (5, 15),    # %
    "moisture_precision": 0.5,     # %
    "capacitor_probe_gap": 5,     # mm
    "capacitor_plate_area": 500,  # mm²
}

# ===== 软件配置 =====
SW_CONFIG = {
    # MQTT
    "mqtt_broker": "mqtt.local",
    "mqtt_port": 1883,
    "mqtt_keepalive": 60,
    "mqtt_qos": 1,

    # REST API
    "api_host": "0.0.0.0",
    "api_port": 5000,
    "api_debug": False,

    # 数据库
    "db_path": "/var/sorter/batches.db",

    # 图像处理
    "image_benchmark_frames": 10,  # 平均降噪帧数
    "blob_min_area": 100,          # 最小豆子像素面积
    "blob_max_area": 50000,        # 最大豆子像素面积

    # 颜色分析
    "lab_color_space": True,
    "defect_detection_mode": "rule",  # "rule" or "ml"
}

# ===== 分选参数 =====
SORT_CONFIG = {
    # 尺寸分选
    "size_grades": [16, 15, 14, 13, 12],  # 目数
    "size_tolerance": 0.5,                 # ±目

    # 密度分选
    "density_grades": ["light", "medium", "heavy"],
    "density_thresholds": {
        "light": ("<", 0.60),
        "medium": ("=", (0.60, 0.72)),
        "heavy": (">", 0.72),
    },

    # 含水率
    "moisture_min": 5.0,    # %
    "moisture_max": 15.0,  # %
    "moisture_optimal": (10.0, 12.5),  # % 最佳范围

    # 颜色评分
    "color_score_thresholds": {
        "A": 85,   # ≥85 = A级
        "B": 70,   # ≥70 = B级
        "C": 50,   # ≥50 = C级
    },

    # 缺陷阈值
    "defect_rate_max": {
        "A": 1.0,  # %
        "B": 3.0,
        "C": 5.0,
    },
}

# ===== 品种/处理法参考数据 =====
# 预置参考范围（需实测标定）
VARIETY_REFERENCES = {
    # 品种 → {处理法 → {L_range, a_range, b_range}}
    "Heirloom": {
        "水洗": {"L": (35, 50), "a": (-1, 5), "b": (12, 25)},
        "日晒": {"L": (38, 55), "a": (-2, 6), "b": (15, 30)},
        "蜜处理": {"L": (36, 52), "a": (-1, 6), "b": (14, 28)},
    },
    "Geisha": {
        "水洗": {"L": (38, 55), "a": (-2, 6), "b": (15, 30)},
        "日晒": {"L": (40, 58), "a": (-1, 7), "b": (16, 32)},
    },
    "Bourbon": {
        "水洗": {"L": (32, 48), "a": (0, 6), "b": (10, 22)},
        "日晒": {"L": (40, 58), "a": (1, 8), "b": (15, 32)},
    },
    "Typica": {
        "水洗": {"L": (34, 50), "a": (-1, 5), "b": (11, 24)},
        "日晒": {"L": (38, 55), "a": (0, 7), "b": (14, 30)},
    },
}

# ===== MQTT 主题 =====
MQTT_TOPICS = {
    "batch_output": "sorter/{{device_id}}/batch/output",   # 发送到烘豆机
    "batch_input": "roaster/{{device_id}}/batch/input",     # 接收烘豆机
    "status": "sorter/{{device_id}}/status",                # 状态发布
    "command": "sorter/{{device_id}}/command",              # 接收命令
}

# ===== 路径配置 =====
PATHS = {
    "sorter_root": "/opt/sorter",
    "data_dir": "/var/sorter/data",
    "models_dir": "/opt/sorter/models",
    "logs_dir": "/var/log/sorter",
    "calibration_dir": "/opt/sorter/calibration",
}

# 确保目录存在
for path in PATHS.values():
    os.makedirs(path, exist_ok=True)
