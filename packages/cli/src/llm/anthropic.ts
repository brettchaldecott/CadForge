/**
 * Anthropic streaming provider using @anthropic-ai/sdk.
 *
 * Handles streaming responses, tool use accumulation, and automatic
 * retry on transient API errors (500, 429, 529).
 */

import Anthropic from '@anthropic-ai/sdk';
import { EventType, makeEvent, type CadForgeSettings } from '@cadforge/shared';
import type { AuthCredentials } from './auth.js';
import { buildClientOptions, needsRefresh, refreshOAuthToken } from './auth.js';
import type { ContentBlock, CredentialInfo, EventCallback, LLMMessage, LLMProvider, LLMResponse } from './provider.js';

const RETRY_DELAYS = [1000, 2000, 4000]; // ms

export class AnthropicProvider implements LLMProvider {
  private _creds: AuthCredentials;

  constructor(creds: AuthCredentials) {
    this._creds = creds;
  }

  get credentials(): AuthCredentials {
    return this._creds;
  }

  private async getClient(): Promise<Anthropic> {
    if (needsRefresh(this._creds)) {
      this._creds = await refreshOAuthToken(this._creds);
    }
    const opts = buildClientOptions(this._creds);
    return new Anthropic(opts as ConstructorParameters<typeof Anthropic>[0]);
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
    let client: Anthropic;
    try {
      client = await this.getClient();
    } catch (e) {
      const errorText = `Authentication error: ${e}`;
      onEvent(makeEvent(EventType.ERROR, { message: errorText }));
      return {
        content: [{ type: 'text', text: errorText }],
        usage: { input_tokens: 0, output_tokens: 0 },
      };
    }

    let lastError: Error | null = null;
    let wasStreamingText = false;

    for (let attempt = 0; attempt <= RETRY_DELAYS.length; attempt++) {
      try {
        const contentBlocks: ContentBlock[] = [];
        const usageInfo = { input_tokens: 0, output_tokens: 0 };

        let currentText = '';
        let currentTool: ContentBlock | null = null;
        let currentToolJson = '';
        wasStreamingText = false;

        const stream = client.messages.stream({
          model: options.settings.model,
          max_tokens: options.settings.maxTokens,
          system: options.system,
          tools: options.tools as unknown as Anthropic.Messages.Tool[],
          messages: messages as unknown as Anthropic.Messages.MessageParam[],
        });

        for await (const event of stream) {
          const etype = event.type;

          if (etype === 'message_start') {
            const evt = event as unknown as { message?: { usage?: { input_tokens?: number } } };
            if (evt.message?.usage) {
              usageInfo.input_tokens = evt.message.usage.input_tokens ?? 0;
            }
          } else if (etype === 'message_delta') {
            const evt = event as unknown as { usage?: { output_tokens?: number } };
            if (evt.usage) {
              usageInfo.output_tokens = evt.usage.output_tokens ?? 0;
            }
          } else if (etype === 'content_block_start') {
            const evt = event as unknown as { content_block?: { type: string; id?: string; name?: string } };
            const cb = evt.content_block;
            if (cb) {
              if (cb.type === 'text') {
                currentText = '';
              } else if (cb.type === 'tool_use') {
                currentTool = {
                  type: 'tool_use',
                  id: cb.id ?? '',
                  name: cb.name ?? '',
                  input: {},
                };
                currentToolJson = '';
                onEvent(makeEvent(EventType.TOOL_USE_START, {
                  name: cb.name ?? '',
                  id: cb.id ?? '',
                  input: {},
                }));
              }
            }
          } else if (etype === 'content_block_delta') {
            const evt = event as unknown as { delta?: { type: string; text?: string; partial_json?: string } };
            const delta = evt.delta;
            if (delta) {
              if (delta.type === 'text_delta') {
                const text = delta.text ?? '';
                currentText += text;
                wasStreamingText = true;
                onEvent(makeEvent(EventType.TEXT_DELTA, { text }));
              } else if (delta.type === 'input_json_delta') {
                currentToolJson += delta.partial_json ?? '';
              }
            }
          } else if (etype === 'content_block_stop') {
            if (currentTool !== null) {
              try {
                currentTool.input = currentToolJson ? JSON.parse(currentToolJson) : {};
              } catch {
                currentTool.input = {};
              }
              contentBlocks.push(currentTool);
              currentTool = null;
              currentToolJson = '';
            } else {
              if (currentText) {
                contentBlocks.push({ type: 'text', text: currentText });
                wasStreamingText = false;
              }
              currentText = '';
            }
          }
        }

        if (contentBlocks.length === 0) {
          contentBlocks.push({ type: 'text', text: '' });
        }

        return { content: contentBlocks, usage: usageInfo };
      } catch (e) {
        lastError = e as Error;

        // Check if retryable
        let isRetryable = false;
        if (e instanceof Anthropic.InternalServerError ||
            e instanceof Anthropic.RateLimitError ||
            e instanceof Anthropic.APIConnectionError) {
          isRetryable = true;
        } else if (e instanceof Anthropic.APIError) {
          isRetryable = (e as { status?: number }).status === 529;
        }

        if (!isRetryable) break;

        if (attempt < RETRY_DELAYS.length) {
          if (wasStreamingText) {
            onEvent(makeEvent(EventType.TEXT, { text: '' }));
            wasStreamingText = false;
          }
          onEvent(makeEvent(EventType.STATUS, {
            message: `API error, retrying (${attempt + 1}/${RETRY_DELAYS.length})...`,
          }));
          await new Promise((r) => setTimeout(r, RETRY_DELAYS[attempt]));
        }
      }
    }

    // All retries exhausted
    let errorMsg = String(lastError);
    if (errorMsg.toLowerCase().includes('api_key') || errorMsg.toLowerCase().includes('auth')) {
      errorMsg = `Authentication error: ${lastError}\n\n` +
        'CadForge supports three auth methods:\n' +
        '1. ANTHROPIC_API_KEY env var (API key billing)\n' +
        '2. ANTHROPIC_AUTH_TOKEN env var (OAuth token)\n' +
        '3. Automatic: Claude Code OAuth from macOS Keychain';
    }

    if (wasStreamingText) {
      onEvent(makeEvent(EventType.TEXT, { text: '' }));
    }
    onEvent(makeEvent(EventType.ERROR, { message: `API error: ${errorMsg}` }));

    return {
      content: [{ type: 'text', text: `API error: ${errorMsg}` }],
      usage: { input_tokens: 0, output_tokens: 0 },
    };
  }

  formatToolResults(toolResults: ContentBlock[]): ContentBlock[] {
    return toolResults;
  }

  getCredentialInfo(): CredentialInfo {
    return {
      provider: 'anthropic',
      apiKey: this._creds.apiKey,
      authToken: this._creds.authToken,
    };
  }
}
