/**
 * Main agentic loop for CadForge.
 *
 * Implements the gather -> act -> verify cycle using streaming LLM
 * responses and tool use, pushing AgentEvents for real-time rendering.
 */

import { EventType, makeEvent, type CadForgeSettings, type ProviderType } from '@cadforge/shared';
import { getDefaultModel } from '@cadforge/shared';
import { loadSettings } from '../config/settings.js';
import type { AuthCredentials } from '../llm/auth.js';
import { resolveAuthForProvider } from '../llm/auth.js';
import { createProvider } from '../llm/factory.js';
import type { ContentBlock, EventCallback, LLMProvider, LLMResponse } from '../llm/provider.js';
import { ToolExecutor } from '../tools/executor.js';
import { getToolDefinitions } from '../tools/registry.js';
import { handleBash } from '../tools/bash.js';
import { handleReadFile, handleWriteFile, handleListFiles } from '../tools/file.js';
import { handleGetPrinter } from '../tools/project.js';
import { loadHookConfigs, runHooks } from '../hooks/hooks.js';
import { Session, SessionIndex } from '../session/session.js';
import {
  type ContextState,
  createContextState,
  needsCompaction,
  estimateMessagesTokens,
  compactMessages,
} from './context.js';
import { buildSystemPrompt } from './system-prompt.js';
import { type InteractionMode, getModeTools, getPlanModePermissions } from './modes.js';
import type { BackendClient } from '../backend/client.js';

export interface AgentOptions {
  projectRoot: string;
  settings?: CadForgeSettings;
  session?: Session;
  askCallback?: (prompt: string) => boolean | Promise<boolean>;
  backendClient?: BackendClient;
}

export class Agent {
  readonly projectRoot: string;
  readonly settings: CadForgeSettings;
  readonly session: Session;
  readonly executor: ToolExecutor;
  readonly sessionIndex: SessionIndex;
  readonly systemPrompt: string;
  readonly contextState: ContextState;

  private _authCreds: AuthCredentials;
  private _provider: LLMProvider;
  private _backendClient?: BackendClient;
  private _currentOnEvent?: EventCallback;

  constructor(opts: AgentOptions) {
    this.projectRoot = opts.projectRoot;
    this.settings = opts.settings ?? loadSettings(opts.projectRoot);
    this.session = opts.session ?? new Session(opts.projectRoot);
    this._backendClient = opts.backendClient;

    // Resolve auth per provider
    this._authCreds = resolveAuthForProvider(this.settings.provider, this.settings.providerConfig);
    this._provider = createProvider(this.settings.provider, {
      credentials: this._authCreds,
      providerConfig: this.settings.providerConfig,
    });

    // Build system prompt
    this.systemPrompt = buildSystemPrompt(this.projectRoot, this.settings);

    // Set up tool executor
    const hookConfigs = loadHookConfigs(this.settings.hooks);
    this.executor = new ToolExecutor({
      projectRoot: this.projectRoot,
      permissions: this.settings.permissions,
      hookConfigs,
      askCallback: opts.askCallback,
    });
    this.registerToolHandlers();

    // Context management
    this.contextState = createContextState();

    // Session index
    this.sessionIndex = new SessionIndex(this.projectRoot);

    // Session start hooks
    runHooks(hookConfigs, 'SessionStart', '', '*', undefined, this.projectRoot);
  }

  private registerToolHandlers(): void {
    const pr = this.projectRoot;

    this.executor.registerHandler('ReadFile', (inp) => handleReadFile(inp, pr));
    this.executor.registerHandler('WriteFile', (inp) => handleWriteFile(inp, pr));
    this.executor.registerHandler('ListFiles', (inp) => handleListFiles(inp, pr));
    this.executor.registerHandler('Bash', (inp) => handleBash(inp, pr));
    this.executor.registerHandler('GetPrinter', (inp) =>
      handleGetPrinter(inp, pr, this.settings.printer),
    );

    // Remote tools — delegate to Python backend
    const remoteTools = ['ExecuteCadQuery', 'AnalyzeMesh', 'ShowPreview', 'ExportModel', 'SearchVault'];
    for (const toolName of remoteTools) {
      this.executor.registerHandler(toolName, async (inp) => {
        if (!this._backendClient) {
          return { success: false, error: 'Python backend not available' };
        }
        return this._backendClient.callTool(toolName, inp);
      });
    }

    this.executor.registerHandler('SearchWeb', () =>
      ({ success: false, error: 'Not yet implemented' }),
    );
    this.executor.registerAsyncHandler('Task', async (inp) => {
      const { handleTask } = await import('../tools/task.js');
      return handleTask(inp, {
        provider: this._provider,
        settings: this.settings,
        projectRoot: this.projectRoot,
        backendClient: this._backendClient,
        onEvent: this._currentOnEvent,
      });
    });
  }

  /**
   * Process a user message through the async agentic loop with streaming.
   *
   * Calls onEvent for each agent event (text deltas, tool uses, errors, etc.)
   * Returns the final assistant text response.
   */
  async processMessage(
    userInput: string,
    mode: InteractionMode = 'agent',
    onEvent?: EventCallback,
    signal?: AbortSignal,
  ): Promise<string> {
    const emit = onEvent ?? (() => {});

    // Record user message
    this.session.addUserMessage(userInput);
    let messages = this.session.getApiMessages();

    // Context compaction
    const tokens = estimateMessagesTokens(messages);
    this.contextState.estimatedTokens = tokens;
    if (needsCompaction(this.contextState) && messages.length > 8) {
      const summary = this.generateSummary(messages.slice(0, -4));
      messages = compactMessages(messages, summary);
      this.contextState.compactionCount += 1;
    }

    // Filter tools by mode
    const allTools = getToolDefinitions() as unknown as Record<string, unknown>[];
    const allowedToolNames = getModeTools(mode);
    const tools = allowedToolNames !== null
      ? allTools.filter((t) => allowedToolNames.has(t.name as string))
      : allTools;

    // Mode-aware system prompt
    let systemPrompt = this.systemPrompt;
    if (mode === 'plan') {
      systemPrompt += '\n\nYou are in PLAN mode. Read-only. ' +
        'Provide a detailed plan, do NOT modify files or execute code. ' +
        'If the user asks you to proceed or execute, tell them to type ' +
        '/agent or press Shift+Tab to switch to agent mode.';
    } else if (mode === 'ask') {
      systemPrompt += '\n\nYou are in ASK mode. No tools available. Answer from knowledge only.';
    }

    // Swap permissions for plan mode
    const originalPermissions = this.executor.permissions;
    if (mode === 'plan') {
      this.executor.permissions = getPlanModePermissions();
    }

    try {
      return await this.runAgenticLoop(messages, systemPrompt, tools, emit, signal);
    } finally {
      this.executor.permissions = originalPermissions;
    }
  }

  private async runAgenticLoop(
    messages: Record<string, unknown>[],
    systemPrompt: string,
    tools: Record<string, unknown>[],
    onEvent: EventCallback,
    signal?: AbortSignal,
  ): Promise<string> {
    this._currentOnEvent = onEvent;
    const MAX_ITERATIONS = 20;

    for (let i = 0; i < MAX_ITERATIONS; i++) {
      // Check for cancellation
      if (signal?.aborted) {
        onEvent(makeEvent(EventType.ERROR, { message: 'Cancelled' }));
        return 'Cancelled by user.';
      }

      onEvent(makeEvent(EventType.STATUS, { message: 'Thinking...' }));

      const response = await this._provider.stream(
        messages as { role: 'user' | 'assistant'; content: string | ContentBlock[] }[],
        { system: systemPrompt, tools, settings: this.settings },
        onEvent,
      );

      if (!response) {
        const errorMsg = 'Failed to get response from API';
        this.session.addAssistantMessage(errorMsg);
        onEvent(makeEvent(EventType.ERROR, { message: errorMsg }));
        return errorMsg;
      }

      // Separate text and tool uses
      const textParts: string[] = [];
      const toolUses: ContentBlock[] = [];

      for (const block of response.content) {
        if (block.type === 'text') {
          textParts.push(block.text as string);
        } else if (block.type === 'tool_use') {
          toolUses.push(block);
        }
      }

      // No tool use — we're done
      if (toolUses.length === 0) {
        const finalText = textParts.join('\n');
        this.session.addAssistantMessage(finalText, response.usage);
        onEvent(makeEvent(EventType.COMPLETION, {
          text: finalText,
          usage: response.usage,
        }));
        return finalText;
      }

      // Record assistant message with tool uses
      this.session.addAssistantMessage(
        response.content as unknown as Record<string, unknown>[],
        response.usage,
      );

      // Execute tools
      const toolResults: Record<string, unknown>[] = [];
      for (const toolUse of toolUses) {
        const name = toolUse.name as string;
        const id = toolUse.id as string;
        const input = toolUse.input as Record<string, unknown>;

        onEvent(makeEvent(EventType.STATUS, { message: `Executing ${name}...` }));

        const result = await this.executor.executeAsync(name, input);

        onEvent(makeEvent(EventType.TOOL_RESULT, {
          name,
          id,
          result: result.result ?? result.error,
          is_error: !result.success,
        }));

        toolResults.push({
          type: 'tool_result',
          tool_use_id: id,
          content: JSON.stringify(result.success ? result.result : { error: result.error }),
        });
      }

      // Add tool results as user message
      this.session.addUserMessage(toolResults);
      messages = this.session.getApiMessages();
    }

    return 'Maximum iterations reached. Please try a simpler request.';
  }

  private generateSummary(messages: Record<string, unknown>[]): string {
    const parts: string[] = [];
    for (const msg of messages.slice(-6)) {
      const content = msg.content;
      if (typeof content === 'string' && content.trim()) {
        parts.push(content.slice(0, 200));
      }
    }
    return 'Previous conversation covered: ' + parts.join('; ');
  }

  /**
   * Switch provider and model at runtime.
   * Re-resolves credentials for the new provider.
   */
  switchProvider(provider: ProviderType, model?: string): void {
    (this.settings as { provider: ProviderType }).provider = provider;
    (this.settings as { model: string }).model = model ?? getDefaultModel(provider);
    this._authCreds = resolveAuthForProvider(provider, this.settings.providerConfig);
    this._provider = createProvider(provider, {
      credentials: this._authCreds,
      providerConfig: this.settings.providerConfig,
    });
  }

  saveSession(): void {
    this.sessionIndex.update(this.session);
  }
}
