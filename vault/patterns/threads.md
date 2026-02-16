---
name: Thread Design for 3D Printing
category: pattern
technology: fdm
applies_to: [PLA, PETG, ABS]
tags: [pattern, thread, screw, insert, fastener, fdm]
---

# Thread Design for 3D Printing

## Overview

Threaded connections in 3D-printed parts can be achieved through three main
approaches: directly printed threads, heat-set threaded inserts, or tapping
printed pilot holes. Each approach has trade-offs in strength, durability,
precision, and complexity. This guide covers all three methods.

## Approach Comparison

| Method              | Strength   | Durability | Precision | Effort   | Cost  |
|---------------------|------------|------------|-----------|----------|-------|
| Printed threads     | Low-Medium | Low        | Low       | Minimal  | Free  |
| Heat-set inserts    | High       | High       | High      | Moderate | $0.05 |
| Tapped pilot holes  | Medium     | Medium     | Medium    | Moderate | Free  |
| Captured hex nuts   | High       | High       | High      | Low      | $0.02 |

## 1. Directly Printed Threads

### When to Use
- Low-force applications (caps, lids, adjustment knobs)
- Large thread pitch (M8 or larger works best)
- Prototyping and non-critical connections

### Design Rules

| Parameter              | Value         | Notes                         |
|------------------------|---------------|-------------------------------|
| Minimum thread size    | M6            | M8+ recommended               |
| Thread pitch           | Coarse only   | Fine threads are unprintable  |
| Clearance on diameter  | +0.4 mm       | Add to nominal OD and ID      |
| Thread depth           | 50--75% of std| Reduce engagement depth       |
| Layer height           | <= 0.15 mm    | Finer layers = better threads |
| Print orientation      | Vertical      | Thread axis along Z           |
| Lead-in chamfer        | 1.0--1.5 mm   | Helps thread engagement       |

### Trapezoidal vs Metric Threads

For FDM printing, trapezoidal (ACME) threads are far superior to standard metric
(triangular) threads:
- Wider flat crests print cleanly
- Less likely to strip under load
- Easier to model in CAD

```
Metric (V-thread):     Trapezoidal:
    /\                   ____
   /  \                 /    \
  /    \               /      \
 /      \             /        \
```

### CadQuery Thread Example

```python
import cadquery as cq

# Simple external thread using helix
pitch = 2.0       # mm
diameter = 10.0   # mm
length = 15.0     # mm
n_turns = length / pitch

thread_profile = (cq.Workplane("XZ")
    .center(diameter/2, 0)
    .polygon(3, pitch * 0.8)  # triangular cross-section
)

# Note: for production threads, use the cq_warehouse thread library
```

### Recommended Library: cq_warehouse

The `cq_warehouse` package provides parametric ISO and ACME threads:

```python
from cq_warehouse.thread import IsoThread

thread = IsoThread(
    major_diameter=10,
    pitch=1.5,
    length=15,
    external=True
)
```

## 2. Heat-Set Threaded Inserts (Recommended)

Heat-set brass inserts provide metal threads in plastic parts. They are the
gold standard for 3D-printed assemblies.

### How They Work
1. Design a pilot hole in the printed part
2. Heat the insert with a soldering iron (set to material temperature + 20 C)
3. Press the insert into the hole -- it melts into the surrounding plastic
4. Allow to cool -- the knurled exterior grips the solidified plastic

### Insert Sizes and Pilot Holes

| Insert Size | Insert OD (mm) | Pilot Hole (mm) | Hole Depth (mm) | Min Boss OD (mm) |
|-------------|-----------------|------------------|------------------|-------------------|
| M2          | 3.2             | 3.0              | 4.0              | 6.0               |
| M2.5        | 3.8             | 3.6              | 5.0              | 7.0               |
| M3          | 4.6             | 4.2              | 5.0              | 8.0               |
| M4          | 5.6             | 5.2              | 7.0              | 10.0              |
| M5          | 7.0             | 6.5              | 8.0              | 12.0              |

### Design Rules for Heat-Set Inserts

- **Wall thickness around insert**: minimum 1.5x insert OD
- **Pilot hole depth**: insert length + 1 mm (to allow plastic to flow)
- **Chamfer at top**: 0.5 mm x 45 degrees to guide the insert
- **Print orientation**: hole axis along Z for best roundness
- **Material**: all common FDM materials work. ABS and PETG are best due to
  higher temperature and better insert grip.

### Installation Tips

- Set soldering iron to material Tg + 20 C (PLA: 80 C, PETG: 100 C, ABS: 125 C)
- Use a dedicated insert tip for your soldering iron
- Push straight down with steady pressure -- do not wobble
- Stop when insert is flush or 0.2 mm below surface
- Allow 30 seconds to cool before applying load

## 3. Tapped Pilot Holes

Drill an undersized hole and cut threads with a standard tap.

| Thread | Tap Drill (mm) | Printed Hole (mm) | Notes               |
|--------|-----------------|---------------------|---------------------|
| M3     | 2.5             | 2.6                 | Add 0.1 for FDM     |
| M4     | 3.3             | 3.4                 |                     |
| M5     | 4.2             | 4.3                 |                     |
| M6     | 5.0             | 5.1                 |                     |

- Tap slowly with cutting oil or wax
- Limit to 3--5 assembly cycles before threads wear out
- Works best in ABS and PETG

## 4. Captured Hex Nut Pockets

Design a hexagonal pocket into the printed part to capture a standard hex nut.

| Nut Size | Hex Width (mm) | Pocket Width (mm) | Pocket Depth (mm) |
|----------|----------------|--------------------|--------------------|
| M2       | 4.0            | 4.4                | 1.8                |
| M3       | 5.5            | 5.9                | 2.6                |
| M4       | 7.0            | 7.4                | 3.4                |
| M5       | 8.0            | 8.4                | 4.2                |

- Add 0.3--0.4 mm to hex width for clearance
- Add 0.2 mm to depth for clearance
- Include a screw clearance hole from the other side
- Can pause print to insert nut, or use a side-loading pocket

## Recommendations by Use Case

| Use Case                    | Best Method        |
|-----------------------------|--------------------|
| Enclosure assembly          | Heat-set inserts   |
| Adjustment screw            | Printed ACME thread|
| Prototype, temporary        | Tapped pilot hole  |
| High-vibration environment  | Heat-set insert    |
| Lid or cap                  | Printed thread M8+ |
| Structural joint            | Captured hex nut   |
| Field-serviceable           | Heat-set insert    |
