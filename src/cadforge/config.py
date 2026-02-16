"""CadForge configuration management.

Loads and merges settings from project and user-level settings.json files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadforge.utils.paths import (
    get_project_settings_path,
    get_user_settings_path,
)


DEFAULT_PERMISSIONS = {
    "deny": ["Bash(rm:*)", "Bash(sudo:*)", "WriteFile(**/.env)"],
    "allow": ["ReadFile(*)", "SearchVault(*)", "AnalyzeMesh(*)", "GetPrinter(*)"],
    "ask": ["ExecuteCadQuery(*)", "WriteFile(*)", "Bash(*)", "ExportModel(*)"],
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "permissions": DEFAULT_PERMISSIONS,
    "hooks": [],
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 8192,
    "temperature": 0.0,
    "printer": None,
}


@dataclass
class CadForgeSettings:
    """Merged CadForge settings."""

    permissions: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_PERMISSIONS))
    hooks: list[dict[str, Any]] = field(default_factory=list)
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 8192
    temperature: float = 0.0
    printer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "permissions": self.permissions,
            "hooks": self.hooks,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "printer": self.printer,
        }


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning empty dict if not found or invalid."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base, returning new dict.

    - Dicts are recursively merged
    - Lists are replaced (not appended)
    - Scalars are replaced
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(project_root: Path | None = None) -> CadForgeSettings:
    """Load and merge settings from user + project levels.

    Precedence: project settings override user settings override defaults.
    """
    merged = dict(DEFAULT_SETTINGS)

    # User-level settings (lower precedence)
    user_path = get_user_settings_path()
    user_settings = load_json_file(user_path)
    if user_settings:
        merged = deep_merge(merged, user_settings)

    # Project-level settings (higher precedence)
    if project_root is not None:
        project_path = get_project_settings_path(project_root)
        project_settings = load_json_file(project_path)
        if project_settings:
            merged = deep_merge(merged, project_settings)

    return CadForgeSettings(
        permissions=merged.get("permissions", DEFAULT_PERMISSIONS),
        hooks=merged.get("hooks", []),
        model=merged.get("model", "claude-sonnet-4-5-20250929"),
        max_tokens=merged.get("max_tokens", 8192),
        temperature=merged.get("temperature", 0.0),
        printer=merged.get("printer"),
    )


def save_settings(settings: CadForgeSettings, path: Path) -> None:
    """Save settings to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def validate_settings(settings: CadForgeSettings) -> list[str]:
    """Validate settings, returning list of error messages (empty if valid)."""
    errors = []

    if not isinstance(settings.permissions, dict):
        errors.append("permissions must be a dict")
    else:
        for key in ("deny", "allow", "ask"):
            if key not in settings.permissions:
                errors.append(f"permissions.{key} is required")
            elif not isinstance(settings.permissions[key], list):
                errors.append(f"permissions.{key} must be a list")

    if not isinstance(settings.hooks, list):
        errors.append("hooks must be a list")

    if not isinstance(settings.max_tokens, int) or settings.max_tokens < 1:
        errors.append("max_tokens must be a positive integer")

    if not isinstance(settings.temperature, (int, float)) or not (0.0 <= settings.temperature <= 1.0):
        errors.append("temperature must be a float between 0.0 and 1.0")

    return errors
