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

export type ProviderType = 'anthropic' | 'openai' | 'ollama' | 'bedrock' | 'litellm';

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

export interface VaultUrlSource {
  name: string;
  urls: string[];
}

export interface ServiceConfig {
  host: string;
  port: number;
  apiKey: string | null;
  corsOrigins: string[];
}

export interface CompetitiveModelRole {
  model: string;
}

export interface CompetitivePipelineConfig {
  enabled: boolean;
  supervisor: CompetitiveModelRole;
  judge: CompetitiveModelRole;
  merger: CompetitiveModelRole;
  sandboxAssistant: CompetitiveModelRole;
  proposalAgents: CompetitiveModelRole[];
  fidelityThreshold: number;
  maxRefinementLoops: number;
  humanApprovalRequired: boolean;
  debateEnabled: boolean;
}

export const DEFAULT_COMPETITIVE_PIPELINE: CompetitivePipelineConfig = {
  enabled: false,
  supervisor: { model: 'minimax/MiniMax-M2.5' },
  judge: { model: 'zai/glm-5' },
  merger: { model: 'minimax/MiniMax-M2.5' },
  sandboxAssistant: { model: 'xai/grok-4-1-fast-reasoning' },
  proposalAgents: [
    { model: 'minimax/MiniMax-M2.5' },
    { model: 'zai/glm-5' },
    { model: 'dashscope/qwen3-coder-next' },
    { model: 'xai/grok-4-1-fast-reasoning' },
  ],
  fidelityThreshold: 95,
  maxRefinementLoops: 3,
  humanApprovalRequired: false,
  debateEnabled: true,
};

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
  vaultUrls: VaultUrlSource[];
  service: ServiceConfig;
  competitivePipeline: CompetitivePipelineConfig;
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
    case 'litellm':   return 'minimax/MiniMax-M2.5';
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
    litellm:   { explore: 'minimax/MiniMax-M2.5', plan: 'zai/glm-5', cad: 'dashscope/qwen3-coder-next' },
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
  vaultUrls: [
    {
      name: 'cadquery',
      urls: [
        'https://cadquery.readthedocs.io/en/latest/primer.html',
        'https://cadquery.readthedocs.io/en/latest/examples.html',
      ],
    },
    {
      name: 'build123d',
      urls: [
        'https://build123d.readthedocs.io/en/latest/introductions.html',
        'https://build123d.readthedocs.io/en/latest/tutorials.html',
      ],
    },
  ],
  service: {
    host: '127.0.0.1',
    port: 8741,
    apiKey: null,
    corsOrigins: ['*'],
  },
  competitivePipeline: { ...DEFAULT_COMPETITIVE_PIPELINE },
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
  if (raw.vault_urls !== undefined) result.vaultUrls = raw.vault_urls as VaultUrlSource[];

  // Nested objects: service → service
  if (raw.service !== undefined) {
    const s = raw.service as Record<string, unknown>;
    result.service = {
      host: (s.host as string) ?? '127.0.0.1',
      port: (s.port as number) ?? 8741,
      apiKey: (s.api_key as string | null) ?? null,
      corsOrigins: (s.cors_origins as string[]) ?? ['*'],
    };
  }

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

  // competitive_pipeline → competitivePipeline
  if (raw.competitive_pipeline !== undefined) {
    const cp = raw.competitive_pipeline as Record<string, unknown>;
    result.competitivePipeline = {
      enabled: (cp.enabled as boolean) ?? false,
      supervisor: (cp.supervisor as CompetitiveModelRole) ?? DEFAULT_COMPETITIVE_PIPELINE.supervisor,
      judge: (cp.judge as CompetitiveModelRole) ?? DEFAULT_COMPETITIVE_PIPELINE.judge,
      merger: (cp.merger as CompetitiveModelRole) ?? DEFAULT_COMPETITIVE_PIPELINE.merger,
      sandboxAssistant: (cp.sandbox_assistant as CompetitiveModelRole) ?? DEFAULT_COMPETITIVE_PIPELINE.sandboxAssistant,
      proposalAgents: (cp.proposal_agents as CompetitiveModelRole[]) ?? DEFAULT_COMPETITIVE_PIPELINE.proposalAgents,
      fidelityThreshold: (cp.fidelity_threshold as number) ?? 95,
      maxRefinementLoops: (cp.max_refinement_loops as number) ?? 3,
      humanApprovalRequired: (cp.human_approval_required as boolean) ?? false,
      debateEnabled: (cp.debate_enabled as boolean) ?? true,
    };
  }

  return result;
}
