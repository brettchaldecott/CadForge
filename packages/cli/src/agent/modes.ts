/**
 * Interaction modes for the REPL.
 *
 * Defines agent, plan, and ask modes with their tool sets and permissions.
 */

import type { PermissionsConfig } from '@cadforge/shared';

export type InteractionMode = 'agent' | 'plan' | 'ask';

export const MODE_COLORS: Record<InteractionMode, string> = {
  agent: 'green',
  plan: 'yellow',
  ask: 'cyan',
};

export function nextMode(mode: InteractionMode): InteractionMode {
  const order: InteractionMode[] = ['agent', 'plan', 'ask'];
  const idx = order.indexOf(mode);
  return order[(idx + 1) % order.length];
}

export function modePromptPrefix(mode: InteractionMode): string {
  return `cadforge:${mode}> `;
}

/** Read-only tools allowed in plan mode */
const PLAN_MODE_TOOLS = new Set([
  'ReadFile', 'ListFiles', 'SearchVault', 'Bash', 'GetPrinter', 'Task',
]);

/**
 * Return the set of allowed tool names for a mode.
 * Returns null for agent mode (all tools allowed).
 */
export function getModeTools(mode: InteractionMode): Set<string> | null {
  if (mode === 'agent') return null;
  if (mode === 'plan') return PLAN_MODE_TOOLS;
  return new Set(); // ask: no tools
}

const PROCEED_PHRASES = new Set([
  'proceed', 'go ahead', 'do it', 'execute', 'implement',
  'build it', 'make it', "let's go", 'start', 'run it',
]);

export function hasProceedIntent(userInput: string): boolean {
  const lower = userInput.toLowerCase().trim();
  for (const phrase of PROCEED_PHRASES) {
    if (lower.includes(phrase)) return true;
  }
  return false;
}

/**
 * Return permissions that deny write tools and allow read tools (for plan mode).
 */
export function getPlanModePermissions(): PermissionsConfig {
  return {
    deny: [
      'WriteFile(*)',
      'ExecuteCadQuery(*)',
      'ExportModel(*)',
      'AnalyzeMesh(*)',
      'ShowPreview(*)',
      'SearchWeb(*)',
    ],
    allow: [
      'ReadFile(*)',
      'ListFiles(*)',
      'SearchVault(*)',
      'GetPrinter(*)',
      'Task(*)',
      'Bash(*)',
    ],
    ask: [],
  };
}
