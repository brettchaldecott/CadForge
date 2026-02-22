"""FastAPI application factory for CadForge Engine."""

from __future__ import annotations

import os

from fastapi import FastAPI

from cadforge_engine import __version__
from cadforge_engine.routes import health, cadquery, mesh, export, vault, subagent, render, pipeline, tasks, designs, competitive


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Service mode is controlled via environment variables:
        CADFORGE_SERVICE_MODE=1 — enable CORS and auth middleware
        CADFORGE_API_KEY — API key for auth (optional, skipped if unset)
        CADFORGE_CORS_ORIGINS — comma-separated CORS origins (default: *)
    """
    app = FastAPI(
        title="CadForge Engine",
        version=__version__,
        description="Python backend for CadForge — CadQuery sandbox, mesh analysis, vault indexing",
    )

    # Service mode: add CORS and auth middleware
    service_mode = os.environ.get("CADFORGE_SERVICE_MODE") == "1"
    if service_mode:
        from starlette.middleware.cors import CORSMiddleware

        from cadforge_engine.middleware.auth import APIKeyMiddleware

        cors_env = os.environ.get("CADFORGE_CORS_ORIGINS", "*")
        origins = [o.strip() for o in cors_env.split(",")]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(APIKeyMiddleware)

    # Register route modules
    app.include_router(health.router)
    app.include_router(cadquery.router)
    app.include_router(mesh.router)
    app.include_router(export.router)
    app.include_router(vault.router)
    app.include_router(subagent.router)
    app.include_router(render.router)
    app.include_router(pipeline.router)
    app.include_router(tasks.router)
    app.include_router(designs.router)
    app.include_router(competitive.router)

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
