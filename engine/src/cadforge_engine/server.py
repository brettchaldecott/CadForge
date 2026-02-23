"""Uvicorn startup for CadForge Engine."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Start the CadForge Engine server."""
    parser = argparse.ArgumentParser(description="CadForge Engine Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8741, help="Bind port (default: 8741)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument(
        "--service",
        action="store_true",
        help="Enable standalone service mode (binds 0.0.0.0, enables CORS and auth)",
    )
    parser.add_argument("--api-key", default=None, help="API key for authentication (service mode)")
    parser.add_argument(
        "--cors-origins",
        default=None,
        help="Comma-separated CORS origins (service mode, default: *)",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    # Service mode overrides
    host = args.host
    if args.service and host == "127.0.0.1":
        host = "0.0.0.0"

    # Store service config in environment for the factory
    import os

    if args.service:
        os.environ["CADFORGE_SERVICE_MODE"] = "1"
    if args.api_key:
        os.environ["CADFORGE_API_KEY"] = args.api_key
    if args.cors_origins:
        os.environ["CADFORGE_CORS_ORIGINS"] = args.cors_origins

    uvicorn.run(
        "cadforge_engine.app:create_app",
        factory=True,
        host=host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
