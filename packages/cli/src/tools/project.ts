/**
 * GetPrinter tool — reads printer profile from YAML frontmatter.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface PrinterProfile {
  name: string;
  build_volume?: { x: number; y: number; z: number };
  nozzle_diameter?: number;
  constraints?: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Extract YAML frontmatter from a markdown file.
 */
function extractFrontmatter(content: string): Record<string, unknown> | null {
  if (!content.startsWith('---')) return null;
  const parts = content.split('---', 3);
  if (parts.length < 3) return null;

  const fm: Record<string, unknown> = {};
  const lines = parts[1].trim().split('\n');

  // Simple YAML parser for flat + one-level nested objects
  let currentKey: string | null = null;
  let currentObj: Record<string, unknown> | null = null;

  for (const line of lines) {
    // Check for nested key (indented)
    const nestedMatch = line.match(/^\s{2,}(\w+):\s*(.+)$/);
    if (nestedMatch && currentKey && currentObj) {
      const value = parseYamlValue(nestedMatch[2]);
      currentObj[nestedMatch[1]] = value;
      continue;
    }

    // Top-level key
    const topMatch = line.match(/^(\w[\w_]*):\s*(.*)$/);
    if (topMatch) {
      // Save previous nested object
      if (currentKey && currentObj) {
        fm[currentKey] = currentObj;
        currentObj = null;
        currentKey = null;
      }

      const [, key, value] = topMatch;
      if (value.trim() === '') {
        // Start of a nested object
        currentKey = key;
        currentObj = {};
      } else {
        fm[key] = parseYamlValue(value);
      }
    }
  }

  // Save last nested object
  if (currentKey && currentObj) {
    fm[currentKey] = currentObj;
  }

  return fm;
}

function parseYamlValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (trimmed === 'null' || trimmed === '~') return null;
  const num = Number(trimmed);
  if (!isNaN(num) && trimmed !== '') return num;
  // Strip quotes
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

/**
 * Get the active printer profile from the printers directory.
 */
export function getPrinter(
  projectRoot: string,
  printerName: string | null,
): { success: boolean; printer?: PrinterProfile; error?: string } {
  if (!printerName) {
    return { success: false, error: 'No printer configured. Set printer in settings.' };
  }

  const printerPath = join(projectRoot, 'vault', 'printers', `${printerName}.md`);
  if (!existsSync(printerPath)) {
    return { success: false, error: `Printer profile not found: ${printerPath}` };
  }

  try {
    const content = readFileSync(printerPath, 'utf-8');
    const fm = extractFrontmatter(content);
    if (!fm) {
      return { success: false, error: 'Printer file missing YAML frontmatter' };
    }

    const profile: PrinterProfile = { name: printerName, ...fm };
    return { success: true, printer: profile };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * Tool handler for GetPrinter.
 */
export function handleGetPrinter(
  _input: Record<string, unknown>,
  projectRoot: string,
  printerName: string | null,
): Record<string, unknown> {
  return getPrinter(projectRoot, printerName);
}
