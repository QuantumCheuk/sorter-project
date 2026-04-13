"""
Weighing Cup Mechanical Design
================================
3D design for the weighing cup that receives beans from the color sensor
and releases them after weighing.

Design Requirements:
- Receive single beans from color sensor output (~20mm diameter tube)
- Hold bean for ~80ms while HX711 stabilizes
- Release bean quickly via solenoid gate (~30ms)
- Total cup mass: ~5g (to maximize load cell sensitivity)
- Material: PETG (3D printed, food-safe)
- Mounts directly on 200g load cell

Author: Little Husky (HUSKY-SORTER-001)
Date: 2026-04-13
"""

# Parameters (all in mm)
INNER_DIAMETER = 14.0       # Inner diameter of cup (mm) - fits single bean
OUTER_DIAMETER = 18.0       # Outer diameter
WALL_THICKNESS = 2.0        # Wall thickness
HEIGHT = 10.0               # Cup height (mm)
INLET_DIAMETER = 22.0       # Top funnel inlet diameter (mm)
FUNNEL_HEIGHT = 8.0         # Funnel section height (mm)
BOTTOM_THICKNESS = 1.5      # Bottom plate thickness (mm)
LOAD_CELL_MOUNT_HOLES = 3   # Number of M2 screw holes for load cell mount
LOAD_CELL_HOLE_DIAMETER = 2.2  # M2 tapped holes
SOLENOID_GATE_WIDTH = 12.0  # Width of release gate opening (mm)


def generate_openscad():
    """Generate OpenSCAD code for the weighing cup."""
    
    code = f'''// Weighing Cup for Coffee Bean Sorter
// HUSKY-SORTER-001
// Generated: 2026-04-13

// Parameters
inner_diameter = {INNER_DIAMETER};
outer_diameter = {OUTER_DIAMETER};
wall_thickness = {WALL_THICKNESS};
cup_height = {HEIGHT};
inlet_diameter = {INLET_DIAMETER};
funnel_height = {FUNNEL_HEIGHT};
bottom_thickness = {BOTTOM_THICKNESS};
total_height = cup_height + funnel_height + bottom_thickness;

// Cup body (hollow cylinder)
difference() {{
    cylinder(h=cup_height, d=outer_diameter, $fn=32);
    translate([0, 0, -0.1])
        cylinder(h=cup_height+0.2, d=inner_diameter, $fn=32);
}}

// Funnel section (truncated cone)
translate([0, 0, cup_height])
    cylinder(h=funnel_height, d1=outer_diameter, d2=inlet_diameter, $fn=32);

// Bottom mounting plate
translate([0, 0, -bottom_thickness])
    cylinder(h=bottom_thickness+0.1, d=outer_diameter, $fn=32);

// Center hole for load cell boss (optional mounting)
translate([0, 0, -bottom_thickness])
    cylinder(h=bottom_thickness+0.2, d=4, $fn=16);

// Load cell mounting holes (3x M2 tapped, 120 apart)
hole_radius = (outer_diameter / 2) - 4;
for (i = [0:2]) {{
    angle = i * 120;
    x = hole_radius * cos(angle);
    y = hole_radius * sin(angle);
    translate([x, y, -bottom_thickness + 0.5])
        cylinder(h=bottom_thickness, d={LOAD_CELL_HOLE_DIAMETER}, $fn=8);
}}

// Solenoid gate slot (one side open)
gate_angle = 45;  // degrees
rotate([0, 0, gate_angle])
    translate([outer_diameter/2 - wall_thickness/2, -{SOLENOID_GATE_WIDTH}/2, cup_height * 0.3])
        cube([wall_thickness + 2, {SOLENOID_GATE_WIDTH}, cup_height * 0.5]);

// Inlet chamfer (ease the bean entry)
translate([0, 0, cup_height + funnel_height])
    cylinder(h=2, d1=inlet_diameter, d2=inlet_diameter-2, $fn=32);
'''
    
    return code


def generate_step_description():
    """Generate text description for 3D printing / machining."""
    import math
    volume_inner = math.pi * (INNER_DIAMETER/2)**2 * HEIGHT / 1000  # cm³
    volume_material = math.pi * (OUTER_DIAMETER/2)**2 * (HEIGHT + FUNNEL_HEIGHT) / 1000 - volume_inner
    mass_petg = volume_material * 1.27  # PETG density ~1.27 g/cm³
    mass_pla = volume_material * 1.24   # PLA density ~1.24 g/cm³
    
    return f"""
WEIGHING CUP DESIGN SPECIFICATION
==================================

1. Geometry
-----------
Inner diameter:     {INNER_DIAMETER} mm
Outer diameter:     {OUTER_DIAMETER} mm
Wall thickness:     {WALL_THICKNESS} mm
Cup height:         {HEIGHT} mm
Funnel inlet dia:   {INLET_DIAMETER} mm
Funnel height:     {FUNNEL_HEIGHT} mm
Bottom thickness:   {BOTTOM_THICKNESS} mm
Total height:       {HEIGHT + FUNNEL_HEIGHT + BOTTOM_THICKNESS:.1f} mm

2. Volume & Mass
----------------
Inner volume:       {volume_inner:.2f} cm³ (fits single bean comfortably)
Material volume:    {volume_material:.2f} cm³
Mass (PETG):        {mass_petg:.1f}g
Mass (PLA):         {mass_pla:.1f}g
→ Target: ≤5g (PETG chosen for food safety)

3. Mounting
-----------
Load cell interface: 3x M2 tapped holes, 120° apart
Hole diameter:       {LOAD_CELL_HOLE_DIAMETER} mm
Pitch circle:        {(OUTER_DIAMETER - 8):.1f} mm diameter
Central boss:        φ4mm × {BOTTOM_THICKNESS}mm (optional alignment pin)

4. Solenoid Gate
----------------
Gate opening:       {SOLENOID_GATE_WIDTH} mm wide × {HEIGHT * 0.5:.1f} mm tall
Solenoid type:      12V mini pull solenoid (6×6×15mm body)
Mounting:           Glued/screwed to cup side wall
Gate mechanism:     Spring-loaded flap, solenoid pulls to open

5. Inlet Funnel
---------------
Matches color sensor tube: φ20mm
Funnel taper:       {OUTER_DIAMETER}mm → {INLET_DIAMETER}mm (divergent)
Purpose:            Centers bean as it falls from tube into cup

6. Print Settings (PETG)
------------------------
Layer height:       0.12mm (high quality)
Infill:             20% (walls are solid anyway)
Material:           PETG (food-safe, temperature resistant)
Orientation:         Print inverted (funnel down, flat bottom up)
Supports:           None needed (good overhang tolerance)

7. Assembly
-----------
1. Print cup (PETG, inverted)
2. Tap 3x M2 holes for load cell screws
3. Glue small neodymium magnet to gate flap
4. Mount solenoid on cup side with M2 screws
5. Attach to load cell with 3x M2x4mm screws
6. Connect solenoid to HX711 relay output
"""


if __name__ == "__main__":
    import math
    
    print("WEIGHING CUP DESIGN GENERATOR")
    print("=" * 50)
    
    # Generate OpenSCAD
    openscad_code = generate_openscad()
    with open('/Users/quantumcheuk/.openclaw/workspace/sorter-project/sorter/cad/weighing_cup.scad', 'w') as f:
        f.write(openscad_code)
    print("[FILE] Saved weighing_cup.scad")
    
    # Generate description
    desc = generate_step_description()
    print(desc)
    
    print("[INFO] To render in OpenSCAD:")
    print("  openscad weighing_cup.scad")
    print("\n[INFO] To export STL for 3D printing:")
    print("  In OpenSCAD: File → Export → Export as STL")
