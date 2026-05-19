// Two-Stage Density Sorting Channel — Stage 2
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// *** REQUIRES TURBO BLOWER (300+ L/min) — 5015 INSUFFICIENT ***
// Fan: Turbo blower -> 25x10mm -> Medium vs Heavy separation
// Design: theta=25deg, v_air target 200-230cm/s
//
// v2 2026-05-17: Plenum moved BELOW channel, nozzles blow UPWARD through floor
// Previous: plenum was on side wall, nozzles blew sideways (rotate[90,0,0] error)
// Also fixed: stage2 baffle was entirely below channel floor (no escape path)
// Also fixed: nozzle dia 1.5mm -> 2.0mm for FDM printability

channel_L   = 120;
channel_W   = 25;
channel_H   = 10;
wall        = 2;
plenum_W    = 12;
plenum_H    = 6;
floor_H     = 1.5;
slope_deg   = 25;
baffle_H    = 3;

rotate([0, 0, slope_deg]) {
    difference() {
        // Outer shell
        translate([-channel_L/2, -channel_W/2, -(plenum_H + floor_H)])
            cube([channel_L, channel_W, channel_H + floor_H + plenum_H]);

        // Plenum cavity (bottom section)
        translate([-channel_L/2+wall, -channel_W/2+wall, -plenum_H-floor_H+wall])
            cube([channel_L-2*wall, channel_W-2*wall, plenum_H-wall]);

        // Channel interior (above floor)
        translate([-channel_L/2+wall, -channel_W/2+wall, floor_H])
            cube([channel_L-2*wall, channel_W-2*wall, channel_H]);
    }

    // Nozzle holes: vertical (Z-axis) through floor — 8x phi2mm
    for (i=[0:7]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/8);
        translate([x, 0, -plenum_H])
            cylinder(h=plenum_H + floor_H + 2, d=2.0, $fn=8);
    }

    // Air inlet: horizontal into plenum from front face
    translate([-channel_L/2-15, 0, -(plenum_H+floor_H)/2 - floor_H])
        rotate([90, 0, 0]) cylinder(h=20, d=8, $fn=16);

    // Top escape baffle (at channel TOP where beans can escape upward)
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, channel_H])
        cube([channel_L-4, baffle_H, baffle_H]);

    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-3],[ channel_L/2+3,-channel_W/2-3],
              [-channel_L/2-3, channel_W/2+3],[ channel_L/2+3, channel_W/2+3]])
        translate([pt[0], pt[1], -(plenum_H+floor_H)-2])
            cylinder(h=4, d=3.2, $fn=8);
}
echo("Stage-2 v2: 25x10mm, theta=25deg, TURBO BLOWER REQUIRED, plenum-below");
