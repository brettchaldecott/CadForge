/**
 * Permission evaluator — deny/allow/ask rule matching.
 */

import type { PermissionsConfig } from '@cadforge/shared';

export type PermissionResult = 'deny' | 'allow' | 'ask';

/**
 * Evaluate whether a tool call is allowed.
 * Rules are matched as glob patterns: ToolName(argument)
 */
export function evaluatePermission(
  permissions: PermissionsConfig,
  toolName: string,
  argument: string,
): PermissionResult {
  const pattern = `${toolName}(${argument})`;

  // Deny rules take priority
  for (const rule of permissions.deny) {
    if (matchRule(rule, toolName, argument)) return 'deny';
  }

  // Allow rules
  for (const rule of permissions.allow) {
    if (matchRule(rule, toolName, argument)) return 'allow';
  }

  // Ask rules
  for (const rule of permissions.ask) {
    if (matchRule(rule, toolName, argument)) return 'ask';
  }

  // Default: ask
  return 'ask';
}

/**
 * Match a permission rule against a tool call.
 * Supports simple glob: * matches anything, ** matches any path.
 */
function matchRule(rule: string, toolName: string, argument: string): boolean {
  // Parse rule: ToolName(pattern) or ToolName(*)
  const match = rule.match(/^(\w+)\((.+)\)$/);
  if (!match) return false;

  const [, ruleTool, rulePattern] = match;
  if (ruleTool !== toolName) return false;

  if (rulePattern === '*') return true;

  // Simple glob matching
  const regex = rulePattern
    .replace(/\*\*/g, '.*')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '.');

  return new RegExp(`^${regex}$`).test(argument);
}
