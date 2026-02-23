---
name: build123d Sketches Guide
category: build123d
topic: sketches
tags: [build123d, sketch, 2d, profiles, cad]
---

# build123d Sketches Guide

## Overview

build123d sketches are created inside `BuildSketch` contexts. They produce 2D
faces that can be extruded, revolved, or lofted into 3D solids. Sketches can
be placed on any plane.

## Basic Sketch Shapes

### Rectangle

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(width=20, height=10)
    extrude(amount=5)

result = part.part
```

### Circle

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Circle(radius=10)
    extrude(amount=5)

result = part.part
```

### Polygon (Regular)

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        RegularPolygon(radius=10, side_count=6)  # hexagon
    extrude(amount=5)

result = part.part
```

## Sketch on Different Planes

```python
with BuildPart() as part:
    # Sketch on XY (default)
    with BuildSketch() as sk:
        Rectangle(20, 10)
    extrude(amount=5)

    # Sketch on top face
    with BuildSketch(part.faces().sort_by(Axis.Z)[-1]) as sk2:
        Circle(radius=3)
    extrude(amount=-5, mode=Mode.SUBTRACT)

result = part.part
```

## Custom Profiles with BuildLine

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        with BuildLine() as ln:
            Line((0, 0), (20, 0))
            Line((20, 0), (20, 10))
            Line((20, 10), (10, 15))
            Line((10, 15), (0, 10))
            Line((0, 10), (0, 0))
        bd.make_face()
    extrude(amount=5)

result = part.part
```

## Arcs and Curves

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        with BuildLine() as ln:
            Line((0, 0), (20, 0))
            bd.RadiusArc((20, 0), (20, 10), radius=10)
            Line((20, 10), (0, 10))
            Line((0, 10), (0, 0))
        bd.make_face()
    extrude(amount=5)

result = part.part
```

## Sketch Boolean Operations

Sketches support boolean operations via `mode`:

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(30, 20)
        Circle(radius=5, mode=Mode.SUBTRACT)           # cut hole
        with Locations((10, 0)):
            Circle(radius=3, mode=Mode.SUBTRACT)        # another hole
    extrude(amount=5)

result = part.part
```

## Text in Sketches

```python
with BuildPart() as part:
    Box(50, 20, 5)
    with BuildSketch(part.faces().sort_by(Axis.Z)[-1]) as sk:
        bd.Text("HELLO", font_size=8)
    extrude(amount=1)

result = part.part
```

## Offset and Fillet on Sketches

```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(20, 10)
        bd.fillet(sk.vertices(), radius=2)  # round corners in 2D
    extrude(amount=5)

result = part.part
```

## Tips

1. Use `BuildSketch` for 2D profiles, `BuildPart` for 3D solids.
2. `make_face()` converts a closed wire from `BuildLine` into a filled face.
3. Place sketches on existing faces using `BuildSketch(face)`.
4. Sketch booleans work the same as 3D booleans — use `mode=Mode.SUBTRACT`.
5. `BuildLine` segments must form a closed loop for `make_face()` to work.
