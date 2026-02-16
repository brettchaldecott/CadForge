---
name: Press-Fit Design for 3D Printing
category: pattern
technology: fdm
applies_to: [PLA, PETG, ABS]
tags: [pattern, press-fit, interference, bearing, shaft, fdm]
---

# Press-Fit Design for 3D Printed Parts

## Overview

A press-fit (interference fit) joins two parts by making one slightly larger
than the opening it is pressed into. The elastic deformation of the surrounding
material creates a friction-based grip that holds the parts together without
fasteners. Press-fits are widely used for inserting bearings, shafts, pins, and
bushings into 3D-printed housings.

## How Press-Fits Work in FDM

FDM parts behave differently from machined metal parts in press-fit applications:

1. **Anisotropic strength** -- layer bonding is weaker than in-plane strength
2. **Surface roughness** -- layer lines create a textured bore surface
3. **Creep** -- plastic deforms over time under constant stress (stress relaxation)
4. **Thermal expansion** -- printed parts expand more than metal inserts

These factors mean FDM press-fits require different interference values than
traditional engineering references suggest.

## Interference Values for FDM

### Shaft into Printed Hole

| Material | Interference (mm) | Notes                              |
|----------|--------------------|------------------------------------|
| PLA      | -0.05 to -0.10    | Brittle, use minimal interference  |
| PETG     | -0.10 to -0.20    | Good elasticity, reliable hold     |
| ABS      | -0.10 to -0.15    | Good but shrinkage varies          |

"Interference" means the hole is undersized by this amount relative to the shaft
diameter. For a 10 mm shaft:
- PLA hole: 9.90--9.95 mm
- PETG hole: 9.80--9.90 mm
- ABS hole: 9.85--9.90 mm

### Bearing into Printed Housing

Bearings require a secure fit to prevent spinning in the housing but must not
be compressed so tightly that the bearing binds.

| Bearing OD (mm) | Interference (mm) | Housing Bore (mm)  |
|------------------|--------------------|---------------------|
| 11 (685ZZ)       | -0.05 to -0.10   | 10.90--10.95        |
| 21 (6702ZZ)      | -0.05 to -0.10   | 20.90--20.95        |
| 37 (6805ZZ)      | -0.05 to -0.10   | 36.90--36.95        |

**Critical**: bearing press-fit interference should be conservative. Excess
interference compresses the outer race and increases rolling friction, which
generates heat and reduces bearing life.

### Pin into Printed Hole

| Pin Diameter (mm) | Interference (mm) | Hole Diameter (mm) |
|--------------------|--------------------|---------------------|
| 2.0                | -0.10 to -0.15    | 1.85--1.90          |
| 3.0                | -0.10 to -0.15    | 2.85--2.90          |
| 5.0                | -0.10 to -0.15    | 4.85--4.90          |
| 8.0                | -0.10 to -0.15    | 7.85--7.90          |

## Design Rules for Press-Fit Housings

### Wall Thickness

The housing wall around a press-fit bore must be thick enough to resist the hoop
stress from the inserted component.

| Component         | Min Wall Thickness | Recommended          |
|-------------------|--------------------|----------------------|
| Bearing seat      | 2.0 mm             | 3.0--4.0 mm         |
| Pin hole          | 1.5 mm             | 2.0--3.0 mm         |
| Shaft bore        | 2.0 mm             | 2.5--3.5 mm         |

Thin walls will crack during insertion (especially PLA) or creep over time,
losing the press-fit grip.

### Lead-In Chamfer

Always add a chamfer at the opening of the bore to guide the component:

- **Chamfer angle**: 30--45 degrees
- **Chamfer depth**: 0.5--1.0 mm
- Prevents cracking at the bore entrance
- Aids alignment during insertion

### Print Orientation

- **Bore axis along Z (vertical)**: best roundness, best surface finish inside
  the bore. Strongly preferred.
- **Bore axis along X or Y (horizontal)**: bore will be slightly oval due to
  layer stacking. Oversize by an additional 0.05--0.1 mm on the minor axis.

### Bore Depth

- The bore should be 0.5--1.0 mm deeper than the component length
- This provides clearance for any material displaced during pressing
- For through-holes, this is not a concern

## Assembly Techniques

### Cold Press
Simply push the component into the bore using steady, straight force.
- Use an arbor press or vise for consistent alignment
- Do not hammer -- impact loading can crack the housing
- For tight fits, cool the metal component (freezer for 30 min) to shrink it

### Thermal Insertion
Heat the printed part to soften it slightly, insert the component, then cool.
- Heat the bore area with a heat gun to 50--60 C (below glass transition)
- Insert the component while warm
- Allow to cool fully before loading
- Only for PETG and ABS (PLA's Tg is too low for controlled heating)

### Press-Fit with Adhesive Assist
For critical applications, apply a thin layer of cyanoacrylate (super glue) or
epoxy to the component before pressing:
- Fills surface roughness gaps
- Prevents creep-related loosening
- Makes the joint permanent

## Preventing Common Failures

| Failure Mode          | Cause                      | Prevention                    |
|-----------------------|----------------------------|-------------------------------|
| Housing cracking      | Too much interference      | Reduce interference, add wall |
| Component spinning    | Too little interference    | Increase interference, add glue|
| Creep/loosening       | Sustained radial stress    | Add retention features or glue|
| Oval bore             | Horizontal print orientation| Print bore vertically         |
| Bearing binding       | Excess interference        | Use -0.05 mm for bearings     |

## Retention Features

For additional security beyond friction, add mechanical retention:

1. **Retaining ring groove**: a shallow groove (0.5 mm deep, 1 mm wide) on the
   bore wall, with a matching groove on the component for an E-clip or C-clip
2. **Set screw boss**: a radial hole with a set screw that presses against the
   inserted component
3. **Shoulder/step**: a step in bore diameter that acts as an axial stop
4. **Adhesive pocket**: small relief grooves in the bore wall to hold adhesive

## Calibration Test

Before committing to a design, print a test piece with multiple bore diameters
in 0.05 mm increments around your target size. This reveals your printer's
actual tolerance for press-fits with your specific material and settings.

```
Test block with holes: 9.80, 9.85, 9.90, 9.95, 10.00, 10.05 mm
Insert a 10.00 mm shaft and note which bore gives the desired fit.
```
