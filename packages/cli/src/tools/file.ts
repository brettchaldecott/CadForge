/**
 * Local file tool handlers — ReadFile, WriteFile, ListFiles.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { readdir } from 'node:fs/promises';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { minimatch } from 'minimatch';

export function readFile(path: string): { success: boolean; content?: string; error?: string } {
  try {
    const content = readFileSync(path, 'utf-8');
    return { success: true, content };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

export function writeFile(
  path: string,
  content: string,
): { success: boolean; error?: string } {
  try {
    const dir = dirname(path);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    writeFileSync(path, content, 'utf-8');
    return { success: true };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * List files matching a glob pattern.
 */
export async function listFiles(
  pattern: string,
  basePath: string,
): Promise<{ success: boolean; files?: string[]; error?: string }> {
  try {
    const files = await walkDir(basePath, pattern);
    return { success: true, files };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

async function walkDir(dir: string, pattern: string): Promise<string[]> {
  const results: string[] = [];
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      const sub = await walkDir(fullPath, pattern);
      results.push(...sub);
    } else {
      if (minimatch(entry.name, pattern) || minimatch(fullPath, pattern)) {
        results.push(fullPath);
      }
    }
  }
  return results;
}

/**
 * Tool handler for ReadFile.
 */
export function handleReadFile(
  input: Record<string, unknown>,
  projectRoot: string,
): Record<string, unknown> {
  const path = resolvePath(input.path as string, projectRoot);
  return readFile(path);
}

/**
 * Tool handler for WriteFile.
 */
export function handleWriteFile(
  input: Record<string, unknown>,
  projectRoot: string,
): Record<string, unknown> {
  const path = resolvePath(input.path as string, projectRoot);
  const content = input.content as string;
  return writeFile(path, content);
}

/**
 * Tool handler for ListFiles.
 */
export async function handleListFiles(
  input: Record<string, unknown>,
  projectRoot: string,
): Promise<Record<string, unknown>> {
  const pattern = input.pattern as string;
  const basePath = input.path ? resolvePath(input.path as string, projectRoot) : projectRoot;
  return listFiles(pattern, basePath);
}

function resolvePath(path: string, projectRoot: string): string {
  if (isAbsolute(path)) return path;
  return resolve(projectRoot, path);
}
