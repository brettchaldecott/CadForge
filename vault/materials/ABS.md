---
name: ABS
full_name: Acrylonitrile Butadiene Styrene
category: material
technology: fdm
temperature:
  nozzle_min: 230
  nozzle_max: 260
  nozzle_default: 245
  bed_min: 90
  bed_max: 110
  bed_default: 100
  glass_transition: 105
  heat_deflection: 88
mechanical:
  tensile_strength_mpa: 40
  elongation_at_break_pct: 20
  flexural_modulus_mpa: 2200
  impact_strength_kj_m2: 20
  hardness_shore_d: 76
density_g_cm3: 1.04
shrinkage_pct: 0.8
moisture_sensitive: true
tags: [material, abs, fdm, high-temp, enclosure-required]
---

# ABS (Acrylonitrile Butadiene Styrene)

## Overview

ABS is an engineering thermoplastic with excellent impact resistance and heat
tolerance. It is the material of choice for functional parts that face mechanical
stress, moderate temperatures, or need post-processing (acetone vapor smoothing).
ABS requires an enclosed printer and heated bed, making it more demanding to
print than PLA or PETG.

## Print Settings

| Parameter          | Value           | Notes                            |
|--------------------|-----------------|----------------------------------|
| Nozzle temperature | 230--260 C      | 245 C is a common starting point |
| Bed temperature    | 90--110 C       | 100 C recommended                |
| Print speed        | 40--60 mm/s     | Moderate speed to reduce warping |
| Cooling fan        | 0--20%          | Minimal or no cooling            |
| Retraction         | 0.5--1.5 mm     | Direct drive; 3--5 mm Bowden     |
| Enclosure          | **Required**    | Maintain 40--60 C chamber temp   |

## Mechanical Properties

- **Tensile strength**: ~40 MPa -- slightly lower than PLA/PETG
- **Elongation at break**: ~20% -- good ductility
- **Flexural modulus**: ~2200 MPa -- moderate stiffness
- **Impact strength**: ~20 kJ/m2 -- excellent impact resistance
- **Glass transition**: ~105 C -- suitable for warm/hot environments

ABS excels in impact resistance and is much tougher than PLA. It absorbs energy
under impact rather than shattering.

## Design Rules for ABS

- **Minimum wall thickness**: 1.2 mm (3 perimeters with 0.4 mm nozzle)
- **Recommended wall thickness**: 1.6--2.4 mm for structural parts
- **Max overhang angle**: 40 degrees without supports
- **Bridge length**: up to 15 mm (poor bridging without cooling)
- **Dimensional tolerance**: +/- 0.3 mm due to shrinkage
- **Shrinkage compensation**: ~0.8% -- significant, must be accounted for
- **Fillet all corners**: minimum 1 mm radius to prevent stress cracking

## Warping Mitigation

ABS is notorious for warping. Follow these rules to minimize warping:

1. **Enclosure is mandatory** -- maintain 40--60 C ambient temperature
2. **Brim**: use a 5--10 mm brim on all parts
3. **Avoid large flat surfaces** -- add ribs or honeycomb infill to large bases
4. **Chamfer or round bottom edges** -- sharp corners concentrate peel stress
5. **Bed adhesion**: ABS slurry (ABS dissolved in acetone) or Kapton tape
6. **No drafts** -- keep enclosure closed during printing

## Acetone Vapor Smoothing

ABS can be smoothed with acetone vapor for a glossy, injection-molded appearance:

1. Place the part on a raised platform inside a sealed container
2. Add a small amount of acetone to the bottom (paper towel method)
3. Seal and wait 15--60 minutes depending on desired smoothness
4. Remove and let dry for 24 hours in a ventilated area
5. **Safety**: acetone is flammable and the vapors are harmful -- work in a
   well-ventilated area away from ignition sources

Vapor smoothing also improves water-tightness by sealing layer lines.

## Strengths

- Excellent impact resistance and toughness
- High temperature resistance (105 C Tg)
- Acetone vapor smoothing for professional finish
- Acetone welding for joining ABS parts
- Good machinability -- can be drilled, tapped, sanded
- Low density (1.04 g/cm3) -- lighter than PLA/PETG

## Weaknesses

- Warping -- the primary challenge with ABS
- Requires enclosed printer with heated bed
- Emits styrene fumes during printing -- ventilation required
- UV degradation -- not suitable for prolonged outdoor use without coating
- Higher shrinkage than PLA/PETG
- Poor bridging performance
- Hygroscopic -- store dry

## Tips

1. Dry ABS at 80 C for 4--6 hours before printing.
2. Use ASA as a UV-resistant alternative to ABS for outdoor parts.
3. For multi-part assemblies, acetone welding creates bonds stronger than the
   base material.
4. When designing for ABS, add 0.8% to all dimensions to compensate for
   shrinkage, or calibrate your slicer's shrinkage compensation setting.
5. ABS is excellent for heat-set threaded inserts -- the high Tg prevents
   deformation during installation.
