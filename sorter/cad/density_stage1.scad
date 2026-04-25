// Two-Stage Density Sorting Channel — Stage 1
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// Fan: 5015 (120 L/min) -> 60x10mm -> 2-way separation
// Design: theta=20deg, PWM=80%, v_air~254cm/s

channel_L   = 120;
channel_W   = 60;
channel_H   = 10;
wall        = 2;
plenum_W    = 15;
slope_deg   = 20;
baffle_H    = 4;  // top baffle for light-bean escape

rotate([0, 0, slope_deg]) {
    difference() {
        translate([-channel_L/2, -channel_W/2-wall, 0])
            cube([channel_L, channel_W + 2*wall + plenum_W, channel_H]);
        translate([-channel_L/2+wall, -channel_W/2, wall])
            cube([channel_L-2*wall, channel_W, channel_H]);
        translate([-channel_L/2+wall, channel_W/2, wall])
            cube([channel_L-2*wall, plenum_W, channel_H]);
    }
    // Air inlet
    translate([-channel_L/2-12, channel_W/2+plenum_W/2, channel_H/2])
        rotate([90, 0, 0]) cylinder(h=15, d=8, $fn=16);
    // Nozzle holes 12x phi2mm
    for (i=[0:11]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/12);
        translate([x, channel_W/2-wall/2, channel_H-wall])
            rotate([90, 0, 0]) cylinder(h=plenum_W+2, d=2.0, center=true, $fn=8);
    }
    // Top escape baffle
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, 0])
        cube([channel_L-4, baffle_H, channel_H]);
    // Bottom guide ridge
    translate([-channel_L/2+2, -channel_W/2-0.25, 0])
        cube([channel_L-4, 0.5, 2]);
    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-wall-3],[ channel_L/2+3,-channel_W/2-wall-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2]) cylinder(h=4, d=3.2, $fn=8);
}
echo(str("Stage-1: 60x10mm, theta=20deg, 5015 fan, v_air~", 254, "cm/s @80% PWM"));
