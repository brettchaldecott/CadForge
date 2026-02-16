"""Tests for CadQuery sandbox execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadforge.cad.sandbox import (
    SandboxResult,
    _make_safe_builtins,
    build_namespace,
    execute_cadquery,
)


class TestSafeBuiltins:
    def test_includes_safe_functions(self):
        builtins = _make_safe_builtins()
        assert "len" in builtins
        assert "range" in builtins
        assert "int" in builtins
        assert "float" in builtins
        assert "print" in builtins
        assert "list" in builtins
        assert "dict" in builtins
        assert "sorted" in builtins

    def test_excludes_dangerous_functions(self):
        builtins = _make_safe_builtins()
        assert "open" not in builtins
        assert "exec" not in builtins
        assert "eval" not in builtins
        assert "__import__" not in builtins
        assert "compile" not in builtins
        assert "globals" not in builtins
        assert "locals" not in builtins


class TestBuildNamespace:
    def test_has_math(self):
        ns = build_namespace()
        assert "math" in ns
        assert hasattr(ns["math"], "pi")

    def test_has_builtins(self):
        ns = build_namespace()
        assert "__builtins__" in ns


class TestSandboxResult:
    def test_success_result(self):
        r = SandboxResult(success=True, result="value")
        assert r.success is True

    def test_error_result(self):
        r = SandboxResult(success=False, error="syntax error")
        assert r.success is False
        assert r.error == "syntax error"

    def test_has_workpiece(self):
        r = SandboxResult(success=True, variables={"result": "mock"})
        assert r.has_workpiece is True

    def test_no_workpiece(self):
        r = SandboxResult(success=True, variables={"x": 42})
        assert r.has_workpiece is False


class TestExecuteCadquery:
    def test_simple_math(self):
        result = execute_cadquery("result = 2 + 2")
        assert result.success is True
        assert result.variables.get("result") == 4

    def test_uses_math_module(self):
        result = execute_cadquery("result = math.pi")
        assert result.success is True
        assert abs(result.variables["result"] - 3.14159) < 0.001

    def test_captures_stdout(self):
        result = execute_cadquery("print('hello sandbox')")
        assert result.success is True
        assert "hello sandbox" in result.stdout

    def test_captures_error(self):
        result = execute_cadquery("x = 1 / 0")
        assert result.success is False
        assert "ZeroDivisionError" in result.error or "division" in result.error

    def test_syntax_error(self):
        result = execute_cadquery("def (invalid syntax")
        assert result.success is False

    def test_blocks_import(self):
        result = execute_cadquery("import os")
        assert result.success is False

    def test_blocks_open(self):
        result = execute_cadquery("f = open('/etc/passwd')")
        assert result.success is False

    def test_extra_namespace(self):
        result = execute_cadquery(
            "result = my_value * 2",
            extra_namespace={"my_value": 21},
        )
        assert result.success is True
        assert result.variables["result"] == 42

    def test_multiline_code(self):
        code = """
x = 10
y = 20
result = x + y
"""
        result = execute_cadquery(code)
        assert result.success is True
        assert result.variables["result"] == 30

    def test_list_comprehension(self):
        code = "result = [x**2 for x in range(5)]"
        result = execute_cadquery(code)
        assert result.success is True
        assert result.variables["result"] == [0, 1, 4, 9, 16]

    def test_r_alias_for_result(self):
        result = execute_cadquery("r = 42")
        assert result.success is True
        assert result.has_workpiece is True
