/**
 * Status bar — shows current mode, model, token count, and status messages.
 * Displayed at the bottom of the terminal.
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { InteractionMode } from '../agent/modes.js';
import { MODE_COLORS } from '../agent/modes.js';

interface StatusBarProps {
  mode: InteractionMode;
  model: string;
  statusText: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  isProcessing: boolean;
}

export function StatusBar({
  mode,
  model,
  statusText,
  totalInputTokens,
  totalOutputTokens,
  isProcessing,
}: StatusBarProps): React.ReactElement {
  const modeColor = MODE_COLORS[mode];
  const tokenStr = totalInputTokens + totalOutputTokens > 0
    ? `${formatTokens(totalInputTokens)}/${formatTokens(totalOutputTokens)}`
    : '';

  return (
    <Box>
      <Text>
        <Text color={modeColor} bold>[{mode.toUpperCase()}]</Text>
        {' '}
        <Text dimColor>{model}</Text>
        {tokenStr ? <Text dimColor> | {tokenStr} tokens</Text> : null}
        {isProcessing && statusText ? (
          <Text color="yellow"> | {statusText}</Text>
        ) : null}
      </Text>
    </Box>
  );
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}
