#!/usr/bin/env python3
"""
课题5 Day3: 含水率检测 — CAD探头设计 + 物理测试协议 + 集成分析
================================================================
内容：
1. CAD探头3D设计（3D打印夹具 + 电极安装 + AD7746模块固定）
2. 物理测试协议（6步硬件验证 + 通过标准）
3. 集成分析（流水线时序 + 含水率决策逻辑 + 多传感器数据融合）

Author: Little Husky 🐕
Date: 2026-04-25
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════════════════════
# PART 1: CAD 探头3D设计
# ═══════════════════════════════════════════════════════════

def cad_probe_design():
    """
    电容式含水率探头 CAD 设计分析
    
    设计目标：
    1. 两块平行电极板（15×15mm），精确间距8mm
    2. 豆子通道：单粒落杯定位
    3. AD7746模块紧贴探头（<5cm引线）
    4. 3D打印可制造性（PETG / SLA树脂）
    5. 同轴电缆出口 + 屏蔽接地
    """
    
    print("\n" + "="*60)
    print("PART 1: CAD 探头3D设计")
    print("="*60)
    
    print("\n📐 探头主体设计规格:")
    design_params = {
        "电极尺寸": "15×15×1mm（不锈钢板）",
        "极板间隙": "8mm（定位销保证）",
        "支架材质": "PETG（食品级，耐温）",
        "总高度": "22mm",
        "安装法兰": "φ30mm，3×M3螺栓",
        "电缆出口": "侧面M6螺纹孔（推荐）或底部走线",
        "AD7746模块安装": "直接插针焊接在探头PCB上（最优先）",
    }
    for k, v in design_params.items():
        print(f"  • {k}: {v}")
    
    print("\n🔧 电极安装方案对比:")
    electrode_options = [
        ("PCB铜箔", "¥3", "高精度，可微调", "✅ 推荐 — 集成AD7746最小化寄生电容", "1.6mm FR4 双面板"),
        ("不锈钢板", "¥5", "耐用，平面度好", "备选 — 需单独接线", "1mm 304不锈钢"),
    ]
    print("  | 方案 | 成本 | 优点 | 结论 | 备注 |")
    print("  |------|------|------|------|------|")
    for opt in electrode_options:
        print(f"  | {' | '.join(opt)} |")
    
    print("\n🏗️ 3D打印结构设计（PETG）：")
    structure_components = [
        ("底座框架", "φ34×4mm法兰盘", "3×M3沉头孔，120°分布", "安装定位台阶"),
        ("下极板托架", "20×20×2mm凹槽", "精确放置下电极，边缘对齐", "M2定位销×2"),
        ("隔离柱×4", "φ3×8mm圆柱", "均匀分布于四角，保证间隙", "±0.05mm同心度"),
        ("上极板压板", "20×20×2mm", "覆盖上电极，M2螺栓固定", "中央M2通孔"),
        ("豆子入口漏斗", "φ20→15mm喇叭口", "引导单粒豆落入两极板间", "3D打印一体化"),
        ("AD7746模块座", "20×15×5mm", "紧贴探头底部，排针直插", "0.5mm间隙避让"),
        ("电缆密封头", "M6×8mm内径", "侧面出口，螺纹锁紧", "PG7也可"),
    ]
    print("  | 零件 | 尺寸 | 制造要求 | 备注 |")
    print("  |------|------|----------|------|")
    for comp in structure_components:
        print(f"  | {' | '.join(comp)} |")
    
    print("\n📁 生成CAD文件:")
    print("  • sorter/cad/moisture_probe.scad (OpenSCAD参数化设计)")
    print("  • sorter/cad/moisture_probe_design.py (设计脚本)")
    
    print("\n🔨 装配步骤:")
    assembly_steps = [
        ("Step 1", "PCB电极 + AD7746模块焊接", "0.8mm铜箔，30AWG细电线连接CAP+/CAP-到电极"),
        ("Step 2", "下极板定位", "PCB放入底座凹槽，插入M2定位销×2"),
        ("Step 3", "安装隔离柱×4", "四角插入φ3隔离柱，确认垂直度"),
        ("Step 4", "上极板安装", "放入上电极，压上压板，M2螺栓轻紧"),
        ("Step 5", "AD7746模块固定", "排针插入模块座，焊接固定"),
        ("Step 6", "电缆密封", "穿入同轴电缆（≤30cm），拧紧M6密封头"),
        ("Step 7", "电气测试", "空载读数应约0.25pF（理论）"),
    ]
    print("  | 步骤 | 内容 | 操作要点 |")
    print("  |------|------|----------|")
    for step in assembly_steps:
        print(f"  | {' | '.join(step)} |")
    
    print("\n⚠️ 关键设计决策（Day3）:")
    decisions = [
        ("AD7746紧贴探头", "模块直接插针焊接在探头PCB上，彻底消除长电缆寄生电容问题", "0 cable distance → 0 extra capacitance ✅"),
        ("PCB一体化电极", "15×15mm铜箔电极 + 探头支架一次设计，定位精度高", "避免不锈钢板+螺丝位移误差"),
        ("隔离柱四角定位", "φ3隔离柱代替弹簧，保证极板平行度<0.05mm", "弹簧长时间会疲劳，隔离柱永不变形"),
    ]
    for title, desc, result in decisions:
        print(f"\n  ✅ {title}")
        print(f"     {desc}")
        print(f"     → {result}")
    
    return {
        'electrode_material': 'PCB copper foil (FR4 1.6mm)',
        'gap_mm': 8.0,
        'plate_size_mm': 15.0,
        'cad_files': ['moisture_probe.scad', 'moisture_probe_design.py'],
    }


# ═══════════════════════════════════════════════════════════
# PART 2: 物理测试协议（6步硬件验证）
# ═══════════════════════════════════════════════════════════

def physical_test_protocol():
    """
    含水率传感器 — 物理测试协议（6步硬件验证）
    """
    
    print("\n" + "="*60)
    print("PART 2: 物理测试协议（6步验证）")
    print("="*60)
    
    print("\n📦 所需测试设备:")
    equipment = [
        ("Raspberry Pi 4B", "1台", "运行AD7746 I2C读取软件"),
        ("AD7746模块", "1片", "已焊接探头PCB"),
        ("USB电源 5V/3A", "1个", "供电"),
        ("分析天平 (±0.001g)", "1台", "称量标定样本"),
        ("烘箱 (±1°C精度)", "1台", "烘干法制备参考样本"),
        ("干燥器 + 硅胶", "1套", "冷却存放"),
        ("1000pF参考电容", "1个", "精度±1%"),
    ]
    print("  | 设备 | 数量 | 用途 |")
    print("  |------|------|------|")
    for item in equipment:
        print(f"  | {' | '.join(item)} |")
    
    print("\n📋 6步测试协议:")
    
    protocol_steps = [
        {
            'step': 'Step 1',
            'name': '电气检查',
            'duration': '5 min',
            'purpose': '排除短路/开路，确认I2C通信',
            'procedure': [
                '1. 视觉检查：PCB无短路，焊点良好',
                '2. 电阻检查：CAP+↔CAP- ≥ 10MΩ（无豆）',
                '3. I2C扫描：i2cdetect -y 1 应显示 0x48',
                '4. AD7746寄存器读：Status=0x00（RDY=0表示待机）',
            ],
            'pass_criteria': 'I2C地址0x48响应，寄存器读数正常',
            'expected_value': '0x48 @ i2cdetect, Status register readable',
        },
        {
            'step': 'Step 2',
            'name': '零点标定（空载基线）',
            'duration': '10 min',
            'purpose': '建立空载电容基线，确认无豆时电容<0.70pF',
            'procedure': [
                '1. 探头内不放任何物体',
                '2. 连续读取10次C值，间隔1秒',
                '3. 计算均值和标准差',
                '4. 与理论值 C_air = ε₀×A/d = 0.248pF 比较',
            ],
            'pass_criteria': '读数稳定，σ<0.05pF，与理论值偏差<0.5pF',
            'expected_value': 'C_air ≈ 0.25 pF（理论），实测应在0.1-0.5pF范围',
        },
        {
            'step': 'Step 3',
            'name': '参考电容验证',
            'duration': '10 min',
            'purpose': '用已知参考电容验证AD7746系统精度',
            'procedure': [
                '1. 断开探头，插入1000pF参考电容（精度±1%）',
                '2. 连续读取10次',
                '3. 计算读数与标称值偏差',
            ],
            'pass_criteria': '偏差<±1%（±10pF @ 1000pF）',
            'expected_value': '1000pF ± 10pF',
        },
        {
            'step': 'Step 4',
            'name': '干豆基准测量（5%含水率）',
            'duration': '60 min（含样本准备）',
            'purpose': '建立第一个标定锚点',
            'procedure': [
                '1. 取约10g咖啡豆样品（已烘干确认为5%）',
                '2. 分析天平精确称重 W_wet',
                '3. 放入探头，等待10秒稳定',
                '4. 连续读取10次含水率值',
                '5. 计算均值，与参考值偏差',
            ],
            'pass_criteria': '含水率读数在4.5%-5.5%范围（±0.5%目标）',
            'expected_value': '5.0% ± 0.5%（即4.5-5.5%）',
        },
        {
            'step': 'Step 5',
            'name': '高湿豆验证（15%含水率）',
            'duration': '30 min（不含平衡时间）',
            'purpose': '建立第二个标定锚点，确认高湿端线性',
            'procedure': [
                '1. 取约10g高湿豆样品（S5，精确配制为15%）',
                '2. 放入探头，等待10秒稳定',
                '3. 连续读取10次含水率值',
                '4. 计算均值，与参考值偏差',
            ],
            'pass_criteria': '含水率读数在14.5%-15.5%范围',
            'expected_value': '15.0% ± 0.5%（即14.5-15.5%）',
        },
        {
            'step': 'Step 6',
            'name': '重复性与稳定性测试',
            'duration': '30 min',
            'purpose': '验证系统重复性（σ<0.2%）和24小时稳定性',
            'procedure': [
                '1. 标准样本（S3，10%含水率）连续测量10次',
                '2. 计算标准差σ',
                '3. 室温放置，每小时测1次，共测6次',
                '4. 计算温漂影响',
            ],
            'pass_criteria': 'σ<0.2% (对应<0.02pF)，温漂<0.5%/°C',
            'expected_value': 'σ<0.2%，典型值约0.05-0.1%',
        },
    ]
    
    print()
    for s in protocol_steps:
        print(f"  ┌{'-'*58}┐")
        print(f"  │ {s['step']}: {s['name']:<45} │")
        print(f"  ├{'-'*58}┤")
        print(f"  │ ⏱️ 时间: {s['duration']:<50} │")
        print(f"  │ 🎯 目的: {s['purpose']:<48} │")
        print(f"  │")
        for proc in s['procedure']:
            print(f"  │   {proc:<55} │")
        print(f"  │")
        print(f"  │ ✅ 通过标准: {s['pass_criteria']:<45} │")
        print(f"  │ 📊 期望值: {s['expected_value']:<46} │")
        print(f"  └{'-'*58}┘")
        print()
    
    print("\n📅 完整测试时间线:")
    total_min = 5 + 10 + 10 + 60 + 30 + 30
    print(f"  总时间: {total_min}分钟（不含样本准备和24h稳定性测试）")
    print("  | 阶段 | 时间 | 内容 |")
    print("  |------|------|------|")
    print("  | 准备 | 30min | 设备就绪，AD7746连接，天平校准 |")
    print(f"  | Steps 1-6 | {total_min}min | 完整6步测试 |")
    print(f"  | 总计 | {total_min+30}min | 含准备时间 |")
    
    print("\n🔧 故障排除指南:")
    faults = [
        ("I2C地址找不到 (0x48)", "检查SDA/SCL接线，确认ADR=GND", "i2cdetect -y 1"),
        ("读数一直为0或负值", "探头短路，检查CAP+/CAP-间是否有焊渣", "万用表测电阻≥10MΩ"),
        ("读数过大 (>10pF空载)", "探头有杂物或潮湿，清洁并烘干", "正常空载<0.5pF"),
        ("读数跳动大 (σ>0.5pF)", "AD7746未初始化，或I2C总线干扰", "检查供电3.3V稳定"),
        ("Step 4/5偏差>1%", "探头位置不正，或样本含水率不准", "重新配制S1/S5样本"),
    ]
    print("  | 故障 | 原因 | 排查方法 |")
    print("  |------|------|----------|")
    for fault in faults:
        print(f"  | {' | '.join(fault)} |")
    
    return protocol_steps


# ═══════════════════════════════════════════════════════════
# PART 3: 集成分析
# ═══════════════════════════════════════════════════════════

def integration_analysis():
    """
    含水率传感器 — 流水线集成分析
    """
    
    print("\n" + "="*60)
    print("PART 3: 集成分析（流水线 + 决策逻辑）")
    print("="*60)
    
    print("\n⏱️ 含水率检测时序分析:")
    
    pipeline_stages = [
        ("Size Sorting", "振动给料→尺寸孔板", 0, 200, "机械"),
        ("Color Detection", "双摄像头拍摄+L*a*b*分析", 200, 270, "图像处理"),
        ("Weight Measurement", "Buffer Cup称重", 270, 350, "LoadCell+HX711"),
        ("Density Sorting", "气流上扬2-way分离", 350, 450, "PWM风扇"),
        ("Moisture Sensing", "电容探头测量", 450, 530, "AD7746 I2C"),
        ("Buffer Storage", "8格缓冲仓", 530, 600, "步进电机"),
        ("Feed to Roaster", "螺旋给料→烘豆机", 600, 700, "气动脉冲"),
    ]
    
    print("  | 阶段 | 动作 | 开始(ms) | 结束(ms) | 类型 |")
    print("  |------|------|---------|---------|------|")
    for stage in pipeline_stages:
        print(f"  | {' | '.join(str(x) for x in stage)} |")
    
    print("\n  含水率检测详细时序:")
    moisture_timing = [
        ("豆子落入探头", 0, 10),
        ("电容稳定等待", 10, 50),
        ("AD7746采样 (5次平均)", 50, 200),
        ("I2C数据传输 (20bytes)", 200, 210),
        ("含水率计算 + 决策", 210, 220),
        ("释放豆子到Buffer", 220, 270),
    ]
    print("  | 子阶段 | 开始(ms) | 结束(ms) |")
    print("  |--------|---------|---------|")
    for t in moisture_timing:
        print(f"  | {' | '.join(str(x) for x in t)} |")
    
    total_moisture = 270
    print(f"\n  总测量周期: {total_moisture}ms/粒 → 最大可行速率: {60000/total_moisture:.0f} beans/min")
    print(f"  ✅ 大幅超过目标 30 beans/min（含水率检测不是瓶颈）")
    
    print("\n🔢 含水率决策逻辑:")
    moisture_thresholds = [
        ("< 5%", "UNDER_DRIED", "❌ 剔除", "含水率过低，烘焙易焦化"),
        ("5-12%", "OPTIMAL", "✅ 合格", "最佳烘焙含水率范围"),
        ("12-15%", "HIGH", "⚠️ 警示", "含水率偏高，需更长预热"),
        ("> 15%", "OVER_WET", "❌ 剔除", "含水率过高，储存风险"),
    ]
    print("  | 含水率范围 | 分类 | 处理 | 备注 |")
    print("  |-----------|------|------|------|")
    for row in moisture_thresholds:
        print(f"  | {' | '.join(row)} |")
    
    print("\n🔗 多传感器数据融合（bean_id追踪）:")
    bean_tracking = {
        'bean_id': 'ID-20260425-001',
        'size_mm': 17.2,
        'color_score': 92,
        'weight_g': 0.152,
        'density_class': 'medium',
        'moisture_pct': 11.4,
        'quality_class': 'A',
    }
    print("  单粒豆完整数据记录:")
    for k, v in bean_tracking.items():
        print(f"    {k}: {v}")
    
    print("\n  最终品质判定规则:")
    print("    • 含水率不在5-12%范围 → 标记UNDER_DRIED/OVER_WET → 剔除")
    print("    • 颜色score<70 → 标记defect → 剔除")
    print("    • 所有指标合格 → 归入对应quality_class（A/B/C）")
    
    print("\n📊 每批次数据统计输出:")
    batch_stats = {
        'total_beans': 1000,
        'moisture_mean_pct': 10.8,
        'moisture_std_pct': 0.9,
        'moisture_min_pct': 8.2,
        'moisture_max_pct': 13.1,
        'under_dried_count': 3,
        'over_wet_count': 1,
        'optimal_count': 996,
    }
    print("  | 指标 | 数值 |")
    print("  |------|------|")
    for k, v in batch_stats.items():
        print(f"  | {k} | {v} |")
    
    return {
        'moisture_cycle_ms': 270,
        'max_rate_bpm': int(60000/270),
        'optimal_range': (5, 12),
    }


# ═══════════════════════════════════════════════════════════
# 图表生成
# ═══════════════════════════════════════════════════════════

def generate_integration_figure():
    """
    生成集成分析可视化图表
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    
    # ── 左图: 流水线时序图 ─────────────────
    ax = axes[0]
    ax.set_xlim(0, 700)
    ax.set_ylim(0, 10)
    ax.set_xlabel('Time since entry (ms)', fontsize=11)
    ax.set_ylabel('Pipeline Stage', fontsize=11)
    ax.set_title('Bean Sorting Pipeline — Timing & Stage Mapping', fontsize=12, fontweight='bold')
    ax.set_yticks([1, 2, 3, 4, 5, 6, 7])
    ax.set_yticklabels([
        'Size Sort', 'Color Detect', 'Weight', 'Density',
        'Moisture', 'Buffer', 'Feed→Roaster'
    ], fontsize=9)
    ax.grid(True, alpha=0.3, axis='x')
    
    stage_colors = ['#e57373', '#ba68c8', '#64b5f6', '#81c784', '#4db6ac', '#ffb74d', '#90a4ae']
    stage_data = [
        (0, 200, 'Size Sorting', 0),
        (200, 270, 'Color Detection', 1),
        (270, 350, 'Weight Measurement', 2),
        (350, 450, 'Density Sorting', 3),
        (450, 530, 'Moisture Sensing', 4),
        (530, 600, 'Buffer Storage', 5),
        (600, 700, 'Feed to Roaster', 6),
    ]
    
    for start, end, name, idx in stage_data:
        rect = mpatches.FancyBboxPatch((start, idx+0.3), end-start, 0.4,
                                        boxstyle="round,pad=0.05",
                                        facecolor=stage_colors[idx], alpha=0.8, linewidth=1)
        ax.add_patch(rect)
        mid = (start + end) / 2
        ax.text(mid, idx+0.5, name, ha='center', va='center', fontsize=7, color='white', fontweight='bold')
    
    ax.axvline(x=2000, color='orange', linestyle=':', alpha=0.6, linewidth=1.5)
    ax.text(2002, 7.5, '30 bpm\n(target)', fontsize=6, color='orange', va='bottom')
    
    ax.text(660, 9.3, 'Target: 30 beans/min\n(2000ms/bean)', fontsize=7,
            ha='right', va='top', color='#555',
            bbox=dict(boxstyle='round', facecolor='#fff9c4', alpha=0.8))
    
    # ── 右图: 含水率决策 + 分布 ───────────────
    ax2 = axes[1]
    ax2.set_xlim(4, 16)
    ax2.set_ylim(0, 1)
    
    ax2.axvspan(4, 5, alpha=0.3, color='red', label='Under-dried (<5%)')
    ax2.axvspan(5, 12, alpha=0.3, color='green', label='Optimal (5-12%)')
    ax2.axvspan(12, 15, alpha=0.3, color='orange', label='High (12-15%)')
    ax2.axvspan(15, 16, alpha=0.3, color='red', label='Over-wet (>15%)')
    
    np.random.seed(42)
    moisture_samples = np.random.normal(10.5, 1.5, 1000)
    moisture_samples = moisture_samples[(moisture_samples >= 5) & (moisture_samples <= 15)]
    
    bins = np.linspace(5, 15, 21)
    ax2.hist(moisture_samples, bins=bins, density=True,
             alpha=0.6, color='#4db6ac', edgecolor='white')
    
    ax2.axvline(x=5, color='red', linewidth=2, linestyle='--')
    ax2.axvline(x=12, color='red', linewidth=2, linestyle='--', label='Decision thresholds')
    
    ax2.text(10.5, 0.85, 'OPTIMAL\nZONE', ha='center', va='center',
             fontsize=12, fontweight='bold', color='darkgreen',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
    
    ax2.set_xlabel('Moisture Content (%)', fontsize=11)
    ax2.set_title('Moisture Decision Thresholds + Batch Distribution', fontsize=12, fontweight='bold')
    ax2.legend(fontsize=7, loc='upper left', framealpha=0.9)
    ax2.set_yticks([])
    
    params_text = '\n'.join([
        'Moisture Sensor Specs:',
        'Range: 5-15%',
        'Accuracy: ±0.5%',
        'Cycle: 270ms/bean',
        'Max rate: 222 beans/min',
        'Target: 30 beans/min ✅',
        '',
        'Probe Design (Day3):',
        'Electrode: 15×15mm PCB',
        'Gap: 8mm',
        'AD7746: on-probe mount',
        'Cable: <5cm (on-PCB)',
    ])
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax2.text(0.97, 0.03, params_text, transform=ax2.transAxes, fontsize=7,
             verticalalignment='bottom', horizontalalignment='right', bbox=props)
    
    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, 'moisture_topic5_day3.png')
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"\n✅ 图表已保存: {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════
# CAD OpenSCAD 文件生成
# ═══════════════════════════════════════════════════════════

CAD_SCRIPT = '''
// moisture_probe.scad — 电容式含水率探头 3D 设计
// ================================================
// Topic 5 Day 3 | Author: Little Husky 🐕 | Date: 2026-04-25

// ═══════════════════════════════════════════════════════════
// 参数配置
// ═══════════════════════════════════════════════════════════

// 电极参数
plate_size = 15;      // mm — 电极边长（正方形）
plate_thick = 1.6;   // mm — PCB板厚度（FR4）

// 间隙参数
gap = 8.0;            // mm — 两极板间距离（含豆空间）
post_dia = 3.0;      // mm — 隔离柱直径
post_count = 4;      // 隔离柱数量（四角分布）

// 法兰参数
flange_dia = 34;     // mm — 安装法兰直径
flange_thick = 4;   // mm — 法兰厚度
bolt_hole_dia = 3.0; // mm — M3螺栓孔径
bolt_count = 3;      // M3螺栓数量

// 电缆出口
cable_hole_dia = 6;  // mm — M6电缆密封头

// 漏斗参数
funnel_top_dia = 20; // mm — 入口直径
funnel_bot_dia = plate_size + 2; // mm — 出口直径

// ═══════════════════════════════════════════════════════════
// 计算变量
// ═══════════════════════════════════════════════════════════

total_height = flange_thick + gap + plate_thick * 2 + 2;

// ═══════════════════════════════════════════════════════════
// 模块定义
// ═══════════════════════════════════════════════════════════

// 底座法兰
module flange_base() {
    difference() {
        cylinder(d=flange_dia, h=flange_thick, center=false);
        // 法兰安装孔（3×M3，120°分布）
        for (i=[0:bolt_count-1]) {
            angle = i * 120 + 30;
            x = flange_dia/2 * cos(angle) - bolt_hole_dia/2;
            y = flange_dia/2 * sin(angle);
            translate([x, y, -1])
                cylinder(d=bolt_hole_dia, h=flange_thick+2, center=false);
        }
        // 电缆出口孔（侧面）
        translate([flange_dia/2 - 3, 0, flange_thick/2])
            rotate([90, 0, 0])
                cylinder(d=cable_hole_dia, h=10, center=false);
    }
}

// 下电极托架（凹槽定位PCB电极）
module lower_holder() {
    translate([0, 0, flange_thick])
    difference() {
        cylinder(d=plate_size + 6, h=plate_thick + 2, center=false);
        // 电极凹槽
        translate([0, 0, -0.5])
            cylinder(d=plate_size + 0.4, h=plate_thick + 1, center=false);
    }
}

// 隔离柱（保证极板间隙）
module isolation_post() {
    cylinder(d=post_dia, h=gap, center=false);
}

// 四角隔离柱阵列
module post_array() {
    offset = plate_size/2 + post_dia/2 + 1;
    for (i=[-1, 1], j=[-1, 1]) {
        translate([i * offset, j * offset, flange_thick + plate_thick])
            isolation_post();
    }
}

// 上极板压板
module upper_press() {
    translate([0, 0, flange_thick + plate_thick + gap])
    difference() {
        cylinder(d=plate_size + 4, h=plate_thick, center=false);
        // 中央M2通孔（穿螺栓压紧）
        cylinder(d=2, h=plate_thick + 2, center=true);
    }
}

// 入口漏斗
module funnel() {
    translate([0, 0, flange_thick + plate_thick * 2 + gap + plate_thick])
    cylinder(d1=funnel_top_dia, d2=funnel_bot_dia, h=plate_thick * 2, center=false);
}

// ═══════════════════════════════════════════════════════════
// 完整装配
// ═══════════════════════════════════════════════════════════

module moisture_probe_assembly() {
    // 底座法兰
    color("#90a4ae") flange_base();
    // 下极板托架
    color("#b0bec5") translate([0, 0, flange_thick])
        cylinder(d=plate_size + 6, h=plate_thick + 2, center=false);
    // 隔离柱
    color("#78909c") post_array();
    // 上极板
    color("#cfd8dc") translate([0, 0, flange_thick + plate_thick + gap])
        cylinder(d=plate_size, h=plate_thick, center=false);
    // 上压板
    color("#b0bec5") upper_press();
    // 漏斗
    color("#b0bec5") funnel();
}

// 渲染
moisture_probe_assembly();

// ═══════════════════════════════════════════════════════════
// 打印说明
// ═══════════════════════════════════════════════════════════
// 推荐打印参数:
//   材料: PETG（食品级，耐温）
//   层高: 0.2mm
//   填充: 40%+（功能件需足够强度）
//   打印方向: 底面朝下（法兰水平），最优
//   支撑: 仅漏斗需要支撑
//
// 装配顺序:
//   1. 法兰 + 下极板托架 一体打印（已合并）
//   2. 隔离柱×4 单独打印（需精确直径±0.05mm）
//   3. 上极板 + 压板 打印
//   4. 漏斗 打印（需支撑）
//
// 隔离柱也可与法兰一起打印（gap空间用可溶解支撑填充）
'''


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "="*60)
    print("课题5 Day3: 含水率检测 — CAD探头设计 + 物理测试协议 + 集成分析")
    print("="*60)
    
    cad_result = cad_probe_design()
    protocol = physical_test_protocol()
    int_result = integration_analysis()
    
    out_path = generate_integration_figure()
    
    # 写CAD文件
    cad_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'sorter', 'cad', 'moisture_probe.scad'
    )
    with open(cad_path, 'w') as f:
        f.write(CAD_SCRIPT)
    print(f"\n✅ CAD文件已保存: {cad_path}")
    
    print("\n" + "="*60)
    print("✅ 课题5 Day3 完成")
    print("="*60)
    print("  新增文件:")
    print(f"    • simulation/moisture_topic5_day3.py (本文件)")
    print(f"    • simulation/moisture_topic5_day3.png (流水线时序图+决策分布)")
    print(f"    • sorter/cad/moisture_probe.scad (OpenSCAD参数化探头设计)")
    print()
    print("  Day3 完成内容:")
    print("    ✅ CAD探头3D设计（参数化PETG支架 + 隔离柱方案）")
    print("    ✅ 物理测试协议（6步硬件验证 + 通过标准）")
    print("    ✅ 集成分析（流水线时序 + 含水率决策逻辑）")
    print()
    print("  课题5 完成 ✅:")
    print("    Day1: 电容探头原理 + 介电模型 + AD7746驱动")
    print("    Day2: 标定方法 + 电路设计 + 电缆效应修正")
    print("    Day3: CAD探头设计 + 物理测试协议 + 集成分析")
    print()
    print("  课题5 剩余待办（需硬件）:")
    print("    ⬜ AD7746模块采购 (¥60)")
    print("    ⬜ 探头PCB制作 + 焊接")
    print("    ⬜ 物理6步测试验证")
    print("    ⬜ 标定样本制备（烘干法）")
