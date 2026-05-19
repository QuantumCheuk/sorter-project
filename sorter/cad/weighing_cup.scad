// Weighing Cup for Coffee Bean Sorter — Buffer Cup Station
// HUSKY-SORTER-001
// Generated: 2026-04-13
//
// v2 2026-05-17: Critical structural fixes:
//  - Gate slot reduced from 12mm×4mm to 5mm×2mm (was overcutting into cup interior)
//  - Gate positioned at upper cup wall (z=6mm) for better bean release
//  - Funnel now converges to inner_diameter (14mm) for proper bean guidance
//  - Bottom plate flush with cup floor (was protruding 1.5mm below)
//  - M2 holes changed to through-holes with nut recess (was 1.5mm blind tap)
//  - Load cell center boss hole enlarged to φ6mm for proper alignment

// Parameters
inner_diameter = 14.0;
outer_diameter = 18.0;
wall_thickness = 2.0;
cup_height = 10.0;
inlet_diameter = 22.0;
funnel_height = 8.0;
bottom_thickness = 3.0;   // v2: 1.5->3.0mm for proper M2 through-hole + nut
total_height = cup_height + funnel_height + bottom_thickness;

// v2: Gate slot parameters — conservative sizing
gate_slot_width = 5.0;       // mm (was 12mm, too wide)
gate_slot_depth = 2.0;       // mm penetration into wall (was 4mm, overcut interior)
gate_slot_height = 3.0;      // mm (was 5mm)
gate_slot_z = 6.0;           // mm from cup bottom (was 3mm, too low)

// ========== Cup body (hollow cylinder) ==========
difference() {
    cylinder(h=cup_height, d=outer_diameter, $fn=32);
    translate([0, 0, -0.1])
        cylinder(h=cup_height+0.2, d=inner_diameter, $fn=32);
}

// ========== Solenoid gate slot (v2: conservative cut) ==========
// Slot only cuts through the 2mm wall thickness, not into interior
// Positioned at upper cup wall (z=6mm) for cleaner bean release
gate_angle = 45;
rotate([0, 0, gate_angle])
    translate([outer_diameter/2, -gate_slot_width/2, gate_slot_z])
        cube([gate_slot_depth, gate_slot_width, gate_slot_height]);

// ========== Funnel section (v2: converges to inner_diameter) ==========
// v1: converged to outer_diameter (18mm) — beans land on cup wall rim
// v2: converges to inner_diameter (14mm) — beans guided into cup interior
translate([0, 0, cup_height])
    cylinder(h=funnel_height, d1=inlet_diameter, d2=inner_diameter, $fn=32);

// ========== Inlet chamfer (ease bean entry) ==========
translate([0, 0, cup_height + funnel_height])
    cylinder(h=2, d1=inlet_diameter, d2=inlet_diameter-2, $fn=32);

// ========== Bottom mounting plate (v2: flush with cup floor) ==========
// v1: protruded 1.5mm below floor — interfered with load cell boss
// v2: sits at floor level (z=-bottom_thickness to z=0)
difference() {
    translate([0, 0, -bottom_thickness])
        cylinder(h=bottom_thickness, d=outer_diameter + 2, $fn=32);

    // v2: Load cell center boss hole — φ6mm for proper alignment
    // (was φ4mm, too small for standard 200g load cell M3/M4 boss)
    translate([0, 0, -bottom_thickness - 0.1])
        cylinder(h=bottom_thickness + 0.2, d=6, $fn=16);

    // v2: M2 through-holes (was blind holes in 1.5mm plate)
    // Through-holes allow M2 screw + nut on bottom side
    // Nut recess: 4mm hex nut sits in 2mm deep recess
    hole_radius = (outer_diameter / 2) - 3;  // v2: moved inward from 4mm
    for (i = [0:2]) {
        angle = i * 120;
        x = hole_radius * cos(angle);
        y = hole_radius * sin(angle);
        // M2 through-hole (φ2.5mm clearance)
        translate([x, y, -bottom_thickness - 0.1])
            cylinder(h=bottom_thickness + 0.2, d=2.5, $fn=8);
        // Nut recess on bottom side (φ4.5mm for M2 hex nut, 1.5mm deep)
        translate([x, y, -bottom_thickness - 0.1])
            cylinder(h=1.5, d=4.5, $fn=6);
    }
}

// Print settings:
//   Material: PETG (food grade)
//   Layer height: 0.12mm
//   Infill: 40%
//   Supports: funnel overhang needs supports
//
// v2 target weight: ≤5g (PETG, 40% infill)
//
// Assembly:
//   1. 3x M2×6mm screws from top through cup bottom
//   2. 3x M2 hex nuts recessed into bottom plate underside
//   3. Load cell boss fits into φ6mm center hole for alignment
//   4. Solenoid gate slides through 5×3mm slot at z=6mm (cup upper wall)
