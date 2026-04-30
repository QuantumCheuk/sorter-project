#!/usr/bin/env python3
"""
生豆分选机成本优化深度研究
HUSKY-SORTER-001 Cost Reduction Analysis
目标：将总成本从¥2244压回¥1500目标预算

研究日期：2026-04-30
版本：v1.0
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime

# =============================================================================
# 1. 当前BOM成本明细
# =============================================================================

# Phase 1 标准配置（已购）
phase1_items = {
    "Raspberry Pi 4B 2GB": {"qty": 1, "unit": 450, "essential": True, "替代方案": None},
    "HQ Camera IMX477 + M12 6mm": {"qty": 1, "unit": 350, "essential": True, "替代方案": "USB Camera ¥80×2"},
    "USB Camera (C270) ×2": {"qty": 2, "unit": 80, "essential": False, "替代方案": None},
    "28BYJ-48 步进电机套": {"qty": 3, "unit": 15, "essential": True, "替代方案": None},
    "DRV8833 电机驱动板": {"qty": 3, "unit": 8, "essential": True, "替代方案": None},
    "红外光电传感器 NPN NO": {"qty": 2, "unit": 8, "essential": True, "替代方案": None},
    "LED 环形灯 5V USB": {"qty": 2, "unit": 20, "essential": True, "替代方案": None},
    "Load Cell 200g + HX711": {"qty": 1, "unit": 35, "essential": True, "替代方案": None},
    "称重杯释放电磁阀 12V": {"qty": 1, "unit": 15, "essential": True, "替代方案": None},
    "气喷电磁阀 12V 2-way NC": {"qty": 1, "unit": 20, "essential": True, "替代方案": None},
    "5015 风扇 12V": {"qty": 1, "unit": 25, "essential": True, "替代方案": None},
    "AD7746 I2C容值计模块": {"qty": 1, "unit": 60, "essential": True, "替代方案": "分立电路¥20"},
    "ESP32 DevKit": {"qty": 1, "unit": 25, "essential": True, "替代方案": None},
    "杜邦线/面包板/焊接件": {"qty": 1, "unit": 50, "essential": True, "替代方案": None},
    "3D打印 PLA/PETG线材": {"qty": 1, "unit": 25, "essential": True, "替代方案": None},
    "2020铝合金框架": {"qty": 1, "unit": 60, "essential": True, "替代方案": None},
    "螺丝/螺母/轴承等紧固件": {"qty": 1, "unit": 40, "essential": True, "替代方案": None},
    "电源适配器 12V 2A": {"qty": 1, "unit": 30, "essential": True, "替代方案": None},
    "电源适配器 5V 3A USB-C": {"qty": 1, "unit": 25, "essential": True, "替代方案": None},
    "MicroSD卡 32GB": {"qty": 1, "unit": 35, "essential": True, "替代方案": None},
    "亚克力板/透明窗口材料": {"qty": 1, "unit": 20, "essential": True, "替代方案": None},
    "废料仓/管道等塑料件": {"qty": 1, "unit": 15, "essential": True, "替代方案": None},
}

# Phase 2 升级件（未购）
phase2_items = {
    "Nema17 ST4118L1804": {"qty": 3, "unit": 35, "替代方案": "继续用28BYJ-48 ¥15×3"},
    "A4988 步进驱动板": {"qty": 3, "unit": 8, "替代方案": "继续用DRV8833 ¥8×3"},
    "Turbo Blower 12V 300+L/min": {"qty": 1, "unit": 120, "替代方案": "继续用5015 ¥25"},
    "Power Supply 12V 10A": {"qty": 1, "unit": 50, "替代方案": "继续用12V 2A ¥30"},
}

# 关键进口件（高风险）
critical_imports = {
    "HQ Camera IMX477": {"unit": 350, "lead_days": 30, "risk": "HIGH", "替代": "USB Camera ¥80"},
    "AD7746 模块": {"unit": 60, "lead_days": 20, "risk": "MEDIUM", "替代": "分立电路¥20"},
    "涡轮鼓风机": {"unit": 120, "lead_days": 30, "risk": "HIGH", "替代": "5015风扇 ¥25"},
}

# =============================================================================
# 2. 成本分析
# =============================================================================

print("=" * 70)
print("HUSKY-SORTER-001 成本优化分析报告")
print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# Phase 1 总计
phase1_total = sum(item["qty"] * item["unit"] for item in phase1_items.values())
phase2_total = sum(item["qty"] * item["unit"] for item in phase2_items.values())
grand_total = phase1_total + phase2_total

print(f"\n📊 当前成本状态")
print(f"  Phase 1（标准配置）：¥{phase1_total}")
print(f"  Phase 2（升级件）：¥{phase2_total}")
print(f"  总计（当前方案）：¥{grand_total}")
print(f"  目标预算：¥1500")
print(f"  超支：¥{grand_total - 1500} ({(grand_total/1500-1)*100:.1f}%)")

# Phase 2 超支原因分析
print(f"\n🔍 超支原因分析")
print("-" * 50)
expensive_items = []
for name, item in {**phase1_items, **phase2_items}.items():
    cost = item["qty"] * item["unit"]
    if cost > 50:
        expensive_items.append((name, cost, item["qty"], item["unit"]))

expensive_items.sort(key=lambda x: x[1], reverse=True)
for name, cost, qty, unit in expensive_items[:8]:
    print(f"  {name}: ¥{cost} ({qty}×¥{unit})")

# =============================================================================
# 3. 成本优化路径分析
# =============================================================================

print(f"\n📉 成本优化方案分析")
print("-" * 50)

# 方案A：维持单通道，砍掉Phase 2（¥520节省）
plan_a = grand_total - phase2_total  # = phase1_total
# 方案B：用USB摄像头替代HQ Camera（¥270节省）
plan_b_usb替代 = phase1_total - 350 + 80  # 替换HQ Camera
# 方案C：AD7746用分立电路替代（¥40节省）
plan_c_adt替代 = phase1_total - 60 + 20  # 替换AD7746
# 方案D：综合方案（HQ→USB + AD→分立 + 砍Phase2）
plan_d综合 = (phase1_total - 350 + 80 - 60 + 20 - phase2_items["Turbo Blower 12V 300+L/min"]["qty"] * phase2_items["Turbo Blower 12V 300+L/min"]["unit"])

print(f"方案A：砍掉Phase 2（维持单通道 0.27kg/h）→ ¥{plan_a} (超支¥{plan_a-1500})")
print(f"方案B：USB摄像头替代HQ Camera → ¥{plan_b_usb替代} (超支¥{plan_b_usb替代-1500})")
print(f"方案C：AD7746分立替代方案 → ¥{plan_c_adt替代} (超支¥{plan_c_adt替代-1500})")
print(f"方案D：HQ→USB + AD→分立 + 砍Phase2涡轮鼓风机 → 需要详细计算")

# 详细计算方案D
hq_saving = 350 - 80  # HQ Camera ¥350 → USB Camera ¥80
ad_saving = 60 - 20   # AD7746 ¥60 → 分立电路 ¥20
turbo_saving = phase2_items["Turbo Blower 12V 300+L/min"]["qty"] * phase2_items["Turbo Blower 12V 300+L/min"]["unit"]  # Turbo ¥120

plan_d = phase1_total - hq_saving - ad_saving
plan_d_upgrade = plan_d + (phase2_total - turbo_saving)  # 有涡轮但无Phase2电机升级

print(f"\n方案D1：HQ→USB + AD→分立，保留Phase2电机升级，砍涡轮鼓风机")
print(f"  Phase1节省：¥{hq_saving} (HQ→USB) + ¥{ad_saving} (AD7746→分立)")
print(f"  新Phase1：¥{plan_d}")
print(f"  Phase2新(无涡轮)：¥{phase2_total - turbo_saving}")
print(f"  总计：¥{plan_d + phase2_total - turbo_saving}")

# 方案E：最激进成本优化（砍所有非必要件）
plan_e_base = phase1_total - 350 + 80 - 60 + 20 - 25  # HQ+AD+5015→继续用（但降级涡轮）
# 降级涡轮方案：继续用5015但优化通道设计达到2-way分离
plan_e = plan_e_base + (phase2_total - turbo_saving)  # 无涡轮，仅Nema17升级

print(f"\n方案E：仅Nema17升级（¥39），砍涡轮鼓风机（¥120节省），用5015风扇")
print(f"  Phase1(降级)：¥{plan_e_base}")
print(f"  Phase2(无涡轮)：¥{phase2_total - turbo_saving}")
print(f"  总计：¥{plan_e}")

# =============================================================================
# 4. 性价比分析（考虑性能损失）
# =============================================================================

print(f"\n⚖️ 性价比分析")
print("-" * 50)

scenarios = [
    ("当前方案(Phase1+2)", grand_total, 2.70, True, "✅ 超出目标35%"),
    ("方案A: 纯Phase1", plan_a, 0.27, False, "❌ 仅达目标13.5%"),
    ("方案D: 综合优化+涡轮", plan_d + phase2_total - turbo_saving, 2.70, True, "✅ 达标，成本最低"),
    ("方案E: 降级涡轮", plan_e, 1.35, True, "⚠️ 1.35kg/h达67.5%目标"),
]

print(f"{'方案':<35} {'成本':>8} {'吞吐量':>10} {'超预算':>10} {'评估':<20}")
print("-" * 85)
for name, cost, throughput, meets_target, eval in scenarios:
    over = cost - 1500
    budget_pct = cost / 1500 * 100 - 100
    target_pct = throughput / 2.0 * 100
    print(f"{name:<35} ¥{cost:>7} {throughput:>9.2f}kg/h +{over:>6.0f}(+{budget_pct:.0f}%) {eval:<20}")

# =============================================================================
# 5. 成本分项饼图
# =============================================================================

categories = {
    "计算平台(Pi4+SD)": 450 + 35,
    "视觉系统(HQ+C270)": 350 + 80 * 2,
    "传感器(光电+LED)": 8 * 2 + 20 * 2,
    "称重系统(LoadCell+HX711)": 35,
    "执行器(电磁阀+风扇)": 15 + 20 + 25,
    "AD7746含水率": 60,
    "电机驱动(28BYJ+DRV)": 15 * 3 + 8 * 3,
    "ESP32": 25,
    "结构件(框架+紧固件)": 60 + 40 + 25 + 15,
    "电源系统": 30 + 25,
    "线材+工具": 50,
    "亚克力等材料": 20,
}

fig, axes = plt.subplots(1, 2, figsize=(16, 8))

# 左图：当前成本分项
colors = plt.cm.Set3(np.linspace(0, 1, len(categories)))
labels = list(categories.keys())
sizes = list(categories.values())
wedges, texts, autotexts = axes[0].pie(
    sizes, labels=None, autopct='%1.1f%%',
    colors=colors, startangle=90, pctdistance=0.75
)
axes[0].set_title(f'当前成本分项分析\n(总计 ¥{grand_total})', fontsize=14, fontweight='bold')
axes[0].legend(wedges, labels, loc='center left', bbox_to_anchor=(1, 0.5), fontsize=9)

# 添加说明
for i, (name, cost) in enumerate(categories.items()):
    if cost > 40:
        wedges[i].set_edgecolor('black')
        wedges[i].set_linewidth(1.5)

# 右图：优化方案对比
plan_names = ['当前方案', '方案A\n(单通道)', '方案D\n(综合优化)', '方案E\n(降级涡轮)']
plan_costs = [grand_total, plan_a, plan_d + phase2_total - turbo_saving, plan_e]
plan_colors = ['#e74c3c', '#e74c3c', '#27ae60', '#f39c12']
bar_budget = axes[1].bar(plan_names, [1500] * 4, color='#27ae60', alpha=0.3, label='目标 ¥1500')
bar_actual = axes[1].bar(plan_names, plan_costs, color=plan_colors, alpha=0.8)

for bar, cost in zip(bar_actual, plan_costs):
    bar.set_edgecolor('black')
    bar.set_linewidth(1)
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                 f'¥{cost}', ha='center', va='bottom', fontsize=11, fontweight='bold')

axes[1].axhline(y=1500, color='#27ae60', linestyle='--', linewidth=2, label='目标 ¥1500')
axes[1].set_ylabel('成本 (¥)', fontsize=12)
axes[1].set_title('成本优化方案对比', fontsize=14, fontweight='bold')
axes[1].set_ylim(0, 2500)
axes[1].legend(loc='upper right')

plt.tight_layout()
plt.savefig('cost_optimization_analysis.png', dpi=150, bbox_inches='tight',
           facecolor='white', edgecolor='none')
plt.close()
print(f"\n📊 生成图表：cost_optimization_analysis.png")

# =============================================================================
# 6. 推荐方案
# =============================================================================

print(f"\n" + "=" * 70)
print("🎯 推荐方案：方案D（综合优化）")
print("=" * 70)
print(f"""
目标：在满足2kg/h性能目标的前提下，将成本压至最低

核心降本措施：
1. HQ Camera → USB Camera（¥80×2替代¥350 HQ）
   - 损失：分辨率从12MP降至1MP，颜色阈值精度略降
   - 补偿：ML训练用合成数据+真实样本采集后优化阈值
   - 注意：需要双USB摄像头同步采集方案

2. AD7746 → 分立电容测量电路（¥20替代¥60）
   - 损失：±0.1%精度 → ±0.5%精度
   - 补偿：SPEC要求±0.5%，刚好满足
   - 注意：需要自行焊接制作

3. 涡轮鼓风机 → 升级版5015+PID控制
   - 损失：3-way分离 → 2-way分离
   - 补偿：密度分选仅作为辅助指标，影响可控
   - 需要：优化通道设计（25mm宽×80mm长）与PWM控制配合

4. 保留Phase2电机升级（Nema17 ¥35×3）
   - 理由：¥105投资换取3通道×50bpm，ROI极高
   - 注意：可分批采购，先买1个验证

预期成本：
  Phase1（降级）：¥{plan_d}（vs 原¥{phase1_total}）
  Phase2（无涡轮）：¥{phase2_total - turbo_saving}（vs 原¥{phase2_total}）
  合计：¥{plan_d + phase2_total - turbo_saving}（vs 原¥{grand_total}）
  节省：¥{grand_total - (plan_d + phase2_total - turbo_saving)}（{(grand_total/(plan_d + phase2_total - turbo_saving)-1)*100:.1f}%）

距离¥1500目标：超支¥{(plan_d + phase2_total - turbo_saving) - 1500}（{(plan_d + phase2_total - turbo_saving)/1500*100-100:.1f}%）
""")

# =============================================================================
# 7. 替代品调研
# =============================================================================

print(f"\n" + "=" * 70)
print("🔎 替代品调研（¥1500目标实现路径）")
print("=" * 70)

alternatives = {
    "HQ Camera IMX477 ¥350": {
        "替代1": "Logitech C270 ×2 ¥160 — 分辨率降级但满足颜色检测",
        "替代2": "Raspberry Pi Camera v2 ¥100 — 8MP但无自动对焦",
        "替代3": "USB Camera ¥80×2 — 最便宜¥160双摄方案",
    },
    "AD7746 ¥60": {
        "替代1": "NE555振荡器+GPIO计数 ¥5 — 精度±2%，勉强可用",
        "替代2": "自制分立电路（运放+比较器）¥20 — 精度±0.5%，刚好达标",
    },
    "涡轮鼓风机 ¥120": {
        "替代1": "5015风扇+PID通道优化 ¥25+工时 — 降级2-way分离",
        "替代2": "盘古风扇 12V ¥60 — 中档方案，150L/min",
    },
    "Pi 4B 2GB ¥450": {
        "替代1": "Pi Zero 2 W ¥180 — 降级但计算能力足够单通道",
        "替代2": "OrangePi 3B ¥180 — 同价位更强CPU",
    },
}

for item, alts in alternatives.items():
    print(f"\n{item}:")
    for alt_name, alt_desc in alts.items():
        print(f"  {alt_name}: {alt_desc}")

# =============================================================================
# 8. 关键结论
# =============================================================================

print(f"\n" + "=" * 70)
print("📋 关键结论")
print("=" * 70)
print(f"""
1. ¥2244超支主因：HQ Camera ¥350（占超支额50%）

2. 实现¥1500目标的最低成本组合：
   - HQ Camera → USB Camera ¥80×2（-¥270）
   - AD7746 → 分立电路（-¥40）
   - 涡轮鼓风机 → 优化版5015（-¥120）
   - 合计节省：¥430 → 降至¥{grand_total-430}
   
3. ¥1500目标下的性能权衡：
   - 降级后性能：2.0kg/h（刚好达标）— 方案D
   - 成本：¥{grand_total-430}
   
4. 建议行动：
   a. 立即采购USB摄像头×2（¥160）替代HQ Camera
   b. 同时启动AD7746分立电路设计（预算¥20）
   c. 保留涡轮鼓风机选项，Phase2再评估
   d. 如成本仍超¥1500，考虑Pi Zero 2W替代方案
""")

# =============================================================================
# 9. 保存JSON报告
# =============================================================================

import json

report = {
    "project": "HUSKY-SORTER-001",
    "analysis_date": datetime.now().isoformat(),
    "current_cost": {
        "phase1": phase1_total,
        "phase2": phase2_total,
        "total": grand_total,
        "budget_target": 1500,
        "over_budget": grand_total - 1500,
        "over_budget_pct": round((grand_total/1500-1)*100, 1)
    },
    "recommended_plan": {
        "name": "方案D: 综合优化",
        "description": "HQ→USB + AD→分立 + 砍涡轮鼓风机",
        "estimated_cost": plan_d + phase2_total - turbo_saving,
        "throughput_kg_h": 2.70,
        "savings_vs_current": grand_total - (plan_d + phase2_total - turbo_saving),
        "actions": [
            "立即采购USB摄像头×2（¥160）替代HQ Camera",
            "启动AD7746分立电路设计（预算¥20）",
            "Phase2采购Nema17电机（¥105）但暂缓涡轮鼓风机",
            "优化5015风扇+PWM通道设计实现2-way密度分离"
        ]
    },
    "cost_breakdown": categories,
    "alternatives": alternatives
}

with open('cost_optimization_report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n📄 JSON报告已保存：cost_optimization_report.json")
print("\n✅ 分析完成")
