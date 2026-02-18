/**
 * Memory hierarchy loader — 4-tier system.
 *
 * 1. .cadforge/CADFORGE.local.md (personal project, gitignored)
 * 2. CADFORGE.md (team project, version controlled)
 * 3. ~/.cadforge/CADFORGE.md (personal global)
 * 4. .cadforge/memory/MEMORY.md (auto-memory, agent-written)
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { getCadforgeDir } from '../config/paths.js';

const MAX_AUTO_MEMORY_LINES = 200;

export interface MemoryEntry {
  path: string;
  content: string;
  tier: number;
  label: string;
}

export interface MemoryHierarchy {
  entries: MemoryEntry[];
}

function readFile(path: string, maxLines?: number): string | null {
  if (!existsSync(path)) return null;
  try {
    let text = readFileSync(path, 'utf-8');
    if (!text.trim()) return null;
    if (maxLines !== undefined) {
      const lines = text.split('\n');
      if (lines.length > maxLines) {
        text = lines.slice(0, maxLines).join('\n');
        text += `\n\n<!-- truncated at ${maxLines} lines -->`;
      }
    }
    return text;
  } catch {
    return null;
  }
}

export function getMemoryDir(projectRoot: string): string {
  const d = join(getCadforgeDir(projectRoot), 'memory');
  mkdirSync(d, { recursive: true });
  return d;
}

/**
 * Get system prompt content from all memory entries.
 */
export function getSystemPromptContent(hierarchy: MemoryHierarchy): string {
  if (hierarchy.entries.length === 0) return '';
  const sorted = [...hierarchy.entries].sort((a, b) => a.tier - b.tier);
  return sorted.map((e) => `# ${e.label}\n\n${e.content}`).join('\n\n---\n\n');
}

/**
 * Load memory from all four tiers.
 */
export function loadMemory(projectRoot: string): MemoryHierarchy {
  const entries: MemoryEntry[] = [];

  // Tier 1: Personal project prefs (gitignored)
  const localMd = join(getCadforgeDir(projectRoot), 'CADFORGE.local.md');
  let content = readFile(localMd);
  if (content) {
    entries.push({ path: localMd, content, tier: 1, label: 'Personal Project Preferences' });
  }

  // Tier 2: Team project conventions
  const projectMd = join(projectRoot, 'CADFORGE.md');
  content = readFile(projectMd);
  if (content) {
    entries.push({ path: projectMd, content, tier: 2, label: 'Project Conventions' });
  }

  // Tier 3: Personal global preferences
  const userMd = join(homedir(), '.cadforge', 'CADFORGE.md');
  content = readFile(userMd);
  if (content) {
    entries.push({ path: userMd, content, tier: 3, label: 'User Preferences' });
  }

  // Tier 4: Auto-memory (truncated)
  const autoMd = join(getMemoryDir(projectRoot), 'MEMORY.md');
  content = readFile(autoMd, MAX_AUTO_MEMORY_LINES);
  if (content) {
    entries.push({ path: autoMd, content, tier: 4, label: 'Auto-Memory' });
  }

  return { entries };
}

export function writeAutoMemory(projectRoot: string, content: string): string {
  const dir = getMemoryDir(projectRoot);
  const path = join(dir, 'MEMORY.md');
  writeFileSync(path, content, 'utf-8');
  return path;
}

export function appendAutoMemory(projectRoot: string, text: string): string {
  const dir = getMemoryDir(projectRoot);
  const path = join(dir, 'MEMORY.md');
  let existing = '';
  if (existsSync(path)) {
    existing = readFileSync(path, 'utf-8');
    if (existing && !existing.endsWith('\n')) existing += '\n';
  }
  writeFileSync(path, existing + text + '\n', 'utf-8');
  return path;
}
