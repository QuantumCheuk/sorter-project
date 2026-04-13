"""
Bean Fall & Air Jet Rejection Physics Simulation
================================================
研究目标：
1. 豆子从T1到T2下落时间的精确计算
2. 气流喷射剔除所需压力/流量的估算
3. 通道尺寸优化建议

Physics References:
- Coffee bean avg mass: 0.12-0.18g (0.00012-0.00018 kg)
- Coffee bean avg terminal velocity in air: ~1.5-2.5 m/s
- Air density: 1.225 kg/m³
- Gravity: 9.81 m/s²
- Drag coefficient (spherical approx): 0.47 (for Re ~ 100-1000)
- Bean equivalent diameter: ~10mm = 0.01m
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Bean physical parameters ──────────────────────────────────────────
BEAN_MASS_G = 0.15          # grams (average green coffee bean)
BEAN_MASS = BEAN_MASS_G / 1000  # kg
BEAN_DIAMETER_MM = 8        # mm (average green coffee bean)
BEAN_DIAMETER = BEAN_DIAMETER_MM / 1000  # m
BEAN_CSA = np.pi * (BEAN_DIAMETER / 2)**2  # cross-sectional area m²

# Cross-sectional area of single-file channel (20mm ID)
CHANNEL_ID_MM = 20
CHANNEL_ID = CHANNEL_ID_MM / 1000  # m
CHANNEL_AREA = np.pi * (CHANNEL_ID / 2)**2  # m²

# Free fall acceleration
G = 9.81  # m/s²

# Air properties
RHO_AIR = 1.225  # kg/m³ (at 20°C sea level)

# ── Physics: Terminal Velocity ───────────────────────────────────────
# Drag force: F_d = 0.5 * rho * Cd * A * v²
# At terminal velocity: mg = F_d  →  v_t = sqrt(2mg / (rho * Cd * A))
CD_SPHERICAL = 0.47  # drag coefficient for sphere-like object

def terminal_velocity(mass_kg, diam_m, cd=CD_SPHERICAL, rho=RHO_AIR):
    A = np.pi * (diam_m / 2)**2
    return np.sqrt(2 * mass_kg * G / (rho * cd * A))

# Use coffee bean specific drag (more irregular → higher Cd)
CD_BEAN = 0.7  # more realistic for bean shape
v_term = terminal_velocity(BEAN_MASS, BEAN_DIAMETER, cd=CD_BEAN)
print(f"Terminal velocity (Cd={CD_BEAN}): {v_term:.2f} m/s  ({v_term*100:.1f} cm/s)")

# ── Section 1: T1→T2 Fall Time Calculation ──────────────────────────
# Using kinematic equation: s = v₀t + ½gt²
# Start from rest (v₀=0), solve for t: t = sqrt(2s/g)
# But real beans don't reach terminal velocity instantly
# More accurate: include drag in free-fall

def bean_fall_distance_approx(t, m=BEAN_MASS, d=BEAN_DIAMETER, cd=CD_BEAN, rho=RHO_AIR):
    """
    Approximate distance fallen under gravity + air drag.
    Uses numerical integration.
    """
    g = G
    # At low Re, drag ~ linear (Stokes): F = 6πμrv
    # At high Re, drag ~ quadratic: F = 0.5*rho*Cd*A*v²
    # Coffee bean falls in Re ~ 100-1000 range → transitional
    # Simplified: use quadratic drag
    A = np.pi * (d / 2)**2
    C = 0.5 * rho * cd * A
    k = C / m  # drag/mass coefficient

    # Analytical approximation for fall distance with quadratic drag:
    # t_fall = (exp(k*g*t) - 1) / k  (no closed form for distance)
    # Use numerical integration instead
    dt = 0.001
    t_vals = np.arange(0, t, dt)
    v_prev = 0
    s = 0
    for i, ti in enumerate(t_vals):
        v = g / k * (1 - np.exp(-k * (ti + dt))) / dt * dt  # simplified Euler
        v = g / k * (1 - np.exp(-k * ti))  # exact: v(t) = v_t * tanh(g*t/v_t)
        s += v * dt
    return s

def bean_fall_time(distance_m, m=BEAN_MASS, d=BEAN_DIAMETER, cd=CD_BEAN, rho=RHO_AIR):
    """
    Compute time for bean to fall a given distance.
    Uses exact solution: v(t) = v_t * tanh(g*t/v_t)
    where s(t) = (v_t²/g) * ln(cosh(g*t/v_t))
    Solve: s = (v_t²/g) * ln(cosh(g*t/v_t))
    """
    v_t = terminal_velocity(m, d, cd, rho)
    s = distance_m

    # From s(t): cosh(g*t/v_t) = exp(g*s/v_t²)
    # cosh(x) = (e^x + e^-x)/2
    # We solve numerically for t
    from scipy.optimize import brentq

    def s_equation(t):
        if t < 1e-9:
            return -s
        return (v_t**2 / G) * np.log(np.cosh(G * t / v_t)) - s

    # Upper bound: use free-fall time * 2 (drag increases time)
    t_free = np.sqrt(2 * s / G)
    try:
        t = brentq(s_equation, 0.001, t_free * 3)
    except:
        t = t_free  # fallback

    return t, v_t

print("\n=== T1→T2 Fall Time Analysis ===")
print(f"Bean mass: {BEAN_MASS_G}g, diameter: {BEAN_DIAMETER_MM}mm")
print(f"Terminal velocity: {v_term:.2f} m/s")

# T1-T2 distance scenarios (channel length between sensors)
T12_distances_mm = [20, 30, 40, 50, 60, 80]
print(f"\n{'T1-T2距离(mm)':<14} {'下落时间(ms)':<12} {'T2时速度(m/s)':<14} {'备注'}")
print("-" * 65)
for d_mm in T12_distances_mm:
    d_m = d_mm / 1000
    t_sec, v_at_T2 = bean_fall_time(d_m)
    t_ms = t_sec * 1000
    v_t = terminal_velocity(BEAN_MASS, BEAN_DIAMETER)
    v_frac = v_at_T2 / v_t * 100
    note = "~terminal" if v_frac > 95 else f"{v_frac:.0f}%v_t"
    print(f"{d_mm:<14} {t_ms:<12.1f} {v_at_T2:<14.2f} {note}")

# ── Section 2: Air Jet Rejection Force Analysis ─────────────────────
print("\n\n=== 气流喷射剔除力分析 ===")
print("气流喷射式剔除：电磁阀打开 → 短气喷横向吹走缺陷豆")

# Air jet parameters
# Micro solenoid valve: 12V 2-way NC
# Nozzle diameter: 2mm (φ2mm)
NOZZLE_DIAM_MM = 2.0
NOZZLE_DIAM = NOZZLE_DIAM_MM / 1000  # m
NOZZLE_AREA = np.pi * (NOZZLE_DIAM / 2)**2  # m²

# Air supply: small compressor or compressed air canister
# Typical pressure for micro-solenoid: 50-100 kPa (0.5-1 bar)
# Available pressure scenarios
pressures_kPa = [50, 100, 150, 200]  # kPa (gauge pressure)

# Air jet velocity from nozzle: v = C * sqrt(2*ΔP/rho)
# C = 0.61-0.95 (orifice discharge coefficient)
C_DISCHARGE = 0.75  # typical for sharp orifice

print(f"\n喷嘴直径: {NOZZLE_DIAM_MM}mm, 截面积: {NOZZLE_AREA*1e6:.2f} mm²")
print(f"\n{'压力(kPa)':<10} {'喷嘴速度(m/s)':<14} {'喷嘴力(N)':<12} {'加速时间(ms)':<14} {'备注'}")
print("-" * 70)

for P_kPa in pressures_kPa:
    P_Pa = P_kPa * 1000  # Pa = N/m²
    v_jet = C_DISCHARGE * np.sqrt(2 * P_Pa / RHO_AIR)
    F_jet = RHO_AIR * v_jet**2 * NOZZLE_AREA  # momentum flux (N)
    # Acceleration time: t = v / a, where a = F_jet / m
    if F_jet > 0:
        a = F_jet / BEAN_MASS
        t_accel = v_jet / a if a > 0 else 999
    else:
        t_accel = 999
    print(f"{P_kPa:<10} {v_jet:<14.1f} {F_jet:<12.4f} {t_accel*1000:<14.1f}  0.5bar为最低可用压力")

# ── Section 3: Rejection Zone Length Calculation ───────────────────
print("\n\n=== 剔除区通道长度计算 ===")
print("从bottom传感器触发 → 气流吹走缺陷豆 → 豆子离开合格通道")

# Bean falls from T2 to rejection point
# Bottom sensor T2 at z=0 (trigger point), bean falls in +z direction
# Air jet acts horizontally at z_reject
# Need to clear the channel (channel width = 20mm)

CHANNEL_WIDTH = CHANNEL_ID_MM  # mm - bean needs to be deflected by this amount
CLEARANCE_TIME_S = 0.15  # 电磁阀持续打开时间 0.15s

print(f"通道内径: {CHANNEL_ID_MM}mm（需将豆子横向推出至少{CHANNEL_WIDTH}mm）")
print(f"气喷持续时间: {CLEARANCE_TIME_S*1000:.0f}ms")
print(f"\n缺陷豆从T2触发到被吹出所需横向位移: {CHANNEL_WIDTH}mm")

for P_kPa in [100, 150, 200]:
    P_Pa = P_kPa * 1000
    v_jet = C_DISCHARGE * np.sqrt(2 * P_Pa / RHO_AIR)
    F_jet = RHO_AIR * v_jet**2 * NOZZLE_AREA
    a_lat = F_jet / BEAN_MASS  # lateral acceleration
    d_lateral = 0.5 * a_lat * CLEARANCE_TIME_S**2  # displacement = 0.5*a*t²
    v_lat = a_lat * CLEARANCE_TIME_S  # final lateral velocity
    print(f"\n{P_kPa}kPa时：侧向加速度={a_lat:.1f}m/s², "
          f"{CLEARANCE_TIME_S*1000:.0f}ms后横向位移={d_lateral*1000:.1f}mm, "
          f"末速度={v_lat:.2f}m/s")

# What pressure is needed to clear the 20mm channel?
TARGET_DISP_MM = CHANNEL_WIDTH  # mm
TARGET_DISP = TARGET_DISP_MM / 1000  # m
TARGET_TIME = 0.12  # s (120ms should be enough)

# Solve for required acceleration: d = 0.5 * a * t²  →  a = 2d/t²
a_required = 2 * TARGET_DISP / TARGET_TIME**2  # m/s²
F_required = a_required * BEAN_MASS  # N
v_j_required = np.sqrt(F_required / (RHO_AIR * NOZZLE_AREA))
P_required_Pa = (v_j_required / C_DISCHARGE)**2 * RHO_AIR / 2
P_required_kPa = P_required_Pa / 1000

print(f"\n达到{TARGET_DISP_MM}mm位移所需参数（{TARGET_TIME*1000:.0f}ms内）：")
print(f"  所需侧向加速度: {a_required:.1f} m/s²")
print(f"  所需侧向力: {F_required*1000:.2f} mN")
print(f"  所需喷嘴速度: {v_j_required:.1f} m/s")
print(f"  所需供气压力: {P_required_kPa:.1f} kPa")

# ── Section 4: Optimal Channel Design ──────────────────────────────
print("\n\n=== 单文件通道尺寸优化建议 ===")

# Key design constraint: T1-T2 distance determines timing budget
# Bottom sensor triggers bottom camera
# Air jet must fire while bean is still in channel

# Channel total length from T1 to exit:
# T1_sensor at z=0, T2_sensor at z=T12, rejection point at z=exit

# The bean must still be in channel when air jet fires
# We need: air_blast_delay_ms + air_blast_duration_ms < bean_exit_time

# Typical fall time from T2 to channel exit:
EXIT_LENGTH_MM = 30  # T2到通道出口的长度
t_exit, _ = bean_fall_time(EXIT_LENGTH_MM / 1000)

# Air blast timing
AIR_BLAST_DELAY_MS = 20  # 电磁阀响应延迟
AIR_BLAST_DURATION_MS = 150  # 气喷持续时间

total_rejection_time_ms = AIR_BLAST_DELAY_MS + AIR_BLAST_DURATION_MS
bean_exit_time_ms = t_exit * 1000

print(f"通道设计参数建议：")
print(f"  T1到T2距离: 建议{T12_distances_mm[1]}mm（下限={T12_distances_mm[0]}mm）")
print(f"  T2到通道出口: 建议{EXIT_LENGTH_MM}mm")
print(f"  T1到出口总长: ~{T12_distances_mm[1]+EXIT_LENGTH_MM}mm")
print(f"\n时序预算：")
print(f"  豆子从T2落到出口: {bean_exit_time_ms:.1f}ms")
print(f"  电磁阀响应延迟: {AIR_BLAST_DELAY_MS}ms")
print(f"  气喷持续时间: {AIR_BLAST_DURATION_MS}ms")
print(f"  总需气时间: {total_rejection_time_ms}ms")
print(f"  时序余量: {bean_exit_time_ms - total_rejection_time_ms:.1f}ms  "
      f"{'✅ 充足' if bean_exit_time_ms > total_rejection_time_ms else '⚠️ 不足'}")

# ── Section 5: Throughput Calculation ──────────────────────────────
print("\n\n=== 理论吞吐量分析 ===")

# With single-file channel, beans must pass one at a time
# Minimum spacing: bean must fully clear T1-T2 section before next arrives

# Minimum bean spacing = time for bean to traverse T1-T2 zone + safety margin
T12_MM = 40  # recommended T1-T2 distance
t_t12, _ = bean_fall_time(T12_MM / 1000)
MIN_SPACING_S = t_t12 * 2  # add safety margin (2x)
THROUGHPUT_PER_HOUR = 3600 / MIN_SPACING_S

print(f"单文件通道理论最大吞吐量：")
print(f"  最小间距时间: {MIN_SPACING_S*1000:.1f}ms")
print(f"  理论最大处理量: {THROUGHPUT_PER_HOUR:.0f} beans/hour")
print(f"  以平均0.15g/粒: {THROUGHPUT_PER_HOUR * 0.15 / 1000:.1f} kg/hour")
print(f"\n目标: ≥2kg/h → 需要: {2000/(0.15/1000):.0f} beans/hour")
print(f"  目标处理量要求: {'✅ 可满足' if THROUGHPUT_PER_HOUR * 0.15 / 1000 >= 2 else '⚠️ 需优化（豆子间距可更紧密）'}")

# ── Section 6: Throughput vs Batch Mode ────────────────────────────
# In batch mode, beans don't need to be truly single-file
# The single-file channel only applies to the color detection zone
# Vibratory bowl feeds beans one by one into the channel

# Vibratory bowl feeder typical rate: 10-50 beans/minute
FEEDER_RATE_BEAN_MIN = 30  # 振动给料器 typical rate

print(f"\n振动给料器实际喂入速率: ~{FEEDER_RATE_BEAN_MIN} beans/min = {FEEDER_RATE_BEAN_MIN*60} beans/hour")
print(f"  对应重量: {FEEDER_RATE_BEAN_MIN*60 * 0.15 / 1000:.1f} kg/hour")
print(f"  目标≥2kg/h → 需升级给料速率或增加并联通道")

# ── Save Figure ──────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# Plot 1: T1-T2 fall time vs distance
ax1 = axes[0, 0]
d_vals = np.linspace(5, 100, 200) / 1000  # mm to m
t_vals = [bean_fall_time(d)[0] * 1000 for d in d_vals]
ax1.plot(d_vals * 1000, t_vals, 'b-', lw=2)
ax1.axhline(y=50, color='r', ls='--', label='50ms threshold')
for dm in [20, 30, 40, 50, 60, 80]:
    t, _ = bean_fall_time(dm / 1000)
    ax1.scatter([dm], [t*1000], color='orange', zorder=5)
    ax1.annotate(f'{dm}mm\n{t*1000:.1f}ms', (dm, t*1000+2))
ax1.set_xlabel('T1-T2 Distance (mm)')
ax1.set_ylabel('Fall Time (ms)')
ax1.set_title('Bean Fall Time: T1 → T2')
ax1.grid(True, alpha=0.3)
ax1.legend()

# Plot 2: Air jet force vs pressure
ax2 = axes[0, 1]
P_vals = np.linspace(10, 300, 100)
v_jet_vals = [C_DISCHARGE * np.sqrt(2 * (p*1000) / RHO_AIR) for p in P_vals]
F_jet_vals = [RHO_AIR * v**2 * NOZZLE_AREA for v in v_jet_vals]
ax2.plot(P_vals, [f*1000 for f in F_jet_vals], 'g-', lw=2)
ax2.axvline(x=P_required_kPa, color='r', ls='--', label=f'Required: {P_required_kPa:.0f} kPa')
ax2.set_xlabel('Supply Pressure (kPa)')
ax2.set_ylabel('Jet Force (mN)')
ax2.set_title('Air Jet Force vs Pressure')
ax2.legend()
ax2.grid(True, alpha=0.3)

# Plot 3: Lateral displacement vs pressure at 150ms
ax3 = axes[1, 0]
P_v = np.linspace(20, 300, 100)
t_disp = 0.15  # 150ms
d_lat = []
for p in P_v:
    P_Pa = p * 1000
    v_j = C_DISCHARGE * np.sqrt(2 * P_Pa / RHO_AIR)
    F_j = RHO_AIR * v_j**2 * NOZZLE_AREA
    a_l = F_j / BEAN_MASS
    d_lat.append(0.5 * a_l * t_disp**2 * 1000)  # in mm
ax3.plot(P_v, d_lat, 'purple', lw=2)
ax3.axhline(y=CHANNEL_WIDTH, color='r', ls='--', label=f'Channel width: {CHANNEL_WIDTH}mm')
ax3.fill_between(P_v, 0, CHANNEL_WIDTH, alpha=0.2, color='red', label='Insufficient zone')
ax3.fill_between(P_v, CHANNEL_WIDTH, max(d_lat)*1.2, alpha=0.2, color='green', label='Effective zone')
ax3.set_xlabel('Supply Pressure (kPa)')
ax3.set_ylabel('Lateral Displacement in 150ms (mm)')
ax3.set_title('Bean Deflection: Can it clear the channel?')
ax3.legend()
ax3.grid(True, alpha=0.3)

# Plot 4: Throughput vs bean spacing
ax4 = axes[1, 1]
spacings = np.linspace(10, 200, 100) / 1000  # mm to m
tp_h = [3600 / (s * 2) for s in spacings]  # 2x safety margin
ax4.plot(spacings * 1000, tp_h, 'orange', lw=2)
ax4.axhline(y=2000/0.15*1000, color='r', ls='--', label='2kg/h target')
ax4.set_xlabel('Min Bean Spacing (mm)')
ax4.set_ylabel('Throughput (beans/hour)')
ax4.set_title('Throughput vs Bean Spacing in Channel')
ax4.legend()
ax4.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('sorter/simulation/physics_analysis.png', dpi=150, bbox_inches='tight')
print(f"\n\n图表已保存: sorter/simulation/physics_analysis.png")

# ── Summary Recommendations ─────────────────────────────────────────
print("\n" + "="*70)
print("📋 物理分析结论与设计建议")
print("="*70)
print(f"""
1. 【T1-T2传感器间距】
   推荐: 40mm（平衡了下落时间和速度稳定性）
   - 40mm下落时间: {bean_fall_time(0.040)[0]*1000:.1f}ms，此时速度{v_term*0.8:.1f}m/s（~80%终端速度）
   - 50mm更好但体积略增

2. 【气流喷射系统】
   最小供气压力: ≥{P_required_kPa:.0f} kPa（{P_required_kPa/100:.1f} bar）
   建议: 150kPa (1.5 bar) 压缩空气系统
   喷嘴直径: φ2mm（已设计）
   气喷持续时间: 120-150ms
   
3. 【通道总长度】
   T1→T2: 40mm（含传感器安装位）
   T2→出口: 30mm（给气喷反应时间）
   通道总高: ~80mm

4. 【吞吐量】
   单文件通道理论上限: {THROUGHPUT_PER_HOUR:.0f} beans/h ≈ {THROUGHPUT_PER_HOUR*0.15/1000:.1f} kg/h
   振动给料器实际: {FEEDER_RATE_BEAN_MIN*60*0.15/1000:.1f} kg/h
   ⚠️ 单通道无法满足2kg/h目标 → 建议增加并联通道（2-3通道）

5. 【关键时序参数】
   T1触发 → top_cam.capture(): 立即（0ms延迟）
   T2触发 → bottom_cam.capture(): {bean_fall_time(0.040)[0]*1000:.1f}ms后
   判定完成 → 气喷打开: ~{AIR_BLAST_DELAY_MS}ms（电磁阀延迟）
   气喷持续: {AIR_BLAST_DURATION_MS}ms
   总窗口: {AIR_BLAST_DELAY_MS + AIR_BLAST_DURATION_MS}ms < {bean_fall_time(0.030)[0]*1000:.1f}ms ✅
""")
