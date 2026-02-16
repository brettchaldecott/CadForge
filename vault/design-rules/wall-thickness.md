---
name: Wall Thickness Guidelines
category: design-rule
technology: fdm
applies_to: [PLA, PETG, ABS, TPU]
tags: [design-rule, wall-thickness, perimeter, fdm, structural]
---

# Wall Thickness Guidelines for FDM Printing

## Overview

Wall thickness in FDM printing is determined by the number of perimeter lines
(shells) multiplied by the extrusion width. Choosing the correct wall thickness
ensures structural integrity, printability, and dimensional accuracy. Walls that
are too thin will be fragile or unprintable; walls that are too thick waste
material and print time.

## Fundamental Formula

```
wall_thickness = number_of_perimeters * extrusion_width
```

For a 0.4 mm nozzle with default extrusion width (typically 100--120% of nozzle
diameter):

| Perimeters | Wall Thickness | Use Case                       |
|------------|----------------|--------------------------------|
| 1          | 0.4--0.48 mm   | Non-structural, thin features  |
| 2          | 0.8--0.96 mm   | Minimum for functional parts   |
| 3          | 1.2--1.44 mm   | Standard structural wall       |
| 4          | 1.6--1.92 mm   | Heavy-duty structural          |
| 5+         | 2.0+ mm        | Maximum strength, thick shells |

## Per-Nozzle Recommendations

| Nozzle (mm) | Min Wall (mm) | Recommended Wall (mm) | Strong Wall (mm) |
|-------------|---------------|-----------------------|-------------------|
| 0.25        | 0.5           | 0.75                  | 1.0               |
| 0.4         | 0.8           | 1.2                   | 1.6               |
| 0.6         | 1.2           | 1.8                   | 2.4               |
| 0.8         | 1.6           | 2.4                   | 3.2               |

## Per-Material Minimum Walls

| Material | Absolute Min (mm) | Recommended Min (mm) | Notes              |
|----------|--------------------|-----------------------|--------------------|
| PLA      | 0.8               | 1.2                   | Stiff but brittle  |
| PETG     | 0.8               | 1.2                   | More forgiving     |
| ABS      | 1.2               | 1.6                   | Warping adds stress|
| TPU      | 1.2               | 1.6                   | Flexible, needs mass|

## Design Rules

### Uniform Wall Thickness
- Keep wall thickness consistent throughout the part where possible
- Sudden thickness changes cause uneven cooling and internal stresses
- Transition between thick and thin sections gradually (taper over 3--5x the
  thickness difference)

### Aligning Walls to Extrusion Width
- Design wall thickness as an integer multiple of extrusion width
- Non-multiple thicknesses create gaps between perimeters or trigger thin-wall
  gap fill, both of which reduce quality
- Example: with 0.4 mm nozzle, use 0.8, 1.2, 1.6 mm -- avoid 1.0, 1.5 mm

### Structural Walls
- For load-bearing walls, use at least 3 perimeters (1.2 mm at 0.4 mm nozzle)
- Add ribs or gussets to thin walls instead of making them thicker
- T-shaped or L-shaped cross-sections are stiffer than flat walls

### Thin Wall Considerations
- Single-perimeter walls (0.4 mm) are fragile and prone to layer splitting
- Avoid single-perimeter walls on functional parts
- If thin walls are required, orient them perpendicular to the build plate for
  maximum strength

## Wall Strength vs. Infill

For most prints, increasing wall count is more effective than increasing infill:

| Configuration          | Relative Strength | Print Time |
|------------------------|-------------------|------------|
| 2 walls, 20% infill   | Baseline          | Baseline   |
| 3 walls, 20% infill   | +40% stronger     | +10% time  |
| 2 walls, 50% infill   | +25% stronger     | +30% time  |
| 4 walls, 15% infill   | +60% stronger     | +15% time  |

The outer perimeters carry most of the load. Adding walls is almost always more
efficient than adding infill for strength.

## Feature-Specific Guidelines

| Feature           | Min Thickness (mm) | Notes                         |
|-------------------|--------------------|-------------------------------|
| Enclosure walls   | 1.2                | 3 perimeters standard         |
| Snap-fit arms     | 1.2--2.0           | Need flexibility and strength |
| Screw bosses      | 2.0--3.0           | Must resist hoop stress       |
| Living hinges     | 0.4--0.8           | PLA too brittle, use PETG/TPU |
| Gear teeth        | 1.2+               | Depends on module             |
| Press-fit sockets | 1.6+               | Resist expansion forces       |
