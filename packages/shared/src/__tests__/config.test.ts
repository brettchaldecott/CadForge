import {
  getDefaultModel,
  getDefaultSubagentModel,
  normalizeSettings,
  DEFAULT_SETTINGS,
} from '../config.js';
import type { ProviderType } from '../config.js';

describe('getDefaultModel', () => {
  const cases: [ProviderType, string][] = [
    ['anthropic', 'claude-sonnet-4-5-20250929'],
    ['openai', 'gpt-4o'],
    ['ollama', 'qwen2.5-coder:14b'],
    ['bedrock', 'anthropic.claude-sonnet-4-5-20250929-v1:0'],
    ['litellm', 'minimax/MiniMax-M2.5'],
  ];

  it.each(cases)('returns correct model for %s', (provider, expected) => {
    expect(getDefaultModel(provider)).toBe(expected);
  });
});

describe('getDefaultSubagentModel', () => {
  const providers: ProviderType[] = ['anthropic', 'openai', 'ollama', 'bedrock', 'litellm'];
  const roles = ['explore', 'plan', 'cad'] as const;

  it.each(providers)('returns strings for all roles on %s', (provider) => {
    for (const role of roles) {
      const result = getDefaultSubagentModel(provider, role);
      expect(typeof result).toBe('string');
      expect(result.length).toBeGreaterThan(0);
    }
  });

  it('returns expected anthropic subagent models', () => {
    expect(getDefaultSubagentModel('anthropic', 'explore')).toBe('claude-haiku-4-5-20251001');
    expect(getDefaultSubagentModel('anthropic', 'plan')).toBe('claude-sonnet-4-5-20250929');
    expect(getDefaultSubagentModel('anthropic', 'cad')).toBe('claude-sonnet-4-5-20250929');
  });
});

describe('normalizeSettings', () => {
  it('returns empty partial on empty input', () => {
    const result = normalizeSettings({});
    expect(result).toEqual({});
  });

  it('converts top-level snake_case keys', () => {
    const result = normalizeSettings({
      max_tokens: 4096,
      base_url: 'http://localhost:1234',
      engine_port: 9000,
    });
    expect(result.maxTokens).toBe(4096);
    expect(result.baseUrl).toBe('http://localhost:1234');
    expect(result.enginePort).toBe(9000);
  });

  it('converts provider_config nested keys', () => {
    const result = normalizeSettings({
      provider_config: {
        api_key: 'sk-test',
        base_url: 'http://custom',
        aws_region: 'us-west-2',
        aws_profile: 'dev',
      },
    });
    expect(result.providerConfig).toEqual({
      apiKey: 'sk-test',
      baseUrl: 'http://custom',
      awsRegion: 'us-west-2',
      awsProfile: 'dev',
    });
  });

  it('converts subagent_models', () => {
    const result = normalizeSettings({
      subagent_models: {
        explore: 'model-a',
        plan: 'model-b',
        cad: 'model-c',
      },
    });
    expect(result.subagentModels).toEqual({
      explore: 'model-a',
      plan: 'model-b',
      cad: 'model-c',
    });
  });

  it('converts competitive_pipeline', () => {
    const result = normalizeSettings({
      competitive_pipeline: {
        enabled: true,
        fidelity_threshold: 90,
        human_approval_required: true,
        max_refinement_loops: 5,
        debate_enabled: false,
      },
    });
    expect(result.competitivePipeline!.fidelityThreshold).toBe(90);
    expect(result.competitivePipeline!.humanApprovalRequired).toBe(true);
    expect(result.competitivePipeline!.maxRefinementLoops).toBe(5);
    expect(result.competitivePipeline!.debateEnabled).toBe(false);
  });

  it('converts service nested keys', () => {
    const result = normalizeSettings({
      service: {
        host: '0.0.0.0',
        port: 9999,
        api_key: 'svc-key',
        cors_origins: ['http://localhost:3000'],
      },
    });
    expect(result.service).toEqual({
      host: '0.0.0.0',
      port: 9999,
      apiKey: 'svc-key',
      corsOrigins: ['http://localhost:3000'],
    });
  });
});

describe('DEFAULT_SETTINGS', () => {
  it('has expected provider', () => {
    expect(DEFAULT_SETTINGS.provider).toBe('anthropic');
  });

  it('has expected model', () => {
    expect(DEFAULT_SETTINGS.model).toBe('claude-sonnet-4-5-20250929');
  });

  it('has expected enginePort', () => {
    expect(DEFAULT_SETTINGS.enginePort).toBe(8741);
  });

  it('has competitivePipeline defaults', () => {
    expect(DEFAULT_SETTINGS.competitivePipeline.enabled).toBe(false);
    expect(DEFAULT_SETTINGS.competitivePipeline.fidelityThreshold).toBe(95);
    expect(DEFAULT_SETTINGS.competitivePipeline.maxRefinementLoops).toBe(3);
  });
});
