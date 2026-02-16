---
name: Overhang Design Rules
category: design-rule
technology: fdm
applies_to: [PLA, PETG, ABS, TPU]
tags: [design-rule, overhang, support, fdm, orientation]
---

# Overhang Design Rules for FDM Printing

## Overview

In FDM (Fused Deposition Modeling), each layer must be supported by the layer
below it. When a feature extends beyond the previous layer at an angle, it
creates an overhang. Understanding overhang limits is critical for designing
printable parts without excessive supports.

## The 45-Degree Rule

The fundamental rule of FDM overhangs: **angles up to 45 degrees from vertical
can be printed without supports on most printers.**

At 45 degrees, each new layer overlaps approximately 50% of the layer below,
providing sufficient support for the molten filament. Beyond 45 degrees, print
quality degrades rapidly.

| Overhang Angle | Printability       | Notes                          |
|----------------|--------------------|--------------------------------|
| 0--30 deg      | Excellent          | No support needed              |
| 30--45 deg     | Good               | Minor surface roughness        |
| 45--60 deg     | Fair               | Visible drooping, curling      |
| 60--80 deg     | Poor               | Supports recommended           |
| 80--90 deg     | Not printable      | Supports required              |
| 90 deg (flat)  | Bridge or support  | Bridging possible up to limit  |

## Material-Specific Overhang Limits

| Material | Max Unsupported Angle | Max Bridge Length | Notes              |
|----------|-----------------------|-------------------|--------------------|
| PLA      | 50--60 deg            | 25--30 mm         | Best overhang perf |
| PETG     | 40--45 deg            | 15--20 mm         | Stringing at edges |
| ABS      | 35--40 deg            | 10--15 mm         | Minimal cooling    |
| TPU      | 30--40 deg            | 10--15 mm         | Flexible, droops   |

## Support Strategies

### 1. Design to Avoid Supports
- **Chamfer instead of fillet**: a 45-degree chamfer on a bottom edge prints
  without supports; a fillet requires them
- **Teardrop holes**: replace circular holes on vertical faces with teardrop
  shapes (pointed at the top) to eliminate the overhang at 12 o'clock
- **Split and rotate**: split the part so each piece can be printed flat

### 2. Strategic Part Orientation
- Rotate the part on the build plate to minimize overhangs
- Prefer overhangs on non-cosmetic surfaces
- Flat bottoms and vertical walls are free (no supports)

### 3. Built-In Support Features
- Add sacrificial break-away tabs at critical overhang zones
- Design internal chamfers at 45 degrees instead of flat ceilings
- Use arched or gothic arch profiles for internal cavities

### 4. Slicer Support Settings
When supports are unavoidable:
- **Support angle threshold**: set to 45 degrees (or per material)
- **Support Z distance**: 0.15--0.2 mm for easy removal
- **Support interface**: use 2--3 dense interface layers for clean surfaces
- **Tree supports**: better for organic shapes, less material waste
- **Support blocker**: manually block supports in non-critical areas

## Bridging

Bridging is printing a horizontal span between two supported points with no
material beneath. Rules of thumb:

- PLA bridges up to 25--30 mm with 100% fan cooling at 30--40 mm/s
- PETG bridges up to 15--20 mm with 50% fan cooling
- ABS bridges up to 10--15 mm (limited cooling available)
- Use dedicated bridge settings in slicer: slower speed, higher fan
- First bridge layer should be printed at 15--25 mm/s

## Design Checklist

1. Are all overhangs at 45 degrees or less?
2. Have bottom fillets been replaced with chamfers?
3. Are holes on vertical faces teardrop-shaped?
4. Has the optimal print orientation been chosen?
5. Are internal cavities self-supporting (arched, chamfered)?
6. If supports are needed, are they accessible for removal?
7. Are supported surfaces on non-cosmetic faces?
