# CadForge

AI-powered CLI CAD tool for 3D printing. Uses CadQuery for parametric modeling, an Obsidian-style knowledge vault with RAG, and Claude as the AI backbone.

## Quick Start

```bash
# Clone and set up
cd /path/to/CadForge
python3 -m venv venv
source venv/bin/activate

# Core install (agent + chat + vault text search)
pip install -e ".[dev]"

# Full install — mesh, RAG, viewer (works on all Python versions)
pip install -e ".[full,dev]"

# Or pick extras individually
pip install -e ".[mesh]"      # trimesh analysis
pip install -e ".[rag]"       # LanceDB + sentence-transformers
pip install -e ".[viewer]"    # PyVista 3D viewer
pip install -e ".[cad]"       # CadQuery (Python <=3.12 only)

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Initialize a project (or use existing)
cadforge init

# Index the knowledge vault
cadforge index

# Start chatting
cadforge chat
```

> **Note:** CadQuery requires `cadquery-ocp` (OpenCascade bindings) which only
> has wheels for Python 3.12 and below. On Python 3.13+, use
> `conda install -c cadquery cadquery`, or install without CadQuery using
> `pip install -e ".[full,dev]"` — the agent can still generate CadQuery code
> (you run it externally) and all other features work normally.

## Commands

| Command | Description |
|---------|-------------|
| `cadforge chat` | Start interactive chat session |
| `cadforge init [path]` | Initialize a new CadForge project |
| `cadforge index [--incremental]` | Index the knowledge vault |
| `cadforge view <file>` | Preview an STL file |
| `cadforge resume` | Resume the last session |

## Slash Commands (Skills)

| Command | Description |
|---------|-------------|
| `/commit` | Create a git commit |
| `/review` | Review code changes |
| `/dfm-check` | Analyze model for manufacturing issues |
| `/help` | Show available commands |
| `/quit` | Exit CadForge |

## Architecture

CadForge mirrors Claude Code's agent architecture with 8 core subsystems:

1. **Permission System** — deny/allow/ask rule evaluation
2. **Memory Hierarchy** — 4-tier CADFORGE.md system
3. **Session Persistence** — JSONL transcript storage
4. **Context Management** — automatic compaction
5. **Hooks System** — PreToolUse/PostToolUse lifecycle
6. **Tool System** — 11 built-in tools with permission gating
7. **Skills System** — SKILL.md slash commands
8. **Subagent Spawner** — explore, plan, cad agents

## Tools

| Tool | Description |
|------|-------------|
| ExecuteCadQuery | Run CadQuery code, export STL |
| ReadFile | Read file contents |
| WriteFile | Write content to file |
| ListFiles | List files with glob pattern |
| SearchVault | Hybrid vault search (vector + FTS) |
| AnalyzeMesh | Mesh analysis + DFM checks |
| ShowPreview | Open 3D viewer |
| ExportModel | Export to STEP or 3MF |
| Bash | Shell command execution |
| GetPrinter | Get active printer profile |
| SearchWeb | Web search for references |

## Knowledge Vault

The `vault/` directory contains Obsidian-compatible markdown files:

- **materials/** — PLA, PETG, ABS properties and design rules
- **design-rules/** — overhangs, wall thickness, tolerances
- **cadquery/** — primitives, boolean ops, performance tips
- **patterns/** — snap-fits, threads, press-fits
- **printers/** — printer profiles (Prusa MK4, Bambu X1C, etc.)

## Printer Profiles

Set your printer in `CADFORGE.md` or `.cadforge/settings.json`:

```json
{"printer": "prusa-mk4"}
```

Available profiles: `prusa-mk4`, `bambu-x1c`, `bambu-a1`, `ender-3-v3`, `voron-2.4`

Add custom printers by copying `vault/printers/custom-template.md`.

## Configuration

### `.cadforge/settings.json`

```json
{
  "permissions": {
    "deny": ["Bash(rm:*)"],
    "allow": ["ReadFile(*)"],
    "ask": ["ExecuteCadQuery(*)"]
  },
  "hooks": [],
  "model": "claude-sonnet-4-5-20250929",
  "printer": "prusa-mk4"
}
```

### Memory Hierarchy

| Priority | File | Purpose |
|----------|------|---------|
| 1 | `.cadforge/CADFORGE.local.md` | Personal project prefs (gitignored) |
| 2 | `CADFORGE.md` | Team conventions (version controlled) |
| 3 | `~/.cadforge/CADFORGE.md` | Personal global preferences |
| 4 | `.cadforge/memory/MEMORY.md` | Auto-memory (agent-written) |

## Development

```bash
# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_config.py -v

# Run with coverage
pytest tests/ --cov=cadforge
```

## License

MIT
