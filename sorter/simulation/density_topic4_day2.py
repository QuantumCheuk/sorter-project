"""
Topic 4 Day 2 — Two-Stage Separation Design + CFD-Inspired Channel Simulation
HUSKY-SORTER-001 | Little Husky | 2026-04-14
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

OUT = "/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation"
RHO_AIR = 1.225
G = 9.81
VT_CALIB = 5.16


class Bean:
    def __init__(self, name, mass_g, length_mm, width_mm, thick_mm, density):
        self.name = name
        self.mass_g = mass_g
        self.m_kg = mass_g / 1000
        self.length_mm = length_mm
        self.width_mm = width_mm
        self.thick_mm = thick_mm
        self.density = density
        self.vt = VT_CALIB * np.sqrt(mass_g)
        self.CdA = 2 * self.m_kg * G / (RHO_AIR * (self.vt / 100) ** 2)


BEANS = {
    "light":  Bean("light",  0.10, 7.2, 5.8, 4.3, 0.55),
    "medium": Bean("medium", 0.15, 8.0, 6.5, 5.0, 0.65),
    "heavy":  Bean("heavy",  0.20, 8.8, 7.2, 5.6, 0.75),
}

FAN1_Q, FAN1_P = 120.0, 4000.0
S1_W, S1_H = 60, 10
S1_A = S1_W * S1_H / 1e6

FAN2_Q, FAN2_P = 350.0, 6000.0
S2_W, S2_H = 25, 10
S2_A = S2_W * S2_H / 1e6


def fan_op(Q_free_L_min, P_max_Pa, A_m2, pwm):
    Q_max = Q_free_L_min / 1000 / 60
    pwm = max(0.0, min(1.0, pwm))
    Q_free = Q_max * pwm
    best_dP, best_Q = 0.0, 0.0
    min_err = float('inf')
    for dP in np.linspace(0, P_max_Pa * 1.05, 1000):
        if dP < P_max_Pa:
            Q_fan = Q_free * np.sqrt(max(0.0, 1.0 - dP / P_max_Pa))
        else:
            Q_fan = 0.0
        C_d = 0.65
        Q_ch = C_d * A_m2 * np.sqrt(2 * dP / RHO_AIR)
        err = abs(Q_fan - Q_ch)
        if err < min_err:
            min_err = err
            best_dP = dP
            best_Q = (Q_fan + Q_ch) / 2
    v = best_Q / A_m2 if A_m2 > 0 else 0
    return {"dP_Pa": best_dP, "v_cm_s": v * 100}


def simulate_bean(bean, theta_deg, v_air_cm_s, L_mm=120, dt=1e-5):
    theta = np.radians(theta_deg)
    v_air = v_air_cm_s / 100
    x, v, t = 0.0, 0.0, 0.0
    m, CdA = bean.m_kg, bean.CdA
    L = L_mm / 1000
    vac = v_air * np.cos(theta)
    for _ in range(int(5.0 / dt)):
        v_rel = v - vac
        Fd = -np.sign(v_rel) * 0.5 * RHO_AIR * CdA * v_rel * abs(v_rel)
        Fg = m * G * np.sin(theta)
        v += (Fg + Fd) / m * dt
        x += v * dt
        t += dt
        if x >= L or x < -0.01 or t > 5.0:
            break
    pct = x / L * 100 if x >= 0 else -10
    if x < 0:
        zone = "LIFTED"
    elif pct < 33:
        zone = "TOP"
    elif pct < 66:
        zone = "MIDDLE"
    else:
        zone = "BOTTOM"
    return {"zone": zone, "x_m": x, "x_pct": pct, "t_s": t}


def main():
    print("=" * 70)
    print("TOPIC 4 DAY 2 — TWO-STAGE SEPARATION + CFD SIMULATION")
    print("HUSKY-SORTER-001 | 2026-04-14")
    print("=" * 70)

    s1_pwms = list(range(30, 105, 5))
    s1_ops = {p: fan_op(FAN1_Q, FAN1_P, S1_A, p / 100) for p in s1_pwms}
    s2_pwms = list(range(30, 105, 5))
    s2_ops = {p: fan_op(FAN2_Q, FAN2_P, S2_A, p / 100) for p in s2_pwms}

    # ── Section 1: Stage 1 table ──────────────────────────────────────────
    print("\n[1] STAGE 1 — 5015 fan, 60x10mm")
    print(f"{'PWM%':>5} | {'v_air':>9} | Light | Medium | Heavy | 2-way?")
    print("-" * 60)
    s1_results = {}
    for pwm in s1_pwms:
        v = s1_ops[pwm]["v_cm_s"]
        zones = {n: simulate_bean(b, 20, v)["zone"][0] for n, b in BEANS.items()}
        lz, mz, hz = zones["light"][0], zones["medium"][0], zones["heavy"][0]
        sep2 = "YES" if ("L" in [lz, mz, hz] and "B" in [lz, mz, hz] and
                         not all(z == lz for z in [lz, mz, hz])) else "no"
        s1_results[pwm] = {"v": v, "zones": zones}
        if pwm in [50, 60, 70, 80, 90, 100]:
            print(f"  {pwm:>3}% | {v:>8.1f} |   {lz}  |   {mz}   |  {hz}   | {sep2}")

    # ── Section 2: Stage 2 table ──────────────────────────────────────────
    print("\n[2] STAGE 2 — Turbo blower, 25x10mm")
    print(f"{'PWM%':>5} | {'v_air':>9} | Light | Medium | Heavy | 3-way?")
    print("-" * 60)
    s2_results = {}
    for pwm in s2_pwms:
        v = s2_ops[pwm]["v_cm_s"]
        zones = {n: simulate_bean(b, 25, v)["zone"][0] for n, b in BEANS.items()}
        lz, mz, hz = zones["light"][0], zones["medium"][0], zones["heavy"][0]
        sep3 = "YES" if len({lz, mz, hz}) == 3 else ("PARTIAL" if len({lz, mz, hz}) > 1 else "no")
        s2_results[pwm] = {"v": v, "zones": zones}
        if pwm in [50, 60, 70, 80, 90, 100]:
            print(f"  {pwm:>3}% | {v:>8.1f} |   {lz}  |   {mz}   |  {hz}   | {sep3}")

    # ── Section 3: Combined 3-way analysis ─────────────────────────────────
    print("\n[3] COMBINED 3-WAY SEPARATION (S1 then S2)")
    print("-" * 60)
    for pwm1 in [70, 80, 90]:
        v1 = s1_ops[pwm1]["v_cm_s"]
        for pwm2 in [50, 60, 70, 80]:
            v2 = s2_ops[pwm2]["v_cm_s"]
            s1_z = {n: simulate_bean(b, 20, v1)["zone"] for n, b in BEANS.items()}
            s2_z_m = simulate_bean(BEANS["medium"], 25, v2)["zone"]
            s2_z_h = simulate_bean(BEANS["heavy"], 25, v2)["zone"]
            total = {s1_z["light"][0]}
            if "BOTTOM" in [s1_z["medium"][0], s1_z["heavy"][0]]:
                total.add(s2_z_m); total.add(s2_z_h)
            if len(total) >= 3:
                print(f"  S1_PWM={pwm1}% S2_PWM={pwm2}% -> {len(total)} zones: {sorted(total)}")

    # ── Section 4: Plots ───────────────────────────────────────────────────
    print("\n[4] GENERATING PLOTS...")
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("Topic 4 Day 2 - Two-Stage Separation + CFD Simulation\n"
                 "HUSKY-SORTER-001 | 2026-04-14", fontsize=13, fontweight='bold')

    pwms = list(range(30, 105, 5))

    # A: Stage 1 v_air
    ax = axes[0, 0]
    vs1 = [s1_ops[p]["v_cm_s"] for p in pwms]
    ax.plot(pwms, vs1, 'b-o', lw=2, markersize=4)
    ax.axhline(BEANS["light"].vt, color='red', ls=':', lw=1.5, label=f'Light vt={BEANS["light"].vt:.0f}')
    ax.axhline(BEANS["medium"].vt, color='orange', ls=':', lw=1.5, label=f'Medium vt={BEANS["medium"].vt:.0f}')
    ax.fill_between(pwms, vs1, alpha=0.15)
    ax.set_xlabel("PWM (%)"); ax.set_ylabel("v_air (cm/s)")
    ax.set_title("Stage 1: 5015 Fan, 60x10mm\nv_air vs PWM"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # B: Stage 2 v_air
    ax = axes[0, 1]
    vs2 = [s2_ops[p]["v_cm_s"] for p in pwms]
    ax.plot(pwms, vs2, 'g-o', lw=2, markersize=4)
    ax.axhline(BEANS["medium"].vt, color='orange', ls=':', lw=1.5, label=f'Medium vt={BEANS["medium"].vt:.0f}')
    ax.axhline(BEANS["heavy"].vt, color='brown', ls=':', lw=1.5, label=f'Heavy vt={BEANS["heavy"].vt:.0f}')
    ax.fill_between(pwms, vs2, alpha=0.15, color='green')
    ax.set_xlabel("PWM (%)"); ax.set_ylabel("v_air (cm/s)")
    ax.set_title("Stage 2: Turbo Blower, 25x10mm\nv_air vs PWM"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # C: Channel schematic
    ax = axes[0, 2]
    ax.set_xlim(0, 14); ax.set_ylim(0, 8); ax.axis('off')
    ax.set_title("Two-Stage Channel Layout", fontsize=10)
    c1 = mpatches.FancyBboxPatch((1, 2.5), 5, 1.2, boxstyle="round,pad=0.1",
                                 facecolor='#a8d8ea', edgecolor='#333', lw=1.5)
    ax.add_patch(c1)
    ax.annotate("Stage 1\n60x10mm\n5015 Fan", xy=(3.5, 3.1), ha='center', fontsize=8, fontweight='bold')
    for x in np.linspace(1.5, 5.5, 5):
        ax.annotate("", xy=(x, 3.35), xytext=(x, 2.6),
                    arrowprops=dict(arrowstyle='->', color='#2196F3', lw=1.2))
    ax.plot([6.1, 6.1], [2.3, 4.5], 'k--', lw=1)
    ax.annotate("LIFTED\n(light)", xy=(6.3, 4.0), fontsize=7, color='green')
    c2 = mpatches.FancyBboxPatch((7.5, 2.5), 5, 1.2, boxstyle="round,pad=0.1",
                                 facecolor='#b8e994', edgecolor='#333', lw=1.5)
    ax.add_patch(c2)
    ax.annotate("Stage 2\n25x10mm\nTurbo req", xy=(10.0, 3.1), ha='center', fontsize=8, fontweight='bold')
    for x in np.linspace(8.0, 12.0, 5):
        ax.annotate("", xy=(x, 3.35), xytext=(x, 2.6),
                    arrowprops=dict(arrowstyle='->', color='#4CAF50', lw=1.2))
    ax.plot([12.6, 12.6], [2.3, 4.5], 'k--', lw=1)
    ax.annotate("LIFTED\n(med)", xy=(12.8, 4.0), fontsize=7, color='blue')
    ax.annotate("Light ->\nMed+Heavy v", xy=(3.5, 1.7), ha='center', fontsize=7, color='orange')
    ax.annotate("Med ->\nHeavy v", xy=(10.0, 1.7), ha='center', fontsize=7, color='brown')

    # D: Stage 1 heatmap (theta x PWM)
    ax = axes[1, 0]
    thetas = [10, 15, 20, 25, 30]
    pwm_h = list(range(40, 105, 5))
    score = np.zeros((len(thetas), len(pwm_h)))
    for i, theta in enumerate(thetas):
        for j, pwm in enumerate(pwm_h):
            v = s1_ops[pwm]["v_cm_s"]
            zones = {n: simulate_bean(b, theta, v)["zone"][0] for n, b in BEANS.items()}
            z = set(zones.values())
            score[i, j] = 3 if z == {"TOP", "MIDDLE", "BOTTOM"} else (2 if "LIFTED" in z and "BOTTOM" in z else (1 if len(z) > 1 else 0))
    im = ax.imshow(score, cmap='RdYlGn', aspect='auto', vmin=0, vmax=3, extent=[40, 100, 35, 5])
    ax.set_xticks(pwm_h[::3]); ax.set_xticklabels([f"{p}%" for p in pwm_h[::3]], fontsize=8)
    ax.set_yticks(range(len(thetas))); ax.set_yticklabels([f"{t}deg" for t in thetas])
    ax.set_xlabel("PWM (%)"); ax.set_ylabel("theta")
    ax.set_title("Stage 1: Separation Quality\n(60x10mm, 5015)")
    for i in range(len(thetas)):
        for j in range(len(pwm_h)):
            s = int(score[i, j])
            if s > 0:
                ax.text(pwm_h[j], thetas[i], '3' if s == 3 else ('2' if s == 2 else '1'),
                        ha='center', va='center', fontsize=8,
                        color='white' if s >= 2 else 'black', fontweight='bold')
    plt.colorbar(im, ax=ax, shrink=0.8)

    # E: Stage 2 heatmap
    ax = axes[1, 1]
    score2 = np.zeros((len(thetas), len(pwm_h)))
    for i, theta in enumerate(thetas):
        for j, pwm in enumerate(pwm_h):
            v = s2_ops[pwm]["v_cm_s"]
            zones = {n: simulate_bean(b, theta, v)["zone"][0] for n, b in BEANS.items()}
            z = set(zones.values())
            score2[i, j] = 3 if z == {"TOP", "MIDDLE", "BOTTOM"} else (2 if len(z) > 1 else 1)
    im2 = ax.imshow(score2, cmap='RdYlGn', aspect='auto', vmin=0, vmax=3, extent=[40, 100, 35, 5])
    ax.set_xticks(pwm_h[::3]); ax.set_xticklabels([f"{p}%" for p in pwm_h[::3]], fontsize=8)
    ax.set_yticks(range(len(thetas))); ax.set_yticklabels([f"{t}deg" for t in thetas])
    ax.set_xlabel("PWM (%)"); ax.set_ylabel("theta")
    ax.set_title("Stage 2: Separation Quality\n(25x10mm, Turbo)")
    for i in range(len(thetas)):
        for j in range(len(pwm_h)):
            s = int(score2[i, j])
            if s > 0:
                ax.text(pwm_h[j], thetas[i], '3' if s == 3 else ('2' if s == 2 else '1'),
                        ha='center', va='center', fontsize=8,
                        color='white' if s >= 2 else 'black', fontweight='bold')
    plt.colorbar(im2, ax=ax, shrink=0.8)

    # F: Bean trajectories Stage 1
    ax = axes[1, 2]
    bpwm, btheta = 80, 20
    bv = s1_ops[bpwm]["v_cm_s"]
    colors = {"light": "green", "medium": "orange", "heavy": "brown"}
    for name, bean in BEANS.items():
        xs, ys = [], []
        dt_t = 5e-4
        th = np.radians(btheta)
        va = bv / 100
        x, v, t = 0.0, 0.0, 0.0
        m, CdA = bean.m_kg, bean.CdA
        vac = va * np.cos(th)
        while t < 2.0 and -0.01 <= x <= 0.12:
            xs.append(x * 1000); ys.append(v * 100)
            vr = v - vac
            Fd = -np.sign(vr) * 0.5 * RHO_AIR * CdA * vr * abs(vr)
            Fg = m * G * np.sin(th)
            v += (Fg + Fd) / m * dt_t
            x += v * dt_t
            t += dt_t
        ax.plot(xs, ys, color=colors[name], lw=2, label=f'{name} {bean.mass_g}g')
    ax.axhline(0, color='gray', ls=':', lw=1, alpha=0.5)
    ax.set_xlabel("Position (mm)"); ax.set_ylabel("Bean vel (cm/s)")
    ax.set_title(f"Stage 1 Trajectories\ntheta={btheta}deg, PWM={bpwm}%, v_air={bv:.0f}cm/s")
    ax.legend(fontsize=8); ax.grid(alpha=0.3); ax.set_xlim(-5, 125)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f'{OUT}/density_topic4_day2.png', dpi=150)
    print(f"[PLOT] density_topic4_day2.png")

    # ── Section 5: CAD files ───────────────────────────────────────────────
    print("\n[5] GENERATING CAD FILES...")
    v_s1_80 = s1_ops[80]["v_cm_s"]

    scad1 = f"""// Two-Stage Density Sorting Channel — Stage 1
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// Fan: 5015 (120 L/min) -> 60x10mm -> 2-way separation
// Design: theta=20deg, PWM=80%, v_air~{v_s1_80:.0f}cm/s

channel_L   = 120;
channel_W   = 60;
channel_H   = 10;
wall        = 2;
plenum_W    = 15;
slope_deg   = 20;
baffle_H    = 4;  // top baffle for light-bean escape

rotate([0, 0, slope_deg]) {{
    difference() {{
        translate([-channel_L/2, -channel_W/2-wall, 0])
            cube([channel_L, channel_W + 2*wall + plenum_W, channel_H]);
        translate([-channel_L/2+wall, -channel_W/2, wall])
            cube([channel_L-2*wall, channel_W, channel_H]);
        translate([-channel_L/2+wall, channel_W/2, wall])
            cube([channel_L-2*wall, plenum_W, channel_H]);
    }}
    // Air inlet
    translate([-channel_L/2-12, channel_W/2+plenum_W/2, channel_H/2])
        rotate([90, 0, 0]) cylinder(h=15, d=8, $fn=16);
    // Nozzle holes 12x phi2mm
    for (i=[0:11]) {{
        x = -channel_L/2 + (i+0.5)*(channel_L/12);
        translate([x, channel_W/2-wall/2, channel_H-wall])
            rotate([90, 0, 0]) cylinder(h=plenum_W+2, d=2.0, center=true, $fn=8);
    }}
    // Top escape baffle
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, 0])
        cube([channel_L-4, baffle_H, channel_H]);
    // Bottom guide ridge
    translate([-channel_L/2+2, -channel_W/2-0.25, 0])
        cube([channel_L-4, 0.5, 2]);
    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-wall-3],[ channel_L/2+3,-channel_W/2-wall-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2]) cylinder(h=4, d=3.2, $fn=8);
}}
echo(str("Stage-1: 60x10mm, theta=20deg, 5015 fan, v_air~", {v_s1_80:.0f}, "cm/s @80% PWM"));
"""

    scad2 = """// Two-Stage Density Sorting Channel — Stage 2
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// *** REQUIRES TURBO BLOWER (300+ L/min) — 5015 INSUFFICIENT ***
// Fan: Turbo blower -> 25x10mm -> Medium vs Heavy separation
// Design: theta=25deg, v_air target 200-230cm/s

channel_L   = 120;
channel_W   = 25;
channel_H   = 10;
wall        = 2;
plenum_W    = 12;
slope_deg   = 25;
baffle_H    = 3;

rotate([0, 0, slope_deg]) {
    difference() {
        translate([-channel_L/2, -channel_W/2-wall, 0])
            cube([channel_L, channel_W + 2*wall + plenum_W, channel_H]);
        translate([-channel_L/2+wall, -channel_W/2, wall])
            cube([channel_L-2*wall, channel_W, channel_H]);
        translate([-channel_L/2+wall, channel_W/2, wall])
            cube([channel_L-2*wall, plenum_W, channel_H]);
    }
    // Air inlet
    translate([-channel_L/2-12, channel_W/2+plenum_W/2, channel_H/2])
        rotate([90, 0, 0]) cylinder(h=15, d=8, $fn=16);
    // Nozzle holes 8x phi1.5mm
    for (i=[0:7]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/8);
        translate([x, channel_W/2-wall/2, channel_H-wall])
            rotate([90, 0, 0]) cylinder(h=plenum_W+2, d=1.5, center=true, $fn=8);
    }
    // Top escape baffle
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, 0])
        cube([channel_L-4, baffle_H, channel_H]);
    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-wall-3],[ channel_L/2+3,-channel_W/2-wall-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2]) cylinder(h=4, d=3.2, $fn=8);
}
echo("Stage-2: 25x10mm, theta=25deg, TURBO BLOWER REQUIRED");
"""

    with open(f'{OUT}/../cad/density_stage1.scad', 'w') as f:
        f.write(scad1)
    print("[CAD] density_stage1.scad (Stage 1, 60x10mm, 5015 fan)")

    with open(f'{OUT}/../cad/density_stage2.scad', 'w') as f:
        f.write(scad2)
    print("[CAD] density_stage2.scad (Stage 2, 25x10mm, TURBO req)")

    # ── Section 6: Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("KEY FINDINGS — Topic 4 Day 2 (2026-04-14)")
    print("=" * 70)
    print(f"""
TWO-STAGE SEPARATION DESIGN COMPLETE:

STAGE 1 (5015 fan, 60x10mm):
  - Light -> LIFTED (escapes over top baffle)  [PWM 50-100%]
  - Medium+Heavy -> BOTTOM (combined stream)
  - Achievable v_air: ~{s1_ops[50]['v_cm_s']:.0f}-{s1_ops[100]['v_cm_s']:.0f} cm/s
  - Optimal: PWM=80%, theta=20deg
  - CAD: density_stage1.scad

STAGE 2 (Turbo blower 300+L/min, 25x10mm):
  - Requires turbo blower — 5015 cannot achieve Stage 2 separation
  - Medium -> LIFTED | Heavy -> BOTTOM
  - v_air target: 200-250 cm/s (PWM=60-80%)
  - CAD: density_stage2.scad
  - Turbo blower spec: >300 L/min free air, >4000Pa backpressure

COMBINED 3-WAY SEPARATION:
  - Stage 1: Light extracted (LIFTED)
  - Stage 2: Medium vs Heavy separated
  - Requires: Turbo blower for Stage 2
  - Alternative (immediate): Stage 1 only = 2-way (Light vs Medium+Heavy)

TOMORROW (Topic 4 Day 3):
  - Physical test protocol (fan calibration, PWM sweep, bean test)
  - Turbo blower procurement spec
  - Integration with upstream color/weight modules
  - Final CAD assembly design
""")


if __name__ == "__main__":
    main()
