/**
 * Agent event types — shared between Node CLI and Python backend.
 */

export enum EventType {
  /** Agent is processing / thinking */
  STATUS = 'status',
  /** Streaming text chunk from LLM */
  TEXT_DELTA = 'text_delta',
  /** Complete text block (non-streaming) */
  TEXT = 'text',
  /** Tool use started */
  TOOL_USE_START = 'tool_use_start',
  /** Tool use completed with result */
  TOOL_RESULT = 'tool_result',
  /** Agent finished processing the message */
  COMPLETION = 'completion',
  /** Error occurred */
  ERROR = 'error',
  /** Permission request for a tool */
  PERMISSION_REQUEST = 'permission_request',
  /** Permission response from user */
  PERMISSION_RESPONSE = 'permission_response',
  /** Mode change (agent, plan, ask) */
  MODE_CHANGE = 'mode_change',
}

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
  timestamp?: string;
}

export function makeEvent(type: EventType, data: Record<string, unknown>): AgentEvent {
  return { type, data, timestamp: new Date().toISOString() };
}
