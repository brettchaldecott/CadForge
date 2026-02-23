---
name: build123d Primitives Guide
category: build123d
topic: primitives
tags: [build123d, primitives, modeling, box, cylinder, sphere, cad]
---

# build123d Primitives Guide

## Overview

build123d uses a context-manager (builder) pattern. Geometry is created inside
`BuildPart`, `BuildSketch`, or `BuildLine` contexts. The result is captured
from the builder's output.

## Builder Pattern

```python
import build123d as bd

with bd.BuildPart() as part:
    bd.Box(10, 20, 5)

result = part.part  # a bd.Part (Solid)
```

Or using top-level names (available in the CadForge sandbox):

```python
with BuildPart() as part:
    Box(10, 20, 5)

result = part.part
```

## Box

```python
with BuildPart() as part:
    # Centered box
    Box(length=20, width=15, height=10)

result = part.part
```

```python
# Align controls centering per axis
with BuildPart() as part:
    Box(20, 15, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))

result = part.part
```

## Cylinder

```python
with BuildPart() as part:
    Cylinder(radius=10, height=20)

result = part.part
```

```python
# Hollow cylinder
with BuildPart() as part:
    Cylinder(radius=10, height=20)
    Cylinder(radius=8, height=20, mode=Mode.SUBTRACT)

result = part.part
```

## Sphere

```python
with BuildPart() as part:
    Sphere(radius=15)

result = part.part
```

## Cone

```python
with BuildPart() as part:
    Cone(bottom_radius=15, top_radius=5, height=25)

result = part.part
```

## Torus

```python
with BuildPart() as part:
    Torus(major_radius=20, minor_radius=5)

result = part.part
```

## Wedge

```python
with BuildPart() as part:
    Wedge(xsize=20, ysize=10, zsize=15, xmin=5, zmin=5, xmax=15, zmax=10)

result = part.part
```

## Extrude from Sketch

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(20, 10)
    extrude(amount=5)

result = part.part
```

```python
# Extrude with taper
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(20, 10)
    extrude(amount=5, taper=5)

result = part.part
```

## Revolve

```python
with BuildPart() as part:
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine() as ln:
            Line((0, 0), (10, 0))
            Line((10, 0), (10, 20))
            Line((10, 20), (5, 20))
            Line((5, 20), (5, 2))
            Line((5, 2), (0, 2))
            Line((0, 2), (0, 0))
        bd.make_face()
    revolve(axis=Axis.Z)

result = part.part
```

## Loft

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(20, 20)
    with BuildSketch(Plane.XY.offset(30)) as sk2:
        Circle(10)
    loft()

result = part.part
```

## Positioning

```python
with BuildPart() as part:
    Box(10, 10, 10)
    with Locations((20, 0, 0)):
        Box(5, 5, 5)

result = part.part
```

## Tips

1. build123d uses millimeters as the default unit.
2. Always assign `part.part` to `result` for export.
3. The `mode` parameter controls boolean behavior: `Mode.ADD` (default),
   `Mode.SUBTRACT`, `Mode.INTERSECT`, `Mode.PRIVATE`.
4. Use `Align.MIN`, `Align.CENTER`, `Align.MAX` to control alignment per axis.
5. Export with `export_stl(result, "output.stl")` or `export_step(result, "output.step")`.
