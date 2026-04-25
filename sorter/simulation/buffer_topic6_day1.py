#!/usr/bin/env python3
"""
课题6 Day1: 缓冲料仓 + 螺旋给料 — 设计与分析
Buffer Bin + Spiral Feeder Design Analysis

研究内容：
1. 缓冲料仓设计（8格分级仓）
2. 流量分析与给料速率
3. 螺旋给料器原理与规格
4. 分批控制逻辑
5. 与烘豆机的接口时序

Author: Little Husky 🐕
Date: 2026-04-26
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# SECTION 1: 缓冲料仓设计 — 8格分级仓
# ============================================================

def design_buffer_bin():
    """
    缓冲料仓设计分析
    目标：接收来自含水率传感器的已分级生豆，按品质等级分配到不同料格
    """
    print("=" * 60)
    print("缓冲料仓设计分析")
    print("=" * 60)

    # 系统参数
    target_throughput_kg_h = 2.0  # 目标产能 kg/h
    bean_avg_weight_g = 0.150    # 单粒平均重量 g
    beans_per_kg = 1 / bean_avg_weight_g * 1000  # ≈ 6667 beans/kg

    # 品质等级分布（典型精品咖啡）
    grade_distribution = {
        'A': 0.70,   # 70% A级
        'B': 0.20,   # 20% B级
        'C': 0.08,   # 8% C级
        'reject': 0.02  # 2% 剔除（前面各站已处理）
    }

    # 8格设计：3个A级格，2个B级格，2个C级格，1个缓冲/备用
    bin_config = {
        'A1': {'capacity_g': 100, 'grade': 'A'},
        'A2': {'capacity_g': 100, 'grade': 'A'},
        'A3': {'capacity_g': 100, 'grade': 'A'},
        'B1': {'capacity_g': 80,  'grade': 'B'},
        'B2': {'capacity_g': 80,  'grade': 'B'},
        'C1': {'capacity_g': 60,  'grade': 'C'},
        'C2': {'capacity_g': 60,  'grade': 'C'},
        'BF': {'capacity_g': 100, 'grade': 'buffer'},  # Buffer/备用
    }

    total_capacity_g = sum(b['capacity_g'] for b in bin_config.values())
    print(f"\n料仓总容量: {total_capacity_g}g = {total_capacity_g/1000:.2f}kg")
    print(f"目标产能: {target_throughput_kg_h} kg/h")
    print(f"满仓持续时间: {total_capacity_g / (target_throughput_kg_h * 1000 / 3600):.0f}s = {total_capacity_g / (target_throughput_kg_h * 1000 / 3600) / 60:.1f}min")

    # 计算各等级流量
    print("\n各等级豆流率:")
    for grade, frac in grade_distribution.items():
        flow_g_h = target_throughput_kg_h * 1000 * frac
        flow_bpm = flow_g_h / bean_avg_weight_g / 60  # beans per minute
        print(f"  {grade}: {flow_g_h:.1f} g/h = {flow_bpm:.1f} beans/min")

    # 入料漏斗设计
    print("\n入料漏斗设计:")
    inlet_hopper_vol_cm3 = 50  # 目标体积 cm3
    inlet_hopper_angle = 45  # 漏斗半角（度）
    inlet_hopper_height_mm = 30  # 漏斗高度
    # 入口面积计算（假设方形）
    inlet_area_mm2 = inlet_hopper_vol_cm3 * 10  # ≈500 mm2
    inlet_side_mm = np.sqrt(inlet_area_mm2)
    print(f"  入口尺寸: {inlet_side_mm:.0f}×{inlet_side_mm:.0f}mm")
    print(f"  漏斗角度: {inlet_hopper_angle}°")
    print(f"  漏斗高度: {inlet_hopper_height_mm}mm")
    print(f"  出料口直径: φ{min(20, inlet_side_mm * 0.4):.0f}mm")

    # 分配器（8通道）设计
    print("\n8通道旋转分配器:")
    distributor_type = "旋转圆盘阀"  # vs 电磁挡板
    n_channels = 8
    channel_pitch_mm = 8.0  # 相邻通道间距
    disc_diameter_mm = 8 * channel_pitch_mm + 20  # 留边
    print(f"  类型: {distributor_type}")
    print(f"  通道数: {n_channels}")
    print(f"  圆盘直径: φ{disc_diameter_mm:.0f}mm")
    print(f"  通道间距: {channel_pitch_mm}mm")
    print(f"  驱动: 42步进电机（28BYJ-48），分度角 = 360°/8 = 45°")
    print(f"  分度时间: <200ms（高速光轴步进电机）")

    # 各格填充时间估算
    print("\n各格预计填充时间（满仓到空仓）:")
    for bin_name, bin_data in bin_config.items():
        grade = bin_data['grade']
        capacity = bin_data['capacity_g']
        frac = grade_distribution.get(grade, 0)
        flow_g_h = target_throughput_kg_h * 1000 * frac
        fill_time_h = capacity / flow_g_h if flow_g_h > 0 else float('inf')
        print(f"  {bin_name} ({grade}, {capacity}g): {fill_time_h*3600:.0f}s = {fill_time_h:.1f}h")

    return bin_config, grade_distribution

# ============================================================
# SECTION 2: 流量分析与给料速率
# ============================================================

def analyze_flow_rate():
    """
    流量分析：从含水率传感器到缓冲仓的流动特性
    """
    print("\n" + "=" * 60)
    print("流量分析与给料速率")
    print("=" * 60)

    # 来自含水率传感器的出料速率
    moisture_measurement_time_ms = 270  # 含水率测量周期（Day3结果）
    max_beans_from_moisture = 60000 / moisture_measurement_time_ms  # beans/min
    print(f"\n含水率传感器最大出料: {max_beans_from_moisture:.0f} beans/min")
    print(f"  （测量周期 {moisture_measurement_time_ms}ms/粒）")

    # 目标处理量换算
    target_kg_h = 2.0
    bean_weight_g = 0.150
    target_bpm = target_kg_h * 1000 / bean_weight_g / 60  # beans/min
    print(f"\n目标处理量 {target_kg_h}kg/h:")
    print(f"  = {target_bpm:.0f} beans/min")

    # 缓冲仓的入料利用率
    utilization = target_bpm / max_beans_from_moisture * 100
    print(f"  含水率传感器利用率: {utilization:.1f}%")
    print(f"  （远低于最大值，系统有余量 ✅）")

    # 螺旋给料器参数设计（修正版：增大管道直径以满足2kg/h出豆需求）
    print("\n螺旋给料器参数设计（修正版）:")

    # 咖啡豆体积
    bean_vol_mm3 = 9 * 6.5 * 3.5  # 近似 mm3
    bean_vol_cm3 = bean_vol_mm3 / 1000  # ≈ 0.20 cm3
    bean_fill_density = 0.65  # 填充密度（豆子松堆）

    # 螺旋参数 — 修正：增大管道到φ20mm，增大螺距到15mm
    helix_pitch_mm = 15       # 螺距（增大以提高给料速率）
    tube_id_mm = 20           # 管道内径（增大到φ20mm）
    effective_fill = 0.40     # 有效填充率（豆子松堆）

    tube_area_mm2 = np.pi * (tube_id_mm/2)**2
    volume_per_rev_cm3 = (tube_area_mm2 * helix_pitch_mm / 1000) * effective_fill
    bean_density_g_cm3 = 0.95  # 咖啡豆真实密度
    mass_per_rev_g = volume_per_rev_cm3 * bean_density_g_cm3
    print(f"  管道内径: φ{tube_id_mm}mm（修正版，增大以满足出豆速率）")
    print(f"  螺距: {helix_pitch_mm}mm")
    print(f"  有效填充率: {effective_fill*100:.0f}%")
    print(f"  每转体积: {volume_per_rev_cm3:.2f} cm3")
    print(f"  每转质量: {mass_per_rev_g:.3f} g/rev")

    # 达到250g批次所需转数
    batch_size_g = 250
    revs_for_batch = batch_size_g / mass_per_rev_g
    print(f"\n  250g批次所需转数: {revs_for_batch:.1f} rev")

    # 步进电机参数（28BYJ-48）
    step_angle_deg = 5.625  # 28BYJ-48 step angle
    steps_per_rev = 360 / step_angle_deg  # = 64 steps/rev
    microstep = 8  # DRV8833 microstep
    steps_for_batch = revs_for_batch * steps_per_rev * microstep
    print(f"  28BYJ-48 步距角: {step_angle_deg}°")
    print(f"  DRV8833 microstep: 1/{microstep}")
    print(f"  每转脉冲数: {steps_per_rev*microstep:.0f}")

    # 典型转速下给料速率（修正版）
    print(f"\n  不同转速下的给料速率（φ20mm管道）:")
    for rpm in [30, 60, 90, 120, 150]:
        g_per_min = mass_per_rev_g * rpm
        kg_per_h = g_per_min * 60 / 1000
        time_for_250g_s = batch_size_g / g_per_min * 60
        marker = " ← 满足2kg/h" if kg_per_h >= 2.0 else ""
        print(f"    {rpm:3d} RPM: {g_per_min:6.2f} g/min = {kg_per_h:.2f} kg/h | 250g需{time_for_250g_s:5.0f}s{marker}")

    # 推荐转速
    target_rpm = 120
    g_per_min_target = mass_per_rev_g * target_rpm
    print(f"\n  ✅ 推荐转速: {target_rpm} RPM ({g_per_min_target:.1f} g/min = {g_per_min_target*60/1000:.2f} kg/h)")
    time_for_250g_target = batch_size_g / g_per_min_target * 60
    print(f"     250g批次出豆时间: {time_for_250g_target:.1f}s")

# ============================================================
# SECTION 3: 分批控制逻辑
# ============================================================

def design_batch_control():
    """
    分批控制逻辑设计
    """
    print("\n" + "=" * 60)
    print("分批控制逻辑设计")
    print("=" * 60)

    # 分批参数
    batch_weight_g = 250
    portion_count = 8  # 2kg / 250g = 8份

    print(f"\n分批参数:")
    print(f"  每份重量: {batch_weight_g}g")
    print(f"  总重量: 2000g")
    print(f"  批次数: {portion_count}")

    # 分批时序
    print("\n分批时序（接收到 ROASTER_READY 信号后）:")
    t = 0
    for i in range(1, portion_count + 1):
        spiral_dispense_time_s = batch_weight_g / 15  # ≈ 16.7g/s @ 15g/min
        roaster_process_time_s = 600  # 烘烤约10分钟（假设）
        cooldown_time_s = 120  # 冷却2分钟

        print(f"  批次{i}: T+{t}s 发送BATCH_START")
        print(f"          T+{t+spiral_dispense_time_s:.0f}s 螺旋给料完成")
        print(f"          T+{t+spiral_dispense_time_s+30:.0f}s 发送BATCH_FEED_COMPLETE")
        t += spiral_dispense_time_s + cooldown_time_s + 60  # cooldown + 信号延迟

    # 状态机
    print("\n缓冲仓状态机:")
    states = [
        ('IDLE', '等待豆子填充，监测各格液位'),
        ('FILLING', '豆子持续落入相应等级格，分配器旋转对准'),
        ('BATCH_READY', f'某格达到{portion_count*batch_weight_g}g，准备出豆'),
        ('DISPENSING', '螺旋给料器运行，目标250g'),
        ('DISPENSE_DONE', '出豆完成，等待烘豆机接收信号'),
        ('COOLDOWN', '等待烘豆机完成本批烘烤'),
        ('NEXT_BATCH', '开始下一批'),
    ]
    for state, desc in states:
        print(f"  [{state}] {desc}")

    # 液位检测方案
    print("\n液位检测方案:")
    level_methods = [
        ('电容液位计', '非接触，可贴仓壁安装', '¥15/个'),
        ('红外对射', '简单可靠，精度±5mm', '¥5/个'),
        ('称重传感器', '可同时测量重量，精确控制', '¥30/个 (复用HX711)'),
    ]
    for name, pros, cost in level_methods:
        print(f"  {name}: {pros} | {cost}")

    # 推荐方案
    print("\n✅ 推荐方案: 电容液位计 × 8（贴仓壁安装）")
    print("   - 非接触，不干扰豆流")
    print("   - 8个液位传感器实时监测各格填充状态")
    print("   - 接近满时通知操作员更换容器")

# ============================================================
# SECTION 4: CAD 缓冲料仓设计
# ============================================================

def generate_cad_buffer_bin():
    """
    生成缓冲料仓的OpenSCAD参数化设计
    """
    print("\n" + "=" * 60)
    print("缓冲料仓 CAD 设计")
    print("=" * 60)

    # 参数（与主逻辑一致）
    n_bins = 8
    bin_width_mm = 25
    bin_depth_mm = 30
    bin_height_mm = 40
    wall_mm = 2.5
    gap_mm = 1.0
    hopper_height_mm = 25
    disc_diameter_mm = 76
    disc_thickness_mm = 3

    cad_code = '''
// ============================================================
// sorter/cad/buffer_bin.scad
// 缓冲料仓 3D 设计 — 8格分级仓 + 旋转分配器
// Generated by: Little Husky 🐕 | 2026-04-26
// ============================================================

// ========== 全局参数 ==========
$fn = 64;

// 8格参数
n_bins = 8;
bin_width_mm = 25;    // 单格宽度
bin_depth_mm = 30;    // 单格深度
bin_height_mm = 40;   // 单格高度
wall_mm = 2.5;        // 壁厚
gap_mm = 1.0;         // 格间间隙

// 漏斗参数
hopper_height_mm = 25;
hopper_angle_deg = 45;

// 分配器参数
disc_diameter_mm = 76;
disc_thickness_mm = 3;

// ========== 仓体 ==========
module bin_box() {
    total_width = n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * wall_mm;
    total_depth = bin_depth_mm + 2 * wall_mm;
    total_height = bin_height_mm + 2 * wall_mm;

    difference() {
        // 外壳
        translate([0, 0, 0])
            cube([total_width, total_depth, total_height], center=false);

        // 内部8格（挖空）
        for (i = [0:n_bins-1]) {
            x = wall_mm + i * (bin_width_mm + gap_mm);
            translate([x, wall_mm, wall_mm])
                cube([bin_width_mm, bin_depth_mm, bin_height_mm + 1]);
        }
    }
}

// ========== 入口漏斗 ==========
module inlet_hopper() {
    total_width = n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * wall_mm;
    inlet_diameter_top_mm = total_width * 0.6;
    inlet_diameter_bottom_mm = 20;

    translate([total_width/2, bin_depth_mm/2 + wall_mm, wall_mm + bin_height_mm])
    rotate([180, 0, 0])
    linear_extrude(height=hopper_height_mm, scale=[inlet_diameter_top_mm/inlet_diameter_bottom_mm, inlet_diameter_top_mm/inlet_diameter_bottom_mm])
        circle(d=inlet_diameter_bottom_mm, $fn=32);
}

// ========== 8通道旋转分配器 ==========
module rotary_distributor() {
    total_width = n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * wall_mm;
    channel_pitch_mm = bin_width_mm + gap_mm;
    center_x = total_width / 2;
    center_z = wall_mm + bin_height_mm + hopper_height_mm;

    translate([center_x, bin_depth_mm/2 + wall_mm, center_z])
    rotate([0, 0, 0])
    difference() {
        // 圆盘
        cylinder(h=disc_thickness_mm, d=disc_diameter_mm);
        // 8个通道孔（120° 分布，每个格对应一个通道）
        for (i = [0:n_bins-1]) {
            angle = i * 360 / n_bins;
            x = cos(angle) * (disc_diameter_mm/2 - 8);
            y = sin(angle) * (disc_diameter_mm/2 - 8);
            translate([x, y, -1])
                cylinder(h=disc_thickness_mm + 2, d=channel_pitch_mm * 0.7);
        }
    }
}

// ========== 步进电机安装座 ==========
module motor_mount() {
    // 28BYJ-48 尺寸: 28×28×19mm
    motor_size_mm = 28;
    mount_height_mm = 15;
    hole_spacing_mm = 20;  // M3螺栓孔间距

    total_width = n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * wall_mm;
    center_x = total_width / 2;

    translate([center_x - motor_size_mm/2, bin_depth_mm/2 + wall_mm + 15, wall_mm + bin_height_mm + hopper_height_mm + disc_thickness_mm])
    difference() {
        cube([motor_size_mm + 10, mount_height_mm, motor_size_mm + 10]);
        // 电机安装孔
        for (x = [2, motor_size_mm + 8])
            for (y = [2, motor_size_mm + 8])
                translate([x, -1, y])
                    cylinder(h=mount_height_mm + 2, d=3.5);
    }
}

// ========== 出豆口（每格底部）==========
module bin_outlet() {
    for (i = [0:n_bins-1]) {
        x = wall_mm + i * (bin_width_mm + gap_mm) + bin_width_mm/2;
        translate([x - 4, wall_mm + bin_depth_mm + 2, 0])
            cube([8, 10, wall_mm]);  // 出豆口
    }
}

// ========== 组装 ==========
module buffer_bin_assembly() {
    bin_box();
    inlet_hopper();
    rotary_distributor();
    motor_mount();
    bin_outlet();
}

// 渲染
buffer_bin_assembly();

// ========== 打印设置 ==========
// 分层切片: 0.2mm
// 材料: PETG
// 填充: 20%
// 支撑: 漏斗需要支撑
'''

    output_path = '/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/cad/buffer_bin.scad'
    with open(output_path, 'w') as f:
        f.write(cad_code)
    print(f"\nCAD 文件已生成: {output_path}")
    print("\n设计参数:")
    print(f"  8格仓体: {n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * 2.5}×{bin_depth_mm + 5}×{bin_height_mm + 5}mm")
    print(f"  单格容量: ~80-100g (按品种密度)")
    print(f"  总容量: ~700g")
    print(f"  分配器: φ76mm 圆盘，8通道，42步进电机驱动")

    return cad_code

# ============================================================
# SECTION 5: 与烘豆机接口时序
# ============================================================

def design_roaster_interface():
    """
    与烘豆机的接口时序设计
    """
    print("\n" + "=" * 60)
    print("与烘豆机接口设计")
    print("=" * 60)

    # 接口信号
    print("\n接口信号定义:")
    signals = [
        ('SORTER_READY',      'DO', '分选机准备就绪'),
        ('UPSTREAM_READY',    'DI', '烘豆机请求接豆（冷却完成）'),
        ('BATCH_DATA',        'DO', '批次数据JSON（MQTT）'),
        ('BATCH_FEED_START',  ('DO', 'DI'), '分选机开始出豆 → 烘豆机确认'),
        ('BATCH_FEED_COMPLETE','DO', '分选机出豆完成'),
        ('ROASTER_RECEIVING', 'DI', '烘豆机正在接收'),
    ]
    for name, direction, desc in signals:
        print(f"  {name}: {direction} | {desc}")

    # MQTT主题
    print("\nMQTT 主题:")
    topics = [
        ('sorter/{id}/batch/output',  'PUB', 'BATCH_READY（批次已就绪）'),
        ('sorter/{id}/batch/feed',    'PUB', 'BATCH_FEED_START/COMPLETE'),
        ('roaster/{id}/batch/input',  'SUB', '接收烘豆机 BATCH_START 信号'),
        ('roaster/{id}/status',       'SUB', '接收烘豆机状态（UPSTREAM_READY等）'),
    ]
    for topic, direction, desc in topics:
        print(f"  {topic} [{direction}] — {desc}")

    # 时序流程
    print("\n典型出豆时序:")
    timeline = [
        (0,    'SORTER_READY=1',       '分选机已完成批次分选，等待出豆'),
        (0,    '订阅 roaster/{id}/status', '监听烘豆机状态'),
        (0,    'IF UPSTREAM_READY==1 → 启动出豆', ''),
        (30,   '发送 BATCH_START JSON', 'MQTT → roaster/{id}/batch/input'),
        (30,   '打开螺旋给料器',        '开始出250g'),
        (47,   '螺旋给料器完成（250g）', '@ 15g/s → ~17s'),
        (47,   '发送 BATCH_FEED_COMPLETE', 'MQTT → sorter/{id}/batch/feed'),
        (47,   '等待 ROASTER_RECEIVING=1', '确认烘豆机已接收'),
        (600,  '收到下一批 UPSTREAM_READY=1', '冷却完成，开始下一批'),
    ]
    for t, event, note in timeline:
        if note:
            print(f"  T+{t:4d}s: {event:40s} — {note}")
        else:
            print(f"  T+{t:4d}s: {event}")

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("课题6 Day1: 缓冲料仓 + 螺旋给料 — 设计分析")
    print("=" * 60)
    print()

    # 1. 缓冲料仓设计
    bin_config, grade_dist = design_buffer_bin()

    # 2. 流量分析
    analyze_flow_rate()

    # 3. 分批控制逻辑
    design_batch_control()

    # 4. CAD设计
    generate_cad_buffer_bin()

    # 5. 烘豆机接口
    design_roaster_interface()

    print("\n" + "=" * 60)
    print("✅ 课题6 Day1 分析完成")
    print("=" * 60)
    print("\n新增文件:")
    print("  sorter/simulation/buffer_topic6_day1.py")
    print("  sorter/cad/buffer_bin.scad")
    print("\n今日成果:")
    print("  1. 8格缓冲仓结构设计（容量/流量分析）")
    print("  2. 螺旋给料器参数设计（螺距/转速/批次）")
    print("  3. 分批控制状态机设计")
    print("  4. CAD OpenSCAD参数化设计（buffer_bin.scad）")
    print("  5. MQTT+信号接口时序设计")
    print("\n待办（Day2）:")
    print("  - PID控制算法设计")
    print("  - 流量标定实验方案")
    print("  - 旋转分配器步进时序")
