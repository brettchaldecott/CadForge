/**
 * REPL orchestrator — manages the input -> process -> output cycle.
 *
 * Handles slash commands, shell shortcuts, mode switching,
 * Ctrl+C cancellation via AbortController, and auto-switch
 * from plan -> agent on proceed intent.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Box, Text, useInput, useStdin, useApp } from 'ink';
import { useStore } from 'zustand';
import type { StoreApi } from 'zustand';
import type { Agent } from '../agent/agent.js';
import type { InteractionMode } from '../agent/modes.js';
import { nextMode, hasProceedIntent, MODE_COLORS } from '../agent/modes.js';
import type { Skill } from '../skills/loader.js';
import { PromptInput } from './PromptInput.js';
import { StreamingText } from './StreamingText.js';
import { ToolPanel } from './ToolPanel.js';
import { Permission } from './Permission.js';
import { StatusBar } from './StatusBar.js';
import type { UIStore, PermissionRequest } from './store.js';
import { createEventHandler } from './store.js';

interface ReplProps {
  store: StoreApi<UIStore>;
  agent: Agent;
  model: string;
  slashCommands: Map<string, Skill>;
  projectRoot: string;
}

export function Repl({ store, agent, model, slashCommands, projectRoot }: ReplProps): React.ReactElement {
  const { exit } = useApp();
  const { isRawModeSupported } = useStdin();

  // Subscribe to store slices
  const mode = useStore(store, (s) => s.mode);
  const isProcessing = useStore(store, (s) => s.isProcessing);
  const streamingText = useStore(store, (s) => s.streamingText);
  const messages = useStore(store, (s) => s.messages);
  const toolPanels = useStore(store, (s) => s.toolPanels);
  const permissionRequest = useStore(store, (s) => s.permissionRequest);
  const statusText = useStore(store, (s) => s.statusText);
  const error = useStore(store, (s) => s.error);
  const totalInputTokens = useStore(store, (s) => s.totalInputTokens);
  const totalOutputTokens = useStore(store, (s) => s.totalOutputTokens);

  // AbortController for cancellation
  const abortRef = useRef<AbortController | null>(null);
  const onEventRef = useRef(createEventHandler(store));

  // --- Ctrl+C and Shift+Tab ---
  useInput((input, key) => {
    // Ctrl+C — cancel running agent or exit
    if (input === 'c' && key.ctrl) {
      if (isProcessing && abortRef.current) {
        abortRef.current.abort();
      } else if (!isProcessing) {
        cleanup();
        exit();
      }
      return;
    }

    // Shift+Tab — cycle modes (only when not processing)
    if (key.tab && key.shift) {
      if (!isProcessing) {
        const next = nextMode(mode);
        store.getState().setMode(next);
      }
      return;
    }
  }, { isActive: isRawModeSupported });

  // Clear error after 5s
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => store.getState().setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error, store]);

  function cleanup() {
    agent.saveSession();
  }

  // --- Process user input ---
  const handleSubmit = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;

    const state = store.getState();

    // Shell shortcut: !command
    if (input.startsWith('!')) {
      await handleShellCommand(input.slice(1), state);
      return;
    }

    // Built-in commands
    if (input === '/quit' || input === '/exit') {
      cleanup();
      exit();
      return;
    }

    if (input === '/help') {
      showHelp(state, mode, slashCommands);
      return;
    }

    if (input === '/agent') {
      state.setMode('agent');
      state.addAssistantMessage('Switched to AGENT mode.');
      return;
    }

    if (input === '/plan') {
      state.setMode('plan');
      state.addAssistantMessage('Switched to PLAN mode.');
      return;
    }

    if (input === '/ask') {
      state.setMode('ask');
      state.addAssistantMessage('Switched to ASK mode.');
      return;
    }

    if (input === '/mode') {
      state.addAssistantMessage(`Current mode: ${mode}`);
      return;
    }

    if (input === '/skills') {
      showSkills(state, slashCommands);
      return;
    }

    if (input === '/sessions') {
      showSessions(state, agent);
      return;
    }

    if (input.startsWith('/provider')) {
      handleProvider(input, state, agent);
      return;
    }

    // Skill slash commands
    let userInput = input;
    const parts = input.split(/\s+/, 2);
    const cmd = parts[0];
    if (slashCommands.has(cmd)) {
      const skill = slashCommands.get(cmd)!;
      const skillArg = parts[1] ?? '';
      userInput = `${skill.prompt}\n\nUser request: ${skillArg}`;
    }

    // Auto-switch plan -> agent on proceed intent
    let currentMode = store.getState().mode;
    if (currentMode === 'plan' && hasProceedIntent(userInput)) {
      state.setMode('agent');
      state.addAssistantMessage('Switched to AGENT mode to execute the plan.');
      currentMode = 'agent';
    }

    // Add user message to display
    state.addUserMessage(input);
    state.setProcessing(true);
    state.setError(null);

    // Run agent
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await agent.processMessage(
        userInput,
        currentMode,
        onEventRef.current,
        controller.signal,
      );
      // Flush any remaining streaming text
      store.getState().flushStreamingText();
    } catch (e) {
      if ((e as Error).name === 'AbortError' || controller.signal.aborted) {
        store.getState().addAssistantMessage('Cancelled.');
      } else {
        store.getState().setError(String(e));
      }
    } finally {
      abortRef.current = null;
      store.getState().setProcessing(false);
    }
  }, [agent, store, mode, slashCommands, exit]);

  return (
    <Box flexDirection="column">
      {/* Recent messages */}
      <MessageList messages={messages} />

      {/* Tool panels */}
      {toolPanels.map((panel) => (
        <ToolPanel
          key={panel.id}
          panel={panel}
          onToggle={() => store.getState().toggleToolCollapsed(panel.id)}
        />
      ))}

      {/* Streaming text */}
      <StreamingText text={streamingText} />

      {/* Error */}
      {error && (
        <Box marginLeft={2}>
          <Text color="red">Error: {error}</Text>
        </Box>
      )}

      {/* Permission prompt */}
      {permissionRequest && (
        <Permission
          request={permissionRequest}
          onResolve={(allowed) => store.getState().resolvePermission(allowed)}
        />
      )}

      {/* Status bar */}
      <StatusBar
        mode={mode}
        model={model}
        statusText={statusText}
        totalInputTokens={totalInputTokens}
        totalOutputTokens={totalOutputTokens}
        isProcessing={isProcessing}
      />

      {/* Input */}
      <PromptInput
        mode={mode}
        isProcessing={isProcessing}
        onSubmit={handleSubmit}
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Message list
// ---------------------------------------------------------------------------

interface MessageListProps {
  messages: Array<{ id: string; role: string; content: string }>;
}

function MessageList({ messages }: MessageListProps): React.ReactElement | null {
  // Show last N messages to keep the terminal readable
  const visible = messages.slice(-20);
  if (visible.length === 0) return null;

  return (
    <Box flexDirection="column">
      {visible.map((msg) => (
        <Box key={msg.id} marginLeft={msg.role === 'assistant' ? 2 : 0}>
          {msg.role === 'user' ? (
            <Text>
              <Text color="blue" bold>You: </Text>
              {msg.content}
            </Text>
          ) : (
            <Text>{msg.content}</Text>
          )}
        </Box>
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function handleShellCommand(
  command: string,
  state: UIStore,
): Promise<void> {
  const trimmed = command.trim();
  if (!trimmed) {
    state.addAssistantMessage('Usage: !<command>');
    return;
  }

  const { execSync } = await import('node:child_process');
  try {
    const result = execSync(trimmed, {
      encoding: 'utf-8',
      timeout: 120_000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    if (result.trim()) {
      state.addAssistantMessage(result.trimEnd());
    }
  } catch (e) {
    const err = e as { stderr?: string; message?: string };
    state.setError(err.stderr?.trimEnd() ?? err.message ?? 'Shell command failed');
  }
}

function showHelp(
  state: UIStore,
  mode: InteractionMode,
  slashCommands: Map<string, Skill>,
): void {
  let help = `Current Mode: ${mode}\n\n` +
    'Modes:\n' +
    '  /agent  — Full agentic loop with all tools\n' +
    '  /plan   — Read-only, generates plans without modifying files\n' +
    '  /ask    — Pure Q&A, no tools, answers from knowledge\n' +
    '  /mode   — Show current mode\n\n' +
    'Commands:\n' +
    '  /help     — Show this help\n' +
    '  /provider — Show or switch LLM provider\n' +
    '  /skills   — List available skills\n' +
    '  /sessions — List recent sessions\n' +
    '  /quit     — Exit CadForge\n\n' +
    'Shortcuts:\n' +
    '  Shift+Tab — Cycle modes (agent -> plan -> ask)\n' +
    '  Ctrl+C    — Cancel running agent / exit\n' +
    '  !command  — Run shell command directly\n' +
    '  \\         — Continue on next line\n';

  if (slashCommands.size > 0) {
    help += '\nSkills:\n';
    for (const [cmd, skill] of slashCommands) {
      help += `  ${cmd} — ${skill.description}\n`;
    }
  }

  state.addAssistantMessage(help);
}

function showSkills(state: UIStore, slashCommands: Map<string, Skill>): void {
  if (slashCommands.size === 0) {
    state.addAssistantMessage('No skills found.');
    return;
  }
  const lines = [...slashCommands.entries()]
    .map(([cmd, skill]) => `  ${cmd} — ${skill.description}`);
  state.addAssistantMessage(lines.join('\n'));
}

function showSessions(state: UIStore, agent: Agent): void {
  const sessions = agent.sessionIndex.listSessions(10);
  if (sessions.length === 0) {
    state.addAssistantMessage('No previous sessions found.');
    return;
  }
  const lines = sessions.map(
    (s) => `  ${s.session_id}: ${s.summary} (${s.message_count} msgs)`,
  );
  state.addAssistantMessage(lines.join('\n'));
}

function handleProvider(input: string, state: UIStore, agent: Agent): void {
  const VALID_PROVIDERS = ['anthropic', 'openai', 'ollama', 'bedrock'] as const;
  const parts = input.split(/\s+/);

  if (parts.length === 1) {
    // Show current provider info
    const info = agent.settings.provider;
    const model = agent.settings.model;
    state.addAssistantMessage(
      `Current provider: ${info}\nModel: ${model}\n\n` +
      `Usage: /provider <${VALID_PROVIDERS.join('|')}> [model]`,
    );
    return;
  }

  const providerName = parts[1] as typeof VALID_PROVIDERS[number];
  if (!VALID_PROVIDERS.includes(providerName)) {
    state.addAssistantMessage(
      `Unknown provider: ${parts[1]}\nValid providers: ${VALID_PROVIDERS.join(', ')}`,
    );
    return;
  }

  const model = parts[2] ?? undefined; // optional model override
  agent.switchProvider(providerName, model);
  state.addAssistantMessage(
    `Switched to ${providerName} provider.\nModel: ${agent.settings.model}`,
  );
}
