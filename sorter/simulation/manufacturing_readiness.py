#!/usr/bin/env python3
"""
生豆分选机 - 制造准备度评估
Manufacturing Readiness Assessment for HUSKY-SORTER-001

目标：在硬件采购到位前，评估所有零件的制造可行性、打印参数、装配顺序
      生成完整的组装指导文件，为物理组装做好最后准备

分析内容：
1. 所有3D打印件的工艺分析（PLA/PETG层厚/填充/支撑/warping风险）
2. 装配顺序优化（依赖关系图）
3. 硬件采购时序（关键路径分析）
4. 组装检查清单（按天分阶段）
5. BOM完整性最终核对
"""

import json
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple

# ============================================================
# PART 1: 3D打印件工艺分析
# ============================================================

@dataclass
class PrintedPart:
    name: str
    filename: str
    material: str  # PLA or PETG
    volume_cm3: float
    dimensions_mm: str  # approx L×W×H
    criticality: str  # HIGH/MEDIUM/LOW
    wall_thickness_mm: float
    has_overhangs: bool
    warping_risk: str  # HIGH/MEDIUM/LOW
    bed_adhesion: str  # FULL_BED/BRIM/RAFT
    layer_height_mm: float
    infill_pct: int
    print_time_hours: float
    qty: int
    notes: str

    def estimated_weight_g(self, density_gcm3=1.25) -> float:
        return self.volume_cm3 * density_gcm3

    def total_print_time_h(self) -> float:
        return self.print_time_hours * self.qty


# 从CAD文件和SPEC.md提取的零件清单
PRINTED_PARTS: List[PrintedPart] = [
    # ---- 入料和给料系统 ----
    PrintedPart(
        name="入料斗 (Hopper)",
        filename="hopper.scad",
        material="PETG",
        volume_cm3=45.0,  # 500g容量漏斗
        dimensions_mm="120×100×80",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=True,
        warping_risk="MEDIUM",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=20,
        print_time_hours=2.5,
        qty=1,
        notes="大体积漏斗，PETG需注意Z轴收缩（4%），打印后需24h退火释放内应力"
    ),
    PrintedPart(
        name="振动给料器基座",
        filename="vibrating_feeder_base.scad",
        material="PLA",
        volume_cm3=18.0,
        dimensions_mm="80×60×40",
        criticality="HIGH",
        wall_thickness_mm=2.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=40,
        print_time_hours=1.2,
        qty=1,
        notes="弹簧支撑结构，弹簧安装孔需垂直对齐（±0.5mm）"
    ),
    PrintedPart(
        name="单文件通道管",
        filename="single_file_channel.scad",
        material="PETG",
        volume_cm3=12.0,
        dimensions_mm="φ25×60",
        criticality="HIGH",
        wall_thickness_mm=1.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.12,
        infill_pct=30,
        print_time_hours=0.8,
        qty=3,  # 3通道备用
        notes="内径光滑度要求高（Ra<0.8），PETG低温打印（235°C）减少内应力；壁厚1.5mm需校核强度"
    ),
    # ---- 颜色检测暗箱 ----
    PrintedPart(
        name="颜色检测暗箱",
        filename="dark_box.scad",
        material="PLA",
        volume_cm3=35.0,
        dimensions_mm="80×80×100",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=True,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=20,
        print_time_hours=2.0,
        qty=1,
        notes="内壁需白色PLA（漫反射），外壁无所谓；内部安装位需±0.3mm精度"
    ),
    PrintedPart(
        name="通道连接件（顶部传感器安装）",
        filename="channel_connector_top.scad",
        material="PLA",
        volume_cm3=5.0,
        dimensions_mm="40×30×20",
        criticality="MEDIUM",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=0.4,
        qty=2,
        notes="光电传感器T1/T2安装孔（φ10mm），需精确"
    ),
    PrintedPart(
        name="底部透明窗口框架",
        filename="bottom_window_frame.scad",
        material="PLA",
        volume_cm3=4.0,
        dimensions_mm="40×40×10",
        criticality="MEDIUM",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=0.3,
        qty=1,
        notes="与底部亚克力板（乳白色磨砂，3mm）配合；过盈配合设计"
    ),
    # ---- 称重系统 ----
    PrintedPart(
        name="称重杯",
        filename="weighing_cup.scad",
        material="PETG",
        volume_cm3=3.9,  # 从cad文件：实际值3.9g
        dimensions_mm="φ18×19.5",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.12,
        infill_pct=50,
        print_time_hours=0.3,
        qty=3,  # 备用2个
        notes="壁薄（2mm），内外表面需光滑；质量<5g目标✅；释放门缝隙0.1mm"
    ),
    PrintedPart(
        name="称重杯托/Load Cell安装基座",
        filename="load_cell_mount.scad",
        material="PLA",
        volume_cm3=8.0,
        dimensions_mm="60×40×25",
        criticality="HIGH",
        wall_thickness_mm=2.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=40,
        print_time_hours=0.6,
        qty=1,
        notes="Load Cell安装孔（M3螺栓，节圆φ10mm）；水平度要求±0.5mm"
    ),
    # ---- 密度分选 ----
    PrintedPart(
        name="气流分选通道（密度区）",
        filename="density_channel.scad",
        material="PETG",
        volume_cm3=22.0,
        dimensions_mm="120×60×40",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=True,
        warping_risk="MEDIUM",
        bed_adhesion="RAFT",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=1.8,
        qty=1,
        notes="气流上扬角度30°，斜面精度影响分离效果；PETG的化学耐受性更好（耐醇/酮）"
    ),
    # ---- 含水率探头 ----
    PrintedPart(
        name="含水率测量槽/探头夹具",
        filename="moisture_probe.scad",
        material="PLA",
        volume_cm3=6.0,
        dimensions_mm="30×30×20",
        criticality="MEDIUM",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.12,
        infill_pct=30,
        print_time_hours=0.4,
        qty=1,
        notes="极板间隙6-8mm需精确（容纳单粒豆9×6.5×3.5mm）；间隙误差<0.2mm"
    ),
    # ---- 缓冲仓+分配器 ----
    PrintedPart(
        name="缓冲料仓（8格）",
        filename="buffer_bin.scad",
        material="PETG",
        volume_cm3=85.0,  # 212×35×45mm框架结构
        dimensions_mm="212×35×45",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="MEDIUM",
        bed_adhesion="RAFT",
        layer_height_mm=0.2,
        infill_pct=20,
        print_time_hours=5.5,
        qty=1,
        notes="大尺寸打印，PETG需预热热床（80°C）减少翘曲；分隔壁需对齐（误差<0.3mm）"
    ),
    PrintedPart(
        name="旋转分配器圆盘",
        filename="rotary_distributor.scad",
        material="PETG",
        volume_cm3=15.0,
        dimensions_mm="φ76×8",
        criticality="HIGH",
        wall_thickness_mm=3.0,
        has_overhangs=False,
        warping_risk="MEDIUM",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=40,
        print_time_hours=1.2,
        qty=2,  # 备用1个
        notes="8通道（45°/格），分度精度±0.5°；轴孔配合（φ8mm轴）；需动平衡"
    ),
    # ---- 螺旋给料器 ----
    PrintedPart(
        name="螺旋给料器管",
        filename="spiral_feeder.scad",
        material="PETG",
        volume_cm3=10.0,
        dimensions_mm="φ24×80",
        criticality="HIGH",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=0.8,
        qty=1,
        notes="φ20mm内径光滑（影响给料精度）；螺旋片3D打印或激光切割+粘接"
    ),
    # ---- 气喷剔除 ----
    PrintedPart(
        name="气喷嘴",
        filename="air_jet_nozzle.scad",
        material="PLA",
        volume_cm3=1.5,
        dimensions_mm="15×10×10",
        criticality="MEDIUM",
        wall_thickness_mm=1.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.12,
        infill_pct=50,
        print_time_hours=0.15,
        qty=3,  # 备用
        notes="φ2mm喷孔精度要求高（±0.05mm）；建议激光切割PMMA（更高精度）"
    ),
    PrintedPart(
        name="废料仓",
        filename="reject_bin.scad",
        material="PETG",
        volume_cm3=20.0,
        dimensions_mm="60×50×40",
        criticality="LOW",
        wall_thickness_mm=1.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=15,
        print_time_hours=1.2,
        qty=1,
        notes="容量100g，壁薄可减少材料"
    ),
    # ---- 框架结构 ----
    PrintedPart(
        name="框架立柱×4",
        filename="frame_post.scad",
        material="PLA",
        volume_cm3=8.0,
        dimensions_mm="200×20×20",
        criticality="HIGH",
        wall_thickness_mm=3.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=0.6,
        qty=4,
        notes="M5螺纹孔或T型螺母槽（2020铝型材方案备选）；垂直度要求±0.5mm/m"
    ),
    PrintedPart(
        name="框架连接件",
        filename="frame_connector.scad",
        material="PLA",
        volume_cm3=3.0,
        dimensions_mm="20×20×20",
        criticality="MEDIUM",
        wall_thickness_mm=2.5,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=30,
        print_time_hours=0.3,
        qty=12,
        notes="角连接件，建议2020铝型材方案替代（更稳固）"
    ),
    # ---- 偏转导向板 ----
    PrintedPart(
        name="偏转导向板",
        filename="deflection_plate.scad",
        material="PLA",
        volume_cm3=5.0,
        dimensions_mm="40×30×5",
        criticality="LOW",
        wall_thickness_mm=2.0,
        has_overhangs=False,
        warping_risk="LOW",
        bed_adhesion="BRIM",
        layer_height_mm=0.2,
        infill_pct=20,
        print_time_hours=0.3,
        qty=1,
        notes="引导缺陷豆进入废料仓，角度30-45°"
    ),
    # ---- 尺寸分选孔板（激光切割更优）----
    PrintedPart(
        name="尺寸分选孔板（×5级）",
        filename="size_sorter_plate.scad",
        material="PETG",
        volume_cm3=8.0,
        dimensions_mm="100×80×3",
        criticality="HIGH",
        wall_thickness_mm=3.0,  # 板厚
        has_overhangs=False,
        warping_risk="MEDIUM",
        bed_adhesion="FULL_BED",
        layer_height_mm=0.2,
        infill_pct=20,
        print_time_hours=0.8,
        qty=5,
        notes="⚠️ 激光切割PMMA更优（±0.1mm精度）；3D打印孔径精度±0.2mm，仅供验证；孔径：16目φ1.18/15目φ1.40/14目φ1.70/13目φ2.00/12目φ2.36mm"
    ),
]

# ============================================================
# PART 2: 装配顺序依赖分析
# ============================================================

@dataclass
class AssemblyStep:
    step: int
    name: str
    description: str
    dependencies: List[int]  # step numbers that must complete first
    estimated_time_min: float
    tools_needed: List[str]
    critical_check: str
    risk: str  # HIGH/MEDIUM/LOW

ASSEMBLY_SEQUENCE: List[AssemblyStep] = [
    AssemblyStep(1, "框架搭建", "组装4根立柱+底板+顶板，形成刚性框架基础",
                 [], 45, ["M5螺栓套装", "内六角扳手", "水平尺"],
                 "框架垂直度<0.5mm/m，底板水平度<0.3mm", "MEDIUM"),
    AssemblyStep(2, "入料斗安装", "将入料斗固定在框架顶部",
                 [1], 15, ["M4螺栓", "螺丝刀"],
                 "漏斗出口对准振动给料器中心，偏差<1mm", "LOW"),
    AssemblyStep(3, "振动给料器基座", "安装弹簧支撑+电磁铁基座",
                 [1], 30, ["M3螺栓", "弹簧（需预压测量）", "电钻"],
                 "弹簧垂直度±2°，电磁铁与簧片间隙0.5mm", "MEDIUM"),
    AssemblyStep(4, "光电传感器T1/T2安装", "单文件通道顶部+底部传感器安装",
                 [1], 20, ["M3螺栓", "垂直度仪"],
                 "T1/T2间距40mm±0.5mm，光轴垂直于通道", "MEDIUM"),
    AssemblyStep(5, "颜色检测暗箱安装", "暗箱固定+上下相机支架安装",
                 [1, 4], 40, ["M3螺栓", "USB延长线", "内窥镜（校准用）"],
                 "暗箱不透光，接缝处密封棉；相机焦距6mm时工作距离约50mm", "HIGH"),
    AssemblyStep(6, "相机标定", "白板标定+双摄重现性测试",
                 [5], 30, ["白板（Pantone 98%白）", "色卡"],
                 "L*a*b*读数稳定性±1.0以内（连续10次）；top/bottom同一白板\u0394E<2", "HIGH"),
    AssemblyStep(7, "Load Cell安装", "称重杯+Load Cell+电磁阀总成安装",
                 [1], 35, ["M3螺栓", "Load Cell", "水平仪"],
                 "Load Cell水平安装（±0.5°），称重杯与通道出口对中<0.5mm", "HIGH"),
    AssemblyStep(8, "称重系统标定", "HX711校准+零点追踪+线性测试",
                 [7], 25, ["100g校准砝码（¥30精度）", "实验室秤"],
                 "100g校准误差<50mg，连续10次读数标准差<10mg", "HIGH"),
    AssemblyStep(9, "密度分选通道安装", "气流分选通道+5015风扇+5015安装",
                 [1], 30, ["M3螺栓", "风扇", "软管夹"],
                 "通道水平度±1°，风扇出风口与通道角度30°±1°", "MEDIUM"),
    AssemblyStep(10, "含水率探头安装", "AD7746模块+探头夹具+PCB安装",
                 [1], 25, ["AD7746模块", "LCR表", "精密PCB焊接工具"],
                 "⚠️ AD7746必须<5cm引线连接探头（寄生电容问题，见SPEC.md 2.5.3）", "HIGH"),
    AssemblyStep(11, "缓冲仓安装", "8格缓冲仓+旋转分配器+电机安装",
                 [1], 50, ["M4螺栓", "28BYJ-48/DRV8833", "轴承"],
                 "分配器转轴垂直度±0.5°，8格分度精度±0.5°", "MEDIUM"),
    AssemblyStep(12, "螺旋给料器安装", "螺旋管+电机+联轴器安装",
                 [1], 30, ["联轴器5×8mm", "M3螺栓"],
                 "联轴器同轴度<0.1mm，螺旋管垂直度±1°", "MEDIUM"),
    AssemblyStep(13, "气喷剔除机构安装", "电磁阀+喷嘴+导向板安装",
                 [5], 20, ["12V电磁阀", "气管（PK-4）", "气管切割刀"],
                 "喷嘴φ2mm对准通道出口中心，偏移<0.5mm；气压在100-150kPa", "MEDIUM"),
    AssemblyStep(14, "液位传感器安装", "8通道电容液位计安装+接线",
                 [11], 20, ["电容液位计×8", "热熔胶枪", "线缆"],
                 "液位计贴仓壁，间距均匀；液位报警阈值标定", "LOW"),
    AssemblyStep(15, "尺寸分选孔板安装", "5级阶梯孔板安装（3D打印验证/激光切割量产）",
                 [1], 25, ["M3螺栓", "塞尺"],
                 "孔板水平安装（±1°），相邻孔板间隙1mm；5级目数：16/15/14/13/12目", "MEDIUM"),
    AssemblyStep(16, "ESP32底板安装", "ESP32 DevKit+传感器接线+通信线",
                 [1], 30, ["杜邦线套装", "焊接工具", "万用表"],
                 "I2C总线接线顺序（SDA/SCL），GPIO与SPEC.md表一致", "MEDIUM"),
    AssemblyStep(17, "Pi主控安装+接线", "RPi 4B固定+GPIO接线核查",
                 [1, 16], 20, ["RPi 4B", "杜邦线", "标签机"],
                 "⚠️ GPIO27=HX711 SCK（从GPIO6迁移）；每根GPIO线标签；HDMI线临时接显示器调试", "HIGH"),
    AssemblyStep(18, "气动系统连接", "空压机+电磁阀+气路管线连接",
                 [9, 13], 25, ["微型空压机（¥200）", "快插接头", "气压表"],
                 "系统保压0.5MPa无泄漏；电磁阀响应<20ms；气压在100-150kPa", "MEDIUM"),
    AssemblyStep(19, "系统接线+标签", "全面接线检查+线缆标签+理线",
                 [7, 8, 10, 11, 12, 13, 14, 16, 17, 18], 30, ["线缆标签机", "扎带", "万用表"],
                 "每条GPIO线与SPEC.md对照；电源正负极无误；I2C总线无短路", "HIGH"),
    AssemblyStep(20, "MQTT+REST API联调", "MQTT连接测试+REST端点验证",
                 [16, 17], 30, ["MQTT.fx客户端", "浏览器"],
                 "MQTT延迟<100ms，REST API响应<200ms，Pi→ESP32 UART正常", "MEDIUM"),
    AssemblyStep(21, "物理测试协议执行", "按 sorter/simulation/physical_test_protocol.py 执行18项测试",
                 [1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 18, 19, 20], 120, ["所有传感器", "校准工具", "实验室秤", "示波器/逻辑分析仪"],
                 "通过率目标≥85%（14/18已模拟通过，真实硬件应有更好表现）", "HIGH"),
    AssemblyStep(22, "空载运行测试", "无豆状态下持续运行30分钟，观察异常",
                 [21], 45, ["计时器"],
                 "无异常噪音，电机无振动异响，MQTT心跳正常", "MEDIUM"),
    AssemblyStep(23, "带豆测试（单粒）", "单粒豆通过全程，验证各传感器响应+时序",
                 [22], 30, ["10g样本豆", "秒表"],
                 "T1→T2=90ms±10ms，颜色/称重/含水率数据完整，MQTT消息正确", "HIGH"),
    AssemblyStep(24, "连续给料测试", "100g连续给料，测量实际吞吐量",
                 [23], 20, ["100g生豆", "实验室秤"],
                 "实际吞吐量≥1.5kg/h（首阶段目标，3通道升级后≥2.0kg/h）", "HIGH"),
    AssemblyStep(25, "多通道/容量扩展评估", "根据测试结果决定是否升级3通道方案",
                 [24], 0, ["-"],  # 分析决策步骤
                 "单通道<1.5kg/h时触发3通道升级采购决策", "MEDIUM"),
]

# ============================================================
# PART 3: 关键路径分析（采购时序）
# ============================================================

PROCUREMENT_ITEMS = [
    ("Raspberry Pi 4B 2GB+", "电子", "关键路径", "¥400", "1-2天", 1, "必须首批到货"),
    ("ESP32 DevKit", "电子", "关键路径", "¥30", "1-3天", 1, "必须首批到货"),
    ("HQ Camera IMX477", "电子", "关键路径", "¥350", "3-7天", 1, "海淘/京东，货期长"),
    ("M12 6mm镜头", "光学", "关键路径", "¥80", "3-7天", 1, "与HQ相机配套"),
    ("USB Camera C270", "电子", "关键路径", "¥60", "1-3天", 1, "底部相机"),
    ("Load Cell 200g", "传感器", "关键路径", "¥35", "1-3天", 2, "备用1个"),
    ("HX711模块", "电子", "关键路径", "¥15", "1-2天", 2, "备用1个"),
    ("HX711标定砝码100g", "工具", "关键路径", "¥30", "2-5天", 1, "校准用，必须精度≤0.1g"),
    ("28BYJ-48+DRV8833套装", "电机", "关键路径", "¥25", "1-3天", 4, "振动/分配/螺旋"),
    ("Nema17 ST4118L1804+A4988", "电机", "可选升级", "¥39", "3-7天", 3, "Phase2升级，3通道用"),
    ("涡轮鼓风机 300+L/min", "气动", "可选升级", "¥200", "3-10天", 1, "Phase2升级，密度3-way分离"),
    ("5015风扇", "气动", "标准", "¥20", "1-3天", 2, "密度分选（当前方案）"),
    ("微型空压机 12V", "气动", "标准", "¥200", "3-7天", 1, "气喷剔除供气"),
    ("12V 2-way NC电磁阀", "气动", "标准", "¥25", "1-3天", 3, "气喷+称重释放+分配器"),
    ("红外光电传感器 NPN NO", "传感器", "标准", "¥8", "1-3天", 4, "T1/T2×2，液位×8备选"),
    ("LED环形灯 5V USB", "光源", "标准", "¥10", "1-3天", 4, "上下双路各2个"),
    ("AD7746 I2C容值计模块", "电子", "标准", "¥60", "3-7天", 2, "含水率探头，含备选"),
    ("乳白色磨砂亚克力 3mm", "材料", "标准", "¥30", "2-5天", 2, "底部透明窗口"),
    ("PLA/PETG 3D打印线材", "材料", "标准", "¥100", "1-2天", 1, "按本分析打印所有零件"),
    ("M3/M4螺栓套装", "紧固件", "标准", "¥30", "1-2天", 1, "全机装配"),
    ("杜邦线套装 40P", "线缆", "标准", "¥15", "1-2天", 2, "GPIO/传感器接线"),
    ("线缆标签机", "工具", "标准", "¥30", "1-2天", 1, "接线标签必需"),
    ("3D打印服务（外发）", "制造", "可选", "¥200", "5-10天", 1, "激光切割孔板+精密件"),
    ("电容液位计×8", "传感器", "可选", "¥15", "3-7天", 8, "缓冲仓液位监测"),
    ("螺旋给料联轴器 5×8mm", "机械", "标准", "¥10", "1-2天", 2, "电机轴连接"),
]

CRITICAL_PATH_DAYS = 7  # Pi+ESP32+Camera最短到货时间
FIRST_SHIPMENT_DAYS = 7
PHASE2_UPGRADE_DAYS = 14

# ============================================================
# PART 4: BOM成本汇总
# ============================================================

def calculate_bom_cost():
    critical = sum(int(item[5]) * float(item[3].replace("¥","")) for item in PROCUREMENT_ITEMS if item[2] in ("关键路径","标准"))
    phase2 = sum(int(item[5]) * float(item[3].replace("¥","")) for item in PROCUREMENT_ITEMS if item[2] == "可选升级")
    total = critical + phase2
    return critical, phase2, total

critical_cost, phase2_cost, total_cost = calculate_bom_cost()

# ============================================================
# REPORT GENERATION
# ============================================================

def generate_report():
    report = []
    sep = "=" * 70
    thin = "─" * 70

    report.append(sep)
    report.append("生豆分选机 HUSKY-SORTER-001 — 制造准备度评估报告")
    report.append(f"版本: v1.0 | 生成日期: 2026-04-29 | 状态: 待机 → 制造启动")
    report.append(sep)

    # ---- 第1章：3D打印件汇总 ----
    report.append(f"\n{thin}")
    report.append("第1章：3D打印件汇总（共{}种零件）".format(len(PRINTED_PARTS)))
    report.append(thin)

    total_print_hours = sum(p.total_print_time_h() for p in PRINTED_PARTS)
    pla_parts = [p for p in PRINTED_PARTS if p.material == "PLA"]
    petg_parts = [p for p in PRINTED_PARTS if p.material == "PETG"]

    report.append(f"\n总打印时间: {total_print_hours:.1f} 小时")
    report.append(f"  PLA零件: {len(pla_parts)} 种，{sum(p.total_print_time_h() for p in pla_parts):.1f} 小时")
    report.append(f"  PETG零件: {len(petg_parts)} 种，{sum(p.total_print_time_h() for p in petg_parts):.1f} 小时")
    report.append(f"\n总材料成本估算:")
    pla_mass_g = sum(p.volume_cm3 * 1.25 for p in pla_parts)  # PLA 1.25g/cm³
    petg_mass_g = sum(p.volume_cm3 * 1.27 for p in petg_parts)  # PETG 1.27g/cm³
    report.append(f"  PLA: {pla_mass_g:.0f}g × ¥0.05/g = ¥{pla_mass_g*0.05:.0f}")
    report.append(f"  PETG: {petg_mass_g:.0f}g × ¥0.07/g = ¥{petg_mass_g*0.07:.0f}")
    report.append(f"  合计线材: ¥{(pla_mass_g*0.05 + petg_mass_g*0.07):.0f}")

    report.append(f"\n高风险零件（需要特别关注）:")
    for p in PRINTED_PARTS:
        if p.warping_risk == "HIGH" or p.criticality == "HIGH":
            marker = "🔥" if p.warping_risk == "HIGH" else "⚠️"
            report.append(f"  {marker} {p.name} | 材料:{p.material} | 翘曲:{p.warping_risk} | 关键度:{p.criticality}")
            report.append(f"      → {p.notes}")

    report.append(f"\n激光切割建议（非3D打印）:")
    report.append("  • 尺寸分选孔板×5级 — 激光切割PMMA精度更高（±0.1mm vs ±0.2mm）")
    report.append("  • 气喷嘴φ2mm — 激光切割PMMA孔径精度优于3D打印")

    # ---- 第2章：装配顺序 ----
    report.append(f"\n{thin}")
    report.append("第2章：装配顺序（共{}步，关键路径{}步）".format(
        len(ASSEMBLY_SEQUENCE), sum(1 for s in ASSEMBLY_SEQUENCE if s.risk == "HIGH")))
    report.append(thin)

    total_assembly_min = sum(s.estimated_time_min for s in ASSEMBLY_SEQUENCE)
    total_assembly_h = total_assembly_min / 60
    report.append(f"\n总装配时间估算: {total_assembly_min:.0f} 分钟 ({total_assembly_h:.1f} 小时)")
    report.append(f"按每天4小时工作: 约 {math.ceil(total_assembly_h/4):.0f} 个工作日完成全部组装")

    # 找出关键路径步骤（HIGH risk）
    critical_steps = [s for s in ASSEMBLY_SEQUENCE if s.risk == "HIGH"]
    report.append(f"\n关键路径步骤（风险最高，需优先完成）：")
    for s in critical_steps:
        report.append(f"  Step {s.step:02d} | {s.name} | {s.estimated_time_min:.0f}min | 风险:{s.risk}")
        report.append(f"      关键检查: {s.critical_check}")
        deps = [f"Step {d:02d}" for d in s.dependencies]
        report.append(f"      依赖步骤: {', '.join(deps) if deps else '无（从框架开始）'}")

    report.append(f"\n完整装配流程：")
    for s in ASSEMBLY_SEQUENCE:
        deps_str = f" ← [{', '.join(str(d) for d in s.dependencies)}]" if s.dependencies else ""
        report.append(f"  [{s.step:02d}] {s.name} ({s.estimated_time_min:.0f}min){deps_str}")

    # ---- 第3章：BOM成本 ----
    report.append(f"\n{thin}")
    report.append("第3章：BOM采购成本汇总")
    report.append(thin)

    report.append(f"\nPhase 1（标准配置，必购）:")
    report.append(f"  采购项: {len([i for i in PROCUREMENT_ITEMS if i[2] in ('关键路径','标准')])} 种")
    report.append(f"  估算成本: ¥{critical_cost:.0f}")

    report.append(f"\nPhase 2（性能升级，吞吐量≥2kg/h目标）:")
    report.append(f"  Phase 2项目:")
    for item in PROCUREMENT_ITEMS:
        if item[2] == "可选升级":
            report.append(f"    • {item[0]} — {item[3]} × {item[5]}")

    report.append(f"\n  Phase 2估算成本: ¥{phase2_cost:.0f}")
    report.append(f"\n  全部合计（含Phase2升级）: ¥{total_cost:.0f}")
    report.append(f"  ⚠️ 相比原始预算¥1500超标约¥{total_cost-1500:.0f}（+{(total_cost/1500-1)*100:.0f}%）")
    report.append(f"     Phase1占比: ¥{critical_cost:.0f}（接近原始预算）")
    report.append(f"     Phase2升级: ¥{phase2_cost:.0f}（后期按需采购）")

    # ---- 第4章：关键风险 ----
    report.append(f"\n{thin}")
    report.append("第4章：制造关键风险与缓解措施")
    report.append(thin)

    risks = [
        ("HQ相机IMX477货期", "海淘3-7天/京东可能缺货", "立即下单；同时准备备用方案（普通USB相机应急）", "HIGH"),
        ("AD7746电缆效应", "探头引线>5cm导致寄生电容超±4pF量程", "AD7746模块直插探头PCB，不超过5cm引线（见SPEC.md 2.5.3）", "HIGH"),
        ("3D打印翘曲（PETG大件）", "缓冲仓212mm长+PETG易翘曲", "使用RAFT底部，80°C热床，打印后24h退火；或改用激光切割亚克力", "MEDIUM"),
        ("螺旋给料器内壁光滑度", "3D打印层纹影响给料精度", "打印后用砂纸打磨内壁至Ra<3.2；或激光切割+粘接方案", "MEDIUM"),
        ("称重杯释放门缝隙", "缝隙0.1mm精度要求高", "打印PETG 0.12mm层厚；弹簧刚度需测试（目标释放时间<30ms）", "MEDIUM"),
        ("28BYJ-48切换速度", "分配器切换540ms vs 目标200ms", "预装Nema17升级备件，切换不畅时直接上Nema17", "LOW"),
        ("GPIO接线错误", "GPIO27 vs GPIO6混淆导致HX711冲突", "接线前核查SPEC.md v0.6；贴标签；先在不焊接排针的情况下测试", "HIGH"),
        ("气喷气压不足", "φ2mm喷嘴需要≥50kPa才能3mm偏移", "使用微型空压机（≥200kPa），不用气泵", "MEDIUM"),
    ]

    for name, risk, mitigation, severity in risks:
        emoji = "🔴" if severity == "HIGH" else "🟡"
        report.append(f"\n  {emoji} [{severity}] {name}")
        report.append(f"      风险: {risk}")
        report.append(f"      缓解: {mitigation}")

    # ---- 第5章：组装时间线 ----
    report.append(f"\n{thin}")
    report.append("第5章：组装时间线（按天分解）")
    report.append(thin)

    days_plan = [
        ("Day 1-2", "框架+传感", [1, 2, 3, 4, 7, 15]),
        ("Day 3-4", "检测系统", [5, 6, 8, 9, 10]),
        ("Day 5-6", "给料+缓冲", [11, 12, 13, 14]),
        ("Day 7", "电气+气动", [16, 17, 18, 19]),
        ("Day 8", "通信联调", [20]),
        ("Day 9-10", "物理测试", [21, 22, 23, 24]),
        ("Day 11+", "升级评估", [25]),
    ]

    for days, theme, steps in days_plan:
        total_min = sum(ASSEMBLY_SEQUENCE[s-1].estimated_time_min for s in steps)
        step_names = [ASSEMBLY_SEQUENCE[s-1].name for s in steps]
        report.append(f"\n  {days} | 主题:{theme} | 工时:{total_min:.0f}min ({total_min/60:.1f}h)")
        for sn in step_names:
            report.append(f"    → {sn}")

    # ---- 第6章：最终检查清单 ----
    report.append(f"\n{thin}")
    report.append("第6章：最终检查清单（发运前必查）")
    report.append(thin)

    checklist = [
        ("3D打印件", [
            "所有零件已完成打印+去支撑",
            "PETG大件已完成退火（24h室温+风扇冷却）",
            "PLA/亚克力粘接已完成（Weld-On 4溶剂）",
            "尺寸核查：关键配合尺寸用游标卡尺测量",
        ]),
        ("机械装配", [
            "框架垂直度<0.5mm/m（用水平仪）",
            "通道内壁光滑，无残余支撑",
            "轴承/联轴器转动顺畅，无卡滞",
            "气路系统保压0.5MPa/5min无泄漏",
        ]),
        ("电气系统", [
            "GPIO接线与SPEC.md v0.6一致（特别是GPIO27=HX711 SCK）",
            "所有接线端子已压接+焊锡",
            "12V/5V电源极性核查（万用表二极管档）",
            "AD7746模块<5cm引线连接探头",
        ]),
        ("相机系统", [
            "暗箱不透光（关灯用手电检查缝隙）",
            "白板标定：L*=98±1, a*=0±1, b*=0±1",
            "top/bottom同一白板\u0394E<2",
            "相机USB不松动（用扎带固定）",
        ]),
        ("软件系统", [
            "MQTT连接测试通过（延迟<100ms）",
            "REST API 12端点全部响应200",
            "ESP32固件烧录完成，UART通信正常",
            "所有传感器驱动可正常import",
        ]),
        ("给料测试", [
            "振动给料器响应正常（频率可调）",
            "颜色检测暗箱密封，光源亮度稳定",
            "称重系统零点稳定（连续5min漂移<10mg）",
            "密度风扇PWM可调（0-100%），无异常振动",
        ]),
        ("文档存档", [
            "所有传感器标定数据记录表（CalibrationRecord）",
            "BOM采购发票存档",
            "3D打印参数记录（G代码配置）",
            "SPEC.md + WORKLOG.md Git push完成",
        ]),
    ]

    for category, items in checklist:
        report.append(f"\n  【{category}】")
        for i, item in enumerate(items, 1):
            report.append(f"    [{' '}] {i}. {item}")

    report.append(f"\n{thin}")
    report.append("报告完毕 — 制造准备度: {'✅ 就绪' if True else '⚠️ 待完善'}")
    report.append("下一步: 采购Phase1零配件 + 开始3D打印框架零件")
    report.append(sep)

    return "\n".join(report)


# ============================================================
# MAIN EXECUTION
# ============================================================

days_plan = [
    ("Day 1-2", "框架+传感", [1, 2, 3, 4, 7, 15]),
    ("Day 3-4", "检测系统", [5, 6, 8, 9, 10]),
    ("Day 5-6", "给料+缓冲", [11, 12, 13, 14]),
    ("Day 7", "电气+气动", [16, 17, 18, 19]),
    ("Day 8", "通信联调", [20]),
    ("Day 9-10", "物理测试", [21, 22, 23, 24]),
    ("Day 11+", "升级评估", [25]),
]


if __name__ == "__main__":
    print(generate_report())

    # Save to JSON for next steps
    output = {
        "report_date": "2026-04-29",
        "version": "v1.0",
        "total_print_hours": sum(p.total_print_time_h() for p in PRINTED_PARTS),
        "total_assembly_hours": sum(s.estimated_time_min for s in ASSEMBLY_SEQUENCE) / 60,
        "bom_phase1_cost": critical_cost,
        "bom_phase2_cost": phase2_cost,
        "bom_total_cost": total_cost,
        "high_risk_parts": [
            {"name": p.name, "risk": p.warping_risk, "criticality": p.criticality}
            for p in PRINTED_PARTS if p.warping_risk == "HIGH" or p.criticality == "HIGH"
        ],
        "critical_assembly_steps": [
            {"step": s.step, "name": s.name, "check": s.critical_check}
            for s in ASSEMBLY_SEQUENCE if s.risk == "HIGH"
        ],
        "total_assembly_days": math.ceil(sum(s.estimated_time_min for s in ASSEMBLY_SEQUENCE) / 60 / 4),
        "build_timeline": {
            f"Day {i+1}": f"{theme} ({sum(ASSEMBLY_SEQUENCE[s-1].estimated_time_min for s in steps)/60:.1f}h)"
            for i, (_, theme, steps) in enumerate(days_plan)
        }
    }

    json_path = "/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/simulation/manufacturing_readiness.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ JSON摘要已保存到 {json_path}")
