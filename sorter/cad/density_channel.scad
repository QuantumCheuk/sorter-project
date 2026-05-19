// Inclined Density Sorting Channel
// HUSKY-SORTER-001 | Topic 4 Day 1 | 2026-04-14
// Design: 60×10mm channel (best for 5015 fan, 2-way separation)
// Future upgrade: turbo blower (300+L/min) for 3-way separation
//
// v2 2026-05-17: Plenum moved BELOW channel, nozzles blow UPWARD through floor
// Previous: plenum was on side wall, nozzles blew sideways (rotate[90,0,0] error)

channel_L = 120;
channel_W = 60;
channel_H = 10;
wall      = 2;
plenum_W  = 15;
plenum_H  = 6;
floor_H   = 1.5;
slope_deg = 20;

rotate([0, 0, slope_deg]) {
    // Outer body: plenum below + channel above, separated by floor
    // Local z=0 is bottom of plenum; channel floor at z=plenum_H to z=plenum_H+floor_H
    translate([-channel_L/2, -channel_W/2, -(plenum_H + floor_H)])
        cube([channel_L, channel_W, channel_H + floor_H + plenum_H]);

    difference() {
        // Outer shell
        translate([-channel_L/2, -channel_W/2, -(plenum_H + floor_H)])
            cube([channel_L, channel_W, channel_H + floor_H + plenum_H]);

        // Plenum cavity (bottom section, below floor)
        translate([-channel_L/2+wall, -channel_W/2+wall, -plenum_H-floor_H+wall])
            cube([channel_L-2*wall, channel_W-2*wall, plenum_H-wall]);

        // Channel interior (above floor)
        translate([-channel_L/2+wall, -channel_W/2+wall, floor_H])
            cube([channel_L-2*wall, channel_W-2*wall, channel_H]);
    }

    // Nozzle holes: vertical (Z-axis) through floor, connecting plenum to channel
    // Each nozzle is a vertical cylinder punching through the floor layer
    for (i=[0:11]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/12);
        translate([x, 0, -plenum_H])
            cylinder(h=plenum_H + floor_H + 2, d=2.0, $fn=8);
    }

    // Air inlet: horizontal cylinder from front face into plenum
    translate([-channel_L/2-15, 0, -(plenum_H+floor_H)/2 - floor_H])
        rotate([90, 0, 0]) cylinder(h=20, d=8, $fn=16);

    // Zone guide ridge
    translate([-channel_L/2+2, -channel_W/2+channel_W/2-0.25, 0])
        cube([channel_L-4, 0.5, 2]);

    // Mounting flanges (4x M3)
    for (pt=[[-channel_L/2-3,-channel_W/2-3],[ channel_L/2+3,-channel_W/2-3],
              [-channel_L/2-3, channel_W/2+3],[ channel_L/2+3, channel_W/2+3]])
        translate([pt[0], pt[1], -(plenum_H+floor_H)-2])
            cylinder(h=4, d=3.2, $fn=8);
}
echo(str("Density Channel v2: ", channel_W, "x", channel_H, "mm, slope=", slope_deg, "deg, plenum-below"));
