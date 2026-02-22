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
  /** Pipeline step (designer/coder/renderer/judge) */
  PIPELINE_STEP = 'pipeline_step',
  /** Pipeline round counter */
  PIPELINE_ROUND = 'pipeline_round',
  /** Pipeline rendered image */
  PIPELINE_IMAGE = 'pipeline_image',
  /** Pipeline judge verdict */
  PIPELINE_VERDICT = 'pipeline_verdict',
  /** Design status updated */
  DESIGN_UPDATED = 'design_updated',
  /** Design iteration saved */
  ITERATION_SAVED = 'iteration_saved',
  /** Design learnings indexed into vault */
  LEARNINGS_INDEXED = 'learnings_indexed',

  // ── Competitive pipeline events ──

  /** Competitive pipeline overall status change */
  COMPETITIVE_STATUS = 'competitive_status',
  /** Competitive round counter */
  COMPETITIVE_ROUND = 'competitive_round',
  /** Supervisor parsed specification */
  COMPETITIVE_SUPERVISOR = 'competitive_supervisor',
  /** Individual proposal status/progress */
  COMPETITIVE_PROPOSAL = 'competitive_proposal',
  /** Debate/critique exchange */
  COMPETITIVE_DEBATE = 'competitive_debate',
  /** Sandbox evaluation result */
  COMPETITIVE_SANDBOX = 'competitive_sandbox',
  /** Fidelity score result */
  COMPETITIVE_FIDELITY = 'competitive_fidelity',
  /** Merger/selector decision */
  COMPETITIVE_MERGER = 'competitive_merger',
  /** Learning extraction complete */
  COMPETITIVE_LEARNING = 'competitive_learning',
  /** Human approval requested — pipeline paused */
  COMPETITIVE_APPROVAL_REQUESTED = 'competitive_approval_requested',
  /** Human approval response received */
  COMPETITIVE_APPROVAL_RESPONSE = 'competitive_approval_response',
}

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
  timestamp?: string;
}

export function makeEvent(type: EventType, data: Record<string, unknown>): AgentEvent {
  return { type, data, timestamp: new Date().toISOString() };
}
