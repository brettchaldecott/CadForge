/**
 * Zustand store for UI state.
 *
 * Manages: messages, streaming text, tool panels, mode (agent/plan/ask),
 * permission prompts, status bar info. The `onEvent` helper maps
 * AgentEvents from the agentic loop into store actions so React
 * components re-render automatically.
 */

import { createStore } from 'zustand/vanilla';
import { EventType, type AgentEvent } from '@cadforge/shared';
import type { InteractionMode } from '../agent/modes.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface ToolPanel {
  id: string;
  name: string;
  input: Record<string, unknown>;
  status: 'running' | 'done' | 'error';
  result?: string;
  collapsed: boolean;
}

export interface PermissionRequest {
  id: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  resolve: (allowed: boolean) => void;
}

export interface UIState {
  // Mode
  mode: InteractionMode;

  // Processing
  isProcessing: boolean;
  streamingText: string;
  statusText: string;

  // Messages & tools
  messages: ChatMessage[];
  toolPanels: ToolPanel[];

  // Permission
  permissionRequest: PermissionRequest | null;

  // Auth & error
  authSource: string;
  error: string | null;

  // Usage
  totalInputTokens: number;
  totalOutputTokens: number;
}

export interface UIActions {
  // Text streaming
  appendTextDelta: (text: string) => void;
  flushStreamingText: () => void;

  // Messages
  addUserMessage: (content: string) => void;
  addAssistantMessage: (content: string) => void;

  // Tool panels
  addToolUse: (id: string, name: string, input: Record<string, unknown>) => void;
  updateToolResult: (id: string, result: string, isError: boolean) => void;
  toggleToolCollapsed: (id: string) => void;

  // Mode
  setMode: (mode: InteractionMode) => void;

  // Processing
  setProcessing: (processing: boolean) => void;
  setStatus: (text: string) => void;

  // Permission
  setPermissionRequest: (req: PermissionRequest | null) => void;
  resolvePermission: (allowed: boolean) => void;

  // Error
  setError: (error: string | null) => void;

  // Auth
  setAuthSource: (source: string) => void;

  // Usage
  addUsage: (input: number, output: number) => void;

  // Reset
  reset: () => void;
}

export type UIStore = UIState & UIActions;

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const initialState: UIState = {
  mode: 'agent',
  isProcessing: false,
  streamingText: '',
  statusText: '',
  messages: [],
  toolPanels: [],
  permissionRequest: null,
  authSource: 'none',
  error: null,
  totalInputTokens: 0,
  totalOutputTokens: 0,
};

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

let msgIdCounter = 0;
function nextMsgId(): string {
  return `msg-${++msgIdCounter}`;
}

export function createUIStore() {
  return createStore<UIStore>((set, get) => ({
    ...initialState,

    appendTextDelta(text: string) {
      set((s) => ({ streamingText: s.streamingText + text }));
    },

    flushStreamingText() {
      const { streamingText } = get();
      if (streamingText) {
        set((s) => ({
          messages: [
            ...s.messages,
            { id: nextMsgId(), role: 'assistant', content: streamingText, timestamp: Date.now() },
          ],
          streamingText: '',
        }));
      }
    },

    addUserMessage(content: string) {
      set((s) => ({
        messages: [
          ...s.messages,
          { id: nextMsgId(), role: 'user', content, timestamp: Date.now() },
        ],
      }));
    },

    addAssistantMessage(content: string) {
      set((s) => ({
        messages: [
          ...s.messages,
          { id: nextMsgId(), role: 'assistant', content, timestamp: Date.now() },
        ],
      }));
    },

    addToolUse(id: string, name: string, input: Record<string, unknown>) {
      set((s) => ({
        toolPanels: [
          ...s.toolPanels,
          { id, name, input, status: 'running', collapsed: false },
        ],
      }));
    },

    updateToolResult(id: string, result: string, isError: boolean) {
      set((s) => ({
        toolPanels: s.toolPanels.map((tp) =>
          tp.id === id
            ? { ...tp, status: isError ? 'error' as const : 'done' as const, result, collapsed: true }
            : tp,
        ),
      }));
    },

    toggleToolCollapsed(id: string) {
      set((s) => ({
        toolPanels: s.toolPanels.map((tp) =>
          tp.id === id ? { ...tp, collapsed: !tp.collapsed } : tp,
        ),
      }));
    },

    setMode(mode: InteractionMode) {
      set({ mode });
    },

    setProcessing(processing: boolean) {
      set({ isProcessing: processing });
      if (!processing) {
        set({ statusText: '', toolPanels: [] });
      }
    },

    setStatus(text: string) {
      set({ statusText: text });
    },

    setPermissionRequest(req: PermissionRequest | null) {
      set({ permissionRequest: req });
    },

    resolvePermission(allowed: boolean) {
      const { permissionRequest } = get();
      if (permissionRequest) {
        permissionRequest.resolve(allowed);
        set({ permissionRequest: null });
      }
    },

    setError(error: string | null) {
      set({ error });
    },

    setAuthSource(source: string) {
      set({ authSource: source });
    },

    addUsage(input: number, output: number) {
      set((s) => ({
        totalInputTokens: s.totalInputTokens + input,
        totalOutputTokens: s.totalOutputTokens + output,
      }));
    },

    reset() {
      msgIdCounter = 0;
      set({ ...initialState });
    },
  }));
}

// ---------------------------------------------------------------------------
// Event dispatcher — maps AgentEvent → store actions
// ---------------------------------------------------------------------------

export function createEventHandler(store: ReturnType<typeof createUIStore>) {
  return function onEvent(event: AgentEvent): void {
    const state = store.getState();

    switch (event.type) {
      case EventType.STATUS:
        state.setStatus((event.data.message as string) ?? '');
        break;

      case EventType.TEXT_DELTA:
        state.appendTextDelta((event.data.text as string) ?? '');
        break;

      case EventType.TEXT:
        // Complete text block (non-streaming fallback)
        break;

      case EventType.TOOL_USE_START:
        state.addToolUse(
          (event.data.id as string) ?? '',
          (event.data.name as string) ?? '',
          (event.data.input as Record<string, unknown>) ?? {},
        );
        break;

      case EventType.TOOL_RESULT: {
        const result = event.data.result;
        const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        state.updateToolResult(
          (event.data.id as string) ?? '',
          resultStr,
          (event.data.is_error as boolean) ?? false,
        );
        break;
      }

      case EventType.COMPLETION: {
        const usage = event.data.usage as { input_tokens: number; output_tokens: number } | undefined;
        if (usage) {
          state.addUsage(usage.input_tokens, usage.output_tokens);
        }
        break;
      }

      case EventType.ERROR:
        state.setError((event.data.message as string) ?? 'Unknown error');
        break;

      case EventType.PERMISSION_REQUEST:
        // Handled by the REPL's askCallback, not via events
        break;

      case EventType.MODE_CHANGE:
        state.setMode((event.data.mode as InteractionMode) ?? 'agent');
        break;
    }
  };
}
