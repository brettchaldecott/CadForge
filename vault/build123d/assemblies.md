---
name: build123d Assemblies Guide
category: build123d
topic: assemblies
tags: [build123d, assembly, multi-part, positioning, cad]
---

# build123d Assemblies Guide

## Overview

build123d assemblies allow combining multiple parts with relative positioning.
Parts can be placed using `Location`, joints, or explicit transforms. This is
useful for multi-component designs where parts need to maintain their identity.

## Basic Assembly

```python
# Create individual parts
with BuildPart() as base_builder:
    Box(50, 50, 5)
base = base_builder.part

with BuildPart() as pillar_builder:
    Cylinder(radius=5, height=30)
pillar = pillar_builder.part

# Assemble
assy = bd.Compound(
    label="assembly",
    children=[
        bd.Compound(label="base", wrapped=base.wrapped),
        bd.Compound(
            label="pillar",
            wrapped=pillar.moved(bd.Location((0, 0, 5))).wrapped,
        ),
    ],
)
result = assy
```

## Positioning with Location

```python
# Location(translation_tuple) or Location(translation, rotation)
loc = bd.Location((10, 20, 5))
loc_rotated = bd.Location((0, 0, 10), (0, 0, 45))  # translate + rotate 45 deg around Z

moved_part = part.moved(loc)
```

## Grid / Array Patterns

```python
with BuildPart() as part:
    with bd.GridLocations(x_spacing=20, y_spacing=20, x_count=3, y_count=3):
        Cylinder(radius=3, height=10)

result = part.part
```

## Polar Pattern

```python
with BuildPart() as part:
    Box(50, 50, 5)
    with bd.PolarLocations(radius=18, count=6):
        Cylinder(radius=2, height=10, mode=Mode.SUBTRACT)

result = part.part
```

## Joints

build123d supports parametric joints for assemblies:

```python
with BuildPart() as base_builder:
    Box(50, 50, 5)
base = base_builder.part

with BuildPart() as pin_builder:
    Cylinder(radius=3, height=15)
pin = pin_builder.part

# Create a rigid joint
base_joint = bd.RigidJoint(
    label="pin_mount",
    to_part=base,
    joint_location=bd.Location((0, 0, 5)),
)
pin_joint = bd.RigidJoint(
    label="base",
    to_part=pin,
    joint_location=bd.Location((0, 0, 0)),
)
base_joint.connect_to(pin_joint)
```

## Exporting Assemblies

```python
# Export as STEP (preserves assembly structure)
export_step(assy, "assembly.step")

# Export as STL (single mesh, no assembly info)
export_stl(assy, "assembly.stl")
```

## Multi-Part Workflow

```python
# Build multiple parts separately
with BuildPart() as housing_builder:
    Box(40, 40, 30)
    Shell(housing_builder.faces().sort_by(Axis.Z)[-1], thickness=-2)
housing = housing_builder.part

with BuildPart() as lid_builder:
    Box(40, 40, 3)
lid = lid_builder.part

# Position lid on top of housing
lid_positioned = lid.moved(bd.Location((0, 0, 30)))

# Combine for visualization / export
result = bd.Compound(children=[housing, lid_positioned])
```

## Tips

1. Use `bd.Location((x, y, z))` for translation and `bd.Location((x,y,z), (rx,ry,rz))` for translate+rotate.
2. `GridLocations` and `PolarLocations` create array patterns efficiently.
3. Export assemblies as STEP to preserve part structure; STL flattens to a single mesh.
4. Joints are useful for parametric assemblies where parts can be repositioned.
5. Assign result to `result` for CadForge export — works with `Part`, `Compound`, or `Shape`.
