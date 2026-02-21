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

export type ProviderType = 'anthropic' | 'openai' | 'ollama' | 'bedrock';

export interface ProviderConfig {
  apiKey: string | null;
  baseUrl: string | null;
  awsRegion: string | null;
  awsProfile: string | null;
}

export interface SubagentModelOverrides {
  explore: string | null;
  plan: string | null;
  cad: string | null;
}

export interface CadForgeSettings {
  provider: ProviderType;
  model: string;
  maxTokens: number;
  temperature: number;
  printer: string | null;
  baseUrl: string | null;
  engineUrl: string | null;
  enginePort: number;
  providerConfig: ProviderConfig;
  subagentModels: SubagentModelOverrides;
  permissions: PermissionsConfig;
  hooks: HookConfig[];
}

export const DEFAULT_PROVIDER_CONFIG: ProviderConfig = {
  apiKey: null,
  baseUrl: null,
  awsRegion: null,
  awsProfile: null,
};

export const DEFAULT_SUBAGENT_MODELS: SubagentModelOverrides = {
  explore: null,
  plan: null,
  cad: null,
};

/** Default model per provider. */
export function getDefaultModel(provider: ProviderType): string {
  switch (provider) {
    case 'anthropic': return 'claude-sonnet-4-5-20250929';
    case 'openai':    return 'gpt-4o';
    case 'ollama':    return 'qwen2.5-coder:14b';
    case 'bedrock':   return 'anthropic.claude-sonnet-4-5-20250929-v1:0';
  }
}

/** Default subagent model per provider and role. */
export function getDefaultSubagentModel(
  provider: ProviderType,
  role: 'explore' | 'plan' | 'cad',
): string {
  const defaults: Record<ProviderType, Record<string, string>> = {
    anthropic: { explore: 'claude-haiku-4-5-20251001', plan: 'claude-sonnet-4-5-20250929', cad: 'claude-sonnet-4-5-20250929' },
    openai:    { explore: 'gpt-4o-mini', plan: 'gpt-4o', cad: 'gpt-4o' },
    ollama:    { explore: 'qwen2.5-coder:7b', plan: 'qwen2.5-coder:14b', cad: 'qwen2.5-coder:14b' },
    bedrock:   { explore: 'anthropic.claude-haiku-4-5-20251001-v1:0', plan: 'anthropic.claude-sonnet-4-5-20250929-v1:0', cad: 'anthropic.claude-sonnet-4-5-20250929-v1:0' },
  };
  return defaults[provider][role];
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
  providerConfig: { ...DEFAULT_PROVIDER_CONFIG },
  subagentModels: { ...DEFAULT_SUBAGENT_MODELS },
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

  // Nested objects: provider_config → providerConfig
  if (raw.provider_config !== undefined) {
    const pc = raw.provider_config as Record<string, unknown>;
    result.providerConfig = {
      apiKey: (pc.api_key as string | null) ?? null,
      baseUrl: (pc.base_url as string | null) ?? null,
      awsRegion: (pc.aws_region as string | null) ?? null,
      awsProfile: (pc.aws_profile as string | null) ?? null,
    };
  }

  // subagent_models → subagentModels
  if (raw.subagent_models !== undefined) {
    const sm = raw.subagent_models as Record<string, unknown>;
    result.subagentModels = {
      explore: (sm.explore as string | null) ?? null,
      plan: (sm.plan as string | null) ?? null,
      cad: (sm.cad as string | null) ?? null,
    };
  }

  return result;
}
