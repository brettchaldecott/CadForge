/**
 * Provider factory — creates the appropriate LLMProvider for a given ProviderType.
 */

import type { ProviderType, ProviderConfig } from '@cadforge/shared';
import type { AuthCredentials } from './auth.js';
import type { LLMProvider } from './provider.js';
import { AnthropicProvider } from './anthropic.js';
import { OpenAICompatibleProvider } from './openai.js';
import { createOllamaProvider } from './ollama.js';
import { BedrockProvider } from './bedrock.js';

export interface ProviderContext {
  credentials: AuthCredentials;
  providerConfig: ProviderConfig;
}

export function createProvider(
  providerType: ProviderType,
  ctx: ProviderContext,
): LLMProvider {
  switch (providerType) {
    case 'anthropic':
      return new AnthropicProvider(ctx.credentials);
    case 'openai':
      return new OpenAICompatibleProvider(
        'openai',
        ctx.credentials.apiKey ?? '',
        ctx.providerConfig.baseUrl ?? 'https://api.openai.com/v1',
      );
    case 'ollama':
      return createOllamaProvider(ctx.providerConfig.baseUrl);
    case 'bedrock':
      return new BedrockProvider(
        ctx.providerConfig.awsRegion ?? 'us-east-1',
        ctx.providerConfig.awsProfile,
      );
    case 'litellm':
      // LiteLLM is used server-side only (Python engine). For CLI provider,
      // fall back to OpenAI-compatible since LiteLLM uses OpenAI format.
      return new OpenAICompatibleProvider(
        'litellm',
        ctx.credentials.apiKey ?? '',
        ctx.providerConfig.baseUrl ?? 'https://api.openai.com/v1',
      );
  }
}
