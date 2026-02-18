/**
 * Settings loader — reads and merges user/project settings.json files.
 * Uses Zod for validation. JSON files use snake_case; internal model uses camelCase.
 */

import { readFileSync, existsSync } from 'node:fs';
import { z } from 'zod';
import {
  type CadForgeSettings,
  DEFAULT_SETTINGS,
  normalizeSettings,
} from '@cadforge/shared';
import { getUserSettingsPath, getProjectSettingsPath } from './paths.js';

const PermissionsSchema = z.object({
  deny: z.array(z.string()),
  allow: z.array(z.string()),
  ask: z.array(z.string()),
});

const SettingsSchema = z.object({
  provider: z.enum(['anthropic', 'ollama']).optional(),
  model: z.string().optional(),
  max_tokens: z.number().int().positive().optional(),
  temperature: z.number().min(0).max(1).optional(),
  printer: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
  engine_url: z.string().nullable().optional(),
  engine_port: z.number().int().positive().optional(),
  permissions: PermissionsSchema.optional(),
  hooks: z.array(z.record(z.unknown())).optional(),
});

/**
 * Load a JSON file safely, returning empty object if missing or invalid.
 */
function loadJsonFile(path: string): Record<string, unknown> {
  if (!existsSync(path)) return {};
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>;
  } catch {
    return {};
  }
}

/**
 * Deep merge: override values into base.
 * Objects are recursively merged; arrays and scalars are replaced.
 */
function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const result = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (
      key in result &&
      typeof result[key] === 'object' &&
      result[key] !== null &&
      !Array.isArray(result[key]) &&
      typeof value === 'object' &&
      value !== null &&
      !Array.isArray(value)
    ) {
      result[key] = deepMerge(
        result[key] as Record<string, unknown>,
        value as Record<string, unknown>,
      );
    } else {
      result[key] = value;
    }
  }
  return result;
}

/**
 * Load and merge settings from user + project levels.
 * Precedence: project overrides user overrides defaults.
 */
export function loadSettings(projectRoot?: string): CadForgeSettings {
  // Start with defaults (already camelCase)
  let merged: Record<string, unknown> = {
    provider: DEFAULT_SETTINGS.provider,
    model: DEFAULT_SETTINGS.model,
    max_tokens: DEFAULT_SETTINGS.maxTokens,
    temperature: DEFAULT_SETTINGS.temperature,
    printer: DEFAULT_SETTINGS.printer,
    base_url: DEFAULT_SETTINGS.baseUrl,
    engine_url: DEFAULT_SETTINGS.engineUrl,
    engine_port: DEFAULT_SETTINGS.enginePort,
    permissions: DEFAULT_SETTINGS.permissions,
    hooks: DEFAULT_SETTINGS.hooks,
  };

  // User-level settings
  const userRaw = loadJsonFile(getUserSettingsPath());
  if (Object.keys(userRaw).length > 0) {
    merged = deepMerge(merged, userRaw);
  }

  // Project-level settings
  if (projectRoot) {
    const projRaw = loadJsonFile(getProjectSettingsPath(projectRoot));
    if (Object.keys(projRaw).length > 0) {
      merged = deepMerge(merged, projRaw);
    }
  }

  // Validate
  const parsed = SettingsSchema.parse(merged);

  // Normalize snake_case → camelCase
  const normalized = normalizeSettings(parsed as Record<string, unknown>);

  return { ...DEFAULT_SETTINGS, ...normalized };
}
