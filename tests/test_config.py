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
        assert s.provider == "anthropic"
        assert s.model == "claude-sonnet-4-5-20250929"
        assert s.max_tokens == 8192
        assert s.temperature == 0.0
        assert s.printer is None
        assert s.base_url is None
        assert "deny" in s.permissions
        assert "allow" in s.permissions
        assert "ask" in s.permissions

    def test_to_dict_roundtrip(self):
        s = CadForgeSettings(printer="prusa-mk4")
        d = s.to_dict()
        assert d["printer"] == "prusa-mk4"
        assert d["model"] == "claude-sonnet-4-5-20250929"
        assert d["provider"] == "anthropic"
        assert d["base_url"] is None

    def test_ollama_settings(self):
        s = CadForgeSettings(
            provider="ollama",
            model="qwen2.5-coder:14b",
            base_url="http://localhost:11434/v1",
        )
        d = s.to_dict()
        assert d["provider"] == "ollama"
        assert d["model"] == "qwen2.5-coder:14b"
        assert d["base_url"] == "http://localhost:11434/v1"


class TestLoadSettings:
    def test_defaults_when_no_files(self, tmp_path: Path):
        s = load_settings(tmp_path)
        assert s.permissions == DEFAULT_PERMISSIONS
        assert s.hooks == []

    def test_project_overrides_defaults(self, tmp_project: Path):
        s = load_settings(tmp_project)
        assert s.permissions["deny"] == ["Bash(rm:*)"]
        assert s.permissions["allow"] == ["ReadFile(*)"]

    def test_load_ollama_settings(self, tmp_path: Path):
        cadforge_dir = tmp_path / ".cadforge"
        cadforge_dir.mkdir()
        (cadforge_dir / "settings.json").write_text(json.dumps({
            "provider": "ollama",
            "model": "qwen2.5-coder:14b",
            "base_url": "http://localhost:11434/v1",
        }))
        s = load_settings(tmp_path)
        assert s.provider == "ollama"
        assert s.model == "qwen2.5-coder:14b"
        assert s.base_url == "http://localhost:11434/v1"

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

    def test_invalid_provider(self):
        s = CadForgeSettings()
        s.provider = "invalid"
        errors = validate_settings(s)
        assert any("provider" in e for e in errors)

    def test_valid_ollama_provider(self):
        s = CadForgeSettings(provider="ollama", model="qwen2.5-coder:14b")
        errors = validate_settings(s)
        assert errors == []

    def test_invalid_base_url_type(self):
        s = CadForgeSettings()
        s.base_url = 12345
        errors = validate_settings(s)
        assert any("base_url" in e for e in errors)


class TestCmdConfig:
    """Tests for the cadforge config CLI subcommand."""

    def test_cmd_config_show(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="show", key=None, value=None)
        ret = cmd_config(args)
        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "provider" in data
        assert "model" in data

    def test_cmd_config_get(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="get", key="provider", value=None)
        ret = cmd_config(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "anthropic" in captured.out

    def test_cmd_config_get_unknown_key(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="get", key="nonexistent", value=None)
        ret = cmd_config(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "Unknown key" in captured.err

    def test_cmd_config_get_missing_key(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="get", key=None, value=None)
        ret = cmd_config(args)
        assert ret == 1

    def test_cmd_config_set(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="set", key="provider", value="ollama")
        ret = cmd_config(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "provider = ollama" in captured.out

        # Verify persisted
        settings_path = tmp_project / ".cadforge" / "settings.json"
        data = json.loads(settings_path.read_text())
        assert data["provider"] == "ollama"

    def test_cmd_config_set_max_tokens(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="set", key="max_tokens", value="4096")
        ret = cmd_config(args)
        assert ret == 0

        settings_path = tmp_project / ".cadforge" / "settings.json"
        data = json.loads(settings_path.read_text())
        assert data["max_tokens"] == 4096

    def test_cmd_config_set_temperature(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="set", key="temperature", value="0.5")
        ret = cmd_config(args)
        assert ret == 0

        settings_path = tmp_project / ".cadforge" / "settings.json"
        data = json.loads(settings_path.read_text())
        assert data["temperature"] == 0.5

    def test_cmd_config_set_invalid_provider(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="set", key="provider", value="invalid")
        ret = cmd_config(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "Validation error" in captured.err

    def test_cmd_config_set_invalid_max_tokens(self, tmp_project: Path, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: tmp_project
        )
        args = argparse.Namespace(action="set", key="max_tokens", value="notanumber")
        ret = cmd_config(args)
        assert ret == 1

    def test_cmd_config_no_project(self, capsys, monkeypatch):
        from cadforge.cli import cmd_config
        import argparse

        monkeypatch.setattr(
            "cadforge.utils.paths.find_project_root", lambda start=None: None
        )
        args = argparse.Namespace(action="show", key=None, value=None)
        ret = cmd_config(args)
        assert ret == 1
