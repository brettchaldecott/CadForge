/**
 * Settings loader — reads and merges user/project settings.json files.
 * Uses Zod for validation. JSON files use snake_case; internal model uses camelCase.
 */

import { readFileSync, existsSync } from 'node:fs';
import { z } from 'zod';
import {
  type CadForgeSettings,
  DEFAULT_COMPETITIVE_PIPELINE,
  DEFAULT_SETTINGS,
  normalizeSettings,
} from '@cadforge/shared';
import { getUserSettingsPath, getProjectSettingsPath } from './paths.js';

const PermissionsSchema = z.object({
  deny: z.array(z.string()),
  allow: z.array(z.string()),
  ask: z.array(z.string()),
});

const ProviderConfigSchema = z.object({
  api_key: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
  aws_region: z.string().nullable().optional(),
  aws_profile: z.string().nullable().optional(),
}).optional();

const SubagentModelsSchema = z.object({
  explore: z.string().nullable().optional(),
  plan: z.string().nullable().optional(),
  cad: z.string().nullable().optional(),
}).optional();

const SettingsSchema = z.object({
  provider: z.enum(['anthropic', 'openai', 'ollama', 'bedrock', 'litellm']).optional(),
  model: z.string().optional(),
  max_tokens: z.number().int().positive().optional(),
  temperature: z.number().min(0).max(1).optional(),
  printer: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
  engine_url: z.string().nullable().optional(),
  engine_port: z.number().int().positive().optional(),
  provider_config: ProviderConfigSchema,
  subagent_models: SubagentModelsSchema,
  competitive_pipeline: z.object({
    enabled: z.boolean().optional(),
    supervisor: z.object({ model: z.string() }).optional(),
    judge: z.object({ model: z.string() }).optional(),
    merger: z.object({ model: z.string() }).optional(),
    sandbox_assistant: z.object({ model: z.string() }).optional(),
    proposal_agents: z.array(z.object({ model: z.string() })).optional(),
    fidelity_threshold: z.number().optional(),
    max_refinement_loops: z.number().optional(),
    human_approval_required: z.boolean().optional(),
    debate_enabled: z.boolean().optional(),
  }).optional(),
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
    provider_config: {
      api_key: DEFAULT_SETTINGS.providerConfig.apiKey,
      base_url: DEFAULT_SETTINGS.providerConfig.baseUrl,
      aws_region: DEFAULT_SETTINGS.providerConfig.awsRegion,
      aws_profile: DEFAULT_SETTINGS.providerConfig.awsProfile,
    },
    subagent_models: {
      explore: DEFAULT_SETTINGS.subagentModels.explore,
      plan: DEFAULT_SETTINGS.subagentModels.plan,
      cad: DEFAULT_SETTINGS.subagentModels.cad,
    },
    competitive_pipeline: {
      enabled: DEFAULT_COMPETITIVE_PIPELINE.enabled,
      supervisor: DEFAULT_COMPETITIVE_PIPELINE.supervisor,
      judge: DEFAULT_COMPETITIVE_PIPELINE.judge,
      merger: DEFAULT_COMPETITIVE_PIPELINE.merger,
      sandbox_assistant: DEFAULT_COMPETITIVE_PIPELINE.sandboxAssistant,
      proposal_agents: DEFAULT_COMPETITIVE_PIPELINE.proposalAgents,
      fidelity_threshold: DEFAULT_COMPETITIVE_PIPELINE.fidelityThreshold,
      max_refinement_loops: DEFAULT_COMPETITIVE_PIPELINE.maxRefinementLoops,
      human_approval_required: DEFAULT_COMPETITIVE_PIPELINE.humanApprovalRequired,
      debate_enabled: DEFAULT_COMPETITIVE_PIPELINE.debateEnabled,
    },
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
