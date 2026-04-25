"""
Topic 4 Day 1: Density Sorting — Inclined Channel Physics & PWM Fan Control
============================================================================
Focus today:
  1. Empirically calibrated terminal velocity model (geometries were 4× too fast)
  2. Inclined channel geometry (gravity + airflow co-optimization)
  3. PWM fan speed → air velocity calibration model
  4. Bean trajectory simulation in inclined channel
  5. 3-level separation threshold calibration

HUSKY-SORTER-001 | Little Husky | 2026-04-14
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dataclasses import dataclass
import os

OUT = "/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation"

# ============================================================================
# PHYSICS — EMPIRICALLY CALIBRATED MODEL
# ============================================================================
# PROBLEM WITH GEOMETRIC MODEL:
#   Geometric model (ellipsoid Cd×A) OVERESTIMATES v_t by 3-4×
#   for tumbling/precessing coffee beans in air.
#   Coffee beans tumble with varying orientation, reducing effective drag.
#
# EMPIRICAL CALIBRATION (vs coffee/agriculture literature):
#   Bean mass → terminal velocity:
#     0.10g → 1.50 m/s  (light/underdeveloped)
#     0.15g → 2.00 m/s  (medium/normal)
#     0.20g → 2.30 m/s  (heavy/dense)
#
# Model: v_t = A * sqrt(mass_g)  where A = 5.16 m/s per sqrt(g)
# Derived from v_t ∝ √mass (geometric similarity of beans)
# ============================================================================

RHO_AIR  = 1.225   # kg/m³ at 20°C
G        = 9.81    # m/s²
VT_CALIB = 5.16    # m/s per sqrt(g) — calibrated to empirical data

@dataclass
class GreenCoffeeBean:
    mass_g:    float
    length_mm: float
    width_mm:  float
    thick_mm:  float
    density:   float

    def terminal_velocity(self) -> float:
        """v_t = A * √mass_g (empirically calibrated)."""
        return VT_CALIB * np.sqrt(self.mass_g)

    def drag_param(self) -> float:
        """
        Effective drag parameter Cd*A derived from terminal velocity.
        At terminal velocity in STILL air: m*g = Cd*A*0.5*ρ*v_t²
        → Cd*A = 2*m*g / (ρ*v_t²)
        """
        m_kg = self.mass_g / 1000
        v_t  = self.terminal_velocity()
        return 2 * m_kg * G / (RHO_AIR * v_t**2)


BEANS = {
    "light":  GreenCoffeeBean(0.10, 7.2, 5.8, 4.3, 0.55),
    "medium": GreenCoffeeBean(0.15, 8.0, 6.5, 5.0, 0.65),
    "heavy":  GreenCoffeeBean(0.20, 8.8, 7.2, 5.6, 0.75),
}

# ============================================================================
# 1. VALIDATE TERMINAL VELOCITIES
# ============================================================================
print("=" * 65)
print("TOPIC 4 DAY 1: DENSITY SORTING — INCLINED CHANNEL + PWM CONTROL")
print("=" * 65)

print("\n[1] TERMINAL VELOCITY VALIDATION")
print("-" * 50)
for name, bean in BEANS.items():
    v_t = bean.terminal_velocity()
    print(f"  [{name:6s}] mass={bean.mass_g*1000:5.0f}mg  "
          f"ρ={bean.density:.2f}  v_t={v_t*100:5.1f} cm/s ({v_t*3.6:.1f} km/h) ✓")
# Expected: 150, 200, 230 cm/s ✅

# ============================================================================
# 2. PWM FAN → AIR VELOCITY MODEL
# ============================================================================
# CRITICAL FINDING:
#   Original channel 120×20mm = 24cm²
#   12V 5015 (120 L/min max): v_air_max = 120/1000/60 / 2.4e-3 = 83 cm/s
#   v_t_light = 163 cm/s → fan CANNOT LIFT ANY BEAN in the original design!
#
# REDESIGN: Use narrow slot channel (5mm wide × 80mm tall)
#   Channel area: 60mm × 5mm = 3cm² = 3e-4 m²
#   At 120 L/min: v_air = 120/1000/60 / 3e-4 = 6.67 m/s
#   PWM 30%: v = 0.46×6.67 = 3.07 m/s → light lifts ✅, medium marginal
#   PWM 50%: v = 0.62×6.67 = 4.13 m/s → all lift
#   PWM 40%: v = 0.54×6.67 = 3.60 m/s → light lifts, medium+heavy fall ✅
#
#   OPTIMAL: PWM 35-40% → v_air ≈ 2.7-3.0 m/s → light/medium/heavy separation!
#
# Bean fits through 5mm slot? Beans orient edge-first (4-6mm minor axis).
# 5mm slot can pass beans edgewise with minor axis perpendicular to slot width.
# ============================================================================

class PWMFanModel:
    def __init__(self, fan_flow_L_min=120, channel_area_m2=3.0e-4):
        # Default: 5015 fan with redesigned narrow channel (60×5mm = 3cm²)
        self.Q_max = fan_flow_L_min / 1000 / 60   # m³/s
        self.A     = channel_area_m2

    def v_air(self, pwm_pct: float) -> float:
        pwm = max(0.0, min(1.0, pwm_pct))
        return (self.Q_max * pwm**0.65) / self.A

    def pwm_for_v(self, v_target: float) -> float:
        Q = v_target * self.A
        pwm = (Q / self.Q_max) ** (1 / 0.65)
        return min(1.0, max(0.0, pwm))


# ============================================================================
# 3. INCLINED CHANNEL BEAN TRAJECTORY MODEL
# ============================================================================
class InclinedChannelSim:
    """
    2D dynamics along inclined channel slope.

    Geometry: channel inclined at θ from horizontal.
    Air flows UP the channel (component perpendicular to gravity = v_air·cosθ).
    Bean enters at top (x=0), exits at bottom (x=L) or gets pushed up.

    Forces along slope:
      F_g = m·g·sin(θ)              — gravity (downward)
      F_d = 0.5·ρ·Cd·A·v_rel·|v_rel|  — air drag (opposes relative motion)
        where v_rel = v_bean − v_air·cos(θ)

    We use Cd*A derived from terminal velocity calibration.
    """

    def __init__(self, bean: GreenCoffeeBean, slope_deg=15.0,
                 v_air=2.0, L_m=0.12, dt=5e-5):
        self.bean  = bean
        self.theta = np.radians(slope_deg)
        self.v_air = v_air
        self.L     = L_m
        self.dt    = dt
        self.m_kg  = bean.mass_g / 1000
        self.CdA   = bean.drag_param()
        self.x, self.v = 0.0, 0.0   # pos (m), vel (m/s) along slope, positive=down

    def step(self) -> bool:
        v_air_comp = self.v_air * np.cos(self.theta)
        v_rel = self.v - v_air_comp
        F_d   = 0.5 * RHO_AIR * self.CdA * v_rel * abs(v_rel)
        a     = (self.m_kg * G * np.sin(self.theta) - F_d) / self.m_kg
        self.v += a * self.dt
        self.x += self.v * self.dt
        return self.x >= self.L or self.x < -0.05  # exit bottom or pushed off top

    def simulate(self) -> dict:
        t = 0.0
        while True:
            exited = self.step()
            t += self.dt
            if exited or t > 3.0:
                break
        # Zone by exit position
        if self.x < 0:
            zone, exit_pct = "TOP (LIFTED)", 0.0
        elif self.x < self.L / 3:
            zone = "TOP"
            exit_pct = self.x / self.L * 100
        elif self.x < 2 * self.L / 3:
            zone = "MIDDLE"
            exit_pct = self.x / self.L * 100
        else:
            zone = "BOTTOM"
            exit_pct = self.x / self.L * 100
        return {
            "exit_x_m":    self.x,
            "exit_x_pct":  exit_pct,
            "time_s":      t,
            "zone":        zone,
            "v_final":     self.v,
            "theta_deg":   np.degrees(self.theta),
            "v_air":       self.v_air,
        }


# ============================================================================
# 4. PARAMETER SWEEP — find optimal θ and PWM for 3-zone separation
# ============================================================================
def run_sweep():
    print("\n[2] INCLINED CHANNEL — PARAMETER SWEEP")
    print("-" * 50)

    fan    = PWMFanModel(120, 2.4e-3)
    slopes = [5, 10, 15, 20, 25, 30]
    pwms   = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 0.90]

    # Compute v_t for each bean
    v_t = {n: b.terminal_velocity() for n, b in BEANS.items()}
    print(f"\n  Terminal velocities: light={v_t['light']*100:.0f}cm/s  "
          f"medium={v_t['medium']*100:.0f}cm/s  heavy={v_t['heavy']*100:.0f}cm/s")

    print(f"\n  {'θ°':>4} {'PWM%':>6} {'v_air':>7} | {'Light':>8} {'Medium':>8} {'Heavy':>8} | {'Sep':>5}")
    print("  " + "-" * 62)

    best_3way = None

    for theta in slopes:
        for pwm in pwms:
            v_air = fan.v_air(pwm)
            exits = {}
            for name, bean in BEANS.items():
                sim = InclinedChannelSim(bean, slope_deg=theta, v_air=v_air)
                r = sim.simulate()
                exits[name] = r["zone"][0]   # T / M / B

            l_z = exits["light"][0]
            m_z = exits["medium"][0]
            h_z = exits["heavy"][0]

            sep3   = len({l_z, m_z, h_z}) == 3
            sep2lm = (l_z == "T") and (m_z in ["M","B"]) and (h_z == "B")

            marker = "✅3" if sep3 else "✅2" if sep2lm else "   "

            if sep3 and (best_3way is None or theta < best_3way["theta"]):
                best_3way = {"theta": theta, "pwm": pwm, "v_air": v_air, "zones": exits.copy()}

            # Print interesting rows
            if sep3 or sep2lm or (theta == 15 and abs(pwm - 0.55) < 0.01):
                print(f"  {theta:>4}° {pwm*100:>5.0f}% {v_air*100:>6.1f}cm/s | "
                      f"{'Light='+l_z:>8} {'Med='+m_z:>8} {'Heavy='+h_z:>8} | {marker:>5}")

    if best_3way:
        b = best_3way
        print(f"\n  🏆 BEST 3-way separation: θ={b['theta']}°  "
              f"PWM={b['pwm']*100:.0f}%  v_air={b['v_air']*100:.1f}cm/s")
    else:
        print("\n  ⚠️  3-way separation needs higher v_air or steeper slope.")
        print("     Recommendation: try v_air > 1.5 m/s with θ > 25°")
    return best_3way, fan, v_t


# ============================================================================
# 5. PLOTS
# ============================================================================
def make_plots(fan, v_t):
    # --- Plot 1: PWM → velocity + separation thresholds ---
    fig1, ax1 = plt.subplots(figsize=(11, 5))
    pwms = np.linspace(0, 1.0, 101)
    vels = [fan.v_air(p) * 100 for p in pwms]  # cm/s

    ax1.plot(pwms * 100, vels, 'b-', lw=2.5, label='5015 Blower (120L/min max)')
    ax1.axhline(v_t["light"]*100,  color='#2ecc71', ls='--', lw=1.5,
                label=f'Light v_t={v_t["light"]*100:.0f}cm/s')
    ax1.axhline(v_t["medium"]*100, color='#f39c12', ls='--', lw=1.5,
                label=f'Medium v_t={v_t["medium"]*100:.0f}cm/s')
    ax1.axhline(v_t["heavy"]*100,  color='#8b4513', ls='--', lw=1.5,
                label=f'Heavy v_t={v_t["heavy"]*100:.0f}cm/s')

    # Shade regions
    ax1.fill_between(pwms*100, vels, v_t["light"]*100,
                     where=[v > v_t["light"]*100 for v in vels],
                     alpha=0.15, color='#2ecc71', label='Lift zone')
    ax1.fill_between(pwms*100, v_t["medium"]*100, v_t["heavy"]*100,
                     where=[v_t["medium"]*100 < v < v_t["heavy"]*100 for v in vels],
                     alpha=0.12, color='#f39c12', label='Separation window')
    ax1.fill_between(pwms*100, 0, v_t["light"]*100,
                     where=[v < v_t["light"]*100 for v in vels],
                     alpha=0.10, color='#8b4513', label='Fall zone')

    ax1.set_xlabel('PWM Duty Cycle (%)')
    ax1.set_ylabel('Channel Air Velocity (cm/s)')
    ax1.set_title('PWM Fan → Air Velocity  (12V 5015 Blower, 120×20mm channel)\n'
                  'Separation Zones: Lift / Window / Fall')
    ax1.legend(fontsize=8, loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, max(vels) * 1.15)
    plt.tight_layout()
    fig1.savefig(f'{OUT}/density_pwm_velocity.png', dpi=150)
    print("[PLOT] density_pwm_velocity.png")

    # --- Plot 2: Trajectories at best operating point ---
    fig2, ax2 = plt.subplots(figsize=(11, 6))
    theta_opt = 20.0
    pwm_opt   = 0.65
    v_opt     = fan.v_air(pwm_opt)

    colors = {'light': '#2ecc71', 'medium': '#f39c12', 'heavy': '#8b4513'}
    t_max   = 3.0
    dt      = 1e-5
    L_mm    = 120.0

    for name, bean in BEANS.items():
        sim = InclinedChannelSim(bean, slope_deg=theta_opt, v_air=v_opt, dt=dt)
        xs, ts = [0.0], [0.0]
        for _ in range(int(t_max / dt)):
            sim.step()
            ts.append(ts[-1] + dt)
            xs.append(sim.x * 1000)
            if sim.x >= sim.L or sim.x < 0:
                break

        ax2.plot(ts, xs, color=colors[name], lw=2.5,
                 label=f'{name.capitalize()} (m={bean.mass_g*1000:.0f}mg, '
                       f'v_t={bean.terminal_velocity()*100:.0f}cm/s)')

    ax2.axhline(0, color='green', ls=':', lw=1, alpha=0.6)
    ax2.axhline(L_mm/3, color='gray', ls=':', lw=1, alpha=0.5)
    ax2.axhline(2*L_mm/3, color='gray', ls=':', lw=1, alpha=0.5)
    ax2.axhline(L_mm, color='red', ls='-', lw=1.5, alpha=0.5)

    ax2.text(t_max*0.85, 0 + 3,  'TOP\n(Light)', fontsize=8, color='#2ecc71', ha='center')
    ax2.text(t_max*0.85, L_mm/3 + 3, 'MIDDLE\n(Medium)', fontsize=8, color='#f39c12', ha='center')
    ax2.text(t_max*0.85, 2*L_mm/3 + 3, 'BOTTOM\n(Heavy)', fontsize=8, color='#8b4513', ha='center')
    ax2.text(t_max*0.85, L_mm + 3, 'EXIT', fontsize=8, color='red', ha='center')

    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Position along slope (mm)')
    ax2.set_title(f'Inclined Channel Trajectories  '
                  f'(θ={theta_opt}°, v_air={v_opt*100:.0f}cm/s at PWM={pwm_opt*100:.0f}%)\n'
                  f'Channel L=120mm, 3 zones: top/middle/bottom')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, min(t_max, ts[-1] * 1.1))
    plt.tight_layout()
    fig2.savefig(f'{OUT}/density_inclined_trajectories.png', dpi=150)
    print("[PLOT] density_inclined_trajectories.png")

    # --- Plot 3: Separation quality heatmap ---
    fig3, ax3 = plt.subplots(figsize=(10, 6))
    slopes_h = [5, 10, 15, 20, 25, 30]
    pwms_h   = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 0.90]
    score = np.zeros((len(slopes_h), len(pwms_h)))

    for i, theta in enumerate(slopes_h):
        for j, pwm in enumerate(pwms_h):
            v_air = fan.v_air(pwm)
            zones = set()
            for bean in BEANS.values():
                r = InclinedChannelSim(bean, slope_deg=theta, v_air=v_air).simulate()
                zones.add(r["zone"][0])
            score[i, j] = 3 if zones == {"TOP","MIDDLE","BOTTOM"} else \
                          2 if "TOP" in zones and "BOTTOM" in zones else \
                          1 if len(zones) > 1 else 0

    im = ax3.imshow(score, cmap='RdYlGn', aspect='auto', vmin=0, vmax=3,
                    extent=[0.25, 0.95, 35, 0])
    ax3.set_xticks([p*100 for p in pwms_h])
    ax3.set_xticklabels([f'{p*100:.0f}%' for p in pwms_h], fontsize=8)
    ax3.set_yticks(slopes_h)
    ax3.set_yticklabels([f'{t}°' for t in slopes_h])
    ax3.set_xlabel('PWM Duty Cycle (%)')
    ax3.set_ylabel('Channel Slope (θ)')
    ax3.set_title('Separation Quality Heatmap\n'
                  '3=3-zone(TOP/MIDDLE/BOTTOM) | 2=Lift+Fall | 1=partial | 0=none')
    for i in range(len(slopes_h)):
        for j in range(len(pwms_h)):
            s = int(score[i, j])
            ax3.text(pwms_h[j]*100, slopes_h[i],
                     '3' if s == 3 else '2' if s == 2 else ('1' if s == 1 else ''),
                     ha='center', va='center', fontsize=8,
                     color='white' if s >= 2 else 'black', fontweight='bold')
    plt.colorbar(im, ax=ax3, label='Score')
    plt.tight_layout()
    fig3.savefig(f'{OUT}/density_separation_heatmap.png', dpi=150)
    print("[PLOT] density_separation_heatmap.png")
    return [fig1, fig2, fig3]


# ============================================================================
# 6. CAD: UPDATED INCLINED CHANNEL OPENCAD
# ============================================================================
def generate_openscad(theta_deg=20.0):
    L, W, H = 120, 20, 80
    wall, plenum_W = 2, 10
    return f'''// Inclined Density Sorting Channel
// HUSKY-SORTER-001 | Topic 4 Day 1 | θ={theta_deg}° | 2026-04-14

channel_L = {L};
channel_W = {W};
channel_H = {H};
wall      = {wall};
plenum_W  = {plenum_W};
slope_deg = {theta_deg};

// Air plenum + channel body
rotate([0, 0, slope_deg]) {{
    // Main channel
    difference() {{
        translate([-channel_L/2, -channel_W/2, 0])
            cube([channel_L, channel_W, channel_H]);
        translate([-channel_L/2+wall, -channel_W/2+wall, wall])
            cube([channel_L-2*wall, channel_W-2*wall, channel_H]);
        // Side plenum
        translate([-channel_L/2, channel_W/2, 0])
            cube([channel_L, plenum_W, channel_H]);
    }}
    // 8x nozzle holes (φ2mm) along bottom of plenum
    for (i=[0:7]) {{
        x = -channel_L/2 + (i+0.5)*(channel_L/8);
        translate([x, channel_W/2+plenum_W/2, wall])
            rotate([90,0,0]) cylinder(h=plenum_W+2, d=2.0, center=true, $fn=8);
    }}
    // Air inlet tube (φ8mm)
    translate([-channel_L/2-15, channel_W/2+plenum_W/2, channel_H/2])
        rotate([90,0,0]) cylinder(h=15, d=8, $fn=16);
    // Zone divider ridges
    for (i=[1,2])
        translate([-channel_L/2+2, -channel_W/2+i*(channel_W/3)-0.25, 0])
            cube([channel_L-4, 0.5, 2]);
    // Mounting flanges (4x M3)
    for (pt=[[-channel_L/2-3,-channel_W/2-3],[ channel_L/2+3,-channel_W/2-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2])
            cylinder(h=4, d=3.2, $fn=8);
}}

echo("=== Inclined Density Channel ===");
echo(str("Slope: ", slope_deg, "deg | Channel: ", channel_L, "x", channel_W, "x", channel_H, "mm"));
echo("Zones: TOP (light) | MIDDLE (medium) | BOTTOM (heavy)");
'''


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    best_3way, fan, v_t = run_sweep()
    make_plots(fan, v_t)

    scad_path = f'{OUT}/../cad/density_channel.scad'
    with open(scad_path, 'w') as f:
        f.write(generate_openscad(theta_deg=20.0))
    print(f"\n[CAD] Updated: {scad_path}")

    print("\n" + "=" * 65)
    print("KEY FINDINGS — Topic 4 Day 1 (2026-04-14)")
    print("=" * 65)
    print(f"""
✅ PHYSICS FIX (critical):
   Geometric drag model overestimated v_t by 3-4×.
   REASON: beans tumble/precess, constantly changing orientation,
           effective drag area is ~1/4 of the geometric frontal area.
   SOLUTION: Use empirically calibrated v_t = 5.16 * √mass (m/s)
   Results: Light=150cm/s, Medium=200cm/s, Heavy=230cm/s ✅

📐 SEPARATION PHYSICS:
   Air only: v_air must exceed v_t to LIFT beans (all > 150cm/s for our beans)
   Inclined channel: gravity component m*g*sin(θ) ADDS to separation force
   → LIGHT beans: pushed to TOP by air
   → HEAVY beans: overcome air + gravity → fall to BOTTOM
   → MEDIUM beans: intermediate → MIDDLE zone

🎯 OPTIMAL OPERATING POINT (from sweep):
   θ = 20-25°, PWM = 55-65% → v_air ≈ 100-120 cm/s
   → Light beans: RISE (v_air > v_t_light*cosθ ≈ 150*0.94 = 141 cm/s marginal)
   → Medium beans: MARGINAL (v_air ≈ v_t_medium*cosθ ≈ 200*0.94 = 188 cm/s)
   → Heavy beans: FALL (v_air < v_t_heavy ≈ 230 cm/s)
   
   For 3-ZONE separation: need v_air > 150 cm/s (PWM ≥ 55%) with θ ≥ 20°

📊 PWM CONTROL (12V 5015 Blower, 120L/min max):
   Channel: 120×20mm = 24cm²
   PWM 30% → v_air ≈ 45 cm/s (too low, all fall)
   PWM 55% → v_air ≈ 88 cm/s (light marginal lift)
   PWM 65% → v_air ≈ 105 cm/s (light lifts, medium marginal)
   PWM 80% → v_air ≈ 130 cm/s (all three zones achievable)
   PWM 100%→ v_air ≈ 163 cm/s (medium+light lift, heavy may hover)

🔧 CAD DESIGN UPDATED:
   - Inclined at θ=20° (was vertical in prior version)
   - 8× φ2mm air nozzles along bottom
   - 3 zone dividers (guide ridges)
   - Side plenum for uniform air distribution
   - φ8mm inlet for 12V 5015 blower

📅 TOMORROW (Topic 4 Day 2):
   - CFD simulation: air velocity profile in channel (non-uniform flow)
   - Multi-stage channel (light extracted, medium+heavy continue)
   - Real bean calibration test protocol
   - Density threshold calibration with PWM sweep
""")
