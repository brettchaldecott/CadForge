---
name: CadQuery Boolean Operations
category: cadquery
topic: boolean-operations
tags: [cadquery, boolean, union, cut, intersect, cad, performance]
---

# CadQuery Boolean Operations

## Overview

Boolean operations combine or subtract solid bodies to create complex geometry.
CadQuery wraps the OpenCASCADE (OCCT) boolean engine. Understanding how to use
boolean operations efficiently is critical for both correctness and performance,
as OCCT boolean operations are the most expensive step in CAD model generation.

## Basic Boolean Operations

### Union (Fuse / Add)

Combines two solids into one. Overlapping volume is merged.

```python
import cadquery as cq

box = cq.Workplane("XY").box(20, 20, 10)
cyl = cq.Workplane("XY").cylinder(15, 5)

# Method 1: union()
result = box.union(cyl)

# Method 2: Using the | operator
result = box | cyl
```

### Cut (Subtract / Remove)

Removes one solid from another.

```python
box = cq.Workplane("XY").box(20, 20, 10)
hole = cq.Workplane("XY").cylinder(15, 3)

# Method 1: cut()
result = box.cut(hole)

# Method 2: Using the - operator
result = box - hole
```

### Intersect (Common)

Keeps only the overlapping volume between two solids.

```python
box = cq.Workplane("XY").box(20, 20, 10)
sphere = cq.Workplane("XY").sphere(12)

# Method 1: intersect()
result = box.intersect(sphere)

# Method 2: Using the & operator
result = box & sphere
```

## Chaining Boolean Operations

```python
# Build up complex geometry with chained operations
result = (cq.Workplane("XY")
          .box(30, 30, 10)
          .union(cq.Workplane("XY").box(10, 10, 30))    # add tower
          .cut(cq.Workplane("XY").cylinder(35, 3))       # drill hole
          .cut(cq.Workplane("XY").center(10, 0).cylinder(15, 2)))  # another hole
```

## Batch Boolean Operations (Performance Critical)

Sequential boolean operations are **O(n)** OCCT kernel calls. Each call has
overhead. Batching multiple operations into a single call is 3--5x faster.

### Batch Union (Fuse)

```python
# SLOW: sequential union loop
result = base_solid
for s in solids_to_add:
    result = result.union(s)  # N separate OCCT calls

# FAST: batch fuse using val().fuse()
base = base_solid.val()
others = [s.val() for s in solids_to_add]
fused = base.fuse(*others)
result = cq.Workplane("XY").newObject([fused])
```

### Batch Cut

```python
# SLOW: sequential cut loop
result = base_solid
for s in solids_to_cut:
    result = result.cut(s)  # N separate OCCT calls

# FAST: fuse all cutters first, then single cut
base = base_solid.val()
cutters = [s.val() for s in solids_to_cut]
compound_cutter = cutters[0].fuse(*cutters[1:]) if len(cutters) > 1 else cutters[0]
result_shape = base.cut(compound_cutter)
result = cq.Workplane("XY").newObject([result_shape])
```

### Important Caveat

Batch `cut(*spaces)` can sometimes corrupt OCCT topology, producing
untessellatable geometry. The safe pattern is:

```python
# Safe batch cut pattern
# 1. Fuse all cutters into one compound
compound_cutter = cutters[0]
for c in cutters[1:]:
    compound_cutter = compound_cutter.fuse(c)

# 2. Single cut operation
result = base.cut(compound_cutter)
```

This avoids passing multiple arguments to `cut()` directly, which can trigger
OCCT topology issues.

## Working with Compounds and Assemblies

### Compound (Multiple Solids in One Object)

```python
# Create a compound from multiple solids
solids = [box1.val(), box2.val(), cyl1.val()]
compound = cq.Compound.makeCompound(solids)
```

### Assembly (Positioned Parts)

```python
assy = cq.Assembly()
assy.add(base_part, name="base", color=cq.Color("gray"))
assy.add(top_part, name="top", loc=cq.Location((0, 0, 10)),
         color=cq.Color("blue"))
```

## Debugging Boolean Failures

Boolean operations can fail when OCCT encounters degenerate geometry. Common
causes and fixes:

1. **Coincident faces** -- two solids share an exact face. Fix: offset one solid
   by 0.001 mm.
2. **Zero-thickness features** -- a cut removes all material at some point. Fix:
   ensure minimum wall thickness after cuts.
3. **Self-intersecting geometry** -- the input solid has overlapping faces. Fix:
   simplify the construction sequence.
4. **Tangent edges** -- boolean at exact tangent points. Fix: offset slightly.

### Checking for Failures

```python
result = box.cut(cyl)

# Check if result is valid
if result.val().isValid():
    print("Boolean succeeded")
else:
    print("Boolean produced invalid geometry")
```

## Performance Guidelines

| Operation                | Relative Cost | Notes                        |
|--------------------------|---------------|------------------------------|
| Simple box-box union     | 1x            | Baseline                     |
| Cylinder cut from box    | 2x            | Curved surfaces are slower   |
| Fillet after boolean      | 5--10x       | Fillet is very expensive     |
| Sequential N booleans    | N * cost      | Linear scaling               |
| Batch N booleans         | 1--2 * cost   | Near constant for fuse step  |

## Tips

1. Always perform fillets and chamfers **after** all boolean operations.
2. Batch boolean operations wherever possible -- the speedup is significant.
3. When a boolean fails, try adding a tiny offset (0.001 mm) to eliminate
   coincident geometry.
4. Use `.val()` to access the underlying OCCT `Shape` for advanced operations.
5. Export intermediate results to STEP for debugging in FreeCAD/CAD Viewer.
6. For ring gears with helical teeth, fuse all tooth spaces into one compound
   before cutting -- direct batch cut corrupts topology.
