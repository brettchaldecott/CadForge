---
name: build123d Boolean Operations
category: build123d
topic: boolean-operations
tags: [build123d, boolean, union, cut, intersect, cad]
---

# build123d Boolean Operations

## Overview

build123d handles boolean operations via the `mode` parameter on shape constructors,
or through operator overloading (`+`, `-`, `&`) on Part objects within a `BuildPart`
context. This is fundamentally different from CadQuery's method-chaining approach.

## Mode-Based Booleans (Implicit)

Every shape constructor accepts a `mode` parameter:

- `Mode.ADD` (default) — union with existing part
- `Mode.SUBTRACT` — cut from existing part
- `Mode.INTERSECT` — keep only overlap
- `Mode.PRIVATE` — create but don't combine

```python
with BuildPart() as part:
    Box(30, 30, 10)                          # base (ADD)
    Cylinder(5, 15, mode=Mode.SUBTRACT)      # drill hole
    with Locations((10, 0, 0)):
        Cylinder(3, 15, mode=Mode.SUBTRACT)  # another hole

result = part.part
```

## Explicit Boolean Operations

Use Python operators to combine shapes outside a builder context:

```python
box = bd.Part() + bd.Box(20, 20, 10)
cyl = bd.Part() + bd.Cylinder(5, 15)

# Explicit operations
result = box - cyl           # cut
result = box + cyl           # union
result = box & cyl           # intersect
```

## Operator Overloading

build123d supports Python operators on `Part` objects:

```python
a = bd.Part() + bd.Box(20, 20, 10)
b = bd.Part() + bd.Sphere(12)

union_result = a + b         # fuse
cut_result = a - b           # cut
intersect_result = a & b     # intersect
```

## Complex Example

```python
with BuildPart() as part:
    # Base plate
    Box(50, 50, 5)
    # Raised cylinder
    with Locations((0, 0, 5)):
        Cylinder(radius=10, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Through-hole
    Cylinder(radius=4, height=30, mode=Mode.SUBTRACT)
    # Corner holes
    for x, y in [(-18, -18), (-18, 18), (18, -18), (18, 18)]:
        with Locations((x, y, 0)):
            Cylinder(radius=2, height=10, mode=Mode.SUBTRACT)

result = part.part
```

## Working with Faces and Edges

```python
with BuildPart() as part:
    Box(30, 30, 10)
    # Fillet all vertical edges
    fillet(*part.edges().filter_by(Axis.Z), radius=2)
    # Chamfer top edges
    chamfer(*part.faces().sort_by(Axis.Z)[-1].edges(), length=1)

result = part.part
```

## Shell

```python
with BuildPart() as part:
    Box(20, 20, 10)
    # Shell: remove top face, keep 1.5mm walls
    Shell(part.faces().sort_by(Axis.Z)[-1], thickness=-1.5)

result = part.part
```

## Tips

1. Use `mode=Mode.SUBTRACT` inside `BuildPart` instead of explicit boolean calls —
   it's cleaner and more efficient.
2. For batch operations, build all features inside one `BuildPart` context — the
   builder batches boolean operations internally.
3. `Mode.PRIVATE` is useful for creating reference geometry without affecting the
   main part.
4. Fillet and chamfer should be applied after all boolean operations, same as in
   CadQuery.
