/**
 * Node-side subagent executor.
 *
 * Spawns explore/plan subagents in Node (lightweight, restricted tool sets).
 * CAD subagent delegation is handled separately via Python SSE.
 */

import { type CadForgeSettings, getDefaultSubagentModel } from '@cadforge/shared';
import type { LLMProvider, ContentBlock, EventCallback } from '../llm/provider.js';
import type { BackendClient } from '../backend/client.js';
import { getToolDefinitions, type ToolDefinition } from '../tools/registry.js';
import { handleReadFile, handleListFiles } from '../tools/file.js';
import { handleBash } from '../tools/bash.js';

export type SubagentType = 'explore' | 'plan';

export interface SubagentConfig {
  name: SubagentType;
  model: string;
  tools: string[];
  maxIterations: number;
  systemPrompt: string;
}

export interface SubagentResult {
  success: boolean;
  output: string;
  agentName: string;
  error?: string;
}

function createExploreConfig(settings: CadForgeSettings): SubagentConfig {
  return {
    name: 'explore',
    model: settings.subagentModels.explore ?? getDefaultSubagentModel(settings.provider, 'explore'),
    tools: ['ReadFile', 'ListFiles', 'SearchVault', 'Bash'],
    maxIterations: 10,
    systemPrompt:
      'You are a CadForge explore subagent. Your role is to search and read files ' +
      'to gather information. Report your findings concisely. ' +
      'You do NOT modify files or run CadQuery code.',
  };
}

function createPlanConfig(settings: CadForgeSettings): SubagentConfig {
  return {
    name: 'plan',
    model: settings.subagentModels.plan ?? getDefaultSubagentModel(settings.provider, 'plan'),
    tools: ['ReadFile', 'ListFiles', 'SearchVault'],
    maxIterations: 10,
    systemPrompt:
      'You are a CadForge plan subagent. Your role is to analyze the project ' +
      'and create a detailed plan. Read files and search the vault as needed. ' +
      'You do NOT modify files, run code, or execute commands.',
  };
}

export function getSubagentConfig(agentType: SubagentType, settings: CadForgeSettings): SubagentConfig {
  switch (agentType) {
    case 'explore':
      return createExploreConfig(settings);
    case 'plan':
      return createPlanConfig(settings);
  }
}

type ToolHandler = (input: Record<string, unknown>) => Record<string, unknown> | Promise<Record<string, unknown>>;

function buildToolHandlers(
  config: SubagentConfig,
  projectRoot: string,
  backendClient?: BackendClient,
): Map<string, ToolHandler> {
  const handlers = new Map<string, ToolHandler>();

  for (const toolName of config.tools) {
    switch (toolName) {
      case 'ReadFile':
        handlers.set('ReadFile', (inp) => handleReadFile(inp, projectRoot));
        break;
      case 'ListFiles':
        handlers.set('ListFiles', (inp) => handleListFiles(inp, projectRoot));
        break;
      case 'Bash':
        handlers.set('Bash', (inp) => handleBash(inp, projectRoot));
        break;
      case 'SearchVault':
        handlers.set('SearchVault', async (inp) => {
          if (!backendClient) {
            return { success: false, error: 'Backend not available for SearchVault' };
          }
          return backendClient.callTool('SearchVault', inp);
        });
        break;
    }
  }

  return handlers;
}

export class SubagentExecutor {
  /**
   * Run a local subagent (explore or plan) with a restricted tool set.
   * Uses a simplified agentic loop — no session tracking, no permissions.
   */
  static async runLocal(
    agentType: SubagentType,
    prompt: string,
    context: string,
    provider: LLMProvider,
    settings: CadForgeSettings,
    projectRoot: string,
    backendClient?: BackendClient,
  ): Promise<SubagentResult> {
    const config = getSubagentConfig(agentType, settings);

    // Filter tool definitions to config.tools only, never include Task
    const allTools = getToolDefinitions();
    const allowedNames = new Set(config.tools);
    const tools: Record<string, unknown>[] = allTools
      .filter((t) => allowedNames.has(t.name) && t.name !== 'Task') as unknown as Record<string, unknown>[];

    // Build tool handlers
    const handlers = buildToolHandlers(config, projectRoot, backendClient);

    // Override model for this subagent
    const subSettings: CadForgeSettings = {
      ...settings,
      model: config.model,
    };

    // Build initial messages
    let userContent = prompt;
    if (context) {
      userContent = `Context:\n${context}\n\nTask:\n${prompt}`;
    }

    const messages: { role: 'user' | 'assistant'; content: string | ContentBlock[] }[] = [
      { role: 'user', content: userContent },
    ];

    // No-op event callback — subagent events are not rendered
    const noopEvent: EventCallback = () => {};

    try {
      for (let i = 0; i < config.maxIterations; i++) {
        const response = await provider.stream(
          messages,
          { system: config.systemPrompt, tools, settings: subSettings },
          noopEvent,
        );

        if (!response) {
          return {
            success: false,
            output: '',
            agentName: config.name,
            error: 'Failed to get response from API',
          };
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

        // No tool use — done
        if (toolUses.length === 0) {
          return {
            success: true,
            output: textParts.join('\n'),
            agentName: config.name,
          };
        }

        // Record assistant message
        messages.push({ role: 'assistant', content: response.content });

        // Execute tools
        const toolResults: ContentBlock[] = [];
        for (const toolUse of toolUses) {
          const name = toolUse.name as string;
          const id = toolUse.id as string;
          const input = toolUse.input as Record<string, unknown>;

          const handler = handlers.get(name);
          if (!handler) {
            toolResults.push({
              type: 'tool_result',
              tool_use_id: id,
              content: JSON.stringify({ error: `No handler for tool: ${name}` }),
            });
            continue;
          }

          try {
            const result = await Promise.resolve(handler(input));
            toolResults.push({
              type: 'tool_result',
              tool_use_id: id,
              content: JSON.stringify(result),
            });
          } catch (e) {
            toolResults.push({
              type: 'tool_result',
              tool_use_id: id,
              content: JSON.stringify({ error: String(e) }),
            });
          }
        }

        // Add tool results as user message
        messages.push({ role: 'user', content: toolResults });
      }

      return {
        success: true,
        output: 'Maximum iterations reached.',
        agentName: config.name,
      };
    } catch (e) {
      return {
        success: false,
        output: '',
        agentName: config.name,
        error: String(e),
      };
    }
  }
}
