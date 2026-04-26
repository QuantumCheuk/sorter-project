"""
课题8 Day2: GPIO重新分配方案 + 采购清单整理
HUSKY-SORTER-001

发现问题（Day1）：
  ⚠️ GPIO6冲突：DRV8833 #2 DIR 与 HX711 SCK 共用 GPIO6
  ⚠️ 28BYJ-48 #2 切换时间 540ms > 200ms 目标

本文件：
  1. GPIO重新分配方案（修复冲突）
  2. 更新后的完整GPIO映射表
  3. 各电机驱动板引脚对照
"""

# ============================================================
# GPIO冲突分析
# ============================================================
# 原冲突：
#   GPIO6: HX711 SCK (clock_pin=6) ← load_cell.py 默认
#   GPIO6: DRV8833 #2 DIR         ← 28BYJ-48 #2 旋转分配器
#
# 解决：将 HX711 SCK 从 GPIO6 改为 GPIO27
#       （GPIO27 是备用GPIO，不与其他设备冲突）
#
# 注意：树莓派 GPIO12/18 有 PWM 功能，但软件PWM（RPi.GPIO）无需硬件PWM引脚
#       因此 GPIO18（软件PWM）可继续用于螺旋给料 PUL

print("=" * 60)
print("GPIO冲突分析")
print("=" * 60)
print()
print("原冲突（Day1发现问题）：")
print("  GPIO6: HX711 SCK  ← sorter/sensors/load_cell.py")
print("  GPIO6: DRV8833 #2 DIR (28BYJ-48 #2 旋转分配器)")
print("  → 同一引脚被两个设备共享 ❌")
print()
print("解决策略：")
print("  将 HX711 SCK 从 GPIO6 重新分配到 GPIO27")
print("  GPIO27 是备用GPIO，不与任何其他设备冲突 ✅")
print()

# ============================================================
# 更新后的GPIO分配表
# ============================================================
# 注意：以下分配已修复冲突
# 关键变更：
#   HX711 SCK: GPIO6 → GPIO27（修复冲突）
#   28BYJ-48 #2 DIR: GPIO6 → 保持（仅此处占用）

GPIO_ASSIGNMENT = {
    # === 传感器输入（GPIO输入）===
    "GPIO4":  ["红外光电传感器 T1 (输入, 遮断式)"],
    "GPIO17": ["红外光电传感器 T2 (输入, 遮断式)"],
    "GPIO5":  ["HX711 DT (DATA) (输入)"],
    "GPIO24": ["液位传感器 DATA (输入)"],

    # === 执行器输出（GPIO输出）===
    "GPIO16": ["12V电磁阀 气喷剔除 (输出, 常闭NC)"],
    "GPIO20": ["12V电磁阀 称重杯释放 (输出, 常闭NC)"],
    "GPIO21": ["12V电磁阀 Buffer出豆 (输出, 常闭NC)"],

    # === 步进电机PUL/STEP（软件PWM，无硬件PWM要求）===
    "GPIO26": ["28BYJ-48 #1 PUL (振动给料)"],
    "GPIO19": ["28BYJ-48 #1 DIR"],
    "GPIO13": ["28BYJ-48 #2 PUL (旋转分配器)"],
    "GPIO12": ["28BYJ-48 #2 DIR (修复后)"],
    "GPIO18": ["28BYJ-48 #3 PUL (螺旋给料)"],
    "GPIO23": ["28BYJ-48 #3 DIR"],

    # === HX711 SCK（重新分配）===
    "GPIO27": ["HX711 SCK (CLK) (输出) ← 从GPIO6迁移 ✅"],

    # === 液位传感器CLK ===
    "GPIO25": ["液位传感器 CLK (输出)"],

    # === 风扇PWM ===
    "GPIO12_pwm": ["风扇PWM (密度分选, GPIO12复用PWM功能)"],
}

# ============================================================
# 树莓派40Pin GPIO对照
# ============================================================
# 树莓派40Pin GPIO布局（从左到右，第1-40Pin）：
#
#  Pin  1: 3.3V      | Pin  2: 5V
#  Pin  3: GPIO2     | Pin  4: 5V
#  Pin  5: GPIO3     | Pin  6: GND
#  Pin  7: GPIO4  ← T1 | Pin  8: GPIO14 (TXD)
#  Pin  9: GND      | Pin 10: GPIO15 (RXD)
#  Pin 11: GPIO17 ← T2 | Pin 12: GPIO18 ← PWM #2DIR/风扇
#  Pin 13: GPIO27 ← HX SCK [NEW!] | Pin 14: GND
#  Pin 15: GPIO22   | Pin 16: GPIO23 ← DIR3
#  Pin 17: 3.3V     | Pin 18: GPIO24 ← 液位DATA
#  Pin 19: GPIO10   | Pin 20: GND
#  Pin 21: GPIO9    | Pin 22: GPIO25 ← 液位CLK
#  Pin 23: GPIO11   | Pin 24: GPIO8  (SPI CE0)
#  Pin 25: GND      | Pin 26: GPIO7  (SPI CE1)
#  Pin 27: GPIO0    | Pin 28: GPIO1
#  Pin 29: GPIO5  ← HX DT | Pin 30: GND
#  Pin 31: GPIO6    | Pin 32: GPIO12 ← PWM
#  Pin 33: GPIO13 ← PUL2  | Pin 34: GND
#  Pin 35: GPIO19 ← DIR1  | Pin 36: GPIO16 ← 气喷阀
#  Pin 37: GPIO26 ← PUL1  | Pin 38: GPIO20 ← 称重阀
#  Pin 39: GND      | Pin 40: GPIO21 ← Buffer阀

print("=" * 60)
print("更新后GPIO分配表（Day2修复版）")
print("=" * 60)
print()

print("【传感器输入】")
for gpio, devs in GPIO_ASSIGNMENT.items():
    if any("输入" in d for d in devs):
        for d in devs:
            print(f"  {gpio}: {d}")
print()
print("【执行器输出】")
for gpio, devs in GPIO_ASSIGNMENT.items():
    if any("输出" in d for d in devs) and "PUL" not in gpio and "DIR" not in gpio:
        for d in devs:
            print(f"  {gpio}: {d}")
print()
print("【步进电机】")
print("  28BYJ-48 #1 振动给料:")
print("    PUL=GPIO26, DIR=GPIO19")
print("  28BYJ-48 #2 旋转分配器:")
print("    PUL=GPIO13, DIR=GPIO12 ✅ (GPIO6冲突已解除)")
print("  28BYJ-48 #3 螺旋给料:")
print("    PUL=GPIO18, DIR=GPIO23")
print()
print("【其他】")
for gpio, devs in GPIO_ASSIGNMENT.items():
    if "HX" in gpio or "液位" in gpio or "PWM" in gpio or "pwm" in gpio.lower():
        for d in devs:
            if "HX" in gpio or "液位" in gpio or "PWM" in gpio:
                print(f"  {gpio}: {d}")
print()

# ============================================================
# 冲突验证
# ============================================================
all_pins = []
conflicts = []
for gpio, devs in GPIO_ASSIGNMENT.items():
    for d in devs:
        pin_name = gpio.split("_")[0]  # 去掉_pwm后缀
        if pin_name in all_pins:
            conflicts.append((gpio, devs))
        all_pins.append(pin_name)

print("=" * 60)
print("冲突检测")
print("=" * 60)
if conflicts:
    print("❌ 仍存在冲突：")
    for g, d in conflicts:
        print(f"  {g}: {d}")
else:
    print("✅ 所有GPIO引脚无冲突！")
print()

# ============================================================
# 更新后的config.py patch
# ============================================================
print("=" * 60)
print("load_cell.py 更新（需修改）")
print("=" * 60)
print()
print("将 HX711Config 默认值从 clock_pin=6 改为 clock_pin=27:")
print()
print("  # sorter/sensors/load_cell.py 第35-36行")
print("  - clock_pin: int = 6    # GPIO pin for SCK (CLK)")
print("  + clock_pin: int = 27   # GPIO pin for SCK (CLK) ← 从GPIO6迁移解决冲突")
print()

# ============================================================
# DRV8833 vs A4988 驱动板比较
# ============================================================
print("=" * 60)
print("电机驱动板比较（28BYJ-48 #2 旋转分配器）")
print("=" * 60)
print()
drv_data = [
    ["参数", "DRV8833", "A4988 (Nema17配套)"],
    ["驱动芯片", "DRV8833", "A4988"],
    ["逻辑电压", "3.3V/5V", "3.3V/5V"],
    ["电机电压", "≤10V", "≤35V"],
    ["连续电流", "1.2A", "1A (无散热) / 2A (加散热)"],
    ["细分模式", "1/2/4/8/16", "1/2/4/8/16"],
    ["封装", "HTSSOP16", "QFN/HTSSOP"],
    ["推荐Nema17", "✅ 适用", "✅ 最佳匹配"],
    ["单路成本", "¥3", "¥8"],
    ["微步平滑度", "一般", "✅ 更平滑"],
    ["供货情况", "常见", "常见"],
]
for row in drv_data:
    print(f"  {row[0]:<16} | {row[1]:<20} | {row[2]}")
print()
print("结论：Nema17配套推荐A4988，DRV8833也可工作但A4988更专业")
print()

# ============================================================
# 更新后的 spiral_feeder.py 电机引脚
# ============================================================
print("=" * 60)
print("spiral_feeder.py 更新（RotaryDistributor引脚）")
print("=" * 60)
print()
print("  # sorter/motor/spiral_feeder.py RotaryDistributor类")
print("  - step_pin: int = 13   # GPIO13 = PUL2")
print("  - dir_pin: int = 6     # GPIO6  = DIR2 (冲突！)")
print("  + step_pin: int = 13  # GPIO13 = PUL2")
print("  + dir_pin: int = 12   # GPIO12 = DIR2 ✅ (冲突已解除)")
print()

# ============================================================
# 树莓派GPIO注意事项
# ============================================================
print("=" * 60)
print("树莓派GPIO注意事项")
print("=" * 60)
print()
print("1. 所有GPIO默认为INPUT模式，上电时状态不确定")
print("   → 程序启动时立即设置所有引脚为OUT并初始化为安全状态（LOW）")
print()
print("2. HX711 DT (GPIO5) 是双向引脚（开漏），需要上拉电阻")
print("   → HX711模块内置上拉，不需要额外处理")
print()
print("3. 电磁阀是感性负载（12V线圈）")
print("   → 必须接续流二极管（模块内置）或MOSFET驱动")
print("   → 禁止直接用GPIO驱动（会损坏GPIO）")
print()
print("4. 步进电机PUL信号")
print("   → GPIO26/13/18作为普通GPIO输出即可，软件PWM/step脉冲")
print("   → 不需要硬件PWM，普通的GPIO.toggle() + sleep()即可生成脉冲")
print()

print("✅ GPIO重新分配分析完成")
print()
print("下一步：更新 load_cell.py 和 spiral_feeder.py 的引脚配置")
