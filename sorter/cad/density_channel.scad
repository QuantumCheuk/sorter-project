
// Density Sorting Channel - Air Lift Design
// HUSKY-SORTER-001 / Topic 4 Day 1
// Generated: 2026-04-13

// Parameters
channel_length = 120;
channel_width = 20;
channel_height = 80;
wall = 2;
outlet_height = 15;

// Air plenum (side chamber for uniform air distribution)
plenum_width = 10;
plenum_height = channel_height;

// Nozzle holes (8 holes along bottom, 2mm diameter)
nozzle_count = 8;
nozzle_dia = 2.0;

// Inlet tube (from fan)
inlet_dia = 8;
inlet_length = 15;

// Main channel body
difference() {
    // Outer shell
    translate([-channel_length/2, -channel_width/2, 0])
        cube([channel_length, channel_width, channel_height]);
    
    // Inner cavity
    translate([-channel_length/2 + wall, -channel_width/2 + wall, wall])
        cube([channel_length - 2*wall, channel_width - 2*wall, channel_height]);
    
    // Bottom air plenum (air inlet from side)
    translate([-channel_length/2, channel_width/2])
        cube([channel_length, plenum_width, channel_height]);
}

// Air plenum - connect inlet to distribution holes
// (simplified, would be integrated in print)

// Inlet tube
translate([-channel_length/2 - inlet_length, 0, channel_height/2])
    rotate([90, 0, 0])
        cylinder(h=inlet_length+5, d=inlet_dia, center=false);

// Collection zone dividers
// Light beans exit at top, heavy at bottom
// We have 3 zones: top (light), middle (medium), bottom (heavy)

// Zone divider lines (guide ridges, not walls)
for (i = [1:2]) {
    y_pos = -channel_width/2 + i * (channel_width / 3);
    translate([-channel_length/2 + 2, y_pos, 0])
        cube([channel_length - 4, 0.5, 2]);
}

// Mounting holes (4x M3, for frame attachment)
mount_positions = [
    [-channel_length/2 + 5, -channel_width/2 - 3],
    [ channel_length/2 - 5, -channel_width/2 - 3],
    [-channel_length/2 + 5,  channel_width/2 + plenum_width + 3],
    [ channel_length/2 - 5,  channel_width/2 + plenum_width + 3]
];
for (pos = mount_positions) {
    translate([pos[0], pos[1], channel_height - 2])
        cylinder(h=4, d=3.2, $fn=8);
}

echo("=== Density Channel Design ===");
echo(str("Channel: ", channel_length, "x", channel_width, "x", channel_height, " mm"));
echo(str("Air plenum: ", channel_width, "x", plenum_width, "x", channel_height, " mm"));
echo(str("Collection zones: TOP (light) / MIDDLE (medium) / BOTTOM (heavy)"));
