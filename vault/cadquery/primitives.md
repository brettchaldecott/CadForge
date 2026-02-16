---
name: CadQuery Primitives Guide
category: cadquery
topic: primitives
tags: [cadquery, primitives, modeling, box, cylinder, sphere, cad]
---

# CadQuery Primitives Guide

## Overview

CadQuery provides a fluent API for creating 3D geometry using a chained
workplane approach. All geometry starts from a `Workplane` object and is built up
through method chaining. This guide covers the fundamental primitive shapes and
construction operations.

## Creating a Workplane

```python
import cadquery as cq

# Standard XY workplane at origin
result = cq.Workplane("XY")

# Other standard planes
result = cq.Workplane("XZ")  # front view
result = cq.Workplane("YZ")  # side view

# Offset workplane
result = cq.Workplane("XY").workplane(offset=10.0)
```

## Box (Rectangular Prism)

```python
# Centered box
box = cq.Workplane("XY").box(length=20, width=15, height=10)

# Box centered only in XY, sitting on Z=0
box = cq.Workplane("XY").box(20, 15, 10, centered=(True, True, False))

# Box at a specific location
box = (cq.Workplane("XY")
       .center(30, 0)
       .box(10, 10, 5))
```

## Cylinder

```python
# Centered cylinder (height along Z)
cyl = cq.Workplane("XY").cylinder(height=20, radius=10)

# Cylinder from a circle sketch (more control)
cyl = (cq.Workplane("XY")
       .circle(10)
       .extrude(20))

# Hollow cylinder (tube)
tube = (cq.Workplane("XY")
        .circle(10)       # outer radius
        .circle(8)        # inner radius
        .extrude(20))
```

## Sphere

```python
# Sphere at origin
sphere = cq.Workplane("XY").sphere(radius=15)

# Sphere using revolve (more control over partial spheres)
hemisphere = (cq.Workplane("XZ")
              .center(0, 0)
              .radiusArc((15, 0), 15)
              .lineTo(0, 0)
              .close()
              .revolve(360))
```

## Cone and Truncated Cone

```python
# Full cone (apex at top)
cone = (cq.Workplane("XY")
        .circle(10)
        .workplane(offset=20)
        .circle(0.01)  # near-zero top for a point
        .loft())

# Truncated cone (frustum)
frustum = (cq.Workplane("XY")
           .circle(15)           # bottom radius
           .workplane(offset=25)
           .circle(8)            # top radius
           .loft())
```

## Torus

```python
# Torus via revolve
torus = (cq.Workplane("XZ")
         .center(20, 0)        # major radius = 20
         .circle(5)            # minor radius = 5
         .revolve(360, (0, 0, 0), (0, 1, 0)))
```

## Extrude Operations

```python
# Simple extrude
part = cq.Workplane("XY").rect(20, 10).extrude(5)

# Extrude with taper (draft angle in degrees)
part = cq.Workplane("XY").rect(20, 10).extrude(5, taper=5)

# Extrude symmetric (both directions from workplane)
part = cq.Workplane("XY").circle(10).extrude(5, both=True)

# Extrude cut (subtract from existing solid)
part = (cq.Workplane("XY")
        .box(30, 30, 10)
        .faces(">Z").workplane()
        .circle(5)
        .cutBlind(-8))
```

## Revolve Operations

```python
# Full revolve (360 degrees)
part = (cq.Workplane("XZ")
        .lineTo(10, 0)
        .lineTo(10, 20)
        .lineTo(5, 20)
        .lineTo(5, 2)
        .lineTo(0, 2)
        .close()
        .revolve(360))

# Partial revolve (90 degrees)
part = (cq.Workplane("XZ")
        .rect(5, 20, centered=False)
        .revolve(90, (0, 0, 0), (0, 1, 0)))
```

## Loft Between Profiles

```python
# Loft between two different shapes
part = (cq.Workplane("XY")
        .rect(20, 20)
        .workplane(offset=30)
        .circle(10)
        .loft())

# Loft with intermediate sections
part = (cq.Workplane("XY")
        .rect(20, 20)
        .workplane(offset=15)
        .rect(15, 15)
        .workplane(offset=15)
        .circle(8)
        .loft())
```

## Sweep Along Path

```python
# Sweep a circle along a path
path = cq.Workplane("XZ").spline([(0,0), (10,10), (20,0)])
part = (cq.Workplane("XY")
        .circle(2)
        .sweep(path))
```

## Common Modifiers

```python
# Fillet edges
part = cq.Workplane("XY").box(20, 20, 10).edges("|Z").fillet(2)

# Chamfer edges
part = cq.Workplane("XY").box(20, 20, 10).edges(">Z").chamfer(1)

# Shell (hollow out)
part = cq.Workplane("XY").box(20, 20, 10).shell(-1.5)

# Shell keeping specific face open
part = (cq.Workplane("XY")
        .box(20, 20, 10)
        .faces(">Z")
        .shell(-1.5))
```

## Tips

1. CadQuery uses millimeters as the default unit.
2. The `centered` parameter on `box()` defaults to `(True, True, True)`.
3. Use `.val()` to extract the underlying OCCT shape when needed for advanced
   operations.
4. Chain `.translate()` and `.rotate()` for positioning after creation.
5. Use `cq.exporters.export(part, "output.stl")` or `.step` to export.
