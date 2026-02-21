/**
 * Project root discovery and path helpers.
 * Mirrors utils/paths.py from the Python codebase.
 */

import { existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

/**
 * Walk up from startDir to find the project root.
 * Project root is identified by CADFORGE.md or .cadforge/ directory.
 */
export function findProjectRoot(startDir?: string): string | null {
  let current = resolve(startDir ?? process.cwd());

  while (true) {
    if (existsSync(join(current, 'CADFORGE.md'))) return current;
    if (existsSync(join(current, '.cadforge'))) return current;
    const parent = dirname(current);
    if (parent === current) return null; // reached filesystem root
    current = parent;
  }
}

/**
 * Get project root or throw.
 */
export function getProjectRoot(startDir?: string): string {
  const root = findProjectRoot(startDir);
  if (!root) {
    throw new Error("No CadForge project found. Run 'cadforge init' to create one.");
  }
  return root;
}

/**
 * Get the .cadforge/ directory, creating it if needed.
 */
export function getCadforgeDir(projectRoot: string): string {
  const d = join(projectRoot, '.cadforge');
  mkdirSync(d, { recursive: true });
  return d;
}

/**
 * Get user-level settings.json path.
 */
export function getUserSettingsPath(): string {
  return join(homedir(), '.cadforge', 'settings.json');
}

/**
 * Get project-level settings.json path.
 */
export function getProjectSettingsPath(projectRoot: string): string {
  return join(projectRoot, '.cadforge', 'settings.json');
}

/**
 * Get user-level .cadforge directory, creating it if needed.
 */
export function getUserCadforgeDir(): string {
  const d = join(homedir(), '.cadforge');
  mkdirSync(d, { recursive: true });
  return d;
}

/**
 * Get the venv directory path for the Python engine.
 */
export function getVenvDir(): string {
  return join(getUserCadforgeDir(), '.venv');
}

