/**
 * Welcome banner — displayed once at the top of the REPL.
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { InteractionMode } from '../agent/modes.js';
import { MODE_COLORS } from '../agent/modes.js';

interface WelcomeProps {
  model: string;
  mode: InteractionMode;
  authSource: string;
  projectRoot: string;
}

const AUTH_LABELS: Record<string, string> = {
  api_key: 'API key',
  env_token: 'ANTHROPIC_AUTH_TOKEN',
  claude_code: 'Claude Code OAuth',
  ollama: 'Ollama (local)',
  none: 'No credentials',
};

export function Welcome({ model, mode, authSource, projectRoot }: WelcomeProps): React.ReactElement {
  const authLabel = AUTH_LABELS[authSource] ?? authSource;
  const modeColor = MODE_COLORS[mode];

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color="green">
        CadForge v0.1.0
      </Text>
      <Text>
        Model: <Text bold>{model}</Text>  Auth: <Text color={authSource === 'none' ? 'red' : 'green'}>{authLabel}</Text>
      </Text>
      <Text dimColor>Project: {projectRoot}</Text>
      <Text dimColor>
        Mode: <Text color={modeColor}>{mode}</Text>  |  Shift+Tab: cycle modes  |  Ctrl+C: cancel  |  /help: commands
      </Text>
    </Box>
  );
}
