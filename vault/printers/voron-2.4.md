---
name: Voron 2.4
manufacturer: Voron Design (Community/Self-sourced)
technology: fdm
build_volume:
  x: 350
  y: 350
  z: 340
nozzle:
  installed: 0.4
  options: [0.25, 0.4, 0.5, 0.6, 0.8]
materials:
  supported: [PLA, PETG, ABS, ASA, TPU, PA, PC, PPA-CF, PA6-CF]
  default: ABS
speed:
  max_print: 500
  recommended: 200
layer_height:
  min: 0.04
  max: 0.30
  default: 0.20
tolerances:
  xy: 0.08
  z: 0.05
  press_fit: -0.08
  sliding_fit: 0.15
constraints:
  min_wall_thickness: 0.8
  max_overhang_angle: 50
  max_bridge_length: 25
heated_bed: true
max_bed_temp: 120
max_nozzle_temp: 300
auto_bed_leveling: true
filament_sensor: true
enclosure: true
direct_drive: true
tags: [printer, fdm, voron, corexy, enclosed, high-performance, diy]
---

# Voron 2.4

## Overview

The Voron 2.4 is a community-designed, self-sourced CoreXY enclosed 3D printer
known for exceptional precision, speed, and material versatility. It is the
reference design for high-performance DIY printers. The Voron 2.4 uses a flying
gantry (bed stays stationary) which enables excellent Z-axis consistency and
supports the full range of engineering filaments.

## Key Features

- **Flying gantry CoreXY**: stationary heated bed with moving gantry for
  exceptional Z consistency on tall prints
- **Full enclosure**: sealed chamber with filtered exhaust, maintains 60+ C
  ambient for ABS/PA/PC
- **Klipper firmware**: pressure advance, input shaping, and CANBUS support
- **Voron Tap / Klicky probe**: accurate Z probing through nozzle or magnetic
  probe
- **Stealthburner toolhead**: direct drive with integrated LEDs and
  high-flow hotend options
- **Multiple build sizes**: 250, 300, and 350 mm variants
- **Open-source**: complete BOM, STLs, and documentation available

## Build Volume (350 mm Variant)

- **X**: 350 mm
- **Y**: 350 mm
- **Z**: 340 mm
- **Usable volume**: 350 x 350 x 340 mm (largest standard variant)

Other variants: 250 x 250 x 230 mm, 300 x 300 x 290 mm.

## Print Quality

| Setting               | Value           | Notes                         |
|-----------------------|-----------------|-------------------------------|
| Min layer height      | 0.04 mm         | Achievable with proper tuning  |
| Default layer height  | 0.20 mm         | Standard quality               |
| Max layer height      | 0.30 mm         | Fast functional prints         |
| XY accuracy           | +/- 0.08 mm     | Best-in-class when tuned       |
| Z accuracy            | +/- 0.05 mm     | Stationary bed = consistent Z  |
| Surface finish        | Excellent        | Comparable to semi-industrial  |

## Material Compatibility

| Material   | Support Level | Notes                                |
|------------|---------------|--------------------------------------|
| PLA        | Excellent     | Though enclosure can cause heat creep|
| PETG       | Excellent     | Open doors slightly for PLA/PETG     |
| ABS        | Excellent     | The Voron's natural habitat          |
| ASA        | Excellent     | Enclosed + filtered exhaust          |
| TPU        | Good          | Direct drive Stealthburner           |
| PA (Nylon) | Excellent     | Dry box feed + enclosed chamber      |
| PC         | Excellent     | High chamber temp handles PC         |
| PA6-CF     | Excellent     | With hardened nozzle (Revo, CHT)     |
| PPA-CF     | Good          | Pushes chamber temp limits           |

## Recommended Settings for CadForge

When generating STL files for the Voron 2.4:
- Design for 0.4 mm nozzle (default, many run hardened)
- Minimum wall thickness: 0.8 mm (2 perimeters)
- Hole compensation: +0.15 mm on diameter (high precision)
- Press-fit interference: -0.08 mm (tighter tolerances achievable)
- Sliding fit clearance: +0.15 mm
- Max unsupported overhang: 50 degrees
- Max bridge span: 25 mm
- Can handle the largest build volumes (350 mm)

## Tuning and Calibration

The Voron 2.4 achieves its best-in-class tolerances through extensive tuning:

1. **Input shaping**: accelerometer-measured resonance compensation
2. **Pressure advance**: calibrated per-filament for clean corners
3. **Belt tension**: matched A/B belts using frequency analysis
4. **Z offset**: nozzle-based probing (Tap) for precise first layers
5. **Flow calibration**: per-material flow rate tuning
6. **Frame squareness**: critical during build -- measured with calipers

## Limitations

- **Self-sourced and self-built**: requires mechanical aptitude and 40--80 hours
  to build
- **No commercial support**: community-only troubleshooting
- **Cost**: $800--1500 for a quality kit or self-sourced build
- **Heat creep with PLA**: enclosed chamber can be too hot for PLA; open doors
- **Ongoing maintenance**: DIY design requires periodic maintenance and tuning
- **Learning curve**: Klipper configuration requires technical comfort
- **Quality depends on builder**: a poorly-built Voron performs poorly
