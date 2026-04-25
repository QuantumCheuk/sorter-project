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

// 法兰参数
flange_dia = 34;     // mm — 安装法兰直径
flange_thick = 4;   // mm — 法兰厚度
bolt_hole_dia = 3.0; // mm — M3螺栓孔径
bolt_count = 3;      // M3螺栓数量

// 电缆出口
cable_hole_dia = 6;  // mm — M6电缆密封头

// 漏斗参数
funnel_top_dia = 20;  // mm — 入口直径
funnel_bot_dia = plate_size + 2; // mm — 出口直径

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
        // 电缆出口孔（侧面）
        translate([flange_dia/2 - 3, 0, flange_thick/2])
            rotate([90, 0, 0])
                cylinder(d=cable_hole_dia, h=10, center=false);
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
module upper_press() {
    translate([0, 0, flange_thick + plate_thick + gap + plate_thick])
    difference() {
        cylinder(d=plate_size + 4, h=plate_thick, center=false);
        // 中央M2通孔（穿螺栓压紧）
        cylinder(d=2, h=plate_thick + 2, center=true);
    }
}

// 入口漏斗
module funnel() {
    base_z = flange_thick + plate_thick * 2 + gap + plate_thick;
    translate([0, 0, base_z])
        cylinder(d1=funnel_top_dia, d2=funnel_bot_dia, h=plate_thick * 2 + 4, center=false);
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
    // 漏斗
    color("#b0bec5") funnel();
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
//   支撑: 仅漏斗需要支撑
//
// 装配顺序:
//   1. 法兰+下极板 一体打印
//   2. 隔离柱×4 单独打印（需精确直径±0.05mm）
//   3. 上极板+压板 打印
//   4. 漏斗 打印（需支撑）
//
// 隔离柱也可与法兰一起打印（gap空间用可溶解支撑填充）
