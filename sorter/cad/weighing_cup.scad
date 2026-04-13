// Weighing Cup for Coffee Bean Sorter
// HUSKY-SORTER-001
// Generated: 2026-04-13

// Parameters
inner_diameter = 14.0;
outer_diameter = 18.0;
wall_thickness = 2.0;
cup_height = 10.0;
inlet_diameter = 22.0;
funnel_height = 8.0;
bottom_thickness = 1.5;
total_height = cup_height + funnel_height + bottom_thickness;

// Cup body (hollow cylinder)
difference() {
    cylinder(h=cup_height, d=outer_diameter, $fn=32);
    translate([0, 0, -0.1])
        cylinder(h=cup_height+0.2, d=inner_diameter, $fn=32);
}

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
for (i = [0:2]) {
    angle = i * 120;
    x = hole_radius * cos(angle);
    y = hole_radius * sin(angle);
    translate([x, y, -bottom_thickness + 0.5])
        cylinder(h=bottom_thickness, d=2.2, $fn=8);
}

// Solenoid gate slot (one side open)
gate_angle = 45;  // degrees
rotate([0, 0, gate_angle])
    translate([outer_diameter/2 - wall_thickness/2, -12.0/2, cup_height * 0.3])
        cube([wall_thickness + 2, 12.0, cup_height * 0.5]);

// Inlet chamfer (ease the bean entry)
translate([0, 0, cup_height + funnel_height])
    cylinder(h=2, d1=inlet_diameter, d2=inlet_diameter-2, $fn=32);
