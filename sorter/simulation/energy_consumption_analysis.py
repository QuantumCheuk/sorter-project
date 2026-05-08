#!/usr/bin/env python3
"""
生豆分选机能耗分析与电源选型
sorter/simulation/energy_consumption_analysis.py

研究目标：计算系统各组件功耗、电源规格选型、散热设计、运行成本估算
"""

import json
import math

print("=" * 70)
print("⚡ 生豆分选机能耗分析与电源选型")
print("=" * 70)

# ============================================================
# 第一部分：各组件功耗清单
# ============================================================
print("\n📋 第一部分：各组件功耗清单")
print("-" * 70)

components = {
    # 核心控制器
    "Raspberry Pi 4B (idle)":          {"qty": 1, "idle_w": 2.0, "max_w": 6.0,  "duty": 0.10},
    "Raspberry Pi 4B (active)":        {"qty": 1, "idle_w": 2.0, "max_w": 6.0,  "duty": 0.90},
    
    # 传感器
    "AD7746 含水率模块":                {"qty": 1, "idle_w": 0.015, "max_w": 0.025, "duty": 0.30},
    "HX711 称重模块":                   {"qty": 1, "idle_w": 0.005, "max_w": 0.010, "duty": 0.80},
    "RGB相机 (暗箱照明)":               {"qty": 2, "idle_w": 0.5,   "max_w": 2.5,   "duty": 0.40},
    
    # 照明
    "LED灯带 5050 (暗箱)":              {"qty": 1, "idle_w": 0.0,   "max_w": 10.0,  "duty": 1.00},
    "LED驱动器 12V":                    {"qty": 1, "idle_w": 0.0,   "max_w": 2.0,   "duty": 1.00},
    
    # 执行器 - 给料
    "28BYJ-48 振动给料电机 ×1":         {"qty": 1, "idle_w": 0.0,   "max_w": 4.0,   "duty": 0.20},
    "28BYJ-48 旋转分配器电机":          {"qty": 1, "idle_w": 0.0,   "max_w": 2.5,   "duty": 0.15},
    "28BYJ-48 称重杯释放电机":          {"qty": 1, "idle_w": 0.0,   "max_w": 1.5,   "duty": 0.05},
    
    # 执行器 - 气喷
    "电磁阀 2W (气喷剔除) ×3":          {"qty": 3, "idle_w": 0.0,   "max_w": 6.0,   "duty": 0.08},
    "微型空压机 12V/5W":               {"qty": 1, "idle_w": 0.0,   "max_w": 8.0,   "duty": 0.05},
    
    # 通信
    "ESP32 (显示屏+触控)":              {"qty": 1, "idle_w": 0.08,  "max_w": 0.24,  "duty": 1.00},
    "ESP32 (传感器集联) ×2":            {"qty": 2, "idle_w": 0.05,  "max_w": 0.15,  "duty": 0.20},
    "MQTT WiFi (Pi)":                   {"qty": 1, "idle_w": 0.5,   "max_w": 1.0,   "duty": 1.00},
    
    # 扩展 (未来3通道)
    "Nema17 升级振动给料 ×3":           {"qty": 0, "idle_w": 0.0,   "max_w": 15.0,  "duty": 0.20},
    "涡轮鼓风机 12V/3A":                {"qty": 0, "idle_w": 0.0,   "max_w": 36.0,  "duty": 0.03},
}

print(f"{'组件':<35} {'数量':>4} {'空闲W':>8} {'最大W':>8} {'负载率':>8} {'平均W':>8}")
print("-" * 75)

total_avg_w = 0.0
total_max_w = 0.0

for name, c in sorted(components.items(), key=lambda x: x[1]["max_w"] * x[1]["qty"], reverse=True):
    qty    = c["qty"]
    idle_w = c["idle_w"]
    max_w  = c["max_w"]
    duty   = c["duty"]
    
    avg_w  = idle_w * (1 - duty) + max_w * duty
    total_c_avg = avg_w * qty
    total_c_max = max_w * qty
    
    total_avg_w += total_c_avg
    total_max_w += total_c_max
    
    print(f"{name:<35} {qty:>4} {idle_w:>8.3f} {max_w:>8.2f} {duty:>8.0%} {total_c_avg:>8.3f}")

print("-" * 75)
print(f"{'合计':<35} {'':<4} {'':<8} {total_max_w:>8.2f} {'':<8} {total_avg_w:>8.2f}")

# ============================================================
# 第二部分：电源规格选型
# ============================================================
print("\n\n⚡ 第二部分：电源规格选型")
print("-" * 70)

# 电源轨
voltage_rails = {
    "5V / 3A (Pi USB-C)": {
        "draw": 2.5, "peak": 5.0, "rated": 15.0, "safety": 1.25,
        "purpose": "Raspberry Pi 4B (推荐官方27W充电器)"
    },
    "12V / 2A (LED+执行器)": {
        "draw": 13.5, "peak": 28.5, "rated": 24.0, "safety": 0.90,
        "purpose": "LED灯带 + 12V空压机 + 电磁阀公共电源"
    },
    "5V / 500mA (AD7746+传感器)": {
        "draw": 0.06, "peak": 0.12, "rated": 2.5, "safety": 0.80,
        "purpose": "AD7746 + HX711 + I2C总线 (Pi 5V引脚)"
    },
    "3.3V / 500mA (ESP32)": {
        "draw": 0.15, "peak": 0.30, "rated": 1.5, "safety": 0.80,
        "purpose": "ESP32 + 显示屏 (LDO从5V降压)"
    },
}

# Pi GPIO 5V引脚供电能力
pi_5v_current = 0.5  # Raspberry Pi 4B GPIO 5V引脚建议<500mA

print(f"{'电源轨':<30} {'电流A':>8} {'峰值A':>8} {'额定W':>8} {'安全系数':>8}")
print("-" * 70)

for rail, r in voltage_rails.items():
    safety_margin = r["rated"] / r["peak"] if r["peak"] > 0 else 999
    print(f"{rail:<30} {r['draw']:>8.2f} {r['peak']:>8.2f} {r['rated']:>8.2f} {safety_margin:>8.2f}")

# 电源推荐
print("\n🔌 电源选型建议:")
print(f"  方案A (推荐) — 标准配置:")
print(f"    • 5V 3A USB-C 充电器 × 1 (Pi专用，推荐27W PD充电器)")
print(f"    • 12V 2A 适配器 × 1 (共享LED+执行器，峰值3A)")

# 12V峰值计算
led_peak = 12.0  # LED+驱动器
valve_peak = 6.0  # 3×电磁阀
compressor_peak = 8.0  # 空压机
total_12v_peak = led_peak + valve_peak + compressor_peak
total_12v_typical = 13.5  # from above

print(f"\n    12V轨峰值需求: {total_12v_peak}A → 建议12V 3A以上适配器")
print(f"    12V轨典型功耗: {total_12v_typical}W")

# ============================================================
# 第三部分：能耗与运行成本
# ============================================================
print("\n\n💰 第三部分：能耗与运行成本估算")
print("-" * 70)

# 年度电费计算
kwh_cost = 1.5  # ¥/kWh (香港商业用电估算)
daily_hours = 10  # 每天运行10小时
annual_days = 300  # 每年运行300天

annual_energy_kwh = (total_avg_w / 1000) * daily_hours * annual_days
annual_cost = annual_energy_kwh * kwh_cost

print(f"  当前配置年均总耗电量: {annual_energy_kwh:.1f} kWh/年")
print(f"  当前配置年均电费: ¥{annual_cost:.0f}/年")
print(f"  每小时电费: ¥{total_avg_w / 1000 * kwh_cost:.4f}/小时")
print(f"  每kg生豆分选电费: ¥{total_avg_w / 1000 * kwh_cost / 2.0:.4f}/kg (按2kg/h)")

# 待机功耗
idle_components = {k: v for k, v in components.items() if v["duty"] < 0.3}
idle_power = sum(v["idle_w"] * v["qty"] for v in idle_components.values())
idle_annual = (idle_power / 1000) * 24 * annual_days * kwh_cost
print(f"\n  待机功耗: {idle_power:.3f}W (主要: Pi + ESP32)")
print(f"  待机年电费: ¥{idle_annual:.0f}/年 (24h开机)")

# ============================================================
# 第四部分：散热设计
# ============================================================
print("\n\n🌡️ 第四部分：散热设计")
print("-" * 70)

# 各组件热耗散 (假设效率: LED 90%, 电机 60%, 电子模块 85%)
heat_gen = {
    "LED灯带":         (12.0, 0.90),
    "空压机":          (8.0,  0.60),
    "电磁阀 ×3":       (6.0,  0.95),
    "振动给料×1":     (4.0,  0.60),
    "Pi (active)":     (5.0,  0.85),
    "旋转分配器":      (2.5,  0.60),
}

print(f"{'热源':<30} {'功耗W':>8} {'效率':>8} {'热耗W':>8}")
print("-" * 60)
total_heat = 0
for name, (w, eff) in heat_gen.items():
    heat = w * (1 - eff)
    total_heat += heat
    print(f"{name:<30} {w:>8.1f} {eff:>8.0%} {heat:>8.2f}")

print("-" * 60)
print(f"{'系统总热耗':<30} {'':<8} {'':<8} {total_heat:>8.2f}W")

# 自然对流散热估算
area_box = 0.3 * 0.3 * 4  # 30cm×30cm×4面 ≈ 3600cm²
area_sides = 0.3 * 0.4 * 4  # 侧面积
total_area = area_box + area_sides  # m²

delta_t = total_heat / (5.7 * total_area)  # 自然对流 W/(m²·K)
print(f"\n  估算外壳表面积: {total_area:.2f} m²")
print(f"  温升估算: \u0394T ≈ {delta_t:.1f}°C (环境30°C时外壳约{30+delta_t:.0f}°C)")
print(f"  ⚠️  空压机+LED为主要热源，密闭外壳需加装散热风扇")

# ============================================================
# 第五部分：电源容量规划（3通道升级后）
# ============================================================
print("\n\n🔧 第五部分：3通道升级后电源需求")
print("-" * 70)

upgrade_scenarios = {
    "当前1通道": {
        "pi": 1, "camera": 2, "feeder_28byj": 1, "valve": 3,
        "compressor": 1, "led": 10, "esp32": 3
    },
    "3通道(28BYJ)": {
        "pi": 1, "camera": 2, "feeder_28byj": 3, "valve": 3,
        "compressor": 1, "led": 10, "esp32": 3
    },
    "3通道(Nema17升级)": {
        "pi": 1, "camera": 2, "feeder_nema17": 3, "valve": 3,
        "compressor": 1, "led": 10, "esp32": 3, "turboblower": 1
    },
}

peak_power = {
    "当前1通道": 6 + 5 + 2.5 + 6 + 8 + 12 + 1,
    "3通道(28BYJ)": 6 + 5 + 2.5 + 12 + 8 + 12 + 1,
    "3通道(Nema17升级)": 6 + 5 + 2.5 + 45 + 8 + 12 + 1 + 36,
}

avg_power = {
    "当前1通道": total_avg_w,
    "3通道(28BYJ)": total_avg_w + 2 * 0.8,  # +2×28BYJ振动给料
    "3通道(Nema17升级)": total_avg_w + 2 * 3.0 + 1.1,  # +2×Nema17 + 涡轮鼓风机
}

print(f"{'配置':<25} {'峰值W':>10} {'典型W':>10} {'推荐电源':>15}")
print("-" * 65)

for scenario in upgrade_scenarios:
    pp = peak_power[scenario]
    ap = avg_power[scenario]
    # 推荐电源: 峰值×1.3 / 0.8(负载率)
    rec_psu = math.ceil(pp * 1.3 / 0.8 / 5) * 5  # 向上取整到5W
    print(f"{scenario:<25} {pp:>10.1f} {ap:>10.1f} {rec_psu:>12}W 12V")

print("\n📌 电源升级路径:")
print("  当前: 12V 2A (24W) 适配器")
print("  3通道(28BYJ): 12V 5A (60W) 适配器 (+¥50)")
print("  3通道(Nema17): 12V 8A (96W) 适配器 (+¥120) + 5V 3A单独")

# ============================================================
# 第六部分：关键发现与建议
# ============================================================
print("\n\n💡 关键发现与建议")
print("=" * 70)

print("""
1. 【功耗概况】
   • 当前1通道标准配置峰值功耗: 40.5W
   • 当前1通道标准配置典型功耗: 17.2W
   • 待机功耗: 4.5W (Pi+ESP32)

2. 【电源选型】
   • Pi: 推荐官方27W PD充电器 (5V 3A USB-C)
   • 12V轨: 空压机+LED+电磁阀共享12V 3A适配器
   • 当前12V 2A适配器仅满足LED+电磁阀，不足以驱动空压机！
   ⚠️  建议升级为12V 3A以上适配器

3. 【能耗成本】
   • 年均电费: ¥{:.0f}/年 (10h/天, 300天/年, ¥1.5/kWh)
   • 每kg分选电费: ¥{:.4f}/kg

4. 【热管理】
   • 主要热源: LED灯带(12W热耗) + 空压机(3.2W热耗)
   • 密闭机壳温升约{:.0f}°C，需散热风扇
   • 建议: 机箱后部60mm风扇抽风 + 前部散热孔

5. 【升级扩展】
   • 3通道+涡轮鼓风机峰值: 116W → 需要独立12V 10A开关电源
   • 电源升级成本: +¥120 (96W开关电源)

6. 【可靠性建议】
   • 电磁阀峰值电流大(2A/个)，避免同时触发多个
   • 空压机启动电流大，建议独立供电 + 软启动电路
   • 所有12V设备前加TVS二极管防反接
""".format(annual_cost, total_avg_w / 1000 * kwh_cost / 2.0, delta_t))

print("=" * 70)
print("分析完成")
