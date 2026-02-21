/**
 * OpenAI-compatible streaming provider.
 *
 * Uses raw fetch() for streaming to avoid an openai npm dependency.
 * Translates between Anthropic-style content blocks and OpenAI chat format.
 * Works with OpenAI, Ollama, and any OpenAI-compatible endpoint.
 */

import { randomUUID } from 'node:crypto';
import { EventType, type AgentEvent, type CadForgeSettings, type ProviderType } from '@cadforge/shared';
import type {
  ContentBlock,
  CredentialInfo,
  EventCallback,
  LLMMessage,
  LLMProvider,
  LLMResponse,
} from './provider.js';

const RETRY_DELAYS = [1000, 2000, 4000]; // ms

function makeEvent(type: EventType, data: Record<string, unknown>): AgentEvent {
  return { type, data, timestamp: new Date().toISOString() };
}

export class OpenAICompatibleProvider implements LLMProvider {
  private _providerName: ProviderType;
  private _apiKey: string;
  private _baseUrl: string;

  constructor(providerName: ProviderType, apiKey: string, baseUrl: string) {
    this._providerName = providerName;
    this._apiKey = apiKey;
    this._baseUrl = baseUrl.replace(/\/+$/, ''); // strip trailing slash
  }

  async stream(
    messages: LLMMessage[],
    options: {
      system: string;
      tools: Record<string, unknown>[];
      settings: CadForgeSettings;
    },
    onEvent: EventCallback,
  ): Promise<LLMResponse> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= RETRY_DELAYS.length; attempt++) {
      try {
        return await this._doStream(messages, options, onEvent);
      } catch (e) {
        lastError = e as Error;

        const status = (e as { status?: number }).status;
        const isRetryable = status === 429 || status === 500 || status === 502 ||
                            status === 503 || status === 529;

        if (!isRetryable) break;

        if (attempt < RETRY_DELAYS.length) {
          onEvent(makeEvent(EventType.STATUS, {
            message: `API error, retrying (${attempt + 1}/${RETRY_DELAYS.length})...`,
          }));
          await new Promise((r) => setTimeout(r, RETRY_DELAYS[attempt]));
        }
      }
    }

    const errorMsg = String(lastError);
    onEvent(makeEvent(EventType.ERROR, { message: `API error: ${errorMsg}` }));
    return {
      content: [{ type: 'text', text: `API error: ${errorMsg}` }],
      usage: { input_tokens: 0, output_tokens: 0 },
    };
  }

  private async _doStream(
    messages: LLMMessage[],
    options: {
      system: string;
      tools: Record<string, unknown>[];
      settings: CadForgeSettings;
    },
    onEvent: EventCallback,
  ): Promise<LLMResponse> {
    // Build request body
    const oaiMessages: Record<string, unknown>[] = [
      { role: 'system', content: options.system },
      ...translateMessages(messages),
    ];

    const body: Record<string, unknown> = {
      model: options.settings.model,
      max_tokens: options.settings.maxTokens,
      messages: oaiMessages,
      stream: true,
      stream_options: { include_usage: true },
    };

    if (options.tools.length > 0) {
      body.tools = translateTools(options.tools);
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this._apiKey && this._apiKey !== 'ollama') {
      headers['Authorization'] = `Bearer ${this._apiKey}`;
    }

    const url = `${this._baseUrl}/chat/completions`;
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(300_000), // 5 min timeout
    });

    if (!response.ok) {
      const errBody = await response.text().catch(() => '');
      const err = new Error(`${this._providerName} API error ${response.status}: ${errBody}`);
      (err as unknown as Record<string, unknown>).status = response.status;
      throw err;
    }

    if (!response.body) {
      throw new Error('No response body');
    }

    // Parse SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let textAccum = '';
    const toolCallsAccum: Map<number, { id: string; name: string; arguments: string }> = new Map();
    const usageInfo = { input_tokens: 0, output_tokens: 0 };
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? ''; // keep incomplete line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed === 'data: [DONE]') continue;
          if (!trimmed.startsWith('data: ')) continue;

          const jsonStr = trimmed.slice(6);
          let chunk: Record<string, unknown>;
          try {
            chunk = JSON.parse(jsonStr);
          } catch {
            continue;
          }

          // Extract usage from top-level (some providers put it here)
          const chunkUsage = chunk.usage as Record<string, number> | undefined;
          if (chunkUsage) {
            usageInfo.input_tokens = chunkUsage.prompt_tokens ?? usageInfo.input_tokens;
            usageInfo.output_tokens = chunkUsage.completion_tokens ?? usageInfo.output_tokens;
          }

          const choices = chunk.choices as Array<Record<string, unknown>> | undefined;
          if (!choices || choices.length === 0) continue;

          const choice = choices[0];
          const delta = choice.delta as Record<string, unknown> | undefined;
          if (!delta) continue;

          // Text content
          if (delta.content) {
            const text = delta.content as string;
            textAccum += text;
            onEvent(makeEvent(EventType.TEXT_DELTA, { text }));
          }

          // Tool calls
          const toolCalls = delta.tool_calls as Array<Record<string, unknown>> | undefined;
          if (toolCalls) {
            for (const tcDelta of toolCalls) {
              const idx = tcDelta.index as number;
              if (!toolCallsAccum.has(idx)) {
                toolCallsAccum.set(idx, { id: '', name: '', arguments: '' });
              }
              const accum = toolCallsAccum.get(idx)!;
              if (tcDelta.id) accum.id = tcDelta.id as string;
              const fn = tcDelta.function as Record<string, unknown> | undefined;
              if (fn) {
                if (fn.name) {
                  accum.name = fn.name as string;
                  onEvent(makeEvent(EventType.TOOL_USE_START, {
                    name: accum.name,
                    id: accum.id,
                    input: {},
                  }));
                }
                if (fn.arguments) {
                  accum.arguments += fn.arguments as string;
                }
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Build normalized response (Anthropic format)
    const contentBlocks: ContentBlock[] = [];

    if (textAccum) {
      contentBlocks.push({ type: 'text', text: textAccum });
    }

    for (const [, tc] of [...toolCallsAccum.entries()].sort((a, b) => a[0] - b[0])) {
      let args: Record<string, unknown> = {};
      try {
        args = tc.arguments ? JSON.parse(tc.arguments) : {};
      } catch {
        args = {};
      }
      contentBlocks.push({
        type: 'tool_use',
        id: tc.id || `call_${randomUUID().replace(/-/g, '').slice(0, 24)}`,
        name: tc.name,
        input: args,
      });
    }

    if (contentBlocks.length === 0) {
      contentBlocks.push({ type: 'text', text: '' });
    }

    return { content: contentBlocks, usage: usageInfo };
  }

  formatToolResults(toolResults: ContentBlock[]): LLMMessage {
    // Convert Anthropic-style tool_result blocks to OpenAI tool messages
    // We return a single user-role message with the tool role messages
    // but since our provider.ts interface allows LLMMessage return,
    // we pack them as a special format the stream method can unpack.
    const oaiMessages: Record<string, unknown>[] = [];
    for (const result of toolResults) {
      oaiMessages.push({
        role: 'tool',
        tool_call_id: result.tool_use_id,
        content: result.content ?? '',
      });
    }
    // Return as a user message with the tool messages embedded
    return {
      role: 'user',
      content: oaiMessages as unknown as ContentBlock[],
    };
  }

  getCredentialInfo(): CredentialInfo {
    return {
      provider: this._providerName,
      apiKey: this._apiKey === 'ollama' ? null : this._apiKey,
      baseUrl: this._baseUrl,
    };
  }
}

// ---------------------------------------------------------------------------
// Translation helpers (ported from Python src/cadforge/core/llm.py)
// ---------------------------------------------------------------------------

/**
 * Translate Anthropic tool definitions to OpenAI function format.
 */
function translateTools(tools: Record<string, unknown>[]): Record<string, unknown>[] {
  return tools.map((tool) => ({
    type: 'function',
    function: {
      name: tool.name,
      description: tool.description ?? '',
      parameters: tool.input_schema ?? {},
    },
  }));
}

/**
 * Translate Anthropic-style messages to OpenAI format.
 */
function translateMessages(messages: LLMMessage[]): Record<string, unknown>[] {
  const oaiMessages: Record<string, unknown>[] = [];

  for (const msg of messages) {
    const role = msg.role;
    const content = msg.content;

    if (typeof content === 'string') {
      oaiMessages.push({ role, content });
      continue;
    }

    if (!Array.isArray(content)) {
      oaiMessages.push({ role, content: String(content) });
      continue;
    }

    // Content is an array of blocks
    if (role === 'assistant') {
      const textParts: string[] = [];
      const toolCalls: Record<string, unknown>[] = [];

      for (const block of content) {
        if (block.type === 'text') {
          textParts.push(block.text as string);
        } else if (block.type === 'tool_use') {
          toolCalls.push({
            id: block.id,
            type: 'function',
            function: {
              name: block.name,
              arguments: JSON.stringify(block.input ?? {}),
            },
          });
        }
      }

      const assistantMsg: Record<string, unknown> = {
        role: 'assistant',
        content: textParts.length > 0 ? textParts.join('\n') : null,
      };
      if (toolCalls.length > 0) {
        assistantMsg.tool_calls = toolCalls;
      }
      oaiMessages.push(assistantMsg);
    } else if (role === 'user') {
      // Check for tool_result blocks
      const toolResults = content.filter((b) => b.type === 'tool_result');
      if (toolResults.length > 0) {
        for (const result of toolResults) {
          oaiMessages.push({
            role: 'tool',
            tool_call_id: result.tool_use_id,
            content: (result.content as string) ?? '',
          });
        }
      } else {
        // Regular user content blocks
        const text = content
          .filter((b) => b.type === 'text')
          .map((b) => b.text as string)
          .join('\n');
        oaiMessages.push({ role: 'user', content: text });
      }
    } else {
      oaiMessages.push({ role, content: String(content) });
    }
  }

  return oaiMessages;
}
