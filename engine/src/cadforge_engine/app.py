"""FastAPI application factory for CadForge Engine."""

from __future__ import annotations

from fastapi import FastAPI

from cadforge_engine import __version__
from cadforge_engine.routes import health, cadquery, mesh, export, vault, subagent


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CadForge Engine",
        version=__version__,
        description="Python backend for CadForge — CadQuery sandbox, mesh analysis, vault indexing",
    )

    # Register route modules
    app.include_router(health.router)
    app.include_router(cadquery.router)
    app.include_router(mesh.router)
    app.include_router(export.router)
    app.include_router(vault.router)
    app.include_router(subagent.router)

    # Load plugins
    _load_plugins(app)

    return app


def _load_plugins(app: FastAPI) -> None:
    """Discover and mount plugin routers from the plugins directory."""
    import importlib
    from pathlib import Path

    plugins_dir = Path(__file__).parent / "plugins"
    if not plugins_dir.is_dir():
        return

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        router_path = plugin_dir / "router.py"
        if not router_path.exists():
            continue

        try:
            module_name = f"cadforge_engine.plugins.{plugin_dir.name}.router"
            module = importlib.import_module(module_name)
            if hasattr(module, "router"):
                app.include_router(
                    module.router,
                    prefix=f"/plugins/{plugin_dir.name}",
                    tags=[f"plugin:{plugin_dir.name}"],
                )
        except Exception:
            # Skip broken plugins silently
            pass
