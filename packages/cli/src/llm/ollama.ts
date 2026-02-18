/**
 * Ollama provider (OpenAI-compatible) — will be implemented in Phase 4.
 */

import type { CadForgeSettings } from '@cadforge/shared';
import type { ContentBlock, EventCallback, LLMMessage, LLMProvider, LLMResponse } from './provider.js';

export class OllamaProvider implements LLMProvider {
  async stream(
    _messages: LLMMessage[],
    _options: { system: string; tools: Record<string, unknown>[]; settings: CadForgeSettings },
    _onEvent: EventCallback,
  ): Promise<LLMResponse> {
    throw new Error('Ollama provider not yet implemented (Phase 4)');
  }

  formatToolResults(toolResults: ContentBlock[]): ContentBlock[] {
    return toolResults;
  }
}
