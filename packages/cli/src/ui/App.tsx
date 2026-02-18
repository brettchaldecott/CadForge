/**
 * Root Ink component — composes Welcome + Repl.
 *
 * Receives resolved props from chat.ts (projectRoot, settings, etc.).
 * Creates the Agent instance and wires the permission callback through
 * the Zustand store so the Permission component handles Y/N input.
 */

import React, { useEffect, useRef, useMemo } from 'react';
import { Box, useApp } from 'ink';
import type { StoreApi } from 'zustand';
import type { CadForgeSettings } from '@cadforge/shared';
import { Agent } from '../agent/agent.js';
import { Session } from '../session/session.js';
import type { BackendClient } from '../backend/client.js';
import { discoverSkills, getSlashCommands } from '../skills/loader.js';
import { Welcome } from './Welcome.js';
import { Repl } from './Repl.js';
import { createUIStore } from './store.js';
import type { UIStore, PermissionRequest } from './store.js';

interface AppProps {
  projectRoot: string;
  settings: CadForgeSettings;
  backendClient: BackendClient;
  sessionId?: string;
  authSource: string;
}

export function App({
  projectRoot,
  settings,
  backendClient,
  sessionId,
  authSource,
}: AppProps): React.ReactElement {
  const { exit } = useApp();

  // Create store once
  const storeRef = useRef<StoreApi<UIStore> | null>(null);
  if (!storeRef.current) {
    storeRef.current = createUIStore();
  }
  const store = storeRef.current;

  // Set auth source
  useEffect(() => {
    store.getState().setAuthSource(authSource);
  }, [authSource, store]);

  // Create agent with permission callback wired to store
  const agentRef = useRef<Agent | null>(null);
  if (!agentRef.current) {
    const session = new Session(projectRoot, sessionId);
    if (sessionId) {
      session.load();
    }

    agentRef.current = new Agent({
      projectRoot,
      settings,
      session,
      backendClient,
      askCallback: (prompt: string) => {
        return new Promise<boolean>((resolve) => {
          // Parse tool name from prompt "Allow ToolName(arg)?"
          const match = prompt.match(/^Allow (\w+)\((.+?)\)\?$/);
          const toolName = match?.[1] ?? 'Unknown';
          const arg = match?.[2] ?? '';

          const req: PermissionRequest = {
            id: `perm-${Date.now()}`,
            toolName,
            toolInput: { _summary: arg },
            resolve,
          };
          store.getState().setPermissionRequest(req);
        });
      },
    });
  }
  const agent = agentRef.current;

  // Discover skills
  const slashCommands = useMemo(() => getSlashCommands(projectRoot), [projectRoot]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      agent.saveSession();
    };
  }, [agent]);

  return (
    <Box flexDirection="column">
      <Welcome
        model={settings.model}
        mode={store.getState().mode}
        authSource={authSource}
        projectRoot={projectRoot}
      />
      <Repl
        store={store}
        agent={agent}
        model={settings.model}
        slashCommands={slashCommands}
        projectRoot={projectRoot}
      />
    </Box>
  );
}
