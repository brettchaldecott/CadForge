---
name: Snap-Fit Design Patterns
category: pattern
technology: fdm
applies_to: [PLA, PETG, ABS, TPU]
tags: [pattern, snap-fit, assembly, clip, cantilever, fdm]
---

# Snap-Fit Design Patterns for 3D Printing

## Overview

Snap-fits are mechanical fastening features that allow parts to be assembled
without screws, glue, or tools. They rely on controlled deflection of a
flexible element to lock parts together. When designed correctly for FDM
printing, snap-fits provide fast, reliable, and repeatable assembly.

## Types of Snap-Fits

### 1. Cantilever Snap-Fit (Most Common)

A beam with a hook at the end that deflects during insertion and locks behind
a ledge on the mating part.

```
         ___________
        |           |  <-- hook (overhang)
        |    _______|
        |   |
        |   |  <-- cantilever beam
        |   |
   _____|   |_____
  |               |  <-- base
```

**Design parameters:**
- **Beam length**: 10--20 mm (longer = less force, more deflection)
- **Beam thickness**: 1.2--2.0 mm
- **Hook depth**: 0.5--1.5 mm (determines holding force)
- **Draft angle on hook**: 30--45 degrees for easy insertion
- **Retention angle**: 90 degrees for permanent, 30--45 degrees for releasable

### 2. Annular Snap-Fit

A ring or cylinder that snaps over a mating feature. Used for caps, lids, and
cylindrical enclosures.

**Design parameters:**
- **Interference**: 0.3--0.6 mm on diameter
- **Wall thickness**: 1.5--2.5 mm
- **Lead-in chamfer**: 0.5--1.0 mm at 45 degrees
- Material must have sufficient elongation (PETG or TPU preferred)

### 3. Torsion Snap-Fit

A feature that twists into position (bayonet-style lock). More complex to
design but provides very secure retention.

## Material Selection for Snap-Fits

| Material | Suitability | Max Strain (%) | Notes                     |
|----------|-------------|----------------|---------------------------|
| PLA      | Poor        | 2--3           | Too brittle, breaks easily|
| PETG     | Good        | 5--8           | Best balance for FDM      |
| ABS      | Good        | 5--7           | Good but warping concerns |
| TPU      | Excellent   | 30+            | Very flexible, low hold   |
| Nylon    | Excellent   | 15--30         | Best engineering choice   |

**Recommendation**: Use PETG for general snap-fits. Avoid PLA for anything that
must flex repeatedly.

## Cantilever Snap-Fit Design Formulas

### Maximum Deflection

```
y_max = (epsilon_max * L^2) / (1.5 * t)
```

Where:
- `y_max` = maximum deflection at tip (mm)
- `epsilon_max` = maximum allowable strain (material dependent)
- `L` = beam length (mm)
- `t` = beam thickness (mm)

### Insertion Force

```
F = (w * t^2 * E * y) / (6 * L^3) * (mu + tan(alpha)) / (1 - mu * tan(alpha))
```

Where:
- `w` = beam width (mm)
- `E` = elastic modulus (MPa)
- `y` = deflection (mm)
- `mu` = coefficient of friction (~0.3 for plastic on plastic)
- `alpha` = insertion angle (degrees)

## Print Orientation Rules

Snap-fits are highly sensitive to print orientation because FDM parts have
anisotropic strength (weak between layers).

1. **Print the beam flat** so layers run along the beam length -- this gives
   maximum flexibility and strength
2. **Never print the beam vertically** -- layers perpendicular to the beam will
   delaminate under flexion
3. If the beam must be vertical, increase thickness by 50% and reduce deflection

## Design Guidelines

| Parameter              | Value           | Notes                        |
|------------------------|-----------------|------------------------------|
| Beam length            | 10--20 mm       | Longer = gentler flex        |
| Beam thickness         | 1.2--2.0 mm     | 3--5 perimeters             |
| Beam width             | 3--8 mm         | Wider = more force           |
| Hook depth             | 0.5--1.5 mm     | Deeper = stronger hold       |
| Hook insertion angle   | 30--45 deg      | Gradual entry                |
| Hook retention angle   | 45--90 deg      | 90 = permanent lock          |
| Lead-in radius/chamfer | 0.5--1.0 mm     | Eases insertion              |
| Gap to mating surface  | 0.2--0.3 mm     | Clearance for FDM tolerance  |
| Fillet at beam root    | 0.5--1.0 mm     | Prevents stress concentration|

## Common Mistakes

1. **No fillet at beam root** -- stress concentrates at the base and the beam
   snaps off after a few cycles
2. **Too short beam** -- requires excessive force and strain, breaks immediately
3. **PLA snap-fits** -- PLA is too brittle for repeated flexing
4. **Wrong print orientation** -- layers perpendicular to flex direction fail
5. **No lead-in chamfer** -- makes assembly difficult and increases peak stress
6. **Ignoring tolerance** -- FDM tolerances mean the hook may not engage.
   Always test with a prototype

## Example: Simple Box Lid Clip

A cantilever clip for a rectangular box lid:
- Beam length: 15 mm
- Beam thickness: 1.5 mm (PETG)
- Beam width: 5 mm
- Hook depth: 1.0 mm
- Insertion angle: 45 degrees
- Retention angle: 60 degrees (releasable)
- Root fillet: 0.8 mm
- Clearance to box wall: 0.25 mm
