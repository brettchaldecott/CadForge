/**
 * Agent event types — shared between Node CLI and Python backend.
 * Mirrors the Python EventType enum in core/events.py.
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

export interface TextDeltaEvent extends AgentEvent {
  type: EventType.TEXT_DELTA;
  data: { text: string };
}

export interface ToolUseStartEvent extends AgentEvent {
  type: EventType.TOOL_USE_START;
  data: { name: string; id: string; input: Record<string, unknown> };
}

export interface ToolResultEvent extends AgentEvent {
  type: EventType.TOOL_RESULT;
  data: {
    name: string;
    id: string;
    result: Record<string, unknown>;
    is_error?: boolean;
  };
}

export interface CompletionEvent extends AgentEvent {
  type: EventType.COMPLETION;
  data: {
    text: string;
    usage?: { input_tokens: number; output_tokens: number };
  };
}

export interface ErrorEvent extends AgentEvent {
  type: EventType.ERROR;
  data: { message: string; code?: string };
}

export interface PermissionRequestEvent extends AgentEvent {
  type: EventType.PERMISSION_REQUEST;
  data: {
    tool_name: string;
    tool_input: Record<string, unknown>;
    id: string;
  };
}

export interface ModeChangeEvent extends AgentEvent {
  type: EventType.MODE_CHANGE;
  data: { mode: 'agent' | 'plan' | 'ask' };
}
