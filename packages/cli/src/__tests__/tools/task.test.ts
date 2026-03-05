import { jest, describe, it, expect } from '@jest/globals';
import { handleTask } from '../../tools/task.js';
import type { TaskDeps } from '../../tools/task.js';
import type { LLMProvider } from '../../llm/provider.js';
import type { BackendClient } from '../../backend/client.js';
import { DEFAULT_SETTINGS } from '@cadforge/shared';

function makeMockProvider(overrides: Partial<ReturnType<LLMProvider['getCredentialInfo']>> = {}): LLMProvider {
  return {
    stream: jest.fn<LLMProvider['stream']>(),
    formatToolResults: jest.fn<LLMProvider['formatToolResults']>(),
    getCredentialInfo: jest.fn<LLMProvider['getCredentialInfo']>().mockReturnValue({
      provider: 'anthropic',
      apiKey: 'sk-test',
      authToken: null,
      baseUrl: null,
      awsRegion: null,
      awsProfile: null,
      ...overrides,
    }),
  };
}

function makeDeps(overrides: Partial<TaskDeps> = {}): TaskDeps {
  return {
    provider: makeMockProvider(),
    settings: { ...DEFAULT_SETTINGS },
    projectRoot: '/tmp/project',
    ...overrides,
  };
}

describe('handleTask', () => {
  describe('validation', () => {
    it('rejects invalid agent_type', async () => {
      const result = await handleTask({ agent_type: 'invalid', prompt: 'test' }, makeDeps());
      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid agent_type');
    });

    it('rejects empty prompt', async () => {
      const result = await handleTask({ agent_type: 'explore', prompt: '' }, makeDeps());
      expect(result.success).toBe(false);
      expect(result.error).toContain('empty');
    });
  });

  describe('competitive pipeline', () => {
    it('passes design_id through to request', async () => {
      const mockStream = jest.fn<BackendClient['streamCompetitivePipeline']>()
        .mockResolvedValue({ success: true, output: 'done' });
      const backendClient = { streamCompetitivePipeline: mockStream } as unknown as BackendClient;

      await handleTask(
        { agent_type: 'competitive', prompt: 'refine box', design_id: 'design-xyz' },
        makeDeps({ backendClient }),
      );

      expect(mockStream).toHaveBeenCalledWith(
        expect.objectContaining({ design_id: 'design-xyz' }),
        expect.any(Function),
      );
    });

    it('omits design_id when absent', async () => {
      const mockStream = jest.fn<BackendClient['streamCompetitivePipeline']>()
        .mockResolvedValue({ success: true, output: 'done' });
      const backendClient = { streamCompetitivePipeline: mockStream } as unknown as BackendClient;

      await handleTask(
        { agent_type: 'competitive', prompt: 'new design' },
        makeDeps({ backendClient }),
      );

      const req = mockStream.mock.calls[0][0];
      expect(req.design_id).toBeUndefined();
    });

    it('returns error when backend is not available', async () => {
      const result = await handleTask(
        { agent_type: 'competitive', prompt: 'test' },
        makeDeps({ backendClient: undefined }),
      );
      expect(result.success).toBe(false);
      expect(result.error).toContain('backend');
    });
  });

  describe('cad agent', () => {
    it('builds provider_config from credentials', async () => {
      const mockStream = jest.fn<BackendClient['streamCadSubagent']>()
        .mockResolvedValue({ success: true, output: 'cad result' });
      const backendClient = { streamCadSubagent: mockStream } as unknown as BackendClient;
      const provider = makeMockProvider({
        provider: 'openai',
        apiKey: 'sk-openai',
        baseUrl: 'http://custom',
      });

      await handleTask(
        { agent_type: 'cad', prompt: 'make a box' },
        makeDeps({ backendClient, provider }),
      );

      const req = mockStream.mock.calls[0][0];
      expect(req.provider_config!.provider).toBe('openai');
      expect(req.provider_config!.api_key).toBe('sk-openai');
      expect(req.provider_config!.base_url).toBe('http://custom');
    });
  });
});
