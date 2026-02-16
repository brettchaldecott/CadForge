"""Tests for CadForge memory hierarchy."""

from __future__ import annotations

from pathlib import Path

import pytest

from cadforge.core.memory import (
    MemoryEntry,
    MemoryHierarchy,
    append_auto_memory,
    list_topic_memories,
    load_memory,
    read_topic_memory,
    write_auto_memory,
    write_topic_memory,
)


class TestLoadMemory:
    def test_loads_project_cadforge_md(self, tmp_project: Path):
        hierarchy = load_memory(tmp_project)
        assert any(e.tier == 2 for e in hierarchy.entries)
        project_entry = next(e for e in hierarchy.entries if e.tier == 2)
        assert "Test Project" in project_entry.content

    def test_loads_auto_memory(self, tmp_project: Path):
        hierarchy = load_memory(tmp_project)
        assert any(e.tier == 4 for e in hierarchy.entries)

    def test_loads_local_cadforge_md(self, tmp_project: Path):
        local_md = tmp_project / ".cadforge" / "CADFORGE.local.md"
        local_md.write_text("# Local Overrides\nprefer-metric: true\n")
        hierarchy = load_memory(tmp_project)
        assert any(e.tier == 1 for e in hierarchy.entries)
        local_entry = next(e for e in hierarchy.entries if e.tier == 1)
        assert "Local Overrides" in local_entry.content

    def test_skips_missing_files(self, tmp_path: Path):
        (tmp_path / ".cadforge").mkdir()
        (tmp_path / ".cadforge" / "memory").mkdir()
        hierarchy = load_memory(tmp_path)
        assert len(hierarchy.entries) == 0

    def test_skips_empty_files(self, tmp_project: Path):
        (tmp_project / "CADFORGE.md").write_text("")
        hierarchy = load_memory(tmp_project)
        assert not any(e.tier == 2 for e in hierarchy.entries)


class TestAutoMemoryTruncation:
    def test_truncates_long_auto_memory(self, tmp_project: Path):
        memory_md = tmp_project / ".cadforge" / "memory" / "MEMORY.md"
        long_content = "\n".join(f"Line {i}" for i in range(300))
        memory_md.write_text(long_content)
        hierarchy = load_memory(tmp_project)
        auto = next(e for e in hierarchy.entries if e.tier == 4)
        assert "truncated at 200 lines" in auto.content
        assert auto.content.count("\n") < 210


class TestMemoryHierarchy:
    def test_system_prompt_content_ordering(self):
        hierarchy = MemoryHierarchy(entries=[
            MemoryEntry(Path("a"), "tier4 content", 4, "Auto"),
            MemoryEntry(Path("b"), "tier1 content", 1, "Local"),
            MemoryEntry(Path("c"), "tier2 content", 2, "Project"),
        ])
        content = hierarchy.get_system_prompt_content()
        # Should be ordered by tier
        assert content.index("tier1") < content.index("tier2")
        assert content.index("tier2") < content.index("tier4")

    def test_empty_hierarchy(self):
        hierarchy = MemoryHierarchy()
        assert hierarchy.get_system_prompt_content() == ""

    def test_total_lines(self):
        hierarchy = MemoryHierarchy(entries=[
            MemoryEntry(Path("a"), "line1\nline2\nline3", 1, "Test"),
        ])
        assert hierarchy.total_lines == 3


class TestWriteAutoMemory:
    def test_write_and_read(self, tmp_project: Path):
        write_auto_memory(tmp_project, "# New Memory\n- item 1\n")
        hierarchy = load_memory(tmp_project)
        auto = next(e for e in hierarchy.entries if e.tier == 4)
        assert "New Memory" in auto.content

    def test_overwrite(self, tmp_project: Path):
        write_auto_memory(tmp_project, "first")
        write_auto_memory(tmp_project, "second")
        hierarchy = load_memory(tmp_project)
        auto = next(e for e in hierarchy.entries if e.tier == 4)
        assert "second" in auto.content
        assert "first" not in auto.content


class TestAppendAutoMemory:
    def test_append(self, tmp_project: Path):
        write_auto_memory(tmp_project, "# Memory\n")
        append_auto_memory(tmp_project, "- new item")
        hierarchy = load_memory(tmp_project)
        auto = next(e for e in hierarchy.entries if e.tier == 4)
        assert "Memory" in auto.content
        assert "new item" in auto.content


class TestTopicMemory:
    def test_write_and_read_topic(self, tmp_project: Path):
        write_topic_memory(tmp_project, "debugging", "# Debug Notes\n")
        content = read_topic_memory(tmp_project, "debugging")
        assert content is not None
        assert "Debug Notes" in content

    def test_read_missing_topic(self, tmp_project: Path):
        assert read_topic_memory(tmp_project, "nonexistent") is None

    def test_list_topics(self, tmp_project: Path):
        write_topic_memory(tmp_project, "debugging", "# A\n")
        write_topic_memory(tmp_project, "materials", "# B\n")
        topics = list_topic_memories(tmp_project)
        assert "debugging" in topics
        assert "materials" in topics
        assert "MEMORY" not in topics  # Excluded
