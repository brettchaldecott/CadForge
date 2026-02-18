/**
 * Permission prompt — asks user to allow/deny a tool execution.
 * Captures Y/N keyboard input and resolves the permission promise.
 */

import React from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { PermissionRequest } from './store.js';

interface PermissionProps {
  request: PermissionRequest;
  onResolve: (allowed: boolean) => void;
}

export function Permission({ request, onResolve }: PermissionProps): React.ReactElement {
  const { isRawModeSupported } = useStdin();

  useInput((input, key) => {
    const lower = input.toLowerCase();
    if (lower === 'y' || key.return) {
      onResolve(true);
    } else if (lower === 'n' || key.escape) {
      onResolve(false);
    }
  }, { isActive: isRawModeSupported });

  const inputSummary = formatToolInput(request.toolName, request.toolInput);

  return (
    <Box flexDirection="column" borderStyle="round" borderColor="yellow" paddingX={1}>
      <Text color="yellow" bold>Permission Required</Text>
      <Text>
        Allow <Text bold color="cyan">{request.toolName}</Text>?
      </Text>
      {inputSummary && (
        <Box marginLeft={2}>
          <Text dimColor>{inputSummary}</Text>
        </Box>
      )}
      <Text>
        Press <Text bold color="green">Y</Text> to allow, <Text bold color="red">N</Text> to deny
      </Text>
    </Box>
  );
}

function formatToolInput(toolName: string, input: Record<string, unknown>): string {
  switch (toolName) {
    case 'Bash':
      return (input.command as string) ?? '';
    case 'WriteFile':
      return (input.path as string) ?? '';
    case 'ExecuteCadQuery':
      return (input.output_name as string) ?? (input.code as string)?.slice(0, 80) ?? '';
    case 'ExportModel':
      return `${input.source ?? ''} -> ${input.format ?? ''}`;
    default: {
      const keys = Object.keys(input);
      if (keys.length === 0) return '';
      return keys.map((k) => `${k}: ${truncate(String(input[k]), 60)}`).join(', ');
    }
  }
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max) + '...';
}
