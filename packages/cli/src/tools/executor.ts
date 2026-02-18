/**
 * Permission-gated tool execution dispatcher.
 *
 * Dispatches tool calls through the permission system and hooks,
 * then executes the appropriate tool handler.
 */

import type { HookConfig, PermissionsConfig } from '@cadforge/shared';
import { runHooks, isBlocked } from '../hooks/hooks.js';
import { evaluatePermission, type PermissionResult } from '../permissions/evaluator.js';

export type ToolHandler = (input: Record<string, unknown>) => Record<string, unknown> | Promise<Record<string, unknown>>;

export interface ToolExecResult {
  success: boolean;
  result: unknown;
  error: string | null;
  blocked: boolean;
}

export class ToolExecutor {
  projectRoot: string;
  permissions: PermissionsConfig;
  hookConfigs: HookConfig[];
  askCallback: (prompt: string) => boolean | Promise<boolean>;

  private handlers = new Map<string, ToolHandler>();
  private asyncHandlers = new Map<string, (input: Record<string, unknown>) => Promise<Record<string, unknown>>>();

  constructor(opts: {
    projectRoot: string;
    permissions: PermissionsConfig;
    hookConfigs?: HookConfig[];
    askCallback?: (prompt: string) => boolean | Promise<boolean>;
  }) {
    this.projectRoot = opts.projectRoot;
    this.permissions = opts.permissions;
    this.hookConfigs = opts.hookConfigs ?? [];
    this.askCallback = opts.askCallback ?? (() => true);
  }

  registerHandler(toolName: string, handler: ToolHandler): void {
    this.handlers.set(toolName, handler);
  }

  registerAsyncHandler(
    toolName: string,
    handler: (input: Record<string, unknown>) => Promise<Record<string, unknown>>,
  ): void {
    this.asyncHandlers.set(toolName, handler);
  }

  /**
   * Execute a tool with permission checking and hooks (sync-compatible).
   */
  execute(toolName: string, toolInput: Record<string, unknown>): ToolExecResult {
    // Permission check
    const arg = extractPermissionArg(toolName, toolInput);
    const perm = evaluatePermission(this.permissions, toolName, arg);

    if (perm === 'deny') {
      return { success: false, result: null, error: `Permission denied: ${toolName}(${arg})`, blocked: true };
    }

    if (perm === 'ask') {
      const prompt = `Allow ${toolName}(${arg})?`;
      const allowed = this.askCallback(prompt);
      // Handle sync callback
      if (typeof allowed === 'boolean' && !allowed) {
        return { success: false, result: null, error: `User denied: ${toolName}(${arg})`, blocked: true };
      }
    }

    // Pre-hooks
    const preResults = runHooks(this.hookConfigs, 'PreToolUse', toolName, arg, undefined, this.projectRoot);
    for (const hr of preResults) {
      if (isBlocked(hr)) {
        return { success: false, result: null, error: `Blocked by hook: ${hr.stderr}`, blocked: true };
      }
    }

    // Execute handler
    const handler = this.handlers.get(toolName);
    if (!handler) {
      return { success: false, result: null, error: `No handler registered for tool: ${toolName}`, blocked: false };
    }

    try {
      const result = handler(toolInput);
      const output: ToolExecResult = { success: true, result, error: null, blocked: false };

      // Post-hooks
      runHooks(this.hookConfigs, 'PostToolUse', toolName, arg,
        { TOOL_OUTPUT: String(result) }, this.projectRoot);

      return output;
    } catch (e) {
      return { success: false, result: null, error: String(e), blocked: false };
    }
  }

  /**
   * Execute a tool asynchronously.
   * Prefers native async handlers; falls back to sync handler.
   */
  async executeAsync(toolName: string, toolInput: Record<string, unknown>): Promise<ToolExecResult> {
    // Permission check
    const arg = extractPermissionArg(toolName, toolInput);
    const perm = evaluatePermission(this.permissions, toolName, arg);

    if (perm === 'deny') {
      return { success: false, result: null, error: `Permission denied: ${toolName}(${arg})`, blocked: true };
    }

    if (perm === 'ask') {
      const prompt = `Allow ${toolName}(${arg})?`;
      const allowed = await Promise.resolve(this.askCallback(prompt));
      if (!allowed) {
        return { success: false, result: null, error: `User denied: ${toolName}(${arg})`, blocked: true };
      }
    }

    // Pre-hooks
    const preResults = runHooks(this.hookConfigs, 'PreToolUse', toolName, arg, undefined, this.projectRoot);
    for (const hr of preResults) {
      if (isBlocked(hr)) {
        return { success: false, result: null, error: `Blocked by hook: ${hr.stderr}`, blocked: true };
      }
    }

    // Prefer async handler
    const asyncHandler = this.asyncHandlers.get(toolName);
    if (asyncHandler) {
      try {
        const result = await asyncHandler(toolInput);
        runHooks(this.hookConfigs, 'PostToolUse', toolName, arg,
          { TOOL_OUTPUT: String(result) }, this.projectRoot);
        return { success: true, result, error: null, blocked: false };
      } catch (e) {
        return { success: false, result: null, error: String(e), blocked: false };
      }
    }

    // Fall back to sync handler
    const handler = this.handlers.get(toolName);
    if (!handler) {
      return { success: false, result: null, error: `No handler registered for tool: ${toolName}`, blocked: false };
    }

    try {
      const result = await Promise.resolve(handler(toolInput));
      runHooks(this.hookConfigs, 'PostToolUse', toolName, arg,
        { TOOL_OUTPUT: String(result) }, this.projectRoot);
      return { success: true, result, error: null, blocked: false };
    } catch (e) {
      return { success: false, result: null, error: String(e), blocked: false };
    }
  }
}

/**
 * Extract the primary argument for permission matching.
 */
function extractPermissionArg(toolName: string, toolInput: Record<string, unknown>): string {
  switch (toolName) {
    case 'Bash': {
      const cmd = (toolInput.command as string) ?? '';
      const parts = cmd.split(/\s+/, 2);
      return parts.length > 1 ? `${parts[0]}:${parts[1]}` : parts[0] ?? '*';
    }
    case 'ReadFile':
    case 'WriteFile':
    case 'AnalyzeMesh':
    case 'ShowPreview':
      return (toolInput.path as string) ?? '*';
    case 'ExecuteCadQuery':
      return (toolInput.output_name as string) ?? '*';
    case 'SearchVault':
      return (toolInput.query as string) ?? '*';
    case 'ExportModel':
      return (toolInput.source as string) ?? '*';
    case 'ListFiles':
      return (toolInput.pattern as string) ?? '*';
    case 'Task':
      return (toolInput.agent_type as string) ?? '*';
    default:
      return '*';
  }
}
