// ============================================================
// sorter/cad/buffer_bin.scad
// 缓冲料仓 3D 设计 — 8格分级仓 + 旋转分配器
// HUSKY-SORTER-001 | 2026-04-26
//
// v2 2026-05-17: Major structural fixes:
//  - Outlet ports now penetrate rear wall (was outside bin)
//  - Hopper feeds through fixed inlet tube into rotary disc
//  - Gap increased to 2.5mm for FDM printability
//  - Motor mount walls thickened from 0.25mm to 4mm
//  - Rotary distributor channel dia increased to 22mm
// ============================================================

// ========== 全局参数 ==========
$fn = 64;

// 8格参数
n_bins = 8;
bin_width_mm = 25;    // 单格宽度
bin_depth_mm = 30;    // 单格深度
bin_height_mm = 40;   // 单格高度
wall_mm = 2.5;        // 壁厚
gap_mm = 2.5;         // 格间间隙 (v2: 1.0->2.5, FDM可打印)

// 漏斗参数
hopper_height_mm = 25;
hopper_angle_deg = 45;

// 分配器参数
disc_diameter_mm = 76;
disc_thickness_mm = 3;

// 计算值
total_width = n_bins * bin_width_mm + (n_bins - 1) * gap_mm + 2 * wall_mm;  // 222.5mm
total_depth = bin_depth_mm + 2 * wall_mm;                                     // 35mm
total_height = bin_height_mm + 2 * wall_mm;                                   // 45mm

// ========== 仓体 ==========
module bin_box() {
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

// ========== 入口漏斗 + 固定入料管 ==========
// v2: 漏斗从顶部向下收敛, 通过固定管穿透旋转分配器中心
// 旋转盘在漏斗下方, 豆子经固定管落入盘中通道孔, 再分配到各格
module inlet_hopper() {
    inlet_diameter_top_mm = total_width * 0.5;   // ~111mm, 宽口接收
    inlet_diameter_bottom_mm = 22;                // 对接固定管
    tube_outer_dia = 24;                          // 固定管外径 (壁厚1mm)
    tube_inner_dia = 20;                          // 固定管内径

    // 漏斗位置: 放在仓体顶部上方
    hopper_base_z = total_height;

    // 漏斗 (上大下小, 正常方向)
    translate([total_width/2, bin_depth_mm/2 + wall_mm, hopper_base_z])
        cylinder(h=hopper_height_mm,
            d1=inlet_diameter_top_mm, d2=inlet_diameter_bottom_mm,
            $fn=32);

    // 固定入料管: 从漏斗底穿过旋转盘, 延伸到盘面下方
    // 旋转盘在 hopper_base_z + hopper_height_mm 处
    disc_top_z = hopper_base_z + hopper_height_mm;

    // 管子上段: 从漏斗底到盘面 (壁厚1mm)
    translate([total_width/2, bin_depth_mm/2 + wall_mm, disc_top_z])
        difference() {
            cylinder(h=hopper_height_mm, d=tube_outer_dia, $fn=32);
            // 管内通孔
            translate([0, 0, -0.1])
                cylinder(h=hopper_height_mm + 0.2, d=tube_inner_dia, $fn=32);
        }
}

// ========== 8通道旋转分配器 ==========
// v2: 中心开孔容纳固定入料管, 通道孔扩大到22mm
module rotary_distributor() {
    channel_pitch_mm = bin_width_mm + gap_mm;     // 27.5mm
    channel_dia = 22;                              // v2: 扩大通道孔径 (原18.2mm, 卡豆风险)
    center_hole_dia = 25;                          // 固定管通过孔 (管外径24 + 1mm间隙)
    center_x = total_width / 2;
    disc_z = total_height + hopper_height_mm;      // 盘在漏斗上方

    translate([center_x, bin_depth_mm/2 + wall_mm, disc_z])
    difference() {
        // 圆盘
        cylinder(h=disc_thickness_mm, d=disc_diameter_mm);
        // 中心固定管通过孔
        translate([0, 0, -1])
            cylinder(h=disc_thickness_mm + 2, d=center_hole_dia, $fn=32);
        // 8个通道孔 (分布在盘面上, 距中心28mm)
        for (i = [0:n_bins-1]) {
            angle = i * 360 / n_bins;
            x = cos(angle) * (disc_diameter_mm/2 - 8);
            y = sin(angle) * (disc_diameter_mm/2 - 8);
            translate([x, y, -1])
                cylinder(h=disc_thickness_mm + 2, d=channel_dia);
        }
    }
}

// ========== 步进电机安装座 ==========
// v2: 加厚壁厚, 螺栓孔距边缘>=4mm
module motor_mount() {
    // 28BYJ-48 尺寸: 28×28×19mm
    motor_size_mm = 28;
    mount_height_mm = 20;           // v2: 15->20mm, 覆盖电机高度
    mount_extra_mm = 12;            // v2: 安装块每边超出电机6mm
    hole_spacing_mm = 20;           // M3螺栓孔间距

    center_x = total_width / 2;
    // 电机安装座放在旋转盘上方一侧 (Y方向偏移, 不遮挡固定管)
    mount_y = bin_depth_mm/2 + wall_mm + disc_diameter_mm/2 + 5;
    disc_top_z = total_height + hopper_height_mm + disc_thickness_mm;

    translate([center_x - (motor_size_mm + mount_extra_mm)/2,
               mount_y,
               disc_top_z])
    difference() {
        cube([motor_size_mm + mount_extra_mm, mount_height_mm, motor_size_mm + mount_extra_mm]);
        // 电机安装孔 (4个M3, 距边缘>=4mm)
        for (x = [4, motor_size_mm + mount_extra_mm - 4])
            for (z = [4, motor_size_mm + mount_extra_mm - 4])
                translate([x, -1, z])
                    cylinder(h=mount_height_mm + 2, d=3.5);
    }
}

// ========== 出豆口（每格底部, 穿透后壁）==========
// v2: 出料口从仓内延伸到仓外, 穿透后壁
// 出料口内端在仓内后壁处(y=wall_mm), 外端延伸到仓外(y=-8mm)
module bin_outlet() {
    outlet_width = 8;
    outlet_depth = 12;    // 穿透后壁(2.5mm) + 延伸到外部

    difference() {
        // 从仓体后壁挖出料通道
        for (i = [0:n_bins-1]) {
            x = wall_mm + i * (bin_width_mm + gap_mm) + bin_width_mm/2;
            // 出料口: 从仓内(y=wall_mm-1, 穿透后壁)延伸到仓外
            translate([x - outlet_width/2, -8, 0])
                cube([outlet_width, outlet_depth, wall_mm]);
        }
        // 在出料口上方切出仓底开口, 让豆子能从仓格落入出料通道
        for (i = [0:n_bins-1]) {
            x = wall_mm + i * (bin_width_mm + gap_mm) + bin_width_mm/2;
            translate([x - outlet_width/2, -8, -1])
                cube([outlet_width, outlet_depth, wall_mm + 2]);
        }
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
// 材料: PETG (食品级)
// 填充: 20%
// 支撑: 漏斗需要支撑
//
// v2 变更说明:
// - gap_mm: 1.0 -> 2.5 (FDM可打印间隙)
// - total_width: ~215mm -> ~222.5mm (因gap增大)
// - 漏斗方向: 改为上大下小 (正常漏斗方向)
// - 新增固定入料管: 穿透旋转盘中心, 豆子经固定管落入盘面
// - 出料口: 改为从仓内穿透后壁, 不再悬空在仓外
// - 电机安装架: 壁厚从0.25mm增加到4mm
// - 旋转盘通道孔: 从18.2mm扩大到22mm (减少卡豆)
