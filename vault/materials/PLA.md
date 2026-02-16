---
name: PLA
full_name: Polylactic Acid
category: material
technology: fdm
temperature:
  nozzle_min: 190
  nozzle_max: 220
  nozzle_default: 210
  bed_min: 0
  bed_max: 60
  bed_default: 60
  glass_transition: 60
  heat_deflection: 52
mechanical:
  tensile_strength_mpa: 50
  elongation_at_break_pct: 6
  flexural_modulus_mpa: 3600
  impact_strength_kj_m2: 5
  hardness_shore_d: 83
density_g_cm3: 1.24
shrinkage_pct: 0.3
moisture_sensitive: true
tags: [material, pla, fdm, beginner, low-temp]
---

# PLA (Polylactic Acid)

## Overview

PLA is the most widely used FDM filament. It is derived from renewable resources
(corn starch, sugarcane) and is biodegradable under industrial composting
conditions. PLA is the easiest material to print with, making it ideal for
prototyping, display models, and parts that will not be exposed to heat or
sustained mechanical stress.

## Print Settings

| Parameter          | Value           | Notes                          |
|--------------------|-----------------|--------------------------------|
| Nozzle temperature | 190--220 C      | 210 C is a reliable default    |
| Bed temperature    | 0--60 C         | 60 C recommended for adhesion  |
| Print speed        | 40--100 mm/s    | Higher speeds possible on newer printers |
| Cooling fan        | 100%            | Always run full cooling        |
| Retraction         | 0.5--2.0 mm     | Direct drive; 4--6 mm Bowden   |
| Enclosure          | Not required    | Enclosure can cause heat creep |

## Mechanical Properties

- **Tensile strength**: ~50 MPa -- stiff but brittle
- **Elongation at break**: ~6% -- very low ductility
- **Flexural modulus**: ~3600 MPa -- high stiffness
- **Impact strength**: ~5 kJ/m2 -- poor impact resistance
- **Glass transition**: 60 C -- parts soften in warm environments

PLA is strong in compression but weak under impact. It is not suitable for parts
that experience cyclic loading or sudden shocks.

## Design Rules for PLA

- **Minimum wall thickness**: 0.8 mm (2 perimeters with 0.4 mm nozzle)
- **Recommended wall thickness**: 1.2--1.6 mm for structural parts
- **Max overhang angle**: 45 degrees without supports (60 degrees with good cooling)
- **Bridge length**: up to 30 mm with aggressive cooling
- **Dimensional tolerance**: +/- 0.2 mm typical on well-calibrated printers
- **Shrinkage compensation**: minimal (~0.3%), usually not needed

## Strengths

- Excellent print quality and surface finish
- Low warping -- no enclosure required
- Wide color availability
- Good bridging performance with cooling
- Low odor during printing
- Biodegradable under industrial conditions

## Weaknesses

- Low heat resistance -- deforms above 50--60 C
- Brittle -- poor impact resistance
- Degrades with UV exposure over time
- Absorbs moisture (store in dry box)
- Not food-safe without specific certifications

## Tips

1. Store PLA in a sealed container with desiccant. Wet PLA produces stringing,
   popping sounds, and rough surfaces.
2. Use a smooth PEI sheet or glue stick on glass for bed adhesion.
3. PLA can be sanded and primed for painting.
4. Annealing PLA at 80--100 C in an oven can increase heat resistance to ~80 C,
   but causes 2--5% dimensional shrinkage. Design parts oversize if annealing.
5. For snap-fits, PLA is too brittle for repeated flex. Use PETG instead.
