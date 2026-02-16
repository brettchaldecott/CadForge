---
name: Dimensional Tolerances
category: design-rule
technology: fdm
applies_to: [PLA, PETG, ABS, TPU]
tags: [design-rule, tolerance, fit, clearance, fdm, precision]
---

# Dimensional Tolerances for FDM Printing

## Overview

FDM 3D printing achieves dimensional accuracy of approximately +/- 0.1 to
+/- 0.3 mm depending on the printer, material, and calibration. Understanding
these tolerances is essential for designing parts that fit together, accept
fasteners, or mate with off-the-shelf components.

## General Dimensional Accuracy

| Printer Class       | XY Accuracy (mm) | Z Accuracy (mm) | Notes             |
|---------------------|-------------------|------------------|-------------------|
| Budget (Ender 3)    | +/- 0.2--0.3     | +/- 0.15         | After calibration |
| Mid-range (MK4, A1) | +/- 0.1--0.2     | +/- 0.10         | Well-calibrated   |
| High-end (Voron)    | +/- 0.05--0.15   | +/- 0.05         | Tuned and enclosed|

## Fit Types for FDM

### Press Fit (Interference Fit)
The hole is smaller than the shaft -- parts are forced together and held by
friction.

| Parameter            | Value (mm)   | Notes                          |
|----------------------|--------------|--------------------------------|
| Interference         | -0.1 to -0.2| Hole undersized by this amount |
| PLA recommendation   | -0.1         | Brittle, less interference     |
| PETG recommendation  | -0.15        | Some flex absorbs stress       |
| ABS recommendation   | -0.15        | Shrinkage may require tuning   |
| Min wall around hole | 2.0 mm       | Prevent cracking               |

Example: for a 10 mm shaft, design the hole at 9.85--9.90 mm diameter.

### Sliding Fit (Clearance Fit)
Parts move freely relative to each other. Used for pivots, guides, and
removable covers.

| Parameter            | Value (mm)   | Notes                          |
|----------------------|--------------|--------------------------------|
| Clearance            | +0.2 to +0.3| Hole oversized by this amount  |
| PLA recommendation   | +0.2         | Low shrinkage, predictable     |
| PETG recommendation  | +0.25        | Slight stringing in holes      |
| ABS recommendation   | +0.3         | Higher shrinkage               |

Example: for a 10 mm shaft, design the hole at 10.2--10.3 mm diameter.

### Transition Fit
Parts can be assembled by hand with moderate force. Used for alignment pins and
locating features.

| Parameter            | Value (mm)   | Notes                          |
|----------------------|--------------|--------------------------------|
| Clearance            | +0.05 to +0.15 | Snug but removable          |
| Recommended          | +0.1         | Works for most printers        |

### Loose Fit
Parts move freely with noticeable play. Used for hinges and pivots where
friction must be minimized.

| Parameter            | Value (mm)   | Notes                          |
|----------------------|--------------|--------------------------------|
| Clearance            | +0.3 to +0.5| Generous gap                   |

## Hole Diameter Compensation

FDM holes tend to print undersized because the circular toolpath pulls inward.
Apply these compensations:

| Hole Diameter (mm) | Add to Diameter (mm) | Notes                       |
|---------------------|----------------------|-----------------------------|
| < 3                 | +0.3                 | Small holes shrink the most |
| 3--10               | +0.2                 | Standard compensation       |
| 10--20              | +0.15                | Less relative error         |
| > 20                | +0.1                 | Minimal compensation needed |

For precision holes, drill or ream to final size after printing.

## Axis-Specific Considerations

- **XY plane**: accuracy depends on belt tension, stepper resolution, flow rate
- **Z axis**: accuracy depends on layer height, first layer squish, thermal
  expansion
- **Holes in Z (vertical)**: most accurate -- circular toolpath
- **Holes in XY (horizontal)**: least accurate -- oval due to layer stacking.
  Use teardrop shape or oversize by +0.3 mm

## Fastener Clearances

| Fastener   | Nominal (mm) | Close Fit Hole (mm) | Free Fit Hole (mm) |
|------------|--------------|---------------------|---------------------|
| M2 screw   | 2.0          | 2.2                 | 2.6                 |
| M2.5 screw | 2.5          | 2.7                 | 3.1                 |
| M3 screw   | 3.0          | 3.2                 | 3.6                 |
| M4 screw   | 4.0          | 4.3                 | 4.8                 |
| M5 screw   | 5.0          | 5.3                 | 5.8                 |
| M6 screw   | 6.0          | 6.4                 | 7.0                 |

## Tips for Achieving Good Tolerances

1. **Calibrate flow rate** -- over-extrusion is the #1 cause of tight holes
2. **Print a tolerance test** -- print a test piece with various hole and peg
   sizes to establish your printer's actual tolerance
3. **Orient precision features vertically** -- Z resolution is typically better
   than XY for cylindrical features
4. **Account for elephant's foot** -- the first 1--2 layers spread wider due to
   bed squish. Chamfer bottom edges of mating parts
5. **Material matters** -- ABS shrinks more than PLA; compensate accordingly
6. **Post-process critical dimensions** -- drill, ream, or sand to final size
