// Inclined Density Sorting Channel
// HUSKY-SORTER-001 | Topic 4 Day 1 | 2026-04-14
// Design: 60×10mm channel (best for 5015 fan, 2-way separation)
// Future upgrade: turbo blower (300+L/min) for 3-way separation

channel_L = 120;
channel_W = 60;
channel_H = 10;
wall      = 2;
plenum_W  = 15;
slope_deg = 20;

rotate([0, 0, slope_deg]) {
    // Main body
    difference() {
        translate([-channel_L/2, -channel_W/2, 0])
            cube([channel_L, channel_W + plenum_W, channel_H]);
        translate([-channel_L/2+wall, -channel_W/2+wall, wall])
            cube([channel_L-2*wall, channel_W-wall, channel_H]);
        translate([-channel_L/2+wall, channel_W/2-wall, wall])
            cube([channel_L-2*wall, plenum_W-wall, channel_H]);
    }
    // Air inlet
    translate([-channel_L/2-15, channel_W/2+plenum_W/2, channel_H/2])
        rotate([90,0,0]) cylinder(h=15, d=8, $fn=16);
    // Nozzle holes (12x φ2mm along top)
    for (i=[0:11]) {
        x = -channel_L/2 + (i+0.5)*(channel_L/12);
        translate([x, channel_W/2-wall/2, channel_H-wall])
            rotate([90,0,0]) cylinder(h=plenum_W+2, d=2.0, center=true, $fn=8);
    }
    // Zone guide ridge
    translate([-channel_L/2+2, -channel_W/2+channel_W/2-0.25, 0])
        cube([channel_L-4, 0.5, 2]);
    // Mounting flanges (4x M3)
    for (pt=[[-channel_L/2-3,-channel_W/2-3],[ channel_L/2+3,-channel_W/2-3],
              [-channel_L/2-3, channel_W/2+plenum_W+3],[ channel_L/2+3, channel_W/2+plenum_W+3]])
        translate([pt[0], pt[1], channel_H-2])
            cylinder(h=4, d=3.2, $fn=8);
}
echo(str("Density Channel: ", channel_W, "x", channel_H, "mm, slope=", slope_deg, "deg"));
