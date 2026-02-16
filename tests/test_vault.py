"""Tests for the knowledge vault system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadforge.vault.chunker import chunk_markdown, extract_frontmatter, _split_sections
from cadforge.vault.indexer import (
    compute_file_hash,
    find_changes,
    index_vault,
    is_index_stale,
    load_manifest,
    save_manifest,
)
from cadforge.vault.schema import VaultChunk


@pytest.fixture
def vault_project(tmp_path: Path) -> Path:
    """Create a project with vault content."""
    (tmp_path / "CADFORGE.md").write_text("# Test\n")
    (tmp_path / ".cadforge").mkdir()
    (tmp_path / ".cadforge" / "memory").mkdir()
    (tmp_path / ".lance").mkdir()

    vault = tmp_path / "vault"
    vault.mkdir()

    # Materials
    materials = vault / "materials"
    materials.mkdir()
    (materials / "PLA.md").write_text(
        "---\ntags: [material, PLA, fdm]\n---\n\n"
        "# PLA\n\n## Properties\n- Density: 1.24 g/cm3\n- Print temp: 190-220C\n"
        "\n## Design Rules\n- Min wall: 0.8mm\n- Max overhang: 45 degrees\n"
    )
    (materials / "PETG.md").write_text(
        "---\ntags: [material, PETG, fdm]\n---\n\n"
        "# PETG\n\n## Properties\n- Density: 1.27 g/cm3\n- Print temp: 220-250C\n"
    )

    # Design rules
    rules = vault / "design-rules"
    rules.mkdir()
    (rules / "wall-thickness.md").write_text(
        "---\ntags: [design-rule, wall-thickness]\n---\n\n"
        "# Wall Thickness\n\n## Guidelines\n- Minimum: 2x nozzle diameter\n"
        "- For 0.4mm nozzle: 0.8mm minimum wall\n"
    )

    return tmp_path


class TestExtractFrontmatter:
    def test_with_frontmatter(self):
        content = "---\ntags: [a, b]\nname: test\n---\n# Body\ntext"
        fm, body = extract_frontmatter(content)
        assert fm["tags"] == ["a", "b"]
        assert fm["name"] == "test"
        assert "# Body" in body

    def test_without_frontmatter(self):
        content = "# Just markdown\nno frontmatter"
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "Just markdown" in body

    def test_empty_frontmatter(self):
        content = "---\n---\n# Body"
        fm, body = extract_frontmatter(content)
        assert fm == {}

    def test_invalid_yaml(self):
        content = "---\n[invalid yaml: {\n---\n# Body"
        fm, body = extract_frontmatter(content)
        assert fm == {}


class TestSplitSections:
    def test_multiple_sections(self):
        body = "intro\n\n## Section 1\ncontent 1\n\n## Section 2\ncontent 2\n"
        sections = _split_sections(body)
        assert len(sections) == 3  # overview + 2 sections
        assert sections[0][0] == "Overview"
        assert sections[1][0] == "Section 1"
        assert sections[2][0] == "Section 2"

    def test_no_headings(self):
        body = "just plain text\nno headings\n"
        sections = _split_sections(body)
        assert len(sections) == 1
        assert sections[0][0] == "Overview"

    def test_h1_heading(self):
        body = "# Title\ncontent\n"
        sections = _split_sections(body)
        assert any(s[0] == "Title" for s in sections)


class TestChunkMarkdown:
    def test_chunks_from_file(self, vault_project: Path):
        pla_path = vault_project / "vault" / "materials" / "PLA.md"
        vault_dir = vault_project / "vault"
        chunks = chunk_markdown(pla_path, base_dir=vault_dir)
        assert len(chunks) >= 2
        assert all(isinstance(c, VaultChunk) for c in chunks)
        assert all("PLA" in c.tags or "material" in c.tags for c in chunks)

    def test_chunk_ids_deterministic(self, vault_project: Path):
        pla_path = vault_project / "vault" / "materials" / "PLA.md"
        vault_dir = vault_project / "vault"
        c1 = chunk_markdown(pla_path, base_dir=vault_dir)
        c2 = chunk_markdown(pla_path, base_dir=vault_dir)
        assert [c.id for c in c1] == [c.id for c in c2]

    def test_relative_paths(self, vault_project: Path):
        pla_path = vault_project / "vault" / "materials" / "PLA.md"
        vault_dir = vault_project / "vault"
        chunks = chunk_markdown(pla_path, base_dir=vault_dir)
        assert all("materials/PLA.md" in c.file_path for c in chunks)


class TestVaultChunk:
    def test_to_dict(self):
        chunk = VaultChunk(
            id="abc123",
            file_path="materials/PLA.md",
            section="Properties",
            content="Density: 1.24 g/cm3",
            tags=["material", "PLA"],
        )
        d = chunk.to_dict()
        assert d["id"] == "abc123"
        assert d["tags"] == "material,PLA"


class TestManifest:
    def test_save_and_load(self, vault_project: Path):
        manifest = {"PLA.md": "hash1", "PETG.md": "hash2"}
        save_manifest(vault_project, manifest)
        loaded = load_manifest(vault_project)
        assert loaded == manifest

    def test_load_missing(self, tmp_path: Path):
        (tmp_path / ".lance").mkdir()
        assert load_manifest(tmp_path) == {}


class TestFindChanges:
    def test_all_new(self):
        added, modified, deleted = find_changes({"a": "1"}, {})
        assert added == ["a"]
        assert modified == []
        assert deleted == []

    def test_modified(self):
        added, modified, deleted = find_changes({"a": "2"}, {"a": "1"})
        assert added == []
        assert modified == ["a"]
        assert deleted == []

    def test_deleted(self):
        added, modified, deleted = find_changes({}, {"a": "1"})
        assert added == []
        assert modified == []
        assert deleted == ["a"]

    def test_mixed(self):
        current = {"a": "1", "b": "changed", "c": "new"}
        previous = {"a": "1", "b": "original", "d": "removed"}
        added, modified, deleted = find_changes(current, previous)
        assert "c" in added
        assert "b" in modified
        assert "d" in deleted
        assert "a" not in modified


class TestIndexVault:
    def test_index_creates_manifest(self, vault_project: Path):
        result = index_vault(vault_project)
        assert result["success"] is True
        assert result["files_indexed"] > 0
        assert result["chunks_created"] > 0

        # Manifest should exist now
        manifest = load_manifest(vault_project)
        assert len(manifest) > 0

    def test_incremental_no_changes(self, vault_project: Path):
        index_vault(vault_project)
        result = index_vault(vault_project, incremental=True)
        assert result["success"] is True
        assert result["files_indexed"] == 0

    def test_incremental_detects_changes(self, vault_project: Path):
        index_vault(vault_project)

        # Modify a file
        pla = vault_project / "vault" / "materials" / "PLA.md"
        pla.write_text(pla.read_text() + "\n## New Section\nNew content\n")

        result = index_vault(vault_project, incremental=True)
        assert result["success"] is True
        assert result["files_indexed"] == 1

    def test_no_vault_directory(self, tmp_path: Path):
        result = index_vault(tmp_path)
        assert result["success"] is False


class TestIsIndexStale:
    def test_stale_when_no_manifest(self, vault_project: Path):
        assert is_index_stale(vault_project) is True

    def test_not_stale_after_index(self, vault_project: Path):
        index_vault(vault_project)
        assert is_index_stale(vault_project) is False

    def test_stale_after_modification(self, vault_project: Path):
        index_vault(vault_project)
        pla = vault_project / "vault" / "materials" / "PLA.md"
        pla.write_text("# Modified\n")
        assert is_index_stale(vault_project) is True
