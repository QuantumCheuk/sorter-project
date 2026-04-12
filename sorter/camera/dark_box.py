"""
dark_box.py - 暗箱3D模型设计
HUSKY-SORTER-001 / 课题2: 颜色检测系统

暗箱设计要点：
1. 漫反射内壁（白PLA打印）
2. 均匀光源（4× LED环形灯）
3. 摄像头固定支架
4. 豆子落料通道
5. 遮光密封
"""

# 暗箱设计参数（单位：mm）
DARK_BOX_PARAMS = {
    # 外形尺寸
    "length": 120,      # X方向（垂直于光轴）
    "width": 120,       # Y方向（垂直于光轴）
    "height": 80,       # Z方向（光轴方向）

    # 摄像头开口
    "camera_hole_diameter": 25,   # M12镜头开孔直径
    "camera_hole_offset": 0,      # 镜头中心偏移

    # LED环形灯位置
    "led_ring_diameter": 60,      # LED环形灯直径
    "led_ring_count": 4,          # LED灯数量

    # 落料通道
    "chute_width": 30,            # 落料通道宽度
    "chute_length": 40,           # 落料通道长度

    # 内壁
    "wall_thickness": 3,          # 壁厚
    "inner_color": "white",       # 内壁颜色（漫反射白）

    # 遮光缝
    "light_seal_gap": 0.5,        # 缝隙（遮光用）

    # 安装孔
    "mount_hole_diameter": 3,     # M3安装孔
    "mount_hole_positions": [
        (-50, -50), (50, -50), (-50, 50), (50, 50)
    ],
}


def generate_openscad(param: dict) -> str:
    """生成 OpenSCAD 脚本"""
    return f'''
// Dark Box for Coffee Bean Color Sorting
// HUSKY-SORTER-001 / Topic 2

// Parameters
length = {param["length"]};
width = {param["width"]};
height = {param["height"]};
wall = {param["wall_thickness"]};
chute_w = {param["chute_width"]};
chute_l = {param["chute_length"]};
led_d = {param["led_ring_diameter"]};
cam_d = {param["camera_hole_diameter"]};

// Colors
inner_color = [1.0, 1.0, 0.95]; // 漫反射白
outer_color = [0.2, 0.2, 0.2];

// === 底部主体 ===
difference() {{
    // 外壳
    color(outer_color)
    translate([-length/2, -width/2, -height/2])
    cube([length, width, height]);

    // 挖空内部（漫反射腔）
    color(inner_color)
    translate([-length/2 + wall, -width/2 + wall, -height/2 + wall])
    cube([
        length - 2*wall,
        width - 2*wall,
        height - wall  // 底部保留
    ]);

    // 摄像头开孔（顶部中心）
    translate([0, 0, height/2])
    cylinder(h=wall+2, d={param["camera_hole_diameter"]+2}, center=true);

    // 落料通道（底部侧面）
    translate([-chute_w/2, -width/2 - 5, -height/2 + 10])
    cube([chute_w, wall + 10, chute_l]);
}}

// === LED环形灯支架 ===
for (i = [0:{param["led_ring_count"]-1}]) {{
    angle = i * 360 / {param["led_ring_count"]};
    rotate([0, 0, angle])
    translate([led_d/2, 0, 0])
    color([0.8, 0.8, 0.8])
    cylinder(h=5, d=8, center=true);
}}

// === 摄像头支架（可选） ===
// translate([0, 0, height/2 - 20])
// cylinder(h=20, d={param["camera_hole_diameter"]}, center=true);

// === 安装脚 ===
for (pos = {param["mount_hole_positions"]}) {{
    translate([pos[0], pos[1], -height/2 - 5])
    cylinder(h=5, d={param["mount_hole_diameter"]+2});
}}

echo("=== Dark Box Volume ===");
echo(str("Inner volume: ", (length-2*wall), "x", (width-2*wall), "x", (height-wall), " mm"));
'''


def generate_freecad_macro(param: dict) -> str:
    """生成 FreeCAD Python macro"""
    return f'''# -*- coding: utf-8 -*-
# FreeCAD Macro: Dark Box for Coffee Bean Sorter
# HUSKY-SORTER-001 / Topic 2

import FreeCAD as App
import Part
import Sketcher
import Mesh

# 创建新文档
doc = App.newDocument("DarkBox")

# 参数
L = {param["length"]}
W = {param["width"]}
H = {param["height"]}
wall = {param["wall_thickness"]}
chute_w = {param["chute_width"]}
chute_l = {param["chute_length"]}
led_d = {param["led_ring_diameter"]}
cam_d = {param["camera_hole_diameter"]}

# 创建外壳（布尔差运算）
outer = doc.addObject("Part::Box", "OuterBox")
outer.Length = L
outer.Width = W
outer.Height = H
outer.Placement.Base = App.Vector(-L/2, -W/2, -H/2)

inner = doc.addObject("Part::Box", "InnerBox")
inner.Length = L - 2*wall
inner.Width = W - 2*wall
inner.Height = H - wall
inner.Placement.Base = App.Vector(-L/2 + wall, -W/2 + wall, -H/2 + wall)

# 布尔差运算
cut = doc.addObject("Part::Cut", "DarkBoxBody")
cut.Base = outer
cut.Tool = inner
doc.recompute()

# 摄像头开孔（圆柱体）
cam_hole = doc.addObject("Part::Cylinder", "CameraHole")
cam_hole.Radius = cam_d/2 + 1
cam_hole.Height = wall + 5
cam_hole.Placement.Base = App.Vector(0, 0, H/2)
doc.recompute()

# 保存
__import__("exportCS").export([cut], "/tmp/dark_box.step")
print("STEP saved to /tmp/dark_box.step")
'''


def generate_3d_print_sla(param: dict) -> str:
    """生成光固化3D打印用STL切片配置"""
    return f'''
; Dark Box SLA 3D Print Settings
; HUSKY-SORTER-001 / Topic 2

; 基础参数
LAYER_HEIGHT = 0.05  ; mm
EXPOSURE_TIME = 2.5   ; 秒
BOTTOM_EXPOSURE = 25  ; 秒
BOTTOM_LAYERS = 5

; 材料
MATERIAL = "White Resin"  ; 漫反射白树脂
INFILL = 100%           ; 实心（遮光需要）

; 特殊要求
WALL_THICKNESS = {param["wall_thickness"]}mm
SURFACE_FINISH = "Matte"  ; 粗糙内壁（增强漫反射）

; 后处理
POST_CURE_TIME = 30  ; 分钟
POST_CURE_TEMP = 60  ; °C

; 注意事项：
; 1. 内壁需要喷涂漫反射白漆
; 2. 接缝处需用黑色密封胶处理
; 3. 摄像头开孔周围贴遮光棉
'''


if __name__ == "__main__":
    import json

    print("=== Dark Box Design Parameters ===")
    print(json.dumps(DARK_BOX_PARAMS, indent=2))

    print("\n=== OpenSCAD Script ===")
    print(generate_openscad(DARK_BOX_PARAMS))

    # 保存参数
    with open("/tmp/dark_box_params.json", "w") as f:
        json.dump(DARK_BOX_PARAMS, f, indent=2)
    print("\nParams saved to /tmp/dark_box_params.json")
