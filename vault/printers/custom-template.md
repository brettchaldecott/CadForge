---
name: My Custom Printer
manufacturer: Unknown
technology: fdm
build_volume:
  x: 220
  y: 220
  z: 250
nozzle:
  installed: 0.4
  options: [0.4]
materials:
  supported: [PLA, PETG]
  default: PLA
speed:
  max_print: 100
  recommended: 60
layer_height:
  min: 0.08
  max: 0.30
  default: 0.20
tolerances:
  xy: 0.20
  z: 0.15
  press_fit: -0.15
  sliding_fit: 0.25
constraints:
  min_wall_thickness: 1.0
  max_overhang_angle: 45
  max_bridge_length: 15
heated_bed: true
max_bed_temp: 100
max_nozzle_temp: 260
auto_bed_leveling: false
filament_sensor: false
enclosure: false
direct_drive: false
tags: [printer, fdm, custom]
---

# Custom Printer Template

## Overview

This is a template for adding your own printer to the CadForge vault. Copy this
file, rename it to match your printer (e.g., `my-printer-name.md`), and fill in
the values below based on your printer's specifications and your calibration
results.

## How to Use This Template

1. Copy this file: `cp custom-template.md my-printer.md`
2. Update the YAML frontmatter with your printer's specifications
3. Calibrate your printer and update the tolerance values
4. Add any material-specific notes based on your experience

## Frontmatter Field Reference

### Required Fields

| Field                          | Description                              |
|--------------------------------|------------------------------------------|
| `name`                         | Human-readable printer name              |
| `manufacturer`                 | Printer manufacturer                     |
| `technology`                   | Printing technology (fdm, sla, etc.)     |
| `build_volume.x/y/z`          | Build volume in mm                       |
| `nozzle.installed`             | Currently installed nozzle diameter (mm) |
| `nozzle.options`               | Available nozzle sizes                   |
| `materials.supported`          | List of compatible material names        |
| `materials.default`            | Default material for this printer        |
| `speed.max_print`              | Maximum advertised speed (mm/s)          |
| `speed.recommended`            | Practical recommended speed (mm/s)       |
| `layer_height.min/max/default` | Layer height range and default (mm)      |

### Tolerance Fields (Calibrate These)

| Field                    | Description                                  |
|--------------------------|----------------------------------------------|
| `tolerances.xy`          | XY dimensional accuracy (+/- mm)             |
| `tolerances.z`           | Z dimensional accuracy (+/- mm)              |
| `tolerances.press_fit`   | Interference for press-fits (negative = tight)|
| `tolerances.sliding_fit` | Clearance for sliding fits (positive = loose) |

### Constraint Fields

| Field                              | Description                          |
|------------------------------------|--------------------------------------|
| `constraints.min_wall_thickness`   | Minimum printable wall thickness (mm)|
| `constraints.max_overhang_angle`   | Max angle from vertical without support (deg)|
| `constraints.max_bridge_length`    | Max horizontal bridge span (mm)      |

### Optional Fields

| Field              | Description                                      |
|--------------------|--------------------------------------------------|
| `heated_bed`       | Whether the printer has a heated bed (true/false) |
| `max_bed_temp`     | Maximum bed temperature (C)                       |
| `max_nozzle_temp`  | Maximum nozzle temperature (C)                    |
| `auto_bed_leveling`| Automatic bed leveling available (true/false)     |
| `filament_sensor`  | Filament runout sensor present (true/false)       |
| `enclosure`        | Whether the printer is enclosed (true/false)      |
| `direct_drive`     | Direct drive extruder (true) or Bowden (false)    |

## Calibrating Tolerances

To determine accurate tolerance values for your printer:

### XY Tolerance Test
1. Print a calibration cube (20 x 20 x 20 mm)
2. Measure X and Y dimensions with calipers
3. `tolerances.xy` = max(|measured_x - 20|, |measured_y - 20|)

### Z Tolerance Test
1. Use the same calibration cube
2. Measure Z height
3. `tolerances.z` = |measured_z - 20|

### Press-Fit Calibration
1. Print a test block with holes from 9.80 to 10.00 mm in 0.05 mm steps
2. Test a 10.00 mm pin in each hole
3. The hole that gives a snug press-fit determines your `tolerances.press_fit`
4. Example: if 9.90 mm hole is snug, `press_fit = -0.10`

### Sliding-Fit Calibration
1. Print a test block with holes from 10.10 to 10.40 mm in 0.05 mm steps
2. Test a 10.00 mm pin in each hole
3. The hole that gives free movement determines your `tolerances.sliding_fit`
4. Example: if 10.25 mm hole slides freely, `sliding_fit = 0.25`

## Notes

Add your printer-specific notes, tips, and observations here. Include any
quirks, firmware settings, or slicer profile recommendations that affect
part quality.
