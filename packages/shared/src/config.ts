/**
 * Configuration types — shared schema for settings.json files.
 * Both Node CLI and Python engine read the same JSON files.
 */

export interface PermissionsConfig {
  deny: string[];
  allow: string[];
  ask: string[];
}

export interface HookDefinition {
  type: string;
  command: string;
  timeout?: number;
}

export interface HookConfig {
  event: string;
  matcher?: string;
  hooks: HookDefinition[];
}

export interface CadForgeSettings {
  provider: 'anthropic' | 'ollama';
  model: string;
  maxTokens: number;
  temperature: number;
  printer: string | null;
  baseUrl: string | null;
  engineUrl: string | null;
  enginePort: number;
  permissions: PermissionsConfig;
  hooks: HookConfig[];
}

/** Default settings matching Python defaults */
export const DEFAULT_SETTINGS: CadForgeSettings = {
  provider: 'anthropic',
  model: 'claude-sonnet-4-5-20250929',
  maxTokens: 8192,
  temperature: 0,
  printer: null,
  baseUrl: null,
  engineUrl: null,
  enginePort: 8741,
  permissions: {
    deny: ['Bash(rm:*)', 'Bash(sudo:*)', 'WriteFile(**/.env)'],
    allow: [
      'ReadFile(*)',
      'SearchVault(*)',
      'AnalyzeMesh(*)',
      'GetPrinter(*)',
      'Task(explore)',
      'Task(plan)',
    ],
    ask: [
      'ExecuteCadQuery(*)',
      'WriteFile(*)',
      'Bash(*)',
      'ExportModel(*)',
      'Task(cad)',
    ],
  },
  hooks: [],
};

/**
 * Convert snake_case JSON (as stored on disk) to camelCase config.
 */
export function normalizeSettings(
  raw: Record<string, unknown>,
): Partial<CadForgeSettings> {
  const result: Partial<CadForgeSettings> = {};

  if (raw.provider !== undefined) result.provider = raw.provider as CadForgeSettings['provider'];
  if (raw.model !== undefined) result.model = raw.model as string;
  if (raw.max_tokens !== undefined) result.maxTokens = raw.max_tokens as number;
  if (raw.temperature !== undefined) result.temperature = raw.temperature as number;
  if (raw.printer !== undefined) result.printer = raw.printer as string | null;
  if (raw.base_url !== undefined) result.baseUrl = raw.base_url as string | null;
  if (raw.engine_url !== undefined) result.engineUrl = raw.engine_url as string | null;
  if (raw.engine_port !== undefined) result.enginePort = raw.engine_port as number;
  if (raw.permissions !== undefined) result.permissions = raw.permissions as PermissionsConfig;
  if (raw.hooks !== undefined) result.hooks = raw.hooks as HookConfig[];

  return result;
}
