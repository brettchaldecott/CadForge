# CadForge Project

## Overview
AI-powered CLI CAD tool for 3D printing, using CadQuery for parametric modeling.

## Conventions
- Python 3.10+, type hints throughout
- CadQuery for all 3D geometry
- Tests in tests/ using pytest with session-scoped fixtures
- Output files go to output/ (gitignored)
- Vault markdown files in vault/ for RAG knowledge base

## Architecture
- Agent loop: gather context → act (tool use) → verify results
- Permission system: deny → allow → ask evaluation chain
- Memory hierarchy: local > project > user > auto-memory
- JSONL session persistence with context compaction
