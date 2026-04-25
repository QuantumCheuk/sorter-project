// Two-Stage Density Sorting Channel — Stage 2
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// *** REQUIRES TURBO BLOWER (300+ L/min) — 5015 INSUFFICIENT ***
// Fan: Turbo blower -> 25x10mm -> Medium vs Heavy separation
// Design: theta=25deg, v_air target 200-230cm/s

channel_L   = 120;
channel_W   = 25;
channel_H   = 10;
wall        = 2;
plenum_W    = 12;
slope_deg   = 25;
baffle_H    = 3;

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
    // Nozzle holes 8x phi1.5mm
    for (i=[0:7]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/8);
        translate([x, channel_W/2-wall/2, channel_H-wall])
            rotate([90, 0, 0]) cylinder(h=plenum_W+2, d=1.5, center=true, $fn=8);
    }
    // Top escape baffle
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, 0])
        cube([channel_L-4, baffle_H, channel_H]);
    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-wall-3],[ channel_L/2+3,-channel_W/2-wall-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2]) cylinder(h=4, d=3.2, $fn=8);
}
echo("Stage-2: 25x10mm, theta=25deg, TURBO BLOWER REQUIRED");
