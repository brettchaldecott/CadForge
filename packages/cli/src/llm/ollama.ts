/**
 * Ollama provider — thin wrapper over OpenAICompatibleProvider.
 *
 * Ollama exposes an OpenAI-compatible API at http://localhost:11434/v1.
 */

import { OpenAICompatibleProvider } from './openai.js';

export function createOllamaProvider(baseUrl?: string | null): OpenAICompatibleProvider {
  return new OpenAICompatibleProvider(
    'ollama',
    'ollama', // api_key ignored by Ollama but required by the provider
    baseUrl ?? 'http://localhost:11434/v1',
  );
}
