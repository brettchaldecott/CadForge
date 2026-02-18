/**
 * Tool dispatch — routes tool calls to local handlers or remote (Python) API.
 * Will be fully implemented in Phase 2.
 */

import type { BackendClient } from '../backend/client.js';
import { TOOL_REGISTRY } from './registry.js';

/**
 * Determine whether a tool runs locally or remotely.
 */
export function getToolLocation(toolName: string): 'local' | 'remote' | null {
  const entry = TOOL_REGISTRY.find((e) => e.definition.name === toolName);
  return entry?.location ?? null;
}
