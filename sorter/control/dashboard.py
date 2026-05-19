#!/usr/bin/env python3
"""
生豆分选机 - 实时监控仪表盘 / Real-Time Monitoring Dashboard
HUSKY-SORTER-001

功能：
  - 状态机实时可视化（颜色编码大字状态显示）
  - 传感器实时读数（重量/含水率/颜色分/流量）
  - 产量统计（已分选/已剔除/总重量/吞吐量）
  - 批次进度（多批次进度条）
  - 实时吞吐量折线图（最近60秒）
  - MQTT连接状态监控
  - 事件日志（滚动）
  - 控制按钮（Start/Stop/Pause/E-Stop/Reset）
  - 模拟给料演示（无需硬件）

依赖：
  pip install matplotlib numpy

使用方法：
  python sorter/control/dashboard.py
  python sorter/control/dashboard.py --simulate        # 默认：模拟模式
  python sorter/control/dashboard.py --hw=192.168.1.100  # 连接真实控制器
"""

import sys
import os
import time
import json
import logging
import threading
import argparse
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime, timedelta
from collections import deque
from typing import Optional, Dict, Any, List

# ── 日志配置 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("dashboard")


# ── 状态颜色映射 ────────────────────────────────────────────────────────────
STATE_COLORS: Dict[str, str] = {
    "IDLE":          "#4a4a4a",   # 深灰
    "INITIALIZING":  "#1a9fff",   # 蓝
    "CALIBRATING":   "#00b4d8",   # 浅蓝
    "READY":         "#00c853",   # 绿
    "RUNNING":       "#00c853",   # 亮绿
    "FEEDING":       "#76ff03",   # 亮绿黄
    "PAUSED":        "#ffab00",   # 橙
    "FAULT":         "#ff3d00",   # 红
    "ESTOP":         "#b71c1c",   # 深红
}

STATE_SUB_COLORS: Dict[str, str] = {
    "RUN_FEEDING":   "#64dd17",
    "RUN_SIZING":    "#00c853",
    "RUN_COLOR_DETECT": "#2979ff",
    "RUN_WEIGHING":  "#aa00ff",
    "RUN_DENSITY":   "#00bcd4",
    "RUN_MOISTURE":  "#ff6d00",
    "RUN_BUFFERING":  "#ffab00",
    "FEED_SELECTING": "#76ff03",
    "FEED_DISPENSING": "#eeff41",
    "FEED_COMPLETING": "#00e676",
}


# ── 数据模拟器 ──────────────────────────────────────────────────────────────
class BeanSimulator:
    """模拟豆子流：产生随机豆子检测数据，用于仪表盘演示"""

    DEFECT_RATE = 0.08  # 8% 缺陷率

    DEFECT_TYPES = [
        ("mold",      "发霉豆"),
        ("fermented", "发酵豆"),
        ("black",     "黑豆"),
        ("broken",    "碎豆"),
        ("underdev",  "发育不全"),
    ]

    SIZE_GRADES = list(range(12, 17))  # 12-16目

    def __init__(self, bpm: float = 50.0):
        self.bpm = bpm
        self._interval_s = 60.0 / bpm
        self._last_bean_time = 0.0
        self._bean_counter = 0

    def maybe_emit(self) -> Optional[Dict[str, Any]]:
        """按BPM节拍返回豆子数据，None表示本周期无新豆"""
        now = time.time()
        if now - self._last_bean_time >= self._interval_s:
            self._last_bean_time = now
            self._bean_counter += 1
            return self._generate_bean(self._bean_counter)
        return None

    def _generate_bean(self, bean_id: int) -> Dict[str, Any]:
        import random
        is_defect = random.random() < self.DEFECT_RATE
        defect_type, defect_name = None, None
        if is_defect:
            defect_type, defect_name = random.choice(self.DEFECT_TYPES)

        # 正常豆参数
        weight_g = random.gauss(0.155, 0.025)
        weight_g = max(0.08, min(0.28, weight_g))

        moisture_pct = random.gauss(11.2, 0.8)
        moisture_pct = max(8.0, min(14.5, moisture_pct))

        density_class = random.choice(["AA", "A", "B", "C"])
        size_grade = random.choice(self.SIZE_GRADES)

        color_score = (random.uniform(82, 98) if not is_defect
                       else random.uniform(38, 68))
        l_star = random.uniform(38, 56) if not is_defect else random.uniform(22, 36)
        a_star = random.uniform(3, 12)
        b_star = random.uniform(14, 30)

        return {
            "bean_id":       bean_id,
            "timestamp":     datetime.now().isoformat(),
            "size_grade":    size_grade,
            "weight_g":      round(weight_g, 4),
            "density_class": density_class,
            "moisture_pct":  round(moisture_pct, 2),
            "color_defect":  is_defect,
            "color_score":   round(color_score, 1),
            "defect_type":   defect_type,
            "defect_name":   defect_name,
            "l_star":        round(l_star, 2),
            "a_star":        round(a_star, 2),
            "b_star":        round(b_star, 2),
            "is_rejected":   is_defect,
            "reject_reason": defect_type if is_defect else None,
            "channel_id":    random.choice([1, 1, 1, 2, 3]),  # 1通道概率更高
        }


# ── 仪表盘 ─────────────────────────────────────────────────────────────────
class SorterDashboard(tk.Tk):
    """生豆分选机实时监控仪表盘"""

    UPDATE_INTERVAL_MS = 200   # 刷新间隔
    CHART_HISTORY_S    = 120   # 图表保留时间（秒）
    LOG_LINES_MAX      = 200

    def __init__(self, simulate: bool = True, controller_host: Optional[str] = None, controller=None):
        super().__init__()
        self.title("🐕 生豆分选机监控仪表盘 — HUSKY-SORTER-001")
        self.geometry("1280x800")
        self.minsize(1100, 700)
        self.configure(bg="#0d1117")

        self.simulate = simulate
        self.controller_host = controller_host
        self._controller = controller  # P2-06: optional SorterController reference

        # ── 状态机状态 (仅模拟模式使用; 有控制器时从控制器读取) ───────
        self._state         = "IDLE"
        self._substate      = ""
        self._running        = False
        self._paused         = False
        self._mqtt_connected = simulate  # 模拟模式默认已连接
        self._uptime_start   = time.time()

        # ── 统计数据 ───────────────────────────────────────────────────────
        self._total_beans      = 0
        self._rejected_beans   = 0
        self._total_weight_g   = 0.0
        self._fault_count      = 0
        self._batch_count       = 0
        self._batch_target_kg   = 1.0    # 当前批次目标 kg
        self._batch_current_g  = 0.0    # 当前批次已重量

        # ── 实时读数 ────────────────────────────────────────────────────────
        self._latest_weight_g   = None
        self._latest_moisture   = None
        self._latest_color_score = None
        self._latest_size       = None
        self._latest_density    = None
        self._latest_defect_name = ""

        # ── 吞吐量历史（环形缓冲）──────────────────────────────────────────
        self._throughput_buf = deque(maxlen=self.CHART_HISTORY_S * 5)  # 5fps
        self._time_buf       = deque(maxlen=self.CHART_HISTORY_S * 5)
        # 预填充
        now = time.time()
        for i in range(self.CHART_HISTORY_S * 5):
            self._time_buf.append(now - self.CHART_HISTORY_S + i * 0.2)
            self._throughput_buf.append(0.0)

        # ── 最近豆子日志（事件日志用）────────────────────────────────────
        self._recent_log: deque[str] = deque(maxlen=self.LOG_LINES_MAX)

        # ── 模拟器 ─────────────────────────────────────────────────────────
        self._sim = BeanSimulator(bpm=50.0)

        # ── 线程锁 ──────────────────────────────────────────────────────────
        self._lock = threading.Lock()

        # ── 控制面板命令 ────────────────────────────────────────────────────
        self._pending_cmd: Optional[str] = None

        self._build_ui()
        self._start_update_loop()

        if self.simulate:
            self._append_log("💡 模拟模式启动（无需硬件）")
        elif self._controller is not None:
            self._append_log("🔌 已连接真实控制器")
        else:
            self._append_log(f"🔌 连接控制器: {controller_host}")

        logger.info("Dashboard initialized")

    # ── P2-06: read state from real controller when injected ────────────────
    def _get_effective_state(self) -> Dict[str, Any]:
        """Return current state dict. Prefers real controller over local mock state."""
        if self._controller is not None:
            try:
                ctrl = self._controller
                status = ctrl.get_status()
                return {
                    "state": status.get("state", self._state),
                    "substate": status.get("substate", self._substate),
                    "running": getattr(ctrl, "_running", self._running),
                    "paused": self._paused,
                    "mqtt_connected": self._mqtt_connected,
                    "uptime_start": self._uptime_start,
                }
            except Exception:
                pass
        return {
            "state": self._state,
            "substate": self._substate,
            "running": self._running,
            "paused": self._paused,
            "mqtt_connected": self._mqtt_connected,
            "uptime_start": self._uptime_start,
        }

    def _send_to_controller(self, event):
        """Post event to controller if available, return True on success."""
        if self._controller is not None:
            try:
                self._controller.post_event(event)
                return True
            except Exception as e:
                self._append_log(f"⚠ 控制器命令失败: {e}")
                return False
        return False

    # ── UI 构建 ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # 全局字体
        self.font_title  = ("SF Mono Display", 28, "bold")
        self.font_state  = ("SF Mono Display", 40, "bold")
        self.font_sub    = ("SF Mono Text",    14,  "normal")
        self.font_label  = ("SF Mono Text",    12,  "bold")
        self.font_value  = ("SF Mono Display", 22,  "bold")
        self.font_small  = ("SF Mono Text",    11,  "normal")
        self.font_log    = ("SF Mono Text",    10,  "normal")

        # 顶栏
        top = tk.Frame(self, bg="#161b22", height=56)
        top.pack(fill="x")
        tk.Label(top, text="🐕 HUSKY-SORTER-001  |  生豆分选机监控仪表盘",
                 font=("SF Mono Display", 15, "bold"),
                 fg="#58a6ff", bg="#161b22").pack(side="left", padx=20, pady=10)
        self._lbl_uptime = tk.Label(top, text="运行: 00:00:00",
                                     font=self.font_small, fg="#8b949e", bg="#161b22")
        self._lbl_uptime.pack(side="right", padx=20, pady=10)

        # ── 主布局：左(状态+统计) / 中(图表) / 右(控制+日志) ─────────────
        paned = tk.PanedWindow(self, bg="#0d1117", opaqueresize=False)
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ─── 左侧面板 ─────────────────────────────────────────────────────
        left = tk.Frame(paned, bg="#0d1117", width=360)
        paned.add(left, width=360)

        # 大状态显示
        state_frame = tk.Frame(left, bg="#161b22", bd=0, highlightthickness=0)
        state_frame.pack(fill="x", pady=(0, 8))

        self._state_canvas = tk.Canvas(state_frame, height=120,
                                        bg="#161b22", highlightthickness=0)
        self._state_canvas.pack(fill="x")
        self._state_rect = self._state_canvas.create_rectangle(
            4, 4, 356, 116, fill="#4a4a4a", outline="")
        self._state_text = self._state_canvas.create_text(
            180, 60, text="IDLE", font=self.font_state,
            fill="white", anchor="center")

        # 子状态
        self._lbl_substate = tk.Label(state_frame, text="",
                                       font=self.font_small, fg="#8b949e",
                                       bg="#161b22", anchor="w")
        self._lbl_substate.pack(fill="x", padx=8, pady=(2, 6))

        # MQTT状态栏
        mqtt_frame = tk.Frame(left, bg="#161b22")
        mqtt_frame.pack(fill="x", pady=(0, 8))
        self._lbl_mqtt = tk.Label(mqtt_frame, text="● MQTT: 断开",
                                   font=self.font_small, fg="#ff3d00",
                                   bg="#161b22", anchor="w", padx=12, pady=6)
        self._lbl_mqtt.pack(fill="x")

        # 传感器读数
        sensor_frame = tk.LabelFrame(left, text=" 实时传感器读数 ",
                                    font=self.font_label, fg="#58a6ff",
                                    bg="#0d1117", padx=10, pady=8)
        sensor_frame.pack(fill="x", pady=(0, 8))

        self._sensor_labels: Dict[str, tk.Label] = {}
        sensor_items = [
            ("weight",  "重量",    "─ ─ ─ g"),
            ("moisture","含水率",  "─ ─ ─ %"),
            ("color",   "颜色分",  "─ ─ ─"),
            ("size",    "尺寸",    "─ ─ ─ 目"),
            ("density", "密度",    "─ ─ ─"),
            ("defect",  "最新缺陷", "─"),
        ]
        for k, label, placeholder in sensor_items:
            row = tk.Frame(sensor_frame, bg="#0d1117")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:", font=self.font_small,
                     fg="#8b949e", bg="#0d1117", width=10, anchor="w").pack(side="left")
            lbl = tk.Label(row, text=placeholder, font=self.font_small,
                            fg="#58a6ff", bg="#0d1117", anchor="e")
            lbl.pack(side="right")
            self._sensor_labels[k] = lbl

        # 统计卡片
        stats_frame = tk.LabelFrame(left, text=" 产量统计 ",
                                    font=self.font_label, fg="#58a6ff",
                                    bg="#0d1117", padx=10, pady=8)
        stats_frame.pack(fill="x", pady=(0, 8))

        self._stat_labels: Dict[str, tk.Label] = {}
        stat_items = [
            ("total",    "已分选",      "0 粒"),
            ("rejected", "已剔除",      "0 粒"),
            ("weight",   "总重量",      "0.000 kg"),
            ("throughput", "吞吐量",   "0.00 kg/h"),
            ("bpm",      "给料速度",    "0 bpm"),
            ("faults",   "故障次数",    "0 次"),
        ]
        for k, label, placeholder in stat_items:
            row = tk.Frame(stats_frame, bg="#0d1117")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=self.font_small,
                     fg="#8b949e", bg="#0d1117", width=10, anchor="w").pack(side="left")
            lbl = tk.Label(row, text=placeholder, font=("SF Mono Display", 16, "bold"),
                            fg="#f0f6fc", bg="#0d1117", anchor="e")
            lbl.pack(side="right")
            self._stat_labels[k] = lbl

        # 批次进度
        batch_frame = tk.LabelFrame(left, text=" 批次进度 ",
                                    font=self.font_label, fg="#58a6ff",
                                    bg="#0d1117", padx=10, pady=8)
        batch_frame.pack(fill="x")

        tk.Label(batch_frame, text="批次 #1  →  烘豆机",
                 font=self.font_small, fg="#8b949e", bg="#0d1117").pack(anchor="w")
        self._batch_progress = ttk.Progressbar(batch_frame, length=320, mode="determinate",
                                               maximum=1000, value=0)
        self._batch_progress.pack(pady=4, fill="x")
        self._lbl_batch_info = tk.Label(batch_frame, text="0.000 kg / 1.000 kg",
                                         font=self.font_small, fg="#58a6ff", bg="#0d1117")
        self._lbl_batch_info.pack(anchor="e")

        # ─── 中间面板 ─────────────────────────────────────────────────────
        middle = tk.Frame(paned, bg="#0d1117")
        paned.add(middle, width=520)

        # 吞吐量图
        chart_frame = tk.LabelFrame(middle, text=" 吞吐量 (kg/h) — 近2分钟 ",
                                    font=self.font_label, fg="#58a6ff",
                                    bg="#0d1117", padx=8, pady=4)
        chart_frame.pack(fill="both", expand=True, pady=(0, 8))

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self._plt = plt
            self._mpl_available = True

            fig, self._ax = plt.subplots(figsize=(6, 3.5), dpi=100)
            fig.patch.set_facecolor("#0d1117")
            self._ax.set_facecolor("#161b22")
            self._ax.tick_params(colors="#8b949e", labelsize=8)
            self._ax.xaxis.label.set_color("#8b949e")
            self._ax.yaxis.label.set_color("#8b949e")
            for spine in self._ax.spines.values():
                spine.set_edgecolor("#30363d")
            self._ax.set_ylabel("kg/h", color="#8b949e", fontsize=8)
            self._ax.set_xlabel("时间 (s)", color="#8b949e", fontsize=8)
            self._ax.set_ylim(0, 4.0)
            self._ax.set_xlim(0, self.CHART_HISTORY_S)
            self._ax.grid(True, alpha=0.3, color="#30363d")
            self._line, = self._ax.plot([], [], color="#58a6ff", linewidth=1.5)
            self._ax.fill_between([], [], alpha=0.15, color="#58a6ff")
            self._ax.axhline(y=2.0, color="#76ff03", linestyle="--", linewidth=0.8, alpha=0.7,
                             label="目标 2.0 kg/h")
            self._ax.legend(fontsize=8, loc="upper right")

            self._chart_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            self._chart_canvas.get_tk_widget().pack(fill="both", expand=True)
        except ImportError:
            self._mpl_available = False
            tk.Label(chart_frame, text="📊 matplotlib 未安装\npip install matplotlib",
                     font=self.font_small, fg="#8b949e", bg="#0d1117",
                     justify="center").pack(fill="both", expand=True)

        # 缺陷分布（简化为文字显示）
        defect_frame = tk.LabelFrame(middle, text=" 缺陷统计 ",
                                      font=self.font_label, fg="#58a6ff",
                                      bg="#0d1117", padx=8, pady=4)
        defect_frame.pack(fill="x")

        self._defect_labels: Dict[str, tk.Label] = {}
        defect_types = ["mold", "fermented", "black", "broken", "underdev"]
        defect_names_cn = ["发霉豆", "发酵豆", "黑豆", "碎豆", "发育不全"]
        self._defect_counts: Dict[str, int] = {k: 0 for k in defect_types}

        for dtype, name_cn in zip(defect_types, defect_names_cn):
            row = tk.Frame(defect_frame, bg="#0d1117")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"  {name_cn}", font=self.font_small,
                     fg="#8b949e", bg="#0d1117", anchor="w").pack(side="left")
            lbl = tk.Label(row, text="0", font=self.font_small,
                            fg="#ff7b72", bg="#0d1117", anchor="e", width=5)
            lbl.pack(side="right")
            self._defect_labels[dtype] = lbl

        # ─── 右侧面板 ─────────────────────────────────────────────────────
        right = tk.Frame(paned, bg="#0d1117")
        paned.add(right, width=380)

        # 控制按钮
        ctrl_frame = tk.LabelFrame(right, text=" 控制面板 ",
                                   font=self.font_label, fg="#58a6ff",
                                   bg="#0d1117", padx=10, pady=8)
        ctrl_frame.pack(fill="x", pady=(0, 8))

        btn_cfg = [
            ("▶  START",  "#00c853", self._cmd_start),
            ("⏸  PAUSE",  "#ffab00", self._cmd_pause),
            ("⏹  STOP",   "#ff3d00", self._cmd_stop),
            ("🛑  E-STOP", "#b71c1c", self._cmd_estop),
            ("↺  RESET",  "#1a9fff", self._cmd_reset),
        ]
        for label, color, cmd in btn_cfg:
            btn = tk.Button(ctrl_frame, text=label, font=("SF Mono Text", 12, "bold"),
                            fg="white", bg=color, activebackground="white",
                            activeforeground=color, relief="flat", bd=0,
                            pady=8, cursor="hand2", command=cmd)
            btn.pack(fill="x", pady=2)

        # 批次控制
        batch_ctrl = tk.Frame(ctrl_frame, bg="#0d1117")
        batch_ctrl.pack(fill="x", pady=(6, 0))
        tk.Label(batch_ctrl, text="批次目标 (kg):", font=self.font_small,
                 fg="#8b949e", bg="#0d1117").pack(side="left")
        self._batch_kg_entry = tk.Entry(batch_ctrl, font=self.font_small,
                                          width=8, bg="#21262d", fg="#f0f6fc",
                                          insertbackground="#58a6ff", relief="flat")
        self._batch_kg_entry.insert(0, "1.0")
        self._batch_kg_entry.pack(side="right")
        tk.Button(ctrl_frame, text="🆕 新批次", font=self.font_small,
                   fg="white", bg="#1a9fff", relief="flat", pady=4,
                   cursor="hand2", command=self._cmd_new_batch).pack(fill="x", pady=(4, 0))

        # 事件日志
        log_frame = tk.LabelFrame(right, text=" 事件日志 ",
                                   font=self.font_label, fg="#58a6ff",
                                   bg="#0d1117", padx=4, pady=4)
        log_frame.pack(fill="both", expand=True)

        self._log_text = scrolledtext.ScrolledText(
            log_frame, wrap="word", font=self.font_log,
            bg="#0d1117", fg="#c9d1d9", insertbackground="#58a6ff",
            relief="flat", state="disabled", height=20,
            highlightthickness=0)
        self._log_text.pack(fill="both", expand=True)

        # 状态栏
        status_bar = tk.Frame(self, bg="#161b22", height=24)
        status_bar.pack(fill="x", side="bottom")
        self._lbl_statusbar = tk.Label(status_bar, text="就绪",
                                        font=self.font_log, fg="#8b949e",
                                        bg="#161b22", anchor="w", padx=12)
        self._lbl_statusbar.pack(side="left", fill="x")

    # ── 命令处理 ─────────────────────────────────────────────────────────────
    def _cmd_start(self):
        self._pending_cmd = "start"
        self._append_log("▶ START 命令已发送")

    def _cmd_pause(self):
        self._pending_cmd = "pause"
        self._append_log("⏸ PAUSE 命令已发送")

    def _cmd_stop(self):
        self._pending_cmd = "stop"
        self._append_log("⏹ STOP 命令已发送")

    def _cmd_estop(self):
        self._pending_cmd = "estop"
        self._append_log("🛑 E-STOP 命令已发送！")

    def _cmd_reset(self):
        self._pending_cmd = "reset"
        self._append_log("↺ RESET 命令已发送")

    def _cmd_new_batch(self):
        try:
            kg = float(self._batch_kg_entry.get())
            if kg <= 0:
                raise ValueError
            self._batch_target_kg = kg
            self._batch_current_g = 0.0
            self._batch_count += 1
            self._batch_progress["value"] = 0
            self._pending_cmd = "new_batch"
            self._append_log(f"🆕 新批次 #{self._batch_count} 目标: {kg}kg")
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的批次目标重量 (kg)")

    # ── 主更新循环 ───────────────────────────────────────────────────────────
    def _start_update_loop(self):
        self._loop_running = True
        self._last_chart_update = 0.0
        self._last_sensor_emit  = 0.0

        def loop():
            last_tick = time.time()
            while self._loop_running:
                now = time.time()
                dt = now - last_tick
                last_tick = now

                # ── 模拟豆子流 ──────────────────────────────────────────────
                eff_state = self._get_effective_state()
                if eff_state["running"] and not eff_state["paused"]:
                    bean = self._sim.maybe_emit()
                    if bean:
                        self._on_bean_processed(bean)

                # ── 更新传感器读数（模拟） ──────────────────────────────────
                if self._running and now - self._last_sensor_emit > 0.5:
                    self._last_sensor_emit = now
                    self._update_sensor_display()

                # ── 处理待处理命令 ──────────────────────────────────────────
                cmd = None
                with self._lock:
                    cmd = self._pending_cmd
                    self._pending_cmd = None
                if cmd:
                    self._execute_cmd(cmd)

                # ── 更新 MQTT 状态（模拟） ───────────────────────────────────
                # 模拟每30秒断连一次再恢复（仅视觉效果）
                if self.simulate and int(now) % 30 == 0 and int(now) != int(self._uptime_start):
                    self._mqtt_connected = not self._mqtt_connected

                # ── 更新图表（5fps） ────────────────────────────────────────
                if now - self._last_chart_update > 0.2:
                    self._last_chart_update = now
                    self._update_chart()
                    self._update_throughput_stat()

                # ── 更新状态显示（10fps） ───────────────────────────────────
                self._update_state_display()
                self._update_uptime()
                self._update_mqtt_display()

                time.sleep(0.1)

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def _execute_cmd(self, cmd: str):
        # P2-06: proxy commands to real controller when injected
        if self._controller is not None:
            from sorter.control.main import Event
            event_map = {
                "start": Event.START,
                "pause": Event.PAUSE,
                "stop": Event.STOP,
                "estop": Event.ESTOP,
            }
            event = event_map.get(cmd)
            if event is not None:
                if self._send_to_controller(event):
                    self._append_log(f"▶ 命令已发送至控制器: {cmd.upper()}")
                return
            # new_batch and reset fall through to local handling

        with self._lock:
            if cmd == "start":
                if self._state in ("IDLE",):
                    self._state = "INITIALIZING"
                    self._substate = ""
                    self._append_log("⚙ 初始化中...")
                    # 模拟初始化
                    def delayed():
                        time.sleep(1.5)
                        self._state = "READY"
                        self._substate = "IDLE_BEANS_LOADED"
                        self._running = True
                        self._append_log("✅ 就绪 — START")
                    threading.Thread(target=delayed, daemon=True).start()
                elif self._state == "PAUSED":
                    self._state = "RUNNING"
                    self._append_log("▶ 恢复运行")

            elif cmd == "pause":
                if self._state == "RUNNING":
                    self._state = "PAUSED"
                    self._paused = True
                    self._append_log("⏸ 已暂停")

            elif cmd == "stop":
                self._running = False
                self._paused = False
                self._state = "IDLE"
                self._substate = ""
                self._append_log("⏹ 已停止")

            elif cmd == "estop":
                self._running = False
                self._paused = False
                self._state = "ESTOP"
                self._fault_count += 1
                self._append_log("🛑 急停！所有执行器关闭！")

            elif cmd == "reset":
                self._state = "IDLE"
                self._substate = ""
                self._running = False
                self._paused = False
                self._append_log("↺ 已复位")

            elif cmd == "new_batch":
                self._batch_current_g = 0.0
                self._batch_progress["value"] = 0
                if self._state == "READY":
                    self._running = True
                    self._state = "RUNNING"

    def _on_bean_processed(self, bean: Dict):
        """处理一粒新豆子的数据更新"""
        self._total_beans += 1
        if bean.get("is_rejected"):
            self._rejected_beans += 1
            dtype = bean.get("defect_type", "unknown")
            if dtype in self._defect_counts:
                self._defect_counts[dtype] += 1
                self._defect_labels[dtype].config(text=str(self._defect_counts[dtype]))
            self._latest_defect_name = f"[剔除] {bean.get('defect_name', '')}"
        self._total_weight_g += bean.get("weight_g", 0.15)
        self._batch_current_g += bean.get("weight_g", 0.15)

        # 更新批次进度
        pct = min(1000, int(self._batch_current_g / 1000.0 / self._batch_target_kg * 1000))
        self._batch_progress["value"] = pct
        self._lbl_batch_info.config(
            text=f"{self._batch_current_g/1000:.3f} kg / {self._batch_target_kg:.3f} kg")

        # 记录最新读数
        self._latest_weight_g     = bean.get("weight_g")
        self._latest_moisture      = bean.get("moisture_pct")
        self._latest_color_score   = bean.get("color_score")
        self._latest_size          = bean.get("size_grade")
        self._latest_density       = bean.get("density_class")

        # 追加吞吐量数据
        elapsed_h = (time.time() - self._uptime_start) / 3600.0
        if elapsed_h > 0:
            throughput = (self._total_weight_g / 1000.0) / elapsed_h
        else:
            throughput = 0.0
        self._throughput_buf.append(throughput)
        self._time_buf.append(time.time())

        # 事件日志
        bean_id = bean["bean_id"]
        size = bean["size_grade"]
        w    = bean["weight_g"]
        defect_str = f" ⚠{bean['defect_name']}" if bean.get("is_rejected") else ""
        self._append_log(
            f"  #{bean_id:04d} | {size}目 | {w*1000:.1f}mg | 颜色{bean['color_score']:.0f}{defect_str}"
        )

    # ── UI 更新 ──────────────────────────────────────────────────────────────
    def _update_state_display(self):
        eff = self._get_effective_state()
        state = eff["state"]
        color = STATE_COLORS.get(state, "#4a4a4a")
        self._state_canvas.itemconfig(self._state_rect, fill=color)
        self._state_canvas.itemconfig(self._state_text, text=state)

    def _update_uptime(self):
        elapsed = int(time.time() - self._uptime_start)
        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        self._lbl_uptime.config(text=f"运行: {h:02d}:{m:02d}:{s:02d}")

    def _update_mqtt_display(self):
        if self._mqtt_connected:
            self._lbl_mqtt.config(text="● MQTT: 已连接 (simulate)", fg="#00c853")
        else:
            self._lbl_mqtt.config(text="● MQTT: 断开连接", fg="#ff3d00")

    def _update_sensor_display(self):
        def fmt(v, unit, decimals=2):
            if v is None:
                return f"─ ─ ─ {unit}"
            return f"{v:.{decimals}f} {unit}"

        self._sensor_labels["weight"].config(
            text=fmt(self._latest_weight_g * 1000, "mg", 1))
        self._sensor_labels["moisture"].config(
            text=fmt(self._latest_moisture, "%"))
        self._sensor_labels["color"].config(
            text=fmt(self._latest_color_score, "", 1))
        self._sensor_labels["size"].config(
            text=fmt(self._latest_size, "目", 0) if self._latest_size else "─ ─ ─ 目")
        self._sensor_labels["density"].config(
            text=str(self._latest_density) if self._latest_density else "─")
        self._sensor_labels["defect"].config(
            text=self._latest_defect_name or "无",
            fg="#ff7b72" if self._latest_defect_name else "#58a6ff")

    def _update_throughput_stat(self):
        # 计算最近30秒平均吞吐量
        buf = list(self._throughput_buf)
        if buf:
            recent = buf[-150:] if len(buf) > 150 else buf  # ~30s
            avg = sum(recent) / len(recent) if recent else 0.0
        else:
            avg = 0.0

        self._stat_labels["total"].config(text=f"{self._total_beans} 粒")
        self._stat_labels["rejected"].config(text=f"{self._rejected_beans} 粒")
        self._stat_labels["weight"].config(text=f"{self._total_weight_g/1000:.3f} kg")
        self._stat_labels["throughput"].config(text=f"{avg:.2f} kg/h")
        self._stat_labels["bpm"].config(
            text=f"{self._sim.bpm:.0f} bpm" if self._running else "0 bpm")
        self._stat_labels["faults"].config(text=f"{self._fault_count} 次")

    def _update_chart(self):
        if not getattr(self, "_mpl_available", False):
            return
        try:
            times  = list(self._time_buf)
            values = list(self._throughput_buf)
            if not times:
                return

            # 相对时间
            t0 = times[0]
            rel_times = [t - t0 for t in times[-300:]]
            rel_vals  = values[-300:]

            self._line.set_data(rel_times, rel_vals)
            self._ax.set_xlim(0, self.CHART_HISTORY_S)
            self._chart_canvas.draw_idle()
        except Exception:
            pass  # 忽略图表更新错误

    def _append_log(self, msg: str):
        """向事件日志追加一条记录（线程安全）"""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log_text.config(state="normal")
        self._log_text.insert("end", line)
        self._log_text.see("end")
        self._log_text.config(state="disabled")


# ── P2-06: global dashboard reference for controller injection ─────────────
_dashboard_instance: Optional['SorterDashboard'] = None


def inject_dashboard_controller(sorter_controller):
    """Inject SorterController into a running dashboard instance.

    Call from main.py after creating the controller:
        from sorter.control.dashboard import inject_dashboard_controller
        inject_dashboard_controller(controller)
    """
    global _dashboard_instance
    if _dashboard_instance is not None:
        _dashboard_instance._controller = sorter_controller
        _dashboard_instance._append_log("🔌 控制器已注入 — 仪表盘连接真实硬件")
        logger.info("Controller injected into dashboard")


# ── 入口 ─────────────────────────────────────────────────────────────────────
def main():
    global _dashboard_instance
    parser = argparse.ArgumentParser(description="HUSKY-SORTER-001 监控仪表盘")
    parser.add_argument("--simulate", action="store_true",
                        help="模拟模式（默认开启）")
    parser.add_argument("--hw", type=str, default=None,
                        help="连接真实控制器主机地址")
    args = parser.parse_args()

    simulate = args.simulate or (args.hw is None)
    app = SorterDashboard(simulate=simulate, controller_host=args.hw)
    _dashboard_instance = app
    app.mainloop()


if __name__ == "__main__":
    main()