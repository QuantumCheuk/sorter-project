// Two-Stage Density Sorting Channel — Stage 1
// HUSKY-SORTER-001 | Topic 4 Day 2 | 2026-04-14
// Fan: 5015 (120 L/min) -> 60x10mm -> 2-way separation
// Design: theta=20deg, PWM=80%, v_air~254cm/s
//
// v2 2026-05-17: Plenum moved BELOW channel, nozzles blow UPWARD through floor
// Previous: plenum was on side wall, nozzles blew sideways (rotate[90,0,0] error)

channel_L   = 120;
channel_W   = 60;
channel_H   = 10;
wall        = 2;
plenum_W    = 15;
plenum_H    = 6;
floor_H     = 1.5;
slope_deg   = 20;
baffle_H    = 4;  // top baffle for light-bean escape

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

    // Nozzle holes: vertical (Z-axis) through floor — 12x phi2mm
    for (i=[0:11]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/12);
        translate([x, 0, -plenum_H])
            cylinder(h=plenum_H + floor_H + 2, d=2.0, $fn=8);
    }

    // Air inlet: horizontal into plenum from front face
    translate([-channel_L/2-15, 0, -(plenum_H+floor_H)/2 - floor_H])
        rotate([90, 0, 0]) cylinder(h=20, d=8, $fn=16);

    // Top escape baffle (at channel TOP, not bottom)
    translate([-channel_L/2+2, -channel_W/2-wall-baffle_H, channel_H])
        cube([channel_L-4, baffle_H, baffle_H]);

    // Bottom guide ridge
    translate([-channel_L/2+2, -channel_W/2-0.25, 0])
        cube([channel_L-4, 0.5, 2]);

    // Mounting flanges 4x M3
    for (pt=[[-channel_L/2-3,-channel_W/2-3],[ channel_L/2+3,-channel_W/2-3],
              [-channel_L/2-3, channel_W/2+3],[ channel_L/2+3, channel_W/2+3]])
        translate([pt[0], pt[1], -(plenum_H+floor_H)-2])
            cylinder(h=4, d=3.2, $fn=8);
}
echo(str("Stage-1 v2: 60x10mm, theta=20deg, 5015 fan, v_air~", 254, "cm/s @80% PWM, plenum-below"));
