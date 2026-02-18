/**
 * Skill loader — discovers and parses SKILL.md files with YAML frontmatter.
 *
 * Discovers skills from three directories (highest priority first):
 * 1. Workspace: <projectRoot>/skills/
 * 2. User: ~/.cadforge/skills/
 * 3. Bundled: (future)
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export interface Skill {
  name: string;
  description: string;
  allowedTools: string[];
  prompt: string;
  source: string;
  priority: number;
}

/**
 * Load a skill from a directory containing SKILL.md.
 */
function loadSkill(skillDir: string, priority: number): Skill | null {
  const skillMd = join(skillDir, 'SKILL.md');
  if (!existsSync(skillMd)) return null;

  const content = readFileSync(skillMd, 'utf-8');
  const { frontmatter, body } = extractFrontmatter(content);

  const dirName = skillDir.split('/').pop() ?? '';
  const name = (frontmatter.name as string) ?? dirName;
  const description = (frontmatter.description as string) ?? '';
  const toolsStr = (frontmatter['allowed-tools'] as string) ?? '';
  const allowedTools = toolsStr.split(',').map((t) => t.trim()).filter(Boolean);

  return {
    name,
    description,
    allowedTools,
    prompt: body.trim(),
    source: skillMd,
    priority,
  };
}

/**
 * Get skill directories in precedence order.
 */
function getSkillDirs(projectRoot: string): string[] {
  const dirs: string[] = [];

  // Workspace skills
  const workspace = join(projectRoot, 'skills');
  if (existsSync(workspace) && statSync(workspace).isDirectory()) {
    dirs.push(workspace);
  }

  // Also check .cadforge/skills in project
  const projCadforgeSkills = join(projectRoot, '.cadforge', 'skills');
  if (existsSync(projCadforgeSkills) && statSync(projCadforgeSkills).isDirectory()) {
    dirs.push(projCadforgeSkills);
  }

  // User skills
  const user = join(homedir(), '.cadforge', 'skills');
  if (existsSync(user) && statSync(user).isDirectory()) {
    dirs.push(user);
  }

  return dirs;
}

/**
 * Discover all available skills, deduplicated by name (highest priority wins).
 */
export function discoverSkills(projectRoot: string): Skill[] {
  const skillDirs = getSkillDirs(projectRoot);
  const seen = new Map<string, Skill>();

  for (let priority = 0; priority < skillDirs.length; priority++) {
    const dir = skillDirs[priority];
    let entries: string[];
    try {
      entries = readdirSync(dir).sort();
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = join(dir, entry);
      try {
        if (!statSync(fullPath).isDirectory()) continue;
      } catch {
        continue;
      }

      const skill = loadSkill(fullPath, priority);
      if (skill && !seen.has(skill.name)) {
        seen.set(skill.name, skill);
      }
    }
  }

  return [...seen.values()].sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name));
}

/**
 * Get a skill by name.
 */
export function getSkillByName(projectRoot: string, name: string): Skill | null {
  return discoverSkills(projectRoot).find((s) => s.name === name) ?? null;
}

/**
 * Get all slash commands as a map.
 */
export function getSlashCommands(projectRoot: string): Map<string, Skill> {
  const map = new Map<string, Skill>();
  for (const skill of discoverSkills(projectRoot)) {
    map.set(`/${skill.name}`, skill);
  }
  return map;
}

// ---------------------------------------------------------------------------
// YAML frontmatter parsing (simple, no yaml dependency)
// ---------------------------------------------------------------------------

interface Frontmatter {
  frontmatter: Record<string, unknown>;
  body: string;
}

function extractFrontmatter(content: string): Frontmatter {
  if (!content.startsWith('---')) {
    return { frontmatter: {}, body: content };
  }

  const parts = content.split('---');
  if (parts.length < 3) {
    return { frontmatter: {}, body: content };
  }

  // Simple YAML key: value parser (no arrays/nested)
  const yamlText = parts[1];
  const fm: Record<string, unknown> = {};
  for (const line of yamlText.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) continue;
    const key = trimmed.slice(0, colonIdx).trim();
    const value = trimmed.slice(colonIdx + 1).trim();
    fm[key] = value;
  }

  const body = parts.slice(2).join('---');
  return { frontmatter: fm, body };
}
