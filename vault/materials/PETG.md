---
name: PETG
full_name: Polyethylene Terephthalate Glycol-modified
category: material
technology: fdm
temperature:
  nozzle_min: 220
  nozzle_max: 250
  nozzle_default: 235
  bed_min: 70
  bed_max: 85
  bed_default: 80
  glass_transition: 80
  heat_deflection: 70
mechanical:
  tensile_strength_mpa: 50
  elongation_at_break_pct: 23
  flexural_modulus_mpa: 2100
  impact_strength_kj_m2: 8
  hardness_shore_d: 75
density_g_cm3: 1.27
shrinkage_pct: 0.4
moisture_sensitive: true
tags: [material, petg, fdm, functional, medium-temp]
---

# PETG (Polyethylene Terephthalate Glycol-modified)

## Overview

PETG combines ease of printing (close to PLA) with significantly better
mechanical properties and temperature resistance. It is the go-to material for
functional parts that need some flexibility, chemical resistance, or moderate
heat tolerance. PETG is naturally translucent and food-safe in its base
formulation (though layer lines harbor bacteria).

## Print Settings

| Parameter          | Value           | Notes                            |
|--------------------|-----------------|----------------------------------|
| Nozzle temperature | 220--250 C      | 235 C is a reliable starting point |
| Bed temperature    | 70--85 C        | 80 C recommended                 |
| Print speed        | 40--80 mm/s     | Slower than PLA for best results |
| Cooling fan        | 30--50%         | Too much cooling causes delamination |
| Retraction         | 1.0--3.0 mm     | Direct drive; 4--6 mm Bowden     |
| Enclosure          | Not required    | Helps with large parts           |

## Mechanical Properties

- **Tensile strength**: ~50 MPa -- comparable to PLA
- **Elongation at break**: ~23% -- significantly more ductile than PLA
- **Flexural modulus**: ~2100 MPa -- more flexible than PLA
- **Impact strength**: ~8 kJ/m2 -- better impact resistance
- **Glass transition**: ~80 C -- usable in warm environments

PETG provides a good balance between stiffness and flexibility. It bends before
it breaks, making it suitable for snap-fits and living hinges (limited cycles).

## Design Rules for PETG

- **Minimum wall thickness**: 0.8 mm (2 perimeters with 0.4 mm nozzle)
- **Recommended wall thickness**: 1.2--2.0 mm for functional parts
- **Max overhang angle**: 40 degrees without supports (slightly worse than PLA)
- **Bridge length**: up to 20 mm with partial cooling
- **Dimensional tolerance**: +/- 0.2 mm typical
- **Shrinkage compensation**: ~0.4%, minor compensation may help for precision fits

## Strengths

- Good balance of strength and flexibility
- Higher temperature resistance than PLA
- Chemical resistance to many solvents and acids
- Good layer adhesion -- strong inter-layer bonding
- Low warping -- no enclosure required for most prints
- Naturally translucent -- good for light diffusers
- UV resistant -- suitable for outdoor use

## Weaknesses

- Stringing -- PETG is prone to stringing and requires tuned retraction
- Support removal is difficult -- PETG bonds strongly to supports
- Hygroscopic -- absorbs moisture from air
- Slightly worse overhang performance than PLA
- Scratches more easily than PLA (softer surface)
- Can stick too well to PEI -- use glue stick as release agent

## Tips

1. Use a textured PEI sheet or apply a thin layer of glue stick on smooth PEI to
   prevent the print from bonding too aggressively to the bed.
2. Reduce cooling fan to 30--50%. Full cooling causes poor layer adhesion and
   visible white stress marks on the surface.
3. PETG loves slow, hot first layers. Use 240 C nozzle and 10--15 mm/s for the
   first layer.
4. For support interfaces, increase Z gap to 0.15--0.2 mm and use a support
   interface material if possible.
5. Dry PETG at 65 C for 4--6 hours before printing. Wet PETG produces bubbles,
   poor surface finish, and weak parts.
6. PETG is an excellent choice for mechanical parts, enclosures, brackets, and
   any part that needs to survive mild impacts or sustained loads.
