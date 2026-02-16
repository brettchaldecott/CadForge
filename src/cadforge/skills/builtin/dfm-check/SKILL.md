---
name: dfm-check
description: Analyze a 3D model for Design for Manufacturing issues
allowed-tools: "AnalyzeMesh, SearchVault, ReadFile, GetPrinter"
---

When asked to check a design for manufacturing issues:
1. Load the STL file using AnalyzeMesh to get geometry metrics
2. Get the active printer profile with GetPrinter
3. Search the vault for material-specific design rules
4. Check the following DFM criteria:
   - Watertightness (mesh must be manifold)
   - Wall thickness meets minimum for material
   - Overhangs within printer capability (typically 45 degrees)
   - Bridge spans within limits
   - Part fits within build volume
   - No inverted normals
5. Report issues with specific descriptions and fix suggestions
6. Rate the design: PASS, WARN (minor issues), or FAIL (critical issues)
