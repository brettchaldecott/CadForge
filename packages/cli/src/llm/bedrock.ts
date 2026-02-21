/**
 * AWS Bedrock provider using the ConverseStream API.
 *
 * Dynamically imports @aws-sdk/client-bedrock-runtime so it's only
 * needed when Bedrock is actually used.
 */

import { EventType, makeEvent, type CadForgeSettings } from '@cadforge/shared';
import type {
  ContentBlock,
  CredentialInfo,
  EventCallback,
  LLMMessage,
  LLMProvider,
  LLMResponse,
} from './provider.js';

const RETRY_DELAYS = [1000, 2000, 4000];

export class BedrockProvider implements LLMProvider {
  private _region: string;
  private _profile: string | null;

  constructor(region: string, profile?: string | null) {
    this._region = region;
    this._profile = profile ?? null;
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

        const name = (e as { name?: string }).name ?? '';
        const isRetryable = name === 'ThrottlingException' ||
                            name === 'ServiceUnavailableException' ||
                            name === 'ModelTimeoutException';

        if (!isRetryable) break;

        if (attempt < RETRY_DELAYS.length) {
          onEvent(makeEvent(EventType.STATUS, {
            message: `Bedrock error, retrying (${attempt + 1}/${RETRY_DELAYS.length})...`,
          }));
          await new Promise((r) => setTimeout(r, RETRY_DELAYS[attempt]));
        }
      }
    }

    const errorMsg = String(lastError);
    onEvent(makeEvent(EventType.ERROR, { message: `Bedrock error: ${errorMsg}` }));
    return {
      content: [{ type: 'text', text: `Bedrock error: ${errorMsg}` }],
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
    // Dynamic import so the SDK is only needed when Bedrock is used
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let BedrockRuntimeClient: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let ConverseStreamCommand: any;
    try {
      // Use string variable to prevent TypeScript from resolving this at compile time
      const modName = '@aws-sdk/client-bedrock-runtime';
      const mod = await (Function('m', 'return import(m)')(modName) as Promise<Record<string, unknown>>);
      BedrockRuntimeClient = mod.BedrockRuntimeClient;
      ConverseStreamCommand = mod.ConverseStreamCommand;
    } catch {
      throw new Error(
        '@aws-sdk/client-bedrock-runtime not installed. ' +
        'Install with: npm install @aws-sdk/client-bedrock-runtime',
      );
    }

    // Build client
    const clientOpts: Record<string, unknown> = { region: this._region };
    if (this._profile) {
      // AWS SDK picks up profile from AWS_PROFILE env var or credentials file
      // We set the env var if a profile is specified
      process.env.AWS_PROFILE = this._profile;
    }

    const client = new (BedrockRuntimeClient as new (opts: Record<string, unknown>) => {
      send(cmd: unknown): Promise<Record<string, unknown>>;
    })(clientOpts);

    // Translate messages to Bedrock Converse format
    const bedrockMessages = translateMessagesForBedrock(messages);

    // Translate tools to Bedrock format
    const toolConfig = options.tools.length > 0
      ? {
          tools: options.tools.map((t) => ({
            toolSpec: {
              name: t.name,
              description: t.description ?? '',
              inputSchema: { json: t.input_schema ?? {} },
            },
          })),
        }
      : undefined;

    const input: Record<string, unknown> = {
      modelId: options.settings.model,
      system: [{ text: options.system }],
      messages: bedrockMessages,
      inferenceConfig: {
        maxTokens: options.settings.maxTokens,
        temperature: options.settings.temperature,
      },
    };
    if (toolConfig) {
      input.toolConfig = toolConfig;
    }

    const command = new (ConverseStreamCommand as new (input: Record<string, unknown>) => unknown)(input);
    const response = await client.send(command);

    // Parse stream events
    const contentBlocks: ContentBlock[] = [];
    const usageInfo = { input_tokens: 0, output_tokens: 0 };
    let currentText = '';
    let currentTool: ContentBlock | null = null;
    let currentToolInput = '';

    const stream = response.stream as AsyncIterable<Record<string, unknown>> | undefined;
    if (stream) {
      for await (const event of stream) {
        if (event.contentBlockStart) {
          const start = event.contentBlockStart as Record<string, unknown>;
          const startBlock = start.start as Record<string, unknown> | undefined;
          if (startBlock?.toolUse) {
            const tu = startBlock.toolUse as Record<string, unknown>;
            currentTool = {
              type: 'tool_use',
              id: (tu.toolUseId as string) ?? '',
              name: (tu.name as string) ?? '',
              input: {},
            };
            currentToolInput = '';
            onEvent(makeEvent(EventType.TOOL_USE_START, {
              name: currentTool.name,
              id: currentTool.id,
              input: {},
            }));
          }
        } else if (event.contentBlockDelta) {
          const delta = event.contentBlockDelta as Record<string, unknown>;
          const d = delta.delta as Record<string, unknown> | undefined;
          if (d?.text) {
            const text = d.text as string;
            currentText += text;
            onEvent(makeEvent(EventType.TEXT_DELTA, { text }));
          } else if (d?.toolUse) {
            const tu = d.toolUse as Record<string, unknown>;
            if (tu.input) {
              currentToolInput += tu.input as string;
            }
          }
        } else if (event.contentBlockStop) {
          if (currentTool) {
            try {
              currentTool.input = currentToolInput ? JSON.parse(currentToolInput) : {};
            } catch {
              currentTool.input = {};
            }
            contentBlocks.push(currentTool);
            currentTool = null;
            currentToolInput = '';
          } else if (currentText) {
            contentBlocks.push({ type: 'text', text: currentText });
            currentText = '';
          }
        } else if (event.metadata) {
          const meta = event.metadata as Record<string, unknown>;
          const usage = meta.usage as Record<string, number> | undefined;
          if (usage) {
            usageInfo.input_tokens = usage.inputTokens ?? 0;
            usageInfo.output_tokens = usage.outputTokens ?? 0;
          }
        }
      }
    }

    // Flush any remaining text
    if (currentText) {
      contentBlocks.push({ type: 'text', text: currentText });
    }

    if (contentBlocks.length === 0) {
      contentBlocks.push({ type: 'text', text: '' });
    }

    return { content: contentBlocks, usage: usageInfo };
  }

  formatToolResults(toolResults: ContentBlock[]): ContentBlock[] {
    // Bedrock uses Anthropic-style format natively
    return toolResults;
  }

  getCredentialInfo(): CredentialInfo {
    return {
      provider: 'bedrock',
      awsRegion: this._region,
      awsProfile: this._profile,
    };
  }
}

/**
 * Translate Anthropic-style messages to Bedrock Converse format.
 */
function translateMessagesForBedrock(
  messages: LLMMessage[],
): Record<string, unknown>[] {
  const result: Record<string, unknown>[] = [];

  for (const msg of messages) {
    if (typeof msg.content === 'string') {
      result.push({
        role: msg.role,
        content: [{ text: msg.content }],
      });
      continue;
    }

    if (!Array.isArray(msg.content)) {
      result.push({
        role: msg.role,
        content: [{ text: String(msg.content) }],
      });
      continue;
    }

    // Translate content blocks
    const bedrockContent: Record<string, unknown>[] = [];
    for (const block of msg.content) {
      if (block.type === 'text') {
        bedrockContent.push({ text: block.text });
      } else if (block.type === 'tool_use') {
        bedrockContent.push({
          toolUse: {
            toolUseId: block.id,
            name: block.name,
            input: block.input ?? {},
          },
        });
      } else if (block.type === 'tool_result') {
        bedrockContent.push({
          toolResult: {
            toolUseId: block.tool_use_id,
            content: [{ text: (block.content as string) ?? '' }],
          },
        });
      }
    }

    if (bedrockContent.length > 0) {
      result.push({ role: msg.role, content: bedrockContent });
    }
  }

  return result;
}
