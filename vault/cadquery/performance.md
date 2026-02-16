---
name: CadQuery Performance Tips
category: cadquery
topic: performance
tags: [cadquery, performance, optimization, boolean, fillet, cad]
---

# CadQuery Performance Tips

## Overview

CadQuery wraps the OpenCASCADE (OCCT) kernel, which performs exact B-rep
(boundary representation) geometry operations. While powerful, OCCT operations
can be slow on complex geometry. This guide covers the most impactful
optimizations for CadQuery model generation.

## 1. Batch Boolean Operations

The single most impactful optimization. Sequential boolean operations are O(n)
individual OCCT kernel calls, each with significant overhead.

### Bad: Sequential Loop

```python
# Each union() triggers a full OCCT boolean -- O(n) calls
result = base
for feature in features:
    result = result.union(feature)  # 30 features = 30 OCCT calls
```

### Good: Batch Fuse

```python
# Single OCCT call for all features -- 3-5x faster
base_shape = base.val()
feature_shapes = [f.val() for f in features]
fused = base_shape.fuse(*feature_shapes)
result = cq.Workplane("XY").newObject([fused])
```

### Measured Impact

| Features | Sequential (s) | Batched (s) | Speedup |
|----------|----------------|-------------|---------|
| 10       | 8              | 3           | 2.7x    |
| 20       | 22             | 5           | 4.4x    |
| 50       | 85             | 18          | 4.7x    |

## 2. Fillet and Chamfer Ordering

Fillets are the most expensive operation in OCCT. They compute rolling-ball
intersections with all adjacent faces.

### Rules

1. **Perform all boolean operations before any fillets.** Filleting, then
   performing booleans on filleted geometry, is dramatically slower.
2. **Fillet fewer edges at once** if full-model fillet fails. Select specific
   edges rather than using broad selectors.
3. **Prefer chamfers over fillets** when appearance is not critical. Chamfers
   are 5--10x faster than fillets.
4. **Order fillets from largest to smallest radius** to avoid topology failures.

```python
# SLOW: fillet then boolean
part = box.edges("|Z").fillet(2)
result = part.cut(cylinder)  # OCCT must intersect filleted surfaces

# FAST: boolean then fillet
result = box.cut(cylinder)
result = result.edges("|Z").fillet(2)  # simpler intersection
```

## 3. Minimize Topology Queries

Edge and face selectors (e.g., `.edges(">Z")`, `.faces("<X")`) perform topology
traversals. On complex solids with thousands of faces, these can be slow.

```python
# SLOW: repeated selector queries
result = part.edges("|Z").fillet(2)
result = result.edges("|X").fillet(1)
result = result.edges("|Y").fillet(1)

# BETTER: combine selectors where possible
result = part.edges("|Z or |X or |Y").fillet(1)

# Or select by position
result = part.edges(
    cq.selectors.BoxSelector((-5,-5,-1), (5,5,1))
).fillet(1)
```

## 4. Reduce Face Count in Source Geometry

OCCT boolean cost scales with the number of faces in both operands. Simpler
geometry = faster booleans.

```python
# SLOW: high-resolution cylinder (many facets in tessellation,
# but B-rep is the same -- this tip applies to imported mesh geometry)

# For CadQuery native geometry, avoid unnecessary construction steps
# that create extra faces:
# SLOW: building a shape from many small pieces
result = cq.Workplane("XY")
for i in range(100):
    result = result.union(make_small_cube(i))

# FAST: construct the geometry directly if possible
points = [(x, y) for x, y in grid]
result = cq.Workplane("XY").pushPoints(points).circle(r).extrude(h)
```

## 5. Helical/Twisted Extrude Optimization

`twistExtrude()` is expensive because it creates complex ruled surfaces.

```python
# Herringbone gear optimization: extrude each half separately
# and fuse once, rather than mirroring and fusing per tooth

# Build all teeth as individual solids
half_teeth = [make_tooth_half(i) for i in range(n_teeth)]

# Batch fuse all teeth
all_teeth = half_teeth[0].fuse(*half_teeth[1:])

# Single cut from blank
gear = blank.cut(all_teeth)
```

## 6. Use Compounds for Non-Interacting Parts

If parts don't need boolean interaction, use compounds instead of unions:

```python
# SLOW: union non-touching parts (OCCT still checks for intersection)
result = part_a.union(part_b)

# FAST: compound (just groups them, no boolean check)
compound = cq.Compound.makeCompound([part_a.val(), part_b.val()])
```

## 7. Profile and Identify Bottlenecks

```python
import time

t0 = time.time()
result = box.cut(complex_shape)
t1 = time.time()
print(f"Boolean cut: {t1-t0:.1f}s")

t2 = time.time()
result = result.edges(">Z").fillet(1)
t3 = time.time()
print(f"Fillet: {t3-t2:.1f}s")
```

## 8. STL Export Optimization

Tessellation (converting B-rep to mesh for STL) can be slow on complex geometry.

```python
import cadquery as cq

# Default export
cq.exporters.export(result, "part.stl")

# Control tessellation quality
cq.exporters.export(
    result, "part.stl",
    tolerance=0.1,       # chord tolerance in mm (larger = coarser)
    angularTolerance=0.2  # angular tolerance in radians
)
```

| Tolerance | File Size | Export Time | Visual Quality |
|-----------|-----------|-------------|----------------|
| 0.01      | Large     | Slow        | Excellent      |
| 0.05      | Medium    | Medium      | Good           |
| 0.1       | Small     | Fast        | Acceptable     |
| 0.5       | Tiny      | Very fast   | Coarse         |

## 9. STEP Export for Debugging

STEP files preserve exact B-rep geometry and are invaluable for debugging:

```python
cq.exporters.export(result, "debug.step")
# Open in FreeCAD, CAD Assistant, or any STEP viewer
```

## Summary: Performance Priority List

1. Batch boolean operations (3--5x speedup)
2. Perform fillets/chamfers last (5--10x per fillet)
3. Use chamfers instead of fillets where possible
4. Use compounds for non-interacting parts
5. Minimize topology queries on complex solids
6. Profile to find actual bottlenecks before optimizing
