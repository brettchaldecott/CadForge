---
name: Prusa MK4
manufacturer: Prusa Research
technology: fdm
build_volume:
  x: 250
  y: 210
  z: 220
nozzle:
  installed: 0.4
  options: [0.25, 0.4, 0.6, 0.8]
materials:
  supported: [PLA, PETG, ABS, ASA, TPU, PA, PC]
  default: PLA
speed:
  max_print: 200
  recommended: 100
layer_height:
  min: 0.05
  max: 0.30
  default: 0.20
tolerances:
  xy: 0.15
  z: 0.10
  press_fit: -0.10
  sliding_fit: 0.20
constraints:
  min_wall_thickness: 0.8
  max_overhang_angle: 50
  max_bridge_length: 25
heated_bed: true
max_bed_temp: 120
max_nozzle_temp: 300
auto_bed_leveling: true
filament_sensor: true
enclosure: false
direct_drive: true
tags: [printer, fdm, prusa, mk4, open-source]
---

# Prusa MK4

## Overview

The Prusa MK4 is a direct-drive, open-frame FDM printer from Prusa Research.
It features the custom Nextruder with a planetary gear extruder, load cell bed
leveling, and input shaping for high-speed printing. The MK4 is widely regarded
as one of the most reliable and well-supported consumer 3D printers.

## Key Features

- **Nextruder**: direct-drive extruder with 10:1 planetary gear ratio for
  precise filament control and high grip force
- **Load cell leveling**: measures nozzle-to-bed distance through force sensing,
  eliminating the need for a separate probe
- **Input shaping**: accelerometer-based resonance compensation allows printing
  at up to 200 mm/s with minimal ringing artifacts
- **32-bit xBuddy board**: powerful control board with silent TMC2209 drivers
- **PrusaSlicer integration**: profiles tuned by the manufacturer
- **Open-source**: firmware and hardware designs are publicly available

## Build Volume

- **X**: 250 mm
- **Y**: 210 mm
- **Z**: 220 mm
- **Usable volume**: approximately 250 x 210 x 220 mm with standard nozzle

## Print Quality

| Setting               | Value           | Notes                         |
|-----------------------|-----------------|-------------------------------|
| Min layer height      | 0.05 mm         | With 0.25 mm nozzle           |
| Default layer height  | 0.20 mm         | Best speed/quality balance     |
| Max layer height      | 0.30 mm         | Draft prints                   |
| XY accuracy           | +/- 0.15 mm     | Well-calibrated                |
| Z accuracy            | +/- 0.10 mm     | Consistent layer stacking      |
| Surface finish        | Excellent        | Smooth with proper settings    |

## Material Compatibility

| Material | Support Level | Notes                                  |
|----------|---------------|----------------------------------------|
| PLA      | Excellent     | Primary material, perfect profiles     |
| PETG     | Excellent     | Great results with textured PEI sheet  |
| ABS      | Good          | Needs enclosure for large parts        |
| ASA      | Good          | UV-resistant ABS alternative           |
| TPU      | Good          | Direct drive handles flex well         |
| PA       | Fair          | Requires dry box and enclosure         |
| PC       | Fair          | High temp, needs enclosure             |

## Recommended Settings for CadForge

When generating STL files for the Prusa MK4:
- Design for 0.4 mm nozzle (default)
- Minimum wall thickness: 0.8 mm (2 perimeters)
- Hole compensation: +0.2 mm on diameter
- Press-fit interference: -0.10 mm
- Sliding fit clearance: +0.20 mm
- Max unsupported overhang: 50 degrees (good cooling)
- Max bridge span: 25 mm

## Limitations

- No enclosure by default -- limits ABS/PA/PC printing
- Single extruder (no multi-material without MMU3 add-on)
- Open frame means environmental sensitivity (drafts, temperature)
- Build plate slightly smaller than competitors in the price range
