"""Tests for model export utilities."""

from __future__ import annotations

import pytest

from cadforge.cad.exporter import get_export_formats


class TestExporter:
    def test_supported_formats(self):
        formats = get_export_formats()
        assert "stl" in formats
        assert "step" in formats
        assert "3mf" in formats
        assert len(formats) == 3
