"""Tests for CadForge configuration management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadforge.config import (
    CadForgeSettings,
    deep_merge,
    load_json_file,
    load_settings,
    save_settings,
    validate_settings,
    DEFAULT_PERMISSIONS,
)


class TestDeepMerge:
    def test_shallow_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_list_replacement(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}


class TestLoadJsonFile:
    def test_load_valid_file(self, tmp_path: Path):
        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}')
        assert load_json_file(p) == {"key": "value"}

    def test_load_missing_file(self, tmp_path: Path):
        p = tmp_path / "missing.json"
        assert load_json_file(p) == {}

    def test_load_invalid_json(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        assert load_json_file(p) == {}


class TestCadForgeSettings:
    def test_defaults(self):
        s = CadForgeSettings()
        assert s.model == "claude-sonnet-4-5-20250929"
        assert s.max_tokens == 8192
        assert s.temperature == 0.0
        assert s.printer is None
        assert "deny" in s.permissions
        assert "allow" in s.permissions
        assert "ask" in s.permissions

    def test_to_dict_roundtrip(self):
        s = CadForgeSettings(printer="prusa-mk4")
        d = s.to_dict()
        assert d["printer"] == "prusa-mk4"
        assert d["model"] == "claude-sonnet-4-5-20250929"


class TestLoadSettings:
    def test_defaults_when_no_files(self, tmp_path: Path):
        s = load_settings(tmp_path)
        assert s.permissions == DEFAULT_PERMISSIONS
        assert s.hooks == []

    def test_project_overrides_defaults(self, tmp_project: Path):
        s = load_settings(tmp_project)
        assert s.permissions["deny"] == ["Bash(rm:*)"]
        assert s.permissions["allow"] == ["ReadFile(*)"]

    def test_project_overrides_user(self, tmp_project: Path, tmp_path: Path, monkeypatch):
        user_dir = tmp_path / "home" / ".cadforge"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text(json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "permissions": {
                "deny": [],
                "allow": ["ReadFile(*)"],
                "ask": [],
            },
        }))
        monkeypatch.setattr(
            "cadforge.config.get_user_settings_path",
            lambda: user_dir / "settings.json",
        )
        s = load_settings(tmp_project)
        # Project permissions override user
        assert s.permissions["deny"] == ["Bash(rm:*)"]


class TestSaveSettings:
    def test_save_and_reload(self, tmp_path: Path):
        s = CadForgeSettings(printer="bambu-x1c", model="claude-opus-4-6")
        path = tmp_path / "settings.json"
        save_settings(s, path)
        data = json.loads(path.read_text())
        assert data["printer"] == "bambu-x1c"
        assert data["model"] == "claude-opus-4-6"

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "sub" / "dir" / "settings.json"
        save_settings(CadForgeSettings(), path)
        assert path.exists()


class TestValidateSettings:
    def test_valid_defaults(self):
        errors = validate_settings(CadForgeSettings())
        assert errors == []

    def test_missing_permissions_key(self):
        s = CadForgeSettings()
        s.permissions = {"deny": [], "allow": []}  # missing "ask"
        errors = validate_settings(s)
        assert any("ask" in e for e in errors)

    def test_invalid_max_tokens(self):
        s = CadForgeSettings()
        s.max_tokens = -1
        errors = validate_settings(s)
        assert any("max_tokens" in e for e in errors)

    def test_invalid_temperature(self):
        s = CadForgeSettings()
        s.temperature = 2.0
        errors = validate_settings(s)
        assert any("temperature" in e for e in errors)

    def test_permissions_not_dict(self):
        s = CadForgeSettings()
        s.permissions = "invalid"
        errors = validate_settings(s)
        assert any("permissions" in e for e in errors)
