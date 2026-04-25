"""
课题6 Day2：PID控制算法设计 + 流量标定实验方案 + 旋转分配器步进时序优化
Topic 6 Day 2: PID Control + Flow Calibration + Rotary Distributor Timing

生成图表：buffer_topic6_day2.png
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib
matplotlib.use('Agg')

# ============================================================
# 1. PID 控制算法设计
# ============================================================

class PIDController:
    """
    离散PID控制器（位置式，适合步进电机速度控制）
    
    u(k) = KP * e(k) + KI * sum(e) + KD * [e(k) - e(k-1)]
    """
    def __init__(self, kp=1.0, ki=0.0, kd=0.0, output_limits=(0, 120)):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits
        self.integral = 0.0
        self.prev_error = 0.0
        self.output = 0.0
        
    def compute(self, setpoint, measured, dt=0.1):
        error = setpoint - measured
        
        # Proportional
        P = self.kp * error
        
        # Integral
        self.integral += error * dt
        I = self.ki * self.integral
        
        # Derivative
        if dt > 0:
            D = self.kd * (error - self.prev_error) / dt
        else:
            D = 0
        self.prev_error = error
        
        # Total output
        raw = P + I + D
        
        # Clamp
        self.output = np.clip(raw, self.output_limits[0], self.output_limits[1])
        return self.output
    
    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.output = 0.0


def simulate_pid_250g_batch():
    """
    仿真：250g批次PID控制出豆
    - 目标：70秒出完250g
    - 目标速率：3.571 g/s
    - 实际速率由PID控制螺旋给料器步进电机转速
    """
    # 物理参数
    target_grams = 250.0
    target_duration_s = 70.0
    target_rate_gps = target_grams / target_duration_s  # 3.571 g/s
    
    # 螺旋给料器参数（φ20mm, 15mm螺距）
    mass_per_rev_g = 1.791  # g/rev
    rpm_to_gps = mass_per_rev_g * (120 / 60)  # @120RPM = 3.582 g/s
    max_rpm = 120
    
    print(f"=== PID控制250g批次出豆仿真 ===")
    print(f"目标：{target_grams}g @ {target_duration_s}s = {target_rate_gps:.3f} g/s")
    print(f"满速120RPM时理论出豆速率：{mass_per_rev_g * 120/60:.3f} g/s")
    print(f"满速75RPM达到目标速率：{target_rate_gps * 60 / mass_per_rev_g:.1f} RPM")
    
    # 初始条件
    current_rpm = 50.0  # 起始转速
    dispensed_g = 0.0
    t_arr = [0.0]
    rate_arr = [0.0]
    rpm_arr = [current_rpm]
    mass_arr = [0.0]
    error_arr = [0.0]
    
    pid = PIDController(kp=15.0, ki=0.3, kd=5.0, output_limits=(0, max_rpm))
    pid.integral = 50.0  # 初始积分项（对应75RPM）
    
    dt = 0.5  # 0.5秒步长
    
    for step in range(int(target_duration_s / dt) + 50):
        t = step * dt
        
        if dispensed_g >= target_grams:
            break
        
        # PID计算（测量值=当前已出豆量对应的平均速率）
        if t > 0:
            measured_rate = dispensed_g / t
        else:
            measured_rate = 0
        
        current_rpm = pid.compute(target_rate_gps, measured_rate, dt)
        
        # 出豆（当前转速产生的实时速率）
        # 实际出豆速率 = RPM * mass_per_rev / 60
        actual_rate_gps = current_rpm * mass_per_rev_g / 60
        dispensed_g += actual_rate_gps * dt
        
        rate_arr.append(actual_rate_gps)
        rpm_arr.append(current_rpm)
        mass_arr.append(dispensed_g)
        t_arr.append(t)
        error_arr.append(target_rate_gps - actual_rate_gps)
    
    # 计算最终精度
    final_time = t_arr[-1]
    final_mass = mass_arr[-1]
    avg_rate = final_mass / final_time if final_time > 0 else 0
    
    print(f"\n结果：{final_mass:.1f}g @ {final_time:.1f}s (目标{target_grams}g @ {target_duration_s}s)")
    print(f"平均速率：{avg_rate:.3f} g/s (目标{target_rate_gps:.3f} g/s)")
    print(f"速率误差：{(avg_rate/target_rate_gps - 1)*100:.1f}%")
    
    return {
        't': t_arr, 'rate': rate_arr, 'rpm': rpm_arr, 
        'mass': mass_arr, 'error': error_arr,
        'target_rate': target_rate_gps,
        'final_mass': final_mass, 'final_time': final_time
    }


def simulate_tuning_pid():
    """
    不同PID参数下的响应曲线（整定过程）
    """
    kp_values = [5.0, 15.0, 30.0]
    ki_values = [0.0, 0.3, 0.5]
    
    results = []
    
    for kp in kp_values:
        for ki in ki_values:
            if kp == 30 and ki == 0.5:
                continue  # 跳过过于激进的组合
            
            pid = PIDController(kp=kp, ki=ki, kd=5.0, output_limits=(0, 120))
            pid.integral = 50.0
            
            target_rate = 3.571
            mass_per_rev_g = 1.791
            dispensed = 0.0
            t = 0.0
            dt = 0.5
            m_arr, r_arr, t_arr = [], [], []
            
            for step in range(200):
                measured_rate = dispensed / t if t > 0 else 0
                rpm = pid.compute(target_rate, measured_rate, dt)
                rate = rpm * mass_per_rev_g / 60
                dispensed += rate * dt
                t += dt
                m_arr.append(dispensed)
                r_arr.append(rate)
                t_arr.append(t)
                if dispensed >= 250:
                    break
            
            results.append({
                'kp': kp, 'ki': ki, 
                'mass': m_arr, 'rate': r_arr, 'time': t_arr,
                'final_mass': m_arr[-1], 'final_time': t_arr[-1]
            })
    
    return results


# ============================================================
# 2. 旋转分配器步进时序优化
# ============================================================

def analyze_rotary_distributor_timing():
    """
    旋转分配器步进时序分析
    - 28BYJ-48 + DRV8833
    - 8位分度，每格45°
    - 要求切换<200ms
    """
    # 电机规格
    steps_per_rev_28byj = 64  # 基础步数（半步模式）
    microstep = 8  # DRV8833 microstep
    total_steps_per_rev = steps_per_rev_28byj * microstep  # 512 steps/rev
    
    # 分度分析
    steps_per_step = total_steps_per_rev / 8  # 64 steps/step (45°)
    
    # 速度分析
    max_rpm_motor = 20  # 28BYJ-48 空载约22rpm，降额20%
    max_steps_per_sec = total_steps_per_rev * max_rpm_motor / 60  # steps/s
    
    # 45°旋转时间
    time_for_45deg = steps_per_step / max_steps_per_sec  # seconds
    
    # 加速曲线分析（S型）
    accel_steps = 16  # 加速用前16步
    decel_steps = 16  # 减速用后16步
    cruise_steps = steps_per_step - accel_steps - decel_steps
    
    print(f"=== 旋转分配器步进时序分析 ===")
    print(f"电机：28BYJ-48 + DRV8833 (microstep={microstep})")
    print(f"总步数/转：{total_steps_per_rev} steps/rev")
    print(f"每格步数（45°）：{steps_per_step} steps")
    print(f"电机最大转速：{max_rpm_motor} RPM")
    print(f"最大步进速率：{max_steps_per_sec:.0f} steps/s")
    print(f"理论45°切换时间：{time_for_45deg*1000:.0f} ms")
    print(f"  - 加速阶段：{accel_steps} steps @ accel")
    print(f"  - 匀速阶段：{cruise_steps} steps @ {max_steps_per_sec:.0f} steps/s")
    print(f"  - 减速阶段：{decel_steps} steps @ decel")
    
    # 时间表（带加速曲线）
    t_arr = []
    v_arr = []
    pos_arr = []
    
    t = 0
    pos = 0
    step = 0
    
    # 加速阶段
    for i in range(accel_steps):
        dt = 0.010 + 0.002 * (1 - i/accel_steps)  # 逐渐加速
        v = 50 + i * 6  # 50 -> 146 steps/s
        t += dt
        pos += 1
        t_arr.append(t)
        v_arr.append(v)
        pos_arr.append(pos)
        step += 1
    
    # 匀速阶段
    for i in range(int(cruise_steps)):
        dt = 1.0 / max_steps_per_sec  # 全速
        t += dt
        pos += 1
        t_arr.append(t)
        v_arr.append(max_steps_per_sec)
        pos_arr.append(pos)
        step += 1
    
    # 减速阶段
    for i in range(decel_steps):
        dt = 0.010 + 0.002 * (i / decel_steps)  # 逐渐减速
        v = max_steps_per_sec - (decel_steps - i) * 5
        t += dt
        pos += 1
        t_arr.append(t)
        v_arr.append(max(0, v))
        pos_arr.append(pos)
        step += 1
    
    total_switch_time_ms = t_arr[-1] * 1000
    print(f"\n带S型加速曲线的切换时间：{total_switch_time_ms:.0f} ms")
    print(f"通过标准（<200ms）：{'✅' if total_switch_time_ms < 200 else '❌'}")
    
    return {
        'steps_per_step': steps_per_step,
        'max_steps_per_sec': max_steps_per_sec,
        'total_switch_ms': total_switch_time_ms,
        't_arr': t_arr, 'v_arr': v_arr, 'pos_arr': pos_arr
    }


# ============================================================
# 3. 流量标定实验方案
# ============================================================

def design_flow_calibration():
    """
    流量标定实验方案设计
    - 静态标定：已知质量的豆子，多次测量
    - 动态标定：实时出豆，HX711连续称重
    - 密度修正：不同豆种密度不同
    """
    print("\n=== 流量标定实验方案 ===")
    
    # 标定矩阵
    cal_matrix = []
    
    for variety in ['Heirloom', 'Geisha', 'Bourbon', 'Typica']:
        for rpm in [30, 60, 90, 120]:
            mass_per_rev = 1.791  # 基础值（Heirloom密度=0.40 g/mL）
            density = {'Heirloom': 0.40, 'Geisha': 0.38, 'Bourbon': 0.42, 'Typica': 0.41}
            density_factor = density[variety] / 0.40  # 归一化
            mass_at_rpm = mass_per_rev * rpm * density_factor  # g/rev @ RPM
            
            cal_matrix.append({
                'variety': variety,
                'rpm': rpm,
                'mass_per_rev_g': round(mass_per_rev * density_factor, 3),
                'rate_gps': round(mass_per_rev * density_factor * rpm / 60, 3),
                '250g_fill_time_s': round(250 / (mass_per_rev * density_factor * rpm / 60), 1)
            })
    
    print("\n标定矩阵（螺旋给料φ20mm, 15mm螺距）：")
    print(f"{'品种':<10} {'RPM':>5} {'g/rev':>8} {'速率(g/s)':>10} {'250g填充时间(s)':>16}")
    print("-" * 52)
    for row in cal_matrix[:8]:
        print(f"{row['variety']:<10} {row['rpm']:>5} {row['mass_per_rev_g']:>8.3f} {row['rate_gps']:>10.3f} {row['250g_fill_time_s']:>16.1f}")
    
    print("\n密度修正系数（以Heirloom=0.40 g/mL为基准）：")
    print("  - Heirloom: ×1.000 (基准)")
    print("  - Geisha:   ×0.950 (密度较低，出豆稍慢)")
    print("  - Bourbon:  ×1.050 (密度较高，出豆稍快)")
    print("  - Typica:   ×1.025 (密度稍高)")
    
    # 实验设计
    experiments = [
        {
            'id': 'EXP-6D-01',
            'name': '静态质量验证',
            '目的': '验证螺旋给料器在不同RPM下的出豆质量',
            '方法': '目标质量100g×3次，测量实际出豆量',
            '设备': '精密电子秤（0.01g精度）',
            '判定标准': '偏差<±3g (<±3%)',
            '预计时间': '30分钟'
        },
        {
            'id': 'EXP-6D-02', 
            'name': 'HX711实时速率测量',
            '目的': '验证PID控制下实时出豆速率',
            '方法': 'HX711每100ms采样，计算实时速率曲线',
            '设备': 'HX711 + LoadCell + Python采样脚本',
            '判定标准': '速率波动<±10%（稳态）',
            '预计时间': '45分钟'
        },
        {
            'id': 'EXP-6D-03',
            'name': '250g批次精度测试',
            '目的': '验证整批次出豆总量精度',
            '方法': '目标250g，测量实际出豆量×5次',
            '设备': '精密电子秤（0.01g精度）',
            '判定标准': '误差<±5g',
            '预计时间': '60分钟'
        },
        {
            'id': 'EXP-6D-04',
            'name': '品种密度修正验证',
            '目的': '验证不同品种的密度修正系数',
            '方法': '同一RPM下测试4个品种各250g',
            '设备': '精密电子秤 + 4种生豆样本',
            '判定标准': '各品种误差均<±5g',
            '预计时间': '90分钟'
        },
        {
            'id': 'EXP-6D-05',
            'name': '长期稳定性测试',
            '目的': '连续10批次稳定性（模拟生产）',
            '方法': '连续10×250g，测量每批次精度',
            '设备': '精密电子秤 + HX711记录',
            '判定标准': 'σ<2g，10次全部±5g内',
            '预计时间': '120分钟'
        }
    ]
    
    print("\n物理测试协议（5步实验）：")
    print(f"{'ID':<10} {'名称':<25} {'判定标准':<20} {'预计时间':<10}")
    print("-" * 70)
    for exp in experiments:
        print(f"{exp['id']:<10} {exp['name']:<25} {exp['判定标准']:<20} {exp['预计时间']:<10}")
    
    total_time = sum([int(e['预计时间'][:-3]) for e in experiments])
    print(f"\n总测试时间：约{total_time}分钟（约{total_time/60:.1f}小时）")
    
    return {
        'cal_matrix': cal_matrix[:8],
        'experiments': experiments
    }


# ============================================================
# 主程序：生成综合分析图
# ============================================================

def main():
    print("=== 课题6 Day2：PID控制 + 流量标定 + 分配器时序 ===\n")
    
    # 1. PID控制仿真
    pid_result = simulate_pid_250g_batch()
    
    # 2. PID参数整定
    tuning_results = simulate_tuning_pid()
    
    # 3. 分配器时序分析
    timing_result = analyze_rotary_distributor_timing()
    
    # 4. 流量标定方案
    cal_result = design_flow_calibration()
    
    # 生成图表
    fig = plt.figure(figsize=(16, 12))
    fig.suptitle('课题6 Day2: PID控制 + 流量标定 + 旋转分配器时序', fontsize=14, fontweight='bold')
    
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)
    
    # 子图1：PID控制250g批次出豆
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.fill_between(pid_result['t'], 0, pid_result['mass'], 
                     alpha=0.3, color='steelblue', label='累计出豆量')
    ax1.plot(pid_result['t'], pid_result['mass'], 'b-', linewidth=2)
    ax1.axhline(y=250, color='red', linestyle='--', label='目标250g')
    ax1.axhline(y=245, color='orange', linestyle=':', alpha=0.7, label='±5g范围')
    ax1.axhline(y=255, color='orange', linestyle=':', alpha=0.7)
    ax1.set_xlabel('时间 (s)')
    ax1.set_ylabel('累计出豆量 (g)')
    ax1.set_title('PID控制250g批次出豆（KP=15, KI=0.3, KD=5）')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, 80)
    ax1.set_ylim(0, 280)
    
    # 标注结果
    final_t = pid_result['final_time']
    final_m = pid_result['final_mass']
    ax1.annotate(f'{final_m:.1f}g @ {final_t:.1f}s', 
                xy=(final_t, final_m), 
                xytext=(final_t-15, final_m+20),
                arrowprops=dict(arrowstyle='->', color='green'),
                fontsize=10, color='green')
    
    # 子图2：出豆速率 vs 时间
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.plot(pid_result['t'], pid_result['rate'], 'b-', linewidth=1.5)
    ax2.axhline(y=pid_result['target_rate'], color='red', linestyle='--', 
                label=f'目标 {pid_result["target_rate"]:.3f} g/s')
    ax2.fill_between(pid_result['t'], pid_result['rate'], 
                     pid_result['target_rate'], alpha=0.3, color='steelblue')
    ax2.set_xlabel('时间 (s)')
    ax2.set_ylabel('出豆速率 (g/s)')
    ax2.set_title('实时出豆速率')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, 80)
    
    # 子图3：PID参数整定对比
    ax3 = fig.add_subplot(gs[1, :2])
    colors = {'5.0': 'lightblue', '15.0': 'steelblue', '30.0': 'darkblue'}
    linestyles = {'0.0': '-', '0.3': '--', '0.5': ':'}
    labels_added = set()
    
    for res in tuning_results:
        kp_label = f'KP={res["kp"]}'
        ki_label = f'KI={res["ki"]}'
        color = colors[str(res['kp'])]
        ls = linestyles[str(res['ki'])]
        
        label = f'{kp_label}, {ki_label}'
        if label not in labels_added:
            ax3.plot(res['time'], res['mass'], color=color, linestyle=ls, 
                    linewidth=1.5, label=label)
            labels_added.add(label)
        else:
            ax3.plot(res['time'], res['mass'], color=color, linestyle=ls, linewidth=1.5)
    
    ax3.axhline(y=250, color='red', linestyle='--', label='目标250g')
    ax3.set_xlabel('时间 (s)')
    ax3.set_ylabel('累计出豆量 (g)')
    ax3.set_title('PID参数整定对比（KP/KI组合）')
    ax3.legend(loc='lower right', fontsize=8)
    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(0, 80)
    ax3.set_ylim(0, 280)
    
    # 子图4：RPM变化曲线
    ax4 = fig.add_subplot(gs[1, 2])
    ax4.plot(pid_result['t'], pid_result['rpm'], 'g-', linewidth=1.5)
    ax4.fill_between(pid_result['t'], pid_result['rpm'], alpha=0.3, color='lightgreen')
    ax4.axhline(y=75, color='red', linestyle='--', label='目标~75 RPM')
    ax4.set_xlabel('时间 (s)')
    ax4.set_ylabel('螺旋给料RPM')
    ax4.set_title('PID输出RPM控制')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    ax4.set_xlim(0, 80)
    ax4.set_ylim(0, 130)
    
    # 子图5：旋转分配器时序
    ax5 = fig.add_subplot(gs[2, 0])
    t_a = timing_result['t_arr']
    v_a = timing_result['v_arr']
    ax5.plot([0] + t_a, [0] + timing_result['pos_arr'], 'b-', linewidth=2, label='位置')
    ax5.set_xlabel('时间 (s)')
    ax5.set_ylabel('步进位置', color='blue')
    ax5.tick_params(axis='y', labelcolor='blue')
    ax5.set_title('旋转分配器步进时序（S型加速）')
    ax5.grid(True, alpha=0.3)
    
    ax5b = ax5.twinx()
    ax5b.plot([0] + t_a, [0] + v_a, 'r-', linewidth=1.5, label='速度')
    ax5b.set_ylabel('步进速度 (steps/s)', color='red')
    ax5b.tick_params(axis='y', labelcolor='red')
    ax5b.axhline(y=timing_result['max_steps_per_sec'], color='red', 
                 linestyle=':', alpha=0.5, label=f'最大 {timing_result["max_steps_per_sec"]:.0f} steps/s')
    
    total_ms = timing_result['total_switch_ms']
    ax5.annotate(f'切换时间:\n{total_ms:.0f}ms', 
                xy=(t_a[-1], timing_result['pos_arr'][-1]),
                xytext=(-30, -30),
                arrowprops=dict(arrowstyle='->', color='green'),
                fontsize=9, color='green')
    
    ax5.annotate(f'✅ <200ms' if total_ms < 200 else f'❌ {total_ms:.0f}ms', 
                xy=(0.5, 0.5), xycoords='axes fraction',
                fontsize=12, color='green' if total_ms < 200 else 'red',
                fontweight='bold')
    
    # 子图6：标定矩阵热图
    ax6 = fig.add_subplot(gs[2, 1])
    cal_data = np.array([
        [r['rate_gps'] for r in cal_result['cal_matrix'][:4]],
        [r['rate_gps'] for r in cal_result['cal_matrix'][4:8]]
    ])
    im = ax6.imshow(cal_data, cmap='YlGnBu', aspect='auto')
    ax6.set_xticks([0, 1, 2, 3])
    ax6.set_xticklabels(['30', '60', '90', '120'])
    ax6.set_yticks([0, 1])
    ax6.set_yticklabels(['Heirloom', 'Bourbon'])
    ax6.set_xlabel('RPM')
    ax6.set_ylabel('品种')
    ax6.set_title('出豆速率标定矩阵 (g/s)')
    
    for i in range(2):
        for j in range(4):
            text = ax6.text(j, i, f'{cal_data[i, j]:.2f}',
                          ha='center', va='center', color='black', fontsize=10)
    
    plt.colorbar(im, ax=ax6, shrink=0.6)
    
    # 子图7：实验时间分配饼图
    ax7 = fig.add_subplot(gs[2, 2])
    exp_names = [e['id'] for e in cal_result['experiments']]
    exp_times = [30, 45, 60, 90, 120]
    colors = plt.cm.Set3(np.linspace(0, 1, len(exp_names)))
    
    wedges, texts, autotexts = ax7.pie(exp_times, labels=exp_names, autopct='%1.0f%%',
                                        colors=colors, startangle=90)
    ax7.set_title('标定实验时间分配\n(总计345分钟≈5.75小时)')
    
    plt.tight_layout()
    plt.savefig('/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation/buffer_topic6_day2.png', 
                dpi=150, bbox_inches='tight', facecolor='white')
    print("\n图表已保存: buffer_topic6_day2.png")
    
    # 打印关键结果摘要
    print("\n" + "="*60)
    print("课题6 Day2 研究结果摘要")
    print("="*60)
    print(f"\n【PID控制算法】")
    print(f"  - 250g批次：{pid_result['final_mass']:.1f}g @ {pid_result['final_time']:.1f}s")
    print(f"  - 推荐参数：KP=15, KI=0.3, KD=5")
    print(f"  - 目标速率：{pid_result['target_rate']:.3f} g/s = 3.571 g/s")
    print(f"  - 满速120RPM对应最大速率：3.582 g/s")
    
    print(f"\n【旋转分配器】")
    print(f"  - 切换时间：{timing_result['total_switch_ms']:.0f}ms")
    print(f"  - 判定：{'✅ <200ms 通过' if timing_result['total_switch_ms'] < 200 else '❌ 超过200ms'}")
    print(f"  - S型加速曲线：加速{int(accel_steps:=16)}步 → 匀速{int(cruise_steps:=timing_result['steps_per_step']-32)}步 → 减速16步")
    
    print(f"\n【流量标定】")
    print(f"  - 5步实验，总计约345分钟（约5.75小时）")
    print(f"  - 密度修正：Heirloom基准×1.000，Geisha×0.950，Bourbon×1.050，Typica×1.025")
    print(f"  - 标定判定标准：250g批次误差<±5g")


if __name__ == '__main__':
    main()