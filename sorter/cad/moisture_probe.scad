// moisture_probe.scad — 电容式含水率探头 3D 设计
// ================================================
// Topic 5 Day 3 | Author: Little Husky 🐕 | Date: 2026-04-25
//
// v2 2026-05-17: Critical fixes:
//  - Funnel bottom now directly contacts upper press plate (was 7.2mm gap)
//  - Funnel bottom dia = plate_size (15mm) matching electrode (was 17mm)
//  - Funnel taller (15mm vs 7.2mm) for better bean guidance
//  - Guide channel extends from press top into electrode gap
//  - Cable exit moved from flange edge to funnel sidewall (fracture risk)
//  - Upper press central hole enlarged from φ2 to φ4 (bean passage)

// ═══════════════════════════════════════════════════════════
// 参数配置
// ═══════════════════════════════════════════════════════════

// 电极参数
plate_size = 15;      // mm — 电极边长（正方形）
plate_thick = 1.6;   // mm — PCB板厚度（FR4）

// 间隙参数
gap = 8.0;            // mm — 两极板间距离（含豆空间）
post_dia = 3.0;      // mm — 隔离柱直径

// 法兰参数
flange_dia = 34;     // mm — 安装法兰直径
flange_thick = 4;   // mm — 法兰厚度
bolt_hole_dia = 3.0; // mm — M3螺栓孔径
bolt_count = 3;      // M3螺栓数量

// 漏斗参数
funnel_top_dia = 20;        // mm — 入口直径
funnel_bot_dia = plate_size; // mm — 出口直径 = 电极尺寸，精准对接
funnel_height_mm = 15;      // mm — 漏斗高度（v2: 从7.2mm增至15mm）
guide_channel_dia = 10;     // mm — 导豆通道直径（v2新增）
guide_channel_depth = 4;    // mm — 导豆通道延伸深度（伸入电极间隙上半部）

// 电缆出口
cable_hole_dia = 6;  // mm — M6电缆密封头

// ═══════════════════════════════════════════════════════════
// Z坐标计算（关键：确保漏斗与压板零间隙对接）
// ═══════════════════════════════════════════════════════════
// z=0~4:           法兰底座 (flange_thick=4)
// z=4~5.6:         下极板托架 (plate_thick=1.6)
// z=5.6~6.6:       下极板PCB (计入托架余量)
// z=6.6~14.6:      电极间隙 (gap=8)
// z=14.6~16.2:     上极板PCB (plate_thick=1.6)
// z=16.2~17.8:     上极板压板 (plate_thick=1.6)
// z=17.8~32.8:     漏斗 (funnel_height=15)
// press_top_z = 17.8mm ← 漏斗底口直接落在此面上

press_top_z = flange_thick + plate_thick + gap + plate_thick + plate_thick;
// = 4 + 1.6 + 8 + 1.6 + 1.6 = 16.8mm

// ═══════════════════════════════════════════════════════════
// 模块定义
// ═══════════════════════════════════════════════════════════

// 底座法兰（集成下极板托架）
module flange_base_with_holder() {
    difference() {
        union() {
            // 法兰底座
            cylinder(d=flange_dia, h=flange_thick, center=false);
            // 下极板托架圆柱
            translate([0, 0, flange_thick])
                cylinder(d=plate_size + 6, h=plate_thick + 2, center=false);
        }
        // 法兰安装孔（3×M3，120°分布）
        for (i=[0:bolt_count-1]) {
            angle = i * 120 + 30;
            x = flange_dia/2 * cos(angle) - bolt_hole_dia/2;
            y = flange_dia/2 * sin(angle);
            translate([x, y, -1])
                cylinder(d=bolt_hole_dia, h=flange_thick+2, center=false);
        }
        // v2: 电缆出口孔改到漏斗侧壁（原在法兰边缘，有断裂风险）
        // 孔位于漏斗上部侧壁，距顶面3mm处
        translate([0, funnel_bot_dia/2 + funnel_height_mm * (funnel_top_dia - funnel_bot_dia) / (2 * funnel_height_mm), press_top_z + funnel_height_mm - 3])
            rotate([90, 0, 0])
                cylinder(d=cable_hole_dia, h=12, center=false);
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

// 上极板
module upper_electrode() {
    translate([0, 0, flange_thick + plate_thick + gap])
        cylinder(d=plate_size, h=plate_thick, center=false);
}

// 上极板压板
// v2: 中央通孔从φ2扩大到φ4（豆子需要通过）
module upper_press() {
    translate([0, 0, flange_thick + plate_thick + gap + plate_thick])
    difference() {
        cylinder(d=plate_size + 4, h=plate_thick, center=false);
        // v2: 中央通孔φ4（原φ2，豆子无法通过2mm孔）
        cylinder(d=4, h=plate_thick + 2, center=true);
    }
}

// 入口漏斗
// v2: 漏斗底口直接对接上压板顶面(z=press_top_z)，消除悬空间隙
// funnel_bot_dia = plate_size = 15mm，精准对接电极区域
module funnel() {
    // 漏斗底口直接落在上压板顶面 (z=press_top_z)
    translate([0, 0, press_top_z])
        cylinder(d1=funnel_top_dia, d2=funnel_bot_dia, h=funnel_height_mm, center=false);
}

// 导豆通道（v2新增）
// 从上压板中央φ4孔向下延伸，引导豆子进入8mm电极间隙
// 通道底部距下极板约4mm，确保豆子落入测量区而不卡住
module bean_guide_channel() {
    translate([0, 0, press_top_z - guide_channel_depth])
        cylinder(d=guide_channel_dia, h=guide_channel_depth + plate_thick + 0.5, center=false);
}

// ═══════════════════════════════════════════════════════════
// 完整装配
// ═══════════════════════════════════════════════════════════

module moisture_probe_assembly() {
    // 底座+下极板托架
    color("#90a4ae") flange_base_with_holder();
    // 隔离柱×4
    color("#78909c") post_array();
    // 上极板
    color("#cfd8dc") upper_electrode();
    // 上压板
    color("#b0bec5") upper_press();
    // 漏斗（直接对接压板，无间隙）
    color("#b0bec5") funnel();
    // 导豆通道（v2新增）
    color("#a0b0c0") bean_guide_channel();
}

moisture_probe_assembly();

// ═══════════════════════════════════════════════════════════
// 打印说明
// ═══════════════════════════════════════════════════════════
// 推荐打印参数:
//   材料: PETG（食品级，耐温）或SLA光敏树脂（更高精度）
//   层高: 0.2mm（PETG）或 0.1mm（SLA）
//   填充: 40%+（功能件需足够强度）
//   打印方向: 底面朝下（法兰水平），最优
//   支撑: 漏斗需要支撑
//
// 装配顺序:
//   1. 法兰+下极板 一体打印
//   2. 隔离柱×4 单独打印（需精确直径±0.05mm）
//   3. 上极板+压板 打印
//   4. 漏斗+导豆通道 打印（需支撑）
//
// v2 变更:
//   - 漏斗底口从 z=24mm(悬空7.2mm) 改为 z=16.8mm(直接对接压板)
//   - 漏斗底径从 17mm 改为 15mm (=plate_size)
//   - 漏斗高度从 7.2mm 增至 15mm
//   - 新增导豆通道φ10×4mm，引导豆子进入电极间隙
//   - 上压板中央孔从φ2扩大到φ4
//   - 电缆出口从法兰边缘改到漏斗侧壁
//
// AD7746模块安装:
//   ⚠️ AD7746必须紧贴探头(<5cm引线)，通过I2C缓冲器(PCA9600)延长到Pi
//   电缆使用屏蔽线，避免寄生电容超出±4pF量程
