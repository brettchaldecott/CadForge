/**
 * Hook system — PreToolUse, PostToolUse, SessionStart.
 *
 * Executes shell commands from settings in response to lifecycle events.
 * Exit codes: 0=success, 2=block (stderr fed to agent), other=non-blocking error.
 */

import { execSync } from 'node:child_process';
import type { HookConfig, HookDefinition } from '@cadforge/shared';

export type HookEvent = 'PreToolUse' | 'PostToolUse' | 'SessionStart' | 'UserPromptSubmit';

export interface HookResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export function isSuccess(result: HookResult): boolean {
  return result.exitCode === 0;
}

export function isBlocked(result: HookResult): boolean {
  return result.exitCode === 2;
}

/**
 * Check if a hook matcher matches a tool invocation.
 */
function matchesHook(matcher: string, toolName: string, toolArg = '*'): boolean {
  if (matcher === '*') return true;

  const match = matcher.match(/^(\w+)\((.+)\)$/);
  if (!match) return matcher === toolName;

  const [, mTool, mPattern] = match;
  if (mTool !== toolName) return false;

  // Simple glob matching
  if (mPattern === '*') return true;

  const regex = mPattern
    .replace(/\*\*/g, '.*')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '.');

  return new RegExp(`^${regex}$`).test(toolArg);
}

/**
 * Execute a single hook command.
 */
function executeHook(
  hook: HookDefinition,
  env?: Record<string, string>,
  cwd?: string,
): HookResult {
  const fullEnv = { ...process.env, ...(env ?? {}) };
  const timeout = (hook.timeout ?? 30) * 1000;

  try {
    const stdout = execSync(hook.command, {
      cwd,
      env: fullEnv,
      timeout,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return { exitCode: 0, stdout: stdout ?? '', stderr: '' };
  } catch (e) {
    const err = e as { status?: number; stdout?: string; stderr?: string; message?: string };
    if (err.status !== undefined) {
      return {
        exitCode: err.status ?? 1,
        stdout: err.stdout ?? '',
        stderr: err.stderr ?? '',
      };
    }
    return {
      exitCode: 1,
      stdout: '',
      stderr: err.message ?? String(e),
    };
  }
}

/**
 * Find all hook definitions that match an event and tool invocation.
 */
function getMatchingHooks(
  configs: HookConfig[],
  event: HookEvent,
  toolName = '',
  toolArg = '*',
): HookDefinition[] {
  const matching: HookDefinition[] = [];
  for (const config of configs) {
    if (config.event !== event) continue;
    if (event === 'PreToolUse' || event === 'PostToolUse') {
      if (!matchesHook(config.matcher ?? '*', toolName, toolArg)) continue;
    }
    matching.push(...config.hooks);
  }
  return matching;
}

/**
 * Run all matching hooks for an event.
 * If any hook returns exit code 2 (block), stop and return.
 */
export function runHooks(
  configs: HookConfig[],
  event: HookEvent,
  toolName = '',
  toolArg = '*',
  env?: Record<string, string>,
  cwd?: string,
): HookResult[] {
  const hooks = getMatchingHooks(configs, event, toolName, toolArg);
  const results: HookResult[] = [];
  for (const hook of hooks) {
    const result = executeHook(hook, env, cwd);
    results.push(result);
    if (isBlocked(result)) break;
  }
  return results;
}

/**
 * Load hook configurations from settings data.
 */
export function loadHookConfigs(hooksData: HookConfig[]): HookConfig[] {
  return hooksData.filter((h) => h.event && h.hooks && h.hooks.length > 0);
}
