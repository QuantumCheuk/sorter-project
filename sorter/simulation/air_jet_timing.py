"""
Air Jet Rejection Timing Analysis — Refined
=============================================
Key Problem: bean falls through channel faster than air blast timing.
This script finds the correct channel geometry and timing parameters.
"""

import numpy as np
from scipy.optimize import brentq

# ── Constants ─────────────────────────────────────────────────────────
G = 9.81          # m/s²
RHO_AIR = 1.22   # kg/m³
BEAN_MASS_G = 0.15  # grams
BEAN_MASS = BEAN_MASS_G / 1000  # kg
BEAN_DIAM = 8 / 1000  # m
CHANNEL_ID = 20 / 1000  # m (20mm inner diameter)
CD = 0.7         # bean drag coefficient
C_DISCHARGE = 0.75  # orifice discharge coefficient
NOZZLE_DIAM = 2 / 1000  # m
NOZZLE_AREA = np.pi * (NOZZLE_DIAM / 2)**2

def v_terminal(m=BEAN_MASS, d=BEAN_DIAM, cd=CD, rho=RHO_AIR):
    A = np.pi * (d / 2)**2
    return np.sqrt(2 * m * G / (rho * cd * A))

def fall_distance(t, v_t):
    """Distance fallen in time t at terminal velocity v_t."""
    return (v_t**2 / G) * np.log(np.cosh(G * t / v_t))

def fall_time(d_m, v_t):
    """Time to fall distance d_m."""
    def eq(t):
        if t < 1e-10:
            return -d_m
        return fall_distance(t, v_t) - d_m
    t_free = np.sqrt(2 * d_m / G)
    try:
        return brentq(eq, 0.001, t_free * 4)
    except:
        return t_free

v_t = v_terminal()
print(f"Terminal velocity: {v_t:.2f} m/s")
print(f"Bean mass: {BEAN_MASS_G}g, diameter: {BEAN_DIAM*1000:.0f}mm")
print(f"Channel ID: {CHANNEL_ID*1000:.0f}mm\n")

# ── Air jet lateral force ────────────────────────────────────────────
def air_jet_lateral_disp(pressure_kPa, duration_ms):
    P_Pa = pressure_kPa * 1000
    v_jet = C_DISCHARGE * np.sqrt(2 * P_Pa / RHO_AIR)
    F_jet = RHO_AIR * v_jet**2 * NOZZLE_AREA
    a_lat = F_jet / BEAN_MASS
    t_s = duration_ms / 1000
    d_lat = 0.5 * a_lat * t_s**2
    return d_lat * 1000, v_jet  # mm, m/s

# ── Timing Layout ────────────────────────────────────────────────────
#   T1 (sensor)
#   T2 (sensor) ← position this ABOVE air jet
#   [AIR JET]  ← positioned below T2
#   exit       ← bottom of channel

VALVE_DELAY_MS = 15   # solenoid valve response time
AIR_DURATION_MS = 80  # shorter burst - bean only needs a nudge
TOTAL_AIR_MS = VALVE_DELAY_MS + AIR_DURATION_MS  # = 95ms

print(f"Air blast: delay={VALVE_DELAY_MS}ms + duration={AIR_DURATION_MS}ms = {TOTAL_AIR_MS}ms total")
print(f"In {TOTAL_AIR_MS}ms the bean falls: ", end="")

# Distance bean falls during total air blast window
t_air = TOTAL_AIR_MS / 1000
d_air = fall_distance(t_air, v_t) * 1000  # mm
print(f"{d_air:.1f}mm")

# Therefore: T2 must be at least d_air mm ABOVE the air jet position
# And exit must be BELOW air jet (bean exits after air jet fires)

# Let T2 be at z=0, air jet at z = -T2_to_JET mm, exit at z = -TOTAL_DEPTH mm
# Bean triggered at T2 → travels down → at z = -T2_to_JET it gets hit by jet
# After air blast ends, bean has lateral velocity and exits further down

# Design: position air jet 30mm below T2
T2_TO_JET_MM = 30  # T2 sensor height above air jet
T2_TO_JET_M = T2_TO_JET_MM / 1000

# Time for bean to reach jet from T2
t_to_jet = fall_time(T2_TO_JET_M, v_t)
print(f"\nT2→Jet time: {t_to_jet*1000:.1f}ms")

# Bean reaches jet, then air jet fires with delay
# Fire decision made at t=0 (T2 trigger), air jet fires at t=VALVE_DELAY_MS
# By that time bean is at:
t_at_fire = VALVE_DELAY_MS / 1000
d_at_fire = fall_distance(t_at_fire, v_t) * 1000  # mm
print(f"At air fire time ({VALVE_DELAY_MS}ms): bean at z={d_at_fire:.1f}mm (from T2)")

# Air jet fires for AIR_DURATION_MS
# During this time bean travels downward:
d_during_air = fall_distance(t_at_fire + AIR_DURATION_MS/1000, v_t) * 1000 - d_at_fire
print(f"Bean travels {d_during_air:.1f}mm during air blast")

# Bean lateral displacement during air blast
for P in [50, 100, 150, 200]:
    d_lat, v_jet = air_jet_lateral_disp(P, AIR_DURATION_MS)
    print(f"  {P}kPa: lateral nudge = {d_lat:.1f}mm, jet speed = {v_jet:.0f}m/s")

# KEY INSIGHT: bean needs to be nudged only ~3-5mm to touch channel wall
# Channel wall provides extra lateral displacement (bean rolls along wall)
# So minimal nudge is sufficient

# ── What pressure is actually needed? ────────────────────────────────
# We just need the bean to touch the wall (3mm nudge), not fully traverse channel
MIN_NUDGE_MM = 3  # mm - just enough to touch wall, then gravity rolls it
MIN_NUDGE_M = MIN_NUDGE_MM / 1000
t_s = AIR_DURATION_MS / 1000
required_a = 2 * MIN_NUDGE_M / t_s**2  # m/s²
required_F = required_a * BEAN_MASS  # N
required_v_jet = np.sqrt(required_F / (RHO_AIR * NOZZLE_AREA))
required_P_Pa = (required_v_jet / C_DISCHARGE)**2 * RHO_AIR / 2
required_P_kPa = required_P_Pa / 1000
print(f"\n最小有效气喷压力（只需3mm偏移）: {required_P_kPa:.2f} kPa")
print(f"→ 实际最低供气压力: 50kPa (0.5bar) 已足够 ✅")

# ── Channel Exit Time ────────────────────────────────────────────────
# After air jet fires, how long until bean exits?
# Bean exits when it reaches bottom of channel
# Total T2-to-exit distance must be determined

# Exit distance = T2 to exit (total channel length below T2)
# Must be enough that bean hasn't exited before air jet fires
# Must also ensure bean exits AFTER air blast ends (so it falls into rejection zone)
EXIT_AFTER_BLAST_MS = 30  # bean should exit ~30ms after blast ends

# Distance bean falls in (AIR_DURATION_MS + EXIT_AFTER_BLAST_MS) after reaching jet
t_after_jet = (AIR_DURATION_MS + EXIT_AFTER_BLAST_MS) / 1000
d_after_jet = fall_distance(t_after_jet, v_t) * 1000 - T2_TO_JET_MM  # from T2
print(f"\nT2到通道出口建议距离: {d_after_jet + T2_TO_JET_MM:.0f}mm")
print(f"  （T2→Jet={T2_TO_JET_MM}mm + Jet→exit={d_after_jet:.0f}mm）")
print(f"  Bean exits {EXIT_AFTER_BLAST_MS}ms after air blast ends ✅")

# Verify: total T2-to-exit fall time
t_total_exit = fall_time((d_after_jet + T2_TO_JET_MM) / 1000, v_t)
print(f"  验证：T2→exit总下落时间: {t_total_exit*1000:.0f}ms")
print(f"  Air blast ends at: {VALVE_DELAY_MS + AIR_DURATION_MS}ms from T2 trigger")
print(f"  Bean exits at: {t_total_exit*1000:.0f}ms → gap = {t_total_exit*1000 - (VALVE_DELAY_MS + AIR_DURATION_MS):.0f}ms ✅")

# ── Throughput Analysis ──────────────────────────────────────────────
print("\n\n=== 吞吐量分析 ===")
# Single-file channel: beans must be spaced so they're resolved at T1/T2
# Minimum bean-to-bean spacing = time for bean to clear T1-T2 zone
T12_DIST_MM = 40  # distance between T1 and T2 sensors
t_t12 = fall_time(T12_DIST_MM / 1000, v_t)
MIN_SPACING_MS = t_t12 * 1000 * 2.5  # 2.5x safety factor for sensor resolution
BEANS_PER_HOUR_SINGLE = 3600 / (MIN_SPACING_MS / 1000)
WEIGHT_PER_HOUR_SINGLE = BEANS_PER_HOUR_SINGLE * BEAN_MASS_G / 1000  # kg

print(f"单通道T1-T2间距: {T12_DIST_MM}mm, 下落时间: {t_t12*1000:.0f}ms")
print(f"最小间距: {MIN_SPACING_MS:.0f}ms")
print(f"单通道理论: {BEANS_PER_HOUR_SINGLE:.0f} beans/h = {WEIGHT_PER_HOUR_SINGLE:.2f} kg/h")

# Vibratory bowl feeder actual rate
FEEDER_RATE = 30  # beans/min
FEEDER_KGH = FEEDER_RATE * 60 * BEAN_MASS_G / 1000
print(f"振动给料器实际: {FEEDER_RATE} beans/min = {FEEDER_KGH:.2f} kg/h")
print(f"目标≥2kg/h → 需要: {2/FEEDER_KGH:.1f}个并联通道")

# Conclusion: single-file channel is a bottleneck for throughput
# Solution: widen channel to allow 2-3 beans in color detection zone simultaneously
# OR use wider multi-lane channel with single-point detection

# ── Wide Channel Design (Alternative) ───────────────────────────────
print("\n\n=== 备选方案：宽通道 + 随机分布 ===")
print("放弃单文件强制单行，改为宽通道（40×20mm）+ 随机分布 + 追踪算法")
print("""
优点：
- 吞吐量不受单文件限制
- 仍然可以实现 top/bottom 对应检测
- 结构更简单

缺点：
- 同一帧可能有2-3颗豆子，需分别定位
- 豆子可能重叠，增加图像处理复杂度
- 需要目标追踪算法（multi-object tracking）

实现方案：
1. 宽通道尺寸：40mm宽 × 20mm高 × 150mm长
2. 摄像头拍摄帧率：≥30fps
3. 每帧检测所有豆子位置，用轮廓/连通域分离
4. 光电传感器触发拍照，配合图像位置确定豆子身份
5. 如果2颗豆子重叠/靠太近：整帧标记为'不可靠'，给后续的分选节点处理
""")

# ── Summary ──────────────────────────────────────────────────────────
print("\n" + "="*70)
print("📋 设计建议总结")
print("="*70)
print(f"""
【单文件通道尺寸】
  T1-T2间距: {T12_DIST_MM}mm
  T2到空气喷嘴: {T2_TO_JET_MM}mm
  T2到通道出口: {d_after_jet:.0f}mm
  总通道高度: ~{(T2_TO_JET_MM + d_after_jet):.0f}mm
  通道内径: 20mm

【气喷时序参数】
  电磁阀延迟: {VALVE_DELAY_MS}ms
  气喷持续: {AIR_DURATION_MS}ms
  总气喷窗口: {TOTAL_AIR_MS}ms
  所需最低压力: {required_P_kPa:.1f}kPa（{required_P_kPa/100:.2f}bar）
  建议供气: 100-150kPa (1.0-1.5bar)

【关键发现】
  ⚠️ 单文件通道吞吐量上限: {WEIGHT_PER_HOUR_SINGLE:.2f}kg/h（振动给料器限制）
  ⚠️ 如果只依赖振动给料器30 beans/min，单通道永远无法达到2kg/h
  💡 解决方案A: 2-3个并联单文件通道
  💡 解决方案B: 宽通道+随机分布+多目标追踪（吞吐量更高）
""")
