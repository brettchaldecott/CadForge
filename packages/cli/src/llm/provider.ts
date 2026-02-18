/**
 * LLM provider interface.
 *
 * Defines the streaming provider interface that Anthropic and Ollama
 * providers implement. All providers emit AgentEvents to a callback
 * as tokens arrive.
 */

import type { AgentEvent } from '@cadforge/shared';
import type { CadForgeSettings } from '@cadforge/shared';

export interface LLMMessage {
  role: 'user' | 'assistant';
  content: string | ContentBlock[];
}

export interface ContentBlock {
  type: string;
  [key: string]: unknown;
}

export interface LLMResponse {
  content: ContentBlock[];
  usage: { input_tokens: number; output_tokens: number };
}

export type EventCallback = (event: AgentEvent) => void;

export interface LLMProvider {
  /**
   * Stream an LLM response, calling the event callback as tokens arrive.
   * Returns the normalized response when complete.
   */
  stream(
    messages: LLMMessage[],
    options: {
      system: string;
      tools: Record<string, unknown>[];
      settings: CadForgeSettings;
    },
    onEvent: EventCallback,
  ): Promise<LLMResponse>;

  /**
   * Format tool results for the next API message.
   * Takes Anthropic-style tool_result blocks and returns provider-specific format.
   */
  formatToolResults(toolResults: ContentBlock[]): ContentBlock[] | LLMMessage;
}
